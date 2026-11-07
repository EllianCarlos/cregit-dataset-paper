#!/usr/bin/env bash
# rebuild-one.sh: build the dataset again for one project, and compare the new files with the
# recorded and the published values.
#
# Usage: scripts/rebuild-one.sh PROJECT [TOOLS_DIR]
#   PROJECT    the manifest name, for example libexpat__libexpat or gitlab.com__muttmua__mutt.
#   TOOLS_DIR  the directory of the tool bundles of tools.lock (default: tools/bundles).
# Optional environment:
#   WORK_DIR     the scratch directory (default: work/rebuild-PROJECT; the script writes only here).
#   CTP_DIR      a ctp clone to copy, in place of TOOLS_DIR/ctp.bundle.
#   CREGIT_DIR   a cregit tree with its built jars and tokenizer programs, in place of the cregit
#                bundle of TOOLS_DIR (the script copies it and checks its commit).
#   CTP_PYTHON   a Python with duckdb 1.5.5 for ctp and the merge step (default: a new venv with
#                python3.12 and duckdb 1.5.5 in WORK_DIR).
#   MERGE_SIDECAR the final sidecar of the layer, when it is not under pipeline/ (sha256 checked).
#   DATA_DIR     the release root; if it has the published file, step 6 compares the columns.
#   MIN_FREE_GB  the start floor of free memory for ctp (default 4; a start condition only).
#
# The published files went through the release write: the organization columns and the
# pseudonyms of the identity columns, in one write, with a salt. The salt is deleted by design,
# so no one can make the published bytes again. The rule (REPRODUCE.md, section 6.1):
#   a. the ctp run gives merge_input_sha256 of data/REBUILD-TARGETS.tsv (the run output);
#   b. the layer merge of that file gives pre_pseudonym_sha256 (the input of the release write);
#   c. the published file of TOM is equal to the file of b in every column that the release
#      write and the release passes do not change, with the same rows in the same order
#      (scripts/compare_published.py; the passes drop 18 columns, rename one and fill language
#      and license).
#
# The script checks the inputs step by step. At the first step that is not ready, it prints
# "not ready: <reason>" and exits with status 3. A sha256 that is not equal gives exit 1.
#
# Steps:
#   1. Find the project in the S7 manifests and in the project_meta sidecars.
#   2. Check the tool sources: the ctp and cregit bundles of the run (sha256 and size of
#      tools.lock; an incremental cregit bundle also needs the bundle of its base commit,
#      column bundle_requires), or CTP_DIR and CREGIT_DIR. Check the final sidecar of the layer.
#   3. Find the published sha256 of the project file in data/SHA256SUMS.
#   4. Find the run record of the published file in data/REBUILD-TARGETS.tsv: the run commit
#      (the commit that the run checked out; the runs used --latest, so this is not column 6 of
#      the manifest), the cregit and ctp commits, and the three target sha256 values.
#   5. Run ctp for the project with the run commit, the run sidecar and the flags of the
#      dataset build.
#   6. Compare: the run output, the merge output, and the published file (rule a, b, c).
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
project=${1:-}
tools=${2:-$root/tools/bundles}
s7="$root/pipeline/s7-run"

notready() { echo "not ready: $*" >&2; exit 3; }
[ -n "$project" ] || { echo "usage: make rebuild-one PROJECT=<owner__repo>" >&2; exit 2; }
work=${WORK_DIR:-$root/work/rebuild-$project}
# An absolute path: step 5 runs ctp in "$work/ctp" with paths under "$work".
mkdir -p "$work" && work=$(cd "$work" && pwd)

# 1. Manifest rows (the run manifests, not the .order files) and the sidecar.
echo "== 1. inputs of $project"
rows=$(cd "$s7" && grep -l -P "^\Q$project\E\t" manifest.*.tsv 2>/dev/null | grep -v '\.order\.tsv$' || true)
[ -n "$rows" ] || notready "$project is in no manifest under pipeline/s7-run (check the name: <host>__<owner>__<repo> for hosts other than GitHub)"
echo "manifests: $(echo "$rows" | tr '\n' ' ')"
# The manifest row: name url category file_filter size_class commit.
first=$(echo "$rows" | head -n 1)
row=$(grep -P "^\Q$project\E\t" "$s7/$first" | head -n 1)
commit=$(echo "$row" | cut -f6)
echo "url: $(echo "$row" | cut -f2)  size_class: $(echo "$row" | cut -f5)  manifest commit: ${commit:-none}"
sidecars=$(cd "$s7" && grep -l -F "\"$project\"" project_meta.*.json 2>/dev/null || true)
[ -n "$sidecars" ] || notready "no project_meta sidecar under pipeline/s7-run names $project"
echo "sidecars: $(echo "$sidecars" | tr '\n' ' ')"

# 3 before 2: the published value and the run record name the tools.
echo "== 3. published sha256"
want=$( { grep -v "^#" "$root/data/SHA256SUMS" || true; } | awk -v p="$project-dataset.parquet" '{ n = split($2, a, "/"); if (a[n] == p) print $1 }' | head -n 1)
[ -n "$want" ] || notready "data/SHA256SUMS has no row for $project-dataset.parquet"
echo "published: $want"

echo "== 4. run record (data/REBUILD-TARGETS.tsv)"
# The unit separator keeps the empty cells (a tab is white space for read).
rec=$(grep -v '^#' "$root/data/REBUILD-TARGETS.tsv" | awk -F'\t' -v OFS='\037' -v p="$project" '$1 == p { $1 = $1; print }' | head -n 1)
[ -n "$rec" ] || notready "data/REBUILD-TARGETS.tsv has no row for $project"
IFS=$'\037' read -r _p layer run_record run_commit frame_commit cregit_commit ctp_commit \
  merge_input merge_sha pre_sha src_sha pub_sha run_sidecar entry_sha note <<< "$rec"
echo "layer $layer, run record $run_record, run commit $run_commit (frame $frame_commit)"
echo "cregit $cregit_commit, ctp $ctp_commit; merge input: $merge_input"
echo "targets: run output ${merge_sha:-none}, before the pseudonyms $pre_sha, source root $src_sha, published (TOM) $pub_sha"
[ "$pub_sha" = "$want" ] || { echo "FAIL: data/REBUILD-TARGETS.tsv and data/SHA256SUMS give other published values" >&2; exit 1; }
[ "$run_record" = proven ] || notready "the run record of $project matches by rows only ($note)"
[ "$merge_input" = run ] || notready "the merge input of $project is not the run output ($merge_input): this script does not run the trailer post-fix step yet (7,775 of the 8,449 files of TOM have merge input = run)"

echo "== 2. tool sources"
lock() { grep -v '^#' "$root/tools.lock" | awk -F'\t' -v t="$1" -v c="$2" '$1 == t && $3 == c' | head -n 1; }
check_bundle() {  # tool commit -> path of the checked bundle
  local r f bsha bbytes got size
  r=$(lock "$1" "$2"); [ -n "$r" ] || notready "tools.lock has no $1 row for $2"
  f=$(echo "$r" | cut -f4); bsha=$(echo "$r" | cut -f5); bbytes=$(echo "$r" | cut -f6)
  case "$f" in -|UNKNOWN|"") notready "tools.lock has no bundle for $1 $2" ;; esac
  [ -f "$tools/$f" ] || notready "$tools/$f is missing ($1 ${2:0:7}); put the bundle files of tools.lock in TOOLS_DIR"
  got=$(sha256sum < "$tools/$f" | cut -d' ' -f1); size=$(stat -L -c %s "$tools/$f")
  [ "$got" = "$bsha" ] && [ "$size" = "$bbytes" ] || notready "$tools/$f has sha256 $got and $size B, tools.lock gives $bsha and $bbytes B"
  echo "OK $f" >&2; echo "$tools/$f"
}
ctp_src=${CTP_DIR:-}; cregit_src=${CREGIT_DIR:-}; cregit_base=""
[ -n "$ctp_src" ] || ctp_src=$(check_bundle ctp "$ctp_commit")
if [ -z "$cregit_src" ]; then
  cregit_bundle=$(check_bundle cregit "$cregit_commit")
  # An incremental bundle (bundle_requires, column 7) needs its base commit first, as on the
  # run machines: clone the base bundle, then fetch the bundle of the run.
  req=$(lock cregit "$cregit_commit" | cut -f7)
  case "$req" in
    -|"") ;;
    *) cregit_base=$(check_bundle cregit "$req") ;;
  esac
fi
[ -x "$HOME/.nix-profile/bin/devenv" ] || notready "ctp runs each cregit step with $HOME/.nix-profile/bin/devenv; install it: nix profile add .#devenv"

# The final sidecar of the layer (step 6). Check it before the ctp run, which can take hours.
case "$layer" in
  v1) ms="$s7/project_meta.v1.final.json"; ms_want=4023295abc589a5eb0f4124e0aa76000402bd2492755e62f50af03121f661946 ;;
  x1k) ms="$root/pipeline/x1k/project_meta.x1k.final.json"; ms_want=1520c5f4d8909b3625c73bdea3cc08f23fced0a77f3722ec0809acd80de96f35 ;;
  *) notready "no merge sidecar for layer $layer" ;;
esac
ms=${MERGE_SIDECAR:-$ms}
[ -f "$ms" ] || notready "the final sidecar of layer $layer is not in this repository ($ms); set MERGE_SIDECAR"
[ "$(sha256sum < "$ms" | cut -d' ' -f1)" = "$ms_want" ] || notready "$ms does not have the sha256 of the final sidecar of layer $layer ($ms_want)"

echo "== 5. run ctp in $work"
mkdir -p "$work"
for d in ctp cregit out; do [ -e "$work/$d" ] && mv "$work/$d" "$work/$d.old.$(date +%s)"; done
git clone -q "$ctp_src" "$work/ctp"
git -C "$work/ctp" checkout -q "$ctp_commit"
[ "$(git -C "$work/ctp" rev-parse HEAD)" = "$ctp_commit" ] || { echo "FAIL: ctp is not at $ctp_commit" >&2; exit 1; }
if [ -n "$cregit_src" ]; then
  cp -a "$cregit_src" "$work/cregit"
  git -C "$work/cregit" rev-parse -q --verify HEAD > /dev/null ||
    notready "CREGIT_DIR is not a git tree (the script checks its commit)"
else
  if [ -n "$cregit_base" ]; then
    git clone -q "$cregit_base" "$work/cregit"
    git -C "$work/cregit" fetch -q "$cregit_bundle" '+refs/heads/*:refs/remotes/fed-bundle/*'
  else
    git clone -q "$cregit_bundle" "$work/cregit"
  fi
  git -C "$work/cregit" cat-file -e "$cregit_commit^{commit}" 2> /dev/null ||
    notready "the cregit bundles of tools.lock do not give the commit $cregit_commit"
  git -C "$work/cregit" checkout -q --detach "$cregit_commit"
  # The build of the run machines (pipeline/s7-run/runner/ec2-batch2/scripts/03-build.sh).
  (cd "$work/cregit" && "$HOME/.nix-profile/bin/devenv" shell -- bash -c \
    './run_pipeline_process.sh --build-only && make -C tokenize/srcMLtoken') > "$work/cregit-build.log" 2>&1 ||
    { tail -n 20 "$work/cregit-build.log" >&2; notready "the cregit build failed (log: $work/cregit-build.log)"; }
fi
[ "$(git -C "$work/cregit" rev-parse HEAD)" = "$cregit_commit" ] || { echo "FAIL: cregit is not at $cregit_commit" >&2; exit 1; }
jar="$work/cregit/blobExec/target/scala-2.13/blobExec-0.1.0-assembly.jar"
jar_want=$(lock blobexec-jar blobExec-0.1.0-assembly.jar | grep -o -E 'jar sha256 [0-9a-f]{64}' | cut -d' ' -f3 || true)
[ -f "$jar" ] || notready "the cregit tree has no blobExec jar"
jar_got=$(sha256sum < "$jar" | cut -d' ' -f1)
echo "blobExec jar: $jar_got ($([ "$jar_got" = "$jar_want" ] && echo "the value of tools.lock" || echo "NOT the value of tools.lock: $jar_want"))"

py=${CTP_PYTHON:-}
if [ -z "$py" ] && command -v python3.12 > /dev/null; then
  python3.12 -m venv "$work/venv" && "$work/venv/bin/pip" install -q --disable-pip-version-check duckdb==1.5.5 ||
    notready "no CTP_PYTHON, and no venv with python3.12 and duckdb 1.5.5"
  py="$work/venv/bin/python"
elif [ -z "$py" ] && [ -n "${CREGIT_PYTHON:-}" ]; then
  py=$CREGIT_PYTHON
  echo "note: ctp runs with CREGIT_PYTHON ($("$py" -c 'import sys; print(sys.version.split()[0])')); the runs used Python 3.12 (tools/ctp-venv/)"
fi
[ -n "$py" ] || notready "no CTP_PYTHON, no python3.12 and no CREGIT_PYTHON"
dv=$("$py" -c 'import duckdb; print(duckdb.__version__)' 2>/dev/null || true)
[ "$dv" = 1.5.5 ] || notready "the ctp Python has duckdb '${dv:-none}', the dataset build used 1.5.5"

# The run sidecar: ctp reads only the entry of the project. Take the sidecar under pipeline/s7-run
# whose entry has the sha256 of the entry of the run sidecar (run_meta_entry_sha256).
[ -n "$entry_sha" ] || notready "data/REBUILD-TARGETS.tsv has no entry sha256 for the run sidecar ($run_sidecar) of $project"
side=""
for s in $run_sidecar $sidecars; do
  [ -f "$s7/$s" ] || continue
  e=$("$py" -I -c 'import hashlib,json,sys; e=json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2]); print("" if e is None else hashlib.sha256(json.dumps(e, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest())' "$s7/$s" "$project")
  if [ "$e" = "$entry_sha" ]; then side=$s; break; fi
done
[ -n "$side" ] || notready "no sidecar under pipeline/s7-run has the entry of the run sidecar $run_sidecar for $project"
echo "run sidecar: $run_sidecar; used: $side (the same entry)"
printf '# Columns: name  url  category  file_filter  size_class  commit\n' > "$work/manifest.tsv"
echo "$row" | awk -F'\t' -v OFS='\t' -v c="$run_commit" '{ $6 = c; print }' >> "$work/manifest.tsv"
printf '# rebuild-one, scratch output.\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' "$work/cregit" "$work/out" > "$work/ctp.cfg"
mkdir -p "$work/out"
# The flags of the dataset build, without --latest (the manifest row has the run commit).
(cd "$work/ctp" && CTP_CONFIG="$work/ctp.cfg" "$py" ctp.py census --manifest "$work/manifest.tsv" \
  --project-meta "$s7/$side" --workers 1 --retries 0 --skip-html --tokenizer-worker \
  --blame-jobs 4 --memory-limit 6GB --min-free-mem-gb "${MIN_FREE_GB:-4}") > "$work/ctp.log" 2>&1 ||
  { grep -v '♥' "$work/ctp.log" | tail -n 20 >&2; echo "FAIL: the ctp run failed (log: $work/ctp.log)" >&2; exit 1; }
out="$work/out/$project/$project-dataset.parquet"
[ -f "$out" ] || { echo "FAIL: ctp wrote no $out" >&2; exit 1; }

echo "== 6. compare"
fail=0
got=$(sha256sum < "$out" | cut -d' ' -f1)
if [ "$got" = "$merge_sha" ]; then echo "OK   a. run output $got"; else echo "FAIL a. run output $got, want $merge_sha"; fail=1; fi
merged="$work/$project.merged.parquet"
PYTHONDONTWRITEBYTECODE=1 "$py" -I "$s7/rewrite_meta_columns.py" "$out" --sidecar "$ms" --key "$project" \
  --out "$merged" --encoding v1 --threads 2 --memory-limit 4GB > "$work/merge.log" 2>&1 ||
  { tail -n 5 "$work/merge.log" >&2; echo "FAIL: the merge step failed (log: $work/merge.log)" >&2; exit 1; }
got=$(sha256sum < "$merged" | cut -d' ' -f1)
if [ "$got" = "$pre_sha" ]; then echo "OK   b. merge output $got (the file before the pseudonyms)"; else echo "FAIL b. merge output $got, want $pre_sha"; fail=1; fi
pubf="${DATA_DIR:-$root/data/published}/parquet/$project-dataset.parquet"
if [ -f "$pubf" ]; then
  got=$(sha256sum < "$pubf" | cut -d' ' -f1)
  [ "$got" = "$want" ] || { echo "FAIL c. $pubf has sha256 $got, data/SHA256SUMS gives $want"; exit 1; }
  if "$py" -I "$root/scripts/compare_published.py" "$merged" "$pubf" > "$work/compare.txt"; then
    echo "OK   c. $(tail -n 1 "$work/compare.txt")"
  else
    grep '^FAIL' "$work/compare.txt"; fail=1
  fi
else
  echo "skip c. no published file at $pubf (download it, then run again with DATA_DIR=<release root>)"
fi
[ "$fail" -eq 0 ] && echo "OK: $project rebuilt; the files match the recorded sha256 values"
exit "$fail"
