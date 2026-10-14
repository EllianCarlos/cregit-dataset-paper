#!/usr/bin/env bash
# Census batch 1: the first 5% of layer 1 (164 projects, >= 5,000 commits), in
# u order. Start it only with the user's agreement. To stop after the running
# projects: touch STOP in the pipeline repository. To resume: run this again.
# --disk-floor-gb 500: one L workdir (Linux) took 435 GB on 2026-09-15.
# --latest (decided 2026-10-07): each project runs at the head of its default
# branch when its first attempt starts. The manifest commit is the S2 snapshot;
# the ledger records both (pinned_sha, snapshot_sha).
# --tokenizer-worker and --retries 2 (decided 2026-10-07 16:40 UTC): step 2 uses the
# runner's worker pool; 2 retries, because Linux and mongodb used one retry in
# runs that were stopped on purpose.
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
CTP=${CTP:-$HOME/Projects/cregit-token-pipeline/.claude/worktrees/agent-a0a3254f563a6a4b5}
export CTP_CONFIG="$here/census.cfg"
cd "$CTP"
exec .venv/bin/python ctp.py census --manifest "$here/manifest.batch1.tsv" \
    --project-meta "$here/project_meta.batch1.json" \
    --workers "${WORKERS:-3}" --retries "${RETRIES:-2}" --skip-html --latest --tokenizer-worker \
    --min-free-mem-gb 8 --disk-floor-gb 500
