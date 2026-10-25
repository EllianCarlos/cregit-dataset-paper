#!/usr/bin/env bash
# D8-rate.sh, machine A (read-only, through scripts/a/ssm-a.sh): per active row, the .blame files
# (out/<p>/blame) finished in each of the last 20 hours (by mtime) with their MB, and the running git blame
# processes of the row (count, and the age of the oldest 3 in s).
set -uo pipefail
L=/data/x1k-long; now=$(date +%s)
echo "== $(date -u +%FT%TZ)"
for p in $(cat $L/run.list); do R=$(readlink -f $L/$p)
  systemctl is-active -q x1k-long@$p || continue
  W=$R/out/$p/blame
  echo "--- $p"
  find "$W" -name '*.blame' -newermt '-20 hours' -printf '%T@ %s\n' 2>/dev/null \
    | awk -v now=$now '{h=int((now-$1)/3600); n[h]++; b[h]+=$2} END {for (h=19; h>=0; h--) printf "  %2d-%2d h ago: %6d files %8.1f MB\n", h+1, h, n[h], b[h]/1e6}'
  pids=$(pgrep -x git | while read q; do c=$(readlink /proc/$q/cwd 2>/dev/null); case $c in "$R"/*) echo $q;; esac; done)
  n=$(echo "$pids" | grep -c . || true)
  ages=$(for q in $pids; do ps -o etimes= -p $q; done | sort -n | tail -3 | tr -s ' \n' ' ')
  echo "  running git processes in the row: $n; oldest (s): $ages"
done
