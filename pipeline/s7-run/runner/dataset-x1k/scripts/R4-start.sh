#!/usr/bin/env bash
# R4-start.sh (the x1k instance, root, through ssm.sh; only after the user ran U1-upload-x1k-inputs.sh
# and it printed ALL OK, and after R1, R2 (all 4 CHECK OK) and R3): start the x1k test run.
#   1. inputs: s3://B/dataset-x1k/inputs/ -> /data/x1k-inputs, sha256 checked;
#   2. each part's ctp clone (ca113e3) gets ctp-no-firm.patch (git apply), and the 4 patched files
#      must have the sha256 of ctp-no-firm.files.sha256; the ctp tests pass in p1's clone;
#   3. no-firm check: libexpat with the patched ctp and --no-firm on p1's cregit copy (scratch ctp
#      clone and output): the stamp says columns=cregit, and the Parquet equals the R2 gate Parquet
#      (14eb5d72, full steps) without the 3 firm columns, row for row (DuckDB EXCEPT ALL both ways);
#   4. each part's manifest.run.tsv = its part manifest minus the projects with dataset-x1k/done/<p>/OK
#      (none on the first start; after a relaunch the rest);
#   5. starts x1k-watch, the upload, live and finalize timers and x1k@1..4 (WORKERS per part, default 6).
# Never on spot a or the big EC2. Writes /etc/dataset-x1k/started and dataset-x1k/live/START.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}) echo "ABORT: $IID is spot a or the big EC2"; exit 1 ;; esac
B=s3://${RUNNER_BUCKET}
E=/etc/dataset-x1k; I=/data/x1k-inputs
WORKERS=${WORKERS:-6}
WANT_PQ=14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
echo "== $(date -u +%FT%TZ) $IID R4 start"
for K in 1 2 3 4; do systemctl is-active -q x1k@$K && { echo "ABORT: x1k@$K runs already"; exit 1; }
  tail -1 $E/p$K.check 2>/dev/null | grep -q '^CHECK OK' || { echo "ABORT: p$K has no CHECK OK (run R2)"; exit 1; }; done
[ -x /usr/local/bin/x1k-run ] || { echo "ABORT: run R3 first"; exit 1; }
# 1. inputs
mkdir -p $I
aws s3 cp $B/dataset-x1k/inputs/ $I/ --recursive --only-show-errors || { echo "ABORT: inputs download"; exit 1; }
(cd $I && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: inputs sha256"; exit 1; }
chown -R ec2-user:ec2-user $I; echo "inputs: $(head -1 $I/SOURCE); $(wc -l < $I/SHA256SUMS) files"
# 2. patch every part's ctp clone
for K in 1 2 3 4; do C=/data$K/x1k/ctp
  cat > /home/ec2-user/x1k-patch-p$K.sh <<U
set -e; cd $C
if [ ! -f .x1k-patched ]; then
  [ "\$(git rev-parse --short HEAD)" = ca113e3 ] && [ -z "\$(git status --porcelain --untracked-files=no)" ]
  git apply --check $I/ctp-no-firm.patch; git apply $I/ctp-no-firm.patch
fi
sha256sum --quiet -c $I/ctp-no-firm.files.sha256
sha256sum $I/ctp-no-firm.patch > .x1k-patched
echo "p$K ctp \$(git rev-parse --short HEAD) + no-firm patch: \$(git status --porcelain --untracked-files=no | tr '\n' ' ')"
U
  chown ec2-user: /home/ec2-user/x1k-patch-p$K.sh
  sudo -u ec2-user bash /home/ec2-user/x1k-patch-p$K.sh || { echo "ABORT: patch of p$K"; exit 1; }
done
t=$(cd /data1/x1k/ctp && sudo -u ec2-user .venv/bin/python -m pytest -q -o addopts= -p no:cacheprovider 2>&1 | tail -1)
echo "ctp tests (p1 clone): $t"; echo "$t" | grep -q ' passed' && ! echo "$t" | grep -q -e failed -e error || { echo "ABORT: ctp tests"; exit 1; }
# 3. no-firm check on p1's cregit copy
P=/data1/x1k; N=$P/nofirm-check
printf '# no-firm libexpat check on the cregit copy %s (scratch output).\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' $P/cregit-ec2 $P/cregit-ec2 $N/out > $E/p1.nofirm.cfg
chmod 644 $E/p1.nofirm.cfg
cat > /home/ec2-user/x1k-nofirm.sh <<U
set -uo pipefail
[ -d $N ] && mv $N $N.old.\$(date +%s)
mkdir -p $N/out; git clone -q /data/input/ctp.bundle $N/ctp -b feat/e2e-runner; cd $N/ctp
git apply $I/ctp-no-firm.patch && sha256sum --quiet -c $I/ctp-no-firm.files.sha256 || exit 1
ln -s $P/ctp/.venv .venv
export CTP_CONFIG=$E/p1.nofirm.cfg
.venv/bin/python ctp.py census --manifest /data/input/manifest.libexpat.tsv --project-meta /data/input/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --no-firm --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > $P/logs/nofirm-check.log 2>&1
echo "census rc=\$?"
.venv/bin/python - $N/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet $P/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet <<'PY'
import duckdb, sys
a, b = sys.argv[1], sys.argv[2]
con = duckdb.connect()
na = len(con.execute("describe select * from read_parquet(?)", [a]).fetchall())
nb = len(con.execute("describe select * from read_parquet(?)", [b]).fetchall())
ra = con.execute("select count(*) from read_parquet(?)", [a]).fetchone()[0]
rb = con.execute("select count(*) from read_parquet(?)", [b]).fetchone()[0]
A = "select * from read_parquet(?)"
G = "select * exclude (firm_raw, firm, firm_source) from read_parquet(?)"
d1 = con.execute(f"select count(*) from ({A} except all {G})", [a, b]).fetchone()[0]
d2 = con.execute(f"select count(*) from ({G} except all {A})", [b, a]).fetchone()[0]
ok = na == 67 and nb == 70 and ra == rb and d1 == 0 and d2 == 0
print(f"no-firm Parquet {na} columns {ra} rows; gate Parquet {nb} columns {rb} rows; differing rows {d1}/{d2}: {'NOFIRM OK' if ok else 'NOFIRM FAILED'}")
PY
U
chown ec2-user: /home/ec2-user/x1k-nofirm.sh
r=$(sudo -u ec2-user -i bash /home/ec2-user/x1k-nofirm.sh 2>&1 | tail -2); echo "$r"
[ "$(sha256sum $P/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet | cut -d' ' -f1)" = $WANT_PQ ] || { echo "ABORT: the gate Parquet is not 14eb5d72"; exit 1; }
echo "$r" | grep -q 'NOFIRM OK' && grep -q '^columns=cregit$' $N/out/libexpat__libexpat/libexpat__libexpat.validated || { echo "ABORT: no-firm check"; exit 1; }
# 4. the remaining rows of each part
{ echo "__none__"; aws s3 ls $B/dataset-x1k/done/ --recursive 2>/dev/null | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u; } > /tmp/x1k-oks
echo "projects with done/OK in S3: $(($(wc -l < /tmp/x1k-oks) - 1))"
for K in 1 2 3 4; do M=$I/manifest.x1k-p$K.tsv; R=/data$K/x1k/manifest.run.tsv
  { grep '^#' $M; grep -v -e '^#' -e '^[[:space:]]*$' $M | awk -F'\t' 'NR==FNR {d[$1]=1; next} !($1 in d)' /tmp/x1k-oks -; } > $R.new
  mv -f $R.new $R; chown ec2-user: $R
  echo "p$K: $(grep -c -v -e '^#' -e '^[[:space:]]*$' $R) of $(grep -c -v -e '^#' -e '^[[:space:]]*$' $M) rows to run"
done
# 5. start
echo $WORKERS > $E/workers
echo "started $(date -u +%FT%TZ) on $IID, $WORKERS workers per part" > $E/started
systemctl daemon-reload
systemctl enable --now x1k-watch.service >/dev/null 2>&1; systemctl start x1k-upload.timer x1k-live.timer x1k-finalize.timer
for K in 1 2 3 4; do systemctl reset-failed x1k@$K 2>/dev/null; systemctl start x1k@$K; done
{ cat $E/started; for K in 1 2 3 4; do echo "p$K: $(grep -c -v -e '^#' -e '^[[:space:]]*$' /data$K/x1k/manifest.run.tsv) rows"; done; echo "$t"; echo "$r"; } > /tmp/x1k-START
aws s3 cp /tmp/x1k-START $B/dataset-x1k/live/START --only-show-errors
sleep 60
for K in 1 2 3 4; do echo "p$K: $(systemctl is-active x1k@$K) $(tail -1 /data$K/x1k/logs/run.log | cut -c1-200)"; done
echo "R4 done $(date -u +%FT%TZ)"
