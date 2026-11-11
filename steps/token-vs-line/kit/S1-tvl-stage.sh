#!/usr/bin/env bash
# S1-tvl-stage.sh (this host; no AWS call): builds stage/ from src/ (the kit tools: blame_lines.py, measure.py,
# tvl_run.py, tvl_unit.sh, tvl_start.sh, tvl.conf, plan.tsv, test_tvl.py), runs the fixture tests and the
# syntax checks, writes stage/SOURCE and stage/SHA256SUMS, and writes the sha256 of SHA256SUMS as WANT_SUMS into
# U1, R1 and B1. An earlier stage/ is moved aside to stage.old.<time>.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); S=$H/src; ST=$H/stage
PY=${PY:-/nix/store/5gnikzfb2hkysq9d45mjl74h7vj4c5ad-python3-3.14.7-env/bin/python3}
FILES="blame_lines.py measure.py tvl_run.py tvl_unit.sh tvl_start.sh tvl.conf plan.tsv test_tvl.py"
for f in $FILES; do [ -f $S/$f ] || { echo "ABORT: no src/$f"; exit 1; }; done
for f in tvl_unit.sh tvl_start.sh; do bash -n $S/$f; done
(cd $S && $PY -I -m py_compile blame_lines.py measure.py tvl_run.py test_tvl.py)
(cd $S && $PY -I test_tvl.py > $H/test-fixture.txt 2>&1) || { tail -20 $H/test-fixture.txt; echo "ABORT: fixture tests"; exit 1; }
tail -3 $H/test-fixture.txt
[ "$(tail -n +2 $S/plan.tsv | wc -l)" = 250 ] || { echo "ABORT: plan.tsv does not have 250 rows"; exit 1; }
if grep -l @ $S/plan.tsv $S/tvl.conf; then echo "ABORT: an at sign in plan.tsv or tvl.conf"; exit 1; fi
[ -d $ST ] && mv $ST $ST.old.$(date +%s)
mkdir -p $ST
for f in $FILES; do cp $S/$f $ST/$f; done
E=/path/to/work-folder
{
  echo "token-vs-line kit stage, built $(date -u +%FT%TZ) on this host by S1-tvl-stage.sh"
  echo "origin: the scripts of $E/scripts (blame_lines.py, measure.py) changed for the larger run; tvl_*: new"
  echo "plan.tsv: $E/tables/plan-sample-random.tsv, draw_rank 1-250 (seed 20261109, scripts/plan_random.py)"
  echo "release root: $(grep ^ROOT= $S/tvl.conf | cut -d= -f2) (TOM 1.0.0, final revision)"
  echo "tests: $(tail -1 $H/test-fixture.txt) ($(grep -c ' ok$' $H/test-fixture.txt) fixture tests)"
} > $ST/SOURCE
(cd $ST && sha256sum $FILES > SHA256SUMS)
W=$(sha256sum $ST/SHA256SUMS | cut -d' ' -f1)
for f in U1-tvl-upload.sh R1-tvl-setup.sh B1-tvl-run.sh; do
  sed -i "s/^WANT_SUMS=.*/WANT_SUMS=$W/" $H/$f
done
echo "stage: $(wc -l < $ST/SHA256SUMS) files + SOURCE, $(du -sb $ST | cut -f1) B; WANT_SUMS=$W"
