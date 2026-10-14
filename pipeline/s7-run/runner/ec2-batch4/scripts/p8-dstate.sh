set +e
date -u +%T; uptime
echo "D by unit:"; for p in $(ps -eo pid=,stat= | awk '$2 ~ /^D/ {print $1}'); do u=$(cat /proc/$p/cgroup 2>/dev/null | sed 's/.*\///'); echo "$u"; done | sort | uniq -c
echo "D by wchan:"; ps -eo stat=,wchan:32=,comm= | awk '$1 ~ /^D/ {print $2, $3}' | sort | uniq -c | sort -rn | head -12
for p in $(ps -eo pid=,stat= | awk '$2 ~ /^D/ {print $1}' | head -3); do echo "-- $p $(cat /proc/$p/comm)"; cat /proc/$p/stack 2>/dev/null | head -8; done
cat /sys/block/loop0/loop/dio 2>/dev/null; cat /proc/pressure/memory | head -1
