#!/usr/bin/env python3
"""measure.py: measure four review findings (M4, M7, M9, M10) on the release
Parquet files of the cregit token dataset. Counts only.

Commands:
  run ROOT       measure each project of ROOT/MANIFEST.tsv, in parallel, with
                 resume (a project with a done marker is skipped), then write
                 the summary.
  summary OUT    merge the per-project TSVs of OUT into the summary files.
  m9-global ROOT the distinct person_domain values per class over all files
                 (one value is in many projects; the per-project counts do not
                 add up to this number).
  m9-sample ROOT write at most 20 values of the classes that are not
                 'registrable' to the private folder (mode 700).

The findings (tool-review-20261028/findings.tsv):
  M4  srcml2token can exit 0 after a xerces fatal error. Then the token stream
      of the file stops and has no end_unit. Per file: the begin_unit and
      end_unit counts and their positions.
  M7  commit_summary can end in ' Former-commit-id: <40 hex>'. Per project:
      the distinct commits with this end.
  M9  a person_domain value with no at sign is published as lower(trim(value)).
      Per project: distinct values and token rows per class (registrable, ip,
      local_host, other) of the Public Suffix List rule of the pseudonymizer.
  M10 a ';' in an earlier file name (field 2 of a .blame line) shifts the
      split of generate_dataset.py: token_type gets 'name.c;<TAB>DECL'.
      Per project: rows and files with the symptom, and rows and files with
      a ';' in file_path.

Privacy: no output file outside the private folder holds a person_domain
value, a name or an address. A file_path is written with '%', TAB, LF, CR,
'\\' and the at sign (code point 64) percent-encoded. The summary step stops
with an error if an output file holds the at sign.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import glob
import hashlib
import json
import os
import re
import resource
import sys
import time
import traceback

AT = chr(64)
TAB = chr(9)
FINDING_GROUPS = ("m4m10", "m7", "m9")
PINNED_PSL_SHA256 = "65365c4c9a4a6f746d53aadc758ab6b08aa10bb1379fea8ac353e381bca4b62e"
PSL_GLOB = "/nix/store/*-publicsuffix-list-*/share/publicsuffix/public_suffix_list.dat"
DEFAULT_OUT_BASE = os.environ.get("MEASURE_OUT_BASE", "measure-out")
DEFAULT_PRIVATE = os.path.join(DEFAULT_OUT_BASE, "private")
# The same character rule as STRICT_DOMAIN of pseudonymize.py (ctp a4b511b).
STRICT_DOMAIN = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*"
LOCAL_SUFFIXES = ("local", "lan", "localdomain", "localhost", "home", "internal",
                  "intranet", "corp", "private", "localnet", "domain", "invalid",
                  "test", "example", "workgroup")
M7_END = " Former-commit-id: [0-9a-f]{40}$"
M7_ONLY = "^Former-commit-id: [0-9a-f]{40}$"
SHIFT_SQL = (f"(contains(token_type, ';' || chr(9)) OR "
             f"(token_type = 'unknown' AND contains(token_value, ';' || chr(9))))")
M4_FLAGS = ("cut_off", "no_begin", "multi_unit", "end_not_last", "begin_not_first",
            "index_gap", "m10_shift", "rust_prefix")


# ---------------------------------------------------------------- helpers

def log(msg: str, fh=None) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line, flush=True)
    if fh is not None:
        fh.write(line + "\n")
        fh.flush()


def enc(value) -> str:
    """Percent-encode the characters that break a TSV row or that the
    privacy rule forbids (the at sign)."""
    s = "" if value is None else str(value)
    for ch, rep in (("%", "%25"), ("\\", "%5C"), (TAB, "%09"), ("\n", "%0A"),
                    ("\r", "%0D"), (AT, "%40")):
        s = s.replace(ch, rep)
    return s


def write_tsv(target: str, header: list[str], rows) -> None:
    """Write a TSV atomically (temporary file, then rename)."""
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = f"{target}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(TAB.join(header) + "\n")
        for r in rows:
            fh.write(TAB.join(enc(v) for v in r) + "\n")
    os.replace(tmp, target)


def read_tsv(src: str) -> list[dict]:
    with open(src, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=TAB, quoting=csv.QUOTE_NONE))


def mem_available() -> int:
    with open("/proc/meminfo") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    return 0


def gib(n: float) -> str:
    return f"{n / 2**30:.2f} GiB"


def sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


# ---------------------------------------------------------------- PSL

def find_psl(want_sha: str) -> str | None:
    for p in sorted(glob.glob(PSL_GLOB)):
        if file_sha256(p) == want_sha:
            return p
    return None


def file_sha256(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_psl(p: str) -> dict:
    """The ICANN section of the Public Suffix List, read as load_psl of
    pseudonymize.py (ctp a4b511b) reads it."""
    rules, wild, exc = set(), set(), set()
    icann = False
    with open(p, "rb") as fh:
        data = fh.read()
    for line in data.decode("utf-8").splitlines():
        line = line.strip()
        if "===BEGIN ICANN DOMAINS===" in line:
            icann = True
        elif "===END ICANN DOMAINS===" in line:
            icann = False
        if not icann or not line or line.startswith("//"):
            continue
        rule = line.split()[0].lower()
        if not rule.isascii() and not rule.startswith(("*", "!")):
            rule = rule.encode("idna").decode()
        if rule.startswith("!"):
            exc.add(rule[1:])
        elif rule.startswith("*."):
            wild.add(rule[2:])
        else:
            rules.add(rule)
    tlds = {r.rsplit(".", 1)[-1] for r in rules} | {w.rsplit(".", 1)[-1] for w in wild}
    return {"rules": sorted(rules), "wild": sorted(wild), "exc": sorted(exc),
            "tlds": sorted(tlds), "sha256": hashlib.sha256(data).hexdigest(), "path": p}


def install_psl(con, psl: dict) -> None:
    for name in ("rules", "wild", "exc", "tlds"):
        con.execute(f"CREATE OR REPLACE TEMP TABLE psl_{name} (v VARCHAR PRIMARY KEY)")
        vals = psl[name] or ["-"]
        con.execute(f"INSERT INTO psl_{name} SELECT DISTINCT unnest(?::VARCHAR[])", [vals])


def m9_class_sql(v: str) -> str:
    """SQL, 'class/subclass' of the lower-case value `v`. The 'registrable'
    test is valid_domain_sql of pseudonymize.py (rule E)."""
    tld = f"regexp_extract({v}, '[^.]+$')"
    strict = f"regexp_full_match({v}, {sql_str(STRICT_DOMAIN)})"
    valid = (f"({strict} AND strpos({v}, '.') > 0 AND "
             f"(({tld} IN (SELECT v FROM psl_tlds) AND {v} NOT IN (SELECT v FROM psl_rules) "
             f"AND substr({v}, strpos({v}, '.') + 1) NOT IN (SELECT v FROM psl_wild)) "
             f"OR {v} IN (SELECT v FROM psl_exc)))")
    is_suffix = (f"({v} IN (SELECT v FROM psl_rules) OR {v} IN (SELECT v FROM psl_tlds) "
                 f"OR substr({v}, strpos({v}, '.') + 1) IN (SELECT v FROM psl_wild))")
    local = ", ".join(sql_str(s) for s in LOCAL_SUFFIXES)
    ipv4 = r"\[?(?:[0-9]{1,3}\.){3}[0-9]{1,3}\]?"
    ipv6 = r"\[?(?:[0-9a-f]{0,4}:){2,7}(?:[0-9a-f]{0,4}|(?:[0-9]{1,3}\.){3}[0-9]{1,3})\]?"
    return (f"CASE WHEN {v} = '' THEN 'empty/empty' "
            f"WHEN regexp_full_match({v}, {sql_str(ipv4)}) THEN 'ip/ipv4' "
            f"WHEN regexp_full_match({v}, {sql_str(ipv6)}) THEN 'ip/ipv6' "
            f"WHEN {valid} THEN 'registrable/registrable' "
            f"WHEN {v} = '(none)' OR ends_with({v}, '.(none)') THEN 'local_host/none_suffix' "
            f"WHEN strpos({v}, '.') > 0 AND {tld} IN ({local}) THEN 'local_host/local_suffix' "
            f"WHEN {strict} AND {is_suffix} THEN 'other/public_suffix_only' "
            f"WHEN {v} IN ({local}) OR regexp_full_match({v}, '[a-z0-9_-]+') "
            f"THEN 'local_host/single_label' "
            f"WHEN {strict} AND {tld} NOT IN (SELECT v FROM psl_tlds) "
            f"THEN 'local_host/no_public_suffix' "
            f"ELSE 'other/bad_chars' END")


# ---------------------------------------------------------------- DuckDB

def connect(mem: str, threads: int, tmpdir: str | None):
    import duckdb
    con = duckdb.connect()
    con.execute(f"SET memory_limit = {sql_str(mem)}")
    con.execute(f"SET threads = {int(threads)}")
    con.execute("SET preserve_insertion_order = false")
    con.execute("SET enable_progress_bar = false")
    if tmpdir:
        os.makedirs(tmpdir, exist_ok=True)
        con.execute(f"SET temp_directory = {sql_str(tmpdir)}")
        con.execute("SET max_temp_directory_size = '50GB'")
    return con


# ---------------------------------------------------------------- measures

def measure_m4m10(con, src: str) -> tuple[dict, list, dict, list]:
    """Per-file unit markers (M4) and the ';' split symptom (M10).

    A marker can have a prefix that ends in a TAB: 'name.c;<TAB>begin_unit'
    (the M10 shift) or '-:-<TAB>begin_unit' (the Rust position prefix of
    cregit before 57551d7, a known defect). The end marker with a prefix has
    no pipe, so generate_dataset.py writes token_type 'unknown' and puts the
    line in token_value. The 'repaired' counts include these markers."""
    t = f"read_parquet({sql_str(src)})"
    tab = "chr(9)"
    bpre = f"(token_type <> 'begin_unit' AND ends_with(token_type, {tab} || 'begin_unit'))"
    epre = f"(token_type = 'unknown' AND ends_with(token_value, {tab} || 'end_unit'))"
    m10t = f"contains(token_type, ';' || {tab})"
    m10v = f"contains(token_value, ';' || {tab})"
    rust_b = f"regexp_full_match(token_type, '([0-9]+|-):([0-9]+|-)' || {tab} || 'begin_unit')"
    rust_e = f"regexp_full_match(token_value, '([0-9]+|-):([0-9]+|-)' || {tab} || 'end_unit')"
    begin_any = f"(token_type = 'begin_unit' OR {bpre})"
    end_any = f"(token_type = 'end_unit' OR {epre})"
    # A blank line with a prefix: token_type 'unknown', token_value ends in TAB.
    blank_any = f"(token_type = 'blank' OR (token_type = 'unknown' AND ends_with(token_value, {tab})))"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE pf AS
        SELECT file_path,
          count(*) AS n_tokens,
          min(token_index) AS min_index,
          max(token_index) AS last_index,
          count(*) FILTER (WHERE token_type = 'begin_unit') AS n_begin,
          count(*) FILTER (WHERE token_type = 'end_unit') AS n_end,
          count(*) FILTER (WHERE {bpre} AND {m10t}) AS n_begin_m10,
          count(*) FILTER (WHERE {epre} AND {m10v}) AS n_end_m10,
          count(*) FILTER (WHERE {bpre} AND {rust_b}) AS n_begin_rust,
          count(*) FILTER (WHERE {epre} AND {rust_e}) AS n_end_rust,
          count(*) FILTER (WHERE {SHIFT_SQL}) AS n_shift,
          min(token_index) FILTER (WHERE {begin_any}) AS first_begin,
          max(token_index) FILTER (WHERE {end_any}) AS last_end,
          max(token_index) FILTER (WHERE NOT {blank_any} AND NOT {end_any}) AS last_content,
          count(*) FILTER (WHERE contains(token_type, {tab}) AND NOT {m10t}) AS n_type_tab
        FROM {t} GROUP BY file_path""")
    con.execute("""CREATE OR REPLACE TEMP TABLE pf2 AS SELECT *,
          n_begin + n_begin_m10 + n_begin_rust AS nb,
          n_end + n_end_m10 + n_end_rust AS ne FROM pf""")
    con.execute("""CREATE OR REPLACE TEMP TABLE pf3 AS SELECT *,
          (ne = 0) AS cut_off,
          (nb = 0) AS no_begin,
          (nb > 1 OR ne > 1) AS multi_unit,
          (last_end IS NOT NULL AND last_content IS NOT NULL AND last_content > last_end)
              AS end_not_last,
          (first_begin IS NOT NULL AND first_begin <> 0) AS begin_not_first,
          (min_index <> 0 OR last_index + 1 <> n_tokens) AS index_gap,
          (n_shift > 0) AS m10_shift,
          (n_begin_rust + n_end_rust > 0) AS rust_prefix,
          NOT (n_begin = 1 AND n_end = 1) AS not_1_1_raw,
          NOT (nb = 1 AND ne = 1) AS not_1_1_repaired
        FROM pf2""")
    flag_cols = ", ".join(M4_FLAGS)
    files = con.execute(f"""SELECT file_path, lower(regexp_extract(file_path, '\\.([^./]+)$', 1)),
          n_tokens, n_begin, n_end, n_begin_m10, n_end_m10, n_begin_rust, n_end_rust,
          first_begin, last_end, last_content, last_index, n_shift, {flag_cols}
        FROM pf3 WHERE not_1_1_raw OR {' OR '.join(M4_FLAGS)}
        ORDER BY file_path""").fetchall()
    agg = con.execute(f"""SELECT count(*), coalesce(sum(n_tokens), 0),
          count(*) FILTER (WHERE not_1_1_raw), count(*) FILTER (WHERE not_1_1_repaired),
          {', '.join(f'count(*) FILTER (WHERE {f})' for f in M4_FLAGS)},
          coalesce(sum(n_tokens) FILTER (WHERE cut_off), 0),
          count(*) FILTER (WHERE not_1_1_raw AND NOT m10_shift AND NOT rust_prefix),
          count(*) FILTER (WHERE not_1_1_raw AND m10_shift),
          count(*) FILTER (WHERE not_1_1_raw AND rust_prefix),
          coalesce(sum(n_type_tab), 0)
        FROM pf3""").fetchone()
    names = (["files", "token_rows", "files_not_1_1_raw", "files_not_1_1_after_repair"]
             + [f"files_{f}" for f in M4_FLAGS]
             + ["token_rows_in_cut_off_files", "files_not_1_1_raw_not_m10_not_rust_prefix",
                "files_not_1_1_raw_by_m10", "files_not_1_1_raw_by_rust_prefix",
                "rows_tab_in_token_type_not_m10"])
    m4 = dict(zip(names, agg))
    m10agg = con.execute(f"""SELECT
          count(*) FILTER (WHERE {SHIFT_SQL}),
          count(DISTINCT file_path) FILTER (WHERE {SHIFT_SQL}),
          count(*) FILTER (WHERE contains(token_type, ';' || chr(9))),
          count(*) FILTER (WHERE token_type = 'unknown' AND contains(token_value, ';' || chr(9))),
          count(*) FILTER (WHERE {SHIFT_SQL} AND is_structural = 0),
          count(*) FILTER (WHERE contains(file_path, ';')),
          count(DISTINCT file_path) FILTER (WHERE contains(file_path, ';'))
        FROM {t}""").fetchone()
    m10 = dict(zip(["rows_shift", "files_shift", "rows_shift_in_token_type",
                    "rows_shift_in_token_value_unknown", "rows_shift_is_structural_0",
                    "rows_path_semicolon", "files_path_semicolon"], m10agg))
    m10files = con.execute(f"""SELECT file_path,
          count(*) FILTER (WHERE {SHIFT_SQL}), count(*), contains(file_path, ';')
        FROM {t} WHERE {SHIFT_SQL} OR contains(file_path, ';')
        GROUP BY file_path ORDER BY file_path""").fetchall()
    con.execute("DROP TABLE pf3; DROP TABLE pf2; DROP TABLE pf")
    return m4, files, m10, m10files


def measure_m7(con, src: str) -> tuple[dict, list]:
    t = f"read_parquet({sql_str(src)})"
    con.execute(f"""CREATE OR REPLACE TEMP TABLE pc AS
        SELECT cregit_commit_sha AS c, any_value(original_commit_sha) AS o,
               any_value(commit_summary) AS s, count(*) AS n
        FROM {t} GROUP BY cregit_commit_sha""")
    agg = con.execute(f"""SELECT count(*),
          count(*) FILTER (WHERE regexp_matches(s, {sql_str(M7_END)})),
          count(*) FILTER (WHERE regexp_matches(s, {sql_str(M7_ONLY)})),
          count(*) FILTER (WHERE contains(s, 'Former-commit-id:')),
          coalesce(sum(n) FILTER (WHERE regexp_matches(s, {sql_str(M7_END)})), 0),
          coalesce(sum(n), 0)
        FROM pc""").fetchone()
    m7 = dict(zip(["commits", "commits_footer_end", "commits_footer_only",
                   "commits_footer_anywhere", "token_rows_footer_end", "token_rows"], agg))
    commits = con.execute(f"""SELECT c, o, n FROM pc
        WHERE regexp_matches(s, {sql_str(M7_END)}) ORDER BY c""").fetchall()
    con.execute("DROP TABLE pc")
    return m7, commits


def measure_m9(con, src: str) -> tuple[dict, list]:
    t = f"read_parquet({sql_str(src)})"
    agg = con.execute(f"""SELECT count(*),
          count(*) FILTER (WHERE person_domain IS NULL),
          count(*) FILTER (WHERE person_domain IS NOT NULL AND strpos(person_domain, chr(64)) > 0)
        FROM {t}""").fetchone()
    rows = con.execute(f"""WITH d AS (
          SELECT lower(trim(person_domain)) AS v, count(*) AS n FROM {t}
          WHERE person_domain IS NOT NULL AND strpos(person_domain, chr(64)) = 0 GROUP BY 1),
        k AS (SELECT {m9_class_sql('v')} AS cls, v, n FROM d)
        SELECT split_part(cls, '/', 1), split_part(cls, '/', 2), count(*), sum(n)
        FROM k GROUP BY cls ORDER BY cls""").fetchall()
    m9 = {"token_rows": agg[0], "rows_null": agg[1], "rows_with_at_sign": agg[2]}
    return m9, rows


# ---------------------------------------------------------------- worker

def out_paths(out: str, project: str) -> dict:
    return {
        "m4": os.path.join(out, "m4", f"{project}.tsv"),
        "m4files": os.path.join(out, "m4", f"{project}.files.tsv"),
        "m10": os.path.join(out, "m10", f"{project}.tsv"),
        "m10files": os.path.join(out, "m10", f"{project}.files.tsv"),
        "m7": os.path.join(out, "m7", f"{project}.tsv"),
        "m7commits": os.path.join(out, "m7", f"{project}.commits.tsv"),
        "m9": os.path.join(out, "m9", f"{project}.tsv"),
    }


def done_marker(out: str, project: str, group: str) -> str:
    return os.path.join(out, "done", f"{project}.{group}")


def measure_project(job: dict) -> dict:
    """Measure one project. Runs in a worker process."""
    project, src, out, groups = job["project"], job["src"], job["out"], job["groups"]
    t0 = time.time()
    res = {"project": project, "ok": False, "groups": [], "seconds": 0.0, "error": ""}
    try:
        if not os.path.isfile(src):
            raise FileNotFoundError("Parquet file not found")
        size = os.path.getsize(src)
        if job.get("bytes") and int(job["bytes"]) != size:
            raise ValueError(f"size {size} differs from MANIFEST bytes {job['bytes']}")
        con = connect(job["mem"], job["threads"],
                      os.path.join(out, "tmp", f"{os.getpid()}"))
        p = out_paths(out, project)
        if "m4m10" in groups:
            m4, files, m10, m10files = measure_m4m10(con, src)
            write_tsv(p["m4files"], ["project", "file_path", "ext", "n_tokens", "n_begin_unit",
                                     "n_end_unit", "n_begin_unit_m10", "n_end_unit_m10",
                                     "n_begin_unit_rust_prefix", "n_end_unit_rust_prefix",
                                     "first_begin_index", "last_end_index", "last_content_index",
                                     "last_index", "rows_m10"] + list(M4_FLAGS),
                      [[project] + list(r[:14]) + [int(bool(x)) for x in r[14:]] for r in files])
            write_tsv(p["m4"], ["project"] + list(m4), [[project] + list(m4.values())])
            write_tsv(p["m10files"], ["project", "file_path", "rows_shift", "rows",
                                      "path_has_semicolon"],
                      [[project, r[0], r[1], r[2], int(bool(r[3]))] for r in m10files])
            write_tsv(p["m10"], ["project"] + list(m10), [[project] + list(m10.values())])
            touch(done_marker(out, project, "m4m10"))
            res["groups"].append("m4m10")
        if "m7" in groups:
            m7, commits = measure_m7(con, src)
            write_tsv(p["m7commits"], ["project", "cregit_commit_sha", "original_commit_sha",
                                       "token_rows"], [[project] + list(r) for r in commits])
            write_tsv(p["m7"], ["project"] + list(m7), [[project] + list(m7.values())])
            touch(done_marker(out, project, "m7"))
            res["groups"].append("m7")
        if "m9" in groups:
            install_psl(con, job["psl"])
            m9, rows = measure_m9(con, src)
            write_tsv(p["m9"], ["project", "class", "subclass", "distinct_values", "token_rows"],
                      [[project] + list(r) for r in rows]
                      + [[project, "meta", k, "", v] for k, v in m9.items()])
            touch(done_marker(out, project, "m9"))
            res["groups"].append("m9")
        con.close()
        res["ok"] = True
        res["bytes"] = size
    except Exception as e:  # report and go on with the next project
        res["error"] = f"{type(e).__name__}: {e}".replace("\n", " ")[:2000]
        res["trace"] = traceback.format_exc()[-4000:]
    res["seconds"] = round(time.time() - t0, 2)
    res["maxrss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    return res


def touch(p: str) -> None:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        fh.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")


# ---------------------------------------------------------------- run

def read_manifest(root: str, manifest: str | None) -> list[dict]:
    mf = manifest or os.path.join(root, "MANIFEST.tsv")
    rows = read_tsv(mf)
    jobs = []
    for r in rows:
        rel = r.get("path") or f"parquet/{r['project']}-dataset.parquet"
        jobs.append({"project": r["project"], "src": os.path.join(root, rel),
                     "bytes": r.get("bytes") or ""})
    return jobs


def jobs_from_files(files: list[str]) -> list[dict]:
    jobs = []
    for f in files:
        name = os.path.basename(f)
        name = name[:-len("-dataset.parquet")] if name.endswith("-dataset.parquet") else name
        jobs.append({"project": name, "src": os.path.abspath(f), "bytes": ""})
    seen = set()
    for j in jobs:
        if j["project"] in seen:
            raise SystemExit(f"two files give the project name {j['project']}")
        seen.add(j["project"])
    return jobs


def plan_resources(a) -> dict:
    """The limits of the scheduler. budget: the sum of the DuckDB memory_limit
    of all running jobs. Each job gets a memory_limit from its file size
    (task_resources), at most the budget."""
    ncpu = os.cpu_count() or 1
    avail = mem_available()
    budget = (float(a.mem_budget) * 2**30 if a.mem_budget
              else min(a.mem_fraction * avail, a.mem_cap * 2**30))
    if a.mem_per_job:
        budget = max(budget, float(a.mem_per_job) * 2**30)
    if budget < 512 * 2**20:
        raise SystemExit(f"memory budget {gib(budget)} is less than 0.5 GiB "
                         f"(MemAvailable {gib(avail)}). Free memory or give --mem-budget.")
    return {"ncpu": ncpu, "budget": int(budget), "jobs": a.jobs or max(1, min(8, ncpu // 2)),
            "max_threads": a.threads or min(8, ncpu), "fixed_mem": a.mem_per_job,
            "avail": avail}


def task_resources(size: int, plan: dict) -> tuple[int, int]:
    """(memory_limit bytes, threads) of one file. Measured on this host: a
    1.6 GiB file (200 M rows) peaks at 0.6-0.7 GiB RSS; a small file at
    0.1 GiB. Thus memory_limit = 0.5 GiB + the file size, at most the budget;
    DuckDB spills to OUT/tmp above the limit."""
    if plan["fixed_mem"]:
        mem = int(float(plan["fixed_mem"]) * 2**30)
    else:
        mem = min(plan["budget"], 512 * 2**20 + size)
    threads = max(1, min(plan["max_threads"], -(-size // (128 * 2**20))))
    return mem, threads


def cmd_run(a) -> int:
    out = os.path.abspath(a.out)
    os.makedirs(os.path.join(out, "logs"), exist_ok=True)
    logfh = open(os.path.join(out, "logs", "run.log"), "a", encoding="utf-8")
    groups = [g for g in FINDING_GROUPS if g in a.only.split(",")] if a.only else list(FINDING_GROUPS)
    psl = None
    if "m9" in groups:
        psl_path = a.psl or find_psl(a.psl_sha256)
        if not psl_path:
            raise SystemExit(f"no Public Suffix List with sha256 {a.psl_sha256} (give --psl)")
        got = file_sha256(psl_path)
        if a.psl_sha256 != "any" and got != a.psl_sha256:
            raise SystemExit(f"PSL sha256 {got} differs from {a.psl_sha256}")
        psl = load_psl(psl_path)
        with open(os.path.join(out, "psl.json"), "w") as fh:
            json.dump({"path": psl_path, "sha256": got, "rules": len(psl["rules"]),
                       "wild": len(psl["wild"]), "exc": len(psl["exc"]),
                       "tlds": len(psl["tlds"])}, fh, indent=1)
    jobs = jobs_from_files(a.files) if a.files else read_manifest(a.root, a.manifest)
    if a.limit:
        jobs = jobs[: a.limit]
    plan = plan_resources(a)
    todo = []
    for j in jobs:
        need = [g for g in groups if not os.path.exists(done_marker(out, j["project"], g))]
        if need:
            j.update({"out": out, "groups": need, "psl": psl})
            todo.append(j)
    for j in todo:
        try:
            j["size"] = os.path.getsize(j["src"])
        except OSError:
            j["size"] = int(j["bytes"] or 0)
        j["mem_bytes"], j["threads"] = task_resources(j["size"], plan)
        j["mem"] = f"{j['mem_bytes'] // 2**20}MB"
    todo.sort(key=lambda j: -j["size"])           # largest first
    total_bytes = sum(j["size"] for j in todo)
    log(f"start: {len(jobs)} projects, {len(jobs) - len(todo)} done before, {len(todo)} to do "
        f"({gib(total_bytes)}); groups {','.join(groups)}; at most {plan['jobs']} jobs, "
        f"{plan['ncpu']} threads and {gib(plan['budget'])} of memory_limit together; "
        f"MemAvailable {gib(plan['avail'])}", logfh)
    errfile = os.path.join(out, "errors.tsv")
    timefile = os.path.join(out, "timings.tsv")
    if not os.path.exists(timefile):
        with open(timefile, "w") as fh:
            fh.write("project\tbytes\tseconds\tgroups\tworker_maxrss_mib\n")
    t0 = time.time()
    done_bytes = 0
    nerr = 0
    reserve = int(a.mem_reserve * 2**30)
    with cf.ProcessPoolExecutor(max_workers=plan["jobs"], max_tasks_per_child=20) as ex:
        pending: dict = {}
        queue = list(todo)
        while queue or pending:
            while queue and len(pending) < plan["jobs"]:
                used_mem = sum(p["mem_bytes"] for p in pending.values())
                used_thr = sum(p["threads"] for p in pending.values())
                pick = None
                for i, j in enumerate(queue):      # the largest file that fits
                    if not pending or (used_mem + j["mem_bytes"] <= plan["budget"]
                                       and used_thr + j["threads"] <= plan["ncpu"]
                                       and mem_available() >= j["mem_bytes"] + reserve):
                        pick = i
                        break
                if pick is None:
                    break                          # wait for a running job to end
                j = queue.pop(pick)
                pending[ex.submit(measure_project, j)] = j
            if not pending:
                time.sleep(5)
                continue
            fin, _ = cf.wait(list(pending), timeout=30, return_when=cf.FIRST_COMPLETED)
            for fu in fin:
                j = pending.pop(fu)
                r = fu.result()
                done_bytes += j["size"]
                el = time.time() - t0
                eta = (total_bytes - done_bytes) / (done_bytes / el) if done_bytes and el else 0
                if r["ok"]:
                    with open(timefile, "a") as fh:
                        fh.write(f"{r['project']}\t{r['bytes']}\t{r['seconds']}\t"
                                 f"{','.join(r['groups'])}\t{r['maxrss_mib']}\n")
                    log(f"done {r['project']} {gib(j['size'])} {r['seconds']} s; "
                        f"rss {r['maxrss_mib']} MiB; {gib(done_bytes)}/{gib(total_bytes)}; ETA {eta / 60:.1f} min", logfh)
                else:
                    nerr += 1
                    with open(errfile, "a") as fh:
                        fh.write(f"{r['project']}\t{enc(r['error'])}\n")
                    log(f"ERROR {r['project']}: {r['error']}", logfh)
                    logfh.write(enc(r.get("trace", "")) + "\n")
    log(f"end: {len(todo)} projects in {time.time() - t0:.1f} s, {nerr} errors", logfh)
    rc = cmd_summary(argparse.Namespace(out=out, private=a.private))
    return 1 if nerr else rc


# ---------------------------------------------------------------- summary

def concat(out: str, sub: str, suffix: str, target: str) -> list[dict]:
    files = sorted(glob.glob(os.path.join(out, sub, f"*{suffix}")))
    if suffix == ".tsv":
        files = [f for f in files if not f.endswith((".files.tsv", ".commits.tsv"))]
    allrows: list[dict] = []
    header: list[str] | None = None
    tmp = f"{target}.tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        for f in files:
            with open(f, encoding="utf-8") as src:
                h = src.readline()
                if header is None:
                    header = h.rstrip("\n").split(TAB)
                    fh.write(h)
                for line in src:
                    fh.write(line)
                    allrows.append(dict(zip(header, line.rstrip("\n").split(TAB))))
    os.replace(tmp, target)
    return allrows


def isum(rows: list[dict], key: str) -> int:
    return sum(int(r[key] or 0) for r in rows)


def cmd_summary(a) -> int:
    out = os.path.abspath(a.out)
    s: list[list] = []
    m4 = concat(out, "m4", ".tsv", os.path.join(out, "m4.projects.tsv"))
    m4f = concat(out, "m4", ".files.tsv", os.path.join(out, "m4.files.tsv"))
    if m4:
        s.append(["M4", "projects", len(m4)])
        for k in m4[0]:
            if k != "project":
                s.append(["M4", k, isum(m4, k)])
        s.append(["M4", "projects_with_cut_off_file", sum(1 for r in m4 if int(r["files_cut_off"]))])
        s.append(["M4", "projects_with_file_not_1_1_after_repair",
                  sum(1 for r in m4 if int(r["files_not_1_1_after_repair"]))])
        s.append(["M4", "flagged_file_rows_in_m4.files.tsv", len(m4f)])
    m10 = concat(out, "m10", ".tsv", os.path.join(out, "m10.projects.tsv"))
    concat(out, "m10", ".files.tsv", os.path.join(out, "m10.files.tsv"))
    if m10:
        s.append(["M10", "projects", len(m10)])
        for k in m10[0]:
            if k != "project":
                s.append(["M10", k, isum(m10, k)])
        s.append(["M10", "projects_with_shift", sum(1 for r in m10 if int(r["rows_shift"]))])
        s.append(["M10", "projects_with_path_semicolon",
                  sum(1 for r in m10 if int(r["rows_path_semicolon"]))])
    m7 = concat(out, "m7", ".tsv", os.path.join(out, "m7.projects.tsv"))
    m7c = concat(out, "m7", ".commits.tsv", os.path.join(out, "m7.commits.tsv"))
    if m7:
        s.append(["M7", "projects", len(m7)])
        for k in m7[0]:
            if k != "project":
                s.append(["M7", k, isum(m7, k)])
        s.append(["M7", "projects_with_footer_end",
                  sum(1 for r in m7 if int(r["commits_footer_end"]))])
        s.append(["M7", "distinct_original_commit_sha_footer_end_all_projects",
                  len({r["original_commit_sha"] for r in m7c})])
    m9 = concat(out, "m9", ".tsv", os.path.join(out, "m9.projects.tsv"))
    if m9:
        projects = {r["project"] for r in m9}
        s.append(["M9", "projects", len(projects)])
        cls: dict = {}
        for r in m9:
            key = (r["class"], r["subclass"])
            c = cls.setdefault(key, [0, 0, set()])
            c[0] += int(r["distinct_values"] or 0)
            c[1] += int(r["token_rows"] or 0)
            if int(r["token_rows"] or 0):
                c[2].add(r["project"])
        rows = [[k[0], k[1], v[0], v[1], len(v[2])] for k, v in sorted(cls.items())]
        write_tsv(os.path.join(out, "m9.classes.tsv"),
                  ["class", "subclass", "sum_of_per_project_distinct_values", "token_rows",
                   "projects"], rows)
        for c, sub, dv, n, np_ in rows:
            if c == "meta":
                s.append(["M9", sub, n])
            else:
                s.append(["M9", f"{c}/{sub}_sum_per_project_distinct", dv])
                s.append(["M9", f"{c}/{sub}_token_rows", n])
                s.append(["M9", f"{c}/{sub}_projects", np_])
        nonreg = {r["project"] for r in m9 if r["class"] in ("ip", "local_host", "other")
                  and int(r["token_rows"] or 0)}
        s.append(["M9", "projects_with_value_not_registrable", len(nonreg)])
    psl_json = os.path.join(out, "psl.json")
    if os.path.exists(psl_json):
        s.append(["M9", "psl_sha256", json.load(open(psl_json))["sha256"]])
    errs = os.path.join(out, "errors.tsv")
    s.append(["run", "error_rows", sum(1 for _ in open(errs)) if os.path.exists(errs) else 0])
    write_tsv(os.path.join(out, "summary.tsv"), ["finding", "measure", "value"], s)
    for f, m, v in s:
        print(f"{f}\t{m}\t{v}")
    return check_no_at(out, getattr(a, "private", DEFAULT_PRIVATE))


def check_no_at(out: str, private: str | None) -> int:
    """Exit status 1 when an output file outside the private folder holds the
    at sign."""
    bad = []
    priv = os.path.abspath(private) if private else None
    for d, _, fs in os.walk(out):
        if priv and os.path.abspath(d).startswith(priv):
            continue
        if os.sep + "tmp" in d[len(out):]:
            continue
        for f in fs:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                if AT.encode() in fh.read():
                    bad.append(p)
    for p in bad:
        print(f"PRIVACY ERROR: the at sign is in {p}", file=sys.stderr)
    return 1 if bad else 0


# ---------------------------------------------------------------- m9 global and sample

def m9_sources(a) -> list[str]:
    jobs = jobs_from_files(a.files) if a.files else read_manifest(a.root, a.manifest)
    return [j["src"] for j in jobs]


def m9_connect(a):
    psl_path = a.psl or find_psl(a.psl_sha256)
    if not psl_path:
        raise SystemExit("no Public Suffix List (give --psl)")
    got = file_sha256(psl_path)
    if a.psl_sha256 != "any" and got != a.psl_sha256:
        raise SystemExit(f"PSL sha256 {got} differs from {a.psl_sha256}")
    con = connect(a.mem, a.threads, os.path.join(os.path.abspath(a.out), "tmp", "m9"))
    install_psl(con, load_psl(psl_path))
    return con, got


def cmd_m9_global(a) -> int:
    """Distinct values per class over all files. Values stay in DuckDB memory."""
    con, sha = m9_connect(a)
    srcs = m9_sources(a)
    t0 = time.time()
    con.execute("CREATE TEMP TABLE g (v VARCHAR, n BIGINT)")
    for i, src in enumerate(srcs, 1):              # one file at a time: low memory
        con.execute(f"""INSERT INTO g SELECT lower(trim(person_domain)), count(*)
            FROM read_parquet({sql_str(src)})
            WHERE person_domain IS NOT NULL AND strpos(person_domain, chr(64)) = 0
            GROUP BY 1""")
        if i % 500 == 0:
            con.execute("CREATE OR REPLACE TEMP TABLE g AS SELECT v, sum(n) AS n FROM g GROUP BY v")
            log(f"m9-global {i}/{len(srcs)} files, {time.time() - t0:.0f} s")
    rows = con.execute(f"""WITH d AS (SELECT v, sum(n) AS n FROM g GROUP BY v),
        k AS (SELECT {m9_class_sql('v')} AS cls, n FROM d)
        SELECT split_part(cls, '/', 1), split_part(cls, '/', 2), count(*), sum(n)
        FROM k GROUP BY cls ORDER BY cls""").fetchall()
    out = os.path.abspath(a.out)
    write_tsv(os.path.join(out, "m9.global.tsv"),
              ["class", "subclass", "distinct_values_all_files", "token_rows"],
              [list(r) for r in rows] + [["meta", "files", len(srcs), ""],
                                         ["meta", "psl_sha256", sha, ""]])
    for r in rows:
        print(TAB.join(str(x) for x in r))
    log(f"m9-global end: {len(srcs)} files in {time.time() - t0:.1f} s")
    return check_no_at(out, a.private)


def cmd_m9_sample(a) -> int:
    """At most --max values (not 'registrable') into the private folder."""
    priv = os.path.abspath(a.private)
    os.makedirs(priv, mode=0o700, exist_ok=True)
    os.chmod(priv, 0o700)
    con, _ = m9_connect(a)
    srcs = m9_sources(a)
    out = os.path.abspath(a.out)
    m9p = os.path.join(out, "m9.projects.tsv")
    if os.path.exists(m9p):                        # read only projects with such values
        hit = {r["project"] for r in read_tsv(m9p)
               if r["class"] in ("ip", "local_host", "other") and int(r["token_rows"] or 0)}
        srcs = [s for s in srcs if os.path.basename(s).rsplit("-dataset.parquet", 1)[0] in hit]
    got: dict = {}
    for src in srcs:
        rows = con.execute(f"""WITH d AS (SELECT DISTINCT lower(trim(person_domain)) AS v
              FROM read_parquet({sql_str(src)})
              WHERE person_domain IS NOT NULL AND strpos(person_domain, chr(64)) = 0)
            SELECT v, {m9_class_sql('v')} AS cls FROM d
            WHERE split_part({m9_class_sql('v')}, '/', 1) IN ('ip', 'local_host', 'other')
            ORDER BY v""").fetchall()
        for v, cls in rows:
            per = sum(1 for c, _ in got.values() if c == cls)
            if v not in got and len(got) < a.max and per < a.per_class:
                got[v] = (cls, os.path.basename(src).rsplit("-dataset.parquet", 1)[0])
        if len(got) >= a.max:
            break
    target = os.path.join(priv, "m9-sample.tsv")
    fd = os.open(target + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("class\tproject\tvalue\n")
        for v, (cls, proj) in sorted(got.items(), key=lambda kv: kv[1]):
            fh.write(f"{cls}\t{proj}\t{enc(v).replace('%40', AT)}\n")
    os.replace(target + ".tmp", target)
    print(f"wrote {len(got)} values to {target} (mode 600, folder mode 700)")
    return 0


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, need_root=True):
        p.add_argument("root", nargs="?" if not need_root else None,
                       help="release root folder (holds MANIFEST.tsv and parquet/)")
        p.add_argument("--files", nargs="+", help="measure these Parquet files, not ROOT")
        p.add_argument("--manifest", help="default: ROOT/MANIFEST.tsv")
        p.add_argument("--out", help=f"output folder (default {DEFAULT_OUT_BASE}/<ROOT name>)")
        p.add_argument("--psl", help="Public Suffix List file (default: the pinned nix copy)")
        p.add_argument("--psl-sha256", default=PINNED_PSL_SHA256,
                       help="expected sha256 of the PSL ('any' for tests)")
        p.add_argument("--private", default=DEFAULT_PRIVATE)

    p = sub.add_parser("run")
    common(p, need_root=False)
    p.add_argument("--only", help="comma list of m4m10,m7,m9 (default all)")
    p.add_argument("--jobs", type=int, default=0, help="at most N files at a time (default min(8, nproc/2))")
    p.add_argument("--threads", type=int, default=0, help="at most N DuckDB threads per job (default min(8, nproc))")
    p.add_argument("--mem-budget", help="GiB: the sum of memory_limit of all running jobs")
    p.add_argument("--mem-per-job", help="GiB: one fixed memory_limit for each job (tests)")
    p.add_argument("--mem-fraction", type=float, default=0.5,
                   help="part of MemAvailable for all jobs together (default 0.5)")
    p.add_argument("--mem-cap", type=float, default=16.0, help="GiB cap for all jobs (default 16)")
    p.add_argument("--mem-reserve", type=float, default=1.0,
                   help="GiB of MemAvailable to keep free before a new job starts")
    p.add_argument("--limit", type=int, default=0, help="first N projects only (a test)")
    p = sub.add_parser("summary")
    p.add_argument("out")
    p.add_argument("--private", default=DEFAULT_PRIVATE)
    for name in ("m9-global", "m9-sample"):
        p = sub.add_parser(name)
        common(p, need_root=False)
        p.add_argument("--mem", default="2GB")
        p.add_argument("--threads", type=int, default=4)
        p.add_argument("--max", type=int, default=20, help="m9-sample: at most N values (<= 20)")
        p.add_argument("--per-class", type=int, default=3,
                       help="m9-sample: at most N values of one subclass")
    a = ap.parse_args(argv)
    if a.cmd == "summary":
        return cmd_summary(a)
    if not a.files and not a.root:
        ap.error("give ROOT or --files")
    if not a.out:
        base = os.path.basename(os.path.normpath(a.root)) if a.root else "files"
        a.out = os.path.join(DEFAULT_OUT_BASE, base)
    if a.cmd == "m9-sample" and a.max > 20:
        ap.error("--max is at most 20")
    return {"run": cmd_run, "m9-global": cmd_m9_global, "m9-sample": cmd_m9_sample}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
