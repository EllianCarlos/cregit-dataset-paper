# L2-install.sh (batch 2 instance): census batch5L, part 2: install (census-other-done with batch5L,
# the guard extended to /b5L, the batch5L run/live/finalize scripts and units), daemon-reload only
# after NeedDaemonReload=no on every existing census unit, power-off rule tests, dry-run finalize,
# then the start. census-batch2, census-batch3L and census-batch4p* are not restarted, stopped or reloaded.
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin; S3=s3://${RUNNER_BUCKET}
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = bf70ea3baf787d44 ] || [ -e $B/census-other-done.orig-3census ] || { echo "census-other-done changed"; exit 1; }
[ "$(sha256sum /b5L/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet | cut -d' ' -f1)" = 40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d ] || { echo "no identity check of /b5L/cregit-ec2"; exit 1; }
U="census-batch2.service census-batch3L.service census-batch3L-wait.service census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch2-finalize.service census-batch3L-finalize.service census-batch4-finalize.service census-batch2-live.timer census-batch3L-live.timer census-batch4-live.timer census-batch4-guard.timer census-batch4-guard.service"
for u in $U; do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; aborting"; exit 1; }; done
echo "NeedDaemonReload=no for all $(echo $U | wc -w) existing census units"
before=$(systemctl show census-batch2.service census-batch3L.service census-batch4p1.service census-batch4p2.service census-batch4p3.service -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')
[ -e $B/census-other-done.orig-3census ] || cp -p $B/census-other-done $B/census-other-done.orig-3census
[ -e $B/census-batch4-guard.orig-b4 ] || cp -p $B/census-batch4-guard $B/census-batch4-guard.orig-b4
[ -e /b5L/ctp/STOP ] && { echo "STOP in /b5L/ctp"; exit 1; }
cat > /usr/local/bin/census-other-done.new <<'EOF_census-other-done'
#!/usr/bin/env bash
# census-other-done SELF: exit 0 when EVERY OTHER census on the batch 2 instance has finalized,
# i.e. its final/DONE is in S3 (a finalize writes DONE only after its upload check passed) and
# its census units are not active. The censuses on this instance (2026-10-09 13:xx, batch 4 added):
#   batch2  : s3://B/batch2/final/DONE,  units census-batch2.service
#   batch3L : s3://B/batch3L/final/DONE, units census-batch3L-wait.service census-batch3L.service
#   batch4  : s3://B/batch4/final/DONE,  units census-batch4p1.service census-batch4p2.service census-batch4p3.service
#   batch5L : s3://B/batch5L/final/DONE, units census-batch5L.service (2026-10-09 ~16:xx, batch 5 added)
# Each finalize writes its own DONE before it asks, so the last census to finish sees all the
# other DONEs and powers off; the earlier ones do not. Same interface as the 2-census version
# (SELF = batch2|batch3L, plus batch4 and batch5L), so the older finalizes are unchanged.
# Test overrides, per census N: DONE_URL_N (an S3 object) and UNITS_N (space-separated; "" = none).
set -uo pipefail
B=s3://${RUNNER_BUCKET}
ALL="batch2 batch3L batch4 batch5L"
declare -A U=(
  [batch2]="census-batch2.service"
  [batch3L]="census-batch3L-wait.service census-batch3L.service"
  [batch4]="census-batch4p1.service census-batch4p2.service census-batch4p3.service"
  [batch5L]="census-batch5L.service"
)
self=${1:-}
case " $ALL " in *" $self "*) [ -n "$self" ] || { echo "usage: census-other-done batch2|batch3L|batch4|batch5L" >&2; exit 2; } ;;
  *) echo "usage: census-other-done batch2|batch3L|batch4|batch5L" >&2; exit 2 ;; esac
ok=""
for n in $ALL; do
  [ "$n" = "$self" ] && continue
  uv="UNITS_$n"; dv="DONE_URL_$n"
  units=${!uv-${U[$n]}}; url=${!dv:-$B/$n/final/DONE}
  for u in $units; do
    s=$(systemctl is-active "$u")
    case $s in active|activating|reloading|deactivating) echo "other census $n not finalized: $u is $s"; exit 1 ;; esac
  done
  aws s3 ls "$url" >/dev/null 2>&1 || { echo "other census $n not finalized: $url is missing"; exit 1; }
  ok="$ok $n"
done
echo "every other census finalized:$ok (DONE in S3, units not active)"
EOF_census-other-done
chmod 755 /usr/local/bin/census-other-done.new; mv -f /usr/local/bin/census-other-done.new /usr/local/bin/census-other-done
cat > /usr/local/bin/census-batch4-guard.new <<'EOF_census-batch4-guard'
#!/usr/bin/env bash
# census-batch4-guard (root, every 10 min). The loop images /data/loop/b4pK.img are sparse files on
# the RAID0 /data that batch 2 and batch 3L also use. (1) fstrim each /b4pK, so blocks freed inside
# (cleaned-up clones) are punched out of the image and returned to /data (measured 13:12: the
# discard mount option alone did not shrink the image, fstrim did). (2) If /data has less than
# GUARD_GB (default 800) GiB free, touch STOP in every batch 4 ctp clone: running batch 4 projects
# finish, no new one starts, so batch 4 cannot fill /data under batch 2 / batch 3L.
# 2026-10-09 (batch 5): the same for census batch5L on /data/loop/b5L.img, /b5L: fstrim /b5L, and
# below the guard also touch /b5L/ctp/STOP.
set -uo pipefail
export AWS_PAGER=""
G=${GUARD_GB:-800}
for k in 1 2 3; do mountpoint -q /b4p$k && fstrim /b4p$k >/dev/null; done
mountpoint -q /b5L && fstrim /b5L >/dev/null
avail=$(df -BG --output=avail /data | tail -1 | tr -dc 0-9)
img=$(for k in 1 2 3; do echo -n "b4p$k $(du -BG /data/loop/b4p$k.img | cut -f1) "; done; [ -e /data/loop/b5L.img ] && echo -n "b5L $(du -BG /data/loop/b5L.img | cut -f1)")
msg="$(date -u +%FT%TZ) /data free ${avail}G (guard ${G}G); image use: $img"
if [ "$avail" -lt "$G" ]; then
  for k in 1 2 3; do [ -d /b4p$k/ctp ] && { touch /b4p$k/ctp/STOP; chown ec2-user: /b4p$k/ctp/STOP; }; done
  [ -d /b5L/ctp ] && { touch /b5L/ctp/STOP; chown ec2-user: /b5L/ctp/STOP; }
  msg="$msg; BELOW GUARD: STOP written in /b4p1..3/ctp and /b5L/ctp"
  echo "$msg" > /run/census-batch4-guard.tripped
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch4/live/GUARD --only-show-errors
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch5L/live/GUARD --only-show-errors
fi
echo "$msg" > /run/census-batch4-guard.status
echo "$msg"
EOF_census-batch4-guard
chmod 755 /usr/local/bin/census-batch4-guard.new; mv -f /usr/local/bin/census-batch4-guard.new /usr/local/bin/census-batch4-guard
cat > /usr/local/bin/census-batch5L-run.new <<'EOF_census-batch5L-run'
#!/usr/bin/env bash
# census-batch5L-run (census-batch5L.service): the L projects of batch1rest and batch5 (5) on the
# batch 2 instance, on their own loop XFS /b5L (own rename lock) with their own ctp clone /b5L/ctp,
# cregit copy /b5L/cregit-ec2 (95cdc88; path fixed before the start), config and output
# /b5L/census-2026-10-batch5L. One worker per project. Stop after the running projects:
# touch /b5L/ctp/STOP (census-batch4-guard does it below 800 GiB free on /data).
set -euo pipefail
I=/home/ec2-user/batch5-input; M=$I/manifest.batch5L.tsv
export CTP_CONFIG=/home/ec2-user/census-batch5L.cfg
cd /b5L/ctp
n=$(grep -c -v -e '^#' -e '^[[:space:]]*$' "$M")
echo "=== $(date -u +%FT%TZ) census-batch5L start (cregit $(git -C /b5L/cregit-ec2 rev-parse --short HEAD) at /b5L/cregit-ec2, ctp $(git rev-parse --short HEAD), $n projects, $n workers, out /b5L/census-2026-10-batch5L)"
exec .venv/bin/python ctp.py census --manifest "$M" --project-meta "$I/project_meta.batch5L.json" \
    --workers "$n" --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300
EOF_census-batch5L-run
chmod 755 /usr/local/bin/census-batch5L-run.new; mv -f /usr/local/bin/census-batch5L-run.new /usr/local/bin/census-batch5L-run
cat > /usr/local/bin/census-batch5L-live.new <<'EOF_census-batch5L-live'
#!/usr/bin/env bash
# Every 10 min (census-batch5L-live.timer): status of census batch5L to s3://BUCKET/batch5L/live/:
# progress.txt (first line "as of <ts>  census-batch5L: <state> ...", read by the local watchdog: it
# must contain ": active" while the census runs), steps.txt, batch5L.log.tail, ledger.jsonl, system.txt.
set -uo pipefail
export AWS_PAGER=""
D=s3://${RUNNER_BUCKET}/batch5L/live
I=/home/ec2-user/batch5-input
T=$(mktemp -d); trap 'rm -r "$T"' EXIT
s=$(systemctl is-active census-batch5L.service)
/usr/local/bin/census-steps /b5L/ctp "$I/manifest.batch5L.tsv" --highlight '' > "$T/steps.txt" 2>&1
{ echo "as of $(date -u +%FT%TZ)  census-batch5L: $s  finalize=$(systemctl is-active census-batch5L-finalize.service)"
  echo "census-batch2=$(systemctl is-active census-batch2.service)  census-batch3L=$(systemctl is-active census-batch3L.service)  census-batch4p1..3=$(systemctl is-active census-batch4p1.service census-batch4p2.service census-batch4p3.service | tr '\n' ' ')"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   /data free: $(df -BG --output=avail /data | tail -1 | tr -d ' ')   /b5L free: $(df -BG --output=avail /b5L | tail -1 | tr -d ' ')   image: $(du -BG /data/loop/b5L.img | cut -f1)$([ -e /b5L/ctp/STOP ] && echo '  STOP present')"
  echo "guard: $(cat /run/census-batch4-guard.status 2>/dev/null || echo none)"
  [ -e /run/census-batch4-guard.tripped ] && echo "GUARD TRIPPED: $(cat /run/census-batch4-guard.tripped)"
  echo; (cd /b5L/ctp && CTP_CONFIG=/home/ec2-user/census-batch5L.cfg .venv/bin/python ctp.py progress --manifest "$I/manifest.batch5L.tsv" --last 5 2>&1)
  echo; cat "$T/steps.txt"
} > "$T/progress.txt"
tail -n 300 /data/logs/batch5L.log > "$T/batch5L.log.tail" 2>/dev/null
[ -f /b5L/ctp/ledger.jsonl ] && cp /b5L/ctp/ledger.jsonl "$T/ledger.jsonl"
{ date -u +%FT%TZ; uptime; cat /proc/pressure/io /proc/pressure/cpu /proc/pressure/memory 2>/dev/null; cat /proc/meminfo; df -h /data /b4p1 /b4p2 /b4p3 /b5L /; du -h /data/loop/*.img; } > "$T/system.txt" 2>&1
aws s3 cp "$T/" "$D/" --recursive --only-show-errors
EOF_census-batch5L-live
chmod 755 /usr/local/bin/census-batch5L-live.new; mv -f /usr/local/bin/census-batch5L-live.new /usr/local/bin/census-batch5L-live
cat > /usr/local/bin/census-batch5L-finalize.new <<'EOF_census-batch5L-finalize'
#!/usr/bin/env bash
# census-batch5L-finalize (census-batch5L-finalize.service; OnSuccess=/OnFailure= of census-batch5L),
# made from census-batch4-finalize (one part "L"). Copies the results of census batch5L (the L
# projects of batch1rest and batch5) to s3://BUCKET/batch5L/final/, checks every object (key and size)
# and SHA256SUMS against the local files, writes DONE. Then it powers the instance off (stop, not
# terminate) only if EVERY other census on this instance (batch 2, batch 3L, batch 4) has
# finalized: /usr/local/bin/census-other-done batch5L decides; the last census to finalize powers off.
# No power-off if the check fails, with --dry-run, if the longest part ran < 1 h, or if
# /home/ec2-user/NO_SHUTDOWN exists.
# --dry-run: copy to batch5L/dryrun/, never power off.
#   CTP_L / OUT_L in the environment override the ctp clone and output dir; MANIFEST the
#   manifest given to ctp progress.
# --decide-only: print only the power-off decision (census-other-done), copy nothing.
set -uo pipefail
export AWS_PAGER=""
SELF=batch5L; PARTS="L"
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}
I=/home/ec2-user/batch5-input
DEST=$B/batch5L/final; [ $DRY = 1 ] && DEST=$B/batch5L/dryrun
S_=/b5L/final-stage; FLOG=/data/logs/finalize-batch5L.log; TM=$(mktemp -d /tmp/finalize-batch5L.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize: $*"; }
fail() { say "FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > "$TM/FINALIZE_FAILED"
         aws s3 cp "$TM/FINALIZE_FAILED" "$DEST/FINALIZE_FAILED" --only-show-errors; aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors; exit 1; }
part_env() { local c="CTP_$1" o="OUT_$1"; CTP=${!c:-/b5L/ctp}; OUT=${!o:-/b5L/census-2026-10-batch5L}
             CFG=/home/ec2-user/census-batch5L.cfg; LOG=/data/logs/batch5L.log; }
unit() { echo census-batch5L.service; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would power off' || echo 'no power-off')"; exit 0; fi
# Hold: while /run/census-batch5L-hold exists, a real finalize does nothing (a census stopped on
# purpose is not finalized as a partial result).
if [ $DRY = 0 ] && [ -e /run/census-batch5L-hold ]; then
  say "hold: /run/census-batch5L-hold exists ($(cat /run/census-batch5L-hold)); no finalize"; exit 0; fi
say "start dry=$DRY parts=$PARTS DEST=$DEST"
if [ $DRY = 0 ]; then
  waited=0
  while :; do
    act=""; for p in $PARTS; do case $(systemctl is-active $(unit $p)) in active|activating|deactivating) act="$act $p" ;; esac; done
    [ -z "$act" ] && break
    [ $waited = 0 ] && say "parts still running:$act; waiting (this unit stays active until they end)"
    waited=1; sleep 60
  done
fi
svc=""; for p in $PARTS; do svc="$svc | $(unit $p): $(systemctl show $(unit $p) -p Result -p ExecMainStatus -p ExecMainExitTimestamp 2>/dev/null | tr '\n' ' ')"; done
say "parts:$svc"
[ -d "$S_" ] && mv "$S_" "$S_.old.$(date +%s)"
mkdir -p "$S_/projects" "$S_/ctp" "$S_/logs" || fail "staging dir"
n=0
for p in $PARTS; do part_env $p
  for d in "$OUT"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d"); [ "$name" = .pin-staging ] && continue
    files=$(find "$d" -maxdepth 1 -type f \( -name '*.parquet' -o -name '*.validated' \))
    [ -n "$files" ] || continue
    mkdir -p "$S_/projects/$name"; for f in $files; do cp -p "$f" "$S_/projects/$name/" || fail "copy $f"; done; n=$((n+1))
  done
  mkdir -p "$S_/ctp/$p"
  for f in ledger.jsonl ctp.duckdb metrics.tsv resources.tsv runs.log; do [ -f "$CTP/$f" ] && { cp -p "$CTP/$f" "$S_/ctp/$p/" || fail "copy $p/$f"; }; done
  if [ -d "$CTP/state" ]; then  # absent when the part was stopped before its first project
  ( cd "$CTP" && find state -maxdepth 1 -mindepth 1 -type d | while read -r s; do
      mkdir -p "$S_/ctp/$p/$s/logs"; find "$s" -maxdepth 1 -type f -name '*.json' -exec cp -p {} "$S_/ctp/$p/$s/" \;
      [ -d "$s/logs" ] && find "$s/logs" -maxdepth 1 -type f -exec cp -p {} "$S_/ctp/$p/$s/logs/" \; ; done ) || fail "copy state $p"
  fi
  [ -f "$LOG" ] && cp -p "$LOG" "$S_/logs/"
  cp -p "$I/manifest.batch5L.tsv" "$I/manifest.batch1rest.tsv" "$I/manifest.batch5.tsv" "$S_/logs/" 2>/dev/null
done
say "projects with a Parquet or stamp: $n"
cp -p /data/logs/build.log "$S_/logs/" 2>/dev/null
journalctl -u census-batch4-guard.service --no-pager -o short-iso > "$S_/logs/guard.journal" 2>/dev/null
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
{ echo "cregit census batch5L finished and copied: $(date -u +%FT%TZ)"
  echo "instance: $(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)  dry_run=$DRY  parts: $PARTS"
  echo "parts:$svc"
  echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")"
  for p in $PARTS; do part_env $p; echo "--- part $p: ctp progress"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest ${MANIFEST:-$I/manifest.batch5L.tsv} --last 3 2>&1 | head -5); done
  echo "--- SHA256SUMS"; cat "$S_/SHA256SUMS"; } > "$TM/DONE"
aws s3 cp "$TM/DONE" "$DEST/DONE" --only-show-errors && aws s3 ls "$DEST/DONE" >/dev/null || fail "DONE upload"
aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors
say "DONE written to $DEST/DONE"
if [ $DRY = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "dry run: no power-off (a real run would: $why -> $([ $rc = 0 ] && echo 'power off' || echo 'no power-off'))"; exit 0; fi
ran=0
for p in $PARTS; do
  st=$(systemctl show $(unit $p) -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show $(unit $p) -p ExecMainExitTimestampMonotonic --value)
  r=$(( (${ex:-0} - ${st:-0}) / 1000000 )); [ "$r" -gt "$ran" ] && ran=$r
done
if [ "$ran" -lt 3600 ]; then say "the longest part ran only ${ran}s (< 1 h): an early failure, so no power-off; look at /data/logs/batch5L.log"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no power-off"; exit 0; fi
if ! why=$(/usr/local/bin/census-other-done $SELF 2>&1); then say "$why: no power-off; the last census to finalize powers off"; exit 0; fi
say "$why"
say "powering off (the instance stops; it is not terminated)"
sync; shutdown -h now
EOF_census-batch5L-finalize
chmod 755 /usr/local/bin/census-batch5L-finalize.new; mv -f /usr/local/bin/census-batch5L-finalize.new /usr/local/bin/census-batch5L-finalize
cat > /etc/systemd/system/census-batch5L.service.new <<'EOF_census-batch5L.service'
[Unit]
Description=cregit census batch5L: the L projects of batch1rest and batch5 (ctp census, loop XFS /b5L)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data /b5L
OnSuccess=census-batch5L-finalize.service
OnFailure=census-batch5L-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/b5L/ctp
ExecStart=/usr/local/bin/census-batch5L-run
StandardOutput=append:/data/logs/batch5L.log
StandardError=append:/data/logs/batch5L.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-batch5L.service
chmod 644 /etc/systemd/system/census-batch5L.service.new; mv -f /etc/systemd/system/census-batch5L.service.new /etc/systemd/system/census-batch5L.service
cat > /etc/systemd/system/census-batch5L-finalize.service.new <<'EOF_census-batch5L-finalize.service'
[Unit]
Description=cregit census batch5L: copy results to S3, write DONE, power off if every census finalized
RequiresMountsFor=/data

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-batch5L-finalize
TimeoutStartSec=infinity
EOF_census-batch5L-finalize.service
chmod 644 /etc/systemd/system/census-batch5L-finalize.service.new; mv -f /etc/systemd/system/census-batch5L-finalize.service.new /etc/systemd/system/census-batch5L-finalize.service
cat > /etc/systemd/system/census-batch5L-live.service.new <<'EOF_census-batch5L-live.service'
[Unit]
Description=cregit census batch5L: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-batch5L-live
TimeoutStartSec=300
EOF_census-batch5L-live.service
chmod 644 /etc/systemd/system/census-batch5L-live.service.new; mv -f /etc/systemd/system/census-batch5L-live.service.new /etc/systemd/system/census-batch5L-live.service
cat > /etc/systemd/system/census-batch5L-live.timer.new <<'EOF_census-batch5L-live.timer'
[Unit]
Description=cregit census batch5L: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF_census-batch5L-live.timer
chmod 644 /etc/systemd/system/census-batch5L-live.timer.new; mv -f /etc/systemd/system/census-batch5L-live.timer.new /etc/systemd/system/census-batch5L-live.timer
systemctl daemon-reload
after=$(systemctl show census-batch2.service census-batch3L.service census-batch4p1.service census-batch4p2.service census-batch4p3.service -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')
[ "$before" = "$after" ] && echo "running censuses unchanged by the reload: $after" || echo "CHANGED: before $before / after $after"
systemctl show census-batch5L.service -p OOMPolicy -p RequiresMountsFor -p OnSuccess -p OnFailure | tr '\n' ' '; echo
echo "== power-off rule tests $(date -u +%FT%TZ) (census-other-done only; nothing powers off)"
r() { local out; out=$("$@" 2>&1); echo "rc=$? $out"; }
F=$S3/batch4/dryrun/DONE
for n in batch2 batch3L batch4 batch5L; do echo "T1 $n, real state: $(r $B/census-other-done $n)"; done
echo "T2 batch4, batch2+3L faked done: $(DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= r $B/census-other-done batch4)"
echo "T3 batch4, batch2+3L+5L faked done: $(DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch5L=$F UNITS_batch5L= r $B/census-other-done batch4)"
echo "T4 batch5L, batch2+3L+4 faked done: $(DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= r $B/census-other-done batch5L)"
echo "T5 batch2, 3L+4 faked done (5L missing): $(DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= r $B/census-other-done batch2)"
echo "T6 bad argument: $(r $B/census-other-done batch9)"
for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize; do echo "T7 $f --decide-only: $($B/$f --decide-only 2>&1 | tail -1)"; done
echo "T8 guard (real run): $($B/census-batch4-guard)"
echo "== dry-run finalize on the check output"
CTP_L=/b5L/ctp-check OUT_L=/b5L/libexpat-check/out MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv $B/census-batch5L-finalize --dry-run 2>&1 | grep -E 'staged|check ok|DONE|dry run|FAILED' | cut -c1-220
echo "== start $(date -u +%FT%TZ)"
systemctl start census-batch5L-live.timer census-batch5L.service
sleep 45
systemctl show census-batch5L.service -p ActiveState -p MainPID -p ActiveEnterTimestamp -p OOMPolicy | tr '\n' ' '; echo
tail -n 4 /data/logs/batch5L.log | cut -c1-220
after2=$(systemctl show census-batch2.service census-batch3L.service census-batch4p1.service census-batch4p2.service census-batch4p3.service -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')
[ "$before" = "$after2" ] && echo "running censuses unchanged after the start" || echo "CHANGED after start: $after2"
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); /data free $(df -BG --output=avail /data | tail -1 | tr -d ' '); load $(cut -d' ' -f1-3 /proc/loadavg)"
