#!/usr/bin/env bash
# jv-upload (an extra machine, root; jv-upload.service, a loop; "jv-upload --once" for one round).
# Each UPLOAD_EVERY s (and at once on a spot interruption notice): the new complete .blame files
# as one batch (jv_batch.sh: tar.zst, list, then sha256) to s3://B/dataset-x1k/java-split/out/<k>/batches/,
# then status.txt (counts, no names), plainblame.log (the PLAIN-BLAME lines of this part) and
# errors.log (the formatBlame error lines). Each 60 s: control/a-pos.txt -> $RS/control/apos
# and control/STOP -> $RS/control/STOP (the file the blame driver checks before each start).
# One round at a time (flock $RS/state/upload.lock).
set -uo pipefail
# Test hooks: JV_BASE (/jv), JV_ETC (/etc/java-split), JV_LIB, JV_IMDS (the metadata URL base).
RS=${JV_BASE:-/jv}; ETC=${JV_ETC:-/etc/java-split}; IMDS=${JV_IMDS:-http://169.254.169.254}
. "$ETC/jv.env"
LIB=${JV_LIB:-/usr/local/lib/java-split}
. "$LIB/jv_batch.sh"
S3P=$S3/out/$K
log() { echo "[$(date -u +%FT%TZ)] $*" | sed 's/@//g' >> $RS/logs/upload.log; }

status_text() {
  local tok itype
  tok=$(curl -s -m 2 -X PUT $IMDS/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
  itype=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $tok" $IMDS/latest/meta-data/instance-type)
  echo "part $K name $NAME instance $(cat /sys/devices/virtual/dmi/id/board_asset_tag) type $itype jobs $JOBS margin $MARGIN"
  echo "time $(date -u +%FT%TZ) epoch $(date +%s) phase $(cat $RS/state/phase 2>/dev/null || echo setup)"
  echo "part_files $(wc -l < "$RS/in/parts/part-$K.tsv")"
  echo "progress $(cat $RS/state/progress 2>/dev/null || echo none)"
  echo "blame_here $(find $RS/out/blame -type f -name '*.blame' 2>/dev/null | wc -l) sent $(sort -u $RS/state/sent.list 2>/dev/null | wc -l) batch $(cat $RS/state/seq 2>/dev/null || echo 0)"
  echo "done_last_1h $(find $RS/out/blame -type f -name '*.blame' -mmin -60 2>/dev/null | wc -l) done_last_3h $(find $RS/out/blame -type f -name '*.blame' -mmin -180 2>/dev/null | wc -l)"
  echo "plain_blame $(grep -c '^PLAIN-BLAME ' $RS/logs/blame.log 2>/dev/null) errors $(grep -c '^Error' $RS/logs/blame.log 2>/dev/null)"
  echo "git_blame_processes $(pgrep -c -f 'git -C .* blame') load $(cut -d' ' -f1-3 /proc/loadavg) mem_used_gib $(free -g | awk '/Mem:/{print $3}') of $(free -g | awk '/Mem:/{print $2}') disk_free_gib $(df -BG --output=avail "$RS" | tail -1 | tr -dc 0-9)"
  echo "gate $(cat $RS/state/gate.summary 2>/dev/null || echo none)"
}

round() {
  local seq rc=0 n
  exec 7>>$RS/state/upload.lock; flock 7
  while :; do
    seq=$(jv_batch_build $RS/out/blame $RS/state $RS/batches) || { log "batch build failed"; rc=1; break; }
    [ -n "$seq" ] || break
    n=$(wc -l < "$RS/batches/b-$seq.list")
    if jv_batch_upload "$S3P" $RS/batches "$seq"; then
      jv_batch_commit $RS/state $RS/batches "$seq" || { log "commit of b-$seq failed"; rc=1; break; }
      log "sent b-$seq: $n files"
    else log "upload of b-$seq failed ($n files): the next round sends it again"; rc=1; break; fi
  done
  status_text > $RS/state/status.txt 2>/dev/null
  aws s3 cp $RS/state/status.txt "$S3P/status.txt" --only-show-errors || rc=1
  grep '^PLAIN-BLAME ' $RS/logs/blame.log > $RS/state/plainblame.log 2>/dev/null
  aws s3 cp $RS/state/plainblame.log "$S3P/plainblame.log" --only-show-errors || rc=1
  grep -e '^Error' -e '^Unable' $RS/logs/blame.log $RS/logs/driver.out 2>/dev/null > $RS/state/errors.log
  aws s3 cp $RS/state/errors.log "$S3P/errors.log" --only-show-errors || rc=1
  flock -u 7
  return $rc
}

control() {
  if aws s3 cp "$S3/control/a-pos.txt" $RS/control/apos.tmp --only-show-errors 2>/dev/null; then
    mv -f $RS/control/apos.tmp $RS/control/apos; chmod 644 $RS/control/apos
  fi
  if aws s3 ls "$S3/control/STOP" > /dev/null 2>&1; then
    [ -e $RS/control/STOP ] || { touch $RS/control/STOP; log "control/STOP seen: no new files"; }
  fi
}

notice() {
  local tok
  tok=$(curl -s -m 2 -X PUT $IMDS/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
  [ "$(curl -s -m 2 -o /dev/null -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" $IMDS/latest/meta-data/spot/instance-action)" = 200 ]
}

if [ "${1:-}" = --once ]; then control; round; exit $?; fi
last=0; lastc=0; noticed=0
while :; do
  now=$(date +%s)
  if [ $noticed = 0 ] && notice; then
    noticed=1; touch $RS/state/spot-notice; log "spot interruption notice: one round now"; round; last=$(date +%s)
  fi
  if [ $((now - lastc)) -ge 60 ]; then control; lastc=$now; fi
  if [ $((now - last)) -ge "$UPLOAD_EVERY" ]; then round || log "round with errors"; last=$(date +%s); fi
  sleep 15
done
