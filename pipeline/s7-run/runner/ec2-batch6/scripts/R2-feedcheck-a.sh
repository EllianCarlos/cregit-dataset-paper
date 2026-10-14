set -uo pipefail
systemctl list-units "census-fed*" --no-legend --no-pager | head -12
tail -15 /data/logs/fed-feeder.log 2>/dev/null | cut -c1-240
ls /etc/cregit-census/fed/ 2>&1 | head; cat /etc/cregit-census/fed/PAUSE 2>/dev/null
cat /etc/cregit-census/fed/slots /etc/cregit-census/fed/worker_slots 2>/dev/null
free -g | head -2; lsblk -d -o NAME,SIZE | head -8
