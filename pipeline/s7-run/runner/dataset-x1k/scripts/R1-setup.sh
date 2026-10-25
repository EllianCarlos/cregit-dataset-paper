#!/usr/bin/env bash
# R1-setup.sh (the x1k instance, root, through ssm.sh; idempotent): the machine layout and the 4
# part trees of the x1k test run, with the tools of the v1 spot parts (census-fed-part-init):
#   - one XFS per instance-store disk at /data1../data4, /data -> /data1 (layout-fsN.sh of batch 3a;
#     own superblock per part, so its own rename lock);
#   - /data/input: the batch 2 code inputs (ctp.bundle with ca113e3, the libexpat check manifest
#     and sidecar), sha256 checked; cregit-57551d7.bundle (sha256 18b1bf1c...);
#   - /data/cregit-ec2: the checked cregit tree of the AMI (/opt/cregit-ec2.checked) + the no-op
#     build step of batch 2 (/home/ec2-user/build.sh);
#   - part pK (K = 1..4) on /dataK/x1k: its own ctp clone ctp/ (ca113e3, Python 3.12 venv with
#     duckdb 1.5.5), its own cregit copy cregit-ec2/ (empty tokenizeByBlobId/build and
#     blameRepo/build) checked out at 57551d7, out/, logs/, uploaded/; config /etc/dataset-x1k/pK.cfg.
#     The paths are fixed here, before any start (blobExec stores the cregit path).
# It never runs on spot a or the big EC2 (instance id check), and starts no run.
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}) echo "ABORT: $IID is spot a or the big EC2"; exit 1 ;; esac
B=s3://${RUNNER_BUCKET}
CREGIT_COMMIT=57551d7ad82a784615c1490623d72cb9dc994ba1
BUNDLE_SHA=18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e
E=/etc/dataset-x1k
echo "== $(date -u +%FT%TZ) $IID $(curl -s -m 2 -H "X-aws-ec2-metadata-token: $(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/instance-type) $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB"
for i in $(seq 1 40); do dnf -y -q install git python3.12 python3.12-pip xfsprogs tar >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
# --- layout (layout-fsN.sh), only once
if ! mountpoint -q /data1; then
  DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
  # 4 disks on c6id, 6 on i4i.24xlarge: every disk gets its XFS; the 4 parts use /data1../data4.
  [ "$(echo $DEVS | wc -w)" -ge 4 ] || { echo "ABORT: expected at least 4 instance-store disks, got: $DEVS"; exit 1; }
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
mkdir -p /data/input /data/logs $E; chmod 755 $E
chown ec2-user:ec2-user /data[0-9]* /data/input /data/logs
df -h /data[0-9]* | tail -n +2
# --- inputs of the v1 spot parts
if ! (cd /data/input && sha256sum --quiet -c SHA256SUMS 2>/dev/null); then
  aws s3 cp $B/batch2/input/ /data/input/ --recursive --only-show-errors
  (cd /data/input && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: batch2 inputs sha256"; exit 1; }
fi
bf=/data/input/cregit-57551d7.bundle
[ -f $bf ] && [ "$(sha256sum $bf | cut -d' ' -f1)" = $BUNDLE_SHA ] || aws s3 cp $B/cregit/cregit-57551d7.bundle $bf --only-show-errors
[ "$(sha256sum $bf | cut -d' ' -f1)" = $BUNDLE_SHA ] || { echo "ABORT: cregit bundle sha256"; exit 1; }
chmod 644 $bf; chown -R ec2-user:ec2-user /data/input
echo "inputs ok: batch2/input ($(wc -l < /data/input/SHA256SUMS) files), cregit-57551d7.bundle"
# --- the checked cregit tree of the AMI, as restore-inputs.sh
[ -d /data/cregit-ec2 ] || cp -a /opt/cregit-ec2.checked /data/cregit-ec2
chown -R ec2-user:ec2-user /data/cregit-ec2
sudo -u ec2-user -i bash /home/ec2-user/build.sh 2>&1 | grep -v -e '^• ' -e '^✓' | tail -4
echo "template cregit: $(sudo -u ec2-user git -C /data/cregit-ec2 rev-parse --short HEAD)"
# --- the 4 part trees
for K in 1 2 3 4; do
  P=/data$K/x1k; C=$P/ctp; D=$P/cregit-ec2; O=$P/out
  mkdir -p $P/logs $P/uploaded $O; chown -R ec2-user:ec2-user $P
  cat > /home/ec2-user/x1k-ctp-p$K.sh <<U
set -e
[ -d $C ] || git clone -q /data/input/ctp.bundle $C -b feat/e2e-runner
cd $C; [ "\$(git rev-parse --short HEAD)" = ca113e3 ] || [ -f $C/.x1k-patched ]
[ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }
.venv/bin/python -c 'import duckdb, sys; print("p$K ctp", sys.version.split()[0], "duckdb", duckdb.__version__)'
U
  chown ec2-user: /home/ec2-user/x1k-ctp-p$K.sh
  sudo -u ec2-user bash /home/ec2-user/x1k-ctp-p$K.sh
  if [ ! -e $D ]; then
    T=$P/.cregit-copy; [ -e $T ] && mv $T $T.old.$(date +%s); mkdir -p $T
    tar -C /data/ -cf - --exclude='cregit-ec2/tokenizeByBlobId/build' --exclude='cregit-ec2/blameRepo/build' cregit-ec2 | tar -C $T -xpf -
    mv $T/cregit-ec2 $D; rmdir $T
    mkdir -p $D/tokenizeByBlobId/build $D/blameRepo/build; chown ec2-user: $D $D/tokenizeByBlobId/build $D/blameRepo/build
  fi
  if [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" != $CREGIT_COMMIT ]; then
    [ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || { echo "ABORT: $D is dirty"; exit 1; }
    cat > /home/ec2-user/x1k-cregit-p$K.sh <<U
set -e; cd $D; git bundle verify -q $bf >/dev/null 2>&1; git fetch -q $bf '+refs/heads/*:refs/remotes/fed-bundle/*'; git checkout -q --detach $CREGIT_COMMIT
U
    chown ec2-user: /home/ec2-user/x1k-cregit-p$K.sh; sudo -u ec2-user bash /home/ec2-user/x1k-cregit-p$K.sh
  fi
  [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = $CREGIT_COMMIT ] || { echo "ABORT: $D is not at $CREGIT_COMMIT"; exit 1; }
  [ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || { echo "ABORT: $D is dirty after the checkout"; exit 1; }
  printf '# ctp config (CTP_CONFIG) for x1k part p%s: own cregit copy %s (57551d7), output %s on XFS /data%s.\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' \
    $K $D $O $K $D $O > $E/p$K.cfg
  chmod 644 $E/p$K.cfg
  echo "p$K: fs $(findmnt -no SOURCE /data$K) fsid=$(stat -f -c %i /data$K) | ctp $(sudo -u ec2-user git -C $C rev-parse --short HEAD) | cregit $(sudo -u ec2-user git -C $D rev-parse --short HEAD) build=$(ls -A $D/tokenizeByBlobId/build | wc -l)"
done
echo "R1 done $(date -u +%FT%TZ)"
