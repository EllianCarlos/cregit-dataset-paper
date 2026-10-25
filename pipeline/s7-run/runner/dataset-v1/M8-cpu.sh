#!/usr/bin/env bash
# M8-cpu.sh (spot a, read-only): CPU ticks of every v1-raw rewrite job over 30 s, with RSS and output growth.
set -uo pipefail
declare -A t0 f0 name
for d in /proc/[0-9]*; do
  c=$(tr '\0' ' ' < $d/cmdline 2>/dev/null) || continue
  case "$c" in *rewrite_meta_columns.py*) ;; *) continue ;; esac
  p=${d#/proc/}; n=$(echo "$c" | grep -o -E '\-\-out [^ ]+' | cut -d' ' -f2)
  name[$p]=$n; t0[$p]=$(awk '{print $14+$15}' $d/stat); f0[$p]=$(stat -c %s $n 2>/dev/null || echo 0)
done
sleep 30
for p in "${!name[@]}"; do
  [ -d /proc/$p ] || { echo "ended $(basename ${name[$p]})"; continue; }
  t1=$(awk '{print $14+$15}' /proc/$p/stat); f1=$(stat -c %s ${name[$p]} 2>/dev/null || echo 0)
  rss=$(awk '/VmRSS/ {print int($2/1024)}' /proc/$p/status)
  echo "$(( (t1-t0[$p])/30 ))% cpu  rss ${rss}M  +$(( (f1-f0[$p])/1024 ))K  $(basename ${name[$p]})"
done | sort -rn | awk '{print} {split($1,a,"%"); if (a[1]>=50) hi++; else lo++} END {print "jobs >=50% cpu:", hi+0, " below:", lo+0}'
grep -c '^processor' /proc/cpuinfo; cat /sys/fs/cgroup/system.slice/v1raw-merge.service/cpu.max 2>/dev/null; cat /sys/fs/cgroup/system.slice/v1raw-merge.service/cpu.stat 2>/dev/null | head -6
