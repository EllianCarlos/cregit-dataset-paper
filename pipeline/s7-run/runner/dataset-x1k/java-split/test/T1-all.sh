#!/usr/bin/env bash
# T1-all.sh (this machine): all checks of the java-split kit, with fakes (no AWS call, no machine).
#   1. render.sh --check (the ssm scripts hold the current lib files);
#   2. bash -n of every script, perl -c of the Perl files, py_compile of the Python files;
#   3. shellcheck -S warning (nix shell nixpkgs#shellcheck);
#   4. test/t_jv.py: the order (against the real blameRepoFiles.pl of 57551d7), the split, the A
#      position, the driver, the real formatBlame.pl bytes, the gate compare, the batches, the pull
#      rule (no overwrite, temp + link, only complete batches), the end rule, jv-pull with fakes;
#   5. test/t_extra.py: jv-run + jv-upload end to end (gate, blame, batches, DONE, resume, STOP,
#      the meeting with A, a failed gate), then the pull on the A side;
#   6. test/t_e1s1.py: the rendered E1 (fake /proc of the running step 7) and S1 end to end, then
#      jv-run as S1 installed it and the pull: the pulled files equal blameRepoFiles.pl output;
#   7. test/t_kits.py: the names of this kit and of ../rust-split do not collide; both pulls on one
#      fake machine A restart only their own row, and never at the same time (rebalance.lock);
#   8. test/t_l1.py: L1 with a fake aws: on-demand request, DRY_RUN, quota, refuse list, names;
#   9. only with AWS_DRY=1: the real EC2 DryRun of L1 for part 1 (a read-only AWS call).
# PY=<python> runs the Python parts with that interpreter (machine A has 3.9).
set -uo pipefail
H=$(cd "$(dirname "$0")/.." && pwd)
cd "$H" || exit 1
fail=0
PY=${PY:-python3}
step() { echo "--- $*"; }
step "render --check"; bash render.sh --check || fail=1
step "bash -n"
for f in ./*.sh lib/*.sh test/*.sh; do bash -n "$f" || { echo "bash -n failed: $f"; fail=1; }; done
step "perl -c"
for f in lib/*.pl; do perl -c "$f" 2>&1 | grep -q 'syntax OK' || { echo "perl -c failed: $f"; fail=1; }; done
step "python compile"
for f in lib/*.py test/*.py; do python3 -I -c 'import sys; compile(open(sys.argv[1]).read(), sys.argv[1], "exec")' "$f" || { echo "compile failed: $f"; fail=1; }; done
step "shellcheck -S warning"
if nix shell nixpkgs#shellcheck -c shellcheck -x -S warning ./*.sh lib/*.sh test/*.sh src/*.body; then echo "shellcheck: no warning"; else fail=1; fi
for t in t_jv t_extra t_e1s1 t_kits t_l1; do
  step "$t.py ($($PY --version))"
  if "$PY" -I -W ignore::ResourceWarning "test/$t.py" > "/tmp/jv-$t.out" 2>&1 && tail -1 "/tmp/jv-$t.out" | grep -q '^OK'; then
    echo "$t.py: $(grep '^Ran ' "/tmp/jv-$t.out"), OK"
  else tail -30 "/tmp/jv-$t.out"; fail=1; fi
  rm -f "/tmp/jv-$t.out"
done
if [ "${AWS_DRY:-0}" = 1 ]; then
  step "L1 EC2 DryRun (on-demand, part 1)"
  if KS=1 DRY_RUN=1 bash L1-launch-jv.sh 2>&1 | sed 's/@//g' | tee /tmp/jv-l1dry.out | grep -q 'Request would have succeeded'; then
    echo "L1 DryRun: Request would have succeeded"
  else tail -5 /tmp/jv-l1dry.out; fail=1; fi
  rm -f /tmp/jv-l1dry.out
fi
[ $fail = 0 ] && echo "T1 ALL PASS" || echo "T1 FAILED"
exit $fail
