#!/usr/bin/env bash
# D5-progress.sh, machine A (read-only, through scripts/a/ssm-a.sh): per active row, the step-7 work done
# and left by count and by bytes (the mask files of the cregit working clone, ls-files, the mask of
# the ledger manifest_row; done = a .blame file exists), the start of the newest attempt, PLAIN-BLAME lines of the
# newest attempt, running git blame processes; for a row past step 7, the tail of pipeline.log.
# Use: I=<id> TAILN=120 bash scripts/a/ssm-a.sh scripts/a/D5-progress.sh 600
set -uo pipefail
L=/data/x1k-long
echo "== $(date -u +%FT%TZ) up $(awk '{printf "%.2f h", $1/3600}' /proc/uptime); $(cat $L/started)"
for p in $(cat $L/run.list); do R=$(readlink -f $L/$p)
  systemctl is-active -q x1k-long@$p || continue
  O=$R/out/$p; W=$O/$p-cregit; PL=$O/pipeline.log
  echo "--- $p"
  echo "  start line: $(grep -a '=== .* x1k-long' $R/logs/run.log | tail -1 | cut -c1-200)"
  st=$(grep -a -n -E 'Step [0-9]+ —' $PL | tail -1)
  echo "  newest step heading: $st"
  if [ -d "$W" ] && [ -d "$O/blame" ]; then
    mask=$(python3 -c '
import json, sys
m = ""
for line in open(sys.argv[1]):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    mr = r.get("manifest_row")
    if isinstance(mr, dict) and mr.get("file_filter"):
        m = mr["file_filter"]
print(m)' $R/ctp/ledger.jsonl)
    echo "  mask (ledger manifest_row): $mask"
    sudo -u ec2-user git -C "$W" ls-files | python3 -c '
import os, re, sys, time
w, b, mask = sys.argv[1], sys.argv[2], sys.argv[3]
rx = re.compile(mask) if mask else None
n = nd = 0; by = byd = 0; t0 = None
for line in sys.stdin:
    f = line.rstrip("\n")
    if rx and not rx.search(f):
        continue
    try:
        s = os.path.getsize(os.path.join(w, f))
    except OSError:
        continue
    n += 1; by += s
    if os.path.exists(os.path.join(b, f + ".blame")):
        nd += 1; byd += s
print("  mask files %d, .blame done %d (%.1f%%); bytes %.1f MB, done %.1f MB (%.1f%%), left %.1f MB in %d files"
      % (n, nd, 100.0 * nd / max(n, 1), by / 1e6, byd / 1e6, 100.0 * byd / max(by, 1), (by - byd) / 1e6, n - nd))
' "$W" "$O/blame" "$mask"
  fi
  a=$(grep -a -n -E 'Step 7 —' $PL | tail -1 | cut -d: -f1)
  [ -n "$a" ] && echo "  PLAIN-BLAME lines after the newest step-7 heading: $(tail -n +$a $PL | grep -a -c PLAIN-BLAME); in the whole pipeline.log: $(grep -a -c PLAIN-BLAME $PL)"
  echo "  pipeline.log tail: $(tail -c 600 $PL | tr '\r' '\n' | grep -a -v '^$' | tail -2 | cut -c1-200 | tr '\n' '|')"
done
echo "--- running git blame processes per volume (elapsed s, top 3)"
for K in 1 2 3 4; do
  ps -eo etimes,args | awk -v k="/data$K/" '$2=="git" && $0 ~ "blame" && $0 ~ k {print $1}' | sort -rn | head -3 | tr '\n' ' ' | sed "s/^/  \/data$K: /"; echo " (n=$(ps -eo args | awk -v k="/data$K/" '$1=="git" && $0 ~ "blame" && $0 ~ k' | wc -l))"
done
free -g | sed -n 2p; uptime
exit 0
