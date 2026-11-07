"""Tests of extract_domains_v1.py --inputs and --cache on two small token files (2026-10-23).
The test addresses are made with chr(64), so this file holds no address."""
import json
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import extract_domains_v1 as ex  # noqa: E402

AT = chr(64)


def tokens(path: Path, rows) -> None:
    """rows: (person_domain, local part, committer local part + domain, commit, date)."""
    con = duckdb.connect()
    con.execute("CREATE TABLE t (person_domain VARCHAR, person_email VARCHAR, committer_email VARCHAR, "
                "original_commit_sha VARCHAR, author_date TIMESTAMP, token VARCHAR)")
    con.executemany("INSERT INTO t VALUES (?, ?, ?, ?, ?, 'x')",
                    [(d, f"{u}{AT}{d}" if d else "", c, sha, day) for d, u, c, sha, day in rows])
    con.execute(f"COPY t TO '{path}' (FORMAT PARQUET)")
    con.close()


@pytest.fixture
def files(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    tokens(src / "p1-dataset.parquet", [
        ("acme.com", "a", f"a{AT}acme.com", "c1", "2020-01-01"),
        ("acme.com", "a", f"a{AT}acme.com", "c1", "2020-01-01"),
        ("acme.com", "a", f"a{AT}acme.com", "c2", "2021-01-01"),
        ("ACME.com ", "b", f"git{AT}host.org", "c3", "2022-01-01"),
        ("", "", "", "c4", "2022-02-01"),
    ])
    tokens(src / "p2-dataset.parquet", [("uni.edu", "u", f"u{AT}uni.edu", "d1", "2019-05-05")])
    inputs = tmp_path / "inputs.tsv"
    inputs.write_text("project\tpath\trows\np2\tsrc/p2-dataset.parquet\t1\n"
                      f"p1\t{src / 'p1-dataset.parquet'}\t5\n")
    return tmp_path, inputs


def rows(path: Path):
    con = duckdb.connect()
    return con.execute("SELECT domain, email, committer_domain, tokens, commits FROM read_parquet(?) "
                       "ORDER BY ALL", [str(path)]).fetchall()


def test_inputs_and_cache(files):
    tmp, inputs = files
    cache = tmp / "x1k" / "cache"
    assert ex.main(["--inputs", str(inputs), "--cache", str(cache), "--jobs", "2", "--threads", "1",
                    "--memory-limit", "1GB"]) == 0
    assert sorted(f.name for f in cache.iterdir()) == ["p1.parquet", "p2.parquet"]
    assert rows(cache / "p1.parquet") == [
        ("", "", "", 1, 1),
        ("acme.com", f"a{AT}acme.com", "acme.com", 3, 2),
        ("acme.com", f"b{AT}acme.com", "host.org", 1, 1),
    ]
    assert rows(cache / "p2.parquet") == [("uni.edu", f"u{AT}uni.edu", "uni.edu", 1, 1)]
    # the index is in the parent folder of the cache; no spill folder is left
    index = json.loads((tmp / "x1k" / "index.json").read_text())
    assert set(index) == {"p1", "p2"} and index["p2"]["src"].endswith("src/p2-dataset.parquet")
    assert not any((tmp / "x1k" / "spill").glob("*"))


def test_second_start_reads_nothing(files, capsys):
    tmp, inputs = files
    args = ["--inputs", str(inputs), "--cache", str(tmp / "c" / "cache"), "--jobs", "1", "--threads", "1",
            "--memory-limit", "1GB"]
    assert ex.main(args) == 0
    assert ex.main(args) == 0
    assert "2 projects, 0 to read" in capsys.readouterr().out


def test_only(files):
    tmp, inputs = files
    cache = tmp / "o" / "cache"
    assert ex.main(["--inputs", str(inputs), "--cache", str(cache), "--only", "p2", "--threads", "1",
                    "--memory-limit", "1GB"]) == 0
    assert [f.name for f in cache.iterdir()] == ["p2.parquet"]


@pytest.mark.parametrize("text", [
    "project\tfile\np1\tx.parquet\n",                    # no path column
    "project\tpath\np2\tsrc/p2-dataset.parquet\np2\tsrc/p2-dataset.parquet\n",  # repeated project
    "project\tpath\np9\tsrc/missing.parquet\n",          # missing file
    "project\tpath\n\tsrc/p2-dataset.parquet\n",         # no project
])
def test_bad_inputs_exit_2(files, text):
    tmp, _ = files
    bad = tmp / "bad.tsv"
    bad.write_text(text)
    with pytest.raises(SystemExit) as e:
        ex.main(["--inputs", str(bad), "--cache", str(tmp / "b" / "cache")])
    assert e.value.code == 2


def test_rule_e_key_and_a_new_read_on_a_rule_change(files, capsys):
    """--person-domain-at first-valid: a person_domain with the at sign gives its first valid domain
    (rule E of pseudonymize.py), the key of build_v0.py --pseudonymize. A change of the rule reads
    the file again."""
    from test_build_v0 import ANON_DIR, anon_module
    P = anon_module()
    tmp, _ = files
    tokens(tmp / "src" / "p3-dataset.parquet", [
        ("acme.com", "a", f"a{AT}acme.com", "e1", "2020-01-01"),
        (f"x{AT}Acme.com", "x", f"x{AT}acme.com", "e2", "2020-01-02"),
        (f"y{AT}localhost", "y", f"y{AT}acme.com", "e3", "2020-01-03"),
    ])
    inputs = tmp / "inputs3.tsv"
    inputs.write_text("project\tpath\np3\tsrc/p3-dataset.parquet\n")
    cache = tmp / "c3" / "cache"
    rule = ["--person-domain-at", "first-valid", "--psl", P.find_psl(), "--anon-dir", str(ANON_DIR)]
    assert ex.main(["--inputs", str(inputs), "--cache", str(cache), "--jobs", "1"] + rule) == 0
    con = duckdb.connect()
    got = con.execute("SELECT domain, sum(tokens) FROM read_parquet(?) GROUP BY 1 ORDER BY 1",
                      [str(cache / "p3.parquet")]).fetchall()
    con.close()
    assert got == [("", 1), ("acme.com", 2)]
    idx = json.loads((cache.parent / "index.json").read_text())
    assert idx["p3"]["domain_rule"] == "first-valid"
    capsys.readouterr()
    assert ex.main(["--inputs", str(inputs), "--cache", str(cache), "--jobs", "1"] + rule) == 0
    assert "1 projects, 0 to read" in capsys.readouterr().out
    assert ex.main(["--inputs", str(inputs), "--cache", str(cache), "--jobs", "1"]) == 0   # keep: read again
    assert "1 projects, 1 to read" in capsys.readouterr().out
    con = duckdb.connect()
    assert con.execute("SELECT count(DISTINCT domain) FROM read_parquet(?)",
                       [str(cache / "p3.parquet")]).fetchone()[0] == 3
    con.close()


def test_rule_e_needs_the_psl(files):
    tmp, inputs = files
    with pytest.raises(SystemExit) as e:
        ex.main(["--inputs", str(inputs), "--cache", str(tmp / "c4"), "--person-domain-at", "first-valid"])
    assert e.value.code == 2
