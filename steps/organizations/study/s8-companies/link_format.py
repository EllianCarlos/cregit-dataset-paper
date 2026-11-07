#!/usr/bin/env python3
"""Read a link folder of build_links.py in the old or the new column format (S8, 2026-10-20).

The link folders before 2026-10-19 (links/, links-v4/, v4.0-20261018/links-v4/) have the v0 column
names: domain_company_id, domain_company_kind, domain_company_confidence; namespace_company_id,
namespace_company_relation, namespace_company_evidence (the best namespace row: owns, then
participates, then candidate). The folders since 2026-10-19 (links-v4.1/, links-v4.5/, links-v4.6/) have the
names of LINK_COLUMNS_DESIGN.md section 2: firm_based_on_domain, organisation_kind, confidence,
source; firm_based_on_namespace (the `owns` organisation only).

The readers (error_model.py, link_shares.py, make_review.py, review/make_review_items.py,
review/audit_sample.py, side/employer_model.py) use the new names. These two functions give a SQL
query with the new names for a folder of either format:

  domain_links_sql(con, path)  domain, firm_based_on_domain, organisation_kind, match, matched_domain,
                               confidence, source. Old format: firm_based_on_domain is
                               coalesce(domain_company_id, domain_company_kind) (a pseudo id has no
                               id in the old files, only the kind); source is NULL.
  project_links_sql(con, path, db=None)
                               project, host, namespace, firm_based_on_namespace,
                               namespace_organisation_id, namespace_relation, namespace_evidence,
                               project_enterprise_driven, project_enterprise_basis.
                               firm_based_on_namespace: the `owns` organisation, else NULL (both
                               formats). namespace_organisation_id, namespace_relation and
                               namespace_evidence: the best namespace row in the old order (owns,
                               participates, candidate; then verified; then the id). The new files
                               do not hold them, so they come from the company_namespace table of
                               the attached database `db` (the organisations that are not rejected,
                               as in build_links.py); with no `db`, they repeat the owns value.
                               hosted_by and sponsored_by rows never count: they do not say who
                               controls the account.
"""
from __future__ import annotations

from pathlib import Path

NEW_DOMAIN_COLS = ("domain", "firm_based_on_domain", "organisation_kind", "match", "matched_domain",
                   "confidence", "source")
NEW_PROJECT_COLS = ("project", "host", "namespace", "firm_based_on_namespace", "namespace_organisation_id",
                    "namespace_relation", "namespace_evidence", "project_enterprise_driven",
                    "project_enterprise_basis")
# The relations that can be the best namespace row (the order of build_links.py before 2026-10-19).
BEST_RELATIONS = ("owns", "participates", "candidate")


def _lit(path: Path | str) -> str:
    return "'" + str(path).replace("'", "''") + "'"


def _columns(con, path: Path | str) -> list[str]:
    return [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({_lit(path)})").fetchall()]


def is_new_format(con, path: Path | str) -> bool:
    """True for a file with the column names of 2026-10-19 (domain or project links)."""
    cols = set(_columns(con, path))
    if "firm_based_on_domain" in cols or "firm_based_on_namespace" in cols:
        return True
    if "domain_company_id" in cols or "namespace_company_id" in cols:
        return False
    raise ValueError(f"{path}: not a link file of build_links.py")


def domain_links_sql(con, path: Path | str) -> str:
    """SQL: the domain links of `path` with the new column names (NEW_DOMAIN_COLS)."""
    src = f"read_parquet({_lit(path)})"
    if is_new_format(con, path):
        return f"SELECT {', '.join(NEW_DOMAIN_COLS)} FROM {src}"
    return ("SELECT domain, coalesce(domain_company_id, domain_company_kind) AS firm_based_on_domain, "
            "domain_company_kind AS organisation_kind, match, matched_domain, "
            f"domain_company_confidence AS confidence, NULL::VARCHAR AS source FROM {src}")


def project_links_sql(con, path: Path | str, db: str | None = None) -> str:
    """SQL: the project links of `path` with the new column names (NEW_PROJECT_COLS)."""
    src = f"read_parquet({_lit(path)})"
    if not is_new_format(con, path):
        return ("SELECT project, host, namespace, CASE WHEN namespace_company_relation = 'owns' "
                "THEN namespace_company_id END AS firm_based_on_namespace, "
                "namespace_company_id AS namespace_organisation_id, namespace_company_relation AS namespace_relation, "
                "namespace_company_evidence AS namespace_evidence, project_enterprise_driven, "
                f"project_enterprise_basis FROM {src}")
    if db is None:
        return ("SELECT project, host, namespace, firm_based_on_namespace, "
                "firm_based_on_namespace AS namespace_organisation_id, "
                "CASE WHEN firm_based_on_namespace IS NOT NULL THEN 'owns' END AS namespace_relation, "
                "NULL::VARCHAR AS namespace_evidence, project_enterprise_driven, project_enterprise_basis "
                f"FROM {src}")
    rel = ", ".join(f"'{r}'" for r in BEST_RELATIONS)
    order = " ".join(f"WHEN '{r}' THEN {i}" for i, r in enumerate(BEST_RELATIONS))
    return f"""
      SELECT p.project, p.host, p.namespace, p.firm_based_on_namespace,
             b.company_id AS namespace_organisation_id, b.relation AS namespace_relation,
             b.evidence AS namespace_evidence, p.project_enterprise_driven, p.project_enterprise_basis
      FROM {src} p LEFT JOIN (
        SELECT project, company_id, relation, evidence FROM (
          SELECT q.project, n.company_id, n.relation, n.evidence,
                 row_number() OVER (PARTITION BY q.project ORDER BY CASE n.relation {order} END,
                                    coalesce(n.verified, false) DESC, n.company_id) AS r
          FROM {src} q
          JOIN {db}.company_namespace n ON n.host = q.host AND lower(n.namespace) = lower(q.namespace)
          JOIN {db}.company o ON o.company_id = n.company_id
          WHERE n.relation IN ({rel}) AND o.review_status <> 'rejected') WHERE r = 1) b USING (project)"""


def check_owns_agree(con, sql: str) -> int:
    """The number of projects whose owns value is not the best namespace row (0 for a sound file)."""
    return con.execute(f"SELECT count(*) FROM ({sql}) WHERE firm_based_on_namespace IS NOT NULL AND "
                       "(namespace_relation IS DISTINCT FROM 'owns' OR "
                       "namespace_organisation_id IS DISTINCT FROM firm_based_on_namespace)").fetchone()[0]
