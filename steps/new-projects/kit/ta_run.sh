#!/usr/bin/env bash
# ta_run.sh (a machine of the kit tom-add-159, root, as the systemd unit ta-run; a tool of the stage; ta_start.sh
# starts it): the new projects of the tokei funnel through the TOM pipeline at their funnel pins. GROUP (lists/
# group-<GROUP>.txt) names the projects of this machine. Each step writes status/STEP.DONE; a new start skips them.
#   precheck a depth-1 fetch of each pin: the bytes of the universal mask, the share in vendor-like folders and with
#            generated-like names, the largest files (results/precheck.tsv). MODE=precheck ends the run here (no salt
#            needed): the results go to S3; the machine stays up for S2 and B1
#   fetch    the TOM file of the gate project from Hugging Face; the sha256 of MANIFEST.tsv (TOM 1.0.0)
#   inputs   ta_tools.py inputs: the manifest, the sidecar, the fill rows and the license list of the group
#   license  license_scan.py (ctp 6b6efcf, the license pass) on the 6 gate projects of that pass (each must give its
#            known value) and on the group, at the pins
#   fill     the commit counts at the pins (a blobless clone) and the fills of the sidecar: commits, size_class,
#            license (LICENSE_RULE)
#   gate     the gate project, pass 1 (no salt), a plain write: equal to its TOM file except the pseudonym columns
#   (pseudo, after links) waits for P1-ta-pass2.sh; route newsalt: a new random salt on the machine; the TOM registry
#            tokens for the collision check; the gate project with the new salt against its TOM file:
#            the pseudonym columns bijections of TOM's, the other columns equal; after reencode the Parquet form of
#            the TOM file (ta_tools.py shape)
#   pass1    ctp run, schema 3, no salt: the private files (real identities) with the TOM link tables; PARALLEL at a
#            time, in the order of the group list (the longest first); the files move to private/pass1/
#   links    the TOM link step on the private files (extract_domains_v1.py with rule E, build_links.py, v4.9), then
#            ta_tools.py merge-links: TOM tables + the new rows (no conflict allowed), the report of new domains
#   pass2    ta_tools.py write: the private file without its 4 organization columns (the 49 generator columns),
#            then schema3.py write of ctp (the call of the ctp write phase) with the salt, one registry for each
#            project and the merged link tables: the published files (the generator does not run again)
#   reencode reencode_parquet.py (ctp c2a8432; the writer of the release files: pyarrow 26.0.1, ZSTD 19, ...; Bloom
#            filters on the 4 columns of the release that are left) with its content check: the published form
#   check    compare_tom.py pass 2 against pass 1 and ta_tools.py judge-pass (the copied columns equal, each
#            identity column a function of the private value); schema3.py check; ta_tools.py shape: the Parquet form of the TOM gate file (stops on any difference)
#   tables   MANIFEST rows, project_facts (schema3.py facts), project_organizations, project_labels,
#            project_languages, the ctp ledgers and logs
#   upload   the files to s3://BUCKET/PREFIX/run/<Name>/parquet/, results/ to run/<Name>/results/, the registries
#            and the full link tables to PREFIX/private/<Name>/ (real identities and personal domains)
#   end      the salt file is removed (shred); run.DONE
# A failed step writes status/run.ALERT, uploads the results, removes the salt, holds ALERT_HOLD_MIN minutes and
# stops the machine. STOP: touch $X/STOP (drive.py starts no new project; the step then fails with an ALERT).
set -uo pipefail
export HOME=${HOME:-/root}
X=${X:-/data/ta}; T=${T:-$X/tools}; B=${B:-s3://BUCKET_NAME}
for v in NOSHUT ALERT_HOLD_MIN PARALLEL BLAME_JOBS MEMORY_LIMIT DUCKDB_THREADS WRITE_JOBS ALLOW_FAIL; do eval "OV_$v=\${$v:-}"; done
. $T/ta.conf
for v in NOSHUT ALERT_HOLD_MIN PARALLEL BLAME_JOBS MEMORY_LIMIT DUCKDB_THREADS WRITE_JOBS ALLOW_FAIL; do eval "[ -n \"\$OV_$v\" ] && $v=\$OV_$v"; done
RUN=${TA_RUN:?TA_RUN (the Name tag) is not set}
GROUP=${GROUP:?GROUP (lists/group-GROUP.txt) is not set}
DEST=$B/$PREFIX/run/$RUN; PRIV_DEST=$B/$PREFIX/private/$RUN
ST=$X/status; R=$X/results; O=$X/out; IN=$X/inputs; TOM=$X/tom; P=$X/private; SALT=$X/secret/salt
PY=$X/venv/bin/python; C=$X/code; CFG=$X/ctp.cfg
LSC_PY=$LSC_STORE/bin/python3
AS="sudo -u ec2-user"
EC2_PATH=$X/venv/bin:/home/ec2-user/.nix-profile/bin:/nix/var/nix/profiles/default/bin:/usr/local/bin:/usr/bin:/bin
mkdir -p $ST $R; install -d -m 0700 -o ec2-user -g ec2-user $P
log() { echo "[$(date -u +%FT%TZ)] $*"; }
drop_salt() { [ -f $SALT ] && { shred -u $SALT 2>/dev/null || rm -f $SALT; log "salt file removed"; }; rm -f $P/tom-tokens.parquet $P/tom-registry.parquet; true; }
upload_results() {
  aws s3 sync $R/ $DEST/results/ --only-show-errors
  aws s3 cp $ST/ $DEST/status/ --recursive --only-show-errors
}
alert() {
  log "ALERT: $*"; echo "$(date -u +%FT%TZ) $*" > $ST/run.ALERT
  upload_results || true
  drop_salt
  if [ "${NOSHUT:-0}" != 1 ]; then
    log "the machine stops in $ALERT_HOLD_MIN minutes unless /run/ta-hold exists"
    sleep $(( ALERT_HOLD_MIN * 60 ))
    [ -e /run/ta-hold ] || shutdown -h now
  fi
  exit 1
}
done_step() { [ -f $ST/$1.DONE ]; }
mark() { date -u +%FT%TZ > $ST/$1.DONE; log "step $1 DONE"; }
LINKS_TOM=$T/links
BASE_ARGS=(--retries 1 --skip-html --drop-memo --tokenizer-worker --blame-jobs $BLAME_JOBS --memory-limit $MEMORY_LIMIT
           --duckdb-threads $DUCKDB_THREADS --project-meta $IN/project_meta.json --schema 3
           --organizations-version $ORGANIZATIONS_VERSION)
PASS1_ARGS=("${BASE_ARGS[@]}" --domain-links $LINKS_TOM/domain_links.parquet --project-links $LINKS_TOM/project_links.parquet)
write2() {  # NAMES LINKS OUT JOBS: the published file of each name from its private pass 1 file (ta_tools.py write)
  install -d -m 0700 -o ec2-user -g ec2-user $P/registries $P/write-work; install -d -o ec2-user -g ec2-user $3
  $AS $PY -I $T/ta_tools.py write --names $1 --private $P/pass1 --work $P/write-work --out-dir $3 --ctp $C/ctp \
    --links $2 --organizations-version $ORGANIZATIONS_VERSION --salt-file $SALT --psl $T/public_suffix_list.dat \
    --registry-dir $P/registries --memory-limit $MEMORY_LIMIT --threads $DUCKDB_THREADS --jobs $4 --log $R/write.jsonl
}
drive() {  # $1 = metrics file, rest = drive.py options, then -- and the ctp run options
  local m=$1; shift
  $PY -I -B $T/drive.py --manifest $IN/manifest.tsv --ctp-dir $C/ctp --ctp-config $CFG --out-dir $O \
    --metrics $m --uid ec2-user --python python3.12 \
    --setenv HOME=/home/ec2-user --setenv PATH=$EC2_PATH "$@"
}
reencode() {  # SRC DST RESULT: the release writer with its content check
  $AS $PY -I -B $T/reencode_parquet.py one $1 $2 --config $T/reencode.json --result $3 --pyarrow-version $PYARROW \
    --duckdb-version $DUCKDB --tmp $X/reencode-tmp --threads 4 > /dev/null 2>&1
}
to_private() {  # $1 = name: the pass 1 file goes to private/pass1/; the stamp goes, so that pass 2 can run
  local n=$1 f=$O/$1/$1-dataset.parquet
  [ -f $f ] || return 1
  install -d -m 0700 -o ec2-user -g ec2-user $P/pass1
  mv -f $f $P/pass1/$n.parquet && rm -f $O/$n/$n.validated
}
names() { grep -v '^#' $T/lists/group-$GROUP.txt | sed '/^$/d'; }
done1() { if [ -f $X/pass1-ok.txt ]; then cat $X/pass1-ok.txt; else names; fi; }  # the projects with a pass 1 file
log "ta_run start: run $RUN, group $GROUP ($(names | wc -l) projects), $(nproc) vCPU, $(free -g | awk '/Mem:/{print $2}') GiB, $(df -h --output=avail $X | tail -1) free"

# --- precheck (PRECHECK=1 or MODE=precheck; ta.conf sets PRECHECK=1 for the group long)
if ! done_step precheck && { [ "${PRECHECK:-0}" = 1 ] || [ "${MODE:-run}" = precheck ]; }; then
  install -d -o ec2-user -g ec2-user $X/precheck-work
  $AS $PY -I $T/ta_tools.py precheck --manifest $T/meta/manifest.tsv --only "$(names | paste -sd,)" --work $X/precheck-work \
    --out $R/precheck.jsonl --jobs 8 > $R/precheck.txt 2>&1 || alert "precheck: $(tail -1 $R/precheck.txt)"
  rm -rf $X/precheck-work
  log "$(tail -1 $R/precheck.txt)"
  mark precheck
fi
if [ "${MODE:-run}" = precheck ]; then
  upload_results; date -u +%FT%TZ > $ST/precheck.END; aws s3 cp $ST/precheck.END $DEST/status/precheck.END --only-show-errors
  log "MODE=precheck: done; the machine stays up (the instance store keeps the setup). Next: S2, then B1."; exit 0
fi

# --- fetch
if ! done_step fetch; then
  mkdir -p $TOM; f=$TOM/$GATE-dataset.parquet
  want=$(awk -F'\t' -v p=$GATE '$1==p{print $11}' $T/MANIFEST.tsv)
  [ -n "$want" ] || alert "fetch: $GATE is not in MANIFEST.tsv"
  for try in 1 2 3; do
    [ -f $f ] && [ "$(sha256sum $f | cut -d' ' -f1)" = "$want" ] && break
    curl -sfL --retry 3 -m 3600 "$HF_BASE/parquet/$GATE-dataset.parquet" -o $f.part && mv $f.part $f; sleep 5
  done
  [ "$(sha256sum $f | cut -d' ' -f1)" = "$want" ] || alert "fetch: the TOM file of $GATE has not the sha256 of MANIFEST.tsv"
  chown -R ec2-user: $TOM
  mark fetch
fi

# --- inputs
if ! done_step inputs; then
  $AS $PY -I $T/ta_tools.py inputs --meta-dir $T/meta --group $T/lists/group-$GROUP.txt --gate-tom $TOM/$GATE-dataset.parquet \
    --gate-row $T/gate.row.tsv --out-dir $IN > $R/inputs.txt 2>&1 || alert "inputs: $(tail -1 $R/inputs.txt)"
  log "$(tail -1 $R/inputs.txt)"
  mark inputs
fi

# --- license
if ! done_step license; then
  LAS="sudo -u ec2-user env HOME=/home/ec2-user PATH=$LSC_STORE/bin:/usr/bin:/bin LC_ALL=C.UTF-8"
  scan() { $LAS $LSC_PY -B $C/ctp-lsc/license_scan.py scan --list $1 --out-dir $2 --work-dir $X/lsc-work \
             --tools $X/lsc-tools.json --jobs $3 --stop-file $X/STOP; }
  mkdir -p $X/lsc-gate $X/lsc-out $X/lsc-work; chown ec2-user: $X/lsc-gate $X/lsc-out $X/lsc-work
  scan $X/lsc-stage/gate.tsv $X/lsc-gate 6 > $R/license-gate.log 2>&1 || alert "license: the gate scan failed"
  $LAS $LSC_PY -B $C/ctp-lsc/license_scan.py collect --out-dir $X/lsc-gate >> $R/license-gate.log 2>&1 || alert "license: gate collect"
  $PY -I - $X/lsc-stage/gate.tsv $X/lsc-gate/results.tsv > $R/license-gate.txt 2>&1 <<'PYEOF' || alert "license: a gate project does not give its value ($(tail -1 $R/license-gate.txt))"
import csv, sys
want = {r["project"]: r["license"] for r in csv.DictReader(open(sys.argv[1]), delimiter="\t")}
got = {r["project"]: r for r in csv.DictReader(open(sys.argv[2]), delimiter="\t")}
bad = [p for p, v in want.items() if got.get(p, {}).get("status") != "ok" or got[p]["license"] != v]
print(f"license gate: {len(want) - len(bad)} of {len(want)} projects give their value {bad}")
sys.exit(1 if bad else 0)
PYEOF
  scan $IN/lsc.tsv $X/lsc-out $LSC_JOBS > $R/license-scan.log 2>&1 || alert "license: scan rc=$? (results/license-scan.log)"
  scan $IN/lsc.tsv $X/lsc-out 4 --redo-status fetch-error,error >> $R/license-scan.log 2>&1 || true
  $LAS $LSC_PY -B $C/ctp-lsc/license_scan.py collect --out-dir $X/lsc-out >> $R/license-scan.log 2>&1 || alert "license: collect"
  cp -f $X/lsc-out/results.tsv $R/license-results.tsv
  log "$(tail -1 $R/license-gate.txt); scan: $(awk -F'\t' 'NR>1{print $3}' $R/license-results.tsv | sort | uniq -c | tr '\n' ' ')"
  mark license
fi

# --- fill
if ! done_step fill; then
  $AS $PY -I $T/ta_tools.py counts --in-dir $IN --work $X/count-work --jobs 16 > $R/counts.txt 2>&1 || alert "fill: $(tail -1 $R/counts.txt)"
  $AS $PY -I $T/ta_tools.py fill --in-dir $IN --lsc-out $X/lsc-out --rule $LICENSE_RULE --licensee-bin $LICENSEE918/bin/licensee > $R/fill.txt 2>&1 || alert "fill: $(tail -1 $R/fill.txt)"
  cp -f $IN/fill.done.tsv $IN/counts.tsv $IN/manifest.tsv $R/ ; rm -rf $X/count-work
  log "$(tail -1 $R/counts.txt); $(tail -1 $R/fill.txt)"
  mark fill
fi

# --- gate
if ! done_step gate; then
  drive $R/metrics-gate1.tsv --only $GATE --parallel 1 -- "${PASS1_ARGS[@]}" > $R/drive-gate.log 2>&1 || alert "gate: pass 1 of $GATE failed"
  to_private $GATE || alert "gate: no pass 1 file of $GATE"
  echo $GATE > $X/gate-name.txt
  $AS $PY -I $T/ta_tools.py write --names $X/gate-name.txt --private $P/pass1 --work $P/write-work --out-dir $X/gate-plain \
    --ctp $C/ctp --links $LINKS_TOM --organizations-version $ORGANIZATIONS_VERSION --jobs 1 --log $R/write-gate-plain.jsonl \
    >> $R/drive-gate.log 2>&1 || alert "gate: the plain write of $GATE failed"
  # the private gate file against TOM: every column except the pseudonym columns must be equal now
  $AS $PY -I $T/compare_tom.py $X/gate-plain/$GATE-dataset.parquet $TOM/$GATE-dataset.parquet --json $R/gate1-compare.json > /dev/null 2>&1
  $PY -I $T/ta_tools.py judge-gate --pseudonyms differ-ok $R/gate1-compare.json > $R/gate1.txt 2>&1 || alert "gate: pass 1 of $GATE ($(tail -1 $R/gate1.txt | cut -c1-200))"
  log "$(tail -1 $R/gate1.txt)"
  mark gate
fi

# --- pass1
if ! done_step pass1; then
  ( while sleep 1800; do upload_results 2>/dev/null; done ) & SYNC=$!
  names > $X/order.txt
  drive $R/metrics-pass1.tsv --order $X/order.txt --only "$(names | paste -sd,)" --parallel $PARALLEL --stop-file $X/STOP -- "${PASS1_ARGS[@]}" \
    > $R/drive-pass1.log 2>&1; rc=$?
  kill $SYNC 2>/dev/null
  for n in $(names); do [ -f $O/$n/$n-dataset.parquet ] && to_private $n; done
  miss=$(for n in $(names); do [ -f $P/pass1/$n.parquet ] || echo $n; done)
  for n in $(names); do [ -f $P/pass1/$n.parquet ] && echo $n; done > $X/pass1-ok.txt
  if [ -n "$miss" ]; then
    echo "$miss" > $R/pass1-failed.txt
    # ALLOW_FAIL=1 (default): the other projects go on; the failed ones are listed and run again later (B1 with
    # GROUP of a new list). ALLOW_FAIL=0: ALERT.
    [ "${ALLOW_FAIL:-1}" = 1 ] && [ -s $X/pass1-ok.txt ] || alert "pass1: drive.py rc=$rc; no private file for: $(echo $miss | cut -c1-200)"
    log "pass1: $(echo $miss | wc -w) projects failed (results/pass1-failed.txt); $(wc -l < $X/pass1-ok.txt) go on"
  fi
  mark pass1
fi

# --- links
if ! done_step links; then
  L=$P/links; install -d -m 0700 -o ec2-user -g ec2-user $L
  { printf 'project\tpath\n'; for n in $(done1); do printf '%s\t%s\n' $n $P/pass1/$n.parquet; done; } > $L/pass1.tsv
  $AS $PY -I $T/ta_tools.py thin --list $L/pass1.tsv --out-dir $L/thin > $R/links-thin.txt 2>&1 || alert "links: thin"
  $AS $PY -I $T/org/extract_domains_v1.py --inputs $L/thin/extract.tsv --cache $L/cache --jobs 8 --threads 1 \
    --memory-limit 4GB --person-domain-at first-valid --psl $T/public_suffix_list.dat --anon-dir $T/org/anon \
    > $L/extract.log 2>&1 || alert "links: extract_domains_v1.py ($(tail -1 $L/extract.log | cut -c1-160))"
  $PY -I - $L/thin/extract.tsv $L/cache > $R/links-cache.txt 2>&1 <<'PYEOF' || alert "links: the cache tokens are not the rows of the files"
import csv, sys, duckdb
want = {r["project"]: int(r["rows"]) for r in csv.DictReader(open(sys.argv[1]), delimiter="\t")}
got = dict(duckdb.execute(f"SELECT project, sum(tokens) FROM read_parquet('{sys.argv[2]}/*.parquet') GROUP BY 1").fetchall())
bad = [p for p in want if got.get(p) != want[p]]
print(f"cache: {len(want) - len(bad)} of {len(want)} projects have tokens = rows {bad[:5]}")
sys.exit(1 if bad else 0)
PYEOF
  $PY -I -c "import json,sys; m=json.load(open(sys.argv[1])); n=[l.strip() for l in open(sys.argv[2]) if l.strip() and not l.startswith('#')]; json.dump({k: m[k] for k in n}, open(sys.argv[3],'w'), indent=1, sort_keys=True)" \
    $IN/project_meta.json $T/lists/group-$GROUP.txt $L/project_meta.group.json
  $AS $PY -I $T/org/build_links.py --organisations-version $ORGANIZATIONS_VERSION --db $T/org/companies.v4.9.duckdb \
    --cache $L/cache --sidecar $L/project_meta.group.json --out $L/new --memory-limit 8GB --threads 4 \
    > $L/build_links.stdout.json 2> $L/build_links.err || alert "links: build_links.py ($(tail -1 $L/build_links.err | cut -c1-160))"
  $AS $PY -I $T/ta_tools.py merge-links --tom-dir $LINKS_TOM --new-dir $L/new --cache $L/cache --out-dir $L/merged \
    > $R/links.txt 2>&1 || alert "links: merge-links ($(tail -1 $R/links.txt | cut -c1-200))"
  cp -f $L/merged/report.json $R/links-report.json; cp -f $L/merged/organization_domains.new.parquet $R/
  log "$(tail -1 $R/links.txt | cut -c1-400)"
  mark links
fi

# --- pseudo: the input of pass 2 (PASS2_MODE of ta.conf, or a file $X/pass2.mode written later). Route newsalt:
# TOM is built in batches, each batch with its own salt that is deleted at the end of the batch, so personid is
# stable only inside a batch. This batch gets a new random salt made here (never printed, never off the machine,
# shredded at the end). The run stops if a new token equals a token of the TOM registry (the private registry of the
# TOM write, read here for its space and token columns only, then shredded).
if ! done_step pseudo; then
  [ -f $X/pass2.mode ] || [ -z "${PASS2_MODE:-}" ] || echo "$PASS2_MODE" > $X/pass2.mode
  if [ ! -f $X/pass2.mode ]; then
    date -u +%FT%TZ > $ST/pass2.WAIT; upload_results 2>/dev/null
    log "pseudo: pass 1 and the links are done; waiting for $X/pass2.mode"
    while [ ! -f $X/pass2.mode ]; do sleep 30; done
    rm -f $ST/pass2.WAIT
  fi
  mode=$(cat $X/pass2.mode)
  [ "$mode" = newsalt ] || alert "pseudo: the route '$mode' is not in this kit (newsalt only)"
  if [ ! -f $SALT ]; then
    ( umask 077; head -c 32 /dev/urandom | base64 > $SALT.new ) && chown ec2-user: $SALT.new && chmod 0400 $SALT.new && mv $SALT.new $SALT
  fi
  aws s3 cp $TOM_REGISTRY $P/tom-registry.parquet --only-show-errors || alert "pseudo: no TOM registry"
  aws s3 cp $TOM_REGISTRY.sha256 $P/tom-registry.sha256 --only-show-errors || alert "pseudo: no TOM registry sha256"
  [ "$(sha256sum $P/tom-registry.parquet | cut -d' ' -f1)" = "$(cut -d' ' -f1 $P/tom-registry.sha256)" ] || alert "pseudo: the TOM registry sha256"
  $AS $PY -I -c "import duckdb,sys; duckdb.execute(f\"COPY (SELECT DISTINCT space, token FROM read_parquet('{sys.argv[1]}') WHERE token IS NOT NULL) TO '{sys.argv[2]}' (FORMAT PARQUET)\"); print(duckdb.execute(f\"SELECT count(*) FROM '{sys.argv[2]}'\").fetchone()[0], 'TOM tokens')" \
    $P/tom-registry.parquet $P/tom-tokens.parquet > $R/pseudo.txt 2>&1 || alert "pseudo: the TOM tokens"
  shred -u $P/tom-registry.parquet 2>/dev/null || rm -f $P/tom-registry.parquet
  chown ec2-user: $P/tom-tokens.parquet
  # the gate project with the new salt: equal to TOM except the pseudonym columns, which must be bijections of TOM's
  echo $GATE > $X/gate-name.txt
  write2 $X/gate-name.txt $LINKS_TOM $X/gate-out 1 >> $R/drive-gate.log 2>&1 || alert "gate: the write of pass 2 of $GATE failed"
  reencode $X/gate-out/$GATE-dataset.parquet $X/gate.parquet $R/gate-reencode.json || alert "gate: reencode"
  $AS $PY -I $T/compare_tom.py $X/gate.parquet $TOM/$GATE-dataset.parquet --json $R/gate-compare.json > $R/gate-compare.txt 2>&1
  $PY -I $T/ta_tools.py judge-gate --pseudonyms bijection $R/gate-compare.json > $R/gate.txt 2>&1 || alert "gate: $(tail -1 $R/gate.txt)"
  $AS $PY -I $T/ta_tools.py shape --ref $TOM/$GATE-dataset.parquet $X/gate.parquet >> $R/gate.txt 2>&1 || alert "gate: the Parquet form differs from the TOM file ($(tail -1 $R/gate.txt | cut -c1-200))"
  log "pseudo: route $mode; $(tail -1 $R/pseudo.txt); $(grep -m1 '^gate' $R/gate.txt)"
  mark pseudo
fi

# --- pass2
if ! done_step pass2; then
  [ -f $SALT ] || alert "pass2: no salt (an ALERT removed it): remove status/pseudo.DONE, $X/final53 and $P/registries, then B1 (one salt for all files of a machine)"
  install -d -m 0700 -o ec2-user -g ec2-user $P/registries
  done1 > $X/order.txt
  write2 $X/order.txt $P/links/merged $X/final53 $WRITE_JOBS > $R/write-pass2.txt 2>&1 || alert "pass2: $(tail -1 $R/write-pass2.txt | cut -c1-200)"
  $AS $PY -I -c "
import duckdb, sys
c = duckdb.connect()
n = c.execute(f\"SELECT count(*) FROM (SELECT DISTINCT space, token FROM read_parquet('{sys.argv[1]}/*.parquet', union_by_name=true) WHERE token IS NOT NULL) x JOIN read_parquet('{sys.argv[2]}') t USING (space, token)\").fetchone()[0]
print(f'collision check: {n} new tokens equal a TOM token'); sys.exit(1 if n else 0)" $P/registries $P/tom-tokens.parquet >> $R/write-pass2.txt 2>&1 \
    || alert "pass2: $(tail -1 $R/write-pass2.txt | cut -c1-200)"
  mark pass2
fi

# --- reencode
if ! done_step reencode; then
  install -d -o ec2-user -g ec2-user $X/files $X/reencode-tmp
  : > $R/reencode.txt; bad=""
  for n in $(done1); do
    reencode $X/final53/$n-dataset.parquet $X/files/$n-dataset.parquet $R/reencode-$n.json || bad="$bad $n"
    echo "$n: $(sha256sum $X/files/$n-dataset.parquet 2>/dev/null | cut -c1-16)" >> $R/reencode.txt
  done
  [ -z "$bad" ] || alert "reencode: the content check failed for:$bad"
  mark reencode
fi

# --- check
if ! done_step check; then
  : > $R/checks.txt; bad=0
  for n in $(done1); do
    f=$X/final53/$n-dataset.parquet
    $AS $PY -I $T/compare_tom.py $f $P/pass1/$n.parquet --json $X/cmp-$n.json > /dev/null 2>&1
    $PY -I $T/ta_tools.py judge-pass $X/cmp-$n.json > $X/judge-$n.txt 2>&1 || bad=$((bad + 1))
    $AS env PATH=$X/venv/bin:/usr/bin:/bin python3 -I $C/ctp/validate.py $X/files/$n-dataset.parquet $X/validated-$n.stamp \
      > $X/validate-$n.txt 2>&1 || { bad=$((bad + 1)); echo "$n: validate.py FAIL" >> $R/checks.txt; }
    echo "$n: $(tail -1 $X/judge-$n.txt)" >> $R/checks.txt
  done
  files=$(for n in $(done1); do echo $X/files/$n-dataset.parquet; done)
  $AS env PATH=/usr/bin:/bin $PY -I $C/ctp/schema3.py check $files > $R/schema3-check.txt 2>&1 || bad=$((bad + 1))
  $AS $PY -I $T/ta_tools.py shape --ref $TOM/$GATE-dataset.parquet $files > $R/shape.txt 2>&1 || bad=$((bad + 1))
  log "check: $(grep -c ' -> OK' $R/checks.txt) of $(done1 | wc -l) pass checks OK; schema3 check $(tail -1 $R/schema3-check.txt | cut -c1-120); shape $(grep -c '^ok ' $R/shape.txt) ok"
  [ $bad = 0 ] || alert "check: $bad failed (results/checks.txt, schema3-check.txt, shape.txt)"
  mark check
fi

# --- tables
if ! done_step tables; then
  done1 > $X/names.txt
  $AS $PY -I $T/ta_tools.py manifest --in-dir $IN --files $X/files --names $X/names.txt --cregit $CREGIT_COMMIT \
    --ctp $CTP_COMMIT --out $R/MANIFEST.new.tsv > $R/tables.txt 2>&1 || alert "tables: manifest"
  $AS env PATH=/usr/bin:/bin $PY -I $C/ctp/schema3.py facts --sidecar $IN/project_meta.json --out $R/project_facts.new.parquet \
    $(cat $X/names.txt) >> $R/tables.txt 2>&1 || alert "tables: project_facts"
  $AS $PY -I $T/ta_tools.py tables --in-dir $IN --meta-dir $T/meta --links $P/links/merged --names $X/names.txt \
    --out-dir $R >> $R/tables.txt 2>&1 || alert "tables: $(tail -1 $R/tables.txt)"
  mkdir -p $R/ledger; cp -f $C/ctp/metrics.tsv $C/ctp/runs.log $C/ctp/resources.tsv $R/ledger/ 2>/dev/null
  for n in $(done1) $GATE; do
    [ -d $C/ctp/state/$n/logs ] && { mkdir -p $R/ledger/$n; cp -rL $C/ctp/state/$n/logs $R/ledger/$n/ 2>/dev/null; cp -f $C/ctp/state/$n/pin.json $R/ledger/$n/ 2>/dev/null; }
    cp -f $O/$n/pipeline.log $R/ledger/$n/ 2>/dev/null
  done
  log "tables: $(grep -c . $R/MANIFEST.new.tsv) manifest lines; $(tail -1 $R/tables.txt | cut -c1-200)"
  mark tables
fi

# --- upload
if ! done_step upload; then
  for n in $(done1); do
    aws s3 cp $X/files/$n-dataset.parquet $DEST/parquet/$n-dataset.parquet --only-show-errors || alert "upload: $n"
  done
  ( cd $X/files && sha256sum *-dataset.parquet ) > $R/SHA256SUMS.parquet
  aws s3 cp --recursive $P/registries/ $PRIV_DEST/registries/ --only-show-errors || alert "upload: registries"
  aws s3 cp --recursive $P/links/merged/ $PRIV_DEST/links-merged/ --only-show-errors || alert "upload: link tables"
  aws s3 cp $P/links/new/links.json $PRIV_DEST/links-new/links.json --only-show-errors || true
  upload_results || alert "upload: results"
  mark upload
fi
drop_salt
date -u +%FT%TZ > $ST/run.DONE
aws s3 cp $ST/run.DONE $DEST/status/run.DONE --only-show-errors
log "ta_run DONE"
[ "${NOSHUT:-0}" = 1 ] || { [ -e /run/ta-hold ] || shutdown -h now; }
