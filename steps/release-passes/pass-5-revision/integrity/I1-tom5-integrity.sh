#!/usr/bin/env bash
# I1-tom5-integrity.sh (the TOM-5 machine, root, through ssm-tom5.sh; EXPORTS="ACTION=start|status"): the integrity
# check of the published root s3://B/DEST/root/ (integrity_check.py, the analogue of PRAGMA integrity_check).
#   ACTION=start   (default) the checks below, then the systemd unit tom5-integrity starts and this script returns:
#                  1. download: aws s3 sync of the published root to /data1/integrity/root (the machine role);
#                     the local files must be the S3 listing (path and size)
#                  2. the downloaded SHA256SUMS must be the SHA256SUMS of the release run (log/final.status.json)
#                  3. integrity_check.py check (ec2-user, the kit venv, all vCPUs) -> /data1/integrity/out/
#                  4. upload of the report to s3://B/DEST/integrity/run-<utc>/ (never into root/)
#   ACTION=status  the unit state, the last log lines and the result line (short: SSM cuts at about 2,500 chars)
# The script integrity_check.py comes from s3://B/DEST/integrity/tools/ (U2, the user) and must have WANT_CHECK.
# It refuses: another instance, a release run that is not DONE or that runs, no hold (/run/tom5-hold), a scheduled
# shutdown, other tool versions, too little disk. FORCE=1 starts again after an earlier integrity run.
# Options (EXPORTS): JOBS (default nproc), NO_MINMAX=1 (faster: no min/max check), VIEW_TIMEOUT (s, default 7200).
set -uo pipefail
WANT_IID=${WANT_IID:-INSTANCE_ID}
WANT_CHECK=1c9ea571592fa84c73318035223c4ecbbee0de9fae24ae6115980ce5b538e30e
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)
[ "$IID" = "$WANT_IID" ] || { echo "ABORT: this is $IID, not the TOM-5 machine $WANT_IID"; exit 1; }
X=${TOM_X:-/data/tom5}; T=$X/tools; PY=$X/venv/bin/python
. $T/tom5.conf
W=${INTEG_DIR:-/data1/integrity}; UNIT=tom5-integrity
B=s3://$BUCKET; ROOT=$B/$DEST/root; IP=$B/$DEST/integrity
ACTION=${ACTION:-start}

status() {
  echo "unit $UNIT: $(systemctl is-active $UNIT 2>/dev/null); $(cat $W/status/state 2>/dev/null || echo 'no state')"
  [ -f $W/run.log ] && tail -n ${TAILN:-8} $W/run.log | cut -c1-230
  [ -f $W/status/result ] && cut -c1-600 $W/status/result
  df -h --output=avail,pcent /data1 | tail -1 | sed 's/^/disk \/data1 free: /'
}
case $ACTION in
  status) status; exit 0 ;;
  start) ;;
  *) echo "ABORT: ACTION is start or status"; exit 1 ;;
esac

fail() { echo "ABORT: $*"; exit 1; }
[ -f $X/status/run.DONE ] || fail "the release run is not DONE ($X/status/run.DONE)"
[ -f $X/status/upload.DONE ] || fail "the release run has no upload.DONE"
systemctl is-active -q tom5-run && fail "the unit tom5-run runs"
systemctl is-active -q $UNIT && fail "the unit $UNIT runs (ACTION=status)"
[ -e /run/tom5-hold ] || fail "no hold: run K1-tom5-hold.sh ACTION=hold first (the check takes about 2 h)"
[ -f /run/systemd/shutdown/scheduled ] && fail "a shutdown is scheduled (K1-tom5-hold.sh ACTION=hold cancels it)"
[ -f $W/status/state ] && [ "${FORCE:-0}" != 1 ] && fail "an earlier integrity run: $(cat $W/status/state) (FORCE=1 starts again)"
v=$($PY -I -B -c "import pyarrow, duckdb; print(pyarrow.__version__, duckdb.__version__)") || fail "the venv $PY"
[ "$v" = "$PYARROW $DUCKDB" ] || fail "the venv has pyarrow/duckdb $v, not $PYARROW $DUCKDB"
want_sums=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['root_sha256sums'])" $X/log/final.status.json) \
  || fail "no root_sha256sums in $X/log/final.status.json"
[ ${#want_sums} = 64 ] || fail "root_sha256sums is '$want_sums'"

AS="runuser -u ec2-user -- env HOME=/home/ec2-user AWS_REGION=us-west-2 AWS_RETRY_MODE=adaptive AWS_MAX_ATTEMPTS=10 PYTHONDONTWRITEBYTECODE=1"
install -d -o ec2-user -g ec2-user $W $W/tools $W/status $W/duckdb-tmp
if [ -d $W/out ]; then mv $W/out $W/out.$(date -u +%Y%m%dT%H%M%SZ); fi
rm -f $W/status/state $W/status/result
$AS aws s3 cp $IP/tools/integrity_check.py $W/tools/integrity_check.py --only-show-errors || fail "download of $IP/tools/integrity_check.py (U2 first)"
[ "$(sha256sum $W/tools/integrity_check.py | cut -d' ' -f1)" = $WANT_CHECK ] || fail "integrity_check.py is not ${WANT_CHECK:0:12}"
$AS $PY -I -B $W/tools/integrity_check.py check --help > /dev/null || fail "integrity_check.py does not run"
size=$($AS aws s3 ls --recursive --summarize $ROOT/ | awk '/Total Size/ {print $3}')
[ -n "$size" ] || fail "the listing of $ROOT/"
have=$(du -sb $W/root 2>/dev/null | cut -f1); have=${have:-0}
avail=$(df -B1 --output=avail /data1 | tail -1 | tr -dc '0-9')
[ $(( avail + have )) -ge $(( size + 60000000000 )) ] || fail "/data1 has $(( avail / 1000000000 )) GB free; the root needs $(( size / 1000000000 )) GB + 60 GB"

cat > $W/aws.conf <<EOF
[default]
region = us-west-2
s3 =
  max_concurrent_requests = 64
  max_queue_size = 10000
  multipart_chunksize = 64MB
EOF
chown ec2-user: $W/aws.conf

cat > $W/run.sh <<EOF
#!/usr/bin/env bash
# The unit $UNIT (written by I1-tom5-integrity.sh $(date -u +%FT%TZ)).
set -uo pipefail
W=$W; ROOT=$ROOT; IP=$IP; BKT=$BUCKET; PFX=$DEST/root/; PY=$PY; WANT_SUMS=$want_sums
STAMP=\$(date -u +%Y%m%dT%H%M%SZ)
AS="$AS AWS_CONFIG_FILE=$W/aws.conf"
st() { echo "\$* \$(date -u +%FT%TZ)" > \$W/status/state; echo "[\$(date -u +%FT%TZ)] \$*"; }
end() { echo "\$1" > \$W/status/result; st "\$2"; exit \$3; }
st "download: \$ROOT/"
t0=\$(date +%s)
\$AS aws s3 sync \$ROOT/ \$W/root/ --delete --only-show-errors || end "ALERT: the download failed" ALERT 1
t1=\$(date +%s)
\$AS aws s3api list-objects-v2 --bucket \$BKT --prefix \$PFX --query 'Contents[].[Key,Size]' --output text \\
  | sed "s#^\$PFX##" | awk '{print \$1, \$2}' | LC_ALL=C sort > \$W/s3.listing.txt || end "ALERT: the S3 listing failed" ALERT 1
(cd \$W/root && find . -type f -printf '%P %s\n' | LC_ALL=C sort) > \$W/local.listing.txt
nd=\$(LC_ALL=C comm -3 \$W/s3.listing.txt \$W/local.listing.txt | wc -l)
[ "\$nd" = 0 ] || end "ALERT: the download is not the S3 listing (\$nd differences)" ALERT 1
got=\$(sha256sum \$W/root/SHA256SUMS | cut -d' ' -f1)
[ "\$got" = "\$WANT_SUMS" ] || [ "${ALLOW_SUMS_CHANGE:-0}" = 1 ] || end "ALERT: the S3 SHA256SUMS is \${got:0:12}, the release run wrote \${WANT_SUMS:0:12}" ALERT 1
st "check: \$(wc -l < \$W/s3.listing.txt) objects, \$(awk '{s+=\$2} END {printf "%d", s}' \$W/s3.listing.txt) B downloaded in \$(( t1 - t0 )) s"
\$AS \$PY -I -B \$W/tools/integrity_check.py check --root \$W/root --out \$W/out --jobs ${JOBS:-$(nproc)} \\
  --expect-files $EXPECT_FILES --expect-columns $EXPECT_COLUMNS --max-files $MAX_PARQUET_FILES --ref parquet/$SHAPE_REF \\
  --root-name $DEST/root --tmp \$W/duckdb-tmp --memory-limit 40GB --view-timeout ${VIEW_TIMEOUT:-7200} \\
  $([ "${NO_MINMAX:-0}" = 1 ] && echo --no-minmax) > \$W/check.log 2>&1; rc=\$?
line=\$(grep '^integrity:' \$W/check.log | tail -1)
[ -f \$W/out/INTEGRITY.md ] || end "ALERT: no report (rc \$rc): \$(tail -3 \$W/check.log | cut -c1-300)" ALERT 1
cp \$W/check.log \$W/s3.listing.txt \$W/out/ 2>/dev/null
echo "download_seconds \$(( t1 - t0 ))" > \$W/out/download.txt
st "upload of the report to \$IP/run-\$STAMP/"
\$AS aws s3 cp --recursive \$W/out/ \$IP/run-\$STAMP/ --checksum-algorithm SHA256 --only-show-errors || end "ALERT: the report upload failed; \$line" ALERT 1
echo \$STAMP > \$W/status/last_run
if [ \$rc = 0 ]; then end "DONE: \$line; report \$IP/run-\$STAMP/" DONE 0
else end "PROBLEMS (rc \$rc): \$line; report \$IP/run-\$STAMP/; first: \$(grep -m3 '^PROBLEM' \$W/check.log | cut -c1-200 | paste -sd'|')" PROBLEMS 1; fi
EOF
bash -n $W/run.sh || fail "run.sh syntax"
RAM=$(free -g | awk '/Mem:/{print $2}')
systemctl reset-failed $UNIT 2>/dev/null || true
systemd-run --unit=$UNIT -p MemoryMax=$(( RAM * 90 / 100 ))G -p OOMPolicy=continue -p WorkingDirectory=$W \
  -p StandardOutput=append:$W/run.log -p StandardError=append:$W/run.log \
  --setenv=PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin --setenv=AWS_REGION=us-west-2 /bin/bash $W/run.sh \
  || fail "systemd-run failed"
echo "START $(date -u +%FT%TZ): unit $UNIT; root $(( size / 1000000000 )) GB; $(nproc) jobs; SHA256SUMS want ${want_sums:0:12}"
sleep 30
status
