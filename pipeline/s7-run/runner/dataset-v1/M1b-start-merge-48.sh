#!/usr/bin/env bash
# M1-start-merge.sh (spot a, as root through ssm.sh). User decisions 2026-10-16: "ZSTD 19 on spot a" and
# "Raw v1 first, then public". Starts final_merge.py (dataset v1-raw) as unit v1raw-merge (ec2-user).
# Inputs: s3://BUCKET/<key> of inputs.tsv. Outputs: /data1/v1raw/out and s3://BUCKET/dataset-v1/raw/ (machine role).
# The ctp firm step of asuswrt (pid 1005816, about 60 GB) still runs: MemoryMax leaves room for it.
set -uo pipefail
A=${RUNNER_EC2_SPOT_A6}
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
B=s3://${RUNNER_BUCKET}
R=/data1/v1raw; W=/data2/v1raw-work
UNIT=v1raw-merge
PY=/data/ctp/.venv/bin/python
VS=/w/batch13a1/ctp/validate_schema.py; VSWANT=2efe32c3a286991a14e848913581e719ea2c0dbfbd621746d573e190d328a053
JOBS=${JOBS:-48}; TH=${TH:-2}; MEM=${MEM:-10GB}; MAX=${MAX:-560G}; EXTRA=${EXTRA:-}
echo "== $(date -u +%FT%TZ) $IID"
[ "$IID" = $A ] || { echo "ABORT: not spot a"; exit 1; }
[ -e /run/census-spot-interrupted ] && { echo "ABORT: spot interruption notice"; exit 1; }
[ -e /home/ec2-user/NO_SHUTDOWN ] || { echo "ABORT: no NO_SHUTDOWN: spot a can stop itself"; exit 1; }
systemctl is-active -q $UNIT && { echo "ABORT: $UNIT runs already"; exit 1; }
[ "$(sha256sum $VS | cut -d' ' -f1)" = $VSWANT ] || { echo "ABORT: validate_schema.py is not the ca113e3 one"; exit 1; }
mkdir -p $R/tools $R/out $W && chown -R ec2-user:ec2-user $R $W
aws s3 cp --recursive --only-show-errors $B/dataset-v1/tools/ $R/tools/ || { echo "ABORT: tools download"; exit 1; }
aws s3 cp --only-show-errors $B/dataset-v1/inputs.tsv $R/inputs.tsv && aws s3 cp --only-show-errors $B/dataset-v1/SHA256SUMS $R/inputs.SHA256SUMS \
  || { echo "ABORT: inputs download"; exit 1; }
(cd $R/tools && sha256sum --quiet -c SHA256SUMS && sha256sum --quiet -c project_meta.v1.final.json.sha256) || { echo "ABORT: tools sha256"; exit 1; }
(cd $R && grep ' inputs.tsv$' inputs.SHA256SUMS | sha256sum --quiet -c) || { echo "ABORT: inputs.tsv sha256"; exit 1; }
chown -R ec2-user:ec2-user $R
echo "inputs: $(($(wc -l < $R/inputs.tsv) - 1)) projects; tools: $(cat $R/tools/SOURCE 2>/dev/null)"
runuser -u ec2-user -- $PY -I -c 'import duckdb; print("duckdb", duckdb.__version__)' || { echo "ABORT: no duckdb"; exit 1; }
systemctl reset-failed $UNIT 2>/dev/null || true
systemd-run --unit=$UNIT --uid=ec2-user --gid=ec2-user -p WorkingDirectory=$R -p Nice=5 -p MemoryMax=$MAX -p OOMPolicy=continue \
  --setenv=HOME=/home/ec2-user --setenv=PATH=/usr/local/bin:/usr/bin:/bin --setenv=AWS_REGION=${RUNNER_AWS_REGION} \
  -p StandardOutput=append:$R/out/merge.log -p StandardError=append:$R/out/merge.log \
  $PY -I $R/tools/final_merge.py --inputs $R/inputs.tsv --sidecar $R/tools/project_meta.v1.final.json \
  --work $W --out $R/out --src $B --dest $B/dataset-v1/raw --validate-schema $VS --rewrite $R/tools/rewrite_meta_columns.py \
  --jobs $JOBS --threads $TH --memory-limit $MEM $EXTRA || { echo "ABORT: systemd-run failed"; exit 1; }
echo "START $(date -u +%FT%TZ) unit $UNIT jobs $JOBS threads $TH memory $MEM MemoryMax $MAX extra [$EXTRA]" | tee -a $R/record
sleep 60; systemctl --no-pager status $UNIT | sed -n 1,8p; tail -5 $R/out/merge.log
