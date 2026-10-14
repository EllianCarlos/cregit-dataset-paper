# R1-check.sh (read-only): census L1r and its waiter.
set -u
echo "== $(date -u +%FT%TZ)"
systemctl is-active census-L1r.service census-L1r-wait.service census-L1r-live.timer census-L1r-firm.timer census-L23.service census-L23-wait.service census-L7-20.service census-L7-20b.service census-L22.service census-batch5L.service | tr '\n' ' '; echo
cut -c1-600 /run/census-L1r-wait.status 2>/dev/null
cat /run/census-L1r-firm.status 2>/dev/null; tail -3 /data/logs/L1r-firm.log 2>/dev/null
ls -la /bL1r/ctp/STOP* 2>&1 | cut -c1-120
/usr/local/bin/census-steps /bL1r/ctp /home/ec2-user/L1r-input/manifest.L1r.tsv --highlight '' 2>&1 | sed -n 1,12p | cut -c1-170
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); /data free $(df -BG --output=avail /data | tail -1 | tr -d ' '); bL1r image $(du -BG /data/loop/bL1r.img | cut -f1); load $(cut -d' ' -f1-3 /proc/loadavg)"
grep -E "stopping|✗|FAILED|PLAIN-BLAME" /data/logs/L1r.log 2>/dev/null | tail -5 | cut -c1-200
