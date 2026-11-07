"""Tests of build_organisations.py on the small database, cache and sidecar of test_build_links.py."""
import csv
import json
import os
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import build_links  # noqa: E402
import build_organisations as bo  # noqa: E402
import build_v0  # noqa: E402
import error_model  # noqa: E402
from test_build_links import inputs, table  # noqa: E402,F401  (inputs is a fixture)


def error_model_dir(path: Path, links: Path) -> Path:
    """A small stand-in for the outputs of error_model.py: p_error by hashed domain key."""
    path.mkdir()
    con = duckdb.connect()
    doms = [r[0] for r in con.execute(f"SELECT domain FROM '{links}/domain_links.parquet'").fetchall()]
    con.execute("CREATE TABLE p (key_hash VARCHAR, error_stratum VARCHAR, p_error DOUBLE)")
    con.execute("CREATE TABLE l (key_hash VARCHAR, tokens BIGINT)")
    for i, d in enumerate(sorted(doms)):
        stratum = "user/B3 <10k/organisation/exact" if d == "acme.com" else "source/B3 <10k/organisation/exact"
        con.execute("INSERT INTO p VALUES (?, ?, ?)", [error_model.key_hash(d), stratum, 0.01 * (i + 1)])
        con.execute("INSERT INTO l VALUES (?, ?)", [error_model.key_hash(d), 10 * (i + 1)])
    con.execute(f"COPY p TO '{path}/organisation_domains_p_error.parquet' (FORMAT PARQUET)")
    con.execute(f"COPY l TO '{path}/link_error.parquet' (FORMAT PARQUET)")
    con.close()
    with open(path / "other_sources.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["source", "tokens", "organisation_share_of_proposals_pct"])
        w.writerow(["no real domain", 7, ""])
        w.writerow(["real domain with an AI proposal", 12, "9.623"])
    return path


def widen(db: Path) -> None:
    """The columns of a v4 database that the small database of test_build_links.py does not have."""
    con = duckdb.connect(str(db))
    for col, typ in (("is_company", "BOOLEAN"), ("sna_sector", "VARCHAR"), ("parent_company_id", "VARCHAR"),
                     ("university_id", "VARCHAR"), ("country", "VARCHAR"), ("wikidata_qid", "VARCHAR"),
                     ("status", "VARCHAR"), ("reviewer", "VARCHAR")):
        con.execute(f"ALTER TABLE company ADD COLUMN {col} {typ}")
    con.execute("UPDATE company SET is_company = kind IN ('company', 'consultancy'), reviewer = 'user'")
    con.execute("ALTER TABLE company_namespace ADD COLUMN namespace_type VARCHAR")
    con.close()


@pytest.fixture
def built(inputs, tmp_path):  # noqa: F811
    db, cache, sidecar, out = inputs
    widen(db)
    build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    em = error_model_dir(tmp_path / "em", out)
    rel, priv = tmp_path / "release" / "organisations", tmp_path / "private"
    res = bo.step_tables(db, out, em, rel, priv)
    return db, out, em, rel, priv, res


def test_key_hash_sql_equals_the_error_model_key():
    con = duckdb.connect()
    for d in ("acme.example.org", "mail.example.org", "x.y.example.org"):
        assert con.execute(f"SELECT {bo.key_hash_sql('?')}", [d]).fetchone()[0] == error_model.key_hash(d)


def test_public_domains_hold_no_personal_domain(built):
    db, links, em, rel, priv, res = built
    pub = {r["domain"]: r for r in table(rel / "organisation_domains.parquet")}
    full = {r["domain"]: r for r in table(priv / "organisation_domains.full.parquet")}
    assert "me.name" in full and full["me.name"]["organisation_id"] == "independent"
    assert "me.name" not in pub
    assert set(full) - set(pub) == {"me.name"}
    assert pub["gmail.com"]["organisation_id"] == "free-provider"      # free-provider domains stay
    assert pub["acme.com"]["review_path"] == "user decision"
    assert pub["eu.acme.com"]["review_path"] == "published or curated list, kept by the checks"
    assert all(r["p_error"] is not None for r in full.values())
    assert not (rel / "organisation_domains.full.parquet").exists()


def test_organisations_get_the_unknown_pseudo_id(built):
    db, links, em, rel, priv, res = built
    o = {r["organisation_id"]: r for r in table(rel / "organisations.parquet")}
    assert o["unknown"]["kind"] == "unknown" and o["unknown"]["is_company"] is False
    assert {"independent", "free-provider", "unknown"} <= set(o)
    assert "reviewer" not in o["acme"]


def test_link_error_strata_and_fallback_rows(built):
    db, links, em, rel, priv, res = built
    le = {r["error_stratum"]: r for r in table(rel / "link_error.parquet")}
    assert le["fallback/unknown/no real domain"]["estimate"] == 0.0
    assert le["fallback/independent/real domain with no row"]["estimate"] == pytest.approx(0.09623)
    assert le["fallback/independent/real domain with no row"]["interval_high"] == pytest.approx(2 * 0.09623)
    # every linked domain, also the personal ones, is in a stratum
    assert sum(r["links"] for r in le.values() if r["links"]) == len(table(priv / "organisation_domains.full.parquet"))
    lj = json.loads((links / "links.json").read_text())
    assert le["fallback/unknown/no real domain"]["tokens"] == round(
        lj["token_share_by_reason"]["unknown / no real domain"] * lj["total_tokens"])


def test_release_info_has_the_mapping_of_the_links(built):
    db, links, em, rel, priv, res = built
    info = {r["key"]: r["value"] for r in table(rel / "release_info.parquet")}
    lj = json.loads((links / "links.json").read_text())
    assert info["mapping_sha256"] == lj["mapping_sha256"]
    assert info["organisations_version"] == "v-test" and info["ctp_schema_version"] == "2"
    assert info["fallback_no_real_domain"] == "unknown"


def test_no_at_sign_in_any_table(built):
    db, links, em, rel, priv, res = built
    for f in list(rel.glob("*.parquet")) + list(priv.glob("*.parquet")):
        for r in table(f):
            assert not any(isinstance(v, str) and chr(64) in v for v in r.values()), (f, r)


def test_the_private_folder_must_not_be_the_release_folder(inputs, tmp_path):  # noqa: F811
    db, cache, sidecar, out = inputs
    widen(db)
    build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    em = error_model_dir(tmp_path / "em", out)
    with pytest.raises(RuntimeError, match="private"):
        bo.step_tables(db, out, em, tmp_path / "o", tmp_path / "o")


def test_views_give_the_ids_of_the_files_and_find_stale_files(built, tmp_path):
    db, links, em, rel, priv, res = built
    root = rel.parent
    (root / "parquet").mkdir()
    src = tmp_path / "src.parquet"
    con = duckdb.connect()
    con.execute("CREATE TABLE t (repo_name VARCHAR, token_index BIGINT, person_domain VARCHAR, firm VARCHAR)")
    con.executemany("INSERT INTO t VALUES ('acme__a', ?, ?, '')", [
        (0, "acme.com"), (1, "eu.acme.com"), (2, "me.name"), (3, "other.example.org"), (4, ""), (5, "gmail.com")])
    con.execute(f"COPY t TO '{src}' (FORMAT PARQUET)")
    con.close()
    dst = root / "parquet" / "acme__a-dataset.parquet"
    assert build_v0.main([str(src), str(dst), "--project", "acme__a",
                          "--project-links", str(links / "project_links.parquet"),
                          "--domain-links", str(links / "domain_links.parquet"),
                          "--organisations-version", "v-test", "--threads", "1", "--memory-limit", "1GB"]) == 0
    cwd = os.getcwd()
    try:
        names = bo.step_views(root, "parquet/*.parquet")
        assert {"tokens", "tokens_with_organisations", "tokens_with_current_organisations", "stale_files",
                "project_hosts", "project_sponsors"} <= set(names)
        os.chdir(root)
        c = duckdb.connect()
        c.execute("ATTACH 'organisations/dataset.duckdb' AS ds (READ_ONLY)")
        a = c.execute("SELECT person_domain, firm_based_on_domain, firm_based_on_namespace FROM ds.tokens "
                      "ORDER BY token_index").fetchall()
        b = c.execute("SELECT person_domain, firm_based_on_domain, firm_based_on_namespace "
                      "FROM ds.tokens_with_current_organisations ORDER BY token_index").fetchall()
        assert a == b
        assert [r[1] for r in a] == ["acme", "acme", "independent", "independent", "unknown", "free-provider"]
        assert c.execute("SELECT count(*) FROM ds.stale_files").fetchone()[0] == 0
        kinds = dict(c.execute("SELECT firm_based_on_domain, domain_organisation_kind "
                               "FROM ds.tokens_with_organisations").fetchall())
        assert kinds["unknown"] == "unknown" and kinds["acme"] == "company"
        c.close()
    finally:
        os.chdir(cwd)


def test_hosted_by_rows_and_the_project_hosts_view(inputs, tmp_path):  # noqa: F811
    """v4.3: organisation_namespaces keeps the hosted_by rows; the view project_hosts joins them to
    the projects; firm_based_on_namespace stays the organisation that controls the account."""
    db, cache, sidecar, out = inputs
    widen(db)
    con = duckdb.connect(str(db))
    con.execute("INSERT INTO company (company_id, name, kind, kind_basis, review_status) "
                "VALUES ('fdn', 'A Foundation', 'foundation', '', 'accepted')")
    con.execute("INSERT INTO company_namespace (host, namespace, company_id, relation, evidence, verified) "
                "VALUES ('github.com', 'acme', 'fdn', 'hosted_by', 'roster', NULL)")
    con.close()
    build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    em = error_model_dir(tmp_path / "em", out)
    rel = tmp_path / "release" / "organisations"
    bo.step_tables(db, out, em, rel, tmp_path / "private")
    c = duckdb.connect()
    for t in ("organisations", "organisation_namespaces", "project_organisations"):
        c.execute(f"CREATE VIEW {t} AS SELECT * FROM '{rel / (t + '.parquet')}'")
    assert c.execute("SELECT relation FROM organisation_namespaces WHERE organisation_id = 'fdn'").fetchall() == [("hosted_by",)]
    sql = [s for s in bo.view_sql("parquet/*.parquet") if s.startswith("CREATE VIEW project_hosts")]
    assert len(sql) == 1
    c.execute(sql[0])
    assert c.execute("SELECT project, hosted_by, hosted_by_kind FROM project_hosts").fetchall() == [
        ("acme__a", "fdn", "foundation")]
    assert c.execute("SELECT firm_based_on_namespace FROM project_organisations WHERE project = 'acme__a'").fetchone()[0] == "acme"


def test_sponsored_by_rows_and_the_project_sponsors_view(inputs, tmp_path):  # noqa: F811
    """v4.5: a fiscal sponsor has the relation sponsored_by (the user, 2026-10-20). The view
    project_sponsors joins those rows to the projects; project_hosts does not show them, and
    firm_based_on_namespace stays the organisation that controls the account."""
    db, cache, sidecar, out = inputs
    widen(db)
    con = duckdb.connect(str(db))
    con.execute("INSERT INTO company (company_id, name, kind, kind_basis, review_status) "
                "VALUES ('fsp', 'A Fiscal Sponsor', 'fiscal-sponsor', '', 'accepted')")
    con.execute("INSERT INTO company (company_id, name, kind, kind_basis, review_status) "
                "VALUES ('fdn', 'A Foundation', 'foundation', '', 'accepted')")
    con.execute("INSERT INTO company_namespace (host, namespace, company_id, relation, evidence, verified) "
                "VALUES ('github.com', 'acme', 'fsp', 'sponsored_by', 'roster', NULL), "
                "('github.com', 'acme', 'fdn', 'hosted_by', 'roster', NULL)")
    con.close()
    build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    em = error_model_dir(tmp_path / "em", out)
    rel = tmp_path / "release" / "organisations"
    bo.step_tables(db, out, em, rel, tmp_path / "private")
    c = duckdb.connect()
    for t in ("organisations", "organisation_namespaces", "project_organisations"):
        c.execute(f"CREATE VIEW {t} AS SELECT * FROM '{rel / (t + '.parquet')}'")
    for s in bo.view_sql("parquet/*.parquet"):
        if s.startswith("CREATE VIEW project_hosts") or s.startswith("CREATE VIEW project_sponsors"):
            c.execute(s)
    assert c.execute("SELECT project, sponsored_by, sponsored_by_name, sponsored_by_kind FROM project_sponsors").fetchall() == [
        ("acme__a", "fsp", "A Fiscal Sponsor", "fiscal-sponsor")]
    assert c.execute("SELECT project, hosted_by FROM project_hosts").fetchall() == [("acme__a", "fdn")]
    assert c.execute("SELECT firm_based_on_namespace FROM project_organisations WHERE project = 'acme__a'").fetchone()[0] == "acme"


def test_an_unknown_namespace_relation_stops_the_tables(inputs, tmp_path):  # noqa: F811
    db, cache, sidecar, out = inputs
    widen(db)
    con = duckdb.connect(str(db))
    con.execute("INSERT INTO company_namespace (host, namespace, company_id, relation, evidence, verified) "
                "VALUES ('github.com', 'acme', 'smallco', 'sponsors', 'roster', NULL)")
    con.close()
    build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    em = error_model_dir(tmp_path / "em", out)
    with pytest.raises(RuntimeError, match="unknown namespace relations"):
        bo.step_tables(db, out, em, tmp_path / "release" / "organisations", tmp_path / "private")


def test_review_path_of_round_9_strata():
    """error_model.py gives the origin r9 to the links that AI round 9 (v4.4) set."""
    con = duckdb.connect()
    stratum = "'" + error_model.error_stratum("r9", "B3 <10k", "company", "exact") + "'"
    assert con.execute(f"SELECT {bo.review_path_sql(stratum, chr(39) + 'x' + chr(39))}").fetchone()[0] == \
        "AI web check (round 9, v4.4)"
