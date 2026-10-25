#!/usr/bin/env bash
# M2-x2-check.sh (the X2 merge machine, read-only, through x2/ssm-x2.sh): progress of x1k-raw.
set -uo pipefail
X=/data/x2; OUT=/data1/x2/out
echo "== $(date -u +%FT%TZ) run ${X2_RUN:-?} up $(awk '{printf "%.1f h", $1/3600}' /proc/uptime); unit $(systemctl is-active x1k-raw-merge)"
n=$(($(wc -l < $X/inputs.x1k.tsv) - 1)); d=$(($(wc -l < $OUT/results.tsv 2>/dev/null || echo 1) - 1))
echo "results.tsv: $d of $n; failed.tsv lines: $(wc -l < $OUT/failed.tsv 2>/dev/null || echo 0)"
awk -F'\t' 'NR>1 {i+=$9; o+=$10} END {if (i) printf "bytes: in %.2f GB, out %.2f GB (%.1f%%)\n", i/1e9, o/1e9, 100*o/i}' $OUT/results.tsv 2>/dev/null
grep -h 'FAIL\|DONE:\|projects,' $OUT/merge.log 2>/dev/null | tail -5 | cut -c1-220
tail -2 $OUT/merge.log 2>/dev/null | cut -c1-200
for s in DONE ALERT; do [ -f $OUT/$s ] && cat $OUT/$s; done
free -g | sed -n 2p; uptime; df -h --output=target,avail /data1 /data2 | tail -2 | tr '\n' ' '; echo
[ -e /home/ec2-user/NO_SHUTDOWN ] && echo "NO_SHUTDOWN is set"
exit 0
