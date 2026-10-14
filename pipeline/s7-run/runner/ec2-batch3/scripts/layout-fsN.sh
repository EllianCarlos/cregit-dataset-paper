# layout-fsN.sh: the batch3a A/B layout: one XFS filesystem per instance-store NVMe disk
# (4 on m6id/c6id/r6id/m5d, 6 on i4i.24xlarge) at /data1../dataN, and /data -> /data1 (so /data/cregit-ec2, /data/input, /data/logs keep
# their batch 2 paths). Takes apart an existing RAID0 /dev/md0 first (its contents are lost).
set -euxo pipefail
DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
[ $(echo $DEVS | wc -w) -ge 1 ]
if mountpoint -q /data; then umount /data; fi
if [ -e /dev/md0 ]; then mdadm --stop /dev/md0; fi
for d in $DEVS; do mdadm --zero-superblock "$d" 2>/dev/null || true; done
sed -i '/^ARRAY /d' /etc/mdadm.conf 2>/dev/null || true
sed -i -e '\# /data #d' -e '\# /data[0-9]* #d' /etc/fstab
k=0
for d in $DEVS; do k=$((k+1))
  mkfs.xfs -f "$d" >/dev/null
  mkdir -p /data$k; mount -o noatime "$d" /data$k
  echo "UUID=$(blkid -s UUID -o value $d) /data$k xfs noatime,nofail 0 0" >> /etc/fstab
done
if [ -d /data ] && [ ! -L /data ]; then rmdir /data; fi
ln -sfn /data1 /data
mkdir -p /data/input /data/logs
chown -R ec2-user:ec2-user /data[0-9]*
df -h /data[0-9]*; ls -ld /data; grep data /etc/fstab
