#!/bin/bash
# Rebuild one GoAccess report per site. Managed by Ansible (role: goaccess).
#
# Each site gets its own report. There is deliberately no combined one: one page listing every domain is where the link between the
# sites of a network becomes visible to whoever gets hold of it.
set -euo pipefail

CONF=/etc/goaccess/krot-sites.conf
# Agents to treat as crawlers in the humans report beyond the ones GoAccess
# knows. Written by Ansible; absent when the humans report is switched off.
CRAWLERS="${CRAWLERS:-/etc/goaccess/krot-crawlers.list}"
REPORT_DIR="${REPORT_DIR:-/var/www/goaccess}"
# The second report per site: the same log read again with crawlers filtered
# out. Kept in a subdirectory rather than as <domain>-humans.html so that
# anything listing the reports by *.html still sees one file per domain and does
# not have to know the suffix. Measured on berlindame.de 2026-08-02: 94 unique
# visitors with crawlers, 37 without — the full report cannot answer "how many
# people",
# and a report without bots cannot show whether Googlebot is coming at all, so
# both are kept.
HUMANS_DIR="$REPORT_DIR/${HUMANS_SUBDIR:-humans}"
BUILD_HUMANS="${BUILD_HUMANS:-1}"

# One build at a time. The timer and an Ansible run can land together — more
# easily than it sounds, because Persistent=true fires a missed build as soon as
# the machine is back — and the second one clears the work directory out from
# under the first, which then fails moving a report that is no longer there.
# Re-executing under flock rather than waiting: a build that is already running
# produces the same reports this one would.
if [ -z "${GOACCESS_REPORTS_LOCKED:-}" ]; then
    export GOACCESS_REPORTS_LOCKED=1
    # --conflict-exit-code, because plain --nonblock exits 1 on a held lock and
    # systemd would record a failed unit for what is the intended outcome. 0
    # says the reports are being rebuilt, just not by this process.
    exec flock --nonblock --conflict-exit-code 0 "$REPORT_DIR" "$0" "$@"
fi
# Reports are built here and moved into place. Inside REPORT_DIR, because a move
# is only atomic within one filesystem and a role that runs on machines it has
# never seen cannot assume /var/www and /var/lib share one. The name starts with
# a dot and the reports are addressed by domain, so nothing that serves them by
# name will hand out a half-written one.
WORK_DIR="$REPORT_DIR/.build"

if [ ! -r "$CONF" ]; then
    echo "missing site list: $CONF" >&2
    exit 1
fi

# Checked before anything below removes a path built from it: an empty or
# mistyped REPORT_DIR would otherwise turn the cleanup into a delete somewhere
# else entirely.
if [ ! -d "$REPORT_DIR" ]; then
    echo "missing report directory: $REPORT_DIR" >&2
    exit 1
fi

status=0

# The setgid bit on REPORT_DIR is what gives a report the group that reads it —
# this account is deliberately not a member of that group, so it cannot set it
# itself. A file built in .build/ takes the group of *that* directory and mv
# does not change it, so .build/ has to carry the bit and the group as well.
#
# Recreated from scratch each run rather than reused: that way it inherits both
# from REPORT_DIR every time, including on a machine where an earlier version
# left the directory behind with the wrong group. Nothing outlives a run in
# here — a leftover is a report whose build was interrupted.
rm -rf "$WORK_DIR"
# Same narrowed umask as the humans directory below, and for the same reason:
# while a build is running this holds finished reports, and the caller's umask
# would leave it 2775 or 2755 — readable to every account on the machine, with
# only the closed parent standing in the way.
(umask 0027 && mkdir "$WORK_DIR")

# Same inheritance as .build/: created under REPORT_DIR so the setgid bit gives
# it the group that reads the reports. Not recreated each run, because unlike
# .build/ its contents are what gets served — but mkdir -p is enough, since a
# directory that already exists was made the same way.
if [ "$BUILD_HUMANS" = "1" ]; then
    # Made by Ansible with the mode it needs; this only covers a directory
    # removed between runs. The umask is narrowed for the mkdir alone, because
    # the caller's decides the mode here and neither candidate is right: 0002
    # gives 2775, a plain 0022 host gives 2755, and the file names in this
    # directory are the list of domains on the machine.
    #
    # Deliberately a umask rather than a chmod afterwards. This account is not
    # in the group that owns the directory, and for such a user the kernel drops
    # S_ISGID on *any* chmod while reporting success — measured: a chmod o-rwx,
    # which does not name the bit at all, turned 2750 into 750. Reports would
    # then be written into a group nothing else can read. A umask never touches
    # the bit: measured 2750 under both 0002 and 0022.
    (umask 0027 && mkdir -p "$HUMANS_DIR")
fi

# Drop reports for sites that are no longer listed. A vhost can be removed or a
# domain retired, and the report would otherwise stay served for as long as the
# machine lives — still naming the domain and its traffic to anyone who kept the
# URL.
listed=$(cut -d'|' -f1 "$CONF.sites" | grep -v '^[[:space:]]*\(#\|$\)' || true)

# Both directories, not just the top one: the humans report of a retired domain
# would otherwise sit there for the life of the machine, still naming the domain
# and its traffic — the very thing this loop exists to prevent.
for report in "$REPORT_DIR"/*.html "$HUMANS_DIR"/*.html; do
    [ -e "$report" ] || continue
    domain=$(basename "$report" .html)

    if ! printf '%s\n' "$listed" | grep -qxF "$domain"; then
        rm -f "$report"
    fi
done

while IFS='|' read -r domain log; do
    # Blank lines and comments in the generated list.
    case "$domain" in ''|\#*) continue ;; esac

    out="$REPORT_DIR/$domain.html"
    # Built out of sight: a half-written report under the document root is
    # reachable at a predictable path while it is being written. It still has to
    # end in .html — GoAccess picks its output format from the extension.
    tmp="$WORK_DIR/$domain.html"
    humans_out="$HUMANS_DIR/$domain.html"
    humans_tmp="$WORK_DIR/$domain.humans.html"

    # Every log still on disk, oldest first, read from scratch on each run.
    #
    # The obvious alternative — GoAccess's --persist/--restore — is wrong here.
    # It accumulates whatever it is given on top of what it stored, and it does
    # not remember which lines it has already seen, so re-reading a log that has
    # not rotated yet counts its requests a second time. Measured: three
    # requests reported as 3, 5, 7, 9 over four consecutive builds. Persistence
    # is built for feeding strictly new input, which a file still being appended
    # to cannot provide.
    #
    # Rebuilding instead means the numbers depend only on what is on disk, and
    # the window is exactly the retention logrotate is configured for. Reading a
    # fortnight of one site's logs takes well under a second.
    # Oldest first. logrotate numbers upwards as files age, so a reverse sort of
    # the compressed generations puts them in chronological order; .1 is the
    # newest rotated one and delaycompress leaves it uncompressed.
    sources=()
    while IFS= read -r candidate; do
        # A glob that matches nothing comes back as the pattern itself.
        [ -r "$candidate" ] && sources+=("$candidate")
    done < <(printf '%s\n' "$log".*.gz | sort -rV)
    [ -r "$log.1" ] && sources+=("$log.1")
    # The live log last, and only if it is there — nginx creates it on the first
    # request, so a site that has had none simply has no live log yet.
    [ -r "$log" ] && sources+=("$log")

    # No readable source at all: the site is new, or its logs were moved or
    # removed. Either way any report from an earlier run goes — a report with
    # nothing behind it is the one thing this must not keep serving. Checked
    # against the whole set rather than the live log alone, so a site whose
    # recent traffic sits in rotated files keeps its report.
    if [ ${#sources[@]} -eq 0 ]; then
        rm -f "$out" "$humans_out"
        continue
    fi

    # Only lines that start with a timestamp are fed in. GoAccess has no
    # tolerance setting: when every line it manages to read is unparseable it
    # gives up on the file entirely rather than skipping those lines. A log
    # still holding entries from before the format carried a time would
    # therefore produce no report at all until it rotated out — which is
    # precisely when a new report matters most.
    # `|| true` because grep exits 1 when it matches nothing, and under
    # pipefail that would read as a failed report rather than as a site with no
    # traffic yet.
    # zcat -f reads compressed and plain files alike, so rotated generations
    # need no special case. The parseable lines are counted first: reading from
    # stdin, GoAccess writes a report whatever it is given, so an empty input
    # produces a page of zeroes rather than nothing — and this is the only place
    # that can tell the difference.
    parseable=$(zcat -f "${sources[@]}" 2>/dev/null | grep -c '^\[' || true)

    # Either the site has had no traffic yet, or its last requests have rotated
    # off the disk. Any previous report goes: now that the numbers are rebuilt
    # from what is on disk, one that outlived its logs would keep showing
    # traffic no source still holds — quietly, for as long as the machine runs.
    if [ "$parseable" -eq 0 ]; then
        rm -f "$out" "$humans_out"
        continue
    fi

    # Kept on disk rather than piped twice: the same lines feed both reports, and
    # decompressing a fortnight of rotated logs a second time buys nothing.
    lines="$WORK_DIR/$domain.log"
    { zcat -f "${sources[@]}" 2>/dev/null | grep '^\[' || true; } > "$lines"

    if ! goaccess - --config-file="$CONF" --output="$tmp" < "$lines"; then
        # The previous report goes too. `grep '^\['` only proves a line starts
        # with a bracket, not that GoAccess can read it, so a format change can
        # land here with a report still on disk — and a stale page that nothing
        # can refresh is worse than an absent one, because it looks current.
        # The humans report goes with it: half a pair, silently older than the
        # page beside it, is worse than none.
        echo "report failed: $domain" >&2
        status=1
        rm -f "$tmp" "$out" "$humans_out" "$lines"
        continue
    fi

    # The same lines again, minus the crawlers. GoAccess decides what a crawler
    # is from the user agent, so this is a filter on the data, not a different
    # set of panels: referrers, countries and everything else appear in both,
    # counted over a different set of visitors.
    #
    # --unknowns-as-crawlers is deliberately left out: measured on berlindame.de
    # it moved the count by a single visit out of 36, which does not justify a
    # flag whose meaning a reader would have to look up.
    #
    # Built before the full report is moved into place, so the pair appears
    # together: a fresh humans page next to a full one still showing yesterday
    # invites exactly the wrong comparison.
    humans_built=0
    if [ "$BUILD_HUMANS" = "1" ]; then
        # -b adds to GoAccess's own browsers.list rather than replacing it, so
        # the agents it already knows stay filtered. Only passed if the file is
        # there: an unreadable one makes GoAccess exit, and losing the humans
        # report over a missing list is worse than a report with more bots in
        # it. Every name in it is one --ignore-crawlers does not catch, because
        # the agent never calls itself a bot.
        humans_args=(--ignore-crawlers)
        [ -r "$CRAWLERS" ] && humans_args+=(-b "$CRAWLERS")

        if goaccess - --config-file="$CONF" "${humans_args[@]}" \
            --output="$humans_tmp" < "$lines"; then
            humans_built=1
        else
            # The full report still stands — it was built from the same lines and
            # is not in doubt. Only the humans one is dropped, so a stale copy is
            # never served beside a fresh page.
            echo "humans report failed: $domain" >&2
            status=1
            rm -f "$humans_tmp" "$humans_out"
        fi
    fi

    rm -f "$lines"

    # Rename last: a half-written report is never served, and a reader either
    # gets the previous one or the new one, never a truncated page.
    mv "$tmp" "$out"

    if [ "$humans_built" = "1" ]; then
        mv "$humans_tmp" "$humans_out"
        chmod 0640 "$humans_out"
    fi
    # Readable by the account that serves it and by nobody else. The directory
    # is closed already, but a report is the traffic of a domain and there is no
    # reason for a second pair of eyes on the machine to have it.
    #
    # The group is not set here: it comes from the setgid bit on the directory,
    # because this account is deliberately not a member of the group that reads
    # the reports, and chgrp into a group you are not in is refused for anyone
    # but root. Setgid has the kernel do it instead — including for the file
    # built in .build/ and moved in, since that directory inherits the bit too.
    chmod 0640 "$out"
done < "$CONF.sites"

exit "$status"
