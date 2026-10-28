#!/usr/bin/env python3
"""Write dataset v1-raw: one Parquet per project, with the final metadata and the v1 encoding.

    final_merge.py --inputs inputs.tsv --sidecar project_meta.v1.final.json --work DIR --out DIR
                   --src SRC --dest DEST --validate-schema PY [--jobs 16] [--threads 4] [--memory-limit 24GB]
                   [--only NAME ...] [--limit N]

This is task 6 (PLAN.md B1), stage 1 of the user decision of 2026-10-16: v1-raw keeps the real
names and e-mail addresses and stays private; v1-public (pseudonymized) comes later from v1-raw.

inputs.tsv (~/s3-work/dataset-v1/build_inputs.py) has one row per project: the run file that
prelim_merge.py chose, its key and its sha256. For each project, largest first:
  1. copy SRC/<key> to WORK and check the sha256;
  2. rewrite_meta_columns.py --encoding v1 --out OUT/parquet/<p>-dataset.parquet (the 11 metadata
     columns from the sidecar, the Savannah owner rule; it compares every other column row by row);
  3. validate_schema.py (the 70-column contract) on the output;
  4. copy the output to DEST/parquet/ and check the size;
  5. append one row to OUT/results.tsv and delete the work copy.
A project with a row in results.tsv is done, so a second start continues. The file OUT/STOP stops
the start of new projects. At the end (all done): OUT/SHA256SUMS and the copies of results.tsv,
the sidecar and its sha256 go to DEST.

SRC and DEST are an s3:// prefix (the aws CLI with the machine role) or a local directory (tests).
Exit 0 all done, 1 some failed, 2 usage or a bad input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULT_COLS = ("project", "source", "cregit", "input_key", "input_sha256", "output", "output_sha256",
               "rows", "input_bytes", "output_bytes", "seconds", "finished_utc", "detail")
LOCK = threading.Lock()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def is_s3(where: str) -> bool:
    return where.startswith("s3://")


def fetch(src: str, key: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if is_s3(src):
        subprocess.run(["aws", "s3", "cp", f"{src.rstrip('/')}/{key}", str(dst), "--only-show-errors"],
                       check=True)
    else:
        shutil.copyfile(Path(src) / key, dst)


def put(path: Path, dest: str, key: str) -> int:
    """Copy path to DEST/key. Returns the size that DEST reports."""
    if is_s3(dest):
        url = f"{dest.rstrip('/')}/{key}"
        subprocess.run(["aws", "s3", "cp", str(path), url, "--only-show-errors"], check=True)
        out = subprocess.run(["aws", "s3", "ls", url], check=True, capture_output=True, text=True).stdout
        return int(out.split()[2])
    target = Path(dest) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    return target.stat().st_size


def done_projects(results: Path) -> set[str]:
    if not results.is_file():
        return set()
    with open(results, newline="") as fh:
        return {r["project"] for r in csv.DictReader(fh, delimiter="\t")}


def append_result(results: Path, row: dict) -> None:
    with LOCK:
        new = not results.is_file()
        with open(results, "a", newline="") as fh:
            w = csv.DictWriter(fh, RESULT_COLS, delimiter="\t", lineterminator="\n")
            if new:
                w.writeheader()
            w.writerow(row)


def log(msg: str) -> None:
    with LOCK:
        print(f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}", flush=True)


def one(row: dict, a) -> bool:
    p, t0 = row["project"], time.time()
    work = a.work / p
    src = work / f"{p}-dataset.parquet"
    out = a.out / "parquet" / f"{p}-dataset.parquet"
    try:
        if out.exists():  # a crash after the rewrite: write it again
            out.unlink()
        fetch(a.src, row["s3_key"], src)
        got = sha256(src)
        if got != row["sha256"]:
            raise RuntimeError(f"input sha256 {got} is not {row['sha256']}")
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, "-I", str(a.rewrite), str(src), "--sidecar", str(a.sidecar),
                            "--key", p, "--out", str(out), "--encoding", "v1",
                            "--memory-limit", a.memory_limit, "--threads", str(a.threads),
                            "--report", str(a.out / "rewrite.tsv")], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"rewrite rc {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}")
        detail = r.stdout.strip().splitlines()[-1][-300:] if r.stdout.strip() else ""
        v = subprocess.run([sys.executable, "-I", str(a.validate_schema), str(out)],
                           capture_output=True, text=True)
        if v.returncode != 0:
            raise RuntimeError(f"validate_schema rc {v.returncode}: {(v.stderr or v.stdout).strip()[-400:]}")
        rows = rows_of(out)
        if rows != int(row["token_rows"]):
            raise RuntimeError(f"{rows} rows, inputs.tsv says {row['token_rows']}")
        osha, isize, osize = sha256(out), src.stat().st_size, out.stat().st_size
        size = put(out, a.dest, f"parquet/{out.name}")
        if size != osize:
            raise RuntimeError(f"DEST size {size} is not {osize}")
        append_result(a.out / "results.tsv", {
            "project": p, "source": row["source"], "cregit": row["cregit"], "input_key": row["s3_key"],
            "input_sha256": got, "output": f"parquet/{out.name}", "output_sha256": osha, "rows": rows,
            "input_bytes": isize, "output_bytes": osize,
            "seconds": f"{time.time() - t0:.1f}",
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "detail": detail})
        shutil.rmtree(work, ignore_errors=True)
        log(f"OK {p}: {rows:,} rows, {isize} -> {osize} B, {time.time() - t0:.0f} s")
        return True
    except Exception as exc:  # one project fails, the others go on
        log(f"FAIL {p}: {exc}")
        with LOCK, open(a.out / "failed.tsv", "a") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\t{p}\t{str(exc)[:500]}\n")
        out.unlink(missing_ok=True)
        return False


def rows_of(path: Path) -> int:
    import duckdb
    con = duckdb.connect()
    try:
        return con.execute("SELECT sum(num_rows) FROM parquet_file_metadata(?)", [str(path)]).fetchone()[0]
    finally:
        con.close()


def finish(a, rows: list[dict]) -> bool:
    """When every project is in results.tsv: SHA256SUMS, then the copies to DEST."""
    done = done_projects(a.out / "results.tsv")
    if not {r["project"] for r in rows} <= done:
        return False
    with open(a.out / "results.tsv", newline="") as fh:
        res = sorted(csv.DictReader(fh, delimiter="\t"), key=lambda r: r["output"])
    with open(a.out / "SHA256SUMS", "w") as fh:
        for r in res:
            fh.write(f"{r['output_sha256']}  {r['output']}\n")
    shutil.copyfile(a.sidecar, a.out / a.sidecar.name)
    names = ["SHA256SUMS", "results.tsv", "rewrite.tsv", a.sidecar.name]
    if a.sidecar_sha.is_file():
        shutil.copyfile(a.sidecar_sha, a.out / a.sidecar_sha.name)
        names.append(a.sidecar_sha.name)
    for name in names:
        if (a.out / name).is_file():
            put(a.out / name, a.dest, name)
    log(f"DONE: {len(res)} projects; SHA256SUMS and results.tsv are in {a.dest}")
    return True


def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--inputs", type=Path, required=True)
    ap.add_argument("--sidecar", type=Path, required=True)
    ap.add_argument("--sidecar-sha", type=Path, help="default: SIDECAR.sha256")
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--src", required=True, help="s3:// prefix or directory of the input keys")
    ap.add_argument("--dest", required=True, help="s3:// prefix or directory for the outputs")
    ap.add_argument("--jobs", type=int, default=16)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--memory-limit", default="24GB")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--rewrite", type=Path, default=HERE / "rewrite_meta_columns.py")
    ap.add_argument("--validate-schema", type=Path, required=True,
                    help="validate_schema.py of ctp (the 70-column contract)")
    a = ap.parse_args(argv)
    a.sidecar_sha = a.sidecar_sha or a.sidecar.with_name(a.sidecar.name + ".sha256")
    return a


def main(argv=None) -> int:
    a = parse(argv)
    for f in (a.inputs, a.sidecar, a.rewrite, a.validate_schema):  # each must exist
        if not f.is_file():
            print(f"usage: {f} is not a file", file=sys.stderr)
            return 2
    if a.sidecar_sha.is_file():
        want = a.sidecar_sha.read_text().split()[0]
        if sha256(a.sidecar) != want:
            print(f"bad input: the sidecar sha256 is not {want}", file=sys.stderr)
            return 2
    with open(a.inputs, newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    if len({r["project"] for r in rows}) != len(rows):
        print("bad input: a project repeats in inputs.tsv", file=sys.stderr)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    a.work.mkdir(parents=True, exist_ok=True)
    done = done_projects(a.out / "results.tsv")
    todo = [r for r in rows if r["project"] not in done and (not a.only or r["project"] in a.only)]
    todo.sort(key=lambda r: -int(r["bytes"]))
    if a.limit:
        todo = todo[:a.limit]
    log(f"{len(rows)} projects, {len(done)} done, {len(todo)} to do; jobs {a.jobs}, threads {a.threads}, "
        f"memory {a.memory_limit}")
    ok = True
    with ThreadPoolExecutor(a.jobs) as ex:
        futures = []
        for r in todo:
            if (a.out / "STOP").exists():
                log("STOP file: no new projects")
                break
            futures.append(ex.submit(lambda r=r: (a.out / "STOP").exists() or one(r, a)))
        for f in futures:
            ok = f.result() and ok
    if not (a.only or a.limit):
        finish(a, rows)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
