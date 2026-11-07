#!/usr/bin/env python3
"""Build the two link tables that build_v0.py reads (S8, 2026-10-16; organisation columns 2026-10-19).

    build_links.py --organisations-version V [--db companies.v4.duckdb] [--cache DIR ...]
                   [--sidecar project_meta.v1.final.json ...] [--out DIR] [--memory-limit 3GB] [--threads 2]

--cache and --sidecar can repeat (2026-10-23): v1 and the extension in one run give one mapping
hash for all files. A project must be in one cache folder and in one sidecar only. With one cache
and one sidecar, links.json is as before; with more, inputs.sidecar_sha256 is a list and
inputs lists the folders and the sidecars.

Inputs: the company database (build_companies.py, build_companies_v4.py), the per-project domain
cache (extract_domains_v1.py; this script reads its columns project, domain, email, tokens and
commits; no output holds an address) and the S7 sidecar (clone_url and owner of each project).

Output (DIR is ~/Projects/cregit-workspace/companies/links by default):
  domain_links.parquet   one row per dataset e-mail domain that matches a company_domain row (or
                         the free-provider rule): domain, firm_based_on_domain (the organisation
                         id; the pseudo ids free-provider, independent and pre-git-import are ids
                         too), organisation_kind, match (exact, suffix, rule), matched_domain,
                         confidence, source
  project_links.parquet  one row per project: project, host, namespace, firm_based_on_namespace
                         (the organisation with relation `owns`, else NULL; the user, 2026-10-19),
                         project_enterprise_driven, project_enterprise_basis
  enterprise_audit.parquet  per project: the numbers behind the three heuristics. This file is an
                         analysis for the replication package. It is not a dataset column (D3).
  links.json             counts, organisations_version, mapping_sha256 (build_v0.mapping_sha256)
                         and the sha256 of each output

The columns of LINK_COLUMNS_DESIGN.md section 2 (approved 2026-10-19). build_v0.py writes them
into the files. A dataset value with no row here gets a fallback value there (build_v0.py):
`independent` for a real domain (not blank, a dot, no at sign), `unknown` for the others.

Domain rule: the exact domain first. Else the longest parent domain (cut at a dot, at least one
dot left) that is in company_domain ("suffix"). A free-provider domain is never the author's
company: its value is the pseudo id free-provider. A company whose review_status is 'rejected'
does not match.
Three more rules (the trial of 2026-10-16 found the errors):
  - an academic or government domain (EDU_GOV_SQL: .edu, .gov, .mil, ac.XX, edu.XX, gov.XX)
    never matches a company or consultancy row. Such rows are developer affiliations of gitdm
    (berkeley.edu -> Microsoft), not domain owners;
  - a suffix match needs a row with a confidence other than single-developer (*.tum.de must not
    get commercetools from one developer);
  - a pseudo organisation (kind independent or free-provider) gives its pseudo id;
  - a dataset value with '@' is not a domain (some person_domain values are whole e-mail
    addresses, for example GitHub noreply addresses, or git-svn ids). It gets no link, so no
    output holds an address. The script stops if an output value holds '@'.

Namespace rule: (host, lower(namespace)) of the clone URL against company_namespace, relation
`owns` only (the user, 2026-10-19). If several owns rows match: verified first, then company_id.
Since v4.3 an owns row names the organisation that controls the account; a foundation that only
hosts a project there has the relation hosted_by, which gives no value (the user, 2026-10-19).

Enterprise heuristics: our versions, with the names of Spinellis et al. (MSR 2020). An author is
one e-mail address. An author's company is the company of the author's e-mail domain (kind
company or consultancy). For one company C:
  sdtc  at least SDTC_MIN of the SDTC_TOP authors with the most tokens have company C;
  mcpc  C has a strong kind_basis (STRONG_BASIS), at least MC_AUTHORS authors, and at least
        MC_COMMIT_SHARE of the project's commits;
  mcve  C (any basis) has at least MC_AUTHORS authors and at least MC_COMMIT_SHARE of the commits.
project_enterprise_driven is true when one heuristic holds; project_enterprise_basis lists them.
The thresholds are ours. They are not the thresholds of the 2020 paper.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_v0 import NO_REAL_DOMAIN, UNMATCHED_REAL, mapping_sha256, real_domain_sql  # noqa: E402

HOME = Path.home()
COMP = HOME / "Projects/cregit-workspace/companies"
DS = HOME / "STUDY-REPOSITORY/dataset-selection"

COMPANY_KINDS = ("company", "consultancy")
STRONG_BASIS = ("sec-filer", "fortune-global-500", "registry-id", "wikidata-instance-of")
SDTC_TOP, SDTC_MIN = 3, 2
MC_AUTHORS, MC_COMMIT_SHARE = 2, 0.10
# GitHub's hidden e-mail addresses: the user is not a GitHub employee.
FREE_SUFFIXES = ("users.noreply.github.com", "noreply.github.com")
PSEUDO_KINDS = ("free-provider", "independent")
EDU_GOV_SQL = r"regexp_matches({d}, '(^|\.)(edu|gov|mil)$|\.(ac|edu|gov|mil)\.[a-z]{{2}}$')"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def as_list(x) -> list[Path]:
    return [Path(p) for p in x] if isinstance(x, (list, tuple)) else [Path(x)]


def read_sidecars(sidecars) -> dict:
    """The union of the sidecars. A project in two sidecars stops the run."""
    meta: dict = {}
    for sc in as_list(sidecars):
        m = json.loads(sc.read_text())
        both = sorted(set(meta) & set(m))
        if both:
            raise RuntimeError(f"{len(both)} projects are in more than one sidecar, for example {both[0]}")
        meta.update(m)
    return meta


def cache_globs(caches) -> list[str]:
    """One glob per cache folder. A project file in two folders stops the run (double tokens)."""
    seen: dict[str, Path] = {}
    for c in as_list(caches):
        for f in c.glob("*.parquet"):
            if f.name in seen:
                raise RuntimeError(f"{f.name} is in {seen[f.name]} and in {c}")
            seen[f.name] = c
    return [f"{c}/*.parquet" for c in as_list(caches)]


def namespaces(sidecar) -> list[tuple[str, str, str]]:
    rows = []
    for project, m in sorted(read_sidecars(sidecar).items()):
        host = urlsplit(m.get("clone_url", "")).netloc.lower()
        rows.append((project, host, (m.get("owner") or "").strip()))
    return rows


def namespace_links(con, sidecar) -> None:
    """Temp tables ns (project, host, namespace) and nl (project, company_id): the namespace column.
    Needs the attached database `c` and the temp table `org` (the organisations that can match).
    firm_based_on_namespace: the owns rows only (the user, 2026-10-19). A hosted_by row (v4.3: a
    foundation that hosts a project of the namespace) never gives the column."""
    con.execute("CREATE TEMP TABLE ns (project VARCHAR, host VARCHAR, namespace VARCHAR)")
    con.executemany("INSERT INTO ns VALUES (?, ?, ?)", namespaces(sidecar))
    con.execute("""
      CREATE TEMP TABLE nl AS
      SELECT project, company_id FROM (
        SELECT ns.project, o.company_id,
               row_number() OVER (PARTITION BY ns.project ORDER BY
                 coalesce(n.verified, false) DESC, o.company_id) AS r
        FROM ns JOIN c.company_namespace n ON n.host = ns.host AND lower(n.namespace) = lower(ns.namespace)
        JOIN org o ON o.company_id = n.company_id
        WHERE n.relation = 'owns') WHERE r = 1""")


def copy(con, sql: str, dst: Path) -> None:
    tmp = dst.with_name(f".{dst.name}.tmp")
    con.execute(f"COPY ({sql}) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    os.replace(tmp, dst)


def build(db: Path, cache, sidecar, out: Path, memory_limit: str, threads: int,
          version: str = "test") -> dict:
    """cache: a folder or a list of folders; sidecar: a file or a list of files."""
    out.mkdir(parents=True, exist_ok=True)
    globs = cache_globs(cache)
    read_sidecars(sidecar)  # stops early on a repeated project
    con = duckdb.connect(config={"memory_limit": memory_limit, "threads": threads})
    con.execute(f"ATTACH '{db}' AS c (READ_ONLY)")
    con.execute("CREATE TEMP VIEW a AS SELECT * FROM read_parquet([{}])"
                .format(", ".join(f"'{g}'" for g in globs)))
    kinds = ", ".join(f"'{k}'" for k in COMPANY_KINDS)
    # The organisations that can match: not rejected.
    con.execute("CREATE TEMP TABLE org AS SELECT company_id, name, kind, kind_basis, review_status "
                "FROM c.company WHERE review_status <> 'rejected'")
    edu = EDU_GOV_SQL.format(d="d.domain")
    con.execute(f"CREATE TEMP TABLE cd AS SELECT d.domain, d.company_id, d.confidence FROM c.company_domain d "
                f"JOIN org USING (company_id) WHERE NOT ({edu} AND org.kind IN ({kinds}))")
    # Every dataset domain, and each of its parent domains with at least one dot. A domain that the
    # review dropped (v4 table company_domain_dropped) matches no organisation, not even by a suffix.
    has_dropped = con.execute("SELECT count(*) FROM duckdb_tables() WHERE database_name = 'c' "
                              "AND table_name = 'company_domain_dropped'").fetchone()[0]
    not_dropped = " AND domain NOT IN (SELECT domain FROM c.company_domain_dropped)" if has_dropped else ""
    con.execute("CREATE TEMP TABLE dom AS SELECT DISTINCT domain FROM a "
                f"WHERE domain <> '' AND domain LIKE '%.%' AND domain NOT LIKE '%@%'{not_dropped}")
    con.execute("""
      CREATE TEMP TABLE cand AS
      SELECT dom.domain, p.k AS cut, array_to_string(list_slice(string_split(dom.domain, '.'), p.k + 1,
             len(string_split(dom.domain, '.'))), '.') AS parent
      FROM dom, LATERAL (SELECT unnest(range(0, len(string_split(dom.domain, '.')) - 1)) AS k) p""")
    con.execute("""
      CREATE TEMP TABLE dl AS
      SELECT domain, company_id, confidence, matched_domain, match FROM (
        SELECT cand.domain, cd.company_id, cd.confidence, cand.parent AS matched_domain,
               CASE WHEN cand.cut = 0 THEN 'exact' ELSE 'suffix' END AS match,
               row_number() OVER (PARTITION BY cand.domain ORDER BY cand.cut) AS r
        FROM cand JOIN cd ON cd.domain = cand.parent
        WHERE cand.cut = 0 OR cd.confidence <> 'single-developer') WHERE r = 1""")
    free = " OR ".join(f"dl.domain = '{s}' OR dl.domain LIKE '%.{s}'" for s in FREE_SUFFIXES)
    # The first source of the matched row (v4 databases; older ones have no source column).
    has_source = con.execute("SELECT count(*) FROM duckdb_columns() WHERE database_name = 'c' AND "
                             "table_name = 'company_domain' AND column_name = 'source'").fetchone()[0]
    source = "src.source" if has_source else "NULL::VARCHAR"
    pkinds = ", ".join(repr(k) for k in PSEUDO_KINDS)
    con.execute(f"""
      CREATE TEMP TABLE domain_links AS
      SELECT dl.domain,
             CASE WHEN {free} THEN 'free-provider' WHEN o.kind IN ({pkinds}) THEN o.kind
                  ELSE o.company_id END AS firm_based_on_domain,
             CASE WHEN {free} THEN 'free-provider' ELSE o.kind END AS organisation_kind,
             dl.match, dl.matched_domain, dl.confidence, {source} AS source
      FROM dl JOIN org o USING (company_id)
      LEFT JOIN c.company_domain src ON src.domain = dl.matched_domain""")
    # Domains like users.noreply.github.com that no company_domain row holds.
    con.execute(f"""
      INSERT INTO domain_links SELECT domain, 'free-provider', 'free-provider', 'rule', domain, 'rule', 'rule'
      FROM dom dl WHERE ({free}) AND domain NOT IN (SELECT domain FROM domain_links)""")
    if con.execute("SELECT count(*) - count(DISTINCT domain) FROM domain_links").fetchone()[0]:
        raise RuntimeError("a domain repeats in domain_links")
    if con.execute("SELECT count(*) FROM domain_links WHERE firm_based_on_domain IS NULL "
                   "OR firm_based_on_domain NOT IN (SELECT company_id FROM org)").fetchone()[0]:
        raise RuntimeError("a domain_links id is NULL or not an organisation of the database")
    if con.execute("SELECT count(*) FROM domain_links WHERE concat_ws('|', domain, firm_based_on_domain, "
                   "matched_domain, source) LIKE '%@%'").fetchone()[0]:
        raise RuntimeError("a domain_links value holds '@'")
    copy(con, "SELECT * FROM domain_links ORDER BY domain", out / "domain_links.parquet")

    namespace_links(con, sidecar)

    # Per author (e-mail) and project: tokens, commits, company.
    con.execute(f"""
      CREATE TEMP TABLE au AS
      SELECT a.project, a.email, sum(a.tokens) AS tokens, sum(a.commits) AS commits,
             any_value(CASE WHEN l.organisation_kind IN ({kinds}) THEN l.firm_based_on_domain END) AS cid
      FROM a LEFT JOIN domain_links l ON l.domain = a.domain
      GROUP BY a.project, a.email""")
    strong = " OR ".join(f"contains(coalesce(o.kind_basis, ''), '{b}')" for b in STRONG_BASIS)
    con.execute(f"""
      CREATE TEMP TABLE pc AS
      WITH tot AS (SELECT project, sum(commits) AS commits, count(*) AS authors FROM au GROUP BY project),
      top AS (SELECT project, cid FROM (SELECT project, cid, row_number() OVER
                (PARTITION BY project ORDER BY tokens DESC, email) AS r FROM au) WHERE r <= {SDTC_TOP}),
      topc AS (SELECT project, cid, count(*) AS n FROM top WHERE cid IS NOT NULL GROUP BY ALL),
      byc AS (SELECT project, cid, count(*) AS authors, sum(commits) AS commits, sum(tokens) AS tokens
              FROM au WHERE cid IS NOT NULL GROUP BY ALL)
      SELECT byc.project, byc.cid, byc.authors, byc.commits, byc.tokens,
             byc.commits / nullif(tot.commits, 0) AS commit_share, coalesce(topc.n, 0) AS top_n,
             ({strong}) AS strong
      FROM byc JOIN tot USING (project) JOIN org o ON o.company_id = byc.cid
      LEFT JOIN topc ON topc.project = byc.project AND topc.cid = byc.cid""")
    con.execute(f"""
      CREATE TEMP TABLE ent AS
      SELECT project,
             bool_or(top_n >= {SDTC_MIN}) AS sdtc,
             bool_or(strong AND authors >= {MC_AUTHORS} AND commit_share >= {MC_COMMIT_SHARE}) AS mcpc,
             bool_or(authors >= {MC_AUTHORS} AND commit_share >= {MC_COMMIT_SHARE}) AS mcve,
             arg_max(cid, commits) AS top_company_id, max(commit_share) AS top_company_commit_share
      FROM pc GROUP BY project""")
    copy(con, """
      SELECT ns.project, ns.host, ns.namespace, nl.company_id AS firm_based_on_namespace,
             coalesce(e.sdtc OR e.mcpc OR e.mcve, false) AS project_enterprise_driven,
             nullif(concat_ws(',', CASE WHEN e.sdtc THEN 'sdtc' END, CASE WHEN e.mcpc THEN 'mcpc' END,
                              CASE WHEN e.mcve THEN 'mcve' END), '') AS project_enterprise_basis
      FROM ns LEFT JOIN nl USING (project) LEFT JOIN ent e USING (project) ORDER BY ns.project""",
         out / "project_links.parquet")
    copy(con, "SELECT * FROM pc ORDER BY project, commits DESC, cid", out / "enterprise_audit.parquet")

    pl = f"read_parquet('{out}/project_links.parquet')"
    # Every dataset token with its value of firm_based_on_domain, as build_v0.py writes it.
    real = real_domain_sql("a.domain")
    con.execute(f"""
      CREATE TEMP TABLE tv AS
      SELECT a.tokens,
             coalesce(l.firm_based_on_domain,
                      CASE WHEN {real} THEN '{UNMATCHED_REAL}' ELSE '{NO_REAL_DOMAIN}' END) AS v,
             CASE WHEN l.domain IS NOT NULL THEN 'linked'
                  WHEN {real} THEN 'unmatched real domain' ELSE 'no real domain' END AS why,
             coalesce(l.organisation_kind, CASE WHEN {real} THEN 'independent' ELSE 'unknown' END) AS kind
      FROM a LEFT JOIN domain_links l ON l.domain = a.domain""")
    total = con.execute("SELECT sum(tokens) FROM tv").fetchone()[0]

    def shares(sql):
        return {k: v / total for k, v in con.execute(sql).fetchall()}
    mapping = mapping_sha256(
        con.execute("SELECT domain, firm_based_on_domain FROM domain_links").fetchall(),
        con.execute(f"SELECT project, firm_based_on_namespace FROM {pl}").fetchall())
    s = {
        "dataset_domains": con.execute("SELECT count(*) FROM dom").fetchone()[0],
        "domain_links": con.execute("SELECT count(*) FROM domain_links").fetchone()[0],
        "domain_links_by_match": dict(con.execute("SELECT match, count(*) FROM domain_links GROUP BY 1 ORDER BY 1").fetchall()),
        "domain_links_by_kind": dict(con.execute("SELECT organisation_kind, count(*) FROM domain_links GROUP BY 1 ORDER BY 1").fetchall()),
        "projects": con.execute(f"SELECT count(*) FROM {pl}").fetchone()[0],
        "projects_with_namespace_owner": con.execute(f"SELECT count(firm_based_on_namespace) FROM {pl}").fetchone()[0],
        "projects_by_namespace_owner_kind": dict(con.execute(
            f"SELECT coalesce(o.kind, '(no owner)'), count(*) FROM {pl} p LEFT JOIN org o "
            "ON o.company_id = p.firm_based_on_namespace GROUP BY 1 ORDER BY 1").fetchall()),
        "projects_enterprise_driven": con.execute(f"SELECT count(*) FILTER (WHERE project_enterprise_driven) FROM {pl}").fetchone()[0],
        "projects_by_basis": dict(con.execute(f"SELECT coalesce(project_enterprise_basis, '-'), count(*) FROM {pl} GROUP BY 1 ORDER BY 1").fetchall()),
        "total_tokens": total,
        "token_share_by_kind": shares("SELECT kind, sum(tokens) FROM tv GROUP BY 1 ORDER BY 2 DESC"),
        "token_share_by_value_class": shares("SELECT CASE WHEN v IN ('free-provider', 'independent', 'unknown') "
                                             "THEN v ELSE 'organisation' END, sum(tokens) FROM tv GROUP BY 1 ORDER BY 1"),
        "token_share_by_reason": shares("SELECT v || ' / ' || why, sum(tokens) FROM tv "
                                        "WHERE v IN ('independent', 'unknown') GROUP BY 1 ORDER BY 1"),
        "token_share_company_kind": shares(f"SELECT 'company_kind', sum(tokens) FROM tv WHERE kind IN ({kinds})")
                                    .get("company_kind", 0.0),
        "organisations_version": version,
        "mapping_sha256": mapping,
        "fallback": {"unmatched_real_domain": UNMATCHED_REAL, "no_real_domain": NO_REAL_DOMAIN},
        "thresholds": {"SDTC_TOP": SDTC_TOP, "SDTC_MIN": SDTC_MIN, "MC_AUTHORS": MC_AUTHORS,
                       "MC_COMMIT_SHARE": MC_COMMIT_SHARE, "STRONG_BASIS": list(STRONG_BASIS)},
        "inputs": {"db": str(db), "db_sha256": sha256(db), "sidecar_sha256": sha256(as_list(sidecar)[0])},
    }
    if len(as_list(sidecar)) > 1 or len(as_list(cache)) > 1:
        s["inputs"]["sidecar_sha256"] = [sha256(p) for p in as_list(sidecar)]
        s["inputs"]["sidecars"] = [str(p) for p in as_list(sidecar)]
        s["inputs"]["caches"] = [str(p) for p in as_list(cache)]
    con.close()
    s["outputs"] = {f: sha256(out / f) for f in ("domain_links.parquet", "project_links.parquet",
                                                  "enterprise_audit.parquet")}
    tmp = out / ".links.json.tmp"
    tmp.write_text(json.dumps(s, indent=1, sort_keys=True, default=float) + "\n")
    os.replace(tmp, out / "links.json")
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--organisations-version", required=True, help="the database version, for example v4.1")
    ap.add_argument("--db", type=Path, default=COMP / "companies.v4.duckdb")
    ap.add_argument("--cache", type=Path, action="append", help=f"repeatable (default {COMP / 'cache'})")
    ap.add_argument("--sidecar", type=Path, action="append",
                    help=f"repeatable (default {DS / 's7-run/project_meta.v1.final.json'})")
    ap.add_argument("--out", type=Path, default=COMP / "links")
    ap.add_argument("--memory-limit", default="3GB")
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args(argv)
    a.cache = a.cache or [COMP / "cache"]
    a.sidecar = a.sidecar or [DS / "s7-run/project_meta.v1.final.json"]
    for f in (a.db, *a.sidecar):
        if not f.is_file():
            print(f"usage: {f} is not a file", file=sys.stderr)
            return 2
    for d in a.cache:
        if not d.is_dir():
            print(f"usage: {d} is not a folder", file=sys.stderr)
            return 2
    s = build(a.db, a.cache, a.sidecar, a.out, a.memory_limit, a.threads, a.organisations_version)
    print(json.dumps({k: v for k, v in s.items() if k not in ("inputs", "outputs")}, indent=1, default=float))
    return 0


if __name__ == "__main__":
    sys.exit(main())
