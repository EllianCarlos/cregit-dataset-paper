set -euo pipefail
cat > /usr/local/bin/census-other-done.new <<'EOF_census-other-done'
#!/usr/bin/env bash
# census-other-done SELF: exit 0 when EVERY OTHER census on the batch 2 instance has finalized,
# i.e. its final/DONE is in S3 (a finalize writes DONE only after its upload check passed) and
# its census units are not active. The censuses on this instance (2026-10-09 13:xx, batch 4 added):
#   batch2  : s3://B/batch2/final/DONE,  units census-batch2.service
#   batch3L : s3://B/batch3L/final/DONE, units census-batch3L-wait.service census-batch3L.service
#   batch4  : s3://B/batch4/final/DONE,  units census-batch4p1.service census-batch4p2.service census-batch4p3.service
# Each finalize writes its own DONE before it asks, so the last census to finish sees all the
# other DONEs and powers off; the earlier ones do not. Same interface as the 2-census version
# (SELF = batch2|batch3L, plus batch4), so the batch 2 and batch 3L finalizes are unchanged.
# Test overrides, per census N: DONE_URL_N (an S3 object) and UNITS_N (space-separated; "" = none).
set -uo pipefail
B=s3://${RUNNER_BUCKET}
ALL="batch2 batch3L batch4"
declare -A U=(
  [batch2]="census-batch2.service"
  [batch3L]="census-batch3L-wait.service census-batch3L.service"
  [batch4]="census-batch4p1.service census-batch4p2.service census-batch4p3.service"
)
self=${1:-}
case " $ALL " in *" $self "*) [ -n "$self" ] || { echo "usage: census-other-done batch2|batch3L|batch4" >&2; exit 2; } ;;
  *) echo "usage: census-other-done batch2|batch3L|batch4" >&2; exit 2 ;; esac
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
chmod 755 /usr/local/bin/census-other-done.new
mv -f /usr/local/bin/census-other-done.new /usr/local/bin/census-other-done
cat > /usr/local/bin/census-batch4-run.new <<'EOF_census-batch4-run'
#!/usr/bin/env bash
# census-batch4-run K (census-batch4pK.service): census batch 4 part pK on the batch 2 instance,
# on its own loop-mounted XFS /b4pK (own rename lock). Own ctp clone /b4pK/ctp, config and output
# /b4pK/census-2026-10-batch4; the same cregit build /data/cregit-ec2 (95cdc88) as batch 2/3L.
# Stop after the running projects: touch /b4pK/ctp/STOP. Resume: start the unit again.
set -euo pipefail
K=${1:?part number}
I=/home/ec2-user/batch4-input
export CTP_CONFIG=/home/ec2-user/census-batch4p$K.cfg
cd /b4p$K/ctp
echo "=== $(date -u +%FT%TZ) census-batch4p$K start (cregit $(git -C /data/cregit-ec2 rev-parse --short HEAD), ctp $(git rev-parse --short HEAD), $(grep -c -v -e '^#' -e '^[[:space:]]*$' "$I/manifest.batch4p$K.tsv") projects, 4 workers, out /b4p$K/census-2026-10-batch4)"
exec .venv/bin/python ctp.py census --manifest "$I/manifest.batch4p$K.tsv" \
    --project-meta "$I/project_meta.batch4p$K.json" \
    --workers 4 --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300
EOF_census-batch4-run
chmod 755 /usr/local/bin/census-batch4-run.new
mv -f /usr/local/bin/census-batch4-run.new /usr/local/bin/census-batch4-run
cat > /usr/local/bin/census-batch4-live.new <<'EOF_census-batch4-live'
#!/usr/bin/env bash
# Every 10 min (census-batch4-live.timer): status of census batch 4 (parts p1..p3) to
# s3://BUCKET/batch4/live/: progress.txt (first line "as of <ts>  census-batch4: <state> ...",
# read by the local watchdog: it must contain ": active" while any part runs), steps.txt (the
# cregit step of every running project of the 3 parts, L projects first), batch4pK.log.tail,
# ledger.pK.jsonl, system.txt (load, PSI, meminfo, df of /data and the loop filesystems).
set -uo pipefail
export AWS_PAGER=""
D=s3://${RUNNER_BUCKET}/batch4/live
I=/home/ec2-user/batch4-input
T=$(mktemp -d); trap 'rm -r "$T"' EXIT
st=""; any=inactive
for k in 1 2 3; do s=$(systemctl is-active census-batch4p$k.service); st="$st p$k=$s"
  case $s in active|activating|deactivating) any=active ;; esac; done
for k in 1 2 3; do
  /usr/local/bin/census-steps /b4p$k/ctp "$I/manifest.batch4p$k.tsv" --highlight 'lvbs-linux|llvm-mos|ceph__ceph' > "$T/steps.p$k.txt" 2>&1
done
{ echo "as of $(date -u +%FT%TZ)  census-batch4: $any ($st )  finalize=$(systemctl is-active census-batch4-finalize.service)"
  echo "census-batch2=$(systemctl is-active census-batch2.service)  census-batch3L=$(systemctl is-active census-batch3L.service)"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   /data free: $(df -BG --output=avail /data | tail -1 | tr -d ' ')"
  echo "guard: $(cat /run/census-batch4-guard.status 2>/dev/null || echo none)"
  [ -e /run/census-batch4-guard.tripped ] && echo "GUARD TRIPPED: $(cat /run/census-batch4-guard.tripped)"
  for k in 1 2 3; do
    echo; echo "=== part p$k: census-batch4p$k $(systemctl is-active census-batch4p$k.service) ($(systemctl show census-batch4p$k.service -p Result --value)), /b4p$k free $(df -BG --output=avail /b4p$k | tail -1 | tr -d ' ')$([ -e /b4p$k/ctp/STOP ] && echo '  STOP present')"
    (cd /b4p$k/ctp && CTP_CONFIG=/home/ec2-user/census-batch4p$k.cfg .venv/bin/python ctp.py progress --manifest "$I/manifest.batch4p$k.tsv" --last 5 2>&1)
    echo; cat "$T/steps.p$k.txt"
  done
} > "$T/progress.txt"
for k in 1 2 3; do echo "### part p$k"; cat "$T/steps.p$k.txt"; echo; done > "$T/steps.txt"
rm -f "$T"/steps.p*.txt
for k in 1 2 3; do
  tail -n 300 /data/logs/batch4p$k.log > "$T/batch4p$k.log.tail" 2>/dev/null
  [ -f /b4p$k/ctp/ledger.jsonl ] && cp /b4p$k/ctp/ledger.jsonl "$T/ledger.p$k.jsonl"
done
{ date -u +%FT%TZ; uptime; cat /proc/pressure/io /proc/pressure/cpu 2>/dev/null; cat /proc/meminfo; df -h /data /b4p1 /b4p2 /b4p3 /; du -h /data/loop/*.img; } > "$T/system.txt" 2>&1
aws s3 cp "$T/" "$D/" --recursive --only-show-errors
EOF_census-batch4-live
chmod 755 /usr/local/bin/census-batch4-live.new
mv -f /usr/local/bin/census-batch4-live.new /usr/local/bin/census-batch4-live
cat > /usr/local/bin/census-batch4-finalize.new <<'EOF_census-batch4-finalize'
#!/usr/bin/env bash
# census-batch4-finalize (census-batch4-finalize.service; OnSuccess=/OnFailure= of every
# census-batch4pK). Waits until no batch 4 part is active (a part that ends early does not finalize
# alone), then copies the results of ALL parts to s3://BUCKET/batch4/final/, checks every object
# (key and size) and SHA256SUMS against the local files, writes DONE. Then it powers the instance
# off (stop, not terminate) only if EVERY other census on this instance (batch 2, batch 3L) has
# finalized: /usr/local/bin/census-other-done batch4 decides; the last census to finalize powers off.
# No power-off if the check fails, with --dry-run, if the longest part ran < 1 h, or if
# /home/ec2-user/NO_SHUTDOWN exists.
# --dry-run: copy to batch4/dryrun/ without waiting for the parts, never power off.
#   CTP_pK / OUT_pK in the environment override a part's ctp clone and output dir; MANIFEST the
#   manifest given to ctp progress.
# --decide-only: print only the power-off decision (census-other-done), copy nothing.
set -uo pipefail
export AWS_PAGER=""
SELF=batch4; PARTS="p1 p2 p3"
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}
I=/home/ec2-user/batch4-input
DEST=$B/batch4/final; [ $DRY = 1 ] && DEST=$B/batch4/dryrun
S_=/data/final-stage-batch4; FLOG=/data/logs/finalize-batch4.log; TM=$(mktemp -d /tmp/finalize-batch4.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize: $*"; }
fail() { say "FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > "$TM/FINALIZE_FAILED"
         aws s3 cp "$TM/FINALIZE_FAILED" "$DEST/FINALIZE_FAILED" --only-show-errors; aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors; exit 1; }
part_env() { local k=${1#p} c="CTP_$1" o="OUT_$1"; CTP=${!c:-/b4p$k/ctp}; OUT=${!o:-/b4p$k/census-2026-10-batch4}
             CFG=/home/ec2-user/census-batch4$1.cfg; LOG=/data/logs/batch4$1.log; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would power off' || echo 'no power-off')"; exit 0; fi
say "start dry=$DRY parts=$PARTS DEST=$DEST"
if [ $DRY = 0 ]; then
  waited=0
  while :; do
    act=""; for p in $PARTS; do case $(systemctl is-active census-batch4$p.service) in active|activating|deactivating) act="$act $p" ;; esac; done
    [ -z "$act" ] && break
    [ $waited = 0 ] && say "parts still running:$act; waiting (this unit stays active until they end)"
    waited=1; sleep 60
  done
fi
svc=""; for p in $PARTS; do svc="$svc | census-batch4$p: $(systemctl show census-batch4$p.service -p Result -p ExecMainStatus -p ExecMainExitTimestamp 2>/dev/null | tr '\n' ' ')"; done
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
  cp -p "$I/manifest.batch4$p.tsv" "$S_/logs/" 2>/dev/null
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
{ echo "cregit census batch 4 finished and copied: $(date -u +%FT%TZ)"
  echo "instance: $(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)  dry_run=$DRY  parts: $PARTS"
  echo "parts:$svc"
  echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")"
  for p in $PARTS; do part_env $p; echo "--- part $p: ctp progress"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest ${MANIFEST:-$I/manifest.batch4$p.tsv} --last 3 2>&1 | head -5); done
  echo "--- SHA256SUMS"; cat "$S_/SHA256SUMS"; } > "$TM/DONE"
aws s3 cp "$TM/DONE" "$DEST/DONE" --only-show-errors && aws s3 ls "$DEST/DONE" >/dev/null || fail "DONE upload"
aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors
say "DONE written to $DEST/DONE"
if [ $DRY = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "dry run: no power-off (a real run would: $why -> $([ $rc = 0 ] && echo 'power off' || echo 'no power-off'))"; exit 0; fi
ran=0
for p in $PARTS; do
  st=$(systemctl show census-batch4$p.service -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show census-batch4$p.service -p ExecMainExitTimestampMonotonic --value)
  r=$(( (${ex:-0} - ${st:-0}) / 1000000 )); [ "$r" -gt "$ran" ] && ran=$r
done
if [ "$ran" -lt 3600 ]; then say "the longest part ran only ${ran}s (< 1 h): an early failure, so no power-off; look at /data/logs/batch4p*.log"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no power-off"; exit 0; fi
if ! why=$(/usr/local/bin/census-other-done $SELF 2>&1); then say "$why: no power-off; the last census to finalize powers off"; exit 0; fi
say "$why"
say "powering off (the instance stops; it is not terminated)"
sync; shutdown -h now
EOF_census-batch4-finalize
chmod 755 /usr/local/bin/census-batch4-finalize.new
mv -f /usr/local/bin/census-batch4-finalize.new /usr/local/bin/census-batch4-finalize
cat > /usr/local/bin/census-batch4-guard.new <<'EOF_census-batch4-guard'
#!/usr/bin/env bash
# census-batch4-guard (root, every 10 min). The loop images /data/loop/b4pK.img are sparse files on
# the RAID0 /data that batch 2 and batch 3L also use. (1) fstrim each /b4pK, so blocks freed inside
# (cleaned-up clones) are punched out of the image and returned to /data (measured 13:12: the
# discard mount option alone did not shrink the image, fstrim did). (2) If /data has less than
# GUARD_GB (default 800) GiB free, touch STOP in every batch 4 ctp clone: running batch 4 projects
# finish, no new one starts, so batch 4 cannot fill /data under batch 2 / batch 3L.
set -uo pipefail
export AWS_PAGER=""
G=${GUARD_GB:-800}
for k in 1 2 3; do mountpoint -q /b4p$k && fstrim -q /b4p$k; done
avail=$(df -BG --output=avail /data | tail -1 | tr -dc 0-9)
img=$(for k in 1 2 3; do echo -n "b4p$k $(du -BG /data/loop/b4p$k.img | cut -f1) "; done)
msg="$(date -u +%FT%TZ) /data free ${avail}G (guard ${G}G); image use: $img"
if [ "$avail" -lt "$G" ]; then
  for k in 1 2 3; do [ -d /b4p$k/ctp ] && { touch /b4p$k/ctp/STOP; chown ec2-user: /b4p$k/ctp/STOP; }; done
  msg="$msg; BELOW GUARD: STOP written in /b4p1..3/ctp"
  echo "$msg" > /run/census-batch4-guard.tripped
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch4/live/GUARD --only-show-errors
fi
echo "$msg" > /run/census-batch4-guard.status
echo "$msg"
EOF_census-batch4-guard
chmod 755 /usr/local/bin/census-batch4-guard.new
mv -f /usr/local/bin/census-batch4-guard.new /usr/local/bin/census-batch4-guard
cat > /etc/systemd/system/census-batch4p1.service.new <<'EOF_census-batch4p1.service'
[Unit]
Description=cregit census batch 4 part p1 (ctp census, 4 workers, loop XFS /b4p1)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data /b4p1
OnSuccess=census-batch4-finalize.service
OnFailure=census-batch4-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/b4p1/ctp
ExecStart=/usr/local/bin/census-batch4-run 1
StandardOutput=append:/data/logs/batch4p1.log
StandardError=append:/data/logs/batch4p1.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-batch4p1.service
chmod 644 /etc/systemd/system/census-batch4p1.service.new
mv -f /etc/systemd/system/census-batch4p1.service.new /etc/systemd/system/census-batch4p1.service
cat > /etc/systemd/system/census-batch4p2.service.new <<'EOF_census-batch4p2.service'
[Unit]
Description=cregit census batch 4 part p2 (ctp census, 4 workers, loop XFS /b4p2)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data /b4p2
OnSuccess=census-batch4-finalize.service
OnFailure=census-batch4-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/b4p2/ctp
ExecStart=/usr/local/bin/census-batch4-run 2
StandardOutput=append:/data/logs/batch4p2.log
StandardError=append:/data/logs/batch4p2.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-batch4p2.service
chmod 644 /etc/systemd/system/census-batch4p2.service.new
mv -f /etc/systemd/system/census-batch4p2.service.new /etc/systemd/system/census-batch4p2.service
cat > /etc/systemd/system/census-batch4p3.service.new <<'EOF_census-batch4p3.service'
[Unit]
Description=cregit census batch 4 part p3 (ctp census, 4 workers, loop XFS /b4p3)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data /b4p3
OnSuccess=census-batch4-finalize.service
OnFailure=census-batch4-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/b4p3/ctp
ExecStart=/usr/local/bin/census-batch4-run 3
StandardOutput=append:/data/logs/batch4p3.log
StandardError=append:/data/logs/batch4p3.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-batch4p3.service
chmod 644 /etc/systemd/system/census-batch4p3.service.new
mv -f /etc/systemd/system/census-batch4p3.service.new /etc/systemd/system/census-batch4p3.service
cat > /etc/systemd/system/census-batch4-finalize.service.new <<'EOF_census-batch4-finalize.service'
[Unit]
Description=cregit census batch 4: wait for all parts, copy results to S3, write DONE, power off if every census finalized
RequiresMountsFor=/data

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-batch4-finalize
TimeoutStartSec=infinity
EOF_census-batch4-finalize.service
chmod 644 /etc/systemd/system/census-batch4-finalize.service.new
mv -f /etc/systemd/system/census-batch4-finalize.service.new /etc/systemd/system/census-batch4-finalize.service
cat > /etc/systemd/system/census-batch4-live.service.new <<'EOF_census-batch4-live.service'
[Unit]
Description=cregit census batch 4: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-batch4-live
TimeoutStartSec=300
EOF_census-batch4-live.service
chmod 644 /etc/systemd/system/census-batch4-live.service.new
mv -f /etc/systemd/system/census-batch4-live.service.new /etc/systemd/system/census-batch4-live.service
cat > /etc/systemd/system/census-batch4-live.timer.new <<'EOF_census-batch4-live.timer'
[Unit]
Description=cregit census batch 4: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF_census-batch4-live.timer
chmod 644 /etc/systemd/system/census-batch4-live.timer.new
mv -f /etc/systemd/system/census-batch4-live.timer.new /etc/systemd/system/census-batch4-live.timer
cat > /etc/systemd/system/census-batch4-guard.service.new <<'EOF_census-batch4-guard.service'
[Unit]
Description=cregit census batch 4: fstrim the loop filesystems, stop batch 4 if /data runs low

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-batch4-guard
TimeoutStartSec=900
EOF_census-batch4-guard.service
chmod 644 /etc/systemd/system/census-batch4-guard.service.new
mv -f /etc/systemd/system/census-batch4-guard.service.new /etc/systemd/system/census-batch4-guard.service
cat > /etc/systemd/system/census-batch4-guard.timer.new <<'EOF_census-batch4-guard.timer'
[Unit]
Description=cregit census batch 4: guard every 10 min

[Timer]
OnActiveSec=2min
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF_census-batch4-guard.timer
chmod 644 /etc/systemd/system/census-batch4-guard.timer.new
mv -f /etc/systemd/system/census-batch4-guard.timer.new /etc/systemd/system/census-batch4-guard.timer
