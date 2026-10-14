#!/usr/bin/env bash
# gen-L2.sh (L7-20b): build L2a-install.sh, L2a2-install.sh and L2b-install.sh (big EC2; run in that order).
# a: pre-checks, backups (.orig-L22) and the scripts (census-other-done, census-batch4-guard, census-backup
# with L7-20b; the census-L7-20b-* scripts; census-L7-20-split). b: NeedDaemonReload=no on every census
# unit, the units, daemon-reload (running census units checked unchanged), the power-off rule, waiter
# and split watcher tests (nothing powers off, nothing starts, no STOP is written in a census clone).
set -euo pipefail
cd "$(dirname "$0")"
bins="census-other-done census-batch4-guard census-backup census-L7-20b-run census-L7-20b-live"
bins2="census-L7-20b-finalize census-L7-20b-wait census-L7-20b-cregit census-L7-20-split"
units="census-L7-20b.service census-L7-20b-finalize.service census-L7-20b-live.service census-L7-20b-live.timer census-L7-20b-wait.service census-L7-20-split.service census-L7-20-split.timer"
for f in $bins $bins2; do bash -n remote-L/$f; done
{
cat <<'H'
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = 0acc488b9a1ed5c6 ] || [ -e $B/census-other-done.orig-L22 ] || { echo "census-other-done changed"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = a96cab084a9525b2 ] || [ -e $B/census-batch4-guard.orig-L22 ] || { echo "census-batch4-guard changed"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = dc3065d425727ea8 ] || [ -e $B/census-backup.orig-L22 ] || { echo "census-backup changed"; exit 1; }
# a finalize that waits for its parts runs census-other-done as a new process at its end, so the
# atomic replacement below is what it will use; the running finalize scripts themselves are not replaced
echo "finalize/backup/guard states: $(for f in census-batch5L-finalize census-L7-20-finalize census-L22-finalize census-backup census-batch4-guard; do echo -n "$f=$(systemctl is-active $f.service) "; done)"
[ -e $B/census-other-done.orig-L22 ] || cp -p $B/census-other-done $B/census-other-done.orig-L22
[ -e $B/census-batch4-guard.orig-L22 ] || cp -p $B/census-batch4-guard $B/census-batch4-guard.orig-L22
[ -e $B/census-backup.orig-L22 ] || cp -p $B/census-backup $B/census-backup.orig-L22
H
for f in $bins; do echo "cat > \$B/$f.new <<'EOF_$f'"; cat remote-L/$f; echo "EOF_$f"; echo "chmod 755 \$B/$f.new; mv -f \$B/$f.new \$B/$f"; done
echo 'echo "L2a: scripts installed: $(cd $B && sha256sum census-other-done census-batch4-guard census-backup | cut -c1-16 | tr "\n" " ")"'
} > L2a-install.sh
{ echo 'set -uo pipefail'; echo 'B=/usr/local/bin'
  for f in $bins2; do echo "cat > \$B/$f.new <<'EOF_$f'"; cat remote-L/$f; echo "EOF_$f"; echo "chmod 755 \$B/$f.new; mv -f \$B/$f.new \$B/$f"; done
  echo 'echo "L2a2: scripts installed: $(cd $B && sha256sum '"$bins2"' | cut -c1-16 | tr "\n" " ")"'
} > L2a2-install.sh
{
cat <<'H2'
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin; S3=s3://${RUNNER_BUCKET}
U=$(systemctl list-units --no-legend --plain --all 'census*' | awk '{print $1}')
for u in $U; do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; aborting"; exit 1; }; done
echo "NeedDaemonReload=no for all $(echo $U | wc -w) loaded census units"
R=$(systemctl list-units --no-legend --plain --state=active 'census*.service' | awk '{print $1}')
before=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
H2
for f in $units; do echo "cat > /etc/systemd/system/$f.new <<'EOF_$f'"; cat remote-L/$f; echo "EOF_$f"; echo "chmod 644 /etc/systemd/system/$f.new; mv -f /etc/systemd/system/$f.new /etc/systemd/system/$f"; done
cat <<'T'
systemctl daemon-reload
after=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
[ "$before" = "$after" ] && echo "running census units unchanged by the reload ($(echo "$R" | grep -c .) units: $(echo $R | tr '\n' ' '))" || { echo "CHANGED:"; diff <(echo "$before") <(echo "$after"); }
systemctl show census-L7-20b.service -p OOMPolicy -p RequiresMountsFor -p OnSuccess -p OnFailure | tr '\n' ' '; echo
echo "== power-off rule tests $(date -u +%FT%TZ) (census-other-done only; nothing powers off)"
F=$S3/batch4/dryrun/DONE
t() { local d=$1 self=$2; shift 2; out=$( ( [ $# -gt 0 ] && export "$@"; $B/census-other-done $self ) 2>&1); echo "$d: rc=$? $out" | cut -c1-200; }
for n in batch2 batch3L batch4 batch5L batch6L L7-20 L22 L7-20b; do t "T1 $n, real state" $n; done
o="DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L= DONE_URL_batch6L=$F UNITS_batch6L="
t "T2 L7-20, 2+3L+4+5L+6L+L22 faked (L7-20b missing)" L7-20 $o DONE_URL_L22=$F UNITS_L22=
t "T3 L7-20, 2+3L+4+5L+6L+L22+L7-20b faked" L7-20 $o DONE_URL_L22=$F UNITS_L22= DONE_URL_L7_20b=$F UNITS_L7_20b=
t "T4 L7-20b, all other faked" L7-20b $o DONE_URL_L22=$F UNITS_L22= DONE_URL_L7_20=$F UNITS_L7_20=
t "T5 L22, all other faked but L7-20b with an active unit" L22 $o DONE_URL_L7_20=$F UNITS_L7_20= DONE_URL_L7_20b=$F UNITS_L7_20b=census-L7-20.service
t "T6 bad argument" L9
for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-batch6L-finalize census-L7-20-finalize census-L22-finalize census-L7-20b-finalize; do echo "T7 $f --decide-only: $($B/$f --decide-only 2>&1 | tail -1 | cut -c1-170)"; done
echo "T8 guard (real run): $($B/census-batch4-guard)"
echo "== waiter tests (--decide-only; nothing starts)"
echo "W1 real state: $($B/census-L7-20b-wait --decide-only 2>&1 | cut -c1-460)"
w() { local d=$1; shift; out=$( ( export ACTIVE_batch2=inactive ACTIVE_batch3L=inactive ACTIVE_batch4p1=inactive ACTIVE_batch4p2=inactive ACTIVE_batch4p3=inactive ACTIVE_batch6L=inactive ACTIVE_batch5L=active ACTIVE_L7_20=active ACTIVE_L22=active COUNTS_batch5L='1 0' COUNTS_L7_20='6 50' COUNTS_L22='1 0' MEMAVAIL_GB=300 DATAFREE_GB=2900 INPUT_OK=1 GATE_OK=1 SPLIT_OK=1; [ $# -gt 0 ] && export "$@"; $B/census-L7-20b-wait --decide-only ) 2>&1); echo "$d: rc=$? ...${out: -80}"; }
w "W2 8 other running"
w "W3 11 other running" COUNTS_L22='4 0'
w "W4 gate missing" GATE_OK=0
w "W5 memory 100G" MEMAVAIL_GB=100
w "W6 /data 2400G" DATAFREE_GB=2400
w "W7 inputs missing" INPUT_OK=0
w "W8 L7-20 has started an L7-20b row" SPLIT_OK=0
w "W9 L7-20 inactive (its counts ignored)" ACTIVE_L7_20=inactive COUNTS_L22='9 0'
echo "== split watcher tests"
echo "S1 real state: $($B/census-L7-20-split --decide-only 2>&1 | cut -c1-300)"
X=$(mktemp -d /tmp/split-test.XXXX); mkdir $X/sd
grep -v -e '^#' -e '^[[:space:]]*$' /home/ec2-user/L7-20-input/manifest.L7-20.tsv | cut -f1 | head -16 | while read -r n; do mkdir $X/sd/$n; done
s() { local d=$1; shift; out=$(env STATE_DIR=$X/sd STOP_FILE=$X/STOP ST_FILE=$X/st LOG_FILE=$X/log NO_TIMER_STOP=1 "$@" $B/census-L7-20-split 2>&1; cat $X/st 2>/dev/null); echo "$d: ${out:0:260}"; }
echo "S2 rows 1-16 started, L7-20b started (decide-only): $(env STATE_DIR=$X/sd STOP_FILE=$X/STOP L720_ACTIVE=active L720B_STARTED=1 $B/census-L7-20-split --decide-only | cut -c1-200)"
s "S3 the same, L7-20b not started (real run, temp STOP path)" L720_ACTIVE=active L720B_STARTED=0
s "S4 the same, L7-20b started (real run, temp STOP path)" L720_ACTIVE=active L720B_STARTED=1
echo "S4 files: $(ls $X | tr '\n' ' '); owner $(stat -c %U $X/STOP 2>/dev/null); marker: $(cut -c1-120 $X/STOP.split-L7-20b 2>/dev/null)"
s "S5 L7-20 ended" L720_ACTIVE=inactive L720B_STARTED=1
rm -r $X
echo "real /bL7/ctp/STOP: $([ -e /bL7/ctp/STOP ] && echo PRESENT || echo absent); split timer: $(systemctl is-active census-L7-20-split.timer)"
bash -n $B/census-backup && echo "census-backup syntax ok; RUNS: $(sed -n '/^RUNS=/,/"$/p' $B/census-backup | cut -d'|' -f1 | tr -d 'RUNS="' | tr '\n' ' ')"
T
} > L2b-install.sh
for f in L2a-install.sh L2a2-install.sh L2b-install.sh; do bash -n $f; echo "$f $(wc -c < $f) bytes"; done
