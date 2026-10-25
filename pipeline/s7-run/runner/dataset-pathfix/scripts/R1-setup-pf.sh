#!/usr/bin/env bash
# R1-setup-pf.sh (the path-fix instance, root, through ssm-run-pf.sh; idempotent): the machine
# layout and the 2 part trees of the cregit path-fix rerun. Copy of
# ~/s3-work/dataset-x1k/scripts/R1-setup.sh with these changes:
#   - cregit 14b8db4 (fix/path-quoting = 57551d7 + the fix) from cregit-14b8db4.bundle (sha256
#     b3d2c139...; the bundle needs 95cdc88, which every copy of /data/cregit-ec2 has);
#   - 2 parts (user decision 2026-10-20: no AliSQL, so part 3 goes away): p1 (v1 rows) on
#     /data1/pf, p2 (x1k rows) on /data2/pf; config /etc/dataset-pathfix/pK.cfg;
#   - at least 2 instance-store disks (all disks get an XFS; the parts use /data1 and /data2).
# The rest as R1-setup.sh: one XFS per instance-store disk at /data1..N, /data -> /data1;
# /data/input = batch2/input (ctp.bundle with ca113e3, the libexpat check manifest and sidecar),
# sha256 checked; /data/cregit-ec2 = the checked cregit tree of the AMI + the no-op build step; per
# part its own ctp clone (ca113e3, Python 3.12 venv with duckdb 1.5.5) and its own cregit copy
# (empty tokenizeByBlobId/build and blameRepo/build) at 14b8db4. The paths are fixed here, before
# any start (blobExec stores the cregit path).
# It never runs on an instance of the refuse list (instance id check), and starts no run.
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}) echo "ABORT: $IID is on the refuse list"; exit 1 ;; esac
B=s3://${RUNNER_BUCKET}
CREGIT_COMMIT=14b8db468e4f6565fab5692a1ab1c3066d12f371
BUNDLE=cregit-14b8db4.bundle
BUNDLE_SHA=b3d2c139f53741388721a36a6f40b53fcc6fbd586a9502b98c9f1bc17c49d916
E=/etc/dataset-pathfix
NPARTS=2
echo "== $(date -u +%FT%TZ) $IID $(curl -s -m 2 -H "X-aws-ec2-metadata-token: $(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" http://169.254.169.254/latest/meta-data/instance-type) $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB"
for i in $(seq 1 40); do dnf -y -q install git python3.12 python3.12-pip xfsprogs tar >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
# --- layout (layout-fsN.sh), only once
if ! mountpoint -q /data1; then
  DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
  [ "$(echo $DEVS | wc -w)" -ge $NPARTS ] || { echo "ABORT: expected at least $NPARTS instance-store disks, got: $DEVS"; exit 1; }
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
bf=/data/input/$BUNDLE
[ -f $bf ] && [ "$(sha256sum $bf | cut -d' ' -f1)" = $BUNDLE_SHA ] || aws s3 cp $B/cregit/$BUNDLE $bf --only-show-errors
[ "$(sha256sum $bf | cut -d' ' -f1)" = $BUNDLE_SHA ] || { echo "ABORT: cregit bundle sha256"; exit 1; }
chmod 644 $bf; chown -R ec2-user:ec2-user /data/input
echo "inputs ok: batch2/input ($(wc -l < /data/input/SHA256SUMS) files), $BUNDLE"
# --- the checked cregit tree of the AMI, as restore-inputs.sh
[ -d /data/cregit-ec2 ] || cp -a /opt/cregit-ec2.checked /data/cregit-ec2
chown -R ec2-user:ec2-user /data/cregit-ec2
sudo -u ec2-user -i bash /home/ec2-user/build.sh 2>&1 | grep -v -e '^• ' -e '^✓' | tail -4
echo "template cregit: $(sudo -u ec2-user git -C /data/cregit-ec2 rev-parse --short HEAD)"
# --- the part trees
for K in $(seq 1 $NPARTS); do
  P=/data$K/pf; C=$P/ctp; D=$P/cregit-ec2; O=$P/out
  mkdir -p $P/logs $P/uploaded $O; chown -R ec2-user:ec2-user $P
  cat > /home/ec2-user/pf-ctp-p$K.sh <<U
set -e
[ -d $C ] || git clone -q /data/input/ctp.bundle $C -b feat/e2e-runner
cd $C; [ "\$(git rev-parse --short HEAD)" = ca113e3 ]
[ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }
.venv/bin/python -c 'import duckdb, sys; print("p$K ctp", sys.version.split()[0], "duckdb", duckdb.__version__)'
U
  chown ec2-user: /home/ec2-user/pf-ctp-p$K.sh
  sudo -u ec2-user bash /home/ec2-user/pf-ctp-p$K.sh
  if [ ! -e $D ]; then
    T=$P/.cregit-copy; [ -e $T ] && mv $T $T.old.$(date +%s); mkdir -p $T
    tar -C /data/ -cf - --exclude='cregit-ec2/tokenizeByBlobId/build' --exclude='cregit-ec2/blameRepo/build' cregit-ec2 | tar -C $T -xpf -
    mv $T/cregit-ec2 $D; rmdir $T
    mkdir -p $D/tokenizeByBlobId/build $D/blameRepo/build; chown ec2-user: $D $D/tokenizeByBlobId/build $D/blameRepo/build
  fi
  if [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" != $CREGIT_COMMIT ]; then
    [ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || { echo "ABORT: $D is dirty"; exit 1; }
    cat > /home/ec2-user/pf-cregit-p$K.sh <<U
set -e; cd $D; git bundle verify -q $bf >/dev/null 2>&1; git fetch -q $bf '+refs/heads/*:refs/remotes/fed-bundle/*'; git checkout -q --detach $CREGIT_COMMIT
U
    chown ec2-user: /home/ec2-user/pf-cregit-p$K.sh; sudo -u ec2-user bash /home/ec2-user/pf-cregit-p$K.sh
  fi
  [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = $CREGIT_COMMIT ] || { echo "ABORT: $D is not at $CREGIT_COMMIT"; exit 1; }
  [ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || { echo "ABORT: $D is dirty after the checkout"; exit 1; }
  for f in blameRepo/blameRepoFiles.pl blameRepo/formatBlame.pl; do
    [ -x $D/$f ] || { echo "ABORT: $D/$f is not executable"; exit 1; }
  done
  printf '# ctp config (CTP_CONFIG) for path-fix part p%s: own cregit copy %s (14b8db4), output %s on XFS /data%s.\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' \
    $K $D $O $K $D $O > $E/p$K.cfg
  chmod 644 $E/p$K.cfg
  echo "p$K: fs $(findmnt -no SOURCE /data$K) fsid=$(stat -f -c %i /data$K) | ctp $(sudo -u ec2-user git -C $C rev-parse --short HEAD) | cregit $(sudo -u ec2-user git -C $D rev-parse --short HEAD) build=$(ls -A $D/tokenizeByBlobId/build | wc -l)"
done
echo "R1 done $(date -u +%FT%TZ)"
