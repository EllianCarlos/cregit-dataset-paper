#!/usr/bin/env bash
# M6-jobs.sh (spot a, read-only): what each v1-raw job does now (walks /proc, no pgrep -f).
set -uo pipefail
echo "== $(date -u +%FT%TZ)"
for d in /proc/[0-9]*; do
  c=$(tr '\0' ' ' < $d/cmdline 2>/dev/null) || continue
  case "$c" in *rewrite_meta_columns.py*|*validate_schema.py*|*"aws s3"*) ;; *) continue ;; esac
  st=$(awk '{print $3}' $d/stat 2>/dev/null); th=$(awk '/^Threads/ {print $2}' $d/status)
  cpu=$(ps -o pcpu= -p ${d#/proc/} 2>/dev/null)
  echo "$st thr=$th cpu=$cpu $(echo "$c" | grep -o -E 'rewrite_meta_columns.py|validate_schema.py|aws s3 [a-z]+' | head -1) $(echo "$c" | grep -o -E '[A-Za-z0-9._-]+__[A-Za-z0-9._-]+-dataset.parquet' | head -1)"
done | sort | uniq -c | sort -rn | head -60
