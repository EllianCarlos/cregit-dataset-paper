#!/usr/bin/env python3
"""The tools of the second TOM release pass (kit dataset-tom-2). Subcommands:

  prepare     (this host, S1) the inputs of the stage from the value-fix tables: fills.tsv (project, column, old,
              new, basis), project_languages.parquet and project_labels.parquet (the kept projects only).
  keep        the project list (the 8,447 of the first pass) plus ADD_PROJECTS, resolved against the SHA256SUMS of
              the first root (TOM-1) and of the source root: project, file, origin (tom1 or src).
  footers     the footer of every TOM-1 project file (S3 ranged reads, or a local folder): the tail bytes and one
              JSON line per file (size, rows, columns, schema, key-values, the statistics of the fill columns).
  plan        the kind of each file (unchanged, value, new) and its values; checks the old values in the footer
              statistics and that every empty language cell has a fill; picks the canary files.
  pass        the value pass, one process per file: input sha256, the audit of the dropped columns (new files),
              parquet_rename.py --values (with --drop, --rename, --set-kv for new files), parquet_rename_check.py,
              the output sha256; one ledger line per file. --only-list runs the canary files.
  facts       project_facts.parquet: the TOM-1 rows and the facts of the new files.
  tables      the side tables project_languages and project_labels, their release_info rows and their views.
  manifest    MANIFEST.tsv: the TOM-1 rows, the rows of the changed files (fill_release.py manifest of a mini root).
  sums        SHA256SUMS: the TOM-1 rows of the unchanged files and the sha256 of every local file.
  view        the check view: the local root (hard links) and a sparse file with the real footer for each
              unchanged file (only footers can be read from it).
  values      the measured values of the placeholders.
  keys        the known placeholder keys.
  check-root  the checks of the new root (footers of all files, values, SHA256SUMS, MANIFEST.tsv, tables, views).
  hf-push     the Hugging Face commits of the changed and new files (and of the allowed deletes).
No output holds the at sign: each log and report line is masked before it is written.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import os
import shutil
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tom_tools as T  # noqa: E402  (the tools of the first pass, staged with their sha256)

mask, jline, utc, sha256, read_sums, project_of = T.mask, T.jline, T.utc, T.sha256, T.read_sums, T.project_of
SUFFIX = T.SUFFIX
FILL_COLUMNS = ("language", "license")
NEW_KEYS = ["project_languages rows", "project_languages projects", "project_labels rows", "project_labels projects",
            "language fills", "license fills", "value files", "new projects", "changed files", "empty language files"]
KNOWN_KEYS = list(T.KNOWN_KEYS) + NEW_KEYS
LINGUIST = {"TSX": "TypeScript", "JSX": "JavaScript", "GNU Style Assembly": "Assembly", "FORTRAN Modern": "Fortran"}


def say(text: str) -> None:
    print(mask(text), flush=True)


def conf_list(text: str) -> list[str]:
    return [x for x in (text or "").split() if x]


def read_tsv(path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def read_resolved(path) -> list[tuple[str, str, str]]:
    out = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            p, f, o = line.split("\t")
            out.append((p, f, o))
    return out


def read_plan(path) -> list[dict]:
    out = []
    for r in read_tsv(path):
        r["values"] = json.loads(r["values"])
        out.append(r)
    return out


def write_pq(table, out) -> None:
    """The settings of project_facts.parquet (kit 1): zstd 19, dictionary, statistics; read back equal."""
    import pyarrow.parquet as pq
    tmp = str(out) + ".tmp"
    pq.write_table(table, tmp, compression="zstd", compression_level=19, use_dictionary=True, write_statistics=True)
    back = pq.read_table(tmp)
    if not back.equals(table):
        raise SystemExit(f"PROBLEM: {out}: the read back is not the table")
    os.replace(tmp, out)


def plain_names(path) -> list[str]:
    """One project name per line (a tab ends the name; # and empty lines are skipped)."""
    out = []
    for raw in Path(path).read_text().splitlines():
        name = raw.split("\t")[0].strip()
        if name and not name.startswith("#"):
            out.append(name)
    return out


# ------------------------------------------------------------------------------------------------- prepare --
def linguist_largest(code_prog: dict) -> str | None:
    sums: dict[str, int] = {}
    for k, v in code_prog.items():
        name = LINGUIST.get(k, k)
        sums[name] = sums.get(name, 0) + int(v)
    if not sums:
        return None
    best = max(sums.values())
    top = sorted(k for k, v in sums.items() if v == best)
    return top[0] if len(top) == 1 else None


def cmd_prepare(a) -> int:
    import duckdb
    probs = []
    src = read_sums(a.src_sums)
    src_projects = {project_of(Path(r).name) for r in src if r.startswith("parquet/") and r.endswith(SUFFIX)}
    keep1 = plain_names(a.keep)
    add = conf_list(a.add)
    if len(set(keep1)) != len(keep1):
        probs.append("the keep list repeats a name")
    for p in keep1 + add:
        if p not in src_projects:
            probs.append(f"{p} is not a project of the source root")
    for p in add:
        if p in keep1:
            probs.append(f"{p} (ADD_PROJECTS) is in the keep list already")
    keep2 = sorted(set(keep1) | set(add))
    manifest = {r["project"]: r for r in read_tsv(a.src_manifest)}
    con = duckdb.connect()
    con.execute("CREATE TABLE k(project VARCHAR)")
    con.executemany("INSERT INTO k VALUES (?)", [(p,) for p in keep2])
    # project_languages: the kept rows; the ADD_PROJECTS rows from the tokei retry (the same columns as p4_languages.sql)
    con.execute("CREATE TABLE lang AS SELECT * FROM read_parquet(?)", [a.languages])
    n, nd = con.execute("SELECT count(*), count(DISTINCT project) FROM lang").fetchone()
    if n != nd:
        probs.append(f"{a.languages}: {n} rows, {nd} projects")
    miss = con.execute("SELECT count(*) FROM k ANTI JOIN lang USING (project)").fetchone()[0]
    if miss:
        probs.append(f"{a.languages} lacks {miss} kept projects")
    con.execute("""CREATE TABLE r AS SELECT * FROM read_json(?, format='newline_delimited', columns={
        project:'VARCHAR', status:'VARCHAR', final:'BOOLEAN', code_prog:'JSON', code_prog_total:'BIGINT',
        largest:'VARCHAR', largest_tied:'VARCHAR[]', target_share:'DOUBLE', pinned_commit:'VARCHAR'})""", [a.retry])
    retry = {}
    for p, st, fin, cp, total, largest, tied, share, commit in con.execute("SELECT * FROM r").fetchall():
        if p in add:
            retry.setdefault(p, []).append((st, fin, json.loads(cp) if cp else {}, largest, commit))
    fixed, fixed_json = {}, {}
    for p in add:
        recs = [x for x in retry.get(p, []) if x[0] == "ok" and x[1]]
        if len(recs) != 1:
            probs.append(f"{p}: {len(recs)} final ok lines in {a.retry}, not 1")
            continue
        st, fin, cp, largest, commit = recs[0]
        if commit != manifest.get(p, {}).get("run_commit"):
            probs.append(f"{p}: the retry commit is not the MANIFEST run_commit")
        lg = linguist_largest(cp)
        if not lg:
            probs.append(f"{p}: no largest language")
        fixed[p] = lg
        fixed_json[p] = json.dumps(dict(sorted(cp.items(), key=lambda kv: (-kv[1], kv[0]))), separators=(",", ":"),
                                   ensure_ascii=False)
        old = con.execute("SELECT language, tokei_status FROM lang WHERE project = ?", [p]).fetchone()
        if old is None or old[0] is not None:
            probs.append(f"{p}: the project_languages row has a host language ({old})")
    if probs:
        for x in probs:
            say("PROBLEM: " + x)
        return 1
    con.execute("CREATE TABLE fx(project VARCHAR, linguist VARCHAR, cj VARCHAR)")
    con.executemany("INSERT INTO fx VALUES (?, ?, ?)", [(p, lg, fixed_json[p]) for p, lg in fixed.items()])
    cols = ("project, language, language_tokei, language_tokei_linguist, largest_tied, target_share, "
            "code_lines_programming, code_lines_json, tokei_status")
    tbl = con.execute(f"""
        SELECT {cols} FROM lang SEMI JOIN k USING (project) WHERE project NOT IN (SELECT project FROM fx)
        UNION ALL
        SELECT r.project, NULL::VARCHAR, r.largest, fx.linguist, coalesce(r.largest_tied, []::VARCHAR[]), r.target_share,
               r.code_prog_total, fx.cj, 'ok'
        FROM r JOIN fx USING (project) WHERE r.status = 'ok' AND r.final
        ORDER BY project""").arrow()
    if hasattr(tbl, "read_all"):
        tbl = tbl.read_all()
    want_schema = con.execute(f"SELECT {cols} FROM lang LIMIT 0").arrow()
    if hasattr(want_schema, "read_all"):
        want_schema = want_schema.read_all()
    tbl = tbl.cast(want_schema.schema)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if tbl.num_rows != len(keep2) or tbl.column("project").to_pylist() != keep2:
        say(f"PROBLEM: project_languages has {tbl.num_rows} rows, not the {len(keep2)} kept projects in order")
        return 1
    write_pq(tbl, out / "project_languages.parquet")
    langs = {r["project"]: r for r in tbl.to_pylist()}
    # project_labels: the kept rows, the columns of LABEL_COLUMNS
    lab_cols = conf_list(a.label_columns)
    have = [c for c, in con.execute("SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet(?))", [a.labels]).fetchall()]
    bad = [c for c in lab_cols if c not in have]
    if bad or lab_cols[0] != "project":
        say(f"PROBLEM: label columns {bad} are not in {a.labels} (or project is not first)")
        return 1
    sel = ", ".join(f'"{c}"' for c in lab_cols)
    lab = con.execute(f"SELECT {sel} FROM read_parquet(?) SEMI JOIN k USING (project) ORDER BY project", [a.labels]).arrow()
    if hasattr(lab, "read_all"):
        lab = lab.read_all()
    if lab.num_rows != len(keep2) or lab.column("project").to_pylist() != keep2:
        say(f"PROBLEM: project_labels has {lab.num_rows} rows, not the {len(keep2)} kept projects")
        return 1
    write_pq(lab, out / "project_labels.parquet")
    # fills.tsv
    kset = set(keep2)
    fills = []
    for r in read_tsv(a.lang_gaps):
        p = r["project"]
        if p not in kset:
            continue
        old = "" if r["old_value"] in ("", '""') else r["old_value"]
        if old != "" or r["proposed_value"] in ("", '""'):
            probs.append(f"{p}: language gap row old {r['old_value']!r} proposed {r['proposed_value']!r}")
            continue
        if r["proposed_value"] != langs[p]["language_tokei_linguist"]:
            probs.append(f"{p}: the proposed language is not language_tokei_linguist")
        fills.append((p, "language", "", r["proposed_value"], "tokei language_tokei_linguist"))
    for p, lg in fixed.items():
        fills.append((p, "language", "", lg, "tokei language_tokei_linguist (savannah https retry)"))
    empty = sorted(p for p, r in langs.items() if r["language"] is None)
    filled = sorted(p for p, c, *_ in fills if c == "language")
    if empty != filled:
        probs.append(f"the empty languages ({len(empty)}) are not the language fills ({len(filled)}): "
                     f"{sorted(set(empty) ^ set(filled))[:5]}")
    classes = set(conf_list(a.license_classes))
    for r in read_tsv(a.lic_fill):
        p = r["project"]
        if p not in kset or r["proposed_value"] in ("", '""'):
            continue
        if r["class"] not in classes:
            probs.append(f"{p}: license class {r['class']} has a value")
        if r["old_value"] != "NOASSERTION" or r["host"] == "github.com":
            probs.append(f"{p}: license row old {r['old_value']!r} host {r['host']}")
        v = r["proposed_value"]
        if any(ch in v for ch in "\t\n\\") or AT_SIGN in v:
            probs.append(f"{p}: the license value has a tab, newline, backslash or at sign")
        fills.append((p, "license", "NOASSERTION", v, f"licensee 98 ({r['class']})"))
    if len({(p, c) for p, c, *_ in fills}) != len(fills):
        probs.append("a project and column have two fills")
    if probs:
        for x in probs[:30]:
            say("PROBLEM: " + x)
        return 1
    fills.sort()
    with open(out / "fills.tsv", "w") as f:
        f.write("project\tcolumn\told\tnew\tbasis\n")
        for row in fills:
            f.write("\t".join(row) + "\n")
    by_p: dict[str, set] = {}
    for p, c, *_ in fills:
        by_p.setdefault(p, set()).add(c)
    rep = {"keep": len(keep1), "add": add, "keep2": len(keep2), "fills": len(fills),
           "language_fills": sum(c == "language" for _, c, *_ in fills),
           "license_fills": sum(c == "license" for _, c, *_ in fills),
           "files_with_fills": len(by_p), "files_both": sum(len(v) == 2 for v in by_p.values()),
           "language_values": sorted({n for _, c, _, n, _ in fills if c == "language"}),
           "add_languages": fixed, "project_languages_rows": tbl.num_rows, "project_labels_rows": lab.num_rows,
           "label_columns": lab_cols}
    (out / "prepare.json").write_text(json.dumps(rep, indent=1, sort_keys=True))
    say(f"prepare: keep {len(keep2)} projects ({len(keep1)} + {len(add)}); fills {len(fills)} "
        f"(language {rep['language_fills']}, license {rep['license_fills']}) in {len(by_p)} files "
        f"({rep['files_both']} with both); project_languages {tbl.num_rows} rows; project_labels {lab.num_rows} rows")
    return 0


AT_SIGN = chr(64)


# ---------------------------------------------------------------------------------------------------- keep --
def cmd_keep(a) -> int:
    tom1 = read_sums(a.tom1_sums)
    src = read_sums(a.src_sums)
    t1 = {project_of(Path(r).name): Path(r).name for r in tom1 if r.startswith("parquet/") and r.endswith(SUFFIX)}
    s1 = {project_of(Path(r).name): Path(r).name for r in src if r.startswith("parquet/") and r.endswith(SUFFIX)}
    keep1 = plain_names(a.list)
    add = conf_list(a.add)
    probs = []
    if sorted(keep1) != sorted(t1):
        probs.append(f"the TOM-1 root has {len(t1)} project files, the keep list {len(keep1)} names; "
                     f"differ: {sorted(set(keep1) ^ set(t1))[:5]}")
    for p in add:
        if p in t1 or p not in s1:
            probs.append(f"{p}: in TOM-1 {p in t1}, in the source {p in s1}")
    rows = sorted([(p, t1[p], "tom1") for p in keep1 if p in t1] + [(p, s1[p], "src") for p in add if p in s1])
    if len(rows) > a.max:
        probs.append(f"{len(rows)} files is more than {a.max}")
    for x in probs:
        say("PROBLEM: " + x)
    if probs:
        return 1
    with open(a.out, "w") as f:
        for r in rows:
            f.write("\t".join(r) + "\n")
    say(f"keep: {len(rows)} files ({sum(o == 'tom1' for *_, o in rows)} of TOM-1, {sum(o == 'src' for *_, o in rows)} "
        f"from the source)")
    return 0


# ------------------------------------------------------------------------------------------------- footers --
def footer_record(name: str, size: int, tail: bytes) -> dict:
    import pyarrow as pa
    import pyarrow.parquet as pq
    if len(tail) < 12 or tail[-4:] != b"PAR1":
        raise ValueError("the tail does not end with PAR1")
    n = struct.unpack("<I", tail[-8:-4])[0]
    if n + 8 > len(tail):
        raise ValueError(f"short tail: footer {n} B")
    md = pq.read_metadata(pa.BufferReader(tail))
    kv = {k.decode(): v.decode() for k, v in (md.metadata or {}).items()}
    sch = md.schema.to_arrow_schema()
    stats = {}
    for c in FILL_COLUMNS:
        if c not in md.schema.names:
            continue
        i = md.schema.names.index(c)
        rgs = []
        for g in range(md.num_row_groups):
            s = md.row_group(g).column(i).statistics
            rgs.append([s.min, s.max, s.null_count, s.has_min_max] if s is not None else [None, None, None, False])
        stats[c] = rgs
    return {"file": name, "size": size, "footer_len": n, "rows": md.num_rows, "row_groups": md.num_row_groups,
            "columns": md.num_columns, "schema": [[f.name, str(f.type)] for f in sch], "kv": kv,
            "created_by": md.created_by, "stats": stats, "tail_sha256": hashlib.sha256(tail[-(n + 8):]).hexdigest()}


def fetch_tail_s3(client, bucket: str, key: str, first: int) -> tuple[bytes, int]:
    r = client.get_object(Bucket=bucket, Key=key, Range=f"bytes=-{first}")
    body = r["Body"].read()
    total = int(r["ContentRange"].rsplit("/", 1)[1])
    n = struct.unpack("<I", body[-8:-4])[0] if len(body) >= 8 else 0
    if n + 8 > len(body) and len(body) < total:
        r = client.get_object(Bucket=bucket, Key=key, Range=f"bytes=-{n + 8}")
        body = r["Body"].read()
    return body, total


def fetch_tail_local(path: str, first: int) -> tuple[bytes, int]:
    total = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, total - first))
        body = f.read()
        n = struct.unpack("<I", body[-8:-4])[0]
        if n + 8 > len(body) and len(body) < total:
            f.seek(total - n - 8)
            body = f.read()
    return body, total


def cmd_footers(a) -> int:
    rows = [(p, f) for p, f, o in read_resolved(a.keep) if o == "tom1"]
    man = {r["path"]: r for r in read_tsv(a.manifest)}
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    client = bucket = None
    if a.s3:
        import boto3
        from botocore.config import Config
        bucket, prefix = a.s3.split("/", 1)
        client = boto3.client("s3", config=Config(retries={"max_attempts": 10, "mode": "adaptive"},
                                                  max_pool_connections=a.jobs + 4))

    def one(item):
        p, f = item
        tf = out / (f + ".tail")
        if a.s3:
            body, total = fetch_tail_s3(client, bucket, f"{prefix}/parquet/{f}", a.first)
        else:
            body, total = fetch_tail_local(os.path.join(a.local, "parquet", f), a.first)
        rec = footer_record(f, total, body)
        n = rec["footer_len"]
        tf.write_bytes(body[-(n + 8):])
        return rec

    probs, recs = [], []
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(one, it): it for it in rows}
        for fu in cf.as_completed(futs):
            p, f = futs[fu]
            try:
                rec = fu.result()
            except Exception as e:  # noqa: BLE001
                probs.append(f"{f}: {type(e).__name__}: {str(e)[:200]}")
                continue
            m = man.get(f"parquet/{f}")
            if m is None or int(m["bytes"]) != rec["size"] or int(m["rows"]) != rec["rows"]:
                probs.append(f"{f}: size {rec['size']} rows {rec['rows']} are not the TOM-1 MANIFEST.tsv row")
            recs.append(rec)
    recs.sort(key=lambda r: r["file"])
    with open(out / "footers.jsonl", "w") as fo:
        for r in recs:
            fo.write(jline(r) + "\n")
    for x in probs[:30]:
        say("PROBLEM: " + x)
    say(f"footers: {len(recs)} of {len(rows)} files, {sum(r['footer_len'] for r in recs):,} footer bytes, "
        f"{sum(r['rows'] for r in recs):,} rows, {sum(r['size'] for r in recs):,} B; problems {len(probs)}")
    return 1 if probs or len(recs) != len(rows) else 0


def read_footers(path) -> dict[str, dict]:
    return {r["file"]: r for r in (json.loads(x) for x in Path(path).read_text().splitlines() if x.strip())}


def stats_hold(rgs: list, value) -> bool:
    """Every row group of the column has statistics with min = max = value and no null."""
    return bool(rgs) and all(s[3] and s[0] == value and s[1] == value and s[2] == 0 for s in rgs)


def stats_empty(rgs: list) -> bool:
    """A row group of the column can hold an empty string or a null."""
    return any((not s[3]) or s[0] == "" or (s[2] or 0) > 0 for s in rgs)


# ---------------------------------------------------------------------------------------------------- plan --
def cmd_plan(a) -> int:
    rows = read_resolved(a.keep)
    feet = read_footers(a.footers)
    fills: dict[str, dict] = {}
    for r in read_tsv(a.fills):
        fills.setdefault(r["project"], {})[r["column"]] = [r["old"], r["new"]]
    probs, plan = [], []
    projects = {p for p, _, _ in rows}
    for p in sorted(set(fills) - projects):
        probs.append(f"{p}: a fill for a project that is not kept")
    for p, f, o in rows:
        vals = fills.get(p, {})
        if o == "tom1":
            fr = feet.get(f)
            if fr is None:
                probs.append(f"{f}: no footer")
                continue
            for c, (old, new) in vals.items():
                if not stats_hold(fr["stats"].get(c, []), old):
                    probs.append(f"{f}: the footer statistics of {c} do not hold {old!r} in every row group")
            if "language" not in vals and stats_empty(fr["stats"].get("language", [])):
                probs.append(f"{f}: an empty or null language cell has no fill")
            kind = "value" if vals else "unchanged"
        else:
            kind = "new"
        plan.append({"project": p, "file": f, "origin": o, "kind": kind, "values": json.dumps(vals, sort_keys=True)})
    counts = {}
    for r in plan:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    nl = sum("language" in json.loads(r["values"]) for r in plan)
    nc = sum("license" in json.loads(r["values"]) for r in plan)
    for what, have, want in (("files", len(plan), a.expect_files), ("value files", counts.get("value", 0), a.expect_value),
                             ("new files", counts.get("new", 0), a.expect_new), ("language fills", nl, a.expect_language),
                             ("license fills", nc, a.expect_license)):
        if want is not None and have != want:
            probs.append(f"{what}: {have}, expected {want}")
    for x in probs[:30]:
        say("PROBLEM: " + x)
    if probs:
        return 1
    with open(a.out, "w") as f:
        f.write("project\tfile\torigin\tkind\tvalues\n")
        for r in plan:
            f.write("\t".join(r[k] for k in ("project", "file", "origin", "kind", "values")) + "\n")
    # the canary: the smallest file of each kind of change
    groups: dict[str, list] = {}
    for r in plan:
        if r["kind"] == "unchanged":
            continue
        cols = "+".join(sorted(json.loads(r["values"])))
        g = f"{r['kind']}:{cols or 'none'}"
        size = feet[r["file"]]["size"] if r["origin"] == "tom1" else os.path.getsize(os.path.join(a.src_dir, r["file"]))
        groups.setdefault(g, []).append((size, r["project"]))
    canary = {g: min(v)[1] for g, v in sorted(groups.items())}
    Path(a.canary_out).write_text("".join(f"{p}\n" for p in canary.values()))
    say(f"plan: {len(plan)} files {counts}; language fills {nl}, license fills {nc}; canary {canary}")
    return 0


# ---------------------------------------------------------------------------------------------------- pass --
def pass_one(job: dict) -> dict:
    cfg, r = job["cfg"], job["row"]
    src, dst = job["src"], job["dst"]
    name = r["file"]
    rec = {"v": 2, "file": name, "project": r["project"], "kind": r["kind"], "origin": r["origin"],
           "values": r["values"], "start_utc": utc(), "status": "ERROR", "problems": []}
    t0 = time.time()
    peak = 0
    try:
        rec["in_bytes"] = os.path.getsize(src)
        rec["in_sha256"] = sha256(src)
        rec["want_in_sha256"] = job["want"]
        if rec["in_sha256"] != job["want"]:
            rec["problems"].append("the input sha256 is not its SHA256SUMS row")
            return rec
        maps = []
        if r["kind"] == "new":
            ta = time.time()
            aprob, avals = T.audit(src, r["project"], cfg, cfg["threads"])
            rec["audit"] = avals
            rec["audit_s"] = round(time.time() - ta, 2)
            if aprob:
                rec["problems"] += aprob
                return rec
            maps = [x for c in cfg["drop_columns"] for x in ("--drop", c)] + \
                   [x for m in cfg["rename"] for x in ("--rename", m)] + \
                   [x for kv in cfg["set_kv"] for x in ("--set-kv", kv)]
        work = Path(job["work"]) / r["project"]
        if work.exists():
            shutil.rmtree(work)
        (work / "out").mkdir(parents=True)
        tsv = work / "values.tsv"
        with open(tsv, "w") as f:
            for c, (old, new) in sorted(r["values"].items()):
                f.write(f"{src}\t{c}\t{old}\t{new}\n")
        vargs = ["--values", str(tsv), "--out-dir", str(work / "out")]
        env = dict(os.environ, OMP_NUM_THREADS=str(cfg["threads"]), PYTHONDONTWRITEBYTECODE="1")
        rc, out, err, dt, rss0 = T.run_child([cfg["py"], "-I", "-B", cfg["rename_py"], *vargs, *maps,
                                              "--copy", cfg["copy_mode"]], env)
        peak = max(peak, rss0)
        rec["rename_s"], rec["rename_rc"] = round(dt, 2), rc
        try:
            rep = json.loads(out.strip().splitlines()[-1])
            rec["rename"] = {k: rep.get(k) for k in ("ok", "dropped", "renamed", "kv_set", "replaced",
                                                    "regions_reencoded", "in_size", "out_size", "copy", "error")}
        except Exception:  # noqa: BLE001
            rec["rename"] = None
        part = work / "out" / os.path.basename(src)
        if rc != 0 or not part.exists():
            rec["problems"].append(f"parquet_rename.py rc {rc}: {(err or out).strip()[-400:]}")
            return rec
        rc, out, err, dt, rss1 = T.run_child([cfg["py"], "-I", "-B", cfg["check_py"], *vargs, *maps], env)
        peak = max(peak, rss1)
        rec["check_s"], rec["check_rc"] = round(dt, 2), rc
        try:
            rep = json.loads(out.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            rep = {"ok": False, "problems": ["no JSON line"]}
        if job.get("check_dir"):
            Path(job["check_dir"], f"{r['project']}.json").write_text(mask(out))
        rec["check"] = {k: rep.get(k) for k in ("ok", "problems", "kv_set", "replaced", "values_checked",
                                               "column_chunks_identical", "page_index_pages", "row_groups", "rows")}
        if rc != 0 or rep.get("ok") is not True:
            rec["problems"].append(f"parquet_rename_check.py rc {rc}, ok {rep.get('ok')}: "
                                   f"{str(rep.get('problems') or err.strip()[-300:])[:400]}")
            return rec
        rec["out_bytes"] = os.path.getsize(part)
        rec["out_sha256"] = sha256(part)
        rec["rows"] = rep.get("rows")
        os.replace(part, dst)
        shutil.rmtree(work)
        rec["peak_rss_bytes"] = peak
        rec["status"] = "OK"
    except Exception as e:  # noqa: BLE001
        rec["problems"].append(f"{type(e).__name__}: {str(e)[:400]}")
    finally:
        rec["total_s"] = round(time.time() - t0, 2)
        rec["end_utc"] = utc()
    return rec


def cmd_pass(a) -> int:
    cfg = dict(drop_columns=conf_list(a.drop_columns), rename=conf_list(a.rename), set_kv=conf_list(a.set_kv),
               expect_empty=conf_list(a.expect_empty), expect_manifest_category=a.expect_manifest_category,
               expect_file_mask=a.expect_file_mask, py=sys.executable, rename_py=a.rename_py, check_py=a.check_py,
               copy_mode=a.copy_mode, threads=a.threads)
    tom1, src = read_sums(a.tom1_sums), read_sums(a.src_sums)
    plan = [r for r in read_plan(a.plan) if r["kind"] != "unchanged"]
    if a.only_list:
        only = set(plain_names(a.only_list))
        plan = [r for r in plan if r["project"] in only]
        if len(plan) != len(only):
            say(f"ABORT: the canary list has {len(only)} names, {len(plan)} are changed files")
            return 2
    os.makedirs(a.dst, exist_ok=True)
    if a.check_dir:
        os.makedirs(a.check_dir, exist_ok=True)
    done = T.read_ledger(a.ledger)
    todo, skipped = [], 0
    for r in plan:
        f = r["file"]
        d = os.path.join(a.dst, f)
        old = done.get(f)
        if old and old.get("status") == "OK" and os.path.exists(d) and os.path.getsize(d) == old.get("out_bytes"):
            skipped += 1
            continue
        s = os.path.join(a.tom1_dir if r["origin"] == "tom1" else a.src_dir, f)
        if not os.path.exists(s):
            say(f"ABORT: no input {s}")
            return 2
        want = (tom1 if r["origin"] == "tom1" else src).get(f"parquet/{f}")
        todo.append({"src": s, "dst": d, "want": want, "cfg": cfg, "row": r, "work": a.work, "check_dir": a.check_dir})
    todo.sort(key=lambda j: -os.path.getsize(j["src"]))
    todo_bytes = sum(os.path.getsize(j["src"]) for j in todo)
    say(f"pass: {len(todo)} files to do ({todo_bytes} B), {skipped} done before; jobs {a.jobs}, threads {a.threads}")
    t0 = time.time()
    counts, done_bytes, failures, running, stopped, last = {}, 0, [], {}, False, 0.0

    def progress(final=False):
        nonlocal last
        if not a.progress or (not final and time.time() - last < 30):
            return
        last = time.time()
        p = {"utc": utc(), "todo": len(todo), "finished": sum(counts.values()), "counts": counts, "skipped": skipped,
             "todo_in_bytes": todo_bytes, "done_in_bytes": done_bytes, "elapsed_s": round(time.time() - t0, 1),
             "final": final, "stopped": stopped,
             "running": [{"file": j["row"]["file"], "in_bytes": os.path.getsize(j["src"]),
                          "elapsed_s": round(time.time() - st, 1)} for j, st in running.values()]}
        tmp = a.progress + ".tmp"
        Path(tmp).write_text(mask(json.dumps(p)))
        os.replace(tmp, a.progress)

    with open(a.ledger, "a") as led, cf.ProcessPoolExecutor(max_workers=a.jobs) as ex:
        queue = list(todo)
        futs = {}
        while queue or futs:
            if a.stop_file and os.path.exists(a.stop_file) and queue:
                stopped = True
                queue.clear()
            while queue and len(futs) < a.jobs:
                j = queue.pop(0)
                fu = ex.submit(pass_one, j)
                futs[fu] = j
                running[id(fu)] = (j, time.time())
            if not futs:
                break
            fin, _ = cf.wait(list(futs), timeout=30, return_when=cf.FIRST_COMPLETED)
            for fu in fin:
                j = futs.pop(fu)
                running.pop(id(fu), None)
                try:
                    rec = fu.result()
                except Exception as e:  # noqa: BLE001
                    rec = {"v": 2, "file": j["row"]["file"], "status": "ERROR", "problems": [f"worker: {e}"],
                           "end_utc": utc()}
                led.write(jline(rec) + "\n")
                led.flush()
                os.fsync(led.fileno())
                counts[rec["status"]] = counts.get(rec["status"], 0) + 1
                done_bytes += os.path.getsize(j["src"])
                if rec["status"] != "OK":
                    failures.append(rec["file"])
                    say(f"FAIL {rec['file']}: {rec['problems']}")
            progress()
    progress(final=True)
    say(f"pass summary: {sum(counts.values())} files {counts}, {skipped} skipped, failures {len(failures)}"
        f"{' (stopped)' if stopped else ''}; wall {time.time() - t0:.0f} s")
    if failures:
        return 1
    return 3 if stopped else 0


# --------------------------------------------------------------------------------------------------- facts --
def cmd_facts(a) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq
    t1 = pq.read_table(a.tom1_facts)
    led = T.read_ledger(a.ledger)
    new = [r for r in read_plan(a.plan) if r["kind"] == "new"]
    have = t1.column("project").to_pylist()
    if have != sorted(have):
        say("PROBLEM: the TOM-1 project_facts rows are not in project order")
        return 1
    rows = t1.to_pylist()
    added = 0
    for r in new:
        rec = led.get(r["file"])
        if not rec or rec.get("status") != "OK":
            say(f"PROBLEM: {r['file']} has no OK ledger line")
            return 1
        if r["project"] in set(have):
            say(f"PROBLEM: {r['project']} is in the TOM-1 project_facts already")
            return 1
        text = rec["audit"]["fact"]
        items = T.split_fact(text)
        if T.join_fact(items) != text:
            say(f"PROBLEM: {r['project']}: the fact text does not split and join back")
            return 1
        for t, v in items:
            rows.append({"project": r["project"], "fact_type": t, "fact_value": v})
            added += 1
    rows.sort(key=lambda x: x["project"])  # stable: the order inside a project stays
    tbl = pa.Table.from_pylist(rows, schema=t1.schema)
    write_pq(tbl, Path(a.out))
    say(f"project_facts: {tbl.num_rows} rows ({t1.num_rows} of TOM-1, {added} new), "
        f"{len(set(tbl.column('project').to_pylist()))} projects")
    return 0


# ------------------------------------------------------------------------------------------------- ledgers --
def cmd_ledgers_check(a) -> int:
    """The new ledgers.parquet (kit 1 ledgers on the 8,449) is the TOM-1 one plus the rows of the new projects."""
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    new, t1 = pq.read_table(a.new), pq.read_table(a.tom1)
    add = conf_list(a.add)
    is_add = pc.is_in(new.column("project"), value_set=__import__("pyarrow").array(add))
    rest = new.filter(pc.invert(is_add))
    n_add = new.num_rows - rest.num_rows
    have = set(new.filter(is_add).column("project").to_pylist())
    if not rest.equals(t1) or have != set(add):
        say(f"PROBLEM: ledgers.parquet is not the TOM-1 rows plus the new projects (rows {new.num_rows}, TOM-1 "
            f"{t1.num_rows}, new {n_add}, projects {sorted(have)})")
        return 1
    say(f"ledgers.parquet: the {t1.num_rows} TOM-1 rows and {n_add} rows of {len(have)} new projects")
    return 0


# -------------------------------------------------------------------------------------------------- tables --
def cmd_tables(a) -> int:
    import duckdb
    root = Path(a.root).resolve()
    keep = sorted(p for p, _, _ in read_resolved(a.keep))
    probs = []
    added = {}
    for name in conf_list(a.tables):
        rel = f"organizations/{name}.parquet"
        dst = root / rel
        if dst.exists():
            probs.append(f"{rel} exists already")
            continue
        shutil.copyfile(Path(a.inputs) / f"{name}.parquet", dst)
        added[name] = rel
    if probs:
        for x in probs:
            say("PROBLEM: " + x)
        return 1
    cwd = os.getcwd()
    os.chdir(root)
    try:
        con = duckdb.connect()
        info = dict(con.execute("SELECT key, value FROM read_parquet('organizations/release_info.parquet')").fetchall())
        t1 = dict(con.execute("SELECT key, value FROM read_parquet(?)",
                              [str(Path(a.tom1_root).resolve() / "organizations/release_info.parquet")]).fetchall())
        moved = sorted(k for k in set(info) | set(t1) if info.get(k) != t1.get(k))
        want_moved = sorted(f"{t}_{x}" for t in ("project_organizations", "project_facts") for x in ("rows", "sha256"))
        if set(info) != set(t1) or not set(moved) <= set(want_moved):
            probs.append(f"release_info differs from TOM-1 in {moved}, not only in {want_moved}")
        for name, rel in added.items():
            n, nd = con.execute(f"SELECT count(*), count(DISTINCT project) FROM read_parquet('{rel}')").fetchone()
            ps = [p for p, in con.execute(f"SELECT DISTINCT project FROM read_parquet('{rel}') ORDER BY 1").fetchall()]
            if n != len(keep) or ps != keep:
                probs.append(f"{rel}: {n} rows, {nd} projects; not one row for each kept project")
            for k in (f"{name}_rows", f"{name}_sha256"):
                if k in info:
                    probs.append(f"release_info has {k} already")
            info[f"{name}_rows"] = str(n)
            info[f"{name}_sha256"] = sha256(rel)
        if probs:
            for x in probs:
                say("PROBLEM: " + x)
            return 1
        db = duckdb.connect(str(root / a.db_rel))
        views = {v for v, in db.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
        for name, rel in added.items():
            if name in views:
                say(f"PROBLEM: the view {name} exists already")
                return 1
            db.execute(f'CREATE VIEW {name} AS SELECT * FROM "{rel}"')
        db.execute("CHECKPOINT")
        n_views = len(views) + len(added)
        db.close()
        # ctp_schema_version: kit 1 kept the source value 2 (build_organisations.py CTP_SCHEMA_VERSION); the files are
        # schema 3. dataset_db_sha256 (new): the sha256 of the organizations/dataset.duckdb of this pass (the views
        # read release_info.parquet; the DB does not hold it, so the order is safe). organizations_db_sha256 and
        # links_json_sha256 stay: they are the sha256 of build inputs (companies DB, links-final/links.json) that the
        # release does not ship (build_organisations.py step_tables).
        fixed = {"ctp_schema_version": [info.get("ctp_schema_version"), a.schema_version],
                 "dataset_db_sha256": [info.get("dataset_db_sha256"), sha256(root / a.db_rel)]}
        for k, (_, v) in fixed.items():
            info[k] = v
        con.execute("CREATE TABLE ri(key VARCHAR, value VARCHAR)")
        con.executemany("INSERT INTO ri VALUES (?, ?)", sorted(info.items()))
        ri = "organizations/release_info.parquet"
        con.execute(f"COPY (SELECT * FROM ri ORDER BY key) TO '{ri}.tmp' (FORMAT parquet, COMPRESSION zstd)")
        os.replace(ri + ".tmp", ri)
        con.close()
        say("release_info: " + "; ".join(f"{k} {o} -> {v}" for k, (o, v) in fixed.items()))
    finally:
        os.chdir(cwd)
    say(f"tables: {', '.join(added.values())}; release_info {len(info)} keys; {a.db_rel}: {n_views} views")
    return 0


# ------------------------------------------------------------------------------------------------ manifest --
def tsv_lines(path) -> tuple[list[str], list[list[str]]]:
    text = Path(path).read_text()
    lines = text.split("\n")
    if lines[-1] != "":
        raise SystemExit(f"PROBLEM: {path} does not end with a newline")
    rows = [ln.split("\t") for ln in lines[:-1]]
    return rows[0], rows[1:]


def cmd_manifest(a) -> int:
    head, t1 = tsv_lines(a.tom1_manifest)
    mhead, mini = tsv_lines(a.mini_manifest)
    if "\n".join("\t".join(r) for r in [head] + t1) + "\n" != Path(a.tom1_manifest).read_text():
        say("PROBLEM: the TOM-1 MANIFEST.tsv does not serialize back")
        return 1
    if mhead != head:
        say(f"PROBLEM: the mini MANIFEST.tsv header is not the TOM-1 header: {mhead}")
        return 1
    ix = {c: i for i, c in enumerate(head)}
    plan = {r["file"]: r for r in read_plan(a.plan)}
    led = T.read_ledger(a.ledger)
    paths = [r[ix["path"]] for r in t1]
    if paths != sorted(paths):
        say("PROBLEM: the TOM-1 MANIFEST.tsv rows are not in path order")
        return 1
    by_path = {r[ix["path"]]: r for r in t1}
    mini_by = {r[ix["path"]]: r for r in mini}
    probs, out = [], []
    for f, r in sorted(plan.items(), key=lambda x: f"parquet/{x[0]}"):
        path = f"parquet/{f}"
        if r["kind"] == "unchanged":
            row = by_path.get(path)
            if row is None:
                probs.append(f"{path}: no TOM-1 row")
                continue
        else:
            row = mini_by.get(path)
            rec = led.get(f) or {}
            if row is None:
                probs.append(f"{path}: no mini row")
                continue
            if row[ix["sha256"]] != rec.get("out_sha256") or int(row[ix["bytes"]]) != rec.get("out_bytes"):
                probs.append(f"{path}: the mini row is not the ledger output")
            if r["kind"] == "value":
                old = by_path.get(path)
                same = [c for c in head if c not in ("bytes", "sha256")]
                if old is None or any(row[ix[c]] != old[ix[c]] for c in same):
                    probs.append(f"{path}: the new row differs from the TOM-1 row in more than bytes and sha256")
            if any(row[ix[c]] == "" for c in ("run_commit", "cregit_commit", "ctp_commit")):
                probs.append(f"{path}: an empty commit cell")
        out.append(row)
    extra = sorted(set(mini_by) - {f"parquet/{f}" for f, r in plan.items() if r["kind"] != "unchanged"})
    if extra:
        probs.append(f"the mini MANIFEST.tsv has rows of unchanged files: {extra[:3]}")
    for x in probs[:30]:
        say("PROBLEM: " + x)
    if probs:
        return 1
    Path(a.out).write_text("\n".join("\t".join(r) for r in [head] + out) + "\n")
    say(f"manifest: {len(out)} rows ({sum(r['kind'] == 'unchanged' for r in plan.values())} TOM-1 rows, "
        f"{sum(r['kind'] == 'value' for r in plan.values())} new bytes and sha256, "
        f"{sum(r['kind'] == 'new' for r in plan.values())} new rows)")
    return 0


# ---------------------------------------------------------------------------------------------------- sums --
def local_files(root: Path) -> list[str]:
    """The rule of fill_release.py release_files: no dot folder or file, no __pycache__, no top-level _staging, not the
    root SHA256SUMS."""
    out = []
    for dirpath, dirs, files in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"
                   and not (rel_dir == Path(".") and d == "_staging")]
        for f in files:
            rel = (rel_dir / f).as_posix()
            if f.startswith(".") or rel == "SHA256SUMS":
                continue
            out.append(rel)
    return sorted(out)


def cmd_sums(a) -> int:
    root = Path(a.root)
    t1text = Path(a.tom1_sums).read_text()
    t1 = read_sums(a.tom1_sums)
    if "".join(f"{d}  {r}\n" for r, d in t1.items()) != t1text or list(t1) != sorted(t1):
        say("PROBLEM: the TOM-1 SHA256SUMS does not serialize back in path order")
        return 1
    plan = read_plan(a.plan)
    unchanged = {f"parquet/{r['file']}" for r in plan if r["kind"] == "unchanged"}
    local = local_files(root)
    both = unchanged & set(local)
    if both:
        say(f"PROBLEM: unchanged files are in the local root: {sorted(both)[:3]}")
        return 1
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        digests = dict(zip(local, ex.map(lambda r: sha256(root / r), local)))
    for r in unchanged:
        if r not in t1:
            say(f"PROBLEM: {r} has no TOM-1 row")
            return 1
        digests[r] = t1[r]
    text = "".join(f"{digests[r]}  {r}\n" for r in sorted(digests))
    (root / "SHA256SUMS").write_text(text)
    changed = sorted(r for r in local if t1.get(r) != digests[r])
    gone = sorted(set(t1) - set(digests))
    Path(a.changed_out).write_text("".join(f"{r}\n" for r in changed))
    Path(a.gone_out).write_text("".join(f"{r}\n" for r in gone))
    say(f"sums: {len(digests)} rows ({len(unchanged)} TOM-1 rows, {len(local)} local files); changed or new "
        f"{len(changed)}, the same as TOM-1 {len(local) - len(changed)}, gone {len(gone)}")
    return 0


# ---------------------------------------------------------------------------------------------------- view --
def cmd_view(a) -> int:
    root, view, tails = Path(a.root), Path(a.out), Path(a.tails)
    if view.exists():
        shutil.rmtree(view)
    feet = read_footers(tails / "footers.jsonl")
    for rel in local_files(root) + ["SHA256SUMS"]:
        (view / rel).parent.mkdir(parents=True, exist_ok=True)
        os.link(root / rel, view / rel)
    n = 0
    for r in read_plan(a.plan):
        if r["kind"] != "unchanged":
            continue
        f = r["file"]
        fr = feet[f]
        tail = (tails / (f + ".tail")).read_bytes()
        if hashlib.sha256(tail).hexdigest() != fr["tail_sha256"]:
            say(f"PROBLEM: {f}: the tail is not the fetched one")
            return 1
        p = view / "parquet" / f
        with open(p, "wb") as o:
            o.truncate(fr["size"])
            o.write(b"PAR1")
            o.seek(fr["size"] - len(tail))
            o.write(tail)
        n += 1
    say(f"view: {len(local_files(view)) + 1} files ({n} sparse files with the TOM-1 footers)")
    return 0


# -------------------------------------------------------------------------------------------------- values --
def view_footers(view: Path, jobs: int) -> dict[str, dict]:
    files = sorted(os.listdir(view / "parquet"))

    def one(f):
        body, total = fetch_tail_local(str(view / "parquet" / f), 1 << 20)
        return footer_record(f, total, body)

    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        return {r["file"]: r for r in ex.map(one, files)}


def cmd_values(a) -> int:
    import duckdb
    root = Path(a.root).resolve()
    plan = read_plan(a.plan)
    feet = read_footers(a.footers)
    led = T.read_ledger(a.ledger)
    probs = []
    nbytes = rows = 0
    for r in plan:
        if r["kind"] == "unchanged":
            nbytes += feet[r["file"]]["size"]
            rows += feet[r["file"]]["rows"]
        else:
            rec = led.get(r["file"]) or {}
            if rec.get("status") != "OK":
                probs.append(f"{r['file']}: no OK ledger line")
                continue
            size = os.path.getsize(root / "parquet" / r["file"])
            if size != rec["out_bytes"]:
                probs.append(f"{r['file']}: the size is not the ledger out_bytes")
            nbytes += size
            rows += rec["rows"]
    n_local = len(local_files(root))
    n_unch = sum(r["kind"] == "unchanged" for r in plan)
    sizes = json.loads(Path(a.sizes).read_text())
    v = {"projects": f"{len(plan):,}", "parquet files": f"{len(plan):,}", "parquet bytes": f"{nbytes:,}",
         "parquet GB": f"{nbytes / 1e9:.1f}", "rows": f"{rows:,}", "date": a.date, "machine": a.machine,
         "root files": f"{n_local + n_unch + 1:,}"}
    for k in T.SIZE_KEYS:
        v[f"size {k}"] = f"{sizes['size_rule_counts'].get(k, 0):,}"
    for k in ("S", "M", "L"):
        v[f"size_class {k}"] = f"{sizes['size_class_counts'].get(k, 0):,}"
    vals = [r["values"] for r in plan]
    v["language fills"] = f"{sum('language' in x for x in vals):,}"
    v["license fills"] = f"{sum('license' in x for x in vals):,}"
    v["value files"] = f"{sum(r['kind'] == 'value' for r in plan):,}"
    v["new projects"] = f"{sum(r['kind'] == 'new' for r in plan):,}"
    v["changed files"] = f"{sum(r['kind'] != 'unchanged' for r in plan):,}"
    v["empty language files"] = "0"
    cwd = os.getcwd()
    os.chdir(root)
    try:
        con = duckdb.connect(str(root / a.db_rel), read_only=True)
        for t in T.TABLES + ["project_languages", "project_labels"]:
            n = con.execute(f"SELECT count(*) FROM read_parquet('organizations/{t}.parquet')").fetchone()[0]
            v["facts rows" if t == "project_facts" else f"{t} rows"] = f"{n:,}"
        v["facts projects"] = f"{con.execute('SELECT count(DISTINCT project) FROM project_facts').fetchone()[0]:,}"
        for view in ("project_hosts", "project_sponsors", "project_languages", "project_labels"):
            n, nd = con.execute(f"SELECT count(*), count(DISTINCT project) FROM {view}").fetchone()
            v[f"{view} rows"], v[f"{view} projects"] = f"{n:,}", f"{nd:,}"
        con.close()
    finally:
        os.chdir(cwd)
    missing = sorted(set(KNOWN_KEYS) - set(v))
    if missing:
        probs.append(f"no value for {missing}")
    for x in probs[:30]:
        say("PROBLEM: " + x)
    if probs:
        return 1
    Path(a.out).write_text(json.dumps(v, indent=1, sort_keys=True))
    say("values: " + "; ".join(f"{k} = {v[k]}" for k in KNOWN_KEYS))
    return 0


def cmd_keys(a) -> int:
    print("\n".join(KNOWN_KEYS))
    return 0


# ---------------------------------------------------------------------------------------------- check-root --
# release_info keys whose value cannot be measured in the root (hashes of inputs that the release does not ship):
# they must keep the source value. The other keys are measured (see release_info_problems).
RI_FROM_SOURCE = {"link_error_source_sha256", "p_error_sha256", "organizations_db_sha256", "links_json_sha256",
                  "domain_key", "fallback_no_real_domain", "fallback_real_domain_with_no_row"}


def release_info_problems(root: Path, info: dict, src_info: dict, kv: dict, con) -> tuple[list[str], dict]:
    """Every release_info key against the value measured in the root: <table>_rows and <table>_sha256 against
    organizations/<table>.parquet, dataset_db_sha256 against organizations/dataset.duckdb, mapping_sha256,
    ctp_schema_version and organizations_version against the footer key-values of the files; the keys of
    RI_FROM_SOURCE (build inputs that the release does not ship, and fixed rule texts) against the source
    release_info. An unknown key is a problem."""
    probs, seen = [], {}
    tables = sorted(p.stem for p in (root / "organizations").glob("*.parquet") if p.stem != "release_info")
    files = {"dataset_db": root / "organizations/dataset.duckdb"}
    for k, v in sorted(info.items()):
        base, _, kind = k.rpartition("_")
        if k == "ctp_schema_version":
            want = kv.get("ctp_schema_version")
        elif k == "organizations_version":
            want = kv.get("organizations_version")
        elif k == "mapping_sha256":
            want = kv.get("organizations_mapping_sha256")
        elif k in RI_FROM_SOURCE:
            want = src_info.get(k)
        elif kind == "rows" and base in tables:
            want = str(con.execute(f"SELECT count(*) FROM read_parquet('organizations/{base}.parquet')").fetchone()[0])
        elif kind == "sha256" and base in tables:
            want = sha256(root / f"organizations/{base}.parquet")
        elif kind == "sha256" and base in files:
            want = sha256(files[base])
        else:
            probs.append(f"release_info: the key {k} has no rule (measured or source)")
            continue
        seen[k] = v == want
        if v != want:
            probs.append(f"release_info: {k} is {v!r}, the measured value is {want!r}")
    for t in tables:
        for k in (f"{t}_rows", f"{t}_sha256"):
            if k not in info:
                probs.append(f"release_info: no key {k} for organizations/{t}.parquet")
    for k in ("ctp_schema_version", "dataset_db_sha256", "mapping_sha256", "organizations_version"):
        if k not in info:
            probs.append(f"release_info: no key {k}")
    return probs, {"keys": len(info), "checked": len(seen), "equal": sum(seen.values())}


def cmd_check_root(a) -> int:
    import duckdb
    root, view = Path(a.root).resolve(), Path(a.view).resolve()
    plan = read_plan(a.plan)
    byf = {r["file"]: r for r in plan}
    feet1 = read_footers(a.footers)
    led = T.read_ledger(a.ledger)
    t1sums, sums = read_sums(a.tom1_sums), read_sums(root / "SHA256SUMS")
    probs, rep = [], {}

    def bad(text):
        probs.append(text)

    # parquet/ of the view: exactly the kept files
    pq_files = sorted(os.listdir(view / "parquet"))
    rep["parquet_entries"] = len(pq_files)
    if pq_files != sorted(byf):
        bad(f"parquet/ of the view has {len(pq_files)} entries, the plan {len(byf)}")
    if len(pq_files) > a.max:
        bad(f"parquet/ has {len(pq_files)} entries, more than {a.max}")
    if a.expect_files and len(pq_files) != a.expect_files:
        bad(f"{len(pq_files)} project files, expected {a.expect_files}")
    # the footers of every file (the view: real files and the sparse TOM-1 footers)
    feet = view_footers(view, a.jobs)
    ref = next(iter(feet1.values()))
    schema, kv_ref = ref["schema"], dict(ref["kv"])
    rep["columns"] = len(schema)
    if a.want_columns and len(schema) != a.want_columns:
        bad(f"the TOM-1 schema has {len(schema)} columns, not {a.want_columns}")
    rows, empty_lang, lic_bad, fills_ok = 0, [], [], 0
    for f, fr in sorted(feet.items()):
        r = byf.get(f)
        if r is None:
            continue
        rows += fr["rows"]
        if fr["schema"] != schema:
            bad(f"{f}: the schema is not the TOM schema")
        kv_want = dict(feet1[f]["kv"]) if f in feet1 else kv_ref
        if fr["kv"] != kv_want:
            bad(f"{f}: the footer key-values are not the TOM-1 ones")
        if stats_empty(fr["stats"].get("language", [])):
            empty_lang.append(f)
        if r["kind"] == "unchanged":
            t = feet1.get(f)
            if t is None or fr["tail_sha256"] != t["tail_sha256"] or fr["size"] != t["size"]:
                bad(f"{f}: the view footer is not the TOM-1 footer")
        else:
            rec = led.get(f) or {}
            if rec.get("status") != "OK" or rec.get("rows") != fr["rows"] or rec.get("out_bytes") != fr["size"]:
                bad(f"{f}: the ledger line is not OK or not the file")
            for c, (old, new) in r["values"].items():
                if stats_hold(fr["stats"].get(c, []), new):
                    fills_ok += 1
                else:
                    bad(f"{f}: the footer statistics of {c} are not {new!r} in every row group")
            if r["kind"] == "value":
                t = feet1[f]
                if fr["rows"] != t["rows"] or fr["row_groups"] != t["row_groups"]:
                    bad(f"{f}: rows or row groups differ from TOM-1")
                for c in FILL_COLUMNS:
                    if c not in r["values"] and fr["stats"].get(c) != t["stats"].get(c):
                        lic_bad.append(f"{f}: {c} changed without a fill")
    probs.extend(lic_bad)
    rep["rows"], rep["fills_in_footers"], rep["empty_language_files"] = rows, fills_ok, len(empty_lang)
    if empty_lang:
        bad(f"{len(empty_lang)} files can hold an empty or null language: {empty_lang[:5]}")
    if a.expect_rows and rows != a.expect_rows:
        bad(f"rows {rows:,}, expected {a.expect_rows:,}")
    n_fills = sum(len(r["values"]) for r in plan)
    if fills_ok != n_fills:
        bad(f"{fills_ok} of {n_fills} fills are in the footers")
    # SHA256SUMS: every file of the view; TOM-1 rows for unchanged files; the ledger for the changed files
    vfiles = set(local_files(view))
    if set(sums) != vfiles:
        bad(f"SHA256SUMS paths != the files of the view: {sorted(set(sums) ^ vfiles)[:5]}")
    for f, r in byf.items():
        d = sums.get(f"parquet/{f}")
        if r["kind"] == "unchanged" and d != t1sums.get(f"parquet/{f}"):
            bad(f"{f}: the SHA256SUMS row is not the TOM-1 row")
        if r["kind"] != "unchanged" and d != (led.get(f) or {}).get("out_sha256"):
            bad(f"{f}: the SHA256SUMS row is not the ledger out_sha256")
    gone = sorted(set(t1sums) - set(sums))
    allowed = set(conf_list(a.allow_gone))
    rep["gone"] = gone
    if set(gone) - allowed:
        bad(f"TOM-1 files that the new root lacks (not in ALLOW_GONE): {sorted(set(gone) - allowed)[:10]}")
    # MANIFEST.tsv
    head, mrows = tsv_lines(root / "MANIFEST.tsv")
    h1, _ = tsv_lines(a.tom1_manifest)
    ix = {c: i for i, c in enumerate(head)}
    if head != h1:
        bad("the MANIFEST.tsv header is not the TOM-1 header")
    else:
        mp = {m[ix["path"]]: m for m in mrows}
        if len(mrows) != len(byf) or set(mp) != {f"parquet/{f}" for f in byf}:
            bad(f"MANIFEST.tsv has {len(mrows)} rows, not one per project file")
        for path, m in mp.items():
            f = path.split("/", 1)[1]
            if m[ix["sha256"]] != sums.get(path):
                bad(f"{path}: the MANIFEST sha256 is not the SHA256SUMS row")
            if f in feet and (int(m[ix["bytes"]]) != feet[f]["size"] or int(m[ix["rows"]]) != feet[f]["rows"]):
                bad(f"{path}: the MANIFEST bytes or rows are not the file")
            if m[ix["project"]] != project_of(f):
                bad(f"{path}: the MANIFEST project is not the file name")
    # the tables and the views (in the local root: real data)
    keep = sorted(r["project"] for r in plan)
    cwd = os.getcwd()
    os.chdir(root)
    try:
        con = duckdb.connect(str(root / a.db_rel), read_only=True)
        views = [v for v, in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal ORDER BY 1").fetchall()]
        rep["views"] = views
        for v in views:
            try:
                con.execute(f"SELECT * FROM {v} LIMIT 1").fetchall()
            except Exception as e:  # noqa: BLE001
                bad(f"the view {v} fails: {type(e).__name__}: {str(e)[:160]}")
        for need in conf_list(a.need_views):
            if need not in views:
                bad(f"no view {need}")
        local_rows = sum((led.get(r["file"]) or {}).get("rows") or 0 for r in plan if r["kind"] != "unchanged")
        n = con.execute("SELECT count(*) FROM tokens").fetchone()[0]
        rep["tokens_view_rows_local"] = n
        if n != local_rows:
            bad(f"tokens in the local root: {n:,} rows, the changed files {local_rows:,}")
        for t in ("project_languages", "project_labels", "project_organizations"):
            ps = [p for p, in con.execute(f"SELECT DISTINCT project FROM {t} ORDER BY 1").fetchall()]
            if ps != keep:
                bad(f"{t}: {len(ps)} projects, not the {len(keep)} kept projects")
        for t in ("project_languages", "project_labels"):
            n, nd = con.execute(f"SELECT count(*), count(DISTINCT project) FROM {t}").fetchone()
            if n != len(keep) or nd != len(keep):
                bad(f"{t}: {n} rows, not one row for each kept project")
        fp = {p for p, in con.execute("SELECT DISTINCT project FROM project_facts").fetchall()}
        if fp - set(keep):
            bad(f"project_facts has projects that are not kept: {sorted(fp - set(keep))[:3]}")
        lp = {p: lg for p, lg in con.execute("SELECT project, language_tokei_linguist FROM project_languages").fetchall()}
        for r in plan:
            new = r["values"].get("language", [None, None])[1]
            if new is not None and lp.get(r["project"]) != new:
                bad(f"{r['project']}: the language fill is not project_languages.language_tokei_linguist")
        info = dict(con.execute("SELECT key, value FROM release_info").fetchall())
        src_info = dict(con.execute("SELECT key, value FROM read_parquet(?)", [str(Path(a.src_release_info).resolve())]).fetchall())
        ri_probs, rep["release_info"] = release_info_problems(root, info, src_info, kv_ref, con)
        probs.extend(ri_probs)
        lg = {p for p, in con.execute("SELECT DISTINCT project FROM read_parquet('ledgers.parquet')").fetchall()}
        if lg != set(keep):
            bad(f"ledgers.parquet: {len(lg)} projects, not the {len(keep)} kept projects")
        con.close()
        con = duckdb.connect()
        n = con.execute(f"SELECT count(*) FROM read_parquet('{view}/parquet/*.parquet')").fetchone()[0]
        rep["tokens_rows_view"] = n
        if n != rows:
            bad(f"count(*) of the view parquet/ is {n:,}, the footers {rows:,}")
        con.close()
    finally:
        os.chdir(cwd)
    left = T.marks_left(root)
    if left:
        bad(f"marker words or placeholders left: {left[:10]}")
    rep["problems"] = len(probs)
    Path(a.out).write_text(mask(json.dumps({"report": rep, "problems": probs[:500]}, indent=1)))
    for x in probs[:30]:
        say("PROBLEM: " + x)
    say(f"check-root: {len(pq_files)} project files, {rows:,} rows, {len(schema)} columns, {fills_ok} fills in the "
        f"footers, empty language files {len(empty_lang)}, views {len(rep.get('views', []))}, gone {len(gone)}; "
        f"{len(probs)} problems")
    return 1 if probs else 0


# ------------------------------------------------------------------------------------------------- hf-push --
def hf_operations(root: Path, adds: list[str], deletes: list[str], last: tuple = ("README.md", "SHA256SUMS")):
    """Two commits: the data (adds and deletes, without the files of `last`), then the files of `last`."""
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete
    first = [CommitOperationAdd(path_in_repo=r, path_or_fileobj=str(root / r)) for r in adds if r not in last]
    first += [CommitOperationDelete(path_in_repo=r) for r in deletes]
    second = [CommitOperationAdd(path_in_repo=r, path_or_fileobj=str(root / r)) for r in adds if r in last]
    return [x for x in (first, second) if x]


def cmd_hf_push(a) -> int:
    from huggingface_hub import HfApi
    root = Path(a.root)
    adds = plain_names(a.adds)
    deletes = plain_names(a.deletes) if a.deletes else []
    sums = read_sums(root / "SHA256SUMS")
    for r in adds:
        if r != "SHA256SUMS" and sha256(root / r) != sums.get(r):
            say(f"ABORT: {r} is not its SHA256SUMS row")
            return 1
    if "SHA256SUMS" not in adds:
        adds.append("SHA256SUMS")
    api = HfApi()
    info = api.dataset_info(a.repo)
    if bool(info.private) != (a.expect == "private"):
        say(f"ABORT: {a.repo} is {'private' if info.private else 'public'}, expected {a.expect}")
        return 1
    commits = hf_operations(root, adds, deletes)
    for k, ops in enumerate(commits, 1):
        t = time.time()
        res = api.create_commit(repo_id=a.repo, repo_type="dataset", operations=ops,
                                commit_message=f"{a.message}: commit {k} of {len(commits)}")
        say(f"HF COMMIT {k}/{len(commits)}: {len(ops)} operations in {time.time() - t:.0f} s; "
            f"{getattr(res, 'oid', '')}")
    info = api.dataset_info(a.repo)
    if bool(info.private) != (a.expect == "private"):
        say(f"ABORT: {a.repo} visibility changed")
        return 1
    say(f"HF PUSH DONE: {len(adds)} files, {len(deletes)} deletes, {len(commits)} commits")
    return 0


# ---------------------------------------------------------------------------------------------------- main --
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("prepare")
    for x in ("--keep", "--src-sums", "--src-manifest", "--lang-gaps", "--lic-fill", "--languages", "--labels",
              "--retry", "--out-dir"):
        s.add_argument(x, required=True)
    s.add_argument("--add", default="")
    s.add_argument("--label-columns", required=True)
    s.add_argument("--license-classes", default="licensee-98 licensee-98-partial")
    s = sub.add_parser("keep")
    for x in ("--list", "--tom1-sums", "--src-sums", "--out"):
        s.add_argument(x, required=True)
    s.add_argument("--add", default="")
    s.add_argument("--max", type=int, default=9999)
    s = sub.add_parser("footers")
    for x in ("--keep", "--manifest", "--out-dir"):
        s.add_argument(x, required=True)
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--s3", help="BUCKET/PREFIX of the TOM-1 root")
    g.add_argument("--local", help="a local TOM-1 root")
    s.add_argument("--jobs", type=int, default=32)
    s.add_argument("--first", type=int, default=1 << 18)
    s = sub.add_parser("plan")
    for x in ("--keep", "--footers", "--fills", "--out", "--canary-out", "--src-dir"):
        s.add_argument(x, required=True)
    for x in ("--expect-files", "--expect-value", "--expect-new", "--expect-language", "--expect-license"):
        s.add_argument(x, type=int)
    s = sub.add_parser("pass")
    for x in ("--plan", "--tom1-dir", "--src-dir", "--dst", "--tom1-sums", "--src-sums", "--ledger", "--rename-py",
              "--check-py", "--work"):
        s.add_argument(x, required=True)
    for x in ("--drop-columns", "--rename", "--set-kv", "--expect-empty", "--expect-manifest-category",
              "--expect-file-mask"):
        s.add_argument(x, default="")
    s.add_argument("--copy-mode", default="read-write")
    s.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    s.add_argument("--threads", type=int, default=2)
    s.add_argument("--only-list")
    s.add_argument("--progress")
    s.add_argument("--stop-file")
    s.add_argument("--check-dir")
    s = sub.add_parser("facts")
    for x in ("--tom1-facts", "--ledger", "--plan", "--out"):
        s.add_argument(x, required=True)
    s = sub.add_parser("tables")
    for x in ("--root", "--tom1-root", "--keep", "--inputs", "--db-rel", "--tables", "--schema-version"):
        s.add_argument(x, required=True)
    s = sub.add_parser("ledgers-check")
    for x in ("--new", "--tom1", "--add"):
        s.add_argument(x, required=True)
    s = sub.add_parser("manifest")
    for x in ("--tom1-manifest", "--mini-manifest", "--plan", "--ledger", "--out"):
        s.add_argument(x, required=True)
    s = sub.add_parser("sums")
    for x in ("--root", "--tom1-sums", "--plan", "--changed-out", "--gone-out"):
        s.add_argument(x, required=True)
    s.add_argument("--jobs", type=int, default=8)
    s = sub.add_parser("view")
    for x in ("--root", "--tails", "--plan", "--out"):
        s.add_argument(x, required=True)
    s = sub.add_parser("values")
    for x in ("--root", "--plan", "--footers", "--ledger", "--sizes", "--db-rel", "--date", "--machine", "--out"):
        s.add_argument(x, required=True)
    sub.add_parser("keys")
    s = sub.add_parser("check-root")
    for x in ("--root", "--view", "--plan", "--footers", "--ledger", "--tom1-sums", "--tom1-manifest", "--db-rel",
              "--out"):
        s.add_argument(x, required=True)
    s.add_argument("--src-release-info", required=True)
    s.add_argument("--need-views", default="")
    s.add_argument("--allow-gone", default="")
    s.add_argument("--max", type=int, default=9999)
    s.add_argument("--want-columns", type=int, default=0)
    s.add_argument("--expect-files", type=int, default=0)
    s.add_argument("--expect-rows", type=int, default=0)
    s.add_argument("--jobs", type=int, default=8)
    s = sub.add_parser("hf-push")
    for x in ("--repo", "--root", "--adds", "--message"):
        s.add_argument(x, required=True)
    s.add_argument("--deletes")
    s.add_argument("--expect", choices=("public", "private"), default="public")
    a = ap.parse_args(argv)
    return {"prepare": cmd_prepare, "keep": cmd_keep, "footers": cmd_footers, "plan": cmd_plan, "pass": cmd_pass,
            "facts": cmd_facts, "ledgers-check": cmd_ledgers_check, "tables": cmd_tables, "manifest": cmd_manifest, "sums": cmd_sums, "view": cmd_view,
            "values": cmd_values, "keys": cmd_keys, "check-root": cmd_check_root, "hf-push": cmd_hf_push}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
