#!/bin/bash
# pass 2 write: DuckDB in parallel threads of one process segfaults; move the base49 COPY into a subprocess.
# Patches ta_tools.py and its SHA256SUMS line, writes /data/ta/sums.patched, then resets pass 2 (moves the old outputs aside).
set -euo pipefail
T=/data/ta/tools; f=$T/ta_tools.py
systemctl is-active --quiet ta-run && { systemctl stop ta-run; sleep 2; }
cat > /tmp/patch_write.py <<'PYEOF'
import sys
p = sys.argv[1]
s = open(p).read()
old = """        con = duckdb.connect()
        con.execute(f"SET memory_limit = '{a.memory_limit}'")
        con.execute(f"COPY (SELECT * EXCLUDE ({', '.join(sorted(ORG))}) FROM read_parquet(?)) TO '{base}' "
                    f"(FORMAT PARQUET, COMPRESSION ZSTD)", [str(src)])
        con.close()
"""
new = """        q = subprocess.run([sys.executable, "-I", "-c",
                            "import duckdb, sys; c = duckdb.connect(); c.execute(sys.argv[1]); c.execute(sys.argv[2], [sys.argv[3]])",
                            f"SET memory_limit = '{a.memory_limit}'",
                            f"COPY (SELECT * EXCLUDE ({', '.join(sorted(ORG))}) FROM read_parquet(?)) TO '{base}' "
                            f"(FORMAT PARQUET, COMPRESSION ZSTD)", str(src)], capture_output=True, text=True)
        if q.returncode:
            raise RuntimeError(f"base49 copy rc={q.returncode}: {q.stderr[-300:]}")
"""
if new in s:
    print("already patched"); sys.exit(0)
assert s.count(old) == 1, "block not found"
open(p, "w").write(s.replace(old, new))
print("patched")
PYEOF
/data/ta/venv/bin/python -I /tmp/patch_write.py $f
/data/ta/venv/bin/python -I -m py_compile $f
new=$(sha256sum $f | cut -d' ' -f1); sed -i "s|^[0-9a-f]\{64\}  ta_tools.py$|$new  ta_tools.py|" $T/SHA256SUMS
(cd $T && sha256sum --quiet -c SHA256SUMS) && echo "sums ok"
sha256sum $T/SHA256SUMS | cut -d' ' -f1 > /data/ta/sums.patched; cut -c1-12 /data/ta/sums.patched
ts=$(date -u +%Y%m%dT%H%M%SZ); cd /data/ta
for d in status/pseudo.DONE final53 private/registries private/write-work; do [ -e $d ] && mv $d $d.old.$ts; done
ls status/ | tr '\n' ' '; echo; echo "ta-run: $(systemctl is-active ta-run)"
