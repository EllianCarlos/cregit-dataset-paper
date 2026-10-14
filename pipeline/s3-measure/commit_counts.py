#!/usr/bin/env python3
"""S3 fact: the commit count of each measured repository at its pinned commit.

Input: ../s2-pool/pool.csv, the same rows as measure_trees.py (GitHub, a
head_oid, a target language). For each row, GitHub GraphQL reads
repository(owner, name).object(oid: head_oid).history.totalCount: the number of
commits reachable from the pinned commit. A later push does not change it.
This is the fact for DP7 and for a commit-count filter.

The name is the resolved name from S2, so a rename does not lose the row (D3).
Batches of 50 repositories; after a 502 or 504 the batch is halved.

Output: commits.jsonl, one row for each repository: name_with_owner, head_oid,
commits (null if GitHub gives no answer), error, fetched_at. Log: run.log.
Resumable: a row that is in commits.jsonl is not read again.
"""
import csv
import datetime as dt
import http.client
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()
TARGET_LANGS = {"C", "C++", "Java", "Rust"}


def log(msg):
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} commits: {msg}"
    print(line, flush=True)
    with (HERE / "run.log").open("a") as f:
        f.write(line + "\n")


class TooHeavy(Exception):
    pass


def query(rows):
    parts = []
    for i, r in enumerate(rows):
        owner, name = r["name_with_owner"].split("/", 1)
        parts.append(f'r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) '
                     f'{{ object(oid: {json.dumps(r["head_oid"])}) {{ ... on Commit {{ history {{ totalCount }} }} }} }}')
    body = json.dumps({"query": "query { rateLimit { remaining resetAt } " + " ".join(parts) + " }"}).encode()
    for _ in range(8):
        req = urllib.request.Request("https://api.github.com/graphql", data=body, headers={
            "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                d = json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (502, 504) and len(rows) > 1:
                raise TooHeavy(e.code)
            wait = int(e.headers.get("Retry-After", 60)) if e.code in (403, 429) else 30
            log(f"HTTP {e.code}, retry in {wait}s")
            time.sleep(wait)
            continue
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
            if len(rows) > 1:
                raise TooHeavy(str(e))
            log(f"network error {e}, retry in 30s")
            time.sleep(30)
            continue
        data = d.get("data") or {}
        rl = data.get("rateLimit")
        if rl and rl["remaining"] < 100:
            wait = (dt.datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00"))
                    - dt.datetime.now(dt.timezone.utc)).total_seconds() + 5
            log(f"GraphQL quota low, sleeping {int(wait)}s")
            time.sleep(max(wait, 5))
        errors = {}
        for e in d.get("errors") or []:
            if e.get("path"):
                errors[e["path"][0]] = e.get("type") or e.get("message", "")[:80]
        time.sleep(0.5)
        out = []
        for i, r in enumerate(rows):
            node = data.get(f"r{i}")
            hist = ((node or {}).get("object") or {}).get("history")
            out.append({"name_with_owner": r["name_with_owner"], "head_oid": r["head_oid"],
                        "commits": hist["totalCount"] if hist else None,
                        "error": errors.get(f"r{i}") if not hist else None})
        return out
    raise RuntimeError("GraphQL failed 8 times")


def main():
    recheck = HERE / "languages_recheck.jsonl"
    extra = {d["name_with_owner"] for d in map(json.loads, recheck.open()) if d["target_bytes"]} if recheck.exists() else set()
    rows = [r for r in csv.DictReader(open(HERE.parent / "s2-pool/pool.csv", encoding="utf-8"))
            if r["host"] == "github.com" and r["head_oid"]
            and (TARGET_LANGS & set(json.loads(r["languages"] or "{}")) or r["name_with_owner"] in extra)]
    out = HERE / "commits.jsonl"
    done = {json.loads(l)["name_with_owner"] for l in out.open()} if out.exists() else set()
    todo = [r for r in rows if r["name_with_owner"] not in done]
    log(f"start: {len(rows)} rows, {len(done)} done, {len(todo)} to go")
    i, size, n = 0, 50, 0
    with out.open("a") as f:
        while i < len(todo):
            batch = todo[i:i + size]
            try:
                res = query(batch)
            except TooHeavy as e:
                size = max(1, size // 2)
                log(f"{e}, batch size now {size}")
                time.sleep(5)
                continue
            now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            for d in res:
                f.write(json.dumps(dict(d, fetched_at=now)) + "\n")
            f.flush()
            i += len(batch)
            n += len(batch)
            size = min(50, size * 2)
            if n >= 1000:
                log(f"{i}/{len(todo)}")
                n = 0
    log("end")


if __name__ == "__main__":
    main()
