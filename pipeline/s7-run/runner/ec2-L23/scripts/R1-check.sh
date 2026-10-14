# R1-check.sh (read-only): census L23 and its waiter.
set -u
echo "== $(date -u +%FT%TZ)"
systemctl is-active census-L23.service census-L23-wait.service census-L23-live.timer census-L7-20.service census-L7-20b.service census-L22.service census-batch5L.service | tr '\n' ' '; echo
cut -c1-460 /run/census-L23-wait.status 2>/dev/null
ls -la /bL23/ctp/STOP* 2>&1 | cut -c1-120
/usr/local/bin/census-steps /bL23/ctp /home/ec2-user/L23-input/manifest.L23.tsv --highlight '' 2>&1 | sed -n 1,12p | cut -c1-170
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); /data free $(df -BG --output=avail /data | tail -1 | tr -d ' '); bL23 image $(du -BG /data/loop/bL23.img | cut -f1); load $(cut -d' ' -f1-3 /proc/loadavg)"
grep -E "stopping|✗|FAILED|PLAIN-BLAME" /data/logs/L23.log 2>/dev/null | tail -5 | cut -c1-200
