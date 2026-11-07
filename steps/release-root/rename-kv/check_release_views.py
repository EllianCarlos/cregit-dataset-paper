#!/usr/bin/env python3
"""Compare the 12 views of dataset.duckdb of release 2 with the views of release 1.

Old: OLD_ROOT/organisations/dataset.duckdb, run with the working folder OLD_ROOT.
New: NEW_ROOT/organizations/dataset.duckdb, run with the working folder NEW_ROOT.

- The SQL of each new view is the SQL of the old view with "organisation" ->
  "organization".
- The column names of each new view are the old names renamed.
- Table views, project_hosts, project_sponsors, stale_files: all rows, in a
  fixed order, equal after the value rename (error_stratum, method,
  release_info key; the 4 release_info sha256 values that were computed again
  are compared with the new files).
- tokens: full count(*) (Parquet metadata) of all 10,754 files.
- tokens, tokens_with_organizations, tokens_with_current_organizations:
  count(*) and an order-free hash sum of each column, for each project of a
  sample (all rows of these projects).

Usage: python -I check_release_views.py OLD_ROOT NEW_ROOT OUT_JSON PROJECT [PROJECT ...]
"""
import hashlib
import json
import os
import sys

import duckdb

ren = lambda s: s.replace("organisation", "organization")  # noqa: E731
LABEL = {"error_stratum", "method", "key"}


class Side:
    def __init__(self, root, db):
        self.root = root
        os.chdir(root)
        self.c = duckdb.connect(db, read_only=True)
        self.c.execute("SET threads=8")

    def q(self, sql, *a):
        os.chdir(self.root)
        return self.c.execute(sql, list(a)).fetchall()


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main(old_root, new_root, out, projects):
    o = Side(old_root, "organisations/dataset.duckdb")
    n = Side(new_root, "organizations/dataset.duckdb")
    osql = dict(o.q("SELECT view_name, sql FROM duckdb_views() WHERE NOT internal"))
    nsql = dict(n.q("SELECT view_name, sql FROM duckdb_views() WHERE NOT internal"))
    rep = {"views_old": len(osql), "views_new": len(nsql), "views": {}}
    token_views = {"tokens", "tokens_with_organisations", "tokens_with_current_organisations"}
    for v in sorted(osql):
        nv = ren(v)
        r = {"sql_is_old_sql_renamed": nsql.get(nv) == ren(osql[v])}
        oc = [x[0] for x in o.q(f'DESCRIBE SELECT * FROM "{v}"')]
        nc = [x[0] for x in n.q(f'DESCRIBE SELECT * FROM "{nv}"')]
        r["columns_ok"] = nc == [ren(c) for c in oc]
        if v not in token_views:
            ro = o.q(f'SELECT * FROM "{v}" ORDER BY ALL')
            rn = n.q(f'SELECT * FROM "{nv}" ORDER BY ALL')
            li = [i for i, c in enumerate(oc) if c in LABEL]
            want = [tuple(ren(x) if i in li and isinstance(x, str) else x for i, x in enumerate(row)) for row in ro]
            if v == "release_info":
                d = dict(want)
                for k in list(d):
                    t = new_root + "/organizations/" + k[:-len("_sha256")] + ".parquet"
                    if k.endswith("_sha256") and os.path.isfile(t):
                        d[k] = sha256(t)
                want = sorted(d.items())
            key = lambda row: tuple((x is None, "" if x is None else str(x)) for x in row)  # noqa: E731
            r.update(rows_old=len(ro), rows_new=len(rn),
                     rows_equal=sorted(rn, key=key) == sorted(want, key=key))
        else:
            if v == "tokens":
                r["count_all_old"] = o.q("SELECT count(*) FROM tokens")[0][0]
                r["count_all_new"] = n.q("SELECT count(*) FROM tokens")[0][0]
            oexpr = [f"replace(\"{c}\", 'organisation', 'organization')" if c in LABEL else f'"{c}"' for c in oc]
            agg_o = ", ".join(f"sum(hash({e}))::HUGEINT" for e in oexpr)
            agg_n = ", ".join(f'sum(hash("{c}"))::HUGEINT' for c in nc)
            per = {}
            for p in projects:
                f = f"parquet/{p}-dataset.parquet"
                a = o.q(f'SELECT count(*), {agg_o} FROM "{v}" WHERE filename = ?', f)[0]
                b = n.q(f'SELECT count(*), {agg_n} FROM "{nv}" WHERE filename = ?', f)[0]
                per[p] = {"rows": b[0], "equal": a == b}
            r["sample"] = per
            r["sample_equal"] = all(x["equal"] for x in per.values())
        r["ok"] = all(val for k, val in r.items() if k in ("sql_is_old_sql_renamed", "columns_ok", "rows_equal",
                                                             "sample_equal"))
        if v == "tokens":
            r["ok"] = r["ok"] and r["count_all_old"] == r["count_all_new"]
        rep["views"][nv] = r
        print(nv, json.dumps({k: x for k, x in r.items() if k != "sample"}), flush=True)
    rep["all_ok"] = all(r["ok"] for r in rep["views"].values()) and len(nsql) == len(osql) == 12
    with open(out, "w") as fh:
        json.dump(rep, fh, indent=1)
    print("all_ok", rep["all_ok"])
    return 0 if rep["all_ok"] else 1


if __name__ == "__main__":
    a = sys.argv
    sys.exit(main(os.path.abspath(os.path.expanduser(a[1])), os.path.abspath(os.path.expanduser(a[2])),
                  os.path.abspath(a[3]), a[4:]))
