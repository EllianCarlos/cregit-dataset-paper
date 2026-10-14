#!/usr/bin/env python3
"""publish_done.py L: copy each finished project of census-local-b into the done/ layout of S3.

Made from census-fed-upload (the spot uploader) on 2026-10-11. It copies to this machine, not to S3.
A project is finished when its last final ledger row ("project") says done or done-dirty and its
.validated stamp exists. For each finished project without L/<wl>/<part>/done/<name>/OK it copies
OUT/<name>/<name>-dataset.parquet, OUT/<name>/<name>.validated, ctp state/<name>/*.json and
state/<name>/logs/* (regular files) and a ledger.jsonl snapshot into a temp dir next to the target,
then renames the temp dir to done/<name>/ and writes OK last. The OK file starts with the line
"<sha256>  <name>-dataset.parquet" (the format that fetch_done.sh and sha256sum -c read), then the
time, host, part and one "<size>\t<file>" line per file.
The project -> part map comes from the part manifests L/input/<wl>/manifest.<wl><part>.tsv of the
parts in L/parts.taken (one "<wl> <part>" per line).
"""
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def part_map(L):
    m = {}
    for line in (L / "parts.taken").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        wl, part = line.split()
        for row in (L / "input" / wl / f"manifest.{wl}{part}.tsv").read_text().splitlines():
            if row.strip() and not row.startswith("#"):
                m[row.split("\t")[0]] = (wl, part)
    return m


def finished(ctp):
    final = {}
    try:
        with (ctp / "ledger.jsonl").open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("step") == "project" and r.get("project"):
                    final[r["project"]] = r.get("state")
    except OSError:
        return []
    return [p for p, s in final.items() if s in ("done", "done-dirty")]


def publish(L, ctp, out, name, wl, part):
    done = L / wl / part / "done"
    dest = done / name
    if (dest / "OK").is_file():
        return None
    pq = out / name / f"{name}-dataset.parquet"
    stamp = out / name / f"{name}.validated"
    if not (pq.is_file() and stamp.is_file()):
        return f"{wl}{part} {name}: Parquet or stamp missing, later"
    done.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=done))
    try:
        for f in (pq, stamp):
            shutil.copy2(f, tmp / f.name)
        st = ctp / "state" / name
        (tmp / "state" / "logs").mkdir(parents=True)
        for f in st.glob("*.json"):
            if f.is_file() and not f.is_symlink():
                shutil.copy2(f, tmp / "state" / f.name)
        for f in (st / "logs").glob("*"):
            if f.is_file() and not f.is_symlink():
                shutil.copy2(f, tmp / "state" / "logs" / f.name)
        shutil.copy2(ctp / "ledger.jsonl", tmp / "ledger.jsonl")
        h = sha256(tmp / pq.name)
        if h != sha256(pq):
            return f"{wl}{part} {name}: Parquet changed during the copy, later"
        files = {str(p.relative_to(tmp)): p.stat().st_size for p in tmp.rglob("*") if p.is_file()}
        if dest.exists():  # a dir without OK: an earlier pass stopped; keep it aside
            dest.rename(done / f".{name}.partial.{int(time.time())}")
        tmp.rename(dest)
        tmp = None
        ok = (f"{h}  {pq.name}\n"
              f"copied {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} on {socket.gethostname()}"
              f" part {wl}{part} (census-local-b)\n"
              f"parquet_sha256 {h}\n"
              + "".join(f"{v}\t{k}\n" for k, v in sorted(files.items())))
        (dest / "OK.tmp").write_text(ok)
        os.replace(dest / "OK.tmp", dest / "OK")
        return f"{wl}{part} {name}: {len(files)} files, OK written"
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    L = Path(sys.argv[1]).resolve()
    ctp, out = L / "ctp", L / "out"
    pm = part_map(L)
    for name in finished(ctp):
        if name not in pm:
            print(time.strftime("%FT%TZ", time.gmtime()), f"{name}: not in a taken part, skipped", flush=True)
            continue
        try:
            msg = publish(L, ctp, out, name, *pm[name])
        except OSError as x:
            msg = f"{name}: copy error {x}, will retry"
        if msg:
            print(time.strftime("%FT%TZ", time.gmtime()), msg, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
