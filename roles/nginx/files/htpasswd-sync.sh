#!/usr/bin/env bash
#
# Writes an apr1 htpasswd entry only when the stored hash does not already match
# the given password. openssl salts every run differently, so writing
# unconditionally would report a change on every play and churn the file.
#
# Usage: htpasswd-sync.sh <file> <user> <password>
# Exits 0 unchanged, 10 when it rewrote the file.
set -euo pipefail

file=$1
user=$2
password=$3

if [ -f "$file" ]; then
    stored=$(cut -d: -f2- "$file")
    salt=$(printf '%s' "$stored" | cut -d'$' -f3)
    if [ -n "$salt" ] && [ "$(openssl passwd -apr1 -salt "$salt" "$password")" = "$stored" ]; then
        exit 0
    fi
fi

printf '%s:%s\n' "$user" "$(openssl passwd -apr1 "$password")" >"$file"
exit 10
