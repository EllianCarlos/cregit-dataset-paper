"""Tests of link_format.py: the old and the new link files give the same columns."""
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import link_format as lf  # noqa: E402


@pytest.fixture
def con():
    c = duckdb.connect()
    yield c
    c.close()


def write(con, path: Path, sql: str) -> Path:
    con.execute(f"COPY ({sql}) TO '{path}' (FORMAT PARQUET)")
    return path


def test_domain_links_old_and_new_give_the_same_rows(con, tmp_path):
    old = write(con, tmp_path / "old.parquet", """
      SELECT * FROM (VALUES ('acme.com', 'acme', 'Acme', 'company', 'curated', 'exact', 'acme.com'),
                            ('me.name', NULL, NULL, 'independent', 'curated', 'exact', 'me.name'))
      t(domain, domain_company_id, domain_company, domain_company_kind, domain_company_confidence, match,
        matched_domain)""")
    new = write(con, tmp_path / "new.parquet", """
      SELECT * FROM (VALUES ('acme.com', 'acme', 'company', 'exact', 'acme.com', 'curated', 'gitdm'),
                            ('me.name', 'independent', 'independent', 'exact', 'me.name', 'curated', 'gitdm'))
      t(domain, firm_based_on_domain, organisation_kind, match, matched_domain, confidence, source)""")
    assert not lf.is_new_format(con, old) and lf.is_new_format(con, new)
    a = con.execute(f"{lf.domain_links_sql(con, old)} ORDER BY domain").fetchall()
    b = con.execute(f"{lf.domain_links_sql(con, new)} ORDER BY domain").fetchall()
    cols = [r[0] for r in con.execute(f"DESCRIBE {lf.domain_links_sql(con, new)}").fetchall()]
    assert tuple(cols) == lf.NEW_DOMAIN_COLS
    assert [r[:6] for r in a] == [r[:6] for r in b]
    assert a[0][6] is None and b[0][6] == "gitdm"


def test_project_links_new_format_takes_the_best_row_from_the_database(con, tmp_path):
    con.execute("ATTACH ':memory:' AS c")
    con.execute("CREATE TABLE c.company (company_id VARCHAR, review_status VARCHAR)")
    con.execute("INSERT INTO c.company VALUES ('acme', 'accepted'), ('lf', 'accepted'), ('nf', 'accepted'), "
                "('bad', 'rejected')")
    con.execute("CREATE TABLE c.company_namespace (host VARCHAR, namespace VARCHAR, company_id VARCHAR, "
                "relation VARCHAR, evidence VARCHAR, verified BOOLEAN)")
    con.execute("""INSERT INTO c.company_namespace VALUES
      ('github.com', 'acme', 'acme', 'owns', 'verified-domain', true),
      ('github.com', 'acme', 'lf', 'hosted_by', 'roster', false),
      ('github.com', 'proj', 'lf', 'hosted_by', 'roster', false),
      ('github.com', 'proj', 'nf', 'sponsored_by', 'roster', false),
      ('github.com', 'proj', 'acme', 'candidate', 'name', false),
      ('github.com', 'gone', 'bad', 'candidate', 'name', false)""")
    new = write(con, tmp_path / "p.parquet", """
      SELECT * FROM (VALUES ('acme/x', 'github.com', 'Acme', 'acme', true, 'sdtc'),
                            ('proj/y', 'github.com', 'proj', NULL, false, NULL),
                            ('gone/z', 'github.com', 'gone', NULL, false, NULL))
      t(project, host, namespace, firm_based_on_namespace, project_enterprise_driven, project_enterprise_basis)""")
    sql = lf.project_links_sql(con, new, "c")
    rows = {r[0]: r for r in con.execute(sql).fetchall()}
    assert rows["acme/x"][3:7] == ("acme", "acme", "owns", "verified-domain")
    # hosted_by and sponsored_by never count; the candidate row is the best row; no owner value.
    assert rows["proj/y"][3:7] == (None, "acme", "candidate", "name")
    # A rejected organisation gives no row.
    assert rows["gone/z"][3:7] == (None, None, None, None)
    assert lf.check_owns_agree(con, sql) == 0
    plain = {r[0]: r for r in con.execute(lf.project_links_sql(con, new)).fetchall()}
    assert plain["acme/x"][3:7] == ("acme", "acme", "owns", None)
    assert plain["proj/y"][3:7] == (None, None, None, None)


def test_project_links_old_format_keeps_only_owns_as_the_value(con, tmp_path):
    old = write(con, tmp_path / "p.parquet", """
      SELECT * FROM (VALUES ('acme/x', 'github.com', 'acme', 'acme', 'Acme', 'owns', 'verified-domain', true, 'sdtc'),
                            ('proj/y', 'github.com', 'proj', 'acme', 'Acme', 'candidate', 'name', false, NULL))
      t(project, host, namespace, namespace_company_id, namespace_company, namespace_company_relation,
        namespace_company_evidence, project_enterprise_driven, project_enterprise_basis)""")
    sql = lf.project_links_sql(con, old)
    cols = [r[0] for r in con.execute(f"DESCRIBE {sql}").fetchall()]
    assert tuple(cols) == lf.NEW_PROJECT_COLS
    rows = {r[0]: r for r in con.execute(sql).fetchall()}
    assert rows["acme/x"][3:7] == ("acme", "acme", "owns", "verified-domain")
    assert rows["proj/y"][3:7] == (None, "acme", "candidate", "name")


def test_a_file_of_another_kind_is_refused(con, tmp_path):
    other = write(con, tmp_path / "x.parquet", "SELECT 1 AS a")
    with pytest.raises(ValueError):
        lf.domain_links_sql(con, other)
