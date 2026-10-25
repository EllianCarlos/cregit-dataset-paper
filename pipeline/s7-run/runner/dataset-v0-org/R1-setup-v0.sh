#!/usr/bin/env bash
# R1-setup-v0.sh (the v0 machine, root, through ssm-v0.sh; idempotent; starts nothing). The layout that
# V1-start.sh needs: one XFS per instance-store disk at /data1../dataN, /data -> /data1 (as
# ../dataset-x1k/x2/R1-x2-setup.sh), and /data/ctp/.venv: Python 3.12 with duckdb 1.5.5 (the version of the
# local v0 test of 2026-10-20).
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1})
  echo "ABORT: $IID is not the v0 machine"; exit 1 ;; esac
echo "== $(date -u +%FT%TZ) $IID $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB"
for i in $(seq 1 40); do dnf -y -q install python3.12 python3.12-pip xfsprogs >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
if ! mountpoint -q /data1; then
  DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
  [ "$(echo $DEVS | wc -w)" -ge 2 ] || { echo "ABORT: expected at least 2 instance-store disks, got: $DEVS"; exit 1; }
  sed -i -e '\# /data #d' -e '\# /data[0-9]* #d' /etc/fstab
  k=0
  for d in $DEVS; do k=$((k+1))
    mkfs.xfs -f "$d" >/dev/null
    mkdir -p /data$k; mount -o noatime "$d" /data$k
    echo "UUID=$(blkid -s UUID -o value $d) /data$k xfs noatime,nofail 0 0" >> /etc/fstab
  done
  if [ -d /data ] && [ ! -L /data ]; then rmdir /data; fi
  ln -sfn /data1 /data
fi
mkdir -p /data/ctp; chown ec2-user:ec2-user /data[0-9]* /data/ctp
df -h /data[0-9]* | tail -n +2
if [ ! -x /data/ctp/.venv/bin/python ]; then
  sudo -u ec2-user python3.12 -m venv /data/ctp/.venv
  sudo -u ec2-user nice -n 19 /data/ctp/.venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5
fi
sudo -u ec2-user /data/ctp/.venv/bin/python -I -c 'import duckdb, sys; print("python", sys.version.split()[0], "duckdb", duckdb.__version__)'
echo "R1-v0 done $(date -u +%FT%TZ)"
