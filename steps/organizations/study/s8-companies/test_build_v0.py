"""Tests for build_v0.py (S8, decisions D1 and D5; ctp schema version 2).
Run: python3 -I -m pytest -q -p no:cacheprovider test_build_v0.py (an interpreter with duckdb)

The source files are small Parquet files with a few columns, person_domain and the 3 firm columns.
The link files are small too. Nothing here reads a dataset file. Test domains use example.org."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_v0 as bv  # noqa: E402

AT = chr(64)
SRC_COLS = ["repo_name", "token_index", "person_domain", "firm_raw", "firm", "firm_source"]


def make_src(path: Path, domains: list, extra: tuple[str, ...] = ()) -> Path:
    con = duckdb.connect()
    cols = SRC_COLS + list(extra)
    con.execute(f"CREATE TABLE t ({', '.join(c + (' BIGINT' if c == 'token_index' else ' VARCHAR') for c in cols)})")
    con.executemany(f"INSERT INTO t VALUES ({', '.join('?' * len(cols))})",
                    [["o__r", i, d, "raw", "firm", "map"] + [None] * len(extra) for i, d in enumerate(domains)])
    con.execute(f"COPY t TO '{path}' (FORMAT PARQUET)")
    con.close()
    return path


def make_links(tmp: Path, project_rows: list[dict], domain_rows: list[dict]) -> tuple[Path, Path]:
    con = duckdb.connect()
    pcols = [("project", "VARCHAR")] + list(bv.PROJECT_COLS)
    con.execute(f"CREATE TABLE p ({', '.join(f'{c} {t}' for c, t in pcols)})")
    con.executemany(f"INSERT INTO p VALUES ({', '.join('?' * len(pcols))})",
                    [[r.get(c) for c, _ in pcols] for r in project_rows])
    con.execute("CREATE TABLE d (domain VARCHAR, firm_based_on_domain VARCHAR, organisation_kind VARCHAR)")
    con.executemany("INSERT INTO d VALUES (?, ?, ?)",
                    [[r["domain"], r["firm_based_on_domain"], r.get("organisation_kind")] for r in domain_rows])
    pl, dl = tmp / "project_links.parquet", tmp / "domain_links.parquet"
    con.execute(f"COPY p TO '{pl}' (FORMAT PARQUET)")
    con.execute(f"COPY d TO '{dl}' (FORMAT PARQUET)")
    con.close()
    return pl, dl


PROJECT = {"project": "o__r", "firm_based_on_namespace": "acme", "project_enterprise_driven": True,
           "project_enterprise_basis": "sdtc"}
DOMAINS = [{"domain": "acme.example.org", "firm_based_on_domain": "acme", "organisation_kind": "company"},
           {"domain": "apache.example.org", "firm_based_on_domain": "apache", "organisation_kind": "foundation"},
           {"domain": "mail.example.org", "firm_based_on_domain": "free-provider",
            "organisation_kind": "free-provider"}]


def run(src, dst, pl, dl, threads="1", version="v-test") -> int:
    return bv.main([str(src), str(dst), "--project", "o__r", "--project-links", str(pl), "--domain-links", str(dl),
                    "--organisations-version", version, "--threads", threads, "--memory-limit", "1GB"])


def rows(path: Path, cols: str) -> list[tuple]:
    con = duckdb.connect()
    out = con.execute(f"SELECT {cols} FROM read_parquet(?)", [str(path)]).fetchall()
    con.close()
    return out


def test_the_columns_and_the_values(tmp_path):
    src = make_src(tmp_path / "a.parquet", ["acme.example.org", "Apache.example.org ", "mail.example.org", None,
                                            "other.example.org", "nodot", "", "n" + AT + "acme.example.org"])
    pl, dl = make_links(tmp_path, [PROJECT], DOMAINS)
    dst = tmp_path / "b.parquet"
    assert run(src, dst, pl, dl) == 0
    con = duckdb.connect()
    names = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(dst)]).fetchall()]
    con.close()
    # The 3 firm columns leave; the 4 organisation columns come at the end (ctp schema 2).
    assert names == ["repo_name", "token_index", "person_domain"] + [c for c, _ in bv.ORG_COLUMNS]
    got = rows(dst, "token_index, firm_based_on_domain, firm_based_on_namespace, project_enterprise_driven, "
                    "project_enterprise_basis")
    assert got == [(0, "acme", "acme", True, "sdtc"),
                   (1, "apache", "acme", True, "sdtc"),         # lower(trim()) in the join
                   (2, "free-provider", "acme", True, "sdtc"),
                   (3, "unknown", "acme", True, "sdtc"),        # NULL: no real domain
                   (4, "independent", "acme", True, "sdtc"),    # a real domain with no row
                   (5, "unknown", "acme", True, "sdtc"),        # no dot
                   (6, "unknown", "acme", True, "sdtc"),        # blank
                   (7, "unknown", "acme", True, "sdtc")]        # an address, not a domain
    # person_domain is copied as it is; only the join key is normalized.
    assert rows(dst, "person_domain")[1] == ("Apache.example.org ",)


def test_the_footer_has_the_schema_and_the_mapping(tmp_path):
    src = make_src(tmp_path / "a.parquet", ["acme.example.org"])
    pl, dl = make_links(tmp_path, [PROJECT], DOMAINS)
    dst = tmp_path / "b.parquet"
    assert run(src, dst, pl, dl, version="v4.1") == 0
    con = duckdb.connect()
    kv = bv.footer(con, dst)
    con.close()
    want = bv.mapping_sha256([(d["domain"], d["firm_based_on_domain"]) for d in DOMAINS],
                             [("o__r", "acme")])
    assert kv["ctp_schema_version"] == "2" and kv["organisations_version"] == "v4.1"
    assert kv["organisations_mapping_sha256"] == want


def test_mapping_sha256_ignores_the_order_and_sees_each_change():
    d = [("a.example.org", "a"), ("b.example.org", "b")]
    p = [("x__y", "a"), ("z__w", None)]
    h = bv.mapping_sha256(d, p)
    assert h == bv.mapping_sha256(d[::-1], p[::-1])
    assert h != bv.mapping_sha256([("a.example.org", "b"), ("b.example.org", "b")], p)
    assert h != bv.mapping_sha256(d, [("x__y", None), ("z__w", None)])


def test_the_row_order_stays_on_a_larger_file(tmp_path):
    pool = ["acme.example.org", "apache.example.org", "x.example.org", "mail.example.org", "acme.example.org", ""]
    doms = [pool[(i * 7919) % 6] for i in range(20000)]
    src = make_src(tmp_path / "a.parquet", doms)
    pl, dl = make_links(tmp_path, [PROJECT], DOMAINS)
    dst = tmp_path / "b.parquet"
    assert run(src, dst, pl, dl, threads="4") == 0
    got = rows(dst, "token_index, person_domain, firm_based_on_domain")
    assert [r[0] for r in got] == list(range(20000))
    want = {"acme.example.org": "acme", "apache.example.org": "apache", "mail.example.org": "free-provider",
            "x.example.org": "independent", "": "unknown"}
    assert all(r[2] == want[r[1]] for r in got)


def test_a_project_without_links_gets_nulls(tmp_path):
    src = make_src(tmp_path / "a.parquet", ["acme.example.org"])
    pl, dl = make_links(tmp_path, [dict(PROJECT, project="other")], DOMAINS)
    dst = tmp_path / "b.parquet"
    assert run(src, dst, pl, dl) == 0
    assert rows(dst, "firm_based_on_namespace, firm_based_on_domain, project_enterprise_driven, "
                     "project_enterprise_basis") == [(None, "acme", None, None)]


def test_a_repeated_domain_or_project_writes_nothing(tmp_path):
    src = make_src(tmp_path / "a.parquet", ["acme.example.org"])
    pl, dl = make_links(tmp_path, [PROJECT], DOMAINS + [DOMAINS[0]])
    assert run(src, tmp_path / "b.parquet", pl, dl) == 1
    pl, dl = make_links(tmp_path, [PROJECT, PROJECT], DOMAINS)
    assert run(src, tmp_path / "c.parquet", pl, dl) == 1
    assert not list(tmp_path.glob("[bc].parquet")) and not list(tmp_path.glob(".*v0-tmp"))


def test_a_file_with_link_columns_is_refused(tmp_path):
    src = make_src(tmp_path / "a.parquet", ["acme.example.org"])
    pl, dl = make_links(tmp_path, [PROJECT], DOMAINS)
    dst = tmp_path / "b.parquet"
    assert run(src, dst, pl, dl) == 0
    assert run(dst, tmp_path / "c.parquet", pl, dl) == 1          # already ctp schema 2
    old = make_src(tmp_path / "old.parquet", ["acme.example.org"], extra=("domain_company_id",))
    assert run(old, tmp_path / "d.parquet", pl, dl) == 1          # a file of the first v0
    assert not (tmp_path / "c.parquet").exists() and not (tmp_path / "d.parquet").exists()


# --------------------------------------------------------------------------------------------
# --pseudonymize: the fused write with pseudonymize.py of ctp-anon (synthetic data only)
# --------------------------------------------------------------------------------------------
# The source is a synthetic v1-raw file of pseudonymize.make_synthetic() (all 70 columns, invented
# people of the example domains). The salt is made in the test and thrown away. CTP_ANON_DIR names
# the folder of pseudonymize.py (default ~/Projects/ctp-anon).

import base64  # noqa: E402
import os  # noqa: E402

ANON_DIR = Path(os.environ.get("CTP_ANON_DIR", Path.home() / "Projects/ctp-anon"))


def anon_module():
    if not (ANON_DIR / "pseudonymize.py").is_file():
        pytest.skip(f"no pseudonymize.py in {ANON_DIR}")
    P = bv.load_pseudonymize(ANON_DIR)
    if not P.find_psl():
        pytest.skip("no Public Suffix List")
    return P


def make_salt(path: Path) -> Path:
    path.write_text(base64.b64encode(os.urandom(32)).decode() + "\n")
    path.chmod(0o400)
    return path


def make_v1raw(P, path: Path, rows: int = 3000, at_every: int = 7) -> Path:
    """A synthetic v1-raw file (ctp schema 1, 70 columns). Each `at_every`-th row gets a
    person_domain with the at sign (rule E gives acme.example.org)."""
    con = duckdb.connect()
    tmp = path.with_name(path.name + ".base")
    P.make_synthetic(con, str(tmp), rows, schema2=False)
    con.execute(f"COPY (SELECT * REPLACE (CASE WHEN token_index % {at_every} = 0 "
                f"THEN 'n' || chr(64) || 'Acme.example.org' ELSE person_domain END AS person_domain) "
                f"FROM read_parquet('{tmp}')) TO '{path}' (FORMAT PARQUET)")
    project = con.execute(f"SELECT any_value(repo_name) FROM read_parquet('{path}')").fetchone()[0]
    con.close()
    tmp.unlink()
    return path, project


def make_registry(P, tmp: Path, srcs: list[Path], salt: Path) -> tuple[Path, str]:
    import io
    keys = P.derive_keys(P.A.load_salt(path=str(salt), env={}))
    reg = tmp / "private" / "registry.parquet"
    r = P.build_registry([str(s) for s in srcs], keys, str(reg), threads=1, memory_limit="1GB",
                         psl=P.find_psl(), out=io.StringIO())
    return reg, r["registry_sha256"]


def anon_args(P, salt: Path, reg: Path, sha: str | None = None) -> list[str]:
    a = ["--pseudonymize", "--salt-file", str(salt), "--registry", str(reg), "--psl", P.find_psl(),
         "--anon-dir", str(ANON_DIR)]
    return a + (["--registry-sha256", sha] if sha else [])


@pytest.fixture
def fused(tmp_path):
    P = anon_module()
    src, project = make_v1raw(P, tmp_path / "src.parquet")
    salt = make_salt(tmp_path / "salt")
    reg, sha = make_registry(P, tmp_path, [src], salt)
    pl, dl = make_links(tmp_path, [dict(PROJECT, project=project)], DOMAINS)
    return dict(P=P, src=src, project=project, salt=salt, reg=reg, sha=sha, pl=pl, dl=dl, tmp=tmp_path)


def run_fused(f, dst: Path, extra: list[str] | None = None, salt: Path | None = None, sha: str | None = None) -> int:
    return bv.main([str(f["src"]), str(dst), "--project", f["project"], "--project-links", str(f["pl"]),
                    "--domain-links", str(f["dl"]), "--organisations-version", "v-test", "--threads", "1",
                    "--memory-limit", "1GB"] + anon_args(f["P"], salt or f["salt"], f["reg"], sha) + (extra or []))


def test_fused_write_gives_schema_2_pseudonyms_and_the_footer(fused, capsys):
    P, dst = fused["P"], fused["tmp"] / "out.parquet"
    assert run_fused(fused, dst) == 0
    out = capsys.readouterr().out
    assert "registry " + fused["sha"][:12] in out and "scan ok" in out and AT not in out
    con = duckdb.connect()
    assert bv.column_types(con, dst) == [tuple(c) for c in P.SCHEMA_2]
    kv = bv.footer(con, dst)
    assert kv["ctp_schema_version"] == "2" and kv["organisations_version"] == "v-test"
    assert kv[P.FOOTER_VERSION_KEY] == P.SCHEME_VERSION and kv[P.FOOTER_REGISTRY_KEY] == fused["sha"]
    assert P.identity_shape_violations(con, f"SELECT * FROM read_parquet('{dst}')") == {}
    n, raw = con.execute("SELECT count(*), count(*) FILTER (WHERE strpos(author_email, chr(64)) > 0 AND "
                         "NOT starts_with(author_email, 'author_')) FROM read_parquet(?)", [str(dst)]).fetchone()
    assert n == 3000 and raw == 0
    con.close()


def test_fused_write_keys_person_domain_by_rule_e(fused):
    """A person_domain with the at sign: the old path gives `unknown`; the fused write publishes
    the rule E domain and looks it up (acme), so the link key equals the value in the file."""
    old, new = fused["tmp"] / "old.parquet", fused["tmp"] / "new.parquet"
    assert bv.main([str(fused["src"]), str(old), "--project", fused["project"], "--project-links",
                    str(fused["pl"]), "--domain-links", str(fused["dl"]), "--organisations-version", "v-test",
                    "--threads", "1", "--memory-limit", "1GB"]) == 0
    assert run_fused(fused, new) == 0
    q = ("SELECT token_index, person_domain, firm_based_on_domain FROM read_parquet(?) "
         "WHERE token_index % 7 = 0 ORDER BY token_index LIMIT 3")
    con = duckdb.connect()
    o, n = con.execute(q, [str(old)]).fetchall(), con.execute(q, [str(new)]).fetchall()
    con.close()
    assert [r[2] for r in o] == ["unknown"] * 3 and all(AT in r[1] for r in o)
    assert [r[1:] for r in n] == [("acme.example.org", "acme")] * 3


def test_fused_write_keeps_the_rows_in_place(fused):
    """The passthrough columns of the fused output equal those of the old path row by row
    (person_domain through the published expression); the identity columns change."""
    old, new = fused["tmp"] / "old.parquet", fused["tmp"] / "new.parquet"
    assert bv.main([str(fused["src"]), str(old), "--project", fused["project"], "--project-links",
                    str(fused["pl"]), "--domain-links", str(fused["dl"]), "--organisations-version", "v-test",
                    "--threads", "1", "--memory-limit", "1GB"]) == 0
    assert run_fused(fused, new) == 0
    P = fused["P"]
    plan = P.A.classify([c for c, _ in P.SCHEMA_2], drop_footers=False)
    org = {c for c, _ in bv.ORG_COLUMNS}                      # rule E changes firm_based_on_domain
    same = [c for c in plan.passthrough if c != "person_domain" and c not in org]
    con = duckdb.connect()
    P.install(con, None, psl=P.load_psl(P.find_psl()))
    assert bv.order_hash(con, old, same) == bv.order_hash(con, new, same)
    pd = [P.person_domain_expr(bv.q("person_domain"))]
    assert bv.order_hash(con, old, [], pd) == bv.order_hash(con, new, ["person_domain"])
    assert bv.order_hash(con, old, ["author_email"]) != bv.order_hash(con, new, ["author_email"])
    con.close()


def test_fused_write_refuses_another_salt_and_a_wrong_registry_sha(fused, capsys):
    other = make_salt(fused["tmp"] / "other-salt")
    dst = fused["tmp"] / "out.parquet"
    assert run_fused(fused, dst, salt=other) == 2
    assert run_fused(fused, dst, sha="0" * 64) == 2
    err = capsys.readouterr().err
    assert "salt check" in err and "--registry-sha256" in err
    assert not dst.exists() and not list(fused["tmp"].glob(".*v0-tmp"))
    assert run_fused(fused, dst, sha=fused["sha"]) == 0           # the footer check of run_v0.py


def test_fused_write_usage(fused, capsys):
    base = [str(fused["src"]), str(fused["tmp"] / "x.parquet"), "--project", fused["project"],
            "--project-links", str(fused["pl"]), "--domain-links", str(fused["dl"]),
            "--organisations-version", "v-test"]
    assert bv.main(base + ["--pseudonymize"]) == 2
    assert bv.main(base + ["--salt-file", str(fused["salt"])]) == 2
    assert bv.main(base + ["--no-scan"]) == 2
    assert "--pseudonymize needs --salt-file, --registry, --psl" in capsys.readouterr().err


def test_a_raw_address_in_an_identity_column_is_found(fused):
    P, dst = fused["P"], fused["tmp"] / "out.parquet"
    assert run_fused(fused, dst) == 0
    bad = fused["tmp"] / "bad.parquet"
    con = duckdb.connect()
    con.execute(f"COPY (SELECT * REPLACE (CASE WHEN token_index = 5 THEN 'x' || chr(64) || 'example.org' "
                f"ELSE author_email END AS author_email, CASE WHEN token_index = 6 THEN ['Ann Bee'] "
                f"ELSE footer_person_names END AS footer_person_names) FROM read_parquet('{dst}')) "
                f"TO '{bad}' (FORMAT PARQUET)")
    got = P.identity_shape_violations(con, f"SELECT * FROM read_parquet('{bad}')")
    con.close()
    assert got["author_email"] == 1 and got["footer_person_names"] == 1
    assert sum(got.values()) == 2


def test_fused_write_can_skip_the_content_columns_of_the_scan(fused, capsys):
    dst = fused["tmp"] / "out.parquet"
    assert run_fused(fused, dst, ["--no-content-scan", "--scan-threads", "2"]) == 0
    assert "scan ok (information columns skipped)" in capsys.readouterr().out
    base = [str(fused["src"]), str(fused["tmp"] / "x.parquet"), "--project", fused["project"],
            "--project-links", str(fused["pl"]), "--domain-links", str(fused["dl"]),
            "--organisations-version", "v-test", "--no-content-scan"]
    assert bv.main(base) == 2                                    # it needs --pseudonymize


def test_the_old_path_does_not_load_pseudonymize(tmp_path):
    src = make_src(tmp_path / "a.parquet", ["acme.example.org"])
    pl, dl = make_links(tmp_path, [PROJECT], DOMAINS)
    before = "pseudonymize" in sys.modules
    assert run(src, tmp_path / "b.parquet", pl, dl) == 0
    assert ("pseudonymize" in sys.modules) == before
