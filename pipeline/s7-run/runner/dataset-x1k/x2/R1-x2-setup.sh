#!/usr/bin/env bash
# R1-x2-setup.sh (the X2 merge machine, root, through x2/ssm-x2.sh; idempotent; starts nothing).
# Layout and tools for x1k-raw (step X2 of the merge plan), as v1-raw on spot a:
#   - one XFS per instance-store disk at /data1../dataN, /data -> /data1 (as ../scripts/R1-setup.sh);
#   - /data/x2/tools: final_merge.py and rewrite_meta_columns.py of v1 (s3://B/dataset-v1/tools/, the
#     sha256 of its SHA256SUMS: acede0d8... and 365867b0..., ${RUNNER_STUDY_REPO} 17bc439) and the x1k final
#     sidecar project_meta.x1k.final.json + .sha256 (s3://B/dataset-x1k/raw-tools/, uploaded by the
#     user with x2/U1-upload-x2.sh; sha256 1520c5f4...);
#   - /data/x2/ctp: a clone of batch2/input/ctp.bundle at ca113e3 (validate_schema.py = 2efe32c3...);
#   - /data/x2/.venv: Python 3.12 with duckdb 1.5.5 (the ctp venvs of the runs).
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1})
  echo "ABORT: $IID is not the X2 machine"; exit 1 ;; esac
B=s3://${RUNNER_BUCKET}
X=/data/x2; T=$X/tools
WANT_FM=acede0d8549383530eb70122ad1a3f05e092619bbbecf93301815cac8b6821d9
WANT_RW=365867b0b06997e255cea0a99cd217ca914a4c7ea59679f2c9a9725a43e6e14f
WANT_SC=1520c5f4d8909b3625c73bdea3cc08f23fced0a77f3722ec0809acd80de96f35
WANT_VS=2efe32c3a286991a14e848913581e719ea2c0dbfbd621746d573e190d328a053
echo "== $(date -u +%FT%TZ) $IID run ${X2_RUN:-?} $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB"
for i in $(seq 1 40); do dnf -y -q install git python3.12 python3.12-pip xfsprogs tar >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
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
mkdir -p $T /data/logs; chown ec2-user:ec2-user /data[0-9]* $X /data/logs
df -h /data[0-9]* | tail -n +2
# --- tools
for f in final_merge.py rewrite_meta_columns.py SOURCE; do aws s3 cp $B/dataset-v1/tools/$f $T/$f --only-show-errors; done
[ "$(sha256sum $T/final_merge.py | cut -d' ' -f1)" = $WANT_FM ] || { echo "ABORT: final_merge.py sha256"; exit 1; }
[ "$(sha256sum $T/rewrite_meta_columns.py | cut -d' ' -f1)" = $WANT_RW ] || { echo "ABORT: rewrite_meta_columns.py sha256"; exit 1; }
for f in project_meta.x1k.final.json project_meta.x1k.final.json.sha256; do
  aws s3 cp $B/dataset-x1k/raw-tools/$f $T/$f --only-show-errors || { echo "ABORT: $f is not in dataset-x1k/raw-tools/ (the user runs x2/U1-upload-x2.sh first)"; exit 1; }
done
(cd $T && sha256sum --quiet -c project_meta.x1k.final.json.sha256) || { echo "ABORT: sidecar sha256"; exit 1; }
[ "$(cut -d' ' -f1 $T/project_meta.x1k.final.json.sha256)" = $WANT_SC ] || { echo "ABORT: the sidecar is not $WANT_SC"; exit 1; }
echo "tools ok: final_merge.py, rewrite_meta_columns.py ($(cat $T/SOURCE)), sidecar $(echo $WANT_SC | cut -c1-16) ($(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' $T/project_meta.x1k.final.json) keys)"
# --- ctp ca113e3 (validate_schema.py)
if [ ! -d $X/ctp ]; then
  aws s3 cp $B/batch2/input/ctp.bundle $X/ctp.bundle --only-show-errors
  aws s3 cp $B/batch2/input/SHA256SUMS $X/batch2.SHA256SUMS --only-show-errors
  (cd $X && grep ' ctp.bundle$' batch2.SHA256SUMS | sha256sum --quiet -c) || { echo "ABORT: ctp.bundle sha256"; exit 1; }
  chown ec2-user: $X/ctp.bundle
  sudo -u ec2-user git clone -q $X/ctp.bundle $X/ctp -b feat/e2e-runner
fi
[ "$(sudo -u ec2-user git -C $X/ctp rev-parse --short HEAD)" = ca113e3 ] || { echo "ABORT: ctp is not ca113e3"; exit 1; }
[ "$(sha256sum $X/ctp/validate_schema.py | cut -d' ' -f1)" = $WANT_VS ] || { echo "ABORT: validate_schema.py is not the ca113e3 one"; exit 1; }
# --- venv
if [ ! -x $X/.venv/bin/python ]; then
  sudo -u ec2-user python3.12 -m venv $X/.venv
  sudo -u ec2-user nice -n 19 $X/.venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5
fi
sudo -u ec2-user $X/.venv/bin/python -I -c 'import duckdb, sys; print("python", sys.version.split()[0], "duckdb", duckdb.__version__)'
chown -R ec2-user:ec2-user $X
echo "R1-x2 done $(date -u +%FT%TZ)"
