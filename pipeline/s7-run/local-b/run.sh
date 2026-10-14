#!/usr/bin/env bash
# run.sh: census-local-b (systemd user unit census-local-b). The rerun of one project of batch11 a4,
# gitlab.eclipse.org__eclipse__objectteams__objectteams (all 4 spot attempts failed at resolve on
# 2026-10-12 00:53 UTC). Code: ctp ca113e3, cregit 57551d7 (the code of the batch 11 spot parts).
# Flags of local-a/run.sh, except 1 worker: --memory-limit 6GB (the spots use 16GB; the memory budget
# of this machine is 14 GB), --min-free-mem-gb 8, --disk-floor-gb 300.
# Beside the census, publish_done.py copies the finished project to batch11/a4/done/<name>/ every
# 60 s, and once more at the end. Stop after the running project: touch /home/ellianco/Projects/cregit-workspace/census-local-b/ctp/STOP.
set -uo pipefail
L=/home/ellianco/Projects/cregit-workspace/census-local-b
export CTP_CONFIG=$L/census.cfg
cd $L/ctp
echo "=== $(date -u +%FT%TZ) census-local-b start on $(hostname) (cregit $(git -C $L/cregit rev-parse --short HEAD), ctp $(git rev-parse --short HEAD), $(grep -c -v -e '^#' -e '^[[:space:]]*$' $L/manifest.local-b.tsv) projects, parts: $(tr '\n' ' ' < $L/parts.taken))"
( while sleep 60; do python3 -I $L/scripts/publish_done.py $L >> $L/logs/publish.log 2>&1; done ) &
pub=$!
.venv/bin/python ctp.py census --manifest $L/manifest.local-b.tsv --project-meta $L/project_meta.local-b.json \
    --workers 1 --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 6GB --min-free-mem-gb 8 --disk-floor-gb 300
rc=$?
kill $pub 2>/dev/null; wait $pub 2>/dev/null
python3 -I $L/scripts/publish_done.py $L >> $L/logs/publish.log 2>&1
echo "=== $(date -u +%FT%TZ) census-local-b end: census rc=$rc; done/OK: $(find $L/batch11 -path '*/done/*' -name OK 2>/dev/null | wc -l)"
exit $rc
