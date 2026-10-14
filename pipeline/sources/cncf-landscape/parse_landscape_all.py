#!/usr/bin/python3
"""The CNCF landscape as a pool source: every entry with a repository.

Input: ../../rosters/raw/cncf/landscape.yml, fetched 2026-10-05T01:29:35Z from
https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml (see
rosters/cncf.method.md). This script reads the same copy; it fetches nothing.

The landscape catalogues the cloud-native ecosystem. Only an entry with a
`project:` key is hosted by CNCF; that is foundation evidence and is already in
rosters/cncf.csv. The other entries are a pool source only, with no evidence.

Output: landscape_repos.csv: name, repo_url, github_slug, cncf_project_status
(empty if CNCF does not host the entry), category, subcategory, source_url,
fetched_at. One row for each repository (repo_url and each additional_repos).
"""
import csv
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SRC = HERE.parent.parent / "rosters/raw/cncf/landscape.yml"
URL = "https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml"
FETCHED = "2026-10-05T01:29:35Z"
GH = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+?)(?:\.git)?/?$")

doc = yaml.safe_load(open(SRC, encoding="utf-8"))
rows, seen = [], set()
for cat in doc.get("landscape", []) or []:
    for sub in cat.get("subcategories", []) or []:
        for it in sub.get("items", []) or []:
            urls = [it.get("repo_url")] + [a.get("repo_url") for a in it.get("additional_repos", []) or []]
            for u in urls:
                if not u or (it.get("name"), u) in seen:
                    continue
                seen.add((it.get("name"), u))
                m = GH.match(u)
                rows.append([it.get("name", ""), u, f"{m.group(1)}/{m.group(2)}" if m else "",
                             it.get("project", "") or "", cat.get("name", ""), sub.get("name", ""), URL, FETCHED])
with open(HERE / "landscape_repos.csv", "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["name", "repo_url", "github_slug", "cncf_project_status", "category", "subcategory", "source_url", "fetched_at"])
    w.writerows(rows)
print(f"{len(rows)} repositories, {sum(1 for r in rows if r[3])} hosted by CNCF, {sum(1 for r in rows if not r[3])} not hosted, "
      f"{sum(1 for r in rows if r[2])} with a GitHub slug")
