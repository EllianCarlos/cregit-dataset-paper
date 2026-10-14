#!/usr/bin/env python3
"""S2, second pass: the slugs that GraphQL did not find.

The GraphQL `repository(owner, name)` lookup does not follow a rename or a
transfer. The REST call GET /repos/{owner}/{repo} follows it (HTTP 301). For
each slug in resolve.jsonl with no result, this script:

1. calls the REST API and records the status and the canonical full_name;
2. if the REST call finds the repository, reads the canonical name with the
   same GraphQL lookup as resolve.py.

Output: resolve_rest.jsonl, one row for each slug: slug, rest_status,
rest_full_name, result (GraphQL fields or null), error, fetched_at.
Resumable.
"""
import datetime as dt
import json
import time
import urllib.error
import urllib.request

import resolve
from resolve import HERE, TOKEN, log


def rest(slug):
    req = urllib.request.Request(f"https://api.github.com/repos/{slug}", headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
    for _ in range(8):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.load(r).get("full_name")
        except urllib.error.HTTPError as e:
            limited = e.headers.get("X-RateLimit-Remaining") == "0" or e.headers.get("Retry-After")
            if e.code == 429 or (e.code == 403 and limited):
                if e.headers.get("X-RateLimit-Remaining") == "0":
                    wait = int(e.headers.get("X-RateLimit-Reset", time.time() + 60)) - time.time() + 5
                else:
                    wait = int(e.headers.get("Retry-After", 60))
                log(f"REST rate limited, sleeping {int(wait)}s")
                time.sleep(max(wait, 5))
                continue
            return e.code, None
        except (urllib.error.URLError, TimeoutError) as e:
            log(f"network error {e}, retry in 30s")
            time.sleep(30)
    raise RuntimeError("REST failed 8 times")


def main():
    rows = [json.loads(l) for l in (HERE / "resolve.jsonl").open()]
    missing = [r["slug"] for r in rows if not r["result"]]
    out = HERE / "resolve_rest.jsonl"
    done = {json.loads(l)["slug"] for l in out.open()} if out.exists() else set()
    todo = [s for s in missing if s not in done]
    log(f"rest pass: {len(missing)} slugs without a GraphQL result, {len(todo)} to go")
    with out.open("a") as f:
        for i, s in enumerate(todo, 1):
            status, full = rest(s)
            row = {"slug": s, "rest_status": status, "rest_full_name": full, "result": None, "error": None}
            if full:
                looked = resolve.lookup([full.lower()])[0]
                row["result"], row["error"] = looked["result"], looked["error"]
            row["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            f.write(json.dumps(row) + "\n")
            f.flush()
            if i % 250 == 0:
                log(f"rest pass {i}/{len(todo)}")
            time.sleep(0.2)
    log("rest pass end")


if __name__ == "__main__":
    main()
