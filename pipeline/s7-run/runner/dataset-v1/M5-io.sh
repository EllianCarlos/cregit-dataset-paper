#!/usr/bin/env bash
# M5-io.sh (spot a, read-only): spill sizes and disk load of the v1-raw merge.
set -uo pipefail
O=/data1/v1raw/out/parquet
echo "== $(date -u +%FT%TZ)"
echo "spill dirs: $(ls -d $O/.meta-spill-* 2>/dev/null | wc -l); spill total: $(du -sc $O/.meta-spill-* 2>/dev/null | tail -1 | cut -f1) KB"
du -s --block-size=1M $O/.meta-spill-* 2>/dev/null | sort -n | tail -5
echo "work dir: $(du -sh /data2/v1raw-work | cut -f1)"
cat /proc/pressure/io 2>/dev/null; cat /proc/pressure/cpu 2>/dev/null; cat /proc/pressure/memory 2>/dev/null
for d in nvme0n1 nvme1n1; do awk -v d=$d '$3==d {print d, "reads", $4, "writes", $8, "io_ms", $13}' /proc/diskstats; done
sleep 10
for d in nvme0n1 nvme1n1; do awk -v d=$d '$3==d {print d, "reads", $4, "writes", $8, "io_ms", $13}' /proc/diskstats; done
vmstat 2 3 | tail -2
