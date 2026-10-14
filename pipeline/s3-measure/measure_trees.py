#!/usr/bin/env python3
"""S3, tree pass: measure each GitHub pool repository at its pinned HEAD commit.

Input: ../s2-pool/pool.csv. A row is measured if its host is github.com, it has
a head_oid, and its Linguist bytes (column languages) include C, C++, Java or
Rust, or languages_recheck.jsonl (recheck_languages.py) finds target bytes below
the cut of 20 languages. The other rows get no tree call; stage S4 records why they leave.

One REST call for each repository: GET /repos/{owner}/{repo}/git/trees/{head_oid}?recursive=1.
The tree is the tree of the commit that S1 or S2 recorded, so the measurement
belongs to that commit and not to a later HEAD.

For each repository: total blob bytes; bytes by extension; vendored bytes by
extension; bytes and blobs that the universal mask selects. Code bytes are
derived later from bytes by extension (prog_exts.py, Linguist commit 538da05f).
A truncated tree is marked; its Linguist bytes from S1/S2 are the fallback.

Output: trees.jsonl (one row for each repository, with fetched_at), run.log.
Resumable.
"""
import csv
import datetime as dt
import http.client
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CTP = Path.home() / "Projects/cregit-token-pipeline"
sys.path.insert(0, str(CTP))
from file_mask import UNIVERSAL_MASK  # noqa: E402

MASK = re.compile(UNIVERSAL_MASK)
VENDOR = re.compile(r"(^|/)(vendor|vendored|third_party|third-party|thirdparty|3rdparty|external|deps)/", re.I)
TARGET_LANGS = {"C", "C++", "Java", "Rust"}
TOKEN = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()


def log(msg):
    line = f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    with (HERE / "run.log").open("a") as f:
        f.write(line + "\n")


def get(path):
    req = urllib.request.Request(f"https://api.github.com/{path}", headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"})
    for _ in range(10):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            limited = e.headers.get("X-RateLimit-Remaining") == "0" or e.headers.get("Retry-After")
            if e.code == 429 or (e.code == 403 and limited):
                # A 403 with quota left and no Retry-After is the repository's own status
                # (for example, access blocked by GitHub). It is recorded, not retried.
                if e.headers.get("X-RateLimit-Remaining") == "0":
                    wait = int(e.headers.get("X-RateLimit-Reset", time.time() + 60)) - time.time() + 5
                else:
                    wait = int(e.headers.get("Retry-After", 60))
                log(f"rate limited, sleeping {int(wait)}s")
                time.sleep(max(wait, 5))
                continue
            if e.code in (500, 502, 503, 504):
                log(f"HTTP {e.code} on {path}, retry in 30s")
                time.sleep(30)
                continue
            return e.code, None
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as e:
            log(f"network error {e}, retry in 30s")
            time.sleep(30)
    return 599, None


def measure(nwo, oid):
    status, tree = get(f"repos/{nwo}/git/trees/{oid}?recursive=1")
    out = {"name_with_owner": nwo, "head_oid": oid, "status": status}
    if status != 200:
        return out
    total = tok = tok_vendor = n_blobs = n_tok = 0
    by_ext, vendor_by_ext = {}, {}
    for e in tree["tree"]:
        if e["type"] != "blob":
            continue
        size = e.get("size", 0)
        total += size
        n_blobs += 1
        name = e["path"].rsplit("/", 1)[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name[1:] else ""
        by_ext[ext] = by_ext.get(ext, 0) + size
        vend = bool(VENDOR.search(e["path"]))
        if vend:
            vendor_by_ext[ext] = vendor_by_ext.get(ext, 0) + size
        if MASK.search(e["path"]):
            tok += size
            n_tok += 1
            if vend:
                tok_vendor += size
    out.update(tree_sha=tree["sha"], truncated=tree["truncated"], total_bytes=total, n_blobs=n_blobs,
               tok_bytes=tok, n_tok=n_tok, tok_vendor_bytes=tok_vendor, by_ext=by_ext, vendor_by_ext=vendor_by_ext)
    return out


def main():
    recheck = HERE / "languages_recheck.jsonl"
    extra = {d["name_with_owner"] for d in map(json.loads, recheck.open()) if d["target_bytes"]} if recheck.exists() else set()
    rows = [r for r in csv.DictReader(open(HERE.parent / "s2-pool/pool.csv", encoding="utf-8"))
            if r["host"] == "github.com" and r["head_oid"]
            and (TARGET_LANGS & set(json.loads(r["languages"] or "{}")) or r["name_with_owner"] in extra)]
    out = HERE / "trees.jsonl"
    done = {json.loads(l)["name_with_owner"] for l in out.open()} if out.exists() else set()
    todo = [r for r in rows if r["name_with_owner"] not in done]
    mask_sha = hashlib.sha256(UNIVERSAL_MASK.encode()).hexdigest()
    ctp_head = subprocess.run(["git", "-C", str(CTP), "log", "-1", "--format=%H", "--", "file_mask.py"],
                              capture_output=True, text=True).stdout.strip()
    log(f"start: {len(rows)} rows to measure, {len(done)} done, {len(todo)} to go; "
        f"mask sha256 {mask_sha[:16]}, file_mask.py at {ctp_head}")
    with out.open("a") as f:
        for i, r in enumerate(todo, 1):
            d = measure(r["name_with_owner"], r["head_oid"])
            d["fetched_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            f.write(json.dumps(d) + "\n")
            f.flush()
            if i % 500 == 0:
                log(f"{i}/{len(todo)}")
    log("end")


if __name__ == "__main__":
    main()
