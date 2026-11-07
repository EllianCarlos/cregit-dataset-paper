-- One row per project: the project-level columns of the release (from the per-file stats of the
-- column review app) joined with the release MANIFEST.tsv (clone_url, pinned commit).
CREATE OR REPLACE TABLE pv AS
SELECT replace(file, '-dataset.parquet', '') AS project, "column" AS col, value
FROM read_parquet('input/project_values.parquet');
CREATE OR REPLACE TABLE m AS
SELECT * FROM read_csv('input/MANIFEST.tsv', delim='\t', header=true, all_varchar=true);
CREATE OR REPLACE TABLE projects AS
SELECT m.project, m.clone_url,
       lower(regexp_extract(m.clone_url, '^[a-z+]+://([^/]+)/', 1)) AS host,
       m.run_commit, m.commits, m.size_class,
       max(CASE WHEN col='stratum' THEN value END) AS stratum,
       max(CASE WHEN col='fact' THEN value END) AS fact,
       max(CASE WHEN col='contested' THEN value END) AS contested,
       max(CASE WHEN col='language' THEN value END) AS language,
       max(CASE WHEN col='license' THEN value END) AS license,
       max(CASE WHEN col='owner_type' THEN value END) AS owner_type,
       max(CASE WHEN col='firm_based_on_namespace' THEN value END) AS firm_based_on_namespace,
       max(CASE WHEN col='project_enterprise_driven' THEN value END) AS project_enterprise_driven,
       max(CASE WHEN col='project_enterprise_basis' THEN value END) AS project_enterprise_basis,
       max(CASE WHEN col='source' THEN value END) AS source
FROM m LEFT JOIN pv ON pv.project = m.project
GROUP BY ALL;
CREATE OR REPLACE TABLE orgs AS
SELECT * FROM read_parquet('input/organizations.parquet');
SELECT count(*) projects, count(stratum) with_stratum, count(*) FILTER (host='github.com') github,
       count(license) with_license FROM projects;
SELECT host, count(*) FROM projects GROUP BY 1 ORDER BY 2 DESC LIMIT 20;
