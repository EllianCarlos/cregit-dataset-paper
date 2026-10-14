#!/usr/bin/env python3
"""S1: the GitHub search part of the pool, all languages.

The search API gives at most 1,000 results for each query. This script splits
the base query into star bands, then into creation-date windows, until each
segment holds at most 1,000 repositories. Then it reads every segment, 100
repositories per GraphQL call.

Outputs, in the folder of this script:
  segments.jsonl  one row for each segment: query, repositoryCount, rows read
  repos.jsonl     one row for each repository and segment, with fetched_at
  run.log

Resumable: a segment that is in segments.jsonl is not read again.

usage: search.py [SNAPSHOT_DATE]   (default 2026-10-05)
"""
import datetime as dt
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = dt.date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else "2026-10-05")
PUSHED_FROM = SNAPSHOT - dt.timedelta(days=550)
BASE = f"archived:false fork:false pushed:>={PUSHED_FROM.isoformat()}"
STARS_MIN, STARS_MAX = 401, 1_000_000
CREATED_MIN, CREATED_MAX = dt.date(2007, 1, 1), SNAPSHOT
CAP = 1000
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


def gql(query, variables, heavy=False):
    body = json.dumps({"query": query, "variables": variables}).encode()
    for attempt in range(8):
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
        if d.get("errors") and not d.get("data"):
            log(f"GraphQL error {d['errors']}, retry in 30s")
            time.sleep(30)
            continue
        rl = d["data"].get("rateLimit")
        if rl and rl["remaining"] < 50:
            wait = (dt.datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00"))
                    - dt.datetime.now(dt.timezone.utc)).total_seconds() + 5
            log(f"GraphQL quota low, sleeping {int(wait)}s")
            time.sleep(max(wait, 5))
        time.sleep(1)
        return d
    raise RuntimeError("GraphQL failed 8 times")


def q_of(s_lo, s_hi, c_lo, c_hi):
    return f"stars:{s_lo}..{s_hi} created:{c_lo.isoformat()}..{c_hi.isoformat()} {BASE}"


def count(q):
    d = gql("query($q:String!){rateLimit{remaining resetAt} search(type:REPOSITORY,query:$q,first:1){repositoryCount}}", {"q": q})
    return d["data"]["search"]["repositoryCount"]


def segments():
    """Yield (query, count) with count <= CAP; split stars first, then dates."""
    todo = [(STARS_MIN, STARS_MAX, CREATED_MIN, CREATED_MAX)]
    while todo:
        s_lo, s_hi, c_lo, c_hi = todo.pop()
        q = q_of(s_lo, s_hi, c_lo, c_hi)
        n = count(q)
        if n <= CAP:
            yield q, n
        elif s_hi > s_lo and (c_lo, c_hi) == (CREATED_MIN, CREATED_MAX):
            mid = (s_lo + s_hi) // 2
            todo += [(mid + 1, s_hi, c_lo, c_hi), (s_lo, mid, c_lo, c_hi)]
        elif c_hi > c_lo:
            mid = c_lo + (c_hi - c_lo) // 2
            todo += [(s_lo, s_hi, mid + dt.timedelta(days=1), c_hi), (s_lo, s_hi, c_lo, mid)]
        else:
            log(f"WARNING: cannot split below {CAP}: {q} has {n}; reading the first {CAP}")
            yield q, n


def read(q):
    """Read all pages of a segment. After a 502 or 504, retry with half the page size."""
    rows, cursor, page = [], None, 50
    while True:
        try:
            d = gql("query($q:String!,$c:String,$n:Int!){rateLimit{remaining resetAt} search(type:REPOSITORY,query:$q,first:$n,after:$c)"
                    "{repositoryCount pageInfo{hasNextPage endCursor} nodes{... on Repository{" + FIELDS + "}}}}",
                    {"q": q, "c": cursor, "n": page}, heavy=page > 5)
        except TooHeavy as e:
            page //= 2
            log(f"HTTP {e}, page size now {page}")
            time.sleep(10)
            continue
        s = d["data"]["search"]
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        rows += [dict(n, fetched_at=now, segment=q) for n in s["nodes"] if n]
        if not s["pageInfo"]["hasNextPage"]:
            return rows
        cursor = s["pageInfo"]["endCursor"]


def main():
    seg_path, repo_path = HERE / "segments.jsonl", HERE / "repos.jsonl"
    done = {json.loads(l)["query"] for l in seg_path.open()} if seg_path.exists() else set()
    log(f"start: snapshot {SNAPSHOT}, base '{BASE}', {len(done)} segments already read")
    total = count(f"stars:>{STARS_MIN - 1} {BASE}")
    log(f"base query has {total} repositories")
    with seg_path.open("a") as sf, repo_path.open("a") as rf:
        for q, n in segments():
            if q in done:
                continue
            rows = read(q)
            for r in rows:
                rf.write(json.dumps(r) + "\n")
            sf.write(json.dumps({"query": q, "repositoryCount": n, "rows": len(rows),
                                 "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}) + "\n")
            sf.flush(); rf.flush()
            log(f"{len(rows):4d}/{n:4d}  {q}")
    log("end")


if __name__ == "__main__":
    main()
