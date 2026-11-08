#!/usr/bin/env python3
"""The partner rows of each new project: every pool row (GitHub and other-host pool, GitLab pool rows) and every
selected row with the same repository name (last path part, lower case, no .git), the project itself excluded.
Writes copycheck/new.jsonl (the 159 new projects) and copycheck/partners.jsonl (one line per pair candidate)."""
import csv, gzip, json, collections
from pathlib import Path
HERE = Path(__file__).resolve().parent.parent
SEL = Path.home() / "STUDY-REPOSITORY/dataset-selection"
rs = {r["pool_key"]: r for r in csv.DictReader(gzip.open(HERE / "row_status.tsv.gz", "rt"), delimiter="\t")
      if r["new_step"] not in ("notpool", "merge")}
pool = {}
for fn in ["pool.csv", "v2/pool.supplement.csv"]:
    for r in csv.DictReader(open(SEL / "s2-pool" / fn, encoding="utf-8")):
        pool[r["pool_key"]] = r
gl = {json.loads(l)["pool_key"]: json.loads(l) for l in open(HERE / "work/gitlab_rows.jsonl")}
def nm(path):
    return path.rstrip("/").split("/")[-1].lower().removesuffix(".git")
rows = {}
for k, s in rs.items():
    if s["new_step"] in ("notpool", "merge"):
        continue
    if k in pool:
        p = pool[k]
        rows[k] = dict(key=k, host=p["host"], path=p["name_with_owner"] or p["repo_url"].split("://", 1)[-1].split("/", 1)[-1],
                       url=p["repo_url"], head=p["head_oid"], fork=p["fork"] == "True", mirror=p["mirror"] == "True",
                       default_branch=p["default_branch"], exit=s["new_step"], project=s["project"])
    elif k in gl:
        g = gl[k]
        rows[k] = dict(key=k, host=g["host"], path=g["path"], url=g["url"], head=g.get("pinned_commit") or "", gl_id=g["id"],
                       fork=g["removed_by"] == "fork", mirror=g["removed_by"] == "mirror", removed_by=g["removed_by"],
                       exit=s["new_step"], project=s["project"], decision=g.get("decision", ""))
    else:
        raise SystemExit(f"unknown pool key {k}")
tom = set()
for r in csv.DictReader(open(Path.home() / "s3-work/dataset-tom-4/final/MANIFEST.tsv"), delimiter="\t"):
    tom.add(r["project"])
for r in rows.values():
    r["selected"] = r["exit"] == ""
    r["tom"] = r["project"] in tom
new = [r for r in rows.values() if r["selected"] and not r["tom"]]
assert len(new) == 159, len(new)
ntom = sum(r["selected"] and r["tom"] for r in rows.values()); assert ntom == 8449, ntom
np = {(r["host"], r["path"].lower()): r for r in new}
for n in csv.DictReader(open(HERE / "new_projects.tsv"), delimiter="\t"):
    host, name = n["host"], n["name"]
    if name.startswith(host + "__"):
        name = name[len(host) + 2:].replace("__", "/")
    r = np[(host, name.lower())]
    r["pinned"] = n["pinned_commit"]; r["commits"] = n["commits"]
by_name = collections.defaultdict(list)
for r in rows.values():
    by_name[nm(r["path"])].append(r["key"])
with open(HERE / "copycheck/new.jsonl", "w") as f:
    for r in sorted(new, key=lambda r: r["key"]):
        f.write(json.dumps(r) + "\n")
n_pairs = 0
with open(HERE / "copycheck/partners.jsonl", "w") as f:
    for r in sorted(new, key=lambda r: r["key"]):
        for k in by_name[nm(r["path"])]:
            if k == r["key"]:
                continue
            f.write(json.dumps(dict(new=r["key"], partner=k, why="same name", **{"p_" + a: b for a, b in rows[k].items()})) + "\n")
            n_pairs += 1
json.dump({k: v for k, v in rows.items()}, open(HERE / "copycheck/rows.json", "w"))
print(len(new), "new;", n_pairs, "same-name pairs")
