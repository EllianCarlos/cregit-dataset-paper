set -euo pipefail
[ -d /opt/cregit-ec2.checked ] || cp -a /data1/cregit-ec2 /opt/cregit-ec2.checked
du -sh /opt/cregit-ec2.checked
/usr/local/bin/census-b3-prep
sha256sum /home/ec2-user/b3-input/manifest.a?.full.tsv
systemctl is-active census-b3@a1.service census-b3@a2.service census-b3@a3.service census-b3@a4.service || true
sync; sync
