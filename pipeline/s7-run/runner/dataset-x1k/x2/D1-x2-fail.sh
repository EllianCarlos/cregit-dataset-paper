#!/usr/bin/env bash
# D1-x2-fail.sh (the X2 merge machine, read-only, through x2/ssm-x2.sh): why rows fail. The FAIL lines
# by minute, the aws CLI error lines of merge.log (lines that do not start with '['), the time of the
# first and the last FAIL, and the number of aws processes now.
set -uo pipefail
OUT=/data1/x2/out; LOG=$OUT/merge.log
echo "== $(date -u +%FT%TZ)"
echo "--- FAIL lines by minute"
grep -a '\] FAIL ' $LOG | cut -c2-17 | sort | uniq -c | tail -20
echo "--- FAIL kinds"
grep -a '\] FAIL ' $LOG | sed -E 's/^\[[^]]*\] FAIL [^:]*: //' | cut -c1-40 | sort | uniq -c | sort -rn | head
echo "--- other lines (aws errors), counted"
grep -a -v '^\[' $LOG | sed -E 's/[A-Za-z0-9._-]+-dataset\.parquet/<file>/g; s#s3://[^ ]*#<s3>#g' | cut -c1-160 | sort | uniq -c | sort -rn | head -15
echo "--- aws processes now: $(pgrep -c -x aws || true); python: $(pgrep -c python || true)"
