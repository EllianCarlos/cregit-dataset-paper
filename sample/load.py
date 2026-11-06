#!/usr/bin/env python3
"""Load the cregit token dataset (the sample or the full release) and run example queries.

Usage:
    python load.py                      # the sample in data/ next to this script
    python load.py --data PATH          # another root, for example the full release
    python load.py --project NAME       # the project of the per-project examples
    python load.py --duckdb             # also run the examples with DuckDB (optional)

The root (PATH) must hold parquet/<project>-dataset.parquet and organizations/*.parquet,
as the release root does. The script needs Python 3.10 or later, pandas and pyarrow. DuckDB
is optional.

The script prints only counts, shares, organization ids and pseudonyms. It never prints a
name, an address, a domain, a commit message or code text.
"""
from __future__ import annotations

import argparse
import collections
import os
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

HERE = os.path.dirname(os.path.abspath(__file__))
SUFFIX = "-dataset.parquet"
ORG_TABLES = ["organizations", "organization_domains", "organization_namespaces",
              "project_organizations", "link_error", "release_info"]
# The project columns have one value for each project. The first row gives it.
PROJECT_COLUMNS = ["clone_url", "language", "stratum", "commits", "license", "firm_based_on_namespace"]
BATCH = 1_000_000


def layer_of(commits: str) -> str:
    """The commit layer of the release, from the column `commits` (the count at the selection time)."""
    return "5,000 or more commits" if int(commits) >= 5000 else "1,000 to 4,999 commits"


def project_files(root: str, only: list[str] | None = None) -> list[str]:
    d = os.path.join(root, "parquet")
    names = sorted(n for n in os.listdir(d) if n.endswith(SUFFIX))
    if only:
        keep = set(only)
        names = [n for n in names if n[: -len(SUFFIX)] in keep]
    return [os.path.join(d, n) for n in names]


def load_projects(files: list[str]) -> pd.DataFrame:
    """One row for each project file: the row count from the footer, the project columns from the first row."""
    rows = []
    for f in files:
        pf = pq.ParquetFile(f)
        first = pf.read_row_group(0, columns=PROJECT_COLUMNS).slice(0, 1).to_pylist()[0]
        kv = {k.decode(): v.decode() for k, v in (pf.metadata.metadata or {}).items()}
        rows.append({"project": os.path.basename(f)[: -len(SUFFIX)], "rows": pf.metadata.num_rows,
                     "bytes": os.path.getsize(f), "columns": pf.metadata.num_columns,
                     "layer": layer_of(first["commits"]), "ctp_schema_version": kv.get("ctp_schema_version"),
                     **first})
    return pd.DataFrame(rows)


def load_organizations(root: str) -> dict[str, pd.DataFrame]:
    return {t: pq.read_table(os.path.join(root, "organizations", t + ".parquet")).to_pandas() for t in ORG_TABLES}


def scan(files: list[str], columns: list[str]):
    """Yield (project, batch) for each batch of 1,000,000 rows. Only the given columns are read."""
    for f in files:
        project = os.path.basename(f)[: -len(SUFFIX)]
        for b in pq.ParquetFile(f).iter_batches(batch_size=BATCH, columns=columns):
            yield project, b


def count_values(files: list[str], column: str, transform=None) -> pd.Series:
    """The number of code tokens (is_structural = 0) for each value of a column."""
    counts: collections.Counter = collections.Counter()
    for _, b in scan(files, ["is_structural", column]):
        values = b.column(column).filter(pc.equal(b.column("is_structural"), 0))
        if transform is not None:
            values = transform(values)
        for item in pc.value_counts(values).to_pylist():
            counts[item["values"]] += item["counts"]
    return pd.Series(counts, dtype="int64").sort_values(ascending=False)


def share(s: pd.Series, n: int | None = None) -> pd.DataFrame:
    df = pd.DataFrame({"tokens": s, "percent": (100.0 * s / s.sum()).round(2)})
    return df.head(n) if n else df


def year_of(values: pa.Array) -> pa.Array:
    # author_date is text in the form yyyy-MM-dd HH:mm:ss (UTC).
    return pc.utf8_slice_codeunits(values, 0, 4)


def print_table(title: str, df) -> None:
    print(f"\n{title}")
    with pd.option_context("display.width", 120, "display.max_rows", 50):
        print(df.to_string())


def summary(projects: pd.DataFrame, orgs: dict[str, pd.DataFrame]) -> None:
    print(f"project files: {len(projects):,}")
    print(f"token rows: {projects['rows'].sum():,}")
    print(f"bytes: {projects['bytes'].sum():,}")
    print(f"columns in each file: {sorted(projects['columns'].unique().tolist())}")
    print(f"ctp schema version in the footer: {sorted(projects['ctp_schema_version'].dropna().unique().tolist())}")
    for col in ["layer", "language", "stratum"]:
        g = projects.groupby(col, dropna=False).agg(projects=("project", "size"), rows=("rows", "sum"))
        print_table(f"projects by {col}:", g.sort_values("rows", ascending=False))
    print("\norganization tables (rows):")
    for t, df in orgs.items():
        print(f"  {t}: {len(df):,}")


def examples(files: list[str], projects: pd.DataFrame, orgs: dict[str, pd.DataFrame], project: str) -> None:
    kinds = orgs["organizations"].set_index("organization_id")["kind"]

    # 1. The share of code tokens by kind of the organization of the author address (all files).
    by_org = count_values(files, "firm_based_on_domain")
    by_kind = by_org.groupby(by_org.index.map(lambda i: kinds.get(i, "(not in the table)"))).sum()
    print_table("example 1: code tokens by kind of the organization of the author address (all files):",
                share(by_kind.sort_values(ascending=False)))

    # 2. One project: the share of code tokens by organization id, and the top 5 author pseudonyms.
    one = [f for f in files if os.path.basename(f) == project + SUFFIX]
    if not one:
        print(f"\nexample 2: no file for project {project}; use --project")
    else:
        row = projects.set_index("project").loc[project]
        print(f"\nexample 2: project {project} (namespace organization: {row['firm_based_on_namespace']}, "
              f"label: {row['stratum']}, {row['layer']})")
        s = count_values(one, "firm_based_on_domain")
        df = share(s, 8)
        df.insert(0, "kind", [kinds.get(i, "(not in the table)") for i in df.index])
        print_table("code tokens by organization id of the author address (top 8):", df)
        print_table("code tokens by author pseudonym (personid, top 5):", share(count_values(one, "personid"), 5))

    # 3. Code tokens by the year of the author date of the commit that last changed the token (all files).
    by_year = count_values(files, "author_date", year_of).sort_index()
    print_table("example 3: code tokens by author year (all files; the last 12 years):", share(by_year).tail(12))


def examples_duckdb(root: str, project: str) -> None:
    import duckdb  # optional

    con = duckdb.connect()
    pq_glob = os.path.join(root, "parquet", "*" + SUFFIX)
    org = os.path.join(root, "organizations", "organizations.parquet")
    print("\nDuckDB: code tokens by kind of the organization of the author address:")
    print(con.sql(f"""
        SELECT o.kind, count(*) AS tokens, round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS percent
        FROM read_parquet('{pq_glob}') t
        LEFT JOIN '{org}' o ON o.organization_id = t.firm_based_on_domain
        WHERE t.is_structural = 0
        GROUP BY 1 ORDER BY 2 DESC""").df().to_string(index=False))
    print(f"\nDuckDB: top 5 author pseudonyms of {project}:")
    print(con.sql(f"""
        SELECT personid, count(*) AS tokens, round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS percent
        FROM read_parquet('{os.path.join(root, 'parquet', project + SUFFIX)}')
        WHERE is_structural = 0
        GROUP BY 1 ORDER BY 2 DESC LIMIT 5""").df().to_string(index=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=os.path.join(HERE, "data"), help="the root with parquet/ and organizations/")
    ap.add_argument("--project", default="google__guava", help="the project of example 2")
    ap.add_argument("--only", nargs="*", help="read only these projects (names without -dataset.parquet)")
    ap.add_argument("--duckdb", action="store_true", help="also run the examples with DuckDB")
    a = ap.parse_args(argv)

    files = project_files(a.data, a.only)
    if not files:
        print(f"no project files in {os.path.join(a.data, 'parquet')}", file=sys.stderr)
        return 1
    projects = load_projects(files)
    orgs = load_organizations(a.data)
    summary(projects, orgs)
    examples(files, projects, orgs, a.project)
    if a.duckdb:
        examples_duckdb(a.data, a.project)
    return 0


if __name__ == "__main__":
    sys.exit(main())
