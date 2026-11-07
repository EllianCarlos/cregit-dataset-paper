#!/usr/bin/env bash
# tom_start.sh (the TOM machine, root; a tool of the stage): starts tools/tom_run.sh as the systemd unit tom-run
# (log /data/tom/run.log), or in the foreground when TOM_LOCAL=1 (the local rehearsal). B1 calls it after its own
# checks. It refuses a start while tom-run runs and after run.DONE; an earlier run.ALERT is moved aside (a new start
# continues: the steps with STEP.DONE and the files of the pass with an OK ledger line are skipped).
set -uo pipefail
B=${TOM_B:-s3://BUCKET_NAME}; X=${TOM_X:-/data/tom}; T=$X/tools; PY=${TOM_PY:-$X/venv/bin/python}
UNIT=tom-run
NP=$(nproc); RAM=$(free -g | awk '/Mem:/{print $2}'); MAX=${MAX:-$(( RAM * 95 / 100 ))G}
bash -n $T/tom_run.sh || { echo "ABORT: tom_run.sh syntax"; exit 1; }
[ -f $X/status/run.DONE ] && { echo "ABORT: run.DONE exists (the run is done)"; exit 1; }
if [ "${TOM_LOCAL:-0}" = 1 ]; then
  RUNAS=""
else
  RUNAS=ec2-user
  systemctl is-active -q $UNIT && { echo "ABORT: the unit $UNIT runs"; exit 1; }
fi
[ -f $X/status/run.ALERT ] && { mv $X/status/run.ALERT $X/status/run.ALERT.$(date -u +%Y%m%dT%H%M%SZ); echo "an earlier ALERT moved aside"; }
if [ -f /run/systemd/shutdown/scheduled ] && [ "${TOM_LOCAL:-0}" != 1 ]; then shutdown -c; echo "a scheduled shutdown was cancelled"; fi
rm -f $X/STOP
ENVS="--setenv=X=$X --setenv=T=$T --setenv=PY=$PY --setenv=B=$B --setenv=RUNAS=$RUNAS --setenv=NOSHUT=${NOSHUT:-0}"
for v in JOBS HF LEDGERS FILL_CHECK ALERT_HOLD_MIN TOM_LOCAL SRC_DIR HF_PY; do
  [ -n "${!v:-}" ] && ENVS="$ENVS --setenv=$v=${!v}"
done
echo "== $(date -u +%FT%TZ) $NP vCPU, $RAM GiB, MemoryMax $MAX"
if [ "${TOM_LOCAL:-0}" = 1 ]; then
  env $(echo $ENVS | sed 's/--setenv=//g') PATH="$PATH" bash $T/tom_run.sh >> $X/run.log 2>&1; rc=$?
  tail -4 $X/run.log | cut -c1-300; echo "run rc $rc"; exit $rc
fi
systemctl reset-failed $UNIT 2>/dev/null || true
systemd-run --unit=$UNIT -p MemoryMax=$MAX -p OOMPolicy=continue \
  -p StandardOutput=append:$X/run.log -p StandardError=append:$X/run.log \
  -p "ExecStopPost=/bin/rm -f /run/tom-hf/token" \
  --setenv=PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin --setenv=AWS_REGION=us-west-2 $ENVS \
  /bin/bash $T/tom_run.sh || { echo "ABORT: systemd-run failed"; exit 1; }
echo "START $(date -u +%FT%TZ) unit $UNIT MemoryMax $MAX" | tee -a $X/record
sleep 20; systemctl --no-pager status $UNIT | sed -n 1,5p; tail -4 $X/run.log | cut -c1-240
