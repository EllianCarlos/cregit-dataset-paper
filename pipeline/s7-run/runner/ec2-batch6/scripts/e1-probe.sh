set +e
export AWS_PAGER=""
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag)"
uptime; awk '/MemAvailable|MemTotal/{printf "%s %.0f GiB  ", $1, $2/1048576}' /proc/meminfo; echo
df -BG --output=target,size,used,avail /data /b4p1 /b4p2 /b4p3 /b5L / 2>/dev/null
du -BG /data/loop/*.img
cd /usr/local/bin && sha256sum census-other-done census-batch4-guard census-backup 2>&1 | cut -c1-16,64-
ls /usr/local/bin | grep -i census | tr '\n' ' '; echo
grep -n 'RUNS' /usr/local/bin/census-backup | head -10
systemctl list-units --no-pager --plain 'census*' --all | grep -v '^$' | head -40
systemctl list-timers --no-pager 'census*' | head
for u in $(systemctl list-units --no-pager --plain --no-legend 'census*' --all | awk '{print $1}'); do echo "$u NRD=$(systemctl show $u -p NeedDaemonReload --value)"; done | grep -v 'NRD=no' | head
for k in 1 2 3; do echo "--- batch4p$k"; (cd /b4p$k/ctp && CTP_CONFIG=$(systemctl show census-batch4p$k -p Environment --value | tr ' ' '\n' | grep CTP_CONFIG | cut -d= -f2) sudo -u ec2-user -E .venv/bin/python ctp.py progress --manifest $(ls /home/ec2-user/batch4-input/manifest.batch4p$k.tsv 2>/dev/null || echo x) --last 0 2>&1 | head -8); done
cat /usr/local/bin/census-batch4p1-run 2>/dev/null | head -20 || ls /usr/local/bin/census-batch4*
pgrep -fa 'ctp.py census' | cut -c1-160
ps -eo args | grep -c '[c]tp.py.*project-worker\|[g]enerate_dataset' 
