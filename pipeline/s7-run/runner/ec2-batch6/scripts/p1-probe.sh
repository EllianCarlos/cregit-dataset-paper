set +e
export AWS_PAGER=""
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag)"
uptime; awk '/MemAvailable|MemTotal/{printf "%s %.0f GiB  ", $1, $2/1048576}' /proc/meminfo; echo; nproc
cat /etc/cregit-census/censuses; cat /etc/cregit-census/s5/batch.env
df -BG --output=target,size,used,avail /data /data[0-9]* / 2>/dev/null
for f in /data*/loop/*.img; do echo "$f $(du -BG $f | cut -f1) $(stat -c %s $f | awk '{printf "%dG", $1/2^30}')"; done 2>/dev/null
. /etc/cregit-census/s5/batch.env
for id in $IDS; do . /etc/cregit-census/s5/$id.env; echo "$id $(systemctl is-active census-b5@$id) host=$HOST free=$(df -BG --output=avail $MP | tail -1) run=$(grep -c -v -e '^#' -e '^[[:space:]]*$' /home/ec2-user/s5-input/manifest.$id.run.tsv) upl=$(ls $MP/uploaded | wc -l) NRD=$(systemctl show census-b5@$id -p NeedDaemonReload --value)"; done
systemctl list-units --no-pager --plain 'census*' | grep -v '^$' | head -30
ls /usr/local/bin | grep census | tr '\n' ' '; echo
ls /data/input | tr '\n' ' '; echo
ls /home/ec2-user | tr '\n' ' '; echo
pgrep -fa 'ctp.py census' | wc -l
grep -m3 -i 'census\|python' /etc/sudoers.d/* 2>/dev/null | head -3
aws --version 2>&1 | head -1
