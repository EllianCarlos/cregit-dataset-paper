set -uo pipefail
[ -e /home/ec2-user/ctp/STOP ] && { echo "STOP exists"; exit 1; }
systemctl enable --now census-batch2-live.timer
systemctl start census-batch2.service
sleep 90
systemctl status census-batch2.service --no-pager | head -12
systemctl list-timers census-batch2-live.timer --no-pager | head -3
tail -n 30 /data/logs/batch2.log
