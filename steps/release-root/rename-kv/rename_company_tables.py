#!/usr/bin/env python3
"""Write the organization tables of dataset release 2 from release 1.

Input (read only):  OLD_ROOT/organisations/*.parquet and dataset.duckdb
Output:             NEW_ROOT/organizations/*.parquet and dataset.duckdb

Changes (our own vocabulary only):
  - file and table names: organisation -> organization
  - column organisation_id -> organization_id
  - label values: organisation_domains.error_stratum, link_error.error_stratum,
    link_error.method ("organisation" -> "organization")
  - release_info keys; the *_sha256 values of the new tables are computed again
  - view names, view column names and paths in dataset.duckdb; the kv key in
    the stale_files view (organizations_mapping_sha256)
Not changed: organisation_namespaces.namespace (real GitHub account names),
names, URLs and all other third-party text; column order, types, row order.

Write settings are the ones of build_organisations.py (read, not edited):
duckdb.connect(config={"threads": 2, "memory_limit": "2GB"}) and
COPY ... (FORMAT PARQUET, COMPRESSION ZSTD) with no level, so the DuckDB
default ZSTD level.  Step "probe" proves this: it copies each old table with
these settings and compares the bytes with the old file.

Usage: python -I rename_company_tables.py OLD_ROOT NEW_ROOT REPORT_JSON
Runtime: the ctp venv (Python 3.12, duckdb 1.5.5).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import duckdb

OLD_TABLES = ("organisations", "organisation_domains", "organisation_namespaces", "project_organisations",
              "link_error", "release_info")
VALUE_COLS = {"organisation_domains": ("error_stratum",), "link_error": ("error_stratum", "method")}
KEEP_ORGANIS = {("organisation_namespaces", "namespace")}  # third-party names: never change


def ren(s: str) -> str:
    return s.replace("organisation", "organization").replace("Organisation", "Organization")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def build_con():
    return duckdb.connect(config={"threads": 2, "memory_limit": "2GB"})


def copy(con, rel: str, dst: Path) -> None:
    tmp = dst.with_name(f".{dst.name}.tmp")
    con.execute(f"COPY (SELECT * FROM {rel}) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    os.replace(tmp, dst)


def cols_of(con, p: Path):
    return con.execute(f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM '{p}')").fetchall()


def rows_of(con, p: Path):
    return con.execute(f"SELECT * FROM '{p}'").fetchall()


def main(old_root: Path, new_root: Path, report: Path) -> int:
    old = old_root / "organisations"
    new = new_root / "organizations"
    new.mkdir(parents=True, exist_ok=True)
    rep = {"probe": {}, "tables": {}, "views": {}}
    con = build_con()

    # 1. probe: the old settings give the old bytes back.
    with tempfile.TemporaryDirectory(dir=new_root) as td:
        for t in OLD_TABLES:
            dst = Path(td) / f"{t}.parquet"
            copy(con, f"'{old / (t + '.parquet')}'", dst)
            rep["probe"][t] = sha256(dst) == sha256(old / f"{t}.parquet")

    # 2. the five data tables.
    for t in OLD_TABLES[:-1]:
        src = old / f"{t}.parquet"
        nt = ren(t)
        cols = cols_of(con, src)
        sel = []
        for c, _ in cols:
            e = f'"{c}"'
            if c in VALUE_COLS.get(t, ()):
                e = f"replace({e}, 'organisation', 'organization')"
            sel.append(f'{e} AS "{ren(c)}"')
        copy(con, f"(SELECT {', '.join(sel)} FROM '{src}')", new / f"{nt}.parquet")
        rep["tables"][nt] = {"source": t}

    # 3. release_info: keys renamed, table sha256 values computed again.
    ri_old = con.execute(f"SELECT key, value FROM '{old / 'release_info.parquet'}'").fetchall()
    ri_new = []
    for k, v in ri_old:
        nk = ren(k)
        if nk.endswith("_sha256") and (new / f"{nk[:-len('_sha256')]}.parquet").is_file():
            v = sha256(new / f"{nk[:-len('_sha256')]}.parquet")
        ri_new.append((nk, v))
    if [k for k, _ in ri_new] != sorted(k for k, _ in ri_new):
        raise SystemExit("release_info keys are not in key order after the rename")
    con.execute("CREATE TEMP TABLE release_info (key VARCHAR, value VARCHAR)")
    con.executemany("INSERT INTO release_info VALUES (?, ?)", ri_new)
    copy(con, "release_info ORDER BY key", new / "release_info.parquet")
    rep["tables"]["release_info"] = {"source": "release_info"}
    con.close()

    # 4. checks of each table against the old one.
    con = build_con()
    for t in OLD_TABLES:
        nt = ren(t)
        po, pn = old / f"{t}.parquet", new / f"{nt}.parquet"
        co, cn = cols_of(con, po), cols_of(con, pn)
        ro, rn = rows_of(con, po), rows_of(con, pn)
        idx = {c: i for i, (c, _) in enumerate(co)}
        if t == "release_info":
            want = [(ren(k), dict(ri_new)[ren(k)]) for k, _ in ro]
        else:
            vc = {idx[c] for c in VALUE_COLS.get(t, ())}
            want = [tuple(ren(x) if i in vc and x is not None else x for i, x in enumerate(r)) for r in ro]
        changed = {}
        for c, i in idx.items():
            n = sum(1 for a, b in zip(ro, rn) if a[i] != b[i])
            if n:
                changed[c] = n
        left = {}
        for c, typ in cn:
            if "VARCHAR" in typ:
                n = con.execute(f"SELECT count(*) FROM '{pn}' WHERE lower(\"{c}\") LIKE '%organis%'").fetchone()[0]
                if n:
                    left[c] = n
        md = con.execute(f"SELECT DISTINCT compression FROM parquet_metadata('{pn}')").fetchall()
        fm = con.execute(f"SELECT created_by, num_row_groups FROM parquet_file_metadata('{pn}')").fetchone()
        ok = (cn == [(ren(c), typ) for c, typ in co] and rn == want and len(rn) == len(ro)
              and all((t, c) in KEEP_ORGANIS for c in left) and md == [("ZSTD",)])
        rep["tables"][nt].update(
            rows=len(rn), columns_before=[c for c, _ in co], columns_after=[c for c, _ in cn],
            types_equal=[x for _, x in co] == [x for _, x in cn], row_order_and_values_ok=rn == want,
            changed_values=changed, organis_left=left, codec=[m[0] for m in md], created_by=fm[0],
            row_groups=fm[1], sha256=sha256(pn), size=pn.stat().st_size, ok=ok)
    con.close()
    rep["release_info_keys_renamed"] = sum(1 for (a, _), (b, _) in zip(ri_old, ri_new) if a != b)
    rep["release_info_values_recomputed"] = sorted(k for (_, va), (k, vb) in zip(ri_old, ri_new) if va != vb)

    # 5. dataset.duckdb with the views renamed.
    oc = duckdb.connect(str(old / "dataset.duckdb"), read_only=True)
    views = dict(oc.execute("SELECT view_name, sql FROM duckdb_views() WHERE NOT internal").fetchall())
    oc.close()
    order = list(OLD_TABLES) + ["tokens", "tokens_with_organisations", "tokens_with_current_organisations",
                                "project_hosts", "project_sponsors", "stale_files"]
    if sorted(order) != sorted(views):
        raise SystemExit(f"unexpected view set: {sorted(views)}")
    dst = new / "dataset.duckdb"
    tmp = new / ".dataset.duckdb.tmp"
    tmp.unlink(missing_ok=True)
    os.chdir(new_root)  # view paths are relative to the release root
    nc = duckdb.connect(str(tmp))
    for v in order:
        nc.execute(ren(views[v]))
    names = [r[0] for r in nc.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal ORDER BY 1").fetchall()]
    nc.close()
    os.replace(tmp, dst)
    rep["views"]["names"] = names
    rep["views"]["sql_is_old_sql_renamed"] = True
    rep["dataset_duckdb_sha256"] = sha256(dst)
    report.write_text(json.dumps(rep, indent=1) + "\n")
    bad = [t for t, r in rep["tables"].items() if not r["ok"]] + [t for t, ok in rep["probe"].items() if not ok]
    print(json.dumps({"probe": rep["probe"], "bad": bad, "views": names,
                      "release_info_keys_renamed": rep["release_info_keys_renamed"],
                      "release_info_values_recomputed": rep["release_info_values_recomputed"],
                      "tables": {t: {k: r[k] for k in ("rows", "changed_values", "organis_left", "sha256", "ok")}
                                 for t, r in rep["tables"].items()}}, indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser(), Path(sys.argv[3]).expanduser()))
