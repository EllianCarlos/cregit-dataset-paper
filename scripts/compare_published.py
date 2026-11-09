#!/usr/bin/env python3
"""Compare a rebuilt file (before the pseudonyms) with the published file of the same project.

Usage: compare_published.py PRE.parquet PUBLISHED.parquet

The published files went through the release write: the organization columns and the pseudonyms
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
  - person_domain: a value with no at sign becomes lower(trim(value)); a value with an at sign
    follows rule E (the first valid domain after an at sign, else empty);
  - firm_raw, firm, firm_source: removed (ctp schema 2);
  - firm_based_on_namespace, firm_based_on_domain, project_enterprise_driven,
    project_enterprise_basis: added (ctp schema 2).
The published file of TOM 1.0.0 (ctp schema 3, 53 columns; the column has `audit_frame_file`)
also went through the release passes (steps/release-passes/). Then the script also allows:
  - the 18 columns that the passes dropped (TOM_DROPPED);
  - the rename provenance_status -> audit_frame_file (the values stay);
  - the fill of pass 2: language (old value empty). A row of this column may differ only where
    the old value is the empty value;
  - license: pass 2 filled it where the old value was NOASSERTION, and the revision of TOM 1.0.0
    (pass 5) writes into every row of a file the license value of the license pass. So a row of
    this column may differ from the rebuilt file, but the published file has one license value.
The pseudonym of a value is a salted hash of the value in lower case (pseudonymize.py of the
release), and NULL and the empty value do not change. So for each identity column the script
checks: one value gives one pseudonym; values that are equal in lower case give one pseudonym;
values that are not equal in lower case give different pseudonyms (for the 7 identity columns
and for footer_personids and footer_person_names); no value that is not empty stays the same.
The 13 trailer text lists keep only the first two checks and the last one: the write parses
each trailer line, so two lines that differ only in spaces or in the text after the address
can give one pseudonym. NULL counts as a value. commit_summary is published as git has it, so
it is in the equal set.

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
# The lists whose elements get the pseudonym of a name or a person id (a hash of the lower-case
# element). The other lists are the trailer text lists.
LIST_OF_NAMES = ("footer_personids", "footer_person_names")
PARTIAL = ("person_domain",)
REMOVED = ("firm_raw", "firm", "firm_source")
ADDED = ("firm_based_on_namespace", "firm_based_on_domain", "project_enterprise_driven",
         "project_enterprise_basis")
KEY = ("file_path", "token_index")
# The release passes of TOM 1.0.0: dropped columns, the rename, the fill of pass 2 and the license.
TOM_MARK = "audit_frame_file"
TOM_DROPPED = ("size_kb", "file_mask", "manifest_category", "fact", "history_cluster",
               "history_shared_with", "history_relation", "history_includes", "history_first",
               "history_created", "person_name", "person_email", "footer_person_names",
               "cregit_commit_sha", "repo_tag", "archived", "fork", "roster_lang")
TOM_RENAMED = {"provenance_status": "audit_frame_file"}
TOM_FILLS = {"language": ("",)}
# The columns that a release pass sets to one value for each file (pass 5: the license pass).
TOM_SET = ("license",)


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def lit(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def distinct(expr: str, src: str = "j") -> str:
    """SQL: the number of distinct values of expr, NULL included (count(DISTINCT) skips NULL)."""
    return f"(SELECT count(*) FROM (SELECT DISTINCT {expr} FROM {src}))"


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
    tom = TOM_MARK in b_cols and TOM_MARK not in a_cols
    a_sel = ", ".join(f"{q(c)} AS {q(TOM_RENAMED.get(c, c) if tom else c)}" for c in a_cols)
    if tom:
        a_cols = [TOM_RENAMED.get(c, c) for c in a_cols]
        print("schema   the published file is ctp schema 3 (TOM): the drops, the rename and the "
              "fills of the release passes are allowed")
    removed = REMOVED + (TOM_DROPPED if tom else ())
    fills = TOM_FILLS if tom else {}
    sets = TOM_SET if tom else ()
    fails: list[str] = []

    def fail(text: str) -> None:
        fails.append(text)
        print("FAIL " + text)

    lost = [c for c in a_cols if c not in b_cols and c not in removed]
    new = [c for c in b_cols if c not in a_cols and c not in ADDED]
    if lost:
        fail(f"columns of the rebuilt file that the published file does not have: {lost}")
    if new:
        fail(f"columns of the published file that the rebuilt file does not have: {new}")
    for c in removed:
        print(f"removed  {c:<26} {'(in the rebuilt file)' if c in a_cols else '(not in either file)'}")

    n_a = con.execute("SELECT count(*) FROM read_parquet(?)", [pre]).fetchone()[0]
    n_b = con.execute("SELECT count(*) FROM read_parquet(?)", [pub]).fetchone()[0]
    print(f"rows     rebuilt {n_a}, published {n_b}")
    if n_a != n_b:
        fail("the row counts are not equal")
        return 1

    con.execute(f"CREATE TEMP VIEW a AS SELECT {a_sel} FROM read_parquet({lit(pre)})")
    con.execute(f"CREATE TEMP VIEW b AS SELECT * FROM read_parquet({lit(pub)})")
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

    changed = set(SCALAR) | set(LISTS) | set(PARTIAL) | set(fills) | set(sets)
    equal_cols = [c for c in common if c not in changed]
    diffs = con.execute("SELECT " + ", ".join(
        f"count(*) FILTER (WHERE {q('a_' + c)} IS DISTINCT FROM {q('b_' + c)})"
        for c in equal_cols) + " FROM j").fetchone()
    for c, d in zip(equal_cols, diffs):
        print(f"equal    {c:<26} rows that differ: {d}")
        if d:
            fail(f"{c}: {d} rows differ")

    for c, olds in fills.items():
        if c not in common:
            continue
        a, b = q("a_" + c), q("b_" + c)
        olds_sql = ", ".join(lit(o) for o in olds)
        bad, filled = con.execute(
            f"SELECT count(*) FILTER (WHERE {a} IS DISTINCT FROM {b} AND coalesce({a}, '') NOT IN ({olds_sql})), "
            f"count(*) FILTER (WHERE {a} IS DISTINCT FROM {b}) FROM j").fetchone()
        print(f"fill     {c:<26} rows with a filled value: {filled}; rows that differ in another way: {bad}")
        if bad:
            fail(f"{c}: {bad} rows differ and their old value is not a value that pass 2 fills")

    for c in sets:
        if c not in common:
            continue
        a, b = q("a_" + c), q("b_" + c)
        diff, values = con.execute(
            f"SELECT count(*) FILTER (WHERE {a} IS DISTINCT FROM {b}), count(DISTINCT coalesce({b}, '')) "
            f"FROM j").fetchone()
        print(f"set      {c:<26} rows with another value: {diff}; values in the published file: {values}")
        if values > 1:
            fail(f"{c}: the published file has {values} values, not one value for the file")

    for c in PARTIAL:
        if c not in common:
            continue
        a, b = q("a_" + c), q("b_" + c)
        no_at, with_at, changed_n = con.execute(
            f"SELECT count(*) FILTER (WHERE NOT coalesce(contains({a}, '{AT}'), false) "
            f"AND lower(trim({a})) IS DISTINCT FROM {b}), "
            f"count(*) FILTER (WHERE contains({a}, '{AT}')), "
            f"count(*) FILTER (WHERE contains({a}, '{AT}') AND {a} IS DISTINCT FROM {b}) FROM j"
        ).fetchone()
        print(f"domain   {c:<26} rows with no at sign that are not lower(trim(value)): {no_at}; "
              f"rows with an at sign: {with_at} ({changed_n} changed)")
        if no_at:
            fail(f"{c}: {no_at} rows with no at sign are not lower(trim(value))")

    def mapping(c: str, a: str, b: str, src: str, by_lower: bool) -> None:
        """The checks of one identity column: a and b are the SQL values before and after."""
        n_from, n_to, pairs, n_low, pairs_low, same = con.execute(
            f"SELECT {distinct(a, src)}, {distinct(b, src)}, {distinct(f'{a}, {b}', src)}, "
            f"{distinct(f'lower({a})', src)}, {distinct(f'lower({a}), {b}', src)}, "
            f"(SELECT count(*) FROM {src} WHERE {a} = {b} AND {a} <> '')").fetchone()
        print(f"pseudo   {c:<26} values {n_from}, lower-case values {n_low}, pseudonyms {n_to}, "
              f"rows with an unchanged value that is not empty: {same}")
        if pairs != n_from:
            fail(f"{c}: one value gives more than one pseudonym")
        if pairs_low != n_low:
            fail(f"{c}: values that are equal in lower case give more than one pseudonym")
        if by_lower and n_to != n_low:
            fail(f"{c}: values that are not equal in lower case give one pseudonym")
        if same:
            fail(f"{c}: {same} rows keep a value that is not empty")

    for c in SCALAR:
        if c in common:
            mapping(c, q("a_" + c), q("b_" + c), "j", True)

    for c in LISTS:
        if c not in common:
            continue
        a, b = q("a_" + c), q("b_" + c)
        bad_len = con.execute(
            f"SELECT count(*) FROM j WHERE len({a}) IS DISTINCT FROM len({b})").fetchone()[0]
        print(f"pseudo   {c:<26} rows with another list length: {bad_len}")
        if bad_len:
            fail(f"{c}: {bad_len} rows have another list length")
        con.execute(f"CREATE OR REPLACE TEMP TABLE e AS SELECT unnest({a}) AS u, unnest({b}) AS v "
                    f"FROM j WHERE len({a}) = len({b}) AND len({a}) > 0")
        mapping(c, "u", "v", "e", c in LIST_OF_NAMES)

    for c in ADDED:
        if c in b_cols:
            filled = con.execute(f"SELECT count({q('b_' + c)}) FROM j").fetchone()[0]
            print(f"added    {c:<26} rows that are not NULL: {filled}")
    if fails:
        print(f"FAIL: {len(fails)} checks failed")
        return 1
    print(f"OK: the published file has the {n_b} rows of the rebuilt file, in the same order; "
          f"{len(equal_cols)} columns are equal, {len([c for c in SCALAR + LISTS if c in common])} "
          f"identity columns follow the pseudonym rule, person_domain follows its rule")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
