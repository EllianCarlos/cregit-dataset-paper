#!/usr/bin/env bash
# x3_run.sh (the x1k links machine; started by M1-x3-start.sh in the unit x1k-links as root; a tool of
# the stage, so its sha256 is in stage/SHA256SUMS). The run of kit x3, step by step:
#   0. in the background: the PLAIN-BLAME logs (only the log files) of done-full/, done-pathfix/,
#      rust-split/out/*/plainblame.log and java-split/out/*/plainblame.log to $X/pb/;
#   1. dataset-v1/raw/ and dataset-x1k/raw/ to $X/raw-v1, $X/raw-x1k (sync); SHA256SUMS has 3,544 and
#      7,209 lines and every file checks (parallel sha256sum); the two sidecars have their sha256;
#   2. per set: x3_report.py inputs, extract_domains_v1.py --inputs --cache (the cache holds addresses
#      and stays on the machine), x3_report.py check-cache (tokens = rows of results.tsv);
#   3. the gate: build_links.py over the v1 cache only; x3_report.py compare-links against the
#      reference links (links-v4.6 of this host): the same mapping hash and the same rows;
#   4. the merged links: build_links.py --cache v1 --cache x1k --sidecar v1 --sidecar x1k; compare-links
#      --subset (each v1 row stays);
#   5. x3_report.py domains (counts, new domains, new namespaces; no address);
#   6. x3_plainblame.py (after step 0);
#   7. x3_report.py no-at over every file of $O; then $O/DONE (all steps ok) or $O/ALERT;
#   8. $O goes to $B/dataset-x1k/links-work/$RUN/ (never the caches or the raw files) only if no file
#      holds the at sign; the size of each file is checked; then the status file DONE or ALERT goes up
#      last; then shutdown -h +5 (the instance terminates) if DONE, unless NOSHUT=1,
#      /home/ec2-user/NO_SHUTDOWN or /run/x3-hold. An ALERT keeps the machine up.
# Environment (M1 sets it): RUN X T PY JOBS TH MEM OV DB REF_MAPPING RUNAS (empty: no runuser) NOSHUT
# B (s3://bucket) WANT_SC_V1 WANT_SC_X1K N_V1 N_X1K. Output: $O = $X/out. A second start skips the
# downloads with a DOWNLOADED file and the extraction of the cached projects (index.json).
set -uo pipefail
: "${RUN:?}" "${X:?}" "${T:?}" "${PY:?}" "${JOBS:?}" "${TH:?}" "${MEM:?}" "${OV:?}" "${DB:?}" "${B:?}"
: "${REF_MAPPING:?}" "${WANT_SC_V1:?}" "${WANT_SC_X1K:?}" "${N_V1:?}" "${N_X1K:?}"
RUNAS=${RUNAS-ec2-user}; NOSHUT=${NOSHUT:-0}
O=$X/out; W=$X/work
mkdir -p $O $W $X/pb
[ -n "$RUNAS" ] && chown -R "$RUNAS": $X
as() { if [ -n "$RUNAS" ]; then runuser -u "$RUNAS" -- env HOME=/home/$RUNAS PATH="$PATH" AWS_REGION=${RUNNER_AWS_REGION} \
         AWS_RETRY_MODE=adaptive AWS_MAX_ATTEMPTS=10 "$@"; else "$@"; fi; }
log() { echo "[$(date -u +%FT%TZ)] $*"; }
BAD=""
bad() { log "FAIL: $*"; BAD="$BAD; $*"; }
t0=$(date +%s)
log "x3 run $RUN: jobs $JOBS, threads $TH, memory $MEM, organisations $OV, db $DB"

# --- 0. PLAIN-BLAME logs (background)
( set -e
  as aws s3 sync $B/dataset-x1k/done-full/ $X/pb/done-full/ --exclude '*' --include '*/state/logs/pipeline-*.log' --only-show-errors
  as aws s3 sync $B/dataset-x1k/done-pathfix/ $X/pb/done-pathfix/ --exclude '*' --include '*/state/logs/pipeline-*.log' --only-show-errors
  for e in rust-split java-split; do
    as aws s3 sync $B/dataset-x1k/$e/out/ $X/pb/$e/out/ --exclude '*' --include '*/plainblame.log' --only-show-errors
  done ) > $W/pb-sync.log 2>&1 &
PB=$!

# --- 1. downloads and sha256
for k in v1 x1k; do
  D=$X/raw-$k; n=$([ $k = v1 ] && echo $N_V1 || echo $N_X1K); want=$([ $k = v1 ] && echo $WANT_SC_V1 || echo $WANT_SC_X1K)
  if [ ! -s $D/DOWNLOADED ]; then
    mkdir -p $D; [ -n "$RUNAS" ] && chown "$RUNAS": $D
    as aws s3 sync $B/dataset-$k/raw/ $D/ --only-show-errors || { bad "download $k"; continue; }
    [ "$(wc -l < $D/SHA256SUMS)" = $n ] || { bad "$k SHA256SUMS has $(wc -l < $D/SHA256SUMS) lines, not $n"; continue; }
    (cd $D && rm -f .chk.* && split -l $(( ($(wc -l < SHA256SUMS) + JOBS - 1) / JOBS )) SHA256SUMS .chk. \
       && printf '%s\n' .chk.* | xargs -P $JOBS -n 1 sha256sum --quiet -c) \
      || { bad "$k sha256 of the files"; continue; }
    rm -f $D/.chk.*
    (cd $D && sha256sum --quiet -c project_meta.$k.final.json.sha256) && [ "$(cut -d' ' -f1 $D/project_meta.$k.final.json.sha256)" = $want ] \
      || { bad "$k sidecar is not $want"; continue; }
    date -u +%FT%TZ > $D/DOWNLOADED
  fi
  log "$k: $(wc -l < $D/SHA256SUMS) files, $(du -sh --apparent-size $D/parquet | cut -f1), sha256 OK, sidecar $(echo $want | cut -c1-12)"
done
[ -z "$BAD" ] || { log "downloads failed$BAD"; }

# --- 2. extraction
for k in v1 x1k; do
  [ -s $X/raw-$k/DOWNLOADED ] || continue
  mkdir -p $W/$k; [ -n "$RUNAS" ] && chown "$RUNAS": $W/$k
  as $PY -I $T/x3_report.py inputs --results $X/raw-$k/results.tsv --root $X/raw-$k --out $W/$k/inputs.tsv || { bad "$k inputs"; continue; }
  s=$(date +%s)
  as $PY -I $T/extract_domains_v1.py --inputs $W/$k/inputs.tsv --cache $W/$k/cache --jobs $JOBS --threads $TH \
     --memory-limit $MEM > $W/$k/extract.log 2>&1 || { tail -3 $W/$k/extract.log | cut -c1-200; bad "$k extraction"; continue; }
  log "$k extraction: $(tail -1 $W/$k/extract.log | cut -c1-120) in $(( $(date +%s) - s )) s"
  as $PY -I $T/x3_report.py check-cache --inputs $W/$k/inputs.tsv --cache $W/$k/cache | tee $O/check-cache.$k.txt | tail -2 \
    ; [ "${PIPESTATUS[0]}" = 0 ] || bad "$k cache check"
done

# --- 3. gate: v1 only
LMEM=${LMEM:-32GB}; LTH=${LTH:-8}
if [ -z "$BAD" ]; then
  as $PY -I $T/build_links.py --organisations-version $OV --db $T/$DB --cache $W/v1/cache \
     --sidecar $X/raw-v1/project_meta.v1.final.json --out $W/links-v1check --memory-limit $LMEM --threads $LTH \
     > $O/links-v1check.stdout.json 2> $W/links-v1check.err || { tail -3 $W/links-v1check.err | cut -c1-200; bad "build_links v1"; }
  [ -f $W/links-v1check/links.json ] && cp $W/links-v1check/links.json $O/links-v1check.links.json
  as $PY -I $T/x3_report.py compare-links --got $W/links-v1check --ref $T/ref-links | tee $O/gate-v1.txt \
    ; [ "${PIPESTATUS[0]}" = 0 ] || bad "the v1 gate (compare-links against the reference links)"
  got=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["mapping_sha256"])' $W/links-v1check/links.json 2>/dev/null)
  [ "$got" = "$REF_MAPPING" ] || bad "v1 mapping hash ${got:0:12} is not ${REF_MAPPING:0:12}"
fi

# --- 4. merged links
if [ -z "$BAD" ]; then
  as $PY -I $T/build_links.py --organisations-version $OV --db $T/$DB --cache $W/v1/cache --cache $W/x1k/cache \
     --sidecar $X/raw-v1/project_meta.v1.final.json --sidecar $X/raw-x1k/project_meta.x1k.final.json \
     --out $W/links-merged --memory-limit $LMEM --threads $LTH > $O/links-merged.stdout.json 2> $W/links-merged.err \
     || { tail -3 $W/links-merged.err | cut -c1-200; bad "build_links merged"; }
  as $PY -I $T/x3_report.py compare-links --got $W/links-merged --ref $T/ref-links --subset | tee $O/check-merged.txt \
    ; [ "${PIPESTATUS[0]}" = 0 ] || bad "merged links: a v1 row changed"
  mkdir -p $O/links-merged
  for f in domain_links.parquet project_links.parquet enterprise_audit.parquet links.json; do
    cp $W/links-merged/$f $O/links-merged/$f || bad "no merged $f"
  done
fi

# --- 5. domain reports
if [ -z "$BAD" ]; then
  as $PY -I $T/x3_report.py domains --v1-cache $W/v1/cache --x1k-cache $W/x1k/cache --links $W/links-merged \
     --v1-sidecar $X/raw-v1/project_meta.v1.final.json --x1k-sidecar $X/raw-x1k/project_meta.x1k.final.json \
     --out $O --memory-limit $LMEM --threads $LTH > $W/domains.log 2>&1 || { tail -3 $W/domains.log | cut -c1-200; bad "domain reports"; }
fi

# --- 6. PLAIN-BLAME
wait $PB; pbrc=$?
[ $pbrc = 0 ] || { tail -3 $W/pb-sync.log | cut -c1-200; bad "PLAIN-BLAME log sync rc $pbrc"; }
if [ -f $X/raw-x1k/results.tsv ]; then
  as $PY -I $T/x3_plainblame.py --results $X/raw-x1k/results.tsv --logs $X/pb --out $O/plainblame.x1k.tsv \
     --summary $O/plainblame.x1k.json | tee $O/plainblame.x1k.txt || bad "PLAIN-BLAME count"
else
  bad "no x1k results.tsv for the PLAIN-BLAME count"
fi

# --- 7. no address in the outputs, status
for f in $W/*/extract.log; do [ -f $f ] && cp $f $O/extract.$(basename $(dirname $f)).log; done
rm -f $O/DONE $O/ALERT
files=$(find $O -type f | sort)
NOAT=0
as $PY -I $T/x3_report.py no-at $files > $O/no-at.txt 2>&1 || { NOAT=1; bad "an output holds the at sign (see no-at.txt on the machine); no upload"; }
tail -1 $O/no-at.txt

# --- 8. upload (only when no output holds the at sign), status, shutdown
DEST=$B/dataset-x1k/links-work/$RUN
if [ $NOAT = 0 ]; then
  as aws s3 cp --recursive $O/ $DEST/ --only-show-errors || bad "upload"
  nbad=0
  for f in $files; do
    k=${f#$O/}; sz=$(as aws s3 ls $DEST/$k | awk '{print $3}')
    [ "$sz" = "$(stat -c %s $f)" ] || nbad=$((nbad + 1))
  done
  [ $nbad = 0 ] && log "uploaded $(echo $files | wc -w) files to $DEST/ (sizes checked)" || bad "upload size check: $nbad files"
fi
st=$([ -z "$BAD" ] && echo DONE || echo ALERT)
echo "x1k-links $st run $RUN $(date -u +%FT%TZ) after $(( $(date +%s) - t0 )) s: ${BAD:-all steps ok}" | sed 's/: ; /: /' > $O/$st
cat $O/$st
[ $NOAT = 0 ] && { as aws s3 cp $O/$st $DEST/$st --only-show-errors || echo "status upload failed"; }
# the unit log (M1 sends the output of this script to $X/run.log), when it holds no at sign
if [ $NOAT = 0 ] && [ -f $X/run.log ]; then
  cp $X/run.log $W/run.log.copy && as $PY -I $T/x3_report.py no-at $W/run.log.copy > /dev/null \
    && as aws s3 cp $W/run.log.copy $DEST/run.log --only-show-errors || echo "run.log not uploaded"
fi
if [ $st = DONE ] && [ "$NOSHUT" != 1 ] && [ ! -e /home/ec2-user/NO_SHUTDOWN ] && [ ! -e /run/x3-hold ]; then
  echo "shutdown in 5 min (the instance terminates)"; shutdown -h +5
fi
[ $st = DONE ]
