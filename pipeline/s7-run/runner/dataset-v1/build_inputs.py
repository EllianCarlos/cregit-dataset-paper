#!/usr/bin/env python3
"""Build inputs.tsv: one row per v1 project chosen by prelim.duckdb, with the S3 key spot a reads.

cloud rows: the run key (the S3 layout of census-cloud), sha256 from census-cloud/verified.tsv.
fixed and local-a..d rows: a new key under dataset-v1/inputs/ (the user uploads them), sha256 computed here
and, for fixed, compared with census-cloud-fixed/manifest.tsv. local-e: the firm-fast key, sha256 known.
Also writes upload.tsv (local path -> key) for the user's upload script.
"""
import csv, hashlib, os, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import duckdb

W = Path.home() / "Projects/cregit-workspace"
OUT = Path(__file__).resolve().parent
FAST = {"gnuton__asuswrt-merlin.ng": ("firm-fast/20261016/gnuton__asuswrt-merlin.ng/gnuton__asuswrt-merlin.ng-dataset.parquet",
                                      "2a22ad47d3e5840b63664c423c87a66e4f50f5fc29677558217b5e48402cce38")}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def main():
    con = duckdb.connect(str(W / "merge-prelim/prelim.duckdb"), read_only=True)
    rows = con.execute("SELECT project, source, run, path, cregit, token_rows FROM projects ORDER BY project").fetchall()
    verified = {}
    for line in open(W / "census-cloud/verified.tsv"):
        f = line.rstrip("\n").split("\t")
        verified[f[1]] = f[2]
    fixed_sha = {}
    with open(W / "census-cloud-fixed/manifest.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["status"] == "ok":
                fixed_sha[r["rel_path"]] = r["output_sha256"]
    out, todo = [], []
    for project, source, run, path, cregit, n in rows:
        p = Path(path)
        if source == "cloud":
            rel = str(p.parent.relative_to(W / "census-cloud"))
            out.append([project, source, cregit, n, p.stat().st_size, str(p.relative_to(W / "census-cloud")), verified[rel], ""])
        elif source == "local-e":
            key, sha = FAST[project]
            out.append([project, source, cregit, n, p.stat().st_size, key, sha, ""])
        else:
            root = W / ("census-cloud-fixed" if source == "fixed" else f"census-{source}")
            rel = p.relative_to(root)
            key = f"dataset-v1/inputs/{source}/{rel}"
            want = fixed_sha.get(str(rel.parent)) if source == "fixed" else ""
            out.append([project, source, cregit, n, p.stat().st_size, key, want, str(p)])
            todo.append(len(out) - 1)
    with ProcessPoolExecutor(8) as ex:
        for i, got in zip(todo, ex.map(sha256, [out[i][7] for i in todo], chunksize=4)):
            want = out[i][6]
            if want and want != got:
                sys.exit(f"SHA256 DIFFERS: {out[i][0]} {out[i][7]} manifest {want} file {got}")
            out[i][6] = got
    with open(OUT / "inputs.tsv", "w") as fh:
        fh.write("project\tsource\tcregit\ttoken_rows\tbytes\ts3_key\tsha256\n")
        for r in out:
            fh.write("\t".join(map(str, r[:7])) + "\n")
    with open(OUT / "upload.tsv", "w") as fh:
        for r in out:
            if r[7]:
                fh.write(f"{r[7]}\t{r[5]}\t{r[6]}\n")
    up = [r for r in out if r[7]]
    print(f"inputs.tsv: {len(out)} rows, {sum(r[4] for r in out)/1e9:.1f} GB, {sum(r[3] for r in out):,} token rows")
    print(f"upload.tsv: {len(up)} files, {sum(r[4] for r in up)/1e9:.1f} GB (sha256 checked; fixed rows equal to the manifest)")


if __name__ == "__main__":
    main()
