#!/usr/bin/env python3
"""Compare project_facts of the schema 3 run with the facts of the TOM pass rule.

    compare_facts.py FACTS.parquet SRC.parquet [SRC.parquet ...]

The TOM pass (../pass-1/tom_tools.py cmd_facts) reads the `fact` text
of each schema 2 file and splits it with split_fact(). This script does the same
from the schema 2 source files and compares the rows with FACTS.parquet.
"""
import importlib.util
import os
import sys
from pathlib import Path

import duckdb

spec = importlib.util.spec_from_file_location(
    "tom_tools", os.environ.get("TOM_TOOLS", Path(__file__).resolve().parent.parent / "pass-1" / "tom_tools.py"))
tom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tom)

facts, srcs = sys.argv[1], sys.argv[2:]
want = []
for src in srcs:
    project = src.rsplit("/", 1)[-1].removesuffix("-dataset.parquet")
    texts = duckdb.execute("SELECT DISTINCT fact FROM read_parquet(?)", [src]).fetchall()
    assert len(texts) == 1, f"{project}: {len(texts)} fact values"
    want += [(project, t, v) for t, v in tom.split_fact(texts[0][0])]
    # roster_lang moved to project_facts (2026-11-07): one row when not empty.
    langs = duckdb.execute("SELECT DISTINCT roster_lang FROM read_parquet(?)", [src]).fetchall()
    assert len(langs) == 1, f"{project}: {len(langs)} roster_lang values"
    if langs[0][0]:
        want.append((project, "roster_lang", langs[0][0]))
got = duckdb.execute("SELECT project, fact_type, fact_value FROM read_parquet(?)", [facts]).fetchall()
print("rows: run", len(got), "TOM rule", len(want))
print("equal:", sorted(got, key=str) == sorted(want, key=str))
print("columns:", [r[0] for r in duckdb.execute("DESCRIBE SELECT * FROM read_parquet(?)", [facts]).fetchall()])
sys.exit(0 if sorted(got, key=str) == sorted(want, key=str) else 1)
