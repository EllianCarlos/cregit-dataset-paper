"""Blame the token files of one project with plain git blame (no -C, no -M).

The cregit repository of the pilot run holds one token per line (token file
line = token_index + 1). TOM blames these files with -C100. A plain blame of
the same files splits the effect of the token unit from the effect of the move
and copy search. Commits are mapped back to the original commits with the
commitmap of the cregit database. With --verify, also run -C100 (the TOM
blame) as a check of the join.

    nice -n 19 python3 -I blame_tokens.py --project tio__tio --jobs 4 [--verify]
"""
import argparse
import concurrent.futures as cf
import gzip
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blame_lines import HERE, SCRATCH, parse_porcelain  # noqa: E402


def blame(repo, path, opts):
    r = subprocess.run(["git", "-C", str(repo), "blame", *opts, "--porcelain", "HEAD", "--", path],
                       capture_output=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"{path}: " + r.stderr.decode("utf-8", "replace")[:200])
    return parse_porcelain(r.stdout)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    p = a.project
    w = SCRATCH / "out-local" / p
    repo = w / f"{p}-cregit.git"
    cm = dict(sqlite3.connect(w / f"{p}-cregit.db").execute("SELECT cid, originalcid FROM commitmap"))
    tom = SCRATCH / "hf-tom" / "parquet" / f"{p}-dataset.parquet"
    files = [r[0] for r in duckdb.connect().execute(
        "SELECT DISTINCT file_path FROM read_parquet(?) ORDER BY 1", [str(tom)]).fetchall()]
    out = HERE / "work" / p
    t0 = time.time()
    errors = 0

    def one(f):
        res = {"tp": blame(repo, f, [])}
        if a.verify:
            res["c100"] = blame(repo, f, ["-C100"])
        return f, res

    with gzip.open(out / "tokblame.tsv.gz", "wt") as fo, cf.ThreadPoolExecutor(a.jobs) as ex:
        fo.write("file_path\ttoken_index\tsha_tp\tsha_c100\n")
        for fu in cf.as_completed([ex.submit(one, f) for f in files]):
            try:
                f, res = fu.result()
            except Exception as e:  # noqa: BLE001
                errors += 1
                print("ERROR", p, e, file=sys.stderr)
                continue
            tp = res["tp"]
            c1 = res.get("c100") or [""] * len(tp)
            for i, s in enumerate(tp):
                fo.write(f"{f}\t{i}\t{cm.get(s, s)}\t{cm.get(c1[i], c1[i])}\n")
    with open(out / "tokblame-meta.tsv", "w") as fm:
        fm.write("project\tfiles\terrors\twall_s\tverify\n")
        fm.write(f"{p}\t{len(files)}\t{errors}\t{time.time() - t0:.1f}\t{int(a.verify)}\n")
    print(f"{p}: token blame {len(files)} files, {errors} errors, {time.time() - t0:.0f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
