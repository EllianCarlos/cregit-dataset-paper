set -euo pipefail
mkdir -p /etc/systemd/system/census-b3@.service.d
printf '[Service]\n# an OOM kill of one project must not stop the whole census\nOOMPolicy=continue\n' > /etc/systemd/system/census-b3@.service.d/oom.conf
systemctl daemon-reload
systemctl show -p OOMPolicy census-b3@a1.service census-b3@b.service | sort -u
systemctl list-units 'census-b3@*' --no-pager --no-legend | head
