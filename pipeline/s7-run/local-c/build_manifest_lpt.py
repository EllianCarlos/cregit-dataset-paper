#!/usr/bin/env python3
"""build_manifest_lpt.py LIST MANIFEST SIDECAR LEDGER OUTDIR: write manifest.local-c.tsv and
project_meta.local-c.json for the projects in LIST. The rows and sidecar entries are copied
unchanged from MANIFEST and SIDECAR. The rows are in LPT order: the longest old duration
(the longest step=project, status=done row of LEDGER; a short later row is a resume) first; equal durations keep the MANIFEST order."""
import json, sys
from pathlib import Path

lst, man, side, led, out = map(Path, sys.argv[1:6])
names = [l.strip() for l in lst.read_text().splitlines() if l.strip()]
rows = {}
order = []
for line in man.read_text().splitlines():
    if line.strip() and not line.startswith("#"):
        n = line.split("\t")[0]
        rows[n] = line
        order.append(n)
dur = {}
with led.open() as f:
    for line in f:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("step") == "project" and r.get("status") == "done" and r.get("project") in names:
            dur[r["project"]] = max(dur.get(r["project"], 0), r["duration_s"])
miss = [n for n in names if n not in rows or n not in dur]
if miss:
    sys.exit(f"missing manifest row or duration: {miss}")
sel = sorted(names, key=lambda n: (-dur[n], order.index(n)))
meta = json.loads(side.read_text())
if isinstance(meta, dict):
    if any(n not in meta for n in sel):
        sys.exit("sidecar misses a project")
    sub = {n: meta[n] for n in sel}
else:
    sys.exit(f"sidecar type {type(meta)} not handled")
hdr = [l for l in man.read_text().splitlines() if l.startswith("#")]
tot = sum(dur[n] for n in sel)
with (out / "manifest.local-c.tsv").open("w") as f:
    f.write(f"# census-local-c: the rerun of {len(sel)} batch 1 projects with the current code. Rows copied unchanged from manifest.batch1.tsv.\n")
    f.write(f"# Order rule: LPT. Longest old duration first (the longest step=project status=done row per project in the batch 1 ledger; a short later done row is a resume); equal durations keep the batch 1 order. Old sum {tot/3600:.1f} h.\n")
    f.write(hdr[-1] + "\n")
    for n in sel:
        f.write(rows[n] + "\n")
(out / "project_meta.local-c.json").write_text(json.dumps(sub, indent=1, ensure_ascii=False) + "\n")
for n in sel:
    print(f"{dur[n]/3600:6.2f} h  {n}")
print(f"sum {tot/3600:.2f} h, {len(sel)} projects")
