#!/usr/bin/env python3
"""Server of one page of the column audit (S8, 2026-10-26): the namespace part or the domain part.

    serve_columns.py [--port 8774] [--host 127.0.0.1]

audit_columns.py build copies this file into each part folder as serve_columns.py (the source is
s8-companies/review/audit_columns_serve.py). The audit hub (127.0.0.1:8767, mounts col-ns and
col-dom) imports its Handler.

GET  /, /audit.html                       the page
GET  /data/items.json, /data/meta.json    the items (made by audit_columns.py build)
GET  /answers.csv                         the saved answers (header only when there is none)
POST /answers.csv                         the page sends all its answers (CSV body); the server checks
                                          the rows, drops each value that holds an at sign, writes
                                          answers.csv (temp file, then rename) and keeps a copy in
                                          history/ at most every 10 minutes.
Every other path gives 404. Alone, the server binds to 127.0.0.1. Python standard library only.
Made after ../audit-tail/serve_tail.py.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import os
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLS = ["item_id", "part", "type", "title", "verdict", "correct_class", "wrong_part", "correct_org", "note",
        "carried", "answered_utc", "items_sha256"]
HEADER = ",".join(COLS)
VERDICTS = {"right", "wrong", "unsure", ""}
DATA_RE = re.compile(r"/data/(items|meta)\.json")
ITEM_RE = re.compile(r"[ND][0-9]{4}")
CLASSES = {"", "company", "other-organisation", "independent", "free-provider", "none", "project", "unknown"}
WRONG_PARTS = {"", "organisation", "kind"}
MAX_BODY = 16 * 1024 * 1024
AT = chr(64)
LAST_COPY = [0.0]
LOCK = threading.Lock()
GZ: dict[str, tuple[float, bytes]] = {}


def answers_path() -> Path:
    return HERE / "answers.csv"


def read_rows(text: str) -> list[dict]:
    return [r for r in csv.DictReader(io.StringIO(text)) if r.get("item_id")]


def drop_at(v: str | None) -> str:
    """A value with an at sign is dropped, never masked."""
    v = v or ""
    return "" if AT in v else v


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLS, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({c: drop_at(r.get(c)) for c in COLS})
    return buf.getvalue()


def check_rows(rows: list[dict]) -> str:
    """An error text, or '' when every row is valid."""
    for r in rows:
        if not ITEM_RE.fullmatch(r.get("item_id") or ""):
            return "bad item"
        if (r.get("verdict") or "") not in VERDICTS:
            return "bad verdict"
        if (r.get("correct_class") or "") not in CLASSES:
            return "bad class"
        if (r.get("wrong_part") or "") not in WRONG_PARTS:
            return "bad wrong part"
    return ""


class Handler(BaseHTTPRequestHandler):
    def send(self, code: int, body: bytes, ctype: str = "text/plain; charset=utf-8", gz: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if gz:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/audit.html"):
            return self.send(200, (HERE / "audit.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/answers.csv":
            p = answers_path()
            body = p.read_bytes() if p.is_file() else (HEADER + "\n").encode()
            return self.send(200, body, "text/csv; charset=utf-8")
        if DATA_RE.fullmatch(path):
            p = HERE / path[1:]
            if not p.is_file():
                return self.send(404, b"no data: run audit_columns.py build")
            if "gzip" in (self.headers.get("Accept-Encoding") or ""):
                m = p.stat().st_mtime
                hit = GZ.get(path)
                if not hit or hit[0] != m:
                    hit = (m, gzip.compress(p.read_bytes(), 6))
                    GZ[path] = hit
                return self.send(200, hit[1], "application/json", gz=True)
            return self.send(200, p.read_bytes(), "application/json")
        return self.send(404, b"not found")

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/answers.csv":
            return self.send(404, b"not found")
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BODY:
            return self.send(400, b"bad length")
        body = self.rfile.read(n).decode("utf-8")
        if not body.startswith(HEADER):
            return self.send(400, b"not an answers.csv of audit.html")
        rows = read_rows(body)
        err = check_rows(rows)
        if err:
            return self.send(400, err.encode())
        seen = {}
        for r in rows:
            seen[r["item_id"]] = r
        rows = sorted(seen.values(), key=lambda r: r["item_id"])
        with LOCK:
            p = answers_path()
            text = to_csv(rows)
            tmp = p.with_name(".answers.csv.tmp")
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, p)
            if time.time() - LAST_COPY[0] > 600:
                hist = HERE / "history"
                hist.mkdir(exist_ok=True)
                (hist / f"answers.{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.csv").write_text(text, encoding="utf-8")
                LAST_COPY[0] = time.time()
        return self.send(200, json.dumps({"saved": len(rows), "utc": time.strftime("%H:%M:%SZ", time.gmtime())}).encode(),
                         "application/json")

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {self.command} "
                         f"{self.path.split('?', 1)[0]} {args[1] if len(args) > 1 else ''}\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=8774)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args(argv)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"serving http://{a.host}:{a.port}/ (folder {HERE})", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
