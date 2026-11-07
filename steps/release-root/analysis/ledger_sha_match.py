#!/usr/bin/env python3
"""Match the gap rows of the release manifest to run records by the sha256 of the file.

Inputs: the ledger-pick report of the release build (classes per project), the results of the layer merge
(v1.raw.results.tsv, x1k.raw.results.tsv: input_key, input_sha256 = the sha256 of the run file that the merge read),
optional the footer-fix manifest (for a fixed file, the run file is the input of the fix row whose output the merge
read), and a folder of run ledgers. Output: one TSV row per gap project with the new class. Read only on its inputs.
Do not give the results of the final write: their input_sha256 is the sha256 of the merged file, and no run record
has that sha256 (review 2026-10-28: with them, 0 of 1,198 gap projects matched).
A record that ended after the merge read the file (finished_utc) is not used: a later rerun can give the same bytes.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--pick", required=True)
ap.add_argument("--results", required=True, nargs="+")
ap.add_argument("--ledgers", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--fix-manifest")
a = ap.parse_args()

fixrows = defaultdict(list)  # rel_path -> rows of the footer-fix manifest
if a.fix_manifest:
    with open(a.fix_manifest, newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            fixrows[r["rel_path"]].append(r)
FIXED = "dataset-v1/inputs/fixed/"

cls = {}
with open(a.pick, newline="") as fh:
    for r in csv.DictReader(fh, delimiter="\t"):
        cls[r["project"]] = r["class"]
gaps = {p for p, c in cls.items() if c.startswith("gap")}

want = {}
for f in a.results:
    with open(f, newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["project"] not in gaps:
                continue
            if "input_key" not in r:
                raise SystemExit(f"{f}: no input_key column (give the merge results, not the final-write results)")
            key, sha = r["input_key"], r["input_sha256"]
            if key.startswith(FIXED) and a.fix_manifest:
                rel = key[len(FIXED):].rsplit("/", 1)[0]
                hit = [x for x in fixrows.get(rel, []) if x["output_sha256"] == sha and x["project"] == r["project"]]
                sha = hit[0]["input_sha256"] if len(hit) == 1 else ""
            want[r["project"]] = (key, sha, r["finished_utc"])

recs = defaultdict(list)  # project -> done records
by_sha = defaultdict(list)  # any sha256 in a parquet dict -> (project, record)
for f in sorted(Path(a.ledgers).rglob("*.jsonl")):
    if f.name.endswith("test.jsonl"):
        continue
    with open(f, errors="replace") as fh:
        for line in fh:
            if '"sha256"' not in line and '"done"' not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            pq = r.get("parquet") or {}
            rec = {"file": str(f.relative_to(a.ledgers)), "step": r.get("step"), "status": r.get("status"),
                   "end_utc": r.get("end_utc", ""), "sha": r.get("checked_out_sha") or "",
                   "cregit": (r.get("tools") or {}).get("cregit_commit") or "",
                   "ctp": (r.get("tools") or {}).get("ctp_commit") or "",
                   "pq_sha": pq.get("sha256") or "", "rows": pq.get("rows")}
            p = r.get("project")
            if p in gaps and r.get("step") == "project" and r.get("status") == "done":
                recs[p].append(rec)
            if rec["pq_sha"]:
                by_sha[rec["pq_sha"]].append((p, rec))

out = Counter()
with open(a.out, "w") as fh:
    fh.write("project\told_class\tnew_class\tinput\trecords\tsha_records\tdistinct_tuples\tchecked_out_sha\tcregit\tctp\tdetail\n")
    for p in sorted(gaps):
        inp, isha, until = want.get(p, ("", "", ""))
        rs = [x for x in recs.get(p, []) if not until or x["end_utc"][:19] <= until[:19]]
        hit = [x for x in rs if x["pq_sha"] and x["pq_sha"] == isha]
        other = [(q, x) for q, x in by_sha.get(isha, []) if q != p]
        tuples = {(x["sha"], x["cregit"], x["ctp"]) for x in hit if x["sha"]}
        detail = ""
        if not isha:
            new = "no-final-input"
        elif len(tuples) == 1:
            new = "sha-match"
        elif len(tuples) > 1:
            new = "sha-match-ambiguous"
        elif other:
            new = "sha-match-other-name"
            detail = ",".join(sorted({q or "" for q, _ in other}))
        else:
            shas = {x["sha"] for x in rs if x["sha"]}
            new = "no-sha-match-one-project-commit" if len(shas) == 1 else "no-sha-match"
            detail = f"{len(shas)} project commits"
        t = next(iter(tuples)) if len(tuples) == 1 else ("", "", "")
        out[(cls[p], new)] += 1
        fh.write(f"{p}\t{cls[p]}\t{new}\t{inp}\t{len(rs)}\t{len(hit)}\t{len(tuples)}\t{t[0]}\t{t[1]}\t{t[2]}\t{detail}\n")
for (o, n), c in sorted(out.items()):
    print(f"{o}\t{n}\t{c}")
