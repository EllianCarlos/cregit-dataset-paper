#!/usr/bin/env python3
"""Write dataset v0 (S8, decisions D1 and D5): one v1-raw Parquet with the organisation columns.

    build_v0.py SRC DST --project NAME --project-links P.parquet --domain-links D.parquet
                 --organisations-version V [--memory-limit 10GB] [--threads 2]

The output has ctp schema version 2 (LINK_COLUMNS_DESIGN.md section 2, approved 2026-10-19):
  version 1  the 70 columns of v1-raw: the 67 columns of cregit and the metadata, then firm_raw,
             firm and firm_source (validate_schema.EXPECTED_COLUMNS of ctp ca113e3).
  version 2  the 67 columns in the same order, then the 4 columns of ORG_COLUMNS. The 3 firm
             columns of the old gitdm map (RETIRED_COLUMNS) leave the file.
SRC is a v1-raw file. DST gets the same rows in the same order. The organisation columns:
  firm_based_on_namespace    per project, from --project-links (the `owns` organisation, else NULL);
  firm_based_on_domain       per row: the id of lower(trim(person_domain)) in --domain-links; else
                             `independent` if the value is a real domain (not blank, a dot, no at
                             sign); else `unknown` (the user, 2026-10-19). Never NULL;
  project_enterprise_driven, project_enterprise_basis   per project, from --project-links (D3).
The Parquet footer gets 3 key-value entries: ctp_schema_version, organisations_version and
organisations_mapping_sha256 (mapping_sha256 below: the domain map, the namespace owners and the
two fallback rules; a change of a name or a kind of an organisation does not change it).

The join must not move a row. So the script sorts only a narrow table (file_row_number and a small
domain index) and joins it by position to the file read in order. Checks before the rename: the
row count, an order-sensitive hash of the 67 kept columns (file_row_number included) in SRC and in
DST, the column list, no NULL firm_based_on_domain, and the footer entries. The encoding is the v1
encoding (ZSTD 19, 1 M-row groups, Parquet V2).
build_links.py imports the rules from this file, so that both use one definition.

--pseudonymize (the final write, 2026-10-25; release plan step 7, decision D1): the same SELECT goes
to pseudonymize.write_public() of ctp-anon as its source relation, so the organisation columns and
the pseudonyms come from one read and one ZSTD 19 encode. Options:
    --pseudonymize --salt-file S --registry R.parquet --psl PSL [--registry-sha256 H]
    [--anon-dir DIR] [--commit-summary keep] [--person-domain-at first-valid] [--no-scan]
    [--no-content-scan] [--scan-threads N]
The salt comes from the file S only (never from the environment); the tool never prints it, and
each error message goes through pseudonymize.safe_error(). The registry R (pseudonymize.py
registry, one invocation over all input files) must have the salt check of S, the sha256 of PSL and
the e-mail domain rule of this write; --registry-sha256 (run_v0.py gives it after one full check)
must equal its footer, else the full digest is computed here. In this mode:
  - the domain key is coalesce(pseudonymize.person_domain_expr(person_domain), ''): rule E for a
    value with the at sign (the published person_domain), so the key equals the value in the file;
    the links must be built with the same rule (extract_domains_v1.py --person-domain-at);
  - the order hash compares the passthrough columns only (not the identity columns, which change),
    and person_domain of SRC through the same expression;
  - the footer also gets pseudonymization_version and pseudonymization_registry_sha256;
  - each identity column must hold pseudonyms only (pseudonymize.identity_shape_violations; NULL and
    '' stay), and pseudonymize.leak_scan() must find no leak (unless --no-scan; --no-content-scan
    skips the information columns, whose findings never fail the gate: the release run uses it);
  - DST is renamed into place only when every check passed.
Without --pseudonymize the old path runs unchanged (the published v1 run stays reproducible).
Exit 0 written, 1 a check failed, 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent

CTP_SCHEMA_VERSION = "2"
ENCODING = "FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 19, ROW_GROUP_SIZE 1000000, PARQUET_VERSION V2"
PROJECT_COLS = (("firm_based_on_namespace", "VARCHAR"), ("project_enterprise_driven", "BOOLEAN"),
                ("project_enterprise_basis", "VARCHAR"))
ORG_COLUMNS = (("firm_based_on_namespace", "VARCHAR"), ("firm_based_on_domain", "VARCHAR"),
               ("project_enterprise_driven", "BOOLEAN"), ("project_enterprise_basis", "VARCHAR"))
# The firm columns of v1-raw (ctp schema 1). They leave v1-public; v1-raw keeps them.
RETIRED_COLUMNS = ("firm_raw", "firm", "firm_source")
# The 12 link columns of the first v0 (company database v3). A file with them is not a v1-raw file.
OLD_V0_COLUMNS = ("namespace_company_id", "namespace_company", "namespace_company_relation",
                  "namespace_company_evidence", "domain_company_id", "domain_company", "domain_company_kind",
                  "domain_company_confidence", "author_is_company", "author_is_insider",
                  "project_enterprise_driven", "project_enterprise_basis")
# The two fallback values of firm_based_on_domain (the user, 2026-10-19).
UNMATCHED_REAL = "independent"     # a real domain with no row in the domain links
NO_REAL_DOMAIN = "unknown"         # blank, no dot, or a value with the at sign (an address, a git-svn id)
DOMAIN_KEY = "lower(trim(coalesce({c}, '')))"


def real_domain_sql(expr: str) -> str:
    """SQL: true when the normalized value is a real domain (not blank, a dot, no at sign)."""
    return f"({expr} <> '' AND contains({expr}, '.') AND NOT contains({expr}, chr(64)))"


def mapping_sha256(domain_pairs, project_pairs) -> str:
    """sha256 of the mapping that the files copy: the sorted (domain, id) pairs, the sorted
    (project, firm_based_on_namespace) pairs, and the two fallback rules."""
    h = hashlib.sha256()
    h.update(f"rule\tunmatched-real-domain\t{UNMATCHED_REAL}\nrule\tno-real-domain\t{NO_REAL_DOMAIN}\n".encode())
    for d, i in sorted((str(d), i or "") for d, i in domain_pairs):
        h.update(f"d\t{d}\t{i}\n".encode())
    for p, i in sorted((str(p), i or "") for p, i in project_pairs):
        h.update(f"p\t{p}\t{i}\n".encode())
    return h.hexdigest()


def mapping_sha256_of_files(con, dlinks: Path, plinks: Path) -> str:
    return mapping_sha256(
        con.execute("SELECT domain, firm_based_on_domain FROM read_parquet(?)", [str(dlinks)]).fetchall(),
        con.execute("SELECT project, firm_based_on_namespace FROM read_parquet(?)", [str(plinks)]).fetchall())


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sql_lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def columns(con, path: Path) -> list[str]:
    return [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]


def column_types(con, path: Path) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]


def order_hash(con, path: Path, cols: list[str], exprs: list[str] | None = None):
    """(rows, order-sensitive hash). `exprs` (default: the quoted names of `cols`) are SQL
    expressions over the columns of PATH."""
    exprs = exprs or [q(c) for c in cols]
    return con.execute(
        f"SELECT count(*), bit_xor(hash(file_row_number, {', '.join(exprs)})) "
        "FROM read_parquet(?, file_row_number = true)", [str(path)]).fetchone()


# --------------------------------------------------------------------------------------------
# --pseudonymize: the fused write with pseudonymize.py of ctp-anon
# --------------------------------------------------------------------------------------------

@dataclass
class Anon:
    """What the fused write needs. Made once per process by prepare_anon()."""
    P: object                  # the module pseudonymize
    keys: tuple[str, str]      # the two keys of the salt (never printed)
    psl: dict                  # pseudonymize.load_psl()
    registry: Path
    registry_sha256: str
    summary_mode: str = "keep"
    domain_at: str = "first-valid"
    scan: bool = True
    content_scan: bool = True  # False: the leak scan skips the information columns (they never fail it)
    scan_threads: int | None = None  # DuckDB threads of the leak scan (default: --threads of the write)


def load_pseudonymize(anon_dir: Path | None = None):
    """The module pseudonymize (with anonymize_parquet and validate_schema in its folder): from
    `anon_dir`, else HERE/anon, else HERE. The module must come from that folder."""
    cands = [anon_dir] if anon_dir else [HERE / "anon", HERE]
    d = next((Path(c).resolve() for c in cands if (Path(c) / "pseudonymize.py").is_file()), None)
    if d is None:
        raise FileNotFoundError(f"no pseudonymize.py in {', '.join(str(c) for c in cands)}")
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))
    import pseudonymize
    got = Path(pseudonymize.__file__).resolve().parent
    if got != d:
        raise ImportError(f"pseudonymize comes from {got}, not from {d}")
    return pseudonymize


def prepare_anon(P, salt_file: Path, registry: Path, psl_path: Path, registry_sha256: str | None = None,
                 summary_mode: str = "keep", domain_at: str = "first-valid", scan: bool = True,
                 content_scan: bool = True) -> Anon:
    """The keys from the salt file, the PSL, and the checks of the registry against both:
    pseudonymization_version, salt_check, psl_sha256, email_domain, registry_sha256 (the footer,
    or the full digest when `registry_sha256` is None). Raises on a mismatch."""
    keys = P.derive_keys(P.A.load_salt(path=str(salt_file), env={}))
    psl = P.load_psl(str(psl_path))
    con = duckdb.connect()
    try:
        meta = P.registry_meta(con, str(registry)) if registry_sha256 else P.verify_registry_file(con, str(registry))
        if meta.get(P.FOOTER_VERSION_KEY) != P.SCHEME_VERSION:
            raise P.RegistryError(f"the registry has {P.FOOTER_VERSION_KEY} {meta.get(P.FOOTER_VERSION_KEY)}, "
                                  f"not {P.SCHEME_VERSION}")
        if registry_sha256 and meta.get("registry_sha256") != registry_sha256:
            raise P.RegistryError("the registry footer sha256 is not --registry-sha256")
        if meta.get("psl_sha256") != psl["sha256"]:
            raise P.RegistryError("the registry was made with another Public Suffix List")
        if meta.get("email_domain") != P.DEFAULT_EMAIL_DOMAIN:
            raise P.RegistryError(f"the registry has the e-mail domain rule {meta.get('email_domain')}, "
                                  f"not {P.DEFAULT_EMAIL_DOMAIN}")
        P.install(con, keys, psl=psl)
        if P.salt_check(con) != meta.get("salt_check"):
            raise P.RegistryError("the salt is not the salt of the registry (salt check)")
    finally:
        con.close()
    return Anon(P, keys, psl, registry, meta["registry_sha256"], summary_mode, domain_at, scan, content_scan)


def footer(con, path: Path) -> dict:
    return dict(con.execute("SELECT decode(key), decode(value) FROM parquet_kv_metadata(?)",
                            [str(path)]).fetchall())


def project_row(con, links: Path, project: str) -> dict:
    names = [c for c, _ in PROJECT_COLS]
    rows = con.execute(f"SELECT {', '.join(names)} FROM read_parquet(?) WHERE project = ?",
                       [str(links), project]).fetchall()
    if len(rows) > 1:
        raise ValueError(f"{project}: {len(rows)} rows in the project links")
    return dict(zip(names, rows[0])) if rows else dict.fromkeys(names)


def write(src: Path, dst: Path, project: str, plinks: Path, dlinks: Path, version: str,
          memory_limit: str, threads: int, anon: Anon | None = None) -> str:
    # The checks raise Err: in the fused write pseudonymize.WriteError (the class for the checks of
    # a caller), whose text (counts and column names only) safe_error() shows; another error shows
    # its class only.
    Err = RuntimeError if anon is None else anon.P.WriteError
    tmp = dst.with_name(f".{dst.name}.v0-tmp")
    spill = dst.with_name(f".{dst.name}.v0-spill")
    con = duckdb.connect(config={"memory_limit": memory_limit, "threads": threads,
                                 "temp_directory": str(spill), "preserve_insertion_order": True})
    try:
        cols = columns(con, src)
        bad = set(cols) & ({c for c, _ in ORG_COLUMNS} | set(OLD_V0_COLUMNS))
        if "person_domain" not in cols or bad:
            raise Err(f"{src}: not a v1-raw file (person_domain missing or link columns present: "
                             f"{sorted(bad)})")
        keep = [c for c in cols if c not in RETIRED_COLUMNS]
        p = project_row(con, plinks, project)
        con.execute("CREATE TEMP TABLE d AS SELECT row_number() OVER (ORDER BY domain)::INTEGER AS di, "
                    "domain, firm_based_on_domain FROM read_parquet(?)", [str(dlinks)])
        n, rep, nulls = con.execute("SELECT count(*), count(*) - count(DISTINCT domain), "
                                    "count(*) - count(firm_based_on_domain) FROM d").fetchone()
        if rep or nulls:
            raise Err(f"{dlinks}: {rep} repeated domains, {nulls} rows with no id")
        ids = [r[0] for r in con.execute("SELECT firm_based_on_domain FROM d ORDER BY di").fetchall()]
        ids += [UNMATCHED_REAL, NO_REAL_DOMAIN]
        mapping = mapping_sha256_of_files(con, dlinks, plinks)
        # The narrow table in file order: one small index per row into the id list.
        if anon is None:
            key = DOMAIN_KEY.format(c="person_domain")
        else:  # rule E: the key is the published person_domain (pseudonymize.person_domain_expr)
            anon.P.install(con, anon.keys, psl=anon.psl)
            key = f"coalesce({anon.P.person_domain_expr('person_domain', anon.domain_at)}, '')"
        narrow = (f"SELECT x.rn, coalesce(d.di, CASE WHEN {real_domain_sql('x.k')} THEN {n + 1} ELSE {n + 2} END) "
                  f"AS di FROM (SELECT file_row_number AS rn, {key} AS k "
                  "FROM read_parquet($src, file_row_number = true)) x LEFT JOIN d ON d.domain = x.k ORDER BY x.rn")
        pvals = ", ".join(f"CAST($p_{c} AS {t}) AS {q(c)}" for c, t in PROJECT_COLS)
        dval = "list_extract($ids::VARCHAR[], n.di) AS firm_based_on_domain"
        sel = f"SELECT t.*, {pvals}, {dval} FROM read_parquet($src) t POSITIONAL JOIN ({narrow}) n"
        want = keep + [c for c, _ in ORG_COLUMNS]
        kv = {"ctp_schema_version": CTP_SCHEMA_VERSION, "organisations_version": version,
              "organisations_mapping_sha256": mapping}
        kvs = ", ".join(f"{k}: {sql_lit(v)}" for k, v in kv.items())
        params = {"src": str(src), "ids": ids, **{f"p_{k}": v for k, v in p.items()}}
        if anon is None:
            con.execute(f"COPY (SELECT {', '.join(q(c) for c in want)} FROM ({sel})) TO '{tmp}' "
                        f"({ENCODING}, KV_METADATA {{{kvs}}})", params)
            hashed, src_exprs = keep, None
        else:
            P = anon.P
            types = dict(column_types(con, src))
            schema = [(c, types[c]) for c in keep] + list(ORG_COLUMNS)
            res = P.write_public(con, str(src), str(tmp), registry=str(anon.registry),
                                 registry_sha256=anon.registry_sha256,
                                 source_sql=f"SELECT {', '.join(q(c) for c in want)} FROM ({sel})",
                                 source_params=params, kv=kv, source_schema=schema,
                                 summary_mode=anon.summary_mode, domain_at=anon.domain_at)
            if res["problems"]:
                raise Err(f"{project}: pseudonymize: " + "; ".join(map(str, res["problems"]))[:600])
            plan = res["plan"]
            # The identity columns change; person_domain of SRC goes through the published expression.
            hashed = [c for c in keep if c in plan.passthrough]
            src_exprs = [P.person_domain_expr(q(c), anon.domain_at) if c == "person_domain" else q(c)
                         for c in hashed]
            kv = {**kv, P.FOOTER_VERSION_KEY: P.SCHEME_VERSION, P.FOOTER_REGISTRY_KEY: anon.registry_sha256}
        a, b = order_hash(con, src, hashed, src_exprs), order_hash(con, tmp, hashed)
        if a != b:
            raise Err(f"{project}: the {len(hashed)} kept columns differ after the write ({a} vs {b})")
        got = columns(con, tmp)
        if got != want:
            raise Err(f"{project}: columns {got[-6:]} are not {want[-6:]}")
        fk = footer(con, tmp)
        if any(fk.get(k) != v for k, v in kv.items()):
            raise Err(f"{project}: footer keys {sorted(fk)} do not hold the values of {sorted(kv)}")
        anon_msg = ""
        if anon is not None:
            bad = P.identity_shape_violations(con, f"SELECT * FROM read_parquet({sql_lit(str(tmp))})", plan)
            if bad:
                raise Err(f"{project}: values that are not pseudonyms (distinct values per column): {bad}")
            scan_msg = "scan off"
            if anon.scan:
                if anon.scan_threads and anon.scan_threads != threads:  # the ordered write is fastest with 1
                    con.execute(f"SET threads = {int(anon.scan_threads)}")
                sc = P.leak_scan(con, str(tmp), str(anon.registry), content=anon.content_scan)
                if sc["failures"]:
                    raise Err(f"{project}: leak scan: {len(sc['failures'])} failures: "
                                       + "; ".join(map(str, sc["failures"][:5]))[:600])
                scan_msg = (f"scan ok ({len(sc.get('reported') or [])} information columns reported)"
                            if anon.content_scan else "scan ok (information columns skipped)")
            anon_msg = (f"; pseudonyms: {res['identity_values']} identity values, registry "
                        f"{anon.registry_sha256[:12]}, {scan_msg}")
        c = con.execute(
            "SELECT count(*) FILTER (WHERE firm_based_on_domain IS NULL), "
            f"count(*) FILTER (WHERE firm_based_on_domain = '{UNMATCHED_REAL}'), "
            f"count(*) FILTER (WHERE firm_based_on_domain = '{NO_REAL_DOMAIN}'), "
            "count(*) FILTER (WHERE firm_based_on_domain = firm_based_on_namespace) "
            "FROM read_parquet(?)", [str(tmp)]).fetchone()
        if c[0]:
            raise Err(f"{project}: {c[0]} rows with no firm_based_on_domain")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    finally:
        con.close()
        shutil.rmtree(spill, ignore_errors=True)
    os.replace(tmp, dst)
    return (f"{a[0]} rows; {c[1]} independent; {c[2]} unknown; {c[3]} insider rows; "
            f"namespace {p['firm_based_on_namespace'] or '-'}; schema {CTP_SCHEMA_VERSION}; mapping {mapping[:12]}"
            + anon_msg)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--project", required=True)
    ap.add_argument("--project-links", type=Path, required=True)
    ap.add_argument("--domain-links", type=Path, required=True)
    ap.add_argument("--organisations-version", required=True, help="for example v4.1")
    ap.add_argument("--memory-limit", default="10GB")
    ap.add_argument("--threads", type=int, default=2)
    g = ap.add_argument_group("the fused write with pseudonymize.py (see the module docstring)")
    g.add_argument("--pseudonymize", action="store_true")
    g.add_argument("--salt-file", type=Path)
    g.add_argument("--registry", type=Path)
    g.add_argument("--registry-sha256", help="the registry_sha256 of the registry footer (skips the full digest)")
    g.add_argument("--psl", type=Path, help="the Public Suffix List of the registry")
    g.add_argument("--anon-dir", type=Path, help="folder of pseudonymize.py (default: ./anon, then .)")
    g.add_argument("--commit-summary", default="keep", help="pseudonymize --commit-summary (default keep)")
    g.add_argument("--person-domain-at", default="first-valid", help="pseudonymize --person-domain-at")
    g.add_argument("--no-scan", action="store_true", help="no leak scan of the output")
    g.add_argument("--scan-threads", type=int, help="DuckDB threads of the leak scan (default: --threads)")
    g.add_argument("--no-content-scan", action="store_true",
                   help="the leak scan skips the information columns (pseudonymize --no-content-scan; their "
                        "findings never fail the gate)")
    a = ap.parse_args(argv)
    if a.pseudonymize:
        miss = [o for o, v in (("--salt-file", a.salt_file), ("--registry", a.registry), ("--psl", a.psl)) if not v]
        if miss:
            print(f"usage: --pseudonymize needs {', '.join(miss)}", file=sys.stderr)
            return 2
    elif any((a.salt_file, a.registry, a.registry_sha256, a.psl, a.anon_dir, a.no_scan, a.no_content_scan,
              a.scan_threads)):
        print("usage: --salt-file, --registry, --registry-sha256, --psl, --anon-dir, --no-scan and "
              "--no-content-scan need --pseudonymize", file=sys.stderr)
        return 2
    for f in (a.src, a.project_links, a.domain_links) + ((a.registry, a.psl) if a.pseudonymize else ()):
        if not f.is_file():
            print(f"usage: {f} is not a file", file=sys.stderr)
            return 2
    if a.dst.exists():
        print(f"usage: {a.dst} exists", file=sys.stderr)
        return 2
    anon, P = None, None
    if a.pseudonymize:
        try:
            P = load_pseudonymize(a.anon_dir)
            anon = prepare_anon(P, a.salt_file, a.registry, a.psl, a.registry_sha256, a.commit_summary,
                                a.person_domain_at, not a.no_scan, not a.no_content_scan)
            anon.scan_threads = a.scan_threads
        except Exception as exc:  # a salt, PSL or registry error: the message names no value
            print(f"usage: {P.safe_error(exc, None) if P else exc}", file=sys.stderr)
            return 2
    try:
        msg = write(a.src, a.dst, a.project, a.project_links, a.domain_links, a.organisations_version,
                    a.memory_limit, a.threads, anon)
    except Exception as exc:
        text = P.safe_error(exc, anon.keys) if anon else str(exc)
        print(f"FAIL {a.src}: {text}", file=sys.stderr)
        return 1
    print(f"OK {a.dst}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
