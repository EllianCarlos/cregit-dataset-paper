# P1-probe.sh (read-only, big EC2): the state that census L1r needs to know before its setup.
set -uo pipefail
B=/usr/local/bin
echo "== $(date -u +%FT%TZ) $(hostname)"
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo) of $(awk '/MemTotal/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); load $(cut -d' ' -f1-3 /proc/loadavg); CPUs $(nproc)"
df -BG --output=target,size,used,avail /data / /bL7 /bL7b /bL22 /bL23 /b5L 2>/dev/null | sed 's/^/  /'
echo "images: $(du -BG /data/loop/*.img 2>/dev/null | tr '\t' ' ' | tr '\n' ';')"
echo "image sizes: $(ls -l --block-size=G /data/loop/*.img 2>/dev/null | awk '{print $9"="$5}' | tr '\n' ' ')"
echo "loops: $(losetup -l -n -O NAME,BACK-FILE 2>/dev/null | tr -s ' ' | tr '\n' ';')"
echo "fsids: $(for m in /data /b4p1 /b4p2 /b4p3 /b5L /b6L /bL7 /bL22 /bL7b /bL23 /bL1r; do mountpoint -q $m && echo -n "$m=$(stat -f -c %i $m) "; done)"
echo "/data/loop/bL1r.img: $([ -e /data/loop/bL1r.img ] && echo EXISTS || echo absent); /bL1r: $([ -e /bL1r ] && echo EXISTS || echo absent)"
grep -n 'bL23\|bL7b' /etc/fstab
echo "== shared scripts (sha256 first 16)"
for f in census-other-done census-batch4-guard census-backup; do echo "$f $(sha256sum $B/$f | cut -c1-16) orig: $(ls $B/$f.orig-* 2>/dev/null | xargs -r -n1 basename | tr '\n' ' ')"; done
grep -n '^ALL=' $B/census-other-done
sed -n '/^RUNS=/,/"$/p' $B/census-backup
grep -n 'bL23\|FLOOR\|800' $B/census-batch4-guard | head -20
echo "== census units"
systemctl list-units --no-legend --plain --all 'census*' | awk '{print $1, $3, $4}' | grep -v '^census-fed' | tr '\n' ';'; echo
for c in batch2 batch3L batch5L L7-20 L7-20b L22 L23 L23-wait; do
  u=census-$c.service; echo "$c: $(systemctl is-active $u) since $(systemctl show $u -p ActiveEnterTimestamp --value)"; done
echo "L23 wait status: $(cat /run/census-L23-wait.status 2>/dev/null | cut -c1-400)"
ls /bL23/ctp/state 2>/dev/null | head
echo "== counts"
for r in "L7-20|/bL7/ctp|/home/ec2-user/L7-20-input/manifest.L7-20.tsv" "L22|/bL22/ctp|/home/ec2-user/L22-input/manifest.batch22L.tsv" "L7-20b|/bL7b/ctp|/home/ec2-user/L7-20b-input/manifest.L7-20b.tsv" "batch5L|/b5L/ctp|/home/ec2-user/batch5-input/manifest.batch5L.tsv" "L23|/bL23/ctp|/home/ec2-user/L23-input/manifest.L23.tsv"; do
  IFS='|' read -r n c m <<<"$r"; echo "$n: $($B/census-steps --counts $c $m 2>&1 | head -1)"; done
echo "== cregit / ctp"
for d in /data/cregit-ec2 /bL23/cregit-ec2; do echo "$d: $(sudo -u ec2-user git -C $d rev-parse --short HEAD 2>&1) dirty=[$(sudo -u ec2-user git -C $d status --porcelain --untracked-files=no 2>&1 | wc -l)]"; done
echo "/bL23/ctp: $(sudo -u ec2-user git -C /bL23/ctp rev-parse --short HEAD) venv $([ -x /bL23/ctp/.venv/bin/python ] && echo ok)"
echo "gates: $(for g in /etc/cregit-census/*.gate; do echo -n "$(basename $g): $(tail -1 $g | cut -c1-90) | "; done)"
ls /data/input/ 2>/dev/null | grep -i bundle; ls /home/ec2-user | grep -i 'input\|bundle\|cfg'
echo "== big processes (RSS > 4 GB): pid rss_GB oom_score_adj unit args"
ps -eo pid,rss,args --sort=-rss --no-headers | awk '$2>4194304' | head -25 | while read -r pid rss args; do
  echo "$pid $((rss/1048576))G adj=$(cat /proc/$pid/oom_score_adj 2>/dev/null) $(grep -o 'census[^/]*\.service' /proc/$pid/cgroup 2>/dev/null | head -1) ${args:0:160}"; done
echo "== processes with oom_score_adj != 0"
for p in /proc/[0-9]*; do a=$(cat $p/oom_score_adj 2>/dev/null) || continue; [ "$a" != 0 ] && echo "${p#/proc/} adj=$a $(tr '\0' ' ' <$p/cmdline 2>/dev/null | cut -c1-140)"; done | grep -v 'systemd\|sshd\|amazon-ssm\|agetty\|dbus' | head -20
echo "== firm in logs"
grep -i -m3 'firm' /data/logs/L7-20.log | cut -c1-200; tail -c 300000 /data/logs/L7-20.log | grep -i 'firm' | tail -5 | cut -c1-200
