#!/usr/bin/env python3
"""S3, clone pass: measure the rows that the tree pass cannot measure.

Two kinds of rows:
  1. Pool rows on other hosts (KDE, Eclipse GitLab, freedesktop, OpenDev, ...).
     They have no pinned commit yet. The pass clones the default branch with
     depth 1 and records its commit as the pinned commit (head_oid) of the row.
  2. GitHub rows whose tree the API cut short (truncated in trees.jsonl). They
     have a pinned commit; the pass fetches exactly that commit with depth 1.

For each row: `git ls-tree -r -l HEAD` gives every blob with its size. The
counts are the same as in measure_trees.py (same universal mask, same vendor
rule, bytes by extension). The clone is deleted after the count.

One clone at a time for each host other than github.com; after HTTP 429 the pass waits and tries
again. Rows that are not git (svn.apache.org, svn.code.sf.net, project web pages)
are recorded with their status and no measurement; stage S4 records why they
leave. Output: clones.jsonl (one row for each repository, with fetched_at),
run.log. Clones go to $TMPDIR/s3-clones; finish_s3.sh sets TMPDIR to a disk
directory, because /tmp is a RAM disk here. Resumable: a row that is in clones.jsonl is not cloned again.
"""
import contextlib
import csv
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from measure_trees import MASK, VENDOR  # noqa: E402  (the same rules as the tree pass)

WORK = Path(tempfile.gettempdir()) / "s3-clones"
HOST_LOCKS = defaultdict(threading.Lock)  # one clone at a time for each host, except GitHub
NOT_GIT = ("svn.apache.org", "svn.code.sf.net", "svn.osgeo.org", "dist.apache.org")


def log(msg):
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} clones: {msg}"
    print(line, flush=True)
    with (HERE / "run.log").open("a") as f:
        f.write(line + "\n")


def git(args, cwd=None, timeout=3600):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout,
                          env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:" + str(Path.home() / ".nix-profile/bin")})


def count(listing):
    total = tok = tok_vendor = n_blobs = n_tok = 0
    by_ext, vendor_by_ext = {}, {}
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        mode, typ, _sha, size = meta.split()
        if typ != "blob" or size == "-":
            continue
        size = int(size)
        total += size
        n_blobs += 1
        name = path.rsplit("/", 1)[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name[1:] else ""
        by_ext[ext] = by_ext.get(ext, 0) + size
        vend = bool(VENDOR.search(path))
        if vend:
            vendor_by_ext[ext] = vendor_by_ext.get(ext, 0) + size
        if MASK.search(path):
            tok += size
            n_tok += 1
            if vend:
                tok_vendor += size
    return dict(total_bytes=total, n_blobs=n_blobs, tok_bytes=tok, n_tok=n_tok, tok_vendor_bytes=tok_vendor,
                by_ext=by_ext, vendor_by_ext=vendor_by_ext)


def measure(row):
    key, url, oid = row["pool_key"], row["url"], row.get("head_oid") or None
    out = {"pool_key": key, "repo_url": url, "kind": row["kind"], "pinned_before": oid}
    host = url.split("://", 1)[-1].split("/", 1)[0]
    if host in NOT_GIT or "/svn/" in url:
        return dict(out, status="not-git")
    d = Path(tempfile.mkdtemp(dir=WORK))
    try:
        r = git(["init", "-q", "--bare", str(d)])
        for attempt in range(6):
            with HOST_LOCKS[host] if host != "github.com" else contextlib.nullcontext():
                r = git(["fetch", "-q", "--depth", "1", url, oid or "HEAD"], cwd=d)
            if r.returncode and "error: 429" in r.stderr:
                time.sleep(60 * (attempt + 1))  # the host asks us to slow down
                continue
            break
        if r.returncode:
            return dict(out, status="clone-failed", error=r.stderr.strip()[-300:])
        head = git(["rev-parse", "FETCH_HEAD"], cwd=d).stdout.strip()
        ls = git(["ls-tree", "-r", "-l", "--full-tree", head], cwd=d)
        if ls.returncode:
            return dict(out, status="ls-tree-failed", error=ls.stderr.strip()[-300:])
        return dict(out, status="ok", head_oid=head, **count(ls.stdout))
    except subprocess.TimeoutExpired:
        return dict(out, status="timeout")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    WORK.mkdir(exist_ok=True)
    rows = []
    for r in csv.DictReader(open(HERE.parent / "s2-pool/pool.csv", encoding="utf-8")):
        if r["host"] != "github.com":
            rows.append({"pool_key": r["pool_key"], "url": r["repo_url"], "kind": "other-host"})
    pool = {r["name_with_owner"]: r for r in csv.DictReader(open(HERE.parent / "s2-pool/pool.csv", encoding="utf-8"))
            if r["host"] == "github.com"}
    for l in open(HERE / "trees.jsonl"):
        t = json.loads(l)
        if t.get("truncated") and t["name_with_owner"] in pool:
            p = pool[t["name_with_owner"]]
            rows.append({"pool_key": p["pool_key"], "url": f"https://github.com/{t['name_with_owner']}.git",
                         "kind": "github-truncated", "head_oid": t["head_oid"]})
    out = HERE / "clones.jsonl"
    # A row that failed only because the host asked us to slow down (HTTP 429)
    # is measured again; its earlier row stays in the file as a record.
    done = set()
    if out.exists():
        for l in out.open():
            d = json.loads(l)
            if not (d["status"] == "clone-failed" and "error: 429" in d.get("error", "")):
                done.add(d["pool_key"])
    todo = [r for r in rows if r["pool_key"] not in done]
    log(f"start: {len(rows)} rows, {len(done)} done, {len(todo)} to go")
    n = 0
    with out.open("a") as f, ThreadPoolExecutor(4) as ex:
        for res in ex.map(measure, todo):
            res["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            f.write(json.dumps(res) + "\n")
            f.flush()
            n += 1
            if n % 100 == 0:
                log(f"{n}/{len(todo)}")
    log("end")


if __name__ == "__main__":
    main()
