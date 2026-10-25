#!/usr/bin/env bash
# M2-x3-check.sh (the x1k links machine, read-only, through x3/ssm-x3.sh): progress of the unit
# x1k-links. Counts and file names only.
set -uo pipefail
X=/data/x3; W=$X/work; O=$X/out
echo "== $(date -u +%FT%TZ) run ${X3_RUN:-?} up $(awk '{printf "%.1f h", $1/3600}' /proc/uptime); unit $(systemctl is-active x1k-links)"
for k in v1 x1k; do
  dl=$([ -s $X/raw-$k/DOWNLOADED ] && echo "downloaded $(cat $X/raw-$k/DOWNLOADED)" || echo "download: $(find $X/raw-$k/parquet -name '*.parquet' 2>/dev/null | wc -l) files, $(du -sh $X/raw-$k 2>/dev/null | cut -f1)")
  n=$(($(wc -l < $W/$k/inputs.tsv 2>/dev/null || echo 1) - 1)); c=$(find $W/$k/cache -name '*.parquet' ! -name '.*' 2>/dev/null | wc -l)
  echo "$k: $dl; cache $c of $n; $(grep -c '^FAIL' $W/$k/extract.log 2>/dev/null || echo 0) FAIL lines"
done
echo "PLAIN-BLAME logs: $(find $X/pb -name 'pipeline-*.log' 2>/dev/null | wc -l) pipeline logs, $(find $X/pb -name plainblame.log 2>/dev/null | wc -l) extra logs"
grep -h 'FAIL\|OK\|DIFFERENT\|x1k-links' $O/gate-v1.txt $O/check-merged.txt $O/DONE $O/ALERT 2>/dev/null | cut -c1-200
tail -6 $X/run.log 2>/dev/null | cut -c1-200
free -g | sed -n 2p; uptime; df -h --output=target,avail /data1 | tail -1
[ -e /home/ec2-user/NO_SHUTDOWN ] && echo "NO_SHUTDOWN is set"
exit 0
