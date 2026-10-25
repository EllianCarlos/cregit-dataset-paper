#!/usr/bin/env bash
# jv-pull (machine A, root; jv-pull.timer every 10 min, installed by P1-install-a.sh).
# The pull of the aws-sdk-java split:
#   1. pull: the new complete batches of s3://B/dataset-x1k/java-split/out/<k>/batches/ into the
#      blame dir of the row, with jv_pull.py as ec2-user (sha256, members, part names; link(2) +
#      unlink: never an overwrite; a temp dir on the file system of the blame dir);
#   2. the status.txt of each part (to state/status/, for P2);
#   3. A's newest started index (jv_pull.py apos) -> java-split/control/a-pos.txt: the extras
#      start no file at or below it plus their margin;
#   4. the end: when every part is finished and no batch waits, and A's list holds files that
#      were pulled after A's last start (its list was built at that start and is not checked
#      again), restart the row once with the R8 procedure (NO_SHUTDOWN, stop, start, the start
#      line must have "from-step 7," and "blame-jobs <JOBS>,"). The new list skips every .blame.
#      Only with AUTO_RESTART=1, under the lock of R8 (rebalance.lock), and never while a guard
#      file exists. Any error writes java-split/ALERT; later runs then only pull.
# Machine A can also run rs-pull (the rust-split kit) and R8 at the same time. Each pull restarts
# only its own row (P is fixed), and every restart takes rebalance.lock with flock -n first, so two
# restarts never run at once. The restart keeps JOBS of run.env, and it refuses when run.env holds
# fewer jobs than the last start line: it never lowers the jobs that R8 gave the row.
# The P1 stop: while /data/x1k-long/java-split/HOLD exists it does nothing. The S3 file
# control/STOP is for the extras (they end); P1 still pulls what they send, and the end rule
# counts a STOPPED part as finished.
# Env (from /etc/java-split/pull.env): N, AUTO_RESTART, STALE_MIN, RESTART_MIN; FORCE_RESTART=1 (P3)
# skips the rule but not the guards. Test hooks: JV_TEST, JV_LIB, JV_BUCKET, ROOT,
# X1K_ASSET, X1K_HOME, X1K_RUN, SYSTEMCTL, RUNAS, POLL, SETTLE.
# Output: counts only, through sed, which drops each at sign. Log: state/pull.log.
set -uo pipefail
P=aws__aws-sdk-java
ROOT=${ROOT:-/data/x1k-long}
S=$ROOT/java-split
B=${JV_BUCKET:-s3://${RUNNER_BUCKET}}
PFX=dataset-x1k/java-split
ASSET=${X1K_ASSET:-/sys/devices/virtual/dmi/id/board_asset_tag}
HOMEU=${X1K_HOME:-/home/ec2-user}
RUND=${X1K_RUN:-/run}
SYSTEMCTL=${SYSTEMCTL:-systemctl}
# RUNAS is split into words on purpose (a command prefix).
RUNAS=${RUNAS-runuser -u ec2-user --}
POLL=${POLL:-5}; SETTLE=${SETTLE:-20}
[ -f /etc/java-split/pull.env ] && [ -z "${JV_TEST:-}" ] && . /etc/java-split/pull.env
N=${N:-4}; AUTO_RESTART=${AUTO_RESTART:-1}; STALE_MIN=${STALE_MIN:-40}; RESTART_MIN=${RESTART_MIN:-100}
LIB=${JV_LIB:-/usr/local/lib/java-split}
for v in N AUTO_RESTART STALE_MIN RESTART_MIN POLL SETTLE; do
  case ${!v} in ''|*[!0-9]*) echo "ABORT: $v=${!v} is not a whole number"; exit 1 ;; esac
done
IID=$(cat "$ASSET" 2>/dev/null)
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: ${IID:-no id} is not machine A"; exit 1; }
mkdir -p "$S/state/status"
exec 9>>"$S/state/pull.lock" || exit 1
flock -n 9 || { echo "== $(date -u +%FT%TZ) jv-pull: another run holds the lock" >> "$S/state/pull.log"; exit 0; }

main() {
  local T BL ST L now apos astart d jobs
  echo "== $(date -u +%FT%TZ) jv-pull on $IID: N=$N AUTO_RESTART=$AUTO_RESTART STALE_MIN=$STALE_MIN RESTART_MIN=$RESTART_MIN"
  if [ -e "$S/HOLD" ]; then echo "  HOLD exists: nothing done"; return 0; fi
  T=$(readlink -f "$ROOT/$P"); BL=$T/out/$P/blame; ST=$T/java-split-stage
  [ -d "$BL" ] || { echo "  no blame dir: nothing done"; return 0; }
  [ -f "$S/e1/left.tsv" ] && [ -d "$S/e1/parts" ] || { echo "  ABORT: no E1 lists in $S/e1"; return 1; }
  $RUNAS mkdir -p "$ST" || return 1
  L=$S/state/listing.txt
  if ! $RUNAS env TZ=UTC aws s3 ls --recursive "$B/$PFX/out/" > "$L.tmp" 2> "$S/state/listing.err"; then
    [ -s "$S/state/listing.err" ] && { echo "  ABORT: s3 ls failed"; return 1; }
  fi
  mv -f "$L.tmp" "$L"
  echo "  listing: $(wc -l < "$L") keys"
  # 1. pull
  $RUNAS python3 -I "$LIB/jv_pull.py" pull --listing "$L" --prefix "$PFX/out/" --s3 "$B/$PFX" --stage "$ST" \
    --blame "$BL" --parts "$S/e1/parts" --n "$N" --state "$S/state/pull" | sed 's/^/  /'
  [ "${PIPESTATUS[0]}" = 0 ] || echo "  WARNING: a batch was bad or had refused names (see state/pull/applied.tsv)"
  # 2. status files of the parts
  for k in $(seq 1 "$N"); do
    if grep -q " $PFX/out/$k/status.txt\$" "$L"; then
      aws s3 cp "$B/$PFX/out/$k/status.txt" "$S/state/status/$k.txt.tmp" --only-show-errors \
        && mv -f "$S/state/status/$k.txt.tmp" "$S/state/status/$k.txt"
    fi
  done
  # 3. A's position
  apos=$($RUNAS python3 -I "$LIB/jv_pull.py" apos --left "$S/e1/left.tsv" --log "$T/out/$P/pipeline.log" --state "$S/state/pull")
  case $apos in ''|*[!0-9]*) echo "  ABORT: apos '$apos'"; return 1 ;; esac
  now=$(date +%s)
  echo "$apos $now" > "$S/state/a-pos.txt"
  $RUNAS aws s3 cp "$S/state/a-pos.txt" "$B/$PFX/control/a-pos.txt" --only-show-errors \
    && echo "  a-pos: $apos (sent)" || echo "  WARNING: a-pos upload failed"
  # 4. the end
  astart=$(grep -a '=== .* x1k-long .* start' "$T/logs/run.log" 2>/dev/null | tail -1 | sed -n 's/^=== \([0-9TZ:-]*\) .*/\1/p')
  astart=$(date -d "${astart:-1970-01-01T00:00:00Z}" +%s 2>/dev/null || echo 0)
  d=$($RUNAS python3 -I "$LIB/jv_pull.py" decide --listing "$L" --prefix "$PFX/out/" --n "$N" --state "$S/state/pull" \
      --apos "$apos" --a-start "$astart" --now "$now" --stale-min "$STALE_MIN" --restart-min "$RESTART_MIN")
  echo "  decide: $d"
  if [ "${FORCE_RESTART:-0}" = 1 ]; then echo "  FORCE_RESTART=1 (P3-restart-a.sh): restart whatever the rule says"
  else
    case $d in RESTART*) ;; *) return 0 ;; esac
    if [ "$AUTO_RESTART" != 1 ]; then echo "  AUTO_RESTART=0: no restart (run it by hand: P3-restart-a.sh)"; return 0; fi
  fi
  if [ -e "$S/ALERT" ]; then echo "  $S/ALERT exists: no restart until a person checks it"; return 0; fi
  restart_row "$T"
}

alert() { echo "  ALERT: $*"; echo "$(date -u +%FT%TZ) jv-pull ALERT: $*" >> "$S/ALERT"; }
starts() { local n; n=$(grep -a -c '=== .* x1k-long' "$1" 2>/dev/null); echo "${n:-0}"; }

# The R8 procedure for one row, with the same guards and lock.
restart_row() {
  local T=$1 PL st jobs run_jobs had=0 n0 sl f fs block=""
  PL=$T/out/$P/pipeline.log
  for f in "$HOMEU/NO_REBALANCE" "$HOMEU/NO_JV_RESTART" "$RUND/census-spot-interrupted" "$RUND/x1k-spot-interrupted" "$ROOT/rebalance.ALERT"; do
    [ -e "$f" ] && block="$block; $f exists"
  done
  fs=$($SYSTEMCTL is-active x1k-long-finalize.service 2>/dev/null)
  case $fs in active|activating|deactivating|reloading) block="$block; the finalize unit is $fs" ;; esac
  if [ -n "$block" ]; then echo "  no restart${block}"; return 0; fi
  exec 8>>"$ROOT/rebalance.lock" || { echo "  cannot open rebalance.lock"; return 1; }
  flock -n 8 || { echo "  R8 holds rebalance.lock: the restart waits for the next run"; return 0; }
  $SYSTEMCTL is-active -q "x1k-long@$P" || { echo "  the unit is not active: no restart"; return 0; }
  st=$(grep -a -E '^  Step [0-9]+ ' "$PL" | tail -1 | awk '{print $2}')
  [ "$st" = 7 ] || { echo "  the newest step heading is ${st:-none}, not 7: no restart"; return 0; }
  jobs=$(sed -n 's/^JOBS=//p' "$T/run.env" | tail -1)
  case $jobs in ''|*[!0-9]*) alert "JOBS '$jobs' in run.env is not a number"; return 1 ;; esac
  # The restart must never lower the jobs. The runner takes JOBS from run.env, and only R8 changes
  # it (under the same lock, never lower). So run.env must hold at least the jobs of the last start.
  run_jobs=$(grep -a '=== .* x1k-long' "$T/logs/run.log" 2>/dev/null | tail -1 | sed -n 's/.*blame-jobs \([0-9]*\),.*/\1/p')
  case $run_jobs in ''|*[!0-9]*) alert "no blame-jobs in the last start line of run.log"; return 1 ;; esac
  if [ "$jobs" -lt "$run_jobs" ]; then alert "JOBS $jobs in run.env is lower than $run_jobs of the last start"; return 1; fi
  [ -e "$HOMEU/NO_SHUTDOWN" ] && had=1
  touch "$HOMEU/NO_SHUTDOWN"; echo "  NO_SHUTDOWN set (it existed before: $had)"
  echo "  restart of $P (JOBS $jobs; .blame $(find "$T/out/$P/blame" -name '*.blame' | wc -l)) at $(date -u +%T)"
  $SYSTEMCTL stop "x1k-long@$P"
  for _ in $(seq 1 30); do $SYSTEMCTL is-active -q "x1k-long@$P" || break; sleep "$POLL"; done
  if $SYSTEMCTL is-active -q "x1k-long@$P"; then alert "$P still active after the stop"; return 1; fi
  n0=$(starts "$T/logs/run.log")
  $SYSTEMCTL reset-failed "x1k-long@$P" 2>/dev/null; $SYSTEMCTL start "x1k-long@$P"
  for _ in $(seq 1 24); do [ "$(starts "$T/logs/run.log")" -gt "$n0" ] && break; sleep "$POLL"; done
  sl=$(grep -a '=== .* x1k-long' "$T/logs/run.log" | tail -1)
  echo "  start line: $(echo "$sl" | cut -c1-80) ... $(echo "$sl" | grep -o 'last completed step.*')"
  if [ "$(starts "$T/logs/run.log")" -gt "$n0" ] && echo "$sl" | grep -q "from-step 7," && echo "$sl" | grep -q "blame-jobs $jobs,"; then
    sleep "$SETTLE"
    if $SYSTEMCTL is-active -q "x1k-long@$P"; then
      echo "  OK: unit active"; echo "$(date -u +%FT%TZ) restart OK" >> "$S/state/restarts.log"
    else alert "the unit is not active $SETTLE s after the start"; return 1; fi
  else alert "no new start line with 'from-step 7,' and 'blame-jobs $jobs,'"; return 1; fi
  if [ $had = 0 ]; then rm -f "$HOMEU/NO_SHUTDOWN"; echo "  NO_SHUTDOWN removed"; fi
  return 0
}

main 2>&1 | sed -u 's/@//g' | tee -a "$S/state/pull.log"
exit "${PIPESTATUS[0]}"
