#!/usr/bin/env python3
"""Write the organisation reference tables of the release (S8, LINK_COLUMNS_DESIGN.md section 3).

    build_organisations.py tables --links DIR --out DIR --private-out DIR [--db companies.v4.duckdb]
                                  [--error-model DIR]
    build_organisations.py views --root DIR [--projects-glob 'parquet/*.parquet']

Step `tables` writes into --out (the folder `organisations/` of the release):
  organisations.parquet            one row per organisation id of the database, plus the pseudo id
                                   `unknown` (the user, 2026-10-19). The columns reviewer, note,
                                   website and the source pointers are left out (reviewer can hold a
                                   person name).
  organisation_domains.parquet     one row per dataset domain with a link to an organisation or to
                                   free-provider (domain_links.parquet of build_links.py):
                                   organisation_id, match, matched_domain, confidence, source,
                                   review_path, error_stratum, p_error. The domains that map to
                                   `independent` (personal and vanity domains) are left out (the
                                   user, 2026-10-19): a domain with no row gets `independent` (real
                                   domain) or `unknown`, so the join gives the same ids as the files.
  organisation_namespaces.parquet  the namespace rows of the database (relation owns, hosted_by,
                                   sponsored_by, participates, candidate). firm_based_on_namespace uses
                                   the owns rows only: the organisation that controls the account.
                                   hosted_by (v4.3, the user, 2026-10-19): a foundation that hosts a
                                   project of the namespace (from its roster) but does not control the
                                   account. sponsored_by (v4.5, the user, 2026-10-20): a fiscal sponsor
                                   that sponsors a project of the namespace (its list of sponsored
                                   projects names it); a fiscal sponsor never owns an account.
  project_organisations.parquet    one row per project: firm_based_on_namespace and the two
                                   enterprise columns (project_links.parquet of build_links.py).
  link_error.parquet               one row per error stratum: links, tokens, the token-weighted
                                   p_error, its range, and the method; plus one row for each of the
                                   two fallback values. The audit columns stay NULL until the audit.
  release_info.parquet             key and value: organisations_version, ctp_schema_version,
                                   mapping_sha256 (the same value as the footer of each project file),
                                   the fallback values, the sha256 of the inputs and of each table.
--private-out (never in the release; it lists personal domains) gets organisation_domains.full.parquet:
the same columns for every linked domain, also the `independent` ones. link_error uses it.
Step `views` writes ROOT/organisations/dataset.duckdb: views only, with paths relative to ROOT
(ROOT holds organisations/ and the project files). Open it with ROOT as the working folder:
  cd ROOT; duckdb -c "ATTACH 'organisations/dataset.duckdb' AS ds (READ_ONLY); FROM ds.release_info"
The views: one per table, tokens (all project files), tokens_with_organisations (the ids in the
files joined to organisations), tokens_with_current_organisations (the ids from a join of
person_domain to organisation_domains, so a newer table applies without a rewrite of the files),
stale_files (the files whose mapping hash is not the one of release_info), project_hosts (the
foundations that host each project: the hosted_by rows of its namespace; the parent of a project
row in organisations gives the main interested entity, rule R4), project_sponsors (the fiscal
sponsors of each project: the sponsored_by rows of its namespace).

The p_error and error_stratum columns come from error_model.py (organisation_domains_p_error.parquet,
by the hashed domain key) and the tokens of each link from its link_error.parquet. The rows of
two runs are the same (no time stamp). No table holds an address: each VARCHAR column is checked
for the at sign. Privacy: the public organisation_domains holds no `independent` row, so it lists
no personal domain (the user, 2026-10-19). person_domain itself stays readable in v1-public today.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_v0 import CTP_SCHEMA_VERSION, DOMAIN_KEY, NO_REAL_DOMAIN, UNMATCHED_REAL, real_domain_sql  # noqa: E402
from build_v0 import mapping_sha256_of_files  # noqa: E402

COMP = Path.home() / "Projects/cregit-workspace/companies"
NS_RELATIONS = ("owns", "hosted_by", "sponsored_by", "participates", "candidate")
TABLES = ("organisations", "organisation_domains", "organisation_namespaces", "project_organisations",
          "link_error", "release_info")
# The pseudo id of a token with no real domain (the user, 2026-10-19). Not in the v4.1 database.
UNKNOWN_ROW = {"organisation_id": NO_REAL_DOMAIN, "name": "(Unknown: no real e-mail domain)", "kind": "unknown",
               "is_company": False, "sna_sector": None, "kind_basis": "rule-no-real-domain", "parent_company_id": None,
               "university_id": None, "country": None, "wikidata_qid": None, "status": None,
               "review_status": "accepted"}
ORG_COLS = tuple(UNKNOWN_ROW)
# The step that set the value of a link (the first part of error_stratum) -> review path.
REVIEW_PATH = {
    "user": "user decision",
    "AB": "AI review: two blind rounds agree (rounds 3 and 4)",
    "r5/r6": "AI review: one answer (adjudication round 5 or research round 6)",
    "r4d/r4f": "AI domain check (round 4d or 4f)",
    "r7": "AI check (round 7)",
    "r8": "AI check (round 8)",
    "r9": "AI web check (round 9, v4.4)",
}
METHOD_LINK = "type B: Bayes rule on the path of each link, central values (ERROR_MODEL.md section 4.5); no audit yet"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def no_at(con, rel: str) -> None:
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall() if r[1] == "VARCHAR"]
    if cols:
        cond = " OR ".join(f'contains("{c}", chr(64))' for c in cols)
        n = con.execute(f"SELECT count(*) FROM {rel} WHERE {cond}").fetchone()[0]
        if n:
            raise RuntimeError(f"{rel}: {n} rows hold the at sign")


def copy(con, rel: str, dst: Path) -> None:
    tmp = dst.with_name(f".{dst.name}.tmp")
    con.execute(f"COPY (SELECT * FROM {rel}) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    os.replace(tmp, dst)


def key_hash_sql(expr: str) -> str:
    """SQL twin of error_model.key_hash (a test checks that both give the same value)."""
    return f"left(sha256('s8-error-model:' || {expr}), 16)"


def review_path_sql(stratum: str, source: str) -> str:
    """SQL: the review path of a link from the first part of its error stratum and its first source."""
    origin = f"regexp_extract({stratum}, '^(.*)/[^/]*/[^/]*/[^/]*$', 1)"
    cases = " ".join(f"WHEN {origin} = '{k}' THEN '{v}'" for k, v in REVIEW_PATH.items())
    return (f"CASE WHEN {stratum} IS NULL THEN NULL {cases} "
            f"WHEN {source} = 'rule' THEN 'rule (free-provider address suffix)' "
            f"WHEN {source} LIKE 'claude-proposal%' THEN 'AI proposal, kept by the checks' "
            "ELSE 'published or curated list, kept by the checks' END")


def fallback_error(em: Path) -> float:
    """The error of `independent` for a real domain with no row: the organisation share of the AI
    proposals (other_sources.csv of error_model.py; ERROR_MODEL.md section 6.3)."""
    with open(em / "other_sources.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("organisation_share_of_proposals_pct"):
                return float(r["organisation_share_of_proposals_pct"]) / 100
    raise RuntimeError(f"{em}/other_sources.csv: no organisation share of the proposals")


def step_tables(db: Path, links: Path, em: Path, out: Path, private_out: Path) -> dict:
    if private_out.resolve() == out.resolve():
        raise RuntimeError("--private-out must not be the release folder")
    out.mkdir(parents=True, exist_ok=True)
    private_out.mkdir(parents=True, exist_ok=True)
    lj = json.loads((links / "links.json").read_text())
    for name in ("domain_links.parquet", "project_links.parquet"):
        if sha256(links / name) != lj["outputs"][name]:
            raise RuntimeError(f"{links / name}: the sha256 is not the one in links.json")
    con = duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})
    con.execute(f"ATTACH '{db}' AS c (READ_ONLY)")
    cols = ", ".join(c if c != "organisation_id" else "company_id AS organisation_id" for c in ORG_COLS)
    con.execute(f"CREATE TABLE organisations AS SELECT {cols} FROM c.company")
    if not con.execute("SELECT count(*) FROM organisations WHERE organisation_id = ?", [NO_REAL_DOMAIN]).fetchone()[0]:
        con.execute(f"INSERT INTO organisations VALUES ({', '.join('?' * len(ORG_COLS))})", list(UNKNOWN_ROW.values()))
    con.execute("CREATE OR REPLACE TABLE organisations AS FROM organisations ORDER BY organisation_id")
    con.execute(f"""
      CREATE TABLE organisation_domains_full AS
      SELECT l.domain, l.firm_based_on_domain AS organisation_id, l.match, l.matched_domain, l.confidence,
             l.source, {review_path_sql('p.error_stratum', 'l.source')} AS review_path, p.error_stratum, p.p_error
      FROM read_parquet('{links}/domain_links.parquet') l
      LEFT JOIN read_parquet('{em}/organisation_domains_p_error.parquet') p ON p.key_hash = {key_hash_sql('l.domain')}
      ORDER BY l.domain""")
    # The public table: no personal domain (no `independent` row; the user, 2026-10-19).
    con.execute(f"CREATE TABLE organisation_domains AS FROM organisation_domains_full "
                f"WHERE organisation_id <> '{UNMATCHED_REAL}' ORDER BY domain")
    con.execute("""
      CREATE TABLE organisation_namespaces AS
      SELECT host, namespace, namespace_type, company_id AS organisation_id, relation, evidence, verified
      FROM c.company_namespace ORDER BY host, namespace, organisation_id, relation""")
    con.execute(f"CREATE TABLE project_organisations AS SELECT * FROM read_parquet('{links}/project_links.parquet') "
                "ORDER BY project")
    # link_error: the tokens of each link from the link_error.parquet of the error model (hashed keys).
    org_err = fallback_error(em)
    unm, unk = (lj["token_share_by_reason"].get(k, 0.0) * lj["total_tokens"]
                for k in ("independent / unmatched real domain", "unknown / no real domain"))
    con.execute(f"""
      CREATE TABLE link_error AS
      SELECT error_stratum, count(*)::BIGINT AS links, sum(t.tokens)::BIGINT AS tokens,
             sum(t.tokens * p.p_error) / sum(t.tokens) AS estimate, min(p.p_error) AS p_error_min,
             max(p.p_error) AS p_error_max, NULL::BIGINT AS audited, NULL::BIGINT AS errors,
             NULL::DOUBLE AS interval_low, NULL::DOUBLE AS interval_high, '{METHOD_LINK}' AS method
      FROM read_parquet('{em}/organisation_domains_p_error.parquet') p
      JOIN read_parquet('{em}/link_error.parquet') t USING (key_hash)
      WHERE p.key_hash IN (SELECT {key_hash_sql('domain')} FROM organisation_domains_full)
      GROUP BY error_stratum
      UNION ALL SELECT 'fallback/{UNMATCHED_REAL}/real domain with no row', NULL, {round(unm)}, {org_err}, NULL, NULL,
             NULL, NULL, 0.0, {2 * org_err},
             'type B: rectangular from 0 to 2 x the organisation share of the AI proposals (ERROR_MODEL.md section 6.3)'
      UNION ALL SELECT 'fallback/{NO_REAL_DOMAIN}/no real domain', NULL, {round(unk)}, 0.0, NULL, NULL, NULL, NULL,
             0.0, 0.0, 'none: the value says that the address is not known (ERROR_MODEL.md assumption A11)'
      ORDER BY error_stratum""")
    checks = {
        "domain ids not in organisations": "SELECT count(*) FROM organisation_domains_full WHERE organisation_id NOT IN "
                                           "(SELECT organisation_id FROM organisations)",
        "domains without p_error": "SELECT count(*) FROM organisation_domains_full WHERE p_error IS NULL",
        "repeated domains": "SELECT count(*) - count(DISTINCT domain) FROM organisation_domains_full",
        "independent rows in the public table": "SELECT count(*) FROM organisation_domains "
                                                f"WHERE organisation_id = '{UNMATCHED_REAL}'",
        "repeated organisations": "SELECT count(*) - count(DISTINCT organisation_id) FROM organisations",
        "repeated projects": "SELECT count(*) - count(DISTINCT project) FROM project_organisations",
        "unknown namespace relations": "SELECT count(*) FROM organisation_namespaces WHERE relation NOT IN "
                                       f"({', '.join(repr(r) for r in NS_RELATIONS)})",
        "namespace rows of unknown organisations": "SELECT count(*) FROM organisation_namespaces WHERE "
            "organisation_id NOT IN (SELECT organisation_id FROM organisations)",
        "namespace ids not in organisations": "SELECT count(*) FROM project_organisations WHERE "
            "firm_based_on_namespace NOT IN (SELECT organisation_id FROM organisations)",
        "pseudo ids missing": "SELECT 3 - count(*) FROM organisations WHERE organisation_id IN "
                              f"('free-provider', '{UNMATCHED_REAL}', '{NO_REAL_DOMAIN}')",
        "linked domains not in the strata": "SELECT (SELECT count(*) FROM organisation_domains_full) - "
            "(SELECT sum(links) FROM link_error WHERE links IS NOT NULL)",
    }
    for what, sql in checks.items():
        n = con.execute(sql).fetchone()[0]
        if n:
            raise RuntimeError(f"{what}: {n}")
    info = {"organisations_version": lj["organisations_version"], "ctp_schema_version": CTP_SCHEMA_VERSION,
            "mapping_sha256": mapping_sha256_of_files(con, links / "domain_links.parquet",
                                                      links / "project_links.parquet"),
            "fallback_real_domain_with_no_row": UNMATCHED_REAL, "fallback_no_real_domain": NO_REAL_DOMAIN,
            "domain_key": DOMAIN_KEY.format(c="person_domain"),
            "organisations_db_sha256": sha256(db), "links_json_sha256": sha256(links / "links.json"),
            "p_error_sha256": sha256(em / "organisation_domains_p_error.parquet"),
            "link_error_source_sha256": sha256(em / "link_error.parquet")}
    if info["mapping_sha256"] != lj["mapping_sha256"]:
        raise RuntimeError("the mapping hash of the link files is not the one in links.json")
    res = {}
    for t in TABLES[:-1]:
        no_at(con, t)
        copy(con, t, out / f"{t}.parquet")
        res[t] = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        info[f"{t}_rows"] = str(res[t])
        info[f"{t}_sha256"] = sha256(out / f"{t}.parquet")
    no_at(con, "organisation_domains_full")
    copy(con, "organisation_domains_full", private_out / "organisation_domains.full.parquet")
    res["organisation_domains_full (private)"] = con.execute("SELECT count(*) FROM organisation_domains_full").fetchone()[0]
    con.execute("CREATE TABLE release_info (key VARCHAR, value VARCHAR)")
    con.executemany("INSERT INTO release_info VALUES (?, ?)", sorted(info.items()))
    no_at(con, "release_info")
    copy(con, "release_info ORDER BY key", out / "release_info.parquet")
    con.close()
    return {"rows": res, "release_info": info}


def view_sql(projects_glob: str) -> list[str]:
    """Views with paths relative to the release root (DuckDB resolves them against the working folder)."""
    org = "organisations"
    project_of = r"regexp_extract(t.filename, '([^/]+)-dataset\.parquet$', 1)"
    key = DOMAIN_KEY.format(c="t.person_domain")
    sql = [f"CREATE VIEW {t} AS SELECT * FROM '{org}/{t}.parquet'" for t in TABLES]
    sql.append(f"CREATE VIEW tokens AS SELECT * FROM read_parquet('{projects_glob}', filename = true)")
    sql.append(f"""CREATE VIEW tokens_with_organisations AS
      SELECT t.*, {project_of} AS project, od.kind AS domain_organisation_kind,
             od.is_company AS domain_organisation_is_company, ons.kind AS namespace_organisation_kind
      FROM tokens t
      LEFT JOIN organisations od ON od.organisation_id = t.firm_based_on_domain
      LEFT JOIN organisations ons ON ons.organisation_id = t.firm_based_on_namespace""")
    sql.append(f"""CREATE VIEW tokens_with_current_organisations AS
      SELECT t.* EXCLUDE (firm_based_on_domain, firm_based_on_namespace), {project_of} AS project,
             coalesce(d.organisation_id, CASE WHEN {real_domain_sql(key)} THEN '{UNMATCHED_REAL}'
                                             ELSE '{NO_REAL_DOMAIN}' END) AS firm_based_on_domain,
             p.firm_based_on_namespace, d.error_stratum, d.p_error
      FROM tokens t
      LEFT JOIN organisation_domains d ON d.domain = {key}
      LEFT JOIN project_organisations p ON p.project = {project_of}""")
    sql.append("""CREATE VIEW project_hosts AS
      SELECT p.project, n.organisation_id AS hosted_by, o.name AS hosted_by_name, o.kind AS hosted_by_kind
      FROM project_organisations p
      JOIN organisation_namespaces n ON n.host = p.host AND lower(n.namespace) = lower(p.namespace)
      LEFT JOIN organisations o ON o.organisation_id = n.organisation_id
      WHERE n.relation = 'hosted_by'""")
    sql.append("""CREATE VIEW project_sponsors AS
      SELECT p.project, n.organisation_id AS sponsored_by, o.name AS sponsored_by_name,
             o.kind AS sponsored_by_kind
      FROM project_organisations p
      JOIN organisation_namespaces n ON n.host = p.host AND lower(n.namespace) = lower(p.namespace)
      LEFT JOIN organisations o ON o.organisation_id = n.organisation_id
      WHERE n.relation = 'sponsored_by'""")
    sql.append(f"""CREATE VIEW stale_files AS
      SELECT file_name, decode(value) AS file_mapping_sha256,
             (SELECT value FROM release_info WHERE key = 'mapping_sha256') AS release_mapping_sha256
      FROM parquet_kv_metadata('{projects_glob}')
      WHERE decode(key) = 'organisations_mapping_sha256'
        AND decode(value) <> (SELECT value FROM release_info WHERE key = 'mapping_sha256')""")
    return sql


def step_views(root: Path, projects_glob: str) -> list[str]:
    root = root.resolve()
    dst = root / "organisations" / "dataset.duckdb"
    for t in TABLES:
        if not (root / "organisations" / f"{t}.parquet").is_file():
            raise RuntimeError(f"{root}/organisations/{t}.parquet is missing")
    tmp = dst.with_name(".dataset.duckdb.tmp")
    tmp.unlink(missing_ok=True)
    os.chdir(root)
    con = duckdb.connect(str(tmp))
    for s in view_sql(projects_glob):
        con.execute(s)
    names = [r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal ORDER BY 1").fetchall()]
    con.close()
    os.replace(tmp, dst)
    return names


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="step", required=True)
    t = sub.add_parser("tables")
    t.add_argument("--links", type=Path, required=True)
    t.add_argument("--out", type=Path, required=True)
    t.add_argument("--private-out", type=Path, required=True,
                   help="a folder outside the release for organisation_domains.full.parquet")
    t.add_argument("--db", type=Path, default=COMP / "companies.v4.duckdb")
    t.add_argument("--error-model", type=Path, default=COMP / "error-model")
    v = sub.add_parser("views")
    v.add_argument("--root", type=Path, required=True)
    v.add_argument("--projects-glob", default="parquet/*.parquet")
    a = ap.parse_args(argv)
    if a.step == "tables":
        for f in (a.db, a.links / "links.json", a.error_model / "organisation_domains_p_error.parquet"):
            if not f.is_file():
                print(f"usage: {f} is not a file", file=sys.stderr)
                return 2
        print(json.dumps(step_tables(a.db, a.links, a.error_model, a.out, a.private_out), indent=1))
    else:
        print(json.dumps(step_views(a.root, a.projects_glob)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
