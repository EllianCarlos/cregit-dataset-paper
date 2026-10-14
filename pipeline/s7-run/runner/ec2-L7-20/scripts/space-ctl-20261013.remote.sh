#!/bin/bash
# space-ctl-20261013: resume the L7-20 step-10 processes paused at 07:32 UTC one at a time, when the disk
# has room; pause the last resumed one again in an emergency. Ends when none is paused. Log below.
set -u
LOG=/data/logs/space-pause-20261013.log
Q="2758025:HewlettPackard__gsc-linux 2819821:ni__linux 2909990:microsoft__WSL2-Linux-Kernel"
last=$(date +%s); resumed="2586124:microsoft__OHCL-Linux-Kernel"
say() { echo "$(date -u +%FT%TZ) ctl: $*" | tee -a $LOG; }
ok() { tr '\0' ' ' < /proc/$1/cmdline 2>/dev/null | grep -q "generate_dataset.py --blame-dir /bL7/census-2026-10-L7-20/$2/blame"; }
say "start; queue $Q"
while :; do
  d=$(df -BG --output=avail /data | tail -1 | tr -dc 0-9); b=$(df -BG --output=avail /bL7 | tail -1 | tr -dc 0-9)
  run=0; for x in $(pgrep -u ec2-user -f 'generate_dataset.py --blame-dir /bL7/census-2026-10-L7-20/'); do [ "$(awk '{print $3}' /proc/$x/stat 2>/dev/null)" != T ] && run=$((run+1)); done
  if [ "$b" -lt 120 ] || [ "$d" -lt 300 ]; then
    r=${resumed##* }; pid=${r%%:*}; p=${r#*:}
    if ok $pid $p && [ "$(awk '{print $3}' /proc/$pid/stat)" != T ]; then kill -STOP $pid; say "EMERGENCY /bL7 ${b}G /data ${d}G: SIGSTOP $pid $p"; Q="$r $Q"; resumed=${resumed% *}; fi
  elif [ -n "$Q" ] && [ "$b" -ge 400 ] && [ "$d" -ge 700 ] && [ "$run" -le 2 ] && [ $(( $(date +%s) - last )) -ge 600 ]; then
    n=${Q%% *}; Q=$(echo "$Q" | cut -s -d' ' -f2-); pid=${n%%:*}; p=${n#*:}
    if ok $pid $p; then kill -CONT $pid; say "SIGCONT $pid $p (/bL7 ${b}G, /data ${d}G free, $run running)"; resumed="$resumed $n"; last=$(date +%s)
    else say "skip $n: not that process any more"; fi
  fi
  [ -z "$Q" ] && { say "queue empty; end"; exit 0; }
  sleep 60
done
