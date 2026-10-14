set -uo pipefail
d=/w/batch7a3/census-2026-10-batch7/signalwire__freeswitch
tail -5 $d/pipeline.log | cut -c1-220
ps -eo pid,etimes,pcpu,stat,rss,args | grep -F "signalwire__freeswitch" | grep -v grep | cut -c1-200 | head -12
for p in $(ps -eo pid,args | grep -F "signalwire__freeswitch" | grep -v grep | awk "{print \$1}"); do echo "$p $(cat /proc/$p/io 2>/dev/null | grep -E "read_bytes|write_bytes" | tr "\n" " ")"; done | head -8
ls -la $d | head -20
