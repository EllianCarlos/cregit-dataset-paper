#!/usr/bin/env bash
# tom5_run.sh (the TOM-5 machine; a tool of the stage, so its sha256 is in stage/SHA256SUMS). tom5_start.sh starts it
# as the systemd unit tom5-run (root, WorkingDirectory /data/tom5); the work runs as ec2-user (RUNAS). One run, the
# steps in order; a step with status/STEP.DONE is skipped (a second start continues). The first failed step ends the
# run (ALERT).
#   preflight  the stage inputs, the TOM-4 root is DONE with its SHA256SUMS, every new-project machine is DONE, the new
#              root prefix is empty, the Hugging Face token is in SSM, the disk
#   fetch      TOM-4: SHA256SUMS (TOM4_SUMS_SHA), the listing, every file outside parquet/; each new-project machine:
#              results/ and parquet/ (only the files of the list are kept later); every fetched file checks
#   newlist    the 149 projects of the list: 149 in, 0 missing, 0 extra (the removed projects of a machine dropped);
#              each new file against its MANIFEST.new.tsv sha256
#   shape      the Parquet form gate of every new file against the TOM-4 file SHAPE_REF (53 columns, order, types,
#              footer key set, writer, codecs, encodings, Bloom filters, row groups)
#   footers    the footer of every project file (TOM-4: ranged S3 reads; new: local) against the merged MANIFEST.tsv
#   license    refuses without inputs/AUDIT_OK; the license value in each file (footer statistics); the rescan of the
#              new projects (license_scan.py of LSC_COMMIT); the rule (70_values.py with the file values and the
#              audit corrections): license_fills.tsv (the value pass input) and project_licenses.tsv
#   ledger     the ledgers.parquet rows of the new projects (the ctp metrics ledger of each machine)
#   pseudo     pseudonymization.json with the registry of the new batch
#   fetch2     the TOM-4 project files with a license fill (the only TOM-4 project files the pass reads)
#   base       the base root: TOM-4 + the new projects (MANIFEST, SHA256SUMS, ledgers, organizations/ rows, pseudo)
#   plan       tom2_tools.py plan: the kind of each file; the old values must be in the footer statistics
#   canary     the smallest changed file alone (value pass + check)
#   pass       the value pass of the other changed files (largest first, JOBS at a time); log/ledger.jsonl
#   assemble   the local root: the stage docs, organizations/, ledgers.parquet, links.json, pseudonymization.json of
#              the base (each byte-identical to its base SHA256SUMS row)
#   tables     project_licenses.parquet, its view, release_info (rows and sha256 of every table, dataset_db_sha256)
#   manifest   MANIFEST.tsv (the base rows; bytes and sha256 of the changed files from the ledger)
#   markers    the size rule counts, the measured values, the placeholders [[tom: KEY]]
#   checksums  SHA256SUMS (the base rows of the unchanged files, the sha256 of every local file)
#   view       the check view: the local root and a sparse stand-in with the real footer for each unchanged file
#   checks     tom5_tools.py check-root, fill_release.py check, sha256sum -c, release_tools.py no-at, no-paths and
#              guard, hf_tools.py precheck and validate-card
#   upload     the new root to s3://B/DEST/root/ (empty prefix only): a server-side copy of the unchanged TOM-4 files,
#              the unchanged new files, then the local root; the listing after (count, sizes, ETags)
#   hf         (HF=1) the token from SSM to tmpfs; the Hub must hold the TOM-4 root; push the changed and new files
#              (the data files, then README.md and SHA256SUMS); verify the whole Hub tree; the token file deleted
#   end        log/final.status, then shutdown: DONE at once, ALERT after ALERT_HOLD_MIN minutes (L1 sets the stop
#              behavior); NOSHUT=1 or /run/tom5-hold keeps it up.
# A file $X/STOP makes the pass start no new file. Environment (tom5_start.sh sets it): X T PY B RUNAS NOSHUT;
# TOM_LOCAL=1 for the local rehearsal (TOM4_DIR, NEW_DIR: local roots; LSC_TOOLS_JSON or LSC_RESULTS_NEW for the
# rescan; no S3, no Hugging Face, no shutdown).
set -uo pipefail
: "${X:?}" "${T:?}" "${PY:?}" "${B:?}"
. $T/tom5.conf
RUNAS=${RUNAS-ec2-user}; NOSHUT=${NOSHUT:-0}; LOCAL=${TOM_LOCAL:-0}
T4=${TOM4_DIR:-$X/tom4}; ND=${NEW_DIR:-$X/new}; NF=$X/newfiles; BASE=$X/base; R=$X/root; V=$X/view; FT=$X/footers
L=$X/log; ST=$X/status; WK=$X/work; OUT=$R/parquet; LIC=$WK/license
D5=$B/$DEST; T43=$B/$TOM4_ROOT; BKT=${B#s3://}
export TOM_DUCKDB_TMP=$X/duckdb-tmp
T5="$PY -I -B $T/tom5_tools.py"; T2="$PY -I -B $T/tom2_tools.py"; TT="$PY -I -B $T/tom_tools.py"
FR="$PY -I -B $R/tools/fill_release.py"; RT="$PY -I -B $T/release_tools.py"
HFPY=${HF_PY:-$PY}; HT="$HFPY -I -B $T/hf_tools.py"; H5="$HFPY -I -B $T/tom5_tools.py"
NP=$(nproc); J=${JOBS:-$(( NP / 2 ))}; [ "$J" -ge 1 ] || J=1
mkdir -p $L $ST $WK $TOM_DUCKDB_TMP
cd $X || exit 1
if [ -n "$RUNAS" ]; then
  AS="runuser -u $RUNAS -- env HOME=/home/$RUNAS PATH=$PATH AWS_REGION=us-west-2 AWS_RETRY_MODE=adaptive AWS_MAX_ATTEMPTS=10 PYTHONDONTWRITEBYTECODE=1 TOM_DUCKDB_TMP=$TOM_DUCKDB_TMP"
  chown "$RUNAS": $X $L $ST $WK $TOM_DUCKDB_TMP
else
  AS="env PYTHONDONTWRITEBYTECODE=1 TOM_DUCKDB_TMP=$TOM_DUCKDB_TMP"
fi
log() { echo "[$(date -u +%FT%TZ)] $*"; }
t0=$(date +%s)
s3put() { [ "$LOCAL" = 1 ] && return 0; $AS aws s3 cp "$1" "$D5/log/$2" --only-show-errors || echo "log upload failed: $2"; }
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
  echo "tom5 run $st $(date -u +%FT%TZ) after $(( $(date +%s) - t0 )) s: $why; steps done: ${steps:-none}" > $ST/run.$st
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
  if [ "$NOSHUT" = 1 ] || [ -e /run/tom5-hold ] || [ -e /home/ec2-user/NO_SHUTDOWN ]; then
    log "no shutdown (NOSHUT=1 or a hold file)"
  elif [ $st = DONE ]; then
    log "shutdown in 1 min (the stop behavior of L1: the instance stops)"; shutdown -h +1
  else
    log "ALERT: shutdown in $ALERT_HOLD_MIN min (K1-tom5-hold.sh ACTION=hold keeps the machine)"; shutdown -h +$ALERT_HOLD_MIN
  fi
  [ $st = DONE ]
}

log "tom5 run: $T43/ + $NEW_RUNS -> $D5/root/; $NP vCPU, $(free -g | awk '/Mem:/{print $2}') GiB, jobs $J; local $LOCAL"
IN=$T/inputs
RUNARGS=(); for m in $NEW_RUNS; do RUNARGS+=(--run "$m=$ND/$m/results"); done

# ---- preflight
if todo preflight; then
  for f in $IN/new_projects.tsv $IN/names.tsv $IN/removed.tsv $IN/tom4.SHA256SUMS $IN/license/results.tom4.tsv \
           $IN/license/70_values.py $IN/license/30_compare.py $IN/license/license_rules.py $IN/lsc/license_scan.py \
           $IN/corrections.tsv $T/docs/README.md $T/docs/tools/fill_release.py; do
    [ -f $f ] || fail "the stage lacks $f"
  done
  [ "$(sha256sum $IN/tom4.SHA256SUMS | cut -d' ' -f1)" = "$TOM4_SUMS_SHA" ] || fail "the staged TOM-4 SHA256SUMS is not ${TOM4_SUMS_SHA:0:12}"
  if [ -n "$(ls -A $R 2>/dev/null)" ]; then fail "$R exists and is not empty (a new run takes a new machine)"; fi
  if [ "$LOCAL" != 1 ] && [ -z "$FAILED" ]; then
    $AS aws s3 cp $B/$TOM4/log/final.status.json $L/tom4.final.status.json --only-show-errors || fail "no $TOM4/log/final.status.json"
    if [ -z "$FAILED" ]; then
      st4=$($PY -I -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['status'], d['root_sha256sums'])" $L/tom4.final.status.json)
      [ "$st4" = "DONE $TOM4_SUMS_SHA" ] || fail "the TOM-4 root is '$st4', not DONE $TOM4_SUMS_SHA"
    fi
    for m in $NEW_RUNS; do
      [ "$({ $AS aws s3 ls $B/$NEW_PREFIX/$m/status/run.DONE || true; } | wc -l)" = 1 ] || fail "the new-project machine $m is not DONE (no status/run.DONE)"
    done
    n=$({ $AS aws s3 ls --recursive $D5/root/ 2>/dev/null || true; } | wc -l)
    [ "$n" = 0 ] || fail "$D5/root/ is not empty ($n objects): the run never writes over a root"
    if [ "$HF" = 1 ]; then
      nm=$(aws ssm get-parameter --region us-west-2 --name $HF_SSM_PARAM --query Parameter.Name --output text 2>/dev/null)
      [ "$nm" = "$HF_SSM_PARAM" ] || fail "no Hugging Face token in $HF_SSM_PARAM (the user runs ../dataset-hf/T1-hf-token-put.sh)"
    fi
    avail=$(df -BG --output=avail $X | tail -1 | tr -dc '0-9')
    [ "$avail" -ge 300 ] || fail "$X has $avail GB free, need 300"
  fi
  [ -z "$FAILED" ] && done_step preflight "new list $(( $(wc -l < $IN/new_projects.tsv) - 1 )) rows; audit flag: $([ -f $IN/AUDIT_OK ] && echo present || echo ABSENT); docs $(find $T/docs -type f | wc -l) files"
fi

# ---- fetch
if todo fetch; then
  if [ "$LOCAL" != 1 ]; then
    mkdir_as $T4 $ND
    $AS aws s3 cp $T43/SHA256SUMS $T4/SHA256SUMS --only-show-errors || fail "download of the TOM-4 SHA256SUMS"
    if [ -z "$FAILED" ]; then
      $AS aws s3 ls --recursive $T43/ > $WK/ls.tom4.txt || fail "the TOM-4 listing"
      base4=${T43#s3://*/}
      nobj=$(wc -l < $WK/ls.tom4.txt); nrow=$(wc -l < $T4/SHA256SUMS)
      miss=$(awk '{print $2}' $T4/SHA256SUMS | sed "s#^#$base4/#" | LC_ALL=C sort | LC_ALL=C comm -23 - <(awk '{print $4}' $WK/ls.tom4.txt | LC_ALL=C sort) | wc -l)
      [ "$nobj" = $((nrow + 1)) ] && [ "$miss" = 0 ] || fail "the TOM-4 root has $nobj objects for $nrow SHA256SUMS rows ($miss rows without an object)"
      [ -z "$FAILED" ] && { run_to fetch.txt aws s3 sync $T43/ $T4/ --exclude "parquet/*" --only-show-errors || fail "download of the TOM-4 files"; }
      [ -z "$FAILED" ] && { run_to fetch.txt aws s3 cp $T43/parquet/$SHAPE_REF $T4/parquet/$SHAPE_REF --only-show-errors || fail "download of $SHAPE_REF"; }
    fi
    for m in $NEW_RUNS; do
      [ -z "$FAILED" ] || break
      run_to fetch.txt aws s3 sync $B/$NEW_PREFIX/$m/ $ND/$m/ --exclude "results/ledger/*/logs/*" --only-show-errors || fail "download of $m"
    done
  fi
  if [ -z "$FAILED" ]; then
    cmp -s $T4/SHA256SUMS $IN/tom4.SHA256SUMS || fail "the TOM-4 SHA256SUMS is not the stage copy"
    (cd $T4 && while read -r d f; do [ -f "$f" ] && echo "$d  $f"; done < SHA256SUMS > $WK/t4.fetched.sums && sha256sum --quiet --strict -c $WK/t4.fetched.sums) >> $L/fetch.txt 2>&1 || fail "a fetched TOM-4 file does not check"
    nt=$(grep -vc '  parquet/' $T4/SHA256SUMS); nf=$(grep -vc '  parquet/' $WK/t4.fetched.sums)
    [ "$nt" = "$nf" ] || fail "fetched $nf of $nt TOM-4 files outside parquet/"
  fi
  [ -z "$FAILED" ] && done_step fetch "TOM-4 $(wc -l < $WK/t4.fetched.sums) files; new-project machines: $(for m in $NEW_RUNS; do echo -n "$m $(ls $ND/$m/parquet 2>/dev/null | wc -l) files; "; done)"
fi

# ---- newlist: the 149 projects and their files
if todo newlist; then
  run_to newlist.txt $T5 newlist --new-projects $IN/new_projects.tsv --names $IN/names.tsv --removed $IN/removed.tsv \
    --tom4-manifest $T4/MANIFEST.tsv "${RUNARGS[@]}" --expect $EXPECT_NEW --out $WK/new.resolved.tsv \
    --out-manifest $WK/new.MANIFEST.tsv || fail "the new list (log/newlist.txt)"
  if [ -z "$FAILED" ]; then
    mkdir_as $NF
    tail -n +2 $WK/new.resolved.tsv | while IFS=$'\t' read -r p f m s b r; do
      src=$ND/$m/parquet/$f
      [ -f "$src" ] || { echo "MISSING $f"; continue; }
      [ "$(sha256sum "$src" | cut -d' ' -f1)" = "$s" ] || { echo "SHA256 $f"; continue; }
      $AS ln -f "$src" $NF/$f 2>/dev/null || $AS cp "$src" $NF/$f
    done > $WK/newfiles.bad
    [ -s $WK/newfiles.bad ] && fail "new files: $(head -3 $WK/newfiles.bad | paste -sd' ') ($(wc -l < $WK/newfiles.bad) problems)"
    [ "$(ls $NF | wc -l)" = "$EXPECT_NEW" ] || fail "$(ls $NF | wc -l) new files, expected $EXPECT_NEW"
    cp $WK/new.resolved.tsv $L/new.resolved.tsv
  fi
  [ -z "$FAILED" ] && done_step newlist "$(tail -1 $L/newlist.txt)"
fi

# ---- shape: the Parquet form gate of the new files
if todo shape; then
  ls $NF/*-dataset.parquet > $WK/newfiles.list
  run_to shape.txt $T5 shape --ref $T4/parquet/$SHAPE_REF --columns $EXPECT_COLUMNS --list $WK/newfiles.list \
    || fail "the Parquet form gate (log/shape.txt)"
  [ -z "$FAILED" ] && done_step shape "$(tail -1 $L/shape.txt)"
fi

# ---- footers (TOM-4 by ranged reads, new files local) against the merged manifest
if todo footers; then
  mkdir_as $FT
  { cat $T4/MANIFEST.tsv; tail -n +2 $WK/new.MANIFEST.tsv; } > $WK/merged.MANIFEST.tsv
  if [ "$LOCAL" = 1 ]; then FSRC=(--local-tom4 $T4); else FSRC=(--s3 $BKT/$TOM4_ROOT); fi
  run_to footers.txt $T5 footers --manifest $WK/merged.MANIFEST.tsv --new $WK/new.resolved.tsv --out-dir $FT \
    --local-new $NF "${FSRC[@]}" --jobs $FOOTER_JOBS --first $FOOTER_FIRST || fail "the footers (log/footers.txt)"
  [ -z "$FAILED" ] && done_step footers "$(tail -1 $L/footers.txt)"
fi

# ---- license: the values (refused without the audit flag)
if todo license; then
  if [ ! -f $IN/AUDIT_OK ]; then
    fail "no inputs/AUDIT_OK: the hand check of the new license values is not done (S1 stages the flag)"
  fi
  if [ -z "$FAILED" ]; then
    mkdir_as $LIC
    run_to license.txt $T5 filevals --footers $FT/footers.jsonl --out $LIC/filevals.tsv || fail "the file values (log/license.txt)"
  fi
  if [ -z "$FAILED" ]; then
    run_to license.txt $T5 lscan-list --manifest $WK/new.MANIFEST.tsv --out $LIC/lscan.tsv
    if [ -n "${LSC_RESULTS_NEW:-}" ]; then
      cp "$LSC_RESULTS_NEW" $LIC/results.new.tsv
    else
      LJ=${LSC_TOOLS_JSON:-$X/lsc/tools.json}
      [ -f "$LJ" ] || fail "no scanner tools.json $LJ (R1)"
      LPY=${LSC_PY:-$(dirname "$(sed -n 's/.*"scancode": "\([^"]*\)".*/\1/p' $LJ)")/python3}
      if [ -z "$FAILED" ]; then
        mkdir_as $LIC/lsc-out $LIC/lsc-work
        run_to lscan.txt $LPY -B $IN/lsc/license_scan.py scan --list $LIC/lscan.tsv --out-dir $LIC/lsc-out \
          --work-dir $LIC/lsc-work --tools $LJ --jobs $LSC_JOBS || fail "the rescan of the new projects (log/lscan.txt)"
        run_to lscan.txt $LPY -B $IN/lsc/license_scan.py scan --list $LIC/lscan.tsv --out-dir $LIC/lsc-out \
          --work-dir $LIC/lsc-work --tools $LJ --jobs 4 --redo-status fetch-error,error || true
        run_to lscan.txt $LPY -B $IN/lsc/license_scan.py collect --out-dir $LIC/lsc-out || fail "the rescan collect"
        cp $LIC/lsc-out/results.tsv $LIC/results.new.tsv 2>/dev/null
      fi
    fi
  fi
  if [ -z "$FAILED" ]; then
    { cat $IN/license/results.tom4.tsv; tail -n +2 $LIC/results.new.tsv; } > $LIC/results.all.tsv
    awk -F'\t' 'BEGIN{OFS="\t"; print "project","clone_url"} NR>1{print $1,$2}' $WK/merged.MANIFEST.tsv > $LIC/projects.tsv
    run_to license.txt $PY -B $IN/license/70_values.py $LIC/results.all.tsv --tom-values $LIC/filevals.tsv \
      --projects $LIC/projects.tsv --corrections $IN/corrections.tsv --require-audit-ok $IN/AUDIT_OK \
      --out $LIC/values --no-sample || fail "the license rule (log/license.txt)"
  fi
  if [ -z "$FAILED" ]; then
    n_res=$(( $(wc -l < $LIC/results.all.tsv) - 1 )); n_files=$(( $(wc -l < $WK/merged.MANIFEST.tsv) - 1 ))
    [ "$n_res" = "$n_files" ] || fail "$n_res license results for $n_files project files"
    cp $LIC/values/license_fills.tsv $L/license_fills.tsv; cp $LIC/values/project_licenses.tsv $L/project_licenses.tsv
  fi
  [ -z "$FAILED" ] && done_step license "$(grep -E '^column:|^license fills' $L/license.txt | tail -2 | paste -sd' ' | cut -c1-300)"
fi
FILLS=$LIC/values/license_fills.tsv

# ---- ledger rows of the new projects
if todo ledger; then
  run_to ledger.txt $T5 ledger-rows --manifest $WK/new.MANIFEST.tsv --resolved $WK/new.resolved.tsv \
    --schema-ref $T4/ledgers.parquet --file-mask-sha256 $FILE_MASK_SHA256 "${RUNARGS[@]}" --out $WK/new.ledgers.parquet \
    || fail "the ledger rows (log/ledger.txt)"
  [ -z "$FAILED" ] && done_step ledger "$(tail -1 $L/ledger.txt)"
fi

# ---- pseudonymization.json
if todo pseudo; then
  run_to pseudo.txt $T5 pseudo --tom4 $T4/pseudonymization.json --footers $FT/footers.jsonl --new $WK/new.resolved.tsv \
    --out $WK/pseudonymization.json || fail "pseudonymization.json (log/pseudo.txt)"
  [ -z "$FAILED" ] && done_step pseudo "$(tail -1 $L/pseudo.txt)"
fi

# ---- fetch2: the TOM-4 project files with a license fill
if todo fetch2; then
  cut -f1 $FILLS | tail -n +2 | sort -u | grep -vxF -f <(tail -n +2 $WK/new.resolved.tsv | cut -f1) | sed 's/$/-dataset.parquet/' > $WK/fill4.list
  if [ "$LOCAL" != 1 ]; then
    INC=(); while read -r f; do INC+=(--include "parquet/$f"); done < $WK/fill4.list
    log "download of $(wc -l < $WK/fill4.list) TOM-4 project files with a fill"
    [ "${#INC[@]}" -gt 0 ] && { run_to fetch2.txt aws s3 sync $T43/ $T4/ --exclude "*" "${INC[@]}" --only-show-errors || fail "download of the changed TOM-4 files"; }
  fi
  if [ -z "$FAILED" ]; then
    (cd $T4 && sed 's#^#parquet/#' $WK/fill4.list | while read -r f; do awk -v f="$f" '$2 == f' SHA256SUMS; done > $WK/fill4.sums && sha256sum --quiet --strict -c $WK/fill4.sums) >> $L/fetch2.txt 2>&1 || fail "a changed TOM-4 file does not check"
    [ "$(wc -l < $WK/fill4.sums)" = "$(wc -l < $WK/fill4.list)" ] || fail "the SHA256SUMS rows of the changed TOM-4 files"
  fi
  [ -z "$FAILED" ] && done_step fetch2 "$(wc -l < $WK/fill4.list) files, $(sed 's#^#'$T4'/parquet/#' $WK/fill4.list | xargs -r du -cbL 2>/dev/null | tail -1 | cut -f1) B"
fi

# ---- base: TOM-4 + the new projects
if todo base; then
  rm -rf $BASE
  NDIRS=(); for m in $NEW_RUNS; do NDIRS+=($ND/$m/results); done
  run_to base.txt $T5 base --tom4 $T4 --new $WK/new.resolved.tsv --new-manifest $WK/new.MANIFEST.tsv \
    --new-ledgers $WK/new.ledgers.parquet --pseudo $WK/pseudonymization.json --new-files $NF --tom4-files $T4/parquet \
    --new-dirs "${NDIRS[@]}" --out $BASE || fail "the base root (log/base.txt)"
  if [ -z "$FAILED" ]; then
    tail -n +2 $BASE/MANIFEST.tsv | cut -f1 | sort > $WK/keep.names
    awk -F'\t' 'NR>1{n=$12; sub("^parquet/","",n); print $1"\t"n"\ttom1"}' $BASE/MANIFEST.tsv | sort > $WK/keep.resolved.tsv
    cut -f1,2 $WK/keep.resolved.tsv > $WK/keep.pf.tsv
    [ "$(wc -l < $WK/keep.names)" = "$EXPECT_FILES" ] || fail "the base has $(wc -l < $WK/keep.names) files, not $EXPECT_FILES"
  fi
  [ -z "$FAILED" ] && done_step base "$(tail -1 $L/base.txt | cut -c1-300)"
fi

# ---- plan
if todo plan; then
  nfill=$(( $(wc -l < $FILLS) - 1 ))
  run_to plan.txt $T2 plan --keep $WK/keep.resolved.tsv --footers $FT/footers.jsonl --fills $FILLS --out $WK/plan.tsv \
    --canary-out $WK/canary.list --src-dir $BASE/parquet --expect-files $EXPECT_FILES --expect-value $nfill \
    --expect-new 0 --expect-language 0 --expect-license $nfill || fail "the plan (log/plan.txt)"
  [ -z "$FAILED" ] && { cp $WK/plan.tsv $L/plan.tsv; done_step plan "$(tail -1 $L/plan.txt | cut -c1-300)"; }
fi

PASSARGS=(--plan $WK/plan.tsv --tom1-dir $BASE/parquet --src-dir $BASE/parquet --dst $OUT --tom1-sums $BASE/SHA256SUMS
  --src-sums $BASE/SHA256SUMS --ledger $L/ledger.jsonl --rename-py $T/parquet_rename.py --check-py $T/parquet_rename_check.py
  --work $WK/pass --drop-columns "" --rename "" --set-kv "" --expect-empty "" --expect-manifest-category "" --expect-file-mask ""
  --copy-mode $COPY_MODE --progress $L/progress.json --stop-file $X/STOP --check-dir $WK/checks)

# ---- canary
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
  miss=$(grep -v '  parquet/\|  organizations/\|  ledgers.parquet$\|  links.json$\|  pseudonymization.json$\|  MANIFEST.tsv$' $BASE/SHA256SUMS \
         | awk '{print $2}' | while read -r f; do [ -f "$T/docs/$f" ] || case " $ALLOW_GONE " in *" $f "*) ;; *) echo "$f" ;; esac; done)
  [ -z "$miss" ] || fail "the docs input lacks documents of the TOM-4 root: $(echo $miss)"
  mkdir_as $R/organizations
  for f in $BASE/organizations/*; do $AS cp "$f" $R/organizations/ || fail "copy of organizations/$(basename "$f")"; done
  for f in links.json pseudonymization.json ledgers.parquet; do $AS cp $BASE/$f $R/$f || fail "copy of $f"; done
  (cd $R && grep -E '  (organizations/|links\.json$|pseudonymization\.json$|ledgers\.parquet$)' $BASE/SHA256SUMS | sha256sum --quiet --strict -c -) \
    || fail "the copied base files are not byte-identical"
  [ -z "$FAILED" ] && done_step assemble "$(find $R -type f | wc -l) files"
fi

# ---- tables
if todo tables; then
  run_to tables.txt $T5 tables --root $R --licenses $LIC/values/project_licenses.tsv --names $WK/keep.names --org-db-version $ORG_DB_VERSION --org-db-doi $ORG_DB_DOI --org-build-tag $ORG_BUILD_TAG --tmp $TOM_DUCKDB_TMP \
    || fail "the side tables (log/tables.txt)"
  [ -z "$FAILED" ] && done_step tables "$(tail -1 $L/tables.txt)"
fi

# ---- manifest
if todo manifest; then
  run_to manifest.txt $T5 manifest --base-manifest $BASE/MANIFEST.tsv --plan $WK/plan.tsv --ledger $L/ledger.jsonl \
    --out $R/MANIFEST.tsv || fail "MANIFEST.tsv (log/manifest.txt)"
  [ -z "$FAILED" ] && done_step manifest "$(tail -1 $L/manifest.txt)"
fi

# ---- markers
if todo markers; then
  run_to markers.txt $TT sizes --manifest $R/MANIFEST.tsv --keep $WK/keep.pf.tsv --rule "$SIZE_RULE" --out $L/sizes.json || fail "the size rule (log/markers.txt)"
  MACH=local; [ "$LOCAL" != 1 ] && MACH=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/instance-type)
  [ -z "$FAILED" ] && { run_to markers.txt $T5 values --root $R --sizes $L/sizes.json --licenses $LIC/values/project_licenses.tsv \
    --fills $FILLS --filevals $LIC/filevals.tsv --new $WK/new.resolved.tsv --date "$(date -u +%F)" --machine "${MACH:-unknown}" \
    --tmp $TOM_DUCKDB_TMP --out $L/values.json || fail "the values (log/markers.txt)"; }
  [ -z "$FAILED" ] && { run_to markers.txt $TT markers --root $R --values $L/values.json --apply || fail "the placeholders (log/markers.txt)"; }
  [ -z "$FAILED" ] && done_step markers "$(tail -1 $L/markers.txt)"
fi

# ---- checksums
if todo checksums; then
  run_to checksums.txt $T5 sums --root $R --base-sums $BASE/SHA256SUMS --plan $WK/plan.tsv --new $WK/new.resolved.tsv \
    --changed-out $WK/changed.list --gone-out $WK/gone.list --new-unchanged-out $WK/new_unchanged.list --jobs $NP \
    || fail "SHA256SUMS (log/checksums.txt)"
  [ -z "$FAILED" ] && [ -s $WK/gone.list ] && fail "files of the base are gone: $(head -5 $WK/gone.list | paste -sd' ')"
  [ -z "$FAILED" ] && { cp $R/SHA256SUMS $L/root.SHA256SUMS; cp $R/MANIFEST.tsv $L/root.MANIFEST.tsv; cp $WK/changed.list $L/changed.list.txt; cp $WK/new_unchanged.list $L/new_unchanged.list.txt; }
  [ -z "$FAILED" ] && done_step checksums "SHA256SUMS $(sha256sum $R/SHA256SUMS | cut -c1-12), $(wc -l < $R/SHA256SUMS) rows; $(tail -1 $L/checksums.txt)"
fi

# ---- view
if todo view; then
  rm -rf $V
  run_to view.txt $T5 view --root $R --tails $FT --plan $WK/plan.tsv --out $V || fail "the check view (log/view.txt)"
  [ -z "$FAILED" ] && done_step view "$(tail -1 $L/view.txt)"
fi

# ---- checks (every check runs; the step fails when one fails)
if todo checks; then
  CF=""
  rows4=$TOM4_ROWS; rowsn=$(awk -F'\t' 'NR>1{s+=$6} END {printf "%d", s}' $WK/new.resolved.tsv)
  run_to check.root.txt $T5 check-root --root $R --view $V --plan $WK/plan.tsv --footers $FT/footers.jsonl --ledger $L/ledger.jsonl \
    --licenses $LIC/values/project_licenses.tsv --fills $FILLS --ref $SHAPE_REF --need-views "$NEED_VIEWS" \
    --want-columns $EXPECT_COLUMNS --expect-files $EXPECT_FILES --expect-rows $((rows4 + rowsn)) --max $MAX_PARQUET_FILES \
    --jobs $NP --tmp $TOM_DUCKDB_TMP --org-db-version $ORG_DB_VERSION --org-db-doi $ORG_DB_DOI --org-build-tag $ORG_BUILD_TAG --out $L/check-root.json || CF="$CF check-root"
  run_to check.fill.txt $FR check --root $V || CF="$CF fill_release-check"
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
    n=$({ $AS aws s3 ls --recursive $D5/root/ 2>/dev/null || true; } | awk '{print $4}' | grep -v "^$DEST/root/parquet/[A-Za-z0-9._-]*-dataset\.parquet$" | wc -l)
    [ "$n" = 0 ] || fail "$D5/root/ holds $n objects outside parquet/ (an earlier copy of the unchanged files can stay)"
    if [ -z "$FAILED" ]; then
      EXC=(); for f in "$OUT"/*-dataset.parquet; do EXC+=(--exclude "$(basename "$f")"); done
      bad=$(ls "$OUT" | grep -v '^[A-Za-z0-9._-]*$' || true)
      [ -z "$bad" ] || fail "file names with other characters than [A-Za-z0-9._-] (the S3 exclude patterns): $(echo $bad)"
      log "server-side copy of the unchanged TOM-4 project files (excludes: $(( ${#EXC[@]} / 2 )))"
      [ -z "$FAILED" ] && { run_to upload.txt aws s3 sync $T43/parquet/ $D5/root/parquet/ "${EXC[@]}" --copy-props metadata-directive --only-show-errors || fail "the S3 copy of the unchanged TOM-4 files"; }
      while read -r rel; do
        [ -z "$FAILED" ] || break
        run_to upload.txt aws s3 cp $NF/$(basename $rel) $D5/root/$rel --checksum-algorithm SHA256 --only-show-errors || fail "the upload of $rel"
      done < $WK/new_unchanged.list
    fi
    [ -z "$FAILED" ] && { run_to upload.txt aws s3 cp --recursive $R/ $D5/root/ --checksum-algorithm SHA256 --only-show-errors || fail "the upload of the local root"; }
    if [ -z "$FAILED" ]; then
      lsq() { $AS aws s3api list-objects-v2 --bucket $BKT --prefix "$1" --query 'Contents[].[Key,Size,ETag]' --output text; }
      lsq "$DEST/root/" > $WK/ls.root.txt || fail "the listing after the upload"
      lsq "$TOM4_ROOT/parquet/" > $WK/ls.tom4.etag.txt || fail "the TOM-4 listing (ETags)"
      miss=$(cd $V && find . -type f | sed 's#^\./##' | while read -r f; do echo "$DEST/root/$f $(stat -c %s "$f")"; done | LC_ALL=C sort \
             | LC_ALL=C comm -3 - <(awk '{print $1, $2}' $WK/ls.root.txt | LC_ALL=C sort) | wc -l)
      nobj=$(wc -l < $WK/ls.root.txt); nf=$(find $V -type f | wc -l)
      [ "$miss" = 0 ] && [ "$nobj" = "$nf" ] || fail "after the upload: $nobj objects for $nf files, $miss differences in path or size"
      unch=$(awk -F'\t' '$4 == "unchanged" {print $2}' $WK/plan.tsv | grep -vxF -f <(tail -n +2 $WK/new.resolved.tsv | cut -f2) | wc -l)
      same=$(LC_ALL=C join <(sed "s#^$TOM4_ROOT/parquet/##" $WK/ls.tom4.etag.txt | awk '{print $1, $3}' | LC_ALL=C sort) \
                            <(grep "^$DEST/root/parquet/" $WK/ls.root.txt | sed "s#^$DEST/root/parquet/##" | awk '{print $1, $3}' | LC_ALL=C sort) \
             | awk '$2 == $3' | wc -l)
      echo "ETags: $same of $unch unchanged TOM-4 project files have the TOM-4 ETag" | tee -a $L/upload.txt
      [ "$ETAG_CHECK" != require ] || [ "$same" = "$unch" ] || fail "ETags: $same of $unch unchanged files have the TOM-4 ETag"
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
        $HAS $HT verify --repo $HF_REPO --sums $T4/SHA256SUMS --out $L/hf-preverify.txt --expect $HF_VISIBILITY >> $L/hf.txt 2>&1; rc=$?
        if [ $rc = 0 ]; then echo "hf-pre DONE $(date -u +%FT%TZ)" > $ST/hf-pre.DONE
        elif [ "$HF_PRE_VERIFY" = require ]; then fail "the Hub is not the TOM-4 root (log/hf-preverify.txt); HF_PRE_VERIFY=skip pushes anyway"
        else log "the Hub is not the TOM-4 root (HF_PRE_VERIFY=$HF_PRE_VERIFY): push anyway"; fi
      fi
      mkdir_as $X/hfnew/parquet
      while read -r rel; do $AS ln -f $NF/$(basename $rel) $X/hfnew/$rel || fail "the Hub copy of $rel"; done < $WK/new_unchanged.list
      [ -z "$FAILED" ] && { $HAS $H5 hf-push --repo $HF_REPO --root $R --adds $WK/changed.list \
        --extra-roots "$X/hfnew=$WK/new_unchanged.list" --expect $HF_VISIBILITY --message "$HF_MESSAGE" >> $L/hf.txt 2>&1 || fail "hf push (log/hf.txt)"; }
      [ -z "$FAILED" ] && { $HAS $HT verify --repo $HF_REPO --sums $R/SHA256SUMS --card $R/README.md --out $L/hf-verify.txt \
        --expect $HF_VISIBILITY >> $L/hf.txt 2>&1 || fail "hf verify (log/hf-verify.txt)"; }
    fi
    rm -f $TOK
    [ -e $TOK ] && fail "the token file is still there"
    [ -z "$FAILED" ] && { echo "hf DONE $(date -u +%FT%TZ) repo $HF_REPO ($HF_VISIBILITY); $(( $(wc -l < $WK/changed.list) + $(wc -l < $WK/new_unchanged.list) )) files pushed; token file deleted" > $ST/hf.DONE; put_log; }
  fi
fi

finish
