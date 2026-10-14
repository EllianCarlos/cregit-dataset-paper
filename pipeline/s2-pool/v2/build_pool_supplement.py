#!/usr/bin/env python3
"""New pool rows from rosters/gnu.v2.csv, in the columns of pool.csv.

- A Savannah clone URL (v2_status "git"), or a repository on another host that
  is not GitHub ("git (another host)"), gives an other-host row, key
  "url:" + norm_url(clone URL), the same key rule as build_pool.py. S3 v2
  measures it with measure_clones (a Savannah row over its git:// form).
- A GitHub repository (github_slug) is resolved with the S2 GraphQL fields
  (resolve.FIELDS, build_pool.facts) and gives a GitHub row, key "gh:<databaseId>".
  Its head_oid is the default branch HEAD at this lookup (2026-10-10), not at
  the S2 snapshot (2026-10-05). The lookup is kept in resolve_gnu.jsonl.
A row whose key, normalized URL or name_with_owner is already in pool.csv is
not added (it is listed in pool.supplement.skipped.tsv).

Output: pool.supplement.csv, pool.supplement.skipped.tsv, resolve_gnu.jsonl.
"""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEL = HERE.parent.parent
sys.path.insert(0, str(HERE.parent))
import build_pool  # noqa: E402
import resolve  # noqa: E402

ORIGIN = "rosters/gnu.v2.csv:gnu"


def lookup(slug):
    out = HERE / "resolve_gnu.jsonl"
    if out.exists():
        for l in out.open():
            d = json.loads(l)
            if d["slug"] == slug:
                return d
    owner, name = slug.split("/", 1)
    q = f'query {{ rateLimit {{ remaining resetAt }} r: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{ {resolve.FIELDS} }} }}'
    d = resolve.gql(q, heavy=False)
    rec = {"slug": slug, "result": d["data"].get("r"), "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with out.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def main():
    pool = list(csv.DictReader(open(HERE.parent / "pool.csv", encoding="utf-8")))
    keys = {r["pool_key"] for r in pool}
    urls = {build_pool.norm_url(r["repo_url"]): r["pool_key"] for r in pool if r["repo_url"]}
    nwos = {r["name_with_owner"].lower(): r["pool_key"] for r in pool if r["name_with_owner"]}
    mapped = {build_pool.norm_url(r["clone_url"]): r["pool_key"]
              for r in csv.DictReader(open(HERE / "url_map.tsv"), delimiter="\t")}
    rows, skipped = [], []
    for g in csv.DictReader(open(SEL / "rosters/gnu.v2.csv", encoding="utf-8")):
        st = g["v2_status"]
        other = st in ("git (another host)", "git (project website)")
        if (st == "git" and g["clone_url"]) or (other and not g["github_slug"]):
            u = build_pool.norm_url(g["clone_url"])
            key = "url:" + u
            dup = keys & {key} or ({urls[u]} if u in urls else set()) or ({mapped[u]} if u in mapped else set())
            if dup:
                skipped.append([g["project"], g["clone_url"], f"already in the pool as {sorted(dup)[0]}"])
                continue
            rows.append({"pool_key": key, "host": u.split("://", 1)[1].split("/", 1)[0], "repo_url": g["clone_url"],
                         "origins": ORIGIN, "in_search": "False", "fetched_at": g["v2_fetched_at"],
                         "fetched_by": "rosters/gnu.v2.csv"})
            keys.add(key)
        elif other and g["github_slug"]:
            s = g["github_slug"].lower()
            if s in nwos:
                skipped.append([g["project"], g["clone_url"], f"already in the pool as {nwos[s]}"])
                continue
            rec = lookup(g["github_slug"])
            if not rec["result"]:
                skipped.append([g["project"], g["clone_url"], "GraphQL NOT_FOUND"])
                continue
            f = build_pool.facts(rec["result"], rec["fetched_at"], "s2-v2-graphql")
            key = f"gh:{f['database_id']}"
            if key in keys:
                skipped.append([g["project"], g["clone_url"], f"already in the pool as {key}"])
                continue
            rows.append(dict(f, pool_key=key, origins=ORIGIN, input_slugs=g["github_slug"], in_search="False"))
            keys.add(key)
    with open(HERE / "pool.supplement.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, build_pool.COLS, lineterminator="\n")
        w.writeheader()
        w.writerows({c: r.get(c, "") for c in build_pool.COLS} for r in rows)
    with open(HERE / "pool.supplement.skipped.tsv", "w") as f:
        f.write("project\turl\twhy\n")
        for s in skipped:
            f.write("\t".join(s) + "\n")
    print(f"{len(rows)} new pool rows ({sum(r['host'] == 'github.com' for r in rows)} GitHub); {len(skipped)} skipped")


if __name__ == "__main__":
    main()
