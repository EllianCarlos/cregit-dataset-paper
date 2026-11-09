#!/usr/bin/env python3
"""User decision 2026-11-09: kitao/pyxel leaves at the first rule, "Commit on the default branch", because its
repository is not found. Before, it left at "Has a project file". This script changes that one row of
row_status.tsv.gz and recomputes the old-placement step counts of funnel_counts.json from row_status.tsv.gz
(the counts that fold_copy_rules.py checks). Run fold_copy_rules.py after it."""
import csv
import gzip
import io
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY, STEP, REASON = "gh:136780445", "Commit on the default branch", "repository not found"
OLD = ["Pool of all sources (GitLab included)", "Commit on the default branch", "Not archived", "Not a fork", "Not a mirror",
       "Push on or after 2025-04-03 (GitLab: last activity)",
       "tokei rule: the largest programming language is C, C++, Java or Rust",
       "License file, or a near miss C, D or E (DP8L v4)", "1,000 or more commits",
       "GitLab copy rules: shared history with a pool row, R1, R2, R3 (GitLab only)",
       "Has a project file (TOM 1.0.0 rows; new rows are not run yet)"]

raw = gzip.open(HERE / "row_status.tsv.gz", "rt", newline="").read()
rows = list(csv.reader(io.StringIO(raw), delimiter="\t"))
head, body = rows[0], rows[1:]
ik, ip, ist, irs = head.index("pool_key"), head.index("project"), head.index("new_step"), head.index("new_reason")
hit = [r for r in body if r[ik] == KEY]
assert len(hit) == 1 and hit[0][ip] == "kitao__pyxel", hit
hit[0][ist], hit[0][irs] = STEP, REASON
term = "\r\n" if raw.split("\n", 1)[0].endswith("\r") else "\n"
out = io.StringIO()
csv.writer(out, delimiter="\t", lineterminator=term).writerows(rows)
with gzip.open(HERE / "row_status.tsv.gz", "wt", newline="") as f:
    f.write(out.getvalue())

exit_of = {}
for r in body:
    st = r[ist]
    if st in ("merge", "notpool"):
        continue
    exit_of[(r[ik], r[head.index("source")].startswith("gitlab"))] = None if st == "" else OLD.index(st)
fc = json.load(open(HERE / "funnel_counts.json"))
for i, s in enumerate(fc["steps"]):
    assert s["step"] == OLD[i]
    s["after"] = sum(1 for e in exit_of.values() if e is None or e > i)
    s["gitlab"] = sum(1 for k, e in exit_of.items() if k[1] and (e is None or e > i))
fc["final"] = fc["steps"][-1]["after"]
fc["changed"] = "2026-11-09: kitao/pyxel leaves at the commit step (repository not found); set_pyxel_exit.py recomputed steps"
(HERE / "funnel_counts.json").write_text(json.dumps(fc, indent=1) + "\n")
print(json.dumps(fc["steps"], indent=1))
