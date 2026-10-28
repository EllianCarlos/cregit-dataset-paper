#!/usr/bin/env python3
"""Compare a rebuilt file (before the pseudonyms) with the published file of the same project.

Usage: compare_published.py PRE.parquet PUBLISHED.parquet

The published files went through the release write: the organisation columns and the pseudonyms
of the identity columns, in one write, with a salt that is deleted by design. So a rebuild cannot
give the published bytes. The rule of rebuild-one is:

  1. The rebuild gives the sha256 of the file before the release write (pre_pseudonym_sha256 of
     data/REBUILD-TARGETS.tsv). The caller checks this sha256.
  2. The published file has the same rows in the same order (file_path and token_index), and it
     is equal to that file in every column that the release write does not change.

This script checks part 2. The release write changes only these columns:
  - the identity columns: author_name, author_email, committer_name, committer_email, personid,
    person_name, person_email (each value becomes a pseudonym), and the 15 footer_* lists (each
    element becomes a pseudonym; the list keeps its length);
  - person_domain: only a value with an at sign can change (rule E: the first valid domain after
    an at sign, else empty);
  - firm_raw, firm, firm_source: removed (ctp schema 2);
  - firm_based_on_namespace, firm_based_on_domain, project_enterprise_driven,
    project_enterprise_basis: added (ctp schema 2).
For the identity columns the script checks that the change is one to one in each column: one
value before gives one pseudonym, and one pseudonym comes from one value. commit_summary is
published as git has it, so it is in the equal set.

The script prints counts and column names only, never a value. It needs duckdb.
Exit 0: the rule holds. Exit 1: a check failed. Exit 2: usage.
"""
from __future__ import annotations

import sys

AT = chr(64)
SCALAR = ("author_name", "author_email", "committer_name", "committer_email", "personid",
          "person_name", "person_email")
LISTS = ("footer_signed_off_by", "footer_co_authored_by", "footer_co_developed_by",
         "footer_reviewed_by", "footer_acked_by", "footer_tested_by", "footer_reported_by",
         "footer_suggested_by", "footer_based_on_patch_by", "footer_helped_by",
         "footer_mentored_by", "footer_assisted_by", "footer_thanks_to", "footer_personids",
         "footer_person_names")
PARTIAL = ("person_domain",)
REMOVED = ("firm_raw", "firm", "firm_source")
ADDED = ("firm_based_on_namespace", "firm_based_on_domain", "project_enterprise_driven",
         "project_enterprise_basis")
KEY = ("file_path", "token_index")


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.splitlines()[2], file=sys.stderr)
        return 2
    import duckdb

    pre, pub = argv
    con = duckdb.connect()
    cols = lambda p: [r[0] for r in con.execute(
        "DESCRIBE SELECT * FROM read_parquet(?)", [p]).fetchall()]
    a_cols, b_cols = cols(pre), cols(pub)
    fails: list[str] = []

    def fail(text: str) -> None:
        fails.append(text)
        print("FAIL " + text)

    lost = [c for c in a_cols if c not in b_cols and c not in REMOVED]
    new = [c for c in b_cols if c not in a_cols and c not in ADDED]
    if lost:
        fail(f"columns of the rebuilt file that the published file does not have: {lost}")
    if new:
        fail(f"columns of the published file that the rebuilt file does not have: {new}")
    for c in REMOVED:
        print(f"removed  {c:<26} {'(in the rebuilt file)' if c in a_cols else '(not in either file)'}")

    n_a = con.execute("SELECT count(*) FROM read_parquet(?)", [pre]).fetchone()[0]
    n_b = con.execute("SELECT count(*) FROM read_parquet(?)", [pub]).fetchone()[0]
    print(f"rows     rebuilt {n_a}, published {n_b}")
    if n_a != n_b:
        fail("the row counts are not equal")
        return 1

    con.execute(f"CREATE TEMP VIEW a AS SELECT * FROM read_parquet('{pre}')")
    con.execute(f"CREATE TEMP VIEW b AS SELECT * FROM read_parquet('{pub}')")
    common = [c for c in a_cols if c in b_cols]
    sel = ", ".join([f"a.{q(c)} AS {q('a_' + c)}" for c in common] +
                    [f"b.{q(c)} AS {q('b_' + c)}" for c in common] +
                    [f"b.{q(c)} AS {q('b_' + c)}" for c in ADDED if c in b_cols])
    con.execute(f"CREATE TEMP TABLE j AS SELECT {sel} FROM a POSITIONAL JOIN b")
    bad_key = con.execute("SELECT count(*) FROM j WHERE " + " OR ".join(
        f"{q('a_' + k)} IS DISTINCT FROM {q('b_' + k)}" for k in KEY)).fetchone()[0]
    print(f"order    rows with another (file_path, token_index) at the same position: {bad_key}")
    if bad_key:
        fail("the rows are not in the same order")
        return 1

    changed = set(SCALAR) | set(LISTS) | set(PARTIAL)
    equal_cols = [c for c in common if c not in changed]
    diffs = con.execute("SELECT " + ", ".join(
        f"count(*) FILTER (WHERE {q('a_' + c)} IS DISTINCT FROM {q('b_' + c)})"
        for c in equal_cols) + " FROM j").fetchone()
    for c, d in zip(equal_cols, diffs):
        print(f"equal    {c:<26} rows that differ: {d}")
        if d:
            fail(f"{c}: {d} rows differ")

    for c in PARTIAL:
        if c not in common:
            continue
        a, b = q("a_" + c), q("b_" + c)
        no_at, with_at, changed_n = con.execute(
            f"SELECT count(*) FILTER (WHERE NOT coalesce(contains({a}, '{AT}'), false) "
            f"AND {a} IS DISTINCT FROM {b}), count(*) FILTER (WHERE contains({a}, '{AT}')), "
            f"count(*) FILTER (WHERE contains({a}, '{AT}') AND {a} IS DISTINCT FROM {b}) FROM j"
        ).fetchone()
        print(f"domain   {c:<26} rows that differ with no at sign: {no_at}; "
              f"rows with an at sign: {with_at} ({changed_n} changed)")
        if no_at:
            fail(f"{c}: {no_at} rows with no at sign differ")

    for c in SCALAR:
        if c not in common:
            continue
        a, b = q("a_" + c), q("b_" + c)
        pairs, n_from, n_to, same = con.execute(
            f"SELECT (SELECT count(*) FROM (SELECT DISTINCT {a}, {b} FROM j)), "
            f"count(DISTINCT {a}), count(DISTINCT {b}), "
            f"count(*) FILTER (WHERE {a} = {b} AND {a} <> '') FROM j").fetchone()
        print(f"pseudo   {c:<26} values {n_from}, pseudonyms {n_to}, pairs {pairs}, "
              f"rows with an unchanged value that is not empty: {same}")
        if not (pairs == n_from == n_to):
            fail(f"{c}: the change is not one to one")

    for c in LISTS:
        if c not in common:
            continue
        a, b = q("a_" + c), q("b_" + c)
        bad_len = con.execute(
            f"SELECT count(*) FROM j WHERE len({a}) IS DISTINCT FROM len({b})").fetchone()[0]
        pairs, n_from, n_to = con.execute(
            f"WITH e AS (SELECT unnest({a}) AS u, unnest({b}) AS v FROM j "
            f"WHERE len({a}) = len({b}) AND len({a}) > 0) "
            f"SELECT (SELECT count(*) FROM (SELECT DISTINCT u, v FROM e)), "
            f"count(DISTINCT u), count(DISTINCT v) FROM e").fetchone()
        print(f"pseudo   {c:<26} rows with another list length: {bad_len}; elements {n_from}, "
              f"pseudonyms {n_to}, pairs {pairs}")
        if bad_len:
            fail(f"{c}: {bad_len} rows have another list length")
        if not (pairs == n_from == n_to):
            fail(f"{c}: the change is not one to one")

    for c in ADDED:
        if c in b_cols:
            filled = con.execute(f"SELECT count({q('b_' + c)}) FROM j").fetchone()[0]
            print(f"added    {c:<26} rows that are not NULL: {filled}")
    if fails:
        print(f"FAIL: {len(fails)} checks failed")
        return 1
    print(f"OK: the published file has the {n_b} rows of the rebuilt file, in the same order; "
          f"{len(equal_cols)} columns are equal, {len([c for c in SCALAR + LISTS if c in common])} "
          f"identity columns change one to one, person_domain changes only with an at sign")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
