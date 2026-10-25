#!/usr/bin/env bash
# resume-test.sh (dev machine; run it in the background with systemd-run --user): the local resume
# test of machine A before the launch, for the FULL v1 pipeline (user decision 2026-10-19: the x1k
# rows join the dataset; firm step, validate and join, no --no-firm). Tools as on A: ctp ca113e3
# (the v1 code, clean clone of feat/e2e-runner) and a copy of the cregit tree of the 57551d7 gate
# (gate-blamelimit/l1f/cregit, which gave libexpat 14eb5d72 with the same ctp and flags).
# The run script is x1k-long-run, cut out of scripts/a/R3-install.sh (the same text as on A).
#   1. tree "clean": one uninterrupted run of libexpat (the R2 gate flags + --retries 10 --disk-floor-gb 50).
#   2. tree "resume": run 1 is killed with SIGKILL (all processes of the unit, as a reclaim) in step 7
#      after KILL_AT .blame files; run 2 is x1k-long-run again (it must choose --from-step 7).
#   3. tree "post": run 1 is killed just after the "✓ completed" line of step 10 (the runner ends,
#      the firm step starts); run 2 must choose --from-step 11 (firm, validate, schema, join only).
#   4. compare: the 3 Parquets must have the sha256 of the gate Parquet 14eb5d72 (byte for byte),
#      and 0 differing rows against it (DuckDB EXCEPT ALL both ways).
set -uo pipefail
X=${X:-${RUNNER_HOME}/Projects/cregit-workspace/x1k-resume-test}
G=${RUNNER_HOME}/Projects/cregit-workspace/gate-blamelimit/l1f
S=${RUNNER_HOME}/s3-work/dataset-x1k
REPO=${RUNNER_HOME}/Projects/cregit-token-pipeline
P=libexpat__libexpat
GATE_PQ=$G/out/$P/$P-dataset.parquet
WANT_PQ=14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
KILL_AT=${KILL_AT:-15}
say() { echo "[$(date -u +%FT%TZ)] $*"; }
[ -e $X ] && { mv $X $X.old.$(date +%s); }
mkdir -p $X
sed -n "/<<'EOF_x1k_long_run'/,/^EOF_x1k_long_run/p" $S/scripts/a/R3-install.sh | sed '1d;$d' > $X/x1k-long-run
chmod 755 $X/x1k-long-run; bash -n $X/x1k-long-run || exit 1
say "run script: $(sha256sum $X/x1k-long-run | cut -c1-16) ($(wc -l < $X/x1k-long-run) lines, from R3-install.sh)"
[ "$(sha256sum $GATE_PQ | cut -d' ' -f1)" = $WANT_PQ ] || { say "ABORT: gate Parquet is not 14eb5d72"; exit 1; }
[ "$(git -C $G/cregit rev-parse HEAD)" = 57551d7ad82a784615c1490623d72cb9dc994ba1 ] || { say "ABORT: gate cregit is not 57551d7"; exit 1; }
tree() {  # tree NAME: the layout of R1 (machine A) for one project
  local T=$X/$1
  mkdir -p $T/logs $T/out $T/uploaded
  git clone -q $REPO $T/ctp -b feat/e2e-runner
  [ "$(git -C $T/ctp rev-parse --short HEAD)" = ca113e3 ] || { say "ABORT: clone HEAD is not ca113e3"; exit 1; }
  ln -s $G/ctp-check/.venv $T/ctp/.venv
  mkdir -p $T/.cc
  tar -C $G -cf - --exclude='cregit/tokenizeByBlobId/build' --exclude='cregit/blameRepo/build' cregit | tar -C $T/.cc -xpf -
  mv $T/.cc/cregit $T/cregit-ec2; rmdir $T/.cc; mkdir -p $T/cregit-ec2/tokenizeByBlobId/build $T/cregit-ec2/blameRepo/build
  printf '# resume test %s\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' $1 $T/cregit-ec2 $T/out > $T/ctp.cfg
  cp $G/manifest.libexpat.tsv $T/manifest.tsv
  printf 'JOBS=2\nMEM=2GB\nMINFREE=10\nDISKFLOOR=50\nRETRIES=10\nMETA=%s\nLATEST=\n' $G/project_meta.batch1.json > $T/run.env
  say "tree $1: ctp $(git -C $T/ctp rev-parse --short HEAD) clean=$([ -z "$(git -C $T/ctp status --porcelain --untracked-files=no)" ] && echo yes), cregit $(git -C $T/cregit-ec2 rev-parse --short HEAD), same fs out/blameRepo: $([ "$(stat -c %d $T/out)" = "$(stat -c %d $T/cregit-ec2/blameRepo/build)" ] && echo yes)"
}
start() {  # start TREE UNIT
  systemd-run --user --quiet --unit=$2 --collect -E X1K_TREE=$X/$1 -E PATH="$PATH" -E HOME="$HOME" \
    -p StandardOutput=append:$X/$1/logs/run.log -p StandardError=append:$X/$1/logs/run.log \
    $X/x1k-long-run $P
}
waitu() { while systemctl --user is-active -q $1; do sleep 2; done; }
pq() { sha256sum $X/$1/out/$P/$P-dataset.parquet 2>/dev/null | cut -d' ' -f1; }
report() {  # report TREE
  local T=$X/$1
  grep -a '=== .* x1k-long' $T/logs/run.log | sed 's/^/    run.log: /'
  say "$1: $(grep -a 'census finished' $T/logs/run.log | tail -1); Parquet $(pq $1)"
  for f in $T/ctp/state/$P/logs/pipeline-2*.log; do echo "    $(basename $f): steps $(grep '^  Step ' $f | awk '{print $2}' | tr '\n' ' ')"; done
  say "$1: step-7 counts: $(grep -h 'Newly processed' $T/ctp/state/$P/logs/pipeline-*.log | tr '\n' ' ')"
  say "$1: phase logs: $(cd $T/ctp/state/$P/logs && command ls | grep -v latest | sed 's/-2026.*//' | sort | uniq -c | tr -s ' ' | tr '\n' ',')"
  say "$1: tmpfile-* $(find $T/cregit-ec2/blameRepo/build -maxdepth 1 -name 'tmpfile-*' | wc -l); PLAIN-BLAME $(cat $T/ctp/state/$P/logs/pipeline-*.log | grep -c '^PLAIN-BLAME'); stamp: $(head -c 300 $T/out/$P/$P.validated | tr '\n' ' ')"
  say "$1: ledger: $(python3 - $T/ctp/ledger.jsonl <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
print("; ".join(f"a{r.get('attempt')} {r.get('step')} {r.get('event', r.get('state', ''))}" for r in rows))
PY
)"
  say "$1: ctp still clean ca113e3: $([ "$(git -C $T/ctp rev-parse --short HEAD)" = ca113e3 ] && [ -z "$(git -C $T/ctp status --porcelain --untracked-files=no)" ] && echo yes || echo NO)"
}
tree clean; tree resume; tree post
say "1. clean run"; start clean x1k-rt-clean; waitu x1k-rt-clean; report clean
say "2. resume: run 1, killed in step 7 at >= $KILL_AT .blame files"
start resume x1k-rt-resume1
W=$X/resume/out/$P; killed=0
while systemctl --user is-active -q x1k-rt-resume1; do
  if grep -q '^  Step 7 ' $W/pipeline.log 2>/dev/null && ! grep -q 'Newly processed' $W/pipeline.log; then
    n=$(find $W/blame -name '*.blame' 2>/dev/null | wc -l)
    if [ $n -ge $KILL_AT ]; then systemctl --user kill -s SIGKILL x1k-rt-resume1; killed=1; say "SIGKILL to every process of x1k-rt-resume1 at $n .blame files"; break; fi
  fi
  sleep 0.2
done
waitu x1k-rt-resume1
[ $killed = 1 ] || { say "TEST INVALID: resume run 1 ended before the kill"; exit 1; }
say "after the kill: $(find $W/blame -name '*.blame' | wc -l) .blame, $(find $X/resume/cregit-ec2/blameRepo/build -maxdepth 1 -name 'tmpfile-*' | wc -l) tmpfile-*, Parquet files $(command ls $W/*.parquet 2>/dev/null | wc -l)"
say "2. resume: run 2"; start resume x1k-rt-resume2; waitu x1k-rt-resume2; report resume
say "3. post: run 1, killed just after step 10 completed"
start post x1k-rt-post1
W=$X/post/out/$P; killed=0
while systemctl --user is-active -q x1k-rt-post1; do
  if [ -f $W/pipeline.log ] && awk 'index(prev, "═══") == 1 && /^  Step 10 / { on = 1 } on && index($0, "  ✓ completed in ") == 1 { f = 1 } { prev = $0 } END { exit !f }' $W/pipeline.log; then
    systemctl --user kill -s SIGKILL x1k-rt-post1; killed=1; say "SIGKILL to every process of x1k-rt-post1 after step 10 completed"; break
  fi
  sleep 0.1
done
waitu x1k-rt-post1
[ $killed = 1 ] || { say "TEST INVALID: post run 1 ended before the kill"; exit 1; }
say "after the kill: ledger tail $(tail -1 $X/post/ctp/ledger.jsonl | cut -c1-200); stamp $([ -f $W/$P.validated ] && echo yes || echo no); Parquet columns $($G/ctp-check/.venv/bin/python -c 'import duckdb,sys; print(len(duckdb.sql(f"describe select * from read_parquet(\"{sys.argv[1]}\")").fetchall()))' $W/$P-dataset.parquet 2>/dev/null); firm leftovers $(command ls -a $W | grep -c -e firm-tmp -e firm-spill)"
say "3. post: run 2"; start post x1k-rt-post2; waitu x1k-rt-post2; report post
$G/ctp-check/.venv/bin/python - $X/clean/out/$P/$P-dataset.parquet $X/resume/out/$P/$P-dataset.parquet $X/post/out/$P/$P-dataset.parquet $GATE_PQ <<'PY'
import duckdb, sys
c, r, q, g = sys.argv[1:5]
con = duckdb.connect()
def n(p): return con.execute("select count(*) from read_parquet(?)", [p]).fetchone()[0]
def cols(p): return len(con.execute("describe select * from read_parquet(?)", [p]).fetchall())
A = "select * from read_parquet(?)"
def diff(x, y):
    return (con.execute(f"select count(*) from ({A} except all {A})", [x, y]).fetchone()[0],
            con.execute(f"select count(*) from ({A} except all {A})", [y, x]).fetchone()[0])
print(f"rows clean {n(c)} resume {n(r)} post {n(q)} gate {n(g)}; columns {cols(c)} {cols(r)} {cols(q)} {cols(g)}")
d = {k: diff(v, g) for k, v in (("clean", c), ("resume", r), ("post", q))}
print(f"differing rows against the gate: {d}")
print("ROWS OK" if all(v == (0, 0) for v in d.values()) and n(c) == n(r) == n(q) == n(g) else "ROWS FAILED")
PY
ok=1
for t in clean resume post; do s=$(pq $t); say "$t Parquet $s $([ "$s" = $WANT_PQ ] && echo '= gate 14eb5d72' || { ok=0; echo 'DIFFERS from the gate'; })"; done
[ $ok = 1 ] && say "RESUME TEST OK (full pipeline): clean, resumed-at-7 and resumed-at-11 Parquets = the gate Parquet 14eb5d72 byte for byte" || say "RESUME TEST FAILED"
