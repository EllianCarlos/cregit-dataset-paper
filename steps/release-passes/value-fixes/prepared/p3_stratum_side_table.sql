-- Fix 3 (stratum side table): the rule of build_labels.py (first match wins), run on the S5 facts of the
-- release `fact` column plus one added fact from the kind of the namespace owner
-- (firm_based_on_namespace -> organizations.kind). Run with ../dw.sh (work.duckdb from ../00_base.sql).
-- company only: company or consultancy give a company fact.
-- all kinds:    also foundation, fiscal-sponsor and government give a fact of that kind.
-- personal is decided from the facts (every fact is owner_kind:user), not from the release stratum, so the
-- check below is not circular.
CREATE OR REPLACE MACRO lab(gov, fnd, spo, com, usr) AS
  CASE WHEN gov THEN 'government'
       WHEN fnd AND com THEN 'contested'
       WHEN fnd THEN 'foundation'
       WHEN spo AND com THEN 'contested'
       WHEN spo THEN 'fiscal-sponsor'
       WHEN com THEN 'company'
       WHEN usr THEN 'personal' ELSE 'unknown' END;
CREATE OR REPLACE TABLE pl AS
WITH f AS (
  SELECT p.project, p.stratum, p.fact, p.firm_based_on_namespace AS owner_id, o.kind AS owner_kind,
         o.kind_basis, coalesce(o.kind, '') AS k,
         list_filter(string_split(coalesce(p.fact, ''), ';'), lambda x: x <> '') AS facts
  FROM projects p LEFT JOIN orgs o ON o.organization_id = p.firm_based_on_namespace),
g AS (
  SELECT *, list_transform(facts, lambda x: split_part(x, ':', 1)) AS ft FROM f),
h AS (
  SELECT *,
    list_has_any(ft, ['roster', 'roster_org']) AS fnd0,
    list_has_any(ft, ['company_pool', 'company_org', 'company_roster', 'company_roster_org']) AS com0,
    list_contains(ft, 'fiscal_sponsor') AS spo0,
    list_contains(ft, 'government') AS gov0,
    len(facts) > 0 AND list_bool_and(list_transform(facts, lambda x: lower(x) = 'owner_kind:user')) AS usr0,
    k IN ('company', 'consultancy') AS com1
  FROM g)
SELECT project, stratum,
  lab(gov0, fnd0, spo0, com0 OR com1, usr0) AS stratum_company_only,
  lab(gov0 OR k = 'government', fnd0 OR k = 'foundation', spo0 OR k = 'fiscal-sponsor', com0 OR com1, usr0)
    AS stratum_all_kinds,
  CASE WHEN com1 THEN 'namespace_owner:' || k END AS added_fact_company_only,
  CASE WHEN k IN ('company', 'consultancy', 'foundation', 'fiscal-sponsor', 'government')
       THEN 'namespace_owner:' || k END AS added_fact_all_kinds,
  owner_id AS namespace_owner, owner_kind AS namespace_owner_kind,
  CASE WHEN k IN ('company', 'consultancy', 'foundation', 'fiscal-sponsor', 'government')
       THEN 'firm_based_on_namespace=' || owner_id || ' -> organizations.kind=' || k
            || ' (kind_basis ' || coalesce(nullif(kind_basis, ''), 'none') || ')' END AS basis,
  lab(gov0, fnd0, spo0, com0, usr0) AS stratum_no_added_fact
FROM h;
.print '== validation: the rule with no added fact against the release value (all projects)'
SELECT count(*) projects, count(*) FILTER (stratum_no_added_fact = stratum) reproduced,
       count(*) FILTER (stratum_no_added_fact IS DISTINCT FROM stratum) mismatches FROM pl;
.print '== validation by release label'
SELECT stratum, count(*) n, count(*) FILTER (stratum_no_added_fact = stratum) reproduced FROM pl GROUP BY 1 ORDER BY 2 DESC;
.print '== changes, company only'
SELECT stratum AS old_label, stratum_company_only AS new_label, count(*) n FROM pl WHERE stratum <> stratum_company_only GROUP BY ALL ORDER BY n DESC;
.print '== changes, all kinds'
SELECT stratum AS old_label, stratum_all_kinds AS new_label, count(*) n FROM pl WHERE stratum <> stratum_all_kinds GROUP BY ALL ORDER BY n DESC;
.print '== totals'
SELECT l, count(*) FILTER (stratum = l) in_release, count(*) FILTER (stratum_company_only = l) company_only,
       count(*) FILTER (stratum_all_kinds = l) all_kinds
FROM pl, (VALUES ('government'), ('contested'), ('foundation'), ('fiscal-sponsor'), ('company'), ('personal'), ('unknown')) t(l)
GROUP BY l ORDER BY l;
.print '== changed files'
SELECT count(*) FILTER (stratum <> stratum_company_only) company_only, count(*) FILTER (stratum <> stratum_all_kinds) all_kinds FROM pl;
.print '== basis of the added fact (projects whose label changes, all kinds)'
SELECT namespace_owner_kind, coalesce(nullif(o.kind_basis, ''), '(none)') kind_basis, count(*) n
FROM pl LEFT JOIN orgs o ON o.organization_id = pl.namespace_owner
WHERE stratum <> stratum_all_kinds GROUP BY ALL ORDER BY n DESC;
COPY (SELECT project, stratum, stratum_company_only, stratum_all_kinds, added_fact_company_only, added_fact_all_kinds,
             namespace_owner, namespace_owner_kind, basis FROM pl ORDER BY project)
  TO 'prepared/project_labels.parquet' (FORMAT parquet, COMPRESSION zstd);
