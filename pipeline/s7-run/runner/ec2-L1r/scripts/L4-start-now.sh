set -euo pipefail
date -u +%FT%TZ
units=$(systemctl list-units 'census*' --all --no-legend --plain | awk '{print $1}')
bad=0; for u in $units; do [ "$(systemctl show -p NeedDaemonReload --value $u)" = yes ] && { echo "NeedDaemonReload=yes: $u"; bad=1; }; done
[ $bad = 0 ] || { echo "ABORT: a census unit needs daemon-reload"; exit 1; }
before=$(systemctl list-units 'census*' --state=active --no-legend --plain | awk '{print $1, $4}' | sort; for u in census-L7-20 census-L7-20b census-L22; do systemctl show -p MainPID --value $u; done)
mkdir -p /etc/systemd/system/census-L1r-wait.service.d
cat > /etc/systemd/system/census-L1r-wait.service.d/maxrun.conf <<'X'
# 2026-10-12 ~20:05 UTC, user decision "Start L1r now": the L23 rule is removed (/bL1r/ctp/IGNORE-L23)
# and L1r may start with at most 14 other projects running (default 12).
[Service]
Environment=MAXRUN=14
X
systemctl daemon-reload
after=$(systemctl list-units 'census*' --state=active --no-legend --plain | awk '{print $1, $4}' | sort; for u in census-L7-20 census-L7-20b census-L22; do systemctl show -p MainPID --value $u; done)
[ "$before" = "$after" ] && echo "running census units unchanged by daemon-reload" || { echo "WARNING: units differ"; diff <(echo "$before") <(echo "$after") || true; }
touch /bL1r/ctp/IGNORE-L23; chown ec2-user: /bL1r/ctp/IGNORE-L23
systemctl restart census-L1r-wait
sleep 75
systemctl show -p Environment --value census-L1r-wait
cat /run/census-L1r-wait.status 2>/dev/null | tail -2
systemctl is-active census-L1r census-L1r-wait | tr '\n' ' '; echo
