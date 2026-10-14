# P2-probe.sh (read-only): script versions, other censuses, kernel blame progress.
set -u
B=/usr/local/bin
cd $B && sha256sum census-other-done census-batch4-guard census-backup census-L22-* census-L7-20-* | cut -c1-16,65- ; ls -la $B | grep -E 'orig|census-other|guard|backup' | cut -c30-
echo "== counts"
for x in "/bL7/ctp /home/ec2-user/L7-20-input/manifest.L7-20.tsv" "/bL22/ctp /home/ec2-user/L22-input/manifest.batch22L.tsv" "/b5L/ctp /home/ec2-user/batch5-input/manifest.batch5L.tsv"; do echo "$x: $($B/census-steps --counts $x)"; done
$B/census-steps /bL22/ctp /home/ec2-user/L22-input/manifest.batch22L.tsv --highlight '' | sed -n 4,8p | cut -c1-200
$B/census-steps /b5L/ctp /home/ec2-user/batch5-input/manifest.batch5L.tsv --highlight '' | sed -n 4,9p | cut -c1-200
echo "== blame progress of the kernels"
for n in multipath-tcp__mptcp_net-next gregkh__linux WireGuard__wireguard-linux ROCm__amdgpu Mellanox__nic-kernel raspberrypi__linux; do
  l=$(ls -t /bL7/ctp/state/$n/logs/*.log 2>/dev/null | head -1)
  echo "$n log=$(basename "$l") $(grep -a -m1 -iE 'files to blame|blaming [0-9]+|[0-9]+ files' "$l" 2>/dev/null | cut -c1-160) | last: $(tail -c 300 "$l" | tr '\r' '\n' | tail -1 | cut -c1-120)"
done
l=$(ls -t /bL7/ctp/state/gregkh__linux/logs/*.log | head -1); grep -a -n "Step 7" -A6 "$l" | cut -c1-200 | head -12
echo "== per-step times of the kernels"
grep -a -h "completed in" /bL7/ctp/state/gregkh__linux/logs/*.log | cut -c1-150 | head -12
echo "== disk and memory"
df -BG /bL7 /bL22 /b5L | cat; du -sh /bL7/census-2026-10-L7-20/* 2>/dev/null | cut -c1-100
ps -eo rss,comm --sort=-rss | head -12
cat /proc/pressure/memory /proc/pressure/io /proc/pressure/cpu
echo "== guard"; cat /run/census-batch4-guard.status; ls /run/census-batch4-guard.tripped 2>&1
echo "== resources.tsv head"; head -3 /bL7/ctp/resources.tsv | cut -c1-300
echo "== batch5L resources peak"; python3 - <<'P'
import csv,collections
for path in ['/b5L/ctp/resources.tsv','/bL22/ctp/resources.tsv']:
    try:
        rows=list(csv.reader(open(path),delimiter='\t'))
    except Exception as e: print(path,e); continue
    print(path,len(rows),rows[0])
P
