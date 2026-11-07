#!/usr/bin/env python3
"""Count the tokens and commits of each author e-mail in each v1 project (S8, 2026-10-16).

    extract_domains_v1.py [--jobs 3] [--memory-limit 3GB] [--threads 2] [--only NAME ...]
                          [--inputs TSV] [--cache DIR]

Input: the files that prelim.duckdb chose for v1 (table projects, column path; 3,544 files). With
--inputs TSV (2026-10-23, the extension on a machine): a tab-separated file with a header and the
columns project and path (other columns are ignored; a relative path is relative to the folder of
the TSV), in the order of the file. A project must not repeat.
Output: one small Parquet per project in ~/Projects/cregit-workspace/companies/cache/ (or --cache
DIR; index.json and the spill folder are then in the parent folder of DIR) with the
columns project, domain, email, committer_domain, tokens, commits, first_date, last_date.
`domain` is person_domain (the author of the token). `committer_domain` is the domain part of
committer_email (Spinellis et al. 2020 use committers and authors). index.json records the
size and mtime of each source, so a second start reads only new or changed files.

--person-domain-at first-valid --psl PSL [--anon-dir DIR] (2026-10-25, the final write): `domain` is
coalesce(pseudonymize.person_domain_expr(person_domain), '') of ctp-anon, the key of
build_v0.py --pseudonymize: a value with the at sign becomes its first valid domain (rule E) or ''.
Then build_links.py gives link keys that equal the published person_domain. The default `keep` is
the old key lower(trim(coalesce(person_domain, ''))). index.json records the rule of each project,
so a cache of the other rule is read again.

The cache holds e-mail addresses. Keep it out of git and out of every published file.
Each query reads only 6 columns of one file. The memory limit is small because other work runs
on this machine.
"""
import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import duckdb

WS = Path.home() / "Projects/cregit-workspace"
OUT = WS / "companies"
CACHE = OUT / "cache"
INDEX = OUT / "index.json"
LOCK = threading.Lock()

KEEP_KEY = "lower(trim(coalesce(person_domain, '')))"
SQL = """
COPY (
  SELECT $project AS project,
         {domain} AS domain,
         lower(trim(coalesce(person_email, ''))) AS email,
         lower(trim(coalesce(split_part(committer_email, '@', 2), ''))) AS committer_domain,
         count(*)::BIGINT AS tokens,
         count(DISTINCT original_commit_sha)::BIGINT AS commits,
         min(author_date) AS first_date, max(author_date) AS last_date
  FROM read_parquet($src)
  GROUP BY ALL
) TO $dst (FORMAT PARQUET, COMPRESSION ZSTD)
"""


def usage(msg: str) -> None:
    print(f"usage: {msg}", file=sys.stderr)
    raise SystemExit(2)


def read_inputs(tsv: Path) -> list[tuple[str, str]]:
    """(project, path) rows of an --inputs file, in file order. Exit 2 on a bad file."""
    with open(tsv, newline="") as fh:
        rd = csv.DictReader(fh, delimiter="\t")
        if not {"project", "path"} <= set(rd.fieldnames or ()):
            usage(f"{tsv} needs the columns project and path")
        rows = list(rd)
    out, seen = [], set()
    for r in rows:
        p, src = (r["project"] or "").strip(), (r["path"] or "").strip()
        if not p or not src:
            usage(f"{tsv} has a row with no project or no path")
        if p in seen:
            usage(f"{tsv}: project {p} repeats")
        seen.add(p)
        src = src if os.path.isabs(src) else str(tsv.parent / src)
        if not os.path.isfile(src):
            usage(f"{tsv}: the file of project {p} is missing")
        out.append((p, src))
    return out


def one(project: str, src: str, a) -> tuple[str, dict | None, str]:
    dst = a.cache / f"{project}.parquet"
    tmp = a.cache / f".{project}.tmp.parquet"
    spill = a.cache.parent / "spill" / project
    t0 = time.time()
    try:
        con = duckdb.connect(config={"memory_limit": a.memory_limit, "threads": a.threads,
                                     "temp_directory": str(spill), "preserve_insertion_order": False})
        try:
            if a.person_domain_at == "keep":
                key = KEEP_KEY
            else:
                a.P.install(con, None, psl=a.psl_data)
                key = f"coalesce({a.P.person_domain_expr('person_domain', a.person_domain_at)}, '')"
            con.execute(SQL.format(domain=key), {"project": project, "src": src, "dst": str(tmp)})
        finally:
            con.close()
        os.replace(tmp, dst)
        st = os.stat(src)
        rec = {"src": src, "size": st.st_size, "mtime": st.st_mtime, "seconds": round(time.time() - t0, 1)}
        if a.person_domain_at != "keep":
            rec["domain_rule"] = a.person_domain_at
        return project, rec, ""
    except Exception as exc:  # one project fails, the others go on
        tmp.unlink(missing_ok=True)
        return project, None, str(exc)[:300]
    finally:
        if spill.exists():
            for f in spill.iterdir():
                f.unlink(missing_ok=True)
            spill.rmdir()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--memory-limit", default="3GB")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--inputs", type=Path, help="TSV with project and path (default: prelim.duckdb)")
    ap.add_argument("--cache", type=Path, default=CACHE, help=f"output folder (default {CACHE})")
    ap.add_argument("--person-domain-at", choices=("keep", "first-valid"), default="keep",
                    help="the domain key: keep (lower/trim) or first-valid (rule E of pseudonymize.py)")
    ap.add_argument("--psl", type=Path, help="the Public Suffix List (with first-valid)")
    ap.add_argument("--anon-dir", type=Path, help="folder of pseudonymize.py (default: ./anon, then .)")
    a = ap.parse_args(argv)
    a.P = a.psl_data = None
    if a.person_domain_at != "keep":
        if not a.psl or not a.psl.is_file():
            usage("--person-domain-at first-valid needs --psl FILE")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from build_v0 import load_pseudonymize
        a.P = load_pseudonymize(a.anon_dir)
        a.psl_data = a.P.load_psl(str(a.psl))
    elif a.psl or a.anon_dir:
        usage("--psl and --anon-dir need --person-domain-at first-valid")
    a.cache = a.cache.resolve()
    index_file = a.cache.parent / "index.json"  # the default cache gives INDEX
    a.cache.mkdir(parents=True, exist_ok=True)
    index = json.loads(index_file.read_text()) if index_file.is_file() else {}
    if a.inputs:
        rows = read_inputs(a.inputs)
    else:
        con = duckdb.connect(str(WS / "merge-prelim/prelim.duckdb"), read_only=True)
        rows = con.execute("SELECT project, path FROM projects ORDER BY token_rows DESC").fetchall()
        con.close()
    todo = []
    for project, src in rows:
        if a.only and project not in a.only:
            continue
        st = os.stat(src)
        old = index.get(project)
        if old and old["src"] == src and old["size"] == st.st_size and old["mtime"] == st.st_mtime \
                and old.get("domain_rule", "keep") == a.person_domain_at \
                and (a.cache / f"{project}.parquet").is_file():
            continue
        todo.append((project, src))
    print(f"{len(rows)} projects, {len(todo)} to read; jobs {a.jobs}", flush=True)
    failed = 0
    with ThreadPoolExecutor(a.jobs) as ex:
        for n, (project, rec, err) in enumerate(ex.map(lambda r: one(*r, a), todo), 1):
            if rec is None:
                failed += 1
                print(f"FAIL {project}: {err}", flush=True)
                continue
            with LOCK:
                index[project] = rec
                if n % 25 == 0 or n == len(todo):
                    tmp = index_file.with_suffix(".tmp")
                    tmp.write_text(json.dumps(index, indent=0, sort_keys=True))
                    os.replace(tmp, index_file)
            if n % 100 == 0 or n == len(todo):
                print(f"{n}/{len(todo)} read ({failed} failed)", flush=True)
    tmp = index_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(index, indent=0, sort_keys=True))
    os.replace(tmp, index_file)
    print(f"done: {len(index)} projects in the cache, {failed} failed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
