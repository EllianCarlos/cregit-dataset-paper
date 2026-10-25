#!/usr/bin/env bash
# V2-check.sh (the v0 machine, through ssm.sh): progress of unit v0-org.
set -uo pipefail
V=/data2/v0
echo "== $(date -u +%FT%TZ)  unit v0-org: $(systemctl is-active v0-org)  $(systemctl show v0-org -p MemoryCurrent | tr '\n' ' ')"
d=$(($(wc -l < $V/out/results.tsv 2>/dev/null || echo 1) - 1)); f=$(wc -l < $V/out/failed.tsv 2>/dev/null || echo 0)
echo "done $d of 3544; failed rows $f"
[ -s $V/out/results.tsv ] && awk -F'\t' 'NR>1 {i+=$7; o+=$8; r+=$6} END {if (i) printf "done: %.1f GB in -> %.1f GB out (%.1f%%), %.2f B rows\n", i/1e9, o/1e9, 100*o/i, r/1e9}' $V/out/results.tsv
[ -s $V/out/failed.tsv ] && tail -3 $V/out/failed.tsv | cut -c1-300
[ -s $V/out/SHA256SUMS ] && echo "SHA256SUMS rows: $(wc -l < $V/out/SHA256SUMS)"
tail -4 $V/out/v0.log 2>/dev/null | cut -c1-200
free -g | sed -n 2p; uptime; df -h /data1 /data2 | tail -2
