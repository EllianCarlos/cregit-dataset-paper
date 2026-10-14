#!/usr/bin/env bash
# gen-L2.sh (L7-20): build L2a-install.sh, L2a2-install.sh and L2b-install.sh (big EC2; run in that order). a: pre-checks,
# backups (.orig-b6L) and the scripts (census-other-done, census-batch4-guard, census-backup with
# L7-20; the census-L7-20-* scripts; census-batch6L-cregit with mkdir -p /etc/cregit-census). b:
# NeedDaemonReload=no on every census unit, the units, daemon-reload (running census units checked
# unchanged), the power-off rule and waiter tests (nothing powers off, nothing starts).
set -euo pipefail
cd "$(dirname "$0")"
bins="census-other-done census-batch4-guard census-backup census-L7-20-run census-L7-20-live"
bins2="census-L7-20-finalize census-L7-20-wait census-L7-20-cregit census-batch6L-cregit"
units="census-L7-20.service census-L7-20-finalize.service census-L7-20-live.service census-L7-20-live.timer census-L7-20-wait.service"
{
cat <<'H'
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = 1e5bcfca099f2f80 ] || [ -e $B/census-other-done.orig-b6L ] || { echo "census-other-done changed"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = 57f0aa43ebedbb06 ] || [ -e $B/census-batch4-guard.orig-b6L ] || { echo "census-batch4-guard changed"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = 87981d084b324aab ] || [ -e $B/census-backup.orig-b6L ] || { echo "census-backup changed"; exit 1; }
# a finalize that waits for its parts runs census-other-done as a new process at its end, so the
# atomic replacement below is what it will use; the running finalize scripts themselves are not replaced
echo "finalize/backup/guard states: $(for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-batch6L-finalize census-backup census-batch4-guard; do echo -n "$f=$(systemctl is-active $f.service) "; done)"
[ -e $B/census-other-done.orig-b6L ] || cp -p $B/census-other-done $B/census-other-done.orig-b6L
[ -e $B/census-batch4-guard.orig-b6L ] || cp -p $B/census-batch4-guard $B/census-batch4-guard.orig-b6L
[ -e $B/census-backup.orig-b6L ] || cp -p $B/census-backup $B/census-backup.orig-b6L
[ -e $B/census-batch6L-cregit.orig-nomkdir ] || cp -p $B/census-batch6L-cregit $B/census-batch6L-cregit.orig-nomkdir
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
systemctl show census-L7-20.service -p OOMPolicy -p RequiresMountsFor -p OnSuccess -p OnFailure | tr '\n' ' '; echo
echo "== power-off rule tests $(date -u +%FT%TZ) (census-other-done only; nothing powers off)"
r() { local out; out=$("$@" 2>&1); echo "rc=$? $out"; }
F=$S3/batch4/dryrun/DONE
for n in batch2 batch3L batch4 batch5L batch6L L7-20; do echo "T1 $n, real state: $(r $B/census-other-done $n | cut -c1-160)"; done
all="DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L="
echo "T2 batch6L, 2+3L+4+5L faked done (L7-20 missing): $(eval env $all r $B/census-other-done batch6L | cut -c1-160)"
echo "T3 batch6L, 2+3L+4+5L+L7-20 faked done: $(eval env $all DONE_URL_L7_20=$F UNITS_L7_20= r $B/census-other-done batch6L | cut -c1-160)"
echo "T4 L7-20, 2+3L+4+5L+6L faked done: $(eval env $all DONE_URL_batch6L=$F UNITS_batch6L= r $B/census-other-done L7-20 | cut -c1-160)"
echo "T5 L7-20, all faked but L7-20's own waiter counted for batch2: $(eval env $all DONE_URL_batch6L=$F UNITS_batch6L= DONE_URL_L7_20=$F UNITS_L7_20=census-L7-20-wait.service UNITS_batch2=census-batch2.service r $B/census-other-done batch6L | cut -c1-160)"
echo "T6 bad argument: $(r $B/census-other-done L9 | cut -c1-120)"
for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-batch6L-finalize census-L7-20-finalize; do echo "T7 $f --decide-only: $($B/$f --decide-only 2>&1 | tail -1 | cut -c1-170)"; done
echo "T8 guard (real run): $($B/census-batch4-guard)"
echo "== waiter tests (--decide-only; nothing starts)"
echo "W1 real state: $(r $B/census-L7-20-wait --decide-only | cut -c1-400)"
ok="COUNTS_batch2='1 0' COUNTS_batch3L='1 0' COUNTS_batch4p1='1 0' COUNTS_batch4p2='1 0' COUNTS_batch4p3='1 0' COUNTS_batch5L='2 0' COUNTS_batch6L='3 0' MEMAVAIL_GB=200 DATAFREE_GB=3000 B6L_STARTED=1 INPUT_OK=1"
w() { eval env $ok "$@" $B/census-L7-20-wait --decide-only 2>&1 | sed 's/.*;\(.*\)$/\1/'; }
echo "W2 all met, gate ok: $(w GATE_OK=1) rc=$(eval env $ok GATE_OK=1 $B/census-L7-20-wait --decide-only >/dev/null 2>&1; echo $?)"
echo "W3 gate missing: $(w GATE_OK=0)"
echo "W4 batch6L not started: $(w GATE_OK=1 B6L_STARTED=0)"
echo "W5 11 other running: $(w GATE_OK=1 COUNTS_batch6L="'4 0'")"
echo "W6 memory 100G: $(w GATE_OK=1 MEMAVAIL_GB=100)"
echo "W7 /data 2000G: $(w GATE_OK=1 DATAFREE_GB=2000)"
echo "W8 inputs missing: $(w GATE_OK=1 INPUT_OK=0)"
echo "W9 batch 4 inactive (counts ignored): $(w GATE_OK=1 ACTIVE_batch4p1=inactive COUNTS_batch4p1="'9 9'")"
bash -n $B/census-backup && echo "census-backup syntax ok; RUNS: $(sed -n '/^RUNS=/,/"$/p' $B/census-backup | cut -d'|' -f1 | tr -d 'RUNS="' | tr '\n' ' ')"
T
} > L2b-install.sh
for f in L2a-install.sh L2a2-install.sh L2b-install.sh; do bash -n $f; echo "$f $(wc -c < $f) bytes"; done
