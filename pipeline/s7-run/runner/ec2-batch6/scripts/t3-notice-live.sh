# t3-notice-live.sh: fake spot notice for census-fed-watch (test mode: no STOP in any clone, no
# /run/census-spot-interrupted), then one census-fed-live run; shows the first live line.
set +e
export AWS_PAGER=""; X=$(cat /etc/cregit-census/fed/half)
echo "TEST notice $(date -u +%FT%TZ)" > /run/census-fed-fake-spot-notice; sleep 20
echo "fake file gone: $([ -e /run/census-fed-fake-spot-notice ] && echo no || echo yes); interrupted flag: $([ -e /run/census-spot-interrupted ] && echo PRESENT || echo absent); test STOPs: $(ls /run/census-fed-STOP.test.* 2>/dev/null | wc -l); journal: $(journalctl -u census-fed-watch --since -2min --no-pager -o cat | tail -2 | tr '\n' ' ' | cut -c1-200)"
aws s3 ls s3://${RUNNER_BUCKET}/feed/$X/live/
systemctl start census-fed-live.service; echo "live: $(systemctl show census-fed-live.service -p Result --value)"
aws s3 cp s3://${RUNNER_BUCKET}/feed/$X/live/progress.txt - | head -8 | cut -c1-260
