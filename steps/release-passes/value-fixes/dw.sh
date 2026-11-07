#!/usr/bin/env bash
# Run SQL against work.duckdb (nice, 6 GB). Usage: dw.sh -c SQL | dw.sh FILE.sql
export PATH="/nix/var/nix/profiles/default/bin:$PATH" TMPDIR=/tmp
D=/nix/store/9wc1c1k7dw67lkzxdvg68cfvwi0lxylw-duckdb-1.5.1/bin/duckdb
cd "$(dirname "$0")"
if [ "$1" = "-c" ]; then exec nice -n 10 "$D" -markdown work.duckdb -c "SET memory_limit='6GB'" -c "$2"
else exec nice -n 10 "$D" -markdown work.duckdb -c "SET memory_limit='6GB'" -f "$1"; fi
