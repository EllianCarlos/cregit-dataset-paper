#!/usr/bin/env bash
# P3-restart-a.sh, machine A (root, through scripts/a/ssm-a.sh): one rs-pull run with FORCE_RESTART=1.
# It pulls, then restarts the aws-sdk-rust row with the R8 procedure even when the end rule of
# rs-pull says WAIT (all guards and the R8 lock still apply). Use it when the extras ended and
# rs-pull waits for a part that will not come back, or with AUTO_RESTART=0.
# Why a restart is needed at all: blameRepoFiles.pl (cregit 57551d7, lines 76-102) checks for an
# existing .blame only once, when it builds its list at the start of step 7. A file pulled later
# is still in that list, and machine A would blame it again. A restart builds a new list.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
[ -x /usr/local/bin/rs-pull ] || { echo "ABORT: run P1-install-a.sh first"; exit 1; }
systemctl is-active -q rs-pull.service && { echo "ABORT: rs-pull runs now; try again in a few minutes"; exit 1; }
FORCE_RESTART=1 /usr/local/bin/rs-pull
