# L3-gate-start.sh (big EC2, census L23): the identity gate of /bL23/cregit-ec2 (a copy of /data/cregit-ec2 at
# 95cdc88; census-L23-cregit fetches the bundle cregit-57551d7.bundle, sha256 18b1bf1c..., and checks out
# 57551d7), WANT_PQ 14eb5d72..., a dry-run finalize on the gate output, then start the L23 live timer and the
# waiter (it starts census-L23 when slots, memory, disk, gate and inputs allow). Made from the L7-20b
# L3-gate-start.sh (2026-10-11), without the split watcher.
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
t0=$(date +%s)
$B/census-L23-cregit --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 2>&1 | tail -5
echo "gate took $(( $(date +%s) - t0 )) s; last gate line: $(tail -1 /etc/cregit-census/L23.gate)"
sudo -u ec2-user git -C /bL23/cregit-ec2 log --oneline -1
ls -l /bL23/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet | awk '{print $5}'
tail -1 /etc/cregit-census/L23.gate | grep -q '^CHECK OK' || { echo "GATE FAILED: waiter not started"; exit 1; }
echo "== dry-run finalize on the gate output"
CTP_L=/bL23/ctp-check OUT_L=/bL23/libexpat-check/out MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv $B/census-L23-finalize --dry-run 2>&1 | grep -E 'staged|check ok|DONE|dry run|FAILED' | cut -c1-220
systemctl start census-L23-live.timer census-L23-wait.service
sleep 75
echo "waiter: $(systemctl is-active census-L23-wait.service); census-L23: $(systemctl is-active census-L23.service); status: $(cut -c1-460 /run/census-L23-wait.status)"
tail -5 /data/logs/L23.log 2>/dev/null | cut -c1-250
