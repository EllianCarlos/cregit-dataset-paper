# p1-spot-probe.sh (read-only): the fed queue, the workload files and the enqueue tool of a spot.
set -uo pipefail
F=/etc/cregit-census/fed
echo "== $(date -u +%FT%TZ) half $(cat $F/half)"
echo "queue: $(grep -c . $F/queue) parts; last 6: $(tail -6 $F/queue | tr '\n' ',')"
echo "started: $(grep -c . $F/started)"
for w in batch21 batch22 batch23; do echo "--- wl/$w.env"; cat $F/wl/$w.env 2>/dev/null || echo "(none)"; done
grep -l 57551d7 $F/wl/*.env 2>/dev/null | xargs -r -n1 basename | tr '\n' ' '; echo "<- wl files at 57551d7"
ls /data/input/ 2>/dev/null | head -30
echo "--- census-fed-enqueue head"; sed -n 1,30p /usr/local/bin/census-fed-enqueue
echo "--- census-fed-workload head"; sed -n 1,25p /usr/local/bin/census-fed-workload
echo "feeder: $(cat /run/census-fed-feeder.status)"
