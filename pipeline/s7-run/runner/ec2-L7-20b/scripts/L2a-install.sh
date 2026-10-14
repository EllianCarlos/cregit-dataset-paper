set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = 0acc488b9a1ed5c6 ] || [ -e $B/census-other-done.orig-L22 ] || { echo "census-other-done changed"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = a96cab084a9525b2 ] || [ -e $B/census-batch4-guard.orig-L22 ] || { echo "census-batch4-guard changed"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = dc3065d425727ea8 ] || [ -e $B/census-backup.orig-L22 ] || { echo "census-backup changed"; exit 1; }
# a finalize that waits for its parts runs census-other-done as a new process at its end, so the
# atomic replacement below is what it will use; the running finalize scripts themselves are not replaced
echo "finalize/backup/guard states: $(for f in census-batch5L-finalize census-L7-20-finalize census-L22-finalize census-backup census-batch4-guard; do echo -n "$f=$(systemctl is-active $f.service) "; done)"
[ -e $B/census-other-done.orig-L22 ] || cp -p $B/census-other-done $B/census-other-done.orig-L22
[ -e $B/census-batch4-guard.orig-L22 ] || cp -p $B/census-batch4-guard $B/census-batch4-guard.orig-L22
[ -e $B/census-backup.orig-L22 ] || cp -p $B/census-backup $B/census-backup.orig-L22
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
#   L7-20   : s3://B/L7-20/final/DONE, units census-L7-20-wait.service census-L7-20.service
#             (2026-10-10 ~00:20 UTC: the 55 L projects of batches 7-20 in one census)
#   L22     : s3://B/L22/final/DONE, units census-L22-wait.service census-L22.service
#             (2026-10-10 ~15:40 UTC: the 2 L projects of batch 22, gcc and emacs)
#   L7-20b  : s3://B/L7-20b/final/DONE, units census-L7-20b-wait.service census-L7-20b.service
#             (2026-10-11: rows 17-56 of the L7-20 queue, the second L queue)
# Each finalize writes its own DONE before it asks, so the last census to finish sees all the
# other DONEs and powers off; the earlier ones do not. Same interface as the 2-census version
# (SELF = batch2|batch3L, plus batch4, batch5L, batch6L, L7-20, L22 and L7-20b), so the older finalizes are unchanged.
# Test overrides, per census N: DONE_URL_N (an S3 object) and UNITS_N (space-separated; "" = none);
# for L7-20 the variable names are DONE_URL_L7_20 and UNITS_L7_20, for L7-20b DONE_URL_L7_20b and UNITS_L7_20b.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
ALL="batch2 batch3L batch4 batch5L batch6L L7-20 L22 L7-20b"
declare -A U=(
  [batch2]="census-batch2.service"
  [batch3L]="census-batch3L-wait.service census-batch3L.service"
  [batch4]="census-batch4p1.service census-batch4p2.service census-batch4p3.service"
  [batch5L]="census-batch5L.service"
  [batch6L]="census-batch6L-wait.service census-batch6L.service"
  [L7-20]="census-L7-20-wait.service census-L7-20.service"
  [L22]="census-L22-wait.service census-L22.service"
  [L7-20b]="census-L7-20b-wait.service census-L7-20b.service"
)
self=${1:-}
case " $ALL " in *" $self "*) [ -n "$self" ] || { echo "usage: census-other-done batch2|batch3L|batch4|batch5L|batch6L|L7-20|L22|L7-20b" >&2; exit 2; } ;;
  *) echo "usage: census-other-done batch2|batch3L|batch4|batch5L|batch6L|L7-20|L22|L7-20b" >&2; exit 2 ;; esac
ok=""
for n in $ALL; do
  [ "$n" = "$self" ] && continue
  uv="UNITS_${n//-/_}"; dv="DONE_URL_${n//-/_}"
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
# 2026-10-10 ~00:20 UTC (L7-20): the same for census L7-20 on /data/loop/bL7.img, /bL7 (the STOP there also
# holds census-L7-20-wait).
# 2026-10-10 ~15:40 UTC (L22): the same for census L22 on /data/loop/bL22.img, /bL22 (the STOP there also
# holds census-L22-wait).
# 2026-10-11 (L7-20b): the same for census L7-20b on /data/loop/bL7b.img, /bL7b (the STOP there also
# holds census-L7-20b-wait).
set -uo pipefail
export AWS_PAGER=""
G=${GUARD_GB:-800}
for k in 1 2 3; do mountpoint -q /b4p$k && fstrim /b4p$k >/dev/null; done
mountpoint -q /b5L && fstrim /b5L >/dev/null
mountpoint -q /b6L && fstrim /b6L >/dev/null
mountpoint -q /bL7 && fstrim /bL7 >/dev/null
mountpoint -q /bL22 && fstrim /bL22 >/dev/null
mountpoint -q /bL7b && fstrim /bL7b >/dev/null
avail=$(df -BG --output=avail /data | tail -1 | tr -dc 0-9)
img=$(for k in 1 2 3; do echo -n "b4p$k $(du -BG /data/loop/b4p$k.img | cut -f1) "; done; [ -e /data/loop/b5L.img ] && echo -n "b5L $(du -BG /data/loop/b5L.img | cut -f1) "; [ -e /data/loop/b6L.img ] && echo -n "b6L $(du -BG /data/loop/b6L.img | cut -f1) "; [ -e /data/loop/bL7.img ] && echo -n "bL7 $(du -BG /data/loop/bL7.img | cut -f1) "; [ -e /data/loop/bL22.img ] && echo -n "bL22 $(du -BG /data/loop/bL22.img | cut -f1) "; [ -e /data/loop/bL7b.img ] && echo -n "bL7b $(du -BG /data/loop/bL7b.img | cut -f1)")
msg="$(date -u +%FT%TZ) /data free ${avail}G (guard ${G}G); image use: $img"
if [ "$avail" -lt "$G" ]; then
  for k in 1 2 3; do [ -d /b4p$k/ctp ] && { touch /b4p$k/ctp/STOP; chown ec2-user: /b4p$k/ctp/STOP; }; done
  [ -d /b5L/ctp ] && { touch /b5L/ctp/STOP; chown ec2-user: /b5L/ctp/STOP; }
  [ -d /b6L/ctp ] && { touch /b6L/ctp/STOP; chown ec2-user: /b6L/ctp/STOP; }
  [ -d /bL7/ctp ] && { touch /bL7/ctp/STOP; chown ec2-user: /bL7/ctp/STOP; }
  [ -d /bL22/ctp ] && { touch /bL22/ctp/STOP; chown ec2-user: /bL22/ctp/STOP; }
  [ -d /bL7b/ctp ] && { touch /bL7b/ctp/STOP; chown ec2-user: /bL7b/ctp/STOP; }
  msg="$msg; BELOW GUARD: STOP written in /b4p1..3/ctp, /b5L/ctp, /b6L/ctp, /bL7/ctp, /bL22/ctp and /bL7b/ctp"
  echo "$msg" > /run/census-batch4-guard.tripped
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch4/live/GUARD --only-show-errors
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch5L/live/GUARD --only-show-errors
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch6L/live/GUARD --only-show-errors
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/L7-20/live/GUARD --only-show-errors
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/L22/live/GUARD --only-show-errors
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/L7-20b/live/GUARD --only-show-errors
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
batch6L|/b6L/census-2026-10-batch6L|/b6L/ctp
L7-20|/bL7/census-2026-10-L7-20|/bL7/ctp
L22|/bL22/census-2026-10-L22|/bL22/ctp
L7-20b|/bL7b/census-2026-10-L7-20b|/bL7b/ctp"
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
cat > $B/census-L7-20b-run.new <<'EOF_census-L7-20b-run'
#!/usr/bin/env bash
# census-L7-20b-run (census-L7-20b.service): the second L queue (user decision 2026-10-11 16:45 UTC):
# rows 17-56 of the L7-20 v2 manifest (BrowserWorks__waterfox .. jlord__patchwork, 40 projects, 330 h
# predicted), in the same order, with 6 workers, on the big EC2, on their own loop XFS /bL7b (own
# rename lock) with their own ctp clone /bL7b/ctp, cregit copy /bL7b/cregit-ec2 (1f17663, gated before
# the start; path fixed), config and output /bL7b/census-2026-10-L7-20b. The same census flags as
# census-L7-20. census-L7-20-split stops census L7-20 before row 17, so no project runs twice.
# Stop after the running projects: touch /bL7b/ctp/STOP (census-batch4-guard does it below 800 GiB
# free on /data).
set -euo pipefail
I=/home/ec2-user/L7-20b-input; M=$I/manifest.L7-20b.tsv
export CTP_CONFIG=/home/ec2-user/census-L7-20b.cfg
cd /bL7b/ctp
n=$(grep -c -v -e '^#' -e '^[[:space:]]*$' "$M")
echo "=== $(date -u +%FT%TZ) census-L7-20b start (cregit $(git -C /bL7b/cregit-ec2 rev-parse --short HEAD) at /bL7b/cregit-ec2, ctp $(git rev-parse --short HEAD), $n projects, 6 workers, out /bL7b/census-2026-10-L7-20b)"
exec .venv/bin/python ctp.py census --manifest "$M" --project-meta "$I/project_meta.L7-20b.json" \
    --workers 6 --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300
EOF_census-L7-20b-run
chmod 755 $B/census-L7-20b-run.new; mv -f $B/census-L7-20b-run.new $B/census-L7-20b-run
cat > $B/census-L7-20b-live.new <<'EOF_census-L7-20b-live'
#!/usr/bin/env bash
# Every 10 min (census-L7-20b-live.timer): status of census L7-20b to s3://BUCKET/L7-20b/live/:
# progress.txt (first line "as of <ts>  census-L7-20b: <state> ...", read by the local watchdog: it
# must contain ": active" while the census runs), steps.txt, L7-20b.log.tail, ledger.jsonl, system.txt.
set -uo pipefail
export AWS_PAGER=""
D=s3://${RUNNER_BUCKET}/L7-20b/live
I=/home/ec2-user/L7-20b-input
T=$(mktemp -d); trap 'rm -r "$T"' EXIT
s=$(systemctl is-active census-L7-20b.service); w=$(systemctl is-active census-L7-20b-wait.service)
# while the waiter holds the start, the state word is "waiting" (the local watchdog accepts it)
case $s in active|activating) ;; *) case $w in active|activating) s=waiting ;; esac ;; esac
/usr/local/bin/census-steps /bL7b/ctp "$I/manifest.L7-20b.tsv" --highlight '' > "$T/steps.txt" 2>&1
{ echo "as of $(date -u +%FT%TZ)  census-L7-20b: $s  waiter=$w  finalize=$(systemctl is-active census-L7-20b-finalize.service)"
  echo "waiter: $(cat /run/census-L7-20b-wait.status 2>/dev/null || echo none)"
  echo "census-L7-20=$(systemctl is-active census-L7-20.service)  census-L22=$(systemctl is-active census-L22.service)  census-batch5L=$(systemctl is-active census-batch5L.service)  census-batch2/3L/4p1-3/6L=$(systemctl is-active census-batch2.service census-batch3L.service census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch6L.service | tr '\n' ' ')"
  # the split watcher: it stops census L7-20 before row 17, so no project runs in both queues
  echo "split: $(systemctl is-active census-L7-20-split.timer) $(cat /run/census-L7-20-split.status 2>/dev/null || echo none)$([ -e /bL7/ctp/STOP ] && echo '  /bL7/ctp/STOP present')"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   /data free: $(df -BG --output=avail /data | tail -1 | tr -d ' ')   /bL7b free: $(df -BG --output=avail /bL7b | tail -1 | tr -d ' ')   image: $(du -BG /data/loop/bL7b.img | cut -f1)$([ -e /bL7b/ctp/STOP ] && echo '  STOP present')"
  echo "guard: $(cat /run/census-batch4-guard.status 2>/dev/null || echo none)"
  [ -e /run/census-batch4-guard.tripped ] && echo "GUARD TRIPPED: $(cat /run/census-batch4-guard.tripped)"
  echo; (cd /bL7b/ctp && CTP_CONFIG=/home/ec2-user/census-L7-20b.cfg .venv/bin/python ctp.py progress --manifest "$I/manifest.L7-20b.tsv" --last 5 2>&1)
  echo; cat "$T/steps.txt"
} > "$T/progress.txt"
tail -n 300 /data/logs/L7-20b.log > "$T/L7-20b.log.tail" 2>/dev/null
[ -f /bL7b/ctp/ledger.jsonl ] && cp /bL7b/ctp/ledger.jsonl "$T/ledger.jsonl"
{ date -u +%FT%TZ; uptime; cat /proc/pressure/io /proc/pressure/cpu /proc/pressure/memory 2>/dev/null; cat /proc/meminfo; df -h /data /b4p1 /b4p2 /b4p3 /b5L /b6L /bL7 /bL22 /bL7b /; du -h /data/loop/*.img; } > "$T/system.txt" 2>&1
aws s3 cp "$T/" "$D/" --recursive --only-show-errors
EOF_census-L7-20b-live
chmod 755 $B/census-L7-20b-live.new; mv -f $B/census-L7-20b-live.new $B/census-L7-20b-live
echo "L2a: scripts installed: $(cd $B && sha256sum census-other-done census-batch4-guard census-backup | cut -c1-16 | tr "\n" " ")"
