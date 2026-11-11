#!/usr/bin/env bash
# tvl_start.sh (the machine, root; a tool of the stage): starts tools/tvl_unit.sh as the systemd unit tvl-run
# (log /data/tvl/unit.log), or in the foreground when TVL_LOCAL=1 (the local rehearsal). B1 calls it after its
# checks. It refuses a start while tvl-run runs and after run.DONE. A second start continues the run: the projects
# with results stay done, the run cap counts from the first start.
set -uo pipefail
X=${X:-/data/tvl}; T=${T:-$X/tools}; PY=${PY:-$X/venv/bin/python}
UNIT=tvl-run
RAM=$(free -g | awk '/Mem:/{print $2}'); MAX=${MAX:-$(( RAM * 95 / 100 ))G}
bash -n $T/tvl_unit.sh || { echo "ABORT: tvl_unit.sh syntax"; exit 1; }
[ -f $X/status/run.DONE ] && { echo "ABORT: run.DONE exists (the run is done)"; exit 1; }
ENVS="X=$X T=$T PY=$PY NOSHUT=${NOSHUT:-0} TVL_RUN=${TVL_RUN:-local}"
for v in TVL_LOCAL TVL_LOCAL_S3 TVL_TOM_DIR TVL_CLONE_MAP TVL_DOMAINS TVL_ROOT_SUMS TVL_BACKOFF_SCALE TVL_ITYPE \
         N JOBS CLONE_JOBS CAP_H RESERVE_MIN PROGRESS_S UPLOAD_BLAME ALERT_HOLD_MIN NICE MEASURE_THREADS MEASURE_GB \
         MEASURE_BIG_GB MEASURE_BUDGET_GB LIMIT_PLAIN LIMIT_W LIMIT_WMC KIT_SUMS; do
  [ -n "${!v:-}" ] && ENVS="$ENVS $v=${!v}"
done
if [ "${TVL_LOCAL:-0}" = 1 ]; then
  (cd $X && env $ENVS PATH="$PATH" bash $T/tvl_unit.sh >> $X/unit.log 2>&1); rc=$?
  tail -3 $X/unit.log | cut -c1-300; exit $rc
fi
systemctl is-active -q $UNIT && { echo "ABORT: the unit $UNIT runs"; exit 1; }
[ -f /run/systemd/shutdown/scheduled ] && { shutdown -c; echo "a scheduled shutdown was cancelled"; }
systemctl reset-failed $UNIT 2>/dev/null || true
SE=""; for kv in $ENVS; do SE="$SE --setenv=$kv"; done
systemd-run --unit=$UNIT -p MemoryMax=$MAX -p OOMPolicy=continue -p WorkingDirectory=$X \
  -p StandardOutput=append:$X/unit.log -p StandardError=append:$X/unit.log \
  --setenv=PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin --setenv=AWS_REGION=us-west-2 --setenv=HOME=/root $SE \
  /bin/bash $T/tvl_unit.sh || { echo "ABORT: systemd-run failed"; exit 1; }
echo "START $(date -u +%FT%TZ) unit $UNIT MemoryMax $MAX" | tee -a $X/record
sleep 20; systemctl --no-pager status $UNIT | sed -n 1,5p; tail -4 $X/unit.log | cut -c1-240
