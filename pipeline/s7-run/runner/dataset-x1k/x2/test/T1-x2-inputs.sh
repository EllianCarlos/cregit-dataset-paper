#!/usr/bin/env bash
# T1-x2-inputs.sh (local, no AWS): test of the path-fix change of the X2 kit on synthetic files.
# It runs the builder embedded in R2-x2-inputs.sh (and checks that it is the same as
# x2/build_inputs_x1k.py), the cregit.x1k.txt code of R2 and the path-fix guard of M1 (both cut out of
# the scripts, not copied). Synthetic done-full/ and done-pathfix/ copies:
#   good-a (part a), good-b (part b2): done-full only -> x1k-a / x1k-b, cregit 57551d7
#   pf-done: path-fix row with done-full OK and done-pathfix OK -> done-pathfix, cregit 14b8db4
#   pf-new: path-fix row with done-pathfix OK only (as ModelArts-Lab) -> done-pathfix, cregit 14b8db4
#   pf-held: path-fix row with done-full OK only -> HELD, no row
#   pf-none: path-fix row without any OK -> HELD, no row
#   excl: excluded, no OK -> no row;  v1row: done-pathfix OK, not an x1k key -> ignored
# Then the error cases (exit 2, no OUT): an excluded row with an OK, a done-pathfix OK of a row that is
# not in the path-fix list, 14b8db4 for a done-full row, a done-pathfix row without its cregit line,
# a bad done-pathfix OK. Usage: bash x2/test/T1-x2-inputs.sh [PYTHON]  (last line: T1-x2 ALL PASS)
set -euo pipefail
K=$(cd "$(dirname "$0")/.." && pwd); PY=${1:-python3}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fails=0
check() { if eval "$2"; then echo "ok   $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi; }

# --- the code under test, cut out of the scripts
awk "/<<'EOF_py'/{f=1;next} /^EOF_py\$/{f=0} f" "$K/R2-x2-inputs.sh" > "$T/build_inputs_x1k.py"
check "embedded builder = x2/build_inputs_x1k.py" "cmp -s '$T/build_inputs_x1k.py' '$K/build_inputs_x1k.py'"
awk '/^\[ -f \$X\/cregit.x1k.txt \]/{f=1} f; /^echo "cregit.x1k.txt:/{f=0}' "$K/R2-x2-inputs.sh" > "$T/cregit-part.sh"
check "cregit code of R2 found (4 lines)" "[ \$(wc -l < '$T/cregit-part.sh') = 4 ]"
grep '^badpf=' "$K/M1-x2-start.sh" > "$T/guard-part.sh"
check "guard of M1 found" "[ -s '$T/guard-part.sh' ]"
awk "/<<'EOF'\$/ && /pathfix.x1k.txt/{f=1;next} f && /^EOF\$/{f=0} f" "$K/R2-x2-inputs.sh" > "$T/pathfix.r2.txt"
PARTS=$HOME/s3-work/dataset-pathfix/stage/inputs/parts.tsv
if [ -f "$PARTS" ]; then
  check "R2 path-fix list = part 2 of the staged parts.tsv (18)" \
    "[ \"\$(grep -v '^#' '$T/pathfix.r2.txt' | sort)\" = \"\$(awk -F'\t' 'NR>1 && \$2==2 {print \$1}' '$PARTS' | sort)\" ] && [ \$(grep -vc '^#' '$T/pathfix.r2.txt') = 18 ]"
fi

# --- synthetic files
mk() {  # mk DIR PROJECT PART ROWS BYTES SHA_CHAR [STAMP_BYTES]
  local d=$1/$2; mkdir -p "$d"
  printf 'uploaded 2026-10-20T20:00:00Z from i-0000000000000000 part %s\nparquet_sha256 %s\n%s\t%s-dataset.parquet\n10\t%s.validated\n' \
    "$3" "$(printf "%064d" 0 | tr 0 "$6")" "$5" "$2" "$2" > "$d/OK"
  printf 'rows=%s bytes=%s\n' "$4" "${7:-$5}" > "$d/$2.validated"
}
X=$T/x2; M=$X/meta; PM=$X/meta-pathfix; mkdir -p $M $PM
mk $M good-a a 100 1000 a; mk $M good-b b2 200 2000 b
mk $M pf-done b1 300 3000 c; mk $M pf-held b1 400 4000 d
mk $PM pf-done p2 310 3100 e; mk $PM pf-new p2 500 5000 f; mk $PM v1row p1 600 6000 0
printf '{"good-a":{},"good-b":{},"pf-done":{},"pf-new":{},"pf-held":{},"pf-none":{},"excl":{}}\n' > $X/sidecar.json
printf '# synthetic exclusions\nexcl\n' > $X/exclude.x1k.txt
printf '# synthetic path-fix list\npf-done\npf-new\npf-held\npf-none\n' > $X/pathfix.x1k.txt
want=$(grep -v '^#' $X/pathfix.x1k.txt | sort); PF_CREGIT=14b8db4
(set -euo pipefail; X=$X PM=$PM want=$want PF_CREGIT=$PF_CREGIT; source "$T/cregit-part.sh") > $T/cregit.out
check "cregit.x1k.txt = pf-done, pf-new with 14b8db4" \
  "[ \"\$(grep -v '^#' $X/cregit.x1k.txt)\" = \"\$(printf 'pf-done 14b8db4\npf-new 14b8db4')\" ]"
check "R2 prints 2 rows with cregit 14b8db4" "grep -q 'cregit.x1k.txt: 2 rows with cregit 14b8db4' $T/cregit.out"

run() {  # run OUTNAME [extra args]: the builder with the R2 arguments
  local o=$1; shift
  "$PY" -I "$T/build_inputs_x1k.py" $M $X/sidecar.json $X/$o --exclude $X/exclude.x1k.txt --cregit $X/cregit.x1k.txt \
    --pathfix-meta $PM --pathfix-list $X/pathfix.x1k.txt --held $X/held.x1k.txt "$@"
}
rc=0; run inputs.x1k.tsv > $T/good.out 2> $T/good.err || rc=$?
cat $T/good.out
check "good run: rc 0" "[ $rc = 0 ]"
I=$X/inputs.x1k.tsv
row() { awk -F'\t' -v p="$1" '$1 == p {print $2, $3, $4, $5, $6, substr($7, 1, 1)}' $I; }
check "4 rows" "[ \$(tail -n +2 $I | wc -l) = 4 ]"
check "good-a: x1k-a 57551d7 done-full" "[ \"\$(row good-a)\" = 'x1k-a 57551d7 100 1000 dataset-x1k/done-full/good-a/good-a-dataset.parquet a' ]"
check "good-b: x1k-b 57551d7 done-full" "[ \"\$(row good-b)\" = 'x1k-b 57551d7 200 2000 dataset-x1k/done-full/good-b/good-b-dataset.parquet b' ]"
check "pf-done: done-pathfix wins, 14b8db4, its rows/bytes/sha" "[ \"\$(row pf-done)\" = 'x1k-pathfix 14b8db4 310 3100 dataset-x1k/done-pathfix/pf-done/pf-done-dataset.parquet e' ]"
check "pf-new: done-pathfix only, 14b8db4" "[ \"\$(row pf-new)\" = 'x1k-pathfix 14b8db4 500 5000 dataset-x1k/done-pathfix/pf-new/pf-new-dataset.parquet f' ]"
check "pf-held, pf-none, excl, v1row: no row" "! grep -qE '^(pf-held|pf-none|excl|v1row)\s' $I"
check "held.x1k.txt = pf-held (done-full OK not used), pf-none (no OK)" \
  "[ \"\$(grep -v '^#' $X/held.x1k.txt)\" = \"\$(printf 'pf-held\tdone-full OK not used\npf-none\tno OK')\" ]"
check "stdout: HELD: 2 rows and both names" "grep -q '^HELD: 2 rows' $T/good.out && grep -q '  pf-held' $T/good.out && grep -q '  pf-none' $T/good.out"
check "stdout: 2 of 4 from done-pathfix, 1 ignored (v1)" "grep -q 'path-fix: 2 of 4 x1k rows from done-pathfix (cregit 14b8db4); 1 done-pathfix OK' $T/good.out"
(set -uo pipefail; X=$X; source "$T/guard-part.sh"; [ -z "$badpf" ]) && g=0 || g=1
check "M1 guard: passes on the good inputs" "[ $g = 0 ]"
cp -p $I $I.good
sed -i 's#dataset-x1k/done-pathfix/pf-done/#dataset-x1k/done-full/pf-done/#' $I
(set -uo pipefail; X=$X; source "$T/guard-part.sh"; [ "$badpf" = pf-done ]) && g=0 || g=1
check "M1 guard: stops a done-full key of a path-fix row" "[ $g = 0 ]"
cp -p $I.good $I; sed -i 's#^\(pf-new\tx1k-pathfix\t\)14b8db4#\157551d7#' $I
(set -uo pipefail; X=$X; source "$T/guard-part.sh"; [ "$badpf" = pf-new ]) && g=0 || g=1
check "M1 guard: stops cregit 57551d7 of a path-fix row" "[ $g = 0 ]"

# --- error cases: exit 2 and no OUT
bad() {  # bad NAME MESSAGE: run to bad.tsv, expect rc 2, no bad.tsv, MESSAGE in stderr
  rm -f $X/bad.tsv; local rc=0; run bad.tsv > $T/bad.out 2> $T/bad.err || rc=$?
  check "error: $1" "[ $rc = 2 ] && [ ! -e $X/bad.tsv ] && grep -q '$2' $T/bad.err"
}
mk $M excl b1 1 10 9; bad "excluded row with an OK" "excl: in the exclusion list but has an OK"; rm -r $M/excl
mk $PM good-b p2 1 10 9; bad "done-pathfix OK of a row not in the list" "good-b (done-pathfix): done-pathfix OK, but not in the path-fix list"; rm -r $PM/good-b
cp -p $X/cregit.x1k.txt $X/cregit.keep; echo "good-b 14b8db4" >> $X/cregit.x1k.txt
bad "14b8db4 for a done-full row" "good-b: cregit file gives 14b8db4, but the row is from done-full"; cp -p $X/cregit.keep $X/cregit.x1k.txt
grep -v '^pf-new ' $X/cregit.keep > $X/cregit.x1k.txt
bad "done-pathfix row without its cregit line" "pf-new (done-pathfix): cregit file gives None, not 14b8db4"; cp -p $X/cregit.keep $X/cregit.x1k.txt
mk $PM pf-new p2 500 5000 f 4999; bad "bad done-pathfix OK (stamp bytes)" "pf-new (done-pathfix): stamp bytes 4999"; mk $PM pf-new p2 500 5000 f
echo "excl" >> $X/pathfix.x1k.txt; bad "path-fix row in the exclusion list" "excl: path-fix row is in the exclusion list"; sed -i '/^excl$/d' $X/pathfix.x1k.txt
rc=0; run inputs.again.tsv > /dev/null 2>&1 || rc=$?
check "after the error cases: same inputs again" "[ $rc = 0 ] && cmp -s $X/inputs.again.tsv $I.good"

# --- the old call (no path-fix options) still works
rc=0; "$PY" -I "$T/build_inputs_x1k.py" $M $X/sidecar.json $X/old.tsv --exclude $X/exclude.x1k.txt > /dev/null 2>&1 || rc=$?
check "old call: rc 0, 4 done-full rows, 57551d7" "[ $rc = 0 ] && [ \$(tail -n +2 $X/old.tsv | cut -f3 | sort -u) = 57551d7 ] && [ \$(tail -n +2 $X/old.tsv | wc -l) = 4 ]"

[ $fails = 0 ] && echo "T1-x2 ALL PASS ($("$PY" --version))" || { echo "T1-x2 FAILED: $fails"; exit 1; }
