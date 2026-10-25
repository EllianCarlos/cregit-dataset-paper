#!/usr/bin/env bash
# D10-summary.sh, machine A (read-only, through scripts/a/ssm-a.sh): per row of run.list the unit
# state, upload state and newest step; the newest R8 block that has a row table; the R8 changes;
# the finalize unit state.
set -uo pipefail
L=/data/x1k-long
for p in $(cat $L/run.list); do R=$(readlink -f $L/$p)
  st=$(grep -a -E '^  Step [0-9]+ ' $R/out/$p/pipeline.log 2>/dev/null | tail -1 | cut -c1-60)
  echo "$p: unit $(systemctl is-active x1k-long@$p); uploaded $([ -e $R/uploaded/$p ] && echo yes || echo no); $st"
done
LOG=$L/rebalance.log
n=$(grep -n '^  row ' $LOG | tail -1 | cut -d: -f1); [ -n "$n" ] && sed -n "$((n-1)),$((n+12))p" $LOG
echo "--- R8 changes:"; grep -a -E 'stop \(JOBS|OK: unit|ALERT' $LOG | tail -12
echo "--- finalize: $(systemctl list-units --all --no-legend 'x1k*final*' 'pf*final*' 2>/dev/null | head -3)"
