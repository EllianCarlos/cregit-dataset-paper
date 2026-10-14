#!/usr/bin/env python3
"""Recompute the 15 footer_* columns of one finished project Parquet from the original commits.
Usage: rewrite_footer_columns.py PARQUET (--out NEW.parquet | --in-place)
       [--persons-db DB] [--git-dir CLONE.git] [--work-dir DIR] [--keep-work]
       [--jar SLICKGITLOG_JAR] [--java JAVA] [--java-opts=-Xmx3g] [--report TSV]
       [--memory-limit 4GB] [--threads 2] [--chunk-rows N]

The defect. generate_dataset.py reads the footer columns from the `footers` table of the cregit
DB. slickGitLog (JGit RevCommit.getFooterLines) builds that table from the REWRITTEN repository,
where blobExec appends "\\n" + "Former-commit-id: X" to each message. A git CLI message ends with
"\\n", so a blank line comes before Former-commit-id and JGit finds only that one footer: the
real trailers are lost. The correct source is the original commit, keyed by original_commit_sha.

What this does, for one Parquet:
 1. A commit-only bare clone of the file's one clone_url (git clone --bare --filter=tree:0), or
    the clone that --git-dir gives.
 2. The same slickGitLog one-jar that step 3 of run_pipeline_process.sh runs, on that clone: an
    original DB. JGit reads a tree:0 partial clone, because a log walk with no path filter reads
    only commit objects. Its `footers` table is what step 3 gives (key, value, idx per commit).
 3. TYPED_SELECT and PERSON_SELECT below are the two footer subqueries of the FIXED
    generate_dataset.py (cregit branch fix/trailers-original-db), word for word (a test keeps
    them the same), on that `footers` table (as original_log.footers, the name the fixed code
    gives it) and on `emails` and `persons` of the kept <repo_name>-persons.db next to the
    Parquet.
 4. The 15 new values per row, in row order: per chunk of rows, (row number, commit) joined to
    that subquery's result and sorted on the row number, into narrow Parquets in the work dir
    (a DuckDB hash join does not keep row order). Then one DuckDB COPY of SELECT * REPLACE
    (the 15 columns) over a POSITIONAL JOIN of the file and the narrow Parquets, so the column
    set, order and types stay; ZSTD and the default row group size, as cregit and the firm
    step write. Then every row is compared with the source (POSITIONAL JOIN, IS DISTINCT
    FROM): the other columns must be identical and the 15 must hold the recomputed values.
    Only then is the file kept (--in-place: renamed over the source).

Refused (nothing is written): the 15 columns are missing or not VARCHAR[]; more than one
repo_name or clone_url; an original_commit_sha that is not a commit of the clone; the persons
DB does not give the person columns that the file has (so it is not the DB that
generate_dataset used); one commit has two different footer values in the file; a commit has
non-empty footer values that differ, as sets, from the trailer lines of the original commit
(typed lists) or from the recomputed person columns (the old values can only be empty, or
right when the message had no final newline; the census SQL could repeat one).

Each of the 13 typed lists then holds one entry for each person (TYPED_SELECT): two values
are one person when their addresses resolve to one personid, or, with no emails row, when the
lowercased addresses are equal. The value with the lowest idx stays, at its place. A value
with no address is never merged.

Output: one "OK ..." line, and with --report one TSV row per Parquet (appended; the header is
written when the file is new): commits, commits with any of the 13 typed trailers before and
after, commits per key after, and the time and disk of the clone and of the parse.
Exit 0 written, 1 refused or the comparison failed, 2 usage. Needs the duckdb module, git, java."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_JAR = Path(os.environ.get(
    "SLICKGITLOG_JAR", Path.home() / "Projects/cregit-ec2/slickGitLog/target/scala-2.10/"
    "slickgitlog_2.10-0.1-SNAPSHOT-one-jar.jar"))

TYPED = (
    ("footer_signed_off_by", "signed-off-by"),
    ("footer_co_authored_by", "co-authored-by"),
    ("footer_co_developed_by", "co-developed-by"),
    ("footer_reviewed_by", "reviewed-by"),
    ("footer_acked_by", "acked-by"),
    ("footer_tested_by", "tested-by"),
    ("footer_reported_by", "reported-by"),
    ("footer_suggested_by", "suggested-by"),
    ("footer_based_on_patch_by", "based-on-patch-by"),
    ("footer_helped_by", "helped-by"),
    ("footer_mentored_by", "mentored-by"),
    ("footer_assisted_by", "assisted-by"),
    ("footer_thanks_to", "thanks-to"),
)
FOOTERS = tuple(c for c, _ in TYPED) + ("footer_personids", "footer_person_names")
CHUNK_ROWS = 40 * 122880        # 40 of DuckDB's default row groups

# The two footer subqueries of the fixed generate_dataset.py (cregit branch
# fix/trailers-original-db: acd08b4 reads original_log.footers, 9079a9c moves the emails join
# out of the typed lists, and the next commit keeps one entry for each person in each typed
# list), word for word. Its f-string writes {{2,}}; the SQL that DuckDB runs has {2,}.
# test_rewrite_footer_columns.py compares the text.
TYPED_SELECT = """
                SELECT
                    f.cid,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'signed-off-by')       AS footer_signed_off_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'co-authored-by')      AS footer_co_authored_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'co-developed-by')     AS footer_co_developed_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'reviewed-by')         AS footer_reviewed_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'acked-by')            AS footer_acked_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'tested-by')           AS footer_tested_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'reported-by')         AS footer_reported_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'suggested-by')        AS footer_suggested_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'based-on-patch-by')   AS footer_based_on_patch_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'helped-by')           AS footer_helped_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'mentored-by')         AS footer_mentored_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'assisted-by')         AS footer_assisted_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'thanks-to')           AS footer_thanks_to
                -- One entry for each person in each list: the trailer line with
                -- the lowest idx. A message can name one person twice, with the
                -- same text or with another address of that person.
                FROM (
                    SELECT
                        f.cid, f.idx, f.key, f.value,
                        row_number() OVER (PARTITION BY f.cid, LOWER(f.key), f.who
                                           ORDER BY f.idx)                                    AS nth,
                        f.who
                    FROM (
                        -- who: the personid of the address, else the lowercased
                        -- address, else NULL (a value with no address is kept).
                        -- The address is the one that footer_personids uses.
                        SELECT
                            f.cid, f.idx, f.key, f.value,
                            CASE WHEN fa.personid IS NOT NULL THEN 'p:' || fa.personid
                                 WHEN f.addr IS NOT NULL THEN 'a:' || LOWER(f.addr)
                            END                                                               AS who
                        FROM (
                            SELECT
                                f.cid, f.idx, f.key, f.value,
                                coalesce(
                                    nullif(regexp_extract(f.value, '<([^>]+)>', 1), ''),
                                    nullif(regexp_extract(f.value, '([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,})', 1), '')
                                )                                                             AS addr
                            -- The trailers come from the original repository, keyed by
                            -- the original commit SHA. In the cregit repository, blobExec
                            -- appends "\\n" + "Former-commit-id: X" to a message whose last
                            -- paragraph has trailers. When that message ends in "\\n" (the
                            -- git CLI writes it so), a blank line comes before the new
                            -- trailer, and JGit then sees only Former-commit-id.
                            FROM original_log.footers f
                        ) f
                        -- One personid for each address. min() if the emails rows of
                        -- one address name two persons.
                        LEFT JOIN (
                            SELECT emailaddr, min(personid) AS personid
                            FROM emails
                            WHERE personid IS NOT NULL
                            GROUP BY emailaddr
                        ) fa ON fa.emailaddr = f.addr
                    ) f
                ) f
                WHERE f.who IS NULL OR f.nth = 1
                GROUP BY f.cid
"""

# The typed lists of 9079a9c: one value for each trailer line, no rule for persons.
# recompute() checks the old values against these, as sets: an old non-empty value came from
# the raw trailer lines, so it can hold two values of one person.
RAW_TYPED_SELECT = """
                SELECT
                    f.cid,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'signed-off-by')       AS footer_signed_off_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'co-authored-by')      AS footer_co_authored_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'co-developed-by')     AS footer_co_developed_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'reviewed-by')         AS footer_reviewed_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'acked-by')            AS footer_acked_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'tested-by')           AS footer_tested_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'reported-by')         AS footer_reported_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'suggested-by')        AS footer_suggested_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'based-on-patch-by')   AS footer_based_on_patch_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'helped-by')           AS footer_helped_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'mentored-by')         AS footer_mentored_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'assisted-by')         AS footer_assisted_by,
                    list(f.value ORDER BY f.idx) FILTER (WHERE LOWER(f.key) = 'thanks-to')           AS footer_thanks_to
                -- The trailers come from the original repository, keyed by
                -- the original commit SHA. In the cregit repository, blobExec
                -- appends "\\n" + "Former-commit-id: X" to a message whose last
                -- paragraph has trailers. When that message ends in "\\n" (the
                -- git CLI writes it so), a blank line comes before the new
                -- trailer, and JGit then sees only Former-commit-id.
                FROM original_log.footers f
                GROUP BY f.cid
"""

PERSON_SELECT = """
                SELECT
                    f.cid,
                    list(DISTINCT fe.personid ORDER BY fe.personid)
                        FILTER (WHERE fe.personid IS NOT NULL)                                           AS footer_personids,
                    list(DISTINCT coalesce(fpn.personname, fe.personid)
                        ORDER BY coalesce(fpn.personname, fe.personid))
                        FILTER (WHERE coalesce(fpn.personname, fe.personid) IS NOT NULL)                AS footer_person_names
                FROM original_log.footers f
                -- regexp_extract returns '' rather than NULL on no match, so
                -- without nullif a no-address trailer joins on '' and matches
                -- every `Name <>` row. Bracketed form first: correct precedence.
                LEFT JOIN emails fe
                    ON fe.emailaddr = coalesce(
                        nullif(regexp_extract(f.value, '<([^>]+)>', 1), ''),
                        nullif(regexp_extract(f.value, '([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,})', 1), '')
                    )
                LEFT JOIN persons fpn ON fe.personid = fpn.personid
                GROUP BY f.cid
"""

# The tables that generate_dataset reads (ATTACH ... AS original_log, sqlite_attach of the
# persons DB), with the columns it uses.
TABLES = {
    "original_log.commits": ("orig", "SELECT cid FROM commits", {"cid": "VARCHAR"}),
    "original_log.footers": ("orig", "SELECT cid, idx, key, value FROM footers",
                {"cid": "VARCHAR", "idx": "BIGINT", "key": "VARCHAR", "value": "VARCHAR"}),
    "emails": ("persons", "SELECT personid, emailaddr, emailname, domain FROM emails",
               {"personid": "VARCHAR", "emailaddr": "VARCHAR", "emailname": "VARCHAR",
                "domain": "VARCHAR"}),
    "persons": ("persons", "SELECT personid, personname FROM persons",
                {"personid": "VARCHAR", "personname": "VARCHAR"}),
}

REPORT_COLS = (("project", "rows", "commits", "before", "after", "any_footer")
               + tuple(k for _, k in TYPED) + ("personids", "already_set",
                                               "clone_s", "clone_mb", "parse_s", "db_mb",
                                               "rewrite_s"))


class Refused(Exception):
    pass


def connect(memory_limit: str, threads: int, spill: Path):
    import duckdb

    config = {"temp_directory": str(spill)}
    if memory_limit:
        config["memory_limit"] = memory_limit
    if threads:
        config["threads"] = threads
    return duckdb.connect(config=config)


def schema(con, path: Path) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in
            con.execute("DESCRIBE SELECT * FROM read_parquet($p)", {"p": str(path)}).fetchall()]


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def nonempty(alias: str, cols=tuple(c for c, _ in TYPED)) -> str:
    return "(" + " OR ".join(f"len({alias}.{q(c)}) > 0" for c in cols) + ")"


def one_value(con, src: Path, col: str) -> str:
    seen = [r[0] for r in con.execute(
        f"SELECT DISTINCT {q(col)} FROM read_parquet($p)", {"p": str(src)}).fetchall()]
    if len(seen) != 1 or not seen[0]:
        raise Refused(f"{src}: {len(seen)} {col} values {sorted(map(repr, seen))[:3]}")
    return seen[0]


def check_schema(con, src: Path) -> None:
    cols = dict(schema(con, src))
    for f in FOOTERS:
        if cols.get(f) != "VARCHAR[]":
            raise Refused(f"{src}: column {f} is {cols.get(f)!r}, not VARCHAR[]")
    for f in ("repo_name", "clone_url", "original_commit_sha", "author_name", "author_email",
              "personid", "person_name", "person_email", "person_domain"):
        if cols.get(f) != "VARCHAR":
            raise Refused(f"{src}: column {f} is {cols.get(f)!r}, not VARCHAR")


def du_mb(path: Path) -> float:
    total = sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.is_dir() \
        else path.stat().st_size
    return round(total / 1e6, 1)


def clone(url: str, dest: Path) -> None:
    """The commits only: no tree and no blob is fetched. GIT_TERMINAL_PROMPT=0, so a URL that
    asks for a password fails at once."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    r = subprocess.run(["git", "clone", "-q", "--bare", "--filter=tree:0", url, str(dest)],
                       env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise Refused(f"git clone {url} failed: {r.stderr.strip()[-500:]}")


def slickgitlog(java: str, jar: Path, git_dir: Path, db: Path, java_opts: tuple = ()) -> None:
    """Step 3 of run_pipeline_process.sh: java -jar SLICKGITLOG_JAR DB REPO. java_opts (a heap
    cap, say) changes only the JVM, not what JGit parses."""
    if not jar.is_file():
        raise Refused(f"no slickGitLog one-jar at {jar}")
    r = subprocess.run([java, *java_opts, "-jar", str(jar), str(db), str(git_dir)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not db.is_file() or "Finished creating database" not in r.stdout:
        raise Refused(f"slickGitLog failed on {git_dir} (exit {r.returncode}): "
                      f"{(r.stdout + r.stderr).strip()[-500:]}")


def load(con, work: Path, dbs: dict) -> None:
    """The four tables into DuckDB, through NDJSON: the system DuckDB has no sqlite extension.
    The text goes through unchanged, so the values are the ones sqlite_attach gives."""
    con.execute("CREATE SCHEMA IF NOT EXISTS original_log")
    for name, (which, sql, cols) in TABLES.items():
        path = work / f"{name}.ndjson"
        src = sqlite3.connect(f"file:{dbs[which]}?mode=ro", uri=True)
        try:
            cur = src.execute(sql)
            keys = [d[0] for d in cur.description]
            with path.open("w", encoding="utf-8") as fh:
                for row in cur:
                    fh.write(json.dumps(dict(zip(keys, row)), ensure_ascii=False))
                    fh.write("\n")
        finally:
            src.close()
        spec = "{" + ", ".join(f"'{k}': '{t}'" for k, t in cols.items()) + "}"
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_json($p, "
                    f"format='newline_delimited', columns={spec})", {"p": str(path)})
        path.unlink()


def check_inputs(con, src: Path) -> None:
    p = {"p": str(src)}
    missing = con.execute(
        "SELECT count(*), min(s) FROM (SELECT DISTINCT original_commit_sha AS s "
        "FROM read_parquet($p)) a WHERE NOT EXISTS (SELECT 1 FROM original_log.commits c "
        "WHERE c.cid = a.s)",
        p).fetchone()
    if missing[0]:
        raise Refused(f"{src}: {missing[0]} original_commit_sha values are not commits of the "
                      f"clone (first {missing[1]})")
    # generate_dataset: LEFT JOIN emails e ON (c.autname = e.emailname AND c.autemail =
    # e.emailaddr) LEFT JOIN persons p ON e.personid = p.personid.
    bad = con.execute("""
        SELECT count(*), min(a.author_email) FROM (SELECT DISTINCT author_name, author_email,
            personid, person_name, person_email, person_domain FROM read_parquet($p)) a
        LEFT JOIN emails e ON (a.author_name = e.emailname AND a.author_email = e.emailaddr)
        LEFT JOIN persons pp ON e.personid = pp.personid
        WHERE a.personid IS DISTINCT FROM e.personid
           OR a.person_name IS DISTINCT FROM coalesce(pp.personname, e.personid)
           OR a.person_email IS DISTINCT FROM e.emailaddr
           OR a.person_domain IS DISTINCT FROM e.domain""", p).fetchone()
    if bad[0]:
        raise Refused(f"{src}: the persons DB does not give the person columns of {bad[0]} "
                      f"authors (first {bad[1]!r}); it is not the DB that generate_dataset used")


def recompute(con, src: Path) -> int:
    """ftr: the 15 values for each commit of the file that has a footer, from the two subqueries
    (both group all footer rows by cid, so they give the same cids). Then the old values per
    commit; returns how many commits have non-empty old values (all of them must agree)."""
    typed = ", ".join(f"t.{q(c)}" for c, _ in TYPED)
    con.execute(f"CREATE TEMP TABLE ftr AS SELECT t.cid, {typed}, p.footer_personids, "
                f"p.footer_person_names FROM ({TYPED_SELECT}) t JOIN ({PERSON_SELECT}) p "
                "ON t.cid = p.cid WHERE t.cid IN (SELECT original_commit_sha FROM "
                "read_parquet($p))", {"p": str(src)})
    cols = ", ".join(q(c) for c in FOOTERS)
    con.execute(f"CREATE TEMP TABLE old AS SELECT DISTINCT original_commit_sha AS cid, {cols} "
                "FROM read_parquet($p)", {"p": str(src)})
    n_old, n_commits = con.execute(
        "SELECT count(*), count(DISTINCT cid) FROM old").fetchone()
    if n_old != n_commits:
        raise Refused(f"{src}: {n_old - n_commits} commits have two different footer values")
    # As sets: the census SQL repeated a value once for each emails row of its address (the
    # fix 9079a9c), and an old non-empty value comes from that SQL. The old typed lists of a
    # census file hold every trailer line, so they are checked against RAW_TYPED_SELECT, not
    # against the lists with one entry per person; a file that this tool already wrote holds
    # exactly ftr's lists. The two person columns did not change, so they are checked
    # against ftr.
    con.execute(f"CREATE TEMP TABLE raw AS SELECT * FROM ({RAW_TYPED_SELECT}) r "
                "WHERE r.cid IN (SELECT cid FROM old)")

    def as_set(expr: str) -> str:
        return f"list_sort(list_distinct({expr}))"

    typed = dict(TYPED)
    differs = " OR ".join(
        f"({as_set(f'o.{q(c)}')} IS DISTINCT FROM {as_set(f'coalesce(r.{q(c)}, [])')} "
        f"AND o.{q(c)} IS DISTINCT FROM coalesce(f.{q(c)}, []))" if c in typed else
        f"{as_set(f'o.{q(c)}')} IS DISTINCT FROM {as_set(f'coalesce(f.{q(c)}, [])')}"
        for c in FOOTERS)
    conflict = con.execute(
        f"SELECT count(*) FILTER (WHERE {differs}), count(*), min(o.cid) FILTER (WHERE {differs}) "
        f"FROM old o LEFT JOIN ftr f ON o.cid = f.cid LEFT JOIN raw r ON o.cid = r.cid "
        f"WHERE {nonempty('o', FOOTERS)}").fetchone()
    if conflict[0]:
        raise Refused(f"{src}: {conflict[0]} commits hold non-empty footer values that differ "
                      f"from the original commits (first {conflict[2]})")
    return conflict[1]


def footer_columns(con, src: Path, work: Path, n_rows: int, chunk_rows: int) -> list[Path]:
    """The 15 new columns, in the file's row order, as narrow Parquets of chunk_rows rows each.
    A hash join does not keep row order in DuckDB (measured: a join in the COPY moved 26% of
    curl's rows, also with one thread), so each chunk joins only (row number, commit) and sorts
    on the row number. A chunk reads only its row groups (file_row_number is pushed down)."""
    cols = ", ".join(f"coalesce(f.{q(c)}, []) AS {q(c)}" for c in FOOTERS)
    parts = []
    for i, lo in enumerate(range(0, n_rows, chunk_rows)):
        part = work / f"footer-cols-{i:06d}.parquet"
        con.execute(
            f"COPY (SELECT {cols} FROM (SELECT file_row_number AS rn, original_commit_sha "
            "FROM read_parquet($src, file_row_number = true) "
            "WHERE file_row_number >= $lo AND file_row_number < $hi) a "
            "LEFT JOIN ftr f ON a.original_commit_sha = f.cid ORDER BY a.rn) "
            "TO $dst (FORMAT PARQUET, COMPRESSION ZSTD)",
            {"src": str(src), "dst": str(part), "lo": lo, "hi": lo + chunk_rows})
        parts.append(part)
    return parts


def rewrite(con, src: Path, dst: Path, parts: list[Path]) -> None:
    """One streaming COPY of SELECT * REPLACE: the file and the narrow Parquets, side by side in
    a POSITIONAL JOIN (two scans, no join that moves rows). compare() checks each row."""
    con.execute("SET preserve_insertion_order = true")
    replace = ", ".join(f"n.{q(c)} AS {q(c)}" for c in FOOTERS)
    con.execute(f"COPY (SELECT s.* REPLACE ({replace}) FROM read_parquet($src) s "
                "POSITIONAL JOIN read_parquet($parts) n) "
                "TO $dst (FORMAT PARQUET, COMPRESSION ZSTD)",
                {"src": str(src), "dst": str(dst), "parts": [str(p) for p in parts]})


def compare(con, src: Path, dst: Path) -> list[str]:
    """Problems; [] when the other columns are identical row by row and the 15 hold ftr's
    values for the row's original_commit_sha. Two passes, so that no join meets the wide rows
    (on linux, a join of ftr to the POSITIONAL JOIN spilled more than 100 GB): the other
    columns side by side; then each distinct (original_commit_sha, 15 values) of the new file,
    which the first pass ties to the source rows, against ftr."""
    a, b = schema(con, src), schema(con, dst)
    if a != b:
        return [f"schema differs: {a} vs {b}"]
    n_a = con.execute("SELECT count(*) FROM read_parquet($p)", {"p": str(src)}).fetchone()[0]
    n_b = con.execute("SELECT count(*) FROM read_parquet($p)", {"p": str(dst)}).fetchone()[0]
    if n_a != n_b:
        return [f"rows differ: {n_a} vs {n_b}"]
    names = [n for n, _ in a if n not in FOOTERS]
    terms = ", ".join(f"count(*) FILTER (WHERE a.{q(n)} IS DISTINCT FROM b.{q(n)})" for n in names)
    row = con.execute(
        f"SELECT {terms} FROM (SELECT {', '.join(q(n) for n in names)} FROM read_parquet($src)) a "
        f"POSITIONAL JOIN (SELECT {', '.join(q(n) for n in names)} FROM read_parquet($dst)) b",
        {"src": str(src), "dst": str(dst)}).fetchone()
    problems = [f"{n}: {k} of {n_a} rows differ" for n, k in zip(names, row) if k]
    cols = ", ".join(q(c) for c in FOOTERS)
    differs = " OR ".join(f"n.{q(c)} IS DISTINCT FROM coalesce(f.{q(c)}, [])" for c in FOOTERS)
    n_new, n_sha, bad = con.execute(
        f"SELECT count(*), count(DISTINCT n.original_commit_sha), "
        f"count(*) FILTER (WHERE {differs}) "
        f"FROM (SELECT DISTINCT original_commit_sha, {cols} FROM read_parquet($dst)) n "
        "LEFT JOIN ftr f ON n.original_commit_sha = f.cid", {"dst": str(dst)}).fetchone()
    if n_new != n_sha:
        problems.append(f"{n_new - n_sha} commits have two different footer values in the new file")
    if bad:
        problems.append(f"{bad} commits have footer values that are not the recomputed ones")
    return problems


def counts(con, path: Path) -> dict:
    """Commits in the file: all, with any of the 13 typed trailers, and per key."""
    keys = ", ".join(f"count(*) FILTER (WHERE len({q(c)}) > 0)" for c in FOOTERS)
    row = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE {nonempty('t')}), {keys} FROM "
        f"(SELECT DISTINCT original_commit_sha, {', '.join(q(c) for c in FOOTERS)} "
        "FROM read_parquet($p)) t", {"p": str(path)}).fetchone()
    out = {"commits": row[0], "any": row[1]}
    for (c, k), v in zip(TYPED, row[2:]):
        out[k] = v
    out["personids"] = row[2 + len(TYPED)]
    return out


def write_report(path: Path, rec: dict) -> None:
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8") as fh:
        if new:
            fh.write("\t".join(REPORT_COLS) + "\n")
        fh.write("\t".join(str(rec[c]) for c in REPORT_COLS) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parquet", type=Path)
    dest = ap.add_mutually_exclusive_group(required=True)
    dest.add_argument("--out", type=Path)
    dest.add_argument("--in-place", action="store_true")
    ap.add_argument("--persons-db", type=Path,
                    help="default: <repo_name>-persons.db next to the Parquet")
    ap.add_argument("--git-dir", type=Path,
                    help="an existing clone of clone_url (default: clone into the work dir)")
    ap.add_argument("--work-dir", type=Path,
                    help="for the clone and the original DB; kept (default: a temporary "
                         "directory next to the output, removed at the end)")
    ap.add_argument("--keep-work", action="store_true", help="keep the temporary work directory")
    ap.add_argument("--jar", type=Path, default=DEFAULT_JAR, help="the slickGitLog one-jar")
    ap.add_argument("--java", default="java")
    ap.add_argument("--java-opts", default="",
                    help="JVM flags for slickGitLog; write --java-opts=-Xmx3g (with =)")
    ap.add_argument("--report", type=Path, help="append one TSV row per Parquet")
    ap.add_argument("--memory-limit", default="4GB")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--chunk-rows", type=int, default=CHUNK_ROWS,
                    help=f"rows per sorted chunk of the new columns (default {CHUNK_ROWS})")
    args = ap.parse_args(argv)
    if args.chunk_rows < 1:
        ap.error("--chunk-rows must be positive")

    src = args.parquet
    if not src.is_file():
        print(f"FAIL {src} does not exist", file=sys.stderr)
        return 1
    if args.out is not None and args.out.exists():
        print(f"FAIL {args.out} exists", file=sys.stderr)
        return 1
    dst = args.out if args.out is not None else src.with_name(f".{src.name}.footer-tmp")
    spill = dst.parent / ".footer-spill"
    if args.work_dir is not None:
        work, own_work = args.work_dir, False
        work.mkdir(parents=True, exist_ok=True)
    else:
        work, own_work = Path(tempfile.mkdtemp(prefix=".footer-work-", dir=dst.parent)), True
    con = connect(args.memory_limit, args.threads, spill)
    rec = {}
    try:
        check_schema(con, src)
        project = one_value(con, src, "repo_name")
        url = one_value(con, src, "clone_url")
        persons_db = args.persons_db or src.with_name(f"{project}-persons.db")
        if not persons_db.is_file():
            raise Refused(f"no persons DB at {persons_db}")
        rec.update(project=project, rows=con.execute(
            "SELECT count(*) FROM read_parquet($p)", {"p": str(src)}).fetchone()[0])
        if not rec["rows"]:
            raise Refused(f"{src} has no rows")

        t = time.monotonic()
        git_dir = args.git_dir
        if git_dir is None:
            git_dir = work / f"{project}.git"
            if git_dir.exists():
                raise Refused(f"{git_dir} exists; pass it as --git-dir")
            clone(url, git_dir)
        rec.update(clone_s=round(time.monotonic() - t, 1), clone_mb=du_mb(git_dir))

        t = time.monotonic()
        orig_db = work / f"{project}-original.db"
        if orig_db.exists():
            raise Refused(f"{orig_db} exists")
        slickgitlog(args.java, args.jar, git_dir, orig_db, tuple(args.java_opts.split()))
        load(con, work, {"orig": orig_db, "persons": persons_db})
        rec.update(parse_s=round(time.monotonic() - t, 1), db_mb=du_mb(orig_db))

        check_inputs(con, src)
        rec["already_set"] = recompute(con, src)
        before = counts(con, src)

        t = time.monotonic()
        parts = []
        try:
            parts = footer_columns(con, src, work, rec["rows"], args.chunk_rows)
            rewrite(con, src, dst, parts)
            problems = compare(con, src, dst)
        except Exception:
            dst.unlink(missing_ok=True)
            raise
        finally:
            for p in parts:
                p.unlink(missing_ok=True)
        if problems:
            dst.unlink(missing_ok=True)
            print(f"FAIL {src}: the rewrite does not match the source:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            return 1
        after = counts(con, dst)
        rec["any_footer"] = con.execute(
            "SELECT count(DISTINCT cid) FROM original_log.footers "
            "WHERE cid IN (SELECT cid FROM old)"
        ).fetchone()[0]
        rec["rewrite_s"] = round(time.monotonic() - t, 1)
    except Refused as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    finally:
        con.close()
        shutil.rmtree(spill, ignore_errors=True)
        if own_work and not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)
    if args.in_place:
        os.replace(dst, src)
    rec.update(commits=after["commits"], before=before["any"], after=after["any"],
               personids=after["personids"], **{k: after[k] for _, k in TYPED})
    if args.report is not None:
        write_report(args.report, rec)
    print(f"OK {dst if not args.in_place else src}: {project} {rec['commits']} commits, "
          f"{rec['before']} -> {rec['after']} with a typed trailer; "
          "the other columns are identical row by row"
          + (f"; work dir {work}" if (args.keep_work or not own_work) else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
