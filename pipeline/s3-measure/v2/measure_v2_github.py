#!/usr/bin/env python3
"""S3 v2 for new GitHub pool rows (s2-pool/v2/pool.supplement.csv): the tree
call and the commit count, with the first-pass code (measure_trees.measure,
commit_counts.query) at the head_oid that the v2 lookup recorded. A tree that
GitHub cuts short is listed, not cloned here (none so far).

Output: trees.jsonl, commits.jsonl (with fetched_at), in this directory.
"""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

V2 = Path(__file__).resolve().parent
sys.path.insert(0, str(V2.parent))
import commit_counts  # noqa: E402
import measure_trees  # noqa: E402


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def main():
    rows = [r for r in csv.DictReader(open(V2.parents[1] / "s2-pool/v2/pool.supplement.csv", encoding="utf-8"))
            if r["host"] == "github.com" and r["head_oid"]]
    for r in rows:
        t = measure_trees.measure(r["name_with_owner"], r["head_oid"])
        t["fetched_at"] = now()
        with (V2 / "trees.jsonl").open("a") as f:
            f.write(json.dumps(t) + "\n")
        c = commit_counts.query([r])[0]
        c["fetched_at"] = now()
        with (V2 / "commits.jsonl").open("a") as f:
            f.write(json.dumps(c) + "\n")
        print(r["name_with_owner"], t["status"], t.get("truncated"), c["commits"])


if __name__ == "__main__":
    main()
