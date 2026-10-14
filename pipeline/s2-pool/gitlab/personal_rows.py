#!/usr/bin/env python3
"""User decision 2026-10-14 ~15:35 UTC ("Yes then"): the gitlab.com search (stars > 400) also takes
projects in personal namespaces, the same rule as the GitHub search (no owner rule). This script takes
the 18 rows of rows/gitlab.com-search.jsonl that the namespace step removed and applies the same later
steps as search_gitlabcom_stars.py: fork, empty repository, no default branch, the languages API lists
none of C, C++, Java, Rust. Output: rows/gitlab.com-search-personal.jsonl (same format)."""
import json, time, urllib.request
from pathlib import Path
H = Path(__file__).resolve().parent
TARGET = {"C", "C++", "Java", "Rust"}
src = [json.loads(l) for l in open(H / "rows/gitlab.com-search.jsonl")]
out = open(H / "rows/gitlab.com-search-personal.jsonl", "w"); n = kept = 0
for r in src:
    if r["removed_by"] != "personal namespace": continue
    n += 1
    why = "fork" if r["fork"] else "empty repository" if r["empty"] else "no default branch" if not r["default_branch"] else None
    if why is None:
        langs = json.load(urllib.request.urlopen(f"https://gitlab.com/api/v4/projects/{r['id']}/languages", timeout=120)); time.sleep(0.5)
        r["languages"] = langs or {}
        if not (set(r["languages"]) & TARGET): why = "no C, C++, Java or Rust in the languages API"
    r["removed_by"] = why or ""; r["search"] = "stars>400 (personal namespace)"; kept += why is None
    out.write(json.dumps(r) + "\n")
print(f"personal rows {n}, kept {kept}")
