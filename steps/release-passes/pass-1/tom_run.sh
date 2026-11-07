#!/usr/bin/env bash
# tom_run.sh (the TOM machine; a tool of the stage, so its sha256 is in stage/SHA256SUMS). tom_start.sh starts it as
# the systemd unit tom-run (root); the work runs as ec2-user (RUNAS). One run, the steps in order; a step with
# status/STEP.DONE is skipped (a second start continues). The first failed step ends the run (ALERT).
#   preflight  the stage inputs (keep list, docs), the new root prefix in S3 is empty, the disk
#   fetch      the source root (SRC_ROOT) to src/: its SHA256SUMS is SRC_SUMS_SHA and the stage copy, every
#              non-project file checks, SRC_FILES project files
#   keep       the project list against the source (tom_tools.py keep), then the kept files of src/ against
#              EXPECT_KEEP_FILES, EXPECT_KEEP_ROWS (footers) and EXPECT_KEEP_IN_BYTES
#   canary     drop + rename + check of ONE file (CANARY, else the smallest kept file); the run stops if it fails
#   pass       drop + rename + check of every kept file (largest first, JOBS at a time); ledger.jsonl
#   assemble   the root: parquet/ (the pass output), the docs of the stage (docs/), organizations/, links.json and
#              pseudonymization.json of the source; ledgers.parquet (LEDGERS=subset: the kept projects only)
#   facts      organizations/project_facts.parquet and its view in organizations/dataset.duckdb; ORGS=subset:
#              project_organizations.parquet of the kept projects only, release_info.parquet with the new rows and
#              sha256 of both tables
#   manifest   tools/fill_release.py manifest (the ledger records of ledgers.parquet give the run commits)
#   markers    the size rule counts, the measured values, the placeholders [[tom: KEY]] and TODO-DATE of the
#              documents (README.md too: it is the card of the Hugging Face upload); each fill is logged; only
#              TODO-DOI may be left
#   checksums  tools/fill_release.py checksums
#   checks     fill_release.py check, tom_tools.py check-root, sha256sum -c, release_tools.py no-at, no-paths and
#              guard, hf_tools.py precheck (the Hub limits) and validate-card (README.md)
#   upload     the root to s3://B/DEST/root/ (empty prefix only), the listing after (count and sizes)
#   hf         (HF=1) the token from SSM to tmpfs, create (HF_VISIBILITY), upload, verify; the token file deleted
#   end        log/final.status (DONE or ALERT and the steps), then shutdown: DONE at once, ALERT after
#              ALERT_HOLD_MIN minutes (L1 sets the stop behavior: the instance stops); NOSHUT=1 or /run/tom-hold
#              keeps it up.
# A file $X/STOP makes the pass start no new file (the run ends with ALERT "stopped"; a new start continues).
# Environment (tom_start.sh sets it): X T PY B RUNAS NOSHUT; TOM_LOCAL=1 for the local rehearsal (SRC_DIR is the
# source root, no S3, no Hugging Face, no shutdown).
set -uo pipefail
: "${X:?}" "${T:?}" "${PY:?}" "${B:?}"
. $T/tom.conf
RUNAS=${RUNAS-ec2-user}; NOSHUT=${NOSHUT:-0}; LOCAL=${TOM_LOCAL:-0}
S=${SRC_DIR:-$X/src}; R=$X/root; L=$X/log; ST=$X/status; WK=$X/work; OUT=$R/parquet
D3=$B/$DEST; SRC3=$B/$SRC_ROOT
TT="$PY -I -B $T/tom_tools.py"; FR="$PY -I -B $R/tools/fill_release.py"; RT="$PY -I -B $T/release_tools.py"
HFPY=${HF_PY:-$PY}; HT="$HFPY -I -B $T/hf_tools.py"
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
put_log() {  # the small files of log/ (tom_tools.py masks the at sign in every line it writes)
  local f
  for f in $L/*.txt $L/*.json $L/*.jsonl $L/*.tsv; do [ -f "$f" ] && s3put "$f" "$(basename "$f")"; done
  for f in $ST/*; do [ -f "$f" ] && s3put "$f" "status/$(basename "$f")"; done
  [ -f $X/run.log ] && tail -300 $X/run.log | sed "s/$(printf '\100')/(at)/g" > $L/run.tail.txt && s3put $L/run.tail.txt run.tail.txt
  return 0
}
FAILED=""
fail() { log "FAIL: $*"; FAILED="$*"; }
# step NAME: true when NAME is to be done now (not DONE before); done_step NAME [note] / the caller checks FAILED
todo() { [ -z "$FAILED" ] && [ ! -f $ST/$1.DONE ]; }
done_step() { echo "$1 DONE $(date -u +%FT%TZ)${2:+ $2}" > $ST/$1.DONE; log "step $1 done${2:+: $2}"; put_log; }
run_to() {  # run_to FILE CMD...: the command as RUNAS, its output appended to log/FILE; returns its rc
  local f=$1; shift
  $AS "$@" >> $L/$f 2>&1
}

finish() {
  local st=DONE why="all steps ok"
  [ -n "$FAILED" ] && { st=ALERT; why="$FAILED"; }
  local steps; steps=$(ls $ST/*.DONE 2>/dev/null | xargs -r -n1 basename | sed 's/\.DONE$//' | paste -sd' ')
  echo "tom run $st $(date -u +%FT%TZ) after $(( $(date +%s) - t0 )) s: $why; steps done: ${steps:-none}" > $ST/run.$st
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
  if [ "$NOSHUT" = 1 ] || [ -e /run/tom-hold ] || [ -e /home/ec2-user/NO_SHUTDOWN ]; then
    log "no shutdown (NOSHUT=1 or a hold file)"
  elif [ $st = DONE ]; then
    log "shutdown in 1 min (the stop behavior of L1: the instance stops)"; shutdown -h +1
  else
    log "ALERT: shutdown in $ALERT_HOLD_MIN min (K1-tom-hold.sh ACTION=hold keeps the machine)"; shutdown -h +$ALERT_HOLD_MIN
  fi
  [ $st = DONE ]
}

log "tom run: $SRC3/ -> $D3/root/; $NP vCPU, $(free -g | awk '/Mem:/{print $2}') GiB, jobs $J; local $LOCAL"

# ---- preflight
if todo preflight; then
  K=$T/keep/projects.keep.txt
  [ -s $K ] || fail "no keep list $K (S1 KEEP=...)"
  [ -f $T/docs/README.md ] && [ -f $T/docs/tools/fill_release.py ] || fail "the docs of the stage lack README.md or tools/fill_release.py"
  if [ -n "$(ls -A $R 2>/dev/null)" ]; then fail "$R exists and is not empty (a new run takes a new machine)"; fi
  if [ "$LOCAL" != 1 ] && [ -z "$FAILED" ]; then
    n=$({ $AS aws s3 ls --recursive $D3/root/ 2>/dev/null || true; } | wc -l)
    [ "$n" = 0 ] || fail "$D3/root/ is not empty ($n objects): the run never writes over a root"
    avail=$(df -BG --output=avail $X | tail -1 | tr -dc '0-9')
    [ "$avail" -ge 600 ] || fail "$X has $avail GB free, need 600"
  fi
  [ -z "$FAILED" ] && done_step preflight "keep list $(grep -c . $K) lines, docs $(find $T/docs -type f | wc -l) files"
fi

# ---- fetch
if todo fetch; then
  if [ "$LOCAL" != 1 ]; then
    mkdir -p $S; chown "$RUNAS": $S
    $AS aws s3 cp $SRC3/SHA256SUMS $S/SHA256SUMS --only-show-errors || fail "download of SHA256SUMS"
    h=$(sha256sum $S/SHA256SUMS | cut -d' ' -f1)
    [ "$h" = "$SRC_SUMS_SHA" ] || fail "the source SHA256SUMS is ${h:0:12}, not ${SRC_SUMS_SHA:0:12}"
    if [ -z "$FAILED" ]; then
      log "download of $SRC3/ (all project files; only the kept ones are used)"
      run_to fetch.txt aws s3 sync $SRC3/ $S/ --only-show-errors --exact-timestamps || fail "download of the source root"
    fi
  fi
  if [ -z "$FAILED" ]; then
    h=$(sha256sum $S/SHA256SUMS | cut -d' ' -f1)
    [ "$h" = "$SRC_SUMS_SHA" ] || fail "the source SHA256SUMS is ${h:0:12}, not ${SRC_SUMS_SHA:0:12}"
    cmp -s $S/SHA256SUMS $T/source.SHA256SUMS || fail "the source SHA256SUMS is not the stage copy"
    (cd $S && grep -v '  parquet/' SHA256SUMS | sha256sum --quiet --strict -c -) >> $L/fetch.txt 2>&1 || fail "a non-project file of the source does not check"
    np=$(find $S/parquet -name '*-dataset.parquet' | wc -l)
    [ "$np" = "$SRC_FILES" ] || fail "the source has $np project files, not $SRC_FILES"
  fi
  [ -z "$FAILED" ] && done_step fetch "$np project files, $(du -sbL $S | cut -f1) B"
fi

# ---- keep
if todo keep; then
  run_to keep.txt $TT keep --list $T/keep/projects.keep.txt --sums $S/SHA256SUMS --drop "$DROP_PROJECTS" \
    --max $MAX_PARQUET_FILES --out $WK/keep.resolved.tsv || fail "the keep list (log/keep.txt)"
  if [ -z "$FAILED" ]; then
    run_to keep.txt $TT count --dir $S/parquet --keep $WK/keep.resolved.tsv --expect-files $EXPECT_KEEP_FILES \
      --expect-rows $EXPECT_KEEP_ROWS --expect-bytes $EXPECT_KEEP_IN_BYTES --jobs $NP --out $L/keep.count.json \
      || fail "the kept source files are not the expected counts (log/keep.txt)"
  fi
  if [ -z "$FAILED" ]; then
    cut -f1 $WK/keep.resolved.tsv > $WK/keep.names; cp $WK/keep.resolved.tsv $L/keep.resolved.tsv
    done_step keep "$(tail -1 $L/keep.txt)"
  fi
fi
if [ -z "$FAILED" ] && [ ! -f $WK/keep.resolved.tsv ]; then fail "no keep.resolved.tsv"; fi

PASSARGS=(--src $S/parquet --dst $OUT --keep $WK/keep.resolved.tsv --sums $S/SHA256SUMS --ledger $L/ledger.jsonl
  --rename-py $T/parquet_rename.py --check-py $T/parquet_rename_check.py --drop-columns "$DROP_COLUMNS"
  --rename "$RENAME" --set-kv "$SET_KV" --expect-empty "$EXPECT_EMPTY" --expect-manifest-category "$EXPECT_MANIFEST_CATEGORY"
  --expect-file-mask "$EXPECT_FILE_MASK" --copy-mode $COPY_MODE --progress $L/progress.json
  --stop-file $X/STOP --check-dir $WK/checks)

# ---- canary: one file alone; the run stops when it fails
if todo canary; then
  mkdir -p $R $OUT; [ -n "$RUNAS" ] && chown "$RUNAS": $R $OUT
  C=$CANARY
  grep -qx "$C" $WK/keep.names 2>/dev/null || C=$(while IFS=$'\t' read -r p f; do echo "$(stat -c %s $S/parquet/$f) $p"; done < $WK/keep.resolved.tsv | sort -n | head -1 | cut -d' ' -f2)
  log "canary: $C"
  run_to canary.txt $TT pass "${PASSARGS[@]}" --only "$C" --jobs 1 --threads $NP \
    || fail "the canary $C failed drop + check (log/canary.txt, log/ledger.jsonl): the pass is stopped"
  [ -z "$FAILED" ] && done_step canary "$C: $(tail -1 $L/canary.txt)"
fi

# ---- pass
if todo pass; then
  run_to pass.txt $TT pass "${PASSARGS[@]}" --jobs $J --threads 2; rc=$?
  [ $rc = 3 ] && fail "stopped by $X/STOP (start the run again to continue)"
  [ $rc = 0 ] || [ $rc = 3 ] || fail "the pass rc $rc (failures in log/pass.txt and log/ledger.jsonl)"
  if [ -z "$FAILED" ]; then
    (cd $WK && tar -czf $L/checks.tgz checks) && s3put $L/checks.tgz checks.tgz
    done_step pass "$(grep '^pass summary' $L/pass.txt | tail -1)"
  fi
fi

# ---- assemble: the root around parquet/
if todo assemble; then
  set -f
  for f in $(cd $T/docs && find . -type f | sed 's#^\./##' | LC_ALL=C sort); do
    $AS mkdir -p "$(dirname "$R/$f")"; $AS cp "$T/docs/$f" "$R/$f" || fail "copy of the document $f"
  done
  set +f
  # the documents of the source root must all be in the docs input
  miss=$(cd $S && grep -v '  parquet/\|  organizations/\|  ledgers.parquet$\|  links.json$\|  pseudonymization.json$\|  MANIFEST.tsv$' SHA256SUMS \
         | awk '{print $2}' | while read -r f; do [ -f "$T/docs/$f" ] || echo "$f"; done)
  [ -z "$miss" ] || fail "the docs input lacks documents of the source root: $(echo $miss)"
  $AS mkdir -p $R/organizations
  for f in $S/organizations/*; do $AS cp "$f" $R/organizations/ || fail "copy of organizations/$(basename "$f")"; done
  for f in links.json pseudonymization.json; do $AS cp $S/$f $R/$f || fail "copy of $f"; done
  (cd $R && grep -E '  (organizations/|links\.json$|pseudonymization\.json$)' $S/SHA256SUMS | sha256sum --quiet --strict -c -) \
    || fail "the copied source files are not byte-identical"
  run_to assemble.txt $TT ledgers --src $S/ledgers.parquet --keep $WK/keep.resolved.tsv --out $R/ledgers.parquet \
    --jsonl $WK/ledger.project.jsonl --mode $LEDGERS || fail "ledgers.parquet (log/assemble.txt)"
  [ -z "$FAILED" ] && done_step assemble "$(find $R -type f | wc -l) files"
fi

# ---- facts
if todo facts; then
  run_to facts.txt $TT facts --root $R --keep $WK/keep.resolved.tsv --ledger $L/ledger.jsonl --facts-rel $FACTS_REL \
    --db-rel organizations/dataset.duckdb --view $FACTS_VIEW --report $L/facts.json || fail "project_facts (log/facts.txt)"
  if [ -z "$FAILED" ] && [ "$ORGS" = subset ]; then
    run_to facts.txt $TT orgs --root $R --src-root $S --keep $WK/keep.resolved.tsv --facts-rel $FACTS_REL \
      || fail "project_organizations and release_info (log/facts.txt)"
  fi
  [ -z "$FAILED" ] && done_step facts "$(grep 'rows' $L/facts.txt | head -1); $(tail -1 $L/facts.txt | cut -c1-160)"
fi

# ---- manifest (the fill step of the docs input)
if todo manifest; then
  run_to manifest.txt $FR manifest --root $R --ledgers $WK/ledger.project.jsonl --jobs $NP || fail "fill_release.py manifest (log/manifest.txt)"
  [ -z "$FAILED" ] && head -1 $R/MANIFEST.tsv | grep -qw layer && fail "MANIFEST.tsv has the layer column (fill_release.py of the docs input is not the TOM one)"
  [ -z "$FAILED" ] && done_step manifest "$(tail -1 $L/manifest.txt)"
fi

# ---- markers
if todo markers; then
  run_to markers.txt $TT sizes --manifest $S/MANIFEST.tsv --keep $WK/keep.resolved.tsv --rule "$SIZE_RULE" --out $L/sizes.json || fail "the size rule (log/markers.txt)"
  MACH=local; [ "$LOCAL" != 1 ] && MACH=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/instance-type)
  [ -z "$FAILED" ] && { run_to markers.txt $TT values --root $R --ledger $L/ledger.jsonl --keep $WK/keep.resolved.tsv --sizes $L/sizes.json \
    --db-rel organizations/dataset.duckdb --date "$(date -u +%F)" --machine "${MACH:-unknown}" --out $L/values.json || fail "the values (log/markers.txt)"; }
  [ -z "$FAILED" ] && { run_to markers.txt $TT markers --root $R --values $L/values.json --apply || fail "the placeholders (log/markers.txt)"; }
  [ -z "$FAILED" ] && done_step markers "$(tail -1 $L/markers.txt)"
fi

# ---- checksums
if todo checksums; then
  run_to checksums.txt $FR checksums --root $R --jobs $NP || fail "fill_release.py checksums (log/checksums.txt)"
  [ -z "$FAILED" ] && cp $R/SHA256SUMS $L/root.SHA256SUMS && cp $R/MANIFEST.tsv $L/root.MANIFEST.tsv
  [ -z "$FAILED" ] && done_step checksums "SHA256SUMS $(sha256sum $R/SHA256SUMS | cut -c1-12), $(wc -l < $R/SHA256SUMS) rows"
fi

# ---- checks (every check runs; the step fails when one fails)
if todo checks; then
  CF=""
  run_to check.fill.txt $FR check --root $R --allow-todo; rc=$?  # the marker rule (only TODO-DOI) is in check-root
  if [ $rc != 0 ]; then
    if [ "$FILL_CHECK" = require ]; then CF="$CF fill_release-check"; else log "fill_release.py check rc $rc (FILL_CHECK=report)"; fi
  fi
  run_to check.root.txt $TT check-root --root $R --src $S/parquet --src-root $S --keep $WK/keep.resolved.tsv \
    --ledger $L/ledger.jsonl --schema-from "$(head -1 $WK/keep.resolved.tsv | cut -f2)" --drop-columns "$DROP_COLUMNS" \
    --rename "$RENAME" --set-kv "$SET_KV" --db-rel organizations/dataset.duckdb --view $FACTS_VIEW --drop-projects "$DROP_PROJECTS" \
    --ledgers-mode $LEDGERS --max $MAX_PARQUET_FILES --want-columns $EXPECT_COLUMNS --jobs $NP --out $L/check-root.json || CF="$CF check-root"
  run_to check.count.txt $TT count --dir $OUT --keep $WK/keep.resolved.tsv --expect-files $EXPECT_KEEP_FILES \
    --expect-rows $EXPECT_KEEP_ROWS --jobs $NP --out $L/root.count.json || CF="$CF count"
  nf=$(find $R -type f | wc -l); rows=$(wc -l < $R/SHA256SUMS)
  [ "$nf" = $((rows + 1)) ] || CF="$CF files($nf)!=rows+1($rows)"
  (cd $R && split -n l/$NP -d SHA256SUMS $WK/sums. && ls $WK/sums.* | xargs -P $NP -I{} sha256sum --quiet --strict -c {}) > $L/check.sums.txt 2>&1 || CF="$CF sha256sum-c"
  rm -f $WK/sums.*
  run_to check.release.txt $RT no-at --root $R || CF="$CF no-at"
  run_to check.release.txt $RT no-paths --root $R || CF="$CF no-paths"
  run_to check.release.txt $RT guard --root $R --names $WK/keep.names || CF="$CF guard"
  pqn=$(find $OUT -mindepth 1 -maxdepth 1 | wc -l); [ "$pqn" -lt 10000 ] || CF="$CF parquet/=$pqn>=10000"
  run_to check.hf.txt $HT precheck --root $R --out $L/hf-precheck.txt \
    --limit MAX_ENTRIES=$HF_MAX_ENTRIES_PER_FOLDER --limit MAX_FILE=$HF_MAX_FILE_BYTES --limit REC_FILE=$HF_REC_FILE_BYTES \
    --limit REC_FILES=$HF_REC_FILES_PER_REPO --limit FREE=$HF_PRIVATE_QUOTA_FREE --limit PRO=$HF_PRIVATE_QUOTA_PRO \
    --limit PUBLIC_NOTE=$HF_PUBLIC_NOTE_BYTES --visibility $HF_VISIBILITY --quota 0 || CF="$CF hf-precheck"
  run_to check.hf.txt $HT validate-card --card $R/README.md || CF="$CF card"
  echo "checks: parquet/ $pqn entries; files $nf; failed:${CF:- none}" | tee -a $L/checks.txt
  [ -z "$CF" ] && done_step checks "parquet/ $pqn entries, $nf files, SHA256SUMS $(sha256sum $R/SHA256SUMS | cut -c1-12)" || fail "checks:$CF (log/check.*.txt)"
fi

# ---- upload: the new root (empty prefix only)
if todo upload; then
  if [ "$LOCAL" = 1 ]; then
    echo "local: no upload" > $ST/upload.SKIP
  else
    n=$({ $AS aws s3 ls --recursive $D3/root/ 2>/dev/null || true; } | wc -l)
    [ "$n" = 0 ] || fail "$D3/root/ is not empty ($n objects)"
    [ -z "$FAILED" ] && { run_to upload.txt aws s3 cp --recursive $R/ $D3/root/ --checksum-algorithm SHA256 --only-show-errors || fail "the upload of the root"; }
    if [ -z "$FAILED" ]; then
      $AS aws s3 ls --recursive $D3/root/ > $WK/ls.root.txt || fail "the listing after the upload"
      base=${D3#s3://*/}/root
      miss=$(cd $R && find . -type f | sed 's#^\./##' | while read -r f; do echo "$(stat -c %s "$f") $base/$f"; done | LC_ALL=C sort \
             | LC_ALL=C comm -23 - <(awk '{print $3, $4}' $WK/ls.root.txt | LC_ALL=C sort) | wc -l)
      nobj=$(wc -l < $WK/ls.root.txt); nf=$(find $R -type f | wc -l)
      [ "$miss" = 0 ] && [ "$nobj" = "$nf" ] || fail "after the upload: $nobj objects for $nf files, $miss files with no object of the same size"
      awk '{print $3, $4}' $WK/ls.root.txt | sed "s#$base/##" > $L/root.listing.txt
      [ -z "$FAILED" ] && done_step upload "$nobj objects, $(awk '{s+=$3} END {printf "%d", s}' $WK/ls.root.txt) B in s3://.../$DEST/root/"
    fi
  fi
fi

# ---- Hugging Face (only when every step before is DONE)
if [ -z "$FAILED" ] && [ ! -f $ST/hf.DONE ]; then
  if [ "$HF" != 1 ] || [ "$LOCAL" = 1 ]; then
    echo "hf skipped (HF=$HF, local $LOCAL)" > $ST/hf.SKIP
  else
    case $HF_VISIBILITY in public) VIS="" ;; private) VIS=--private ;; *) VIS=BAD ;; esac
    [ "$VIS" = BAD ] && fail "HF_VISIBILITY is $HF_VISIBILITY"
    TOK=$HF_TOKEN_DIR/token
    if [ -z "$FAILED" ]; then
      install -d -m 700 -o $RUNAS -g $RUNAS $HF_TOKEN_DIR
      (umask 077; aws ssm get-parameter --region us-west-2 --name $HF_SSM_PARAM --with-decryption --query Parameter.Value \
         --output text 2>/dev/null | tr -d '[:space:]' > $TOK); chown $RUNAS: $TOK
      [ -s $TOK ] || { rm -f $TOK; fail "no Hugging Face token in $HF_SSM_PARAM (the user runs ../dataset-hf/T1-hf-token-put.sh)"; }
    fi
    if [ -z "$FAILED" ]; then
      HAS="runuser -u $RUNAS -- env HOME=/home/$RUNAS HF_HOME=$X/hf-home HF_TOKEN_PATH=$TOK HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_PROGRESS_BARS=1 HF_XET_HIGH_PERFORMANCE=1"
      $HAS $HT create --repo $HF_REPO $VIS >> $L/hf.txt 2>&1 || fail "hf create (log/hf.txt)"
      [ -z "$FAILED" ] && { $HAS $HT upload --repo $HF_REPO $VIS --root $R --card $R/README.md --batch-files $HF_BATCH_FILES \
        --batch-bytes $HF_BATCH_BYTES >> $L/hf.txt 2>&1 || fail "hf upload (log/hf.txt; a new start resumes: the files on the Hub are skipped)"; }
      [ -z "$FAILED" ] && { $HAS $HT verify --repo $HF_REPO --sums $R/SHA256SUMS --card $R/README.md --out $L/hf-verify.txt \
        --expect $HF_VISIBILITY >> $L/hf.txt 2>&1 || fail "hf verify (log/hf-verify.txt)"; }
    fi
    rm -f $TOK
    [ -e $TOK ] && fail "the token file is still there"
    [ -z "$FAILED" ] && { echo "hf DONE $(date -u +%FT%TZ) repo $HF_REPO ($HF_VISIBILITY); token file deleted" > $ST/hf.DONE; put_log; }
  fi
fi

finish
