#!/bin/bash
# Bring the running server up to this role's config file, asking the server rather
# than guessing. Prints "reloaded" when it reloaded and "restart: <names>" when only
# a restart applies what the files now say; exits 2 naming any value the server
# refused, after which nothing is restarted.
#
# The server's own verdict decides, not a comparison of values: the same setting
# prints differently from `postgres -C` and from pg_settings (file modes in octal,
# an extension's setting as raw text until its library loads), and every such
# difference became a reload or a restart on every run. Nor do pg_file_settings
# messages: "setting could not be applied" covers a restart-only change and an
# invalid value alike.
#
# - Reload when the file is newer than the server's last config load — a run that
#   stopped after writing the file is finished by the next one.
# - pending_restart is then the server's list of changed postmaster-level settings
#   it accepted but cannot apply live, a setting dropped from the file included.
#   It is set only for a valid value: an invalid one is refused and not applied.
set -euo pipefail

version=$1
file=$2
datadir=/var/lib/postgresql/$version/main

# The port the running postmaster listens on, not the one the new file asks for:
# a changed port is exactly a setting that is pending until the restart.
port=$(sed -n 4p "$datadir/postmaster.pid")

q() {
    psql -XAtq -p "$port" -v ON_ERROR_STOP=1 -c "$1"
}

# The file's time has whole seconds only, so a load in the same second as the write
# counts as older: the file may have been written just after it.
stale="SELECT date_trunc('second', pg_conf_load_time()) <= (pg_stat_file('$file')).modification"
if [ "$(q "$stale")" = t ]; then
    # A reload is a signal; a backend forked after the postmaster re-read the file
    # inherits the new load time and the pending flags. Sent again until the load
    # lands in a later second than the write — a repeated reload changes nothing.
    for _ in $(seq 1 40); do
        q "SELECT pg_reload_conf()" >/dev/null
        sleep 0.25
        [ "$(q "$stale")" = f ] && break
    done
    if [ "$(q "$stale")" = t ]; then
        echo "the server did not reload $file within 10 seconds" >&2
        exit 3
    fi
    echo reloaded
fi

refused=$(q "SELECT coalesce(string_agg(DISTINCT coalesce(f.name, '?') || ' (' || f.error || ')', '; '), '')
               FROM pg_file_settings f
              WHERE f.error IS NOT NULL
                AND f.error NOT LIKE '%cannot be changed without restarting the server'
                AND NOT EXISTS (SELECT 1 FROM pg_settings s WHERE s.name = f.name AND s.pending_restart)")
if [ -n "$refused" ]; then
    echo "the server refused: $refused" >&2
    exit 2
fi

pending=$(q "SELECT coalesce(string_agg(name, ', ' ORDER BY name), '') FROM pg_settings WHERE pending_restart")
if [ -n "$pending" ]; then
    echo "restart: $pending"
fi
