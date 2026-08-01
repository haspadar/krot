#!/bin/bash
# Rebuild one GoAccess report per site. Managed by Ansible (role: goaccess).
#
# Each site gets its own report and its own database. There is deliberately no
# combined report: one page listing every domain is where the link between the
# sites of a network becomes visible to whoever gets hold of it.
set -euo pipefail

CONF=/etc/goaccess/krot-sites.conf
REPORT_DIR="${REPORT_DIR:-/var/www/goaccess}"
DB_DIR="${DB_DIR:-/var/lib/goaccess}"

if [ ! -r "$CONF" ]; then
    echo "missing site list: $CONF" >&2
    exit 1
fi

status=0

while IFS='|' read -r domain log; do
    # Blank lines and comments in the generated list.
    case "$domain" in ''|\#*) continue ;; esac

    db="$DB_DIR/$domain"
    out="$REPORT_DIR/$domain.html"
    # The temporary name has to end in .html too: GoAccess picks its output
    # format from the extension, and for anything it does not recognise it
    # writes nothing at all — successfully, without a word.
    tmp="$REPORT_DIR/.$domain.new.html"
    mkdir -p "$db"

    # --persist keeps counts across runs, so history outlives the log files it
    # came from: without it, every logrotate would reset the numbers to whatever
    # is still on disk. --restore reads that state back before parsing.
    #
    # Only the live log is fed in. Rotated files were already counted into the
    # database on an earlier run, and feeding them again would double every hit
    # they hold.
    if [ ! -r "$log" ]; then
        # A site whose log has not been written yet is not an error: nginx
        # creates the file on the first request.
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
    if ! { grep '^\[' "$log" || true; } | goaccess - \
        --config-file="$CONF" \
        --db-path="$db" \
        --persist --restore \
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
