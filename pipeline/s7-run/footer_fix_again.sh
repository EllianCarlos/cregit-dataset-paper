#!/usr/bin/env bash
# Start the trailer post-fix (footer-fix) again for new arrivals. The transient user timer
# footer-fix-again runs this every 2 h at :20 (after the census-fetch passes at :05 and :35).
#  1. footer-fix is active, or OUT/STOP exists: do nothing.
#  2. Fetch the run ledgers of the big EC2 runs from S3 (read only) into run-ledgers/latest,
#     then split_run_ledgers.py writes ledger.from-run.jsonl and pin.from-run.json.
#  3. footer_fix_batches.py --pending exits 0 (every project of the 95cdc88 runs is settled):
#     stop the timer. Else start footer-fix with --retry-transient (not the refused ones).
# Log: census-cloud-fixed/footer-fix-again.log. Stop by hand:
#   systemctl --user stop footer-fix-again.timer
set -u
PY=${FOOTER_FIX_PY:-/nix/store/5gnikzfb2hkysq9d45mjl74h7vj4c5ad-python3-3.14.7-env/bin/python3}
HERE=$(cd "$(dirname "$0")" && pwd)
WS="$HOME/Projects/cregit-workspace"
OUT="$WS/census-cloud-fixed"
LOG="$OUT/footer-fix-again.log"
log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

if systemctl --user is-active --quiet footer-fix; then log "footer-fix is active; nothing to do"; exit 0; fi
if [ -e "$OUT/STOP" ]; then log "STOP exists; nothing to do"; exit 0; fi

export AWS_PROFILE=ellianco-personal AWS_REGION=us-west-2 AWS_PAGER=""
B=s3://cregit-census-905418043997-usw2
D="$WS/run-ledgers/latest"
for k in batch2/live/ledger.jsonl batch3L/live/ledger.jsonl batch4/live/ledger.p1.jsonl \
         batch4/live/ledger.p2.jsonl batch4/live/ledger.p3.jsonl batch5L/live/ledger.jsonl \
         batch6L/live/ledger.jsonl; do
  mkdir -p "$(dirname "$D/$k")"
  if aws s3 cp --only-show-errors "$B/$k" "$D/$k.new" 2>> "$LOG"; then mv "$D/$k.new" "$D/$k"
  else log "ledger $k not fetched; the older copy stays"; fi
done
"$PY" -I "$HERE/split_run_ledgers.py" >> "$LOG" 2>&1 || log "split_run_ledgers.py failed"

if "$PY" -I "$HERE/footer_fix_batches.py" --pending > "$OUT/pending.txt" 2>> "$LOG"; then
  log "every project is settled; stopping the timer"
  systemctl --user stop footer-fix-again.timer
  exit 0
fi
log "$(tail -n 1 "$OUT/pending.txt"); starting footer-fix"
systemctl --user reset-failed footer-fix 2>/dev/null
systemd-run --user --unit=footer-fix -p OOMPolicy=continue -p MemoryMax=12G \
  -p StandardOutput=append:"$OUT/footer-fix.log" -p StandardError=append:"$OUT/footer-fix.log" \
  --working-directory="$OUT" --setenv=HOME="$HOME" --setenv=PATH="$PATH" \
  "$PY" -I "$HERE/footer_fix_batches.py" --jobs 2 --retry-transient >> "$LOG" 2>&1 \
  || log "systemd-run failed"
