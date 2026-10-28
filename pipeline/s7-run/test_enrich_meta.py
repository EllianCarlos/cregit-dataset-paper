"""Tests for enrich_meta.py and rewrite_meta_columns.py (2026-10-09).
Run: python3 -m pytest -q test_enrich_meta.py   (an interpreter with duckdb and pytest)
     CREGIT=<cregit checkout>  CTP=<cregit-token-pipeline checkout>  override the defaults.

The end-to-end tests run cregit's own generate_dataset.main() (the step that writes the 29
provenance columns into the Parquet) on cregit's one-token test project, keyed by real batch 1
names with the real sidecars, then ctp's firm step and schema gate. Nothing here reads or
writes a census output; every file is in pytest's tmp_path."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import enrich_meta  # noqa: E402
import rewrite_meta_columns  # noqa: E402

CREGIT = Path(os.environ.get("CREGIT", Path.home() / "Projects/cregit-workspace/scratch/"
                             "e2e-runner/cregit-157cf8b"))
CTP = Path(os.environ.get("CTP", Path.home() / "Projects/cregit-token-pipeline/.claude/"
                          "worktrees/agent-a0a3254f563a6a4b5"))
FIELDS = enrich_meta.FIELDS
GH = "horsicq__x64dbg-Plugin-Manager"       # MIT, User
NOASSERT = "bitwarden__clients"             # NOASSERTION, Organization
NON_GH = "gitlab.winehq.org__wine__wine"    # not on GitHub: pool.csv leaves the 4 blank


# --------------------------------------------------------------------------- enrich_meta

def rec(clone_url, **kw):
    r = {f: "" for f in ("clone_url", "provenance_status", "source", "owner", "repo") + FIELDS}
    r.update(clone_url=clone_url, **kw)
    return r


FRAME = {
    "o__r": {"host": "github.com", "slug": "o/r", "repo_url": "https://github.com/o/r.git",
             "pool_key": "gh:1"},
    "gitlab.com__g__p": {"host": "gitlab.com", "slug": "g/p", "repo_url": "https://gitlab.com/g/p",
                         "pool_key": "url:https://gitlab.com/g/p"},
}
POOL = {"gh:1": {"license": "NOASSERTION", "owner_type": "User", "archived": "False", "fork": "False",
                 "source": "search;spinellis-2020:enterprise"},
        "url:https://gitlab.com/g/p": {**{f: "" for f in FIELDS}, "source": "rosters/x.csv:x"}}


def test_project_name_matches_build_manifest():
    sys.path.insert(0, str(CTP))
    bm = pytest.importorskip("build_manifest")
    for host, slug in (("github.com", "jqlang/jq"), ("gitlab.eclipse.org", "eclipse/escet/escet"),
                       ("git.libreoffice.org", "core")):
        assert enrich_meta.project_name(host, slug) == bm.project_name(host, slug)


def test_values_are_copied_as_they_are_and_only_the_four_change():
    meta = {"o__r": rec("https://github.com/o/r.git", provenance_status="frame:x", owner="o"),
            "gitlab.com__g__p": rec("https://gitlab.com/g/p")}
    out, problems = enrich_meta.enrich(meta, FRAME, POOL)
    assert problems == []
    assert out["o__r"] == {**meta["o__r"], "license": "NOASSERTION", "owner_type": "User",
                           "archived": "False", "fork": "False",
                           "source": "search;spinellis-2020:enterprise"}
    assert out["gitlab.com__g__p"] == {**meta["gitlab.com__g__p"], "source": "rosters/x.csv:x"}
    assert list(out) == list(meta) and list(out["o__r"]) == list(meta["o__r"])


@pytest.mark.parametrize("meta, needle", [
    ({"x__y": rec("https://github.com/x/y.git")}, "not in the frame"),
    ({"o__r": rec("https://github.com/o/other.git")}, "is not the frame's repo_url"),
    ({"o__r": rec("https://github.com/o/r.git", license="MIT")}, "already 'MIT'"),
    ({"o__r": rec("https://github.com/o/r.git", source="search")}, "source is already 'search'"),
])
def test_a_key_that_does_not_join_or_disagrees_is_a_problem(meta, needle):
    _, problems = enrich_meta.enrich(meta, FRAME, POOL)
    assert len(problems) == 1 and needle in problems[0]


@pytest.mark.parametrize("origins", ["spinellis-2020:enterprise;search", "search;search", "",
                                     "search;;x"])
def test_a_source_that_is_not_a_sorted_unique_list_is_a_problem(origins):
    pool = {**POOL, "gh:1": {**POOL["gh:1"], "source": origins}}
    out, problems = enrich_meta.enrich({"o__r": rec("https://github.com/o/r.git")}, FRAME, pool)
    assert out == {} and len(problems) == 1 and "sorted list of unique tokens" in problems[0]


def test_a_sidecar_with_no_source_field_is_a_problem():
    r = rec("https://github.com/o/r.git")
    del r["source"]
    _, problems = enrich_meta.enrich({"o__r": r}, FRAME, POOL)
    assert len(problems) == 1 and "no source field" in problems[0]


def write_license_values(tmp_path, rows):
    path = tmp_path / "licenses.csv"
    path.write_text("pool_key,license,license_evidence\n" + "".join(f"{k},{v},{e}\n" for k, v, e in rows),
                    encoding="utf-8")
    return path


def test_license_values_fill_only_a_blank_pool_license(tmp_path):
    pool = {k: dict(v) for k, v in POOL.items()}
    path = write_license_values(tmp_path, [("url:https://gitlab.com/g/p", "BSD-2-Clause;CC0-1.0", "LICENSES/"),
                                           ("gh:1", "NOASSERTION", "LICENSE"), ("gh:9", "MIT", "LICENSE")])
    assert enrich_meta.apply_license_values(pool, path) == []
    assert pool["url:https://gitlab.com/g/p"]["license"] == "BSD-2-Clause;CC0-1.0"
    assert pool["gh:1"]["license"] == "NOASSERTION" and "gh:9" not in pool
    out, problems = enrich_meta.enrich({"gitlab.com__g__p": rec("https://gitlab.com/g/p")}, FRAME, pool)
    assert problems == [] and out["gitlab.com__g__p"]["license"] == "BSD-2-Clause;CC0-1.0"
    assert "license_evidence" not in out["gitlab.com__g__p"]


@pytest.mark.parametrize("rows, needle", [
    ([("gh:1", "MIT", "LICENSE")], "pool license 'NOASSERTION', the CSV says 'MIT'"),
    ([("gh:1", "", "LICENSE")], "blank license value"),
    ([("gh:1", "NOASSERTION", "x"), ("gh:1", "NOASSERTION", "y")], "repeats"),
])
def test_license_values_that_conflict_or_are_bad_are_problems(tmp_path, rows, needle):
    pool = {k: dict(v) for k, v in POOL.items()}
    problems = enrich_meta.apply_license_values(pool, write_license_values(tmp_path, rows))
    assert len(problems) == 1 and needle in problems[0]


def test_pool_values_read_source_from_origins(tmp_path):
    pool = tmp_path / "pool.csv"
    pool.write_text("pool_key,origins,license,owner_type,archived,fork,stars\n"
                    "gh:1,search;spinellis-2020:enterprise,MIT,User,False,False,9\n"
                    "gh:2,search,,,,,1\n")
    assert enrich_meta.pool_values(pool, {"gh:1"}) == {"gh:1": {
        "license": "MIT", "owner_type": "User", "archived": "False", "fork": "False",
        "source": "search;spinellis-2020:enterprise"}}


def test_the_real_layer1_sidecar_gets_a_source_for_every_key_and_nothing_else_changes(tmp_path):
    pool = HERE.parent / "s2-pool" / "pool.csv"
    if not pool.exists():
        pytest.skip("no s2-pool/pool.csv (restore it with xz -d -k pool.csv.xz)")
    src = HERE / "project_meta.layer1.enriched.json"
    out = tmp_path / "layer1.json"
    assert enrich_meta.main([str(src), "--out", str(out)]) == 0
    a, b = json.loads(src.read_text()), json.loads(out.read_text())
    assert list(a) == list(b) and len(b) == 3265
    for k in a:
        assert list(a[k]) == list(b[k])
        assert {f for f in a[k] if a[k][f] != b[k][f]} == {"source"}
    assert b["reyamira__models"]["source"] == "search"
    assert b["microsoft__terminal"]["source"] == "company-org:Microsoft;search;spinellis-2020:enterprise"


def test_in_place_refuses_a_sidecar_listed_in_sha256sums(tmp_path, capsys):
    side = tmp_path / "project_meta.batch2.json"
    side.write_text("{}\n")
    (tmp_path / "SHA256SUMS").write_text("0" * 64 + "  project_meta.batch2.json\n")
    assert enrich_meta.main([str(side), "--in-place"]) == 1
    assert "SHA256SUMS" in capsys.readouterr().err
    assert side.read_text() == "{}\n"


def test_out_refuses_an_existing_file(tmp_path):
    side, out = tmp_path / "a.json", tmp_path / "b.json"
    side.write_text("{}\n")
    out.write_text("keep\n")
    assert enrich_meta.main([str(side), "--out", str(out)]) == 1
    assert out.read_text() == "keep\n"


def test_the_real_batch1_sidecar_joins_fully_and_differs_in_the_four_fields_only():
    if not (HERE / "project_meta.batch1.json").exists():
        pytest.skip("no project_meta.batch1.json (git-ignored run output)")
    a = json.loads((HERE / "project_meta.batch1.json").read_text())
    b = json.loads((HERE / "project_meta.batch1.enriched.json").read_text())
    assert list(a) == list(b)
    for k in a:
        assert {f for f in a[k] if a[k][f] != b[k][f]} <= set(FIELDS)
    assert {f: b[GH][f] for f in FIELDS} == {"license": "MIT", "owner_type": "User",
                                             "archived": "False", "fork": "False"}
    assert b[NOASSERT]["license"] == "NOASSERTION"
    assert {f: b[NON_GH][f] for f in FIELDS} == {f: "" for f in FIELDS}


# --------------------------------------------------------------------------- end to end

@pytest.fixture
def gd():
    if not (CREGIT / "generate_dataset" / "generate_dataset.py").exists():
        pytest.skip(f"no cregit checkout at {CREGIT}")
    pytest.importorskip("duckdb")
    sys.path.insert(0, str(CREGIT / "generate_dataset"))
    sys.path.insert(0, str(CREGIT / "tests"))
    import generate_dataset
    return generate_dataset


def generate(gd, monkeypatch, workdir: Path, sidecar: Path, key: str) -> Path:
    """cregit's generate_dataset.main() on its one-token test project, as ctp calls it:
    --repo-name and --project-key are the manifest name, --project-meta the sidecar."""
    from test_generate_dataset import build_tiny_project

    workdir.mkdir()
    blame, src, cregit_db, persons_db = build_tiny_project(workdir)
    out = workdir / "out" / f"{key}-dataset.parquet"
    monkeypatch.setattr(gd.sys, "argv", [
        "generate_dataset.py", "--blame-dir", str(blame), "--source-dir", str(src),
        "--cregit-db", str(cregit_db), "--persons-db", str(persons_db), "--output", str(out),
        "--repo-name", key, "--project-meta", str(sidecar), "--project-key", key,
        "--memory-limit", "512MB", "--duckdb-threads", "1"])
    gd.main()
    return out


def rows(path: Path) -> tuple[list[str], list[tuple]]:
    import duckdb
    rel = duckdb.sql(f"SELECT * FROM read_parquet('{path}')")
    return rel.columns, rel.fetchall()


@pytest.mark.parametrize("key, expected", [
    (GH, ("MIT", "User", "False", "False")),
    (NOASSERT, ("NOASSERTION", "Organization", "False", "False")),
    (NON_GH, ("", "", "", "")),
])
def test_the_enriched_sidecar_fills_the_four_parquet_columns(gd, monkeypatch, tmp_path, key, expected):
    old = generate(gd, monkeypatch, tmp_path / "old", HERE / "project_meta.batch1.json", key)
    new = generate(gd, monkeypatch, tmp_path / "new", HERE / "project_meta.batch1.enriched.json", key)
    cols, a = rows(old)
    cols_b, b = rows(new)
    assert cols == cols_b and len(cols) == 67 and len(a) == len(b) == 1
    idx = [cols.index(f) for f in FIELDS]
    assert tuple(a[0][i] for i in idx) == ("", "", "", "")
    assert tuple(b[0][i] for i in idx) == expected
    other = [i for i in range(len(cols)) if i not in idx]
    assert [a[0][i] for i in other] == [b[0][i] for i in other]


def test_firm_step_and_schema_gate_keep_the_four_values(gd, monkeypatch, tmp_path):
    if not (CTP / "firm_attribution.py").exists():
        pytest.skip(f"no ctp checkout at {CTP}")
    sys.path.insert(0, str(CTP))
    import firm_attribution
    import validate_schema

    out = generate(gd, monkeypatch, tmp_path / "new", HERE / "project_meta.batch1.enriched.json", GH)
    firm_attribution.add_firm_columns(out, firm_attribution.FIRM_MAP,
                                      firm_attribution.FIRM_CANONICAL, "512MB", 1)
    assert validate_schema.compare_schema(validate_schema.read_schema(str(out)),
                                          validate_schema.EXPECTED_COLUMNS) == []
    cols, r = rows(out)
    assert len(cols) == 70
    assert tuple(r[0][cols.index(f)] for f in FIELDS) == ("MIT", "User", "False", "False")


@pytest.mark.parametrize("key", [GH, NOASSERT, NON_GH])
def test_rewriting_an_old_parquet_equals_generating_with_the_enriched_sidecar(
        gd, monkeypatch, tmp_path, key):
    old = generate(gd, monkeypatch, tmp_path / "old", HERE / "project_meta.batch1.json", key)
    new = generate(gd, monkeypatch, tmp_path / "new", HERE / "project_meta.batch1.enriched.json", key)
    fixed = tmp_path / "fixed.parquet"
    assert rewrite_meta_columns.main([str(old), "--sidecar",
                                      str(HERE / "project_meta.batch1.enriched.json"),
                                      "--out", str(fixed), "--memory-limit", "512MB",
                                      "--threads", "1"]) == 0
    assert rows(fixed) == rows(new)


def test_rewrite_in_place_replaces_the_file_and_leaves_no_temp(gd, monkeypatch, tmp_path):
    old = generate(gd, monkeypatch, tmp_path / "old", HERE / "project_meta.batch1.json", GH)
    assert rewrite_meta_columns.main([str(old), "--sidecar",
                                      str(HERE / "project_meta.batch1.enriched.json"),
                                      "--in-place", "--threads", "1"]) == 0
    cols, r = rows(old)
    assert r[0][cols.index("license")] == "MIT"
    assert sorted(p.name for p in old.parent.iterdir()) == [old.name]


def test_rewrite_refuses_a_conflicting_value(gd, monkeypatch, tmp_path):
    new = generate(gd, monkeypatch, tmp_path / "new", HERE / "project_meta.batch1.enriched.json", GH)
    meta = json.loads((HERE / "project_meta.batch1.enriched.json").read_text())
    meta[GH]["license"] = "GPL-3.0"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(meta))
    before = new.read_bytes()
    assert rewrite_meta_columns.main([str(new), "--sidecar", str(bad), "--in-place"]) == 1
    assert new.read_bytes() == before


# --------------------------------------------------------------------------- all 11 columns

FINAL = HERE / "project_meta.layer1.final.json"
ALL = rewrite_meta_columns.ALL_FIELDS


@pytest.fixture
def final_sidecar():
    if not FINAL.exists():
        pytest.skip(f"no {FINAL.name} (final_meta.py writes it)")
    return FINAL


@pytest.mark.parametrize("key", [GH, NON_GH])
def test_rewrite_fills_all_eleven_columns_from_the_final_sidecar(gd, monkeypatch, tmp_path, key,
                                                                   final_sidecar):
    old = generate(gd, monkeypatch, tmp_path / "old", HERE / "project_meta.batch1.json", key)
    new = generate(gd, monkeypatch, tmp_path / "new", final_sidecar, key)
    fixed, rep = tmp_path / "fixed.parquet", tmp_path / "report.tsv"
    assert rewrite_meta_columns.main([str(old), "--sidecar", str(final_sidecar), "--out", str(fixed),
                                      "--report", str(rep), "--memory-limit", "512MB",
                                      "--threads", "1"]) == 0
    assert rows(fixed) == rows(new)
    cols, r = rows(fixed)
    meta = json.loads(final_sidecar.read_text())[key]
    assert {f: r[0][cols.index(f)] for f in ALL} == {f: meta[f] for f in ALL}
    assert meta["stratum"] and meta["source"] and meta["label_date"]
    line = rep.read_text().splitlines()
    assert len(line) == 1 and line[0].split("\t")[3] == "OK" and line[0].split("\t")[2] == key


def test_rewrite_fields_fills_only_the_named_columns(gd, monkeypatch, tmp_path, final_sidecar):
    old = generate(gd, monkeypatch, tmp_path / "old", HERE / "project_meta.batch1.json", GH)
    fixed = tmp_path / "fixed.parquet"
    assert rewrite_meta_columns.main([str(old), "--sidecar", str(final_sidecar), "--out", str(fixed),
                                      "--fields", "stratum,fact", "--threads", "1"]) == 0
    cols, r = rows(fixed)
    meta = json.loads(final_sidecar.read_text())[GH]
    assert r[0][cols.index("stratum")] == meta["stratum"] == "personal"
    assert r[0][cols.index("fact")] == "owner_kind:user"
    assert r[0][cols.index("source")] == "" and r[0][cols.index("license")] == ""


@pytest.mark.parametrize("fields", ["stratum,stratum", "nope", ""])
def test_rewrite_rejects_bad_fields(fields):
    with pytest.raises(SystemExit) as e:
        rewrite_meta_columns.main(["x.parquet", "--sidecar", "s.json", "--out", "y.parquet",
                                   "--fields", fields])
    assert e.value.code == 2


def test_rewrite_refuses_a_sidecar_record_with_no_such_field(gd, monkeypatch, tmp_path):
    old = generate(gd, monkeypatch, tmp_path / "old", HERE / "project_meta.batch1.json", GH)
    meta = json.loads((HERE / "project_meta.batch1.json").read_text())
    del meta[GH]["stratum"]
    bad, rep = tmp_path / "bad.json", tmp_path / "r.tsv"
    bad.write_text(json.dumps(meta))
    before = old.read_bytes()
    assert rewrite_meta_columns.main([str(old), "--sidecar", str(bad), "--in-place",
                                      "--report", str(rep)]) == 1
    assert old.read_bytes() == before
    assert "no field stratum" in rep.read_text() and "\tFAIL\t" in rep.read_text()


def test_rewrite_refuses_a_label_that_differs_from_the_parquet(gd, monkeypatch, tmp_path,
                                                              final_sidecar):
    new = generate(gd, monkeypatch, tmp_path / "new", final_sidecar, GH)
    meta = json.loads(final_sidecar.read_text())
    meta[GH]["stratum"] = "company"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(meta))
    before = new.read_bytes()
    assert rewrite_meta_columns.main([str(new), "--sidecar", str(bad), "--in-place"]) == 1
    assert new.read_bytes() == before


def test_rewrite_on_a_parquet_that_already_holds_the_values_is_a_no_op(gd, monkeypatch, tmp_path,
                                                                      final_sidecar):
    new = generate(gd, monkeypatch, tmp_path / "new", final_sidecar, GH)
    again = tmp_path / "again.parquet"
    assert rewrite_meta_columns.main([str(new), "--sidecar", str(final_sidecar), "--out", str(again),
                                      "--threads", "1"]) == 0
    assert rows(again) == rows(new)
