set -u
LOG=/data/logs/space-pause-20261013.log
date -u +%FT%TZ | tee -a $LOG
for p in microsoft__WSL2-Linux-Kernel ni__linux HewlettPackard__gsc-linux microsoft__OHCL-Linux-Kernel; do
  pid=$(pgrep -u ec2-user -f "generate_dataset.py --blame-dir /bL7/census-2026-10-L7-20/$p/blame" | head -1)
  if [ -n "$pid" ] && tr '\0' ' ' < /proc/$pid/cmdline | grep -q "generate_dataset.py --blame-dir /bL7/census-2026-10-L7-20/$p/blame"; then
    kill -STOP $pid && echo "$(date -u +%FT%TZ) SIGSTOP $pid $p (state $(awk '{print $3}' /proc/$pid/stat))" | tee -a $LOG
  else echo "$(date -u +%FT%TZ) no step-10 process for $p" | tee -a $LOG; fi
done
sleep 20; df -BG /data /bL7 | tail -2 | tee -a $LOG
