#!/usr/bin/env python3
"""Split manifest.batch3.tsv (u order) into the three batch 3 runs (2026-10-09).

batch3L: the L projects, on the batch 2 on-demand instance after batch 2 has
         started all its projects.
batch3a, batch3b: the S and M projects, on two EC2 spot instances, by alternate
         rows in u order (batch3a rows 1, 3, 5 ..., batch3b rows 2, 4, 6 ...), so
         both get a mix of S and M.
Each split keeps u order and gets a project_meta.<part>.json with its projects
only (the same records as project_meta.batch3.json). The S/M/L class is the
manifest's size_class column, which build_manifest.py copies from the frame and
ctp reads as is.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "manifest.batch3.tsv"
CLASS_COL = 4  # name url category file_filter size_class commit


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    digest = hashlib.sha256(SRC.read_bytes()).hexdigest()
    meta = json.loads((HERE / "project_meta.batch3.json").read_text(encoding="utf-8"))
    lines = text.splitlines()
    cols = next(line for line in lines if line.startswith("# Columns:"))
    rows = [line for line in lines if line.strip() and not line.startswith("#")]
    large = [r for r in rows if r.split("\t")[CLASS_COL] == "L"]
    small = [r for r in rows if r.split("\t")[CLASS_COL] != "L"]
    parts = {
        "batch3L": (large, "the L projects"),
        "batch3a": (small[0::2], "the S and M projects at odd positions (1, 3, 5 ...)"),
        "batch3b": (small[1::2], "the S and M projects at even positions (2, 4, 6 ...)"),
    }
    assert sum(len(k) for k, _ in parts.values()) == len(rows)
    for part, (keep, what) in parts.items():
        head = (f"# Split of {SRC.name} (sha256 {digest}): {what}.\n"
                f"# {len(keep)} projects in u order.\n{cols}\n")
        (HERE / f"manifest.{part}.tsv").write_text(
            head + "".join(r + "\n" for r in keep), encoding="utf-8")
        names = [r.split("\t")[0] for r in keep]
        (HERE / f"project_meta.{part}.json").write_text(
            json.dumps({n: meta[n] for n in names}, indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")
        counts = {c: sum(r.split("\t")[CLASS_COL] == c for r in keep) for c in "SML"}
        print(f"{part}: {len(keep)} projects  S {counts['S']}  M {counts['M']}  L {counts['L']}")
    # The batch3a A/B test (2026-10-09): batch3a runs as 4 census parts, one per XFS filesystem
    # (no RAID0), 5 workers each; part k gets rows k, k+4, k+8 ... of manifest.batch3a.tsv in u
    # order. The spot instance writes the same files itself (census-b3-prep, manifest.a<k>.full.tsv);
    # these copies are the record, byte-identical to those.
    small_a = parts["batch3a"][0]
    for k in range(4):
        share = small_a[k::4]
        (HERE / f"manifest.batch3a{k + 1}.tsv").write_text(
            f"# Part a{k + 1} of manifest.batch3a.tsv: rows {k + 1}, {k + 5}, ... (every 4th), u order.\n"
            f"# {len(share)} projects.\n{cols}\n" + "".join(r + "\n" for r in share), encoding="utf-8")
        counts = {c: sum(r.split("\t")[CLASS_COL] == c for r in share) for c in "SM"}
        print(f"batch3a{k + 1}: {len(share)} projects  S {counts['S']}  M {counts['M']}")


if __name__ == "__main__":
    main()
