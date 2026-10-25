#!/usr/bin/env python3
"""Fill the sidecar columns that changed after the run in one finished project Parquet, from a sidecar.
Usage: rewrite_meta_columns.py PARQUET --sidecar project_meta.X.json
       (--out NEW.parquet | --in-place) [--key NAME] [--fields F1,F2,...] [--report TSV]
       [--memory-limit 2GB] [--threads 2]

The columns (--fields, default all 11): the 4 provenance columns license, owner_type,
archived, fork (enrich_meta.py, 2026-10-09); source (the S1 sources, enrich_meta.py); the S6
label columns stratum, fact, contested, label_date; and roster_name, roster_lang (S5). The run
wrote them from the sidecar of its batch, where they were '' (batches 1-6) or partly filled
(batches 6-20: the 4 provenance columns; batches 7-20: source too). The sidecar to use is the
final one, s7-run/project_meta.layer1.final.json (final_meta.py), which holds all 11.

The rewrite is one DuckDB COPY of SELECT * REPLACE (the precedent is ctp's
firm_attribution.py), so the column set, order and types stay. Then every column is compared
with the source row by row (POSITIONAL JOIN, IS DISTINCT FROM): the other columns must be
identical and the chosen ones must hold the sidecar's values. Only then is the file kept
(--in-place: renamed over the source). The key defaults to the file's one repo_name, which ctp
sets to the manifest name. rewrite_footer_columns.py (the 15 footer_* columns) has the same
CLI and touches other columns, so the two can run one after the other on the same file.

Refused: a chosen column already holds a non-blank value that is not the sidecar's value;
clone_url, owner or repo differ from the sidecar (the wrong sidecar or the wrong file); more
than one repo_name; the sidecar record has no such field. One host rule (decision of the user,
2026-10-16): for a clone_url on git.savannah.gnu.org the sidecar owner is gnu (final_meta.py
HOST_OWNER), but the run wrote git or git.savannah.gnu.org. The tool accepts these two old
values and writes gnu in the owner column. The OK line and --report name the change. clone_url
and repo are always checked and never written. A chosen field that is '' in the
sidecar is written as '' and named in the OK line, so a sidecar that is not the final one shows.
--report appends one TSV row for each Parquet: time, parquet, key, result, fields, detail.
Exit 0 written, 1 refused or the comparison failed, 2 usage. Needs the duckdb module."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

PROVENANCE = ("license", "owner_type", "archived", "fork")
LABEL = ("stratum", "fact", "contested", "label_date")
ROSTER = ("roster_name", "roster_lang")
ALL_FIELDS = ("source",) + LABEL + ROSTER + PROVENANCE
FIELDS = ALL_FIELDS  # the default of --fields
CHECKED = ("clone_url", "owner", "repo")
# COPY options per --encoding. "default" is the encoding of the runs. "v1" is the encoding of the
# published v1 (user decision, 2026-10-16): about 70-73% of the default size, the same values.
ENCODINGS = {"default": "FORMAT PARQUET, COMPRESSION ZSTD",
             "v1": "FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 19, ROW_GROUP_SIZE 1000000, "
                   "PARQUET_VERSION V2"}
HOST_OWNER = {"git.savannah.gnu.org": "gnu"}  # the same rule as final_meta.HOST_OWNER
OLD_OWNER = {"git.savannah.gnu.org": {"git", "git.savannah.gnu.org"}}  # what the run wrote


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


def host_owner_ok(record: dict, seen: set) -> bool:
    """True when the host rule accepts the Parquet owner values in seen."""
    host = urlsplit(record.get("clone_url", "")).hostname
    return (host in HOST_OWNER and record.get("owner") == HOST_OWNER[host]
            and seen <= OLD_OWNER[host] | {HOST_OWNER[host]})


def distinct(con, src: Path, f: str) -> set:
    return {r[0] for r in con.execute(
        f"SELECT DISTINCT {q(f)} FROM read_parquet($p)", {"p": str(src)}).fetchall()}


def refusal(con, src: Path, values: dict, record: dict) -> str | None:
    cols = dict(schema(con, src))
    for f in tuple(values) + CHECKED + ("repo_name",):
        if cols.get(f) != "VARCHAR":
            return f"{src}: column {f} is {cols.get(f)!r}, not VARCHAR"
    for f in values:
        seen = {r[0] for r in con.execute(
            f"SELECT DISTINCT {q(f)} FROM read_parquet($p)", {"p": str(src)}).fetchall()}
        if not seen <= {"", values[f]}:
            return f"{src}: {f} already holds {sorted(map(repr, seen))}, the sidecar says {values[f]!r}"
    for f in CHECKED:
        seen = distinct(con, src, f)
        if f == "owner" and host_owner_ok(record, seen):
            continue
        if seen != {record.get(f, "")}:
            return f"{src}: {f} is {sorted(map(repr, seen))}, the sidecar says {record.get(f)!r}"
    return None


def rewrite(con, src: Path, dst: Path, values: dict, encoding: str = "default") -> None:
    """One streaming COPY. preserve_insertion_order (DuckDB's default) keeps the row order of a
    plain projection; compare() checks it row by row."""
    replace = ", ".join(f"${f} AS {q(f)}" for f in values)
    con.execute("SET preserve_insertion_order = true")
    con.execute(f"COPY (SELECT * REPLACE ({replace}) FROM read_parquet($src)) "
                f"TO $dst ({ENCODINGS[encoding]})",
                {"src": str(src), "dst": str(dst), **values})


def compare(con, src: Path, dst: Path, values: dict) -> list[str]:
    """Problems; [] when the other columns are identical row by row and the chosen hold the values."""
    a, b = schema(con, src), schema(con, dst)
    if a != b:
        return [f"schema differs: {a} vs {b}"]
    n_a = con.execute("SELECT count(*) FROM read_parquet($p)", {"p": str(src)}).fetchone()[0]
    n_b = con.execute("SELECT count(*) FROM read_parquet($p)", {"p": str(dst)}).fetchone()[0]
    if n_a != n_b:
        return [f"rows differ: {n_a} vs {n_b}"]
    names = [n for n, _ in a]
    terms = []
    for n in names:
        if n in values:
            terms.append(f"count(*) FILTER (WHERE b.{q(n)} IS DISTINCT FROM ${n})")
        else:
            terms.append(f"count(*) FILTER (WHERE a.{q(n)} IS DISTINCT FROM b.{q(n)})")
    row = con.execute(
        f"SELECT {', '.join(terms)} FROM (SELECT * FROM read_parquet($src)) a "
        "POSITIONAL JOIN (SELECT * FROM read_parquet($dst)) b",
        {"src": str(src), "dst": str(dst), **values}).fetchone()
    return [f"{n}: {k} of {n_a} rows differ" for n, k in zip(names, row) if k]


def parse_fields(text: str) -> tuple[str, ...]:
    fields = tuple(f.strip() for f in text.split(",") if f.strip())
    bad = [f for f in fields if f not in ALL_FIELDS]
    if bad or not fields or len(set(fields)) != len(fields):
        raise argparse.ArgumentTypeError(
            f"--fields takes a comma list of distinct names from {','.join(ALL_FIELDS)}; got {text!r}")
    return fields


def report(path: Path | None, src: Path, key: str, result: str, fields, detail: str) -> None:
    if path is None:
        return
    t = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\t".join([t, str(src), key, result, ",".join(fields),
                            detail.replace("\t", " ").replace("\n", " ")]) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("parquet", type=Path)
    ap.add_argument("--sidecar", required=True, type=Path)
    dest = ap.add_mutually_exclusive_group(required=True)
    dest.add_argument("--out", type=Path)
    dest.add_argument("--in-place", action="store_true")
    ap.add_argument("--key", help="sidecar key (default: the file's one repo_name)")
    ap.add_argument("--fields", type=parse_fields, default=FIELDS,
                    help=f"comma list of the columns to fill (default: {','.join(FIELDS)})")
    ap.add_argument("--report", type=Path, help="append one TSV row per Parquet")
    ap.add_argument("--memory-limit", default="2GB")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--encoding", choices=sorted(ENCODINGS), default="default",
                    help="COPY options of the output (default: the encoding of the runs)")
    args = ap.parse_args(argv)

    src = args.parquet
    key = args.key or ""

    def fail(msg: str) -> int:
        print(f"FAIL {msg}", file=sys.stderr)
        report(args.report, src, key, "FAIL", args.fields, msg)
        return 1

    if args.out is not None and args.out.exists():
        return fail(f"{args.out} exists")
    dst = args.out if args.out is not None else src.with_name(f".{src.name}.meta-tmp")
    # One spill directory per output: jobs that write into the same directory must not delete
    # the spill of each other (final_merge.py, 2026-10-16).
    spill = dst.parent / f".meta-spill-{dst.name}"
    con = connect(args.memory_limit, args.threads, spill)
    try:
        if not key:
            names = [r[0] for r in con.execute(
                "SELECT DISTINCT repo_name FROM read_parquet($p)", {"p": str(src)}).fetchall()]
            if len(names) != 1:
                return fail(f"{src}: {len(names)} repo_name values; pass --key")
            key = names[0]
        meta = json.loads(args.sidecar.read_text(encoding="utf-8"))
        if key not in meta:
            return fail(f"{key} is not in {args.sidecar}")
        record = meta[key]
        missing = [f for f in args.fields if f not in record]
        if missing:
            return fail(f"{args.sidecar}: the record {key} has no field {', '.join(missing)}")
        values = {f: record[f] for f in args.fields}
        reason = refusal(con, src, values, record)
        if reason:
            return fail(reason)
        # The refusal check passed. Thus an old owner that is not the sidecar's is a host rule case.
        old_owner = sorted(distinct(con, src, "owner") - {record["owner"]})
        written = dict(values, owner=record["owner"]) if old_owner else values
        try:
            rewrite(con, src, dst, written, args.encoding)
            problems = compare(con, src, dst, written)
        except Exception:
            dst.unlink(missing_ok=True)
            raise
        if problems:
            dst.unlink(missing_ok=True)
            print(f"FAIL {src}: the rewrite does not match the source:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
            report(args.report, src, key, "FAIL", args.fields, "; ".join(problems))
            return 1
    finally:
        con.close()
        shutil.rmtree(spill, ignore_errors=True)
    if args.in_place:
        os.replace(dst, src)
    blank = [f for f in args.fields if values[f] == ""]
    detail = (" ".join(f"{f}={values[f]!r}" for f in args.fields)
              + (f"; blank in the sidecar: {','.join(blank)}" if blank else "")
              + (f"; owner rewritten: {','.join(map(repr, old_owner))} -> {record['owner']!r}"
                 if old_owner else ""))
    print(f"OK {dst if not args.in_place else src}: {key} {detail}"
          "; the other columns are identical row by row")
    report(args.report, dst if not args.in_place else src, key, "OK", args.fields, detail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
