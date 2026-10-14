# Batch 4 setup on the batch 2 instance: 3 sparse XFS images on /data, loop-mounted at /b4p1..3
# (each its own superblock, so its own s_vfs_rename_mutex), inputs, ctp clones, configs.
set -euo pipefail
export AWS_PAGER=""
S3=s3://${RUNNER_BUCKET}
mkdir -p /data/loop
for k in 1 2 3; do
  img=/data/loop/b4p$k.img; mp=/b4p$k
  [ -e $img ] || { truncate -s 1200G $img; mkfs.xfs -q -L b4p$k $img; }
  mkdir -p $mp
  grep -q "^$img " /etc/fstab || echo "$img $mp xfs loop,noatime,discard,nofail,x-systemd.requires-mounts-for=/data 0 0" >> /etc/fstab
  mountpoint -q $mp || mount $mp
  chown ec2-user:ec2-user $mp
done
echo "== mounts"
for k in 1 2 3; do echo "$(findmnt -no TARGET,SOURCE,FSTYPE,OPTIONS /b4p$k)  fsid=$(stat -f -c %i /b4p$k) dev=$(stat -c %d /b4p$k) size=$(df -BG --output=size /b4p$k | tail -1)"; done
echo "/data fsid=$(stat -f -c %i /data) dev=$(stat -c %d /data)"
ls -ls /data/loop/
echo "== discard test on /b4p3 (2 GiB written, then removed)"
dd if=/dev/zero of=/b4p3/t bs=1M count=2048 status=none oflag=direct; sync
echo "image blocks after write: $(du -BM /data/loop/b4p3.img | cut -f1)"
rm /b4p3/t; sync; sleep 5
echo "image blocks after rm:    $(du -BM /data/loop/b4p3.img | cut -f1)"
echo "== inputs"
sudo -u ec2-user bash -c 'set -e; export AWS_PAGER=""; mkdir -p ~/batch4-input; aws s3 cp s3://${RUNNER_BUCKET}/batch4/input/ ~/batch4-input/ --recursive --only-show-errors; cd ~/batch4-input && sha256sum -c SHA256SUMS'
echo "== ctp clones"
for k in 1 2 3; do
  sudo -u ec2-user bash -c "set -e; C=/b4p$k/ctp; [ -d \$C ] || git clone -q /home/ec2-user/batch2-input/ctp.bundle \$C -b feat/e2e-runner; cd \$C; [ \"\$(git rev-parse --short HEAD)\" = ca113e3 ]; [ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }; echo \"p$k: \$(git rev-parse HEAD) \$(.venv/bin/python -c 'import duckdb,sys;print(sys.version.split()[0], duckdb.__version__)')\"; mkdir -p /b4p$k/census-2026-10-batch4"
  printf '# ctp config (CTP_CONFIG) for census batch 4 part p%s on the batch 2 instance: cregit 95cdc88, output on loop XFS /b4p%s.\n[paths]\ncregit_dir = /data/cregit-ec2\noutput_dir = /b4p%s/census-2026-10-batch4\n' $k $k $k > /home/ec2-user/census-batch4p$k.cfg
  chown ec2-user: /home/ec2-user/census-batch4p$k.cfg
done
printf '# libexpat identity check for batch 4 on /b4p1 (scratch output).\n[paths]\ncregit_dir = /data/cregit-ec2\noutput_dir = /b4p1/libexpat-check/out\n' > /home/ec2-user/census-batch4-check.cfg
chown ec2-user: /home/ec2-user/census-batch4-check.cfg
git -C /b4p1/ctp rev-parse HEAD; git -C /home/ec2-user/ctp rev-parse HEAD
echo "== units still running"; systemctl is-active census-batch2.service census-batch3L.service
