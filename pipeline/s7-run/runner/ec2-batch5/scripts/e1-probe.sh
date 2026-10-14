set +e
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag)"
uptime; free -g | sed -n 2p; grep MemAvailable /proc/meminfo
df -BG --output=target,size,used,avail /data /b4p1 /b4p2 /b4p3 / 2>/dev/null
du -BG /data/loop/*.img 2>/dev/null
ls -la /home/ec2-user/NO_SHUTDOWN 2>&1
systemctl is-active census-batch2.service census-batch3L-wait.service census-batch3L.service census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch4-finalize.service census-batch4-guard.timer census-batch4-live.timer | tr '\n' ' '; echo
for u in census-batch2 census-batch3L census-batch4p1 census-batch4p2 census-batch4p3 census-batch4-finalize census-batch4-guard census-batch4-live; do echo "$u NeedDaemonReload=$(systemctl show -p NeedDaemonReload --value $u.service) MainPID=$(systemctl show -p MainPID --value $u.service) OOM=$(systemctl show -p OOMPolicy --value $u.service)"; done
cat /run/census-batch4-guard.status
sha256sum /usr/local/bin/census-other-done /usr/local/bin/census-batch4-guard /usr/local/bin/census-batch4-live /usr/local/bin/census-batch4-finalize /usr/local/bin/census-batch2-finalize /usr/local/bin/census-batch3L-finalize | cut -c1-16,65-
grep -n 'census-other-done' /usr/local/bin/census-batch*-finalize | cut -c1-160
ls /home/ec2-user/ | head -30; ls /data | head -30
for k in 1 2 3; do echo "p$k: $(grep -c . /b4p$k/ctp/ledger.jsonl) ledger rows; running: $(pgrep -u ec2-user -f "census-batch4p$k" | wc -l)"; done
pgrep -fa 'ctp.py census' | cut -c1-150
ps -eo rss,comm --sort=-rss | head -8
lsblk | grep loop
