#!/usr/bin/env python3
"""Fetch a list of web pages politely and keep each one as evidence.

One page at a time, a pause between pages, redirects followed. For each URL:
pages/<sha1 of the URL>.html (the bytes) and .headers, and one row in
fetch.tsv: utc, url, http status, final url, bytes, sha256 of the body, file.
A URL that is already in fetch.tsv with status 200 is not fetched again.

  python3 fetch_pages.py urls.txt [--pause 5] [--timeout 60]
"""
import argparse
import csv
import datetime as dt
import hashlib
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGES = HERE / "pages"
UA = "cregit-dataset-selection/1.0 (research; one request at a time)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls")
    ap.add_argument("--pause", type=float, default=5)
    ap.add_argument("--timeout", type=float, default=60)
    args = ap.parse_args()
    PAGES.mkdir(exist_ok=True)
    log = HERE / "fetch.tsv"
    done = set()
    if log.exists():
        done = {r["url"] for r in csv.DictReader(log.open(), delimiter="\t") if r["status"] == "200"}
    new = not log.exists()
    with log.open("a") as f:
        if new:
            f.write("utc\turl\tstatus\tfinal_url\tbytes\tsha256\tfile\n")
        for url in [u.strip() for u in open(args.urls) if u.strip()]:
            if url in done:
                continue
            name = hashlib.sha1(url.encode()).hexdigest()
            body, head = PAGES / f"{name}.html", PAGES / f"{name}.headers"
            t = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            p = subprocess.run(["curl", "-sL", "-m", str(args.timeout), "-A", UA, "-D", str(head), "-o", str(body),
                                "-w", "%{http_code}\t%{url_effective}", url], capture_output=True, text=True)
            status, final = (p.stdout.split("\t") + [""])[:2] if p.stdout else ("000", "")
            data = body.read_bytes() if body.exists() else b""
            f.write(f"{t}\t{url}\t{status}\t{final}\t{len(data)}\t{hashlib.sha256(data).hexdigest()}\t{body.name}\n")
            f.flush()
            print(t, status, url, flush=True)
            time.sleep(args.pause)


if __name__ == "__main__":
    main()
