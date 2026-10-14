#!/usr/bin/env bash
# run.sh: census-local-a (systemd user unit census-local-a). The S projects of the parts in
# parts.taken, taken from the end of spot a's queue on 2026-10-11, with the code of the spot parts
# (ctp ca113e3, cregit 1f17663) and the flags of census-fed-run, except: 2 workers,
# --min-free-mem-gb 8, --memory-limit 6GB (the memory budget of this machine), --disk-floor-gb 300.
# Beside the census, publish_done.py copies each finished project to <wl>/<part>/done/<name>/ every
# 60 s, and once more at the end. Stop after the running projects: touch /home/ellianco/Projects/cregit-workspace/census-local-a/ctp/STOP.
set -uo pipefail
L=/home/ellianco/Projects/cregit-workspace/census-local-a
export CTP_CONFIG=$L/census.cfg
cd $L/ctp
echo "=== $(date -u +%FT%TZ) census-local-a start on $(hostname) (cregit $(git -C $L/cregit rev-parse --short HEAD), ctp $(git rev-parse --short HEAD), $(grep -c -v -e '^#' -e '^[[:space:]]*$' $L/manifest.local-a.tsv) projects, parts: $(tr '\n' ' ' < $L/parts.taken))"
( while sleep 60; do python3 -I $L/scripts/publish_done.py $L >> $L/logs/publish.log 2>&1; done ) &
pub=$!
.venv/bin/python ctp.py census --manifest $L/manifest.local-a.tsv --project-meta $L/project_meta.local-a.json \
    --workers 2 --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 6GB --min-free-mem-gb 8 --disk-floor-gb 300
rc=$?
kill $pub 2>/dev/null; wait $pub 2>/dev/null
python3 -I $L/scripts/publish_done.py $L >> $L/logs/publish.log 2>&1
echo "=== $(date -u +%FT%TZ) census-local-a end: census rc=$rc; done/OK: $(find $L/batch2? -path '*/done/*' -name OK 2>/dev/null | wc -l)"
exit $rc
