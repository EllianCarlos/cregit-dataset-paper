# s24-enqueue.sh (spot b ONLY; run with I=<spot b id> ~/s3-work/ec2-batch23/scripts/ssm.sh after upload-batch24.sh
# printed ALL OK): set the cregit commit of workload batch24 (57551d7, the git blame -C100 time limit; bundle
# cregit-57551d7.bundle; libexpat gate 14eb5d72, unchanged), under the feeder lock, then queue the batch24
# parts (census-fed-enqueue takes the lock itself). Made from s23-enqueue.sh (2026-10-13). User decision
# 2026-10-13 ~12:35 UTC: the 32 not-started L7-20b rows (all L) run on spot b as 5 parts of 3 workers
# (b1-b5); the script refuses on half a. Run it only while /bL7b/ctp/STOP exists on the big EC2.
set -uo pipefail
F=/etc/cregit-census/fed
X=$(cat $F/half)
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag) half $X"
[ "$X" = b ] || { echo "ABORT: this is half $X; batch 23 runs on spot b only: nothing changed"; exit 1; }
[ -e /run/census-spot-interrupted ] && { echo "ABORT: spot interruption notice: nothing changed"; exit 1; }
grep -q "^batch24 " $F/queue 2>/dev/null && echo "note: batch24 parts are already queued (enqueue skips them)"
(
  exec 9>$F/lock; flock -w 3000 9 || { echo "LOCK TIMEOUT: nothing changed"; exit 1; }
  /usr/local/bin/census-fed-workload batch24 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 | cut -c1-80
) || exit 1
/usr/local/bin/census-fed-workload batch24 --show
/usr/local/bin/census-fed-enqueue batch24 $X 2>&1 | grep -v "^queued [0-9]* parts"; echo "rc=${PIPESTATUS[0]}"
echo "queue: $(grep -c . $F/queue) parts; first: $(head -1 $F/queue); last 6: $(tail -6 $F/queue | tr "
" ",")"
echo "censuses: $(tr "
" " " < /etc/cregit-census/censuses)  slots: $(cat $F/slots 2>/dev/null || echo default) / $(cat $F/worker_slots 2>/dev/null || echo default)  PAUSE: $(cat $F/PAUSE 2>/dev/null || echo none)"
echo "feeder: $(cat /run/census-fed-feeder.status)"
