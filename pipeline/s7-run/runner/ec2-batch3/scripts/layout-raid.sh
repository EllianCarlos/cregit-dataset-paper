# layout-raid.sh: the batch 2 layout (batch3b, the control): one RAID0 /dev/md0 of all the
# instance-store NVMe disks (4, or 6 on i4i.24xlarge), XFS at /data. Undoes the /data -> /data1 link an AMI made on a may carry.
set -euxo pipefail
DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
N=$(echo $DEVS | wc -w); [ $N -ge 1 ]
if [ -L /data ]; then rm -f /data; fi
mkdir -p /data
sed -i '/^ARRAY /d' /etc/mdadm.conf 2>/dev/null || true
sed -i -e '\# /data #d' -e '\# /data[0-9]* #d' /etc/fstab
if ! [ -e /dev/md0 ]; then mdadm --create /dev/md0 --level=0 --raid-devices=$N --run $DEVS; fi
mkfs.xfs -f /dev/md0 >/dev/null
mount -o noatime /dev/md0 /data
mdadm --detail --scan > /etc/mdadm.conf
echo '/dev/md0 /data xfs noatime,nofail 0 0' >> /etc/fstab
mkdir -p /data/input /data/logs
chown -R ec2-user:ec2-user /data
df -h /data; cat /proc/mdstat
