"""Aggregate the Linux kernel file of the release to organization level.

Usage (from the duckdb-workbench nix shell):
    RELEASE_ROOT=<folder of the release files> nice -n 15 python3 -I extract_linux_orgs.py

Writes, next to this script, only organization-level counts (no person data):
    linux_org_day.csv   tokens and surviving commits per (committer day, author year,
                        organization, AMD register header flag, kernel.org address flag)
    linux_org_total.csv tokens per organization, whole file
"""
import os
import pathlib

import duckdb

root = pathlib.Path(os.environ["RELEASE_ROOT"])
out = pathlib.Path(__file__).resolve().parent
linux = root / "parquet" / "torvalds__linux-dataset.parquet"
orgs = root / "organizations" / "organizations.parquet"

con = duckdb.connect()
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=4")
con.execute(f"SET temp_directory='{os.environ.get('TMPDIR', '/tmp')}/linux-validation-duckdb'")

con.execute(f"""
CREATE TEMP TABLE agg AS
SELECT
    CAST(substr(t.committer_date, 1, 10) AS DATE) AS committer_day,
    CAST(substr(t.author_date, 1, 4) AS INTEGER) AS author_year,
    t.firm_based_on_domain AS organization_id,
    t.file_path LIKE 'drivers/gpu/drm/amd/include/asic_reg/%' AS amd_register_header,
    coalesce(t.person_domain = 'kernel.org', false) AS kernel_org_address,
    count(*) AS tokens,
    count(DISTINCT t.original_commit_sha) AS commits
FROM read_parquet('{linux}') AS t
WHERE t.is_structural = 0
GROUP BY ALL
""")

con.execute(f"""
COPY (
    SELECT a.*, o.name, o.kind, o.is_company, o.parent_company_id
    FROM agg AS a LEFT JOIN read_parquet('{orgs}') AS o USING (organization_id)
    ORDER BY committer_day, organization_id
) TO '{out / "linux_org_day.csv"}' (HEADER)
""")

con.execute(f"""
COPY (
    SELECT a.organization_id, o.name, o.kind, o.is_company, o.parent_company_id,
           sum(tokens) AS tokens,
           sum(tokens) FILTER (WHERE NOT amd_register_header) AS tokens_without_amd_register_headers
    FROM agg AS a LEFT JOIN read_parquet('{orgs}') AS o USING (organization_id)
    GROUP BY ALL ORDER BY tokens DESC
) TO '{out / "linux_org_total.csv"}' (HEADER)
""")

for row in con.execute("SELECT sum(tokens), sum(tokens) FILTER (WHERE amd_register_header) FROM agg").fetchall():
    print("code tokens:", row[0], " in AMD register headers:", row[1])
