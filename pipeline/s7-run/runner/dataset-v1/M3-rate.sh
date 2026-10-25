#!/usr/bin/env bash
# M3-rate.sh (spot a, read-only): bytes written by the running v1-raw jobs, measured twice 120 s apart.
set -uo pipefail
O=/data1/v1raw/out/parquet
s1=$(du -sb $O 2>/dev/null | cut -f1); t1=$(date +%s); ls -la $O | tail -n +4 | awk '{print $5, $9}' | sort -n | tail -20
sleep 120
s2=$(du -sb $O | cut -f1); t2=$(date +%s)
echo "written $s1 -> $s2 B in $((t2-t1)) s: $(( (s2-s1)/(t2-t1)/1000 )) kB/s"
top -b -n1 | head -20 | tail -13
