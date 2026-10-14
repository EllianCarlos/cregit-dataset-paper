set +e
. /etc/cregit-census/batch.env
for p in $PARTS; do export CTP_$p=/home/ec2-user/ctp-check OUT_$p=/data/ec2-check/out; done
MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv /usr/local/bin/census-b3-finalize --dry-run 2>&1 | grep -v "^\s*$" | tail -n 6
echo "dry rc=${PIPESTATUS[0]}"
for p in $PARTS; do echo -n "$(systemctl is-active census-b3@$p.service) "; done; echo
