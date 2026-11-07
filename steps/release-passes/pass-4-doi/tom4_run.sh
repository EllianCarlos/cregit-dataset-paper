#!/usr/bin/env bash
# tom4_run.sh (the TOM-4 machine; a tool of the stage, so its sha256 is in stage/SHA256SUMS). tom4_start.sh starts
# it as the systemd unit tom4-run (root); the work runs as ec2-user (RUNAS). One run, the steps in order; a step
# with status/STEP.DONE is skipped (a second start continues). The first failed step ends the run (ALERT).
# The DOI pass changes documents only. The 8,449 project files are not downloaded and not uploaded: the new root gets
# them by a server-side S3 copy of TOM-3; Hugging Face keeps them.
#   preflight  the stage inputs, DOI and DATE, the third pass is DONE (TOM3/log/final.status.json; its
#              root_sha256sums starts with TOM3_SUMS_PREFIX), the new root prefix is empty, the Hugging Face token is
#              in SSM, the disk
#   fetch      of TOM-3: SHA256SUMS (its sha256 is root_sha256sums of the final status), the listing (one object
#              for each row), every file outside parquet/, log/values.json (the measured values of the third pass);
#              every fetched file checks against its row; no project file is fetched
#   keep       the 8,449 project files: SHA256SUMS against MANIFEST.tsv (tom4_tools.py keep)
#   footers    the footer of every TOM-3 project file (S3 ranged reads), against the TOM-3 MANIFEST.tsv
#   assemble   the local root: the TOM-3 files outside parquet/ (byte copies), then the docs of the stage over them;
#              the TOM-3 documents that the stage lacks must be exactly REMOVED_DOCS: they leave the root
#   fill       [[tom: KEY]] from the TOM-3 values, TODO-DATE -> DATE, TODO-DOI -> DOI (the expected line counts);
#              after the fill no marker word and no placeholder is left
#   checksums  SHA256SUMS: the TOM-3 rows of the project files, the sha256 of every local file (the removed
#              documents have no row)
#   view       the check view: the local root and a sparse file with the real footer for each project file
#   checks     fill_release.py check (view; no --allow-todo), tom4_tools.py check-root (project rows and KEEP_SAME
#              files = TOM-3, only documents changed, footers, the DOI and the date), sha256sum -c,
#              release_tools.py no-at, no-paths and guard, hf_tools.py precheck and validate-card
#   upload     to s3://B/DEST/root/ (empty prefix; or, after a failed upload of this run, a prefix that holds only
#              files of this root): a server-side copy of TOM-3 parquet/ (--copy-props metadata-directive), then the
#              local root; the listing after (count, sizes); every project object has its TOM-3 ETag (else it is
#              downloaded and hashed) and HASH_SAMPLE project objects are downloaded and hashed
#   hf         (HF=1) the token from SSM to tmpfs; the Hub must hold the TOM-3 root (hf_tools.py verify); push the
#              changed documents and the deletes of REMOVED_DOCS (README.md and SHA256SUMS in the last commit); verify the
#              whole Hub tree against the new SHA256SUMS; the token file deleted
#   end        log/final.status, then shutdown: DONE at once, ALERT after ALERT_HOLD_MIN minutes (L1 sets the stop
#              behavior); NOSHUT=1 or /run/tom4-hold keeps it up.
# Environment (tom4_start.sh sets it): X T PY B RUNAS NOSHUT; TOM_LOCAL=1 for the local rehearsal (TOM3_DIR is a
# local TOM-3 root with its project files, TOM3_LOG_DIR holds its values.json and final.status.json; no S3, no
# Hugging Face, no shutdown).
set -uo pipefail
: "${X:?}" "${T:?}" "${PY:?}" "${B:?}"
. $T/tom4.conf
RUNAS=${RUNAS-ec2-user}; NOSHUT=${NOSHUT:-0}; LOCAL=${TOM_LOCAL:-0}
T3D=${TOM3_DIR:-$X/tom3}; T3L=${TOM3_LOG_DIR:-$X/tom3-log}; R=$X/root; V=$X/view; FT=$X/footers
L=$X/log; ST=$X/status; WK=$X/work
D4=$B/$DEST; T33=$B/$TOM3_ROOT; BKT=${B#s3://}
T2="$PY -I -B $T/tom2_tools.py"; T4="$PY -I -B $T/tom4_tools.py"
FR="$PY -I -B $R/tools/fill_release.py"; RT="$PY -I -B $T/release_tools.py"
HFPY=${HF_PY:-$PY}; HT="$HFPY -I -B $T/hf_tools.py"; H2="$HFPY -I -B $T/tom2_tools.py"
NP=$(nproc)
mkdir -p $L $ST $WK
if [ -n "$RUNAS" ]; then
  AS="runuser -u $RUNAS -- env HOME=/home/$RUNAS PATH=$PATH AWS_REGION=us-west-2 AWS_RETRY_MODE=adaptive AWS_MAX_ATTEMPTS=10 PYTHONDONTWRITEBYTECODE=1"
  chown "$RUNAS": $X $L $ST $WK
else
  AS="env PYTHONDONTWRITEBYTECODE=1"
fi
log() { echo "[$(date -u +%FT%TZ)] $*"; }
t0=$(date +%s)
s3put() { [ "$LOCAL" = 1 ] && return 0; $AS aws s3 cp "$1" "$D4/log/$2" --only-show-errors || echo "log upload failed: $2"; }
put_log() {
  local f
  for f in $L/*.txt $L/*.json $L/*.jsonl $L/*.tsv; do [ -f "$f" ] && s3put "$f" "$(basename "$f")"; done
  for f in $ST/*; do [ -f "$f" ] && s3put "$f" "status/$(basename "$f")"; done
  [ -f $X/run.log ] && tail -300 $X/run.log | sed "s/$(printf '\100')/(at)/g" > $L/run.tail.txt && s3put $L/run.tail.txt run.tail.txt
  return 0
}
FAILED=""
fail() { log "FAIL: $*"; FAILED="$*"; }
todo() { [ -z "$FAILED" ] && [ ! -f $ST/$1.DONE ]; }
done_step() { echo "$1 DONE $(date -u +%FT%TZ)${2:+ $2}" > $ST/$1.DONE; log "step $1 done${2:+: $2}"; put_log; }
run_to() { local f=$1; shift; $AS "$@" >> $L/$f 2>&1; }
mkdir_as() { $AS mkdir -p "$@"; }
VAL=(--doi "$DOI" --date "$DATE" --pattern "$DOI_PATTERN" --date-min "$DATE_MIN" --date-max "$DATE_MAX")

finish() {
  local st=DONE why="all steps ok"
  [ -n "$FAILED" ] && { st=ALERT; why="$FAILED"; }
  local steps; steps=$(find $ST -maxdepth 1 -name '*.DONE' -printf '%f\n' | sed 's/\.DONE$//' | LC_ALL=C sort | paste -sd' ')
  echo "tom4 run $st $(date -u +%FT%TZ) after $(( $(date +%s) - t0 )) s: $why; steps done: ${steps:-none}" > $ST/run.$st
  rm -f "$ST/run.$([ $st = DONE ] && echo ALERT || echo DONE)"
  cat $ST/run.$st
  { echo "{"; echo "  \"status\": \"$st\","; echo "  \"utc\": \"$(date -u +%FT%TZ)\","
    echo "  \"why\": \"$(echo "$why" | tr '"' "'" | sed "s/$(printf '\100')/(at)/g")\","
    echo "  \"steps_done\": \"${steps:-}\","; echo "  \"root\": \"s3://.../$DEST/root/\","
    echo "  \"doi\": \"$DOI\","; echo "  \"date\": \"$DATE\","
    echo "  \"root_sha256sums\": \"$(sha256sum $R/SHA256SUMS 2>/dev/null | cut -c1-64)\","
    echo "  \"uploaded\": $([ -f $ST/upload.DONE ] && echo true || echo false),"
    echo "  \"hf\": \"$(cat $ST/hf.DONE $ST/hf.SKIP 2>/dev/null | head -1 | tr '"' "'")\""; echo "}"; } > $L/final.status.json
  cp $ST/run.$st $L/final.status.txt
  put_log
  [ "$LOCAL" = 1 ] && { [ $st = DONE ]; return; }
  if [ "$NOSHUT" = 1 ] || [ -e /run/tom4-hold ] || [ -e /home/ec2-user/NO_SHUTDOWN ]; then
    log "no shutdown (NOSHUT=1 or a hold file)"
  elif [ $st = DONE ]; then
    log "shutdown in 1 min (the stop behavior of L1: the instance stops)"; shutdown -h +1
  else
    log "ALERT: shutdown in $ALERT_HOLD_MIN min (K1-tom4-hold.sh ACTION=hold keeps the machine)"; shutdown -h +$ALERT_HOLD_MIN
  fi
  [ $st = DONE ]
}

log "tom4 run (DOI pass): $T33/ -> $D4/root/; DOI $DOI, date $DATE; $NP vCPU, $(free -g | awk '/Mem:/{print $2}') GiB; local $LOCAL"

# ---- preflight
if todo preflight; then
  for f in $T/docs/README.md $T/docs/CITATION.cff $T/docs/tools/fill_release.py $T/tom_tools.py $T/tom2_tools.py $T/tom4_tools.py; do
    [ -f $f ] || fail "the stage lacks $f"
  done
  run_to preflight.txt $T4 validate "${VAL[@]}" || fail "DOI or DATE (log/preflight.txt)"
  [[ $EXPECT_DOI_LINES =~ ^[1-9][0-9]*$ && $EXPECT_DATE_LINES =~ ^[1-9][0-9]*$ ]] || fail "EXPECT_DOI_LINES and EXPECT_DATE_LINES are not set (S1 counts them)"
  if [ -n "$(ls -A $R 2>/dev/null)" ]; then fail "$R exists and is not empty (a new run takes a new machine)"; fi
  if [ "$LOCAL" != 1 ] && [ -z "$FAILED" ]; then
    mkdir_as $T3L
    $AS aws s3 cp $B/$TOM3/log/final.status.json $T3L/final.status.json --only-show-errors || fail "no $TOM3/log/final.status.json"
    $AS aws s3 cp $B/$TOM3/log/values.json $T3L/values.json --only-show-errors || fail "no $TOM3/log/values.json"
    n=$({ $AS aws s3 ls --recursive $D4/root/ 2>/dev/null || true; } | wc -l)
    [ "$n" = 0 ] || fail "$D4/root/ is not empty ($n objects): the run never writes over a root"
    if [ "$HF" = 1 ]; then
      nm=$(aws ssm get-parameter --region us-west-2 --name $HF_SSM_PARAM --query Parameter.Name --output text 2>/dev/null)
      [ "$nm" = "$HF_SSM_PARAM" ] || fail "no Hugging Face token in $HF_SSM_PARAM (the user runs ../dataset-hf/T1-hf-token-put.sh)"
    fi
    avail=$(df -BG --output=avail $X | tail -1 | tr -dc '0-9')
    [ "$avail" -ge 20 ] || fail "$X has $avail GB free, need 20"
  fi
  if [ -z "$FAILED" ]; then
    st3=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['status'])" $T3L/final.status.json)
    want3=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['root_sha256sums'])" $T3L/final.status.json)
    [ "$st3" = DONE ] || fail "the third pass is $st3, not DONE"
    case $want3 in "$TOM3_SUMS_PREFIX"*) ;; *) fail "the TOM-3 root_sha256sums ${want3:0:12} does not start with $TOM3_SUMS_PREFIX" ;; esac
    [ -z "$TOM3_SUMS_SHA" ] || [ "$TOM3_SUMS_SHA" = "$want3" ] || fail "TOM3_SUMS_SHA ${TOM3_SUMS_SHA:0:12} is not the final status ${want3:0:12}"
    echo "$want3" > $WK/tom3.sums.sha
  fi
  [ -z "$FAILED" ] && done_step preflight "DOI $DOI, date $DATE; docs $(find $T/docs -type f | wc -l) files; TOM-3 SHA256SUMS $(cut -c1-12 $WK/tom3.sums.sha)"
fi

# ---- fetch: TOM-3 without parquet/
if todo fetch; then
  if [ "$LOCAL" != 1 ]; then
    mkdir_as $T3D
    $AS aws s3 cp $T33/SHA256SUMS $T3D/SHA256SUMS --only-show-errors || fail "download of the TOM-3 SHA256SUMS"
    if [ -z "$FAILED" ]; then
      $AS aws s3 ls --recursive $T33/ > $WK/ls.tom3.txt || fail "the TOM-3 listing"
      base=${T33#s3://*/}
      nobj=$(wc -l < $WK/ls.tom3.txt); nrow=$(wc -l < $T3D/SHA256SUMS)
      miss=$(awk '{print $2}' $T3D/SHA256SUMS | sed "s#^#$base/#" | LC_ALL=C sort | LC_ALL=C comm -23 - <(awk '{print $4}' $WK/ls.tom3.txt | LC_ALL=C sort) | wc -l)
      [ "$nobj" = $((nrow + 1)) ] && [ "$miss" = 0 ] || fail "the TOM-3 root has $nobj objects for $nrow SHA256SUMS rows ($miss rows without an object)"
    fi
    [ -z "$FAILED" ] && { run_to fetch.txt aws s3 sync $T33/ $T3D/ --exclude "parquet/*" --only-show-errors || fail "download of the TOM-3 files"; }
  fi
  if [ -z "$FAILED" ]; then
    [ "$(sha256sum $T3D/SHA256SUMS | cut -d' ' -f1)" = "$(cat $WK/tom3.sums.sha)" ] || fail "the TOM-3 SHA256SUMS is not $(cut -c1-12 $WK/tom3.sums.sha)"
  fi
  if [ -z "$FAILED" ]; then
    grep -v '  parquet/' $T3D/SHA256SUMS > $WK/t3.other.sums
    (cd $T3D && sha256sum --quiet --strict -c $WK/t3.other.sums) >> $L/fetch.txt 2>&1 || fail "a fetched TOM-3 file does not check (log/fetch.txt)"
    nloc=$(cd $T3D && find . -type f ! -name SHA256SUMS ! -path './parquet/*' | wc -l)
    [ "$nloc" = "$(wc -l < $WK/t3.other.sums)" ] || fail "fetched $nloc files for $(wc -l < $WK/t3.other.sums) rows outside parquet/"
    [ "$LOCAL" = 1 ] || [ ! -e $T3D/parquet ] || fail "a project file was fetched"
  fi
  [ -z "$FAILED" ] && done_step fetch "TOM-3 $(wc -l < $WK/t3.other.sums) files outside parquet/, $(du -sb --exclude=parquet $T3D | cut -f1) B, every file = its row"
fi

# ---- keep
if todo keep; then
  run_to keep.txt $T4 keep --sums $T3D/SHA256SUMS --manifest $T3D/MANIFEST.tsv --out-dir $WK --expect $EXPECT_FILES \
    --max $MAX_PARQUET_FILES || fail "the project files (log/keep.txt)"
  [ -z "$FAILED" ] && done_step keep "$(tail -1 $L/keep.txt)"
fi

# ---- footers
if todo footers; then
  mkdir_as $FT
  if [ "$LOCAL" = 1 ]; then FSRC=(--local "$T3D"); else FSRC=(--s3 "$BKT/$TOM3_ROOT"); fi
  run_to footers.txt $T2 footers --keep $WK/keep.resolved.tsv --manifest $T3D/MANIFEST.tsv --out-dir $FT "${FSRC[@]}" \
    --jobs $FOOTER_JOBS --first $FOOTER_FIRST || fail "the TOM-3 footers (log/footers.txt)"
  [ -z "$FAILED" ] && done_step footers "$(tail -1 $L/footers.txt)"
fi

# ---- assemble: TOM-3 outside parquet/, then the docs of the stage
if todo assemble; then
  mkdir_as $R
  set -f
  for f in $(awk '{print $2}' $WK/t3.other.sums); do
    mkdir_as "$(dirname "$R/$f")"; $AS cp "$T3D/$f" "$R/$f" || fail "copy of the TOM-3 file $f"
  done
  (cd $R && sha256sum --quiet --strict -c $WK/t3.other.sums) || fail "the copied TOM-3 files are not byte-identical"
  docs=$(cd $T/docs && find . -type f | sed 's#^\./##' | LC_ALL=C sort)
  for f in $docs; do
    mkdir_as "$(dirname "$R/$f")"; $AS cp "$T/docs/$f" "$R/$f" || fail "copy of the document $f"
  done
  for s in $KEEP_SAME; do echo "$docs" | grep -q "^$s" && fail "the docs input holds $s (a file of KEEP_SAME)"; done
  # the removed documents: the TOM-3 documents that the docs input does not have; exactly REMOVED_DOCS
  miss=$(grep -v '  parquet/\|  organizations/\|  ledgers.parquet$\|  links.json$\|  pseudonymization.json$\|  MANIFEST.tsv$' $T3D/SHA256SUMS \
         | awk '{print $2}' | while read -r f; do echo "$docs" | grep -qxF "$f" || echo "$f"; done | LC_ALL=C sort | paste -sd' ')
  want=$(echo $REMOVED_DOCS | tr ' ' '\n' | grep . | LC_ALL=C sort | paste -sd' ')
  [ "$miss" = "$want" ] || fail "the TOM-3 documents that the docs input lacks ($miss) are not REMOVED_DOCS ($want)"
  if [ -z "$FAILED" ]; then for f in $miss; do $AS rm -f "$R/$f"; done; echo "$miss" > $L/removed.txt; fi
  set +f
  [ -z "$FAILED" ] && done_step assemble "$(find $R -type f | wc -l) files ($(echo "$docs" | wc -l) documents of the stage); removed: ${miss:-none}"
fi

# ---- fill: the DOI, the date and the placeholders
if todo fill; then
  run_to fill.txt $T4 fill --root $R --values $T3L/values.json "${VAL[@]}" --expect-doi-lines $EXPECT_DOI_LINES \
    --expect-date-lines $EXPECT_DATE_LINES --apply || fail "the fill (log/fill.txt)"
  [ -z "$FAILED" ] && done_step fill "$(tail -1 $L/fill.txt)"
fi

# ---- checksums
if todo checksums; then
  run_to checksums.txt $T2 sums --root $R --tom1-sums $T3D/SHA256SUMS --plan $WK/plan.tsv --changed-out $WK/changed.list \
    --gone-out $WK/gone.list --jobs $NP || fail "SHA256SUMS (log/checksums.txt)"
  [ -z "$FAILED" ] && { cp $R/SHA256SUMS $L/root.SHA256SUMS; cp $WK/changed.list $L/changed.list.txt; cp $WK/gone.list $L/gone.list.txt; }
  [ -z "$FAILED" ] && done_step checksums "SHA256SUMS $(sha256sum $R/SHA256SUMS | cut -c1-12), $(wc -l < $R/SHA256SUMS) rows; changed: $(paste -sd' ' $WK/changed.list)"
fi

# ---- view
if todo view; then
  run_to view.txt $T4 view --root $R --tails $FT --keep $WK/keep.pf.tsv --out $V || fail "the check view (log/view.txt)"
  [ -z "$FAILED" ] && done_step view "$(tail -1 $L/view.txt)"
fi

# ---- checks (every check runs; the step fails when one fails)
if todo checks; then
  CF=""
  run_to check.fill.txt $FR check --root $V || CF="$CF fill_release-check"
  run_to check.root.txt $T4 check-root --root $R --view $V --tom3-sums $T3D/SHA256SUMS --keep $WK/keep.pf.tsv \
    --doi "$DOI" --date "$DATE" --schema-version $SCHEMA_VERSION --keep-same "$KEEP_SAME" --removed "$REMOVED_DOCS" \
    --want-columns $EXPECT_COLUMNS --expect-rows $EXPECT_ROWS --expect-doi-lines $EXPECT_DOI_LINES --jobs $NP \
    --out $L/check-root.json || CF="$CF check-root"
  (cd $R && while read -r d f; do [ -f "$f" ] && echo "$d  $f"; done < SHA256SUMS > $WK/local.sums && sha256sum --quiet --strict -c $WK/local.sums) > $L/check.sums.txt 2>&1 || CF="$CF sha256sum-c"
  nloc=$(cd $R && find . -type f ! -name SHA256SUMS | wc -l); [ "$nloc" = "$(wc -l < $WK/local.sums)" ] || CF="$CF local-rows"
  nf=$(find $V -type f | wc -l); rows=$(wc -l < $R/SHA256SUMS); [ "$nf" = $((rows + 1)) ] || CF="$CF view-files($nf)!=rows+1($rows)"
  run_to check.release.txt $RT no-at --root $R || CF="$CF no-at"
  run_to check.release.txt $RT no-paths --root $R || CF="$CF no-paths"
  run_to check.release.txt $RT guard --root $V --names $WK/keep.names || CF="$CF guard"
  run_to check.hf.txt $HT precheck --root $V --out $L/hf-precheck.txt \
    --limit MAX_ENTRIES=$HF_MAX_ENTRIES_PER_FOLDER --limit MAX_FILE=$HF_MAX_FILE_BYTES --limit REC_FILE=$HF_REC_FILE_BYTES \
    --limit REC_FILES=$HF_REC_FILES_PER_REPO --limit FREE=$HF_PRIVATE_QUOTA_FREE --limit PRO=$HF_PRIVATE_QUOTA_PRO \
    --limit PUBLIC_NOTE=$HF_PUBLIC_NOTE_BYTES --visibility $HF_VISIBILITY --quota 0 || CF="$CF hf-precheck"
  run_to check.hf.txt $HT validate-card --card $R/README.md || CF="$CF card"
  echo "checks: view files $nf; local files $nloc; failed:${CF:- none}" | tee -a $L/checks.txt
  [ -z "$CF" ] && done_step checks "$(tail -1 $L/check.root.txt | cut -c1-300)" || fail "checks:$CF (log/check.*.txt)"
fi

# ---- upload: the new root (a server-side copy of the project files, then the local files)
if todo upload; then
  if [ "$LOCAL" = 1 ]; then
    echo "local: no upload" > $ST/upload.SKIP
  else
    lsr() { $AS aws s3api list-objects-v2 --bucket $BKT --prefix "$1" --query 'Contents[].[Key,Size,ETag]' --output text | grep -v '^None$' || true; }
    (cd $V && find . -type f | sed 's#^\./##' | while read -r f; do echo "$DEST/root/$f $(stat -c %s "$f")"; done | LC_ALL=C sort) > $WK/want.listing.txt
    lsr "$DEST/root/" | awk '{print $1, $2}' | LC_ALL=C sort > $WK/ls.before.txt
    n=$(wc -l < $WK/ls.before.txt)
    if [ "$n" != 0 ] && [ ! -f $ST/upload.STARTED ]; then
      fail "$D4/root/ is not empty ($n objects) and this machine did not start an upload there"
    elif [ "$n" != 0 ]; then
      other=$(LC_ALL=C comm -23 $WK/ls.before.txt $WK/want.listing.txt | wc -l)
      [ "$other" = 0 ] || fail "$D4/root/ holds $other objects that are not files of this root (path and size)"
      [ -z "$FAILED" ] && { log "upload resume: $n objects there"
        run_to upload.txt aws s3 sync $T33/parquet/ $D4/root/parquet/ --size-only --copy-props metadata-directive --only-show-errors || fail "the S3 copy of the project files (resume)"; }
      [ -z "$FAILED" ] && { run_to upload.txt aws s3 sync $R/ $D4/root/ --size-only --checksum-algorithm SHA256 --only-show-errors || fail "the upload of the local root (resume)"; }
    else
      echo "upload started $(date -u +%FT%TZ)" > $ST/upload.STARTED
      log "server-side copy of the $EXPECT_FILES project files of TOM-3"
      run_to upload.txt aws s3 cp --recursive $T33/parquet/ $D4/root/parquet/ --copy-props metadata-directive --only-show-errors || fail "the S3 copy of the project files"
      [ -z "$FAILED" ] && { run_to upload.txt aws s3 cp --recursive $R/ $D4/root/ --checksum-algorithm SHA256 --only-show-errors || fail "the upload of the local root"; }
    fi
    if [ -z "$FAILED" ]; then
      lsr "$DEST/root/" > $WK/ls.root.txt; lsr "$TOM3_ROOT/parquet/" > $WK/ls.tom3.etag.txt
      miss=$(LC_ALL=C comm -3 $WK/want.listing.txt <(awk '{print $1, $2}' $WK/ls.root.txt | LC_ALL=C sort) | wc -l)
      nobj=$(wc -l < $WK/ls.root.txt); nf=$(find $V -type f | wc -l)
      [ "$miss" = 0 ] && [ "$nobj" = "$nf" ] || fail "after the upload: $nobj objects for $nf files, $miss differences in path or size"
    fi
    if [ -z "$FAILED" ]; then
      # the ETag of each copied project object against TOM-3; the others are downloaded and hashed
      LC_ALL=C join -a1 <(sed "s#^$TOM3_ROOT/parquet/##" $WK/ls.tom3.etag.txt | awk '{print $1, $3}' | LC_ALL=C sort) \
                        <(grep "^$DEST/root/parquet/" $WK/ls.root.txt | sed "s#^$DEST/root/parquet/##" | awk '{print $1, $3}' | LC_ALL=C sort) \
        | awk '$2 != $3 {print "parquet/" $1}' > $WK/etag.diff
      same=$(( EXPECT_FILES - $(wc -l < $WK/etag.diff) ))
      run_to upload.txt $T4 sample --sums $R/SHA256SUMS --n $HASH_SAMPLE --seed "$HASH_SEED" --out $WK/hash.sample
      sort -u $WK/etag.diff $WK/hash.sample > $WK/hash.list
      mkdir_as $WK/h; bad=0
      while read -r f; do
        $AS aws s3 cp "$D4/root/$f" $WK/h/obj --only-show-errors || { bad=$((bad + 1)); continue; }
        [ "$(sha256sum $WK/h/obj | cut -d' ' -f1)" = "$(awk -v f="$f" '$2 == f {print $1}' $R/SHA256SUMS)" ] || { bad=$((bad + 1)); echo "HASH MISMATCH $f" >> $L/upload.txt; }
        rm -f $WK/h/obj
      done < $WK/hash.list
      echo "copies: $same of $EXPECT_FILES project objects have the TOM-3 ETag; $(wc -l < $WK/hash.list) objects downloaded and hashed, $bad differ" | tee -a $L/upload.txt
      [ "$bad" = 0 ] || fail "the S3 copy: $bad project objects are not their SHA256SUMS row (log/upload.txt)"
      awk '{print $1, $2}' $WK/ls.root.txt | sed "s#^$DEST/root/##" > $L/root.listing.txt
      [ -z "$FAILED" ] && done_step upload "$nobj objects, $(awk '{s+=$2} END {printf "%d", s}' $WK/ls.root.txt) B; ETags $same/$EXPECT_FILES; hashed $(wc -l < $WK/hash.list), 0 differ"
    fi
  fi
fi

# ---- Hugging Face (only when every step before is DONE)
if [ -z "$FAILED" ] && [ ! -f $ST/hf.DONE ]; then
  if [ "$HF" != 1 ] || [ "$LOCAL" = 1 ]; then
    echo "hf skipped (HF=$HF, local $LOCAL)" > $ST/hf.SKIP
  else
    [ "$HF_VISIBILITY" = public ] || [ "$HF_VISIBILITY" = private ] || fail "HF_VISIBILITY is $HF_VISIBILITY"
    TOK=$HF_TOKEN_DIR/token
    if [ -z "$FAILED" ]; then
      install -d -m 700 -o $RUNAS -g $RUNAS $HF_TOKEN_DIR
      (umask 077; aws ssm get-parameter --region us-west-2 --name $HF_SSM_PARAM --with-decryption --query Parameter.Value \
         --output text 2>/dev/null | tr -d '[:space:]' > $TOK); chown $RUNAS: $TOK
      [ -s $TOK ] || { rm -f $TOK; fail "no Hugging Face token in $HF_SSM_PARAM (the user runs ../dataset-hf/T1-hf-token-put.sh)"; }
    fi
    if [ -z "$FAILED" ]; then
      HAS="runuser -u $RUNAS -- env HOME=/home/$RUNAS HF_HOME=$X/hf-home HF_TOKEN_PATH=$TOK HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_PROGRESS_BARS=1"
      if [ ! -f $ST/hf-pre.DONE ]; then
        $HAS $HT verify --repo $HF_REPO --sums $T3D/SHA256SUMS --out $L/hf-preverify.txt --expect $HF_VISIBILITY >> $L/hf.txt 2>&1; rc=$?
        if [ $rc = 0 ]; then echo "hf-pre DONE $(date -u +%FT%TZ)" > $ST/hf-pre.DONE
        elif [ "$HF_PRE_VERIFY" = require ]; then fail "the Hub is not the TOM-3 root (log/hf-preverify.txt); HF_PRE_VERIFY=skip pushes anyway"
        else log "the Hub is not the TOM-3 root (HF_PRE_VERIFY=$HF_PRE_VERIFY): push anyway"; fi
      fi
      [ -z "$FAILED" ] && { $HAS $H2 hf-push --repo $HF_REPO --root $R --adds $WK/changed.list --deletes $WK/gone.list \
        --expect $HF_VISIBILITY --message "TOM 1.0.0: DOI $DOI, release date $DATE" >> $L/hf.txt 2>&1 || fail "hf push (log/hf.txt)"; }
      [ -z "$FAILED" ] && { $HAS $HT verify --repo $HF_REPO --sums $R/SHA256SUMS --card $R/README.md --out $L/hf-verify.txt \
        --expect $HF_VISIBILITY >> $L/hf.txt 2>&1 || fail "hf verify (log/hf-verify.txt)"; }
    fi
    rm -f $TOK
    [ -e $TOK ] && fail "the token file is still there"
    [ -z "$FAILED" ] && { echo "hf DONE $(date -u +%FT%TZ) repo $HF_REPO ($HF_VISIBILITY); $(wc -l < $WK/changed.list) changed documents and SHA256SUMS pushed; $(wc -l < $WK/gone.list) deletes; token file deleted" > $ST/hf.DONE; put_log; }
  fi
fi

finish
