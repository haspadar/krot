#!/bin/bash
# Bring the running server up to the config files, asking the server rather than
# guessing. Exits 2, touching nothing, when the files hold a value a starting
# server would refuse; prints "reloaded" when it reloaded and "restart: <names>"
# when only a restart applies what the files now say.
#
# - `postgres -C` reads every file as a starting server would and fails on an
#   invalid value anywhere, so the check comes before any reload: a reload of such
#   a file would still apply its valid lines. It is a check, not a comparison —
#   the same value prints differently from -C and from pg_settings (file modes in
#   octal, an extension's setting as raw text until its library loads), and
#   comparing them restarted or reloaded on every run. pg_file_settings messages
#   cannot decide either: "setting could not be applied" covers a restart-only
#   change and an invalid value alike.
# - Reload when the file is newer than the server's last config load — a run that
#   stopped after writing the file is finished by the next one.
# - pending_restart is then the server's list of changed postmaster-level settings
#   it accepted but cannot apply live, a setting dropped from the file included.
#
# Not caught: a value valid for its setting that still stops the server starting
# (max_connections below the reserved connections, a preload library that is not
# installed) — -C exits before those checks. The role restores the previous file
# and starts the server if the restart fails.
set -euo pipefail

version=$1
file=$2
postgres=/usr/lib/postgresql/$version/bin/postgres
confdir=/etc/postgresql/$version/main
datadir=/var/lib/postgresql/$version/main

if ! refusal=$("$postgres" -D "$confdir" -C max_connections 2>&1 >/dev/null); then
    printf 'the server refused the configuration: %s\n' "$refusal" >&2
    exit 2
fi

# The port the running postmaster listens on, not the one the new file asks for:
# a changed port is exactly a setting that is pending until the restart.
port=$(sed -n 4p "$datadir/postmaster.pid")

q() {
    psql -XAtq -p "$port" -v ON_ERROR_STOP=1 -c "$1"
}

# The file's time has whole seconds only, so a load in the same second as the write
# counts as older: the file may have been written just after it.
# Assigned, never tested inline: a failing psql inside `[ "$(...)" = t ]` escapes
# set -e and reads as "not stale", skipping the reload without a word.
stale="SELECT date_trunc('second', pg_conf_load_time()) <= (pg_stat_file('$file')).modification"
is_stale=$(q "$stale")
if [ "$is_stale" = t ]; then
    # A reload is a signal; a backend forked after the postmaster re-read the file
    # inherits the new load time and the pending flags. Sent again until the load
    # lands in a later second than the write — a repeated reload changes nothing.
    for _ in $(seq 1 40); do
        q "SELECT pg_reload_conf()" >/dev/null
        sleep 0.25
        is_stale=$(q "$stale")
        [ "$is_stale" = f ] && break
    done
    if [ "$is_stale" = t ]; then
        echo "the server did not reload $file within 10 seconds" >&2
        exit 3
    fi
    echo reloaded
fi

pending=$(q "SELECT coalesce(string_agg(name, ', ' ORDER BY name), '') FROM pg_settings WHERE pending_restart")
if [ -n "$pending" ]; then
    echo "restart: $pending"
fi
