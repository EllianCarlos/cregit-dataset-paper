-- Fix 4 (language side table): tokei 14.0.0 at the pinned run_commit, from the finished measure
-- input/tokei-measure.jsonl (last final line per project).
-- Run with ../dw.sh (work.duckdb from ../00_base.sql). code_prog: programming code lines per tokei
-- language, with C Header merged into C and C++ Header into C++ (measure.py MERGE).
-- language_tokei_linguist: the same lines after the name map TSX->TypeScript, JSX->JavaScript,
-- GNU Style Assembly->Assembly, FORTRAN Modern->Fortran, summed per mapped name, then the largest
-- (ties: the first name in sort order, as in measure.py).
CREATE OR REPLACE MACRO to_linguist(x) AS CASE x
  WHEN 'TSX' THEN 'TypeScript' WHEN 'JSX' THEN 'JavaScript' WHEN 'GNU Style Assembly' THEN 'Assembly'
  WHEN 'FORTRAN Modern' THEN 'Fortran' ELSE x END;
CREATE OR REPLACE TABLE tkm AS
WITH j AS (
  SELECT row_number() OVER () AS ln, *
  FROM read_json('input/tokei-measure.jsonl', format='newline_delimited',
                 columns={project:'VARCHAR', status:'VARCHAR', final:'BOOLEAN', pinned_commit:'VARCHAR',
                          code_prog:'JSON', code_prog_total:'BIGINT', largest:'VARCHAR', largest_tied:'VARCHAR[]',
                          target_share:'DOUBLE', "rule":'BOOLEAN', measured_at:'VARCHAR', error:'VARCHAR'}))
SELECT * EXCLUDE (ln) FROM j QUALIFY row_number() OVER (PARTITION BY project ORDER BY final DESC, ln DESC) = 1;
CREATE OR REPLACE TABLE lang AS
WITH e AS (
  SELECT project, code_prog, unnest(json_keys(code_prog)) AS k FROM tkm WHERE status = 'ok'),
m AS (SELECT project, to_linguist(k) AS lname, sum(json_extract(code_prog, '$.' || to_json(k)::VARCHAR)::BIGINT) AS c
      FROM e GROUP BY ALL),
r AS (SELECT project, lname, c, max(c) OVER (PARTITION BY project) AS top FROM m),
ml AS (SELECT project, min(lname) FILTER (c = top) AS largest_mapped,
              sum(c) FILTER (lname IN ('C', 'C++', 'Java', 'Rust')) AS tgt, sum(c) AS allc
       FROM r GROUP BY project)
SELECT p.project, nullif(p.language, '') AS language,
       t.status AS tokei_status, t.pinned_commit = p.run_commit AS tokei_at_run_commit,
       t.largest AS language_tokei, ml.largest_mapped AS language_tokei_linguist,
       coalesce(t.largest_tied, []) AS largest_tied, t.target_share,
       coalesce(ml.tgt, 0)::DOUBLE / nullif(ml.allc, 0) AS target_share_check,
       t.code_prog_total AS code_lines_programming, CAST(t.code_prog AS VARCHAR) AS code_lines_json
FROM projects p LEFT JOIN tkm t USING (project) LEFT JOIN ml USING (project);
.print '== tokei status of the release projects'
SELECT coalesce(tokei_status, '(no line)') status, count(*) FROM lang GROUP BY 1 ORDER BY 2 DESC;
.print '== checks: commit, target_share recomputed from the lines, largest_tied consistent'
SELECT count(*) FILTER (tokei_status = 'ok') ok, count(*) FILTER (tokei_status = 'ok' AND tokei_at_run_commit) at_run_commit,
       count(*) FILTER (tokei_status = 'ok' AND abs(target_share - target_share_check) > 1e-5) share_mismatch,
       count(*) FILTER (tokei_status = 'ok' AND language_tokei IS NULL) ok_no_programming_code,
       count(*) FILTER (len(largest_tied) > 1) tied
FROM lang;
.print '== agreement with the host value where both exist (raw / Linguist names)'
SELECT count(*) both_exist, count(*) FILTER (language = language_tokei) agree_raw,
       round(100.0 * count(*) FILTER (language = language_tokei) / count(*), 1) pct_raw,
       count(*) FILTER (language = language_tokei_linguist) agree_mapped,
       round(100.0 * count(*) FILTER (language = language_tokei_linguist) / count(*), 1) pct_mapped
FROM lang WHERE language IS NOT NULL AND language_tokei IS NOT NULL;
.print '== the name map: projects whose largest language changes under the map'
SELECT language_tokei, language_tokei_linguist, count(*) n FROM lang
WHERE language_tokei IS DISTINCT FROM language_tokei_linguist AND tokei_status = 'ok' GROUP BY ALL ORDER BY n DESC;
.print '== FORTRAN Legacy as largest (not in the map)'
SELECT count(*) FROM lang WHERE language_tokei = 'FORTRAN Legacy';
.print '== keep rule (largest tokei language C, C++, Java or Rust)'
SELECT language_tokei IN ('C', 'C++', 'Java', 'Rust') AS keep, count(*) FROM lang WHERE tokei_status = 'ok' GROUP BY 1;
.print '== gaps: empty host language'
SELECT count(*) empty_language, count(*) FILTER (language_tokei_linguist IS NOT NULL) fillable,
       count(*) FILTER (tokei_status IS DISTINCT FROM 'ok') not_measured,
       count(*) FILTER (tokei_status = 'ok' AND language_tokei IS NULL) no_programming_code
FROM lang WHERE language IS NULL;
SELECT language_tokei_linguist proposed, count(*) n FROM lang WHERE language IS NULL AND language_tokei_linguist IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC;
COPY (SELECT project, language, language_tokei, language_tokei_linguist, largest_tied, target_share,
             code_lines_programming, code_lines_json, tokei_status FROM lang ORDER BY project)
  TO 'prepared/project_languages.parquet' (FORMAT parquet, COMPRESSION zstd);
COPY (SELECT l.project, p.host, p.run_commit, '' AS old_value, l.language_tokei_linguist AS proposed_value,
             l.language_tokei, array_to_string(l.largest_tied, ';') AS largest_tied, round(l.target_share, 6) AS target_share
      FROM lang l JOIN projects p USING (project)
      WHERE l.language IS NULL AND l.language_tokei_linguist IS NOT NULL ORDER BY p.host, l.project)
  TO 'prepared/language_fill_gaps.tsv' (HEADER, DELIMITER '\t');
