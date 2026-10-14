# s6-arm.sh: arm the feeder on this spot instance: queue the batch 6 parts of the half with the cregit
# commit "pending" (the feeder starts none of them until census-fed-workload batch6 --commit ... is run),
# then the feeder timer, watcher, upload and live timers (census-fed-enqueue starts them).
set -uo pipefail
X=$(. /etc/cregit-census/s5/batch.env; echo $HALF)
/usr/local/bin/census-fed-enqueue batch6 $X || exit 1
/usr/local/bin/census-fed-workload batch6 --show
sleep 70
echo "feeder: $(cat /run/census-fed-feeder.status 2>/dev/null)"
systemctl is-active census-fed-feeder.timer census-fed-watch.service census-fed-upload.timer census-fed-live.timer | tr '\n' ' '; echo
echo "censuses: $(tr '\n' ' ' < /etc/cregit-census/censuses)  queue: $(tr '\n' ',' < /etc/cregit-census/fed/queue)  started: [$(cat /etc/cregit-census/fed/started)]"
/usr/local/bin/census-spot-decide; echo "decide rc=$?"
