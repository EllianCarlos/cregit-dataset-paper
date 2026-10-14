#!/usr/bin/env bash
# gate.sh LINE: the libexpat identity gate for the blame time-limit commit, as census-local-a/scripts/gate.sh:
# a fresh scratch ctp clone at ca113e3, the cregit copy $G/LINE/cregit, the flags of census-fed-check.
set -uo pipefail
# CREGIT_PROJECTS: the directory that holds cregit-workspace and the clones of ctp and cregit.
# Default: the nearest parent directory of this script that holds cregit-workspace.
if [ -z "${CREGIT_PROJECTS:-}" ]; then
  CREGIT_PROJECTS=$(cd "$(dirname "$0")" && pwd)
  while [ "$CREGIT_PROJECTS" != / ] && [ ! -d "$CREGIT_PROJECTS/cregit-workspace" ]; do
    CREGIT_PROJECTS=$(dirname "$CREGIT_PROJECTS")
  done
fi
G=$CREGIT_PROJECTS/cregit-workspace/gate-blamelimit
line=${1:?line}; L=$G/$line
C=$L/ctp-check
[ -d $C ] && mv $C $C.old.$(date +%s)
git clone -q $CREGIT_PROJECTS/cregit-token-pipeline $C -b feat/e2e-runner
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0
printf '# libexpat gate, cregit copy %s, scratch output.\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' $L/cregit $L/cregit $L/out > $L/check.cfg
export CTP_CONFIG=$L/check.cfg
[ -d $L/out ] && mv $L/out $L/out.old.$(date +%s)
mkdir -p $L/out
echo "=== $(date -u +%FT%TZ) gate start (cregit $(git -C $L/cregit rev-parse --short HEAD), ctp $(git rev-parse --short HEAD))"
.venv/bin/python ctp.py census --manifest $L/manifest.libexpat.tsv --project-meta $L/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10
echo "census rc=$?"
P=$L/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet
echo "libexpat Parquet: $(sha256sum $P 2>/dev/null | cut -d' ' -f1) $(stat -c %s $P 2>/dev/null) bytes"
echo "PLAIN-BLAME lines in the pipeline logs: $(cat $C/state/libexpat__libexpat/logs/pipeline-*.log 2>/dev/null | grep -c '^PLAIN-BLAME')"
grep -h "Newly processed" $C/state/libexpat__libexpat/logs/pipeline-*.log 2>/dev/null
echo "=== $(date -u +%FT%TZ) gate end"
