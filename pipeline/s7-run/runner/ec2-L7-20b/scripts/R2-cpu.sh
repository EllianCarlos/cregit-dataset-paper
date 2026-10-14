# R2-cpu.sh (read-only): CPU load and pressure after the L7-20b start.
echo "== $(date -u +%FT%TZ) load $(cut -d' ' -f1-3 /proc/loadavg); nproc $(nproc)"
cat /proc/pressure/cpu
top -b -n1 -o %CPU | sed -n 7,22p | cut -c1-110
for u in census-L7-20 census-L7-20b census-L22 census-batch5L; do echo "$u CPU: $(systemctl show $u.service -p CPUUsageNSec --value)"; done
sleep 30
for u in census-L7-20 census-L7-20b census-L22 census-batch5L; do echo "$u CPU: $(systemctl show $u.service -p CPUUsageNSec --value)"; done
tail -n 2 /data/logs/L7-20.log | cut -c1-300
