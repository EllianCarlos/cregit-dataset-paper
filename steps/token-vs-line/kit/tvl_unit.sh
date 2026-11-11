#!/usr/bin/env bash
# tvl_unit.sh (the machine, root; a tool of the stage): the body of the unit tvl-run that tvl_start.sh starts.
# It sets the backstop shutdown (the run cap + 20 min from the first start), runs tvl_run.py under nice, then
# shuts the machine down: DONE in 1 min, ALERT after ALERT_HOLD_MIN min (L1 set the stop behavior: the instance
# stops). NOSHUT=1, /run/tvl-hold or TVL_LOCAL=1: no shutdown.
set -uo pipefail
X=${X:-/data/tvl}; T=${T:-$X/tools}; PY=${PY:-$X/venv/bin/python}
conf() { awk -F= -v k="$1" '$1 == k {sub(/[ \t]*#.*/, "", $2); print $2}' $T/tvl.conf; }
CAP_H=${CAP_H:-$(conf CAP_H)}; NICE=${NICE:-$(conf NICE)}; HOLD_MIN=${ALERT_HOLD_MIN:-$(conf ALERT_HOLD_MIN)}
B=s3://$(conf BUCKET)/$(conf RUN_PREFIX)/${TVL_RUN:-local}
LOCAL=${TVL_LOCAL:-0}
mkdir -p $X/state $X/status $X/log
[ -f $X/state/start_utc ] || date +%s > $X/state/start_utc
start=$(cut -d. -f1 $X/state/start_utc)
noshut() { [ "$LOCAL" = 1 ] || [ "${NOSHUT:-0}" = 1 ] || [ -e /run/tvl-hold ]; }
if ! noshut; then
  left=$(awk -v s=$start -v c=$CAP_H -v n=$(date +%s) 'BEGIN {m = int((s + c * 3600 + 1200 - n) / 60); print (m < 5 ? 5 : m)}')
  shutdown -h +$left "token-vs-line run cap" && echo "$(date -u +%FT%TZ) backstop shutdown in $left min (the run cap)"
fi
rm -f $X/status/run.DONE $X/status/run.ALERT
nice -n $NICE $PY -I -B $T/tvl_run.py --conf $T/tvl.conf --plan $T/plan.tsv --x $X; rc=$?
if [ ! -f $X/status/run.DONE ] && [ ! -f $X/status/run.ALERT ]; then
  echo "ALERT $(date -u +%FT%TZ): tvl_run.py ended with rc $rc and no status" > $X/status/run.ALERT
  if [ "$LOCAL" != 1 ]; then
    aws s3 cp $X/status/run.ALERT $B/status/run.ALERT --only-show-errors || true
    if ! grep -q @ $X/log/run.log 2>/dev/null; then aws s3 cp $X/log/run.log $B/log/run.log --only-show-errors || true; fi
  fi
fi
echo "$(date -u +%FT%TZ) tvl_run.py rc $rc: $(cat $X/status/run.* 2>/dev/null | head -1)"
if noshut; then
  echo "no shutdown (local, NOSHUT=1 or /run/tvl-hold)"; [ "$LOCAL" = 1 ] || shutdown -c 2>/dev/null || true
elif [ -f $X/status/run.DONE ]; then
  echo "DONE: shutdown in 1 min (the instance stops)"; shutdown -h +1
else
  echo "ALERT: shutdown in $HOLD_MIN min (K1-tvl-hold.sh ACTION=hold keeps the machine)"; shutdown -h +$HOLD_MIN
fi
exit $rc
