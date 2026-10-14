set -euo pipefail
install -m 0755 /root/ssm/census-backup.payload /usr/local/bin/census-backup
cat > /etc/systemd/system/census-backup.service <<'U'
[Unit]
Description=Back up finished census Parquets to S3 (read-only on the census)
[Service]
Type=oneshot
Nice=10
IOSchedulingClass=idle
ExecStart=/usr/local/bin/census-backup
U
cat > /etc/systemd/system/census-backup.timer <<'U'
[Unit]
Description=Back up finished census Parquets to S3 every 30 min
[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
[Install]
WantedBy=timers.target
U
for u in census-batch2 census-batch3L census-batch4p1 census-batch4p2 census-batch4p3 census-batch5L; do
  echo "$u NeedDaemonReload=$(systemctl show -p NeedDaemonReload --value $u) MainPID=$(systemctl show -p MainPID --value $u)"
done
systemctl daemon-reload
systemctl enable --now census-backup.timer
for u in census-batch2 census-batch3L census-batch4p1 census-batch4p2 census-batch4p3 census-batch5L; do
  echo "after $u MainPID=$(systemctl show -p MainPID --value $u) $(systemctl is-active $u)"
done
systemctl start census-backup.service; systemctl is-active census-backup.timer; tail -3 /data/logs/census-backup.log
