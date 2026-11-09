#!/bin/bash
# re-encode and check one file at a time took hours on machine A; run them in parallel (REENCODE_JOBS 16, CHECK_JOBS 8).
# Patches ta_run.sh and its SHA256SUMS line, writes /data/ta/sums.patched. Stops ta-run first (it re-encodes again from the start).
set -euo pipefail
T=/data/ta/tools; f=$T/ta_run.sh
systemctl is-active --quiet ta-run && { systemctl stop ta-run; sleep 3; }
pkill -f reencode_parquet.py || true
cat > /tmp/patch_par.py <<'PYEOF'
import sys
p = sys.argv[1]; s = open(p).read()
if "REENCODE_JOBS" in s:
    print("already patched"); sys.exit(0)
old_r = """  for n in $(done1); do
    reencode $X/final53/$n-dataset.parquet $X/files/$n-dataset.parquet $R/reencode-$n.json || bad="$bad $n"
    echo "$n: $(sha256sum $X/files/$n-dataset.parquet 2>/dev/null | cut -c1-16)" >> $R/reencode.txt
  done
"""
new_r = """  rj() { install -d -o ec2-user -g ec2-user $X/reencode-tmp/$1
    $AS $PY -I -B $T/reencode_parquet.py one $X/final53/$1-dataset.parquet $X/files/$1-dataset.parquet --config $T/reencode.json \\
      --result $R/reencode-$1.json --pyarrow-version $PYARROW --duckdb-version $DUCKDB --tmp $X/reencode-tmp/$1 --threads 4 \\
      > /dev/null 2>&1 || echo $1 >> $X/reencode-bad.txt; }
  : > $X/reencode-bad.txt
  for n in $(done1); do while [ $(jobs -rp | wc -l) -ge ${REENCODE_JOBS:-16} ]; do wait -n; done; rj $n & done; wait
  for n in $(done1); do echo "$n: $(sha256sum $X/files/$n-dataset.parquet 2>/dev/null | cut -c1-16)" >> $R/reencode.txt; done
  bad=$(tr '\\n' ' ' < $X/reencode-bad.txt | sed 's/ *$//'); [ -z "$bad" ] || bad=" $bad"
"""
old_c = """  for n in $(done1); do
    f=$X/final53/$n-dataset.parquet
    $AS $PY -I $T/compare_tom.py $f $P/pass1/$n.parquet --json $X/cmp-$n.json > /dev/null 2>&1
    $PY -I $T/ta_tools.py judge-pass $X/cmp-$n.json > $X/judge-$n.txt 2>&1 || bad=$((bad + 1))
    $AS env PATH=$X/venv/bin:/usr/bin:/bin python3 -I $C/ctp/validate.py $X/files/$n-dataset.parquet $X/validated-$n.stamp \\
      > $X/validate-$n.txt 2>&1 || { bad=$((bad + 1)); echo "$n: validate.py FAIL" >> $R/checks.txt; }
    echo "$n: $(tail -1 $X/judge-$n.txt)" >> $R/checks.txt
  done
"""
new_c = """  ck() { local n=$1 f=$X/final53/$1-dataset.parquet
    $AS $PY -I $T/compare_tom.py $f $P/pass1/$n.parquet --json $X/cmp-$n.json > /dev/null 2>&1
    $PY -I $T/ta_tools.py judge-pass $X/cmp-$n.json > $X/judge-$n.txt 2>&1 || echo "$n judge" >> $X/check-bad.txt
    $AS env PATH=$X/venv/bin:/usr/bin:/bin python3 -I $C/ctp/validate.py $X/files/$n-dataset.parquet $X/validated-$n.stamp \\
      > $X/validate-$n.txt 2>&1 || { echo "$n validate" >> $X/check-bad.txt; echo "$n: validate.py FAIL" >> $R/checks.txt; }
    echo "$n: $(tail -1 $X/judge-$n.txt)" >> $R/checks.txt; }
  : > $X/check-bad.txt
  for n in $(done1); do while [ $(jobs -rp | wc -l) -ge ${CHECK_JOBS:-8} ]; do wait -n; done; ck $n & done; wait
  bad=$(wc -l < $X/check-bad.txt)
"""
assert s.count(old_r) == 1 and s.count(old_c) == 1, "blocks not found"
s = s.replace(old_r, new_r).replace(old_c, new_c)
open(p, "w").write(s); print("patched")
PYEOF
python3 -I /tmp/patch_par.py $f
bash -n $f && echo "syntax ok"
new=$(sha256sum $f | cut -d' ' -f1); sed -i "s|^[0-9a-f]\{64\}  ta_run.sh$|$new  ta_run.sh|" $T/SHA256SUMS
(cd $T && sha256sum --quiet -c SHA256SUMS) && echo "sums ok"
sha256sum $T/SHA256SUMS | cut -d' ' -f1 > /data/ta/sums.patched; cut -c1-12 /data/ta/sums.patched
ls /data/ta/status | tr '\n' ' '; echo; echo "ta-run: $(systemctl is-active ta-run)"; ls -f /data/ta/SALT* /data/ta/secret/ 2>/dev/null | head -3
