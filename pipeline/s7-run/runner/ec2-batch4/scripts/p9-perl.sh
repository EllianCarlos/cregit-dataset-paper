set +e
for p in $(ps -eo pid=,stat=,comm= | awk '$2 ~ /^D/ && $3=="perl" {print $1}' | shuf -n 6 --random-source=/dev/zero); do
  echo "$p $(cat /proc/$p/cgroup | sed 's/.*\///') cwd=$(readlink /proc/$p/cwd) args=$(tr '\0' ' ' < /proc/$p/cmdline | cut -c1-160)"; done
echo "TMPDIR of a batch4 perl: $(for p in $(pgrep -u ec2-user perl | head -50); do grep -q batch4 /proc/$p/cgroup && { tr '\0' '\n' < /proc/$p/environ | grep -e ^TMPDIR -e ^TMP; break; }; done)"
uptime
