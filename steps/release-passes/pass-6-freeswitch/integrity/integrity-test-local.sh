#!/usr/bin/env bash
# integrity-test-local.sh (this host, no AWS): the local test of integrity_check.py.
#   part 1: tiny TOM-form roots of test/integrity_fixtures.py: the good root must pass; each bad copy must fail with
#           the expected column set to "no" in integrity.tsv.
#   part 2: the real files of the last local rehearsal root (3 project files, 41.6 M rows, the real dataset.duckdb
#           and its 16 views): must pass. It gives the decode speed.
# PY: the venv with pyarrow 26.0.1 and DuckDB 1.5.5 (the versions of the machine). Output: test/integrity-work.<utc>/
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd)
PY=${PY:-$HOME/s3-work/dataset-reencode/.venv/bin/python}
W=$H/test/integrity-work.$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$W"
CK="$PY -I -B $H/integrity_check.py check"
$PY -I -c "import pyarrow, duckdb; print('pyarrow', pyarrow.__version__, 'duckdb', duckdb.__version__)"
fails=0
expect() {  # case rc_want "column=value file" ...
  local c=$1 want=$2; shift 2
  $CK --root "$W/fix/$c" --out "$W/out/$c" --jobs 4 --progress 3600 > "$W/out.$c.txt" 2>&1; local rc=$?
  local ok=1
  [ "$rc" = "$want" ] || ok=0
  for e in "$@"; do
    local col=${e%%=*} rest=${e#*=}; local val=${rest%% *} file=${rest#* }
    local got
    got=$(awk -F'\t' -v c="$col" -v f="$file" 'NR==1 {for (i=1;i<=NF;i++) if ($i==c) k=i; next} $1==f {print $k}' "$W/out/$c/integrity.tsv")
    [ "$got" = "$val" ] || { ok=0; echo "  $c: $file $col is '$got', want '$val'"; }
  done
  local line; line=$(grep '^integrity:' "$W/out.$c.txt" | tail -1)
  if [ $ok = 1 ]; then echo "ok   $c (rc $rc): ${line:0:150}"; else echo "FAIL $c (rc $rc, want $want): ${line:0:150}"; fails=$((fails + 1)); fi
  grep '^PROBLEM' "$W/out.$c.txt" | head -3 | cut -c1-220 | sed 's/^/       /'
}

echo "== part 1: tiny roots"
$PY -I -B "$H/test/integrity_fixtures.py" "$W/fix" > "$W/fixtures.txt" || { echo "FAIL: fixtures"; exit 1; }
mkdir -p "$W/out"
expect good 0
expect flip 1 "sha256_ok=no parquet/acme__alpha-dataset.parquet"
expect flip-crc 1 "sha256_ok=yes parquet/acme__beta-dataset.parquet" "decode_ok=no parquet/acme__beta-dataset.parquet"
expect flip-nocrc 1 "sha256_ok=yes parquet/git.savannah.gnu.org__gamma-dataset.parquet" "decode_ok=no parquet/git.savannah.gnu.org__gamma-dataset.parquet"
expect truncated 1 "sha256_ok=no parquet/acme__beta-dataset.parquet" "footer_ok=no parquet/acme__beta-dataset.parquet"
expect schema 1 "sha256_ok=yes parquet/acme__alpha-dataset.parquet" "schema_ok=no parquet/acme__alpha-dataset.parquet"
expect extra 1 "sha256_ok=no docs/README.md"
echo "   page_crc of the good root: $(cut -f13 "$W/out/good/integrity.tsv" | tail -n +2 | sort | uniq -c | paste -sd' ')"

echo "== part 2: the real files of the rehearsal root"
X1=$(ls -d "$H"/test/work.*/x1 | tail -1)
RR=$W/real/root
mkdir -p "$RR"
cp -al "$X1/root/." "$RR/"
L=$HOME/s3-work/dataset-tom-4/test/tom3-root/parquet/libexpat__libexpat-dataset.parquet
ln "$L" "$RR/parquet/" 2>/dev/null || cp "$L" "$RR/parquet/"
G=$HOME/s3-work/dataset-tom-4/test/tom3-root/parquet/git.savannah.gnu.org__gnubg-dataset.parquet
[ -e "$RR/parquet/git.savannah.gnu.org__gnubg-dataset.parquet" ] || { ln "$G" "$RR/parquet/" 2>/dev/null || cp "$G" "$RR/parquet/"; }
$CK --root "$RR" --out "$W/real/out" --ref parquet/libexpat__libexpat-dataset.parquet --expect-files 3 --jobs 4 \
  --tmp "$W/real/duckdb-tmp" --progress 3600 > "$W/real.txt" 2>&1; rc=$?
grep -E '^integrity:|^PROBLEM|view ' "$W/real.txt" | cut -c1-200
cut -f1,3,7,9,12,13,14 "$W/real/out/integrity.tsv" | grep -E 'path|parquet/'
[ "$rc" = 0 ] && echo "ok   real (rc 0)" || { echo "FAIL real (rc $rc)"; fails=$((fails + 1)); }
echo "integrity-test-local: $([ $fails = 0 ] && echo "all cases as expected" || echo "$fails cases FAILED"); output $W"
exit $fails
