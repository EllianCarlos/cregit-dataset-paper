# P1 (read-only): spot b capacity for batch 24 (the 32 L7-20b rows moved to spot b).
set -uo pipefail
F=/etc/cregit-census/fed
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag) half $(cat $F/half)"
nproc; uptime
grep -E 'MemTotal|MemAvailable' /proc/meminfo
df -BG --output=target,size,used,avail /data /w/* 2>/dev/null
echo "slots: $(cat $F/slots 2>/dev/null || echo default8) worker_slots: $(cat $F/worker_slots 2>/dev/null || echo default20) PAUSE: $(cat $F/PAUSE 2>/dev/null || echo none)"
echo "queue: $(tr '\n' ',' < $F/queue)"; echo "feeder: $(cat /run/census-fed-feeder.status)"
ls $F/wl/; ls /home/ec2-user/fed-input/ | tr '\n' ' '; echo
for e in $F/*.env; do . $e; systemctl is-active -q census-fed@$ID.service && echo "active $ID workers=$WORKERS size=${SIZE_G}G floor=$FLOOR host=$HOST"; done
ls -ls /data/loop/ | head -40
grep -c . $F/started; cat /etc/cregit-census/censuses | tr '\n' ' '; echo
ls /usr/local/bin/census-fed-* | tr '\n' ' '; echo
sha256sum /usr/local/bin/census-fed-derive /usr/local/bin/census-fed-enqueue /usr/local/bin/census-fed-feeder /usr/local/bin/census-fed-part-init /usr/local/bin/census-fed-run
