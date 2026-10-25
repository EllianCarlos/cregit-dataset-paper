#!/usr/bin/env bash
# M2-check.sh (spot a, read-only): progress of the v1-raw merge.
set -uo pipefail
R=/data1/v1raw
echo "== $(date -u +%FT%TZ)  unit v1raw-merge: $(systemctl is-active v1raw-merge)  $(systemctl show v1raw-merge -p MemoryCurrent | tr '\n' ' ')"
echo "ctp firm pid 1005816: $(grep -q firm_attribution /proc/1005816/cmdline 2>/dev/null && echo alive || echo ended)"
n=$(($(wc -l < $R/inputs.tsv) - 1)); d=$(($(wc -l < $R/out/results.tsv 2>/dev/null || echo 1) - 1)); f=$(wc -l < $R/out/failed.tsv 2>/dev/null || echo 0)
echo "done $d of $n; failed rows $f"
[ -s $R/out/results.tsv ] && awk -F'\t' 'NR>1 {i+=$9; o+=$10; r+=$8} END {if (i) printf "done: %.1f GB in -> %.1f GB out (%.1f%%), %.2f B rows\n", i/1e9, o/1e9, 100*o/i, r/1e9}' $R/out/results.tsv
[ -s $R/out/failed.tsv ] && tail -3 $R/out/failed.tsv | cut -c1-300
tail -4 $R/out/merge.log | cut -c1-200
free -g | sed -n 2p; uptime; df -h /data1 /data2 | tail -2
