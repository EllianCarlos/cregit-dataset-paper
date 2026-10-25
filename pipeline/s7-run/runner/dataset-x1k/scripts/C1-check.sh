#!/usr/bin/env bash
# C1-check.sh (the x1k instance, read-only, through ssm.sh): progress of the x1k test run.
# Local use: I=<instance id> TAILN=80 bash ~/s3-work/dataset-x1k/scripts/ssm.sh ~/s3-work/dataset-x1k/scripts/C1-check.sh 300
# Quick look without SSM: aws s3 cp s3://${RUNNER_BUCKET}/dataset-x1k/live/progress.txt -
set -uo pipefail
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag) up $(awk '{printf "%.1f h", $1/3600}' /proc/uptime); $(cat /etc/dataset-x1k/started 2>/dev/null || echo 'not started')"
tot=0; up=0; fl=0
for K in 1 2 3 4; do P=/data$K/x1k; M=$P/manifest.run.tsv
  n=$(grep -c -v -e '^#' -e '^[[:space:]]*$' $M 2>/dev/null); n=${n:-0}; u=$(ls $P/uploaded 2>/dev/null | wc -l)
  f=$(python3 - $P/ctp/ledger.jsonl <<'PY'
import json, sys
final = {}
try:
    for line in open(sys.argv[1]):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("step") == "project" and r.get("project"):
            final[r["project"]] = r.get("state")
except OSError:
    pass
print(sum(1 for s in final.values() if s == "failed"), sum(1 for s in final.values() if s in ("done", "done-dirty")))
PY
)
  tot=$((tot + n)); up=$((up + u)); fl=$((fl + ${f%% *}))
  echo "p$K: unit $(systemctl is-active x1k@$K); rows $n; done ${f##* }; uploaded $u; last final row failed ${f%% *}; $(df -h --output=avail /data$K | tail -1 | tr -d ' ') free"
  tail -1 $P/logs/run.log 2>/dev/null | cut -c1-160
done
echo "ALL: uploaded $up of $tot ($(awk -v u=$up -v t=$tot 'BEGIN {if (t) printf "%.1f%%", 100*u/t}')); failed (last row) $fl"
st=$(cut -d' ' -f2 /etc/dataset-x1k/started 2>/dev/null)
[ -n "$st" ] && awk -v u=$up -v t=$tot -v s=$(date -d "$st" +%s) -v n=$(date +%s) 'BEGIN {h=(n-s)/3600; if (h > 0 && u > 0) printf "rate %.0f projects/h over %.1f h; at this rate the rest takes %.1f h\n", u/h, h, (t-u)/(u/h)}'
echo "running ctp projects: $(pgrep -c -u ec2-user -x git) git, $(pgrep -c -u ec2-user java) java"
tail -2 /data/logs/x1k-upload.log 2>/dev/null | cut -c1-160
free -g | sed -n 2p; uptime
[ -e /run/x1k-spot-interrupted ] && echo "SPOT INTERRUPTION: $(cat /run/x1k-spot-interrupted)"
[ -f /etc/dataset-x1k/final-DONE ] && cat /etc/dataset-x1k/final-DONE
exit 0
