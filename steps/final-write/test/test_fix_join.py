"""Tests of fix_join.py (fix 2026-10-27). Synthetic data only.
Run: python3 -I -m pytest -q -p no:cacheprovider test/
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
F = Path(__file__).resolve().parent.parent
STAGE = Path(os.environ.get("FINAL_STAGE_DIR", "FINAL_STAGE_DIR-is-not-set"))
COLS = ("project", "input", "input_sha256", "output", "output_sha256", "rows", "input_bytes",
        "output_bytes", "seconds", "finished_utc", "detail")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tsv(p: Path, rows: list[dict], cols) -> None:
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


@pytest.fixture
def world(tmp_path):
    if not (STAGE / "run_v0.py").is_file():
        pytest.skip("no stage")
    sys.path[:0] = [str(STAGE), str(STAGE / "anon")]
    import run_v0 as rv
    assert tuple(rv.RESULT_COLS) == COLS
    import pseudonymize as P
    con = duckdb.connect()
    src = tmp_path / "src.parquet"
    P.make_synthetic(con, str(src), 50)
    con.close()
    reg = tmp_path / "priv" / "registry.parquet"
    reg.parent.mkdir()
    P.build_registry([str(src)], P.derive_keys(b"0123456789abcdef0123456789abcdef-test"), str(reg),
                     psl=str(STAGE / "public_suffix_list.dat"), out=io.StringIO())
    O, REL, PART, L = (tmp_path / n for n in ("out", "rel", "part", "links"))
    for d in (O / "parquet", REL / "parquet", PART / "parquet", PART / "meta", L):
        d.mkdir(parents=True)
    for n in ("domain_links.parquet", "project_links.parquet", "links.json"):
        (L / n).write_text(n)
    inputs, first, part = [], [], []
    c = duckdb.connect()
    for i, n in enumerate((10, 20, 30, 40)):
        p = f"p{i}"
        inputs.append({"project": p, "layer": "v1", "source": "s", "output": f"v1/parquet/{p}-dataset.parquet",
                       "output_sha256": "-", "rows": n, "output_bytes": 100 - i})
        where = (O, REL) if i < 2 else (PART,)
        f = where[0] / "parquet" / f"{p}-dataset.parquet"
        c.execute(f"COPY (SELECT range AS x FROM range({n})) TO '{f}' (FORMAT PARQUET)")
        for d in where[1:]:
            (d / "parquet" / f.name).write_bytes(f.read_bytes())
        row = {"project": p, "input": f"v1/parquet/{f.name}", "input_sha256": "i", "output": f"parquet/{f.name}",
               "output_sha256": sha(f), "rows": n, "input_bytes": 1, "output_bytes": f.stat().st_size,
               "seconds": "1", "finished_utc": "2026-10-27T00:00:00Z", "detail": "d"}
        (first if i < 2 else part).append(row)
    c.close()
    tsv(tmp_path / "inputs.tsv", inputs, list(inputs[0]))
    tsv(O / "results.tsv", first, COLS)
    tsv(PART / "meta" / "results.tsv", part, COLS)
    args = ["--tools", str(STAGE), "--inputs", str(tmp_path / "inputs.tsv"), "--out", str(O), "--release", str(REL),
            "--part", str(PART), "--links", str(L), "--registry", str(reg), "--report", str(tmp_path / "r.json")]
    return tmp_path, args, part


def run(args):
    return subprocess.run([sys.executable, "-I", str(F / "fix_join.py")] + args, capture_output=True, text=True)


def test_the_join_writes_the_release_text_files(world):
    tmp, args, part = world
    r = run(args)
    assert r.returncode == 0, r.stdout + r.stderr
    O, REL = tmp / "out", tmp / "rel"
    sums = (REL / "SHA256SUMS").read_text().splitlines()
    assert len(sums) == 4 and sums == sorted(sums, key=lambda l: l.split()[1])
    for l in sums:
        h, name = l.split()
        assert sha(REL / name) == h
    info = json.loads((REL / "pseudonymization.json").read_text())
    assert info["leak_scan"] is True and info["leak_scan_content_columns"] is False
    assert info["person_domain_at"] == "first-valid" and info["commit_summary"] == "keep"
    assert len(info["registry_sha256"]) == 64 and info["salt_check"]
    assert (REL / "links.json").read_text() == "links.json"
    assert len((O / "results.tsv").read_text().splitlines()) == 5
    assert json.loads((tmp / "r.json").read_text())["added"] == 2


def test_a_file_of_both_machines_must_be_equal(world):
    tmp, args, part = world
    # p2 written on the first machine too, with another sha256
    with open(tmp / "out" / "results.tsv", "a") as fh:
        fh.write("\t".join(str(part[0][c]) if c != "output_sha256" else "x" * 64 for c in COLS) + "\n")
    r = run(args)
    assert r.returncode == 1 and "another sha256" in r.stdout
    assert len((tmp / "out" / "results.tsv").read_text().splitlines()) == 4  # nothing appended


def test_a_bad_part_file_and_a_gap_stop_the_join(world):
    tmp, args, part = world
    f = tmp / "part" / "parquet" / "p3-dataset.parquet"
    f.write_bytes(f.read_bytes() + b"x")
    r = run(args)
    assert r.returncode == 1 and "sha256 is not its row" in r.stdout
    # without the bad row: p3 is missing, the report names it, no SHA256SUMS
    rows = [r for r in csv.DictReader(open(tmp / "part" / "meta" / "results.tsv"), delimiter="\t") if r["project"] != "p3"]
    tsv(tmp / "part" / "meta" / "results.tsv", rows, COLS)
    r = run(args)
    assert r.returncode == 1 and "1 projects missing" in r.stdout and "p3" in r.stdout
    assert not (tmp / "rel" / "SHA256SUMS").exists()
    assert json.loads((tmp / "r.json").read_text())["missing"] == ["p3"]
