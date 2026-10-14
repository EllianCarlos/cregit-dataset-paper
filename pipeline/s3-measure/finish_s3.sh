#!/usr/bin/env bash
# Finish S3 (2026-10-06). 1) Clone pass. 2) Clone facts. 3) Wait for the tree
# pass to end. 4) Clone pass again, for the truncated trees that the tree pass
# found after step 1 started. 5) Clone facts again. Each step is resumable.
# Clones go to disk: /tmp on this machine is a RAM disk (tmpfs, 16 GB).
set -u
cd "$(dirname "$0")"
export TMPDIR="$HOME/s3-work"
mkdir -p "$TMPDIR"
nice -n 10 python3 measure_clones.py
nice -n 10 python3 clone_facts.py
while ps -eo args | awk '$1=="python3" && $2=="measure_trees.py" {f=1} END {exit !f}'; do sleep 60; done
nice -n 10 python3 measure_clones.py
nice -n 10 python3 clone_facts.py
echo "finish_s3 end $(date -u +%FT%TZ)"
