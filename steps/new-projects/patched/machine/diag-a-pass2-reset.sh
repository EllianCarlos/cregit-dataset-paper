#!/bin/bash
set -euo pipefail
systemctl is-active --quiet ta-run && { systemctl stop ta-run; sleep 2; }
python3 -c "import json; r=[json.loads(l) for l in open('/data/ta/results/write.jsonl') if l.strip()]; r=r[-156:]; print('sum s', round(sum(x['seconds'] for x in r)), 'max', max((x['seconds'],x['project']) for x in r))"
free -g | awk '/Mem:/{print "used "$3" avail "$7}'
ts=$(date -u +%Y%m%dT%H%M%SZ); cd /data/ta
for d in status/pseudo.DONE final53 private/registries private/write-work; do [ -e $d ] && mv $d $d.old.$ts; done
ls status/ | tr '\n' ' '; echo; echo "ta-run: $(systemctl is-active ta-run)"
