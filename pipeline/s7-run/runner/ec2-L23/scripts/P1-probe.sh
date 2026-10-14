# P1-probe.sh (read-only, big EC2): the state that census L23 needs to know before its setup.
set -uo pipefail
B=/usr/local/bin
echo "== $(date -u +%FT%TZ) $(hostname)"
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo) of $(awk '/MemTotal/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); load $(cut -d' ' -f1-3 /proc/loadavg); CPUs $(nproc)"
df -BG --output=target,size,used,avail /data / | sed 's/^/  /'
echo "images: $(du -BG /data/loop/*.img 2>/dev/null | tr '\t' ' ' | tr '\n' ';')"
echo "loops: $(losetup -l -n -O NAME,BACK-FILE 2>/dev/null | tr -s ' ' | tr '\n' ';')"
echo "fsids: $(for m in /data /b4p1 /b4p2 /b4p3 /b5L /b6L /bL7 /bL22 /bL7b /bL23; do mountpoint -q $m && echo -n "$m=$(stat -f -c %i $m) "; done)"
echo "/data/loop/bL23.img: $([ -e /data/loop/bL23.img ] && echo EXISTS || echo absent); /bL23: $([ -e /bL23 ] && echo EXISTS || echo absent)"
echo "== shared scripts (sha256 first 16)"
for f in census-other-done census-batch4-guard census-backup; do echo "$f $(sha256sum $B/$f | cut -c1-16) orig: $(ls $B/$f.orig-* 2>/dev/null | xargs -r -n1 basename | tr '\n' ' ')"; done
grep -n '^ALL=' $B/census-other-done
sed -n '/^RUNS=/,/"$/p' $B/census-backup
echo "== census units"
systemctl list-units --no-legend --plain --all 'census*' | awk '{print $1, $3, $4}' | grep -v '^census-fed' | tr '\n' ';'; echo
for c in batch2 batch3L batch4p1 batch4p2 batch4p3 batch5L batch6L L7-20 L22 L7-20b; do
  u=census-$c.service; echo "$c: $(systemctl is-active $u) since $(systemctl show $u -p ActiveEnterTimestamp --value)"; done
echo "== counts (census-steps --counts)"
for r in "L7-20|/bL7/ctp|/home/ec2-user/L7-20-input/manifest.L7-20.tsv" "L22|/bL22/ctp|/home/ec2-user/L22-input/manifest.batch22L.tsv" "L7-20b|/bL7b/ctp|/home/ec2-user/L7-20b-input/manifest.L7-20b.tsv" "batch5L|/b5L/ctp|/home/ec2-user/batch5-input/manifest.batch5L.tsv"; do
  IFS='|' read -r n c m <<<"$r"; echo "$n: $($B/census-steps --counts $c $m 2>&1 | head -1)"; done
echo "== wait scripts: MAXRUN / others"
grep -n 'MAXRUN=\|^L22|\|^L7_20b|\|L7_20|census' $B/census-L7-20b-wait | head -20
echo "== cregit"
for d in /data/cregit-ec2 /bL22/cregit-ec2 /bL7b/cregit-ec2 /bL7/cregit-ec2; do echo "$d: $(sudo -u ec2-user git -C $d rev-parse --short HEAD 2>&1) dirty=[$(sudo -u ec2-user git -C $d status --porcelain --untracked-files=no 2>&1 | wc -l)] has57551d7=$(sudo -u ec2-user git -C $d cat-file -t 57551d7ad82a784615c1490623d72cb9dc994ba1 2>/dev/null || echo no)"; done
ls -la /home/ec2-user/ | grep -i 'input\|bundle' | head -20
ls /data/input/ 2>/dev/null | grep -i bundle
echo "gates: $(for g in /etc/cregit-census/*.gate; do echo -n "$(basename $g): $(tail -1 $g | cut -c1-90) | "; done)"
echo "== ctp"
for c in /bL7b/ctp /bL22/ctp; do echo "$c: $(sudo -u ec2-user git -C $c rev-parse --short HEAD) venv $([ -x $c/.venv/bin/python ] && echo ok)"; done
echo "== watch: recent guard"
tail -2 /run/census-batch4-guard.log 2>/dev/null; journalctl -u census-batch4-guard.service -n 2 --no-pager 2>/dev/null | tail -2
