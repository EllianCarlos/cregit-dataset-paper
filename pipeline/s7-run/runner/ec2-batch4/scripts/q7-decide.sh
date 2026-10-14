set +e
export AWS_PAGER=""
B=/usr/local/bin
dcount() { for p in $(ps -eo pid=,stat= | awk '$2 ~ /^D/ {print $1}'); do sed 's/.*\///' /proc/$p/cgroup 2>/dev/null; done | sort | uniq -c | tr '\n' ' '; }
[ -e /run/census-batch4-hold ] && echo "hold still present!" || echo "hold released"
$B/census-batch2-finalize --decide-only | tail -1
$B/census-batch3L-finalize --decide-only | tail -1
$B/census-batch4-finalize --decide-only | tail -1
$B/census-other-done batch4; echo "rc=$?"
sha256sum $B/census-other-done $B/census-batch4-finalize $B/census-batch4-live | cut -c1-16
for i in 1 2 3; do echo "D $(date -u +%T): $(dcount)"; sleep 20; done
for p in $(pgrep -f tokenWorker.pl); do echo "$(sed 's/.*\///' /proc/$p/cgroup) $(readlink /proc/$p/cwd)"; done | sort | uniq -c
systemctl is-active census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch2.service census-batch3L.service | tr '\n' ' '; echo; uptime
