set +e
export AWS_PAGER=""
B=/usr/local/bin; R=/data/logs/batch4-restart-20261009.txt
dcount() { for p in $(ps -eo pid=,stat= | awk '$2 ~ /^D/ {print $1}'); do sed 's/.*\///' /proc/$p/cgroup 2>/dev/null; done | sort | uniq -c | tr '\n' ' '; }
echo "tree diff line: $(diff -rq --no-dereference -x build -x .devenv /data/cregit-ec2 /b4p1/cregit-ec2 2>&1 | head -3)"
echo "D before ($(date -u +%T)): $(dcount)"
echo "perl tokenWorkers per cwd before: $(for p in $(pgrep -f tokenWorker.pl); do readlink /proc/$p/cwd; done | sort | uniq -c | tr '\n' ' ')"
[ -e /run/census-batch4-hold ] || { echo "no hold: abort"; exit 1; }
{ echo "== $(date -u +%FT%TZ) still running, terminated by SIGTERM to ctp (STOP set, so it terminates the running projects)"
  for k in 1 2 3; do echo "p$k: $(grep '♥' /data/logs/batch4p$k.log | tail -1 | sed 's/.*running: //; s/ |.*//')"; done; } >> $R
tail -4 $R
for k in 1 2 3; do systemctl is-active --quiet census-batch4p$k.service && systemctl kill --kill-whom=main --signal=SIGTERM census-batch4p$k.service; done
for i in $(seq 1 30); do
  act=$(for k in 1 2 3; do systemctl is-active --quiet census-batch4p$k.service && echo p$k; done | tr '\n' ' ')
  [ -z "$act" ] && break
  [ $i = 6 ] && for k in 1 2 3; do systemctl is-active --quiet census-batch4p$k.service && systemctl kill --kill-whom=main --signal=SIGTERM census-batch4p$k.service; done
  sleep 10
done
act=$(for k in 1 2 3; do systemctl is-active --quiet census-batch4p$k.service && echo p$k; done | tr '\n' ' ')
if [ -n "$act" ]; then echo "still active after 5 min: $act -> systemctl stop"; for p in $act; do systemctl stop census-batch4$p.service; done; fi
echo "parts stopped at $(date -u +%T): $(systemctl is-active census-batch4p1.service census-batch4p2.service census-batch4p3.service | tr '\n' ' ')"
for k in 1 2 3; do grep -e terminating -e "census finished" /data/logs/batch4p$k.log | tail -5 | cut -c1-160; done
echo "finalize runs during the stop:"; journalctl -u census-batch4-finalize.service --since "-15min" --no-pager -o cat | grep -e hold -e start | tail -4
aws s3 ls s3://${RUNNER_BUCKET}/batch4/final/ || echo "batch4/final/ empty (good)"
echo "== restart"
for k in 1 2 3; do rm -f /b4p$k/ctp/STOP; done
rm -f /run/census-batch4-hold
for k in 1 2 3; do ls /b4p$k/cregit-ec2/tokenizeByBlobId/build | wc -l; done | tr '\n' ' '; echo "(build/ entries before restart)"
for k in 1 2 3; do systemctl start census-batch4p$k.service; echo "started census-batch4p$k at $(date -u +%T)"; done
systemctl show census-batch4p1.service census-batch4p2.service census-batch4p3.service -p OOMPolicy | tr '\n' ' '; echo
sleep 120
echo "after 2 min: $(systemctl is-active census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch2.service census-batch3L.service | tr '\n' ' ')"
for k in 1 2 3; do grep -e "▶" /data/logs/batch4p$k.log | tail -4 | cut -c1-170; grep '♥' /data/logs/batch4p$k.log | tail -1 | cut -c1-230; done
echo "perl tokenWorkers per cwd and unit after:"
for p in $(pgrep -f tokenWorker.pl); do echo "$(sed 's/.*\///' /proc/$p/cgroup) $(readlink /proc/$p/cwd)"; done | sort | uniq -c
echo "temp entries per build dir: shared $(ls -A /data/cregit-ec2/tokenizeByBlobId/build | wc -l), b4p1 $(ls -A /b4p1/cregit-ec2/tokenizeByBlobId/build | wc -l), b4p2 $(ls -A /b4p2/cregit-ec2/tokenizeByBlobId/build | wc -l), b4p3 $(ls -A /b4p3/cregit-ec2/tokenizeByBlobId/build | wc -l)"
echo "D after ($(date -u +%T)): $(dcount)"; sleep 60; echo "D after ($(date -u +%T)): $(dcount)"; uptime
sudo -u ec2-user $B/census-batch4-live; aws s3 cp s3://${RUNNER_BUCKET}/batch4/live/progress.txt - | head -1
