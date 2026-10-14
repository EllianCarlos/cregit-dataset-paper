set -euo pipefail
[ -e /usr/local/bin/census-b3-finalize.orig-b3only ] || cp -p /usr/local/bin/census-b3-finalize /usr/local/bin/census-b3-finalize.orig-b3only
cat > /usr/local/bin/census-b5-live.new <<'EOF_census-b5-live'
#!/usr/bin/env bash
# Every 10 min (census-b5-live.timer, ec2-user; census-b5-trim runs before it as root): status of the
# batch5 / batch1rest parts of this spot instance to each part's s3://BUCKET/<workload>/<part>/live/:
#   progress.txt  the one combined view of the instance (the same file in every part's live/). Its
#                 first line is "as of <ts>  census-b5 on <iid> (spot <x>): <state> ( <id>=<unit state> ... )
#                 finalize=<state>  batch3=<state>"; <state> is "active" while any part or the
#                 finalize runs (the local watchdog greps ": active"), then "finalized" (every part
#                 has its final DONE) or "stopped". Then load, memory, disks, and per part: unit,
#                 free space, ctp progress and the step table.
#   steps.txt     this part's step table;  <id>.log.tail;  ledger.jsonl;  system.txt (the instance).
set -uo pipefail
export AWS_PAGER=""
E=/etc/cregit-census/s5; . $E/batch.env
B=s3://${RUNNER_BUCKET}; I=/home/ec2-user/s5-input
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
T=$(mktemp -d); trap 'rm -r "$T"' EXIT
st=""; any=no; fin=yes
for id in $IDS; do s=$(systemctl is-active census-b5@$id.service); st="$st $id=$s"
  case $s in active|activating|deactivating) any=yes ;; esac
  [ -e /w/$id/final-DONE ] || fin=no; done
fz=$(systemctl is-active census-b5-finalize.service); case $fz in active|activating) any=yes ;; esac
if [ $any = yes ]; then state=active; elif [ $fin = yes ]; then state=finalized; else state=stopped; fi
b3=none; if grep -qx b3 /etc/cregit-census/censuses 2>/dev/null; then . /etc/cregit-census/batch.env; b3=inactive
  for p in $PARTS; do case $(systemctl is-active census-b3@$p.service) in active|activating|deactivating) b3=active ;; esac; done; fi
for id in $IDS; do . $E/$id.env
  /usr/local/bin/census-steps "$CTP" $I/manifest.$id.run.tsv --highlight '' > "$T/steps.$id.txt" 2>&1; done
{ echo "as of $(date -u +%FT%TZ)  census-b5 on $IID (spot $HALF): $state ($st )  finalize=$fz  batch3=$b3$([ -e /home/ec2-user/NO_SHUTDOWN ] && echo '  NO_SHUTDOWN')"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   watcher: $(systemctl is-active census-b5-watch.service)"
  echo "uploaded to done/: $(cat /w/*/uploaded/* 2>/dev/null | grep -c '^uploaded ')   hosts: $(df -BG --output=target,avail $(for id in $IDS; do . $E/$id.env; echo $HOST; done | sort -u) | tail -n +2 | tr -s ' ' | tr '\n' ' ')"
  for id in $IDS; do . $E/$id.env
    echo; echo "=== part $id ($WL/$PART): census-b5@$id $(systemctl is-active census-b5@$id.service) ($(systemctl show census-b5@$id.service -p Result --value)), $MP free $(df -BG --output=avail $MP | tail -1 | tr -d ' '), image $(du -BG $IMG | cut -f1)$([ -e $CTP/STOP ] && echo '  STOP present')$([ -e $MP/final-DONE ] && echo '  final DONE')"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest $I/manifest.$id.run.tsv --last 5 2>&1)
    echo; cat "$T/steps.$id.txt"
  done
} > "$T/progress.txt"
{ date -u +%FT%TZ; uptime; cat /proc/pressure/io /proc/pressure/cpu 2>/dev/null; cat /proc/meminfo; df -h /data /data[0-9]* /w/* / 2>/dev/null; du -h /data*/loop/*.img 2>/dev/null; } > "$T/system.txt"
for id in $IDS; do . $E/$id.env; mkdir -p $T/p/$id
  cp $T/progress.txt $T/system.txt $T/p/$id/; cp $T/steps.$id.txt $T/p/$id/steps.txt
  tail -n 300 "$LOG" > $T/p/$id/$id.log.tail 2>/dev/null
  [ -f "$CTP/ledger.jsonl" ] && cp "$CTP/ledger.jsonl" $T/p/$id/ledger.jsonl
  aws s3 cp $T/p/$id/ "$B/$WL/$PART/live/" --recursive --only-show-errors
done
EOF_census-b5-live
chmod 755 /usr/local/bin/census-b5-live.new
mv -f /usr/local/bin/census-b5-live.new /usr/local/bin/census-b5-live
cat > /usr/local/bin/census-b5-trim.new <<'EOF_census-b5-trim'
#!/usr/bin/env bash
# census-b5-trim (root, before every census-b5-live): fstrim each part's loop XFS /w/<id>, so blocks
# freed inside (cleaned-up clones) are punched out of the sparse image and the host disk gets them back.
. /etc/cregit-census/s5/batch.env
for id in $IDS; do mountpoint -q /w/$id && fstrim /w/$id >/dev/null 2>&1; done
exit 0
EOF_census-b5-trim
chmod 755 /usr/local/bin/census-b5-trim.new
mv -f /usr/local/bin/census-b5-trim.new /usr/local/bin/census-b5-trim
cat > /usr/local/bin/census-b5-watch.new <<'EOF_census-b5-watch'
#!/usr/bin/env bash
# census-b5-watch (census-b5-watch.service, root): poll IMDSv2 spot/instance-action every 5 s.
# On a notice: touch STOP in every batch5 / batch1rest part's ctp clone (no new project starts),
# write INTERRUPTED (time, notice, running projects) and the part's ledger to each part's
# s3://BUCKET/<workload>/<part>/live/, and run census-b5-upload once. EC2 terminates the instance
# about 2 min later; restart_spot.sh relaunches every unfinished workload of the half.
# (census-b3-watch does the same for the batch 3 parts, when they run here.)
# Test mode: if /run/census-b5-fake-spot-notice exists, its content is the notice; STOP then goes to
# /run/census-b5-STOP.test.<id> instead of the ctp clones and the S3 names get a .test suffix, so the
# census is not stopped. The fake file is removed after it is handled and watching goes on.
set -uo pipefail
export AWS_PAGER=""
E=/etc/cregit-census/s5; . $E/batch.env
B=s3://${RUNNER_BUCKET}
FAKE=/run/census-b5-fake-spot-notice
IMDS=http://169.254.169.254/latest
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
handle() {  # $1 notice, $2 suffix ("" or .test)
  local notice=$1 sfx=$2 T id; T=$(mktemp -d)
  for id in $IDS; do . $E/$id.env
    if [ -z "$sfx" ]; then stop=$CTP/STOP; else stop=/run/census-b5-STOP.test.$id; fi
    touch "$stop"; chown ec2-user: "$stop"
  done
  for id in $IDS; do . $E/$id.env; mkdir -p $T/$id
    { echo "spot interruption notice seen $(date -u +%FT%TZ) on $IID (spot $HALF, part $id)${sfx:+  TEST, census not stopped}"
      echo "notice: $notice"
      echo "STOP: $([ -z "$sfx" ] && echo "$CTP/STOP" || echo /run/census-b5-STOP.test.$id)"
      /usr/local/bin/census-steps "$CTP" /home/ec2-user/s5-input/manifest.$id.run.tsv --highlight '' 2>&1
      echo "uploaded to done/ so far: $(ls $MP/uploaded 2>/dev/null | wc -l)"
    } > "$T/$id/INTERRUPTED$sfx"
    [ -f "$CTP/ledger.jsonl" ] && cp "$CTP/ledger.jsonl" "$T/$id/ledger$sfx.jsonl"
    aws s3 cp "$T/$id/" "$B/$WL/$PART/live/" --recursive --only-show-errors
  done
  echo "$(date -u +%FT%TZ) handled notice${sfx:+ (test)}: $notice"
  sudo -u ec2-user /usr/local/bin/census-b5-upload
  rm -r "$T"
}
echo "$(date -u +%FT%TZ) watching $IMDS/meta-data/spot/instance-action every 5 s (spot $HALF, parts $IDS)"
while :; do
  if [ -e $FAKE ]; then handle "$(cat $FAKE)" .test; rm -f $FAKE; sleep 5; continue; fi
  tok=$(curl -s -m 2 -X PUT "$IMDS/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
  if [ -n "$tok" ]; then
    code=$(curl -s -m 2 -o /run/census-b5-instance-action -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" "$IMDS/meta-data/spot/instance-action")
    if [ "$code" = 200 ]; then echo "$(date -u +%FT%TZ) $(cat /run/census-b5-instance-action)" > /run/census-spot-interrupted
      handle "$(cat /run/census-b5-instance-action)" ""; echo "real notice handled; idle until termination"; exec sleep infinity; fi
  fi
  sleep 5
done
EOF_census-b5-watch
chmod 755 /usr/local/bin/census-b5-watch.new
mv -f /usr/local/bin/census-b5-watch.new /usr/local/bin/census-b5-watch
cat > /usr/local/bin/census-b5-finalize.new <<'EOF_census-b5-finalize'
#!/usr/bin/env bash
# census-b5-finalize (census-b5-finalize.service; OnSuccess=/OnFailure= of every census-b5@<id>).
# Waits until no batch5 / batch1rest part of this spot instance is active (a part that ends early
# does not finalize alone), runs census-b5-upload once more, then for EACH part copies its results to
# s3://BUCKET/<workload>/<part>/final/<instance-id>/ (Parquet and .validated per project, the ctp
# ledger, duckdb, state json and logs, the census log, the part and run manifests), checks every
# object (key and size) and that SHA256SUMS reads back byte-identical, and writes DONE there; when
# every project of the part manifest has done/<project>/OK it also writes <workload>/<part>/final/DONE.
# Then it terminates the instance (shutdown; shutdown behavior terminate) only if EVERY census on it
# has finalized: census-spot-decide (batch 3 parts too, when they run here).
# No shutdown if a part's copy failed, with --dry-run, if the longest part ran < 1 h and no project
# of this instance reached done/OK (an early failure), or if /home/ec2-user/NO_SHUTDOWN exists.
# After a real spot notice (/run/census-spot-interrupted) it copies nothing: done/ has every finished
# project and restart_spot.sh relaunches the rest.
# --dry-run: copy to <workload>/<part>/dryrun/<instance-id>/ without waiting, never shut down.
# --decide-only: print only the termination decision (census-spot-decide), copy nothing.
set -uo pipefail
export AWS_PAGER=""
E=/etc/cregit-census/s5; . $E/batch.env
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}; I=/home/ec2-user/s5-input
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
FLOG=/data/logs/finalize-b5.log; TM=$(mktemp -d /tmp/finalize-b5.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize-b5: $*"; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-spot-decide 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would terminate' || echo 'no termination')"; exit 0; fi
say "start dry=$DRY spot $HALF parts=$IDS"
first=${IDS%% *}
if [ $DRY = 0 ] && [ -e /run/census-spot-interrupted ]; then
  say "spot interruption notice seen ($(cat /run/census-spot-interrupted)): no final copy; done/ has the finished projects; restart with restart_spot.sh $HALF"
  (. $E/$first.env; aws s3 cp "$FLOG" "$B/$WL/$PART/live/finalize-b5.log" --only-show-errors); exit 0
fi
if [ $DRY = 0 ]; then
  waited=0
  while :; do
    act=""; for id in $IDS; do case $(systemctl is-active census-b5@$id.service) in active|activating|deactivating) act="$act $id" ;; esac; done
    [ -z "$act" ] && break
    [ $waited = 0 ] && say "parts still running:$act; waiting (this unit stays active until they end)"
    waited=1; sleep 60
  done
fi
sudo -u ec2-user /usr/local/bin/census-b5-upload || say "census-b5-upload returned $? (continuing)"
finalize_part() {  # $1 = id; returns 1 on a failed copy or check
  local id=$1 n=0 S_ DEST d name files f; . $E/$id.env
  DEST=$B/$WL/$PART/final/$IID; [ $DRY = 1 ] && DEST=$B/$WL/$PART/dryrun/$IID
  pfail() { say "$id FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > "$TM/FINALIZE_FAILED.$id"
            aws s3 cp "$TM/FINALIZE_FAILED.$id" "$DEST/FINALIZE_FAILED" --only-show-errors; return 1; }
  local svc="census-b5@$id: $(systemctl show census-b5@$id.service -p Result -p ExecMainStatus -p ExecMainExitTimestamp 2>/dev/null | tr '\n' ' ')"
  S_=$MP/final-stage; [ -d "$S_" ] && mv "$S_" "$S_.old.$(date +%s)"
  mkdir -p "$S_/projects" "$S_/ctp" "$S_/logs" || { pfail "staging dir"; return 1; }
  for d in "$OUT"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d"); [ "$name" = .pin-staging ] && continue
    files=$(find "$d" -maxdepth 1 -type f \( -name '*.parquet' -o -name '*.validated' \))
    [ -n "$files" ] || continue
    mkdir -p "$S_/projects/$name"; for f in $files; do cp -l "$f" "$S_/projects/$name/" 2>/dev/null || cp -p "$f" "$S_/projects/$name/" || { pfail "copy $f"; return 1; }; done; n=$((n+1))
  done
  for f in ledger.jsonl ctp.duckdb metrics.tsv resources.tsv runs.log; do [ -f "$CTP/$f" ] && { cp -p "$CTP/$f" "$S_/ctp/" || { pfail "copy $f"; return 1; }; }; done
  if [ -d "$CTP/state" ]; then
    ( cd "$CTP" && find state -maxdepth 1 -mindepth 1 -type d | while read -r s; do
        mkdir -p "$S_/ctp/$s/logs"; find "$s" -maxdepth 1 -type f -name '*.json' -exec cp -p {} "$S_/ctp/$s/" \;
        [ -d "$s/logs" ] && find "$s/logs" -maxdepth 1 -type f -exec cp -p {} "$S_/ctp/$s/logs/" \; ; done ) || { pfail "copy state"; return 1; }
  fi
  [ -f "$LOG" ] && cp -p "$LOG" "$S_/logs/"
  cp -p $I/manifest.$id.tsv $I/manifest.$id.run.tsv $E/$id.env $E/$id.cfg "$S_/logs/" 2>/dev/null
  ( cd "$S_" && find . -type f ! -name SHA256SUMS -printf '%P\0' | sort -z | xargs -0 -r sha256sum > SHA256SUMS ) || { pfail "sha256"; return 1; }
  say "$id: staged $(wc -l < "$S_/SHA256SUMS") files ($n projects), $(du -sh "$S_" | cut -f1) -> $DEST"
  aws s3 cp "$S_/" "$DEST/" --recursive --only-show-errors --checksum-algorithm SHA256 || { pfail "upload"; return 1; }
  ( cd "$S_" && find . -type f -printf '%P\t%s\n' | sort ) > "$TM/final.local.$id"
  aws s3 ls "$DEST/" --recursive | awk -v p="${DEST#s3://*/}/" '{k=$0; sub(/^[^ ]+ +[^ ]+ +[0-9]+ /,"",k); sub("^" p,"",k); print k "\t" $3}' | grep -v -e '^DONE	' -e '^FINALIZE_FAILED	' | sort > "$TM/final.remote.$id" || { pfail "list"; return 1; }
  local missing; missing=$(comm -23 "$TM/final.local.$id" "$TM/final.remote.$id" | wc -l)
  [ "$missing" = 0 ] || { comm -23 "$TM/final.local.$id" "$TM/final.remote.$id" | head; pfail "$missing staged files are missing or differ in size in $DEST"; return 1; }
  aws s3 cp "$DEST/SHA256SUMS" "$TM/final.sums.$id" --only-show-errors && cmp "$TM/final.sums.$id" "$S_/SHA256SUMS" || { pfail "SHA256SUMS read-back differs"; return 1; }
  ( cd "$S_" && sha256sum --quiet -c SHA256SUMS ) || { pfail "staged files changed during upload"; return 1; }
  say "$id: check ok: $(wc -l < "$TM/final.local.$id") objects, sizes equal, SHA256SUMS read back identical"
  { echo "cregit census $WL part $PART ($id) finished and copied: $(date -u +%FT%TZ)"
    echo "instance: $IID  spot $HALF  dry_run=$DRY"
    echo "$svc"
    echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")   uploaded to done/ by this instance: $(ls $MP/uploaded 2>/dev/null | wc -l)"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest $I/manifest.$id.run.tsv --last 3 2>&1 | head -5)
    echo "--- SHA256SUMS"; cat "$S_/SHA256SUMS"; } > "$TM/DONE.$id"
  aws s3 cp "$TM/DONE.$id" "$DEST/DONE" --only-show-errors && aws s3 ls "$DEST/DONE" >/dev/null || { pfail "DONE upload"; return 1; }
  say "$id: DONE written to $DEST/DONE"
  [ $DRY = 0 ] && cp "$TM/DONE.$id" $MP/final-DONE
  local want have left
  want=$(grep -v -e '^#' -e '^[[:space:]]*$' $I/manifest.$id.tsv | cut -f1 | sort -u)
  have=$(aws s3 ls "$B/$WL/$PART/done/" --recursive | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u)
  left=$(comm -23 <(echo "$want") <(echo "$have") | grep -c . || true)
  if [ "$left" = 0 ] && [ $DRY = 0 ]; then
    aws s3 cp "$TM/DONE.$id" "$B/$WL/$PART/final/DONE" --only-show-errors && say "$id: every project of the part has done/OK: wrote $B/$WL/$PART/final/DONE"
  else say "$id: $left projects of the part have no done/OK yet (restart_spot.sh $HALF runs them)"; fi
  return 0
}
bad=""
for id in $IDS; do finalize_part $id || bad="$bad $id"; done
(. $E/$first.env; aws s3 cp "$FLOG" "$B/$WL/$PART/$([ $DRY = 1 ] && echo dryrun || echo final)/$IID/finalize-b5.log" --only-show-errors)
if [ $DRY = 1 ]; then why=$(/usr/local/bin/census-spot-decide 2>&1); rc=$?
  say "dry run: no shutdown (a real run would: $why -> $([ $rc = 0 ] && echo terminate || echo 'no termination'))"; exit 0; fi
[ -z "$bad" ] || { say "the final copy failed for:$bad: no shutdown; look at $FLOG"; exit 1; }
ran=0; up=$(cat /w/*/uploaded/* 2>/dev/null | grep -c '^uploaded ')
for id in $IDS; do
  st=$(systemctl show census-b5@$id.service -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show census-b5@$id.service -p ExecMainExitTimestampMonotonic --value)
  r=$(( (${ex:-0} - ${st:-0}) / 1000000 )); [ "$r" -gt "$ran" ] && ran=$r
done
if [ "$ran" -lt 3600 ] && [ "$up" = 0 ]; then say "the longest part ran only ${ran}s (< 1 h) and no project reached done/OK: an early failure, so no shutdown; look at /data/logs/b5-*.log"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no shutdown"; exit 0; fi
if ! why=$(/usr/local/bin/census-spot-decide 2>&1); then say "$why: no shutdown; the last census on this instance to finalize terminates it"; exit 0; fi
say "$why"
say "shutting down: this one-time spot instance terminates (shutdown behavior terminate)"
sync; shutdown -h now
EOF_census-b5-finalize
chmod 755 /usr/local/bin/census-b5-finalize.new
mv -f /usr/local/bin/census-b5-finalize.new /usr/local/bin/census-b5-finalize
cat > /usr/local/bin/census-spot-decide.new <<'EOF_census-spot-decide'
#!/usr/bin/env bash
# census-spot-decide (2026-10-09): exit 0 when EVERY census on this spot instance has finalized, so
# the instance may terminate; otherwise print why not and exit 1. Called by census-b3-finalize and
# census-b5-finalize just before they would shut down (shutdown behavior terminate); each writes its
# own DONE first, so only the last census to finalize terminates the instance.
# The censuses of this instance are the words in /etc/cregit-census/censuses (default "b3", the
# batch 3 rule before 2026-10-09):
#   b3: no census-b3@<part> (PARTS of /etc/cregit-census/batch.env) is active, and
#       s3://BUCKET/batch3/<a|b>/final/<instance-id>/DONE exists (census-b3-finalize, after its check);
#   b5: no census-b5@<id> (IDS of /etc/cregit-census/s5/batch.env) is active, and for every part
#       s3://BUCKET/<workload>/<part>/final/<instance-id>/DONE exists (census-b5-finalize).
# Test overrides: CENSUSES (the list), IID, BUCKET_DONE (prefix used for the DONE lookups instead of
# s3://BUCKET; e.g. a dry-run prefix), UNITS_b3 / UNITS_b5 (space-separated units; "" = none).
set -uo pipefail
export AWS_PAGER=""
B=${BUCKET_DONE:-s3://${RUNNER_BUCKET}}
IID=${IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
CENSUSES=${CENSUSES-$(cat /etc/cregit-census/censuses 2>/dev/null || echo b3)}
[ -n "$(echo $CENSUSES)" ] || CENSUSES=b3
ok=""
for c in $CENSUSES; do
  case $c in
    b3) . /etc/cregit-census/batch.env
        units=${UNITS_b3-$(for p in $PARTS; do echo census-b3@$p.service; done)}
        urls="$B/batch3/$BATCH/final/$IID/DONE" ;;
    b5) . /etc/cregit-census/s5/batch.env
        units=${UNITS_b5-$(for i in $IDS; do echo census-b5@$i.service; done)}
        urls=$(for i in $IDS; do . /etc/cregit-census/s5/$i.env; echo "$B/$WL/$PART/final/$IID/DONE"; done) ;;
    *) echo "unknown census '$c' in /etc/cregit-census/censuses"; exit 2 ;;
  esac
  for u in $units; do s=$(systemctl is-active "$u")
    case $s in active|activating|reloading|deactivating) echo "census $c not finalized: $u is $s"; exit 1 ;; esac; done
  for url in $urls; do aws s3 ls "$url" >/dev/null 2>&1 || { echo "census $c not finalized: $url is missing"; exit 1; }; done
  ok="$ok $c($(echo $urls | wc -w) DONE)"
done
echo "every census on this instance finalized:$ok (units not active, DONE in S3)"
EOF_census-spot-decide
chmod 755 /usr/local/bin/census-spot-decide.new
mv -f /usr/local/bin/census-spot-decide.new /usr/local/bin/census-spot-decide
cat > /usr/local/bin/census-b3-finalize.new <<'EOF_census-b3-finalize'
#!/usr/bin/env bash
# census-b3-finalize (census-b3-finalize.service; OnSuccess=/OnFailure= of every census-b3@<part>).
# Waits until no census part of this spot instance is active (so a part that ends early does not
# finalize alone), runs census-b3-upload once more, then copies the results of ALL parts to
# s3://BUCKET/batch3/<a|b>/final/<instance-id>/, checks every object (key and size) and SHA256SUMS
# against the local files, writes DONE there and, when every project of manifest.batch3<a|b>.tsv
# has done/<project>/OK, also batch3/<a|b>/final/DONE (the batch is complete). Then it shuts down.
# The instance was launched with shutdown behavior "terminate", so it TERMINATES (it is a one-time
# spot instance; nothing is left on it after this).
# After a real spot notice (/run/census-spot-interrupted, from census-b3-watch) it copies nothing:
# done/ has every finished project, and restart_spot.sh runs the rest.
# No shutdown if the check fails, with --dry-run, if the longest part ran < 1 h, or if
# /home/ec2-user/NO_SHUTDOWN exists.
# 2026-10-09 (batch 5): the instance may carry other censuses (batch5 / batch1rest parts,
# census-b5@<id>). It terminates only when EVERY census on it has finalized: census-spot-decide
# decides, after this finalize wrote its DONE, so the last census to finalize terminates it.
# --decide-only: print only the termination decision (census-spot-decide), copy nothing.
# --dry-run: copy to batch3/<a|b>/dryrun/ without waiting for the parts, never shut down.
#   CTP_<part>/OUT_<part> in the environment override a part's ctp clone and output dir.
set -uo pipefail
. /etc/cregit-census/batch.env
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
DEST=$B/batch3/$BATCH/final/$IID; [ $DRY = 1 ] && DEST=$B/batch3/$BATCH/dryrun/$IID
S_=/data/final-stage; FLOG=/data/logs/finalize.log; TM=$(mktemp -d /tmp/finalize.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize: $*"; }
fail() { say "FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > "$TM/FINALIZE_FAILED"
         aws s3 cp "$TM/FINALIZE_FAILED" "$DEST/FINALIZE_FAILED" --only-show-errors; aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors; exit 1; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-spot-decide 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would terminate' || echo 'no termination')"; exit 0; fi
part_env() { . /etc/cregit-census/$1.env; local c="CTP_$1" o="OUT_$1"; CTP=${!c:-$CTP}; OUT=${!o:-$OUT}; }
say "start dry=$DRY batch3$BATCH parts=$PARTS DEST=$DEST"
if [ $DRY = 0 ] && [ -e /run/census-spot-interrupted ]; then
  say "spot interruption notice seen ($(cat /run/census-spot-interrupted)): no final copy; done/ has the finished projects; restart with restart_spot.sh $BATCH"
  aws s3 cp "$FLOG" "$B/batch3/$BATCH/live/finalize.log" --only-show-errors; exit 0
fi
if [ $DRY = 0 ]; then
  waited=0
  while :; do
    act=""; for p in $PARTS; do case $(systemctl is-active census-b3@$p.service) in active|activating|deactivating) act="$act $p" ;; esac; done
    [ -z "$act" ] && break
    [ $waited = 0 ] && say "parts still running:$act; waiting (this unit stays active until they end)"
    waited=1; sleep 60
  done
fi
svc=""; for p in $PARTS; do svc="$svc | census-b3@$p: $(systemctl show census-b3@$p.service -p Result -p ExecMainStatus -p ExecMainExitTimestamp 2>/dev/null | tr '\n' ' ')"; done
say "parts:$svc"
sudo -u ec2-user /usr/local/bin/census-b3-upload || say "census-b3-upload returned $? (continuing)"
[ -d "$S_" ] && mv "$S_" "$S_.old.$(date +%s)"
mkdir -p "$S_/projects" "$S_/ctp" "$S_/logs" || fail "staging dir"
n=0
for p in $PARTS; do part_env $p
  for d in "$OUT"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d"); [ "$name" = .pin-staging ] && continue
    files=$(find "$d" -maxdepth 1 -type f \( -name '*.parquet' -o -name '*.validated' \))
    [ -n "$files" ] || continue
    mkdir -p "$S_/projects/$name"; for f in $files; do cp -l "$f" "$S_/projects/$name/" 2>/dev/null || cp -p "$f" "$S_/projects/$name/" || fail "copy $f"; done; n=$((n+1))
  done
  mkdir -p "$S_/ctp/$p"
  for f in ledger.jsonl ctp.duckdb metrics.tsv resources.tsv runs.log; do [ -f "$CTP/$f" ] && { cp -p "$CTP/$f" "$S_/ctp/$p/" || fail "copy $p/$f"; }; done
  if [ -d "$CTP/state" ]; then  # absent when the part was stopped before its first project
  ( cd "$CTP" && find state -maxdepth 1 -mindepth 1 -type d | while read -r s; do
      mkdir -p "$S_/ctp/$p/$s/logs"; find "$s" -maxdepth 1 -type f -name '*.json' -exec cp -p {} "$S_/ctp/$p/$s/" \;
      [ -d "$s/logs" ] && find "$s/logs" -maxdepth 1 -type f -exec cp -p {} "$S_/ctp/$p/$s/logs/" \; ; done ) || fail "copy state $p"
  fi
  [ -f "$LOG" ] && cp -p "$LOG" "$S_/logs/"
  cp -p /home/ec2-user/b3-input/manifest.$p.full.tsv /home/ec2-user/b3-input/manifest.$p.run.tsv "$S_/logs/" 2>/dev/null
done
say "projects with a Parquet or stamp: $n"
cp -p /data/logs/build.log "$S_/logs/" 2>/dev/null
journalctl -u census-b3-upload.service -u census-b3-watch.service --no-pager -o short-iso > "$S_/logs/upload-watch.journal" 2>/dev/null
( cd "$S_" && find . -type f ! -name SHA256SUMS -printf '%P\0' | sort -z | xargs -0 -r sha256sum > SHA256SUMS ) || fail "sha256"
say "staged $(wc -l < "$S_/SHA256SUMS") files, $(du -sh "$S_" | cut -f1)"
aws s3 cp "$S_/" "$DEST/" --recursive --only-show-errors --checksum-algorithm SHA256 || fail "upload"
# Check 1: every staged file is in the bucket with the same size.
( cd "$S_" && find . -type f -printf '%P\t%s\n' | sort ) > "$TM/final.local"
aws s3 ls "$DEST/" --recursive | awk -v p="${DEST#s3://*/}/" '{k=$0; sub(/^[^ ]+ +[^ ]+ +[0-9]+ /,"",k); sub("^" p,"",k); print k "\t" $3}' | grep -v -e '^DONE	' -e '^finalize.log	' -e '^FINALIZE_FAILED	' | sort > "$TM/final.remote" || fail "list"
missing=$(comm -23 "$TM/final.local" "$TM/final.remote" | wc -l)
[ "$missing" = 0 ] || { comm -23 "$TM/final.local" "$TM/final.remote" | head; fail "$missing staged files are missing or differ in size in $DEST"; }
# Check 2: the uploaded SHA256SUMS reads back byte-identical, and the staged files still match it.
aws s3 cp "$DEST/SHA256SUMS" "$TM/final.sums" --only-show-errors && cmp "$TM/final.sums" "$S_/SHA256SUMS" || fail "SHA256SUMS read-back differs"
( cd "$S_" && sha256sum --quiet -c SHA256SUMS ) || fail "staged files changed during upload"
say "check ok: $(wc -l < "$TM/final.local") objects, sizes equal, SHA256SUMS read back identical"
{ echo "cregit census batch3$BATCH finished and copied: $(date -u +%FT%TZ)"
  echo "instance: $(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)  dry_run=$DRY  parts: $PARTS"
  echo "parts:$svc"
  echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")   uploaded to done/: $(ls /data/uploaded 2>/dev/null | wc -l)"
  for p in $PARTS; do part_env $p; echo "--- part $p: ctp progress"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest ${MANIFEST:-/home/ec2-user/b3-input/manifest.$p.run.tsv} --last 3 2>&1 | head -5); done
  echo "--- SHA256SUMS"; cat "$S_/SHA256SUMS"; } > "$TM/DONE"
aws s3 cp "$TM/DONE" "$DEST/DONE" --only-show-errors && aws s3 ls "$DEST/DONE" >/dev/null || fail "DONE upload"
aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors
say "DONE written to $DEST/DONE"
want=$(grep -v -e '^#' -e '^[[:space:]]*$' /home/ec2-user/b3-input/manifest.batch3$BATCH.tsv | cut -f1 | sort -u)
have=$(aws s3 ls "$B/batch3/$BATCH/done/" --recursive | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u)
left=$(comm -23 <(echo "$want") <(echo "$have") | grep -c . || true)
if [ "$left" = 0 ] && [ $DRY = 0 ]; then
  aws s3 cp "$TM/DONE" "$B/batch3/$BATCH/final/DONE" --only-show-errors && say "every project of batch3$BATCH has done/OK: wrote $B/batch3/$BATCH/final/DONE"
else
  say "$left projects of batch3$BATCH have no done/OK yet: batch not complete (restart_spot.sh $BATCH runs them)"
fi
if [ $DRY = 1 ]; then say "dry run: no shutdown"; exit 0; fi
ran=0
for p in $PARTS; do
  st=$(systemctl show census-b3@$p.service -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show census-b3@$p.service -p ExecMainExitTimestampMonotonic --value)
  r=$(( (${ex:-0} - ${st:-0}) / 1000000 )); [ "$r" -gt "$ran" ] && ran=$r
done
if [ "$ran" -lt 3600 ]; then say "the longest part ran only ${ran}s (< 1 h): an early failure, so no shutdown; look at /data/logs/batch3-*.log"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no shutdown"; exit 0; fi
if ! why=$(/usr/local/bin/census-spot-decide 2>&1); then say "$why: no shutdown; the last census on this instance to finalize terminates it"; exit 0; fi
say "$why"
say "shutting down: this one-time spot instance terminates (shutdown behavior terminate)"
sync; shutdown -h now
EOF_census-b3-finalize
chmod 755 /usr/local/bin/census-b3-finalize.new
mv -f /usr/local/bin/census-b3-finalize.new /usr/local/bin/census-b3-finalize
cat > /etc/systemd/system/census-b5@.service.new <<'EOF_census-b5@.service'
[Unit]
Description=cregit census batch5/batch1rest spot part %i (ctp census, own loop XFS /w/%i)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/w/%i
OnSuccess=census-b5-finalize.service
OnFailure=census-b5-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/w/%i/ctp
ExecStart=/usr/local/bin/census-b5-run %i
StandardOutput=append:/data/logs/b5-%i.log
StandardError=append:/data/logs/b5-%i.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-b5@.service
chmod 644 /etc/systemd/system/census-b5@.service.new
mv -f /etc/systemd/system/census-b5@.service.new /etc/systemd/system/census-b5@.service
cat > /etc/systemd/system/census-b5-finalize.service.new <<'EOF_census-b5-finalize.service'
[Unit]
Description=cregit census batch5/batch1rest spot: wait for all parts, copy results to S3, write DONE, terminate if every census on the instance finalized

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-b5-finalize
TimeoutStartSec=infinity
EOF_census-b5-finalize.service
chmod 644 /etc/systemd/system/census-b5-finalize.service.new
mv -f /etc/systemd/system/census-b5-finalize.service.new /etc/systemd/system/census-b5-finalize.service
cat > /etc/systemd/system/census-b5-live.service.new <<'EOF_census-b5-live.service'
[Unit]
Description=cregit census batch5/batch1rest spot: live status to S3

[Service]
Type=oneshot
User=ec2-user
# fstrim of the loop filesystems needs root ("+"): it hands freed blocks back to the host disk
ExecStartPre=+/usr/local/bin/census-b5-trim
ExecStart=/usr/local/bin/census-b5-live
TimeoutStartSec=600
EOF_census-b5-live.service
chmod 644 /etc/systemd/system/census-b5-live.service.new
mv -f /etc/systemd/system/census-b5-live.service.new /etc/systemd/system/census-b5-live.service
cat > /etc/systemd/system/census-b5-live.timer.new <<'EOF_census-b5-live.timer'
[Unit]
Description=cregit census batch5/batch1rest spot: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s
EOF_census-b5-live.timer
chmod 644 /etc/systemd/system/census-b5-live.timer.new
mv -f /etc/systemd/system/census-b5-live.timer.new /etc/systemd/system/census-b5-live.timer
cat > /etc/systemd/system/census-b5-upload.service.new <<'EOF_census-b5-upload.service'
[Unit]
Description=cregit census batch5/batch1rest spot: copy finished projects to S3 <workload>/<part>/done/

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-b5-upload
TimeoutStartSec=3600
EOF_census-b5-upload.service
chmod 644 /etc/systemd/system/census-b5-upload.service.new
mv -f /etc/systemd/system/census-b5-upload.service.new /etc/systemd/system/census-b5-upload.service
cat > /etc/systemd/system/census-b5-upload.timer.new <<'EOF_census-b5-upload.timer'
[Unit]
Description=cregit census batch5/batch1rest spot: copy finished projects to S3 every minute

[Timer]
OnActiveSec=1min
OnUnitActiveSec=1min
AccuracySec=10s
EOF_census-b5-upload.timer
chmod 644 /etc/systemd/system/census-b5-upload.timer.new
mv -f /etc/systemd/system/census-b5-upload.timer.new /etc/systemd/system/census-b5-upload.timer
cat > /etc/systemd/system/census-b5-watch.service.new <<'EOF_census-b5-watch.service'
[Unit]
Description=cregit census batch5/batch1rest spot: watch for a spot interruption notice (IMDSv2)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/census-b5-watch
Restart=always
RestartSec=5
EOF_census-b5-watch.service
chmod 644 /etc/systemd/system/census-b5-watch.service.new
mv -f /etc/systemd/system/census-b5-watch.service.new /etc/systemd/system/census-b5-watch.service
echo "s5 files installed: $(sha256sum /usr/local/bin/census-b3-finalize /usr/local/bin/census-spot-decide /usr/local/bin/census-b5-finalize | cut -c1-12 | tr "\n" " ")"
