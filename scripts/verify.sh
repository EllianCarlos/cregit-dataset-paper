#!/usr/bin/env bash
# verify.sh: check the sha256 of each published file against data/SHA256SUMS.
#
# Usage: scripts/verify.sh DATA_DIR
#   DATA_DIR is the directory of the downloaded published files.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
sums="$root/data/SHA256SUMS"
dir=${1:-}

rows=$(grep -v -E '^[[:space:]]*(#|$)' "$sums" || true)
if [ -z "$rows" ]; then
  echo "not ready: data/SHA256SUMS has no rows (it must hold the project rows of the release root)" >&2
  exit 3
fi
if [ -z "$dir" ] || [ ! -d "$dir" ]; then
  echo "not ready: DATA_DIR='$dir' is not a directory (download the published files first)" >&2
  exit 3
fi
cd "$dir"
echo "$rows" | sha256sum --check --strict -
echo "OK: $(echo "$rows" | wc -l) files match data/SHA256SUMS"
