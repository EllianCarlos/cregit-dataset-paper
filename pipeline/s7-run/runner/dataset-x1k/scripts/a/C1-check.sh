#!/usr/bin/env bash
# C1-check.sh, machine A (read-only, through scripts/a/ssm-a.sh): progress of the 11 long rows, one block
# per project (x1k-long-status: unit, step now, last completed step, .blame files and the files that
# step 7 of this attempt started, PLAIN-BLAME lines, orphan tmpfile-*, upload, out size), free space per volume, memory;
# then the last final ledger row per project and the running git/java counts.
# Local use: I=<instance id> TAILN=80 bash ~/s3-work/dataset-x1k/scripts/a/ssm-a.sh ~/s3-work/dataset-x1k/scripts/a/C1-check.sh 300
# Quick look without SSM: aws s3 cp s3://${RUNNER_BUCKET}/dataset-x1k/live-a/progress.txt -
set -uo pipefail
L=/data/x1k-long
[ -x /usr/local/bin/x1k-long-status ] || { echo "R3 (machine A) is not installed"; exit 0; }
/usr/local/bin/x1k-long-status
for p in $(cat $L/run.list 2>/dev/null); do
  python3 - $p $L/$p/ctp/ledger.jsonl <<'PY'
import json, sys
p, last, n = sys.argv[1], None, 0
try:
    for line in open(sys.argv[2]):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("project") == p:
            n += 1
            if r.get("step") == "project":
                last = r
except OSError:
    pass
print(f"{p}: {n} ledger rows; last final row: " + (f"attempt {last.get('attempt')} {last.get('state')} {str(last.get('detail', ''))[:100]}" if last else "none"))
PY
done
echo "running: $(pgrep -c -u ec2-user -x git) git, $(pgrep -c -u ec2-user java) java"
tail -2 /data/logs/x1k-long-upload.log 2>/dev/null | cut -c1-160
exit 0
