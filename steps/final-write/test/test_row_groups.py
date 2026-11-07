"""Defect 2 of the final write (2026-10-27): check-out refused the row groups of 1,001,472 rows that DuckDB
writes with ROW_GROUP_SIZE 1000000. Synthetic data only.
Run: python3 -I -m pytest -q -p no:cacheprovider test/
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
F = Path(__file__).resolve().parent.parent
ENC = "FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 19, ROW_GROUP_SIZE 1000000, PARQUET_VERSION V2"


def load(path: Path):
    spec = importlib.util.spec_from_file_location(f"ft_{path.parent.name}", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def max_group(con, f: Path) -> int:
    return con.execute("SELECT max(row_group_num_rows) FROM parquet_metadata(?)", [str(f)]).fetchone()[0]


def test_the_limit_is_489_vectors():
    ft = load(F / "tools" / "final_tools.py")
    assert ft.ROW_GROUP_MAX == 1_001_472 == 489 * 2048


@pytest.mark.parametrize("threads", [1, 4])
def test_a_build_v0_write_fits_the_limit(tmp_path, threads):
    ft = load(F / "tools" / "final_tools.py")
    con = duckdb.connect(config={"threads": threads, "preserve_insertion_order": True})
    f = tmp_path / "x.parquet"
    con.execute(f"COPY (SELECT range AS i, md5(range::VARCHAR) AS s FROM range(2_600_000)) TO '{f}' ({ENC})")
    g = max_group(con, f)
    assert 1_000_000 <= g <= ft.ROW_GROUP_MAX


def test_a_larger_row_group_still_fails(tmp_path):
    ft = load(F / "tools" / "final_tools.py")
    con = duckdb.connect()
    f = tmp_path / "y.parquet"
    con.execute(f"COPY (SELECT range AS i FROM range(1_200_000)) TO '{f}' (FORMAT PARQUET, ROW_GROUP_SIZE 1200000)")
    assert max_group(con, f) > ft.ROW_GROUP_MAX
