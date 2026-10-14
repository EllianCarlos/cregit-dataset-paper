set -uo pipefail
for p in batch6a1 batch6a4 batch7a1 batch7a3; do echo "== $p"; for d in /w/$p/census-2026-10-*/*/; do n=$(basename $d); [ -f $d/pipeline.log ] || continue; st=$(grep -o "Step [0-9]* — [a-z0-9 ()-]*" $d/pipeline.log | tail -1); echo "$n | $st | log age $(( $(date +%s) - $(stat -c %Y $d/pipeline.log) ))s"; done; done
ps -eo etimes,pcpu,args --sort=-pcpu | grep -E "git (blame|gc|repack|pack-objects)|java|duckdb" | grep -v grep | head -12 | cut -c1-200
