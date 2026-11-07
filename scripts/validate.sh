#!/usr/bin/env bash
# validate.sh: check the column contract and the footer of each published project file.
#
# Usage: scripts/validate.sh DATA_DIR
# DATA_DIR is the release root (parquet/<project>-dataset.parquet, MANIFEST.tsv, organizations/).
# The files of TOM 1.0.0 are ctp schema 3 (53 columns). The check is the release tool
# fill_release.py check (steps/release-passes/fill-release/tools/fill_release.py, the same file
# as tools/fill_release.py of the root): the 53 columns, the footer keys, the organization
# tables, MANIFEST.tsv, the text rules.
# SCHEMA=2 checks the source root of the release passes (ctp schema 2, 71 columns) with
# scripts/validate_schema2.py: the 67 cregit columns of the ctp ca113e3 contract
# (tools/ctp/validate_schema.py, unchanged), then the 4 organization columns, the footer keys,
# the registry of each file, and the rows of MANIFEST.tsv.
# It needs the dev shell (CREGIT_PYTHON, with duckdb 1.5.5).
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
dir=${1:-}
py=${CREGIT_PYTHON:-}
[ -n "$py" ] || { echo "not ready: CREGIT_PYTHON is not set (run in the dev shell: nix develop)" >&2; exit 3; }
if [ -z "$dir" ] || [ ! -d "$dir" ]; then
  echo "not ready: DATA_DIR='$dir' is not a directory (download the published files first)" >&2
  exit 3
fi
[ -d "$dir/parquet" ] || { echo "not ready: no parquet/ folder under $dir (DATA_DIR is the release root)" >&2; exit 3; }
if [ "${SCHEMA:-3}" = 2 ]; then
  "$py" -I "$root/scripts/validate_schema2.py" "$dir" --jobs "${JOBS:-8}"
else
  "$py" -I "$root/steps/release-passes/fill-release/tools/fill_release.py" check --root "$dir"
fi
