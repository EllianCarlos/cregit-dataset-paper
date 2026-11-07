#!/usr/bin/env bash
# tom2_run.sh (the TOM-2 machine; a tool of the stage, so its sha256 is in stage/SHA256SUMS). tom2_start.sh starts
# it as the systemd unit tom2-run (root); the work runs as ec2-user (RUNAS). One run, the steps in order; a step
# with status/STEP.DONE is skipped (a second start continues). The first failed step ends the run (ALERT).
#   preflight  the stage inputs, the first pass is DONE (TOM1/log/final.status.json), the new root prefix is empty,
#              the Hugging Face token is in SSM, the disk
#   fetch      of TOM-1: SHA256SUMS (its sha256 is TOM1_SUMS_SHA or root_sha256sums of the final status), the
#              listing (every row, one object each), every file except parquet/, and the parquet files with a
#              fill; of the source: SHA256SUMS (SRC_SUMS_SHA), MANIFEST.tsv, ledgers.parquet, two organizations
#              tables and the files of ADD_PROJECTS; every fetched file checks against its SHA256SUMS row
#   keep       the keep list (8,447) and ADD_PROJECTS against both SHA256SUMS (tom2_tools.py keep)
#   footers    the footer of every TOM-1 project file (ranged reads), against the TOM-1 MANIFEST.tsv
#   plan       the kind of each file and its values; the old values must be in the footer statistics; every empty
#              language cell must have a fill; the expected counts; the canary files (one per kind of change)
#   canary     the canary files alone (value pass + check); the run stops when one fails
#   pass       the value pass of the other changed files (largest first, JOBS at a time); log/ledger.jsonl
#   assemble   the local root: the docs of the stage, links.json and pseudonymization.json of TOM-1,
#              organizations/ of TOM-1, ledgers.parquet (kit 1 ledgers on the kept projects)
#   facts      project_facts.parquet (TOM-1 rows + the new facts), project_organizations and release_info (kit 1
#              orgs on the kept projects)
#   tables     project_languages.parquet, project_labels.parquet, their release_info rows and their views;
#              release_info: ctp_schema_version = 3 (kit 1 kept the build value 2) and the new key
#              dataset_db_sha256 = the sha256 of the dataset.duckdb of this pass
#   manifest   MANIFEST.tsv (TOM-1 rows; fill_release.py manifest of a mini root for the changed files)
#   markers    the size rule counts, the measured values, the placeholders [[tom: KEY]] and TODO-DATE
#   checksums  SHA256SUMS (TOM-1 rows of the unchanged files, the sha256 of every local file)
#   view       the check view: the local root and a sparse file with the real footer for each unchanged file
#   checks     fill_release.py check (view), tom2_tools.py check-root (also every release_info key against its
#              measured value), sha256sum -c (local files),
#              release_tools.py no-at, no-paths and guard, hf_tools.py precheck (view) and validate-card
#   upload     the new root to s3://B/DEST/root/ (empty prefix only): a server-side copy of the unchanged project
#              files of TOM-1, then the local root; the listing after (count, sizes, ETags)
#   hf         (HF=1) the token from SSM to tmpfs; the Hub must hold the TOM-1 root (hf_tools.py verify); push the
#              changed and new files (and the allowed deletes); verify the whole Hub tree against the new
#              SHA256SUMS; the token file deleted
#   end        log/final.status, then shutdown: DONE at once, ALERT after ALERT_HOLD_MIN minutes (L1 sets the stop
#              behavior); NOSHUT=1 or /run/tom2-hold keeps it up.
# A file $X/STOP makes the pass start no new file. Environment (tom2_start.sh sets it): X T PY B RUNAS NOSHUT;
# TOM_LOCAL=1 for the local rehearsal (TOM1_DIR and SRC_DIR are local roots; no S3, no Hugging Face, no shutdown).
set -uo pipefail
: "${X:?}" "${T:?}" "${PY:?}" "${B:?}"
. $T/tom2.conf
RUNAS=${RUNAS-ec2-user}; NOSHUT=${NOSHUT:-0}; LOCAL=${TOM_LOCAL:-0}
T1=${TOM1_DIR:-$X/tom1}; S=${SRC_DIR:-$X/src}; R=$X/root; V=$X/view; FT=$X/footers
L=$X/log; ST=$X/status; WK=$X/work; OUT=$R/parquet
D3=$B/$DEST; T13=$B/$TOM1_ROOT; SRC3=$B/$SRC_ROOT; BKT=${B#s3://}
TT="$PY -I -B $T/tom_tools.py"; T2="$PY -I -B $T/tom2_tools.py"; FR="$PY -I -B $R/tools/fill_release.py"
RT="$PY -I -B $T/release_tools.py"; HFPY=${HF_PY:-$PY}; HT="$HFPY -I -B $T/hf_tools.py"; H2="$HFPY -I -B $T/tom2_tools.py"
NP=$(nproc); J=${JOBS:-$(( NP / 2 ))}; [ "$J" -ge 1 ] || J=1
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

finish() {
  local st=DONE why="all steps ok"
  [ -n "$FAILED" ] && { st=ALERT; why="$FAILED"; }
  local steps; steps=$(ls $ST/*.DONE 2>/dev/null | xargs -r -n1 basename | sed 's/\.DONE$//' | paste -sd' ')
  echo "tom2 run $st $(date -u +%FT%TZ) after $(( $(date +%s) - t0 )) s: $why; steps done: ${steps:-none}" > $ST/run.$st
  rm -f $ST/run.$([ $st = DONE ] && echo ALERT || echo DONE)
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
  if [ "$NOSHUT" = 1 ] || [ -e /run/tom2-hold ] || [ -e /home/ec2-user/NO_SHUTDOWN ]; then
    log "no shutdown (NOSHUT=1 or a hold file)"
  elif [ $st = DONE ]; then
    log "shutdown in 1 min (the stop behavior of L1: the instance stops)"; shutdown -h +1
  else
    log "ALERT: shutdown in $ALERT_HOLD_MIN min (K1-tom2-hold.sh ACTION=hold keeps the machine)"; shutdown -h +$ALERT_HOLD_MIN
  fi
  [ $st = DONE ]
}

log "tom2 run: $T13/ + $SRC3/ -> $D3/root/; $NP vCPU, $(free -g | awk '/Mem:/{print $2}') GiB, jobs $J; local $LOCAL"
K1=$T/keep/projects.keep.txt; FILLS=$T/inputs/fills.tsv

# ---- preflight
if todo preflight; then
  [ -s $K1 ] || fail "no keep list $K1"
  for f in $FILLS $T/inputs/project_languages.parquet $T/inputs/project_labels.parquet $T/docs/README.md $T/docs/tools/fill_release.py; do
    [ -f $f ] || fail "the stage lacks $f"
  done
  if [ -n "$(ls -A $R 2>/dev/null)" ]; then fail "$R exists and is not empty (a new run takes a new machine)"; fi
  if [ "$LOCAL" != 1 ] && [ -z "$FAILED" ]; then
    $AS aws s3 cp $B/$TOM1/log/final.status.json $L/tom1.final.status.json --only-show-errors || fail "no $TOM1/log/final.status.json"
    if [ -z "$FAILED" ]; then
      st1=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['status'])" $L/tom1.final.status.json)
      want1=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['root_sha256sums'])" $L/tom1.final.status.json)
      [ "$st1" = DONE ] || fail "the first pass is $st1, not DONE"
      [ -z "$TOM1_SUMS_SHA" ] || [ "$TOM1_SUMS_SHA" = "$want1" ] || fail "TOM1_SUMS_SHA ${TOM1_SUMS_SHA:0:12} is not the final status ${want1:0:12}"
      echo "$want1" > $WK/tom1.sums.sha
    fi
    n=$({ $AS aws s3 ls --recursive $D3/root/ 2>/dev/null || true; } | wc -l)
    [ "$n" = 0 ] || fail "$D3/root/ is not empty ($n objects): the run never writes over a root"
    if [ "$HF" = 1 ]; then
      nm=$(aws ssm get-parameter --region us-west-2 --name $HF_SSM_PARAM --query Parameter.Name --output text 2>/dev/null)
      [ "$nm" = "$HF_SSM_PARAM" ] || fail "no Hugging Face token in $HF_SSM_PARAM (the user runs ../dataset-hf/T1-hf-token-put.sh)"
    fi
    avail=$(df -BG --output=avail $X | tail -1 | tr -dc '0-9')
    [ "$avail" -ge 100 ] || fail "$X has $avail GB free, need 100"
  fi
  if [ "$LOCAL" = 1 ]; then sha256sum $T1/SHA256SUMS | cut -d' ' -f1 > $WK/tom1.sums.sha; fi
  [ -z "$FAILED" ] && done_step preflight "keep list $(grep -c . $K1) lines, fills $(( $(wc -l < $FILLS) - 1 )), docs $(find $T/docs -type f | wc -l) files, TOM-1 SHA256SUMS $(cut -c1-12 $WK/tom1.sums.sha)"
fi

# the TOM-1 files with a fill (the only TOM-1 project files the pass reads)
fill_files() { cut -f1 $FILLS | tail -n +2 | sort -u | grep -vxF -f <(tr ' ' '\n' <<< "$ADD_PROJECTS" | grep .) | sed 's/$/-dataset.parquet/'; }

# ---- fetch
if todo fetch; then
  if [ "$LOCAL" != 1 ]; then
    mkdir_as $T1 $S
    $AS aws s3 cp $T13/SHA256SUMS $T1/SHA256SUMS --only-show-errors || fail "download of the TOM-1 SHA256SUMS"
    [ -z "$FAILED" ] && [ "$(sha256sum $T1/SHA256SUMS | cut -d' ' -f1)" != "$(cat $WK/tom1.sums.sha)" ] && fail "the TOM-1 SHA256SUMS is not $(cut -c1-12 $WK/tom1.sums.sha)"
    if [ -z "$FAILED" ]; then
      $AS aws s3 ls --recursive $T13/ > $WK/ls.tom1.txt || fail "the TOM-1 listing"
      base=${T13#s3://*/}
      nobj=$(wc -l < $WK/ls.tom1.txt); nrow=$(wc -l < $T1/SHA256SUMS)
      miss=$(awk '{print $2}' $T1/SHA256SUMS | sed "s#^#$base/#" | LC_ALL=C sort | LC_ALL=C comm -23 - <(awk '{print $4}' $WK/ls.tom1.txt | LC_ALL=C sort) | wc -l)
      [ "$nobj" = $((nrow + 1)) ] && [ "$miss" = 0 ] || fail "the TOM-1 root has $nobj objects for $nrow SHA256SUMS rows ($miss rows without an object)"
    fi
    if [ -z "$FAILED" ]; then
      INC=(); while read -r f; do INC+=(--include "parquet/$f"); done < <(fill_files)
      log "download of the TOM-1 root without parquet/, and ${#INC[@]} / 2 project files"
      run_to fetch.txt aws s3 sync $T13/ $T1/ --exclude "parquet/*" "${INC[@]}" --only-show-errors || fail "download of the TOM-1 files"
      $AS aws s3 cp $SRC3/SHA256SUMS $S/SHA256SUMS --only-show-errors || fail "download of the source SHA256SUMS"
      SI=(--include MANIFEST.tsv --include ledgers.parquet --include organizations/project_organizations.parquet --include organizations/release_info.parquet)
      for p in $ADD_PROJECTS; do SI+=(--include "parquet/$p-dataset.parquet"); done
      [ -z "$FAILED" ] && { run_to fetch.txt aws s3 sync $SRC3/ $S/ --exclude "*" "${SI[@]}" --only-show-errors || fail "download of the source files"; }
    fi
  fi
  if [ -z "$FAILED" ]; then
    [ "$(sha256sum $S/SHA256SUMS | cut -d' ' -f1)" = "$SRC_SUMS_SHA" ] || fail "the source SHA256SUMS is not ${SRC_SUMS_SHA:0:12}"
    cmp -s $S/SHA256SUMS $T/source.SHA256SUMS || fail "the source SHA256SUMS is not the stage copy"
    [ "$(sha256sum $T1/SHA256SUMS | cut -d' ' -f1)" = "$(cat $WK/tom1.sums.sha)" ] || fail "the TOM-1 SHA256SUMS changed"
  fi
  if [ -z "$FAILED" ]; then
    # every fetched file against its row (TOM-1: all but the unchanged parquet/; source: the files of SI)
    (cd $T1 && while read -r d f; do [ -f "$f" ] && echo "$d  $f"; done < SHA256SUMS > $WK/t1.fetched.sums && sha256sum --quiet --strict -c $WK/t1.fetched.sums) >> $L/fetch.txt 2>&1 || fail "a fetched TOM-1 file does not check"
    nt=$(grep -vc '  parquet/' $T1/SHA256SUMS); nf=$(grep -vc '  parquet/' $WK/t1.fetched.sums)
    np=$(grep -c '  parquet/' $WK/t1.fetched.sums); nw=$(fill_files | wc -l)
    [ "$LOCAL" = 1 ] || { [ "$nt" = "$nf" ] && [ "$np" = "$nw" ]; } || fail "fetched $nf of $nt TOM-1 files outside parquet/ and $np of $nw project files"
    (cd $S && for f in MANIFEST.tsv ledgers.parquet organizations/project_organizations.parquet organizations/release_info.parquet $(for p in $ADD_PROJECTS; do echo parquet/$p-dataset.parquet; done); do
       grep -F "  $f" SHA256SUMS | awk -v f="$f" '$2 == f'; done > $WK/src.fetched.sums && sha256sum --quiet --strict -c $WK/src.fetched.sums) >> $L/fetch.txt 2>&1 || fail "a fetched source file does not check"
    [ "$(wc -l < $WK/src.fetched.sums)" = $((4 + $(wc -w <<< "$ADD_PROJECTS"))) ] || fail "the source rows of the fetched files"
  fi
  [ -z "$FAILED" ] && done_step fetch "TOM-1 $(wc -l < $WK/t1.fetched.sums) files ($(du -sbL $T1 | cut -f1) B), source $(wc -l < $WK/src.fetched.sums) files"
fi

# ---- keep
if todo keep; then
  run_to keep.txt $T2 keep --list $K1 --add "$ADD_PROJECTS" --tom1-sums $T1/SHA256SUMS --src-sums $S/SHA256SUMS \
    --max $MAX_PARQUET_FILES --out $WK/keep.resolved.tsv || fail "the keep list (log/keep.txt)"
  if [ -z "$FAILED" ]; then
    cut -f1,2 $WK/keep.resolved.tsv > $WK/keep.pf.tsv; cut -f1 $WK/keep.resolved.tsv > $WK/keep.names
    cp $WK/keep.resolved.tsv $L/keep.resolved.tsv
    [ "$(wc -l < $WK/keep.names)" = "$EXPECT_FILES" ] || fail "the keep list has $(wc -l < $WK/keep.names) files, not $EXPECT_FILES"
  fi
  [ -z "$FAILED" ] && done_step keep "$(tail -1 $L/keep.txt)"
fi

# ---- footers
if todo footers; then
  mkdir_as $FT
  if [ "$LOCAL" = 1 ]; then FSRC=(--local $T1); else FSRC=(--s3 $BKT/$TOM1_ROOT); fi
  run_to footers.txt $T2 footers --keep $WK/keep.resolved.tsv --manifest $T1/MANIFEST.tsv --out-dir $FT "${FSRC[@]}" \
    --jobs $FOOTER_JOBS --first $FOOTER_FIRST || fail "the TOM-1 footers (log/footers.txt)"
  [ -z "$FAILED" ] && done_step footers "$(tail -1 $L/footers.txt)"
fi

# ---- plan
if todo plan; then
  run_to plan.txt $T2 plan --keep $WK/keep.resolved.tsv --footers $FT/footers.jsonl --fills $FILLS --out $WK/plan.tsv \
    --canary-out $WK/canary.list --src-dir $S/parquet --expect-files $EXPECT_FILES --expect-value $EXPECT_VALUE_FILES \
    --expect-new $EXPECT_NEW_FILES --expect-language $EXPECT_LANGUAGE_FILLS --expect-license $EXPECT_LICENSE_FILLS \
    || fail "the plan (log/plan.txt)"
  [ -z "$FAILED" ] && { cp $WK/plan.tsv $L/plan.tsv; done_step plan "$(tail -1 $L/plan.txt | cut -c1-300)"; }
fi

PASSARGS=(--plan $WK/plan.tsv --tom1-dir $T1/parquet --src-dir $S/parquet --dst $OUT --tom1-sums $T1/SHA256SUMS
  --src-sums $S/SHA256SUMS --ledger $L/ledger.jsonl --rename-py $T/parquet_rename.py --check-py $T/parquet_rename_check.py
  --work $WK/pass --drop-columns "$DROP_COLUMNS" --rename "$RENAME" --set-kv "$SET_KV" --expect-empty "$EXPECT_EMPTY"
  --expect-manifest-category "$EXPECT_MANIFEST_CATEGORY" --expect-file-mask "$EXPECT_FILE_MASK" --copy-mode $COPY_MODE
  --progress $L/progress.json --stop-file $X/STOP --check-dir $WK/checks)

# ---- canary: one file of each kind of change; the run stops when one fails
if todo canary; then
  mkdir_as $R $OUT $WK/pass
  log "canary: $(paste -sd' ' $WK/canary.list)"
  run_to canary.txt $T2 pass "${PASSARGS[@]}" --only-list $WK/canary.list --jobs 1 --threads $NP \
    || fail "a canary file failed (log/canary.txt, log/ledger.jsonl): the pass is stopped"
  [ -z "$FAILED" ] && done_step canary "$(paste -sd' ' $WK/canary.list): $(tail -1 $L/canary.txt)"
fi

# ---- pass
if todo pass; then
  run_to pass.txt $T2 pass "${PASSARGS[@]}" --jobs $J --threads 2; rc=$?
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
  miss=$(grep -v '  parquet/\|  organizations/\|  ledgers.parquet$\|  links.json$\|  pseudonymization.json$\|  MANIFEST.tsv$' $T1/SHA256SUMS \
         | awk '{print $2}' | while read -r f; do [ -f "$T/docs/$f" ] || case " $ALLOW_GONE " in *" $f "*) ;; *) echo "$f" ;; esac; done)
  [ -z "$miss" ] || fail "the docs input lacks documents of the TOM-1 root: $(echo $miss)"
  mkdir_as $R/organizations
  for f in $T1/organizations/*; do $AS cp "$f" $R/organizations/ || fail "copy of organizations/$(basename "$f")"; done
  for f in links.json pseudonymization.json; do $AS cp $T1/$f $R/$f || fail "copy of $f"; done
  (cd $R && grep -E '  (organizations/|links\.json$|pseudonymization\.json$)' $T1/SHA256SUMS | sha256sum --quiet --strict -c -) \
    || fail "the copied TOM-1 files are not byte-identical"
  run_to assemble.txt $TT ledgers --src $S/ledgers.parquet --keep $WK/keep.pf.tsv --out $R/ledgers.parquet \
    --jsonl $WK/ledger.project.jsonl --mode subset || fail "ledgers.parquet (log/assemble.txt)"
  [ -z "$FAILED" ] && { run_to assemble.txt $T2 ledgers-check --new $R/ledgers.parquet --tom1 $T1/ledgers.parquet --add "$ADD_PROJECTS" \
    || fail "ledgers.parquet is not TOM-1 plus the new projects (log/assemble.txt)"; }
  [ -z "$FAILED" ] && done_step assemble "$(find $R -type f | wc -l) files; $(tail -1 $L/assemble.txt)"
fi

# ---- facts
if todo facts; then
  run_to facts.txt $T2 facts --tom1-facts $T1/organizations/project_facts.parquet --ledger $L/ledger.jsonl --plan $WK/plan.tsv \
    --out $R/organizations/project_facts.parquet || fail "project_facts (log/facts.txt)"
  [ -z "$FAILED" ] && { run_to facts.txt $TT orgs --root $R --src-root $S --keep $WK/keep.pf.tsv --facts-rel organizations/project_facts.parquet \
    || fail "project_organizations and release_info (log/facts.txt)"; }
  [ -z "$FAILED" ] && done_step facts "$(grep '^project_facts' $L/facts.txt | tail -1); $(tail -1 $L/facts.txt | cut -c1-200)"
fi

# ---- tables
if todo tables; then
  run_to tables.txt $T2 tables --root $R --tom1-root $T1 --keep $WK/keep.resolved.tsv --inputs $T/inputs \
    --db-rel organizations/dataset.duckdb --tables "$SIDE_TABLES" --schema-version "${SET_KV#ctp_schema_version=}" \
    || fail "the side tables (log/tables.txt)"
  [ -z "$FAILED" ] && done_step tables "$(tail -1 $L/tables.txt)"
fi

# ---- manifest
if todo manifest; then
  M=$WK/mini; rm -rf $M; mkdir_as $M/parquet
  for f in $OUT/*-dataset.parquet; do $AS ln "$f" $M/parquet/ || fail "the mini root"; done
  run_to manifest.txt $FR manifest --root $M --ledgers $WK/ledger.project.jsonl --jobs $NP || fail "fill_release.py manifest of the mini root (log/manifest.txt)"
  [ -z "$FAILED" ] && { run_to manifest.txt $T2 manifest --tom1-manifest $T1/MANIFEST.tsv --mini-manifest $M/MANIFEST.tsv \
    --plan $WK/plan.tsv --ledger $L/ledger.jsonl --out $R/MANIFEST.tsv || fail "MANIFEST.tsv (log/manifest.txt)"; }
  [ -z "$FAILED" ] && done_step manifest "$(tail -1 $L/manifest.txt)"
fi

# ---- markers
if todo markers; then
  run_to markers.txt $TT sizes --manifest $R/MANIFEST.tsv --keep $WK/keep.pf.tsv --rule "$SIZE_RULE" --out $L/sizes.json || fail "the size rule (log/markers.txt)"
  MACH=local; [ "$LOCAL" != 1 ] && MACH=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/instance-type)
  [ -z "$FAILED" ] && { run_to markers.txt $T2 values --root $R --plan $WK/plan.tsv --footers $FT/footers.jsonl --ledger $L/ledger.jsonl \
    --sizes $L/sizes.json --db-rel organizations/dataset.duckdb --date "$(date -u +%F)" --machine "${MACH:-unknown}" --out $L/values.json || fail "the values (log/markers.txt)"; }
  [ -z "$FAILED" ] && { run_to markers.txt $TT markers --root $R --values $L/values.json --apply || fail "the placeholders (log/markers.txt)"; }
  [ -z "$FAILED" ] && done_step markers "$(tail -1 $L/markers.txt)"
fi

# ---- checksums
if todo checksums; then
  run_to checksums.txt $T2 sums --root $R --tom1-sums $T1/SHA256SUMS --plan $WK/plan.tsv --changed-out $WK/changed.list \
    --gone-out $WK/gone.list --jobs $NP || fail "SHA256SUMS (log/checksums.txt)"
  [ -z "$FAILED" ] && { cp $R/SHA256SUMS $L/root.SHA256SUMS; cp $R/MANIFEST.tsv $L/root.MANIFEST.tsv; cp $WK/changed.list $L/changed.list.txt; cp $WK/gone.list $L/gone.list.txt; }
  [ -z "$FAILED" ] && done_step checksums "SHA256SUMS $(sha256sum $R/SHA256SUMS | cut -c1-12), $(wc -l < $R/SHA256SUMS) rows; $(tail -1 $L/checksums.txt)"
fi

# ---- view
if todo view; then
  run_to view.txt $T2 view --root $R --tails $FT --plan $WK/plan.tsv --out $V || fail "the check view (log/view.txt)"
  [ -z "$FAILED" ] && done_step view "$(tail -1 $L/view.txt)"
fi

# ---- checks (every check runs; the step fails when one fails)
if todo checks; then
  CF=""
  run_to check.fill.txt $FR check --root $V --allow-todo || CF="$CF fill_release-check"
  run_to check.root.txt $T2 check-root --root $R --view $V --plan $WK/plan.tsv --footers $FT/footers.jsonl --ledger $L/ledger.jsonl \
    --tom1-sums $T1/SHA256SUMS --tom1-manifest $T1/MANIFEST.tsv --db-rel organizations/dataset.duckdb --need-views "$NEED_VIEWS" \
    --src-release-info $S/organizations/release_info.parquet \
    --allow-gone "$ALLOW_GONE" --max $MAX_PARQUET_FILES --want-columns $EXPECT_COLUMNS --expect-files $EXPECT_FILES \
    --expect-rows $EXPECT_ROWS --jobs $NP --out $L/check-root.json || CF="$CF check-root"
  nloc=$(cd $R && while read -r d f; do [ -f "$f" ] && echo "$d  $f"; done < SHA256SUMS | tee $WK/local.sums | wc -l)
  (cd $R && sha256sum --quiet --strict -c $WK/local.sums) > $L/check.sums.txt 2>&1 || CF="$CF sha256sum-c"
  [ "$nloc" = "$(cd $R && find . -type f ! -name SHA256SUMS | wc -l)" ] || CF="$CF local-rows($nloc)"
  nf=$(find $V -type f | wc -l); rows=$(wc -l < $R/SHA256SUMS)
  [ "$nf" = $((rows + 1)) ] || CF="$CF view-files($nf)!=rows+1($rows)"
  run_to check.release.txt $RT no-at --root $R || CF="$CF no-at"
  run_to check.release.txt $RT no-paths --root $R || CF="$CF no-paths"
  run_to check.release.txt $RT guard --root $V --names $WK/keep.names || CF="$CF guard"
  pqn=$(find $V/parquet -mindepth 1 -maxdepth 1 | wc -l); [ "$pqn" -lt 10000 ] || CF="$CF parquet/=$pqn>=10000"
  run_to check.hf.txt $HT precheck --root $V --out $L/hf-precheck.txt \
    --limit MAX_ENTRIES=$HF_MAX_ENTRIES_PER_FOLDER --limit MAX_FILE=$HF_MAX_FILE_BYTES --limit REC_FILE=$HF_REC_FILE_BYTES \
    --limit REC_FILES=$HF_REC_FILES_PER_REPO --limit FREE=$HF_PRIVATE_QUOTA_FREE --limit PRO=$HF_PRIVATE_QUOTA_PRO \
    --limit PUBLIC_NOTE=$HF_PUBLIC_NOTE_BYTES --visibility $HF_VISIBILITY --quota 0 || CF="$CF hf-precheck"
  run_to check.hf.txt $HT validate-card --card $R/README.md || CF="$CF card"
  echo "checks: parquet/ $pqn entries; view files $nf; local files $nloc; failed:${CF:- none}" | tee -a $L/checks.txt
  [ -z "$CF" ] && done_step checks "parquet/ $pqn entries, $nf files, SHA256SUMS $(sha256sum $R/SHA256SUMS | cut -c1-12)" || fail "checks:$CF (log/check.*.txt)"
fi

# ---- upload: the new root (empty prefix only)
if todo upload; then
  if [ "$LOCAL" = 1 ]; then
    echo "local: no upload" > $ST/upload.SKIP
  else
    n=$({ $AS aws s3 ls --recursive $D3/root/ 2>/dev/null || true; } | awk '{print $4}' | grep -v "^$DEST/root/parquet/[A-Za-z0-9._-]*-dataset\.parquet$" | wc -l)
    [ "$n" = 0 ] || fail "$D3/root/ holds $n objects outside parquet/ (an earlier copy of the unchanged files can stay)"
    if [ -z "$FAILED" ]; then
      EXC=(); for f in "$OUT"/*-dataset.parquet; do EXC+=(--exclude "$(basename "$f")"); done
      bad=$(ls "$OUT" | grep -v '^[A-Za-z0-9._-]*$' || true)
      [ -z "$bad" ] || fail "file names with other characters than [A-Za-z0-9._-] (the S3 exclude patterns): $(echo $bad)"
      log "server-side copy of the unchanged project files of TOM-1 (excludes: ${#EXC[@]} / 2)"
      [ -z "$FAILED" ] && { run_to upload.txt aws s3 sync $T13/parquet/ $D3/root/parquet/ "${EXC[@]}" --copy-props metadata-directive --only-show-errors || fail "the S3 copy of the unchanged files"; }
    fi
    [ -z "$FAILED" ] && { run_to upload.txt aws s3 cp --recursive $R/ $D3/root/ --checksum-algorithm SHA256 --only-show-errors || fail "the upload of the local root"; }
    if [ -z "$FAILED" ]; then
      lsq() { $AS aws s3api list-objects-v2 --bucket $BKT --prefix "$1" --query 'Contents[].[Key,Size,ETag]' --output text; }
      lsq "$DEST/root/" > $WK/ls.root.txt || fail "the listing after the upload"
      lsq "$TOM1_ROOT/parquet/" > $WK/ls.tom1.etag.txt || fail "the TOM-1 listing (ETags)"
      miss=$(cd $V && find . -type f | sed 's#^\./##' | while read -r f; do echo "$DEST/root/$f $(stat -c %s "$f")"; done | LC_ALL=C sort \
             | LC_ALL=C comm -3 - <(awk '{print $1, $2}' $WK/ls.root.txt | LC_ALL=C sort) | wc -l)
      nobj=$(wc -l < $WK/ls.root.txt); nf=$(find $V -type f | wc -l)
      [ "$miss" = 0 ] && [ "$nobj" = "$nf" ] || fail "after the upload: $nobj objects for $nf files, $miss differences in path or size"
      unch=$(awk -F'\t' '$4 == "unchanged" {print $2}' $WK/plan.tsv | wc -l)
      same=$(LC_ALL=C join <(sed "s#^$TOM1_ROOT/parquet/##" $WK/ls.tom1.etag.txt | awk '{print $1, $3}' | LC_ALL=C sort) \
                            <(grep "^$DEST/root/parquet/" $WK/ls.root.txt | sed "s#^$DEST/root/parquet/##" | awk '{print $1, $3}' | LC_ALL=C sort) \
             | awk '$2 == $3' | wc -l)
      echo "ETags: $same of $unch unchanged project files have the TOM-1 ETag" | tee -a $L/upload.txt
      [ "$ETAG_CHECK" != require ] || [ "$same" = "$unch" ] || fail "ETags: $same of $unch unchanged files have the TOM-1 ETag"
      awk '{print $1, $2}' $WK/ls.root.txt | sed "s#^$DEST/root/##" > $L/root.listing.txt
      [ -z "$FAILED" ] && done_step upload "$nobj objects, $(awk '{s+=$2} END {printf "%d", s}' $WK/ls.root.txt) B in s3://.../$DEST/root/; ETags $same/$unch"
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
      HAS="runuser -u $RUNAS -- env HOME=/home/$RUNAS HF_HOME=$X/hf-home HF_TOKEN_PATH=$TOK HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_PROGRESS_BARS=1 HF_XET_HIGH_PERFORMANCE=1"
      if [ ! -f $ST/hf-pre.DONE ]; then
        $HAS $HT verify --repo $HF_REPO --sums $T1/SHA256SUMS --out $L/hf-preverify.txt --expect $HF_VISIBILITY >> $L/hf.txt 2>&1; rc=$?
        if [ $rc = 0 ]; then echo "hf-pre DONE $(date -u +%FT%TZ)" > $ST/hf-pre.DONE
        elif [ "$HF_PRE_VERIFY" = require ]; then fail "the Hub is not the TOM-1 root (log/hf-preverify.txt); HF_PRE_VERIFY=skip pushes anyway"
        else log "the Hub is not the TOM-1 root (HF_PRE_VERIFY=$HF_PRE_VERIFY): push anyway"; fi
      fi
      [ -z "$FAILED" ] && { $HAS $H2 hf-push --repo $HF_REPO --root $R --adds $WK/changed.list --deletes $WK/gone.list \
        --expect $HF_VISIBILITY --message "TOM 1.0.0 second pass" >> $L/hf.txt 2>&1 || fail "hf push (log/hf.txt)"; }
      [ -z "$FAILED" ] && { $HAS $HT verify --repo $HF_REPO --sums $R/SHA256SUMS --card $R/README.md --out $L/hf-verify.txt \
        --expect $HF_VISIBILITY >> $L/hf.txt 2>&1 || fail "hf verify (log/hf-verify.txt)"; }
    fi
    rm -f $TOK
    [ -e $TOK ] && fail "the token file is still there"
    [ -z "$FAILED" ] && { echo "hf DONE $(date -u +%FT%TZ) repo $HF_REPO ($HF_VISIBILITY); $(wc -l < $WK/changed.list) files pushed; token file deleted" > $ST/hf.DONE; put_log; }
  fi
fi

finish
