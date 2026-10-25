#!/usr/bin/env bash
# R4-start.sh, machine A (root, through scripts/a/ssm-a.sh; after R1, R2 (11 x CHECK OK) and R3; the
# same script for the first start and after a reclaim). The full v1 pipeline (user decision
# 2026-10-19: the x1k rows join the dataset): ctp ca113e3 without a patch, no --no-firm.
#   1. inputs: s3://B/dataset-x1k/inputs/ -> /data/x1k-inputs (on /data1), sha256 checked (only
#      manifest.x1k.tsv and project_meta.x1k.json are used; the no-firm patch is not applied);
#   2. each tree's ctp clone must be the clean ca113e3 (the code of the R2 gate, 14eb5d72 with the
#      firm step); the ctp tests run once (result in /data/x1k-long/tests.ok);
#   3. per row of long.tsv without s3://B/dataset-x1k/done-full/<p>/OK (the full done set): T/manifest.tsv (one row of
#      manifest.x1k.tsv) and T/run.env (blame jobs = long.tsv jobs x nproc / 192, at least 1;
#      --memory-limit by MemTotal >= 700 GiB; --min-free-mem-gb 24 --disk-floor-gb 50 --retries 10
#      --latest); /data/x1k-long/run.list = these rows;
#   4. starts x1k-long-watch, the upload, live and finalize timers and x1k-long@<p> per row. Each
#      unit chooses its own --from-step (x1k-long-run). Writes /data/x1k-long/started and live-a/START.
# Never on spot a or the big EC2.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}) echo "ABORT: $IID is spot a or the big EC2"; exit 1 ;; esac
B=s3://${RUNNER_BUCKET}
L=/data/x1k-long; I=/data/x1k-inputs
echo "== $(date -u +%FT%TZ) $IID R4 (machine A) start"
[ -x /usr/local/bin/x1k-long-run ] || { echo "ABORT: run R3 (machine A) first"; exit 1; }
[ -f $L/long.tsv ] || { echo "ABORT: run R1 first"; exit 1; }
ROWS=$(cut -f1 $L/long.tsv)
for p in $ROWS; do systemctl is-active -q x1k-long@$p && { echo "ABORT: x1k-long@$p runs already"; exit 1; }
  tail -1 $L/$p/gate.check 2>/dev/null | grep -q '^CHECK OK' || { echo "ABORT: $p has no CHECK OK (run R2)"; exit 1; }; done
# 1. inputs
mkdir -p $I
if ! (cd $I && sha256sum --quiet -c SHA256SUMS 2>/dev/null); then
  aws s3 cp $B/dataset-x1k/inputs/ $I/ --recursive --only-show-errors || { echo "ABORT: inputs download"; exit 1; }
  (cd $I && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: inputs sha256"; exit 1; }
fi
chown -R ec2-user:ec2-user $I; echo "inputs: $(head -1 $I/SOURCE); $(wc -l < $I/SHA256SUMS) files"
# 2. the ctp clones and the tests
for p in $ROWS; do C=$L/$p/ctp
  h=$(sudo -u ec2-user git -C $C rev-parse --short HEAD); dirty=$(sudo -u ec2-user git -C $C status --porcelain --untracked-files=no)
  [ "$h" = ca113e3 ] && [ -z "$dirty" ] || { echo "ABORT: ctp of $p is $h, not the clean ca113e3: $dirty"; exit 1; }
  [ -f $C/.x1k-patched ] && { echo "ABORT: ctp of $p has a .x1k-patched marker"; exit 1; }
done
echo "ctp: the clean ca113e3 in $(echo $ROWS | wc -w) trees"
if grep -q "^ca113e3 .* passed" $L/tests.ok 2>/dev/null; then t="ctp tests: $(tail -1 $L/tests.ok) (recorded)"
else
  t=$(cd $L/notnotype__neuro-book/ctp && sudo -u ec2-user .venv/bin/python -m pytest -q -o addopts= -p no:cacheprovider 2>&1 | tail -1)
  echo "$t" | grep -q ' passed' && ! echo "$t" | grep -q -e failed -e error || { echo "ABORT: ctp tests: $t"; exit 1; }
  echo "ca113e3 $t" > $L/tests.ok; t="ctp tests: $t"
fi
echo "$t"
r="gate: $(tail -1 $L/notnotype__neuro-book/gate.check)"
# 3. the rows to run
{ echo "__none__"; aws s3 ls $B/dataset-x1k/done-full/ --recursive 2>/dev/null | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u; } > /tmp/x1k-oks
NCPU=$(nproc); MEMG=$(awk '/MemTotal/ {print int($2 / 1048576)}' /proc/meminfo)
: > $L/run.list.new
while IFS=$'\t' read -r -u 3 p K jobs m1 m2; do T=$(readlink -f $L/$p)
  if grep -qx "$p" /tmp/x1k-oks; then echo "$p: done-full/OK in S3, not started"; continue; fi
  row=$(awk -F'\t' -v p="$p" '!/^#/ && $1 == p' $I/manifest.x1k.tsv)
  [ "$(echo "$row" | awk 'NF' | wc -l)" = 1 ] || { echo "ABORT: $p is not exactly once in manifest.x1k.tsv"; exit 1; }
  { echo "# x1k long row $p: one row of manifest.x1k.tsv (R4 machine A, $(date -u +%FT%TZ))."; grep '^# Columns:' $I/manifest.x1k.tsv | head -1; echo "$row"; } > $T/manifest.tsv
  j=$(( (jobs * NCPU + 96) / 192 )); [ $j -ge 1 ] || j=1
  mem=$m2; [ "$MEMG" -ge 700 ] && mem=$m1
  printf 'JOBS=%s\nMEM=%s\nMINFREE=24\nDISKFLOOR=50\nRETRIES=10\nMETA=%s\nLATEST=--latest\n' $j $mem $I/project_meta.x1k.json > $T/run.env
  chown ec2-user: $T/manifest.tsv $T/run.env
  echo "$p" >> $L/run.list.new
  echo "$p: /data$K, blame jobs $j, memory limit $mem, $( [ -f $T/out/$p/pipeline.log ] && echo 'has pipeline.log (resume)' || echo 'new')"
done 3< $L/long.tsv
mv -f $L/run.list.new $L/run.list; chown ec2-user: $L/run.list
[ -s $L/run.list ] || { echo "nothing to start: every row has done-full/OK"; exit 0; }
# 4. start
rm -f /etc/dataset-x1k/final-a-DONE
echo "started $(date -u +%FT%TZ) on $IID $(cat /sys/devices/virtual/dmi/id/product_name 2>/dev/null) $NCPU vCPU $MEMG GiB, $(wc -l < $L/run.list) rows" > $L/started
cat $L/started >> $L/starts.log; chown ec2-user: $L/started $L/starts.log
systemctl daemon-reload
systemctl enable --now x1k-long-watch.service >/dev/null 2>&1; systemctl start x1k-long-upload.timer x1k-long-live.timer x1k-long-finalize.timer
for p in $(cat $L/run.list); do systemctl reset-failed x1k-long@$p 2>/dev/null; systemctl start x1k-long@$p; done
{ cat $L/started; cat $L/run.list; echo "$t"; echo "$r"; } > /tmp/x1k-long-START
aws s3 cp /tmp/x1k-long-START $B/dataset-x1k/live-a/START --only-show-errors
sleep 90
for p in $(cat $L/run.list); do echo "$p: $(systemctl is-active x1k-long@$p) | $(grep -a '=== .* x1k-long' $L/$p/logs/run.log | tail -1 | cut -c1-260)"; done
echo "R4 (machine A) done $(date -u +%FT%TZ)"
