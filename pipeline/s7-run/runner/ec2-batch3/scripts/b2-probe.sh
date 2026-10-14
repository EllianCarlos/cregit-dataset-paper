set -uo pipefail
date; timedatectl | grep -i "time zone"
systemctl is-active census-batch2.service census-batch2-live.timer
systemctl list-timers census-batch2-live.timer --no-pager | head -3
cd /home/ec2-user/ctp
ls state | wc -l
for d in state/*/logs; do ls -1 $d | tail -1; done | head -5
tail -c 1500 ledger.jsonl | tail -2 | cut -c1-700
wc -l ledger.jsonl
grep -c '"step": *"project"' ledger.jsonl
cat /home/ec2-user/census-batch2.cfg
ls /home/ec2-user/ /data /data/logs
uptime; free -g | head -2; df -h /data | tail -1
