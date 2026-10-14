#!/usr/bin/env bash
# One check of git.savannah.gnu.org (at most one each 30 minutes, decided
# 2026-10-10): a smart-HTTP ref request for one clone URL that Savannah
# publishes (https://savannah.gnu.org/git/?group=bash). Appends to host_checks.tsv.
set -u
cd "$(dirname "$0")"
url="https://git.savannah.gnu.org/git/bash.git/info/refs?service=git-upload-pack"
t=$(date -u +%FT%T+00:00)
r=$(curl -s -m 60 -o /dev/null -w '%{http_code}\t%{time_total}' "$url")
[ -f host_checks.tsv ] || printf 'utc\turl\thttp\tseconds\n' > host_checks.tsv
printf '%s\t%s\t%s\n' "$t" "$url" "$r" >> host_checks.tsv
tail -1 host_checks.tsv
