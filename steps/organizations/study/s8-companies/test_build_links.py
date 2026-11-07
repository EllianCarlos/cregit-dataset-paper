"""Tests of build_links.py on a small database, cache and sidecar."""
import json
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import build_links  # noqa: E402


@pytest.fixture
def inputs(tmp_path):
    db = tmp_path / "companies.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE company (company_id VARCHAR, name VARCHAR, kind VARCHAR, kind_basis VARCHAR, "
                "review_status VARCHAR)")
    con.executemany("INSERT INTO company VALUES (?, ?, ?, ?, ?)", [
        ("acme", "Acme", "company", "sec-filer", "accepted"),
        ("smallco", "SmallCo", "company", "legal-form-in-name", "proposed"),
        ("gmail", "Gmail", "free-provider", "manual-review", "accepted"),
        ("uni", "Uni", "academic", "gov-or-edu-domain", "accepted"),
        ("bad", "Bad", "company", "", "rejected"),
        ("msft", "Microsoft", "company", "sec-filer", "accepted"),
        ("ctools", "commercetools", "company", "", "proposed"),
        ("independent", "Independent", "independent", "", "accepted"),
        ("free-provider", "Free mail provider", "free-provider", "", "accepted"),
        ("pre-git-import", "Pre-git import", "project", "", "accepted"),
    ])
    con.execute("CREATE TABLE company_domain (domain VARCHAR, company_id VARCHAR, confidence VARCHAR, "
                "source VARCHAR DEFAULT 'gitdm')")
    con.executemany("INSERT INTO company_domain (domain, company_id, confidence) VALUES (?, ?, ?)", [
        ("acme.com", "acme", "curated"), ("smallco.io", "smallco", "proposed"),
        ("gmail.com", "gmail", "curated"), ("uni.edu", "uni", "curated"), ("bad.com", "bad", "proposed"),
        ("berkeley.edu", "msft", "multi-developer"), ("tum.de", "ctools", "single-developer"),
        ("me.name", "independent", "curated"), ("osdl.org", "pre-git-import", "curated"),
    ])
    con.execute("CREATE TABLE company_namespace (host VARCHAR, namespace VARCHAR, company_id VARCHAR, "
                "relation VARCHAR, evidence VARCHAR, verified BOOLEAN)")
    con.executemany("INSERT INTO company_namespace VALUES (?, ?, ?, ?, ?, ?)", [
        ("github.com", "Acme", "acme", "owns", "company page", True),
        ("github.com", "shared", "smallco", "participates", "roster", False),
        ("github.com", "shared", "acme", "owns", "name match", False),
        ("gitlab.com", "solo", "smallco", "participates", "roster", True),
    ])
    con.close()
    cache = tmp_path / "cache"
    cache.mkdir()
    rows = {  # project -> (domain, email, tokens, commits)
        "acme__a": [("acme.com", "x@acme.com", 100, 10), ("eu.acme.com", "y@eu.acme.com", 90, 5),
                    ("gmail.com", "z@gmail.com", 80, 85)],
        "shared__b": [("smallco.io", "p@smallco.io", 50, 20), ("smallco.io", "q@smallco.io", 40, 20),
                      ("users.noreply.github.com", "n@users.noreply.github.com", 30, 60)],
        "solo__c": [("uni.edu", "u@uni.edu", 10, 1), ("bad.com", "b@bad.com", 10, 1), ("", "", 5, 1),
                    ("berkeley.edu", "e@berkeley.edu", 1, 1), ("tum.de", "t@tum.de", 1, 1),
                    ("in.tum.de", "i@in.tum.de", 1, 1), ("me.name", "m@me.name", 1, 1),
                    ("ppc.osdl.org", "o@ppc.osdl.org", 1, 1),
                    ("n+1@users.noreply.github.com", "n+1@users.noreply.github.com", 1, 1),
                    ("x@eu.acme.com", "x@eu.acme.com", 1, 1)],
    }
    c = duckdb.connect()
    for p, rs in rows.items():
        c.execute("CREATE OR REPLACE TABLE t (project VARCHAR, domain VARCHAR, email VARCHAR, "
                  "committer_domain VARCHAR, tokens BIGINT, commits BIGINT)")
        c.executemany("INSERT INTO t VALUES (?, ?, ?, '', ?, ?)", [(p, *r) for r in rs])
        c.execute(f"COPY t TO '{cache / (p + '.parquet')}' (FORMAT PARQUET)")
    sidecar = tmp_path / "meta.json"
    sidecar.write_text(json.dumps({
        "acme__a": {"clone_url": "https://github.com/acme/a.git", "owner": "acme"},
        "shared__b": {"clone_url": "https://github.com/shared/b.git", "owner": "shared"},
        "solo__c": {"clone_url": "https://gitlab.com/solo/c.git", "owner": "solo"},
    }))
    return db, cache, sidecar, tmp_path / "out"


def table(path, sql="SELECT * FROM t"):
    con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{path}')")
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def test_domain_links(inputs):
    db, cache, sidecar, out = inputs
    build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    d = {r["domain"]: r for r in table(out / "domain_links.parquet")}
    assert d["acme.com"]["firm_based_on_domain"] == "acme" and d["acme.com"]["match"] == "exact"
    assert d["acme.com"]["source"] == "gitdm" and d["eu.acme.com"]["source"] == "gitdm"
    assert d["eu.acme.com"]["firm_based_on_domain"] == "acme" and d["eu.acme.com"]["match"] == "suffix"
    assert d["eu.acme.com"]["matched_domain"] == "acme.com"
    # A free provider is never the author's company: its value is the pseudo id free-provider.
    assert d["gmail.com"]["firm_based_on_domain"] == "free-provider"
    assert d["gmail.com"]["organisation_kind"] == "free-provider"
    assert d["users.noreply.github.com"]["firm_based_on_domain"] == "free-provider"
    assert d["users.noreply.github.com"]["match"] == "rule"
    assert d["uni.edu"]["firm_based_on_domain"] == "uni" and d["uni.edu"]["organisation_kind"] == "academic"
    assert "bad.com" not in d  # rejected company
    assert "" not in d
    # An academic domain never gives a company; a single-developer row gives no suffix match.
    assert "berkeley.edu" not in d
    assert d["tum.de"]["firm_based_on_domain"] == "ctools" and "in.tum.de" not in d
    # The pseudo ids are values.
    assert d["me.name"]["firm_based_on_domain"] == "independent"
    assert d["ppc.osdl.org"]["firm_based_on_domain"] == "pre-git-import"
    assert d["ppc.osdl.org"]["organisation_kind"] == "project"
    # A dataset value that is an e-mail address gets no link.
    assert not any("@" in k for k in d)
    assert all(r["firm_based_on_domain"] for r in d.values())


def test_project_links(inputs):
    db, cache, sidecar, out = inputs
    s = build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    p = {r["project"]: r for r in table(out / "project_links.parquet")}
    assert set(p) == {"acme__a", "shared__b", "solo__c"}
    assert list(table(out / "project_links.parquet")[0]) == [
        "project", "host", "namespace", "firm_based_on_namespace", "project_enterprise_driven",
        "project_enterprise_basis"]
    # Namespace match is case-insensitive.
    assert p["acme__a"]["firm_based_on_namespace"] == "acme"
    # Only owns rows count: shared has an owns row (acme) and a participates row (smallco).
    assert p["shared__b"]["firm_based_on_namespace"] == "acme"
    # solo has only a participates row: no owner.
    assert p["solo__c"]["firm_based_on_namespace"] is None
    # acme__a: the top 3 authors hold 2 acme authors (sdtc); acme has 15 of 100 commits and a strong basis.
    assert p["acme__a"]["project_enterprise_driven"] is True
    assert p["acme__a"]["project_enterprise_basis"] == "sdtc,mcpc,mcve"
    # shared__b: smallco has a weak basis: sdtc and mcve, not mcpc.
    assert p["shared__b"]["project_enterprise_basis"] == "sdtc,mcve"
    assert p["solo__c"]["project_enterprise_driven"] is False and p["solo__c"]["project_enterprise_basis"] is None
    assert s["projects"] == 3 and s["projects_enterprise_driven"] == 2
    assert s["projects_with_namespace_owner"] == 2
    j = json.loads((out / "links.json").read_text())
    assert j["outputs"]["project_links.parquet"] and j["organisations_version"] == "v-test"


def test_fallback_values_and_token_shares(inputs):
    """A real domain with no row is independent; blank, no dot or an address is unknown (the user,
    2026-10-19). The token shares of links.json use the same rule as build_v0.py."""
    db, cache, sidecar, out = inputs
    s = build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    total = 270 + 120 + 32
    assert s["total_tokens"] == total
    r = s["token_share_by_reason"]
    # unknown: blank (5), the noreply address (1), the address under eu.acme.com (1)
    assert r["unknown / no real domain"] == pytest.approx(7 / total)
    # independent: bad.com (rejected, 10), berkeley.edu (1), in.tum.de (1); me.name has a row (1)
    assert r["independent / unmatched real domain"] == pytest.approx(12 / total)
    assert r["independent / linked"] == pytest.approx(1 / total)
    assert sum(s["token_share_by_value_class"].values()) == pytest.approx(1.0)
    assert s["token_share_by_kind"]["unknown"] == pytest.approx(7 / total)
    assert s["fallback"] == {"unmatched_real_domain": "independent", "no_real_domain": "unknown"}


def test_mapping_sha256_changes_only_with_the_mapping(inputs):
    db, cache, sidecar, out = inputs
    a = build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")["mapping_sha256"]
    con = duckdb.connect(str(db))
    con.execute("UPDATE company SET name = 'Acme Corp' WHERE company_id = 'acme'")
    con.close()
    b = build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")["mapping_sha256"]
    assert a == b       # a new name changes no id
    con = duckdb.connect(str(db))
    con.execute("UPDATE company_domain SET company_id = 'uni' WHERE domain = 'smallco.io'")
    con.close()
    c = build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")["mapping_sha256"]
    assert c != a


def test_a_database_without_the_free_provider_id_stops(inputs):
    db, cache, sidecar, out = inputs
    con = duckdb.connect(str(db))
    con.execute("DELETE FROM company WHERE company_id = 'free-provider'")
    con.close()
    with pytest.raises(RuntimeError, match="not an organisation"):
        build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")


def test_no_address_in_outputs(inputs):
    db, cache, sidecar, out = inputs
    build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    for f in ("domain_links.parquet", "project_links.parquet", "enterprise_audit.parquet"):
        for r in table(out / f):
            assert not any(isinstance(v, str) and "@" in v for v in r.values()), (f, r)


def test_dropped_domains_match_nothing(inputs):
    """A v4 database lists the domains that the review dropped; such a domain gets no company, not even
    by a suffix (eu.acme.com would match acme.com), and the other domains do not change."""
    db, cache, sidecar, out = inputs
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE company_domain_dropped (domain VARCHAR, company_id VARCHAR, reason VARCHAR, "
                "source VARCHAR)")
    con.execute("INSERT INTO company_domain_dropped VALUES ('eu.acme.com', 'acme', 'domain-decision', 'review-4f')")
    con.close()
    build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    dl = {r["domain"]: r for r in table(out / "domain_links.parquet")}
    assert "eu.acme.com" not in dl
    assert dl["acme.com"]["firm_based_on_domain"] == "acme"


def test_hosted_by_row_gives_no_namespace_value(inputs):
    """v4.3 (the user, 2026-10-19): a foundation that only hosts a project of the namespace has the
    relation hosted_by; only the owns row of the organisation that controls the account gives the value."""
    db, cache, sidecar, out = inputs
    con = duckdb.connect(str(db))
    con.execute("INSERT INTO company VALUES ('fdn', 'A Foundation', 'foundation', '', 'accepted')")
    con.execute("INSERT INTO company_namespace VALUES ('gitlab.com', 'solo', 'fdn', 'hosted_by', 'roster', true)")
    con.execute("INSERT INTO company_namespace VALUES ('github.com', 'acme', 'fdn', 'hosted_by', 'roster', true)")
    con.close()
    build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    p = {r["project"]: r for r in table(out / "project_links.parquet")}
    assert p["solo__c"]["firm_based_on_namespace"] is None
    assert p["acme__a"]["firm_based_on_namespace"] == "acme"


def split_inputs(cache, sidecar, tmp):
    """The fixture as two caches and two sidecars: solo__c alone in the second ones."""
    c1, c2 = tmp / "c1", tmp / "c2"
    c1.mkdir()
    c2.mkdir()
    for f in cache.glob("*.parquet"):
        (c2 if f.stem == "solo__c" else c1).joinpath(f.name).write_bytes(f.read_bytes())
    meta = json.loads(sidecar.read_text())
    s1, s2 = tmp / "s1.json", tmp / "s2.json"
    s1.write_text(json.dumps({k: v for k, v in meta.items() if k != "solo__c"}))
    s2.write_text(json.dumps({"solo__c": meta["solo__c"]}))
    return [c1, c2], [s1, s2]


def test_two_caches_and_sidecars_give_the_one_cache_result(inputs, tmp_path):
    db, cache, sidecar, out = inputs
    one = build_links.build(db, cache, sidecar, out, "1GB", 1, "v-test")
    caches, sidecars = split_inputs(cache, sidecar, tmp_path)
    out2 = tmp_path / "out2"
    two = build_links.build(db, caches, sidecars, out2, "1GB", 1, "v-test")
    assert two["mapping_sha256"] == one["mapping_sha256"]
    for f in ("domain_links.parquet", "project_links.parquet", "enterprise_audit.parquet"):
        assert table(out2 / f) == table(out / f), f
    for k in ("dataset_domains", "domain_links", "projects", "total_tokens", "token_share_by_kind",
              "projects_by_basis"):
        assert two[k] == one[k], k
    assert isinstance(one["inputs"]["sidecar_sha256"], str) and "caches" not in one["inputs"]
    assert len(two["inputs"]["sidecar_sha256"]) == 2 and len(two["inputs"]["caches"]) == 2


def test_main_takes_repeated_cache_and_sidecar(inputs, tmp_path):
    db, cache, sidecar, out = inputs
    caches, sidecars = split_inputs(cache, sidecar, tmp_path)
    argv = ["--organisations-version", "v-test", "--db", str(db), "--out", str(out),
            "--memory-limit", "1GB", "--threads", "1"]
    for c in caches:
        argv += ["--cache", str(c)]
    for s in sidecars:
        argv += ["--sidecar", str(s)]
    assert build_links.main(argv) == 0
    assert json.loads((out / "links.json").read_text())["projects"] == 3
    assert build_links.main(argv[:-2] + ["--sidecar", str(tmp_path / "none.json")]) == 2
    assert build_links.main(argv + ["--cache", str(tmp_path / "no-folder")]) == 2


def test_a_project_in_two_caches_or_sidecars_stops(inputs, tmp_path):
    db, cache, sidecar, out = inputs
    caches, sidecars = split_inputs(cache, sidecar, tmp_path)
    (caches[1] / "acme__a.parquet").write_bytes((caches[0] / "acme__a.parquet").read_bytes())
    with pytest.raises(RuntimeError, match="acme__a.parquet is in"):
        build_links.build(db, caches, sidecars, out, "1GB", 1, "v-test")
    with pytest.raises(RuntimeError, match="more than one sidecar"):
        build_links.build(db, cache, [sidecar, sidecars[1]], out, "1GB", 1, "v-test")
