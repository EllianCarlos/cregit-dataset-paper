#!/usr/bin/env bash
# gen-L2.sh (L22): build L2a-install.sh, L2a2-install.sh and L2b-install.sh (big EC2; run in that order). a: pre-checks,
# backups (.orig-L7-20) and the scripts (census-other-done, census-batch4-guard, census-backup with
# L22; the census-L22-* scripts; census-batch6L-cregit with mkdir -p /etc/cregit-census). b:
# NeedDaemonReload=no on every census unit, the units, daemon-reload (running census units checked
# unchanged), the power-off rule and waiter tests (nothing powers off, nothing starts).
set -euo pipefail
cd "$(dirname "$0")"
bins="census-other-done census-batch4-guard census-backup census-L22-run census-L22-live"
bins2="census-L22-finalize census-L22-wait census-L22-cregit"
units="census-L22.service census-L22-finalize.service census-L22-live.service census-L22-live.timer census-L22-wait.service"
{
cat <<'H'
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = 5711f7113abbf1e5 ] || [ -e $B/census-other-done.orig-L7-20 ] || { echo "census-other-done changed"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = 70a5a009ee0c9815 ] || [ -e $B/census-batch4-guard.orig-L7-20 ] || { echo "census-batch4-guard changed"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = f55939db56fb9208 ] || [ -e $B/census-backup.orig-L7-20 ] || { echo "census-backup changed"; exit 1; }
# a finalize that waits for its parts runs census-other-done as a new process at its end, so the
# atomic replacement below is what it will use; the running finalize scripts themselves are not replaced
echo "finalize/backup/guard states: $(for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-batch6L-finalize census-L7-20-finalize census-backup census-batch4-guard; do echo -n "$f=$(systemctl is-active $f.service) "; done)"
[ -e $B/census-other-done.orig-L7-20 ] || cp -p $B/census-other-done $B/census-other-done.orig-L7-20
[ -e $B/census-batch4-guard.orig-L7-20 ] || cp -p $B/census-batch4-guard $B/census-batch4-guard.orig-L7-20
[ -e $B/census-backup.orig-L7-20 ] || cp -p $B/census-backup $B/census-backup.orig-L7-20
H
for f in $bins; do echo "cat > \$B/$f.new <<'EOF_$f'"; cat remote-L/$f; echo "EOF_$f"; echo "chmod 755 \$B/$f.new; mv -f \$B/$f.new \$B/$f"; done
echo 'echo "L2a: scripts installed: $(cd $B && sha256sum census-other-done census-batch4-guard census-backup | cut -c1-16 | tr "\n" " ")"'
} > L2a-install.sh
{ echo 'set -uo pipefail'; echo 'B=/usr/local/bin'
  for f in $bins2; do echo "cat > \$B/$f.new <<'EOF_$f'"; cat remote-L/$f; echo "EOF_$f"; echo "chmod 755 \$B/$f.new; mv -f \$B/$f.new \$B/$f"; done
  echo 'echo "L2a2: scripts installed"'
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
systemctl show census-L22.service -p OOMPolicy -p RequiresMountsFor -p OnSuccess -p OnFailure | tr '\n' ' '; echo
echo "== power-off rule tests $(date -u +%FT%TZ) (census-other-done only; nothing powers off)"
F=$S3/batch4/dryrun/DONE
t() { local d=$1 self=$2; shift 2; out=$( ( [ $# -gt 0 ] && export "$@"; $B/census-other-done $self ) 2>&1); echo "$d: rc=$? $out" | cut -c1-200; }
for n in batch2 batch3L batch4 batch5L batch6L L7-20 L22; do t "T1 $n, real state" $n; done
o="DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L= DONE_URL_batch6L=$F UNITS_batch6L="
t "T2 L7-20, 2+3L+4+5L+6L faked (L22 missing)" L7-20 $o
t "T3 L7-20, 2+3L+4+5L+6L+L22 faked" L7-20 $o DONE_URL_L22=$F UNITS_L22=
t "T4 L22, 2+3L+4+5L+6L+L7-20 faked" L22 $o DONE_URL_L7_20=$F UNITS_L7_20=
t "T5 L22, all faked but L22 counted for batch2 with an active unit" batch2 DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L= DONE_URL_batch6L=$F UNITS_batch6L= DONE_URL_L7_20=$F UNITS_L7_20= DONE_URL_L22=$F UNITS_L22=census-batch2.service
t "T6 bad argument" L9
for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-batch6L-finalize census-L7-20-finalize census-L22-finalize; do echo "T7 $f --decide-only: $($B/$f --decide-only 2>&1 | tail -1 | cut -c1-170)"; done
echo "T8 guard (real run): $($B/census-batch4-guard)"
echo "== waiter tests (--decide-only; nothing starts)"
echo "W1 real state: $($B/census-L22-wait --decide-only 2>&1 | cut -c1-420)"
w() { local d=$1; shift; out=$( ( export COUNTS_batch2='1 0' COUNTS_batch3L='1 0' COUNTS_batch4p1='1 0' COUNTS_batch4p2='1 0' COUNTS_batch4p3='1 0' COUNTS_batch5L='2 0' COUNTS_batch6L='3 0' COUNTS_L7_20='6 0' MEMAVAIL_GB=200 DATAFREE_GB=2000 INPUT_OK=1 GATE_OK=1 ACTIVE_batch2=active ACTIVE_batch3L=active ACTIVE_batch4p1=active ACTIVE_batch4p2=active ACTIVE_batch4p3=active ACTIVE_batch5L=active ACTIVE_batch6L=active ACTIVE_L7_20=active; [ $# -gt 0 ] && export "$@"; $B/census-L22-wait --decide-only ) 2>&1); echo "$d: rc=$? ...${out: -70}"; }
w "W2 16 other running" 
w "W3 14 other running" COUNTS_L7_20='4 0'
w "W4 14 running, gate missing" COUNTS_L7_20='4 0' GATE_OK=0
w "W5 14 running, memory 100G" COUNTS_L7_20='4 0' MEMAVAIL_GB=100
w "W6 14 running, /data 1400G" COUNTS_L7_20='4 0' DATAFREE_GB=1400
w "W7 14 running, inputs missing" COUNTS_L7_20='4 0' INPUT_OK=0
w "W8 L7-20 inactive (its counts ignored)" ACTIVE_L7_20=inactive
bash -n $B/census-backup && echo "census-backup syntax ok; RUNS: $(sed -n '/^RUNS=/,/"$/p' $B/census-backup | cut -d'|' -f1 | tr -d 'RUNS="' | tr '\n' ' ')"
T
} > L2b-install.sh
for f in L2a-install.sh L2a2-install.sh L2b-install.sh; do bash -n $f; echo "$f $(wc -c < $f) bytes"; done
