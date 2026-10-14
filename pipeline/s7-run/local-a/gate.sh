#!/usr/bin/env bash
# gate.sh: the libexpat identity gate of census-local-a, as census-fed-check on the spots:
# a fresh scratch ctp clone at ca113e3, the cregit copy $CREGIT_PROJECTS/cregit-workspace/census-local-a/cregit, flags of the spot check.
set -uo pipefail
# CREGIT_PROJECTS: the directory that holds cregit-workspace and the clones of ctp and cregit.
# Default: the nearest parent directory of this script that holds cregit-workspace.
if [ -z "${CREGIT_PROJECTS:-}" ]; then
  CREGIT_PROJECTS=$(cd "$(dirname "$0")" && pwd)
  while [ "$CREGIT_PROJECTS" != / ] && [ ! -d "$CREGIT_PROJECTS/cregit-workspace" ]; do
    CREGIT_PROJECTS=$(dirname "$CREGIT_PROJECTS")
  done
fi
L=$CREGIT_PROJECTS/cregit-workspace/census-local-a
C=$L/gate/ctp-check
[ -d $C ] && mv $C $C.old.$(date +%s)
git clone -q $CREGIT_PROJECTS/cregit-token-pipeline $C -b feat/e2e-runner
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0
export CTP_CONFIG=$L/gate/check.cfg
[ -d $L/gate/out ] && mv $L/gate/out $L/gate/out.old.$(date +%s)
mkdir -p $L/gate/out
echo "=== $(date -u +%FT%TZ) gate start (cregit $(git -C $L/cregit rev-parse --short HEAD), ctp $(git rev-parse --short HEAD))"
.venv/bin/python ctp.py census --manifest $L/gate/manifest.libexpat.tsv --project-meta $L/gate/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10
echo "census rc=$?"
P=$L/gate/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet
echo "libexpat Parquet: $(sha256sum $P 2>/dev/null | cut -d' ' -f1) $(stat -c %s $P 2>/dev/null) bytes"
echo "=== $(date -u +%FT%TZ) gate end"
