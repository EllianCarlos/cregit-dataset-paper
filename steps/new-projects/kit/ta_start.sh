#!/usr/bin/env bash
# ta_start.sh (a machine of the kit tom-add-159, root; a tool of the stage): starts tools/ta_run.sh as the systemd unit ta-run
# (log /data/ta/run.log). B1 calls it after its own checks. It refuses a start while ta-run runs and after
# run.DONE; an earlier run.ALERT is moved aside (a new start continues: the steps with STEP.DONE are skipped).
set -uo pipefail
export HOME=${HOME:-/root}
[ -n "${GROUP:-}" ] || { echo "ABORT: GROUP is not set (EXPORTS=\"GROUP=<g>\")"; exit 1; }
B=${TA_B:-s3://BUCKET_NAME}; X=${TA_X:-/data/ta}; T=$X/tools
UNIT=ta-run
RAM=$(free -g | awk '/Mem:/{print $2}'); MAX=${MAX:-$(( RAM * 92 / 100 ))G}
bash -n $T/ta_run.sh || { echo "ABORT: ta_run.sh syntax"; exit 1; }
[ -f $X/status/run.DONE ] && { echo "ABORT: run.DONE exists (the run is done)"; exit 1; }
systemctl is-active -q $UNIT && { echo "ABORT: the unit $UNIT runs"; exit 1; }
[ -f $X/status/run.ALERT ] && { mv $X/status/run.ALERT "$X/status/run.ALERT.$(date -u +%Y%m%dT%H%M%SZ)"; echo "an earlier ALERT moved aside"; }
if [ -f /run/systemd/shutdown/scheduled ]; then shutdown -c; echo "a scheduled shutdown was cancelled"; fi
rm -f $X/STOP
ENVS="--setenv=X=$X --setenv=T=$T --setenv=B=$B --setenv=TA_RUN=${TA_RUN:?TA_RUN is not set}"
for v in NOSHUT ALERT_HOLD_MIN PARALLEL BLAME_JOBS MEMORY_LIMIT DUCKDB_THREADS WRITE_JOBS ALLOW_FAIL GROUP MODE; do
  [ -n "${!v:-}" ] && ENVS="$ENVS --setenv=$v=${!v}"
done
echo "== $(date -u +%FT%TZ) $(nproc) vCPU, $RAM GiB, MemoryMax $MAX"
systemctl reset-failed $UNIT 2>/dev/null || true
systemd-run --unit=$UNIT -p MemoryMax=$MAX -p OOMPolicy=continue -p Delegate=yes \
  -p StandardOutput=append:$X/run.log -p StandardError=append:$X/run.log \
  --setenv=PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin --setenv=HOME=/root --setenv=AWS_REGION=us-west-2 $ENVS \
  /bin/bash $T/ta_run.sh || { echo "ABORT: systemd-run failed"; exit 1; }
echo "START $(date -u +%FT%TZ) unit $UNIT MemoryMax $MAX run $TA_RUN" | tee -a $X/record
sleep 20; systemctl --no-pager status $UNIT | sed -n 1,5p; tail -4 $X/run.log | cut -c1-240
