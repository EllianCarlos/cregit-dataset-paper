# L3-gate-start.sh (big EC2, census L7-20b): the identity gate of /bL7b/cregit-ec2 (already at 1f17663, copied
# from /bL7/cregit-ec2; the bundle is used only if HEAD differs), WANT_PQ 14eb5d72..., a dry-run finalize on
# the gate output, then start the L7-20b live timer, the waiter (it starts census-L7-20b when slots, memory,
# disk, gate, inputs and the split check allow) and the split watcher timer.
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
t0=$(date +%s)
$B/census-L7-20b-cregit --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 2>&1 | tail -5
echo "gate took $(( $(date +%s) - t0 )) s; last gate line: $(tail -1 /etc/cregit-census/L7-20b.gate)"
sudo -u ec2-user git -C /bL7b/cregit-ec2 log --oneline -1
ls -l /bL7b/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet | awk '{print $5}'
tail -1 /etc/cregit-census/L7-20b.gate | grep -q '^CHECK OK' || { echo "GATE FAILED: waiter and split watcher not started"; exit 1; }
echo "== dry-run finalize on the gate output"
CTP_L=/bL7b/ctp-check OUT_L=/bL7b/libexpat-check/out MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv $B/census-L7-20b-finalize --dry-run 2>&1 | grep -E 'staged|check ok|DONE|dry run|FAILED' | cut -c1-220
systemctl start census-L7-20b-live.timer census-L7-20b-wait.service census-L7-20-split.timer
sleep 75
echo "waiter: $(systemctl is-active census-L7-20b-wait.service); census-L7-20b: $(systemctl is-active census-L7-20b.service); status: $(cut -c1-460 /run/census-L7-20b-wait.status)"
echo "split timer: $(systemctl is-active census-L7-20-split.timer); $(cat /run/census-L7-20-split.status | cut -c1-300)"
tail -5 /data/logs/L7-20b.log 2>/dev/null | cut -c1-250
