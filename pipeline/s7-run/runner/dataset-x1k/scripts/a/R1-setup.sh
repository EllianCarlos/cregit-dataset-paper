#!/usr/bin/env bash
# R1-setup.sh, machine A (root, through scripts/a/ssm-a.sh, which sets X1K_VOLS="1:vol-.. 2:vol-..
# 3:vol-.. 4:vol-.."; idempotent, also after a reclaim): the EBS layout and one tree per long row.
#   - Slot K volume -> /dataK. The device is found by its NVMe serial (= the volume id without "-").
#     A volume with no signature (blkid -p finds nothing) gets mkfs.xfs -L x1k-long-K (no -f). A
#     volume with a file system is only mounted, and only if it is XFS with the label x1k-long-K.
#     Anything else aborts. /data -> /data1. The paths stay the same on every relaunch.
#   - /data/input: the batch 2 code inputs and cregit-57551d7.bundle (sha256 checked; kept on /data1);
#     /data/cregit-ec2: the checked cregit tree of the AMI (kept if it exists).
#   - /data/x1k-long/long.tsv (the 11 rows: slot, blame jobs on 192 vCPU, --memory-limit for step 10
#     and the firm step on >= 700 GiB and on less) and per row a tree T=/dataK/x1k/<p> (link /data/x1k-long/<p>): ctp/ (ca113e3 +
#     Python 3.12 venv, duckdb 1.5.5), cregit-ec2/ (own copy at 57551d7, empty build dirs), out/,
#     logs/, uploaded/, ctp.cfg. A tree that exists is kept (never moved, never cleaned).
# It never runs on spot a or the big EC2, and starts nothing.
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}) echo "ABORT: $IID is spot a or the big EC2"; exit 1 ;; esac
[ -n "${X1K_VOLS:-}" ] || { echo "ABORT: X1K_VOLS is not set (run R1 through scripts/a/ssm-a.sh)"; exit 1; }
B=s3://${RUNNER_BUCKET}
CREGIT_COMMIT=57551d7ad82a784615c1490623d72cb9dc994ba1
BUNDLE_SHA=18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e
L=/data/x1k-long
tok=$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
md() { curl -s -m 2 -H "X-aws-ec2-metadata-token: $tok" http://169.254.169.254/latest/meta-data/$1; }
echo "== $(date -u +%FT%TZ) $IID $(md instance-type) $(md placement/availability-zone) $(md ami-id) $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB; volumes: $X1K_VOLS"
for i in $(seq 1 40); do dnf -y -q install git python3.12 python3.12-pip xfsprogs tar >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
# --- the 4 volumes
for sv in $X1K_VOLS; do
  K=${sv%%:*}; v=${sv#*:}; serial=${v//-/}
  case $K in 1|2|3|4) ;; *) echo "ABORT: bad slot in X1K_VOLS: $sv"; exit 1 ;; esac
  dev=""
  for i in $(seq 1 30); do
    dev=$(lsblk -d -n -o NAME,SERIAL | awk -v s=$serial '$2 == s {print "/dev/" $1}')
    [ -n "$dev" ] && break; sleep 5
  done
  [ -n "$dev" ] || { echo "ABORT: slot $K: no NVMe device with serial $serial (run L2-attach.sh)"; exit 1; }
  set +e; sig=$(blkid -p -o export "$dev" 2>/dev/null); rc=$?; set -e
  if [ $rc = 2 ]; then
    echo "slot $K $v $dev: no signature, mkfs.xfs -L x1k-long-$K"
    mkfs.xfs -q -L x1k-long-$K "$dev"
  elif [ $rc = 0 ]; then
    t=$(echo "$sig" | sed -n 's/^TYPE=//p'); lb=$(echo "$sig" | sed -n 's/^LABEL=//p')
    [ "$t" = xfs ] && [ "$lb" = x1k-long-$K ] || { echo "ABORT: slot $K $v $dev holds TYPE=$t LABEL=$lb, not xfs x1k-long-$K"; exit 1; }
    echo "slot $K $v $dev: XFS x1k-long-$K exists, mount only"
  else
    echo "ABORT: slot $K $v $dev: blkid -p rc=$rc"; exit 1
  fi
  if mountpoint -q /data$K; then
    [ "$(readlink -f "$(findmnt -no SOURCE /data$K)")" = "$(readlink -f $dev)" ] || { echo "ABORT: /data$K is mounted from $(findmnt -no SOURCE /data$K), not $dev"; exit 1; }
  else
    mkdir -p /data$K; mount -o noatime "$dev" /data$K
  fi
  sed -i "\# /data$K #d" /etc/fstab
  echo "UUID=$(blkid -s UUID -o value $dev) /data$K xfs noatime,nofail 0 0" >> /etc/fstab
done
for K in 1 2 3 4; do mountpoint -q /data$K || { echo "ABORT: /data$K is not mounted"; exit 1; }; done
if [ -d /data ] && [ ! -L /data ]; then rmdir /data; fi
ln -sfn /data1 /data
mkdir -p /data/input /data/logs $L /etc/dataset-x1k; chmod 755 /etc/dataset-x1k
chown ec2-user:ec2-user /data1 /data2 /data3 /data4 /data/input /data/logs $L
df -h --output=source,target,size,avail /data1 /data2 /data3 /data4 | tail -n +2
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
[ -d /data/cregit-ec2 ] || cp -a /opt/cregit-ec2.checked /data/cregit-ec2
chown -R ec2-user:ec2-user /data/cregit-ec2
sudo -u ec2-user -i bash /home/ec2-user/build.sh 2>&1 | grep -v -e '^• ' -e '^✓' | tail -4
echo "template cregit: $(sudo -u ec2-user git -C /data/cregit-ec2 rev-parse --short HEAD)"
# --- the rows: name, slot, blame jobs on 192 vCPU (R4 scales by nproc/192), --memory-limit on >= 700 GiB,
# on less. The limit is for step 10 and the firm sort (firm_attribution.py ORDER BY over all token rows;
# at 16GB asuswrt spilled 402 GB for hours, at 400GB it took 16 min). Rows scale with the tokenizable size
# (asuswrt 4,633 MB, about 563 M rows): aws-sdk-rust 1,845 MB, aws-sdk-java 1,023 MB, the 300-650 MB rows.
# 2026-10-20 (user decision "more jobs"): blame jobs of the slow step-7 rows raised: aws-sdk-rust 28->64,
# aws-sdk-java 20->44, metashell 12->20, Retro68 8->20, msgraph-beta 8->12 (total 176 of 192 vCPU with
# tencentcloud 16); the done rows do not matter. R4 writes run.env from this table at each relaunch.
cat > $L/long.tsv.new <<'EOF_long'
RMerl__asuswrt-merlin.ng	1	32	300GB	150GB
awslabs__aws-sdk-rust	2	64	128GB	64GB
notnotype__neuro-book	2	2	24GB	24GB
pur1fying__blue_archive_auto_script	2	2	24GB	24GB
aws__aws-sdk-java	3	44	96GB	48GB
TencentCloud__tencentcloud-sdk-cpp	3	16	48GB	32GB
metashell__metashell	3	20	48GB	32GB
googleapis__google-cloud-rust	4	16	48GB	32GB
Byron__google-apis-rs	4	16	48GB	32GB
microsoftgraph__msgraph-beta-sdk-java	4	12	32GB	24GB
autc04__Retro68	4	20	48GB	32GB
EOF_long
mv -f $L/long.tsv.new $L/long.tsv; chown ec2-user: $L/long.tsv
while IFS=$'\t' read -r -u 3 p K jobs m1 m2; do
  T=/data$K/x1k/$p; C=$T/ctp; D=$T/cregit-ec2
  mkdir -p $T/logs $T/uploaded $T/out; chown ec2-user:ec2-user /data$K/x1k $T $T/logs $T/uploaded $T/out
  ln -sfn $T $L/$p
  cat > /home/ec2-user/x1k-long-ctp.sh <<U
set -e
[ -d $C ] || git clone -q /data/input/ctp.bundle $C -b feat/e2e-runner
cd $C; [ "\$(git rev-parse --short HEAD)" = ca113e3 ]
[ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }
.venv/bin/python -c 'import duckdb'
U
  chown ec2-user: /home/ec2-user/x1k-long-ctp.sh
  sudo -u ec2-user bash /home/ec2-user/x1k-long-ctp.sh || { echo "ABORT: ctp clone or venv of $p"; exit 1; }
  if [ ! -e $D ]; then
    X=$T/.cregit-copy; [ -e $X ] && mv $X $X.old.$(date +%s); mkdir -p $X
    tar -C /data/ -cf - --exclude='cregit-ec2/tokenizeByBlobId/build' --exclude='cregit-ec2/blameRepo/build' cregit-ec2 | tar -C $X -xpf -
    mv $X/cregit-ec2 $D; rmdir $X
    mkdir -p $D/tokenizeByBlobId/build $D/blameRepo/build; chown ec2-user: $D $D/tokenizeByBlobId/build $D/blameRepo/build
  fi
  if [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" != $CREGIT_COMMIT ]; then
    [ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || { echo "ABORT: $D is dirty"; exit 1; }
    echo "set -e; cd $D; git bundle verify -q $bf >/dev/null 2>&1; git fetch -q $bf '+refs/heads/*:refs/remotes/fed-bundle/*'; git checkout -q --detach $CREGIT_COMMIT" > /home/ec2-user/x1k-long-cregit.sh
    chown ec2-user: /home/ec2-user/x1k-long-cregit.sh; sudo -u ec2-user bash /home/ec2-user/x1k-long-cregit.sh
  fi
  [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = $CREGIT_COMMIT ] || { echo "ABORT: $D is not at $CREGIT_COMMIT"; exit 1; }
  [ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || { echo "ABORT: $D is dirty after the checkout"; exit 1; }
  printf '# ctp config (CTP_CONFIG) of x1k long row %s: own cregit copy %s (57551d7), output %s on /data%s.\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' \
    $p $D $T/out $K $D $T/out > $T/ctp.cfg
  chmod 644 $T/ctp.cfg
  st="new"; [ -f $T/out/$p/pipeline.log ] && st="has pipeline.log"; [ -e $T/uploaded/$p ] && st="uploaded"
  echo "$p: /data$K $(findmnt -no SOURCE /data$K) | ctp $(sudo -u ec2-user git -C $C rev-parse --short HEAD)$([ -f $C/.x1k-patched ] && echo +no-firm) | cregit $(sudo -u ec2-user git -C $D rev-parse --short HEAD) | $st | out $(du -sh $T/out | cut -f1)"
done 3< $L/long.tsv
echo "R1 (machine A) done $(date -u +%FT%TZ)"
