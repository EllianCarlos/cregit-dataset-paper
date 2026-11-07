#!/usr/bin/env python3
"""brlcad_tools.py: the tools of kit dataset-brlcad (one added project file after the final write).

  select-check   the selection rules of the frame on the clone of the new host (step 1 on the machine).
  links-merge    the links of the final write (A) plus the links of the added project only (C):
                 links-A1 = A with the project row of the added project from C (the domain table of A,
                 so the mapping hash of A); links-B = A1 plus the domain rows of C that A does not have.
  registry-merge the registry of the final write (A) plus the registry of the added file (C) = the
                 registry that one run over all files gives (same rows, anchors, digest).

All outputs hold counts, hashes, organisation ids and organisation domains only: no identity value,
no address. Exit 0: ok; 1: a check failed (the message names it); 2: usage.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import duckdb

AT = chr(64)


class Fail(Exception):
    pass


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load(path: Path, name: str):
    """Import one tool file by path (the stage files, not an installed copy)."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise Fail(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------------------------------
# select-check
# --------------------------------------------------------------------------------------------------

def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check,
                          env={"GIT_TERMINAL_PROMPT": "0", "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                               "HOME": os.environ.get("HOME", "/tmp")})


def count_tree(listing: str, mask, vendor) -> dict:
    """The tree count of the frame (s3-measure/measure_clones.py count(), same rules)."""
    total = tok = tok_vendor = n_blobs = n_tok = 0
    by_ext: dict[str, int] = {}
    for line in listing.splitlines():
        meta, path = line.split("\t", 1)
        _mode, typ, _sha, size = meta.split()
        if typ != "blob" or size == "-":
            continue
        size = int(size)
        total += size
        n_blobs += 1
        name = path.rsplit("/", 1)[-1]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name[1:] else ""
        by_ext[ext] = by_ext.get(ext, 0) + size
        vend = bool(vendor.search(path))
        if mask.search(path):
            tok += size
            n_tok += 1
            if vend:
                tok_vendor += size
    return dict(total_bytes=total, n_blobs=n_blobs, tok_bytes=tok, n_tok=n_tok, tok_vendor_bytes=tok_vendor,
                by_ext=by_ext)


def measure(repo: Path, rev: str, mask, vendor, prog: set[str], dp8l) -> dict:
    m = count_tree(git(repo, "ls-tree", "-r", "-l", rev).stdout, mask, vendor)
    m["code_bytes"] = sum(v for k, v in m["by_ext"].items() if k in prog)
    own = m["tok_bytes"] - m["tok_vendor_bytes"]
    m["dp3_share"] = own / m["code_bytes"] if m["code_bytes"] else 0.0
    lic = []
    for line in git(repo, "ls-tree", rev).stdout.splitlines():
        meta, name = line.split("\t", 1)
        _mode, typ, sha = meta.split()
        if typ == "blob" and dp8l.is_license_file(name):
            lic.append(name)
        elif typ == "tree" and dp8l.is_license_dir(name) and git(repo, "ls-tree", sha).stdout.strip():
            lic.append(name + "/")
    m["license_root"] = sorted(lic)
    del m["by_ext"]
    return m


FORGE_KEEP = ("full_name", "private", "fork", "mirror", "archived", "empty", "size", "default_branch",
              "created_at", "updated_at", "clone_url", "html_url")


def forge_facts(api: str, path: str | None) -> dict:
    """The repository record of the forge API, only the fields of the frame rules (no owner, no person)."""
    if path:
        d = json.loads(Path(path).read_text())
    else:
        with urllib.request.urlopen(urllib.request.Request(api, headers={"Accept": "application/json"}),
                                    timeout=60) as r:
            d = json.loads(r.read().decode())
    return {k: d.get(k) for k in FORGE_KEEP}


def cmd_select_check(a) -> int:
    frame = json.loads(Path(a.frame).read_text())
    sel = Path(a.select_dir)
    sys.path.insert(0, str(sel))
    fm = load(sel / "file_mask.py", "file_mask")
    pe = load(sel / "prog_exts.py", "prog_exts")
    dp8l = load(sel / "dp8l_rule.py", "dp8l_rule")
    mask = re.compile(fm.UNIVERSAL_MASK)
    vendor = re.compile(r"(^|/)(vendor|vendored|third_party|third-party|thirdparty|3rdparty|external|deps)/", re.I)
    prog = pe.programming_extensions(sel / "languages.yml")
    repo, fc = Path(a.repo), frame["frame_commit"]
    rules: list[tuple[str, bool, bool, str]] = []   # (rule, ok, stops, detail)

    def rule(name: str, ok: bool, detail: str, stops: bool = True) -> None:
        rules.append((name, bool(ok), stops, detail))

    out: dict = {"project": frame["project"], "url": a.url, "frame_commit": fc}
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    branch = git(repo, "symbolic-ref", "--short", "HEAD", check=False).stdout.strip()
    out.update(head=head, branch=branch)
    present = git(repo, "cat-file", "-e", f"{fc}^{{commit}}", check=False).returncode == 0
    rule("frame commit on the new host", present, f"{fc[:12]} {'present' if present else 'MISSING'}")
    if present:
        n_frame = int(git(repo, "rev-list", "--count", fc).stdout)
        n_head = int(git(repo, "rev-list", "--count", "HEAD").stdout)
        anc = git(repo, "merge-base", "--is-ancestor", fc, "HEAD", check=False).returncode == 0
        n_before = int(git(repo, "rev-list", "--count", f"--before={frame['frame_date']}", "HEAD").stdout)
        out.update(commits_frame=n_frame, commits_head=n_head, commits_before_frame_date=n_before,
                   frame_is_ancestor_of_head=anc)
        rule("commit count at the frame commit = the frame count", n_frame == frame["commits"],
             f"{n_frame} (frame {frame['commits']})")
        rule("commit layer 5,000+ (count >= 5,000)", n_frame >= 5000, f"{n_frame}")
        rule("frame commit is an ancestor of the run head (no rewritten history)", anc,
             f"head {head[:12]} on {branch or '?'}, {n_head} commits")
        rule("commits before the frame date (information)", True,
             f"{n_before} commits of the head history before {frame['frame_date']}", stops=False)
        mf = measure(repo, fc, mask, vendor, prog, dp8l)
        out["measure_frame"] = mf
        same = all(mf[k] == frame[k] for k in ("total_bytes", "n_blobs", "tok_bytes", "n_tok", "tok_vendor_bytes",
                                               "code_bytes"))
        rule("tree count at the frame commit = the frame measurement", same,
             ", ".join(f"{k} {mf[k]}/{frame[k]}" for k in ("total_bytes", "n_blobs", "tok_bytes", "n_tok",
                                                             "tok_vendor_bytes", "code_bytes")))
        rule("DP3 at the frame commit (non-vendored tokenizable >= 5% of code bytes)", mf["dp3_share"] >= 0.05,
             f"{mf['dp3_share']:.4f}")
        rule("DP8L at the frame commit (root license file, or the license that GitHub detected)",
             bool(mf["license_root"]) or bool(frame.get("license")),
             f"root {mf['license_root'] or '-'}; frame license {frame.get('license') or '-'}")
    mh = measure(repo, "HEAD", mask, vendor, prog, dp8l)
    out["measure_head"] = mh
    rule("run head has in-scope files (else no tokens)", mh["n_tok"] > 0, f"{mh['n_tok']} files, {mh['tok_bytes']} B")
    rule("DP3 at the run head (information)", True, f"{mh['dp3_share']:.4f}", stops=False)
    rule("DP8L at the run head (information)", True, f"root {mh['license_root'] or '-'}", stops=False)
    try:
        f = forge_facts(a.forge_api, a.forge_file)
        out["forge"] = f
        rule("DP6: not archived, not a fork, not a mirror (forge API)",
             f.get("archived") is False and f.get("fork") is False and f.get("mirror") is False,
             f"archived {f.get('archived')} fork {f.get('fork')} mirror {f.get('mirror')}")
        rule("DP5: last update on or after " + frame["pushed_min"], str(f.get("updated_at") or "") >= frame["pushed_min"],
             f"updated_at {f.get('updated_at')}")
    except Exception as exc:  # noqa: BLE001 - a failed lookup is a failed rule
        rule("forge API (DP5, DP6)", False, f"no answer: {str(exc)[:120]}")
    out["rules"] = [{"rule": r, "ok": ok, "stops": st, "detail": d} for r, ok, st, d in rules]
    stop = [r for r, ok, st, _ in rules if st and not ok]
    out["result"] = "STOP: " + "; ".join(stop) if stop else "PASS"
    Path(a.out).write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    for r, ok, st, d in rules:
        print(f"{'ok  ' if ok else ('FAIL' if st else 'info')} {r}: {d}")
    print(f"select-check {out['result']}")
    return 0 if not stop else 1


# --------------------------------------------------------------------------------------------------
# links-merge
# --------------------------------------------------------------------------------------------------

LINK_FILES = ("domain_links.parquet", "project_links.parquet", "enterprise_audit.parquet")
NS_COLS = ("project", "host", "namespace", "firm_based_on_namespace")
ENT_COLS = ("project_enterprise_driven", "project_enterprise_basis")


def rows_of(con, sql: str, params=None) -> list[tuple]:
    return con.execute(sql, params or []).fetchall()


def copy_sql(con, sql: str, dst: Path) -> None:
    tmp = dst.with_name(f".{dst.name}.tmp")
    con.execute(f"COPY ({sql}) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    os.replace(tmp, dst)


def recount(con, d: Path, BL) -> dict:
    """The counts of links.json that come from the two tables (the queries of build_links.py)."""
    dl, pl = f"read_parquet('{d}/domain_links.parquet')", f"read_parquet('{d}/project_links.parquet')"
    return {
        "domain_links": con.execute(f"SELECT count(*) FROM {dl}").fetchone()[0],
        "domain_links_by_match": dict(rows_of(con, f"SELECT match, count(*) FROM {dl} GROUP BY 1 ORDER BY 1")),
        "domain_links_by_kind": dict(rows_of(con, f"SELECT organisation_kind, count(*) FROM {dl} GROUP BY 1 ORDER BY 1")),
        "projects": con.execute(f"SELECT count(*) FROM {pl}").fetchone()[0],
        "projects_with_namespace_owner": con.execute(f"SELECT count(firm_based_on_namespace) FROM {pl}").fetchone()[0],
        "projects_by_namespace_owner_kind": dict(rows_of(
            con, f"SELECT coalesce(o.kind, '(no owner)'), count(*) FROM {pl} p LEFT JOIN org o "
            "ON o.company_id = p.firm_based_on_namespace GROUP BY 1 ORDER BY 1")),
        "projects_enterprise_driven": con.execute(
            f"SELECT count(*) FILTER (WHERE project_enterprise_driven) FROM {pl}").fetchone()[0],
        "projects_by_basis": dict(rows_of(
            con, f"SELECT coalesce(project_enterprise_basis, '-'), count(*) FROM {pl} GROUP BY 1 ORDER BY 1")),
    }


def token_sums(con, cache_glob: str, dlinks: Path, BL, V0) -> dict:
    """Token sums of the cache by the classes of links.json, with the domain table dlinks (the tv table of
    build_links.py). Returns {"total": n, "by_kind": {...}, "by_value_class": {...}, "by_reason": {...},
    "company_kind": n}."""
    real = V0.real_domain_sql("a.domain")
    kinds = ", ".join(f"'{k}'" for k in BL.COMPANY_KINDS)
    con.execute(f"""CREATE OR REPLACE TEMP TABLE tv AS
      SELECT a.tokens,
             coalesce(l.firm_based_on_domain, CASE WHEN {real} THEN '{V0.UNMATCHED_REAL}' ELSE '{V0.NO_REAL_DOMAIN}' END) AS v,
             CASE WHEN l.domain IS NOT NULL THEN 'linked' WHEN {real} THEN 'unmatched real domain' ELSE 'no real domain' END AS why,
             coalesce(l.organisation_kind, CASE WHEN {real} THEN 'independent' ELSE 'unknown' END) AS kind
      FROM read_parquet('{cache_glob}') a LEFT JOIN read_parquet('{dlinks}') l ON l.domain = a.domain""")
    return {
        "total": int(con.execute("SELECT coalesce(sum(tokens), 0) FROM tv").fetchone()[0]),
        "by_kind": {k: int(v) for k, v in rows_of(con, "SELECT kind, sum(tokens) FROM tv GROUP BY 1")},
        "by_value_class": {k: int(v) for k, v in rows_of(
            con, "SELECT CASE WHEN v IN ('free-provider', 'independent', 'unknown') THEN v ELSE 'organisation' END, "
            "sum(tokens) FROM tv GROUP BY 1")},
        "by_reason": {k: int(v) for k, v in rows_of(
            con, "SELECT v || ' / ' || why, sum(tokens) FROM tv WHERE v IN ('independent', 'unknown') GROUP BY 1")},
        "company_kind": int(con.execute(f"SELECT coalesce(sum(tokens), 0) FROM tv WHERE kind IN ({kinds})").fetchone()[0]),
    }


SHARE_KEYS = (("token_share_by_kind", "by_kind"), ("token_share_by_value_class", "by_value_class"),
              ("token_share_by_reason", "by_reason"))


def sums_of_links_json(j: dict) -> dict:
    """The token sums behind the shares of a links.json (share x total, to the nearest token)."""
    t = int(j["total_tokens"])
    s = {"total": t, "company_kind": round(j["token_share_company_kind"] * t)}
    for jk, sk in SHARE_KEYS:
        s[sk] = {k: round(v * t) for k, v in j[jk].items()}
    return s


def add_sums(x: dict, y: dict) -> dict:
    out = {"total": x["total"] + y["total"], "company_kind": x["company_kind"] + y["company_kind"]}
    for _, sk in SHARE_KEYS:
        out[sk] = {k: x[sk].get(k, 0) + y[sk].get(k, 0) for k in sorted(set(x[sk]) | set(y[sk]))}
    return out


def shares_of(s: dict) -> dict:
    t = s["total"]
    out = {"total_tokens": t, "token_share_company_kind": s["company_kind"] / t}
    for jk, sk in SHARE_KEYS:
        out[jk] = {k: v / t for k, v in s[sk].items() if v}
    return out


def close(x, y, tol: float = 1e-12) -> bool:
    """Equal numbers (within tol) in the same nested dict shape."""
    if isinstance(x, dict) or isinstance(y, dict):
        return isinstance(x, dict) and isinstance(y, dict) and set(x) == set(y) and all(close(x[k], y[k], tol) for k in x)
    return abs(float(x) - float(y)) <= tol


def cmd_links_merge(a) -> int:
    T = Path(a.tools)
    sys.path.insert(0, str(T))
    V0 = load(T / "build_v0.py", "build_v0")
    BL = load(T / "build_links.py", "build_links")
    A, C, out, P = Path(a.a), Path(a.c), Path(a.out), a.project
    con = duckdb.connect(config={"memory_limit": a.memory_limit, "threads": a.threads})
    con.execute(f"ATTACH '{a.db}' AS c (READ_ONLY)")
    con.execute("CREATE TEMP TABLE org AS SELECT company_id, kind FROM c.company WHERE review_status <> 'rejected'")
    rep: list[str] = []

    def say(msg: str) -> None:
        rep.append(msg)
        print(msg)

    ja = json.loads((A / "links.json").read_text())
    if (C / "links.json").is_file():
        jc = json.loads((C / "links.json").read_text())
        c_json = "written by build_links.py"
    else:
        # build_links.py writes its 3 tables first and stops in its summary when the cache has no token of a
        # company-kind domain (sum() is NULL). The tables are complete; the summary values come from here.
        if not all((C / f).is_file() for f in LINK_FILES):
            raise Fail("C has no links.json and not all 3 tables")
        if sha256(Path(a.db)) != ja["inputs"]["db_sha256"]:
            raise Fail("the database is not the database of A")
        dropped = con.execute("SELECT count(*) FROM duckdb_tables() WHERE database_name = 'c' "
                              "AND table_name = 'company_domain_dropped'").fetchone()[0]
        nd = " AND domain NOT IN (SELECT domain FROM c.company_domain_dropped)" if dropped else ""
        n_dom = con.execute(f"SELECT count(DISTINCT domain) FROM read_parquet('{a.cache}/*.parquet') WHERE domain <> '' "
                            f"AND domain LIKE '%.%' AND domain NOT LIKE '%{AT}%'{nd}").fetchone()[0]
        jc = {"organisations_version": ja["organisations_version"], "fallback": ja["fallback"],
              "thresholds": ja["thresholds"], "dataset_domains": n_dom, "total_tokens": None,
              "domain_links": con.execute(f"SELECT count(*) FROM read_parquet('{C}/domain_links.parquet')").fetchone()[0],
              "inputs": {"db_sha256": ja["inputs"]["db_sha256"], "note": "no links.json from build_links.py "
                         "(no token of a company-kind domain); values of brlcad_tools.py"}}
        c_json = "missing (no company-kind token); summary values computed here"
    for name in LINK_FILES:
        if sha256(A / name) != ja["outputs"][name]:
            raise Fail(f"A: the sha256 of {name} is not the one in links.json")
    map_a = V0.mapping_sha256_of_files(con, A / "domain_links.parquet", A / "project_links.parquet")
    if map_a != ja["mapping_sha256"] or (a.want_mapping and map_a != a.want_mapping):
        raise Fail(f"A: mapping {map_a[:12]} is not links.json {ja['mapping_sha256'][:12]} / the pin")
    if ja["organisations_version"] != jc["organisations_version"] or ja["inputs"]["db_sha256"] != jc["inputs"]["db_sha256"]:
        raise Fail("A and C have another organisations version or database")
    for k in ("fallback", "thresholds"):
        if ja[k] != jc[k]:
            raise Fail(f"A and C differ in {k}")
    # the recount method must give the numbers of A (else this tool is wrong for the release)
    rc_a = recount(con, A, BL)
    bad = [k for k, v in rc_a.items() if ja[k] != v]
    if bad:
        raise Fail(f"the recount of A differs from its links.json in {bad}")
    da, dc = f"read_parquet('{A}/domain_links.parquet')", f"read_parquet('{C}/domain_links.parquet')"
    cols = [r[0] for r in rows_of(con, f"DESCRIBE SELECT * FROM {da}")]
    if cols != [r[0] for r in rows_of(con, f"DESCRIBE SELECT * FROM {dc}")]:
        raise Fail("the domain tables of A and C have other columns")
    sel = ", ".join(f'"{c}"' for c in cols)
    common = con.execute(f"SELECT count(*) FROM {da} x JOIN {dc} y USING (domain)").fetchone()[0]
    differ = con.execute(f"SELECT count(*) FROM (SELECT {sel} FROM {dc} WHERE domain IN (SELECT domain FROM {da}) "
                         f"EXCEPT SELECT {sel} FROM {da})").fetchone()[0]
    if differ:
        raise Fail(f"{differ} domain rows of C differ from A for the same domain (a domain row is not local)")
    con.execute(f"CREATE TEMP TABLE newd AS SELECT * FROM {dc} WHERE domain NOT IN (SELECT domain FROM {da})")
    n_new = con.execute("SELECT count(*) FROM newd").fetchone()[0]
    # the project row
    pa, pc = f"read_parquet('{A}/project_links.parquet')", f"read_parquet('{C}/project_links.parquet')"
    pcols = [r[0] for r in rows_of(con, f"DESCRIBE SELECT * FROM {pa}")]
    if pcols != [r[0] for r in rows_of(con, f"DESCRIBE SELECT * FROM {pc}")]:
        raise Fail("the project tables of A and C have other columns")
    ra = rows_of(con, f"SELECT * FROM {pa} WHERE project = ?", [P])
    rcp = rows_of(con, f"SELECT * FROM {pc} WHERE project = ?", [P])
    if len(ra) != 1 or len(rcp) != 1:
        raise Fail(f"{P}: {len(ra)} rows in A, {len(rcp)} in C (want 1 and 1)")
    ra_d, rc_d = dict(zip(pcols, ra[0])), dict(zip(pcols, rcp[0]))
    if any(ra_d[k] != rc_d[k] for k in NS_COLS):
        raise Fail(f"{P}: the namespace columns of A and C differ")
    n_cache = con.execute(f"SELECT count(DISTINCT project) FROM read_parquet('{a.cache}/*.parquet')").fetchone()[0]
    if n_cache != 1 or rows_of(con, f"SELECT DISTINCT project FROM read_parquet('{a.cache}/*.parquet')")[0][0] != P:
        raise Fail("the cache of C must hold the added project only")
    say(f"A: mapping {map_a[:12]}, {rc_a['domain_links']} domain rows, {rc_a['projects']} projects; recount = links.json")
    say(f"C: {jc['domain_links']} domain rows ({common} also in A, all equal), {n_new} not in A")
    say(f"{P}: namespace {ra_d['host']}/{ra_d['namespace']} -> {ra_d['firm_based_on_namespace']} (A = C); "
        f"enterprise A {ra_d['project_enterprise_driven']}/{ra_d['project_enterprise_basis']}, "
        f"with its cache {rc_d['project_enterprise_driven']}/{rc_d['project_enterprise_basis']}")
    psel = ", ".join(f'"{c}"' for c in pcols)
    ent_c = ", ".join(f'CASE WHEN a.project = \'{P}\' THEN c."{c}" ELSE a."{c}" END AS "{c}"' if c in ENT_COLS
                      else f'a."{c}"' for c in pcols)
    sums_a = sums_of_links_json(ja)
    cache_glob = f"{a.cache}/*.parquet"
    tc = token_sums(con, cache_glob, C / "domain_links.parquet", BL, V0)
    if jc["total_tokens"] is None:
        jc["total_tokens"] = tc["total"]
        if tc["company_kind"] != 0:
            raise Fail("C has no links.json, but its cache has company-kind tokens (build_links.py stopped for another reason)")
    elif not close(shares_of(tc), {k: jc[k] for k in shares_of(tc)}, 1e-9) or tc["total"] != jc["total_tokens"]:
        raise Fail("the token sums of C do not give the shares of its links.json (method check)")
    say(f"C links.json: {c_json}")
    results = {}
    for label in ("A1", "B"):
        d = out / f"links-{label}"
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        if label == "A1" or n_new == 0:
            shutil.copyfile(A / "domain_links.parquet", d / "domain_links.parquet")
        else:
            copy_sql(con, f"SELECT {sel} FROM (SELECT {sel} FROM {da} UNION ALL SELECT {sel} FROM newd) ORDER BY domain",
                     d / "domain_links.parquet")
        copy_sql(con, f"SELECT {psel} FROM (SELECT {ent_c} FROM {pa} a LEFT JOIN (SELECT * FROM {pc} WHERE project = "
                      f"'{P}') c USING (project)) ORDER BY project", d / "project_links.parquet")
        # the enterprise audit: the rows of A without the project, and the rows of C of the project
        ea, ec = f"read_parquet('{A}/enterprise_audit.parquet')", f"read_parquet('{C}/enterprise_audit.parquet')"
        copy_sql(con, f"SELECT * FROM (SELECT * FROM {ea} WHERE project <> '{P}' UNION ALL "
                      f"SELECT * FROM {ec} WHERE project = '{P}') ORDER BY project, commits DESC, cid",
                 d / "enterprise_audit.parquet")
        m = V0.mapping_sha256_of_files(con, d / "domain_links.parquet", d / "project_links.parquet")
        if label == "A1" and m != map_a:
            raise Fail("links-A1 has another mapping than A")
        tb = token_sums(con, cache_glob, d / "domain_links.parquet", BL, V0)
        j = dict(ja)
        j.update(recount(con, d, BL))
        j.update(shares_of(add_sums(sums_a, tb)))
        j["mapping_sha256"] = m
        j["dataset_domains"] = None
        j["dataset_domains_parts"] = {"final_write": ja["dataset_domains"], "added_project": jc["dataset_domains"]}
        j["dataset_domains_note"] = ("the distinct domains of the union are not counted: the caches of the final "
                                     "write are gone; the value of each part is its own count")
        j["inputs"] = {"final_write": ja["inputs"], "added_project": jc["inputs"],
                       "final_write_links_json_sha256": sha256(A / "links.json"),
                       "final_write_mapping_sha256": map_a, "added_project_name": P,
                       "domain_table": "final write" if label == "A1" else "final write + rows of the added project"}
        j["outputs"] = {f: sha256(d / f) for f in LINK_FILES}
        (d / "links.json").write_text(json.dumps(j, indent=1, sort_keys=True, default=float) + "\n")
        results[label] = {"mapping_sha256": m, "domain_links": j["domain_links"], "tokens_added": tb["total"],
                          "classes_of_added_project": tb["by_value_class"]}
        say(f"links-{label}: mapping {m[:12]} ({'= A' if m == map_a else 'NOT A'}); {j['domain_links']} domain rows; "
            f"{j['projects_enterprise_driven']} enterprise-driven projects; {j['total_tokens']} tokens")
    if n_new == 0 and sha256(out / "links-A1/domain_links.parquet") != sha256(out / "links-B/domain_links.parquet"):
        raise Fail("no new domain rows, but links-B and links-A1 differ")
    # what the added project loses with links-A1: the tokens of the new domain rows get the fallback
    real = V0.real_domain_sql("a.domain")
    lost = rows_of(con, f"""SELECT n.organisation_kind, n.confidence, count(DISTINCT a.domain), sum(a.tokens)
                            FROM read_parquet('{cache_glob}') a JOIN newd n USING (domain) GROUP BY 1, 2 ORDER BY 4 DESC""")
    lost_tok = sum(int(r[3]) for r in lost)
    say(f"new domain rows used by the added project: {sum(int(r[2]) for r in lost)} domains, {lost_tok} tokens "
        f"({(lost_tok / tc['total'] if tc['total'] else 0):.4%} of its {tc['total']} tokens); with links-A1 they get "
        f"'{V0.UNMATCHED_REAL}' or '{V0.NO_REAL_DOMAIN}'")
    for kind, conf, nd, tok in lost:
        say(f"  {kind} ({conf}): {nd} domains, {int(tok)} tokens")
    # the value error of links-A1: the tokens whose firm_based_on_domain is not the value that links-B gives
    # (a new row of kind independent gives the same value as the fallback)
    err = con.execute(f"""SELECT coalesce(sum(a.tokens), 0), count(DISTINCT a.domain) FROM read_parquet('{cache_glob}') a
                          JOIN newd n USING (domain) WHERE n.firm_based_on_domain IS DISTINCT FROM
                          CASE WHEN {real} THEN '{V0.UNMATCHED_REAL}' ELSE '{V0.NO_REAL_DOMAIN}' END""").fetchone()
    a1_err = int(err[0])
    say(f"value error of links-A1 for {P}: {a1_err} tokens in {err[1]} domains get another value than with links-B "
        f"({(a1_err / tc['total'] if tc['total'] else 0):.4%} of its tokens; "
        f"{a1_err / (sums_a['total'] + tc['total']):.6%} of all tokens)")
    named = rows_of(con, f"""SELECT n.domain, n.firm_based_on_domain, sum(a.tokens) FROM read_parquet('{cache_glob}') a
                             JOIN newd n USING (domain) WHERE n.confidence <> 'single-developer'
                             AND n.organisation_kind NOT IN ('independent') GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20""")
    for dom, fid, tok in named:
        say(f"  new row {dom} -> {fid}: {int(tok)} tokens")
    cls = rows_of(con, f"""SELECT CASE WHEN l.domain IS NOT NULL THEN 'in the final write table'
                                      WHEN n.domain IS NOT NULL THEN 'new row (database or free-provider match)'
                                      WHEN {real} THEN 'real domain, no row (independent)'
                                      ELSE 'no real domain (unknown)' END, count(DISTINCT a.domain), sum(a.tokens)
                           FROM read_parquet('{cache_glob}') a LEFT JOIN {da} l ON l.domain = a.domain
                           LEFT JOIN newd n ON n.domain = a.domain GROUP BY 1 ORDER BY 3 DESC""")
    say(f"tokens of {P} by domain class:")
    for c, nd, tok in cls:
        say(f"  {c}: {nd} domains, {int(tok)} tokens ({int(tok) / tc['total']:.4%})")
    summary = {"project": P, "mapping_a": map_a, "new_domain_rows": n_new, "new_rows_tokens": lost_tok,
               "a1_value_error_tokens": a1_err,
               "added_tokens": tc["total"], "links": results,
               "same_mapping": results["B"]["mapping_sha256"] == map_a}
    (out / "links-merge.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    if a.report:
        Path(a.report).write_text("\n".join(rep) + "\n")
    if any(AT in line for line in rep):
        raise Fail("the report holds the at sign")
    return 0


# --------------------------------------------------------------------------------------------------
# registry-merge
# --------------------------------------------------------------------------------------------------

def cmd_registry_merge(a) -> int:
    sys.path.insert(0, str(Path(a.anon_dir)))
    P = load(Path(a.anon_dir) / "pseudonymize.py", "pseudonymize")
    con = P.connect(a.memory_limit, a.threads, a.temp_dir)
    fa, fc = P.verify_registry_file(con, a.a), P.verify_registry_file(con, a.c)
    keys = P.derive_keys(P.A.load_salt(path=a.salt_file, env={}))
    psl = P.load_psl(a.psl)
    P.install(con, keys, email_domain=fa["email_domain"], psl=psl)
    check = P.salt_check(con)
    if a.want_a and fa["registry_sha256"] != a.want_a:
        raise Fail(f"registry A is {fa['registry_sha256'][:12]}, not the pin {a.want_a[:12]}")
    for k in ("pseudonymization_version", "email_domain", "psl_sha256", "salt_check"):
        if fa.get(k) != fc.get(k):
            raise Fail(f"registries A and C differ in {k}")
    if fa["salt_check"] != check:
        raise Fail("the salt is not the salt of registry A")
    if fa["psl_sha256"] != psl["sha256"]:
        raise Fail("the PSL is not the PSL of registry A")
    cols = ", ".join(P.REGISTRY_COLUMNS)
    con.execute(f"CREATE TEMP TABLE u AS SELECT 'a' AS src, {cols} FROM read_parquet({P.sql_str(a.a)}) "
                f"UNION ALL SELECT 'c', {cols} FROM read_parquet({P.sql_str(a.c)})")
    nx = {s: n for s, n in rows_of(con, "SELECT src, count(*) FROM u GROUP BY 1")}
    # an identity in both: the same token, pseudonym, shape and local part (the anchor is set again below)
    bad = con.execute("SELECT count(*) FROM (SELECT space, identity FROM u GROUP BY ALL "
                      "HAVING count(DISTINCT concat_ws(chr(31), coalesce(token, ''), coalesce(pseudonym, ''), "
                      "coalesce(shape, ''), coalesce(local, ''))) > 1)").fetchone()[0]
    if bad:
        raise Fail(f"{bad} identities have another pseudonym in A and C (another salt or another rule)")
    con.execute(f"CREATE TEMP TABLE anon_reg AS SELECT {', '.join(c if c != 'anchor' else 'NULL::VARCHAR AS anchor' for c in P.REGISTRY_COLUMNS)} "
                "FROM (SELECT *, row_number() OVER (PARTITION BY space, identity ORDER BY src) AS r FROM u) WHERE r = 1")
    # the anchors of the build: NULL, then _add_anchors over all name rows (an anchor depends on all names)
    P._add_anchors(con)
    collisions = rows_of(con, "SELECT space, count(*) FROM (SELECT space, token FROM anon_reg WHERE token IS NOT NULL "
                              "GROUP BY ALL HAVING count(*) > 1) GROUP BY 1")
    if collisions:
        raise Fail(f"pseudonym collisions in the union: {dict(collisions)} (the registry is refused)")
    digest = P.registry_digest(con, "anon_reg")
    counts = dict(rows_of(con, "SELECT space, count(*) FROM anon_reg GROUP BY 1"))
    kv = {"pseudonymization_version": P.SCHEME_VERSION, "registry_sha256": digest, "salt_check": check,
          "files": str(int(fa["files"]) + int(fc["files"])), "email_domain": fa["email_domain"],
          "psl_sha256": fa["psl_sha256"]}
    for s in P.ALL_SPACES:
        kv[f"n_{s}"] = str(counts.get(s, 0))
    P.check_registry_path(a.out, tuple(a.release_root or ()))
    tmp = a.out + ".tmp"
    old = os.umask(0o077)
    try:
        con.execute(f"COPY (SELECT {cols} FROM anon_reg ORDER BY space, identity) TO {P.sql_str(tmp)} "
                    f"(FORMAT PARQUET, COMPRESSION ZSTD, KV_METADATA {P._kv_sql(kv)})")
    finally:
        os.umask(old)
    os.chmod(tmp, 0o600)
    os.replace(tmp, a.out)
    got = P.verify_registry_file(con, a.out)
    new = {s: counts.get(s, 0) - int(fa.get(f"n_{s}", 0)) for s in P.ALL_SPACES}
    rep = {"registry_a": fa["registry_sha256"], "registry_c": fc["registry_sha256"], "registry_b": digest,
           "files": kv["files"], "rows_a": nx.get("a", 0), "rows_c": nx.get("c", 0),
           "identities_b": {s: counts.get(s, 0) for s in P.ALL_SPACES}, "new_in_b": new,
           "collisions": 0, "salt_check_equal": True}
    if got["registry_sha256"] != digest:
        raise Fail("the written registry does not verify")
    if a.report:
        Path(a.report).write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    print(f"registry-merge: A {fa['registry_sha256'][:12]} ({fa['files']} files) + C {fc['registry_sha256'][:12]} "
          f"({fc['files']} files) = B {digest[:12]} ({kv['files']} files); new identities {new}; 0 collisions")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("select-check")
    s.add_argument("--repo", required=True, help="a full bare clone of the new host")
    s.add_argument("--frame", required=True, help="frame.brlcad.json")
    s.add_argument("--select-dir", required=True, help="file_mask.py, prog_exts.py, languages.yml, dp8l_rule.py")
    s.add_argument("--url", required=True)
    s.add_argument("--forge-api", required=True)
    s.add_argument("--forge-file", help="a saved forge API answer (tests)")
    s.add_argument("--out", required=True)
    m = sub.add_parser("links-merge")
    m.add_argument("--tools", required=True, help="folder with build_v0.py and build_links.py")
    m.add_argument("--a", required=True, help="the links of the final write")
    m.add_argument("--c", required=True, help="build_links.py output over the cache of the added project")
    m.add_argument("--cache", required=True, help="the cache folder of the added project")
    m.add_argument("--project", required=True)
    m.add_argument("--db", required=True)
    m.add_argument("--want-mapping", default="")
    m.add_argument("--out", required=True)
    m.add_argument("--report")
    m.add_argument("--memory-limit", default="8GB")
    m.add_argument("--threads", type=int, default=4)
    r = sub.add_parser("registry-merge")
    r.add_argument("--a", required=True, help="the registry of the final write")
    r.add_argument("--c", required=True, help="the registry of the added file")
    r.add_argument("--out", required=True)
    r.add_argument("--anon-dir", required=True)
    r.add_argument("--salt-file", required=True)
    r.add_argument("--psl", required=True)
    r.add_argument("--want-a", default="")
    r.add_argument("--release-root", action="append")
    r.add_argument("--report")
    r.add_argument("--memory-limit", default="16GB")
    r.add_argument("--threads", type=int, default=4)
    r.add_argument("--temp-dir")
    a = ap.parse_args(argv)
    try:
        return {"select-check": cmd_select_check, "links-merge": cmd_links_merge,
                "registry-merge": cmd_registry_merge}[a.cmd](a)
    except Fail as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
