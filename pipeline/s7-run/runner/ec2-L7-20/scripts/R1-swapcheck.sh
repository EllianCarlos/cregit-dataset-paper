set -uo pipefail
systemctl is-active cregit-L7-20-v2swap.timer cregit-L7-20-v2swap.service census-L7-20-wait.service census-L7-20.service
journalctl -u cregit-L7-20-v2swap.service --since "-20 min" --no-pager | tail -8 | cut -c1-250
ls -la /bL7/ctp/STOP* 2>&1
cut -c1-300 /run/census-L7-20-wait.status 2>/dev/null
sha256sum /home/ec2-user/L7-20-input/* 2>/dev/null | cut -c1-90
