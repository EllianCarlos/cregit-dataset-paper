#!/usr/bin/env bash
# M4-stop-merge.sh (spot a, as root). User yes 2026-10-16 ~20:25 UTC: "Restart with 48 jobs". Stops unit v1raw-merge
# (the next start deletes the partial outputs). Does not touch the ctp firm step (pid 1005816).
set -uo pipefail
[ "$(cat /sys/devices/virtual/dmi/id/board_asset_tag)" = ${RUNNER_EC2_SPOT_A6} ] || { echo "ABORT: not spot a"; exit 1; }
echo "== $(date -u +%FT%TZ)"
systemctl stop v1raw-merge; systemctl is-active v1raw-merge
echo "STOP $(date -u +%FT%TZ) unit v1raw-merge (restart with more jobs; shared spill dir bug)" >> /data1/v1raw/record
grep -q firm_attribution /proc/1005816/cmdline && echo "ctp firm step: alive"
ls -la /data1/v1raw/out/ /data1/v1raw/out/parquet | head -30
du -sh /data1/v1raw/out/parquet/.meta-spill 2>/dev/null
