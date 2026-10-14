set -uo pipefail
echo '{"action": "terminate", "time": "2099-01-01T00:00:00Z", "note": "FAKE notice for the watcher test"}' > /run/census-fake-spot-notice
for i in $(seq 1 30); do [ -e /run/census-fake-spot-notice ] || break; sleep 2; done
sleep 5
echo "fake file left: $([ -e /run/census-fake-spot-notice ] && echo yes || echo no)"
ls -la /run/census-STOP.test.* 2>&1
for k in 1 2 3 4; do [ -e /data$k/ctp/STOP ] && echo "REAL STOP in /data$k/ctp (bad)" || echo "no STOP in /data$k/ctp (good)"; done
rm -f /run/census-STOP.test.*
systemctl is-active census-b3@a1.service census-b3@a2.service census-b3@a3.service census-b3@a4.service census-b3-watch.service
journalctl -u census-b3-watch.service --no-pager -n 6 -o short-iso
aws s3 ls s3://${RUNNER_BUCKET}/batch3/a/live/
aws s3 cp s3://${RUNNER_BUCKET}/batch3/a/live/INTERRUPTED.test - | head -12 | cut -c1-180
