"""Tests for final_merge.py (dataset v1-raw, 2026-10-16).
Run: python3 -I -m pytest -q -p no:cacheprovider test_final_merge.py
     (an interpreter with duckdb and pytest)

SRC and DEST are local directories here, not S3. The input Parquet files are small. They have
the columns that rewrite_meta_columns.py reads. A stub takes the place of ctp's validate_schema.py
(the 70-column contract is not part of these tests)."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import final_merge as fm  # noqa: E402
import rewrite_meta_columns as rmc  # noqa: E402

URL = "https://github.com/o/{}.git"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_parquet(path: Path, name: str, rows: int) -> Path:
    cols = ["repo_name", "token"] + list(rmc.CHECKED) + list(rmc.ALL_FIELDS)
    vals = []
    for i in range(rows):
        v = [name, f"t{i}", URL.format(name), "o", name] + [""] * len(rmc.ALL_FIELDS)
        vals.append("(" + ", ".join(f"'{x}'" for x in v) + ")")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM (VALUES {', '.join(vals)}) t({', '.join(cols)})) "
                f"TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    return path


@pytest.fixture
def setup(tmp_path):
    src = tmp_path / "src"
    projects = {"o__a": 3, "o__b": 5}
    rows = []
    side = {}
    for p, n in projects.items():
        key = f"run/done/{p}/{p}-dataset.parquet"
        f = make_parquet(src / key, p, n)
        rows.append({"project": p, "source": "cloud", "cregit": "57551d7", "token_rows": n,
                     "bytes": f.stat().st_size, "s3_key": key, "sha256": sha(f)})
        rec = {"clone_url": URL.format(p), "owner": "o", "repo": p}
        rec.update({k: f"v-{k}" for k in rmc.ALL_FIELDS})
        side[p] = rec
    inputs = tmp_path / "inputs.tsv"
    with open(inputs, "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    sidecar = tmp_path / "project_meta.v1.final.json"
    sidecar.write_text(json.dumps(side))
    (tmp_path / "project_meta.v1.final.json.sha256").write_text(f"{sha(sidecar)}  {sidecar.name}\n")
    stub = tmp_path / "validate_schema_stub.py"
    stub.write_text("import sys\nsys.exit(0)\n")
    argv = ["--inputs", str(inputs), "--sidecar", str(sidecar), "--work", str(tmp_path / "work"),
            "--out", str(tmp_path / "out"), "--src", str(src), "--dest", str(tmp_path / "dest"),
            "--validate-schema", str(stub), "--jobs", "2", "--threads", "1", "--memory-limit", "1GB"]
    return tmp_path, argv, rows


def results(out: Path) -> list[dict]:
    with open(out / "results.tsv", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def test_every_project_is_written_checked_and_copied(setup):
    tmp, argv, rows = setup
    assert fm.main(argv) == 0
    res = {r["project"]: r for r in results(tmp / "out")}
    assert set(res) == {"o__a", "o__b"}
    for p, r in res.items():
        out = tmp / "out" / r["output"]
        assert sha(out) == r["output_sha256"]
        assert sha(tmp / "dest" / r["output"]) == r["output_sha256"]
        con = duckdb.connect()
        assert con.execute("SELECT DISTINCT license FROM read_parquet(?)", [str(out)]).fetchall() == [("v-license",)]
        con.close()
    sums = (tmp / "dest" / "SHA256SUMS").read_text().splitlines()
    assert sums == sorted(f"{r['output_sha256']}  {r['output']}" for r in res.values())
    assert (tmp / "dest" / "results.tsv").is_file()
    assert (tmp / "dest" / "project_meta.v1.final.json.sha256").is_file()
    assert not any((tmp / "work").iterdir())  # the work copies are gone


def test_a_bad_input_sha256_fails_only_that_project(setup):
    tmp, argv, rows = setup
    lines = (tmp / "inputs.tsv").read_text().splitlines()
    lines[1] = lines[1].replace(rows[0]["sha256"], "0" * 64)
    (tmp / "inputs.tsv").write_text("\n".join(lines) + "\n")
    assert fm.main(argv) == 1
    assert [r["project"] for r in results(tmp / "out")] == ["o__b"]
    assert "input sha256" in (tmp / "out" / "failed.tsv").read_text()
    assert not (tmp / "out" / "parquet" / "o__a-dataset.parquet").exists()
    assert not (tmp / "dest" / "SHA256SUMS").exists()  # not all done: no final list


def test_a_second_start_skips_the_done_projects(setup, capsys):
    tmp, argv, rows = setup
    assert fm.main(argv + ["--only", "o__a"]) == 0
    assert not (tmp / "dest" / "SHA256SUMS").exists()  # --only never finishes
    assert fm.main(argv) == 0
    assert sorted(r["project"] for r in results(tmp / "out")) == ["o__a", "o__b"]
    assert "2 projects, 1 done, 1 to do" in capsys.readouterr().out


def test_the_stop_file_starts_no_new_project(setup):
    tmp, argv, rows = setup
    (tmp / "out").mkdir()
    (tmp / "out" / "STOP").write_text("")
    assert fm.main(argv) == 0
    assert not (tmp / "out" / "results.tsv").exists()


def test_a_sidecar_with_another_sha256_is_refused(setup):
    tmp, argv, rows = setup
    (tmp / "project_meta.v1.final.json.sha256").write_text("f" * 64 + "  x\n")
    assert fm.main(argv) == 2
    assert not (tmp / "out").exists()


def test_a_repeated_project_is_refused(setup):
    tmp, argv, rows = setup
    lines = (tmp / "inputs.tsv").read_text().splitlines()
    (tmp / "inputs.tsv").write_text("\n".join(lines + [lines[1]]) + "\n")
    assert fm.main(argv) == 2


def test_the_largest_input_starts_first(setup, monkeypatch):
    tmp, argv, rows = setup
    seen = []
    monkeypatch.setattr(fm, "one", lambda r, a: seen.append(r["project"]) or True)
    assert fm.main(argv[:-6] + ["--jobs", "1", "--threads", "1", "--memory-limit", "1GB"]) == 0
    assert seen == ["o__b", "o__a"]  # o__b has 5 rows, so the larger file
