#!/usr/bin/env bash
# D3-running.sh (machine B, read-only, through ssm.sh): for each active part, the running project, the
# step headings and the last lines of its newest pipeline log, and its .blame count and size.
# Use: I=<id> TAILN=120 bash scripts/ssm.sh scripts/D3-running.sh 300
set -uo pipefail
echo "== $(date -u +%FT%TZ) $(cat /etc/dataset-x1k/run 2>/dev/null)"
for K in 1 2 3 4; do P=/data$K/x1k
  systemctl is-active -q x1k@$K || continue
  p=$(tail -1 $P/logs/run.log | sed -n 's/.*running: \([^ (]*\)(.*/\1/p')
  echo "--- p$K running $p"
  [ -n "$p" ] || continue
  last=$(ls -t $P/ctp/state/$p/logs/pipeline-2*.log 2>/dev/null | head -1)
  echo "  log $last, attempts $(ls $P/ctp/state/$p/logs/pipeline-2*.log 2>/dev/null | wc -l)"
  grep -n -E 'Step [0-9]+ —|completed in|PLAIN-BLAME|Newly processed' "$last" | tail -14 | cut -c1-200
  echo "  tail:"; tail -c 2000 "$last" | tr '\r' '\n' | tail -4 | cut -c1-200
  w=$P/out/$p
  echo "  .blame done: $(find $w -name '*.blame' 2>/dev/null | wc -l); tmpfile-* $(ls $P/cregit-ec2/blameRepo/build/ 2>/dev/null | grep -c tmpfile); out size $(du -sh $w 2>/dev/null | cut -f1)"
  echo "  manifest row: $(grep -P "^$p\t" $P/manifest.run.tsv | cut -c1-200)"
  echo "  git blame processes: $(ps -eo args | grep -c '^git .*blame')"
done
exit 0
