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
cat > $B/census-other-done.new <<'EOF_census-other-done'
#!/usr/bin/env bash
# census-other-done SELF: exit 0 when EVERY OTHER census on the batch 2 instance has finalized,
# i.e. its final/DONE is in S3 (a finalize writes DONE only after its upload check passed) and
# its census units are not active. The censuses on this instance (2026-10-09 13:xx, batch 4 added):
#   batch2  : s3://B/batch2/final/DONE,  units census-batch2.service
#   batch3L : s3://B/batch3L/final/DONE, units census-batch3L-wait.service census-batch3L.service
#   batch4  : s3://B/batch4/final/DONE,  units census-batch4p1.service census-batch4p2.service census-batch4p3.service
#   batch5L : s3://B/batch5L/final/DONE, units census-batch5L.service (2026-10-09 ~16:xx, batch 5 added)
#   batch6L : s3://B/batch6L/final/DONE, units census-batch6L-wait.service census-batch6L.service
#             (2026-10-09 ~20:00 UTC, batch 6 added; the waiter counts as "not finalized" while it waits)
# Each finalize writes its own DONE before it asks, so the last census to finish sees all the
# other DONEs and powers off; the earlier ones do not. Same interface as the 2-census version
# (SELF = batch2|batch3L, plus batch4, batch5L and batch6L), so the older finalizes are unchanged.
# Test overrides, per census N: DONE_URL_N (an S3 object) and UNITS_N (space-separated; "" = none).
set -uo pipefail
B=s3://${RUNNER_BUCKET}
ALL="batch2 batch3L batch4 batch5L batch6L"
declare -A U=(
  [batch2]="census-batch2.service"
  [batch3L]="census-batch3L-wait.service census-batch3L.service"
  [batch4]="census-batch4p1.service census-batch4p2.service census-batch4p3.service"
  [batch5L]="census-batch5L.service"
  [batch6L]="census-batch6L-wait.service census-batch6L.service"
)
self=${1:-}
case " $ALL " in *" $self "*) [ -n "$self" ] || { echo "usage: census-other-done batch2|batch3L|batch4|batch5L|batch6L" >&2; exit 2; } ;;
  *) echo "usage: census-other-done batch2|batch3L|batch4|batch5L|batch6L" >&2; exit 2 ;; esac
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
chmod 755 $B/census-other-done.new; mv -f $B/census-other-done.new $B/census-other-done
cat > $B/census-batch4-guard.new <<'EOF_census-batch4-guard'
#!/usr/bin/env bash
# census-batch4-guard (root, every 10 min). The loop images /data/loop/b4pK.img are sparse files on
# the RAID0 /data that batch 2 and batch 3L also use. (1) fstrim each /b4pK, so blocks freed inside
# (cleaned-up clones) are punched out of the image and returned to /data (measured 13:12: the
# discard mount option alone did not shrink the image, fstrim did). (2) If /data has less than
# GUARD_GB (default 800) GiB free, touch STOP in every batch 4 ctp clone: running batch 4 projects
# finish, no new one starts, so batch 4 cannot fill /data under batch 2 / batch 3L.
# 2026-10-09 (batch 5): the same for census batch5L on /data/loop/b5L.img, /b5L: fstrim /b5L, and
# below the guard also touch /b5L/ctp/STOP.
# 2026-10-09 ~20:00 UTC (batch 6): the same for census batch6L on /data/loop/b6L.img, /b6L (the STOP
# there also holds census-batch6L-wait).
set -uo pipefail
export AWS_PAGER=""
G=${GUARD_GB:-800}
for k in 1 2 3; do mountpoint -q /b4p$k && fstrim /b4p$k >/dev/null; done
mountpoint -q /b5L && fstrim /b5L >/dev/null
mountpoint -q /b6L && fstrim /b6L >/dev/null
avail=$(df -BG --output=avail /data | tail -1 | tr -dc 0-9)
img=$(for k in 1 2 3; do echo -n "b4p$k $(du -BG /data/loop/b4p$k.img | cut -f1) "; done; [ -e /data/loop/b5L.img ] && echo -n "b5L $(du -BG /data/loop/b5L.img | cut -f1) "; [ -e /data/loop/b6L.img ] && echo -n "b6L $(du -BG /data/loop/b6L.img | cut -f1)")
msg="$(date -u +%FT%TZ) /data free ${avail}G (guard ${G}G); image use: $img"
if [ "$avail" -lt "$G" ]; then
  for k in 1 2 3; do [ -d /b4p$k/ctp ] && { touch /b4p$k/ctp/STOP; chown ec2-user: /b4p$k/ctp/STOP; }; done
  [ -d /b5L/ctp ] && { touch /b5L/ctp/STOP; chown ec2-user: /b5L/ctp/STOP; }
  [ -d /b6L/ctp ] && { touch /b6L/ctp/STOP; chown ec2-user: /b6L/ctp/STOP; }
  msg="$msg; BELOW GUARD: STOP written in /b4p1..3/ctp, /b5L/ctp and /b6L/ctp"
  echo "$msg" > /run/census-batch4-guard.tripped
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch4/live/GUARD --only-show-errors
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch5L/live/GUARD --only-show-errors
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch6L/live/GUARD --only-show-errors
fi
echo "$msg" > /run/census-batch4-guard.status
echo "$msg"
EOF_census-batch4-guard
chmod 755 $B/census-batch4-guard.new; mv -f $B/census-batch4-guard.new $B/census-batch4-guard
cat > $B/census-backup.new <<'EOF_census-backup'
#!/usr/bin/env bash
# census-backup (2026-10-09, user request: regular S3 backup of the Parquets). Every 30 min from
# census-backup.timer. For each finished project (a *.validated file next to its Parquet) that has no
# s3://BUCKET/<run>/done/<project>/OK yet: copy the Parquet, .validated and persons files, compare the
# S3 sizes with the local sizes, then write OK (with the Parquet sha256). Each pass also copies each
# run's ledger.jsonl, metrics.tsv and resources.tsv to <run>/backup-ledger/. Read-only on the census.
set -uo pipefail
exec 9>/run/census-backup.lock; flock -n 9 || exit 0
B=s3://${RUNNER_BUCKET}
log=/data/logs/census-backup.log
ts() { date -u +%FT%TZ; }
# run prefix | output dir | ctp dir
RUNS="batch2|/data/census-2026-10-batch2|/home/ec2-user/ctp
batch3L|/data/census-2026-10-batch3L|/home/ec2-user/ctp-b3L
batch4/p1|/b4p1/census-2026-10-batch4|/b4p1/ctp
batch4/p2|/b4p2/census-2026-10-batch4|/b4p2/ctp
batch4/p3|/b4p3/census-2026-10-batch4|/b4p3/ctp
batch5L|/b5L/census-2026-10-batch5L|/b5L/ctp
batch6L|/b6L/census-2026-10-batch6L|/b6L/ctp"
done_list=$(mktemp); trap 'rm -f "$done_list"' EXIT
new=0; fail=0
while IFS='|' read -r run out ctp; do
  [ -d "$out" ] || continue
  aws s3 ls "$B/$run/done/" --recursive 2>/dev/null | awk '/\/OK$/{print $4}' > "$done_list"
  for v in "$out"/*/*.validated; do
    [ -e "$v" ] || continue
    d=$(dirname "$v"); p=$(basename "$d")
    case "$p" in .*) continue ;; esac
    grep -qx "$run/done/$p/OK" "$done_list" && continue
    pq="$d/$p-dataset.parquet"; [ -s "$pq" ] || { echo "$(ts) $run $p: no parquet yet" >> "$log"; continue; }
    ok=1
    for f in "$pq" "$v" "$d/$p-persons.db" "$d/$p-persons.xls"; do
      [ -e "$f" ] || continue
      key="$run/done/$p/$(basename "$f")"
      nice -n 10 aws s3 cp "$f" "$B/$key" --only-show-errors || { ok=0; break; }
      rs=$(aws s3api head-object --bucket "${B#s3://}" --key "$key" --query ContentLength --output text 2>/dev/null)
      [ "$rs" = "$(stat -c %s "$f")" ] || { ok=0; break; }
    done
    if [ $ok = 1 ]; then
      printf '%s  %s\nbacked_up=%s\n' "$(sha256sum "$pq" | cut -d' ' -f1)" "$(basename "$pq")" "$(ts)" \
        | aws s3 cp - "$B/$run/done/$p/OK" --only-show-errors && new=$((new + 1))
    else
      fail=$((fail + 1)); echo "$(ts) $run $p: upload or size check FAILED" >> "$log"
    fi
  done
  for f in ledger.jsonl metrics.tsv resources.tsv; do
    [ -e "$ctp/$f" ] && aws s3 cp "$ctp/$f" "$B/$run/backup-ledger/$f" --only-show-errors
  done
done <<<"$RUNS"
echo "$(ts) pass done: new=$new failed=$fail" >> "$log"
EOF_census-backup
chmod 755 $B/census-backup.new; mv -f $B/census-backup.new $B/census-backup
cat > $B/census-batch6L-run.new <<'EOF_census-batch6L-run'
#!/usr/bin/env bash
# census-batch6L-run (census-batch6L.service): the L projects of batch6 (3) on the
# batch 2 instance, on their own loop XFS /b6L (own rename lock) with their own ctp clone /b6L/ctp,
# cregit copy /b6L/cregit-ec2 (95cdc88; path fixed before the start), config and output
# /b6L/census-2026-10-batch6L. One worker per project. Stop after the running projects:
# touch /b6L/ctp/STOP (census-batch4-guard does it below 800 GiB free on /data).
set -euo pipefail
I=/home/ec2-user/batch6-input; M=$I/manifest.batch6L.tsv
export CTP_CONFIG=/home/ec2-user/census-batch6L.cfg
cd /b6L/ctp
n=$(grep -c -v -e '^#' -e '^[[:space:]]*$' "$M")
echo "=== $(date -u +%FT%TZ) census-batch6L start (cregit $(git -C /b6L/cregit-ec2 rev-parse --short HEAD) at /b6L/cregit-ec2, ctp $(git rev-parse --short HEAD), $n projects, $n workers, out /b6L/census-2026-10-batch6L)"
exec .venv/bin/python ctp.py census --manifest "$M" --project-meta "$I/project_meta.batch6L.json" \
    --workers "$n" --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300
EOF_census-batch6L-run
chmod 755 $B/census-batch6L-run.new; mv -f $B/census-batch6L-run.new $B/census-batch6L-run
cat > $B/census-batch6L-live.new <<'EOF_census-batch6L-live'
#!/usr/bin/env bash
# Every 10 min (census-batch6L-live.timer): status of census batch6L to s3://BUCKET/batch6L/live/:
# progress.txt (first line "as of <ts>  census-batch6L: <state> ...", read by the local watchdog: it
# must contain ": active" while the census runs), steps.txt, batch6L.log.tail, ledger.jsonl, system.txt.
set -uo pipefail
export AWS_PAGER=""
D=s3://${RUNNER_BUCKET}/batch6L/live
I=/home/ec2-user/batch6-input
T=$(mktemp -d); trap 'rm -r "$T"' EXIT
s=$(systemctl is-active census-batch6L.service); w=$(systemctl is-active census-batch6L-wait.service)
# while the waiter holds the start, the state word is "waiting" (the local watchdog accepts it)
case $s in active|activating) ;; *) case $w in active|activating) s=waiting ;; esac ;; esac
/usr/local/bin/census-steps /b6L/ctp "$I/manifest.batch6L.tsv" --highlight '' > "$T/steps.txt" 2>&1
{ echo "as of $(date -u +%FT%TZ)  census-batch6L: $s  waiter=$w  finalize=$(systemctl is-active census-batch6L-finalize.service)"
  echo "waiter: $(cat /run/census-batch6L-wait.status 2>/dev/null || echo none)"
  echo "census-batch2=$(systemctl is-active census-batch2.service)  census-batch3L=$(systemctl is-active census-batch3L.service)  census-batch4p1..3=$(systemctl is-active census-batch4p1.service census-batch4p2.service census-batch4p3.service | tr '\n' ' ')  census-batch5L=$(systemctl is-active census-batch5L.service)"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   /data free: $(df -BG --output=avail /data | tail -1 | tr -d ' ')   /b6L free: $(df -BG --output=avail /b6L | tail -1 | tr -d ' ')   image: $(du -BG /data/loop/b6L.img | cut -f1)$([ -e /b6L/ctp/STOP ] && echo '  STOP present')"
  echo "guard: $(cat /run/census-batch4-guard.status 2>/dev/null || echo none)"
  [ -e /run/census-batch4-guard.tripped ] && echo "GUARD TRIPPED: $(cat /run/census-batch4-guard.tripped)"
  echo; (cd /b6L/ctp && CTP_CONFIG=/home/ec2-user/census-batch6L.cfg .venv/bin/python ctp.py progress --manifest "$I/manifest.batch6L.tsv" --last 5 2>&1)
  echo; cat "$T/steps.txt"
} > "$T/progress.txt"
tail -n 300 /data/logs/batch6L.log > "$T/batch6L.log.tail" 2>/dev/null
[ -f /b6L/ctp/ledger.jsonl ] && cp /b6L/ctp/ledger.jsonl "$T/ledger.jsonl"
{ date -u +%FT%TZ; uptime; cat /proc/pressure/io /proc/pressure/cpu /proc/pressure/memory 2>/dev/null; cat /proc/meminfo; df -h /data /b4p1 /b4p2 /b4p3 /b5L /b6L /; du -h /data/loop/*.img; } > "$T/system.txt" 2>&1
aws s3 cp "$T/" "$D/" --recursive --only-show-errors
EOF_census-batch6L-live
chmod 755 $B/census-batch6L-live.new; mv -f $B/census-batch6L-live.new $B/census-batch6L-live
cat > $B/census-batch6L-finalize.new <<'EOF_census-batch6L-finalize'
#!/usr/bin/env bash
# census-batch6L-finalize (census-batch6L-finalize.service; OnSuccess=/OnFailure= of census-batch6L),
# made from census-batch5L-finalize (2026-10-09 ~20:00 UTC; one part "L"). Copies the results of
# census batch6L (the L projects of batch6) to s3://BUCKET/batch6L/final/, checks every object (key and size)
# and SHA256SUMS against the local files, writes DONE. Then it powers the instance off (stop, not
# terminate) only if EVERY other census on this instance (batch 2, 3L, 4, 5L) has
# finalized: /usr/local/bin/census-other-done batch6L decides; the last census to finalize powers off.
# No power-off if the check fails, with --dry-run, if the longest part ran < 1 h, or if
# /home/ec2-user/NO_SHUTDOWN exists.
# --dry-run: copy to batch6L/dryrun/, never power off.
#   CTP_L / OUT_L in the environment override the ctp clone and output dir; MANIFEST the
#   manifest given to ctp progress.
# --decide-only: print only the power-off decision (census-other-done), copy nothing.
set -uo pipefail
export AWS_PAGER=""
SELF=batch6L; PARTS="L"
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}
I=/home/ec2-user/batch6-input
DEST=$B/batch6L/final; [ $DRY = 1 ] && DEST=$B/batch6L/dryrun
S_=/b6L/final-stage; FLOG=/data/logs/finalize-batch6L.log; TM=$(mktemp -d /tmp/finalize-batch6L.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize: $*"; }
fail() { say "FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > "$TM/FINALIZE_FAILED"
         aws s3 cp "$TM/FINALIZE_FAILED" "$DEST/FINALIZE_FAILED" --only-show-errors; aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors; exit 1; }
part_env() { local c="CTP_$1" o="OUT_$1"; CTP=${!c:-/b6L/ctp}; OUT=${!o:-/b6L/census-2026-10-batch6L}
             CFG=/home/ec2-user/census-batch6L.cfg; LOG=/data/logs/batch6L.log; }
unit() { echo census-batch6L.service; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would power off' || echo 'no power-off')"; exit 0; fi
# Hold: while /run/census-batch6L-hold exists, a real finalize does nothing (a census stopped on
# purpose is not finalized as a partial result).
if [ $DRY = 0 ] && [ -e /run/census-batch6L-hold ]; then
  say "hold: /run/census-batch6L-hold exists ($(cat /run/census-batch6L-hold)); no finalize"; exit 0; fi
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
  cp -p "$I/manifest.batch6L.tsv" "$I/manifest.batch6.tsv" "$S_/logs/" 2>/dev/null
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
{ echo "cregit census batch6L finished and copied: $(date -u +%FT%TZ)"
  echo "instance: $(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)  dry_run=$DRY  parts: $PARTS"
  echo "parts:$svc"
  echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")"
  for p in $PARTS; do part_env $p; echo "--- part $p: ctp progress"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest ${MANIFEST:-$I/manifest.batch6L.tsv} --last 3 2>&1 | head -5); done
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
if [ "$ran" -lt 3600 ]; then say "the longest part ran only ${ran}s (< 1 h): an early failure, so no power-off; look at /data/logs/batch6L.log"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no power-off"; exit 0; fi
if ! why=$(/usr/local/bin/census-other-done $SELF 2>&1); then say "$why: no power-off; the last census to finalize powers off"; exit 0; fi
say "$why"
say "powering off (the instance stops; it is not terminated)"
sync; shutdown -h now
EOF_census-batch6L-finalize
chmod 755 $B/census-batch6L-finalize.new; mv -f $B/census-batch6L-finalize.new $B/census-batch6L-finalize
cat > $B/census-batch6L-wait.new <<'EOF_census-batch6L-wait'
#!/usr/bin/env bash
# census-batch6L-wait (census-batch6L-wait.service, root; 2026-10-09 ~20:00 UTC): start census-batch6L
# (the 3 L projects of batch 6) only when the batch 4 parts free slots on this instance. Every 60 s it
# starts census-batch6L.service when ALL of these hold:
#   (1) batch 4 has no project it has not started: each census-batch4pK is inactive, or census-steps
#       --counts reports 0 not started for it;
#   (2) the instance runs at most MAXRUN (default 16) projects in total (batch2, batch3L, batch4p1-3,
#       batch5L; census-steps --counts of each active census), so with the 3 L projects it runs <= 19,
#       about the 20 slots of batches 2-4;
#   (3) MemAvailable >= MINMEM_GB (default 120 GiB): the 3 L projects run with --memory-limit 16GB
#       each plus git and blame, and the running L projects of batch 3L and 5L still grow;
#   (4) /data has >= MINDISK_GB (default 1500) GiB free, well above the 800 GiB guard.
#   (5) the identity gate passed for the commit the copy /b6L/cregit-ec2 is at: the last line of
#       /etc/cregit-census/batch6L.gate is "CHECK OK <time> cregit <that commit> ..." (census-batch6L-cregit;
#       batches 6-20 run on the new trailers commit, so the start waits until it is set and gated).
# A STOP file in /b6L/ctp holds the start. Status: /run/census-batch6L-wait.status.
# --decide-only: print the decision once and exit (0 = would start, 1 = would wait); starts nothing.
# Test overrides: COUNTS_<name> ("RUNNING NOT_STARTED") and ACTIVE_<name> (unit state) per census name
# (batch2 batch3L batch4p1 batch4p2 batch4p3 batch5L), MEMAVAIL_GB, DATAFREE_GB, GATE_OK (1 = gate passed, 0 = not).
set -uo pipefail
MAXRUN=${MAXRUN:-16}; MINMEM=${MINMEM_GB:-120}; MINDISK=${MINDISK_GB:-1500}
ST=/run/census-batch6L-wait.status
# name | unit | ctp dir | manifest
CENS="batch2|census-batch2.service|/home/ec2-user/ctp|/home/ec2-user/batch2-input/manifest.batch2.tsv
batch3L|census-batch3L.service|/home/ec2-user/ctp-b3L|/home/ec2-user/batch3L-input/manifest.batch3L.tsv
batch4p1|census-batch4p1.service|/b4p1/ctp|/home/ec2-user/batch4-input/manifest.batch4p1.tsv
batch4p2|census-batch4p2.service|/b4p2/ctp|/home/ec2-user/batch4-input/manifest.batch4p2.tsv
batch4p3|census-batch4p3.service|/b4p3/ctp|/home/ec2-user/batch4-input/manifest.batch4p3.tsv
batch5L|census-batch5L.service|/b5L/ctp|/home/ec2-user/batch5-input/manifest.batch5L.tsv"
decide() {  # sets msg; returns 0 = start
  local run=0 b4pend=0 bad="" n u c m s cv av r p desc=""
  while IFS='|' read -r n u c m; do
    av="ACTIVE_$n"; s=${!av-$(systemctl is-active "$u")}
    case $s in active|activating|deactivating) ;; *) desc="$desc $n=$s"; continue ;; esac
    cv="COUNTS_$n"; read -r r p < <(echo "${!cv-$(/usr/local/bin/census-steps --counts "$c" "$m" 2>/dev/null || echo '? ?')}")
    case "$r$p" in *[!0-9]*|'') bad="$bad $n"; desc="$desc $n=?"; continue ;; esac
    run=$((run + r)); case $n in batch4p*) b4pend=$((b4pend + p)) ;; esac
    desc="$desc $n=${r}r/${p}q"
  done <<<"$CENS"
  local mem=${MEMAVAIL_GB:-$(awk '/MemAvailable/{printf "%d", $2/1048576}' /proc/meminfo)}
  local disk=${DATAFREE_GB:-$(df -BG --output=avail /data | tail -1 | tr -dc 0-9)}
  msg="$(date -u +%FT%TZ) running $run (max $MAXRUN), batch 4 not started $b4pend, MemAvailable ${mem}G (min $MINMEM), /data free ${disk}G (min $MINDISK);$desc"
  [ -z "$bad" ] || { msg="$msg; counts unreadable for:$bad: waiting"; return 1; }
  [ -e /b6L/ctp/STOP ] && { msg="$msg; STOP exists in /b6L/ctp: holding"; return 1; }
  local gok=${GATE_OK:-} gc head
  if [ -z "$gok" ]; then
    gc=$(tail -1 /etc/cregit-census/batch6L.gate 2>/dev/null | sed -n 's/^CHECK OK [^ ]* cregit \([0-9a-f]\{40\}\).*/\1/p')
    head=$(sudo -u ec2-user git -C /b6L/cregit-ec2 rev-parse HEAD 2>/dev/null); gok=0; [ -n "$gc" ] && [ "$gc" = "$head" ] && gok=1
  fi
  [ "$gok" = 1 ] || { msg="$msg; no passed identity gate for the cregit commit of /b6L/cregit-ec2 (census-batch6L-cregit): waiting"; return 1; }
  [ "$b4pend" = 0 ] || { msg="$msg; batch 4 still has projects to start: waiting"; return 1; }
  [ "$run" -le "$MAXRUN" ] || { msg="$msg; too many running: waiting"; return 1; }
  [ "$mem" -ge "$MINMEM" ] || { msg="$msg; memory low: waiting"; return 1; }
  [ "$disk" -ge "$MINDISK" ] || { msg="$msg; /data low: waiting"; return 1; }
  msg="$msg; start"; return 0
}
if [ "${1:-}" = --decide-only ]; then decide; rc=$?; echo "decide-only: $msg"; exit $rc; fi
while :; do
  if decide; then
    echo "$msg: starting census-batch6L.service" | tee "$ST"
    systemctl start --no-block census-batch6L.service
    exit 0
  fi
  echo "$msg" > "$ST"
  sleep 60
done
EOF_census-batch6L-wait
chmod 755 $B/census-batch6L-wait.new; mv -f $B/census-batch6L-wait.new $B/census-batch6L-wait
cat > $B/census-batch6L-cregit.new <<'EOF_census-batch6L-cregit'
#!/usr/bin/env bash
# census-batch6L-cregit --commit SHA --bundle S3URL --bundle-sha256 H --want-pq H [--want-srcml H] | --base
# (root, big EC2; 2026-10-09 ~20:10 UTC): set the cregit commit of census batch6L before it starts. It checks
# the copy /b6L/cregit-ec2 out at SHA (fetched from the git bundle, sha256-checked; --base: the AMI
# commit 95cdc88 with the batch 5 gate values), then runs the identity gate on it: libsrcml.so.1.1.0
# sha256, the libexpat Parquet sha256 (scratch ctp clone /b6L/ctp-check, output /b6L/libexpat-check/out)
# and the blobExec jar against /data/cregit-ec2. The result goes to /etc/cregit-census/batch6L.gate; its
# last line "CHECK OK <time> cregit <SHA> libexpat <H>" lets census-batch6L-wait start the census.
# Refused once census-batch6L has started (a ledger in /b6L/ctp) or while it is active.
set -uo pipefail
export AWS_PAGER=""
G=/etc/cregit-census/batch6L.gate; D=/b6L/cregit-ec2
srcml=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3 commit="" bundle="" bsha="" pq=""
case ${1:-} in
  --base) commit=$(sudo -u ec2-user git -C /data/cregit-ec2 rev-parse HEAD); pq=40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d ;;
  --commit) while [ $# -gt 0 ]; do case $1 in --commit) commit=$2; shift 2 ;; --bundle) bundle=$2; shift 2 ;;
      --bundle-sha256) bsha=$2; shift 2 ;; --want-pq) pq=$2; shift 2 ;; --want-srcml) srcml=$2; shift 2 ;; *) echo "unknown $1"; exit 2 ;; esac; done
    [[ $commit =~ ^[0-9a-f]{40}$ ]] && [[ $bsha =~ ^[0-9a-f]{64}$ ]] && [[ $pq =~ ^[0-9a-f]{64}$ ]] && [ -n "$bundle" ] || { echo "bad arguments"; exit 2; } ;;
  *) echo "usage: census-batch6L-cregit --commit SHA --bundle URL --bundle-sha256 H --want-pq H | --base"; exit 2 ;;
esac
case $(systemctl is-active census-batch6L.service) in active|activating|deactivating) echo "census-batch6L is active: refusing"; exit 1 ;; esac
[ -e /b6L/ctp/ledger.jsonl ] && { echo "census-batch6L has started (/b6L/ctp/ledger.jsonl): refusing"; exit 1; }
fail() { echo "CHECK FAILED $(date -u +%FT%TZ): $*" | tee -a $G; exit 1; }
echo "gate of $D for $commit started $(date -u +%FT%TZ)" >> $G; chmod 644 $G
if [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" != "$commit" ]; then
  [ -n "$bundle" ] || fail "no bundle for $commit"
  bf=/home/ec2-user/batch6-input/$(basename "$bundle")
  if [ ! -f $bf ] || [ "$(sha256sum $bf | cut -d' ' -f1)" != "$bsha" ]; then aws s3 cp "$bundle" $bf.tmp --only-show-errors && mv -f $bf.tmp $bf; fi
  [ "$(sha256sum $bf | cut -d' ' -f1)" = "$bsha" ] || fail "bundle sha256 differs"
  chown ec2-user: $bf
  [ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || fail "$D is dirty"
  sudo -u ec2-user bash -c "set -e; cd $D; git fetch -q $bf '+refs/heads/*:refs/remotes/fed-bundle/*'; git checkout -q --detach $commit" || fail "fetch/checkout"
fi
[ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = "$commit" ] || fail "$D is not at $commit"
[ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || fail "$D is dirty after the checkout"
got_s=$(sudo -u ec2-user -i bash /home/ec2-user/srcml-sha-b6L.sh 2>/dev/null | grep -o '^[0-9a-f]\{64\}' | tail -1)
echo "libsrcml.so.1.1.0 sha256 $got_s" | tee -a $G; [ "$got_s" = "$srcml" ] || fail "libsrcml differs from $srcml"
ts=$(date +%s); [ -d /b6L/libexpat-check/out ] && mv /b6L/libexpat-check/out /b6L/libexpat-check/out.old.$ts
[ -d /b6L/ctp-check ] && mv /b6L/ctp-check /b6L/ctp-check.old.$ts  # a fresh scratch clone: no ledger of the earlier check
t0=$(date +%s); sudo -u ec2-user -i bash /home/ec2-user/check-b6L.sh | tail -2
got=$(sha256sum /b6L/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
echo "libexpat Parquet sha256 $got ($(( $(date +%s) - t0 )) s)" | tee -a $G; [ "$got" = "$pq" ] || fail "libexpat Parquet differs from $pq"
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
ref=$(jar /data/cregit-ec2); [ -n "$ref" ] && [ "$(jar $D)" = "$ref" ] || fail "blobExec jar differs"
echo "CHECK OK $(date -u +%FT%TZ) cregit $commit libexpat $pq" | tee -a $G
EOF_census-batch6L-cregit
chmod 755 $B/census-batch6L-cregit.new; mv -f $B/census-batch6L-cregit.new $B/census-batch6L-cregit
echo "L2a: scripts installed: $(cd $B && sha256sum census-other-done census-batch4-guard census-backup | cut -c1-16 | tr "\n" " ")"
