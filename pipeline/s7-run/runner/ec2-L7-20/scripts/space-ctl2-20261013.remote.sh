#!/bin/bash
# space-ctl2-20261013 (v2, 08:35 UTC): v1 ended when its queue was empty and so lost its emergency
# pause. v2 runs until no L7-20 step-10 process is left. At most 2 step-10 processes run; resume the
# next paused one when /bL7 >= 400 GB and /data >= 700 GB free and 10 min passed since the last resume;
# SIGSTOP the last resumed running one if /bL7 < 150 GB or /data < 350 GB.
set -u
LOG=/data/logs/space-pause-20261013.log
Q="2819821:ni__linux 2909990:microsoft__WSL2-Linux-Kernel"   # paused, in resume order
resumed="2758025:HewlettPackard__gsc-linux"                    # running, oldest first
last=0
say() { echo "$(date -u +%FT%TZ) ctl2: $*" | tee -a $LOG; }
ok() { tr '\0' ' ' < /proc/$1/cmdline 2>/dev/null | grep -q "generate_dataset.py --blame-dir /bL7/census-2026-10-L7-20/$2/blame"; }
alive() { local out=""; for n in $1; do ok ${n%%:*} ${n#*:} && out="$out $n"; done; echo $out; }
say "start; paused: $Q; running: $resumed"
while :; do
  resumed=$(alive "$resumed"); Q=$(alive "$Q")
  [ -z "$resumed$Q" ] && { say "no step-10 process left; end"; exit 0; }
  d=$(df -BG --output=avail /data | tail -1 | tr -dc 0-9); b=$(df -BG --output=avail /bL7 | tail -1 | tr -dc 0-9)
  nrun=$(echo $resumed | wc -w)
  if { [ "$b" -lt 150 ] || [ "$d" -lt 350 ]; } && [ "$nrun" -gt 1 ]; then
    r=${resumed##* }; kill -STOP ${r%%:*}; say "EMERGENCY /bL7 ${b}G /data ${d}G: SIGSTOP $r"
    resumed=$(echo $resumed | awk '{$NF=""; print}'); Q="$r $Q"
  elif [ -n "$Q" ] && [ "$nrun" -lt 2 ] && [ "$b" -ge 400 ] && [ "$d" -ge 700 ] && [ $(( $(date +%s) - last )) -ge 600 ]; then
    n=${Q%% *}; Q=$(echo $Q | cut -s -d' ' -f2-); kill -CONT ${n%%:*}; last=$(date +%s)
    say "SIGCONT $n (/bL7 ${b}G, /data ${d}G free, $nrun running before)"; resumed="$resumed $n"
  fi
  sleep 60
done
