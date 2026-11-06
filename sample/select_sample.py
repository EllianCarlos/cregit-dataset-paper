#!/usr/bin/env python3
"""Select the sample projects from the release, with the rule of SAMPLE.md.

Usage:
    python select_sample.py --root RELEASE_ROOT [--out sample_projects.tsv]

RELEASE_ROOT is the root of the full release: it holds MANIFEST.tsv and parquet/. The script
reads MANIFEST.tsv and the footer of each project file (no data pages). It prints the chosen
projects as a TSV table. It needs Python 3.10 or later, pandas and pyarrow.

The rule:
1. The candidates are the project files whose `language` (the primary language that the host
   gives) is C, C++, Java or Rust.
2. The groups (cells): for the labels `company`, `foundation`, `personal` and `unknown` of the
   column `stratum`, one cell for each layer, language and label (2 x 4 x 4 = 32 cells). For the
   labels `contested` and `fiscal-sponsor`, one cell for each layer and label, with the four
   languages together (2 x 2 = 4 cells).
3. In each cell, sort the files by the number of rows (token rows), then by the project name.
   Take the file at the position (n - 1) // 2 (from 0): the lower median of the cell.

The rule uses rows, not bytes, because the rows do not change when a file is written again with
other Parquet settings. The script then checks that each chosen file is under 100,000,000 bytes.
"""
from __future__ import annotations

import argparse
import os
import sys

import pandas as pd
import pyarrow.parquet as pq

LANGUAGES = ["C", "C++", "Java", "Rust"]
LABELS_BY_LANGUAGE = ["company", "foundation", "personal", "unknown"]
LABELS_TOGETHER = ["contested", "fiscal-sponsor"]
MAX_BYTES = 100_000_000  # a check of the result, not a part of the rule


def first_value(pf: pq.ParquetFile, name: str) -> str | None:
    """The value of a project column, from the statistics of the first row group (footer only)."""
    md = pf.metadata
    idx = md.schema.to_arrow_schema().get_field_index(name)
    st = md.row_group(0).column(idx).statistics
    if st is None or not st.has_min_max:
        return None
    return st.min


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, help="the release root (MANIFEST.tsv, parquet/)")
    ap.add_argument("--out", help="write the table to this TSV file")
    a = ap.parse_args(argv)

    m = pd.read_csv(os.path.join(a.root, "MANIFEST.tsv"), sep="\t", dtype=str)
    m["rows"] = m["rows"].astype("int64")
    m["bytes"] = m["bytes"].astype("int64")
    langs, labels = [], []
    for path in m["path"]:
        pf = pq.ParquetFile(os.path.join(a.root, path))
        langs.append(first_value(pf, "language"))
        labels.append(first_value(pf, "stratum"))
    m["language"], m["stratum"] = langs, labels

    c = m[m["language"].isin(LANGUAGES) & m["stratum"].isin(LABELS_BY_LANGUAGE + LABELS_TOGETHER)].copy()
    c["cell"] = [f"{l}|{lang}|{s}" if s in LABELS_BY_LANGUAGE else f"{l}|*|{s}"
                 for l, lang, s in zip(c["layer"], c["language"], c["stratum"])]
    c = c.sort_values(["cell", "rows", "project"])
    c["rank"] = c.groupby("cell").cumcount()
    c["cell_size"] = c.groupby("cell")["project"].transform("size")
    pick = c[c["rank"] == (c["cell_size"] - 1) // 2]
    cols = ["project", "layer", "language", "stratum", "rows", "bytes", "sha256", "cell", "cell_size", "rank"]
    pick = pick[cols].sort_values(["layer", "language", "stratum"]).reset_index(drop=True)
    big = pick[pick["bytes"] >= MAX_BYTES]
    if len(big):
        print(f"error: {len(big)} chosen files have {MAX_BYTES:,} bytes or more", file=sys.stderr)
        return 1
    if a.out:
        pick.to_csv(a.out, sep="\t", index=False)
    pick.to_csv(sys.stdout, sep="\t", index=False)
    print(f"# {len(pick)} projects, {pick['rows'].sum():,} rows, {pick['bytes'].sum():,} bytes", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
