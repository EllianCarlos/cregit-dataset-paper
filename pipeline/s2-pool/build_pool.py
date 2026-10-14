#!/usr/bin/env python3
"""S2: build the pool, the union of all sources. Facts only: no row is dropped.

Inputs (relative to dataset-selection/):
  s1-search/repos.jsonl         GitHub search rows (restore it with xz -d -k)
  s2-pool/slugs.csv             each input slug (rosters, Spinellis enterprise set,
                                CNCF landscape), with its origins
  s2-pool/resolve.jsonl         GraphQL lookup of each slug
  s2-pool/resolve_rest.jsonl    REST pass for the slugs GraphQL did not find
  rosters/*.csv                 repo_url of roster rows with no GitHub slug
  sources/company-orgs/repos.jsonl  every public repository of each kept company org

Outputs, in the folder of this script:
  pool.csv          one row for each repository: GitHub rows merged by
                    databaseId, other hosts by their normalized repo_url
  unresolved.csv    each input slug that neither lookup found, with the reason
  pool_counts.txt   the counts for the flow diagram
"""
import csv
import glob
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

COLS = ["pool_key", "host", "database_id", "name_with_owner", "repo_url", "origins", "input_slugs",
        "in_search", "archived", "fork", "mirror", "empty", "created_at", "pushed_at", "stars",
        "owner_type", "owner_login", "license", "primary_language", "languages_total_bytes",
        "languages", "default_branch", "head_oid", "head_committed_at", "fetched_at", "fetched_by"]


def facts(r, fetched_at, fetched_by):
    br = r.get("defaultBranchRef") or {}
    tgt = br.get("target") or {}
    langs = r.get("languages") or {}
    return {
        "host": "github.com",
        "database_id": r["databaseId"],
        "name_with_owner": r["nameWithOwner"],
        "repo_url": r["url"],
        "archived": r["isArchived"], "fork": r["isFork"], "mirror": r["isMirror"], "empty": r["isEmpty"],
        "created_at": r["createdAt"], "pushed_at": r["pushedAt"], "stars": r["stargazerCount"],
        "owner_type": (r.get("owner") or {}).get("__typename", ""),
        "owner_login": (r.get("owner") or {}).get("login", ""),
        "license": (r.get("licenseInfo") or {}).get("spdxId", "") if r.get("licenseInfo") else "",
        "primary_language": (r.get("primaryLanguage") or {}).get("name", "") if r.get("primaryLanguage") else "",
        "languages_total_bytes": langs.get("totalSize", ""),
        "languages": json.dumps({e["node"]["name"]: e["size"] for e in langs.get("edges", [])}, separators=(",", ":")),
        "default_branch": br.get("name", ""),
        "head_oid": tgt.get("oid", ""), "head_committed_at": tgt.get("committedDate", ""),
        "fetched_at": fetched_at, "fetched_by": fetched_by,
    }


def norm_url(u):
    u = u.strip().rstrip("/")
    u = re.sub(r"^http://", "https://", u, flags=re.I)
    u = re.sub(r"\.git$", "", u)
    return u.lower()


def main():
    pool = {}
    origins = defaultdict(set)
    inputs = defaultdict(set)

    def put(key, row):
        old = pool.get(key)
        if old is None or row["fetched_at"] > old["fetched_at"]:
            pool[key] = row

    for l in (ROOT / "s1-search/repos.jsonl").open():
        r = json.loads(l)
        key = f"gh:{r['databaseId']}"
        put(key, facts(r, r["fetched_at"], "s1-search"))
        origins[key].add("search")

    # Every public repository of each kept company org (sources/company-orgs/).
    org_repos = ROOT / "sources/company-orgs/repos.jsonl"
    if org_repos.exists():
        for l in org_repos.open():
            r = json.loads(l)
            key = f"gh:{r['databaseId']}"
            put(key, facts(r, r["fetched_at"], "company-orgs"))
            origins[key].add(f"company-org:{r['org']}")

    slug_origins = {r["slug"]: r["origins"].split(";") for r in csv.DictReader(open(HERE / "slugs.csv"))}
    found, unresolved = {}, {}
    for name, by in [("resolve.jsonl", "s2-graphql"), ("resolve_rest.jsonl", "s2-rest")]:
        p = HERE / name
        if not p.exists():
            continue
        for l in p.open():
            r = json.loads(l)
            if r["slug"] not in slug_origins:
                continue  # looked up for an earlier input list; not a pool input now
            if r["result"]:
                found[r["slug"]] = (r["result"], r["fetched_at"], by)
                unresolved.pop(r["slug"], None)
            elif r["slug"] not in found:
                why = r.get("error") or ""
                if "rest_status" in r:
                    why = f"GraphQL NOT_FOUND; REST HTTP {r['rest_status']}" + (f" as {r['rest_full_name']}" if r["rest_full_name"] else "")
                unresolved[r["slug"]] = (why, r["fetched_at"])
    for slug, (res, at, by) in found.items():
        key = f"gh:{res['databaseId']}"
        put(key, facts(res, at, by))
        origins[key].update(slug_origins.get(slug, []))
        inputs[key].add(slug)

    for f in sorted(glob.glob(str(ROOT / "rosters/*.csv"))):
        name = Path(f).name
        if name.endswith(".orig.csv"):
            continue
        for r in csv.DictReader(open(f, encoding="utf-8")):
            u = (r.get("repo_url") or "").strip()
            if (r.get("github_slug") or "").strip() or not u or re.match(r"^https?://(www\.)?github\.com/", u, re.I):
                continue
            key = "url:" + norm_url(u)
            host = re.sub(r"^[a-z+]+://", "", u, flags=re.I).split("/")[0].lower()
            pool.setdefault(key, {"host": host, "repo_url": u, "fetched_at": r.get("fetched_at", ""),
                                  "fetched_by": f"rosters/{name}"})
            origins[key].add(f"rosters/{name}:{r['org_key']}")

    with (HERE / "pool.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, COLS, lineterminator="\n")
        w.writeheader()
        for key in sorted(pool):
            row = dict(pool[key], pool_key=key, origins=";".join(sorted(origins[key])),
                       input_slugs=";".join(sorted(inputs[key])), in_search="search" in origins[key])
            w.writerow({c: row.get(c, "") for c in COLS})
    with (HERE / "unresolved.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["slug", "origins", "reason", "fetched_at"])
        for s in sorted(unresolved):
            w.writerow([s, ";".join(slug_origins.get(s, [])), *unresolved[s]])

    hosts = Counter(r["host"] for r in pool.values())
    lines = [f"pool rows: {len(pool)}",
             f"  GitHub: {hosts['github.com']} (in the search: {sum(1 for k in pool if 'search' in origins[k])})",
             f"  other hosts: {len(pool) - hosts['github.com']}"]
    lines += [f"    {h}: {n}" for h, n in hosts.most_common() if h != "github.com"]
    lines += [f"input slugs: {len(slug_origins)}; found {len(found)}; unresolved {len(unresolved)}",
              f"slugs that resolve to another name: {sum(1 for s, (r, _, _) in found.items() if r['nameWithOwner'].lower() != s)}"]
    (HERE / "pool_counts.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
