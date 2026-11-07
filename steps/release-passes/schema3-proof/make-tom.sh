#!/usr/bin/env bash
# Make the TOM pass output of each given schema 2 release file, as the release kit
# does (../pass-1/tom.conf: drop 10 columns, rename one, set
# ctp_schema_version=3), with parquet_rename.py of ctp 467677c, then check it.
#   bash make-tom.sh OUTDIR FILE [FILE ...]
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
export LD_LIBRARY_PATH=/nix/store/0ba5kj6r0zhfwd84l5vzccqvx7amlq2c-gcc-15.3.0-lib/lib:/nix/store/2kdz3m7ic8w226pcvkz1dlg169v91p6a-zlib-1.3.2/lib
PY=(uv run -q --no-project --with pyarrow --with duckdb==1.5.5 python -I -B)
out=$1; shift
ARGS=()
for c in size_kb file_mask manifest_category fact history_cluster history_shared_with \
         history_relation history_includes history_first history_created; do ARGS+=(--drop "$c"); done
ARGS+=(--rename provenance_status=audit_frame_file --set-kv ctp_schema_version=3)
for src in "$@"; do
  dst=$out/$(basename "$src")
  "${PY[@]}" "$H/parquet_rename.py" "$src" "$dst" "${ARGS[@]}" --copy read-write > /dev/null
  "${PY[@]}" "$H/parquet_rename_check.py" "${ARGS[@]}" "$src" "$dst" | tail -1 | cut -c1-200
done
