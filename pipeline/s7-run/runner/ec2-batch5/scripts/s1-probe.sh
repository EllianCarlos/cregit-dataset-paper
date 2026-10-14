set +e
export AWS_PAGER=""
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag) $(curl -s -m2 -H "X-aws-ec2-metadata-token: $(curl -s -m2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/instance-type)"
uptime; free -g | sed -n 2p; nproc
cat /etc/cregit-census/batch.env
. /etc/cregit-census/batch.env
for p in $PARTS; do . /etc/cregit-census/$p.env; echo "$p $(systemctl is-active census-b3@$p.service) W=$WORKERS CTP=$CTP OUT=$OUT"; done
ls -ld /data /data[0-9]* /opt/cregit-ec2.checked 2>&1
df -BG --output=target,size,avail /data /data[0-9]* / 2>/dev/null
lsblk -d -n -o NAME,SIZE,MODEL | head -10
for d in /data/cregit-ec2 /opt/cregit-ec2.checked; do [ -d $d ] && echo "$d $(sudo -u ec2-user git -C $d rev-parse --short HEAD) dirty=$(sudo -u ec2-user git -C $d status --porcelain --untracked-files=no | wc -l) build=$(ls -A $d/tokenizeByBlobId/build 2>/dev/null | wc -l) size=$(du -sh $d 2>/dev/null | cut -f1)"; done
ls /data/input /home/ec2-user | head -40
ls -la /home/ec2-user/NO_SHUTDOWN
systemctl list-units --no-pager --plain 'census*' | head -30
ls /usr/local/bin/ | grep -i census
ps -eo comm | sort | uniq -c | sort -rn | head -8
grep -c . /home/ec2-user/b3-input/done.txt 2>/dev/null
pgrep -fa 'ctp.py census' | cut -c1-200
which python3.12; python3.12 --version
