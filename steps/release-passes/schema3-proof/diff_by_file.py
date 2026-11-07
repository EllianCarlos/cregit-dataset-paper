#!/usr/bin/env python3
"""Rows whose original_commit_sha differs, grouped by file_path (counts only).

    diff_by_file.py REBUILT TOM [EXCLUDE_FILE]

With EXCLUDE_FILE, also says whether every column except the identity
columns is equal on all other rows.
"""
import sys

import duckdb

a, b = sys.argv[1], sys.argv[2]
ex = sys.argv[3] if len(sys.argv) > 3 else None
con = duckdb.connect(config={"preserve_insertion_order": True, "threads": 4})
src = f"read_parquet('{a}') x POSITIONAL JOIN read_parquet('{b}') y"
rows = con.execute(f"SELECT x.file_path, count(*) FROM {src} WHERE x.original_commit_sha "
                   f"IS DISTINCT FROM y.original_commit_sha GROUP BY 1 ORDER BY 2 DESC").fetchall()
print("files with a different commit:", len(rows), "rows:", sum(r[1] for r in rows))
for f, n in rows[:5]:
    print(f"  {f}: {n}")
total = con.execute(f"SELECT count(*) FROM read_parquet('{a}') WHERE file_path = ?",
                    [rows[0][0]]).fetchone()[0] if rows else 0
print("rows of the first file:", total)
if ex:
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{a}')").fetchall()]
    ident = {"author_name", "author_email", "committer_name", "committer_email", "personid",
             "footer_signed_off_by", "footer_co_authored_by", "footer_co_developed_by",
             "footer_reviewed_by", "footer_acked_by", "footer_tested_by", "footer_reported_by",
             "footer_suggested_by", "footer_based_on_patch_by", "footer_helped_by",
             "footer_mentored_by", "footer_assisted_by", "footer_thanks_to", "footer_personids"}
    other = [c for c in cols if c not in ident]
    cond = " OR ".join(f'x."{c}" IS DISTINCT FROM y."{c}"' for c in other)
    n = con.execute(f"SELECT count(*) FROM {src} WHERE x.file_path <> ? AND ({cond})",
                    [ex]).fetchone()[0]
    print(f"rows outside {ex} with any of the {len(other)} non-identity columns different: {n}")
    for c in sorted(ident & set(cols)):
        lst = c.startswith("footer_")
        if lst:
            pairs = (f'SELECT unnest(x."{c}") l, unnest(y."{c}") r FROM {src} '
                     f'WHERE x.file_path <> ? AND len(x."{c}") = len(y."{c}")')
        else:
            pairs = f'SELECT x."{c}" l, y."{c}" r FROM {src} WHERE x.file_path <> ?'
        nl, nr, npair = con.execute(
            f"SELECT count(DISTINCT coalesce(l, chr(0))), count(DISTINCT coalesce(r, chr(0))), "
            f"count(DISTINCT (coalesce(l, chr(0)), coalesce(r, chr(0)))) FROM ({pairs})", [ex]).fetchone()
        print(f"  outside: {c:<26} distinct {nl} / {nr}, pairs {npair}, bijection {nl == nr == npair}")
