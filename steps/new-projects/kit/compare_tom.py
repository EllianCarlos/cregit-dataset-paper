#!/usr/bin/env python3
"""Compare a rebuilt ctp schema 3 file with the TOM pass output of the same project.

    compare_tom.py REBUILT TOM [--json OUT.json]

Prints counts, column names, types, hashes and footer keys only, never a value.

Checks:
  1. the column names and types, in order (DuckDB DESCRIBE);
  2. the footer key-values (ARROW:schema is left out: pyarrow writes it, DuckDB not);
  3. the row count;
  4. for each column, row for row (POSITIONAL JOIN, file order): the number of rows
     whose values differ (IS DISTINCT FROM, so NULL is a value), and an order
     hash on each side: bit_xor(hash(row number, column));
  5. for each column that differs: is the pair map a bijection? For a list column
     the lists must have the same length, and the elements are paired by
     position. A pseudonym column made with another salt differs in every
     value, but a bijection shows that both files group the rows the same way.
Exit 0 when every column is equal or a bijection, 1 otherwise.
"""
from __future__ import annotations

import json
import sys

import duckdb


def q(c: str) -> str:
    return '"' + c.replace('"', '""') + '"'


def main(argv: list[str]) -> int:
    a, b = argv[0], argv[1]
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    con = duckdb.connect(config={"threads": 4, "memory_limit": "4GB",
                                 "preserve_insertion_order": True})
    sa = [(r[0], r[1]) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [a]).fetchall()]
    sb = [(r[0], r[1]) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [b]).fetchall()]
    kv = {}
    for side, path in (("rebuilt", a), ("tom", b)):
        kv[side] = {k: v for k, v in con.execute(
            "SELECT decode(key), decode(value) FROM parquet_kv_metadata(?)", [path]).fetchall()
            if k != "ARROW:schema"}
    rows = {s: con.execute("SELECT count(*) FROM read_parquet(?)", [p]).fetchone()[0]
            for s, p in (("rebuilt", a), ("tom", b))}
    report = {"schema_equal": sa == sb, "columns": len(sa), "rows": rows,
              "kv_equal": [k for k in sorted(set(kv["rebuilt"]) | set(kv["tom"]))
                           if kv["rebuilt"].get(k) == kv["tom"].get(k)],
              "kv_differ": [k for k in sorted(set(kv["rebuilt"]) | set(kv["tom"]))
                            if kv["rebuilt"].get(k) != kv["tom"].get(k)],
              "per_column": []}
    # --subset: the rebuilt file may have fewer columns (the 53 of the later
    # schema 3); its columns must be the TOM columns of the same names, in order.
    subset = "--subset" in argv
    names_a = {c for c, _ in sa}
    sb_kept = [x for x in sb if x[0] in names_a] if subset else sb
    absent = [c for c, _ in sb if c not in names_a]
    report.update(schema_equal=sa == sb_kept, tom_columns=len(sb), absent_in_rebuilt=absent,
                  extra_in_rebuilt=[c for c, _ in sa if c not in {x for x, _ in sb}])
    print(f"schema equal (names, types, order){' on the kept TOM columns' if subset else ''}: "
          f"{sa == sb_kept} ({len(sa)} vs {len(sb_kept)} of {len(sb)} columns)")
    if subset:
        print(f"TOM columns absent from the rebuilt file ({len(absent)}): {absent}")
        print(f"rebuilt columns not in TOM: {report['extra_in_rebuilt']}")
    print(f"rows: rebuilt {rows['rebuilt']}, tom {rows['tom']}")
    print(f"footer keys equal: {report['kv_equal']}")
    print(f"footer keys that differ: {report['kv_differ']}")
    bad = sa != sb_kept or rows["rebuilt"] != rows["tom"]
    if bad:
        print("FAIL: schema or row count differ; no column check")
        return 1
    types = dict(sa)
    src = f"read_parquet({duckdb_str(a)}) x POSITIONAL JOIN read_parquet({duckdb_str(b)}) y"
    for c, t in sa:
        diff = con.execute(f"SELECT count(*) FILTER (WHERE x.{q(c)} IS DISTINCT FROM y.{q(c)}) "
                           f"FROM {src}").fetchone()[0]
        ha = con.execute(f"SELECT bit_xor(hash(file_row_number, {q(c)})) FROM "
                         f"read_parquet(?, file_row_number = true)", [a]).fetchone()[0]
        hb = con.execute(f"SELECT bit_xor(hash(file_row_number, {q(c)})) FROM "
                         f"read_parquet(?, file_row_number = true)", [b]).fetchone()[0]
        entry = {"column": c, "type": t, "rows_differ": diff,
                 "hash_rebuilt": f"{ha:016x}", "hash_tom": f"{hb:016x}"}
        if diff:
            entry.update(bijection(con, src, c, types[c].endswith("[]")))
            ok = entry["bijection"]
            bad |= not ok
        report["per_column"].append(entry)
    eq = [e["column"] for e in report["per_column"] if not e["rows_differ"]]
    bij = [e for e in report["per_column"] if e["rows_differ"]]
    print(f"columns equal row for row (hash equal): {len(eq)} of {len(sa)}")
    for e in bij:
        print(f"  differ: {e['column']:<26} rows {e['rows_differ']:>9}  distinct rebuilt "
              f"{e['distinct_rebuilt']}, tom {e['distinct_tom']}, pairs {e['pairs']}"
              f"{', list lengths differ in ' + str(e['length_differ']) + ' rows' if 'length_differ' in e else ''}"
              f"  -> bijection {e['bijection']}")
    if out_json:
        with open(out_json, "w") as fh:
            json.dump(report, fh, indent=1)
    print("RESULT:", "FAIL" if bad else "OK")
    return 1 if bad else 0


def duckdb_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def bijection(con, src: str, c: str, is_list: bool) -> dict:
    if is_list:
        n_len = con.execute(f"SELECT count(*) FILTER (WHERE len(x.{q(c)}) IS DISTINCT FROM "
                            f"len(y.{q(c)})) FROM {src}").fetchone()[0]
        pairs_sql = (f"SELECT unnest(x.{q(c)}) AS l, unnest(y.{q(c)}) AS r FROM {src} "
                     f"WHERE len(x.{q(c)}) = len(y.{q(c)})")
    else:
        n_len = None
        pairs_sql = f"SELECT x.{q(c)} AS l, y.{q(c)} AS r FROM {src}"
    nl, nr, np_ = con.execute(
        f"SELECT count(DISTINCT coalesce(l, chr(0))), count(DISTINCT coalesce(r, chr(0))), "
        f"count(DISTINCT (coalesce(l, chr(0)), coalesce(r, chr(0)))) FROM ({pairs_sql})").fetchone()
    out = {"distinct_rebuilt": nl, "distinct_tom": nr, "pairs": np_,
           "bijection": nl == nr == np_ and not n_len}
    if is_list:
        out["length_differ"] = n_len
    return out


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
