#!/usr/bin/env bash
# gen-L2.sh: build L2a-install.sh and L2b-install.sh (big EC2; run a, then b): install the batch6L files and the new census-other-done,
# census-batch4-guard and census-backup (originals kept as .orig-4census / .orig-b5L / .orig-b5L), check
# NeedDaemonReload=no on every census unit, daemon-reload, run the power-off rule and waiter tests
# (nothing powers off, nothing starts a census), a dry-run finalize, then start the batch6L live timer
# and the waiter (which holds the start until the batch6L identity gate passed: census-batch6L-cregit).
set -euo pipefail
cd "$(dirname "$0")"
bins="census-other-done census-batch4-guard census-backup census-batch6L-run census-batch6L-live census-batch6L-finalize census-batch6L-wait census-batch6L-cregit"
units="census-batch6L.service census-batch6L-finalize.service census-batch6L-live.service census-batch6L-live.timer census-batch6L-wait.service"
{
cat <<'H'
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin; S3=s3://${RUNNER_BUCKET}
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = bf852463a1fbb5ff ] || [ -e $B/census-other-done.orig-4census ] || { echo "census-other-done changed"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = da30580a956ae1b3 ] || [ -e $B/census-batch4-guard.orig-b5L ] || { echo "census-batch4-guard changed"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = 847c6c13d0ab8316 ] || [ -e $B/census-backup.orig-b5L ] || { echo "census-backup changed"; exit 1; }
for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-backup; do s=$(systemctl is-active $f.service); case $s in active|activating) echo "$f.service is $s: not replacing the shared scripts now"; exit 1 ;; esac; done
U=$(systemctl list-units --no-legend --plain --all 'census*' | awk '{print $1}')
for u in $U; do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; aborting"; exit 1; }; done
echo "NeedDaemonReload=no for all $(echo $U | wc -w) loaded census units"
R="census-batch2.service census-batch3L.service census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch5L.service"
before=$(systemctl show $R -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')
[ -e $B/census-other-done.orig-4census ] || cp -p $B/census-other-done $B/census-other-done.orig-4census
[ -e $B/census-batch4-guard.orig-b5L ] || cp -p $B/census-batch4-guard $B/census-batch4-guard.orig-b5L
[ -e $B/census-backup.orig-b5L ] || cp -p $B/census-backup $B/census-backup.orig-b5L
H
for f in $bins; do echo "cat > \$B/$f.new <<'EOF_$f'"; cat remote-L/$f; echo "EOF_$f"; echo "chmod 755 \$B/$f.new; mv -f \$B/$f.new \$B/$f"; done
echo 'echo "L2a: scripts installed: $(cd $B && sha256sum census-other-done census-batch4-guard census-backup | cut -c1-16 | tr "\n" " ")"'
} > L2a-install.sh
{
cat <<'H2'
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin; S3=s3://${RUNNER_BUCKET}
U=$(systemctl list-units --no-legend --plain --all 'census*' | awk '{print $1}')
for u in $U; do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; aborting"; exit 1; }; done
echo "NeedDaemonReload=no for all $(echo $U | wc -w) loaded census units"
R="census-batch2.service census-batch3L.service census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch5L.service"
before=$(systemctl show $R -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')
H2
for f in $units; do echo "cat > /etc/systemd/system/$f.new <<'EOF_$f'"; cat remote-L/$f; echo "EOF_$f"; echo "chmod 644 /etc/systemd/system/$f.new; mv -f /etc/systemd/system/$f.new /etc/systemd/system/$f"; done
cat <<'T'
systemctl daemon-reload
after=$(systemctl show $R -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')
[ "$before" = "$after" ] && echo "running censuses unchanged by the reload (6 units)" || echo "CHANGED: before $before / after $after"
systemctl show census-batch6L.service -p OOMPolicy -p RequiresMountsFor -p OnSuccess -p OnFailure | tr '\n' ' '; echo
echo "== power-off rule tests $(date -u +%FT%TZ) (census-other-done only; nothing powers off)"
r() { local out; out=$("$@" 2>&1); echo "rc=$? $out"; }
F=$S3/batch4/dryrun/DONE
for n in batch2 batch3L batch4 batch5L batch6L; do echo "T1 $n, real state: $(r $B/census-other-done $n)"; done
echo "T2 batch5L, 2+3L+4 faked done (6L missing): $(DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= r $B/census-other-done batch5L)"
echo "T3 batch5L, 2+3L+4+6L faked done: $(DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch6L=$F UNITS_batch6L= r $B/census-other-done batch5L)"
echo "T4 batch6L, 2+3L+4+5L faked done: $(DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L= r $B/census-other-done batch6L)"
echo "T5 batch6L, all faked done but its waiter unit counted active: $(DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L= DONE_URL_batch6L=$F UNITS_batch6L=census-batch2.service r $B/census-other-done batch2)"
echo "T6 bad argument: $(r $B/census-other-done batch9)"
for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-batch6L-finalize; do echo "T7 $f --decide-only: $($B/$f --decide-only 2>&1 | tail -1 | cut -c1-200)"; done
echo "T8 guard (real run): $($B/census-batch4-guard)"
echo "== waiter tests (--decide-only; nothing starts)"
echo "W1 real state: $(r $B/census-batch6L-wait --decide-only)"
ok="COUNTS_batch2='1 0' COUNTS_batch3L='1 0' COUNTS_batch4p1='2 0' COUNTS_batch4p2='2 0' COUNTS_batch4p3='2 0' COUNTS_batch5L='5 0' MEMAVAIL_GB=200 DATAFREE_GB=3000"
echo "W2 all conditions met, gate ok: $(eval env $ok GATE_OK=1 $B/census-batch6L-wait --decide-only 2>&1 | tail -c 120; echo " rc=$?")"
echo "W3 gate missing: $(eval env $ok GATE_OK=0 $B/census-batch6L-wait --decide-only 2>&1 | tail -c 110)"
echo "W4 batch 4 has 3 unstarted: $(eval env $ok COUNTS_batch4p2="'2 3'" GATE_OK=1 $B/census-batch6L-wait --decide-only 2>&1 | tail -c 80)"
echo "W5 17 running: $(eval env $ok COUNTS_batch5L="'10 0'" GATE_OK=1 $B/census-batch6L-wait --decide-only 2>&1 | tail -c 60)"
echo "W6 memory 100G: $(eval env $ok MEMAVAIL_GB=100 GATE_OK=1 $B/census-batch6L-wait --decide-only 2>&1 | tail -c 60)"
echo "W7 /data 1000G: $(eval env $ok DATAFREE_GB=1000 GATE_OK=1 $B/census-batch6L-wait --decide-only 2>&1 | tail -c 60)"
echo "W8 batch 4 parts inactive (their counts ignored): $(eval env $ok ACTIVE_batch4p1=inactive ACTIVE_batch4p2=inactive ACTIVE_batch4p3=inactive COUNTS_batch4p1="'4 9'" GATE_OK=1 $B/census-batch6L-wait --decide-only 2>&1 | tail -c 70)"
echo "W9 real counts, real gate file (absent): $(r $B/census-batch6L-wait --decide-only | tail -c 120)"
echo "== dry-run finalize on the check output"
CTP_L=/b6L/ctp-check OUT_L=/b6L/libexpat-check/out MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv $B/census-batch6L-finalize --dry-run 2>&1 | grep -E 'staged|check ok|DONE|dry run|FAILED' | cut -c1-220
bash -n $B/census-backup && echo "census-backup syntax ok; RUNS: $(sed -n '/^RUNS=/,/"$/p' $B/census-backup | cut -d'|' -f1 | tr -d 'RUNS="' | tr '\n' ' ')"
echo "== start live timer and waiter $(date -u +%FT%TZ)"
systemctl start census-batch6L-live.timer census-batch6L-wait.service
sleep 20
echo "waiter: $(systemctl is-active census-batch6L-wait.service); census-batch6L: $(systemctl is-active census-batch6L.service); status: $(cat /run/census-batch6L-wait.status | cut -c1-300)"
after2=$(systemctl show $R -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')
[ "$before" = "$after2" ] && echo "running censuses unchanged after the start" || echo "CHANGED after start: $after2"
T
} > L2b-install.sh
for f in L2a-install.sh L2b-install.sh; do bash -n $f; echo "$f $(wc -c < $f) bytes"; done
