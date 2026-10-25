#!/usr/bin/env bash
# D9-rebalance-log.sh, machine A (read-only, through scripts/a/ssm-a.sh): the newest block of
# /data/x1k-long/rebalance.log (the per-row table of R8), the timer state and the ALERT file.
set -uo pipefail
L=/data/x1k-long/rebalance.log
n=$(grep -n '^== .* R8 rebalance' $L | tail -1 | cut -d: -f1)
[ -n "$n" ] && tail -n +$n $L | head -25
echo "timer: $(systemctl is-active x1k-rebalance.timer); ALERT file: $([ -e /data/x1k-long/rebalance.ALERT ] && echo PRESENT || echo absent)"
echo "changes so far: $(grep -c 'JOBS .* -> ' $L | head -1) plan lines with a change; restarts: $(grep -c 'stop (JOBS' $L)"
