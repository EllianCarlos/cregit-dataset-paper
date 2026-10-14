"""Tests for rewrite_footer_columns.py (2026-10-09).
Run: python3 -m pytest -q test_rewrite_footer_columns.py   (an interpreter with duckdb and pytest;
     the end-to-end tests need python >= 3.10, as generate_dataset.py does)
     CREGIT=<census cregit>  CREGIT_FIXED=<fixed cregit>  SLICKGITLOG_JAR=<one-jar>  override
     the defaults of rewrite_footer_columns.py (the clones cregit-ec2 and cregit-trailers, the cregit-ec2 one-jar).

The test project is real git: an original bare repository with five commits, and a rewritten
one where each message gets "\\n" + "Former-commit-id: X", as blobExec writes it. The cregit DB
is slickGitLog's DB of the rewritten repository (so its footers hold the defect), and the
census generate_dataset.main() writes the old Parquet from it. The expected Parquet is the
FIXED generate_dataset.main() (branch fix/trailers-original-db) on the same input plus the
original DB (slickGitLog on the original repository). The tool, on the old Parquet, must give
that file row for row. Nothing here reads or writes a census output."""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rewrite_footer_columns as rfc  # noqa: E402

CREGIT = Path(os.environ.get("CREGIT", Path.home() / "Projects/cregit-ec2"))
# The fixed cregit, which reads the footers from the step 3 original DB (--original-db).
CREGIT_FIXED = Path(os.environ.get("CREGIT_FIXED", Path.home() / "Projects/cregit-trailers"))
KEY = "o__r"
ENV = dict(os.environ, GIT_AUTHOR_NAME="A Dev", GIT_AUTHOR_EMAIL="a@example.com",
           GIT_COMMITTER_NAME="A Dev", GIT_COMMITTER_EMAIL="a@example.com",
           GIT_AUTHOR_DATE="2020-01-01T00:00:00Z", GIT_COMMITTER_DATE="2020-01-01T00:00:00Z")
for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):   # a git hook or rebase --exec sets them
    ENV.pop(k, None)

MESSAGES = [
    # A git CLI message ends with "\n": the rewritten one has a blank line before Former-commit-id.
    # The same Reviewed-by twice: one entry.
    "Add a\n\nBody text.\n\nSigned-off-by: A Dev <a@example.com>\n"
    "Reviewed-by: B Rev <b@example.com>\nReviewed-by: B Rev <b@example.com>\n",
    # JGit takes the Reported-by lines; git does not (the paragraph has a non-trailer line).
    # The second address is not in emails and differs only in letter case: one entry.
    "Fix b\n\nReported-by: C Rep <c@example.com>\nReported-by: c rep <C@Example.COM>\n"
    "Closes #12\n",
    # No final newline: the old file already has the Signed-off-by lines. The two addresses
    # are one personid: one entry, the first.
    "Change c\n\nSigned-off-by: A Dev <a@example.com>\n"
    "Signed-off-by: A Dev (work) <a@work.example>",
    "Plain d\n",
    # No address in Thanks-to, twice: both stay. Cc is not one of the 13 keys but gives a
    # footer person.
    "Thanks e\n\nThanks-to: Nobody\nThanks-to: Nobody\nCc: B Rev <b@example.com>\n",
]
FILES = ["a.c", "b.c", "c.c", "d.c", "e.c", "f.c"]
FILE_COMMIT = [0, 1, 2, 3, 4, 0]          # f.c has the same commit as a.c


def git(*args, cwd=None, inp=None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, input=inp, env=ENV, check=True,
                          capture_output=True, text=True).stdout.strip()


def make_repo(path: Path, messages: list[str]) -> list[str]:
    git("init", "-q", "--bare", str(path))
    git("config", "uploadpack.allowFilter", "true", cwd=path)
    tree = git("mktree", cwd=path, inp="")
    shas, parent = [], []
    for m in messages:
        sha = git("commit-tree", tree, *parent, "-F", "-", cwd=path, inp=m)
        shas.append(sha)
        parent = ["-p", sha]
    git("update-ref", "refs/heads/main", shas[-1], cwd=path)
    git("symbolic-ref", "HEAD", "refs/heads/main", cwd=path)
    return shas


def slickgitlog(repo: Path, db: Path) -> Path:
    rfc.slickgitlog("java", rfc.DEFAULT_JAR, repo, db)
    return db


@pytest.fixture(scope="module")
def tools():
    if not rfc.DEFAULT_JAR.is_file():
        pytest.skip(f"no slickGitLog one-jar at {rfc.DEFAULT_JAR}")
    if shutil.which("java") is None or shutil.which("git") is None:
        pytest.skip("needs java and git")
    pytest.importorskip("duckdb")


@pytest.fixture(scope="module")
def project(tools, tmp_path_factory):
    """The original repository, the rewritten one, and their slickGitLog DBs."""
    d = tmp_path_factory.mktemp("project")
    orig = make_repo(d / "orig.git", MESSAGES)
    assert git("cat-file", "commit", orig[2], cwd=d / "orig.git").endswith("<a@work.example>")
    rewritten = make_repo(d / "cregit.git", [m + "\nFormer-commit-id: " + s
                                             for m, s in zip(MESSAGES, orig)])
    return {"dir": d, "orig": orig, "cregit": rewritten,
            "orig_db": slickgitlog(d / "orig.git", d / "orig.db"),
            "cregit_db": slickgitlog(d / "cregit.git", d / "cregit.db")}


def load_gd(root: Path, name: str, needs: str = ""):
    """generate_dataset.py of one checkout, as its own module (two checkouts in one session)."""
    import importlib.util
    if sys.version_info < (3, 10):
        pytest.skip("generate_dataset.py needs python >= 3.10")
    path = root / "generate_dataset" / "generate_dataset.py"
    if not path.exists() or needs not in path.read_text():
        pytest.skip(f"no generate_dataset.py with {needs!r} at {root}")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def gd():
    return load_gd(CREGIT, "generate_dataset_census")


@pytest.fixture
def fixed_gd():
    return load_gd(CREGIT_FIXED, "generate_dataset_fixed", "--original-db")


def persons_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE emails (recordid INTEGER PRIMARY KEY, personid TEXT, fullemail TEXT,
            emailaddr TEXT, emailname TEXT, lcemail TEXT, userid TEXT, domain TEXT,
            autcount INTEGER, comcount INTEGER, dateadded TEXT, checked BOOLEAN, notes TEXT);
        CREATE TABLE persons (personid TEXT PRIMARY KEY, personname TEXT);
    """)
    # Two emails rows for one address: generate_dataset's join then repeats the footer value.
    for i, (pid, name, addr) in enumerate([("a dev", "A Dev", "a@example.com"),
                                          ("a dev", "A D.", "a@example.com"),
                                          ("a dev", "A Dev", "a@work.example"),
                                          ("b rev", "B Rev", "b@example.com")]):
        con.execute("INSERT INTO emails VALUES (?,?,?,?,?,?,?,?,0,0,'',0,NULL)",
                    (i, pid, f"{name} <{addr}>", addr, name, addr, addr.split("@")[0],
                     addr.split("@")[1]))
    con.executemany("INSERT INTO persons VALUES (?,?)", [("a dev", "A Dev"), ("b rev", None)])
    con.commit()
    con.close()
    return path


def generate(gd, monkeypatch, project, workdir: Path, extra=()) -> Path:
    """generate_dataset.main() as ctp calls it, with the cregit DB of the rewritten repository."""
    workdir.mkdir()
    blame, src = workdir / "blame", workdir / "src"
    blame.mkdir()
    src.mkdir()
    for f, i in zip(FILES, FILE_COMMIT):
        (blame / f"{f}.blame").write_text(f"{project['cregit'][i]};1;\tkeyword|int\n")
        (src / f).write_text("int\n")
    cregit_db = shutil.copy(project["cregit_db"], workdir / "cregit.db")
    con = sqlite3.connect(cregit_db)
    con.execute("CREATE TABLE commitmap (cid CHAR(40) PRIMARY KEY, originalcid CHAR(40), "
                "repo VARCHAR(254))")
    con.executemany("INSERT INTO commitmap VALUES (?,?,'')",
                    list(zip(project["cregit"], project["orig"])))
    con.commit()
    con.close()
    pdb = persons_db(workdir / "persons.db")
    sidecar = workdir / "meta.json"
    sidecar.write_text(json.dumps({KEY: {"clone_url": (project["dir"] / "orig.git").as_uri(),
                                         "owner": "o", "repo": "r"}}))
    out = workdir / "out" / f"{KEY}-dataset.parquet"
    monkeypatch.setattr(gd.sys, "argv", [
        "generate_dataset.py", "--blame-dir", str(blame), "--source-dir", str(src),
        "--cregit-db", str(cregit_db), "--persons-db", str(pdb), "--output", str(out),
        "--repo-name", KEY, "--project-meta", str(sidecar), "--project-key", KEY,
        "--memory-limit", "512MB", "--duckdb-threads", "1", *extra])
    gd.main()
    shutil.copy(pdb, out.with_name(f"{KEY}-persons.db"))      # kept next to the Parquet
    return out


def rows(path: Path) -> tuple[list[str], list[tuple]]:
    import duckdb
    rel = duckdb.sql(f"SELECT * FROM read_parquet('{path}')")
    return rel.columns, rel.fetchall()


def col(path: Path, name: str) -> list:
    cols, r = rows(path)
    return [x[cols.index(name)] for x in r]


@pytest.fixture
def old_new(gd, fixed_gd, monkeypatch, project, tmp_path):
    """The census file, and the file that the fixed cregit writes."""
    return (generate(gd, monkeypatch, project, tmp_path / "old"),
            generate(fixed_gd, monkeypatch, project, tmp_path / "new",
                     ("--original-db", str(project["orig_db"]))))


def run(old: Path, *extra) -> int:
    return rfc.main([str(old), *map(str, extra), "--memory-limit", "512MB", "--threads", "1"])


# --------------------------------------------------------------------------- the SQL

def normalized(sql: str) -> str:
    """Without comments and layout."""
    sql = "\n".join(line.split("--")[0] for line in sql.splitlines())
    return " ".join(sql.replace("{{", "{").replace("}}", "}").split())


@pytest.mark.parametrize("alias, ours", [("ftr", "TYPED_SELECT"), ("fpr", "PERSON_SELECT")])
def test_the_sql_is_the_footer_subqueries_of_the_fixed_generate_dataset(alias, ours):
    path = CREGIT_FIXED / "generate_dataset" / "generate_dataset.py"
    if not path.exists():
        pytest.skip(f"no fixed cregit checkout at {CREGIT_FIXED}")
    # One subquery: it must not run past the end of another (") ftr ON", ") fpr ON").
    one = r"(\s*SELECT\s+f\.cid,(?:(?!\)\s+(?:ftr|fpr)\s+ON).)*?GROUP BY f\.cid)"
    m = re.search(r"LEFT JOIN \(" + one + rf"\s*\) {alias} ON", path.read_text(), re.S)
    assert m, f"generate_dataset.py has no {alias} subquery: re-read it before using this tool"
    assert normalized(m.group(1)) == normalized(getattr(rfc, ours))


# --------------------------------------------------------------------------- JGit on a clone

def test_jgit_reads_a_tree0_partial_clone_as_it_reads_a_full_clone(project, tmp_path):
    part = tmp_path / "part.git"
    rfc.clone((project["dir"] / "orig.git").as_uri(), part)
    assert git("config", "remote.origin.partialclonefilter", cwd=part) == "tree:0"
    db = slickgitlog(part, tmp_path / "part.db")
    for sql in ("SELECT * FROM commits ORDER BY cid", "SELECT * FROM footers ORDER BY cid, idx"):
        assert (sqlite3.connect(db).execute(sql).fetchall()
                == sqlite3.connect(project["orig_db"]).execute(sql).fetchall())


def test_the_rewritten_db_holds_the_defect(project):
    """The census input: only Former-commit-id, except for the message with no final newline."""
    got = sqlite3.connect(project["cregit_db"]).execute(
        "SELECT cid, key FROM footers ORDER BY cid, idx").fetchall()
    keys = {c: [k for cc, k in got if cc == c] for c in project["cregit"]}
    assert [keys[c] for c in project["cregit"]] == [
        ["Former-commit-id"], ["Former-commit-id"],
        ["Signed-off-by", "Signed-off-by", "Former-commit-id"],
        ["Former-commit-id"], ["Former-commit-id"]]


# --------------------------------------------------------------------------- end to end

def test_rewriting_the_old_parquet_equals_the_fixed_generate_dataset(old_new, tmp_path, capsys):
    old, new = old_new
    assert col(old, "footer_signed_off_by").count([]) == 5      # the defect: only c.c is right
    fixed, report = tmp_path / "fixed.parquet", tmp_path / "report.tsv"
    assert run(old, "--out", fixed, "--report", report) == 0
    assert rows(fixed) == rows(new)
    # a@example.com has two emails rows (the census SQL gave it twice), and a@work.example is
    # the same personid: one entry, the first value.
    assert col(old, "footer_signed_off_by")[2] == ["A Dev <a@example.com>"] * 2 + [
        "A Dev (work) <a@work.example>"]
    assert col(fixed, "footer_signed_off_by") == [
        ["A Dev <a@example.com>"], [], ["A Dev <a@example.com>"], [], [],
        ["A Dev <a@example.com>"]]
    assert col(fixed, "footer_reviewed_by")[0] == ["B Rev <b@example.com>"]
    assert col(fixed, "footer_reported_by")[1] == ["C Rep <c@example.com>"]
    assert col(fixed, "footer_thanks_to")[4] == ["Nobody", "Nobody"]
    assert col(fixed, "footer_personids")[4] == ["b rev"]
    assert col(fixed, "footer_person_names")[0] == ["A Dev", "b rev"]
    head, line = report.read_text().splitlines()
    rec = dict(zip(head.split("\t"), line.split("\t")))
    assert (rec["commits"], rec["before"], rec["after"], rec["already_set"]) == ("5", "1", "4", "1")
    assert (rec["signed-off-by"], rec["reviewed-by"], rec["reported-by"]) == ("2", "1", "1")
    assert "1 -> 4 with a typed trailer" in capsys.readouterr().out
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".footer")] == []


def test_one_row_chunks_keep_the_row_order(old_new, project, tmp_path):
    old, new = old_new
    fixed = tmp_path / "fixed.parquet"
    assert run(old, "--out", fixed, "--chunk-rows", 1,
               "--git-dir", project["dir"] / "orig.git") == 0
    assert rows(fixed) == rows(new)


def test_values_on_the_wrong_rows_are_refused(old_new, monkeypatch, tmp_path, capsys):
    """compare() is the guard against a row order change: give it one."""
    old, _ = old_new
    real = rfc.rewrite
    monkeypatch.setattr(rfc, "rewrite",
                        lambda con, src, dst, parts: real(con, src, dst, parts[::-1]))
    out = tmp_path / "x.parquet"
    assert run(old, "--out", out, "--chunk-rows", 1) == 1
    assert "commits have footer values that are not the recomputed ones" in capsys.readouterr().err
    assert not out.exists()


def test_a_second_run_changes_nothing(old_new, tmp_path):
    _, new = old_new
    again = tmp_path / "again.parquet"
    assert run(new, "--out", again) == 0
    assert rows(again) == rows(new)


def test_in_place_replaces_the_file_and_leaves_no_temp(old_new):
    old, new = old_new
    assert run(old, "--in-place") == 0
    assert rows(old) == rows(new)
    assert sorted(p.name for p in old.parent.iterdir()) == sorted(
        [old.name, f"{KEY}-persons.db"])


# --------------------------------------------------------------------------- refusals

def test_out_refuses_an_existing_file(old_new, tmp_path):
    old, _ = old_new
    out = tmp_path / "x.parquet"
    out.write_text("keep\n")
    assert run(old, "--out", out) == 1
    assert out.read_text() == "keep\n"


def test_refuses_a_commit_that_the_clone_does_not_have(old_new, project, tmp_path, capsys):
    old, _ = old_new
    repo = project["dir"] / "orig.git"
    git("branch", "short", project["orig"][1], cwd=repo)
    short = tmp_path / "short.git"
    git("clone", "-q", "--bare", "--single-branch", "--branch", "short", repo.as_uri(), str(short))
    before = old.read_bytes()
    out = tmp_path / "x.parquet"
    assert run(old, "--out", out, "--git-dir", short) == 1
    assert "3 original_commit_sha values are not commits of the clone" in capsys.readouterr().err
    assert not out.exists() and old.read_bytes() == before


def test_refuses_a_persons_db_that_did_not_make_the_file(old_new, tmp_path, capsys):
    old, _ = old_new
    bad = shutil.copy(old.with_name(f"{KEY}-persons.db"), tmp_path / "bad.db")
    con = sqlite3.connect(bad)
    con.execute("UPDATE emails SET personid = 'someone else' WHERE emailname = 'A Dev'")
    con.commit()
    con.close()
    assert run(old, "--out", tmp_path / "x.parquet", "--persons-db", bad) == 1
    assert "not the DB that generate_dataset used" in capsys.readouterr().err


def test_refuses_old_values_that_the_original_commits_do_not_give(old_new, tmp_path, capsys):
    import duckdb
    old, _ = old_new
    bad = tmp_path / "bad.parquet"
    duckdb.execute(f"COPY (SELECT * REPLACE (['Someone <s@x.org>'] AS footer_acked_by) "
                   f"FROM read_parquet('{old}')) TO '{bad}' (FORMAT PARQUET)")
    shutil.copy(old.with_name(f"{KEY}-persons.db"), tmp_path / f"{KEY}-persons.db")
    assert run(bad, "--out", tmp_path / "x.parquet") == 1
    assert "5 commits hold non-empty footer values that differ" in capsys.readouterr().err
