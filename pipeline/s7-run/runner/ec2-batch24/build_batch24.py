#!/usr/bin/env python3
"""Build batch 24: the 32 L7-20b rows that census L7-20b had not started, as fed parts on spot b.

User decision 2026-10-13 ~12:35 UTC: move the not-started L7-20b rows to spot b (it had 17 of 20 workers
idle). /bL7b/ctp/STOP was written at 12:40:50 UTC (M1-freeze.sh); then 8 rows had a state dir in
/bL7b/ctp/state/ (STARTED below). This script reads the L7-20 v2 inputs (~/s3-work/ec2-L7-20/upload-v2/)
and writes ~/s3-work/ec2-batch24/upload/ (the 5 files for B/batch24/input/) and record/ (the part manifests,
made with the census-fed-derive part_text function, so their sha256 equals what the spot derives).
  manifest.batch24.tsv       the 32 rows, fields and order unchanged (L7-20 LPT order)
  project_meta.batch24.json  a byte copy of project_meta.L7-20.json (the L7-20b sidecar is the same copy)
  parts.batch24.tsv          5 parts b1-b5 on half b, 3 workers each, LPT by predicted hours
  parts.batch24.assign.tsv   workload, part, project
Refuses to overwrite.
"""
import hashlib
import importlib.machinery
import importlib.util
import re
import shutil
import sys
from pathlib import Path

H = Path.home() / "s3-work"
SRC = H / "ec2-L7-20/upload-v2"
OUT = Path(__file__).resolve().parent
UP, REC = OUT / "upload", OUT / "record"
WL, NPARTS, WORKERS = "batch24", 5, 3
STARTED = {"BrowserWorks__waterfox", "MotorolaMobilityLLC__kernel-msm", "aftermathlabs__llvm-msvc",
           "flang-compiler__classic-flang-llvm-project", "intel__llvm", "liferay__liferay-portal",
           "mozilla__enterprise-firefox", "openucx__ODOS"}
WANT = {"manifest.L7-20.tsv": "58af4ad6", "project_meta.L7-20.json": "28ddbccc"}

loader = importlib.machinery.SourceFileLoader("fed_derive", str(H / "ec2-batch6/scripts/remote-spot/census-fed-derive"))
spec = importlib.util.spec_from_loader("fed_derive", loader)
fd = importlib.util.module_from_spec(spec); loader.exec_module(fd)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    for f, pre in WANT.items():
        assert sha(SRC / f).startswith(pre), f"{f} sha256 differs from {pre}"
    names_out = [UP / n for n in (f"manifest.{WL}.tsv", f"project_meta.{WL}.json", f"parts.{WL}.tsv",
                                  f"parts.{WL}.assign.tsv", "SHA256SUMS")]
    for p in names_out:
        assert not p.exists(), f"{p} exists"
    src = SRC / "manifest.L7-20.tsv"
    text = src.read_text(encoding="utf-8")
    cols, rows = fd.read_manifest(src)
    pred = {}
    for line in text.splitlines():
        m = re.match(r"^#\s+([0-9.]+)\s+batch\d+\s+(\S+)\s*$", line)
        if m:
            pred[m.group(2)] = float(m.group(1))
    assert len(rows) == 56 and set(pred) == {fd.name(r) for r in rows}
    names = [fd.name(r) for r in rows]
    # L7-20b = rows 17-56; it starts rows in order, so the not-started rows are those after the last started one
    l720b = names[16:]
    assert l720b[0] == "BrowserWorks__waterfox" and l720b[-1] == "jlord__patchwork"
    last = max(l720b.index(n) for n in STARTED)
    assert set(l720b[:last + 1]) == STARTED, "the started rows are not a prefix of L7-20b"
    keep = [r for r in rows[16:] if fd.name(r) not in STARTED]
    assert len(keep) == 32 and fd.name(keep[0]) == "freebsd__freebsd-src"
    assert all(r.split("\t")[fd.CLASS_COL] == "L" for r in keep)
    # LPT: rows in decreasing predicted hours (the L7-20 order is already LPT) to the part with the least sum
    sums = {f"b{i}": 0.0 for i in range(1, NPARTS + 1)}
    assign = {p: [] for p in sums}
    for r in sorted(keep, key=lambda r: -pred[fd.name(r)]):
        p = min(sums, key=lambda k: (sums[k], k))
        sums[p] += pred[fd.name(r)]; assign[p].append(fd.name(r))

    def makespan(ns):  # list scheduling in manifest order with WORKERS workers (predicted, inferred)
        free = [0.0] * WORKERS
        for n in ns:
            i = free.index(min(free)); free[i] += pred[n]
        return max(free)

    order = [fd.name(r) for r in keep]
    man = UP / f"manifest.{WL}.tsv"
    total = sum(pred[n] for n in order)
    man.write_text(
        f"# Batch 24 (2026-10-13): the {len(keep)} rows of census L7-20b (big EC2) that it had not started when\n"
        f"# /bL7b/ctp/STOP was written (12:40:50 UTC, user decision: move them to spot b). Rows 25-56 of\n"
        f"# manifest.L7-20.tsv v2 (sha256 {sha(src)}), fields and order unchanged (LPT order).\n"
        f"# {len(keep)} projects, all L, {total:.1f} h predicted in total (inferred).\n"
        f"{cols}\n" + "".join(r + "\n" for r in keep), encoding="utf-8")
    shutil.copyfile(SRC / "project_meta.L7-20.json", UP / f"project_meta.{WL}.json")
    plines = []
    for p in sums:
        ns = set(assign[p]); h = f"{makespan([n for n in order if n in ns]):.1f}"
        t = fd.part_text(man, p, WORKERS, h, ns)
        (REC / f"manifest.{WL}{p}.tsv").write_text(t, encoding="utf-8")
        plines.append(f"b\t{WL}\t{p}\t{WORKERS}\t{len(ns)}\t{h}\t{hashlib.sha256(t.encode()).hexdigest()}")
    (UP / f"parts.{WL}.tsv").write_text(
        f"# Fed spot parts of {WL} (build_batch24.py): the 32 not-started L7-20b rows, all L, on spot half b only.\n"
        f"# LPT by predicted hours into {NPARTS} parts of {WORKERS} workers (3 L projects at once per 1200G image,\n"
        f"# floor 300G). predicted_h = list-schedule makespan in manifest order (inferred). sha256 is that of the\n"
        f"# part manifest manifest.<workload><part>.tsv, which census-fed-derive rebuilds.\n"
        "half\tworkload\tpart\tworkers\tprojects\tpredicted_h\tsha256\n" + "\n".join(plines) + "\n", encoding="utf-8")
    (UP / f"parts.{WL}.assign.tsv").write_text(
        "workload\tpart\tproject\n" + "".join(f"{WL}\t{p}\t{n}\n" for p in sums for n in order if n in set(assign[p])),
        encoding="utf-8")
    files = [f"manifest.{WL}.tsv", f"project_meta.{WL}.json", f"parts.{WL}.tsv", f"parts.{WL}.assign.tsv"]
    (UP / "SHA256SUMS").write_text("".join(f"{sha(UP / f)}  {f}\n" for f in files), encoding="utf-8")
    # self-check: derive from upload/ into a temp dir must give the recorded sha256s
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        for f in files:
            shutil.copy(UP / f, d)
        assert fd.derive(Path(d), WL) == 0
    for p in sums:
        print(f"{WL}{p}: {len(assign[p])} rows, sum {sums[p]:.1f} h, makespan {makespan([n for n in order if n in set(assign[p])]):.1f} h: "
              + ", ".join(f"{n} {pred[n]}" for n in order if n in set(assign[p])))
    print(f"total {total:.1f} h predicted (inferred)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
