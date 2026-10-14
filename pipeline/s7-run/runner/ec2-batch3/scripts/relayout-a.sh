set -euo pipefail
# keep the built cregit tree on the root volume (for the re-layout now, and for the AMI)
mkdir -p /opt && [ -d /opt/cregit-ec2 ] || cp -a /data/cregit-ec2 /opt/cregit-ec2
du -sh /opt/cregit-ec2; sudo -u ec2-user git -C /opt/cregit-ec2 log --oneline -1
# layout-fs4.sh: the batch3a A/B layout: 4 separate XFS filesystems, one per instance-store NVMe
# disk, at /data1../data4, and /data -> /data1 (so /data/cregit-ec2, /data/input, /data/logs keep
# their batch 2 paths). Takes apart an existing RAID0 /dev/md0 first (its contents are lost).
set -euxo pipefail
DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
[ $(echo $DEVS | wc -w) -eq 4 ]
if mountpoint -q /data; then umount /data; fi
if [ -e /dev/md0 ]; then mdadm --stop /dev/md0; fi
for d in $DEVS; do mdadm --zero-superblock "$d" 2>/dev/null || true; done
sed -i '/^ARRAY /d' /etc/mdadm.conf 2>/dev/null || true
sed -i -e '\# /data #d' -e '\# /data[1-4] #d' /etc/fstab
k=0
for d in $DEVS; do k=$((k+1))
  mkfs.xfs -f "$d" >/dev/null
  mkdir -p /data$k; mount -o noatime "$d" /data$k
  echo "UUID=$(blkid -s UUID -o value $d) /data$k xfs noatime,nofail 0 0" >> /etc/fstab
done
if [ -d /data ] && [ ! -L /data ]; then rmdir /data; fi
ln -sfn /data1 /data
mkdir -p /data/input /data/logs
chown -R ec2-user:ec2-user /data1 /data2 /data3 /data4
df -h /data1 /data2 /data3 /data4; ls -ld /data; grep data /etc/fstab
set +x
aws s3 cp s3://${RUNNER_BUCKET}/batch2/input/ /data/input/ --recursive --only-show-errors
(cd /data/input && sha256sum --quiet -c SHA256SUMS) && echo "batch2 inputs sha256 ok"
mkdir -p /data/input3; aws s3 cp s3://${RUNNER_BUCKET}/batch3/input/ /data/input3/ --recursive --only-show-errors
(cd /data/input3 && sha256sum -c SHA256SUMS)
cp -a /opt/cregit-ec2 /data1/cregit-ec2
chown -R ec2-user:ec2-user /data1
# the same build step as batch 2 (up to date after the copy, so quick), then the identity check on /data1
sudo -u ec2-user -i bash /home/ec2-user/build.sh 2>&1 | grep -v -e '^• ' -e '^✓' | tail -12
