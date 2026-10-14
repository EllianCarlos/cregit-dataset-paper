LOG=/data/logs/space-pause-20261013.log
d=$(df -BG --output=avail /data | tail -1 | tr -dc 0-9)
[ "$d" -ge 1500 ] || { echo "ABORT: /data only ${d}G free"; exit 1; }
for f in /bL7/ctp/STOP /bL7b/ctp/STOP /bL1r/ctp/STOP /bL23/ctp/STOP; do [ -e $f ] && { stat -c "%y $f" $f; rm -f $f; echo "$(date -u +%FT%TZ) removed guard $f (/data ${d}G free)" | tee -a $LOG; }; done
sleep 90
grep -a -E 'stopping|started|▶ clone' /data/logs/L7-20.log | tail -4 | cut -c1-150
cat /run/census-L23-wait.status 2>/dev/null | tail -1 | cut -c1-200
systemctl is-active census-L7-20 census-L7-20b census-L1r census-L23 census-L7-20-split.timer | tr '\n' ' '
