#!/bin/bash
# Bring the running server up to the config files, asking the server rather than
# guessing. Output, one line each, all optional:
#   reloaded                    the server re-read its config
#   overridden: <name by file:line; ...>
#                               settings of this file a later source wins over
#   restart: <names>            settings only a restart applies
# Exit codes: 0 with the output above; 64, touching nothing, when the files hold a
# value a starting server would refuse — the one failure the role answers by putting
# the previous file back; anything else (3 from this script, 2 or 3 from psql, 2 from
# sed) is a failure that rolls nothing back. 64 because psql and sed exit 2 on their
# own (no connection, no file), and set -e passes that through: 2 cannot mean refusal.
#
# - `postgres -C` reads every file as a starting server would and fails on an
#   invalid value anywhere, so the check comes before any reload: a reload of such
#   a file would still apply its valid lines. It is a check, not a comparison —
#   the same value prints differently from -C and from pg_settings (file modes in
#   octal, an extension's setting as raw text until its library loads), and
#   comparing them restarted or reloaded on every run. pg_file_settings messages
#   cannot decide either: "setting could not be applied" covers a restart-only
#   change and an invalid value alike.
# - Reload when any config source is newer than the server's last load: this
#   file, or postgresql.auto.conf after an ALTER SYSTEM RESET, which reloads
#   nothing by itself. A run that stopped after writing the file is finished by
#   the next one.
# - Overridden: a later assignment of the same name in another file (by seqno —
#   the winner may itself be pending a restart, so `applied` cannot tell).
#   postgresql.auto.conf, written by ALTER SYSTEM, is read after conf.d. Reported,
#   not failed here, so the role still restarts with its rollback before refusing.
# - pending_restart is then the server's list of changed postmaster-level settings
#   it accepted but cannot apply live, a setting dropped from the file included.
#
# Nor does -C check an extension's settings: the library is not loaded in it, so
# they stay raw text. The role asserts pg_stat_statements' own values instead.
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

if [ ! -x "$postgres" ]; then
    echo "no PostgreSQL $version server binary at $postgres" >&2
    exit 3
fi
if ! refusal=$("$postgres" -D "$confdir" -C max_connections 2>&1 >/dev/null); then
    printf 'the server refused the configuration: %s\n' "$refusal" >&2
    exit 64
fi

# The port the running postmaster listens on, not the one the new file asks for:
# a changed port is exactly a setting that is pending until the restart.
port=$(sed -n 4p "$datadir/postmaster.pid")

q() {
    psql -XAtq -p "$port" -v ON_ERROR_STOP=1 -c "$1"
}

# A path spelled differently from the server's would match no row below and turn
# every check into a silent pass.
if [ "$(q "SELECT count(*) FROM pg_file_settings WHERE sourcefile = '$file'")" = 0 ]; then
    echo "the server reads no setting from $file" >&2
    exit 3
fi

# The file times have whole seconds only, so a load in the same second as a write
# counts as older: the file may have been written just after it. Assigned, never
# tested inline: a failing psql inside `[ "$(...)" = t ]` escapes set -e and reads
# as "not stale", skipping the reload without a word.
#
# Times alone miss a source that is gone: an overriding conf.d file deleted or
# emptied without a reload leaves pg_file_settings, so there is no newer time to
# see, while the server still runs its value. Hence the second half: a role line
# no later file overrides, whose running value the server takes from anywhere
# but this file and is not waiting on a restart for, is stale whatever the times.
# Postmaster-level settings stay out: a reload that finds one unchanged keeps the
# source it had at start (port, listen_addresses from postgresql.conf), so it would
# read as stale forever — and a changed one is pending_restart, handled below.
stale="SELECT date_trunc('second', pg_conf_load_time()) <= (
           SELECT max((pg_stat_file(f, true)).modification)
             FROM (SELECT DISTINCT sourcefile FROM pg_file_settings
                   UNION SELECT current_setting('data_directory') || '/postgresql.auto.conf'
                   UNION SELECT '$file') AS sources(f))
        OR EXISTS (
           SELECT 1 FROM pg_file_settings o JOIN pg_settings s ON lower(s.name) = lower(o.name)
            WHERE o.sourcefile = '$file'
              AND NOT EXISTS (SELECT 1 FROM pg_file_settings w
                               WHERE lower(w.name) = lower(o.name) AND w.seqno > o.seqno)
              AND s.sourcefile IS DISTINCT FROM '$file'
              AND NOT s.pending_restart
              AND s.context NOT IN ('postmaster', 'internal'))"
is_stale=$(q "$stale")
if [ "$is_stale" = t ]; then
    # A reload is a signal; a backend forked after the postmaster re-read the files
    # inherits the new load time and the pending flags. Sent again until the load
    # lands in a later second than the write — a repeated reload changes nothing.
    for _ in $(seq 1 40); do
        q "SELECT pg_reload_conf()" >/dev/null
        sleep 0.25
        is_stale=$(q "$stale")
        [ "$is_stale" = f ] && break
    done
    if [ "$is_stale" = t ]; then
        echo "the server did not reload its configuration within 10 seconds" >&2
        exit 3
    fi
    echo reloaded
fi

overridden=$(q "SELECT coalesce(string_agg(DISTINCT o.name || ' by ' || w.sourcefile || ':' || w.sourceline, '; '), '')
                  FROM pg_file_settings o
                  JOIN pg_file_settings w
                    ON lower(w.name) = lower(o.name) AND w.seqno > o.seqno AND w.sourcefile <> o.sourcefile
                 WHERE o.sourcefile = '$file'")
if [ -n "$overridden" ]; then
    echo "overridden: $overridden"
fi

pending=$(q "SELECT coalesce(string_agg(name, ', ' ORDER BY name), '') FROM pg_settings WHERE pending_restart")
if [ -n "$pending" ]; then
    echo "restart: $pending"
fi
