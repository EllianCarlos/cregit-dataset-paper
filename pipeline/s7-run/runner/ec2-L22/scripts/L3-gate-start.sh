# L3-gate-start.sh (big EC2, census L22): check /bL22/cregit-ec2 out at 1f17663 (bundle from S3) and run its identity
# gate (WANT_PQ 14eb5d72...), a dry-run finalize on the gate's output, then start the L22 live timer
# and the waiter (it holds the start until batch6L has started, slots, memory, disk, gate and inputs allow).
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
t0=$(date +%s)
$B/census-L22-cregit --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 2>&1 | tail -5
echo "gate took $(( $(date +%s) - t0 )) s; last gate line: $(tail -1 /etc/cregit-census/L22.gate)"
sudo -u ec2-user git -C /bL22/cregit-ec2 log --oneline -1
ls -l /bL22/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet | awk '{print $5}'
tail -1 /etc/cregit-census/L22.gate | grep -q '^CHECK OK' || { echo "GATE FAILED: waiter not started"; exit 1; }
echo "== dry-run finalize on the gate output"
CTP_L=/bL22/ctp-check OUT_L=/bL22/libexpat-check/out MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv $B/census-L22-finalize --dry-run 2>&1 | grep -E 'staged|check ok|DONE|dry run|FAILED' | cut -c1-220
systemctl start census-L22-live.timer census-L22-wait.service
sleep 20
echo "waiter: $(systemctl is-active census-L22-wait.service); census-L22: $(systemctl is-active census-L22.service); status: $(cut -c1-420 /run/census-L22-wait.status)"
