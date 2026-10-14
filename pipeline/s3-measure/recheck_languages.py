#!/usr/bin/env python3
"""S3: re-check the language list of the rows where it can be cut short.

S1 and S2 read `languages(first: 20)`, the 20 largest languages of each
repository. A row that lists 20 languages and none of C, C++, Java or Rust can
have a target language below the cut. This script reads the full list
(`first: 100`) for those rows.

Output: languages_recheck.jsonl, one row for each re-checked repository:
name_with_owner, total language count, full language bytes, target bytes,
fetched_at. measure_trees.py also measures a row that has target bytes here.
"""
import csv
import datetime as dt
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET_LANGS = {"C", "C++", "Java", "Rust"}


def main():
    rows = [r for r in csv.DictReader(open(HERE.parent / "s2-pool/pool.csv", encoding="utf-8"))
            if r["host"] == "github.com" and r["head_oid"]
            and len(json.loads(r["languages"] or "{}")) >= 20
            and not TARGET_LANGS & set(json.loads(r["languages"]))]
    out = []
    for k in range(0, len(rows), 25):
        batch = rows[k:k + 25]
        parts = []
        for i, r in enumerate(batch):
            o, n = r["name_with_owner"].split("/", 1)
            parts.append(f"r{i}: repository(owner: {json.dumps(o)}, name: {json.dumps(n)}) "
                         "{ nameWithOwner languages(first: 100) { totalCount edges { size node { name } } } }")
        q = "query { " + " ".join(parts) + " }"
        d = json.loads(subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"],
                                      capture_output=True, text=True, check=True).stdout)
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        for i, r in enumerate(batch):
            x = d["data"][f"r{i}"]
            langs = {e["node"]["name"]: e["size"] for e in x["languages"]["edges"]}
            out.append({"name_with_owner": r["name_with_owner"], "total_languages": x["languages"]["totalCount"],
                        "languages": langs, "target_bytes": {k2: v for k2, v in langs.items() if k2 in TARGET_LANGS},
                        "fetched_at": now})
    with (HERE / "languages_recheck.jsonl").open("w") as f:
        for o in out:
            f.write(json.dumps(o) + "\n")
    print(f"{len(out)} rows re-checked, {sum(1 for o in out if o['target_bytes'])} with target bytes")


if __name__ == "__main__":
    main()
