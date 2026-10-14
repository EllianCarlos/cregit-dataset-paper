#!/usr/bin/env python3
"""Build batch1rest and split it and batch 5 into the census parts (2026-10-09).

Two workloads, decided by the user at 14:36 UTC:
  batch5     = manifest.batch5.tsv (rows 657-820 of frame.layer1.csv, 164 projects).
  batch1rest = the manifest.batch1.tsv projects that did not finish locally: every row
               except the 49 in batch1-finished-20261009.txt and the two that finish locally
               (SAP__project-foxhound, wolfpld__tracy). Same rows and pins as batch 1; the new
               code (cregit 95cdc88) runs them on EC2.

Where they run:
  L projects of both  -> batch5L: one census on the batch 2 on-demand instance, u order.
  S and M of both     -> 10 census parts of 4 workers, 5 on each batch 3 spot instance (a, b):
                         about 20 new workers per instance next to the CPU-light batch 3 tails
                         (main session, 2026-10-09 ~15:00 UTC; supersedes the 8-part split of 3ceea81).
Parts are balanced by predicted time (longest first, to the part that would finish first,
weighted by its workers), and every part keeps u order. Predicted time, in seconds:
  exp(-5.846 + 0.5957 ln(commits) + 0.4389 ln(tok_bytes)), commits and tok_bytes from the frame;
  a log-linear fit on 354 finished EC2 projects of batches 2, 3, 3L and 4 (R^2 0.73, 14:45 UTC).

Writes manifest.batch1rest.tsv (+ .order.tsv, project_meta), manifest.batch5L.tsv (+ project_meta),
the parts table parts.tsv (half, workload, part, workers, projects, predicted h, sha256 of the
part manifest) and parts.assign.tsv (workload, part, project), and the part manifests
manifest.<W><P>.tsv as the record.

The spot instances get only the workload manifests and the two parts files; they derive the
part manifests themselves with `split_batch5.py --derive DIR` (DIR holds manifest.<W>.tsv,
parts.tsv, parts.assign.tsv), which writes DIR/manifest.<W><P>.tsv and checks each sha256
against parts.tsv, so they are byte-identical to the record here.
"""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLASS_COL = 4  # name url category file_filter size_class commit
FINISH_LOCALLY = ("SAP__project-foxhound", "wolfpld__tracy")
# (half, workload, part, workers): 5 parts of 4 workers per spot instance.
PARTS = [
    ("a", "batch5", "a1", 4), ("a", "batch5", "a2", 4), ("a", "batch5", "a3", 4),
    ("a", "batch1rest", "a1", 4), ("a", "batch1rest", "a2", 4),
    ("b", "batch5", "b1", 4), ("b", "batch5", "b2", 4), ("b", "batch5", "b3", 4),
    ("b", "batch1rest", "b1", 4), ("b", "batch1rest", "b2", 4),
]
FIT = (-5.846, 0.5957, 0.4389)


def read_manifest(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    cols = next(line for line in lines if line.startswith("# Columns:"))
    rows = [line for line in lines if line.strip() and not line.startswith("#")]
    return cols, rows


def name(row: str) -> str:
    return row.split("\t")[0]


def write(stem: str, head: str, cols: str, rows: list, meta: dict) -> None:
    (HERE / f"manifest.{stem}.tsv").write_text(
        head + f"# {len(rows)} projects in u order.\n{cols}\n" + "".join(r + "\n" for r in rows),
        encoding="utf-8")
    (HERE / f"project_meta.{stem}.json").write_text(
        json.dumps({name(r): meta[name(r)] for r in rows}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")


def part_text(src: Path, part: str, workers: int, pred_h: str, names: set) -> str:
    """The part manifest: the rows of src named in names, in src (u) order. Used here and by --derive."""
    cols, rows = read_manifest(src)
    keep = [r for r in rows if name(r) in names]
    assert len(keep) == len(names), (src, part)
    return (f"# Part {part} of the S and M projects of {src.name} (sha256 "
            f"{hashlib.sha256(src.read_bytes()).hexdigest()}),\n"
            f"# balanced by predicted time ({pred_h} h for {workers} workers), u order.\n"
            f"# {len(keep)} projects in u order.\n{cols}\n" + "".join(r + "\n" for r in keep))


def read_parts(d: Path):
    parts = [line.split("\t") for line in (d / "parts.tsv").read_text(encoding="utf-8").splitlines()
             if line and not line.startswith("#")][1:]
    assign = {}
    for line in (d / "parts.assign.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        wl, p, n = line.split("\t")
        assign.setdefault((wl, p), set()).add(n)
    return parts, assign


def derive(d: Path) -> int:
    parts, assign = read_parts(d)
    bad = 0
    for half, wl, p, w, n, h, sha in parts:
        text = part_text(d / f"manifest.{wl}.tsv", p, int(w), h, assign[(wl, p)])
        got = hashlib.sha256(text.encode("utf-8")).hexdigest()
        (d / f"manifest.{wl}{p}.tsv").write_text(text, encoding="utf-8")
        ok = got == sha and len(assign[(wl, p)]) == int(n)
        bad += not ok
        print(f"{half} {wl}{p}: {n} projects, {w} workers, sha256 {'ok' if ok else 'DIFFERS ' + got}")
    return 1 if bad else 0


def counts(rows: list) -> str:
    c = {k: sum(r.split("\t")[CLASS_COL] == k for r in rows) for k in "SML"}
    return f"S {c['S']}  M {c['M']}  L {c['L']}"


def main() -> None:
    sha = {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest()
           for f in ("manifest.batch1.tsv", "manifest.batch5.tsv", "batch1-finished-20261009.txt")}
    finished = {line.strip() for line in (HERE / "batch1-finished-20261009.txt").read_text().splitlines()
                if line.strip() and not line.startswith("#")}
    assert len(finished) == 49, len(finished)
    cols1, b1 = read_manifest(HERE / "manifest.batch1.tsv")
    cols5, b5 = read_manifest(HERE / "manifest.batch5.tsv")
    assert cols1 == cols5
    meta = json.loads((HERE / "project_meta.batch1.json").read_text(encoding="utf-8"))
    meta.update(json.loads((HERE / "project_meta.batch5.json").read_text(encoding="utf-8")))
    assert finished <= {name(r) for r in b1}
    rest = [r for r in b1 if name(r) not in finished and name(r) not in FINISH_LOCALLY]
    write("batch1rest",
          f"# Rows of manifest.batch1.tsv (sha256 {sha['manifest.batch1.tsv']}) that did not finish locally:\n"
          f"# without the {len(finished)} in batch1-finished-20261009.txt (sha256 {sha['batch1-finished-20261009.txt']})\n"
          f"# and {', '.join(FINISH_LOCALLY)} (they finish locally). Same rows and pins as batch 1.\n",
          cols1, rest, meta)
    order = (HERE / "manifest.batch1.order.tsv").read_text(encoding="utf-8").splitlines()
    keep = {name(r) for r in rest}
    (HERE / "manifest.batch1rest.order.tsv").write_text(
        "\n".join([order[0]] + [o for o in order[1:] if o.split("\t")[1] in keep]) + "\n", encoding="utf-8")
    print(f"batch1rest: {len(rest)} projects  {counts(rest)}")

    u = {}
    for f in ("manifest.batch1.order.tsv", "manifest.batch5.order.tsv"):
        for line in (HERE / f).read_text(encoding="utf-8").splitlines()[1:]:
            c = line.split("\t")
            u[c[1]] = float(c[4])
    frame = {r["repo_url"].rstrip("/").removesuffix(".git"): r
             for r in csv.DictReader(open(HERE / "frame.layer1.csv", encoding="utf-8"))}

    def pred(row: str) -> float:
        f = frame[row.split("\t")[1].rstrip("/").removesuffix(".git")]
        return math.exp(FIT[0] + FIT[1] * math.log(int(f["commits"]))
                        + FIT[2] * math.log(max(int(f["tok_bytes"] or 1), 1)))

    work = {"batch1rest": rest, "batch5": b5}
    large = sorted((r for rows in work.values() for r in rows if r.split("\t")[CLASS_COL] == "L"),
                   key=lambda r: u[name(r)])
    write("batch5L",
          f"# The L projects of manifest.batch1rest.tsv and manifest.batch5.tsv (sha256 {sha['manifest.batch5.tsv']}),\n"
          f"# for the census batch5L on the batch 2 on-demand instance.\n", cols5, large, meta)
    print(f"batch5L: {len(large)} projects  {counts(large)}  predicted h: "
          + ", ".join(f"{name(r)} {pred(r) / 3600:.1f}" for r in large))

    table, assign = [], []
    for wl, rows in work.items():
        parts = [(p, w) for (_, x, p, w) in PARTS if x == wl]
        small = [r for r in rows if r.split("\t")[CLASS_COL] != "L"]
        load = {p: 0.0 for p, _ in parts}
        share = {p: [] for p, _ in parts}
        workers = dict(parts)
        for r in sorted(small, key=lambda r: (-pred(r), u[name(r)])):
            p = min(load, key=lambda p: ((load[p] + pred(r)) / workers[p], p))
            load[p] += pred(r)
            share[p].append(name(r))
        assert sum(len(v) for v in share.values()) == len(small)
        for p, w in parts:
            h = f"{load[p] / 3600:.1f}"
            text = part_text(HERE / f"manifest.{wl}.tsv", p, w, h, set(share[p]))
            (HERE / f"manifest.{wl}{p}.tsv").write_text(text, encoding="utf-8")
            _, keep = read_manifest(HERE / f"manifest.{wl}{p}.tsv")
            assert all(u[name(keep[i])] <= u[name(keep[i + 1])] for i in range(len(keep) - 1))
            half = next(x for (x, y, q, _) in PARTS if y == wl and q == p)
            table.append((half, wl, p, w, len(keep), h, hashlib.sha256(text.encode("utf-8")).hexdigest()))
            assign += [(wl, p, name(r)) for r in keep]
            print(f"{half} {wl}{p}: {len(keep)} projects  {counts(keep)}  {w} workers  "
                  f"predicted {h} h of work, {load[p] / 3600 / w:.1f} h per worker")
    table.sort(key=lambda t: (t[0], t[1] != "batch5", t[2]))
    (HERE / "parts.tsv").write_text(
        "# Census parts of batch5 and batch1rest on the two spot halves (split_batch5.py). sha256 is that of\n"
        "# the part manifest manifest.<workload><part>.tsv, which split_batch5.py --derive rebuilds.\n"
        "half\tworkload\tpart\tworkers\tprojects\tpredicted_h\tsha256\n"
        + "".join("\t".join(map(str, t)) + "\n" for t in table), encoding="utf-8")
    (HERE / "parts.assign.tsv").write_text(
        "workload\tpart\tproject\n" + "".join(f"{a}\t{b}\t{c}\n" for a, b, c in assign), encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--derive"]:
        sys.exit(derive(Path(sys.argv[2])))
    main()
