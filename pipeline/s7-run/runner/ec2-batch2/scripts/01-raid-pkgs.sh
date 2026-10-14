set -euxo pipefail
uname -r; cat /etc/os-release | grep PRETTY
lsblk -d -o NAME,SIZE,MODEL
DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
echo "instance store: $DEVS"; [ $(echo $DEVS | wc -w) -eq 4 ]
dnf -y -q install mdadm git tmux python3.12 python3.12-pip xfsprogs nvme-cli tar xz
if ! [ -e /dev/md0 ]; then mdadm --create /dev/md0 --level=0 --raid-devices=4 --run $DEVS; fi
mkfs.xfs -f /dev/md0 >/dev/null
mkdir -p /data; mount -o noatime /dev/md0 /data
df -h /data; cat /proc/mdstat
mkdir -p /data/input /data/logs
aws s3 cp s3://${RUNNER_BUCKET}/batch2/input/ /data/input/ --recursive --only-show-errors
cd /data/input && sha256sum -c SHA256SUMS
chown -R ec2-user:ec2-user /data
git --version; mdadm --version 2>&1; tmux -V; python3.12 --version; aws --version
nproc; free -g | head -2
