#!/usr/bin/env bash
# tom4_start.sh (the TOM-4 machine, root; a tool of the stage): starts tools/tom4_run.sh as the systemd unit tom4-run
# (log /data/tom4/run.log), or in the foreground when TOM_LOCAL=1 (the local rehearsal). B1 calls it after its own
# checks. It refuses a start while tom4-run runs and after run.DONE; an earlier run.ALERT is moved aside (a new start
# continues: the steps with STEP.DONE are skipped).
set -uo pipefail
B=${TOM_B:-s3://BUCKET_NAME}; X=${TOM_X:-/data/tom4}; T=$X/tools; PY=${TOM_PY:-$X/venv/bin/python}
UNIT=tom4-run
NP=$(nproc); RAM=$(free -g | awk '/Mem:/{print $2}'); MAX=${MAX:-$(( RAM * 95 / 100 ))G}
bash -n $T/tom4_run.sh || { echo "ABORT: tom4_run.sh syntax"; exit 1; }
[ -f $X/status/run.DONE ] && { echo "ABORT: run.DONE exists (the run is done)"; exit 1; }
if [ "${TOM_LOCAL:-0}" = 1 ]; then
  RUNAS=""
else
  RUNAS=ec2-user
  systemctl is-active -q $UNIT && { echo "ABORT: the unit $UNIT runs"; exit 1; }
fi
[ -f $X/status/run.ALERT ] && { mv $X/status/run.ALERT "$X/status/run.ALERT.$(date -u +%Y%m%dT%H%M%SZ)"; echo "an earlier ALERT moved aside"; }
if [ -f /run/systemd/shutdown/scheduled ] && [ "${TOM_LOCAL:-0}" != 1 ]; then shutdown -c; echo "a scheduled shutdown was cancelled"; fi
rm -f $X/STOP
ENVS="--setenv=X=$X --setenv=T=$T --setenv=PY=$PY --setenv=B=$B --setenv=RUNAS=$RUNAS --setenv=NOSHUT=${NOSHUT:-0}"
for v in FOOTER_JOBS HASH_SAMPLE HF HF_PRE_VERIFY ALERT_HOLD_MIN TOM_LOCAL TOM3_DIR TOM3_LOG_DIR HF_PY; do
  [ -n "${!v:-}" ] && ENVS="$ENVS --setenv=$v=${!v}"
done
echo "== $(date -u +%FT%TZ) $NP vCPU, $RAM GiB, MemoryMax $MAX"
if [ "${TOM_LOCAL:-0}" = 1 ]; then
  env $(echo $ENVS | sed 's/--setenv=//g') PATH="$PATH" bash $T/tom4_run.sh >> $X/run.log 2>&1; rc=$?
  tail -4 $X/run.log | cut -c1-300; echo "run rc $rc"; exit $rc
fi
systemctl reset-failed $UNIT 2>/dev/null || true
systemd-run --unit=$UNIT -p MemoryMax=$MAX -p OOMPolicy=continue \
  -p StandardOutput=append:$X/run.log -p StandardError=append:$X/run.log \
  -p "ExecStopPost=/bin/rm -f /run/tom4-hf/token" \
  --setenv=PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin --setenv=AWS_REGION=us-west-2 $ENVS \
  /bin/bash $T/tom4_run.sh || { echo "ABORT: systemd-run failed"; exit 1; }
echo "START $(date -u +%FT%TZ) unit $UNIT MemoryMax $MAX" | tee -a $X/record
sleep 20; systemctl --no-pager status $UNIT | sed -n 1,5p; tail -4 $X/run.log | cut -c1-240
