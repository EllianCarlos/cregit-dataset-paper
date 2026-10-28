#!/usr/bin/env bash
# validate.sh: check the column contract and the footer of each published project file.
#
# Usage: scripts/validate.sh DATA_DIR
# DATA_DIR is the release root (parquet/<project>-dataset.parquet, pseudonymization.json,
# MANIFEST.tsv). The published files are ctp schema 2 (71 columns): the 67 cregit columns of
# the ctp ca113e3 contract (tools/ctp/validate_schema.py, unchanged), then the 4 organisation
# columns. scripts/validate_schema2.py does the check: the names, the types and the order, the
# footer keys, the registry of each file, and the rows of MANIFEST.tsv.
# The 70-column contract of ca113e3 alone refuses every published file: the release write
# replaced its 3 firm columns with the 4 organisation columns.
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
"$py" -I "$root/scripts/validate_schema2.py" "$dir" --jobs "${JOBS:-8}"
