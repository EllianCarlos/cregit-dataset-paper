"""Tests of release_tools.py (fake data only). Run:
    PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider test/
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import duckdb
import pytest

sys.dont_write_bytecode = True
KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_tools as RT  # noqa: E402
import fake  # noqa: E402

if not (fake.FILL_RELEASE.is_file() and fake.DB.is_file()):
    pytest.skip("set COMPANIES_DB (see ../README.md)", allow_module_level=True)

AT = chr(64)
A_PROJECTS = [("alpha__one", 7, "v1"), ("confluentinc__schema-registry", 5, "x1k"), ("gamma__three", 3, "pf17"),
              ("delta__four", 4, "x1k")]
B_PROJECTS = [("BRL-CAD__brlcad", 6, "brl")]


def run(*args) -> int:
    return RT.main([str(x) for x in args])


def sources_fn(tmp_path):
    links = tmp_path / "links"
    fake.make_links(links, [p for p, _, _ in A_PROJECTS + B_PROJECTS])
    a, b = tmp_path / "a", tmp_path / "b"
    fake.make_source(a, A_PROJECTS, fake.REG_A, links)
    fake.make_source(b, B_PROJECTS, fake.REG_B, links)
    return a, b


def inputs_fn(tmp_path):
    """The input prefix of release 2: the project files of A and B with the new footer keys, and organizations/."""
    links = tmp_path / "links"
    mapping = json.loads((links / "links.json").read_text())["mapping_sha256"]
    d = tmp_path / "in"
    fake.make_input(d, [(p, r, fake.REG_A) for p, r, _ in A_PROJECTS] + [(p, r, fake.REG_B) for p, r, _ in B_PROJECTS],
                    mapping)
    return d


def docs_fn(tmp_path):
    d = tmp_path / "docs-src"
    (d / "docs").mkdir(parents=True)
    (d / "tools").mkdir()
    (d / "_staging").mkdir()
    (d / "parquet").mkdir()
    (d / "organizations").mkdir()
    (d / "tools" / "__pycache__").mkdir()
    (d / "README.md").write_text("A test release.\n")
    (d / "docs" / "SCHEMA.md").write_text("The schema.\n")
    shutil.copyfile(fake.FILL_RELEASE, d / "tools" / "fill_release.py")
    (d / "_staging" / "PLAN.md").write_text("not in the release\n")
    (d / "parquet" / "TODO.txt").write_text("x\n")
    (d / "organizations" / "TODO.txt").write_text("x\n")
    (d / "docs" / "SCHEMA.md.before-organization").write_text("a backup of release-staging\n")
    (d / "tools" / "__pycache__" / "x.pyc").write_bytes(b"x")
    (d / ".hidden").write_text("x\n")
    return d


sources = pytest.fixture(sources_fn, name="sources")
docs = pytest.fixture(docs_fn, name="docs")


@pytest.fixture(name="inputs")
def inputs_fixture(tmp_path, sources):
    return inputs_fn(tmp_path)


def assemble(tmp_path, sources, docs, expect=5, inp=None) -> Path:
    a, b = sources
    root = tmp_path / "R"
    rc = run("assemble", "--a", a, "--b", b, "--docs", docs, "--root", root, "--expect", expect,
             "--names-out", tmp_path / "names.txt", *(["--input", inp] if inp else []))
    assert rc == 0
    return root


# ---------------------------------------------------------------- the 10,754-file count logic, small
def test_assemble_counts_and_documents(tmp_path, sources, docs):
    root = assemble(tmp_path, sources, docs)
    files = sorted(p.name for p in (root / "parquet").iterdir())
    assert len(files) == 5 and "BRL-CAD__brlcad-dataset.parquet" in files
    assert (root / "README.md").is_file() and (root / "docs/SCHEMA.md").is_file() and (root / "tools/fill_release.py").is_file()
    assert not (root / "_staging").exists() and not (root / "parquet/TODO.txt").exists()
    assert not (root / "organizations").exists() and not (root / ".hidden").exists()
    assert not (root / "docs/SCHEMA.md.before-organization").exists()                  # a backup is not a document
    assert not (root / "tools/__pycache__").exists()
    assert (tmp_path / "names.txt").read_text().split() == sorted(p for p, _, _ in A_PROJECTS + B_PROJECTS)
    a_file = sources[0] / "parquet/alpha__one-dataset.parquet"
    assert os.stat(root / "parquet/alpha__one-dataset.parquet").st_ino == os.stat(a_file).st_ino  # a hard link


def test_assemble_links_the_file_of_a_symbolic_link(tmp_path, sources, docs):
    a, b = sources
    real = tmp_path / "store"
    real.mkdir()
    f = a / "parquet/alpha__one-dataset.parquet"
    f.rename(real / f.name)
    os.symlink(real / f.name, f)                              # as the fake aws downloads a Parquet file
    root = assemble(tmp_path, sources, docs)
    g = root / "parquet/alpha__one-dataset.parquet"
    assert not g.is_symlink() and os.stat(g).st_ino == os.stat(real / f.name).st_ino
    assert run("guard", "--root", root, "--names", tmp_path / "names.txt") == 0


def test_assemble_refuses_another_total_and_an_overlap(tmp_path, sources, docs):
    a, b = sources
    assert run("assemble", "--a", a, "--b", b, "--docs", docs, "--root", tmp_path / "R1", "--expect", 6,
               "--names-out", tmp_path / "n1") == 1
    fake.make_source(tmp_path / "b2", [("alpha__one", 7, "brl")], fake.REG_B)
    assert run("assemble", "--a", a, "--b", tmp_path / "b2", "--docs", docs, "--root", tmp_path / "R2",
               "--expect", 4, "--names-out", tmp_path / "n2") == 1


def test_verify_source_ok_and_problems(tmp_path, sources, capsys):
    a, b = sources
    assert run("verify-source", "--dir", a, "--label", "A", "--expect", 4, "--expect-rows", 19, "--jobs", 2,
               "--out", tmp_path / "a.json") == 0
    rep = json.loads((tmp_path / "a.json").read_text())
    assert rep["files"] == 4 and rep["rows"] == 19 and rep["registry_sha256"] == fake.REG_A
    assert run("verify-source", "--dir", a, "--label", "A", "--expect", 5, "--out", tmp_path / "x.json") == 1
    (a / "registry.parquet").write_bytes(b"x")                       # a registry in a release folder
    assert run("verify-source", "--dir", a, "--label", "A", "--expect", 4, "--out", tmp_path / "x.json") == 1
    (a / "registry.parquet").unlink()
    with open(a / "parquet/alpha__one-dataset.parquet", "ab") as fh:  # another sha256
        fh.write(b"\0")
    assert run("verify-source", "--dir", a, "--label", "A", "--expect", 4, "--out", tmp_path / "x.json") == 1
    assert "another sha256" in capsys.readouterr().out


def test_s3_list_check(tmp_path):
    base = "dataset-final/release/x"
    ok = [f"2026-10-27 06:30:06 10 {base}/{f}" for f in RT.SMALL_FILES]
    ok += [f"2026-10-27 06:30:06 10 {base}/parquet/confluentinc__schema-registry-dataset.parquet",
           f"2026-10-27 06:30:06 10 {base}/parquet/a__b-dataset.parquet"]
    (tmp_path / "ls.txt").write_text("\n".join(ok) + "\n")
    assert run("s3-list-check", "--listing", tmp_path / "ls.txt", "--prefix", base, "--expect", 2) == 0
    (tmp_path / "ls2.txt").write_text("\n".join(ok + [f"2026-10-27 06:30:06 10 {base}/registry.parquet"]) + "\n")
    assert run("s3-list-check", "--listing", tmp_path / "ls2.txt", "--prefix", base, "--expect", 2) == 1


# ---------------------------------------------------------------- registry and salt names
def test_guard_refuses_a_registry_file_but_accepts_a_project_name_with_the_word(tmp_path, sources, docs, capsys):
    root = assemble(tmp_path, sources, docs)
    names = tmp_path / "names.txt"
    assert run("guard", "--root", root, "--names", names) == 0          # confluentinc__schema-registry is accepted
    (root / "organizations").mkdir()
    (root / "organizations/registry.parquet").write_bytes(b"x")
    assert run("guard", "--root", root, "--names", names) == 1
    assert "a file named registry" in capsys.readouterr().out
    (root / "organizations/registry.parquet").unlink()
    (root / "docs/salt").write_text("x\n")
    assert run("guard", "--root", root, "--names", names) == 1
    (root / "docs/salt").unlink()
    (root / "parquet/zeta__other-dataset.parquet").write_bytes(b"x")    # a project file outside the list
    assert run("guard", "--root", root, "--names", names) == 1
    (root / "parquet/zeta__other-dataset.parquet").unlink()
    (root / "tools/__pycache__").mkdir()
    assert run("guard", "--root", root, "--names", names) == 1
    (root / "tools/__pycache__").rmdir()
    os.symlink(root / "README.md", root / "docs/LINK.md")
    assert run("guard", "--root", root, "--names", names) == 1


# ---------------------------------------------------------------- both registry hashes
def test_pseudo_merge_names_both_registries(tmp_path, sources):
    a, b = sources
    out = tmp_path / "p.json"
    assert run("pseudo-merge", "--a", a / "pseudonymization.json", "--b", b / "pseudonymization.json", "--a-files", 4,
               "--b-projects", "BRL-CAD__brlcad", "--want-a", fake.REG_A[:12], "--want-b", fake.REG_B[:12], "--out", out) == 0
    j = json.loads(out.read_text())
    regs = [r["registry_sha256"] for r in j["registries"]]
    assert regs == [fake.REG_A, fake.REG_B]
    assert j["registries"][0]["files"] == 4 and j["registries"][1]["projects"] == ["BRL-CAD__brlcad"]
    assert "registry_sha256" not in j and j["pseudonymization_version"] == "2"
    assert AT not in out.read_text()
    # a wrong pin, and a shared key with another value, stop the merge
    assert run("pseudo-merge", "--a", a / "pseudonymization.json", "--b", b / "pseudonymization.json", "--a-files", 4,
               "--b-projects", "BRL-CAD__brlcad", "--want-a", "deadbeef0000", "--want-b", fake.REG_B[:12],
               "--out", tmp_path / "q.json") == 1
    jb = json.loads((b / "pseudonymization.json").read_text())
    jb["psl_sha256"] = "cd" * 32
    (b / "pseudonymization.json").write_text(json.dumps(jb))
    assert run("pseudo-merge", "--a", a / "pseudonymization.json", "--b", b / "pseudonymization.json", "--a-files", 4,
               "--b-projects", "BRL-CAD__brlcad", "--want-a", fake.REG_A[:12], "--want-b", fake.REG_B[:12],
               "--out", tmp_path / "r.json") == 1


def test_schema_checks_the_registry_of_each_file(tmp_path, sources, inputs, docs, capsys):
    a, b = sources
    root = assemble(tmp_path, sources, docs, inp=inputs)
    pj = root / "pseudonymization.json"
    run("pseudo-merge", "--a", a / "pseudonymization.json", "--b", b / "pseudonymization.json", "--a-files", 4,
        "--b-projects", "BRL-CAD__brlcad", "--want-a", fake.REG_A[:12], "--want-b", fake.REG_B[:12], "--out", pj)
    mapping = json.loads((a / "links.json").read_text())["mapping_sha256"]
    args = ["schema", "--root", root, "--fill-release", root / "tools/fill_release.py", "--pseudonymization", pj,
            "--mapping", mapping, "--ov", "v4.9", "--expect", 5, "--expect-rows", 25, "--jobs", 2, "--out", tmp_path / "s.tsv"]
    assert run(*args) == 0
    rows = (tmp_path / "s.tsv").read_text().splitlines()
    assert len(rows) == 6 and rows[0].split("\t") == ["project", "columns", "rows", "registry", "problems"]
    # the BRL-CAD file with registry A, and a file of 70 columns, are problems
    f = root / "parquet/BRL-CAD__brlcad-dataset.parquet"
    f.unlink()
    fake.write_project(f, "BRL-CAD__brlcad", 6, fake.REG_A, mapping)
    g = root / "parquet/delta__four-dataset.parquet"
    g.unlink()
    fake.write_project(g, "delta__four", 4, fake.REG_A, mapping, columns=fake.schema2()[:70])
    assert run(*args) == 1
    out = capsys.readouterr().out
    assert "BRL-CAD__brlcad: registry" in out and "delta__four: not the 71 columns" in out


def test_schema_stops_on_the_old_footer_keys_of_release_1(tmp_path, sources, docs, capsys):
    a, b = sources
    root = assemble(tmp_path, sources, docs)            # the files of the final writes: the old spelling
    pj = root / "pseudonymization.json"
    run("pseudo-merge", "--a", a / "pseudonymization.json", "--b", b / "pseudonymization.json", "--a-files", 4,
        "--b-projects", "BRL-CAD__brlcad", "--want-a", fake.REG_A[:12], "--want-b", fake.REG_B[:12], "--out", pj)
    mapping = json.loads((a / "links.json").read_text())["mapping_sha256"]
    assert run("schema", "--root", root, "--fill-release", root / "tools/fill_release.py", "--pseudonymization", pj,
               "--mapping", mapping, "--ov", "v4.9", "--expect", 5, "--jobs", 2, "--out", tmp_path / "s.tsv") == 1
    out = capsys.readouterr().out
    assert "footer key with the old spelling: organisations_mapping_sha256, organisations_version" in out
    assert "organizations_version None" in out


# ---------------------------------------------------------------- layers, links, ledgers, classes
def test_layers(tmp_path, sources):
    a, b = sources
    out = tmp_path / "layers.tsv"
    assert run("layers", "--results-a", a / "results.tsv", "--results-b", b / "results.tsv", "--b-layer", "v1",
               "--expect-v1", 3, "--expect-x1k", 2, "--out", out) == 0
    rows = dict(l.split("\t") for l in out.read_text().splitlines()[1:])
    assert rows == {"alpha__one": "v1", "gamma__three": "v1", "BRL-CAD__brlcad": "v1",
                    "confluentinc__schema-registry": "x1k", "delta__four": "x1k"}
    assert run("layers", "--results-a", a / "results.tsv", "--results-b", b / "results.tsv", "--expect-v1", 2,
               "--expect-x1k", 3, "--out", tmp_path / "x.tsv") == 1
    assert run("layers", "--results-a", a / "results.tsv", "--results-b", b / "results.tsv", "--prefixes", "v1=v1 x1k=x1k",
               "--expect-v1", 3, "--expect-x1k", 2, "--out", tmp_path / "y.tsv") == 1     # pf17 has no layer


def test_links_check(tmp_path, sources, capsys):
    a, b = sources
    mapping = json.loads((b / "links.json").read_text())["mapping_sha256"]
    assert run("links-check", "--a", a, "--b", b, "--mapping", mapping[:12], "--ov", "v4.9") == 0
    assert run("links-check", "--a", a, "--b", b, "--mapping", "0" * 12) == 1
    (b / "project_links.parquet").write_bytes(b"x")
    assert run("links-check", "--a", a, "--b", b, "--mapping", mapping[:12]) == 1


def test_links_rewrite_cuts_machine_paths(tmp_path, sources):
    a, b = sources
    out, rep = tmp_path / "links.json", tmp_path / "rw.tsv"
    assert run("links-rewrite", "--src", b / "links.json", "--out", out, "--report", rep) == 0
    src, got = json.loads((b / "links.json").read_text()), json.loads(out.read_text())
    assert got["inputs"]["db"] == "companies.v4.9.duckdb"
    assert got["inputs"]["caches"] == ["cache", "cache"]
    assert got["inputs"]["sidecars"] == ["project_meta.v1.final.json"]
    assert got["mapping_sha256"] == src["mapping_sha256"] and got["outputs"] == src["outputs"]
    # release 2: the key organisations_version of the final write gets the American spelling, its value stays
    assert "organisations_version" not in got and got["organizations_version"] == src["organisations_version"]
    rest = {k: v for k, v in got.items() if k not in ("inputs", "organizations_version")}
    assert rest == {k: v for k, v in src.items() if k not in ("inputs", "organisations_version")}
    assert len(rep.read_text().splitlines()) == 1 + 4 + 1
    assert "\tkey organisations_version\tkey organizations_version" in rep.read_text()
    assert run("no-paths", out) == 0 and run("no-paths", b / "links.json") == 1


def test_no_paths_finds_machine_paths_only(tmp_path, capsys):
    root = tmp_path / "R"
    (root / "docs").mkdir(parents=True)
    (root / "README.md").write_text("See https://example.org/home/data and the folder data/x.\n")
    (root / "docs/A.md").write_text("ok\n")
    assert run("no-paths", "--root", root) == 0
    for text in ("the file /home/u/x.txt\n", "`/data1/final/in`\n", "path=/tmp/x\n", '"/root/ssm"\n', "/data2/x\n"):
        (root / "docs/A.md").write_text("ok\n" + text)
        assert run("no-paths", "--root", root) == 1
    assert "A.md: lines 2" in capsys.readouterr().out


def test_ledger_pick_classes(tmp_path):
    schema = tmp_path / "schema.tsv"
    rows = {"p1": 10, "p2": 20, "p3": 30, "p4": 40}
    schema.write_text("project\tcolumns\trows\tregistry\tproblems\n" + "".join(f"{p}\t71\t{r}\tx\t\n" for p, r in rows.items()))
    led = tmp_path / "led"
    fake.make_ledgers(led, rows, skip=("p4",), other_rows=("p2",), no_rows=("p3",))
    out, rep = tmp_path / "picked.jsonl", tmp_path / "pick.tsv"
    assert run("ledger-pick", "--ledgers", led, "--schema", schema, "--out", out, "--report", rep) == 0
    cls = dict((l.split("\t")[0], l.split("\t")[1]) for l in rep.read_text().splitlines()[1:])
    assert cls == {"p1": "rows", "p2": "gap-other-rows", "p3": "one-run-no-rows", "p4": "gap-no-record"}
    picked = [json.loads(l) for l in out.read_text().splitlines()]
    assert [p["project"] for p in picked] == ["p1", "p3"]
    assert all(p["checked_out_sha"] == "a" * 40 for p in picked)                 # the test ledger is skipped
    assert set(picked[0]) == {"step", "status", "project", "end_utc", "checked_out_sha", "snapshot_sha", "tools"}


def test_ledger_merge(tmp_path, capsys):
    schema = tmp_path / "schema.tsv"
    schema.write_text("project\tcolumns\trows\tregistry\tproblems\n" + "".join(f"{p}\t71\t1\tx\t\n" for p in ("p1", "p2", "p3", "p4")))
    rec = lambda p, sha="a" * 40, cregit="c1": {"step": "project", "status": "done", "project": p, "end_utc": "t",
                                                 "checked_out_sha": sha, "snapshot_sha": "",
                                                 "tools": {"cregit_commit": cregit, "ctp_commit": "k1"}}
    write = lambda f, rs: f.write_text("".join(json.dumps(r) + "\n" for r in rs))
    proven, picked, out = tmp_path / "proven.jsonl", tmp_path / "picked.jsonl", tmp_path / "final.jsonl"
    write(proven, [rec("p1"), rec("p2", cregit="c2")])                         # p2: the gap of ledger-pick
    write(picked, [rec("p1"), rec("p3")])                                     # p4: no record anywhere
    assert run("ledger-merge", "--proven", proven, "--picked", picked, "--schema", schema, "--out", out) == 0
    got = {json.loads(l)["project"]: json.loads(l) for l in out.read_text().splitlines()}
    assert sorted(got) == ["p1", "p2", "p3"] and got["p2"]["tools"]["cregit_commit"] == "c2"
    assert "proven 2; ledger-pick only 1; no record 1; 0 problems; picked 3;" in capsys.readouterr().out
    write(picked, [rec("p1", sha="b" * 40), rec("p3")])                       # two records that disagree stop
    assert run("ledger-merge", "--proven", proven, "--picked", picked, "--schema", schema, "--out", out) == 1
    write(proven, [rec("p1"), rec("zz")])                                     # a project not in the release stops
    write(picked, [rec("p1")])
    assert run("ledger-merge", "--proven", proven, "--picked", picked, "--schema", schema, "--out", out) == 1
    capsys.readouterr()
    write(proven, [rec("p1"), rec("p1", cregit="c2")])                       # one project twice, other commits
    assert run("ledger-merge", "--proven", proven, "--picked", picked, "--schema", schema, "--out", out) == 1
    assert "p1: two records with other commits in proven.jsonl" in capsys.readouterr().out
    write(proven, [rec("p1"), rec("p1")])                                    # the same record twice is no problem
    assert run("ledger-merge", "--proven", proven, "--picked", picked, "--schema", schema, "--out", out) == 0
    for rs in ([dict(rec("p1"), tools={})], [dict(rec("p2"), checked_out_sha="")]):  # a proven record with no commit
        write(proven, rs)
        assert run("ledger-merge", "--proven", proven, "--picked", picked, "--schema", schema, "--out", out) == 1
        assert "the proven record has no checked_out_sha, cregit_commit or ctp_commit" in capsys.readouterr().out


def test_ledger_cleaner_replaces_a_user_name_that_holds_a_machine_value():
    cl = RT.LedgerCleaner(RT.deny_words(["fake-bucket-123456789012-usw2"]))     # a bucket name with an account id
    assert cl.text("from fake-bucket-123456789012-usw2 to i-0123456789abcdef0", "note") == "from user to machine"



# ---------------------------------------------------------------- ledger-clean, ledger-clean-check
LC_ROWS = {"p1": 10, "p2": 20, "p3": 30}


def ledger_clean(tmp_path, out_name="ledgers.parquet"):
    led = tmp_path / "led"
    recs = fake.make_run_ledgers(led, LC_ROWS, copy=("p2",), note=("p3",))
    records = tmp_path / "records.jsonl"
    records.write_text("".join(json.dumps(r) + "\n" for r in recs))
    out, rep = tmp_path / out_name, tmp_path / (out_name + ".tsv")
    rc = run("ledger-clean", "--records", records, "--ledgers", led, "--out", out, "--report", rep)
    return rc, out, rep, records, recs


def test_ledger_clean_keeps_the_picked_run_and_cleans_it(tmp_path, capsys):
    rc, out, rep, records, recs = ledger_clean(tmp_path)
    assert rc == 0
    con = duckdb.connect()
    cols = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(out)]).fetchall()]
    assert cols == [c for c, _ in RT.LEDGER_COLUMNS]
    assert RT.kv_of(con, out)["records_sha256"] == hashlib.sha256(records.read_bytes()).hexdigest()
    rows = con.execute("SELECT project, run_id, attempt, seq, step, status, argv, parquet_file, parquet_rows, "
                       "tools, flags, extra FROM read_parquet(?)", [str(out)]).fetchall()
    assert [r[0] for r in rows] == ["p1"] * 5 + ["p2"] * 5 + ["p3"] * 5     # attempt 2 only; the copy adds no row
    assert {(r[1], r[2]) for r in rows} == {("20261001T000000Z-11", 2)}
    assert [r[3] for r in rows[:5]] == [1, 2, 3, 4, 5]
    assert [(r[4], r[5]) for r in rows[:5]] == [("resolve", "ok"), ("clone", "ok"), ("validate", "ok"),
                                                ("cleanup", "ok"), ("project", "done")]
    clone, done = rows[1], rows[4]
    assert clone[6] == ["python3", "pin.py", "--dest", "p1.git", "--out=p1"]
    assert done[7] == "p1-dataset.parquet" and done[8] == 10
    tools, flags = json.loads(done[9]), json.loads(done[10])
    assert tools["srcml_path"] == "/nix/store/0abc-srcml-1.1.0/bin/srcml"         # a Nix store path stays
    assert flags["argv"][-1] == "manifest.b1.tsv" and flags["config_path"] == "b1.cfg"
    assert "cregit_dir" not in flags and "output_dir" not in flags
    extra = [json.loads(r[11]) if r[11] else {} for r in rows]
    assert extra[0]["resolve"]["seeded"] == "copied by user from latest.json"
    assert "dest" not in extra[1]["pin"] and "log" not in extra[1] and "cleanup" not in extra[3]
    assert "author" not in extra[12] and extra[12]["note"] == "ran on machine at machine"
    text = out.read_bytes()
    for word in (b"/data3", b"/home", b"ec2-user", b"i-0123", b"10.1.2.3", b"ip-10", b"queue_pos"):
        assert word not in text
    tsv = rep.read_text()
    for key in ("queue_pos\tkey dropped (machine state)", "cleanup\tkey dropped (machine state)",
                "pin.dest\tkey dropped (machine state)", "author\tkey dropped (identity)",
                "note\tmachine value replaced by machine\t2", "resolve.seeded\tuser name replaced by user\t3"):
        assert key in tsv
    assert run("ledger-clean-check", "--file", out, "--records", records) == 0
    assert run("no-at", out) == 0 and run("no-paths", out) == 0
    # the same input gives the same bytes
    (tmp_path / "again").mkdir()
    assert ledger_clean(tmp_path / "again")[0] == 0
    assert (tmp_path / "again/ledgers.parquet").read_bytes() == out.read_bytes()


def test_ledger_clean_stops_on_a_missing_or_ambiguous_run(tmp_path, capsys):
    rc, out, rep, records, recs = ledger_clean(tmp_path)
    led = tmp_path / "led"
    bad = dict(recs[0], end_utc="2026-10-01T09:00:00+00:00")                       # no done row has this end
    (tmp_path / "bad.jsonl").write_text(json.dumps(bad) + "\n")
    assert run("ledger-clean", "--records", tmp_path / "bad.jsonl", "--ledgers", led, "--out", tmp_path / "x.parquet",
               "--report", tmp_path / "x.tsv") == 1
    assert "no done row with the commits of the record" in capsys.readouterr().out
    rs, _ = fake.run_rows("p1", 10, run_id="20261005T000000Z-55")                  # the same done row, another run
    (led / "batch9").mkdir()
    (led / "batch9/ledger.jsonl").write_text(json.dumps(rs[-1]) + "\n")
    assert run("ledger-clean", "--records", records, "--ledgers", led, "--out", tmp_path / "y.parquet",
               "--report", tmp_path / "y.tsv") == 1
    assert "p1: the done rows name 2 runs" in capsys.readouterr().out
    assert not (tmp_path / "y.parquet").exists()


def test_ledger_clean_check_finds_problems(tmp_path, capsys):
    rc, out, rep, records, recs = ledger_clean(tmp_path)
    assert rc == 0
    schema = tmp_path / "schema.tsv"
    schema.write_text("project\tcolumns\trows\tregistry\tproblems\n" + "".join(f"{p}\t71\t{r}\tx\t\n" for p, r in LC_ROWS.items()))
    targets = tmp_path / "targets.tsv"
    targets.write_text("project\tsha256\n" + "".join(f"{p}\t{hashlib.sha256(p.encode()).hexdigest()}\n" for p in LC_ROWS))
    assert run("ledger-clean-check", "--file", out, "--records", records, "--schema", schema, "--targets", targets) == 0
    assert "sha256 of the run file for 3, rows of the release file for 3" in capsys.readouterr().out
    schema.write_text(schema.read_text() + "p4\t71\t1\tx\t\n")                      # a project with no rows
    assert run("ledger-clean-check", "--file", out, "--records", records, "--schema", schema) == 1
    assert "p4: no rows" in capsys.readouterr().out
    other = [dict(r, checked_out_sha="b" * 40) if r["project"] == "p2" else r for r in recs]
    (tmp_path / "other.jsonl").write_text("".join(json.dumps(r) + "\n" for r in other))
    assert run("ledger-clean-check", "--file", out, "--records", tmp_path / "other.jsonl") == 1
    assert "p2: the done row does not have the commits of the record" in capsys.readouterr().out
    con = duckdb.connect()
    for expr, word in (("'/data1/x/' || parquet_file", "a path"), ("'a' || chr(64) || 'b'", "the at sign"),
                       ("'i-0123456789abcdef0'", "a machine value"), ("'ec2-user'", "a user name")):
        bad = tmp_path / "bad.parquet"
        con.execute(f"COPY (SELECT * REPLACE (CASE WHEN seq = 5 AND project = 'p1' THEN {expr} ELSE parquet_file END "
                    f"AS parquet_file) FROM read_parquet('{out}')) TO '{bad}' (FORMAT parquet)")
        assert run("ledger-clean-check", "--file", bad, "--records", records) == 1
        assert f"parquet_file: {word} (1 values)" in capsys.readouterr().out
    con.execute(f"COPY (SELECT * REPLACE ('{{\"log\":\"x\"}}' AS extra) FROM read_parquet('{out}')) TO '{bad}' (FORMAT parquet)")
    assert run("ledger-clean-check", "--file", bad, "--records", records) == 1
    assert "log{key}: a dropped key" in capsys.readouterr().out


def test_guard_and_no_paths_accept_the_ledgers_file_only(tmp_path, sources, docs, capsys):
    root = assemble(tmp_path, sources, docs)
    names = tmp_path / "names.txt"
    rc, out, rep, records, recs = ledger_clean(tmp_path)
    shutil.copyfile(out, root / RT.LEDGERS_FILE)
    assert run("guard", "--root", root, "--names", names) == 0
    assert run("no-paths", "--root", root) == 0
    assert run("no-at", "--root", root) == 0
    duckdb.execute(f"COPY (SELECT '/data1/x/y' AS v) TO '{root}/other.parquet' (FORMAT parquet)")
    assert run("guard", "--root", root, "--names", names) == 1
    assert "a Parquet file outside parquet/ and organizations/: other.parquet" in capsys.readouterr().out
    assert run("no-paths", "--root", root) == 1
    assert "MACHINE PATH: other.parquet: 1 rows" in capsys.readouterr().out


def test_check_classes(tmp_path):
    mark = "TO" + "DO"
    f = tmp_path / "c.txt"
    f.write_text(f"README.md:3: {mark} marker\nMANIFEST.tsv: a__b has no run_commit\ncheck: 2 problems\n")
    assert run("check-classes", "--check-out", f) == 0
    f.write_text(f"README.md:3: {mark} marker\ndocs/X.md:2: the at sign\ncheck: 2 problems\n")
    assert run("check-classes", "--check-out", f) == 1


def test_no_at(tmp_path):
    (tmp_path / "a.txt").write_text("fine\n")
    assert run("no-at", tmp_path / "a.txt") == 0
    (tmp_path / "b.json").write_text('{"x": "a' + AT + 'b"}\n')
    assert run("no-at", tmp_path / "a.txt", tmp_path / "b.json") == 1
    duckdb.execute(f"COPY (SELECT 'x' || chr(64) AS v) TO '{tmp_path}/t.parquet' (FORMAT parquet)")
    assert run("no-at", tmp_path / "t.parquet") == 1


def test_sums_compare(tmp_path, sources, docs):
    a, b = sources
    root = assemble(tmp_path, sources, docs)
    lines = [l for l in (a / "SHA256SUMS").read_text().splitlines() + (b / "SHA256SUMS").read_text().splitlines()]
    (root / "SHA256SUMS").write_text("\n".join(sorted(lines, key=lambda l: l.split("  ")[1]) + ["00  README.md"]) + "\n")
    assert run("sums-compare", "--root", root, "--a", a, "--b", b) == 0
    (root / "SHA256SUMS").write_text("\n".join(lines[1:]) + "\n")
    assert run("sums-compare", "--root", root, "--a", a, "--b", b) == 1


# ---------------------------------------------------------------- the Zenodo plan
def sparse_root(tmp_path, sizes: dict[str, int]) -> Path:
    root = tmp_path / "Z"
    (root / "parquet").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "organizations").mkdir()
    (root / "tools").mkdir()
    small = {"README.md": 3000, "LICENSE.md": 2000, "MANIFEST.tsv": 2_000_000, "pseudonymization.json": 900,
             "links.json": 3000, "docs/SCHEMA.md": 6000, "organizations/dataset.duckdb": 3_000_000,
             "organizations/organizations.parquet": 170_000, "tools/fill_release.py": 17_000}
    lines = []
    for rel, size in list(small.items()) + [(f"parquet/{p}-dataset.parquet", s) for p, s in sizes.items()]:
        with open(root / rel, "wb") as fh:
            fh.truncate(size)                                   # sparse: no disk space
        lines.append(f"{'ab' * 32}  {rel}")
    (root / "SHA256SUMS").write_text("\n".join(sorted(lines, key=lambda l: l.split("  ")[1])) + "\n")
    return root


def plan(root: Path, out: Path, limit=50_000_000_000, max_files=100, archive=10_000_000_000) -> int:
    return run("split-plan", "--root", root, "--limit", limit, "--max-files", max_files, "--archive-max", archive,
               "--out-dir", out)


def read_tsv(path: Path) -> list[dict]:
    lines = path.read_text().splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, l.split("\t"))) for l in lines[1:]]


def test_split_plan_respects_50_gb(tmp_path):
    # 163 GB in 1,100 files: 3 files of about 2.9 GB, the rest 145 MB each (sizes like the release)
    sizes = {f"org{i:04d}__p": 145_000_000 + i * 1000 for i in range(1097)}
    sizes.update({"RMerl__asuswrt-merlin.ng": 2_910_000_000, "gnuton__asuswrt": 2_240_000_000, "torvalds__linux": 1_370_000_000})
    root = sparse_root(tmp_path, sizes)
    assert plan(root, tmp_path / "p1") == 0
    recs = read_tsv(tmp_path / "p1/zenodo-records.tsv")
    assert len(recs) == 4
    assert all(int(r["upload_bytes_max"]) <= 50_000_000_000 for r in recs)
    assert all(int(r["zenodo_files"]) <= 100 for r in recs)
    rows = read_tsv(tmp_path / "p1/zenodo-plan.tsv")
    paths = [r["path"] for r in rows]
    assert len(paths) == len(set(paths)) == len(sizes) + 10                     # each file once (and SHA256SUMS)
    rec1 = {r["path"]: r for r in rows if r["record"] == "01"}
    for rel in ("README.md", "MANIFEST.tsv", "SHA256SUMS", "pseudonymization.json", "links.json"):
        assert rec1[rel]["zenodo_file"] == rel                                  # top-level files: plain, record 1
    for rel in ("docs/SCHEMA.md", "organizations/dataset.duckdb", "tools/fill_release.py"):
        assert rec1[rel]["zenodo_file"] == "release-meta.tar"                   # docs and organizations: record 1
    by_arch: dict[str, int] = {}
    for r in rows:
        if r["zenodo_file"].startswith("parquet-"):
            by_arch[r["zenodo_file"]] = by_arch.get(r["zenodo_file"], 0) + int(r["bytes"])
    assert max(by_arch.values()) <= 10_000_000_000
    # contiguous name ranges: the records follow the name order
    order = [r["path"] for r in rows if r["path"].startswith("parquet/")]
    assert order == sorted(order)
    for k in range(1, 5):
        assert (tmp_path / f"p1/records/record-0{k}.tsv").is_file()
    # the same root gives the same plan
    assert plan(root, tmp_path / "p2") == 0
    for f in ("zenodo-plan.tsv", "zenodo-records.tsv", "records/record-01.tsv"):
        assert (tmp_path / "p1" / f).read_bytes() == (tmp_path / "p2" / f).read_bytes()


def test_split_plan_stops_on_a_file_over_the_limit(tmp_path):
    root = sparse_root(tmp_path, {"big__one": 50_000_000_001, "small__two": 1000})
    assert plan(root, tmp_path / "p") == 1


def test_split_plan_respects_the_file_limit(tmp_path):
    sizes = {f"org{i:03d}__p": 1_000_000 for i in range(300)}
    root = sparse_root(tmp_path, sizes)
    # record 1 holds 7 small files and its manifest: 4 archives of 20 MB fit; the other records 11
    assert plan(root, tmp_path / "p", limit=200_000_000, max_files=12, archive=20_000_000) == 0
    recs = read_tsv(tmp_path / "p/zenodo-records.tsv")
    assert all(int(r["zenodo_files"]) <= 12 for r in recs) and len(recs) >= 2
    assert all(int(r["upload_bytes_max"]) <= 200_000_000 for r in recs)
    assert sum(int(r["project_files"]) for r in recs) == 300


# ---------------------------------------------------------------- release 2: the input prefix and the spelling
def test_spell_gives_the_american_spelling():
    assert RT.spell("organisations_version") == "organizations_version"
    assert RT.spell("Organisation ORGANISATIONS reorganised") == "Organization ORGANIZATIONS reorganized"
    assert RT.spell("organizations") == "organizations"


def test_assemble_takes_the_project_files_of_the_input(tmp_path, sources, inputs, docs):
    root = assemble(tmp_path, sources, docs, inp=inputs)
    f = root / "parquet/alpha__one-dataset.parquet"
    assert os.stat(f).st_ino == os.stat(inputs / "parquet/alpha__one-dataset.parquet").st_ino
    (inputs / "parquet/delta__four-dataset.parquet").unlink()              # a name of A is not in the input
    a, b = sources
    assert run("assemble", "--a", a, "--b", b, "--input", inputs, "--docs", docs, "--root", tmp_path / "R2",
               "--expect", 5, "--names-out", tmp_path / "n2") == 1


def test_verify_input_ok_and_problems(tmp_path, sources, inputs, capsys):
    a, b = sources
    args = ["verify-input", "--dir", inputs, "--a", a, "--b", b, "--expect", 5, "--jobs", 2, "--out", tmp_path / "i.json"]
    assert run(*args) == 0
    rep = json.loads((tmp_path / "i.json").read_text())
    assert rep["files"] == 5 and rep["sha256_checked"] == 5 + 7 and len(rep["organizations"]) == 7
    assert run(*args[:-4], "--expect", 10754, "--out", tmp_path / "x.json") == 1          # not 10,754 files
    assert "5 project files in the input, not 10754" in capsys.readouterr().out
    with open(inputs / "parquet/alpha__one-dataset.parquet", "ab") as fh:           # another sha256
        fh.write(b"\0")
    assert run(*args) == 1
    assert "1 files with another sha256 than in SHA256SUMS of the input" in capsys.readouterr().out
    (inputs / "SHA256SUMS").unlink()                                              # SHA256SUMS is optional
    assert run(*args) == 0
    (inputs / "organizations/organizations.parquet").rename(inputs / "organizations/organisations.parquet")
    assert run(*args) == 1                                                        # the old spelling
    out = capsys.readouterr().out
    assert "organizations/organizations.parquet is missing" in out and "the old spelling organis" in out


def test_verify_input_sums_with_the_organization_files(tmp_path, sources, inputs, capsys):
    import hashlib
    a, b = sources
    args = ["verify-input", "--dir", inputs, "--a", a, "--b", b, "--expect", 5, "--jobs", 2, "--out", tmp_path / "i.json"]
    lines = (inputs / "SHA256SUMS").read_text().splitlines()                    # the U2 form: with organizations/
    assert run(*args) == 0 and json.loads((tmp_path / "i.json").read_text())["sha256_checked"] == 12
    (inputs / "SHA256SUMS").write_text("\n".join(l for l in lines if "  parquet/" in l) + "\n")   # project rows only
    assert run(*args) == 0 and json.loads((tmp_path / "i.json").read_text())["sha256_checked"] == 5
    with open(inputs / "SHA256SUMS", "a") as fh:                                  # a row of no input file
        fh.write(f"{'0' * 64}  links.json\n")
    assert run(*args) == 1
    assert "names are not the project files and the files of organizations/" in capsys.readouterr().out


def test_s3_list_check_of_the_input(tmp_path):
    base = "dataset-release/dataset-release-2/input"
    ok = [f"2026-10-29 06:30:06 10 {base}/parquet/a__b-dataset.parquet",
          f"2026-10-29 06:30:06 10 {base}/organizations/organizations.parquet",
          f"2026-10-29 06:30:06 10 {base}/organizations/dataset.duckdb", f"2026-10-29 06:30:06 10 {base}/SHA256SUMS"]
    (tmp_path / "ls.txt").write_text("\n".join(ok) + "\n")
    assert run("s3-list-check", "--listing", tmp_path / "ls.txt", "--prefix", base, "--expect", 1, "--input") == 0
    assert run("s3-list-check", "--listing", tmp_path / "ls.txt", "--prefix", base, "--expect", 1) == 1
    (tmp_path / "ls2.txt").write_text("\n".join(ok + [f"2026-10-29 06:30:06 10 {base}/links.json"]) + "\n")
    assert run("s3-list-check", "--listing", tmp_path / "ls2.txt", "--prefix", base, "--expect", 1, "--input") == 1


def test_verify_source_without_the_project_files(tmp_path, sources, capsys):
    a, b = sources
    for f in (a / "parquet").iterdir():
        f.unlink()
    assert run("verify-source", "--dir", a, "--label", "A", "--expect", 4, "--expect-rows", 19,
               "--no-project-files", "--out", tmp_path / "a.json") == 0
    rep = json.loads((tmp_path / "a.json").read_text())
    assert rep["project_files"] == "input" and rep["organizations_version"] == "v4.9"     # the old key of links.json
    assert run("verify-source", "--dir", a, "--label", "A", "--expect", 4, "--out", tmp_path / "x.json") == 1


def test_links_check_reads_the_old_and_the_new_key(tmp_path, sources, capsys):
    a, b = sources
    mapping = json.loads((b / "links.json").read_text())["mapping_sha256"]
    assert run("links-check", "--a", a, "--b", b, "--mapping", mapping[:12], "--ov", "v4.9") == 0
    lj = json.loads((b / "links.json").read_text())
    lj["organizations_version"] = lj.pop("organisations_version")
    (b / "links.json").write_text(json.dumps(lj))
    assert run("links-check", "--a", a, "--b", b, "--mapping", mapping[:12], "--ov", "v4.9") == 0
    assert run("links-check", "--a", a, "--b", b, "--mapping", mapping[:12], "--ov", "v5") == 1
    assert "B: organizations version v4.9, not v5" in capsys.readouterr().out


def test_sums_compare_with_the_input(tmp_path, sources, inputs, docs):
    a, b = sources
    root = assemble(tmp_path, sources, docs, inp=inputs)
    lines = (inputs / "SHA256SUMS").read_text().splitlines()
    (root / "SHA256SUMS").write_text("\n".join(lines + ["00  README.md"]) + "\n")
    assert run("sums-compare", "--root", root, "--a", a, "--b", b, "--input", inputs) == 0
    assert run("sums-compare", "--root", root, "--a", a, "--b", b) == 1          # not the sha256 of the final writes
    (inputs / "SHA256SUMS").unlink()
    assert run("sums-compare", "--root", root, "--a", a, "--b", b, "--input", inputs) == 0   # the names only


def test_sums_compare_with_organization_rows_in_the_input(tmp_path, sources, inputs, docs, capsys):
    a, b = sources
    root = assemble(tmp_path, sources, docs, inp=inputs)
    lines = (inputs / "SHA256SUMS").read_text().splitlines()                    # the U2 form: with organizations/
    (root / "SHA256SUMS").write_text("\n".join(lines + ["00  README.md"]) + "\n")
    assert run("sums-compare", "--root", root, "--a", a, "--b", b, "--input", inputs) == 0
    one = ["2" * 64 + "  organizations/organizations.parquet" if l.endswith("  organizations/organizations.parquet") else l
           for l in lines]                                                      # one file of organizations/ differs
    (root / "SHA256SUMS").write_text("\n".join(one) + "\n")
    assert run("sums-compare", "--root", root, "--a", a, "--b", b, "--input", inputs) == 1
    assert "1 files of organizations/ in R are not the files of the input" in capsys.readouterr().out


def test_links_rewrite_gives_nested_keys_the_new_spelling(tmp_path, sources):
    a, b = sources
    lj = json.loads((b / "links.json").read_text())
    lj["token_share_by_value_class"] = {"organisation": 0.5, "person": 0.5}     # a key of the real links.json
    (tmp_path / "src.json").write_text(json.dumps(lj))
    out, rep = tmp_path / "links.json", tmp_path / "rw.tsv"
    assert run("links-rewrite", "--src", tmp_path / "src.json", "--out", out, "--report", rep) == 0
    got = json.loads(out.read_text())
    assert got["token_share_by_value_class"] == {"organization": 0.5, "person": 0.5}
    assert not [k for k in RT.key_names(got) if "organis" in k]
    lj["organizations_version"] = "v4.9"                       # both spellings: the new name would be there twice
    (tmp_path / "both.json").write_text(json.dumps(lj))
    assert run("links-rewrite", "--src", tmp_path / "both.json", "--out", tmp_path / "x.json", "--report", rep) == 1


# ---------------------------------------------------------------- the re-encode chain (kit dataset-reencode)
SETTINGS_FAKE = "e9" * 32


def _reencode_scene(tmp_path):
    """A published input (pub/), its re-encode (inp/: the same rows written again by DuckDB with other settings,
    the same organizations/ files) and the re-encode log of reencode.py (one OK line per file)."""
    pub, inp = tmp_path / "pub", tmp_path / "inp"
    projects = [("alpha__one", 7, fake.REG_A), ("BRL-CAD__brlcad", 6, fake.REG_B)]
    fake.make_input(pub, projects, fake.MAPPING_FAKE)
    (inp / "parquet").mkdir(parents=True)
    shutil.copytree(pub / "organizations", inp / "organizations")
    con = duckdb.connect()
    pub_sums = dict((r, h) for h, r in RT.read_sums(pub / "SHA256SUMS"))
    lines, rows = [], []
    for name, n, _ in projects:
        src, dst = pub / "parquet" / f"{name}-dataset.parquet", inp / "parquet" / f"{name}-dataset.parquet"
        kv = ", ".join(f"{k.decode()}: '{v.decode()}'" for k, v in
                       con.execute("SELECT key, value FROM parquet_kv_metadata(?)", [str(src)]).fetchall())
        con.execute(f"COPY (SELECT * FROM read_parquet('{src}')) TO '{dst}' (FORMAT parquet, COMPRESSION snappy, "
                    f"KV_METADATA {{{kv}}})")
        fp = RT.reencode_fingerprint(con, src)
        assert RT.reencode_fingerprint(con, dst) == fp
        lines.append({"file": dst.name, "status": "OK", "checks": {"rows": True, "rowhash": True, "kv": True},
                      "versions": {"pyarrow": "26.0.1", "duckdb": "1.5.5", "reencode_sha256": "ab" * 32},
                      "settings_sha256": SETTINGS_FAKE, "in_sha256": pub_sums[f"parquet/{dst.name}"],
                      "want_sha256": pub_sums[f"parquet/{dst.name}"], "out_sha256": fake.sha(dst),
                      "in_bytes": src.stat().st_size, "out_bytes": dst.stat().st_size, "rows": n,
                      "fingerprint": {k: fp[k] for k in ("rowhash", "orderhash", "colhash")}})
        rows.append((fake.sha(dst), f"parquet/{dst.name}"))
    rows += [(h, r) for r, h in pub_sums.items() if r.startswith("organizations/")]
    (inp / "SHA256SUMS").write_text("".join(f"{h}  {r}\n" for h, r in sorted(rows, key=lambda x: x[1])))
    log = tmp_path / "reencode-log.jsonl"
    log.write_text("".join(json.dumps(x) + "\n" for x in lines))
    return pub, inp, log, lines


def _chain(pub, inp, log, tmp_path, *extra, published_sha=None):
    return run("reencode-chain", "--log", log, "--published", pub / "SHA256SUMS", "--published-sha",
               published_sha or fake.sha(pub / "SHA256SUMS"), "--input", inp, "--settings-sha", SETTINGS_FAKE,
               "--recheck", 5, "--jobs", 2, "--out", tmp_path / "chain.json", *extra)


def test_reencode_chain_ok(tmp_path, capsys):
    pub, inp, log, _ = _reencode_scene(tmp_path)
    assert _chain(pub, inp, log, tmp_path) == 0
    out = capsys.readouterr().out
    assert "reencode-chain: 2 project files" in out and "content hash again for 2 files" in out
    rep = json.loads((tmp_path / "chain.json").read_text())
    assert rep["chain_ok"] == 2 and rep["rows"] == 13 and rep["organizations_rows"] == 7


@pytest.mark.parametrize("change", ["in_sha", "out_sha", "settings", "pyarrow", "check", "status", "missing",
                                    "fingerprint", "rows"])
def test_reencode_chain_breaks(tmp_path, change):
    pub, inp, log, lines = _reencode_scene(tmp_path)
    x = lines[0]
    if change == "in_sha":
        x["in_sha256"] = "0" * 64
    elif change == "out_sha":
        x["out_sha256"] = "0" * 64
    elif change == "settings":
        x["settings_sha256"] = "1" * 64
    elif change == "pyarrow":
        x["versions"]["pyarrow"] = "25.0.0"
    elif change == "check":
        x["checks"]["rowhash"] = False
    elif change == "status":
        x["status"] = "FAIL"
    elif change == "fingerprint":
        x["fingerprint"]["colhash"][3] = "1"
    elif change == "rows":
        x["rows"] += 1
    keep = lines[1:] if change == "missing" else lines
    log.write_text("".join(json.dumps(y) + "\n" for y in keep))
    assert _chain(pub, inp, log, tmp_path) == 1


def test_reencode_chain_breaks_on_organizations_and_pin(tmp_path):
    pub, inp, log, _ = _reencode_scene(tmp_path)
    assert _chain(pub, inp, log, tmp_path, published_sha="0" * 64) == 1
    sums = (inp / "SHA256SUMS").read_text().splitlines()
    sums = [("0" * 64 + l[64:]) if "organizations/release_info" in l else l for l in sums]
    (inp / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    assert _chain(pub, inp, log, tmp_path) == 1


def _root_scene(tmp_path):
    pub, inp, log, lines = _reencode_scene(tmp_path)
    hdr = ["project", "clone_url", "layer", "rows", "bytes", "sha256", "path"]
    def man(which):
        out = ["\t".join(hdr)]
        for x in lines:
            p = x["file"][: -len("-dataset.parquet")]
            b, h = (x["in_bytes"], x["in_sha256"]) if which == "old" else (x["out_bytes"], x["out_sha256"])
            out.append("\t".join([p, f"https://example.org/{p}.git", "v1", str(x["rows"]), str(b), h, f"parquet/{x['file']}"]))
        return "\n".join(out) + "\n"
    pm = tmp_path / "published.MANIFEST.tsv"
    pm.write_text(man("old"))
    root = tmp_path / "R"
    root.mkdir()
    (root / "MANIFEST.tsv").write_text(man("new"))
    other = {"README.md": ("aa" * 32, "bb" * 32), "ledgers.parquet": ("cc" * 32, "cc" * 32),
             "links.json": ("dd" * 32, "dd" * 32)}
    old_rows = [(x["in_sha256"], f"parquet/{x['file']}") for x in lines]
    new_rows = [(x["out_sha256"], f"parquet/{x['file']}") for x in lines]
    for r, (o, n) in other.items():
        old_rows.append((o, r))
        new_rows.append((n, r))
    org = [(h, r) for h, r in RT.read_sums(pub / "SHA256SUMS") if r.startswith("organizations/")]
    old_rows += org + [(fake.sha(pm), "MANIFEST.tsv")]
    new_rows += org + [(fake.sha(root / "MANIFEST.tsv"), "MANIFEST.tsv")]
    ps = tmp_path / "published.SHA256SUMS"
    ps.write_text("".join(f"{h}  {r}\n" for h, r in sorted(old_rows, key=lambda x: x[1])))
    (root / "SHA256SUMS").write_text("".join(f"{h}  {r}\n" for h, r in sorted(new_rows, key=lambda x: x[1])))
    return root, ps, pm, log


def _root(root, ps, pm, log, tmp_path):
    return run("reencode-root", "--root", root, "--published", ps, "--published-sha", fake.sha(ps),
               "--published-manifest", pm, "--log", log, "--out", tmp_path / "root.tsv")


def test_reencode_root_ok(tmp_path, capsys):
    root, ps, pm, log = _root_scene(tmp_path)
    assert _root(root, ps, pm, log, tmp_path) == 0
    out = capsys.readouterr().out
    assert "1 changed (README.md)" in out and "MANIFEST.tsv: only bytes and sha256 changed" in out
    tsv = (tmp_path / "root.tsv").read_text()
    assert "organizations/release_info.parquet\tsame" in tsv and "README.md\tchanged" in tsv


@pytest.mark.parametrize("change", ["organizations", "ledgers", "manifest-column", "manifest-sha", "added",
                                    "project-sha"])
def test_reencode_root_breaks(tmp_path, change):
    root, ps, pm, log = _root_scene(tmp_path)
    sums = root / "SHA256SUMS"
    rows = RT.read_sums(sums)
    if change == "organizations":
        rows = [("0" * 64 if r.startswith("organizations/link_error") else h, r) for h, r in rows]
    elif change == "ledgers":
        rows = [("0" * 64 if r == "ledgers.parquet" else h, r) for h, r in rows]
    elif change == "added":
        rows.append(("e" * 64, "docs/NEW.md"))
    elif change == "project-sha":
        rows = [("0" * 64 if r.startswith("parquet/alpha") else h, r) for h, r in rows]
    elif change in ("manifest-column", "manifest-sha"):
        m = (root / "MANIFEST.tsv").read_text().splitlines()
        f = m[1].split("\t")
        if change == "manifest-column":
            f[2] = "x1k"
        else:
            f[5] = "0" * 64
        m[1] = "\t".join(f)
        (root / "MANIFEST.tsv").write_text("\n".join(m) + "\n")
    sums.write_text("".join(f"{h}  {r}\n" for h, r in sorted(rows, key=lambda x: x[1])))
    assert _root(root, ps, pm, log, tmp_path) == 1


def test_reencode_chain_two_kit_versions(tmp_path, capsys):
    """The retry of one file with a new reencode.py: two reencode_sha256 values, each a kit version of the stage
    (--kit-sha), with one set of pyarrow, duckdb and settings; a read_batch on the retried line."""
    pub, inp, log, lines = _reencode_scene(tmp_path)
    lines[0]["versions"]["reencode_sha256"] = "cd" * 32
    lines[0]["read_batch"] = 32768
    log.write_text("".join(json.dumps(y) + "\n" for y in lines))
    kit = ["--kit-sha", "ab" * 32, "--kit-sha", "cd" * 32]
    assert _chain(pub, inp, log, tmp_path, *kit) == 0
    out = capsys.readouterr().out
    assert "reencode-chain: 2 project files" in out and "read batch 262144 1 files, 32768 1 files" in out
    rep = json.loads((tmp_path / "chain.json").read_text())
    assert rep["reencode_sha256"] == {"ab" * 32: 1, "cd" * 32: 1} and rep["kit_sha256"] == ["ab" * 32, "cd" * 32]
    assert rep["read_batch"] == {"262144": 1, "32768": 1} and rep["versions"] == [["26.0.1", "1.5.5"]]
    assert rep["read_batch_not_default"] == [f"{lines[0]['file'][: -len('-dataset.parquet')]}=32768"]
    # no --kit-sha: one version only (the rule before the retry)
    assert _chain(pub, inp, log, tmp_path) == 1
    # a version that is not in the kit list
    assert _chain(pub, inp, log, tmp_path, "--kit-sha", "ab" * 32) == 1


@pytest.mark.parametrize("change", ["settings", "pyarrow", "duckdb"])
def test_reencode_chain_two_kit_versions_keeps_settings_and_versions_strict(tmp_path, change):
    pub, inp, log, lines = _reencode_scene(tmp_path)
    lines[0]["versions"]["reencode_sha256"] = "cd" * 32
    if change == "settings":
        lines[0]["settings_sha256"] = "1" * 64
    else:
        lines[0]["versions"][change] = "9.9.9"
    log.write_text("".join(json.dumps(y) + "\n" for y in lines))
    assert _chain(pub, inp, log, tmp_path, "--kit-sha", "ab" * 32, "--kit-sha", "cd" * 32) == 1
