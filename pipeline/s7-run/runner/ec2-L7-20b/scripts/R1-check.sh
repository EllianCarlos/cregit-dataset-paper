# R1-check.sh (read-only): census L7-20b a few minutes after its start, and the split watcher.
set -u
echo "== $(date -u +%FT%TZ)"
systemctl is-active census-L7-20b.service census-L7-20b-wait.service census-L7-20b-live.timer census-L7-20-split.timer census-L7-20.service census-L22.service census-batch5L.service | tr '\n' ' '; echo
cat /run/census-L7-20-split.status | cut -c1-200
ls -la /bL7/ctp/STOP* /bL7b/ctp/STOP* 2>&1 | cut -c1-120
ls /bL7/ctp/state | tr '\n' ' '; echo
/usr/local/bin/census-steps /bL7b/ctp /home/ec2-user/L7-20b-input/manifest.L7-20b.tsv --highlight '' | sed -n 1,12p | cut -c1-170
grep -c . /data/logs/L7-20-split.log 2>/dev/null; journalctl -u census-L7-20-split.service --since "-10 min" --no-pager | wc -l
systemctl list-timers --no-legend census-L7-20-split.timer | cat
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); /data free $(df -BG --output=avail /data | tail -1 | tr -d ' '); bL7b image $(du -BG /data/loop/bL7b.img | cut -f1); load $(cut -d' ' -f1-3 /proc/loadavg)"
grep -E "stopping|✗|FAILED" /data/logs/L7-20b.log | tail -5 | cut -c1-200
