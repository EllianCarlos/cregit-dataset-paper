set +e
. /etc/cregit-census/batch.env
for p in $PARTS; do systemctl show -p Id -p OOMPolicy -p ActiveEnterTimestamp census-b3@$p.service | tr '\n' ' '; echo; done
tok=$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
echo "instance-action http $(curl -s -m 2 -o /dev/null -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" http://169.254.169.254/latest/meta-data/spot/instance-action)"
systemctl is-active census-b3-watch.service census-b3-upload.timer census-b3-live.timer
uptime; free -g | sed -n 2p
