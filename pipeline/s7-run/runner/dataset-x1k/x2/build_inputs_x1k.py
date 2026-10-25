#!/usr/bin/env python3
"""Build inputs.x1k.tsv for final_merge.py (X2): one row per x1k project with an OK.
    build_inputs_x1k.py META SIDECAR OUT [--exclude FILE] [--cregit FILE]
        [--pathfix-meta DIR --pathfix-list FILE] [--held FILE]
META is a copy of s3://B/dataset-x1k/done-full/ with only <p>/OK and <p>/<p>.validated (aws s3 sync
--exclude '*' --include '*/OK' --include '*.validated'). --pathfix-meta DIR is the same copy of
s3://B/dataset-x1k/done-pathfix/ (the cregit path-fix run dataset-pathfix-b1, cregit 14b8db4 =
14b8db468e4f6565fab5692a1ab1c3066d12f371; it also holds v1 rows: they are not x1k keys and are ignored).
--pathfix-list FILE: the x1k rows of the path-fix run, one project per line (# comments).
For each row the builder takes done-pathfix/<p>/OK before done-full/<p>/OK:
  - a project of the path-fix list with done-pathfix/<p>/OK: source x1k-pathfix, s3_key
    dataset-x1k/done-pathfix/<p>/<p>-dataset.parquet; --cregit FILE must give it 14b8db4.
  - a project of the path-fix list without done-pathfix/<p>/OK is HELD: no row, also when it has a
    done-full OK (that Parquet has the path defect). The held list goes to stdout and to --held FILE.
  - every other project with done-full/<p>/OK: source x1k-a (part a) or x1k-b, s3_key
    dataset-x1k/done-full/<p>/<p>-dataset.parquet, cregit 57551d7 unless --cregit FILE gives another.
Each OK: line 1 "uploaded <utc> from <instance> part <part>"; line 2 "parquet_sha256 <sha>"; the size
line of <p>-dataset.parquet; <p>.validated "rows=<n>" and "bytes=<n>": bytes must equal the OK size.
--cregit FILE: "<project> <commit>" per line. A 14b8db4 line for a row that does not come from
done-pathfix is an error. s3_key is relative to the bucket (the --src of final_merge.py).
The project must be a key of SIDECAR. --exclude FILE: one project per line (# comments); such a
project must have no OK (a row with an OK is not dropped silently: exit 2).
Every error is reported, then exit 2 (no OUT is written).
Columns (as ~/s3-work/dataset-v1/inputs.tsv): project source cregit token_rows bytes s3_key sha256.
"""
import argparse
import json
import sys
from pathlib import Path

BASE_CREGIT = "57551d7"
PATHFIX_CREGIT = "14b8db4"


def names(f: Path) -> list[str]:
    return [l.split()[0] for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")]


def parse_ok(ok: Path) -> tuple[str, str, int, int]:
    """-> (part, parquet sha256, token rows, bytes) of one <p>/OK and its <p>.validated."""
    p = ok.parent.name
    lines = ok.read_text().splitlines()
    head = lines[0].split()
    assert head[0] == "uploaded" and head[-2] == "part", f"OK line 1: {lines[0]!r}"
    assert lines[1].startswith("parquet_sha256 "), f"OK line 2: {lines[1]!r}"
    sha = lines[1].split()[1]
    assert len(sha) == 64, "sha256 length"
    size = {l.split("\t")[1]: int(l.split("\t")[0]) for l in lines[2:] if "\t" in l}
    pq = f"{p}-dataset.parquet"
    assert pq in size, "no Parquet size line"
    st = dict(l.split("=", 1) for l in (ok.parent / f"{p}.validated").read_text().split() if "=" in l)
    n, b = int(st["rows"]), int(st["bytes"])
    assert b == size[pq], f"stamp bytes {b} != OK size {size[pq]}"
    return head[-1], sha, n, b


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("meta", type=Path)
    ap.add_argument("sidecar", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--exclude", type=Path)
    ap.add_argument("--cregit", type=Path)
    ap.add_argument("--pathfix-meta", type=Path)
    ap.add_argument("--pathfix-list", type=Path)
    ap.add_argument("--held", type=Path)
    a = ap.parse_args(argv)
    if (a.pathfix_meta is None) != (a.pathfix_list is None):
        ap.error("--pathfix-meta and --pathfix-list go together")
    keys = set(json.loads(a.sidecar.read_text()))
    exclude = set(names(a.exclude)) if a.exclude else set()
    cregit = {}
    if a.cregit:
        cregit = dict(l.split()[:2] for l in a.cregit.read_text().splitlines() if l.strip() and not l.startswith("#"))
    pf_list = set(names(a.pathfix_list)) if a.pathfix_list else set()
    rows, bad, held, ignored = [], [], [], 0
    bad += [f"{p}: path-fix row is not a key of the sidecar" for p in sorted(pf_list - keys)]
    bad += [f"{p}: path-fix row is in the exclusion list" for p in sorted(pf_list & exclude)]

    pf_done = set()
    if a.pathfix_meta:
        for ok in sorted(a.pathfix_meta.glob("*/OK")):
            p = ok.parent.name
            if p not in keys:
                ignored += 1  # a v1 row of the path-fix run
                continue
            try:
                assert p in pf_list, "done-pathfix OK, but not in the path-fix list"
                assert cregit.get(p) == PATHFIX_CREGIT, f"cregit file gives {cregit.get(p)!r}, not {PATHFIX_CREGIT}"
                _, sha, n, b = parse_ok(ok)
                rows.append((p, "x1k-pathfix", PATHFIX_CREGIT, n, b,
                             f"dataset-x1k/done-pathfix/{p}/{p}-dataset.parquet", sha))
                pf_done.add(p)
            except Exception as exc:  # noqa: BLE001 - report every bad row, then stop
                bad.append(f"{p} (done-pathfix): {exc}")

    full_ok = {ok.parent.name for ok in a.meta.glob("*/OK")}
    for ok in sorted(a.meta.glob("*/OK")):
        p = ok.parent.name
        if p in pf_list:
            continue  # done-pathfix wins; without a done-pathfix OK the row is held (below)
        try:
            part, sha, n, b = parse_ok(ok)
            assert p in keys, "not a key of the sidecar"
            assert p not in exclude, "in the exclusion list but has an OK"
            c = cregit.get(p, BASE_CREGIT)
            assert c != PATHFIX_CREGIT, f"cregit file gives {PATHFIX_CREGIT}, but the row is from done-full"
            source = "x1k-a" if part == "a" else "x1k-b"
            rows.append((p, source, c, n, b, f"dataset-x1k/done-full/{p}/{p}-dataset.parquet", sha))
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{p}: {exc}")
    for p in sorted(pf_list - pf_done):
        held.append(f"{p}\t{'done-full OK not used' if p in full_ok else 'no OK'}")
    bad += [f"{p}: cregit file gives {PATHFIX_CREGIT}, but no done-pathfix OK"
            for p, c in sorted(cregit.items()) if c == PATHFIX_CREGIT and p not in pf_done and p not in pf_list]

    if bad:
        print("BAD ROWS:\n  " + "\n  ".join(bad[:50]), file=sys.stderr)
        return 2
    rows.sort()
    with open(a.out, "w") as fh:
        fh.write("project\tsource\tcregit\ttoken_rows\tbytes\ts3_key\tsha256\n")
        for r in rows:
            fh.write("\t".join(map(str, r)) + "\n")
    if a.held:
        a.held.write_text("# path-fix rows without done-pathfix/<p>/OK: not merged (project, reason)\n"
                          + "".join(h + "\n" for h in held))
    by = {}
    for r in rows:
        by[r[1]] = by.get(r[1], 0) + 1
    print(f"{a.out.name}: {len(rows)} rows ({', '.join(f'{k} {v}' for k, v in sorted(by.items()))}), "
          f"{sum(r[4] for r in rows) / 1e9:.2f} GB, {sum(r[3] for r in rows):,} token rows; "
          f"sidecar keys without a row: {len(keys - {r[0] for r in rows})}")
    if a.pathfix_list:
        print(f"path-fix: {len(pf_done)} of {len(pf_list)} x1k rows from done-pathfix (cregit {PATHFIX_CREGIT}); "
              f"{ignored} done-pathfix OK of other rows ignored (v1)")
        print(f"HELD: {len(held)} rows (not merged; they join in a later pass)"
              + "".join(f"\n  {h}" for h in held))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
