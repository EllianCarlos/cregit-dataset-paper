#!/usr/bin/env bash
# test-local.sh (this host, local only; S1 runs it on stage.new): the local rehearsal of tom5_run.sh (TOM_LOCAL=1: no
# S3, no Hugging Face, no shutdown) on 3 project files: 2 old files of a small TOM-4 style root (libexpat__libexpat,
# git.savannah.gnu.org__gnubg) and 1 new file (Weather-OS__WineGDK, with a test registry key), plus 1 file of a
# removed project on the machine (emscripten-core__emscripten). test/make_fixtures.py builds them from
# ../dataset-tom-4/test/tom3-root.
#   STAGE=<stage dir> [SCAN=1] bash test-local.sh
# SCAN=1 runs the real rescan of the new project (license_scan.py with the local scanner tools; it fetches the key
# files from GitHub); else the stored result of that project is the rescan.
# Scratch: test/work.<time> (not /tmp). Runs:
#   1  the whole run must end DONE; then: 3 project files in the view (2 changed: gnubg and WineGDK get their new
#      license values, libexpat stays), the removed project is not in the root, MANIFEST.tsv and SHA256SUMS check, the
#      side table and its view, the new rows of the project tables and of ledgers.parquet, the new registry in
#      pseudonymization.json, no placeholder left, the DOI of the release in the docs
#   2  no AUDIT_OK: the license step refuses, the run ends ALERT before the value pass
#   3  a project of the list without a file: the new list step stops the run
#   4  a new file of another Parquet form (the DuckDB-written gnubg file as a new file): the form gate stops the run
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
STAGE=${STAGE:?STAGE=<stage dir>}
PY=${PY:-$HOME/s3-work/dataset-reencode/.venv/bin/python}
HF_PY=${HF_PY:-$HOME/s3-work/dataset-hf/.venv/bin/python}
W=$H/test/work.$(date -u +%Y%m%dT%H%M%SZ); mkdir -p $W
echo "== test-local $(date -u +%FT%TZ) stage $STAGE work $W"
FIX=$W/fix
mkdir -p $H/stage-src
cp -f $STAGE/parquet_rename.py $H/stage-src/parquet_rename.py
$PY -I -B $H/test/make_fixtures.py $HOME/s3-work/dataset-tom-4/test/tom3-root $FIX > $W/fixtures.json
SUMS4=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['tom4_sums_sha'])" $FIX/info.json)
ROWS4=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['tom4_rows'])" $FIX/info.json)
REF=$($PY -I -c "import json,sys; print(json.load(open(sys.argv[1]))['shape_ref'])" $FIX/info.json)

tools() {  # a copy of the stage with the test values ($1: folder)
  local t=$1
  cp -r $STAGE $t
  sed -i -e "s/^TOM4_SUMS_SHA=.*/TOM4_SUMS_SHA=$SUMS4/" -e "s/^TOM4_FILES=.*/TOM4_FILES=2/" -e "s/^TOM4_ROWS=.*/TOM4_ROWS=$ROWS4/" \
    -e 's/^NEW_RUNS=.*/NEW_RUNS="tom-add-159-1"/' -e "s/^EXPECT_NEW=.*/EXPECT_NEW=1/" -e "s/^EXPECT_FILES=.*/EXPECT_FILES=3/" \
    -e "s/^SHAPE_REF=.*/SHAPE_REF=$REF/" $t/tom5.conf
  cp $FIX/inputs/new_projects.tsv $FIX/inputs/names.tsv $FIX/inputs/removed.tsv $t/inputs/
  cp $FIX/tom4-root/SHA256SUMS $t/inputs/tom4.SHA256SUMS
  cp $FIX/inputs/results.tom4.tsv $t/inputs/license/results.tom4.tsv
  printf 'test audit flag\n' > $t/inputs/AUDIT_OK
}
runit() {  # $1: run folder, $2: tools folder, $3: new-project folder
  local x=$1 t=$2 nd=$3
  mkdir -p $x
  local scan=(LSC_RESULTS_NEW=$FIX/inputs/results.new.tsv)
  [ "${SCAN:-0}" = 1 ] && scan=(LSC_TOOLS_JSON=LICENSE-PASS-FOLDER/local/tools.json LSC_JOBS=1)
  env TOM_LOCAL=1 TOM_X=$x TOM_PY=$PY HF_PY=$HF_PY TOM4_DIR=$FIX/tom4-root NEW_DIR=$nd JOBS=1 FOOTER_JOBS=2 "${scan[@]}" \
    bash -c "mkdir -p $x/tools && cp -r $t/. $x/tools/ && bash $x/tools/tom5_start.sh" > $x/start.txt 2>&1 || true
  cat $x/status/run.* 2>/dev/null | head -1
}

# ---- run 1: the whole run
tools $W/t1
R1=$(runit $W/x1 $W/t1 $FIX/new)
echo "run 1: $R1"
case "$R1" in *"run DONE"*) ;; *) tail -40 $W/x1/run.log; echo "FAIL: run 1 did not end DONE"; exit 1 ;; esac
X1=$W/x1; RT=$X1/root; V=$X1/view
$PY -I -B - $X1 <<'P'
import csv, json, os, sys, hashlib
import duckdb, pyarrow.parquet as pq
x = sys.argv[1]
root, view = f"{x}/root", f"{x}/view"
fail = []
pq_files = sorted(os.listdir(f"{view}/parquet"))
want = ["Weather-OS__WineGDK-dataset.parquet", "git.savannah.gnu.org__gnubg-dataset.parquet", "libexpat__libexpat-dataset.parquet"]
if pq_files != want: fail.append(f"view parquet/ {pq_files}")
if sorted(os.listdir(f"{root}/parquet")) != ["Weather-OS__WineGDK-dataset.parquet", "git.savannah.gnu.org__gnubg-dataset.parquet"]:
    fail.append(f"root parquet/ {sorted(os.listdir(f'{root}/parquet'))}")
for f, v in (("Weather-OS__WineGDK", "LGPL-2.1-or-later"), ("git.savannah.gnu.org__gnubg", "GPL-3.0-or-later")):
    got = duckdb.sql(f"SELECT DISTINCT license FROM read_parquet('{root}/parquet/{f}-dataset.parquet')").fetchall()
    if got != [(v,)]: fail.append(f"{f}: license {got}")
sums = {l.split("  ", 1)[1]: l.split("  ", 1)[0] for l in open(f"{root}/SHA256SUMS").read().splitlines()}
man = list(csv.DictReader(open(f"{root}/MANIFEST.tsv"), delimiter="\t"))
if len(man) != 3 or any(sums[r["path"]] != r["sha256"] for r in man): fail.append("MANIFEST.tsv vs SHA256SUMS")
os.chdir(view)
con = duckdb.connect(f"{root}/organizations/dataset.duckdb", read_only=True)
pl = con.execute("SELECT project, license, source FROM project_licenses ORDER BY 1").fetchall()
if [p for p, *_ in pl] != ["Weather-OS__WineGDK", "git.savannah.gnu.org__gnubg", "libexpat__libexpat"]: fail.append(f"project_licenses {pl}")
for t in ("project_organizations", "project_languages", "project_labels"):
    n = con.execute(f"SELECT count(DISTINCT project) FROM {t}").fetchone()[0]
    if n != 3: fail.append(f"{t}: {n} projects")
if con.execute("SELECT count(*) FROM tokens").fetchone()[0] <= 0: fail.append("tokens")
ri = dict(con.execute("SELECT key, value FROM release_info").fetchall())
if (ri.get("organization_database_version"), ri.get("organization_database_doi"), ri.get("organizations_version")) != \
        ("1.0.0", "10.5281/zenodo.23744044", "v4.9"): fail.append("release_info organization database keys")
os.chdir(x)
lp = set(pq.read_table(f"{root}/ledgers.parquet", columns=["project"]).column(0).to_pylist())
if "Weather-OS__WineGDK" not in lp or "emscripten-core__emscripten" in lp: fail.append(f"ledgers projects {sorted(lp)}")
pj = json.load(open(f"{root}/pseudonymization.json"))
if len(pj["registries"]) != 3 or "batches" not in pj or pj["registries"][-1]["projects"] != ["Weather-OS__WineGDK"]:
    fail.append("pseudonymization.json")
txt = "".join(open(os.path.join(d, f), errors="replace").read() for d, _, fs in os.walk(root) for f in fs if f.endswith((".md", ".cff")))
for bad in ("[[tom:", "TO" + "DO", "emscripten-core__emscripten"):
    if bad in txt: fail.append(f"docs hold {bad}")
if "10.57967/hf/11505" not in txt: fail.append("no DOI in the docs")
print("run 1 checks:", "ok" if not fail else fail)
sys.exit(1 if fail else 0)
P
grep -h -E '^newlist:|^shape:|^footers:|^filevals:|^column:|^license fills|^base:|^plan:|^pass summary|^tables:|^manifest:|^sums:|^check-root:' $X1/log/*.txt | cut -c1-220

# ---- run 2: no audit flag
tools $W/t2; rm -f $W/t2/inputs/AUDIT_OK
R2=$(runit $W/x2 $W/t2 $FIX/new)
echo "run 2: $R2"
case "$R2" in *"run ALERT"*"AUDIT_OK"*) ;; *) echo "FAIL: run 2 did not refuse without the audit flag"; exit 1 ;; esac
[ ! -f $W/x2/status/pass.DONE ] || { echo "FAIL: run 2 passed the value step"; exit 1; }

# ---- run 3: a project of the list without a file
tools $W/t3; printf 'Nobody/none\tgithub.com\n' >> $W/t3/inputs/new_projects.tsv; printf 'Nobody/none\tgithub.com\tNobody__none\n' >> $W/t3/inputs/names.tsv
sed -i "s/^EXPECT_NEW=.*/EXPECT_NEW=2/" $W/t3/tom5.conf
R3=$(runit $W/x3 $W/t3 $FIX/new)
echo "run 3: $R3"
case "$R3" in *"run ALERT"*"new list"*) grep -h 'missing' $W/x3/log/newlist.txt | head -2 ;; *) echo "FAIL: run 3 did not stop at the new list"; exit 1 ;; esac

# ---- run 4: a new file of another form
cp -r $FIX/new $W/new4
G=git.savannah.gnu.org__gnubg-dataset.parquet
cp $HOME/s3-work/dataset-tom-4/test/tom3-root/parquet/$G $W/new4/tom-add-159-1/parquet/Weather-OS__WineGDK-dataset.parquet
$PY -I -B - $W/new4/tom-add-159-1 <<'P'
import csv, hashlib, os, sys
d = sys.argv[1]
p = f"{d}/results/MANIFEST.new.tsv"
rows = list(csv.DictReader(open(p), delimiter="\t"))
for r in rows:
    if r["project"] == "Weather-OS__WineGDK":
        f = f"{d}/parquet/Weather-OS__WineGDK-dataset.parquet"
        r["sha256"], r["bytes"] = hashlib.sha256(open(f, "rb").read()).hexdigest(), str(os.path.getsize(f))
w = csv.DictWriter(open(p, "w", newline=""), fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
w.writeheader(); w.writerows(rows)
P
tools $W/t4
R4=$(runit $W/x4 $W/t4 $W/new4)
echo "run 4: $R4"
case "$R4" in *"run ALERT"*"form gate"*) grep -h '^BAD' $W/x4/log/shape.txt | cut -c1-160 | head -2 ;; *) echo "FAIL: run 4 did not stop at the form gate"; exit 1 ;; esac
echo "test-local: all 4 runs as expected (run 1 DONE; runs 2-4 stopped where they must)"
