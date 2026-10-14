#!/usr/bin/env python3
"""S3 facts for other-host rows: the commit count and the license files.

GitHub gives these two facts for GitHub rows (commits.jsonl, the pool column
license). Other hosts give neither, so this pass reads them from git, for each
row that measure_clones.py measured (status ok, kind other-host):
  - commits: `git rev-list --count <head_oid>`, from a fetch of the full history
    of the pinned commit without file contents (--filter=blob:none);
  - license_files: the top-level files whose name starts with LICENSE, LICENCE,
    COPYING or UNLICENSE (case-insensitive), from `git ls-tree --name-only`.
One fetch at a time for each host; after HTTP 429 the pass waits and tries
again. Output: clone_facts.jsonl (pool_key, head_oid, commits, license_files,
status, fetched_at). Resumable.
"""
import datetime as dt
import json
import re
import shutil
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from measure_clones import HERE, WORK, git, log

LICENSE = re.compile(r"^(licen[cs]e|copying|unlicense)", re.I)
HOST_LOCKS = defaultdict(threading.Lock)


def facts(row):
    url, oid = row["repo_url"], row["head_oid"]
    host = url.split("://", 1)[-1].split("/", 1)[0]
    out = {"pool_key": row["pool_key"], "head_oid": oid}
    d = Path(tempfile.mkdtemp(dir=WORK))
    try:
        git(["init", "-q", "--bare", str(d)])
        for attempt in range(6):
            with HOST_LOCKS[host]:
                r = git(["fetch", "-q", "--filter=blob:none", url, oid], cwd=d)
            if r.returncode and "error: 429" in r.stderr:
                time.sleep(60 * (attempt + 1))
                continue
            break
        if r.returncode:
            return dict(out, status="fetch-failed", error=r.stderr.strip()[-300:])
        n = git(["rev-list", "--count", oid], cwd=d)
        ls = git(["ls-tree", "--name-only", oid], cwd=d)
        if n.returncode or ls.returncode:
            return dict(out, status="git-failed", error=(n.stderr + ls.stderr).strip()[-300:])
        lic = [x for x in ls.stdout.splitlines() if LICENSE.match(x)]
        return dict(out, status="ok", commits=int(n.stdout.strip()), license_files=lic)
    except Exception as e:  # a timeout or a git crash is recorded, not fatal
        return dict(out, status="error", error=str(e)[-300:])
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    WORK.mkdir(exist_ok=True)
    rows = {}
    for l in open(HERE / "clones.jsonl"):
        c = json.loads(l)
        if c["kind"] == "other-host" and c["status"] == "ok":
            rows[c["pool_key"]] = c
    out = HERE / "clone_facts.jsonl"
    done = {json.loads(l)["pool_key"] for l in out.open()} if out.exists() else set()
    todo = [c for k, c in rows.items() if k not in done]
    log(f"facts start: {len(rows)} rows, {len(done)} done, {len(todo)} to go")
    with out.open("a") as f, ThreadPoolExecutor(4) as ex:
        for i, res in enumerate(ex.map(facts, todo), 1):
            res["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            f.write(json.dumps(res) + "\n")
            f.flush()
            if i % 100 == 0:
                log(f"facts {i}/{len(todo)}")
    log("facts end")


if __name__ == "__main__":
    main()
