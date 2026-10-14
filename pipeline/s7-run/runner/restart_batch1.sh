#!/usr/bin/env bash
# One-off (2026-10-07): restart batch 1 with --latest after the census that STOP
# ends has exited.
set -euo pipefail
S=${RUNNER_PROJECTS}/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection/s7-run
W=${RUNNER_PROJECTS}/cregit-token-pipeline/.claude/worktrees/agent-a0a3254f563a6a4b5
echo "$(date -u +%FT%TZ) waiting for census 326357 to exit"
while kill -0 326357 2>/dev/null; do sleep 30; done
grep -q -- "--latest" "$S/run_batch1.sh"
rm "$W/STOP"
echo "$(date -u +%FT%TZ) census exited, STOP removed; starting batch 1 with --latest"
cd "$S" && WORKERS=2 setsid nohup ./run_batch1.sh >> batch1.log 2>&1 < /dev/null &
sleep 5; echo "$(date -u +%FT%TZ) started: $(pgrep -f 'ctp.py census' | tr '\n' ' ')"
