# s4-a-stopfin.sh (spot a): stop the old census-b3-finalize that waits (old script, would terminate
# once NO_SHUTDOWN is gone); a batch 3 part that ends starts the new one. Then remove NO_SHUTDOWN.
set -uo pipefail
. /etc/cregit-census/batch.env
pid=$(systemctl show -p MainPID --value census-b3-finalize.service); st=$(systemctl is-active census-b3-finalize.service)
act=""; for p in $PARTS; do systemctl is-active --quiet census-b3@$p.service && act="$act $p"; done
echo "finalize $st pid $pid started $(systemctl show -p ExecMainStartTimestamp --value census-b3-finalize.service); children: $(ps -o comm= --ppid $pid | tr '\n' ' '); b3 parts active:$act"
echo "journal: $(journalctl -u census-b3-finalize.service --no-pager -o cat -n 2 | tr '\n' ' ' | cut -c1-300)"
echo "running script inode deleted? $(ls -l /proc/$pid/fd 2>/dev/null | grep -c 'census-b3-finalize (deleted)') ; cmdline: $(tr '\0' ' ' < /proc/$pid/cmdline)"
if [ "$st" = activating ] && [ -n "$act" ] && ps -o comm= --ppid $pid | grep -qx sleep; then
  systemctl stop census-b3-finalize.service
  echo "stopped: finalize $(systemctl is-active census-b3-finalize.service); parts:$(for p in $PARTS; do echo -n " $p=$(systemctl is-active census-b3@$p.service)"; done)"
  rm -f /home/ec2-user/NO_SHUTDOWN && echo "NO_SHUTDOWN removed $(date -u +%FT%TZ)"
elif [ "$st" = inactive ]; then echo "old finalize not running: nothing to stop"; rm -f /home/ec2-user/NO_SHUTDOWN && echo "NO_SHUTDOWN removed $(date -u +%FT%TZ)"
else echo "not in the wait loop: NOT stopped, NO_SHUTDOWN kept"; fi
echo "$(/usr/local/bin/census-b3-finalize --decide-only 2>&1 | tail -1)"
grep -c 'census-spot-decide' /usr/local/bin/census-b3-finalize; uptime
