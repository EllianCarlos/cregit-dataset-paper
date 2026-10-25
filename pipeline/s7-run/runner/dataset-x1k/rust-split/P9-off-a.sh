#!/usr/bin/env bash
# P9-off-a.sh, machine A (root, through scripts/a/ssm-a.sh): after the row passed step 7, stop and
# disable rs-pull.timer. It refuses while the row is still in step 7. The files and logs stay.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
P=awslabs__aws-sdk-rust; T=$(readlink -f /data/x1k-long/$P)
st=$(grep -a -E '^  Step [0-9]+ ' "$T/out/$P/pipeline.log" | tail -1 | awk '{print $2}')
if [ "$st" = 7 ] && systemctl is-active -q "x1k-long@$P"; then echo "ABORT: the row is still in step 7"; exit 1; fi
systemctl disable --now rs-pull.timer >/dev/null 2>&1
echo "rs-pull.timer: $(systemctl is-active rs-pull.timer); the row: step ${st:-?}, unit $(systemctl is-active x1k-long@$P)"
