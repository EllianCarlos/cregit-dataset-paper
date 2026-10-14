#!/usr/bin/env bash
# run.sh: census-local-c (systemd user unit census-local-c). The rerun of 49 of the 51 batch 1
# projects that finished locally on 2026-10-07..09 with old code (cregit 157cf8b, old srcML, no
# trailer fix). torvalds__linux and SAP__project-foxhound wait for a user decision. Code: ctp
# ca113e3, cregit 57551d7 (the code of the batch 11 spot parts and of census-local-b).
# Flags of local-a/run.sh: 2 workers, --memory-limit 6GB (the spots use 16GB; the memory budget of
# this machine is 14 GB), --min-free-mem-gb 8, --disk-floor-gb 300. --latest pins today's head.
# The manifest is in LPT order (longest old duration first).
# Beside the census, publish_done.py copies each finished project to batch1/done/<name>/ every
# 60 s, and once more at the end. The old outputs in census-2026-10/ do not change.
# Stop after the running projects: touch /home/ellianco/Projects/cregit-workspace/census-local-c/ctp/STOP.
set -uo pipefail
L=/home/ellianco/Projects/cregit-workspace/census-local-c
export CTP_CONFIG=$L/census.cfg
cd $L/ctp
echo "=== $(date -u +%FT%TZ) census-local-c start on $(hostname) (cregit $(git -C $L/cregit rev-parse --short HEAD), ctp $(git rev-parse --short HEAD), $(grep -c -v -e '^#' -e '^[[:space:]]*$' $L/manifest.local-c.tsv) projects, parts: $(tr '\n' ' ' < $L/parts.taken))"
( while sleep 60; do python3 -I $L/scripts/publish_done.py $L >> $L/logs/publish.log 2>&1; done ) &
pub=$!
.venv/bin/python ctp.py census --manifest $L/manifest.local-c.tsv --project-meta $L/project_meta.local-c.json \
    --workers 2 --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 6GB --min-free-mem-gb 8 --disk-floor-gb 300
rc=$?
kill $pub 2>/dev/null; wait $pub 2>/dev/null
python3 -I $L/scripts/publish_done.py $L >> $L/logs/publish.log 2>&1
echo "=== $(date -u +%FT%TZ) census-local-c end: census rc=$rc; done/OK: $(find $L/batch1 -path '*/done/*' -name OK 2>/dev/null | wc -l)"
exit $rc
