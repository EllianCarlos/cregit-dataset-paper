#!/usr/bin/env bash
# rs-run (an extra machine, root; rs-run.service, started by S1-setup-start.sh).
#   1. the gate (once): blame the gate files (machine A finished them) with the same call and
#      environment, compare byte for byte with A's .blame files (rs_gate.sh). Any difference: the
#      marker GATE-FAILED, no blame, power off after GATE_FAIL_HOLD s (unless /rs/NO_SHUTDOWN).
#   2. resume: the names of the batches of this part that S3 has already (a relaunch) -> skip list;
#      the batch number goes on after the largest one in S3.
#   3. the blame: rs_blame.pl over part K, from the largest index down, JOBS at a time, as
#      ec2-user with the environment of A's step 7 (blame.env). It stops at control/STOP or when
#      it meets machine A (index <= a-pos + MARGIN).
#   4. the end: the last batch (rs-upload --once, retried), a check that every local .blame was
#      sent, the marker DONE (or STOPPED after a STOP), then power off (the instance terminates;
#      if the marker upload fails, machine A sees the part as finished when status.txt is stale).
#      An unclear end writes the marker ALERT and powers off after GATE_FAIL_HOLD s; a failed last
#      upload writes ALERT and powers off after 3 x GATE_FAIL_HOLD s.
set -uo pipefail
# Test hooks: RS_BASE (/rs), RS_ETC (/etc/rust-split), RS_LIB, RS_UPLOAD (/usr/local/bin/rs-upload),
# RS_SHUTDOWN ("shutdown -h now"), RS_RUNAS ("runuser -u ec2-user --"; split into words on purpose).
RS=${RS_BASE:-/rs}; ETC=${RS_ETC:-/etc/rust-split}
UPLOAD=${RS_UPLOAD:-/usr/local/bin/rs-upload}; SHUTDOWN=${RS_SHUTDOWN:-shutdown -h now}; RUNAS=${RS_RUNAS-runuser -u ec2-user --}
. "$ETC/rs.env"
LIB=${RS_LIB:-/usr/local/lib/rust-split}
. "$LIB/rs_gate.sh"
mapfile -t ENVV < $ETC/blame.env
S3P=$S3/out/$K
log() { echo "[$(date -u +%FT%TZ)] $*" | sed 's/@//g'; }
phase() { echo "$1" > $RS/state/phase; log "phase $1"; }
as_user() { $RUNAS env -i "${ENVV[@]}" "$@"; }
marker() {  # marker NAME TEXT: write and upload out/<k>/NAME
  echo "$2" > "$RS/state/$1"
  for _ in 1 2 3 4 5; do aws s3 cp "$RS/state/$1" "$S3P/$1" --only-show-errors && return 0; sleep 30; done
  log "upload of the marker $1 failed"; return 1
}
power_off() {  # power_off WAIT_S
  if [ -e $RS/NO_SHUTDOWN ]; then log "NO_SHUTDOWN: no power off"; return 0; fi
  [ "$1" -gt 0 ] && { log "power off in $1 s"; sleep "$1"; }
  [ -e $RS/NO_SHUTDOWN ] && { log "NO_SHUTDOWN: no power off"; return 0; }
  log "power off"; $SHUTDOWN
}

cd "$CREGIT" || exit 1
find "$CREGIT/blameRepo/build" -maxdepth 1 -name 'tmpfile-*' -delete 2>/dev/null
# 1. the gate
if [ ! -e $RS/state/GATE-OK ]; then
  phase gate
  rm -rf "$RS/gate/out"; mkdir -p "$RS/gate/out" "$RS/state/gate"; [ -n "$RUNAS" ] && chown ec2-user: "$RS/gate/out" "$RS/state/gate"
  awk -F'\t' 'NF >= 2 {print NR "\t0\t" $2}' $RS/in/gate/gate.tsv > $RS/state/gate-part.tsv
  as_user perl "$LIB/rs_blame.pl" --formatblame="$CREGIT/blameRepo/formatBlame.pl" --jobs="$(wc -l < $RS/state/gate-part.tsv)" \
    --part=$RS/state/gate-part.tsv --margin=-1 --state=$RS/state/gate "$REPO" $RS/gate/out >> $RS/logs/gate.out 2>> $RS/logs/gate.log
  if rs_gate_compare $RS/in/gate/gate.tsv $RS/in/gate/a $RS/gate/out $RS/state/gate.result > $RS/state/gate.summary; then
    log "$(cat $RS/state/gate.summary)"
    aws s3 cp $RS/state/gate.result "$S3P/gate.txt" --only-show-errors
    touch $RS/state/GATE-OK
  else
    log "$(cat $RS/state/gate.summary): the gate failed"
    aws s3 cp $RS/state/gate.result "$S3P/gate.txt" --only-show-errors
    phase gate-failed
    marker GATE-FAILED "gate failed $(date -u +%FT%TZ): $(cat $RS/state/gate.summary)"
    power_off "$GATE_FAIL_HOLD"; exit 1
  fi
fi
# 2. resume from S3
phase resume
aws s3 ls "$S3P/batches/" > "$RS/state/s3-batches.txt" 2>/dev/null
: > "$RS/state/s3sent.list"
for b in $(awk '{print $4}' "$RS/state/s3-batches.txt" | sed -n 's/^\(b-[0-9]\{6\}\)\.sha256$/\1/p' | sort); do
  grep -q " $b.tar.zst\$" "$RS/state/s3-batches.txt" && grep -q " $b.list\$" "$RS/state/s3-batches.txt" || continue
  aws s3 cp "$S3P/batches/$b.list" - --only-show-errors >> "$RS/state/s3sent.list" || { log "resume: list $b failed"; exit 1; }
done
top=$(awk '{print $4}' "$RS/state/s3-batches.txt" | sed -n 's/^b-\([0-9]\{6\}\)\..*/\1/p' | sort | tail -1)
if [ -n "$top" ] && [ "$((10#$top))" -gt "$((10#$(cat "$RS/state/seq" 2>/dev/null || echo 0)))" ]; then echo "$top" > "$RS/state/seq"; fi
# sent.list (the uploader's) holds "<name>.blame"; the driver's skip list holds "<name>".
touch "$RS/state/sent.list"
LC_ALL=C sort -u "$RS/state/s3sent.list" "$RS/state/sent.list" > "$RS/state/sent.merged" && mv -f "$RS/state/sent.merged" "$RS/state/sent.list"
sed 's/\.blame$//' "$RS/state/sent.list" > "$RS/state/skip.sorted"
log "resume: $(wc -l < "$RS/state/sent.list") names sent before, batch number $(cat "$RS/state/seq" 2>/dev/null || echo 0)"
[ -n "$RUNAS" ] && chown ec2-user: "$RS/state/skip.sorted"
# 3. the blame
phase run
rm -f $RS/state/end
as_user perl "$LIB/rs_blame.pl" --formatblame="$CREGIT/blameRepo/formatBlame.pl" --jobs="$JOBS" \
  --part="$RS/in/parts/part-$K.tsv" --skip=$RS/state/skip.sorted --apos-file=$RS/control/apos \
  --stop-file=$RS/control/STOP --margin="$MARGIN" --state=$RS/state "$REPO" $RS/out/blame >> $RS/logs/driver.out 2>> $RS/logs/blame.log
rc=$?
end=$(cut -d' ' -f1 $RS/state/end 2>/dev/null)
log "driver rc $rc, end ${end:-none}: $(tail -1 $RS/logs/driver.out)"
# 4. the end
phase final-upload
ok=0
for _ in 1 2 3 4 5 6; do
  if $UPLOAD --once; then
    (cd $RS/out/blame && find . -type f -name '*.blame' -printf '%P\n') | LC_ALL=C sort > $RS/state/final.local
    LC_ALL=C sort -u $RS/state/sent.list > $RS/state/final.sent
    if [ -z "$(LC_ALL=C comm -23 $RS/state/final.local $RS/state/final.sent | head -1)" ]; then ok=1; break; fi
  fi
  sleep 60
done
summ="part $K end ${end:-none} rc $rc $(date -u +%FT%TZ): $(tail -1 $RS/logs/driver.out | sed 's/@//g'); here $(wc -l < $RS/state/final.local 2>/dev/null) sent $(wc -l < $RS/state/final.sent 2>/dev/null) PLAIN-BLAME $(grep -c '^PLAIN-BLAME ' $RS/logs/blame.log)"
if [ $ok != 1 ]; then
  # The files that are not in S3 stay open on machine A (its restart at the end lists them), so
  # this costs time, not data. Wait 3 x GATE_FAIL_HOLD for a person, then power off.
  phase upload-failed; marker ALERT "upload failed: $summ"; log "the last upload failed"; power_off $((GATE_FAIL_HOLD * 3)); exit 1
fi
case $end in
  part-end|met-A) phase "done"; marker DONE "$summ"; power_off 0 ;;
  stop) phase stopped; marker STOPPED "$summ"; power_off 0 ;;
  *) phase alert; marker ALERT "unclear end: $summ"; power_off "$GATE_FAIL_HOLD"; exit 1 ;;
esac
