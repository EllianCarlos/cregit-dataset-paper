set -uo pipefail
d=/w/batch7a3/census-2026-10-batch7/signalwire__freeswitch
grep -n -m3 -E "Exception|Error|error:" $d/pipeline.log | cut -c1-300
grep -n -B2 -A6 -m1 "Exception" $d/pipeline.log | cut -c1-300
grep -c "\"signalwire__freeswitch\"" /w/batch7a3/ctp/ledger.jsonl; grep "signalwire__freeswitch" /w/batch7a3/ctp/ledger.jsonl | tail -3 | cut -c1-300
cat /etc/cregit-census/fed/batch7a3.cfg 2>/dev/null | grep -i -E "retr|workers" | head
