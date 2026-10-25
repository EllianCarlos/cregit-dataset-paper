#!/usr/bin/env bash
# T8-rebalance.sh (this machine): runs R8-rebalance.sh against a fake machine A in a temp folder, with a
# fake systemctl (unit states in files; "start" writes the runner's start line from run.env), a fake git
# (ls-files -z = the files of the fake clone) and fake .blame mtimes (touch -d). Nothing runs on any machine.
# Cases: (a) Retro68 ends; (a2) NO_SHUTDOWN existed before; (b) no row ended; (c) a row past step 7 counts 8;
# (d) every gain below MIN_GAIN; (d2) sharing the free jobs drops a row below MIN_GAIN; (e) DRY_RUN;
# (f) the lock; (g) a start-line check fails; (h) NO_REBALANCE; (i) a row inactive without upload;
# (k) R9 embeds R8. With BIG=1 also (z): the DRY_RUN plan for the numbers of 2026-10-21 (390k fake files).
# Use: bash scripts/a/test/T8-rebalance.sh [> scripts/a/test/T8-rebalance.out]
set -uo pipefail
A=$(cd "$(dirname "$0")/.." && pwd); R8=$A/R8-rebalance.sh; R9=$A/R9-install-rebalance.sh
bash -n "$R8" || { echo "R8 bash -n failed"; exit 1; }
X=$(mktemp -d); trap 'rm -rf "$X"' EXIT
B=$X/bin; mkdir -p "$B"
cat > "$B/systemctl" <<'EOF'
#!/usr/bin/env bash
# fake systemctl: unit states in $FAKE/units/<unit> (default inactive); every call in $FAKE/calls.
echo "$*" >> "$FAKE/calls"
q=0; [ "${2:-}" = -q ] && q=1
u=${!#}
case $1 in
  is-active) s=$(cat "$FAKE/units/$u" 2>/dev/null || echo inactive); [ $q = 1 ] || echo "$s"; [ "$s" = active ] ;;
  stop) echo inactive > "$FAKE/units/$u" ;;
  reset-failed) : ;;
  start) p=${u#x1k-long@}; T=$(readlink -f "$ROOT/$p"); J=$(sed -n 's/^JOBS=//p' "$T/run.env"); fs=7
    [ -e "$FAKE/startfail.$p" ] && fs=1
    echo "=== $(date -u +%FT%TZ) x1k-long $p start on ${RUNNER_EC2_X1K_LONG_A4} (cregit 57551d7, ctp ca113e3, full pipeline): last completed step 6, from-step $fs, removed 0 tmpfile-* and 0 step-10/firm scratch files; blame-jobs $J, memory-limit 64G, retries 2" >> "$T/logs/run.log"
    echo active > "$FAKE/units/$u" ;;
  *) echo "fake systemctl: $1 not known" >&2; exit 1 ;;
esac
EOF
cat > "$B/git" <<'EOF'
#!/usr/bin/env bash
# fake git: "-C DIR ls-files -z" prints the files under DIR, NUL-separated.
d=.
while [ $# -gt 0 ]; do case $1 in -c) shift 2 ;; -C) d=$2; shift 2 ;; ls-files) cd "$d" && find . -type f -printf '%P\0'; exit 0 ;; *) shift ;; esac; done
exit 1
EOF
chmod 755 "$B"/*
N=0; fail=0
iso() { date -u -d "@$1" +%FT%TZ; }
setup() {
  N=$((N + 1)); F=$X/c$N; L=$F/data/x1k-long; mkdir -p "$L" "$F/units" "$F/home" "$F/run"
  : > "$F/calls"; echo ${RUNNER_EC2_X1K_LONG_A4} > "$F/asset"; : > "$L/run.list"; NOW=$(date +%s)
}
# mkrow P JOBS LEFT N2H STEP STATE [K] [JOBS_IN_LOG]: one fake row in /dataK/x1k/P.
# STATE: active, ended (inactive + uploaded) or odd (inactive, no upload). N2H .blame files have mtimes
# in the last 2 h (60 buckets), 20 more are 10 h old. JOBS_IN_LOG is the blame-jobs of the start line.
mkrow() {
  local p=$1 j=$2 left=$3 n2=$4 st=$5 state=$6 K=${7:-1} jl=${8:-$2}
  local T=$F/data$K/x1k/$p; local O=$T/out/$p; local W=$O/$p-cregit n=$(( left + n2 + 20 ))
  mkdir -p "$W/src" "$O/blame/src" "$T/ctp" "$T/logs" "$T/uploaded"
  ln -s "$T" "$L/$p"; echo "$p" >> "$L/run.list"
  printf 'JOBS=%s\nMEM=64G\nRETRIES=2\n' "$j" > "$T/run.env"
  printf '═══\n  Step 6 — Tokenize\n  ✓ completed in 10s\n═══\n  Step %s — Blame\n' "$st" > "$O/pipeline.log"
  cat > "$T/ctp/ledger.jsonl" <<'EOF'
{"project": "x", "step": "start", "manifest_row": {"file_filter": "\\.(rs|java|c|h)$"}}
EOF
  echo "=== $(iso $((NOW - 72000))) x1k-long $p start on ${RUNNER_EC2_X1K_LONG_A4} (cregit 57551d7, ctp ca113e3, full pipeline): last completed step 6, from-step 7, removed 0 tmpfile-* and 0 step-10/firm scratch files; blame-jobs $jl, memory-limit 64G, retries 2" > "$T/logs/run.log"
  (cd "$W/src" && seq 0 $((n - 1)) | sed 's/$/.rs/' | xargs touch)
  touch "$W/README.md" "$W/src/notes.txt" "$O/blame/src/notes.txt.blame"
  local b
  for b in $(seq 0 59); do
    (cd "$O/blame/src" && seq "$b" 60 $((n2 - 1)) | sed 's/$/.rs.blame/' | xargs -r touch -d "@$((NOW - 60 - b * 110))")
  done
  (cd "$O/blame/src" && seq "$n2" $((n2 + 19)) | sed 's/$/.rs.blame/' | xargs touch -d "@$((NOW - 36000))")
  case $state in
    active) echo active > "$F/units/x1k-long@$p" ;;
    ended) echo "uploaded test" > "$T/uploaded/$p" ;;
    odd) : ;;
  esac
  cp -p "$T/run.env" "$T/run.env.orig"
}
run() { PATH=$B:$PATH FAKE=$F ROOT=$L X1K_ASSET=$F/asset X1K_HOME=$F/home X1K_RUN=$F/run POLL=0 SETTLE=0 "$@" bash "$R8" > "$F/out" 2>&1; echo $? > "$F/rc"; }
chk() { if eval "$2"; then echo "  PASS $1"; else echo "  FAIL $1"; fail=1; sed 's/^/    | /' "$F/out"; fi; }
jobs_of() { sed -n 's/^JOBS=//p' "$L/$1/run.env"; }
same() { cmp -s "$L/$1/run.env" "$L/$1/run.env.orig"; }
nbak() { find -L "$L/$1/" -maxdepth 1 -name 'run.env.before-R8-*' | wc -l; }
rust=awslabs__aws-sdk-rust; java=aws__aws-sdk-java; meta=metashell__metashell; retro=autc04__Retro68
# The weights of case (a): rust 120 left x (88 x 7200 / 100) = 760,320 CPU s; metashell 92 x (24 x 7200 / 60)
# = 264,960; java 129 x (44 x 7200 / 200) = 204,336. Free 20: rust + meta share 132 by weight -> 98 and 34.
layout_a() { mkrow $rust 88 120 100 7 active 1; mkrow $java 44 129 200 7 active 2; mkrow $meta 24 92 60 7 active 3; mkrow $retro 20 50 60 7 "${1:-ended}" 4; }

echo "case (a): Retro68 ended -> its 20 jobs to rust and metashell by weight; java not lowered"
setup; layout_a; run
chk "exit 0" "[ \$(cat $F/rc) = 0 ]"
chk "rust 88 -> 98, metashell 24 -> 34" "[ \$(jobs_of $rust) = 98 ] && [ \$(jobs_of $meta) = 34 ]"
chk "java and Retro68 run.env unchanged, no backup" "same $java && same $retro && [ \$(nbak $java) = 0 ] && [ \$(nbak $retro) = 0 ]"
chk "one backup each for rust and metashell (the old JOBS)" "[ \$(nbak $rust) = 1 ] && [ \$(nbak $meta) = 1 ] && grep -q '^JOBS=88$' $L/$rust/run.env.before-R8-*"
chk "stop and start only for rust and metashell" "[ \$(grep -c '^stop ' $F/calls) = 2 ] && grep -q 'stop x1k-long.$rust' $F/calls && grep -q 'stop x1k-long.$meta' $F/calls && [ \$(grep -c '^start ' $F/calls) = 2 ]"
chk "new start lines with blame-jobs 98 and 34" "tail -1 $L/$rust/logs/run.log | grep -q 'blame-jobs 98,' && tail -1 $L/$meta/logs/run.log | grep -q 'blame-jobs 34,'"
chk "NO_SHUTDOWN removed (it did not exist)" "[ ! -e $F/home/NO_SHUTDOWN ] && grep -q 'NO_SHUTDOWN removed' $F/out"
chk "log has the block, no ALERT, no at sign" "grep -q 'R8 rebalance on' $L/rebalance.log && ! grep -q ALERT $L/rebalance.log && ! grep -q '@' $L/rebalance.log $F/out"
sed -n '/^  row/,/R8 done/p' "$F/out" | grep -v -E '^    |memory|git blame' | sed 's/^/    out| /'

echo "case (a2): as (a), NO_SHUTDOWN existed before -> kept"
setup; layout_a; touch "$F/home/NO_SHUTDOWN"; run
chk "changes done, NO_SHUTDOWN kept" "[ \$(jobs_of $rust) = 98 ] && [ -e $F/home/NO_SHUTDOWN ] && grep -q 'NO_SHUTDOWN existed before R8: kept' $F/out"

echo "case (b): no row ended (176 jobs in use) -> no change"
setup; layout_a active; run
chk "exit 0, no stop, all run.env unchanged" "[ \$(cat $F/rc) = 0 ] && ! grep -q '^stop ' $F/calls && same $rust && same $java && same $meta && same $retro"
chk "says the budget is reached" "grep -q 'reach the budget 176: no change' $F/out"

echo "case (c): Retro68 ended, java past step 7 (counts 8) -> free 56 to rust and metashell"
setup; mkrow $rust 88 120 100 7 active 1; mkrow $java 44 129 200 9 active 2; mkrow $meta 24 92 60 7 active 3; mkrow $retro 20 50 60 7 ended 4; run
chk "java counted as 8" "grep -q 'rows past step 7: 1 x 8' $F/out && grep -q 'used 120 of 176, free 56' $F/out"
chk "rust 88 -> 125, metashell 24 -> 43, java unchanged" "[ \$(jobs_of $rust) = 125 ] && [ \$(jobs_of $meta) = 43 ] && same $java && ! grep -q 'stop x1k-long.$java' $F/calls"

echo "case (d): Retro68 past step 7 (free 12), weights near the current JOBS -> every gain below 8, no restart"
setup; mkrow $rust 88 95 100 7 active 1; mkrow $java 44 100 100 7 active 2; mkrow $meta 24 100 100 7 active 3; mkrow $retro 20 50 60 8 active 4; run
chk "no stop, all run.env unchanged" "! grep -q '^stop ' $F/calls && same $rust && same $java && same $meta && same $retro"
chk "says no row gains 8" "grep -q 'no row gains 8 or more: no change' $F/out"

echo "case (d2): Retro68 past step 7 (free 12), the weights of (a) -> rust's share falls below 8, metashell gets the 12"
setup; mkrow $rust 88 120 100 7 active 1; mkrow $java 44 129 200 7 active 2; mkrow $meta 24 92 60 7 active 3; mkrow $retro 20 50 60 8 active 4; run
chk "metashell 24 -> 36, rust and java unchanged" "[ \$(jobs_of $meta) = 36 ] && same $rust && same $java && [ \$(grep -c '^stop ' $F/calls) = 1 ]"

echo "case (e): as (a) with DRY_RUN=1 -> the plan only"
setup; layout_a; run env DRY_RUN=1
chk "the plan says rust 98, metashell 34" "grep -q 'plan: $rust JOBS 88 -> 98' $F/out && grep -q 'plan: $meta JOBS 24 -> 34' $F/out && grep -q 'DRY_RUN: nothing changed' $F/out"
chk "no stop/start, no run.env change, no backup, no NO_SHUTDOWN" "! grep -q -E '^(stop|start) ' $F/calls && same $rust && same $meta && [ \$(nbak $rust) = 0 ] && [ ! -e $F/home/NO_SHUTDOWN ]"

echo "case (f): another run holds the lock -> the second run does nothing"
setup; layout_a; ( flock "$L/rebalance.lock" sleep 4 ) & lp=$!
for _ in $(seq 1 50); do flock -n "$L/rebalance.lock" true || break; sleep 0.1; done
run; wait $lp
chk "says the lock is held, exit 0" "grep -q 'another R8 run holds the lock; nothing done' $F/out && [ \$(cat $F/rc) = 0 ]"
chk "no systemctl call, no run.env change" "[ ! -s $F/calls ] && same $rust && same $meta"
chk "the line is in the log" "grep -q 'holds the lock' $L/rebalance.log"

echo "case (g): the start line of rust is wrong (from-step 1) -> ALERT, NO_SHUTDOWN kept, stop"
setup; layout_a; touch "$F/startfail.$rust"; run
chk "exit 1, ALERT in the log and in rebalance.ALERT" "[ \$(cat $F/rc) = 1 ] && grep -q '^ALERT: $rust: no new start line' $L/rebalance.log && [ -s $L/rebalance.ALERT ]"
chk "NO_SHUTDOWN kept" "[ -e $F/home/NO_SHUTDOWN ] && grep -q 'NO_SHUTDOWN kept' $F/out"
chk "stopped: metashell not touched" "! grep -q 'x1k-long.$meta' <(grep -E '^(stop|start) ' $F/calls) && same $meta && same $java"
: > "$F/calls"; rm -f "$F/startfail.$rust"; run
chk "the next run does nothing while rebalance.ALERT exists" "grep -q 'no action.*rebalance.ALERT exists' $F/out && ! grep -q -E '^(stop|start) ' $F/calls && same $meta"

echo "case (h): NO_REBALANCE exists -> no action"
setup; layout_a; touch "$F/home/NO_REBALANCE"; run
chk "no action, nothing changed" "grep -q 'no action.*NO_REBALANCE exists' $F/out && ! grep -q -E '^(stop|start) ' $F/calls && same $rust && same $meta"
setup; layout_a; touch "$F/run/x1k-spot-interrupted"; run
chk "the same for a spot notice" "grep -q 'no action.*x1k-spot-interrupted exists' $F/out && same $rust"
setup; layout_a; echo activating > "$F/units/x1k-long-finalize.service"; run
chk "the same while the finalize unit runs" "grep -q 'no action; the finalize unit is activating' $F/out && same $rust"

echo "case (i): Retro68 inactive but not uploaded -> no action"
setup; layout_a odd; run
chk "no action, nothing changed" "grep -q 'no action; inactive without upload: $retro' $F/out && ! grep -q '^stop ' $F/calls && same $rust"
setup; layout_a; echo ${RUNNER_EC2_BIG} > "$F/asset"; run
chk "another instance id -> ABORT, no log" "grep -q 'ABORT: ${RUNNER_EC2_BIG} is not machine A' $F/out && [ ! -e $L/rebalance.log ] && [ ! -s $F/calls ]"

echo "case (k): R9 embeds R8 exactly"
sed -n "/^cat > \$S.new <<'EOF_x1k_rebalance'$/,/^EOF_x1k_rebalance$/p" "$R9" | sed '1d;$d' > "$X/r9-r8"
F=$X; echo "" > "$X/out"
chk "embedded text = R8, sha256 in R9 = R8" "cmp -s $X/r9-r8 $R8 && grep -q \"^SUM=\$(sha256sum $R8 | cut -d' ' -f1)\$\" $R9"
chk "no at sign in the echo lines of R9" "! grep -n 'echo.*@' $R9 | grep -v -e \"s/@//g\" -e 'touch -d'"

if [ "${BIG:-0}" = 1 ]; then
  echo "case (z): the numbers of 2026-10-21, Retro68 ended, DRY_RUN=1"
  # rust 230,915 left, 540/h at 64 (start line 64, run.env 88); metashell 36,722 left, 177/h at 20 (now 24);
  # java 122,488 left, 1,424/h at 44; Retro68 82,428 left, 4,512/h at 20, ended.
  setup; mkrow $rust 88 230915 1080 7 active 1 64; mkrow $java 44 122488 2848 7 active 2; mkrow $meta 24 36722 354 7 active 3 20
  mkrow $retro 20 10 60 7 ended 4
  t0=$(date +%s.%N); run env DRY_RUN=1; t1=$(date +%s.%N)
  chk "DRY_RUN: no change" "! grep -q -E '^(stop|start) ' $F/calls && same $rust"
  echo "  R8 took $(awk -v a="$t0" -v b="$t1" 'BEGIN {printf "%.1f", b - a}') s for 390k files"
  sed 's/^/    plan| /' "$F/out"
fi
[ $fail = 0 ] && echo "T8 REBALANCE TEST OK" || { echo "T8 REBALANCE TEST FAILED"; exit 1; }
