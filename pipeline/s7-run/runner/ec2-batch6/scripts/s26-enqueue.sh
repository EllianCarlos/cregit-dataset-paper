# s26-enqueue.sh (spot a ONLY; run with I=<spot a id> ~/s3-work/ec2-batch23/scripts/ssm.sh after upload-batch26.sh
# printed ALL OK): set the cregit commit of workload batch26 (57551d7, the git blame -C100 time limit; bundle
# cregit-57551d7.bundle; libexpat gate 14eb5d72, unchanged), under the feeder lock, then queue the batch26
# part (census-fed-enqueue takes the lock itself). Made from s25-enqueue.sh (2026-10-14). User decision
# 2026-10-14 ~16:40 UTC "yes to mutt": gitlab.com/muttmua/mutt (a DP8L v4 near miss C) goes into v1 as batch 26,
# on spot a: part a1 with 1 worker; the script refuses on half b.
set -uo pipefail
F=/etc/cregit-census/fed
X=$(cat $F/half)
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag) half $X"
[ "$X" = a ] || { echo "ABORT: this is half $X; batch 26 runs on spot a only: nothing changed"; exit 1; }
[ -e /run/census-spot-interrupted ] && { echo "ABORT: spot interruption notice: nothing changed"; exit 1; }
grep -q "^batch26 " $F/queue 2>/dev/null && echo "note: batch26 parts are already queued (enqueue skips them)"
(
  exec 9>$F/lock; flock -w 3000 9 || { echo "LOCK TIMEOUT: nothing changed"; exit 1; }
  /usr/local/bin/census-fed-workload batch26 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 | cut -c1-80
) || exit 1
/usr/local/bin/census-fed-workload batch26 --show
/usr/local/bin/census-fed-enqueue batch26 $X 2>&1 | grep -v "^queued [0-9]* parts"; echo "rc=${PIPESTATUS[0]}"
echo "queue: $(grep -c . $F/queue) parts; first: $(head -1 $F/queue); last 6: $(tail -6 $F/queue | tr "
" ",")"
echo "censuses: $(tr "
" " " < /etc/cregit-census/censuses)  slots: $(cat $F/slots 2>/dev/null || echo default) / $(cat $F/worker_slots 2>/dev/null || echo default)  PAUSE: $(cat $F/PAUSE 2>/dev/null || echo none)"
echo "feeder: $(cat /run/census-fed-feeder.status)"
