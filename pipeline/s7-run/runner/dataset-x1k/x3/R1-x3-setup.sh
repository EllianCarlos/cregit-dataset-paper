#!/usr/bin/env bash
# R1-x3-setup.sh (the x1k links machine, root, through x3/ssm-x3.sh; idempotent; starts nothing).
#   - one XFS per instance-store disk at /data1../dataN, /data -> /data1 (as ../x2/R1-x2-setup.sh; one
#     disk is enough here: the run needs about 200 GB);
#   - /data/x3/tools: the stage of S0-x3-stage.sh from s3://B/dataset-x1k/links-tools/ (uploaded by
#     the user with U1-upload-x3.sh). The sha256 of its SHA256SUMS must be WANT_SUMS, and each file
#     must check (extract_domains_v1.py, build_links.py, build_v0.py, x3_report.py, x3_plainblame.py,
#     x3_run.sh, companies.v4.6.duckdb, ref-links/);
#   - /data/x3/.venv: Python 3.12 with duckdb 1.5.5 (the version of this host and of the x2 runs);
#   - the aws CLI of ec2-user: s3 max_concurrent_requests 32 (faster downloads).
# Prints counts and versions only.
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1}|${RUNNER_EC2_X1K_RAW_1}|${RUNNER_EC2_X1K_RAW_2}|${RUNNER_EC2_V0_ORG_1})
  echo "ABORT: $IID is not the x3 links machine"; exit 1 ;; esac
B=s3://${RUNNER_BUCKET}
X=/data/x3; T=$X/tools
WANT_SUMS=7dba806bb9e3a1f78eb2da654f7daa870978637bff687ad6ae49ef8f9e60ba2b
echo "== $(date -u +%FT%TZ) $IID run ${X3_RUN:-?} $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB"
for i in $(seq 1 40); do dnf -y -q install python3.12 python3.12-pip xfsprogs >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
if ! mountpoint -q /data1; then
  DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
  [ "$(echo $DEVS | wc -w)" -ge 1 ] || { echo "ABORT: no instance-store disk"; exit 1; }
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
avail=$(df -BG --output=avail /data1 | tail -1 | tr -dc 0-9)
[ "$avail" -ge 400 ] || { echo "ABORT: /data1 has ${avail} GB free, need 400"; exit 1; }
mkdir -p $T; chown ec2-user:ec2-user /data[0-9]* $X
df -h /data[0-9]* | tail -n +2
# --- tools
aws s3 cp --recursive $B/dataset-x1k/links-tools/ $T/ --only-show-errors || { echo "ABORT: no links-tools/ (the user runs x3/U1-upload-x3.sh first)"; exit 1; }
[ "$(sha256sum $T/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: links-tools/SHA256SUMS is not $WANT_SUMS (S0 changed: update WANT_SUMS here, in U1 and in M1)"; exit 1; }
(cd $T && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a tool sha256"; exit 1; }
echo "tools ok: $(wc -l < $T/SHA256SUMS) files, SHA256SUMS $(echo $WANT_SUMS | cut -c1-12); $(cat $T/SOURCE)"
# --- venv
if [ ! -x $X/.venv/bin/python ]; then
  sudo -u ec2-user python3.12 -m venv $X/.venv
  sudo -u ec2-user nice -n 19 $X/.venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5
fi
sudo -u ec2-user $X/.venv/bin/python -I -c 'import duckdb, sys; print("python", sys.version.split()[0], "duckdb", duckdb.__version__)'
# more parallel S3 transfers for the downloads of x3_run.sh (the aws CLI of ec2-user on this machine)
sudo -u ec2-user aws configure set default.s3.max_concurrent_requests 32
chown -R ec2-user:ec2-user $X
echo "R1-x3 done $(date -u +%FT%TZ)"
