#!/usr/bin/env bash
# C1-check-pf.sh (the path-fix instance, read-only, through ssm-run-pf.sh): progress of the cregit
# path-fix rerun. Copy of ~/s3-work/dataset-x1k/scripts/C1-check.sh for the 2 parts /data1/pf and
# /data2/pf (units pf@1, pf@2).
# Local use: RUN=dataset-pathfix-b1 I=<instance id> TAILN=80 bash ~/s3-work/dataset-pathfix/scripts/ssm-run-pf.sh ~/s3-work/dataset-pathfix/scripts/C1-check-pf.sh 300
# Quick look without SSM: aws s3 cp s3://${RUNNER_BUCKET}/dataset-x1k/live/<run>/progress.txt -
set -uo pipefail
E=/etc/dataset-pathfix; N=$(cat $E/nparts 2>/dev/null || echo 2)
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag) run $(cat $E/run 2>/dev/null || echo '-') up $(awk '{printf "%.1f h", $1/3600}' /proc/uptime); $(cat $E/started 2>/dev/null || echo 'not started')"
tot=0; up=0; fl=0
for K in $(seq 1 $N); do P=/data$K/pf; M=$P/manifest.run.tsv
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
  echo "p$K: unit $(systemctl is-active pf@$K); rows $n; done ${f##* }; uploaded $u; last final row failed ${f%% *}; $(df -h --output=avail /data$K | tail -1 | tr -d ' ') free"
  tail -1 $P/logs/run.log 2>/dev/null | cut -c1-160
done
echo "ALL: uploaded $up of $tot ($(awk -v u=$up -v t=$tot 'BEGIN {if (t) printf "%.1f%%", 100*u/t}')); failed (last row) $fl"
echo "running ctp projects: $(pgrep -c -u ec2-user -x git) git, $(pgrep -c -u ec2-user java) java"
tail -2 /data/logs/pf-upload.log 2>/dev/null | cut -c1-160
tail -2 /data/logs/pf-finalize.log 2>/dev/null | cut -c1-160
free -g | sed -n 2p; uptime
[ -e /run/pf-spot-interrupted ] && echo "SPOT INTERRUPTION: $(cat /run/pf-spot-interrupted)"
[ -f $E/final-DONE ] && cat $E/final-DONE
exit 0
