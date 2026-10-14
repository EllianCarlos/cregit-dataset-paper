#!/usr/bin/env python3
"""Pool source: every public repository of each kept company org.

Rule (decided 2026-10-06): a repository enters the pool from this source if its
owner is an org that ../spinellis-2020/org_links.csv keeps (rules L1 to L3) and
the repository is public at the snapshot. No other condition applies here; the
S4 filters apply later, as for every row. This source gives no label: the
company label needs the S5 evidence for the org.

For each kept org, the script reads organization(login).repositories(privacy:
PUBLIC), ordered by creation date, with the same fields as the S1 search.
After a 502 or 504 it retries with half the page size.

Outputs, in the folder of this script:
  repos.jsonl  one row for each repository: the org, the fields, fetched_at
  orgs.jsonl   one row for each org: totalCount, rows read, fetched_at
  run.log
Resumable: an org that is in orgs.jsonl is not read again.
"""
import csv
import datetime as dt
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
FIELDS = """
nameWithOwner databaseId url stargazerCount isArchived isFork isMirror isEmpty
createdAt pushedAt owner { __typename login }
primaryLanguage { name }
licenseInfo { spdxId }
languages(first: 20, orderBy: {field: SIZE, direction: DESC}) { totalSize edges { size node { name } } }
defaultBranchRef { name target { ... on Commit { oid committedDate } } }
"""
QUERY = ("query($login: String!, $c: String, $n: Int!) { rateLimit { remaining resetAt } "
         "organization(login: $login) { repositories(privacy: PUBLIC, first: $n, after: $c, "
         "orderBy: {field: CREATED_AT, direction: ASC}) { totalCount pageInfo { hasNextPage endCursor } "
         "nodes { " + FIELDS + " } } } }")


def log(msg):
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with (HERE / "run.log").open("a") as f:
        f.write(line + "\n")


class TooHeavy(Exception):
    pass


def gql(variables):
    body = json.dumps({"query": QUERY, "variables": variables}).encode()
    for _ in range(8):
        req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
            "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (502, 504) and variables["n"] > 5:
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
        time.sleep(0.5)
        return d
    raise RuntimeError("GraphQL failed 8 times")


def read_org(login):
    rows, cursor, page, total = [], None, 50, None
    while True:
        try:
            d = gql({"login": login, "c": cursor, "n": page})
        except TooHeavy as e:
            page //= 2
            log(f"{login}: HTTP {e}, page size now {page}")
            time.sleep(5)
            continue
        org = d["data"].get("organization")
        if org is None:
            return None, rows
        rp = org["repositories"]
        total = rp["totalCount"]
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        rows += [dict(n, org=login, fetched_at=now) for n in rp["nodes"] if n]
        if not rp["pageInfo"]["hasNextPage"]:
            return total, rows
        cursor = rp["pageInfo"]["endCursor"]


def main():
    kept = [r["owner"] for r in csv.DictReader(open(HERE.parent / "spinellis-2020/org_links.csv", encoding="utf-8"))
            if r["link"] == "kept"]
    op, rp = HERE / "orgs.jsonl", HERE / "repos.jsonl"
    done = {json.loads(l)["login"] for l in op.open()} if op.exists() else set()
    todo = [o for o in kept if o not in done]
    log(f"start: {len(kept)} kept orgs, {len(done)} done, {len(todo)} to go")
    with op.open("a") as of, rp.open("a") as rf:
        for i, login in enumerate(todo, 1):
            total, rows = read_org(login)
            for r in rows:
                rf.write(json.dumps(r) + "\n")
            of.write(json.dumps({"login": login, "totalCount": total, "rows": len(rows),
                                 "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}) + "\n")
            rf.flush(); of.flush()
            if total is None or total != len(rows):
                log(f"CHECK {login}: totalCount {total}, rows {len(rows)}")
            if i % 50 == 0:
                log(f"{i}/{len(todo)} orgs")
    log("end")


if __name__ == "__main__":
    main()
