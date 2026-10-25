#!/usr/bin/env bash
# M1-x2-start.sh (the X2 merge machine, root, through x2/ssm-x2.sh). Step X2 of the merge plan
# (x1k-raw): final_merge.py of v1 (meta rewrite with the x1k final sidecar + ZSTD 19 + validate_schema
# of ca113e3 + row count check) over /data/x2/inputs.x1k.tsv, to s3://B/dataset-x1k/raw/ (parquet/,
# SHA256SUMS, results.tsv, rewrite.tsv, the sidecar and its sha256). The flags of v1-raw (spot a,
# M1c-start-merge-88x1.sh): --jobs 88 --threads 1 --memory-limit 5GB (JOBS = nproc - 8 on another type).
#   1. Pass 2 or later (a new machine for the rows that end later): when DEST has results.tsv and the
#      local OUT has none, it copies results.tsv and rewrite.tsv of DEST to OUT; final_merge.py then
#      skips each project in results.tsv and writes SHA256SUMS over all of them at the end.
#   2. Smoke test (SMOKE=1, the default, only when OUT has no results.tsv): 3 projects (the smallest
#      GitHub row, the smallest git.savannah.gnu.org row and the smallest invent.kde.org row) with
#      --only, to a separate OUT and to s3://B/dataset-x1k/raw-smoke/<run>/. It checks rc 0, 3 OK lines,
#      the owner gnu of the Savannah row, a stratum in each file and ZSTD compression.
#   3. The unit x1k-raw-merge (root; final_merge.py runs as ec2-user): /data/x2/x2-run.sh. At the end:
#      rc 0 + "DONE:" in merge.log + DEST/SHA256SUMS with the local size -> raw-work/<run>/DONE, the
#      log copies, then shutdown -h +5 (the instance terminates), unless /home/ec2-user/NO_SHUTDOWN or
#      /run/x2-hold exists; else raw-work/<run>/ALERT and no shutdown.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1})
  echo "ABORT: $IID is not the X2 machine"; exit 1 ;; esac
RUN=${X2_RUN:?no X2_RUN: send this script with x2/ssm-x2.sh}
B=s3://${RUNNER_BUCKET}; X=/data/x2; T=$X/tools; PY=$X/.venv/bin/python
OUT=/data1/x2/out; WORK=/data2/x2-work; DEST=$B/dataset-x1k/raw; UNIT=x1k-raw-merge
NP=$(nproc); JOBS=${JOBS:-$([ "$NP" = 96 ] && echo 88 || echo $((NP - 8)))}; TH=${TH:-1}; MEM=${MEM:-5GB}
MAX=${MAX:-$(( $(free -g | awk '/Mem:/{print $2}') * 78 / 100 ))G}; SMOKE=${SMOKE:-1}
VS=$X/ctp/validate_schema.py; VSWANT=2efe32c3a286991a14e848913581e719ea2c0dbfbd621746d573e190d328a053
echo "== $(date -u +%FT%TZ) $IID run $RUN, $NP vCPU, jobs $JOBS, threads $TH, memory $MEM, MemoryMax $MAX"
systemctl is-active -q $UNIT && { echo "ABORT: $UNIT runs"; exit 1; }
[ -d /data2 ] || { echo "ABORT: no /data2"; exit 1; }
[ "$(sha256sum $VS | cut -d' ' -f1)" = $VSWANT ] || { echo "ABORT: validate_schema.py is not the ca113e3 one"; exit 1; }
(cd $X && sha256sum --quiet -c inputs.x1k.tsv.sha256) || { echo "ABORT: inputs.x1k.tsv sha256 (run R2-x2-inputs.sh)"; exit 1; }
(cd $T && sha256sum --quiet -c project_meta.x1k.final.json.sha256) || { echo "ABORT: sidecar sha256"; exit 1; }
mkdir -p $OUT $WORK; chown -R ec2-user:ec2-user /data1/x2 $WORK
echo "inputs: $(($(wc -l < $X/inputs.x1k.tsv) - 1)) projects ($(awk -F'\t' 'NR>1 {n[$2" cregit "$3]++} END {for (k in n) printf "%s %d; ", k, n[k]}' $X/inputs.x1k.tsv))"
# the path-fix rows (R2-x2): only from done-pathfix/ with cregit 14b8db4, never the done-full version
[ -f $X/pathfix.x1k.txt ] && [ -f $X/held.x1k.txt ] || { echo "ABORT: no pathfix.x1k.txt or held.x1k.txt (run the R2-x2-inputs.sh of the path-fix change)"; exit 1; }
badpf=$(awk -F'\t' 'NR==FNR {if ($0 !~ /^#/ && NF) pf[$1]=1; next} FNR>1 && ($1 in pf) && ($6 !~ /^dataset-x1k\/done-pathfix\// || $3 != "14b8db4") {print $1}' $X/pathfix.x1k.txt $X/inputs.x1k.tsv)
[ -z "$badpf" ] || { echo "ABORT: path-fix rows not from done-pathfix with cregit 14b8db4: $badpf"; exit 1; }
echo "held (path-fix rows without done-pathfix OK; a later pass): $(grep -vc '^#' $X/held.x1k.txt || true)$(grep -v '^#' $X/held.x1k.txt | cut -f1 | sed 's/^/ /' | tr -d '\n')"
# --- 1. a later pass continues the results of DEST
if [ ! -f $OUT/results.tsv ] && aws s3 ls $DEST/results.tsv >/dev/null 2>&1; then
  for f in results.tsv rewrite.tsv; do aws s3 cp $DEST/$f $OUT/$f --only-show-errors || true; done
  chown ec2-user: $OUT/*.tsv; SMOKE=0
  echo "later pass: $(($(wc -l < $OUT/results.tsv) - 1)) projects are in results.tsv of DEST already"
fi
# --- 2. smoke test
if [ "$SMOKE" = 1 ] && [ ! -f $OUT/results.tsv ]; then
  # a second start: move the smoke output of an earlier start aside (kept), so that the test runs again
  ts=$(date -u +%Y%m%dT%H%M%SZ); for d in /data1/x2-smoke /data2/x2-smoke-work; do [ -e $d ] && mv $d $d.$ts; done
  SO=/data1/x2-smoke/out; SW=/data2/x2-smoke-work; mkdir -p $SO $SW; chown -R ec2-user: /data1/x2-smoke $SW
  pick() { awk -F'\t' -v pat="$1" 'NR>1 && $1 ~ pat {print $5, $1}' $X/inputs.x1k.tsv | sort -n | head -1 | cut -d' ' -f2; }
  S1=$(awk -F'\t' 'NR>1 && $1 !~ /\./ {print $5, $1}' $X/inputs.x1k.tsv | sort -n | head -1 | cut -d' ' -f2)
  S2=$(pick '^git\\.savannah\\.gnu\\.org__'); S3=$(pick '^invent\\.kde\\.org__')
  echo "smoke test: $S1 $S2 $S3"
  only=(); for s in $S1 $S2 $S3; do only+=(--only "$s"); done
  runuser -u ec2-user -- env HOME=/home/ec2-user AWS_REGION=${RUNNER_AWS_REGION} $PY -I $T/final_merge.py --inputs $X/inputs.x1k.tsv \
    --sidecar $T/project_meta.x1k.final.json --work $SW --out $SO --src $B --dest $B/dataset-x1k/raw-smoke/$RUN \
    --validate-schema $VS --rewrite $T/rewrite_meta_columns.py --jobs 3 --threads 1 --memory-limit $MEM "${only[@]}" > $SO/merge.log 2>&1
  rc=$?; cat $SO/merge.log | cut -c1-200
  nok=$(grep -c '\] OK ' $SO/merge.log)
  want=$(( ${#only[@]} / 2 ))
  [ $rc = 0 ] && [ "$nok" = $want ] || { echo "ABORT: smoke test rc $rc, $nok OK lines (want $want)"; exit 1; }
  runuser -u ec2-user -- $PY -I - $SO/parquet "$S2" <<'P' || { echo "ABORT: smoke test content check"; exit 1; }
import duckdb, sys, pathlib
d, sav = pathlib.Path(sys.argv[1]), sys.argv[2]
con = duckdb.connect()
for f in sorted(d.glob("*-dataset.parquet")):
    owner, strata = con.execute("SELECT min(owner), list(DISTINCT stratum) FROM read_parquet(?)", [str(f)]).fetchone()
    comp = [r[0] for r in con.execute("SELECT DISTINCT compression FROM parquet_metadata(?)", [str(f)]).fetchall()]
    print(f"  {f.name}: owner {owner}, stratum {strata}, compression {comp}")
    assert all(s for s in strata), "blank stratum"
    assert comp == ["ZSTD"], "not ZSTD"
    if f.name.startswith(sav + "-"):
        assert owner == "gnu", "Savannah owner is not gnu"
P
  echo "SMOKE TEST OK (outputs in $B/dataset-x1k/raw-smoke/$RUN/; not part of the dataset)"
fi
# --- 3. the run
cat > $X/x2-run.sh <<EOF
#!/usr/bin/env bash
# x2-run.sh (unit $UNIT, root): final_merge.py as ec2-user, then DONE or ALERT, then shutdown.
set -uo pipefail
/usr/sbin/runuser -u ec2-user -- env HOME=/home/ec2-user AWS_REGION=${RUNNER_AWS_REGION} AWS_METADATA_SERVICE_NUM_ATTEMPTS=10 AWS_METADATA_SERVICE_TIMEOUT=5 AWS_RETRY_MODE=adaptive AWS_MAX_ATTEMPTS=10 $PY -I $T/final_merge.py --inputs $X/inputs.x1k.tsv \\
  --sidecar $T/project_meta.x1k.final.json --work $WORK --out $OUT --src $B --dest $DEST \\
  --validate-schema $VS --rewrite $T/rewrite_meta_columns.py --jobs $JOBS --threads $TH --memory-limit $MEM >> $OUT/merge.log 2>&1
rc=\$?
n=\$((\$(wc -l < $OUT/results.tsv 2>/dev/null || echo 1) - 1)); f=\$(wc -l < $OUT/failed.tsv 2>/dev/null || echo 0)
ok=0
if [ \$rc = 0 ] && grep -q 'DONE:' $OUT/merge.log && [ "\$(aws s3 ls $DEST/SHA256SUMS | awk '{print \$3}')" = "\$(stat -c %s $OUT/SHA256SUMS 2>/dev/null)" ]; then ok=1; fi
st=\$([ \$ok = 1 ] && echo DONE || echo ALERT)
echo "x1k-raw \$st run $RUN \$(date -u +%FT%TZ) on $IID: rc \$rc, results.tsv \$n projects, failed.tsv \$f lines, inputs \$((\$(wc -l < $X/inputs.x1k.tsv) - 1))" > $OUT/\$st
for x in merge.log failed.tsv \$st; do [ -f $OUT/\$x ] && aws s3 cp $OUT/\$x $B/dataset-x1k/raw-work/$RUN/\$x --only-show-errors; done
cat $OUT/\$st
if [ \$ok = 1 ] && [ ! -e /home/ec2-user/NO_SHUTDOWN ] && [ ! -e /run/x2-hold ]; then
  echo "shutdown in 5 min (the instance terminates)"; shutdown -h +5
fi
EOF
chmod 755 $X/x2-run.sh; bash -n $X/x2-run.sh || { echo "ABORT: x2-run.sh syntax"; exit 1; }
systemctl reset-failed $UNIT 2>/dev/null || true
systemd-run --unit=$UNIT -p Nice=5 -p MemoryMax=$MAX -p OOMPolicy=continue \
  --setenv=PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin --setenv=AWS_REGION=${RUNNER_AWS_REGION} $X/x2-run.sh || { echo "ABORT: systemd-run failed"; exit 1; }
echo "START $(date -u +%FT%TZ) unit $UNIT run $RUN jobs $JOBS threads $TH memory $MEM MemoryMax $MAX" | tee -a $X/record
sleep 60; systemctl --no-pager status $UNIT | sed -n 1,6p; tail -4 $OUT/merge.log | cut -c1-200
echo "M1-x2 done"
