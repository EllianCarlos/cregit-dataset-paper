#!/usr/bin/env python3
"""S3 v2: measure again, or for the first time, a short list of other-host rows.

The same S3 method and code as the first pass: measure_clones.measure (a fetch
of one commit with depth 1, then `git ls-tree`, the same mask and vendor rule)
and clone_facts.facts (a fetch of the full history without blobs, then
`git rev-list --count` and the top-level license files). This script only
reads another input list and writes to this directory, so the first-pass files
and their sha256 files do not change.

Input: rows.tsv (pool_key, url, kind, head_oid, why). An empty head_oid means
"measure the default branch HEAD now" (the first-pass rule for other hosts).
A row with a head_oid and kind "facts-only" gets only the clone facts, at that
commit (for a row whose tree the first pass measured).

One row at a time, with a pause between rows (polite to small hosts).
Output: clones.jsonl, clone_facts.jsonl, run.log (with the git version and
the mask hash). Resumable: a pool_key with an ok row in the output is not done again; a failed
row stays in the file as a record. If a host refuses the pinned commit by SHA
("unadvertised object"), the facts come from a fetch of the default branch, and
the row records "fetch": "default-branch-head".

  TMPDIR=$HOME/s3-work python3 measure_v2.py [--pause 20]
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

V2 = Path(__file__).resolve().parent
sys.path.insert(0, str(V2.parent))
import clone_facts  # noqa: E402
import measure_clones  # noqa: E402
from measure_trees import CTP  # noqa: E402
from file_mask import UNIVERSAL_MASK  # noqa: E402


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def log(msg):
    line = f"{now()} {msg}"
    print(line, flush=True)
    with (V2 / "run.log").open("a") as f:
        f.write(line + "\n")


def facts_from_head(row):
    """clone_facts.facts, but fetch the default branch HEAD instead of the pinned
    commit. For a host that refuses a fetch by SHA ("unadvertised object") after
    its branch moved on. The count is still `git rev-list --count <pinned>`; the
    row fails if the pinned commit is not in the fetched history."""
    url, oid = row["repo_url"], row["head_oid"]
    out = {"pool_key": row["pool_key"], "head_oid": oid, "fetch": "default-branch-head"}
    d = Path(tempfile.mkdtemp(dir=measure_clones.WORK))
    try:
        measure_clones.git(["init", "-q", "--bare", str(d)])
        r = measure_clones.git(["fetch", "-q", "--filter=blob:none", url, "HEAD"], cwd=d)
        if r.returncode:
            return dict(out, status="fetch-failed", error=r.stderr.strip()[-300:])
        if measure_clones.git(["cat-file", "-e", f"{oid}^{{commit}}"], cwd=d).returncode:
            return dict(out, status="pinned-not-in-history")
        n = measure_clones.git(["rev-list", "--count", oid], cwd=d)
        ls = measure_clones.git(["ls-tree", "--name-only", oid], cwd=d)
        if n.returncode or ls.returncode:
            return dict(out, status="git-failed", error=(n.stderr + ls.stderr).strip()[-300:])
        lic = [x for x in ls.stdout.splitlines() if clone_facts.LICENSE.match(x)]
        return dict(out, status="ok", commits=int(n.stdout.strip()), license_files=lic)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def done_keys(path):
    return {d["pool_key"] for d in map(json.loads, path.open()) if d["status"] == "ok"} if path.exists() else set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pause", type=float, default=20)
    args = ap.parse_args()
    gitv = measure_clones.git(["--version"]).stdout.strip()
    mask_commit = subprocess.run(["git", "-C", str(CTP), "log", "-1", "--format=%H", "--", "file_mask.py"],
                                 capture_output=True, text=True).stdout.strip()
    log(f"start: {gitv}; mask sha256 {hashlib.sha256(UNIVERSAL_MASK.encode()).hexdigest()[:16]}, "
        f"file_mask.py at {mask_commit}")
    measure_clones.WORK.mkdir(exist_ok=True)
    rows = list(csv.DictReader(open(V2 / "rows.tsv"), delimiter="\t"))
    cl_out, cf_out = V2 / "clones.jsonl", V2 / "clone_facts.jsonl"
    cl_done, cf_done = done_keys(cl_out), done_keys(cf_out)
    for r in rows:
        key = r["pool_key"]
        head = r["head_oid"]
        if r["kind"] != "facts-only" and key not in cl_done:
            res = measure_clones.measure({"pool_key": key, "url": r["url"], "kind": r["kind"], "head_oid": head})
            res["fetched_at"], res["why"] = now(), r["why"]
            with cl_out.open("a") as f:
                f.write(json.dumps(res) + "\n")
            log(f"clone {key} {r['url']}: {res['status']}")
            if res["status"] != "ok":
                time.sleep(args.pause)
                continue
            head = res["head_oid"]
            time.sleep(args.pause)
        elif r["kind"] != "facts-only":
            last = [json.loads(l) for l in cl_out.open() if json.loads(l)["pool_key"] == key][-1]
            if last["status"] != "ok":
                continue
            head = last["head_oid"]
        if key in cf_done:
            continue
        res = clone_facts.facts({"pool_key": key, "repo_url": r["url"], "head_oid": head})
        if res["status"] == "fetch-failed" and "unadvertised object" in res.get("error", ""):
            log(f"facts {key}: the host refuses the pinned commit by SHA; fetching the default branch")
            res = facts_from_head({"pool_key": key, "repo_url": r["url"], "head_oid": head})
        res["fetched_at"], res["why"] = now(), r["why"]
        with cf_out.open("a") as f:
            f.write(json.dumps(res) + "\n")
        log(f"facts {key}: {res['status']} {res.get('commits', '')} {res.get('error', '')[-120:]}")
        time.sleep(args.pause)
    log("end")


if __name__ == "__main__":
    main()
