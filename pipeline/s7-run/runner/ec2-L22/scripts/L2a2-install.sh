set -uo pipefail
B=/usr/local/bin
cat > $B/census-L22-finalize.new <<'EOF_census-L22-finalize'
#!/usr/bin/env bash
# census-L22-finalize (census-L22-finalize.service; OnSuccess=/OnFailure= of census-L22),
# made from census-L7-20-finalize (2026-10-10 ~15:40 UTC; one part "L"). Copies the results of
# census L22 (the 2 L projects of batch 22) to s3://BUCKET/L22/final/, checks every object (key and size)
# and SHA256SUMS against the local files, writes DONE. Then it powers the instance off (stop, not
# terminate) only if EVERY other census on this instance (batch 2, 3L, 4, 5L, 6L, L7-20) has
# finalized: /usr/local/bin/census-other-done L22 decides; the last census to finalize powers off.
# No power-off if the check fails, with --dry-run, if the longest part ran < 1 h, or if
# /home/ec2-user/NO_SHUTDOWN exists.
# --dry-run: copy to L22/dryrun/, never power off.
#   CTP_L / OUT_L in the environment override the ctp clone and output dir; MANIFEST the
#   manifest given to ctp progress.
# --decide-only: print only the power-off decision (census-other-done), copy nothing.
set -uo pipefail
export AWS_PAGER=""
SELF=L22; PARTS="L"
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}
I=/home/ec2-user/L22-input
DEST=$B/L22/final; [ $DRY = 1 ] && DEST=$B/L22/dryrun
S_=/bL22/final-stage; FLOG=/data/logs/finalize-L22.log; TM=$(mktemp -d /tmp/finalize-L22.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize: $*"; }
fail() { say "FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > "$TM/FINALIZE_FAILED"
         aws s3 cp "$TM/FINALIZE_FAILED" "$DEST/FINALIZE_FAILED" --only-show-errors; aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors; exit 1; }
part_env() { local c="CTP_$1" o="OUT_$1"; CTP=${!c:-/bL22/ctp}; OUT=${!o:-/bL22/census-2026-10-L22}
             CFG=/home/ec2-user/census-L22.cfg; LOG=/data/logs/L22.log; }
unit() { echo census-L22.service; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would power off' || echo 'no power-off')"; exit 0; fi
# Hold: while /run/census-L22-hold exists, a real finalize does nothing (a census stopped on
# purpose is not finalized as a partial result).
if [ $DRY = 0 ] && [ -e /run/census-L22-hold ]; then
  say "hold: /run/census-L22-hold exists ($(cat /run/census-L22-hold)); no finalize"; exit 0; fi
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
  cp -p "$I/manifest.batch22L.tsv" "$S_/logs/" 2>/dev/null
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
{ echo "cregit census L22 finished and copied: $(date -u +%FT%TZ)"
  echo "instance: $(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)  dry_run=$DRY  parts: $PARTS"
  echo "parts:$svc"
  echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")"
  for p in $PARTS; do part_env $p; echo "--- part $p: ctp progress"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest ${MANIFEST:-$I/manifest.batch22L.tsv} --last 3 2>&1 | head -5); done
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
if [ "$ran" -lt 3600 ]; then say "the longest part ran only ${ran}s (< 1 h): an early failure, so no power-off; look at /data/logs/L22.log"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no power-off"; exit 0; fi
if ! why=$(/usr/local/bin/census-other-done $SELF 2>&1); then say "$why: no power-off; the last census to finalize powers off"; exit 0; fi
say "$why"
say "powering off (the instance stops; it is not terminated)"
sync; shutdown -h now
EOF_census-L22-finalize
chmod 755 $B/census-L22-finalize.new; mv -f $B/census-L22-finalize.new $B/census-L22-finalize
cat > $B/census-L22-wait.new <<'EOF_census-L22-wait'
#!/usr/bin/env bash
# census-L22-wait (census-L22-wait.service, root; 2026-10-10 ~15:40 UTC, made from census-L7-20-wait):
# start census-L22 (the 2 L projects of batch 22, gcc and emacs, 2 workers) only when the big EC2 has
# room. Every 60 s it starts census-L22.service when ALL of these hold:
#   (1) at most MAXRUN (default 14) other projects run on the instance (batch2, batch3L, batch4p1-3,
#       batch5L, batch6L, L7-20; census-steps --counts of each active census), so <= 16 after the start;
#   (2) MemAvailable >= MINMEM_GB (default 120 GiB);
#   (3) /data has >= MINDISK_GB (default 1500) GiB free (gcc and emacs are big; the guard stops new
#       starts below 800 GiB);
#   (4) the identity gate passed for the commit /bL22/cregit-ec2 is at: the last line of
#       /etc/cregit-census/L22.gate is "CHECK OK <time> cregit <that commit> ..." (census-L22-cregit);
#   (5) the inputs are there: /home/ec2-user/L22-input/SHA256SUMS checks (s3://BUCKET/batch22/input/ is
#       copied as ec2-user while it is missing).
# A STOP file in /bL22/ctp holds the start. Status: /run/census-L22-wait.status.
# --decide-only: print the decision once and exit (0 = would start, 1 = would wait); starts nothing.
# Test overrides: COUNTS_<name> ("RUNNING NOT_STARTED"), ACTIVE_<name> per census name (batch2 batch3L
# batch4p1 batch4p2 batch4p3 batch5L batch6L L7_20), MEMAVAIL_GB, DATAFREE_GB, GATE_OK (1/0), INPUT_OK (1/0).
set -uo pipefail
MAXRUN=${MAXRUN:-14}; MINMEM=${MINMEM_GB:-120}; MINDISK=${MINDISK_GB:-1500}
ST=/run/census-L22-wait.status; IN=/home/ec2-user/L22-input
CENS="batch2|census-batch2.service|/home/ec2-user/ctp|/home/ec2-user/batch2-input/manifest.batch2.tsv
batch3L|census-batch3L.service|/home/ec2-user/ctp-b3L|/home/ec2-user/batch3L-input/manifest.batch3L.tsv
batch4p1|census-batch4p1.service|/b4p1/ctp|/home/ec2-user/batch4-input/manifest.batch4p1.tsv
batch4p2|census-batch4p2.service|/b4p2/ctp|/home/ec2-user/batch4-input/manifest.batch4p2.tsv
batch4p3|census-batch4p3.service|/b4p3/ctp|/home/ec2-user/batch4-input/manifest.batch4p3.tsv
batch5L|census-batch5L.service|/b5L/ctp|/home/ec2-user/batch5-input/manifest.batch5L.tsv
batch6L|census-batch6L.service|/b6L/ctp|/home/ec2-user/batch6-input/manifest.batch6L.tsv
L7_20|census-L7-20.service|/bL7/ctp|/home/ec2-user/L7-20-input/manifest.L7-20.tsv"
inputs() {  # 0 when the inputs check; copies them while they are missing
  [ -n "${INPUT_OK:-}" ] && { [ "$INPUT_OK" = 1 ]; return; }
  (cd $IN 2>/dev/null && sha256sum --quiet -c SHA256SUMS >/dev/null 2>&1) && return 0
  sudo -u ec2-user bash -c "mkdir -p $IN; AWS_PAGER= aws s3 cp s3://${RUNNER_BUCKET}/batch22/input/ $IN/ --recursive --only-show-errors" >/dev/null 2>&1
  (cd $IN 2>/dev/null && sha256sum --quiet -c SHA256SUMS >/dev/null 2>&1)
}
decide() {  # sets msg; returns 0 = start
  local run=0 bad="" n u c m s cv av r p desc=""
  while IFS='|' read -r n u c m; do
    av="ACTIVE_$n"; s=${!av-$(systemctl is-active "$u")}
    case $s in active|activating|deactivating) ;; *) desc="$desc $n=$s"; continue ;; esac
    cv="COUNTS_$n"; read -r r p < <(echo "${!cv-$(/usr/local/bin/census-steps --counts "$c" "$m" 2>/dev/null || echo '? ?')}")
    case "$r$p" in *[!0-9]*|'') bad="$bad $n"; desc="$desc $n=?"; continue ;; esac
    run=$((run + r)); desc="$desc $n=${r}r/${p}q"
  done <<<"$CENS"
  local mem=${MEMAVAIL_GB:-$(awk '/MemAvailable/{printf "%d", $2/1048576}' /proc/meminfo)}
  local disk=${DATAFREE_GB:-$(df -BG --output=avail /data | tail -1 | tr -dc 0-9)}
  msg="$(date -u +%FT%TZ) other projects running $run (max $MAXRUN), MemAvailable ${mem}G (min $MINMEM), /data free ${disk}G (min $MINDISK);$desc"
  [ -z "$bad" ] || { msg="$msg; counts unreadable for:$bad: waiting"; return 1; }
  [ -e /bL22/ctp/STOP ] && { msg="$msg; STOP exists in /bL22/ctp: holding"; return 1; }
  [ "$run" -le "$MAXRUN" ] || { msg="$msg; too many running: waiting"; return 1; }
  [ "$mem" -ge "$MINMEM" ] || { msg="$msg; memory low: waiting"; return 1; }
  [ "$disk" -ge "$MINDISK" ] || { msg="$msg; /data low: waiting"; return 1; }
  local gok=${GATE_OK:-} gc head
  if [ -z "$gok" ]; then
    gc=$(tail -1 /etc/cregit-census/L22.gate 2>/dev/null | sed -n 's/^CHECK OK [^ ]* cregit \([0-9a-f]\{40\}\).*/\1/p')
    head=$(sudo -u ec2-user git -C /bL22/cregit-ec2 rev-parse HEAD 2>/dev/null); gok=0; [ -n "$gc" ] && [ "$gc" = "$head" ] && gok=1
  fi
  [ "$gok" = 1 ] || { msg="$msg; no passed identity gate for the cregit commit of /bL22/cregit-ec2 (census-L22-cregit): waiting"; return 1; }
  inputs || { msg="$msg; inputs s3://BUCKET/batch22/input/ missing or not checked: waiting"; return 1; }
  msg="$msg; start"; return 0
}
if [ "${1:-}" = --decide-only ]; then decide; rc=$?; echo "decide-only: $msg"; exit $rc; fi
while :; do
  if decide; then
    echo "$msg: starting census-L22.service" | tee "$ST"
    systemctl start --no-block census-L22.service
    exit 0
  fi
  echo "$msg" > "$ST"
  sleep 60
done
EOF_census-L22-wait
chmod 755 $B/census-L22-wait.new; mv -f $B/census-L22-wait.new $B/census-L22-wait
cat > $B/census-L22-cregit.new <<'EOF_census-L22-cregit'
#!/usr/bin/env bash
# census-L22-cregit --commit SHA --bundle S3URL --bundle-sha256 H --want-pq H [--want-srcml H] | --base
# (root, big EC2; made from census-L7-20-cregit 2026-10-10 ~15:40 UTC): set the cregit commit of census L22 before it starts. It checks
# the copy /bL22/cregit-ec2 out at SHA (fetched from the git bundle, sha256-checked; --base: the AMI
# commit 95cdc88 with the batch 5 gate values), then runs the identity gate on it: libsrcml.so.1.1.0
# sha256, the libexpat Parquet sha256 (scratch ctp clone /bL22/ctp-check, output /bL22/libexpat-check/out)
# and the blobExec jar against /data/cregit-ec2. The result goes to /etc/cregit-census/L22.gate; its
# last line "CHECK OK <time> cregit <SHA> libexpat <H>" lets census-L22-wait start the census.
# Refused once census-L22 has started (a ledger in /bL22/ctp) or while it is active.
set -uo pipefail
export AWS_PAGER=""
mkdir -p /etc/cregit-census
G=/etc/cregit-census/L22.gate; D=/bL22/cregit-ec2
srcml=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3 commit="" bundle="" bsha="" pq=""
case ${1:-} in
  --base) commit=$(sudo -u ec2-user git -C /data/cregit-ec2 rev-parse HEAD); pq=40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d ;;
  --commit) while [ $# -gt 0 ]; do case $1 in --commit) commit=$2; shift 2 ;; --bundle) bundle=$2; shift 2 ;;
      --bundle-sha256) bsha=$2; shift 2 ;; --want-pq) pq=$2; shift 2 ;; --want-srcml) srcml=$2; shift 2 ;; *) echo "unknown $1"; exit 2 ;; esac; done
    [[ $commit =~ ^[0-9a-f]{40}$ ]] && [[ $bsha =~ ^[0-9a-f]{64}$ ]] && [[ $pq =~ ^[0-9a-f]{64}$ ]] && [ -n "$bundle" ] || { echo "bad arguments"; exit 2; } ;;
  *) echo "usage: census-L22-cregit --commit SHA --bundle URL --bundle-sha256 H --want-pq H | --base"; exit 2 ;;
esac
case $(systemctl is-active census-L22.service) in active|activating|deactivating) echo "census-L22 is active: refusing"; exit 1 ;; esac
[ -e /bL22/ctp/ledger.jsonl ] && { echo "census-L22 has started (/bL22/ctp/ledger.jsonl): refusing"; exit 1; }
fail() { echo "CHECK FAILED $(date -u +%FT%TZ): $*" | tee -a $G; exit 1; }
echo "gate of $D for $commit started $(date -u +%FT%TZ)" >> $G; chmod 644 $G
if [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" != "$commit" ]; then
  [ -n "$bundle" ] || fail "no bundle for $commit"
  mkdir -p /home/ec2-user/L22-input; bf=/home/ec2-user/L22-input/$(basename "$bundle")
  if [ ! -f $bf ] || [ "$(sha256sum $bf | cut -d' ' -f1)" != "$bsha" ]; then aws s3 cp "$bundle" $bf.tmp --only-show-errors && mv -f $bf.tmp $bf; fi
  [ "$(sha256sum $bf | cut -d' ' -f1)" = "$bsha" ] || fail "bundle sha256 differs"
  chown ec2-user: $bf
  [ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || fail "$D is dirty"
  sudo -u ec2-user bash -c "set -e; cd $D; git fetch -q $bf '+refs/heads/*:refs/remotes/fed-bundle/*'; git checkout -q --detach $commit" || fail "fetch/checkout"
fi
[ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = "$commit" ] || fail "$D is not at $commit"
[ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || fail "$D is dirty after the checkout"
got_s=$(sudo -u ec2-user -i bash /home/ec2-user/srcml-sha-bL22.sh 2>/dev/null | grep -o '^[0-9a-f]\{64\}' | tail -1)
echo "libsrcml.so.1.1.0 sha256 $got_s" | tee -a $G; [ "$got_s" = "$srcml" ] || fail "libsrcml differs from $srcml"
ts=$(date +%s); [ -d /bL22/libexpat-check/out ] && mv /bL22/libexpat-check/out /bL22/libexpat-check/out.old.$ts
[ -d /bL22/ctp-check ] && mv /bL22/ctp-check /bL22/ctp-check.old.$ts  # a fresh scratch clone: no ledger of the earlier check
t0=$(date +%s); sudo -u ec2-user -i bash /home/ec2-user/check-bL22.sh | tail -2
got=$(sha256sum /bL22/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
echo "libexpat Parquet sha256 $got ($(( $(date +%s) - t0 )) s)" | tee -a $G; [ "$got" = "$pq" ] || fail "libexpat Parquet differs from $pq"
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
ref=$(jar /data/cregit-ec2); [ -n "$ref" ] && [ "$(jar $D)" = "$ref" ] || fail "blobExec jar differs"
echo "CHECK OK $(date -u +%FT%TZ) cregit $commit libexpat $pq" | tee -a $G
EOF_census-L22-cregit
chmod 755 $B/census-L22-cregit.new; mv -f $B/census-L22-cregit.new $B/census-L22-cregit
echo "L2a2: scripts installed"
