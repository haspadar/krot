#!/bin/bash
# Which of this role's settings the running server does not have, and what applying
# them takes. Prints "<context> <name>: <running> -> <files>" for every setting whose
# value as the files say it differs from the value in effect; nothing when current.
#
# Values are compared, not messages: pg_file_settings reports "setting could not be
# applied" both for a change that needs a restart and for an invalid value, so
# reading its errors would restart a server into a config it refuses. `postgres -C`
# reads every file as a starting server would — an invalid value anywhere fails it
# before anything is touched — and prints a value in the same base units as
# pg_settings.setting.
#
# A setting the server still takes from this file but the file no longer names (a
# preload library dropped) is compared too: the files now give it another value.
set -euo pipefail

version=$1
port=$2
file=$3
postgres=/usr/lib/postgresql/$version/bin/postgres
confdir=/etc/postgresql/$version/main

if ! check=$("$postgres" -D "$confdir" -C max_connections 2>&1); then
    printf 'the configuration would not start the server: %s\n' "$check" >&2
    exit 2
fi

psql -XAtq -F '|' -p "$port" -v ON_ERROR_STOP=1 -v file="$file" <<'SQL' |
SELECT name, context, setting FROM pg_settings
 WHERE sourcefile = :'file'
    OR name IN (SELECT name FROM pg_file_settings WHERE sourcefile = :'file' AND name IS NOT NULL)
SQL
while IFS='|' read -r name context running; do
    [ -n "$name" ] || continue
    # The whole config already passed above, so a name -C does not know is one the
    # files dropped: an extension's setting whose library is no longer preloaded.
    wanted=$("$postgres" -D "$confdir" -C "$name" 2>/dev/null) || wanted='(not in the files)'
    # File modes (log_file_mode) show in octal in pg_settings and in decimal from -C:
    # 0640 and 416 are one value, and reading them as two reloaded on every run.
    if [[ $running =~ ^0[0-7]+$ && $wanted =~ ^[0-9]+$ ]]; then
        running=$((8#$running))
    fi
    [ "$wanted" = "$running" ] || printf '%s %s: %s -> %s\n' "$context" "$name" "$running" "$wanted"
done
