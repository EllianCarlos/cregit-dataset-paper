#!/usr/bin/env python3
"""Find the run record of each gap project by the sha256 of the run file.

--target: TSV with the columns project and sha256 (the sha256 of the file that the layer merge read).
--ledgers: one or more folders of run ledgers (test ledgers and gate ledgers are skipped).
--out: one row per target project: class, the record (project commit, cregit, ctp, end, ledger file).
--picked: JSON lines in the form of the release build (ledger.picked.jsonl) for the found records.
--not-after: TSV files with the columns project and finished_utc (the merge results): the time when a later
step read the file. A run that ended after that time did not make the file that the step read (for example a rerun
that gave the same bytes), so the tool does not use its record.
A project is "found" when all records with its sha256 name one (project commit, cregit, ctp). Of these records the
tool writes the first (the first run that made the bytes).
"""
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

SKIP = re.compile(r"(^|\.)test\.jsonl$")

ap = argparse.ArgumentParser()
ap.add_argument("--target", required=True)
ap.add_argument("--ledgers", required=True, nargs="+")
ap.add_argument("--out", required=True)
ap.add_argument("--picked", required=True)
ap.add_argument("--not-after", nargs="*", default=[])
a = ap.parse_args()

limit = {}
for f in a.not_after:
    with open(f, newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            limit[r["project"]] = r["finished_utc"]


def utc(s):
    """The time as YYYY-MM-DDTHH:MM:SS (the form of the ledgers and of the results files)."""
    return (s or "")[:19]

target = {}
with open(a.target, newline="") as fh:
    for r in csv.DictReader(fh, delimiter="\t"):
        target[r["project"]] = r["sha256"]
want = set(target.values())

hits = defaultdict(list)
nfiles = 0
for d in a.ledgers:
    for f in sorted(Path(d).rglob("*.jsonl")):
        if SKIP.search(f.name) or "/gate/" in str(f) or "/.venv/" in str(f):
            continue
        nfiles += 1
        with open(f, errors="replace") as fh:
            for line in fh:
                if '"done"' not in line or '"sha256"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("step") != "project" or r.get("status") != "done":
                    continue
                s = (r.get("parquet") or {}).get("sha256") or ""
                if s in want:
                    t = r.get("tools") or {}
                    hits[s].append({"project": r.get("project"), "end_utc": r.get("end_utc", ""),
                                    "checked_out_sha": r.get("checked_out_sha") or "",
                                    "snapshot_sha": r.get("snapshot_sha") or "",
                                    "cregit_commit": t.get("cregit_commit") or "",
                                    "ctp_commit": t.get("ctp_commit") or "", "file": str(f)})

n = Counter()
with open(a.out, "w") as fo, open(a.picked, "w") as fp:
    fo.write("project\tclass\tchecked_out_sha\tcregit_commit\tctp_commit\tend_utc\tledger\n")
    for p in sorted(target):
        rs = [x for x in hits.get(target[p], []) if x["project"] == p]
        if p in limit:
            n["records after the reader (not used)"] += sum(utc(x["end_utc"]) > utc(limit[p]) for x in rs)
            rs = [x for x in rs if utc(x["end_utc"]) <= utc(limit[p])]
        tup = {(x["checked_out_sha"], x["cregit_commit"], x["ctp_commit"]) for x in rs}
        if not rs:
            c = "no-record-with-sha"
        elif len(tup) == 1 and all(tup.pop()):
            c = "found"
        else:
            c = "sha-ambiguous-or-empty"
        n[c] += 1
        x = sorted(rs, key=lambda y: y["end_utc"])[0] if rs else {}
        fo.write(f"{p}\t{c}\t{x.get('checked_out_sha', '')}\t{x.get('cregit_commit', '')}\t{x.get('ctp_commit', '')}"
                 f"\t{x.get('end_utc', '')}\t{x.get('file', '')}\n")
        if c == "found":
            fp.write(json.dumps({"step": "project", "status": "done", "project": p, "end_utc": x["end_utc"],
                                 "checked_out_sha": x["checked_out_sha"], "snapshot_sha": x["snapshot_sha"],
                                 "tools": {"cregit_commit": x["cregit_commit"], "ctp_commit": x["ctp_commit"]}},
                                sort_keys=True) + "\n")
print(f"resolve: {nfiles} ledger files; {len(target)} projects; " + ", ".join(f"{k} {v}" for k, v in sorted(n.items())))
