#!/usr/bin/env python3
"""S2: resolve every GitHub slug of the pool with the GitHub GraphQL API.

Inputs (paths relative to dataset-selection/):
  sources/spinellis-2020/enterprise-oss.tar.gz   Spinellis et al., MSR 2020,
                                    file enterprise_projects.txt (all 17,264 rows)
  sources/cncf-landscape/landscape_repos.csv     every landscape repository
  rosters/*.csv                     column github_slug (not *.orig.csv),
                                    including the home page lookups *.repos.csv

For each distinct slug, one GraphQL lookup reads the same fields as the S1
search: the canonical nameWithOwner (a renamed repository resolves to its new
name), databaseId, archived, fork, mirror, dates, owner type, license, the
Linguist language bytes and the default branch HEAD commit.

Output, in the folder of this script:
  slugs.csv      each input slug and where it comes from (file and row source)
  roster_orgs.csv  roster rows whose repo_url is a GitHub organization, not a
                 repository; they are evidence for stage S5, not pool rows
  resolve.jsonl  one row for each slug: the input slug, the result or the
                 error (for example NOT_FOUND), and fetched_at
  run.log

Resumable: a slug that is in resolve.jsonl is not looked up again.
"""
import csv
import datetime as dt
import glob
import json
import re
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GH_URL = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+?)(?:\.git)?/?$")
TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()

FIELDS = """
nameWithOwner databaseId url stargazerCount isArchived isFork isMirror isEmpty
createdAt pushedAt owner { __typename login }
primaryLanguage { name }
licenseInfo { spdxId }
languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name } } }
defaultBranchRef { name target { ... on Commit { oid committedDate } } }
"""


def log(msg):
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with (HERE / "run.log").open("a") as f:
        f.write(line + "\n")


class TooHeavy(Exception):
    pass


def gql(query, heavy):
    body = json.dumps({"query": query}).encode()
    for _ in range(8):
        req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
            "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (502, 504) and heavy:
                raise TooHeavy(e.code)
            wait = int(e.headers.get("Retry-After", 60)) if e.code in (403, 429) else 30
            log(f"HTTP {e.code}, retry in {wait}s")
            time.sleep(wait)
            continue
        except (urllib.error.URLError, TimeoutError) as e:
            log(f"network error {e}, retry in 30s")
            time.sleep(30)
            continue
        if not d.get("data"):
            log(f"GraphQL error {d.get('errors')}, retry in 30s")
            time.sleep(30)
            continue
        rl = d["data"].get("rateLimit")
        if rl and rl["remaining"] < 100:
            wait = (dt.datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00"))
                    - dt.datetime.now(dt.timezone.utc)).total_seconds() + 5
            log(f"GraphQL quota low, sleeping {int(wait)}s")
            time.sleep(max(wait, 5))
        time.sleep(1)
        return d
    raise RuntimeError("GraphQL failed 8 times")


def collect():
    """Return {slug_lower: [origin, ...]} and write slugs.csv."""
    origins = {}
    # Spinellis et al., MSR 2020: the enterprise set (17,264 rows), read from the
    # verified Zenodo archive. No stars rule: only the S4 filters apply.
    with tarfile.open(ROOT / "sources/spinellis-2020/enterprise-oss.tar.gz") as t:
        for line in t.extractfile("enterprise_projects.txt").read().decode("utf-8", "replace").splitlines():
            m = GH_URL.match(line.split("\t", 1)[0].strip())
            if m:
                origins.setdefault(f"{m.group(1)}/{m.group(2)}".lower(), []).append("spinellis-2020:enterprise")
    # The CNCF landscape, every entry with a GitHub repository (pool only).
    for r in csv.DictReader(open(ROOT / "sources/cncf-landscape/landscape_repos.csv", encoding="utf-8")):
        if r["github_slug"]:
            origins.setdefault(r["github_slug"].lower(), []).append(
                "cncf-landscape:" + ("hosted" if r["cncf_project_status"] else "not-hosted"))
    orgs = []
    for f in sorted(glob.glob(str(ROOT / "rosters/*.csv"))):
        name = Path(f).name
        if name.endswith(".orig.csv"):
            continue
        for r in csv.DictReader(open(f, encoding="utf-8")):
            s = (r.get("github_slug") or "").strip().lower()
            u = (r.get("repo_url") or "").strip()
            if s:
                origins.setdefault(s, []).append(f"rosters/{name}:{r['org_key']}")
            elif re.match(r"^https?://(www\.)?github\.com/", u, re.I):
                # A GitHub URL with no slug names an organization (roster_org evidence, stage S5).
                orgs.append([name, r["org_key"], r.get("project", ""), u])
    with (HERE / "roster_orgs.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["roster_file", "org_key", "project", "repo_url"])
        w.writerows(orgs)
    with (HERE / "slugs.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["slug", "origins"])
        for s in sorted(origins):
            w.writerow([s, ";".join(sorted(set(origins[s])))])
    return origins


def lookup(batch):
    parts = []
    for i, s in enumerate(batch):
        owner, name = s.split("/", 1)
        parts.append(f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ {FIELDS} }}')
    d = gql("query { rateLimit { remaining resetAt } " + " ".join(parts) + " }", heavy=len(batch) > 1)
    errors = {}
    for e in d.get("errors") or []:
        path = (e.get("path") or ["?"])[0]
        errors[path] = e.get("type") or e.get("message")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return [{"slug": s, "result": d["data"].get(f"r{i}"), "error": errors.get(f"r{i}"), "fetched_at": now}
            for i, s in enumerate(batch)]


def main():
    origins = collect()
    out = HERE / "resolve.jsonl"
    done = {json.loads(l)["slug"] for l in out.open()} if out.exists() else set()
    todo = [s for s in sorted(origins) if s not in done and s.count("/") == 1]
    log(f"start: {len(origins)} slugs, {len(done)} done, {len(todo)} to go")
    size = 50
    with out.open("a") as f:
        i = 0
        while i < len(todo):
            batch = todo[i:i + size]
            try:
                rows = lookup(batch)
            except TooHeavy as e:
                size = max(1, size // 2)
                log(f"HTTP {e}, batch size now {size}")
                time.sleep(10)
                continue
            for r in rows:
                f.write(json.dumps(r) + "\n")
            f.flush()
            i += len(batch)
            if i % 1000 < len(batch):
                log(f"{i}/{len(todo)}")
    log("end")


if __name__ == "__main__":
    main()
