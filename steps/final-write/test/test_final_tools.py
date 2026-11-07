"""Tests of final_tools.py (kit dataset-final). Synthetic data only; the test addresses use chr(64).
Run: python3 -I -m pytest -q -p no:cacheprovider test/
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
K = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(K))
import final_tools as ft  # noqa: E402

ANON = Path(os.environ.get("CTP_ANON_DIR", "CTP_ANON_DIR-is-not-set"))
AT = chr(64)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tsv(path: Path, rows: list[dict]) -> Path:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return path


def pathfix_meta(d: Path, p: str, rows: int = 10, size: int = 123, ok_size: int | None = None) -> None:
    (d / p).mkdir(parents=True)
    (d / p / "OK").write_text(f"uploaded 2026-10-20T22:00:00Z from i-x part 1\nparquet_sha256 {'a' * 64}\n"
                              f"{ok_size or size}\t{p}-dataset.parquet\n")
    (d / p / f"{p}.validated").write_text(f"rows={rows} bytes={size}\n")


def test_pathfix_inputs(tmp_path):
    meta = tmp_path / "meta"
    pathfix_meta(meta, "a__b", rows=10, size=100)
    pathfix_meta(meta, "c__d", rows=20, size=200)
    lst = tmp_path / "list.txt"
    lst.write_text("# comment\na__b\nc__d\n")
    v1 = tsv(tmp_path / "v1.tsv", [{"project": "a__b"}, {"project": "c__d"}, {"project": "e__f"}])
    out = tmp_path / "in.tsv"
    assert ft.main(["pathfix-inputs", "--meta", str(meta), "--list", str(lst), "--v1-results", str(v1),
                    "--out", str(out)]) == 0
    rows = ft.read_tsv(out)
    assert [(r["project"], r["token_rows"], r["cregit"]) for r in rows] == [("a__b", "10", "14b8db4"), ("c__d", "20", "14b8db4")]
    assert rows[0]["s3_key"] == "dataset-x1k/done-pathfix/a__b/a__b-dataset.parquet"


def test_pathfix_inputs_fails_on_a_bad_row(tmp_path, capsys):
    meta = tmp_path / "meta"
    pathfix_meta(meta, "a__b", size=100, ok_size=101)        # the stamp and the OK disagree
    lst = tmp_path / "list.txt"
    lst.write_text("a__b\nx__y\nz__w\n")
    pathfix_meta(meta, "z__w")
    v1 = tsv(tmp_path / "v1.tsv", [{"project": "a__b"}, {"project": "x__y"}])
    assert ft.main(["pathfix-inputs", "--meta", str(meta), "--list", str(lst), "--v1-results", str(v1),
                    "--out", str(tmp_path / "o.tsv")]) == 1
    err = capsys.readouterr().err
    assert "a__b: the bytes" in err and "x__y: no done-pathfix OK" in err and "z__w: not a project" in err
    assert not (tmp_path / "o.tsv").exists()


def layer(root: Path, sub: str, names: list[str], rows=7) -> list[dict]:
    (root / sub / "parquet").mkdir(parents=True, exist_ok=True)
    res = []
    for n in names:
        f = root / sub / "parquet" / f"{n}-dataset.parquet"
        f.write_bytes(n.encode() * 3)
        res.append({"project": n, "source": "s", "output": f"parquet/{f.name}", "output_sha256": sha(f),
                    "rows": rows, "output_bytes": f.stat().st_size})
    tsv(root / sub / "results.tsv", res)
    return res


def test_assemble(tmp_path):
    layer(tmp_path, "v1", ["a__b", "pf__1", "c__d"])
    layer(tmp_path, "pf17", ["pf__1"], rows=9)
    layer(tmp_path, "x1k", ["x__1", "x__2"])
    lst = tmp_path / "pf.txt"
    lst.write_text("pf__1\n")
    rep = tmp_path / "rep.json"
    assert ft.main(["assemble", "--root", str(tmp_path), "--list", str(lst), "--expect", "5", "--report", str(rep)]) == 0
    rows = ft.read_tsv(tmp_path / "results.tsv")
    assert [(r["project"], r["layer"], r["output"].split("/")[0]) for r in rows] == [
        ("a__b", "v1", "v1"), ("c__d", "v1", "v1"), ("pf__1", "v1", "pf17"), ("x__1", "x1k", "x1k"), ("x__2", "x1k", "x1k")]
    assert len((tmp_path / "files.txt").read_text().splitlines()) == 5
    assert len(ft.read_tsv(tmp_path / "extract.x1k.tsv")) == 2
    r = json.loads(rep.read_text())
    assert r["pathfix"] == {"files": 1, "rows_new": 9, "rows_v1raw": 7, "projects_with_other_rows": 1}


def test_assemble_refuses_a_repeat_a_count_and_a_size(tmp_path, capsys):
    layer(tmp_path, "v1", ["a__b", "pf__1"])
    layer(tmp_path, "pf17", ["pf__1"])
    layer(tmp_path, "x1k", ["a__b"])                            # the project of another layer
    lst = tmp_path / "pf.txt"
    lst.write_text("pf__1\n")
    (tmp_path / "x1k/parquet/a__b-dataset.parquet").write_bytes(b"x")
    assert ft.main(["assemble", "--root", str(tmp_path), "--list", str(lst), "--expect", "4"]) == 1
    err = capsys.readouterr().err
    assert "1 projects repeat" in err and "3 rows, not 4" in err and "1 files with another size" in err
    assert not (tmp_path / "results.tsv").exists()


@pytest.fixture
def release(tmp_path):
    if not (ANON / "pseudonymize.py").is_file():
        pytest.skip("no pseudonymize.py")
    sys.path.insert(0, str(ANON))
    import pseudonymize as P
    rel = tmp_path / "rel"
    (rel / "parquet").mkdir(parents=True)
    kv = {"ctp_schema_version": "2", "organisations_version": "vT", "organisations_mapping_sha256": "m" * 64,
          P.FOOTER_VERSION_KEY: P.SCHEME_VERSION, P.FOOTER_REGISTRY_KEY: "r" * 64}
    con = duckdb.connect()
    inputs = []
    for i, n in enumerate((300, 500)):
        f = rel / "parquet" / f"p{i}-dataset.parquet"
        P.make_synthetic(con, str(f), n, schema2=True, kv=kv)
        inputs.append({"project": f"p{i}", "layer": "v1", "source": "s", "output": f"v1/parquet/{f.name}",
                       "output_sha256": "-", "rows": n, "output_bytes": 0})
    con.close()
    (rel / "SHA256SUMS").write_text("".join(f"{sha(f)}  parquet/{f.name}\n" for f in sorted((rel / "parquet").iterdir())))
    for t in ("results.tsv", "links.json", "pseudonymization.json"):
        (rel / t).write_text("{}\n")
    for t in ("domain_links.parquet", "project_links.parquet"):
        (rel / t).write_bytes(b"PAR1")
    inp = tsv(tmp_path / "inputs.tsv", inputs)
    args = ["check-out", "--inputs", str(inp), "--release", str(rel), "--anon-dir", str(ANON), "--ov", "vT",
            "--mapping", "m" * 64, "--registry-sha256", "r" * 64, "--jobs", "2"]
    return rel, inp, args


def test_check_out_ok(release, capsys):
    rel, inp, args = release
    assert ft.main(args) == 0
    assert "0 files with problems; release folder: ok" in capsys.readouterr().out


def test_check_out_finds_rows_footer_extra_files_and_the_at_sign(release, capsys):
    rel, inp, args = release
    rows = ft.read_tsv(inp)
    rows[0]["rows"] = "301"
    tsv(inp, rows)
    (rel / "registry.parquet").write_bytes(b"x")
    (rel / "results.tsv").write_text(f"x{AT}example.org\n")
    bad = list(args)
    bad[bad.index("--ov") + 1] = "vOther"
    assert ft.main(bad) == 1
    out = capsys.readouterr().out
    assert "2 files with problems" in out and "300 rows, the input has 301" in out
    assert "footer values of ['organisations_version']" in out
    assert "a file named registry" in out and "results.tsv holds the at sign" in out


def test_compare_links(tmp_path):
    con = duckdb.connect()
    for d, dom, proj in (("got", [("a.org", "a"), ("b.org", "b"), ("c.org", "c")], [("p", "a"), ("q", None)]),
                         ("ref", [("a.org", "a"), ("b.org", "x")], [("p", "a"), ("q", None), ("r", "z")])):
        (tmp_path / d).mkdir()
        con.execute(f"COPY (SELECT * FROM (VALUES {', '.join(f'({chr(39)}{x}{chr(39)}, {chr(39)}{y}{chr(39)})' for x, y in dom)}) "
                    f"t(domain, firm_based_on_domain)) TO '{tmp_path / d / 'domain_links.parquet'}' (FORMAT PARQUET)")
        vals = ", ".join(f"('{x}', {('NULL' if y is None else repr(y))})" for x, y in proj)
        con.execute(f"COPY (SELECT * FROM (VALUES {vals}) t(project, firm_based_on_namespace)) "
                    f"TO '{tmp_path / d / 'project_links.parquet'}' (FORMAT PARQUET)")
        (tmp_path / d / "links.json").write_text(json.dumps({"mapping_sha256": d * 20}))
    out = tmp_path / "c.txt"
    assert ft.main(["compare-links", "--got", str(tmp_path / "got"), "--ref", str(tmp_path / "ref"), "--out", str(out)]) == 0
    text = out.read_text()
    assert "domain_links.parquet: got 3 rows, ref 2; only in got 1, only in ref 0, other values 1" in text
    assert "project_links.parquet: got 2 rows, ref 3; only in got 0, only in ref 1, other values 0" in text


def test_check_out_accepts_a_project_name_with_the_word_registry(release, capsys):
    rel, inp, args = release
    rows = ft.read_tsv(inp)
    old = rel / "parquet" / "p1-dataset.parquet"
    new = rel / "parquet" / "x__schema-registry-dataset.parquet"
    old.rename(new)
    rows[1]["project"], rows[1]["output"] = "x__schema-registry", f"v1/parquet/{new.name}"
    tsv(inp, rows)
    (rel / "SHA256SUMS").write_text("".join(f"{sha(f)}  parquet/{f.name}\n" for f in sorted((rel / "parquet").iterdir())))
    assert ft.main(args) == 0
    assert "0 files with problems; release folder: ok" in capsys.readouterr().out
    (rel / "parquet" / "registry.parquet").write_bytes(b"x")
    assert ft.main(args) == 1
    assert "a file named registry" in capsys.readouterr().out
