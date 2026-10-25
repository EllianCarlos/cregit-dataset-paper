#!/usr/bin/env bash
# V1-start.sh (the v0 machine, as root through ssm.sh; set A to its instance id): write dataset v0 with the
# organisation columns (ctp schema 2) from v1-raw in S3. Needs: /data1 and /data2 on the instance store,
# /data/ctp/.venv/bin/python with duckdb, the machine role, the inputs of U-upload.sh in S3.
# Two passes in one unit (v0-org): pass A, the 10 files with 195 M rows or more, 10 jobs x 56GB (the 6
# linux-size files failed at 5GB in the first v0; asuswrt took hours at 5GB); then pass B, the rest,
# 88 jobs x 5GB. The pass that ends last writes SHA256SUMS. Output /data2/v0/out, s3://BUCKET/dataset-v0-org/.
set -uo pipefail
A=${A:?set A to the instance id of the v0 machine}
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
B=s3://${RUNNER_BUCKET}
R=/data1/v1raw; V=/data2/v0
UNIT=v0-org
PY=/data/ctp/.venv/bin/python
BIG=${BIG:-195000000}
echo "== $(date -u +%FT%TZ) $IID"
[ "$IID" = "$A" ] || { echo "ABORT: not $A"; exit 1; }
[ -e /run/census-spot-interrupted ] && { echo "ABORT: spot interruption notice"; exit 1; }
systemctl is-active -q $UNIT && { echo "ABORT: $UNIT runs already"; exit 1; }
runuser -u ec2-user -- $PY -c 'import duckdb; print("duckdb", duckdb.__version__)' || { echo "ABORT: no duckdb"; exit 1; }
mkdir -p $R $V/inputs $V/out && chown -R ec2-user:ec2-user $R $V
if [ ! -s $R/DOWNLOADED ]; then
  aws s3 cp --recursive --only-show-errors $B/dataset-v1/raw/ $R/ || { echo "ABORT: v1-raw download"; exit 1; }
  [ "$(wc -l < $R/SHA256SUMS)" = 3544 ] || { echo "ABORT: v1-raw SHA256SUMS has $(wc -l < $R/SHA256SUMS) rows"; exit 1; }
  (cd $R && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: v1-raw sha256"; exit 1; }
  date -u +%FT%TZ > $R/DOWNLOADED
fi
aws s3 cp --recursive --only-show-errors $B/dataset-v0-org/inputs/ $V/inputs/ || { echo "ABORT: inputs download"; exit 1; }
(cd $V/inputs && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: inputs sha256"; exit 1; }
chown -R ec2-user:ec2-user $R $V
echo "inputs: $(cat $V/inputs/SOURCE)"
RUN="$PY -I $V/inputs/run_v0.py --v1raw $R --links $V/inputs --out $V/out --dest $B/dataset-v0-org --build-v0 $V/inputs/build_v0.py --threads 1"
systemctl reset-failed $UNIT 2>/dev/null || true
systemd-run --unit=$UNIT --uid=ec2-user --gid=ec2-user -p WorkingDirectory=$V -p Nice=5 -p MemoryMax=700G -p OOMPolicy=continue \
  --setenv=HOME=/home/ec2-user --setenv=PATH=/usr/local/bin:/usr/bin:/bin --setenv=AWS_REGION=${RUNNER_AWS_REGION} \
  -p StandardOutput=append:$V/out/v0.log -p StandardError=append:$V/out/v0.log \
  /bin/bash -c "$RUN --jobs 10 --memory-limit 56GB --min-rows $BIG; $RUN --jobs 88 --memory-limit 5GB --max-rows $((BIG - 1))" \
  || { echo "ABORT: systemd-run failed"; exit 1; }
echo "START $(date -u +%FT%TZ) unit $UNIT pass A >= $BIG rows (10 x 56GB), pass B (88 x 5GB)" | tee -a $V/record
sleep 60; systemctl --no-pager status $UNIT | sed -n 1,8p; tail -5 $V/out/v0.log
