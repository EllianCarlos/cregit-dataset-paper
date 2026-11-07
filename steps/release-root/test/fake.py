"""Fake data for the tests and the rehearsal of kit dataset-release (no real data, no person value).

make_source(dir, projects, registry, links) writes a fake release folder of a final write: parquet/ with schema 2
files (fill_release.SCHEMA_2) and their footers, SHA256SUMS (project files only), results.tsv, links.json (with
machine paths in `inputs`, as the real ones), domain_links.parquet, project_links.parquet, pseudonymization.json.
The final writes are files of release 1: their footers and links.json have the old (British) spelling of the keys
(organisations_version, organisations_mapping_sha256), and the link tables and the error model have the column
names of release 1.
make_input(dir, projects, mapping) writes a fake input prefix of release 2: parquet/ with the new keys
(organizations_version, organizations_mapping_sha256), organizations/ with small fake tables of the release names
and dataset.duckdb, and SHA256SUMS (sums=True; project files and the files of organizations/, as U2 writes it).
make_links(dir, db, projects) writes the link tables with organization ids of the database DB and the mapping hash
of build_v0.py; make_error_model(dir, links) writes the three files that build_organisations.py (the tool of
release 1) reads.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import duckdb

# FILL_RELEASE: fill_release.py (default: the copy in ../fill-release/). COMPANIES_DB: the organization database v4.9.
# BUILD_V0_DIR: the folder of build_v0.py (default: the copy of the organization step in this repository).
FILL_RELEASE = Path(os.environ.get("FILL_RELEASE", Path(__file__).resolve().parents[1] / "fill-release/tools/fill_release.py"))
BUILD_V0_DIR = Path(os.environ.get("BUILD_V0_DIR", Path(__file__).resolve().parents[2] / "organizations/study/s8-companies"))
DB = Path(os.environ.get("COMPANIES_DB", "COMPANIES_DB-is-not-set"))
MAPPING_FAKE = "7b" * 32
REG_A = "ca" * 32
REG_B = "56" * 32
PSEUDO_KEYS = {"commit_summary": "keep", "email_domain": "first-valid", "leak_scan": True,
               "leak_scan_content_columns": False, "person_domain_at": "first-valid", "psl_sha256": "ab" * 32,
               "pseudonymization_version": "2", "salt_check": "0f" * 7}


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def schema2():
    sys.dont_write_bytecode = True
    return load(FILL_RELEASE, "fill_release_fake").SCHEMA_2


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def literal(name: str, typ: str, project: str) -> str:
    if name == "clone_url":
        return f"'https://example.org/{project}.git' AS {name}"
    if name == "size_class":
        return f"'M' AS {name}"
    if name == "commits":
        return f"'5432' AS {name}"
    if name == "person_domain":
        return f"(CASE WHEN i % 2 = 0 THEN 'alpha.example' ELSE 'beta.example' END) AS {name}"
    if typ == "VARCHAR[]":
        return f"[]::VARCHAR[] AS {name}"
    if typ == "BIGINT":
        return f"i::BIGINT AS {name}"
    if typ == "BOOLEAN":
        return f"false AS {name}"
    return f"'x' AS {name}"


# The footer keys of the organizations version and the mapping hash: release 2 (new) and release 1 (old spelling).
NEW_KEYS = ("organizations_version", "organizations_mapping_sha256")
OLD_KEYS = ("organisations_version", "organisations_mapping_sha256")
ORG_FILES = ("organizations", "organization_domains", "organization_namespaces", "project_organizations",
             "link_error", "release_info")


def write_project(out: Path, project: str, rows: int, registry: str, mapping: str = MAPPING_FAKE,
                  ov: str = "v4.9", columns=None, extra_kv: dict | None = None, old_keys: bool = False) -> None:
    cols = columns if columns is not None else schema2()
    sel = ", ".join(literal(n, t, project) for n, t in cols)
    kov, kmap = OLD_KEYS if old_keys else NEW_KEYS
    kv = {"ctp_schema_version": "2", kov: ov, kmap: mapping,
          "pseudonymization_version": "2", "pseudonymization_registry_sha256": registry}
    kv.update(extra_kv or {})
    kvs = ", ".join(f"{k}: '{v}'" for k, v in kv.items())
    out.parent.mkdir(parents=True, exist_ok=True)
    duckdb.execute(f"COPY (SELECT {sel} FROM range({rows}) t(i)) TO '{out}' (FORMAT parquet, KV_METADATA {{{kvs}}})")


def org_ids(db: Path = DB, n: int = 3) -> list[str]:
    con = duckdb.connect()
    con.execute(f"ATTACH '{db}' AS c (READ_ONLY)")
    ids = [r[0] for r in con.execute("SELECT company_id FROM c.company WHERE company_id NOT IN "
                                     "('free-provider', 'independent', 'unknown') ORDER BY company_id LIMIT ?", [n]).fetchall()]
    con.close()
    return ids


def make_links(d: Path, projects: list[str], db: Path = DB, total_tokens: int = 100) -> dict:
    d.mkdir(parents=True, exist_ok=True)
    ids = org_ids(db)
    con = duckdb.connect()
    dom = [("alpha.example", ids[0], "company", "exact", "alpha.example", "high", "gitdm"),
           ("beta.example", ids[1], "company", "suffix", "beta.example", "high", "claude-proposal-v2"),
           ("mail.example", "free-provider", "free-provider", "exact", "mail.example", "high", "rule"),
           ("solo.example", "independent", "independent", "exact", "solo.example", "low", "rule")]
    # the column names of the link tables of the final writes (release 1; build_v0.py of release 1)
    con.execute("CREATE TABLE d (domain VARCHAR, firm_based_on_domain VARCHAR, organisation_kind VARCHAR, match VARCHAR,"
                " matched_domain VARCHAR, confidence VARCHAR, source VARCHAR)")
    con.executemany("INSERT INTO d VALUES (?, ?, ?, ?, ?, ?, ?)", dom)
    con.execute("CREATE TABLE p (project VARCHAR, host VARCHAR, namespace VARCHAR, firm_based_on_namespace VARCHAR,"
                " project_enterprise_driven BOOLEAN, project_enterprise_basis VARCHAR)")
    con.executemany("INSERT INTO p VALUES (?, 'example.org', ?, ?, false, 'none')",
                    [(p, p.split("__")[0], ids[2] if i % 2 else "unknown") for i, p in enumerate(sorted(projects))])
    con.execute(f"COPY (FROM d ORDER BY domain) TO '{d}/domain_links.parquet' (FORMAT parquet)")
    con.execute(f"COPY (FROM p ORDER BY project) TO '{d}/project_links.parquet' (FORMAT parquet)")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(BUILD_V0_DIR))
    import build_v0 as bv
    mapping = bv.mapping_sha256_of_files(con, d / "domain_links.parquet", d / "project_links.parquet")
    lj = {"dataset_domains": 4, "domain_links": len(dom), "fallback": {"no_real_domain": "unknown",
          "unmatched_real_domain": "independent"},
          "inputs": {"caches": ["/data2/final/work/links/v1/cache", "/data2/final/work/links/x1k/cache"],
                     "db": "/data/final/tools/companies.v4.9.duckdb",
                     "sidecars": ["/data1/final/in/v1/project_meta.v1.final.json"]},
          "mapping_sha256": mapping, OLD_KEYS[0]: "v4.9",            # links.json of a final write (release 1)
          "outputs": {"domain_links.parquet": sha(d / "domain_links.parquet"),
                      "enterprise_audit.parquet": "ee" * 32,
                      "project_links.parquet": sha(d / "project_links.parquet")},
          "projects": len(projects), "token_share_by_reason": {"independent / linked": 0.1,
          "independent / unmatched real domain": 0.2, "unknown / no real domain": 0.05}, "total_tokens": total_tokens}
    (d / "links.json").write_text(json.dumps(lj, indent=1, sort_keys=True) + "\n")
    return lj


def make_error_model(em: Path, links: Path) -> None:
    """The three files of the error model of release 1 (their names and columns are the ones of release 1)."""
    em.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    key = "left(sha256('s8-error-model:' || domain), 16)"
    con.execute(f"COPY (SELECT {key} AS key_hash, 'x/a/b/c' AS error_stratum, 0.02::DOUBLE AS p_error "
                f"FROM read_parquet('{links}/domain_links.parquet')) TO '{em}/organisation_domains_p_error.parquet' (FORMAT parquet)")
    con.execute(f"COPY (SELECT {key} AS key_hash, 10::BIGINT AS tokens FROM read_parquet('{links}/domain_links.parquet')) "
                f"TO '{em}/link_error.parquet' (FORMAT parquet)")
    (em / "other_sources.csv").write_text("source,organisation_share_of_proposals_pct\nproposals,4.5\n")


def make_source(d: Path, projects: list[tuple[str, int, str]], registry: str, links: Path | None = None,
                mapping: str | None = None) -> None:
    """projects: (name, rows, input prefix); links: a folder of make_links (its files are copied)."""
    (d / "parquet").mkdir(parents=True, exist_ok=True)
    if links is not None:
        for f in ("links.json", "domain_links.parquet", "project_links.parquet"):
            (d / f).write_bytes((links / f).read_bytes())
        mapping = mapping or json.loads((links / "links.json").read_text())["mapping_sha256"]
    mapping = mapping or MAPPING_FAKE
    rows_out = []
    for name, rows, prefix in projects:
        out = d / "parquet" / f"{name}-dataset.parquet"
        write_project(out, name, rows, registry, mapping, old_keys=True)
        rows_out.append({"project": name, "input": f"{prefix}/parquet/{name}-dataset.parquet", "input_sha256": "11" * 32,
                         "output": f"parquet/{name}-dataset.parquet", "output_sha256": sha(out), "rows": rows,
                         "input_bytes": 1, "output_bytes": out.stat().st_size, "seconds": 1.0,
                         "finished_utc": "2026-10-27T00:00:00Z", "detail": "OK fake"})
    rows_out.sort(key=lambda r: r["output"])
    with open(d / "SHA256SUMS", "w") as fh:
        for r in rows_out:
            fh.write(f"{r['output_sha256']}  {r['output']}\n")
    with open(d / "results.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows_out[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows_out)
    (d / "pseudonymization.json").write_text(json.dumps({**PSEUDO_KEYS, "registry_sha256": registry}, indent=1,
                                                        sort_keys=True) + "\n")


def make_input(d: Path, projects: list[tuple[str, int, str]], mapping: str, sums: bool = True) -> None:
    """The input prefix of release 2. projects: (name, rows, registry). The tables are small fake tables."""
    (d / "parquet").mkdir(parents=True, exist_ok=True)
    rows = []
    for name, n, registry in projects:
        out = d / "parquet" / f"{name}-dataset.parquet"
        write_project(out, name, n, registry, mapping)
        rows.append((sha(out), f"parquet/{name}-dataset.parquet"))
    org = d / "organizations"
    org.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for t in ORG_FILES:
        if t == "release_info":           # one key and one value in each row; fill_release.py reads mapping_sha256
            con.execute(f"COPY (SELECT * FROM (VALUES ('mapping_sha256', '{mapping}'), ('organizations_version', 'v4.9')) "
                        f"t(key, value)) TO '{org}/{t}.parquet' (FORMAT parquet)")
        else:
            con.execute(f"COPY (SELECT 'fake-{t}' AS organization_id, range AS n FROM range(2)) TO '{org}/{t}.parquet' "
                        f"(FORMAT parquet)")
    dbf = duckdb.connect(str(org / "dataset.duckdb"))
    dbf.execute("CREATE VIEW organizations AS SELECT 'fake' AS organization_id")
    dbf.close()
    rows += [(sha(f), f"organizations/{f.name}") for f in sorted(org.iterdir()) if f.is_file()]   # the U2 form
    if sums:
        (d / "SHA256SUMS").write_text("".join(f"{h}  {r}\n" for h, r in sorted(rows, key=lambda x: x[1])))


def make_ledgers(d: Path, rows: dict[str, int], skip: tuple = (), other_rows: tuple = (), no_rows: tuple = ()) -> None:
    """Fake ledgers: one live ledger with all projects (except skip), one ledger.rows.jsonl of a done folder, and a
    test ledger with wrong commits (it must be skipped)."""
    def rec(p, r, commit):
        return {"v": 1, "run_id": "20261001T000000Z-1", "project": p, "step": "project", "status": "done",
                "end_utc": "2026-10-01T00:00:00+00:00", "checked_out_sha": commit, "snapshot_sha": "f" * 40,
                "tools": {"cregit_commit": "c" * 40, "ctp_commit": "d" * 40}, "parquet": {"rows": r}}
    live = d / "batch2/live/ledger.jsonl"
    live.parent.mkdir(parents=True, exist_ok=True)
    with open(live, "w") as fh:
        fh.write(json.dumps({"v": 1, "step": "run-start"}) + "\n")
        for p, r in sorted(rows.items()):
            if p in skip:
                continue
            x = rec(p, r + (1 if p in other_rows else 0), "a" * 40)
            if p in no_rows:
                del x["parquet"]
            fh.write(json.dumps(x) + "\n")
            fh.write(json.dumps({**x, "step": "clone", "status": "ok"}) + "\n")
    first = sorted(rows)[0]
    done = d / f"dataset-x1k/done-full/{first}/ledger.rows.jsonl"
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text(json.dumps(rec(first, rows[first], "a" * 40)) + "\n")
    test = d / "batch2/live/ledger.test.jsonl"
    test.write_text("".join(json.dumps({**rec(p, r, "9" * 40), "end_utc": "2026-12-01"}) + "\n" for p, r in rows.items()))


def run_rows(p: str, rows: int, run_id: str = "20261001T000000Z-11", extra_note: bool = False) -> tuple[list, dict]:
    """The ledger rows of one fake ctp run of project p in the form of ProjectRun.base() and record(): attempt 1
    stops at the clone, attempt 2 ends done. The rows hold machine paths, machine state, a Nix store path, a user
    name and (with extra_note) machine values and an identity key, as a test of ledger-clean. Returns the rows and
    the record of the done row (the form of ledger.proven.jsonl)."""
    sha, snap, cregit, ctp = "a" * 40, "f" * 40, "c" * 40, "d" * 40
    run_sha = hashlib.sha256(p.encode()).hexdigest()

    def base(att):
        return {"v": 1, "run_id": run_id, "project": p, "queue_pos": 2, "queue_total": 9, "attempt": att,
                "manifest_row": {"name": p, "url": f"https://example.org/{p}.git", "commit": snap,
                                 "file_filter": "(?i)\\.(c|h)$", "size_class": "S"},
                "pinned_sha": sha, "snapshot_sha": snap, "checked_out_sha": "", "file_mask_sha256": "e" * 64,
                "tools": {"ctp_commit": ctp, "cregit_commit": cregit,
                          "srcml_path": "/nix/store/0abc-srcml-1.1.0/bin/srcml"},
                "flags": {"argv": ["census", "--manifest", "/home/ec2-user/in/manifest.b1.tsv"],
                          "cli": {"manifest": "/home/ec2-user/in/manifest.b1.tsv", "workers": 4},
                          "config_path": "/etc/ctp/b1.cfg", "config_sha256": "0" * 64,
                          "cregit_dir": "/w/cregit-ec2", "output_dir": "/b4p1/out-b1"}}

    def rec(att, step, status, t0, t1, **extra):
        r = base(att)
        r.update(step=step, status=status, start_utc=f"2026-10-01T00:00:{t0:02d}+00:00",
                 end_utc=f"2026-10-01T00:00:{t1:02d}+00:00", duration_s=float(t1 - t0), **extra)
        return r

    pq = {"bytes": 1000 + rows, "path": f"/data3/x1k/out/{p}/{p}-dataset.parquet", "rows": rows, "sha256": run_sha}
    argv = ["python3", "/data3/x1k/ctp/pin.py", "--dest", f"/data3/x1k/out/.ctp-pinned/{p}.git", f"--out=/tmp/{p}"]
    out = [rec(1, "resolve", "ok", 0, 1),
           rec(1, "clone", "started", 1, 1, argv=argv),
           rec(1, "clone", "failed", 1, 2, argv=argv, exit_code=128, log=f"/data3/x1k/ctp/state/{p}/logs/clone.log"),
           rec(1, "project", "failed", 0, 2, state="failed", failed_step="clone"),
           rec(2, "resolve", "ok", 3, 4, resolve={"url": f"https://example.org/{p}.git", "branch": "main",
                                                   "seeded": "copied by ec2-user from /home/ec2-user/seed/latest.json"}),
           rec(2, "clone", "ok", 4, 5, argv=argv, exit_code=0, log=f"/data3/x1k/ctp/state/{p}/logs/clone.log",
               pin={"dest": f"/data3/x1k/out/.ctp-pinned/{p}.git", "url": f"https://example.org/{p}.git",
                    "checked_out_sha": sha}),
           rec(2, "validate", "ok", 5, 6, exit_code=0, parquet=pq),
           rec(2, "cleanup", "ok", 6, 7, cleanup={"bytes_freed": 9, "kept": [f"{p}-dataset.parquet"],
                                                  "removed": [f"/data3/x1k/out/.ctp-pinned/{p}.git"],
                                                  "removed_bytes": {f"/data3/x1k/out/{p}/memo": 9}})]
    if extra_note:
        out[6]["note"] = "ran on i-0123456789abcdef0 at 10.1.2.3"
        out[6]["author"] = "a person"
    for r in out[4:]:
        r["checked_out_sha"] = sha
    out.append({**rec(2, "project", "done", 3, 8, state="done", parquet=pq), "checked_out_sha": sha})
    record = {"step": "project", "status": "done", "project": p, "end_utc": out[-1]["end_utc"],
              "checked_out_sha": sha, "snapshot_sha": snap, "tools": {"cregit_commit": cregit, "ctp_commit": ctp}}
    return out, record


def make_run_ledgers(d: Path, rows: dict[str, int], copy: tuple = (), note: tuple = ()) -> list[dict]:
    """Fake run ledgers of the projects (name -> rows) in one batch ledger with a run-start row and the rows of
    another project run; for the projects of copy, a second copy of the done attempt in done/<p>/ledger.rows.jsonl
    (in another key order); a test ledger and a gate/ ledger with a done row of another run (both must be skipped).
    Returns the records of the done rows."""
    live = d / "batch1/live/ledger.jsonl"
    live.parent.mkdir(parents=True, exist_ok=True)
    recs = []
    with open(live, "w") as fh:
        fh.write(json.dumps({"v": 1, "step": "run-start", "run_id": "20261001T000000Z-11",
                             "host": "ip-10-0-0-1.ec2.internal"}) + "\n")
        for p, r in sorted(rows.items()):
            rs, rec = run_rows(p, r, extra_note=p in note)
            recs.append(rec)
            for x in rs:
                fh.write(json.dumps(x) + "\n")
            if p in copy:
                c = d / f"dataset-x1k/done/{p}/ledger.rows.jsonl"
                c.parent.mkdir(parents=True, exist_ok=True)
                c.write_text("".join(json.dumps(dict(reversed(list(x.items())))) + "\n" for x in rs if x["attempt"] == 2))
            other, _ = run_rows(p, r + 1, run_id="20261002T000000Z-22")
            for x in other[:2]:
                fh.write(json.dumps(x) + "\n")
    first = sorted(rows)[0]
    rs, _ = run_rows(first, rows[first], run_id="20261009T000000Z-99")
    (d / "batch1/live/ledger.test.jsonl").write_text(json.dumps(rs[-1]) + "\n")
    (d / "gate").mkdir(exist_ok=True)
    (d / "gate/ledger.jsonl").write_text(json.dumps(rs[-1]) + "\n")
    return recs
