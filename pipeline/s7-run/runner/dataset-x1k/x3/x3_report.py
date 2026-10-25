#!/usr/bin/env python3
"""x3_report.py: the checks and the address-free reports of the x1k links machine (kit x3, 2026-10-23).

    x3_report.py inputs --results RESULTS.tsv --root DIR --out INPUTS.tsv
    x3_report.py check-cache --inputs INPUTS.tsv --cache DIR
    x3_report.py compare-links --got DIR --ref DIR [--subset]
    x3_report.py domains --v1-cache DIR --x1k-cache DIR --links DIR --v1-sidecar F --x1k-sidecar F --out DIR
    x3_report.py no-at FILE ...

inputs        From results.tsv of final_merge.py (columns project, output, output_sha256, rows): one row
              per project with project, path (DIR/output), sha256 and rows, the most rows first. The
              extraction (extract_domains_v1.py --inputs) reads it. Every file must exist.
check-cache   Each project of INPUTS has DIR/<project>.parquet, and its sum of tokens is its rows.
compare-links Two build_links.py outputs. Default (the v1 gate): the same mapping_sha256 and the same
              rows in domain_links, project_links and enterprise_audit. --subset (the merged links): each
              row of REF is in GOT (the v1 rows stay as they were); GOT can have more rows.
domains       The extension reports. The caches hold addresses; no output holds one:
                domain_counts.x1k.parquet  per project and domain: tokens, commits (the sum over the
                    author and committer groups of the cache; one author and one committer per commit,
                    so it is the number of commits), authors (a count). A value with the at sign is
                    not a domain: it becomes '(not a domain)'.
                new_domains.x1k.tsv  the real domains (not blank, a dot, no at sign) of the extension
                    that v1 does not have and that have no row in domain_links: their value is
                    `independent` until a review. Columns: domain, projects, tokens, commits, authors,
                    token_share_x1k, token_share_all, top_project. Most tokens first.
                new_domains_linked.x1k.tsv  the extension domains that v1 does not have but that have a
                    link row (a suffix match, the free-provider rule, an exact row): domain,
                    firm_based_on_domain, organisation_kind, match, tokens, token_share_x1k.
                new_namespaces.x1k.tsv  (host, namespace) of the extension sidecar that v1 does not
                    have and that have no `owns` value: host, namespace, projects, tokens.
                domains.x1k.json  the counts and token shares (the value classes of build_links.py).
no-at         Exit 1 if a file holds the at sign: each text value of a Parquet file, the text of the
              other files. It prints file names and counts only.
Exit 0 ok, 1 a check failed, 2 usage.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import duckdb

AT = chr(64)
NOT_A_DOMAIN = "(not a domain)"
LINK_TABLES = ("domain_links", "project_links", "enterprise_audit")
CSV = "FORMAT CSV, DELIMITER '\t', HEADER"


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", flush=True)
    return 1


def real(expr: str) -> str:
    """The real-domain rule of build_v0.real_domain_sql."""
    return f"({expr} <> '' AND contains({expr}, '.') AND NOT contains({expr}, chr(64)))"


# ---------------------------------------------------------------- inputs
def cmd_inputs(a) -> int:
    with open(a.results, newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    need = {"project", "output", "output_sha256", "rows"}
    if not rows or not need <= set(rows[0]):
        print(f"usage: {a.results} needs the columns {sorted(need)}", file=sys.stderr)
        return 2
    seen, out, missing = set(), [], []
    for r in rows:
        if r["project"] in seen:
            return fail(f"project {r['project']} repeats in {a.results}")
        seen.add(r["project"])
        p = a.root / r["output"]
        if not p.is_file():
            missing.append(r["project"])
        out.append((r["project"], str(p), r["output_sha256"], int(r["rows"])))
    if missing:
        return fail(f"{len(missing)} files are missing, for example {missing[0]}")
    out.sort(key=lambda r: (-r[3], r[0]))
    tmp = a.out.with_name(f".{a.out.name}.tmp")
    with open(tmp, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(("project", "path", "sha256", "rows"))
        w.writerows(out)
    os.replace(tmp, a.out)
    print(f"inputs: {len(out)} projects, {sum(r[3] for r in out)} rows -> {a.out}")
    return 0


# ---------------------------------------------------------------- check-cache
def cmd_check_cache(a) -> int:
    with open(a.inputs, newline="") as fh:
        want = {r["project"]: int(r["rows"]) for r in csv.DictReader(fh, delimiter="\t")}
    con = duckdb.connect()
    got = dict(con.execute(f"SELECT project, sum(tokens)::BIGINT FROM read_parquet('{a.cache}/*.parquet') "
                           "GROUP BY project").fetchall())
    files = {f.stem for f in a.cache.glob("*.parquet")}
    bad = []
    missing = sorted(set(want) - files)
    extra = sorted(files - set(want))
    for p, n in want.items():
        if p in files and got.get(p, 0) != n:
            bad.append(p)
    print(f"cache {a.cache}: {len(files)} files, {len(want)} inputs, {sum(got.values())} tokens "
          f"(inputs {sum(want.values())} rows); missing {len(missing)}, extra {len(extra)}, "
          f"token sum differs {len(bad)}")
    if missing or extra or bad:
        return fail("cache check: " + ", ".join(f"{k} e.g. {v[0]}" for k, v in
                                                (("missing", missing), ("extra", extra), ("differs", bad)) if v))
    print("cache check OK")
    return 0


# ---------------------------------------------------------------- compare-links
def cmd_compare_links(a) -> int:
    con = duckdb.connect()
    bad = 0
    for t in LINK_TABLES:
        g, r = f"read_parquet('{a.got}/{t}.parquet')", f"read_parquet('{a.ref}/{t}.parquet')"
        missing = con.execute(f"SELECT count(*) FROM (SELECT * FROM {r} EXCEPT ALL SELECT * FROM {g})").fetchone()[0]
        extra = con.execute(f"SELECT count(*) FROM (SELECT * FROM {g} EXCEPT ALL SELECT * FROM {r})").fetchone()[0]
        ng, nr = (con.execute(f"SELECT count(*) FROM {x}").fetchone()[0] for x in (g, r))
        ok = missing == 0 and (a.subset or extra == 0)
        bad += not ok
        print(f"{t}: got {ng} rows, ref {nr}; ref rows not in got {missing}, got rows not in ref {extra} "
              f"-> {'OK' if ok else 'DIFFERENT'}")
    gj, rj = (json.loads((d / "links.json").read_text()) for d in (a.got, a.ref))
    if not a.subset:
        same = gj["mapping_sha256"] == rj["mapping_sha256"]
        bad += not same
        print(f"mapping_sha256: got {gj['mapping_sha256'][:12]}, ref {rj['mapping_sha256'][:12]} "
              f"-> {'OK' if same else 'DIFFERENT'}")
        for f, h in sorted(rj.get("outputs", {}).items()):
            print(f"  {f}: bytes {'equal' if gj.get('outputs', {}).get(f) == h else 'differ (not a gate)'}")
    else:
        print(f"mapping_sha256: got {gj['mapping_sha256'][:12]} (merged), ref {rj['mapping_sha256'][:12]} (v1 only)")
    if bad:
        return fail(f"compare-links {a.got} against {a.ref}: {bad} differences")
    print("compare-links OK")
    return 0


# ---------------------------------------------------------------- domains
def namespaces(sidecar: Path) -> dict[str, tuple[str, str]]:
    return {p: (urlsplit(m.get("clone_url", "")).netloc.lower(), (m.get("owner") or "").strip().lower())
            for p, m in json.loads(sidecar.read_text()).items()}


def copy(con, sql: str, dst: Path, fmt: str = "FORMAT PARQUET, COMPRESSION ZSTD") -> None:
    tmp = dst.with_name(f".{dst.name}.tmp")
    con.execute(f"COPY ({sql}) TO '{tmp}' ({fmt})")
    os.replace(tmp, dst)


def cmd_domains(a) -> int:
    a.out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(config={"memory_limit": a.memory_limit, "threads": a.threads})
    con.execute(f"CREATE TEMP VIEW x AS SELECT * FROM read_parquet('{a.x1k_cache}/*.parquet')")
    con.execute(f"CREATE TEMP VIEW v AS SELECT * FROM read_parquet('{a.v1_cache}/*.parquet')")
    con.execute(f"CREATE TEMP TABLE dl AS SELECT * FROM read_parquet('{a.links}/domain_links.parquet')")
    con.execute(f"CREATE TEMP TABLE pl AS SELECT * FROM read_parquet('{a.links}/project_links.parquet')")
    con.execute("CREATE TEMP TABLE v1dom AS SELECT DISTINCT domain FROM v")
    # per project and domain (the cache groups by domain, email and committer domain)
    con.execute(f"""
      CREATE TEMP TABLE dc AS
      SELECT project, CASE WHEN contains(domain, chr(64)) THEN '{NOT_A_DOMAIN}' ELSE domain END AS domain,
             sum(tokens)::BIGINT AS tokens, sum(commits)::BIGINT AS commits,
             count(DISTINCT email)::BIGINT AS authors
      FROM x GROUP BY ALL""")
    copy(con, "SELECT * FROM dc ORDER BY project, tokens DESC, domain", a.out / "domain_counts.x1k.parquet")
    tot_x = con.execute("SELECT sum(tokens) FROM x").fetchone()[0] or 0
    tot_v = con.execute("SELECT sum(tokens) FROM v").fetchone()[0] or 0
    tot = tot_x + tot_v
    con.execute(f"""
      CREATE TEMP TABLE xd AS
      SELECT x.domain, count(DISTINCT x.project) AS projects, sum(x.tokens)::BIGINT AS tokens,
             sum(x.commits)::BIGINT AS commits, count(DISTINCT x.email)::BIGINT AS authors
      FROM x WHERE {real('x.domain')} GROUP BY x.domain""")
    # the project with the most tokens of the domain (sum over its groups)
    con.execute(f"""
      CREATE TEMP TABLE xtop AS SELECT domain, arg_max(project, t) AS top_project FROM (
        SELECT domain, project, sum(tokens) AS t FROM x WHERE {real('domain')} GROUP BY ALL) GROUP BY domain""")
    new = f"""
      SELECT xd.domain, xd.projects, xd.tokens, xd.commits, xd.authors,
             round(xd.tokens / {max(tot_x, 1)}, 9) AS token_share_x1k, round(xd.tokens / {max(tot, 1)}, 9) AS token_share_all,
             xtop.top_project
      FROM xd JOIN xtop USING (domain)
      WHERE xd.domain NOT IN (SELECT domain FROM v1dom) AND xd.domain NOT IN (SELECT domain FROM dl)"""
    con.execute(f"CREATE TEMP TABLE new_t AS {new}")
    copy(con, "SELECT * FROM new_t ORDER BY tokens DESC, domain", a.out / "new_domains.x1k.tsv", CSV)
    linked = f"""
      SELECT xd.domain, dl.firm_based_on_domain, dl.organisation_kind, dl.match, xd.tokens,
             round(xd.tokens / {max(tot_x, 1)}, 9) AS token_share_x1k
      FROM xd JOIN dl USING (domain) WHERE xd.domain NOT IN (SELECT domain FROM v1dom)"""
    con.execute(f"CREATE TEMP TABLE linked_t AS {linked}")
    copy(con, "SELECT * FROM linked_t ORDER BY tokens DESC, domain", a.out / "new_domains_linked.x1k.tsv", CSV)
    # namespaces of the extension that v1 does not have and that get no owns value
    v1ns = set(namespaces(a.v1_sidecar).values())
    xns = namespaces(a.x1k_sidecar)
    con.execute("CREATE TEMP TABLE xns (project VARCHAR, host VARCHAR, namespace VARCHAR, in_v1 BOOLEAN)")
    con.executemany("INSERT INTO xns VALUES (?, ?, ?, ?)",
                    [(p, h, n, (h, n) in v1ns) for p, (h, n) in sorted(xns.items())])
    con.execute("""
      CREATE TEMP TABLE ns_t AS
      SELECT xns.host, xns.namespace, count(*) AS projects, coalesce(sum(pt.tokens), 0)::BIGINT AS tokens
      FROM xns LEFT JOIN pl USING (project)
      LEFT JOIN (SELECT project, sum(tokens) AS tokens FROM x GROUP BY project) pt USING (project)
      WHERE NOT xns.in_v1 AND pl.firm_based_on_namespace IS NULL
      GROUP BY ALL""")
    copy(con, "SELECT * FROM ns_t ORDER BY tokens DESC, host, namespace", a.out / "new_namespaces.x1k.tsv", CSV)
    # the value classes of the extension tokens (the rule of build_links.py / build_v0.py)
    con.execute(f"""
      CREATE TEMP TABLE tv AS
      SELECT x.tokens, coalesce(dl.firm_based_on_domain,
                                CASE WHEN {real('x.domain')} THEN 'independent' ELSE 'unknown' END) AS v,
             x.domain IN (SELECT domain FROM v1dom) AS in_v1
      FROM x LEFT JOIN dl USING (domain)""")

    def one(sql):
        return con.execute(sql).fetchone()[0] or 0
    n_new, t_new = one("SELECT count(*) FROM new_t"), one("SELECT sum(tokens) FROM new_t")
    n_lnk, t_lnk = one("SELECT count(*) FROM linked_t"), one("SELECT sum(tokens) FROM linked_t")
    xproj = set(xns)
    s = {
        "x1k_cache_projects": one("SELECT count(DISTINCT project) FROM x"),
        "x1k_tokens": tot_x, "v1_tokens": tot_v,
        "x1k_real_domains": one("SELECT count(*) FROM xd"),
        "x1k_real_domains_also_in_v1": one("SELECT count(*) FROM xd WHERE domain IN (SELECT domain FROM v1dom)"),
        "new_domains_unlinked": n_new, "new_domains_unlinked_token_share_x1k": t_new / max(tot_x, 1),
        "new_domains_unlinked_token_share_all": t_new / max(tot, 1),
        "new_domains_linked": n_lnk, "new_domains_linked_token_share_x1k": t_lnk / max(tot_x, 1),
        "x1k_token_share_by_value_class": {k: v / max(tot_x, 1) for k, v in con.execute(
            "SELECT CASE WHEN v IN ('free-provider', 'independent', 'unknown') THEN v ELSE 'organisation' END, "
            "sum(tokens) FROM tv GROUP BY 1 ORDER BY 1").fetchall()},
        "x1k_token_share_in_v1_domains": one("SELECT sum(tokens) FROM tv WHERE in_v1") / max(tot_x, 1),
        "x1k_sidecar_projects": len(xproj),
        "x1k_projects_with_namespace_owner": one(
            "SELECT count(*) FROM pl WHERE firm_based_on_namespace IS NOT NULL AND project IN "
            "(SELECT project FROM xns)"),
        "x1k_projects_enterprise_driven": one(
            "SELECT count(*) FROM pl WHERE project_enterprise_driven AND project IN (SELECT project FROM xns)"),
        "x1k_namespaces_new_without_owner": one("SELECT count(*) FROM ns_t"),
        "links_mapping_sha256": json.loads((a.links / "links.json").read_text())["mapping_sha256"],
    }
    tmp = a.out / ".domains.x1k.json.tmp"
    tmp.write_text(json.dumps(s, indent=1, sort_keys=True, default=float) + "\n")
    os.replace(tmp, a.out / "domains.x1k.json")
    print(json.dumps(s, indent=1, sort_keys=True, default=float))
    return 0


# ---------------------------------------------------------------- no-at
def cmd_no_at(a) -> int:
    con = duckdb.connect()
    bad = 0
    for f in a.files:
        if f.suffix == ".parquet":
            cols = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(f)]).fetchall()]
            cond = " OR ".join(f'contains(coalesce(CAST("{c}" AS VARCHAR), \'\'), chr(64))' for c in cols) or "false"
            n = con.execute(f"SELECT count(*) FROM read_parquet(?) WHERE {cond}", [str(f)]).fetchone()[0]
        else:
            n = f.read_bytes().count(AT.encode())
        print(f"{f.name}: {n} values with the at sign")
        bad += n > 0
    if bad:
        return fail(f"{bad} files hold the at sign")
    print(f"no-at OK ({len(a.files)} files)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("inputs")
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("check-cache")
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p = sub.add_parser("compare-links")
    p.add_argument("--got", type=Path, required=True)
    p.add_argument("--ref", type=Path, required=True)
    p.add_argument("--subset", action="store_true")
    p = sub.add_parser("domains")
    for o in ("--v1-cache", "--x1k-cache", "--links", "--v1-sidecar", "--x1k-sidecar", "--out"):
        p.add_argument(o, type=Path, required=True)
    p.add_argument("--memory-limit", default="8GB")
    p.add_argument("--threads", type=int, default=4)
    p = sub.add_parser("no-at")
    p.add_argument("files", type=Path, nargs="+")
    a = ap.parse_args(argv)
    return {"inputs": cmd_inputs, "check-cache": cmd_check_cache, "compare-links": cmd_compare_links,
            "domains": cmd_domains, "no-at": cmd_no_at}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
