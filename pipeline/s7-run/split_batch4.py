#!/usr/bin/env python3
"""Split manifest.batch4.tsv (u order) into the three batch 4 census parts (2026-10-09).

Batch 4 runs on the batch 2 on-demand instance as 3 censuses, each on its own
loop-mounted XFS filesystem (own rename lock; see ec2-load-20261009.md).
batch4p1, batch4p2, batch4p3: rows 1, 4, 7 ... / 2, 5, 8 ... / 3, 6, 9 ... of
manifest.batch4.tsv, all size classes (S, M and L), so each part gets a mix.
Each part keeps u order and gets a project_meta.<part>.json with its projects
only (the same records as project_meta.batch4.json). The S/M/L class is the
manifest's size_class column.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "manifest.batch4.tsv"
CLASS_COL = 4  # name url category file_filter size_class commit
PARTS = 3


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    digest = hashlib.sha256(SRC.read_bytes()).hexdigest()
    meta = json.loads((HERE / "project_meta.batch4.json").read_text(encoding="utf-8"))
    lines = text.splitlines()
    cols = next(line for line in lines if line.startswith("# Columns:"))
    rows = [line for line in lines if line.strip() and not line.startswith("#")]
    total = 0
    for k in range(PARTS):
        part = f"batch4p{k + 1}"
        keep = rows[k::PARTS]
        total += len(keep)
        head = (f"# Split of {SRC.name} (sha256 {digest}): rows {k + 1}, {k + 1 + PARTS}, ..."
                f" (every {PARTS}rd), all size classes.\n"
                f"# {len(keep)} projects in u order.\n{cols}\n")
        (HERE / f"manifest.{part}.tsv").write_text(
            head + "".join(r + "\n" for r in keep), encoding="utf-8")
        names = [r.split("\t")[0] for r in keep]
        (HERE / f"project_meta.{part}.json").write_text(
            json.dumps({n: meta[n] for n in names}, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")
        counts = {c: sum(r.split("\t")[CLASS_COL] == c for r in keep) for c in "SML"}
        print(f"{part}: {len(keep)} projects  S {counts['S']}  M {counts['M']}  L {counts['L']}")
    assert total == len(rows)


if __name__ == "__main__":
    main()
