#!/usr/bin/env bash
# tom3_run.sh (the TOM-3 machine; a tool of the stage, so its sha256 is in stage/SHA256SUMS). tom3_start.sh starts
# it as the systemd unit tom3-run (root); the work runs as ec2-user (RUNAS). One run, the steps in order; a step
# with status/STEP.DONE is skipped (a second start continues). The first failed step ends the run (ALERT).
#   preflight  the stage inputs, the second pass is DONE (TOM2/log/final.status.json), the new root prefix is empty,
#              the Hugging Face token is in SSM, the disk
#   fetch      the whole TOM-2 root: SHA256SUMS (its sha256 is TOM2_SUMS_SHA or root_sha256sums of the final status),
#              the listing (one object for each row), all files; every file checks against its row, no other file
#   keep       the 8,449 project files: SHA256SUMS against MANIFEST.tsv (tom3_tools.py keep)
#   canary     the file CANARY alone: proof, drop, check; the run stops when it fails
#   prove      the proof of every file (full rows, DuckDB, PROVE_JOBS at a time): no drop starts before all are proved
#   proof      all proofs together (tom3_tools.py proof-sum): every file OK, the rows, the files per archived and fork
#              value, the roster_lang facts; a failed proof stops the run, so nothing is uploaded
#   pass       the drop of DROP_COLUMNS (chunk copy) and its check in every file (largest first, JOBS at a time);
#              log/ledger.jsonl
#   assemble   the local root: the docs of the stage, organizations/, ledgers.parquet, links.json and
#              pseudonymization.json of TOM-2 (byte copies)
#   facts      project_facts.parquet: the TOM-2 rows and one roster_language row per project with a roster_lang value
#   release    release_info.parquet: project_facts_rows and project_facts_sha256 measured again; all other keys stay
#   manifest   MANIFEST.tsv (TOM-2 rows with the new bytes and sha256; fill_release.py manifest of a mini root)
#   markers    the size rule counts, the measured values, the placeholders [[tom: KEY]] and TODO-DATE
#   checksums  SHA256SUMS of every file of the local root
#   checks     fill_release.py check, tom3_tools.py check-root (also every release_info key against its measured
#              value and every view), sha256sum -c, release_tools.py no-at, no-paths and guard, hf_tools.py precheck
#              and validate-card
#   upload     the new root to s3://B/DEST/root/ (an empty prefix; or, after a failed upload of this run, a prefix
#              that holds only files of this root: sync --size-only); the listing after (count and sizes)
#   hf         (HF=1) the token from SSM to tmpfs; the Hub must hold the TOM-2 root (hf_tools.py verify); upload of
#              every file that differs from the Hub (hf_tools.py upload, batches); the allowed deletes; verify of the
#              whole Hub tree against the new SHA256SUMS; the token file deleted
#   end        log/final.status, then shutdown: DONE at once, ALERT after ALERT_HOLD_MIN minutes (L1 sets the stop
#              behavior); NOSHUT=1 or /run/tom3-hold keeps it up.
# A file $X/STOP makes prove and pass start no new file. Environment (tom3_start.sh sets it): X T PY B RUNAS NOSHUT;
# TOM_LOCAL=1 for the local rehearsal (TOM2_DIR is a local TOM-2 root; no S3, no Hugging Face, no shutdown).
set -uo pipefail
: "${X:?}" "${T:?}" "${PY:?}" "${B:?}"
. $T/tom3.conf
RUNAS=${RUNAS-ec2-user}; NOSHUT=${NOSHUT:-0}; LOCAL=${TOM_LOCAL:-0}
T2D=${TOM2_DIR:-$X/tom2}; R=$X/root; L=$X/log; ST=$X/status; WK=$X/work; OUT=$R/parquet
D3=$B/$DEST; T23=$B/$TOM2_ROOT; BKT=${B#s3://}
TT="$PY -I -B $T/tom_tools.py"; T2="$PY -I -B $T/tom2_tools.py"; T3="$PY -I -B $T/tom3_tools.py"
FR="$PY -I -B $R/tools/fill_release.py"; RT="$PY -I -B $T/release_tools.py"
HFPY=${HF_PY:-$PY}; HT="$HFPY -I -B $T/hf_tools.py"; H2="$HFPY -I -B $T/tom2_tools.py"
NP=$(nproc); J=${JOBS:-$(( NP / 2 ))}; [ "$J" -ge 1 ] || J=1
PJ=${PROVE_JOBS:-$(( NP / PROVE_THREADS ))}; [ "$PJ" -ge 1 ] || PJ=1
mkdir -p $L $ST $WK
if [ -n "$RUNAS" ]; then
  AS="runuser -u $RUNAS -- env HOME=/home/$RUNAS PATH=$PATH AWS_REGION=us-west-2 AWS_RETRY_MODE=adaptive AWS_MAX_ATTEMPTS=10 PYTHONDONTWRITEBYTECODE=1"
  chown "$RUNAS": $X $L $ST $WK
else
  AS="env PYTHONDONTWRITEBYTECODE=1"
fi
log() { echo "[$(date -u +%FT%TZ)] $*"; }
t0=$(date +%s)
s3put() { [ "$LOCAL" = 1 ] && return 0; $AS aws s3 cp "$1" "$D3/log/$2" --only-show-errors || echo "log upload failed: $2"; }
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
# sha256sum -c of a sums file in a folder, NP processes (each file once)
par_check() {  # par_check DIR SUMS LOG
  local d=$1 s=$2 lg=$3 p
  rm -f $WK/pc.part.*; split -n l/$NP -d -a 3 "$s" $WK/pc.part.
  for p in $WK/pc.part.*; do [ -s "$p" ] || rm -f "$p"; done
  find $WK -maxdepth 1 -name 'pc.part.*' -print0 | xargs -0 -P $NP -I{} sh -c "cd '$d' && sha256sum --quiet --strict -c '{}'" >> "$lg" 2>&1
}

finish() {
  local st=DONE why="all steps ok"
  [ -n "$FAILED" ] && { st=ALERT; why="$FAILED"; }
  local steps; steps=$(find $ST -maxdepth 1 -name '*.DONE' -printf '%f\n' | sed 's/\.DONE$//' | LC_ALL=C sort | paste -sd' ')
  echo "tom3 run $st $(date -u +%FT%TZ) after $(( $(date +%s) - t0 )) s: $why; steps done: ${steps:-none}" > $ST/run.$st
  rm -f "$ST/run.$([ $st = DONE ] && echo ALERT || echo DONE)"
  cat $ST/run.$st
  { echo "{"; echo "  \"status\": \"$st\","; echo "  \"utc\": \"$(date -u +%FT%TZ)\","
    echo "  \"why\": \"$(echo "$why" | tr '"' "'" | sed "s/$(printf '\100')/(at)/g")\","
    echo "  \"steps_done\": \"${steps:-}\","; echo "  \"root\": \"s3://.../$DEST/root/\","
    echo "  \"root_sha256sums\": \"$(sha256sum $R/SHA256SUMS 2>/dev/null | cut -c1-64)\","
    echo "  \"uploaded\": $([ -f $ST/upload.DONE ] && echo true || echo false),"
    echo "  \"hf\": \"$(cat $ST/hf.DONE $ST/hf.SKIP 2>/dev/null | head -1 | tr '"' "'")\""; echo "}"; } > $L/final.status.json
  cp $ST/run.$st $L/final.status.txt
  put_log
  [ "$LOCAL" = 1 ] && { [ $st = DONE ]; return; }
  if [ "$NOSHUT" = 1 ] || [ -e /run/tom3-hold ] || [ -e /home/ec2-user/NO_SHUTDOWN ]; then
    log "no shutdown (NOSHUT=1 or a hold file)"
  elif [ $st = DONE ]; then
    log "shutdown in 1 min (the stop behavior of L1: the instance stops)"; shutdown -h +1
  else
    log "ALERT: shutdown in $ALERT_HOLD_MIN min (K1-tom3-hold.sh ACTION=hold keeps the machine)"; shutdown -h +$ALERT_HOLD_MIN
  fi
  [ $st = DONE ]
}

log "tom3 run: $T23/ -> $D3/root/; drop: $DROP_COLUMNS; $NP vCPU, $(free -g | awk '/Mem:/{print $2}') GiB, jobs $J, proof jobs $PJ x $PROVE_THREADS threads; local $LOCAL"

# ---- preflight
if todo preflight; then
  for f in $T/docs/README.md $T/docs/tools/fill_release.py $T/tom_tools.py $T/tom2_tools.py $T/tom3_tools.py $T/parquet_rename.py $T/parquet_rename_check.py; do
    [ -f $f ] || fail "the stage lacks $f"
  done
  [ "$(wc -w <<< "$DROP_COLUMNS")" = $((EXPECT_IN_COLUMNS - EXPECT_COLUMNS)) ] || fail "DROP_COLUMNS has not $((EXPECT_IN_COLUMNS - EXPECT_COLUMNS)) names"
  if [ -n "$(ls -A $R 2>/dev/null)" ]; then fail "$R exists and is not empty (a new run takes a new machine)"; fi
  if [ "$LOCAL" != 1 ] && [ -z "$FAILED" ]; then
    $AS aws s3 cp $B/$TOM2/log/final.status.json $L/tom2.final.status.json --only-show-errors || fail "no $TOM2/log/final.status.json"
    if [ -z "$FAILED" ]; then
      st2=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['status'])" $L/tom2.final.status.json)
      want2=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['root_sha256sums'])" $L/tom2.final.status.json)
      [ "$st2" = DONE ] || fail "the second pass is $st2, not DONE"
      [ -z "$TOM2_SUMS_SHA" ] || [ "$TOM2_SUMS_SHA" = "$want2" ] || fail "TOM2_SUMS_SHA ${TOM2_SUMS_SHA:0:12} is not the final status ${want2:0:12}"
      echo "$want2" > $WK/tom2.sums.sha
    fi
    n=$({ $AS aws s3 ls --recursive $D3/root/ 2>/dev/null || true; } | wc -l)
    [ "$n" = 0 ] || fail "$D3/root/ is not empty ($n objects): the run never writes over a root"
    if [ "$HF" = 1 ]; then
      nm=$(aws ssm get-parameter --region us-west-2 --name $HF_SSM_PARAM --query Parameter.Name --output text 2>/dev/null)
      [ "$nm" = "$HF_SSM_PARAM" ] || fail "no Hugging Face token in $HF_SSM_PARAM (the user runs ../dataset-hf/T1-hf-token-put.sh)"
    fi
    avail=$(df -BG --output=avail $X | tail -1 | tr -dc '0-9')
    [ "$avail" -ge 600 ] || fail "$X has $avail GB free, need 600"
  fi
  if [ "$LOCAL" = 1 ]; then sha256sum $T2D/SHA256SUMS | cut -d' ' -f1 > $WK/tom2.sums.sha; fi
  [ -z "$FAILED" ] && done_step preflight "drop $(wc -w <<< "$DROP_COLUMNS") columns, docs $(find $T/docs -type f | wc -l) files, TOM-2 SHA256SUMS $(cut -c1-12 $WK/tom2.sums.sha)"
fi

# ---- fetch: the whole TOM-2 root
if todo fetch; then
  if [ "$LOCAL" != 1 ]; then
    mkdir_as $T2D
    $AS aws s3 cp $T23/SHA256SUMS $T2D/SHA256SUMS --only-show-errors || fail "download of the TOM-2 SHA256SUMS"
    [ -z "$FAILED" ] && [ "$(sha256sum $T2D/SHA256SUMS | cut -d' ' -f1)" != "$(cat $WK/tom2.sums.sha)" ] && fail "the TOM-2 SHA256SUMS is not $(cut -c1-12 $WK/tom2.sums.sha)"
    if [ -z "$FAILED" ]; then
      $AS aws s3 ls --recursive $T23/ > $WK/ls.tom2.txt || fail "the TOM-2 listing"
      base=${T23#s3://*/}
      nobj=$(wc -l < $WK/ls.tom2.txt); nrow=$(wc -l < $T2D/SHA256SUMS)
      miss=$(awk '{print $2}' $T2D/SHA256SUMS | sed "s#^#$base/#" | LC_ALL=C sort | LC_ALL=C comm -23 - <(awk '{print $4}' $WK/ls.tom2.txt | LC_ALL=C sort) | wc -l)
      [ "$nobj" = $((nrow + 1)) ] && [ "$miss" = 0 ] || fail "the TOM-2 root has $nobj objects for $nrow SHA256SUMS rows ($miss rows without an object)"
    fi
    if [ -z "$FAILED" ]; then
      log "download of the TOM-2 root ($(awk '{s+=$3} END {printf "%d", s}' $WK/ls.tom2.txt) B)"
      run_to fetch.txt aws s3 sync $T23/ $T2D/ --only-show-errors --exact-timestamps || fail "download of the TOM-2 root"
    fi
  fi
  if [ -z "$FAILED" ]; then
    [ "$(sha256sum $T2D/SHA256SUMS | cut -d' ' -f1)" = "$(cat $WK/tom2.sums.sha)" ] || fail "the TOM-2 SHA256SUMS changed"
    nloc=$(cd $T2D && find . -type f ! -name SHA256SUMS | wc -l); nrow=$(wc -l < $T2D/SHA256SUMS)
    [ "$nloc" = "$nrow" ] || fail "the TOM-2 copy has $nloc files for $nrow SHA256SUMS rows"
  fi
  if [ -z "$FAILED" ]; then
    par_check $T2D $T2D/SHA256SUMS $L/fetch.txt || fail "a TOM-2 file does not check (log/fetch.txt)"
  fi
  [ -z "$FAILED" ] && done_step fetch "TOM-2 $(wc -l < $T2D/SHA256SUMS) files, $(du -sbL $T2D | cut -f1) B, every file = its SHA256SUMS row"
fi

# ---- keep
if todo keep; then
  run_to keep.txt $T3 keep --sums $T2D/SHA256SUMS --manifest $T2D/MANIFEST.tsv --out-dir $WK --expect $EXPECT_FILES \
    --max $MAX_PARQUET_FILES || fail "the project files (log/keep.txt)"
  if [ -z "$FAILED" ]; then
    cp $WK/keep.tsv $L/keep.tsv
    grep -qP "\t\Q$CANARY\E\t" $WK/keep.tsv || fail "the canary $CANARY is not a TOM-2 project file"
  fi
  [ -z "$FAILED" ] && done_step keep "$(tail -1 $L/keep.txt)"
fi

PROVEARGS=(--keep "$WK/keep.tsv" --src-dir "$T2D/parquet" --out "$L/proof.jsonl" --archived-values "$ARCHIVED_VALUES"
  --in-columns "$EXPECT_IN_COLUMNS" --mem "$MEM_PER_JOB" --progress "$L/progress.json" --stop-file "$X/STOP")
PASSARGS=(--keep "$WK/keep.tsv" --proof "$L/proof.jsonl" --src-dir "$T2D/parquet" --dst "$OUT" --ledger "$L/ledger.jsonl"
  --rename-py "$T/parquet_rename.py" --check-py "$T/parquet_rename_check.py" --drop-columns "$DROP_COLUMNS"
  --want-columns "$EXPECT_COLUMNS" --copy-mode "$COPY_MODE" --progress "$L/progress.json" --stop-file "$X/STOP" --check-dir "$WK/checks")

# ---- canary: one file alone (proof, drop, check); the run stops when it fails
if todo canary; then
  mkdir_as $R $OUT $WK/checks
  echo "$CANARY" > $WK/canary.list
  log "canary: $CANARY"
  run_to canary.txt $T3 prove "${PROVEARGS[@]}" --only-list $WK/canary.list --jobs 1 --threads $NP \
    || fail "the proof of the canary $CANARY failed (log/canary.txt, log/proof.jsonl): the run is stopped"
  [ -z "$FAILED" ] && { run_to canary.txt $T3 pass "${PASSARGS[@]}" --only-list $WK/canary.list --jobs 1 --threads $NP \
    || fail "the drop of the canary $CANARY failed (log/canary.txt, log/ledger.jsonl): the run is stopped"; }
  [ -z "$FAILED" ] && done_step canary "$CANARY: $(grep '^prove summary' $L/canary.txt | tail -1); $(grep '^pass summary' $L/canary.txt | tail -1)"
fi

# ---- prove: every file before any other drop
if todo prove; then
  run_to prove.txt $T3 prove "${PROVEARGS[@]}" --jobs $PJ --threads $PROVE_THREADS; rc=$?
  [ $rc = 3 ] && fail "stopped by $X/STOP (start the run again to continue)"
  [ $rc = 0 ] || [ $rc = 3 ] || fail "a proof failed (log/prove.txt, log/proof.jsonl): no file is dropped, nothing is uploaded"
  [ -z "$FAILED" ] && done_step prove "$(grep '^prove summary' $L/prove.txt | tail -1)"
fi

# ---- proof: all proofs together
if todo proof; then
  run_to proof.txt $T3 proof-sum --keep $WK/keep.tsv --proof $L/proof.jsonl --expect-archived "$EXPECT_ARCHIVED" \
    --expect-fork "$EXPECT_FORK" --expect-rows $EXPECT_ROWS --expect-roster $EXPECT_ROSTER_FACTS --out $L/proof-summary.json \
    || fail "the proof summary (log/proof.txt, log/proof-summary.json): no file is dropped, nothing is uploaded"
  [ -z "$FAILED" ] && done_step proof "$(tail -1 $L/proof.txt | cut -c1-400)"
fi

# ---- pass
if todo pass; then
  run_to pass.txt $T3 pass "${PASSARGS[@]}" --jobs $J --threads 2; rc=$?
  [ $rc = 3 ] && fail "stopped by $X/STOP (start the run again to continue)"
  [ $rc = 0 ] || [ $rc = 3 ] || fail "the pass rc $rc (failures in log/pass.txt and log/ledger.jsonl)"
  if [ -z "$FAILED" ]; then
    (cd $WK && tar -czf $L/checks.tgz checks) && s3put $L/checks.tgz checks.tgz
    done_step pass "$(grep '^pass summary' $L/pass.txt | tail -1)"
  fi
fi

# ---- assemble: the local root around parquet/
if todo assemble; then
  set -f
  for f in $(cd $T/docs && find . -type f | sed 's#^\./##' | LC_ALL=C sort); do
    mkdir_as "$(dirname "$R/$f")"; $AS cp "$T/docs/$f" "$R/$f" || fail "copy of the document $f"
  done
  set +f
  miss=$(grep -v '  parquet/\|  organizations/\|  ledgers.parquet$\|  links.json$\|  pseudonymization.json$\|  MANIFEST.tsv$' $T2D/SHA256SUMS \
         | awk '{print $2}' | while read -r f; do [ -f "$T/docs/$f" ] || case " $ALLOW_GONE " in *" $f "*) ;; *) echo "$f" ;; esac; done)
  [ -z "$miss" ] || fail "the docs input lacks documents of the TOM-2 root: $(echo $miss)"
  mkdir_as $R/organizations
  for f in $T2D/organizations/*; do $AS cp "$f" $R/organizations/ || fail "copy of organizations/$(basename "$f")"; done
  for f in ledgers.parquet links.json pseudonymization.json; do $AS cp $T2D/$f $R/$f || fail "copy of $f"; done
  (cd $R && grep -E '  (organizations/|ledgers\.parquet$|links\.json$|pseudonymization\.json$)' $T2D/SHA256SUMS | sha256sum --quiet --strict -c -) \
    || fail "the copied TOM-2 files are not byte-identical"
  [ -z "$FAILED" ] && { run_to assemble.txt $TT ledgers --src $T2D/ledgers.parquet --keep $WK/keep.pf.tsv --out $WK/ledgers.subset.parquet \
    --jsonl $WK/ledger.project.jsonl --mode subset || fail "the ledger records of ledgers.parquet (log/assemble.txt)"; }
  [ -z "$FAILED" ] && done_step assemble "$(find $R -type f | wc -l) files; $(tail -1 $L/assemble.txt | cut -c1-200)"
fi

# ---- facts: project_facts with the roster_language facts
if todo facts; then
  run_to facts.txt $T3 facts --tom2-facts $T2D/organizations/project_facts.parquet --proof $L/proof.jsonl --keep $WK/keep.tsv \
    --fact-type $ROSTER_FACT_TYPE --expect $EXPECT_ROSTER_FACTS --out $R/organizations/project_facts.parquet || fail "project_facts (log/facts.txt)"
  [ -z "$FAILED" ] && done_step facts "$(tail -1 $L/facts.txt | cut -c1-300)"
fi

# ---- release: release_info.parquet
if todo release; then
  run_to release.txt $T3 release-info --root $R --tom2-root $T2D --changed "$RI_CHANGED" --db-rel organizations/dataset.duckdb \
    --schema-version $SCHEMA_VERSION --expect-keys $EXPECT_RI_KEYS || fail "release_info (log/release.txt)"
  [ -z "$FAILED" ] && done_step release "$(tail -1 $L/release.txt | cut -c1-300)"
fi

# ---- manifest
if todo manifest; then
  M=$WK/mini; rm -rf $M; mkdir_as $M/parquet
  for f in $OUT/*-dataset.parquet; do $AS ln "$f" $M/parquet/ || fail "the mini root"; done
  run_to manifest.txt $FR manifest --root $M --ledgers $WK/ledger.project.jsonl --jobs $NP || fail "fill_release.py manifest of the mini root (log/manifest.txt)"
  [ -z "$FAILED" ] && { run_to manifest.txt $T2 manifest --tom1-manifest $T2D/MANIFEST.tsv --mini-manifest $M/MANIFEST.tsv \
    --plan $WK/plan.tsv --ledger $L/ledger.jsonl --out $R/MANIFEST.tsv || fail "MANIFEST.tsv (log/manifest.txt)"; }
  [ -z "$FAILED" ] && done_step manifest "$(tail -1 $L/manifest.txt)"
fi

# ---- markers
if todo markers; then
  run_to markers.txt $TT sizes --manifest $R/MANIFEST.tsv --keep $WK/keep.pf.tsv --rule "$SIZE_RULE" --out $L/sizes.json || fail "the size rule (log/markers.txt)"
  MACH=local; [ "$LOCAL" != 1 ] && MACH=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/instance-type)
  [ -z "$FAILED" ] && { run_to markers.txt $T3 values --root $R --keep $WK/keep.tsv --ledger $L/ledger.jsonl --proof $L/proof.jsonl \
    --sizes $L/sizes.json --db-rel organizations/dataset.duckdb --date "$(date -u +%F)" --machine "${MACH:-unknown}" \
    --drop-columns "$DROP_COLUMNS" --fact-type $ROSTER_FACT_TYPE --out $L/values.json || fail "the values (log/markers.txt)"; }
  [ -z "$FAILED" ] && { run_to markers.txt $TT markers --root $R --values $L/values.json --apply || fail "the placeholders (log/markers.txt)"; }
  [ -z "$FAILED" ] && done_step markers "$(tail -1 $L/markers.txt)"
fi

# ---- checksums
if todo checksums; then
  run_to checksums.txt $T2 sums --root $R --tom1-sums $T2D/SHA256SUMS --plan $WK/plan.tsv --changed-out $WK/changed.list \
    --gone-out $WK/gone.list --jobs $NP || fail "SHA256SUMS (log/checksums.txt)"
  [ -z "$FAILED" ] && { cp $R/SHA256SUMS $L/root.SHA256SUMS; cp $R/MANIFEST.tsv $L/root.MANIFEST.tsv; cp $WK/changed.list $L/changed.list.txt; cp $WK/gone.list $L/gone.list.txt; }
  [ -z "$FAILED" ] && done_step checksums "SHA256SUMS $(sha256sum $R/SHA256SUMS | cut -c1-12), $(wc -l < $R/SHA256SUMS) rows; $(tail -1 $L/checksums.txt)"
fi

# ---- checks (every check runs; the step fails when one fails)
if todo checks; then
  CF=""
  run_to check.fill.txt $FR check --root $R --allow-todo || CF="$CF fill_release-check"
  run_to check.root.txt $T3 check-root --root $R --tom2-root $T2D --src-dir $T2D/parquet --keep $WK/keep.tsv --ledger $L/ledger.jsonl \
    --proof $L/proof.jsonl --tom2-sums $T2D/SHA256SUMS --db-rel organizations/dataset.duckdb --drop-columns "$DROP_COLUMNS" \
    --schema-version $SCHEMA_VERSION --fact-type $ROSTER_FACT_TYPE --need-views "$NEED_VIEWS" --allow-gone "$ALLOW_GONE" \
    --ri-changed "$RI_CHANGED" --max $MAX_PARQUET_FILES --want-columns $EXPECT_COLUMNS --expect-files $EXPECT_FILES \
    --expect-rows $EXPECT_ROWS --expect-roster $EXPECT_ROSTER_FACTS --expect-ri-keys $EXPECT_RI_KEYS --jobs $NP \
    --out $L/check-root.json || CF="$CF check-root"
  par_check $R $R/SHA256SUMS $L/check.sums.txt || CF="$CF sha256sum-c"
  nloc=$(cd $R && find . -type f ! -name SHA256SUMS | wc -l); rows=$(wc -l < $R/SHA256SUMS)
  [ "$nloc" = "$rows" ] || CF="$CF local-files($nloc)!=rows($rows)"
  run_to check.release.txt $RT no-at --root $R || CF="$CF no-at"
  run_to check.release.txt $RT no-paths --root $R || CF="$CF no-paths"
  run_to check.release.txt $RT guard --root $R --names $WK/keep.names || CF="$CF guard"
  pqn=$(find $R/parquet -mindepth 1 -maxdepth 1 | wc -l); [ "$pqn" -lt 10000 ] || CF="$CF parquet/=$pqn>=10000"
  run_to check.hf.txt $HT precheck --root $R --out $L/hf-precheck.txt \
    --limit MAX_ENTRIES=$HF_MAX_ENTRIES_PER_FOLDER --limit MAX_FILE=$HF_MAX_FILE_BYTES --limit REC_FILE=$HF_REC_FILE_BYTES \
    --limit REC_FILES=$HF_REC_FILES_PER_REPO --limit FREE=$HF_PRIVATE_QUOTA_FREE --limit PRO=$HF_PRIVATE_QUOTA_PRO \
    --limit PUBLIC_NOTE=$HF_PUBLIC_NOTE_BYTES --visibility $HF_VISIBILITY --quota 0 || CF="$CF hf-precheck"
  run_to check.hf.txt $HT validate-card --card $R/README.md || CF="$CF card"
  echo "checks: parquet/ $pqn entries; local files $nloc; SHA256SUMS rows $rows; failed:${CF:- none}" | tee -a $L/checks.txt
  [ -z "$CF" ] && done_step checks "parquet/ $pqn entries, $nloc files, SHA256SUMS $(sha256sum $R/SHA256SUMS | cut -c1-12); $(tail -1 $L/check.root.txt | cut -c1-300)" || fail "checks:$CF (log/check.*.txt)"
fi

# ---- upload: the new root (empty prefix only)
if todo upload; then
  if [ "$LOCAL" = 1 ]; then
    echo "local: no upload" > $ST/upload.SKIP
  else
    lsr() { $AS aws s3api list-objects-v2 --bucket $BKT --prefix "$DEST/root/" --query 'Contents[].[Key,Size]' --output text | grep -v '^None$' || true; }
    (cd $R && find . -type f | sed 's#^\./##' | while read -r f; do echo "$DEST/root/$f $(stat -c %s "$f")"; done | LC_ALL=C sort) > $WK/local.listing.txt
    lsr | awk '{print $1, $2}' | LC_ALL=C sort > $WK/ls.before.txt
    n=$(wc -l < $WK/ls.before.txt)
    if [ "$n" != 0 ] && [ ! -f $ST/upload.STARTED ]; then
      fail "$D3/root/ is not empty ($n objects) and this machine did not start an upload there: the run never writes over a root"
    elif [ "$n" != 0 ]; then
      # a new start after a failed upload of this run: every object must be a file of this root with its size
      other=$(LC_ALL=C comm -23 $WK/ls.before.txt $WK/local.listing.txt | wc -l)
      [ "$other" = 0 ] || fail "$D3/root/ holds $other objects that are not files of this root (path and size)"
      [ -z "$FAILED" ] && { log "upload resume: $n objects there, $(wc -l < $WK/local.listing.txt) files"
        run_to upload.txt aws s3 sync $R/ $D3/root/ --size-only --checksum-algorithm SHA256 --only-show-errors || fail "the upload of the root (resume)"; }
    else
      echo "upload started $(date -u +%FT%TZ)" > $ST/upload.STARTED
      run_to upload.txt aws s3 cp --recursive $R/ $D3/root/ --checksum-algorithm SHA256 --only-show-errors || fail "the upload of the root"
    fi
    if [ -z "$FAILED" ]; then
      lsr > $WK/ls.root.txt
      miss=$(LC_ALL=C comm -3 $WK/local.listing.txt <(awk '{print $1, $2}' $WK/ls.root.txt | LC_ALL=C sort) | wc -l)
      nobj=$(wc -l < $WK/ls.root.txt); nf=$(find $R -type f | wc -l)
      [ "$miss" = 0 ] && [ "$nobj" = "$nf" ] || fail "after the upload: $nobj objects for $nf files, $miss differences in path or size"
      awk '{print $1, $2}' $WK/ls.root.txt | sed "s#^$DEST/root/##" > $L/root.listing.txt
      [ -z "$FAILED" ] && done_step upload "$nobj objects, $(awk '{s+=$2} END {printf "%d", s}' $WK/ls.root.txt) B in s3://.../$DEST/root/"
    fi
  fi
fi

# ---- Hugging Face (only when every step before is DONE)
if [ -z "$FAILED" ] && [ ! -f $ST/hf.DONE ]; then
  if [ "$HF" != 1 ] || [ "$LOCAL" = 1 ]; then
    echo "hf skipped (HF=$HF, local $LOCAL)" > $ST/hf.SKIP
  else
    case $HF_VISIBILITY in public) VIS="" ;; private) VIS=--private ;; *) VIS=BAD; fail "HF_VISIBILITY is $HF_VISIBILITY" ;; esac
    TOK=$HF_TOKEN_DIR/token
    if [ -z "$FAILED" ]; then
      install -d -m 700 -o $RUNAS -g $RUNAS $HF_TOKEN_DIR
      (umask 077; aws ssm get-parameter --region us-west-2 --name $HF_SSM_PARAM --with-decryption --query Parameter.Value \
         --output text 2>/dev/null | tr -d '[:space:]' > $TOK); chown $RUNAS: $TOK
      [ -s $TOK ] || { rm -f $TOK; fail "no Hugging Face token in $HF_SSM_PARAM (the user runs ../dataset-hf/T1-hf-token-put.sh)"; }
    fi
    if [ -z "$FAILED" ]; then
      HAS="runuser -u $RUNAS -- env HOME=/home/$RUNAS HF_HOME=$X/hf-home HF_TOKEN_PATH=$TOK HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_PROGRESS_BARS=1 HF_XET_HIGH_PERFORMANCE=1"
      if [ ! -f $ST/hf-pre.DONE ]; then
        $HAS $HT verify --repo $HF_REPO --sums $T2D/SHA256SUMS --out $L/hf-preverify.txt --expect $HF_VISIBILITY >> $L/hf.txt 2>&1; rc=$?
        if [ $rc = 0 ]; then echo "hf-pre DONE $(date -u +%FT%TZ)" > $ST/hf-pre.DONE
        elif [ "$HF_PRE_VERIFY" = require ]; then fail "the Hub is not the TOM-2 root (log/hf-preverify.txt); HF_PRE_VERIFY=skip pushes anyway"
        else log "the Hub is not the TOM-2 root (HF_PRE_VERIFY=$HF_PRE_VERIFY): push anyway"; fi
      fi
      [ -z "$FAILED" ] && { $HAS $HT upload --repo $HF_REPO $VIS --root $R --card $R/README.md --batch-files $HF_BATCH_FILES \
        --batch-bytes $HF_BATCH_BYTES >> $L/hf.txt 2>&1 || fail "hf upload (log/hf.txt; a new start resumes: the files on the Hub are skipped)"; }
      if [ -z "$FAILED" ] && [ -s $WK/gone.list ]; then
        echo SHA256SUMS > $WK/hf.adds
        $HAS $H2 hf-push --repo $HF_REPO --root $R --adds $WK/hf.adds --deletes $WK/gone.list --expect $HF_VISIBILITY \
          --message "TOM 1.0.0 third pass: deletes" >> $L/hf.txt 2>&1 || fail "hf deletes (log/hf.txt)"
      fi
      [ -z "$FAILED" ] && { $HAS $HT verify --repo $HF_REPO --sums $R/SHA256SUMS --card $R/README.md --out $L/hf-verify.txt \
        --expect $HF_VISIBILITY >> $L/hf.txt 2>&1 || fail "hf verify (log/hf-verify.txt)"; }
    fi
    rm -f $TOK
    [ -e $TOK ] && fail "the token file is still there"
    [ -z "$FAILED" ] && { echo "hf DONE $(date -u +%FT%TZ) repo $HF_REPO ($HF_VISIBILITY); $(wc -l < $WK/changed.list) changed files; $(wc -l < $WK/gone.list) deletes; token file deleted" > $ST/hf.DONE; put_log; }
  fi
fi

finish
