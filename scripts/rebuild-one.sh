#!/usr/bin/env bash
# rebuild-one.sh: build the dataset again for one project, and compare the sha256 of the new
# Parquet file with the published value.
#
# Usage: scripts/rebuild-one.sh PROJECT [TOOLS_DIR]
#   PROJECT    the manifest name, for example libexpat__libexpat or gitlab.com__muttmua__mutt.
#   TOOLS_DIR  the directory of the tool bundles of tools.lock (default: tools/bundles).
#
# The script checks the inputs step by step. At the first step that is not ready, it prints
# "not ready: <reason>" and exits with status 3. It never changes a file outside WORK_DIR.
#
# Steps:
#   1. Find the project in the S7 manifests and in the project_meta sidecars.
#   2. Check the tool bundles in TOOLS_DIR against tools.lock (sha256 and size).
#   3. Find the published sha256 of the project Parquet file in data/SHA256SUMS.
#   4. Find the tool versions of the published file (the per-project ledger).
#   5. Run ctp for the project with the pinned commit (column 6 of the manifest row, no
#      --latest), with the flags of the dataset build.
#   6. Compare the sha256.
# Steps 4 and 5 are not written yet. REPRODUCE.md says why.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
project=${1:-}
tools=${2:-$root/tools/bundles}
s7="$root/pipeline/s7-run"

notready() { echo "not ready: $*" >&2; exit 3; }
[ -n "$project" ] || { echo "usage: make rebuild-one PROJECT=<owner__repo>" >&2; exit 2; }

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

# 2. Tool bundles.
echo "== 2. tool bundles in $tools"
[ -d "$tools" ] || notready "TOOLS_DIR=$tools is missing; put the bundle files of tools.lock there (they are not published yet)"
missing=0
while IFS=$'\t' read -r tool repo tcommit bfile bsha bbytes _rest; do
  case "$bfile" in -|UNKNOWN) continue ;; esac
  f="$tools/$bfile"
  if [ ! -f "$f" ]; then echo "MISSING $bfile ($tool ${tcommit:0:7})"; missing=1; continue; fi
  got=$(sha256sum < "$f" | cut -d' ' -f1); size=$(stat -L -c %s "$f")
  if [ "$got" = "$bsha" ] && [ "$size" = "$bbytes" ]; then echo "OK $bfile"; else echo "BAD $bfile (sha256 $got, $size B)"; missing=1; fi
done < <(grep -v '^#' "$root/tools.lock" | tail -n +2)
[ "$missing" -eq 0 ] || notready "one or more bundles of tools.lock are missing or have a wrong sha256"

# 3. Published sha256.
echo "== 3. published sha256"
want=$( { grep -v "^#" "$root/data/SHA256SUMS" || true; } | awk -v p="$project-dataset.parquet" '{ n = split($2, a, "/"); if (a[n] == p) print $1 }' | head -n 1)
[ -n "$want" ] || notready "data/SHA256SUMS has no row for $project-dataset.parquet (it gets filled at the v1 freeze)"
echo "published: $want"

# 4 and 5.
notready "steps 4 and 5 are not written: the per-project ledger (the cregit commit and the pinned commit of the published file) is not in this repository, and ctp runs each cregit step through a devenv command at a fixed path"
