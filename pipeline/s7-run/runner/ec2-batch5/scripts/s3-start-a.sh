X=a
# s3-start.sh (prepend X=a|b): termination-rule tests, start of the batch5 / batch1rest parts, the
# dry-run finalize, the fake spot-notice test; on a the waiting old batch 3 finalize is stopped
# (its replacement runs when a batch 3 part ends); then NO_SHUTDOWN is removed. Nothing terminates:
# only census-spot-decide, --decide-only and --dry-run are called.
set -uo pipefail
export AWS_PAGER=""
E=/etc/cregit-census; B=s3://${RUNNER_BUCKET}; IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
grep -q '^CHECK OK' $E/s5/check.result || { echo "no CHECK OK in $E/s5/check.result"; exit 1; }
touch $E/censuses; grep -qx b3 $E/censuses || echo b3 >> $E/censuses
. $E/batch.env; . $E/s5/batch.env
T=s3://${RUNNER_BUCKET}/s5test/$IID
echo "== decision tests $(date -u +%FT%TZ)"
r() { local out; out=$("$@" 2>&1); echo "rc=$? $out"; }
echo "T1 real state, censuses=$(tr '\n' ' ' < $E/censuses): $(r /usr/local/bin/census-spot-decide)"
echo "T2 b3+b5, no units, no DONE: $(CENSUSES='b3 b5' UNITS_b3= UNITS_b5= BUCKET_DONE=$T r /usr/local/bin/census-spot-decide)"
echo x > /tmp/fake-done; aws s3 cp /tmp/fake-done $T/batch3/$BATCH/final/$IID/DONE --only-show-errors
echo "T3 b3 DONE only: $(CENSUSES='b3 b5' UNITS_b3= UNITS_b5= BUCKET_DONE=$T r /usr/local/bin/census-spot-decide)"
for id in $IDS; do . $E/s5/$id.env; aws s3 cp /tmp/fake-done $T/$WL/$PART/final/$IID/DONE --only-show-errors; done
echo "T4 every DONE, no units: $(CENSUSES='b3 b5' UNITS_b3= UNITS_b5= BUCKET_DONE=$T r /usr/local/bin/census-spot-decide)"
echo "T5 every DONE, real units: $(CENSUSES='b3 b5' BUCKET_DONE=$T r /usr/local/bin/census-spot-decide)"
echo "T6 bad census word: $(CENSUSES='bx' r /usr/local/bin/census-spot-decide)"
echo "T7 $(/usr/local/bin/census-b3-finalize --decide-only 2>&1 | tail -1)"
echo "== start $(date -u +%FT%TZ)"
/usr/local/bin/census-b5-start || { echo "census-b5-start failed"; exit 1; }
echo "censuses: $(tr '\n' ' ' < $E/censuses)"
echo "T8 real state after the start: $(r /usr/local/bin/census-spot-decide)"
echo "T9 $(/usr/local/bin/census-b5-finalize --decide-only 2>&1 | tail -1)"
echo "T10 $(/usr/local/bin/census-b3-finalize --decide-only 2>&1 | tail -1)"
if [ "$X" = a ] && [ "$(systemctl is-active census-b3-finalize.service)" = activating ]; then
  act=""; for p in $PARTS; do systemctl is-active --quiet census-b3@$p.service && act="$act $p"; done
  if [ -n "$act" ] && tail -n 1 /data/logs/finalize.log | grep -q 'waiting'; then
    echo "== stopping the waiting old census-b3-finalize (pid $(systemctl show -p MainPID --value census-b3-finalize.service); parts still running:$act)"
    systemctl stop census-b3-finalize.service; echo "census-b3-finalize: $(systemctl is-active census-b3-finalize.service); census-b3@:$(for p in $PARTS; do echo -n " $p=$(systemctl is-active census-b3@$p.service)"; done)"
  else echo "old finalize not in its wait loop (parts:$act; $(tail -n 1 /data/logs/finalize.log)): NOT stopped, NO_SHUTDOWN kept"; NOKEEP=1; fi
fi
echo "== dry-run finalize $(date -u +%FT%TZ)"
/usr/local/bin/census-b5-finalize --dry-run 2>&1 | grep -E 'check ok|FAILED|dry run' | cut -c1-200
echo "== fake spot notice test"
echo '{"action":"terminate","time":"TEST"}' > /run/census-b5-fake-spot-notice
for i in $(seq 1 24); do [ -e /run/census-b5-fake-spot-notice ] || break; sleep 5; done
sleep 5; echo "fake file gone: $([ -e /run/census-b5-fake-spot-notice ] && echo no || echo yes); test STOP files: $(ls /run/census-b5-STOP.test.* 2>/dev/null | wc -l); real STOP in clones: $(for id in $IDS; do . $E/s5/$id.env; [ -e $CTP/STOP ] && echo -n "$id "; done)"
. $E/s5/${IDS%% *}.env; aws s3 ls $B/$WL/$PART/live/ | grep -i test
journalctl -u census-b5-watch.service --no-pager -n 3 -o cat
rm -f /run/census-b5-STOP.test.*
if [ "${NOKEEP:-0}" = 0 ]; then rm -f /home/ec2-user/NO_SHUTDOWN; echo "NO_SHUTDOWN removed $(date -u +%FT%TZ)"; fi
echo "T11 $(/usr/local/bin/census-b5-finalize --decide-only 2>&1 | tail -1)"
systemctl is-active census-b5-watch.service census-b5-upload.timer census-b5-live.timer census-b3-watch.service | tr '\n' ' '; echo
for id in $IDS; do echo "$id $(systemctl show census-b5@$id.service -p ActiveState -p OOMPolicy -p ActiveEnterTimestamp | tr '\n' ' ')"; done
uptime
