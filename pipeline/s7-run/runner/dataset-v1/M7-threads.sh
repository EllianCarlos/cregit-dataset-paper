#!/usr/bin/env bash
# M7-threads.sh (spot a, read-only): thread states and wait channels of two v1-raw jobs; the output growth of one.
set -uo pipefail
echo "== $(date -u +%FT%TZ)"
n=0
for d in /proc/[0-9]*; do
  c=$(tr '\0' ' ' < $d/cmdline 2>/dev/null) || continue
  case "$c" in *rewrite_meta_columns.py*torvalds__linux*|*rewrite_meta_columns.py*llvm__llvm-project*) ;; *) continue ;; esac
  p=${d#/proc/}; echo "-- pid $p $(echo "$c" | grep -o -E '[A-Za-z0-9._-]+__[A-Za-z0-9._-]+-dataset.parquet' | head -1)"
  for t in $d/task/*; do echo "$(awk '{print $3}' $t/stat) $(cat $t/wchan 2>/dev/null)"; done | sort | uniq -c | sort -rn | head -8
  grep -E 'voluntary_ctxt|Threads' $d/status
  echo "utime+stime ticks: $(awk '{print $14+$15}' $d/stat)"; sleep 5; echo "after 5 s: $(awk '{print $14+$15}' $d/stat)"
  n=$((n+1)); [ $n -ge 2 ] && break
done
f=/data1/v1raw/out/parquet/torvalds__linux-dataset.parquet; a=$(stat -c %s $f); sleep 20; b=$(stat -c %s $f); echo "torvalds output: $a -> $b in 20 s"
grep -c . /data1/v1raw/out/rewrite.tsv 2>/dev/null; tail -3 /data1/v1raw/out/merge.log | cut -c1-200
