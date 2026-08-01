#!/bin/bash
# Rebuild one GoAccess report per site. Managed by Ansible (role: goaccess).
#
# Each site gets its own report. There is deliberately no
# combined report: one page listing every domain is where the link between the
# sites of a network becomes visible to whoever gets hold of it.
set -euo pipefail

CONF=/etc/goaccess/krot-sites.conf
REPORT_DIR="${REPORT_DIR:-/var/www/goaccess}"
# Reports are built here and moved into place. Inside REPORT_DIR, because a move
# is only atomic within one filesystem and a role that runs on machines it has
# never seen cannot assume /var/www and /var/lib share one. The vhost refuses
# this directory, so a half-written report is not reachable while it is written.
WORK_DIR="$REPORT_DIR/.build"

if [ ! -r "$CONF" ]; then
    echo "missing site list: $CONF" >&2
    exit 1
fi

status=0

mkdir -p "$WORK_DIR"

# Drop reports for sites that are no longer listed. A vhost can be removed or a
# domain retired, and the report would otherwise stay served for as long as the
# machine lives — still naming the domain and its traffic to anyone who kept the
# URL.
listed=$(cut -d'|' -f1 "$CONF.sites" | grep -v '^[[:space:]]*\(#\|$\)' || true)

for report in "$REPORT_DIR"/*.html; do
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
    # Built outside the served directory: a half-written report under the
    # document root is reachable at a predictable path while it is being
    # written, and nothing in the vhost refuses dotfiles. It still has to end in
    # .html — GoAccess picks its output format from the extension, and for
    # anything it does not recognise it writes nothing at all, successfully and
    # without a word.
    tmp="$WORK_DIR/$domain.html"

    if [ ! -r "$log" ]; then
        # A site whose log has not been written yet is not an error: nginx
        # creates the file on the first request.
        continue
    fi

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
    sources=()
    for candidate in $(ls -1r "$log".*.gz 2>/dev/null); do
        sources+=("$candidate")
    done
    [ -r "$log.1" ] && sources+=("$log.1")
    sources+=("$log")

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
    # need no special case.
    if ! { zcat -f "${sources[@]}" 2>/dev/null | grep '^\[' || true; } | goaccess - \
        --config-file="$CONF" \
        --output="$tmp"; then
        echo "report failed: $domain" >&2
        status=1
        rm -f "$tmp"
        continue
    fi

    # A site with no traffic yet leaves GoAccess with nothing to write, and it
    # produces no file rather than an empty one. Not a failure — but without
    # this check the mv below would fail and take the remaining sites' reports
    # down with it.
    if [ ! -f "$tmp" ]; then
        continue
    fi

    # Rename last: a half-written report is never served, and a reader either
    # gets the previous one or the new one, never a truncated page.
    mv "$tmp" "$out"
    chmod 0644 "$out"
done < "$CONF.sites"

exit "$status"
