"""Tests for the owner host rule of rewrite_meta_columns.py (2026-10-16).
Run: python3 -I -m pytest -q -p no:cacheprovider test_rewrite_meta_columns.py
     (an interpreter with duckdb and pytest)

The test Parquet files are small. DuckDB writes them from a VALUES list. They have the 11
sidecar columns, the 3 checked columns, repo_name and one other column. The rule: for a project
on git.savannah.gnu.org, the sidecar owner is gnu (final_meta.HOST_OWNER). The run wrote the
owner git or git.savannah.gnu.org. The tool writes gnu in its place. Every other owner mismatch,
and every clone_url or repo mismatch, is still refused. Nothing here reads or writes a dataset
output."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rewrite_meta_columns as rmc  # noqa: E402

KEY = "p"
SAVANNAH = "https://git.savannah.gnu.org/git/texinfo.git"
GITHUB = "https://github.com/o/r.git"


def sidecar_record(clone_url: str, owner: str, repo: str) -> dict:
    rec = {"clone_url": clone_url, "owner": owner, "repo": repo}
    rec.update({f: f"new-{f}" for f in rmc.ALL_FIELDS})
    rec["contested"] = ""
    return rec


def make_parquet(path: Path, clone_url: str, owner: str, repo: str, rows: int = 3) -> Path:
    """A Parquet with `rows` rows. The 11 sidecar columns are ''."""
    cols = ["repo_name", "token"] + list(rmc.CHECKED) + list(rmc.ALL_FIELDS)
    values = []
    for i in range(rows):
        vals = [KEY, f"tok{i}", clone_url, owner, repo] + [""] * len(rmc.ALL_FIELDS)
        values.append("(" + ", ".join("'" + v.replace("'", "''") + "'" for v in vals) + ")")
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * FROM (VALUES {', '.join(values)}) t({', '.join(cols)})) "
                f"TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    return path


def write_sidecar(path: Path, rec: dict) -> Path:
    path.write_text(json.dumps({KEY: rec}), encoding="utf-8")
    return path


def column(path: Path, name: str) -> list:
    con = duckdb.connect()
    rows = con.execute(f'SELECT "{name}" FROM read_parquet(?)', [str(path)]).fetchall()
    out = [r[0] for r in rows]
    con.close()
    return out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(tool, src: Path, sidecar: Path, out: Path, report: Path | None = None) -> int:
    argv = [str(src), "--sidecar", str(sidecar), "--out", str(out), "--threads", "1"]
    if report is not None:
        argv += ["--report", str(report)]
    return tool.main(argv)


@pytest.mark.parametrize("old", ["git", "git.savannah.gnu.org"])
def test_a_savannah_owner_is_rewritten_to_gnu(tmp_path, old):
    src = make_parquet(tmp_path / "a.parquet", SAVANNAH, old, "texinfo")
    side = write_sidecar(tmp_path / "s.json", sidecar_record(SAVANNAH, "gnu", "texinfo"))
    out = tmp_path / "b.parquet"
    assert run(rmc, src, side, out) == 0
    assert column(out, "owner") == ["gnu"] * 3
    assert column(out, "clone_url") == [SAVANNAH] * 3
    assert column(out, "repo") == ["texinfo"] * 3
    assert column(out, "token") == ["tok0", "tok1", "tok2"]
    assert column(out, "license") == ["new-license"] * 3


def test_a_git_protocol_savannah_url_is_rewritten_too(tmp_path):
    url = "git://git.savannah.gnu.org/poke.git"
    src = make_parquet(tmp_path / "a.parquet", url, "git.savannah.gnu.org", "poke")
    side = write_sidecar(tmp_path / "s.json", sidecar_record(url, "gnu", "poke"))
    out = tmp_path / "b.parquet"
    assert run(rmc, src, side, out) == 0
    assert column(out, "owner") == ["gnu"] * 3


def test_a_savannah_owner_that_is_already_gnu_is_kept(tmp_path):
    src = make_parquet(tmp_path / "a.parquet", SAVANNAH, "gnu", "texinfo")
    side = write_sidecar(tmp_path / "s.json", sidecar_record(SAVANNAH, "gnu", "texinfo"))
    out = tmp_path / "b.parquet"
    assert run(rmc, src, side, out) == 0
    assert column(out, "owner") == ["gnu"] * 3


@pytest.mark.parametrize("url, old, side_owner", [
    (GITHUB, "git", "gnu"),                 # (c) not Savannah
    (GITHUB, "x", "o"),                     # (c) not Savannah
    (SAVANNAH, "git", "fsf"),               # (d) the sidecar owner is not gnu
    (SAVANNAH, "foo", "gnu"),               # (e) an unexpected old owner
    (SAVANNAH, "github.com", "gnu"),        # (e) an unexpected old owner
])
def test_other_owner_mismatches_are_still_refused(tmp_path, capsys, url, old, side_owner):
    src = make_parquet(tmp_path / "a.parquet", url, old, "r")
    side = write_sidecar(tmp_path / "s.json", sidecar_record(url, side_owner, "r"))
    out = tmp_path / "b.parquet"
    assert run(rmc, src, side, out) == 1
    assert not out.exists()
    assert f"""owner is ["'{old}'"], the sidecar says '{side_owner}'""" in capsys.readouterr().err


@pytest.mark.parametrize("old", ["git", "gnu"])
@pytest.mark.parametrize("field, pq, side", [
    ("clone_url", SAVANNAH, "https://git.savannah.gnu.org/git/gawk.git"),
    ("clone_url", "https://git.savannah.gnu.org/git/gawk.git", SAVANNAH),
    ("repo", "texinfo", "gawk"),
])
def test_a_clone_url_or_repo_mismatch_is_still_refused(tmp_path, capsys, old, field, pq, side):
    vals = {"clone_url": SAVANNAH, "repo": "texinfo"}
    pq_vals, side_vals = dict(vals, **{field: pq}), dict(vals, **{field: side})
    src = make_parquet(tmp_path / "a.parquet", pq_vals["clone_url"], old, pq_vals["repo"])
    side_p = write_sidecar(tmp_path / "s.json",
                           sidecar_record(side_vals["clone_url"], "gnu", side_vals["repo"]))
    out = tmp_path / "b.parquet"
    assert run(rmc, src, side_p, out) == 1
    assert not out.exists()
    assert f"""{field} is ["'{pq}'"], the sidecar says '{side}'""" in capsys.readouterr().err


def head_tool(tmp_path: Path):
    """The committed version of rewrite_meta_columns.py (HEAD), as a module."""
    text = subprocess.run(["git", "show", "HEAD:./rewrite_meta_columns.py"], cwd=HERE,
                          check=True, capture_output=True, text=True).stdout
    path = tmp_path / "head_tool" / "rewrite_meta_columns_head.py"
    path.parent.mkdir()
    path.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("rewrite_meta_columns_head", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_non_savannah_file_gives_the_same_bytes_as_the_head_version(tmp_path):
    src = make_parquet(tmp_path / "a.parquet", GITHUB, "o", "r", rows=50)
    side = write_sidecar(tmp_path / "s.json", sidecar_record(GITHUB, "o", "r"))
    old_out, new_out = tmp_path / "old" / "b.parquet", tmp_path / "new" / "b.parquet"
    old_out.parent.mkdir()
    new_out.parent.mkdir()
    assert run(head_tool(tmp_path), src, side, old_out) == 0
    assert run(rmc, src, side, new_out) == 0
    assert sha256(old_out) == sha256(new_out)


def test_the_report_shows_the_owner_rewrite(tmp_path, capsys):
    src = make_parquet(tmp_path / "a.parquet", SAVANNAH, "git", "texinfo")
    side = write_sidecar(tmp_path / "s.json", sidecar_record(SAVANNAH, "gnu", "texinfo"))
    out, rep = tmp_path / "b.parquet", tmp_path / "r.tsv"
    assert run(rmc, src, side, out, rep) == 0
    rows = list(csv.reader(rep.open(encoding="utf-8"), delimiter="\t"))
    assert len(rows) == 1 and rows[0][3] == "OK"
    assert "owner rewritten: 'git' -> 'gnu'" in rows[0][5]
    assert "owner rewritten: 'git' -> 'gnu'" in capsys.readouterr().out


def test_the_report_of_a_non_savannah_file_names_no_owner_rewrite(tmp_path):
    src = make_parquet(tmp_path / "a.parquet", GITHUB, "o", "r")
    side = write_sidecar(tmp_path / "s.json", sidecar_record(GITHUB, "o", "r"))
    out, rep = tmp_path / "b.parquet", tmp_path / "r.tsv"
    assert run(rmc, src, side, out, rep) == 0
    assert "owner rewritten" not in rep.read_text(encoding="utf-8")


def test_the_comparison_still_checks_the_owner_value(tmp_path, monkeypatch, capsys):
    """A rewrite that writes the wrong owner must fail the row-by-row comparison."""
    src = make_parquet(tmp_path / "a.parquet", SAVANNAH, "git", "texinfo")
    side = write_sidecar(tmp_path / "s.json", sidecar_record(SAVANNAH, "gnu", "texinfo"))
    out = tmp_path / "b.parquet"
    real = rmc.rewrite

    def bad_rewrite(con, s, d, values, encoding="default"):
        real(con, s, d, dict(values, owner="git"), encoding)

    monkeypatch.setattr(rmc, "rewrite", bad_rewrite)
    assert run(rmc, src, side, out) == 1
    assert not out.exists()
    assert "owner: 3 of 3 rows differ" in capsys.readouterr().err


def test_the_v1_encoding_keeps_every_value_and_uses_the_v1_options(tmp_path):
    """--encoding v1 (user decision, 2026-10-16): ZSTD level 19, 1 M-row groups, Parquet V2.
    The values and the row order are the same as with the default encoding."""
    src = make_parquet(tmp_path / "a.parquet", GITHUB, "o", "r", rows=50)
    side = write_sidecar(tmp_path / "s.json", sidecar_record(GITHUB, "o", "r"))
    plain, v1 = tmp_path / "plain.parquet", tmp_path / "v1.parquet"
    assert run(rmc, src, side, plain) == 0
    assert rmc.main([str(src), "--sidecar", str(side), "--out", str(v1), "--threads", "1",
                     "--encoding", "v1"]) == 0
    con = duckdb.connect()
    rows = "SELECT * FROM read_parquet(?)"
    assert con.execute(rows, [str(plain)]).fetchall() == con.execute(rows, [str(v1)]).fetchall()
    codecs = {r[0] for r in con.execute(
        "SELECT DISTINCT compression FROM parquet_metadata(?)", [str(v1)]).fetchall()}
    assert codecs == {"ZSTD"}
    con.close()
    assert sha256(plain) != sha256(v1)


def test_an_unknown_encoding_is_a_usage_error(tmp_path):
    src = make_parquet(tmp_path / "a.parquet", GITHUB, "o", "r")
    side = write_sidecar(tmp_path / "s.json", sidecar_record(GITHUB, "o", "r"))
    with pytest.raises(SystemExit) as e:
        rmc.main([str(src), "--sidecar", str(side), "--out", str(tmp_path / "b.parquet"),
                  "--encoding", "fast"])
    assert e.value.code == 2


def test_each_output_has_its_own_spill_directory(tmp_path, monkeypatch):
    """Two jobs that write into one directory must not share (and delete) one spill directory."""
    seen = []
    real = rmc.connect
    (tmp_path / "out").mkdir()
    monkeypatch.setattr(rmc, "connect", lambda m, t, spill: seen.append(spill) or real(m, t, spill))
    for name in ("x", "y"):
        src = make_parquet(tmp_path / f"{name}.parquet", GITHUB, "o", "r")
        side = write_sidecar(tmp_path / "s.json", sidecar_record(GITHUB, "o", "r"))
        assert run(rmc, src, side, tmp_path / "out" / f"{name}-out.parquet") == 0
    assert len(set(seen)) == 2
    assert all(s.parent == tmp_path / "out" for s in seen)
    assert not [p for p in (tmp_path / "out").iterdir() if p.name.startswith(".meta-spill")]
