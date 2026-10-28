"""Tests of validate_schema2.py and compare_published.py on small Parquet files (made here).

They need duckdb (the dev shell: make test).
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


vs2 = load("validate_schema2")
cp = load("compare_published")


def lit(text):
    return "'" + str(text).replace("'", "''") + "'"


# validate_schema2.py

REG_A = "a" * 64
REG_B = "b" * 64


def write_release_file(path, rows=3, footer=None, columns=None, old_keys=False):
    vs = vs2.load_ca113e3()
    cols = columns or (tuple(vs.CREGIT_COLUMNS) + vs2.ORGANIZATION_COLUMNS)
    sel = ", ".join(f"CAST(NULL AS {t}) AS \"{n}\"" for n, t in cols)
    kv = {**vs2.WANT_FOOTER, vs2.REGISTRY_KEY: REG_A, **(footer or {})}
    if old_keys:  # the footer of release 1: organisations_version, organisations_mapping_sha256
        kv = {vs2.OLD_FOOTER_KEYS.get(k, k): v for k, v in kv.items()}
    kvs = ", ".join(f"{k}: {lit(v)}" for k, v in kv.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    duckdb.sql(f"COPY (SELECT {sel} FROM range({rows})) TO {lit(path)} "
               f"(FORMAT PARQUET, KV_METADATA {{{kvs}}})")


def release_root(tmp_path, projects=("p__one", "p__two"), rows=None, named=None):
    root = tmp_path / "root"
    for p in projects:
        write_release_file(root / "parquet" / f"{p}-dataset.parquet",
                           footer={vs2.REGISTRY_KEY: REG_B} if p in (named or ()) else None)
    lines = ["project\trows"] + [f"{p}\t{(rows or {}).get(p, 3)}" for p in projects]
    (root / "MANIFEST.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    regs = [{"registry_sha256": REG_A, "files": len(projects)}]
    if named:
        regs.append({"registry_sha256": REG_B, "projects": list(named)})
    (root / "pseudonymization.json").write_text(json.dumps({"registries": regs}), encoding="utf-8")
    return root


def test_validate_good_root(tmp_path, capsys):
    root = release_root(tmp_path, projects=("p__one", "p__two", "p__three"), named=("p__three",))
    assert vs2.main([str(root), "--jobs", "2"]) == 0
    assert "OK: 3 files" in capsys.readouterr().out


def test_validate_accepts_the_old_footer_keys_of_release_1(tmp_path, capsys):
    root = release_root(tmp_path)
    write_release_file(root / "parquet" / "p__one-dataset.parquet", old_keys=True)
    assert vs2.main([str(root)]) == 0
    assert "OK: 2 files" in capsys.readouterr().out
    write_release_file(root / "parquet" / "p__one-dataset.parquet", old_keys=True,
                       footer={"organizations_version": "v4.8"})
    assert vs2.main([str(root)]) == 1
    assert "p__one: footer organizations_version is 'v4.8'" in capsys.readouterr().out


def test_validate_refuses_a_schema_1_file(tmp_path, capsys):
    root = release_root(tmp_path)
    vs = vs2.load_ca113e3()
    write_release_file(root / "parquet" / "p__one-dataset.parquet", columns=vs.EXPECTED_COLUMNS)
    assert vs2.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "p__one: " in out and "firm_based_on_namespace" in out and "firm_raw" in out


def test_validate_finds_rows_registry_and_manifest_gaps(tmp_path, capsys):
    root = release_root(tmp_path, rows={"p__two": 4})
    write_release_file(root / "parquet" / "p__extra-dataset.parquet")
    write_release_file(root / "parquet" / "p__one-dataset.parquet", footer={vs2.REGISTRY_KEY: REG_B})
    assert vs2.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "p__two: 3 rows, MANIFEST.tsv has 4" in out
    assert "p__extra: a file with no row in MANIFEST.tsv" in out
    assert f"p__one: footer {vs2.REGISTRY_KEY}" in out


def test_validate_reports_a_file_with_no_registry(tmp_path, capsys):
    root = release_root(tmp_path)
    (root / "pseudonymization.json").write_text(
        json.dumps({"registries": [{"registry_sha256": REG_A, "projects": ["p__one"]}]}),
        encoding="utf-8")
    assert vs2.main([str(root)]) == 1
    assert "p__two: pseudonymization.json gives no registry" in capsys.readouterr().out


def test_validate_reports_a_file_that_it_cannot_read(tmp_path, capsys):
    root = release_root(tmp_path)
    (root / "parquet" / "p__two-dataset.parquet").write_bytes(b"not a parquet file")
    assert vs2.main([str(root)]) == 1
    out = capsys.readouterr().out
    assert "p__two: cannot read the file" in out and "FAIL" in out


def test_validate_not_ready_with_no_file(tmp_path):
    (tmp_path / "parquet").mkdir()
    assert vs2.main([str(tmp_path)]) == 3


# compare_published.py

AT = chr(64)
PRE_ROWS = [
    # file_path, token_index, repo_name, author_name, author_email, person_domain, footer, firm
    ("a.c", 0, "r", "Ann Lee", f"ann{AT}x.org", " Example.COM ", ["Ann Lee <ann" + AT + "x.org>"], "f"),
    ("a.c", 1, "r", "ann lee", f"Ann{AT}x.org", "example.com", [], "f"),
    ("a.c", 2, "r", "Bo Ng", f"bo{AT}y.org", f"bo{AT}y.org", ["Bo Ng <bo" + AT + "y.org>",
                                                            "Bo Ng  <bo" + AT + "y.org>"], None),
    ("b.c", 0, "r", None, "", None, None, None),
]


def pseudo(v):
    return v if v is None or v == "" else ("P-" + str(abs(hash(v.lower())) % 10**6))


def footer_pseudo(e):
    return "F-" + e.split("<")[1].lower()


def write_pair(tmp_path, pub_rows=None, extra_pub=""):
    con = duckdb.connect()
    con.execute("CREATE TABLE pre (file_path VARCHAR, token_index BIGINT, repo_name VARCHAR, "
                "author_name VARCHAR, author_email VARCHAR, person_domain VARCHAR, "
                "footer_signed_off_by VARCHAR[], firm VARCHAR)")
    con.executemany("INSERT INTO pre VALUES (?, ?, ?, ?, ?, ?, ?, ?)", PRE_ROWS)
    pub = pub_rows if pub_rows is not None else [
        (fp, ti, rn, pseudo(an), pseudo(ae),
         pd.strip().lower() if pd and AT not in pd else ("y.org" if pd else pd),
         None if ft is None else [footer_pseudo(e) for e in ft], "dom")
        for fp, ti, rn, an, ae, pd, ft, _f in PRE_ROWS]
    con.execute("CREATE TABLE pub (file_path VARCHAR, token_index BIGINT, repo_name VARCHAR, "
                "author_name VARCHAR, author_email VARCHAR, person_domain VARCHAR, "
                "footer_signed_off_by VARCHAR[], firm_based_on_domain VARCHAR)")
    con.executemany("INSERT INTO pub VALUES (?, ?, ?, ?, ?, ?, ?, ?)", pub)
    a, b = tmp_path / "pre's.parquet", tmp_path / "pub.parquet"
    con.execute(f"COPY pre TO {lit(a)} (FORMAT PARQUET)")
    con.execute(f"COPY (SELECT * FROM pub) TO {lit(b)} (FORMAT PARQUET)")
    return str(a), str(b)


def test_compare_accepts_the_rule(tmp_path, capsys):
    a, b = write_pair(tmp_path)
    assert cp.main([a, b]) == 0, capsys.readouterr().out


def pub_with(change):
    rows = [list(r) for r in [
        (fp, ti, rn, pseudo(an), pseudo(ae),
         pd.strip().lower() if pd and AT not in pd else ("y.org" if pd else pd),
         None if ft is None else [footer_pseudo(e) for e in ft], "dom")
        for fp, ti, rn, an, ae, pd, ft, _f in PRE_ROWS]]
    change(rows)
    return [tuple(r) for r in rows]


CHANGES = [
    (lambda r: r[2].__setitem__(3, r[0][3]), "values that are not equal in lower case give one"),
    (lambda r: r[1].__setitem__(3, "P-other"), "equal in lower case give more than one"),
    (lambda r: r[2].__setitem__(2, "other"), "repo_name: 1 rows differ"),
    (lambda r: r[0].__setitem__(5, " Example.COM "), "not lower(trim(value))"),
    (lambda r: r[2].__setitem__(4, f"bo{AT}y.org"), "keep a value that is not empty"),
    (lambda r: r[2].__setitem__(6, ["F-x"]), "another list length"),
    (lambda r: r.reverse(), "the rows are not in the same order"),
]


def check_refused_change(tmp_path, capsys, change, text):
    a, b = write_pair(tmp_path, pub_rows=pub_with(change))
    assert cp.main([a, b]) == 1
    assert text in capsys.readouterr().out


test_compare_refuses_a_change_out_of_the_rule = pytest.mark.parametrize(
    "change, text", CHANGES)(check_refused_change)


def test_compare_usage():
    assert cp.main(["one"]) == 2
