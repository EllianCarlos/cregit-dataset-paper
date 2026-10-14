#!/usr/bin/env bash
# validate.sh: check the column contract of each published Parquet file.
#
# Usage: scripts/validate.sh DATA_DIR
# It runs tools/ctp/validate_schema.py (the 70-column contract of ctp ca113e3: the names,
# the types and the order) on each *-dataset.parquet file under DATA_DIR.
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
files=$(find "$dir" -name '*-dataset.parquet' | LC_ALL=C sort)
[ -n "$files" ] || { echo "not ready: no *-dataset.parquet file under $dir" >&2; exit 3; }
echo "$files" | xargs -d '\n' "$py" -I "$root/tools/ctp/validate_schema.py"
echo "OK: $(echo "$files" | wc -l) files have the 70-column contract"
