set +e
export AWS_PAGER=""
B=/usr/local/bin
$B/census-batch4-guard
for k in 1 2 3; do [ -e /b4p$k/ctp/STOP ] && { echo "STOP in /b4p$k/ctp: not starting"; exit 1; }; done
systemctl is-active --quiet census-batch2.service && systemctl is-active --quiet census-batch3L.service || echo "note: batch2/3L state changed"
systemctl enable --now census-batch4-guard.timer census-batch4-live.timer 2>&1 | tail -2
for k in 1 2 3; do systemctl start census-batch4p$k.service; echo "started census-batch4p$k at $(date -u +%FT%TZ)"; done
sleep 60
systemctl is-active census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch4-live.timer census-batch4-guard.timer census-batch2.service census-batch3L.service | tr '\n' ' '; echo
for k in 1 2 3; do tail -n 2 /data/logs/batch4p$k.log | cut -c1-200; done
sudo -u ec2-user $B/census-batch4-live; aws s3 cp s3://${RUNNER_BUCKET}/batch4/live/progress.txt - | head -2
systemctl list-timers 'census*' --no-pager | head -8
