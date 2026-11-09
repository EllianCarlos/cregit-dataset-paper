"""integrity_check.py: the integrity check of a local root of the dataset "Token on Me" (TOM) 1.0.0.

DuckDB and Parquet have no PRAGMA integrity_check (SQLite). This tool does the same work for a TOM root:
  1. Each file of SHA256SUMS: the file is there, and its sha256 is its row (a project file: also its MANIFEST.tsv row).
     A file of the root that is not in SHA256SUMS is a problem.
  2. Each Parquet file: the footer parses. A project file has the 53 TOM columns in order and type, and the footer key
     set of the reference file. Each footer value outside the pseudonymization_* keys is the reference value.
  3. Each Parquet file is read in full: every row group, every column chunk, every page is decoded (pyarrow, one row
     group at a time, page CRC verification on). The tool also validates the decoded arrays and compares the null
     count and min/max of each flat column chunk with the footer statistics. Rows read = footer rows = MANIFEST rows
     (project files) or the release_info rows (side tables).
  4. organizations/dataset.duckdb opens read-only; each view runs SELECT count(*). The tokens view count is the
     MANIFEST.tsv total; a tokens_* view has the row count of tokens.
Output (--out): integrity.tsv (one row per file), integrity.json, INTEGRITY.md. Exit 0 when there are 0 problems.

  python -I integrity_check.py check --root ROOT --out OUT [--jobs 16]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import multiprocessing as mp
import os
import platform
import re
import struct
import sys
import threading
import time
from pathlib import Path

SUFFIX = "-dataset.parquet"
REF_DEFAULT = "parquet/tio__tio-dataset.parquet"
COLS = ["path", "kind", "bytes", "sha256_ok", "footer_ok", "row_groups", "rows_footer", "rows_manifest", "rows_read",
        "columns", "schema_ok", "decode_ok", "page_crc", "seconds", "error"]
# The TOM 1.0.0 schema (53 columns, in order): the Arrow types that pyarrow reads from the published files.
S, I, L = "string", "int64", "list<element: string>"
TOM_SCHEMA = (
    [(n, S) for n in ("repo_name", "clone_url", "audit_frame_file", "source", "stratum", "contested", "label_date",
                      "owner", "repo", "roster_name", "language", "commits", "size_class", "stars", "pushed_at",
                      "license", "owner_type", "file_path")]
    + [("token_index", I), ("source_line", I), ("source_col", I), ("source_text", S), ("token_type", S),
       ("token_value", S), ("is_structural", I)]
    + [(n, S) for n in ("original_commit_sha", "author_name", "author_email", "author_date", "committer_name",
                        "committer_email", "committer_date", "commit_summary", "personid", "person_domain")]
    + [(f"footer_{n}", L) for n in ("signed_off_by", "co_authored_by", "co_developed_by", "reviewed_by", "acked_by",
                                    "tested_by", "reported_by", "suggested_by", "based_on_patch_by", "helped_by",
                                    "mentored_by", "assisted_by", "thanks_to", "personids")]
    + [("firm_based_on_namespace", S), ("firm_based_on_domain", S), ("project_enterprise_driven", "bool"),
       ("project_enterprise_basis", S)])
TOM_KEYS = sorted(["ctp_schema_version", "organizations_mapping_sha256", "organizations_version",
                   "pseudonymization_registry_sha256", "pseudonymization_version"])


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def say(text: str) -> None:
    print(text.replace("@", "(at)"), flush=True)


def sha256(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_sums(p) -> dict[str, str]:
    out = {}
    for line in Path(p).read_text().splitlines():
        if line.strip():
            d, f = line.split("  ", 1)
            if f in out:
                raise SystemExit(f"ABORT: {f} twice in {p}")
            out[f] = d
    return out


def read_tsv(p) -> list[dict]:
    with open(p, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def kind_of(rel: str) -> str:
    if rel.startswith("parquet/") and rel.endswith(SUFFIX):
        return "project"
    if rel == "organizations/dataset.duckdb":
        return "db"
    if rel.endswith(".parquet"):
        return "side"
    return "other"


# ------------------------------------------------------------------------------------------------ page CRC --
def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = val = 0
    while True:
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7


def page_has_crc(fh, offset: int) -> bool:
    """Read the Thrift compact PageHeader at offset: True if the optional field 4 (crc) is there."""
    fh.seek(offset)
    buf = fh.read(64)
    i = last = 0
    while i < len(buf):
        b = buf[i]
        i += 1
        if b == 0:
            return False
        delta, typ = b >> 4, b & 0x0F
        if delta:
            fid = last + delta
        else:
            z, i = _varint(buf, i)
            fid = (z >> 1) ^ -(z & 1)
        if fid == 4:
            return True
        if fid > 4 or typ != 5:
            return False
        _, i = _varint(buf, i)
        last = fid
    raise ValueError(f"no page header at offset {offset}")


def crc_state(path, md) -> str:
    have = total = 0
    with open(path, "rb") as fh:
        for g in range(md.num_row_groups):
            rg = md.row_group(g)
            for c in range(rg.num_columns):
                cc = rg.column(c)
                off = cc.dictionary_page_offset if cc.has_dictionary_page else cc.data_page_offset
                total += 1
                have += page_has_crc(fh, off)
    if total == 0:
        return "no pages"
    if have == total:
        return "checked"
    if have == 0:
        return "not written"
    return f"partial {have}/{total}"


# ------------------------------------------------------------------------------------------------ one file --
def _min_ok(got: bytes, stat: bytes) -> bool:
    """The min read is the statistics min, or its cut prefix (DuckDB cuts string statistics at 256 bytes)."""
    return got == stat or (len(stat) >= 128 and got.startswith(stat))


def _max_ok(got: bytes, stat: bytes) -> bool:
    """The max read is the statistics max, or the cut max with the last byte plus one (an upper bound)."""
    return got == stat or (len(stat) >= 128 and got.startswith(stat[:-1]) and got < stat)


def _stat_value(st, typ: str):
    if typ == "bool":
        return bool(st.min), bool(st.max)
    return st.min, st.max


def decode_file(path: str, batch_rows: int, minmax: bool = True) -> tuple[int, list[str], int]:
    """Read every row group of the file in full. Return (rows read, problems, chunks decoded)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    probs = []
    pf = pq.ParquetFile(path, page_checksum_verification=True, pre_buffer=False)
    md = pf.metadata
    schema = pf.schema_arrow
    flat = {i: str(f.type) for i, f in enumerate(schema)
            if not (pa.types.is_list(f.type) or pa.types.is_struct(f.type) or pa.types.is_map(f.type)
                    or pa.types.is_large_list(f.type))}
    leaf_of = {}
    for j in range(md.num_columns):
        top = md.schema.column(j).path.split(".")[0]
        leaf_of.setdefault(top, j)
    rows = chunks = 0
    for g in range(md.num_row_groups):
        rg = md.row_group(g)
        got = 0
        nulls = {i: 0 for i in flat}
        mins: dict[int, object] = {}
        maxs: dict[int, object] = {}
        for batch in pf.iter_batches(batch_size=batch_rows, row_groups=[g], use_threads=False):
            batch.validate(full=True)
            got += batch.num_rows
            for i, typ in flat.items():
                col = batch.column(i)
                nulls[i] += col.null_count
                if minmax and typ in ("int64", "int32", "double", "float", "bool", "string") and col.null_count < len(col):
                    mm = pc.min_max(col)
                    lo, hi = mm["min"].as_py(), mm["max"].as_py()
                    if lo is not None:
                        mins[i] = lo if i not in mins else min(mins[i], lo)
                        maxs[i] = hi if i not in maxs else max(maxs[i], hi)
        chunks += rg.num_columns
        rows += got
        if got != rg.num_rows:
            probs.append(f"row group {g}: {got} rows read, footer {rg.num_rows}")
        for i, typ in flat.items():
            name = schema.field(i).name
            st = rg.column(leaf_of[name]).statistics
            if st is None:
                continue
            if st.has_null_count and st.null_count != nulls[i]:
                probs.append(f"row group {g} {name}: {nulls[i]} nulls read, statistics {st.null_count}")
            if st.has_min_max and i in mins:
                if typ == "string":
                    lo, hi = st.min_raw, st.max_raw
                    lo = lo if isinstance(lo, bytes) else str(lo).encode()
                    hi = hi if isinstance(hi, bytes) else str(hi).encode()
                    ok = _min_ok(mins[i].encode(), lo) and _max_ok(maxs[i].encode(), hi)
                else:
                    lo, hi = _stat_value(st, typ)
                    ok = lo == mins[i] and hi == maxs[i]
                if not ok:
                    probs.append(f"row group {g} {name}: min/max read {str(mins[i])[:40]!r}/{str(maxs[i])[:40]!r}, "
                                 f"statistics {str(lo)[:40]!r}/{str(hi)[:40]!r}")
    return rows, probs, chunks


def check_file(job: dict) -> dict:
    import pyarrow as pa
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    import pyarrow.parquet as pq
    t0 = time.time()
    rel, path, kind = job["rel"], job["path"], job["kind"]
    row = {c: "-" for c in COLS}
    row.update(path=rel, kind=kind, error="")
    errs = []
    if not os.path.isfile(path):
        row.update(sha256_ok="no", error="missing: the file is in SHA256SUMS but not in the root", seconds="0.0")
        return row
    row["bytes"] = str(os.path.getsize(path))
    if job.get("man_bytes") is not None and int(job["man_bytes"]) != int(row["bytes"]):
        errs.append(f"{row['bytes']} B, MANIFEST {job['man_bytes']} B")
    try:
        got = sha256(path)
    except OSError as e:
        got = None
        errs.append(f"read: {e}")
    ok = got is not None and got == job["want_sha"] and (job.get("man_sha") in (None, got))
    row["sha256_ok"] = "yes" if ok else "no"
    if not ok and got is not None:
        if got != job["want_sha"]:
            errs.append(f"sha256 {got[:12]} is not the SHA256SUMS row {job['want_sha'][:12]}")
        if job.get("man_sha") not in (None, got):
            errs.append(f"sha256 {got[:12]} is not the MANIFEST row {job['man_sha'][:12]}")
    if kind in ("project", "side"):
        try:
            pf = pq.ParquetFile(path)
            md = pf.metadata
            row.update(footer_ok="yes", row_groups=str(md.num_row_groups), rows_footer=str(md.num_rows),
                       columns=str(len(pf.schema_arrow)))
        except Exception as e:  # noqa: BLE001
            row["footer_ok"] = "no"
            errs.append(f"footer: {type(e).__name__}: {str(e)[:160]}")
            md = None
        if md is not None:
            if job.get("rows_want") is not None:
                row["rows_manifest"] = str(job["rows_want"])
                if int(job["rows_want"]) != md.num_rows:
                    errs.append(f"footer rows {md.num_rows}, {job['rows_src']} {job['rows_want']}")
            if kind == "project":
                schema = [(f.name, str(f.type)) for f in pf.schema_arrow]
                kv = {k.decode(): v.decode() for k, v in (md.metadata or {}).items()}
                why = []
                if schema != job["ref_schema"]:
                    why.append("columns, order or types")
                if sorted(kv) != job["ref_keys"]:
                    why.append(f"footer keys {sorted(kv)}")
                diff = [k for k, v in job["ref_values"].items() if kv.get(k) != v]
                if diff:
                    why.append(f"footer values {diff}")
                row["schema_ok"] = "no" if why else "yes"
                if why:
                    errs.append("schema: " + "; ".join(why))
            try:
                row["page_crc"] = crc_state(path, md)
            except Exception as e:  # noqa: BLE001
                row["page_crc"] = "unreadable"
                errs.append(f"page header: {type(e).__name__}: {str(e)[:120]}")
            try:
                n, probs, _ = decode_file(path, job["batch_rows"], job["minmax"])
                row["rows_read"] = str(n)
                row["decode_ok"] = "no" if probs else "yes"
                errs += probs[:5]
                if n != md.num_rows:
                    errs.append(f"{n} rows read, footer {md.num_rows}")
            except Exception as e:  # noqa: BLE001
                row["decode_ok"] = "no"
                errs.append(f"decode: {type(e).__name__}: {str(e)[:200]}")
    row["seconds"] = f"{time.time() - t0:.1f}"
    row["error"] = " | ".join(errs).replace("\t", " ").replace("\n", " ")
    return row


# ------------------------------------------------------------------------------------------------ the views --
def check_views(root: Path, threads: int, memory: str, tmp: str | None, timeout: int, total_rows: int,
                skip: str | None) -> tuple[list[dict], list[str]]:
    import duckdb
    probs, out = [], []
    cwd = os.getcwd()
    os.chdir(root)
    try:
        con = duckdb.connect(str(root / "organizations" / "dataset.duckdb"), read_only=True)
        con.execute(f"SET threads = {int(threads)}")
        con.execute(f"SET memory_limit = '{memory}'")
        if tmp:
            os.makedirs(tmp, exist_ok=True)
            con.execute(f"SET temp_directory = '{tmp}'")
        views = [x[0] for x in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal "
                                           "ORDER BY view_name").fetchall()]
        tables = [x[0] for x in con.execute("SELECT table_name FROM duckdb_tables() WHERE NOT internal").fetchall()]
        if tables:
            probs.append(f"dataset.duckdb has tables (expected views only): {tables[:5]}")
        order = sorted(views, key=lambda v: (v.startswith("tokens_"), v))
        counts = {}
        for v in order:
            if skip and re.fullmatch(skip, v):
                out.append({"view": v, "rows": "skipped", "seconds": "0"})
                continue
            t0 = time.time()
            timer = threading.Timer(timeout, con.interrupt)
            timer.start()
            try:
                n = con.execute(f'SELECT count(*) FROM "{v}"').fetchone()[0]
                counts[v] = n
                out.append({"view": v, "rows": str(n), "seconds": f"{time.time() - t0:.1f}"})
            except Exception as e:  # noqa: BLE001
                msg = "timeout" if time.time() - t0 >= timeout else f"{type(e).__name__}: {str(e)[:160]}"
                probs.append(f"view {v}: {msg}")
                out.append({"view": v, "rows": "error", "seconds": f"{time.time() - t0:.1f}", "error": msg})
            finally:
                timer.cancel()
            say(f"[{utc()}] view {v}: {out[-1]['rows']} rows in {out[-1]['seconds']} s")
        if "tokens" not in counts:
            probs.append("no count for the view tokens")
        elif counts["tokens"] != total_rows:
            probs.append(f"view tokens: {counts['tokens']:,} rows, MANIFEST.tsv total {total_rows:,}")
        for v, n in counts.items():
            if v.startswith("tokens_") and "tokens" in counts and n != counts["tokens"]:
                probs.append(f"view {v}: {n:,} rows, tokens {counts['tokens']:,}")
        if counts.get("stale_files", 0):
            probs.append(f"view stale_files: {counts['stale_files']} files have another organizations_mapping_sha256")
        con.close()
    except Exception as e:  # noqa: BLE001
        probs.append(f"dataset.duckdb: {type(e).__name__}: {str(e)[:200]}")
    finally:
        os.chdir(cwd)
    return out, probs


# ------------------------------------------------------------------------------------------------ the report --
METHOD = """1. The tool computes the sha256 of each file and compares it with its SHA256SUMS row (and the MANIFEST.tsv row).
2. It reads the Parquet footer of each file. A project file must have the 53 TOM columns, in order and type.
3. A project file must have the footer key set and the footer values (not the pseudonymization keys) of {ref}.
4. It decodes each row group, column chunk and page with pyarrow, one row group at a time.
5. It validates the decoded arrays, and compares {stats} of each flat column chunk with the footer statistics.
6. Rows read must be the footer rows and the MANIFEST.tsv rows (side tables: the release_info rows).
7. It opens organizations/dataset.duckdb read-only and counts the rows of each view with DuckDB.
8. The tokens view count must be the MANIFEST.tsv total. Page CRC: {crc}."""


def write_md(path: Path, s: dict) -> None:
    t = s["totals"]
    crc = ", ".join(f"{k}: {v:,} files" for k, v in sorted(s["page_crc"].items())) or "none"
    n_crc = s["page_crc"].get("checked", 0)
    if n_crc == t["parquet_files"]:
        crc_text = "each file has page CRCs, and pyarrow verified each page CRC"
    elif n_crc == 0:
        crc_text = "the writer did not write page CRCs, so the sha256 is the byte check of the pages"
    else:
        crc_text = (f"{n_crc:,} of {t['parquet_files']:,} files have page CRCs (pyarrow verified them); "
                    "for the other files the sha256 is the byte check of the pages")
    lines = [
        "# Integrity check of TOM 1.0.0",
        "",
        "DuckDB and Parquet do not have an integrity check like `PRAGMA integrity_check` of SQLite. This file is the "
        "report of `integrity_check.py`, a check that reads the full release.",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| Date (UTC) | {s['finished']} |",
        f"| Result | **{'0 problems' if s['problems_total'] == 0 else str(s['problems_total']) + ' problems'}** |",
        f"| Root | `{s['root_name']}` |",
        f"| SHA256SUMS checked | `{s['sha256sums_sha256']}` |",
        f"| Files checked | {t['files']:,} ({t['project_files']:,} project files, {t['side_files']:,} side tables, "
        f"1 database, {t['other_files']:,} other files) |",
        f"| Bytes read | {t['bytes']:,} |",
        f"| Token rows read | {t['project_rows_read']:,} (MANIFEST.tsv: {t['manifest_rows']:,}) |",
        f"| Side table rows read | {t['side_rows_read']:,} |",
        f"| Row groups decoded | {t['row_groups']:,} |",
        f"| Column chunks decoded | {t['column_chunks']:,} |",
        f"| Page CRC | {crc} |",
        f"| Views counted | {len(s['views'])} (tokens: {s['tokens_view_rows']}) |",
        f"| Tools | Python {s['tools']['python']}, pyarrow {s['tools']['pyarrow']}, DuckDB {s['tools']['duckdb']} |",
        f"| Time | {s['seconds']:,.0f} s with {s['jobs']} jobs |",
        "",
        "## Method",
        "",
        METHOD.format(ref=f"`{s['ref']}`", crc=crc_text, stats="the nulls" if s["no_minmax"] else "the nulls and min/max"),
        "",
        "## Views",
        "",
        "| View | Rows | Seconds |",
        "|---|---:|---:|",
    ] + [f"| `{v['view']}` | {int(v['rows']):,} | {v['seconds']} |" if v["rows"].isdigit() else
         f"| `{v['view']}` | {v['rows']} | {v['seconds']} |" for v in s["views"]] + [
        "",
        "## Problems",
        "",
    ]
    if s["problems_total"] == 0:
        lines.append("None.")
    else:
        lines += [f"- {p}" for p in s["problems"][:200]]
        if s["problems_total"] > 200:
            lines.append(f"- ... and {s['problems_total'] - 200} more (see `integrity.tsv`)")
    lines += ["", "`integrity.tsv` has one row for each file. Columns: " + ", ".join(f"`{c}`" for c in COLS) + ".", ""]
    path.write_text("\n".join(lines))


def cmd_check(a) -> int:
    import duckdb
    import pyarrow
    import pyarrow.parquet as pq
    t_start = time.time()
    started = utc()
    root = Path(a.root).resolve()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    root_probs: list[str] = []
    sums = read_sums(root / "SHA256SUMS")
    on_disk = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    for rel in sorted(on_disk - set(sums) - {"SHA256SUMS"}):
        root_probs.append(f"{rel}: in the root, not in SHA256SUMS")
    man = read_tsv(root / "MANIFEST.tsv")
    man_by = {r["path"]: r for r in man}
    if len(man_by) != len(man):
        root_probs.append("MANIFEST.tsv has a path twice")
    projects = sorted(r for r in sums if kind_of(r) == "project")
    if set(projects) != set(man_by):
        root_probs.append(f"MANIFEST.tsv paths are not the SHA256SUMS project files: "
                          f"{sorted(set(projects) ^ set(man_by))[:5]}")
    if a.expect_files is not None and len(projects) != a.expect_files:
        root_probs.append(f"{len(projects):,} project files, expected {a.expect_files:,}")
    if len(projects) >= a.max_files:
        root_probs.append(f"{len(projects):,} project files: the limit of one folder is {a.max_files:,}")
    manifest_rows = sum(int(r["rows"]) for r in man)
    if a.expect_rows is not None and manifest_rows != a.expect_rows:
        root_probs.append(f"MANIFEST.tsv total {manifest_rows:,} rows, expected {a.expect_rows:,}")

    ref = root / a.ref
    if not ref.is_file() or sha256(ref) != sums.get(a.ref):
        raise SystemExit(f"ABORT: the reference {a.ref} is not in the root or is not its SHA256SUMS row")
    rmd = pq.ParquetFile(ref)
    ref_schema = [(f.name, str(f.type)) for f in rmd.schema_arrow]
    ref_kv = {k.decode(): v.decode() for k, v in (rmd.metadata.metadata or {}).items()}
    if [list(x) for x in ref_schema] != [list(x) for x in TOM_SCHEMA] or len(ref_schema) != a.expect_columns:
        root_probs.append(f"the reference {a.ref} does not have the TOM schema of this tool ({len(ref_schema)} columns)")
    if sorted(ref_kv) != TOM_KEYS:
        root_probs.append(f"the reference {a.ref} does not have the TOM footer keys: {sorted(ref_kv)}")
    ref_values = {k: v for k, v in ref_kv.items() if not k.startswith("pseudonymization_")}

    info = {}
    ri = root / "organizations" / "release_info.parquet"
    if ri.is_file() and sha256(ri) == sums.get("organizations/release_info.parquet"):
        t = pq.read_table(ri)
        info = dict(zip(t.column("key").to_pylist(), t.column("value").to_pylist()))
    else:
        root_probs.append("organizations/release_info.parquet is missing or is not its SHA256SUMS row")
    for rel in sorted(sums):
        if rel.startswith("organizations/") and rel.endswith(".parquet") and rel != "organizations/release_info.parquet":
            stem = Path(rel).stem
            if info and info.get(f"{stem}_sha256") != sums[rel]:
                root_probs.append(f"release_info: {stem}_sha256 is not the SHA256SUMS row of {rel}")
    if info and info.get("dataset_db_sha256") != sums.get("organizations/dataset.duckdb"):
        root_probs.append("release_info: dataset_db_sha256 is not the SHA256SUMS row of organizations/dataset.duckdb")

    jobs = []
    for rel in sorted(sums):
        k = kind_of(rel)
        j = {"rel": rel, "path": str(root / rel), "kind": k, "want_sha": sums[rel], "batch_rows": a.batch_rows,
             "minmax": not a.no_minmax}
        if k == "project":
            m = man_by.get(rel, {})
            j.update(man_sha=m.get("sha256"), man_bytes=m.get("bytes"), rows_want=m.get("rows"),
                     rows_src="MANIFEST", ref_schema=ref_schema, ref_keys=sorted(ref_kv), ref_values=ref_values)
        elif k == "side" and rel.startswith("organizations/") and info.get(f"{Path(rel).stem}_rows") is not None:
            j.update(rows_want=info[f"{Path(rel).stem}_rows"], rows_src="release_info")
        try:
            j["size"] = os.path.getsize(j["path"])
        except OSError:
            j["size"] = 0
        jobs.append(j)
    jobs.sort(key=lambda j: -j["size"])
    total_bytes = sum(j["size"] for j in jobs)
    say(f"[{utc()}] integrity check of {root.name}: {len(jobs):,} files ({len(projects):,} project files), "
        f"{total_bytes:,} B; {a.jobs} jobs")

    rows, done_b, t_last = [], 0, time.time()
    with cf.ProcessPoolExecutor(max_workers=a.jobs, mp_context=mp.get_context("spawn")) as ex:
        futs = {ex.submit(check_file, j): j for j in jobs}
        for fu in cf.as_completed(futs):
            j = futs[fu]
            try:
                r = fu.result()
            except Exception as e:  # noqa: BLE001
                r = {c: "-" for c in COLS}
                r.update(path=j["rel"], kind=j["kind"], sha256_ok="no", error=f"worker: {type(e).__name__}: {e}")
            rows.append(r)
            done_b += j["size"]
            if r["error"]:
                say(f"PROBLEM {r['path']}: {r['error'][:300]}")
            if time.time() - t_last > a.progress:
                t_last = time.time()
                say(f"[{utc()}] {len(rows):,}/{len(jobs):,} files, {done_b / 1e9:,.1f}/{total_bytes / 1e9:,.1f} GB, "
                    f"{sum(1 for x in rows if x['error']):,} with problems, {time.time() - t_start:,.0f} s")
    rows.sort(key=lambda r: r["path"])
    say(f"[{utc()}] files done: {len(rows):,} in {time.time() - t_start:,.0f} s")

    views, view_probs = check_views(root, a.db_threads or os.cpu_count() or 4, a.memory_limit, a.tmp,
                                    a.view_timeout, manifest_rows, a.skip_views)

    with open(out / "integrity.tsv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    file_probs = [f"{r['path']}: {r['error']}" for r in rows if r["error"]]
    probs = root_probs + file_probs + view_probs
    pq_rows = [r for r in rows if r["kind"] in ("project", "side")]
    crc = {}
    for r in pq_rows:
        crc[r["page_crc"]] = crc.get(r["page_crc"], 0) + 1

    def isum(rs, c):
        return sum(int(r[c]) for r in rs if r[c] not in ("-", ""))

    by = {k: [r for r in rows if r["kind"] == k] for k in ("project", "side", "db", "other")}
    chunks = sum(int(r["row_groups"]) * int(r["columns"]) for r in pq_rows
                 if r["row_groups"] != "-" and r["columns"] != "-")
    s = {
        "tool": "integrity_check.py", "started": started, "finished": utc(), "seconds": time.time() - t_start,
        "jobs": a.jobs, "root_name": a.root_name or root.name, "ref": a.ref, "no_minmax": a.no_minmax,
        "sha256sums_sha256": sha256(root / "SHA256SUMS"),
        "tools": {"python": platform.python_version(), "pyarrow": pyarrow.__version__, "duckdb": duckdb.__version__},
        "totals": {"files": len(rows), "project_files": len(by["project"]), "side_files": len(by["side"]),
                   "other_files": len(by["other"]), "parquet_files": len(pq_rows),
                   "bytes": isum(rows, "bytes"), "project_rows_read": isum(by["project"], "rows_read"),
                   "manifest_rows": manifest_rows, "side_rows_read": isum(by["side"], "rows_read"),
                   "row_groups": isum(pq_rows, "row_groups"), "column_chunks": chunks},
        "page_crc": crc, "views": views,
        "tokens_view_rows": next((f"{int(v['rows']):,}" for v in views if v["view"] == "tokens"
                                  and v["rows"].isdigit()), "-"),
        "problems_total": len(probs), "problems": probs[:1000],
    }
    if s["totals"]["project_rows_read"] != manifest_rows:
        probs.append(f"token rows read {s['totals']['project_rows_read']:,}, MANIFEST.tsv total {manifest_rows:,}")
        s["problems_total"], s["problems"] = len(probs), probs[:1000]
    (out / "integrity.json").write_text(json.dumps(s, indent=1) + "\n")
    write_md(out / "INTEGRITY.md", s)
    say(f"integrity: {len(rows):,} files ({len(by['project']):,} project), {s['totals']['bytes']:,} B, "
        f"{s['totals']['project_rows_read']:,} token rows (MANIFEST {manifest_rows:,}), {len(views)} views; "
        f"page CRC {crc}; problems {len(probs)}; {s['seconds']:,.0f} s")
    for p in probs[:10]:
        say("PROBLEM: " + p[:300])
    return 0 if not probs else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("check", help="check a local root")
    s.add_argument("--root", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    s.add_argument("--ref", default=REF_DEFAULT, help="the reference project file, relative to the root")
    s.add_argument("--root-name", default=None, help="the root name in the report (default: the folder name)")
    s.add_argument("--expect-files", type=int, default=None)
    s.add_argument("--expect-rows", type=int, default=None)
    s.add_argument("--expect-columns", type=int, default=53)
    s.add_argument("--max-files", type=int, default=9999)
    s.add_argument("--batch-rows", type=int, default=131072)
    s.add_argument("--db-threads", type=int, default=None)
    s.add_argument("--memory-limit", default="40GB")
    s.add_argument("--tmp", default=None, help="the DuckDB temp folder")
    s.add_argument("--view-timeout", type=int, default=7200)
    s.add_argument("--skip-views", default=None, help="a regular expression of views not to count")
    s.add_argument("--no-minmax", action="store_true", help="do not compare min/max with the statistics (faster)")
    s.add_argument("--progress", type=int, default=300, help="seconds between progress lines")
    a = ap.parse_args(argv)
    return {"check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
