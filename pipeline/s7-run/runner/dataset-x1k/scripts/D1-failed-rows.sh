#!/usr/bin/env bash
# D1-failed-rows.sh (machine B, read-only, through ssm.sh): name, failed step and log evidence of each
# row whose last final ledger row says failed. Also the finalize timer state and the finalize log tail.
# Use: I=<id> TAILN=400 bash scripts/ssm.sh scripts/D1-failed-rows.sh 300
set -uo pipefail
echo "== $(date -u +%FT%TZ) $(cat /etc/dataset-x1k/run 2>/dev/null) slot $(cat /etc/dataset-x1k/slot 2>/dev/null)"
for K in 1 2 3 4; do P=/data$K/x1k; C=$P/ctp
  python3 - "$C/ledger.jsonl" "$K" <<'PY' > /tmp/d1.p$K.txt
import json, sys
final, steps = {}, {}
for line in open(sys.argv[1]):
    try:
        r = json.loads(line)
    except ValueError:
        continue
    p = r.get("project")
    if not p:
        continue
    if r.get("step") == "project":
        final[p] = (r.get("state"), r.get("failed_step"), r.get("attempt"), r.get("start_utc"), r.get("end_utc"))
    elif r.get("status") in ("failed", "timeout", "killed"):
        steps.setdefault(p, []).append((r.get("attempt"), r.get("step"), r.get("status"), r.get("exit_code"), r.get("duration_s"), r.get("log")))
for p, f in final.items():
    if f[0] == "failed":
        print("FAILED", p, "failed_step=%s attempt=%s %s..%s" % (f[1], f[2], f[3], f[4]))
        for s in steps.get(p, [])[-4:]:
            print("  step-row attempt=%s step=%s status=%s rc=%s dur=%s log=%s" % s)
PY
  echo "--- p$K: unit $(systemctl is-active x1k@$K)"
  cat /tmp/d1.p$K.txt
  for p in $(awk '$1=="FAILED"{print $2}' /tmp/d1.p$K.txt); do
    L=$C/state/$p/logs
    echo "  logs: $(ls $L 2>/dev/null | tr '\n' ' ' | cut -c1-400)"
    last=$(ls -t $L/pipeline-*.log 2>/dev/null | head -1)
    if [ -n "$last" ]; then
      echo "  newest pipeline log $last ($(stat -c %s "$last") B)"
      grep -n -i -E 'no \.blame|no tokens|error|fatal|timed? ?out|killed|PLAIN-BLAME|memory|traceback|exception|^#+ *step|step [0-9]+' "$last" | grep -v -i 'Error \[0\]' | tail -25 | cut -c1-240
      echo "  tail:"; tail -8 "$last" | cut -c1-240
    fi
    for s in clone firm validate schema join; do
      lf=$(ls -t $L/$s-*.log 2>/dev/null | head -1)
      [ -n "$lf" ] && grep -q -i -E 'error|fatal|traceback' "$lf" && { echo "  $s log $lf:"; grep -i -E 'error|fatal|traceback' "$lf" | tail -5 | cut -c1-240; }
    done
    echo "  out: $(ls $P/out/$p 2>/dev/null | tr '\n' ' ' | cut -c1-300)"
    echo "  .blame in work: $(find $P -path "*$p*" -name '*.blame' 2>/dev/null | wc -l)"
    echo "  manifest row: $(grep -P "^$p\t" $P/manifest.run.tsv | cut -c1-300)"
  done
done
echo "--- timers"; systemctl is-active x1k-finalize.timer x1k-upload.timer x1k-live.timer x1k-watch 2>&1 | tr '\n' ' '; echo
systemctl list-timers --all --no-pager 2>/dev/null | grep x1k
echo "--- finalize log"; tail -6 /data/logs/x1k-finalize.log 2>/dev/null | cut -c1-200
[ -f /etc/dataset-x1k/final-DONE ] && { echo "final-DONE:"; cat /etc/dataset-x1k/final-DONE; }
[ -e /home/ec2-user/NO_SHUTDOWN ] && echo "NO_SHUTDOWN is set"
[ -e /run/x1k-hold ] && echo "/run/x1k-hold is set"
exit 0
