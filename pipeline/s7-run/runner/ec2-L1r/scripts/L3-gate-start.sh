# L3-gate-start.sh (big EC2, census L1r): the identity gate of /bL1r/cregit-ec2 (a copy of /data/cregit-ec2 at
# 95cdc88; census-L1r-cregit fetches the bundle cregit-57551d7.bundle, sha256 18b1bf1c..., and checks out
# 57551d7), WANT_PQ 14eb5d72..., a dry-run finalize on the gate output, then start the L1r live timer, the
# firm protection timer and the waiter (it starts census-L1r after census L23 has started, when slots,
# memory, disk, gate and inputs allow). Made from the L23 L3-gate-start.sh (2026-10-12).
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
t0=$(date +%s)
$B/census-L1r-cregit --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 2>&1 | tail -5
echo "gate took $(( $(date +%s) - t0 )) s; last gate line: $(tail -1 /etc/cregit-census/L1r.gate)"
sudo -u ec2-user git -C /bL1r/cregit-ec2 log --oneline -1
ls -l /bL1r/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet | awk '{print $5}'
tail -1 /etc/cregit-census/L1r.gate | grep -q '^CHECK OK' || { echo "GATE FAILED: waiter not started"; exit 1; }
echo "== dry-run finalize on the gate output"
CTP_L=/bL1r/ctp-check OUT_L=/bL1r/libexpat-check/out MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv $B/census-L1r-finalize --dry-run 2>&1 | grep -E 'staged|check ok|DONE|dry run|FAILED' | cut -c1-220
systemctl start census-L1r-live.timer census-L1r-firm.timer census-L1r-wait.service
sleep 75
echo "waiter: $(systemctl is-active census-L1r-wait.service); census-L1r: $(systemctl is-active census-L1r.service); firm timer: $(systemctl is-active census-L1r-firm.timer) ($(cat /run/census-L1r-firm.status 2>/dev/null)); status: $(cut -c1-600 /run/census-L1r-wait.status)"
tail -5 /data/logs/L1r.log 2>/dev/null | cut -c1-250
