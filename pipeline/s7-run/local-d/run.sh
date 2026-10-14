#!/usr/bin/env bash
# run.sh: census-local-d (systemd user unit census-local-d). The rerun of one project of batch25 a4,
# gitlab.inria.fr__cedar__connectionlens: all 4 spot attempts (cregit 57551d7) failed in blame, because
# git -C100 exits 128 ("unable to generate diff") on a moved blob over 1 GiB. User decision
# 2026-10-14 ~14:35 UTC: rerun with the fix. Code: ctp ca113e3, cregit 23e4ccb (57551d7 + plain blame
# after a -C100 git exit 128, branch fix/blame-exit128-fallback; libexpat gate 14eb5d72 OK).
# Flags of the fed parts, except the memory flags of this machine (30 GB RAM; the spots use
# --memory-limit 16GB --min-free-mem-gb 24): --memory-limit 6GB --min-free-mem-gb 8, as census-local-b.
# Beside the census, publish_done.py copies the finished project to batch25/a4/done/<name>/ every
# 60 s, and once more at the end. Stop after the running project: touch $CREGIT_PROJECTS/cregit-workspace/census-local-d/ctp/STOP.
set -uo pipefail
# CREGIT_PROJECTS: the directory that holds cregit-workspace and the clones of ctp and cregit.
# Default: the nearest parent directory of this script that holds cregit-workspace.
if [ -z "${CREGIT_PROJECTS:-}" ]; then
  CREGIT_PROJECTS=$(cd "$(dirname "$0")" && pwd)
  while [ "$CREGIT_PROJECTS" != / ] && [ ! -d "$CREGIT_PROJECTS/cregit-workspace" ]; do
    CREGIT_PROJECTS=$(dirname "$CREGIT_PROJECTS")
  done
fi
L=$CREGIT_PROJECTS/cregit-workspace/census-local-d
export CTP_CONFIG=$L/census.cfg
cd $L/ctp
echo "=== $(date -u +%FT%TZ) census-local-d start on $(hostname) (cregit $(git -C $L/cregit rev-parse --short HEAD), ctp $(git rev-parse --short HEAD), $(grep -c -v -e '^#' -e '^[[:space:]]*$' $L/manifest.local-d.tsv) projects, parts: $(tr '\n' ' ' < $L/parts.taken))"
( while sleep 60; do python3 -I $L/scripts/publish_done.py $L >> $L/logs/publish.log 2>&1; done ) &
pub=$!
.venv/bin/python ctp.py census --manifest $L/manifest.local-d.tsv --project-meta $L/project_meta.local-d.json \
    --workers 1 --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 6GB --min-free-mem-gb 8 --disk-floor-gb 300
rc=$?
kill $pub 2>/dev/null; wait $pub 2>/dev/null
python3 -I $L/scripts/publish_done.py $L >> $L/logs/publish.log 2>&1
echo "=== $(date -u +%FT%TZ) census-local-d end: census rc=$rc; done/OK: $(find $L/batch25 -path '*/done/*' -name OK 2>/dev/null | wc -l)"
exit $rc
