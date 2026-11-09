-- Join the project files of Token on Me (TOM) with the organization database.
--
-- Run it from the release root, or from sample/data for the sample. Both folders hold
-- parquet/ and organizations/:
--   duckdb -readonly organizations/dataset.duckdb < ../queries/join-organizations.sql
--
-- Keys:
--   - A row (one token): (clone_url, file_path, token_index) is unique in the dataset.
--     In one project file, (file_path, token_index) is unique.
--   - A project: clone_url is the project key in the project files. The organization tables
--     use project, the file name without "-dataset.parquet". Do not join on repo_name: two
--     hosts can give the same repo_name.
--   - firm_based_on_namespace and firm_based_on_domain -> organizations.organization_id.
--     firm_based_on_namespace is NULL for an account of a person, so use a LEFT JOIN.
--     firm_based_on_domain can be one of the pseudo ids free-provider, independent and unknown;
--     organizations.parquet has a row for each of them.
--   - lower(trim(person_domain)) -> organization_domains.domain (the link of the domain).
--   - organization_domains.error_stratum -> link_error.error_stratum (the error of the link).

-- 1. The join. A query on all project files reads all of them (about 117 GB).
--    To test it, change parquet/*-dataset.parquet to one file, for example
--    parquet/google__guava-dataset.parquet.
CREATE OR REPLACE TEMP VIEW tokens_joined AS
WITH t AS (
    SELECT *,
           regexp_extract(filename, '([^/]+)-dataset\.parquet$', 1) AS project
    FROM read_parquet('parquet/*-dataset.parquet', filename = true)
)
SELECT t.project,
       t.clone_url,
       t.file_path,
       t.token_index,
       t.token_value,
       t.is_structural,
       t.original_commit_sha,
       t.author_date,
       t.personid,
       t.person_domain,
       t.firm_based_on_domain,
       od.name                     AS domain_organization,
       od.kind                     AS domain_organization_kind,
       d.match                     AS domain_match,
       d.source                    AS domain_link_source,
       d.p_error                   AS domain_link_p_error,
       e.estimate                  AS domain_link_error_estimate,
       t.firm_based_on_namespace,
       nso.name                    AS namespace_organization,
       nso.kind                    AS namespace_organization_kind,
       p.project_enterprise_driven,
       p.project_enterprise_basis
FROM t
LEFT JOIN 'organizations/organizations.parquet'          od  ON od.organization_id  = t.firm_based_on_domain
LEFT JOIN 'organizations/organizations.parquet'          nso ON nso.organization_id = t.firm_based_on_namespace
LEFT JOIN 'organizations/organization_domains.parquet'   d   ON d.domain            = lower(trim(t.person_domain))
LEFT JOIN 'organizations/link_error.parquet'             e   ON e.error_stratum     = d.error_stratum
LEFT JOIN 'organizations/project_organizations.parquet'  p   ON p.project           = t.project;

-- 2. An example: the code tokens of each project by the kind of the organization of the
--    author address.
SELECT project,
       domain_organization_kind,
       count(*) AS tokens
FROM tokens_joined
WHERE is_structural = 0
GROUP BY ALL
ORDER BY project, tokens DESC;

-- 3. The key checks. Each query must give 0 rows.
--    One clone_url for each project file:
SELECT project FROM tokens_joined GROUP BY project HAVING count(DISTINCT clone_url) <> 1;
--    The row key is unique:
SELECT clone_url, file_path, token_index
FROM tokens_joined
GROUP BY ALL
HAVING count(*) > 1;
