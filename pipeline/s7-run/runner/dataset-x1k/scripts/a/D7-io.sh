#!/usr/bin/env bash
# D7-io.sh, machine A (read-only, through scripts/a/ssm-a.sh): CPU and disk wait. vmstat 5 x 6; the
# per-disk use over 10 s from /proc/diskstats; git processes by state (R running, D disk wait,
# S sleep); git blame processes per row with their mean CPU.
set -uo pipefail
echo "== $(date -u +%FT%TZ) $(nproc) vCPU"
vmstat 5 6
echo "--- disk use over 10 s"
a=$(awk '$3 ~ /^nvme[0-9]+n1$/ {print $3, $6, $10, $13}' /proc/diskstats | sort); sleep 10
b=$(awk '$3 ~ /^nvme[0-9]+n1$/ {print $3, $6, $10, $13}' /proc/diskstats | sort)
join <(echo "$a") <(echo "$b") | awk '{printf "%s read %.1f MB/s write %.1f MB/s busy %.0f%%\n", $1, ($5-$2)*512/1e6/10, ($6-$3)*512/1e6/10, ($7-$4)/100}'
lsblk -n -o NAME,SIZE,MOUNTPOINT | grep -E 'nvme' | tr -s ' '
echo "--- git processes by state"
ps -eo stat=,comm= | awk '$2=="git" {print substr($1,1,1)}' | sort | uniq -c
echo "--- git blame processes per row (count, mean CPU %)"
ps -eo pcpu=,args= | awk '$0 ~ /git .*blame/ && $0 !~ /awk/ {r="?"; for (i=1;i<=NF;i++) if ($i=="-C" && $(i+1) ~ /^\//) r=$(i+1); n[r]++; c[r]+=$1}
  END {for (k in n) printf "%s n=%d mean_cpu=%.0f%%\n", k, n[k], c[k]/n[k]}' | sed -E 's#/out/.*##'
echo "--- pressure stall (some = share of time a task waited)"
for f in cpu io memory; do echo "$f: $(head -1 /proc/pressure/$f)"; done
