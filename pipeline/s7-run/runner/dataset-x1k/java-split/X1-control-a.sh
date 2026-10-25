#!/usr/bin/env bash
# X1-control-a.sh, machine A (root, through scripts/a/ssm-a.sh): the stop ways of the split.
# MODE (set it in the line below before you send the script; ssm.sh passes no environment):
#   stop    s3 control/STOP: each extra starts no new file, finishes the running ones, sends its
#           last batch, writes STOPPED and powers off. jv-pull goes on pulling, and its end rule
#           counts a STOPPED part as finished (then the row restarts once, as at a normal end).
#   unstop  removes s3 control/STOP (extras that have not ended go on; ended ones stay ended).
#   hold    /data/x1k-long/java-split/HOLD: jv-pull does nothing at all (no pull, no a-pos, no restart).
#   unhold  removes HOLD.
MODE=stop
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
C=s3://${RUNNER_BUCKET}/dataset-x1k/java-split/control
S=/data/x1k-long/java-split
case $MODE in
  stop) echo "STOP $(date -u +%FT%TZ) from machine A" > /tmp/jv-STOP; aws s3 cp /tmp/jv-STOP $C/STOP --only-show-errors && echo "control/STOP written" ;;
  unstop) aws s3 rm $C/STOP --only-show-errors && echo "control/STOP removed" ;;
  hold) mkdir -p $S && touch $S/HOLD && echo "HOLD written: jv-pull does nothing" ;;
  unhold) rm -f $S/HOLD && echo "HOLD removed" ;;
  *) echo "ABORT: MODE $MODE"; exit 1 ;;
esac
echo "control now: $(aws s3 ls $C/ 2>/dev/null | awk '{print $4}' | tr '\n' ' '); HOLD $([ -e $S/HOLD ] && echo present || echo absent)"
