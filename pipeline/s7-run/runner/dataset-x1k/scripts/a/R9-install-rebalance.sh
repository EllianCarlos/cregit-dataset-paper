#!/usr/bin/env bash
# R9-install-rebalance.sh, machine A (root, through scripts/a/ssm-a.sh; idempotent; written 2026-10-21).
# Installs the automatic rebalance of the blame jobs (user request 2026-10-21 "When a specific one
# finishes can we extend the blame workers?"):
#   1. /usr/local/sbin/x1k-rebalance.sh: the text of scripts/a/R8-rebalance.sh (embedded below; sha256
#      13dbf3efee35baab...; T8 checks that it equals R8);
#   2. x1k-rebalance.service (oneshot, root) and x1k-rebalance.timer (OnBootSec=10min,
#      OnUnitActiveSec=10min); each file is written only if its text changed;
#   3. one run with DRY_RUN=1: the plan for now (it changes nothing);
#   4. enable --now of the timer. The boot time is long past, so the timer may fire at once; the first
#      real run then does what the plan of step 3 says (if nothing changed in between).
# The log of every run: /data/x1k-long/rebalance.log. Ways to stop it are printed at the end.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in
  ${RUNNER_EC2_X1K_LONG_A4}) ;;
  ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}) echo "ABORT: $IID is not machine A"; exit 1 ;;
  *) echo "ABORT: ${IID:-no id} is not machine A (${RUNNER_EC2_X1K_LONG_A4})"; exit 1 ;;
esac
S=/usr/local/sbin/x1k-rebalance.sh; U=/etc/systemd/system
SUM=13dbf3efee35baab4d04a3a8b1b37f7b4fe0a6c4edc0735799b11489b4330e53
# put FILE: move FILE.new over FILE if the text differs; else drop FILE.new.
put() { if cmp -s "$1.new" "$1"; then rm -f "$1.new"; echo "  $1: unchanged"; else mv -f "$1.new" "$1"; echo "  $1: written"; fi; }
main() {
echo "== $(date -u +%FT%TZ) R9 on $IID"
mkdir -p /usr/local/sbin
cat > $S.new <<'EOF_x1k_rebalance'
#!/usr/bin/env bash
# R8-rebalance.sh, machine A (root; from x1k-rebalance.timer every 10 min, or by hand; written 2026-10-21;
# user request 2026-10-21 "When a specific one finishes can we extend the blame workers?").
# Goal: the last row ends as early as possible. When a row ends, its blame jobs go to the step-7 rows
# that have the most work left. It never lowers a row's JOBS (a restart loses the files in progress).
#   1. Guards: no action when /home/ec2-user/NO_REBALANCE, /run/census-spot-interrupted,
#      /run/x1k-spot-interrupted or /data/x1k-long/rebalance.ALERT exists, when the finalize unit runs,
#      or when a row is inactive without an upload (and not in excluded.tsv).
#   2. Budget: TOTAL jobs (default 176). An active row past step 7 counts BUDGET_OTHER (default 8).
#      A step-7 row without rate data keeps its JOBS. The other step-7 rows share the rest.
#   3. Weight of a step-7 row = files left x CPU s per file. Files left: as D5 (the ledger mask on
#      git ls-files -z of the working clone, minus the existing .blame files). CPU s per file: the
#      job-seconds of the window (JOBS from the start lines of logs/run.log) / the .blame files with
#      mtime in the window. Window: last 2 h; last 6 h if fewer than 50 files in 2 h.
#   4. Target = budget x weight / sum of weights (floor, at least 4, the rest to the largest weight).
#      Only rows with target - JOBS >= MIN_GAIN (default 8) restart. If their targets need more than the
#      free jobs, the free jobs are shared so that their new JOBS are in proportion to their weights
#      (a row whose gain then falls below MIN_GAIN is dropped, and the others are computed again).
#   5. Each change is the R6 procedure: NO_SHUTDOWN, stop, run.env.before-R8-<UTC time>, JOBS=,
#      reset-failed, start, the start line must have "from-step 7," and "blame-jobs <n>,". On any error:
#      stop, keep NO_SHUTDOWN, write ALERT to the log and rebalance.ALERT (later runs then do nothing
#      until a person checks the rows and removes the file).
# Env: DRY_RUN=1 (print the plan, change nothing), TOTAL, MIN_GAIN, BUDGET_OTHER. Test hooks (T8 only):
# ROOT, X1K_ASSET, X1K_HOME, X1K_RUN, POLL, SETTLE. Log: /data/x1k-long/rebalance.log (one block per run).
# No '@' is printed: the output goes through sed, which drops each at sign.
set -uo pipefail
ROOT=${ROOT:-/data/x1k-long}
TOTAL=${TOTAL:-176}; MIN_GAIN=${MIN_GAIN:-8}; BUDGET_OTHER=${BUDGET_OTHER:-8}; DRY_RUN=${DRY_RUN:-0}
ASSET=${X1K_ASSET:-/sys/devices/virtual/dmi/id/board_asset_tag}
HOMEU=${X1K_HOME:-/home/ec2-user}
RUND=${X1K_RUN:-/run}
POLL=${POLL:-5}; SETTLE=${SETTLE:-20}
LOG=$ROOT/rebalance.log; LOCK=$ROOT/rebalance.lock; ALERTF=$ROOT/rebalance.ALERT
for v in TOTAL MIN_GAIN BUDGET_OTHER DRY_RUN POLL SETTLE; do
  case ${!v} in ''|*[!0-9]*) echo "ABORT: $v=${!v} is not a whole number"; exit 1 ;; esac
done
IID=$(cat "$ASSET" 2>/dev/null)
case $IID in
  ${RUNNER_EC2_X1K_LONG_A4}) ;;
  ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}) echo "ABORT: $IID is not machine A"; exit 1 ;;
  *) echo "ABORT: ${IID:-no id} is not machine A (${RUNNER_EC2_X1K_LONG_A4})"; exit 1 ;;
esac
[ -d "$ROOT" ] || { echo "ABORT: $ROOT is not a folder"; exit 1; }
exec 9>>"$LOCK" || { echo "ABORT: cannot open $LOCK"; exit 1; }
if ! flock -n 9; then
  echo "== $(date -u +%FT%TZ) R8 pid $$: another R8 run holds the lock; nothing done" | sed 's/@//g' | tee -a "$LOG"
  exit 0
fi

# Per step-7 row: files left and CPU s per file. Stdin: git ls-files -z of the working clone.
# Out: "left n2h n6h window_h files_in_window cpu_s_per_file avg_jobs", or "nodata left n2h n6h".
measure() {
  python3 -c '
import calendar, json, os, re, sys, time
w, b, ledger, runlog, p = sys.argv[1:6]
now, jobs_now = float(sys.argv[6]), int(sys.argv[7])
mask = ""
try:
    for line in open(ledger, errors="replace"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        mr = r.get("manifest_row")
        if isinstance(mr, dict) and mr.get("file_filter"):
            mask = mr["file_filter"]
except OSError:
    pass
rx = re.compile(mask) if mask else None
left = 0
mt = []
for raw in sys.stdin.buffer.read().split(b"\0"):
    if not raw:
        continue
    f = os.fsdecode(raw)
    if rx and not rx.search(f):
        continue
    try:
        os.stat(os.path.join(w, f))
    except OSError:
        continue
    try:
        mt.append(os.stat(os.path.join(b, f + ".blame")).st_mtime)
    except OSError:
        left += 1
# The JOBS in effect over time: the start lines of the runner ("=== <UTC> x1k-long <p> start ... blame-jobs <n>,").
srx = re.compile(r"^=== (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) x1k-long (\S+) start .*?blame-jobs (\d+),")
starts = []
try:
    for line in open(runlog, errors="replace"):
        m = srx.match(line)
        if m and m.group(2) == p:
            starts.append((calendar.timegm(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%SZ")), int(m.group(3))))
except OSError:
    pass
starts.sort()
def jobs_seconds(t0, t1):
    if not starts:
        return jobs_now * (t1 - t0)
    total = 0.0
    for i, (ts, j) in enumerate(starts):
        a = t0 if i == 0 else max(t0, ts)
        z = starts[i + 1][0] if i + 1 < len(starts) else t1
        z = min(z, t1)
        if z > a:
            total += j * (z - a)
    return total
n2 = sum(1 for m in mt if m >= now - 7200)
n6 = sum(1 for m in mt if m >= now - 21600)
if n2 >= 50:
    h, n = 2, n2
elif n6 > 0:
    h, n = 6, n6
else:
    print("nodata %d %d %d" % (left, n2, n6)); sys.exit(0)
# Start the window no earlier than the first .blame of the row (step 7 may have begun inside it).
t0 = max(now - h * 3600, min(mt))
if now - t0 < 600:
    print("nodata %d %d %d" % (left, n2, n6)); sys.exit(0)
js = jobs_seconds(t0, now)
print("%d %d %d %d %d %.3f %.1f" % (left, n2, n6, h, n, js / n, js / (now - t0)))
' "$@"
}

# The plan. Stdin: "p kind jobs weight" (kind: s7 = step 7 with data, nodata, other). Out: "p cur target new".
plan() {
  python3 -c '
import math, sys
total, min_gain, b_other = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
rows = [l.split() for l in sys.stdin if l.strip()]
cur = {r[0]: int(r[2]) for r in rows}
kind = {r[0]: r[1] for r in rows}
w = {r[0]: float(r[3]) for r in rows if r[1] == "s7"}
n_other = sum(1 for r in rows if r[1] == "other")
used = sum(cur[p] for p in cur if kind[p] != "other") + n_other * b_other
free = total - used
b7 = total - n_other * b_other - sum(cur[p] for p in cur if kind[p] == "nodata")
W = sum(w.values())
target = {}
if W > 0 and b7 > 0:
    for p in w:
        target[p] = max(4, int(math.floor(b7 * w[p] / W)))
    big = max(w, key=lambda q: w[q])
    target[big] += b7 - sum(target.values())
new = dict(cur)
cand = [p for p in target if target[p] - cur[p] >= min_gain]
note = ""
if free <= 0:
    note = "the jobs in use (%d) reach the budget %d: no change" % (used, total)
elif not cand:
    note = "no row gains %d or more: no change" % min_gain
elif sum(target[p] - cur[p] for p in cand) <= free:
    for p in cand:
        new[p] = target[p]
    note = "the gaining rows get their targets"
else:
    S = list(cand)
    while S:
        avail = free + sum(cur[p] for p in S)
        WS = sum(w[p] for p in S)
        share = {p: avail * w[p] / WS for p in S}
        low = min(S, key=lambda q: share[q] - cur[q])
        if share[low] - cur[low] >= min_gain:
            break
        S.remove(low)
    if S:
        give = {p: min(target[p], int(math.floor(share[p]))) for p in S}
        big = max(S, key=lambda q: w[q])
        give[big] = min(target[big], give[big] + avail - sum(give.values()))
        for p in S:
            new[p] = give[p]
        note = "the targets need more than the %d free jobs: shared by weight among the gaining rows" % free
    else:
        note = "after sharing the %d free jobs, no row gains %d or more: no change" % (free, min_gain)
after = sum(new[p] for p in new if kind[p] != "other") + n_other * b_other
assert after <= max(total, used), "plan over budget"
assert all(new[p] >= cur[p] for p in cur), "plan lowers a row"
print("# used %d of %d, free %d; step-7 share %d (rows past step 7: %d x %d); after the plan %d" % (used, total, free, b7, n_other, b_other, after))
print("# " + note)
for p in cur:
    print("%s %d %s %d" % (p, cur[p], target.get(p, "-"), new[p]))
' "$TOTAL" "$MIN_GAIN" "$BUDGET_OTHER"
}

alert() { echo "ALERT: $*"; echo "$(date -u +%FT%TZ) R8 ALERT: $*" >> "$ALERTF"; }
starts() { local n; n=$(grep -a -c '=== .* x1k-long' "$1" 2>/dev/null); echo "${n:-0}"; }

main() {
  local now p T PL st jobs block="" odd="" rows="" info
  now=$(date +%s)
  echo "== $(date -u +%FT%TZ) R8 rebalance on $IID: DRY_RUN=$DRY_RUN TOTAL=$TOTAL MIN_GAIN=$MIN_GAIN BUDGET_OTHER=$BUDGET_OTHER"
  for f in "$HOMEU/NO_REBALANCE" "$RUND/census-spot-interrupted" "$RUND/x1k-spot-interrupted" "$ALERTF"; do
    [ -e "$f" ] && block="$block; $f exists"
  done
  fs=$(systemctl is-active x1k-long-finalize.service 2>/dev/null)
  case $fs in active|activating|deactivating|reloading) block="$block; the finalize unit is $fs" ;; esac
  [ -f "$ROOT/run.list" ] || { echo "  no $ROOT/run.list: nothing to do"; return 0; }
  if [ -n "$block" ] && [ "$DRY_RUN" = 0 ]; then echo "  no action${block}"; return 0; fi
  printf '  %-40s %5s %4s %8s %6s %6s %3s %9s %8s %10s\n' row step JOBS left 2h 6h win cpu_s/file avg_jobs weight_cpu_h
  for p in $(cat "$ROOT/run.list"); do T=$(readlink -f "$ROOT/$p"); PL=$T/out/$p/pipeline.log
    if ! systemctl is-active -q "x1k-long@$p"; then
      if [ -e "$T/uploaded/$p" ]; then :
      elif [ -f "$ROOT/excluded.tsv" ] && cut -f1 "$ROOT/excluded.tsv" | grep -q -x -F "$p"; then :
      else odd="$odd $p"; fi
      continue
    fi
    st=$(grep -a -E '^  Step [0-9]+ ' "$PL" 2>/dev/null | tail -1 | awk '{print $2}')
    jobs=$(sed -n 's/^JOBS=//p' "$T/run.env" 2>/dev/null | tail -1)
    case $jobs in ''|*[!0-9]*) echo "  $p: JOBS '$jobs' in run.env is not a number"; alert "$p has no valid JOBS in run.env"; return 1 ;; esac
    if [ "$st" != 7 ]; then
      printf '  %-40s %5s %4s   (not in step 7: counts %d)\n' "$p" "${st:-none}" "$jobs" "$BUDGET_OTHER"
      rows="$rows$p other $jobs 0"$'\n'; continue
    fi
    info=$(git -c safe.directory="$T/out/$p/$p-cregit" -C "$T/out/$p/$p-cregit" ls-files -z 2>/dev/null \
           | measure "$T/out/$p/$p-cregit" "$T/out/$p/blame" "$T/ctp/ledger.jsonl" "$T/logs/run.log" "$p" "$now" "$jobs")
    # shellcheck disable=SC2086  # split the fields of the measure line on purpose
    set -- $info
    if [ "${1:-nodata}" = nodata ]; then
      printf '  %-40s %5s %4s %8s %6s %6s   (no rate data: keeps its JOBS)\n' "$p" 7 "$jobs" "${2:-?}" "${3:-?}" "${4:-?}"
      rows="$rows$p nodata $jobs 0"$'\n'
    else
      wt=$(awk -v l="$1" -v c="$6" 'BEGIN {printf "%.1f", l * c}')
      printf '  %-40s %5s %4s %8s %6s %6s %2sh %9s %8s %10.1f\n' "$p" 7 "$jobs" "$1" "$2" "$3" "$4" "$6" "$7" "$(awk -v x="$wt" 'BEGIN {print x / 3600}')"
      rows="$rows$p s7 $jobs $wt"$'\n'
    fi
  done
  if [ -n "$odd" ]; then block="$block; inactive without upload:$odd"; fi
  [ -n "$rows" ] || { echo "  no active row: nothing to do"; return 0; }
  out=$(printf '%s' "$rows" | plan) || { alert "the plan failed"; return 1; }
  echo "$out" | sed -n 's/^# /  /p'
  changes=""
  while read -r p c t n; do
    case $p in '#'*|'') continue ;; esac
    if [ "$n" -gt "$c" ]; then echo "  plan: $p JOBS $c -> $n (+$((n - c)); target $t)"; changes="$changes $p:$c:$n"
    elif [ "$t" != - ]; then echo "  plan: $p keeps $c (target $t)"; fi
  done <<< "$out"
  if [ "$DRY_RUN" != 0 ]; then echo "  DRY_RUN: nothing changed${block:+ (a real run would not act$block)}"; return 0; fi
  if [ -n "$block" ]; then echo "  no action${block}"; return 0; fi
  [ -n "$changes" ] || { echo "  no change"; return 0; }

  # The changes: the R6 procedure, one row after the other; any error stops the run.
  echo "  memory before: $(free -g | sed -n 2p)"
  local had=0 bad=0 ts pj c j old nb0 n0 sl left
  [ -e "$HOMEU/NO_SHUTDOWN" ] && had=1
  touch "$HOMEU/NO_SHUTDOWN"; echo "  NO_SHUTDOWN set (it existed before: $had)"
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  for pj in $changes; do p=${pj%%:*}; c=${pj#*:}; c=${c%%:*}; j=${pj##*:}
    T=$(readlink -f "$ROOT/$p"); PL=$T/out/$p/pipeline.log
    old=$(sed -n 's/^JOBS=//p' "$T/run.env" | tail -1)
    if ! systemctl is-active -q "x1k-long@$p"; then alert "$p: the unit is no longer active; stopped before the change"; bad=1; break; fi
    st=$(grep -a -E '^  Step [0-9]+ ' "$PL" | tail -1 | awk '{print $2}')
    if [ "$st" != 7 ]; then alert "$p: the newest step heading is now $st, not 7; stopped before the change"; bad=1; break; fi
    if [ "$old" != "$c" ]; then alert "$p: JOBS is now $old, not $c as in the plan; stopped before the change"; bad=1; break; fi
    nb0=$(find "$T/out/$p/blame" -name '*.blame' 2>/dev/null | wc -l)
    echo "  $p: stop (JOBS $old -> $j; .blame $nb0) at $(date -u +%T)"
    systemctl stop "x1k-long@$p"
    for _ in $(seq 1 30); do systemctl is-active -q "x1k-long@$p" || break; sleep "$POLL"; done
    if systemctl is-active -q "x1k-long@$p"; then alert "$p: still active after the stop; not changed"; bad=1; break; fi
    left=$(ps -eo args | awk -v t="$T/" 'index($0, t) && $1 != "awk"' | wc -l)
    echo "    stopped at $(date -u +%T); processes with the tree path left: $left"
    cp -p "$T/run.env" "$T/run.env.before-R8-$ts" || { alert "$p: the backup of run.env failed; the unit is stopped"; bad=1; break; }
    sed -i "s/^JOBS=.*/JOBS=$j/" "$T/run.env"
    grep -q "^JOBS=$j\$" "$T/run.env" || { alert "$p: run.env not changed; the unit is stopped"; bad=1; break; }
    n0=$(starts "$T/logs/run.log")
    systemctl reset-failed "x1k-long@$p" 2>/dev/null; systemctl start "x1k-long@$p"
    for _ in $(seq 1 24); do [ "$(starts "$T/logs/run.log")" -gt "$n0" ] && break; sleep "$POLL"; done
    sl=$(grep -a '=== .* x1k-long' "$T/logs/run.log" | tail -1)
    echo "    start line: $(echo "$sl" | cut -c1-80) ... $(echo "$sl" | grep -o 'last completed step.*')"
    if [ "$(starts "$T/logs/run.log")" -gt "$n0" ] && echo "$sl" | grep -q "from-step 7," && echo "$sl" | grep -q "blame-jobs $j,"; then
      sleep "$SETTLE"
      if systemctl is-active -q "x1k-long@$p"; then echo "    OK: unit active; .blame $(find "$T/out/$p/blame" -name '*.blame' | wc -l)"
      else alert "$p: the unit is not active $SETTLE s after the start"; bad=1; break; fi
    else alert "$p: no new start line with 'from-step 7,' and 'blame-jobs $j,'"; bad=1; break; fi
  done
  echo "  git blame processes per volume now:$(for K in 1 2 3 4; do echo -n " /data$K $(ps -eo args | awk -v k="/data$K/" '$1=="git" && $0 ~ "blame" && $0 ~ k' | wc -l)"; done)"
  echo "  memory after: $(free -g | sed -n 2p)"
  if [ $bad = 0 ] && [ $had = 0 ]; then rm -f "$HOMEU/NO_SHUTDOWN"; echo "  NO_SHUTDOWN removed: the finalize can power off again"
  elif [ $bad = 0 ]; then echo "  NO_SHUTDOWN existed before R8: kept"
  else echo "  ALERT: a change failed: NO_SHUTDOWN kept, $ALERTF written; R8 does nothing until a person checks the rows and removes it"; fi
  echo "  R8 done, errors $bad"
  return $bad
}

main 2>&1 | sed -u 's/@//g' | tee -a "$LOG"
exit "${PIPESTATUS[0]}"
EOF_x1k_rebalance
[ "$(sha256sum $S.new | cut -d' ' -f1)" = "$SUM" ] || { echo "ABORT: the embedded text has another sha256"; rm -f $S.new; return 1; }
bash -n $S.new || { echo "ABORT: bash -n failed"; rm -f $S.new; return 1; }
chmod 755 $S.new; put $S
cat > $U/x1k-rebalance.service.new <<'EOF_u1'
[Unit]
Description=x1k long rows: rebalance the blame jobs of the step-7 rows (R8)
RequiresMountsFor=/data1 /data2 /data3 /data4

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/x1k-rebalance.sh
TimeoutStartSec=3600
EOF_u1
put $U/x1k-rebalance.service
cat > $U/x1k-rebalance.timer.new <<'EOF_u2'
[Unit]
Description=x1k long rows: rebalance the blame jobs every 10 min

[Timer]
OnBootSec=10min
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF_u2
put $U/x1k-rebalance.timer
systemctl daemon-reload
echo "-- the plan now (DRY_RUN=1; it changes nothing):"
DRY_RUN=1 $S; echo "-- DRY_RUN exit $?"
systemctl enable --now x1k-rebalance.timer
echo "timer: $(systemctl is-enabled x1k-rebalance.timer), $(systemctl is-active x1k-rebalance.timer); service: $(systemctl is-active x1k-rebalance.service)"
systemctl list-timers --all --no-pager x1k-rebalance.timer | head -2
echo "NO_REBALANCE: $([ -e /home/ec2-user/NO_REBALANCE ] && echo exists || echo absent); rebalance.ALERT: $([ -e /data/x1k-long/rebalance.ALERT ] && echo exists || echo absent)"
echo "To pause it (R8 then does nothing; rm the file to resume): touch /home/ec2-user/NO_REBALANCE"
echo "To stop it for good:                                      systemctl disable --now x1k-rebalance.timer"
echo "To see what it did:                                       tail -40 /data/x1k-long/rebalance.log"
echo "R9 (machine A) done"
}
main 2>&1 | sed -u 's/@//g'
exit "${PIPESTATUS[0]}"
