import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path
pick, led = sys.argv[1], Path(sys.argv[2])
rows = {}; cls = {}
for r in csv.DictReader(open(pick), delimiter="\t"):
    cls[r["project"]] = r["class"]
schema = csv.DictReader(open(sys.argv[3]), delimiter="\t")
for r in schema: rows[r["project"]] = int(r["rows"])
gaps = {p for p, c in cls.items() if c == "gap-ambiguous"}
recs = defaultdict(list)
for f in sorted(led.rglob("*.jsonl")):
    if f.name.endswith("test.jsonl"): continue
    for line in open(f, errors="replace"):
        if '"done"' not in line: continue
        try: r = json.loads(line)
        except json.JSONDecodeError: continue
        p = r.get("project")
        if p in gaps and r.get("step") == "project" and r.get("status") == "done":
            t = r.get("tools") or {}; pq = r.get("parquet") or {}
            if pq.get("rows") is not None and int(pq["rows"]) == rows[p]:
                recs[p].append((r.get("checked_out_sha",""), t.get("cregit_commit",""), t.get("ctp_commit",""), str(f.relative_to(led)).split("/")[0], r.get("end_utc","")))
which = Counter(); pairs = Counter(); dirs = Counter()
for p, rs in recs.items():
    u = set(x[:3] for x in rs)
    k = tuple(n for i, n in enumerate(("project", "cregit", "ctp")) if len({x[i] for x in u}) > 1)
    which[k] += 1
    pairs[tuple(sorted({(x[1][:7], x[2][:7]) for x in rs}))] += 1
    dirs[tuple(sorted({x[3] for x in rs}))] += 1
print("fields that differ:", which.most_common())
print("tool pairs:"); [print(" ", c, k) for k, c in pairs.most_common(8)]
print("folders:"); [print(" ", c, k) for k, c in dirs.most_common(10)]
