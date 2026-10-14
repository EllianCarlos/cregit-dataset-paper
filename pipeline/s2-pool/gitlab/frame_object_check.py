#!/usr/bin/env python3
"""For the large-family roots (GitHub commit search total > 300 and no frame repository in its first 300
results), test each root commit directly in each GitHub frame repository of a chosen layer with the
GitHub GraphQL API: repository(owner, name) { object(oid: <root>) { oid } }, 50 repositories and all
roots in one query (gh api graphql). A hit means the frame repository has that root commit (shared
history). Usage: frame_object_check.py LAYER_PREFIX (for example "≥" for layer 1, "" for the whole
frame). Output: frame_object_hits.tsv (root, frame slug, layer)."""
import csv, json, subprocess, sys, time
from pathlib import Path
H = Path(__file__).resolve().parent; S4 = H.parent.parent / "s4-filter"
pref = sys.argv[1]
roots = sorted({l.split("\t")[1] for l in open(H / "roots.tsv").read().splitlines()[1:]
                if l.split("\t")[5] == "" and l.split("\t")[3].isdigit() and int(l.split("\t")[3]) > 300})
fr = [r for r in csv.DictReader(open(S4 / "frame.v4.csv")) if r["host"] == "github.com" and r["layer"].startswith(pref)]
out = open(H / "frame_object_hits.tsv", "a")
print(len(roots), "roots,", len(fr), "frame repositories", flush=True)
for i in range(0, len(fr), 50):
    chunk = fr[i:i + 50]; parts = []
    for j, r in enumerate(chunk):
        o, n = r["slug"].split("/", 1)
        objs = " ".join(f'o{k}: object(oid: "{x}") {{ oid }}' for k, x in enumerate(roots))
        parts.append(f'r{j}: repository(owner: {json.dumps(o)}, name: {json.dumps(n)}) {{ {objs} }}')
    q = "query { " + " ".join(parts) + " }"
    for t in range(4):
        p = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"], capture_output=True, text=True)
        if p.stdout.strip().startswith("{"): break
        time.sleep(20 * (t + 1))
    d = (json.loads(p.stdout).get("data") or {}) if p.stdout.strip().startswith("{") else {}
    for j, r in enumerate(chunk):
        repo = d.get(f"r{j}") or {}
        for k, x in enumerate(roots):
            if repo.get(f"o{k}"): out.write(f"{x}\t{r['slug']}\t{r['layer']}\n")
    out.flush(); time.sleep(1)
print("done", flush=True)
