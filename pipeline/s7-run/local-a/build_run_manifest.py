#!/usr/bin/env python3
"""build_run_manifest.py L: the run manifest and sidecar of census-local-a.

Reads L/parts.taken ("<wl> <part>" per line, in run order) and writes
L/manifest.local-a.tsv (the S rows of each part manifest L/input/<wl>/manifest.<wl><part>.tsv,
in part order, u order kept inside each part; M and L rows are left out and listed) and
L/project_meta.local-a.json (the records of those projects, copied unchanged from
L/input/<wl>/project_meta.<wl>.json; only the record of the project goes into its Parquet).
"""
import json
import sys
from pathlib import Path

L = Path(sys.argv[1]).resolve()
rows, meta, cols, skipped = [], {}, None, []
for line in (L / "parts.taken").read_text().splitlines():
    if not line.strip() or line.startswith("#"):
        continue
    wl, part = line.split()
    lines = (L / "input" / wl / f"manifest.{wl}{part}.tsv").read_text().splitlines()
    c = next(x for x in lines if x.startswith("# Columns:"))
    assert cols in (None, c), "column header differs"
    cols = c
    src = json.loads((L / "input" / wl / f"project_meta.{wl}.json").read_text(encoding="utf-8"))
    for r in lines:
        if not r.strip() or r.startswith("#"):
            continue
        f = r.split("\t")
        if f[4] != "S":
            skipped.append(f"{wl}{part} {f[0]} {f[4]}")
            continue
        assert f[0] not in meta, f"{f[0]} twice"
        rows.append(r)
        meta[f[0]] = src[f[0]]
(L / "manifest.local-a.tsv").write_text(
    f"# Run manifest of census-local-a: the S rows of the parts in parts.taken ({len(rows)} projects).\n"
    f"{cols}\n" + "".join(r + "\n" for r in rows), encoding="utf-8")
(L / "project_meta.local-a.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"{len(rows)} projects; skipped (not S): {skipped or 'none'}")
