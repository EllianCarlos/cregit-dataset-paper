#!/usr/bin/env bash
# Full run, resume-safe: projects whose last line in measure.jsonl is final are skipped.
# Stop softly: touch "$TOKEI_WORK/STOP" (running projects finish, no new ones start).
cd "$(dirname "$0")"
export PATH=/nix/var/nix/profiles/default/bin:$PATH TMPDIR=/tmp
exec nice -n 10 ionice -c2 -n7 python3 -I measure.py run --all --workers 8 --sample-every 60 >> run.log 2>&1
