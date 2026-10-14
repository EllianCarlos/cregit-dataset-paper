set +e
B=/usr/local/bin; S3=s3://${RUNNER_BUCKET}
rm -rf $B/__pycache__
# inputs
sudo -u ec2-user bash -c 'set -e; mkdir -p ~/batch3L-input; aws s3 cp s3://${RUNNER_BUCKET}/batch3/input/ ~/batch3L-input/ --recursive --only-show-errors; cd ~/batch3L-input && sha256sum -c SHA256SUMS'
echo "inputs rc=$?"
# own ctp clone from the same bundle as batch 2 (feat/e2e-runner ca113e3), own venv
sudo -u ec2-user -i bash -c 'set -e; [ -d ~/ctp-b3L ] || git clone -q /data/input/ctp.bundle ~/ctp-b3L -b feat/e2e-runner; cd ~/ctp-b3L; git log --oneline -1; [ "$(git rev-parse --short HEAD)" = ca113e3 ]; [ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }; .venv/bin/python -c "import duckdb,sys;print(sys.version.split()[0], duckdb.__version__)"; git -C ~/ctp rev-parse HEAD; git rev-parse HEAD; mkdir -p /data/census-2026-10-batch3L'
echo "clone rc=$?"
cat > /home/ec2-user/census-batch3L.cfg <<'C'
# ctp config (CTP_CONFIG) for census batch 3L on the batch 2 instance: cregit 95cdc88, output on the RAID0.
[paths]
cregit_dir = /data/cregit-ec2
output_dir = /data/census-2026-10-batch3L
C
chown ec2-user: /home/ec2-user/census-batch3L.cfg
systemctl daemon-reload
echo "=== test 1: batch 2 finalize, decide only (batch3L not finalized -> no power-off)"
$B/census-batch2-finalize --decide-only | tail -1
echo "=== test 2: batch3L finalize, decide only (batch 2 running -> no power-off)"
$B/census-batch3L-finalize --decide-only | tail -1
echo "=== test 3: batch3L finalize, decide only, other DONE faked by batch2/dryrun/DONE and no units -> would power off"
OTHER_DONE_URL=$S3/batch2/dryrun/DONE OTHER_UNITS= $B/census-batch3L-finalize --decide-only | tail -1
echo "=== test 4: full dry run of the batch3L finalize on the libexpat check output -> batch3L/dryrun/, no power-off"
CTP=/home/ec2-user/ctp-check OUT=/data/ec2-check/out CLOG=/data/logs/check.log CTP_CONFIG=/home/ec2-user/ctp-check.cfg \
  MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv $B/census-batch3L-finalize --dry-run | tail -4
echo "rc=$?"; aws s3 ls $S3/batch3L/dryrun/ --recursive | wc -l
echo "=== test 5: full dry run of the edited batch 2 finalize -> batch2/dryrun/, no power-off"
CTP=/home/ec2-user/ctp-check OUT=/data/ec2-check/out CLOG=/data/logs/check.log CTP_CONFIG=/home/ec2-user/ctp-check.cfg \
  MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv $B/census-batch2-finalize --dry-run | tail -3
echo "rc=$?"
echo "=== start waiter and live timer"
[ -e /home/ec2-user/ctp-b3L/STOP ] && echo "STOP exists!"
systemctl enable --now census-batch3L-live.timer
systemctl start census-batch3L-wait.service
sleep 5; cat /run/census-batch3L-wait.status
sudo -u ec2-user $B/census-batch3L-live; echo "live rc=$?"
aws s3 cp $S3/batch3L/live/progress.txt - | head -12
systemctl is-active census-batch2.service census-batch3L-wait.service census-batch3L.service census-batch3L-live.timer
uptime
