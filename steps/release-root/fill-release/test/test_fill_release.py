"""Tests of tools/fill_release.py on a small fake release (no real data)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "fill_release.py"
spec = importlib.util.spec_from_file_location("fill_release", TOOL)
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)

HASH = "ab" * 32


def literal(name: str, typ: str, project: str) -> str:
    if name == "clone_url":
        return f"'https://example.org/{project}.git' AS {name}"
    if name == "size_class":
        return f"'S' AS {name}"
    if name == "commits":
        return f"'1234' AS {name}"
    if typ == "VARCHAR[]":
        return f"[]::VARCHAR[] AS {name}"
    if typ == "BIGINT":
        return f"i::BIGINT AS {name}"
    if typ == "BOOLEAN":
        return f"false AS {name}"
    return f"'x' AS {name}"


def write_project(root: Path, project: str, rows: int, mapping: str = HASH,
                  columns=fr.SCHEMA_2, keys=("organizations_version", "organizations_mapping_sha256")) -> None:
    sel = ", ".join(literal(n, t, project) for n, t in columns)
    out = root / "parquet" / f"{project}-dataset.parquet"
    duckdb.execute(
        f"COPY (SELECT {sel} FROM range({rows}) t(i)) TO '{out}' (FORMAT parquet, KV_METADATA "
        f"{{ctp_schema_version: '2', {keys[0]}: 'vtest', "
        f"{keys[1]}: '{mapping}'}})")


def make_release(tmp_path: Path) -> Path:
    root = tmp_path / "rel"
    (root / "parquet").mkdir(parents=True)
    (root / "organizations").mkdir()
    (root / "docs").mkdir()
    (root / "_staging").mkdir()
    write_project(root, "org__alpha", 3)
    write_project(root, "org__beta", 5)
    for t in fr.ORG_TABLES:
        if t == "release_info":
            duckdb.execute(f"COPY (SELECT 'mapping_sha256' AS key, '{HASH}' AS value) "
                           f"TO '{root}/organizations/{t}.parquet' (FORMAT parquet)")
        else:
            duckdb.execute(f"COPY (SELECT 1 AS a) TO '{root}/organizations/{t}.parquet' (FORMAT parquet)")
    duckdb.connect(str(root / "organizations" / "dataset.duckdb")).close()
    (root / "README.md").write_text("A test release.\n")
    (root / "_staging" / "notes.md").write_text("ignored folder\n")
    (tmp_path / "layers.tsv").write_text("project\tlayer\norg__alpha\tv1\norg__beta\tx1k\n")
    led = tmp_path / "runs" / "a" / "ledger.jsonl"
    led.parent.mkdir(parents=True)
    recs = [
        {"step": "project", "status": "done", "project": "org__alpha", "end_utc": "2026-10-01",
         "checked_out_sha": "old", "snapshot_sha": "f1", "tools": {"cregit_commit": "c0", "ctp_commit": "t0"}},
        {"step": "project", "status": "done", "project": "org__alpha", "end_utc": "2026-10-02",
         "checked_out_sha": "new", "snapshot_sha": "f1", "tools": {"cregit_commit": "c1", "ctp_commit": "t1"}},
        {"step": "project", "status": "failed", "project": "org__beta", "end_utc": "2026-10-03"},
        {"step": "project", "status": "done", "project": "org__beta", "end_utc": "2026-10-02",
         "checked_out_sha": "b1", "snapshot_sha": "b0", "tools": {"cregit_commit": "c1", "ctp_commit": "t1"}},
    ]
    led.write_text("".join(json.dumps(r) + "\n" for r in recs))
    return root


def run(*args) -> int:
    return fr.main([str(a) for a in args])


def fill(tmp_path: Path, root: Path) -> None:
    assert run("manifest", "--root", root, "--layers", tmp_path / "layers.tsv",
               "--ledgers", str(tmp_path / "runs" / "**" / "ledger.jsonl"), "--jobs", 1) == 0
    assert run("checksums", "--root", root, "--jobs", 2) == 0


def test_manifest_rows(tmp_path):
    root = make_release(tmp_path)
    fill(tmp_path, root)
    lines = (root / "MANIFEST.tsv").read_text().splitlines()
    assert lines[0].split("\t") == list(fr.MANIFEST_COLUMNS)
    rows = {l.split("\t")[0]: dict(zip(fr.MANIFEST_COLUMNS, l.split("\t"))) for l in lines[1:]}
    assert rows["org__alpha"]["run_commit"] == "new"      # the last finished record wins
    assert rows["org__alpha"]["cregit_commit"] == "c1"
    assert rows["org__beta"]["run_commit"] == "b1"        # a failed record does not count
    assert rows["org__beta"]["layer"] == "x1k"
    assert rows["org__alpha"]["rows"] == "3" and rows["org__beta"]["rows"] == "5"
    assert rows["org__alpha"]["sha256"] == fr.sha256_file(str(root / "parquet/org__alpha-dataset.parquet"))


def test_checksums_skip_staging_and_self(tmp_path):
    root = make_release(tmp_path)
    fill(tmp_path, root)
    sums = fr.read_sums(root / "SHA256SUMS")
    assert "MANIFEST.tsv" in sums and "README.md" in sums
    assert not any(k.startswith("_staging") for k in sums)
    assert "SHA256SUMS" not in sums
    out = subprocess.run(["sha256sum", "-c", "--quiet", "SHA256SUMS"], cwd=root)
    assert out.returncode == 0
    assert run("verify", "--root", root, "--jobs", 1) == 0
    (root / "README.md").write_text("changed\n")
    assert run("verify", "--root", root, "--jobs", 1) == 1


def test_check_passes_on_a_clean_release(tmp_path):
    root = make_release(tmp_path)
    fill(tmp_path, root)
    assert run("check", "--root", root) == 0


def test_check_finds_problems(tmp_path, capsys):
    root = make_release(tmp_path)
    write_project(root, "org__stale", 2, mapping="cd" * 32)
    write_project(root, "org__old", 2, columns=fr.SCHEMA_2[:67])
    (tmp_path / "layers.tsv").write_text(
        "org__alpha\tv1\norg__beta\tx1k\norg__stale\tv1\norg__old\tv1\n")
    fill(tmp_path, root)
    (root / "docs" / "X.md").write_text("mail: a" + chr(64) + "b.org\n" + "TO" + "DO(data): later\n")
    private = tmp_path / "private.txt"
    private.write_text("Secret Person\n")
    (root / "docs" / "Y.md").write_text("by secret person\n")
    assert run("check", "--root", root, "--private-names", private) == 1
    out = capsys.readouterr().out
    assert "org__stale-dataset.parquet: stale file" in out
    assert "org__old-dataset.parquet: not schema 2" in out
    assert "the at sign" in out
    assert "marker" in out
    assert "a name from the private list" in out
    assert "org__stale has no run_commit" in out
    assert run("check", "--root", root, "--allow-todo") == 1


def test_check_finds_the_old_spelling(tmp_path, capsys):
    root = make_release(tmp_path)
    # a file of the first build of the release root: the footer keys with the British spelling
    write_project(root, "org__gamma", 2, keys=("organisations_version", "organisations_mapping_sha256"))
    (root / "organisations").mkdir()
    (root / "organisations" / "notes.txt").write_text("x\n")
    (tmp_path / "layers.tsv").write_text("org__alpha\tv1\norg__beta\tx1k\norg__gamma\tv1\n")
    fill(tmp_path, root)
    assert run("check", "--root", root, "--allow-todo") == 1
    out = capsys.readouterr().out
    assert "org__gamma-dataset.parquet: footer has no organizations_version" in out
    assert ("org__gamma-dataset.parquet: footer key with the old spelling: organisations_mapping_sha256, "
            "organisations_version") in out
    assert "organisations/notes.txt: a name with the old spelling organis" in out


def test_missing_layer_stops_the_manifest(tmp_path):
    root = make_release(tmp_path)
    (tmp_path / "layers.tsv").write_text("org__alpha\tv1\n")
    assert run("manifest", "--root", root, "--layers", tmp_path / "layers.tsv", "--jobs", 1) == 2
    assert not (root / "MANIFEST.tsv").exists()


def test_the_tool_passes_its_own_text_check():
    text = TOOL.read_text()
    assert chr(64) not in text
    assert ("TO" + "DO") not in text
    for w in fr.FORBIDDEN_WORDS:
        assert w not in text.lower()
