"""tom6_tools.py: the tools of the TOM-6 machine (a revision of TOM 1.0.0: the 149 new project files and the license
values). It uses tom2_tools.py (footer records, plan, value pass) and tom_tools.py (sizes, markers) of the stage.

  newlist     the 149 new projects: the funnel list, the name map, the removed list and the MANIFEST.new.tsv of each
              new-project machine; 149 in, 0 missing, 0 extra (a removed project of a machine is dropped)
  footfix     organizations_mapping_sha256 of the new files := the mapping_sha256 of release_info (footer only,
              parquet_rename.py --set-kv, proved by parquet_rename_check.py); new.resolved.tsv, new.MANIFEST.tsv
  footers     the footer of every project file: TOM-4 files by ranged S3 reads (or a local root), new files local;
              against the merged MANIFEST.tsv (size and rows)
  shape       the Parquet form gate of the new files against a TOM-4 file (columns and order, types, footer keys,
              writer, codecs, encodings, Bloom filters, page index, statistics, row groups)
  filevals    project -> the license value in the file (footer statistics: one value in every row group)
  lscan-list  the license_scan.py list of the new projects (project, clone_url, run_commit)
  ledger-rows the ledgers.parquet rows of the new projects from the ctp metrics ledger of each machine
  pseudo      pseudonymization.json with the registry of the new batch (from the footers of the new files)
  domains     the published form of the new domain rows (organization_domains.new.parquet of each new-project
              machine has the link schema; it moves to organization_domains.linkschema.parquet): organization_id,
              and review_path, error_stratum, p_error of the error model of TOM 1.0.0 (inputs/new_domain_errors.tsv)
  base        the base root: TOM-4 plus the new projects (MANIFEST.tsv, SHA256SUMS, ledgers.parquet, organizations/
              with the new rows, pseudonymization.json); parquet/ links to the local input files
  manifest    MANIFEST.tsv of the new root (the base rows; bytes and sha256 of the changed files from the ledger)
  sums        SHA256SUMS of the new root; the changed list, the gone list and the list of new unchanged files
  view        the check view: local files and a sparse stand-in with the real footer for each unchanged file
  tables      project_licenses.parquet, its view, and the release_info rows and sha256 of every table
  values      the measured values of the [[tom: KEY]] placeholders
  check-root  the checks of the new root
  hf-push     a new revision of the Hugging Face repository: the data files, then README.md and SHA256SUMS
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tom2_tools as T2  # noqa: E402
import tom_tools as T  # noqa: E402

SUFFIX = "-dataset.parquet"
MAN_COLS = ["project", "clone_url", "size_class", "commits", "run_commit", "frame_commit", "cregit_commit", "ctp_commit",
            "rows", "bytes", "sha256", "path"]
TABLE_KEY = {"project_facts": None, "project_labels": "project", "project_languages": "project",
             "project_organizations": "project", "organization_domains": None}
SALT_NOTE = ("By design we do not guarantee that the pseudonymization is stable, since the project ran in multiple "
             "batches and each batch deletes its own salt; a personid is stable only inside one batch.")


def say(text: str) -> None:
    print(T2.mask(text), flush=True)


def sha256(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_tsv(p) -> list[dict]:
    with open(p, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(p, rows, cols) -> None:
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read_sums(p) -> dict[str, str]:
    out = {}
    for line in Path(p).read_text().splitlines():
        if line.strip():
            d, f = line.split("  ", 1)
            out[f] = d
    return out


def write_sums(p, sums: dict) -> None:
    Path(p).write_text("".join(f"{sums[f]}  {f}\n" for f in sorted(sums)))


def project_of(name: str) -> str:
    return name[:-len(SUFFIX)] if name.endswith(SUFFIX) else name


def duck(db=None, tmp=None, read_only=False):
    import duckdb
    con = duckdb.connect(db, read_only=read_only) if db else duckdb.connect()
    t = tmp or os.environ.get("TOM_DUCKDB_TMP")
    if t:
        os.makedirs(t, exist_ok=True)
        con.execute(f"SET temp_directory = '{t}'")
    return con


# --------------------------------------------------------------------------------------------------- newlist --
def cmd_newlist(a) -> int:
    names = {(r["name"], r["host"]): r["project"] for r in read_tsv(a.names)}
    want, probs = [], []
    for r in read_tsv(a.new_projects):
        p = names.get((r["name"], r["host"]))
        if p is None:
            probs.append(f"no TOM name for {r['host']} {r['name']}")
        else:
            want.append(p)
    removed = {r["project"] for r in read_tsv(a.removed)}
    tom4 = {r["project"] for r in read_tsv(a.tom4_manifest)}
    hdr = None
    got, dropped = {}, []
    for spec in a.run:
        mach, d = spec.split("=", 1)
        man = Path(d) / "MANIFEST.new.tsv"
        if not man.exists():
            probs.append(f"{mach}: no MANIFEST.new.tsv")
            continue
        with open(man, newline="") as f:
            rd = csv.DictReader(f, delimiter="\t")
            if rd.fieldnames != MAN_COLS:
                probs.append(f"{mach}: MANIFEST.new.tsv columns {rd.fieldnames} are not the TOM columns")
            for r in rd:
                p = r["project"]
                if p in got:
                    probs.append(f"{p}: in {got[p]['machine']} and {mach}")
                elif p in removed:
                    dropped.append(p)
                elif p not in want:
                    probs.append(f"{p} ({mach}): not in the list and not removed (extra)")
                else:
                    got[p] = dict(r, machine=mach, dir=d)
            hdr = rd.fieldnames
    missing = sorted(set(want) - set(got))
    extra = sorted(set(got) - set(want))
    both = sorted(set(got) & tom4)
    if len(set(want)) != len(want):
        probs.append("the list has a project twice")
    if a.expect is not None and len(want) != a.expect:
        probs.append(f"the list has {len(want)} projects, expected {a.expect}")
    for p in missing:
        probs.append(f"{p}: missing (no machine file)")
    for p in both:
        probs.append(f"{p}: already in TOM-4")
    for x in probs[:40]:
        say("PROBLEM: " + x)
    say(f"newlist: {len(got)} in, {len(missing)} missing, {len(extra)} extra; {len(dropped)} removed rows dropped "
        f"({len(removed)} removed projects); machines {sorted({r['machine'] for r in got.values()})}")
    if probs:
        return 1
    rows = [got[p] for p in sorted(got, key=lambda p: f"parquet/{p}{SUFFIX}")]
    write_tsv(a.out_manifest, rows, MAN_COLS)
    write_tsv(a.out, [{"project": r["project"], "file": f"{r['project']}{SUFFIX}", "machine": r["machine"],
                       "sha256": r["sha256"], "bytes": r["bytes"], "rows": r["rows"]} for r in rows],
              ["project", "file", "machine", "sha256", "bytes", "rows"])
    return 0


# --------------------------------------------------------------------------------------------------- footfix --
FOOTFIX_KEY = "organizations_mapping_sha256"


def _kv(p) -> tuple:
    import pyarrow.parquet as pq
    md = pq.ParquetFile(p).metadata
    return {k.decode(): v.decode() for k, v in (md.metadata or {}).items()}, md.num_rows, md.num_row_groups


def _prefix_sha(p, n) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        left = n
        while left:
            b = f.read(min(8 << 20, left))
            if not b:
                break
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def _footer_start(p) -> int:
    size = os.path.getsize(p)
    with open(p, "rb") as f:
        f.seek(size - 8)
        tail = f.read(8)
    if tail[4:] != b"PAR1":
        raise SystemExit(f"ABORT: {p}: no PAR1 at the end")
    return size - 8 - int.from_bytes(tail[:4], "little")


def _footfix_one(job) -> dict:
    import subprocess
    r, a, want = job
    f = r["file"]
    src, out = Path(a.new_files) / f, Path(a.work) / "out" / f
    rec = {"file": f, "problems": []}
    kv, rows, rgs = _kv(src)
    rec["old_value"] = kv.get(FOOTFIX_KEY)
    if kv.get(FOOTFIX_KEY) == want:
        rec["status"] = "already"
        return rec
    if sha256(src) != r["sha256"] or os.path.getsize(src) != int(r["bytes"]) or rows != int(r["rows"]):
        rec["problems"].append("the input is not its new.resolved.tsv row (sha256, bytes or rows)")
        return rec
    if out.exists():
        stale = Path(a.work) / "stale"
        stale.mkdir(exist_ok=True)
        os.rename(out, stale / f"{f}.{time.strftime('%Y%m%dT%H%M%S')}")
    setkv = f"{FOOTFIX_KEY}={want}"
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    p = subprocess.run([sys.executable, "-I", "-B", a.rename_py, str(src), str(out), "--set-kv", setkv],
                       capture_output=True, text=True, env=env)
    if p.returncode or not out.exists():
        rec["problems"].append(f"parquet_rename.py rc {p.returncode}: {p.stderr.strip()[-300:]}")
        return rec
    c = subprocess.run([sys.executable, "-I", "-B", a.check_py, "--set-kv", setkv, str(src), str(out)],
                       capture_output=True, text=True, env=env)
    try:
        cj = json.loads((c.stdout.strip().splitlines() or ["{}"])[-1])
    except json.JSONDecodeError:
        cj = {}
    rec["check_ok"] = bool(c.returncode == 0 and cj.get("ok"))
    if not rec["check_ok"]:
        rec["problems"].append(f"parquet_rename_check.py rc {c.returncode}: {(c.stdout + c.stderr).strip()[-400:]}")
    # the same proof once more here: the bytes before the old footer, rows, row groups, the other key-values
    nkv, nrows, nrgs = _kv(out)
    fs = _footer_start(src)
    rec["prefix_same"] = _footer_start(out) == fs and _prefix_sha(src, fs) == _prefix_sha(out, fs)
    rec["rows_same"] = (nrows, nrgs) == (rows, rgs)
    rec["other_kv_same"] = ({k: v for k, v in nkv.items() if k != FOOTFIX_KEY} ==
                            {k: v for k, v in kv.items() if k != FOOTFIX_KEY}) and sorted(nkv) == sorted(kv)
    rec["new_value_ok"] = nkv.get(FOOTFIX_KEY) == want
    for k in ("prefix_same", "rows_same", "other_kv_same", "new_value_ok"):
        if not rec[k]:
            rec["problems"].append(k)
    rec.update(status="fixed", old_sha256=r["sha256"], old_bytes=int(r["bytes"]), sha256=sha256(out),
               bytes=os.path.getsize(out), rows=nrows, row_groups=nrgs, footer_start=fs)
    return rec


def cmd_footfix(a) -> int:
    """organizations_mapping_sha256 of the new files := the mapping_sha256 of release_info (the TOM 1.0.0 label).
    Each new-project machine wrote the hash of its own merged links (TOM + its new rows); the values of the files are
    the values of the release tables. Footer only (parquet_rename.py --set-kv); every file is proved by
    parquet_rename_check.py and here (the bytes before the footer, rows, row groups, the other key-values). The files
    change place only when all pass; the old link moves to WORK/before/. new.resolved.tsv and new.MANIFEST.tsv get the
    new sha256 and bytes (their first form stays as *.before-footfix)."""
    import pyarrow.parquet as pq
    ri = {r["key"]: r["value"] for r in pq.read_table(a.release_info).to_pylist()}
    want = ri.get("mapping_sha256") or ""
    refkv = _kv(a.ref)[0]
    if not re.fullmatch(r"[0-9a-f]{64}", want) or refkv.get(FOOTFIX_KEY) != want:
        say(f"PROBLEM: release_info mapping_sha256 {want[:12]!r} is not the footer value of {Path(a.ref).name} "
            f"({str(refkv.get(FOOTFIX_KEY))[:12]})")
        return 1
    res = read_tsv(a.resolved)
    man = read_tsv(a.manifest)
    rcols = ["project", "file", "machine", "sha256", "bytes", "rows"]
    for path, rows, cols in ((a.resolved, res, rcols), (a.manifest, man, MAN_COLS)):
        tmp = Path(a.work) / (Path(path).name + ".roundtrip")
        Path(a.work).mkdir(parents=True, exist_ok=True)
        write_tsv(tmp, rows, cols)
        if tmp.read_bytes() != Path(path).read_bytes():
            say(f"PROBLEM: {Path(path).name} does not round-trip through write_tsv; nothing changed")
            return 1
        os.replace(tmp, Path(a.work) / (Path(path).name + ".roundtrip-ok"))
    (Path(a.work) / "out").mkdir(parents=True, exist_ok=True)
    (Path(a.work) / "before").mkdir(exist_ok=True)
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        recs = list(ex.map(_footfix_one, [(r, a, want) for r in res]))
    probs = [f"{r['file']}: {x}" for r in recs for x in r["problems"]]
    already = [r for r in recs if r["status"] == "already"]
    fixed = [r for r in recs if r["status"] == "fixed"]
    # an already fixed file must be the one that an earlier run of this step put in place
    rowmap = {r["file"]: r for r in res}
    for r in already:
        p = Path(a.new_files) / r["file"]
        if sha256(p) != rowmap[r["file"]]["sha256"] or os.path.getsize(p) != int(rowmap[r["file"]]["bytes"]):
            probs.append(f"{r['file']}: has the label but is not its new.resolved.tsv row")
    with open(a.log, "a") as fo:
        for r in recs:
            fo.write(json.dumps(r, sort_keys=True) + "\n")
    for x in probs[:40]:
        say("PROBLEM: " + x)
    if probs:
        say(f"footfix: {len(fixed)} to fix, {len(already)} already; problems {len(probs)}; nothing moved")
        return 1
    for path in (a.resolved, a.manifest):
        bk = Path(str(path) + ".before-footfix")
        if not bk.exists():
            bk.write_bytes(Path(path).read_bytes())
    for r in fixed:
        f = r["file"]
        os.rename(Path(a.new_files) / f, Path(a.work) / "before" / f)
        os.rename(Path(a.work) / "out" / f, Path(a.new_files) / f)
    fx = {r["file"]: r for r in fixed}
    for row in res:
        if row["file"] in fx:
            row["sha256"], row["bytes"] = fx[row["file"]]["sha256"], str(fx[row["file"]]["bytes"])
    mp = {f"parquet/{r['file']}": r for r in fixed}
    nman = 0
    for row in man:
        if row["path"] in mp:
            row["sha256"], row["bytes"] = mp[row["path"]]["sha256"], str(mp[row["path"]]["bytes"])
            nman += 1
    if nman != len(fixed):
        say(f"PROBLEM: {nman} new.MANIFEST.tsv rows for {len(fixed)} fixed files")
        return 1
    write_tsv(a.resolved, res, rcols)
    write_tsv(a.manifest, man, MAN_COLS)
    for row in res:
        p = Path(a.new_files) / row["file"]
        if sha256(p) != row["sha256"] or _kv(p)[0].get(FOOTFIX_KEY) != want:
            say(f"PROBLEM: {row['file']}: after the move, the file is not its row or has not the label")
            return 1
    say(f"footfix: {len(res)} new files: {len(fixed)} fixed, {len(already)} already; {FOOTFIX_KEY} = {want[:12]} "
        f"(release_info); checks ok {sum(r.get('check_ok', False) for r in fixed)} of {len(fixed)}, prefix same "
        f"{sum(r.get('prefix_same', False) for r in fixed)}, rows same {sum(r.get('rows_same', False) for r in fixed)}, "
        f"other key-values same {sum(r.get('other_kv_same', False) for r in fixed)}; problems 0")
    return 0


# --------------------------------------------------------------------------------------------------- footers --
def cmd_footers(a) -> int:
    man = {r["path"]: r for r in read_tsv(a.manifest)}
    new = {r["file"] for r in read_tsv(a.new)}
    items = [(Path(p).name, "new" if Path(p).name in new else "tom4") for p in sorted(man)]
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    client = bucket = prefix = None
    if a.s3:
        import boto3
        from botocore.config import Config
        bucket, prefix = a.s3.split("/", 1)
        client = boto3.client("s3", config=Config(retries={"max_attempts": 10, "mode": "adaptive"},
                                                  max_pool_connections=a.jobs + 4))

    def one(item):
        f, origin = item
        if origin == "new":
            body, total = T2.fetch_tail_local(os.path.join(a.local_new, f), a.first)
        elif a.s3:
            body, total = T2.fetch_tail_s3(client, bucket, f"{prefix}/parquet/{f}", a.first)
        else:
            body, total = T2.fetch_tail_local(os.path.join(a.local_tom4, "parquet", f), a.first)
        rec = T2.footer_record(f, total, body)
        rec["origin"] = origin
        (out / (f + ".tail")).write_bytes(body[-(rec["footer_len"] + 8):])
        return rec

    probs, recs = [], []
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(one, it): it for it in items}
        for fu in cf.as_completed(futs):
            f, _ = futs[fu]
            try:
                rec = fu.result()
            except Exception as e:  # noqa: BLE001
                probs.append(f"{f}: {type(e).__name__}: {str(e)[:200]}")
                continue
            m = man[f"parquet/{f}"]
            if int(m["bytes"]) != rec["size"] or int(m["rows"]) != rec["rows"]:
                probs.append(f"{f}: size {rec['size']} rows {rec['rows']} are not its MANIFEST.tsv row")
            recs.append(rec)
    recs.sort(key=lambda r: r["file"])
    with open(out / "footers.jsonl", "w") as fo:
        for r in recs:
            fo.write(T2.jline(r) + "\n")
    for x in probs[:30]:
        say("PROBLEM: " + x)
    say(f"footers: {len(recs)} of {len(items)} files ({sum(r['origin'] == 'new' for r in recs)} new), "
        f"{sum(r['rows'] for r in recs):,} rows, {sum(r['size'] for r in recs):,} B; problems {len(probs)}")
    return 1 if probs or len(recs) != len(items) else 0


# ----------------------------------------------------------------------------------------------------- shape --
def parquet_form(con, f: str) -> dict:
    """The published form of a file (the gate of the new-project kit, ta_tools.py shape)."""
    import pyarrow.parquet as pq
    md = pq.ParquetFile(f).metadata
    kv = [k.decode() for k in (md.metadata or {}).keys()]
    cols = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [f]).fetchall()
    sch = con.execute("SELECT name, type, type_length, repetition_type, converted_type, logical_type "
                      "FROM parquet_schema(?)", [f]).fetchall()
    per = con.execute("""SELECT path_in_schema, list(DISTINCT compression), list(DISTINCT encodings),
                                bool_or(bloom_filter_offset IS NOT NULL), bool_and(bloom_filter_offset IS NOT NULL),
                                bool_or(index_page_offset IS NOT NULL), bool_and(stats_null_count IS NOT NULL)
                         FROM parquet_metadata(?) GROUP BY path_in_schema ORDER BY min(column_id)""", [f]).fetchall()
    rgn = [r[1] for r in con.execute("SELECT DISTINCT row_group_id, row_group_num_rows FROM parquet_metadata(?) "
                                     "ORDER BY 1", [f]).fetchall()]
    return {"columns": [(c[0], c[1]) for c in cols], "parquet_schema": sch, "kv_keys": kv,
            "created_by": md.created_by, "format_version": md.format_version,
            "codec": {p: c for p, c, *_ in per},
            "encodings": {p: sorted({x.strip() for e in encs for x in e.split(",")}) for p, _, encs, *_ in per},
            "bloom_any": {p: b for p, _, _, b, *_ in per}, "bloom_all": {p: b for p, _, _, _, b, *_ in per},
            "index_page": any(r[5] for r in per), "statistics": all(r[6] for r in per),
            "row_groups_full": all(n == 1_000_000 for n in rgn[:-1]) and (rgn[-1] <= 1_000_000 if rgn else True),
            "row_groups": len(rgn)}


DICT_FALLBACK = {"PLAIN", "RLE", "BIT_PACKED", "RLE_DICTIONARY", "PLAIN_DICTIONARY"}


def cmd_shape(a) -> int:
    con = duck()
    ref = parquet_form(con, a.ref)
    if len(ref["columns"]) != a.columns:
        say(f"PROBLEM: the reference {Path(a.ref).name} has {len(ref['columns'])} columns, not {a.columns}")
        return 1
    bad = 0
    files = [x.strip() for x in open(a.list) if x.strip()] if a.list else a.files
    for f in files:
        got = parquet_form(con, f)
        why = [k for k in ("columns", "parquet_schema", "kv_keys", "created_by", "format_version", "codec", "bloom_any",
                           "bloom_all", "index_page", "statistics") if got[k] != ref[k]]
        for c, encs in got["encodings"].items():
            allow = set(ref["encodings"].get(c, [])) | (DICT_FALLBACK if "RLE_DICTIONARY" in ref["encodings"].get(c, [])
                                                        else set())
            if not set(encs) <= allow:
                why.append(f"encodings of {c}")
        if not got["row_groups_full"]:
            why.append("row groups")
        bad += bool(why)
        say(f"{'ok ' if not why else 'BAD'} {Path(f).name}: {len(got['columns'])} columns, {got['row_groups']} row "
            f"groups, {got['created_by']}, format {got['format_version']}{'; differs: ' + ', '.join(why) if why else ''}")
    say(f"shape: {len(files) - bad} of {len(files)} files have the form of {Path(a.ref).name}")
    return 1 if bad else 0


# -------------------------------------------------------------------------------------------------- filevals --
def cmd_filevals(a) -> int:
    probs, rows = [], []
    for f, r in sorted(T2.read_footers(a.footers).items()):
        rgs = r["stats"].get("license", [])
        vals = {s[0] for s in rgs}
        if not rgs or len(vals) != 1 or not T2.stats_hold(rgs, next(iter(vals))):
            probs.append(f"{f}: the license column has not one value in the footer statistics")
            continue
        rows.append({"project": project_of(f), "license": next(iter(vals))})
    for x in probs[:20]:
        say("PROBLEM: " + x)
    write_tsv(a.out, rows, ["project", "license"])
    say(f"filevals: {len(rows)} files; NOASSERTION {sum(r['license'] == 'NOASSERTION' for r in rows)}; "
        f"problems {len(probs)}")
    return 1 if probs else 0


def cmd_lscan_list(a) -> int:
    rows = [{"project": r["project"], "clone_url": r["clone_url"], "run_commit": r["run_commit"], "fetch_urls": ""}
            for r in read_tsv(a.manifest)]
    write_tsv(a.out, rows, ["project", "clone_url", "run_commit", "fetch_urls"])
    say(f"lscan-list: {len(rows)} projects")
    return 0


# ------------------------------------------------------------------------------------------------ ledger-rows --
def cmd_ledger_rows(a) -> int:
    """The ledgers.parquet rows of the new projects. The source is the ctp metrics ledger of each machine
    (results/ledger/metrics.tsv: one row per phase attempt) and the published file (MANIFEST.new.tsv): one row per
    phase attempt (step = the phase), then one row step=project status=done with the file. Columns without a source
    stay null. No path, no host name and no person data goes into a row."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    ref = pq.read_schema(a.schema_ref)
    names = {r["project"]: r for r in read_tsv(a.manifest)}
    out, probs = [], []
    mask_sha = a.file_mask_sha256
    for spec in a.run:
        mach, d = spec.split("=", 1)
        met = Path(d) / "ledger" / "metrics.tsv"
        if not met.exists():
            if any(r["machine"] == mach for r in read_tsv(a.resolved)):
                probs.append(f"{mach}: no ledger/metrics.tsv")
            continue
        rows = read_tsv(met)
        by: dict[str, list] = {}
        for r in rows:
            if r.get("project") in names and r.get("project") in {x["project"] for x in read_tsv(a.resolved)
                                                                  if x["machine"] == mach}:
                by.setdefault(r["project"], []).append(r)
        for p, rs in sorted(by.items()):
            m = names[p]
            rs.sort(key=lambda r: r.get("iso_start", ""))
            run_id = f"tom-add-{rs[0].get('iso_start', '')[:19].replace(':', '').replace('-', '')}Z-{mach}"
            attempts: dict[str, int] = {}
            seq = 0
            for r in rs:
                ph = r.get("phase") or ""
                attempts[ph] = attempts.get(ph, 0) + 1
                seq += 1
                rc = r.get("rc")
                rc_i = int(rc) if rc not in (None, "") and re.fullmatch(r"-?\d+", rc) else None
                dur = float(r["duration_s"]) if r.get("duration_s") not in (None, "") else None
                st = r.get("iso_start") or None
                end = None
                if st and dur is not None:
                    from datetime import datetime, timedelta
                    try:
                        end = (datetime.fromisoformat(st) + timedelta(seconds=dur)).isoformat()
                    except ValueError:
                        end = None
                out.append({"project": p, "run_id": run_id, "attempt": attempts[ph], "seq": seq, "step": ph,
                            "status": "ok" if rc_i == 0 else "failed", "start_utc": st, "end_utc": end,
                            "duration_s": dur, "exit_code": rc_i, "v": 1, "pinned_sha": m["run_commit"],
                            "checked_out_sha": m["run_commit"], "snapshot_sha": m["run_commit"],
                            "file_mask_sha256": mask_sha})
            seq += 1
            out.append({"project": p, "run_id": run_id, "attempt": 1, "seq": seq, "step": "project", "status": "done",
                        "start_utc": rs[0].get("iso_start") or None, "end_utc": out[-1]["end_utc"], "v": 1,
                        "pinned_sha": m["run_commit"], "checked_out_sha": m["run_commit"],
                        "snapshot_sha": m["run_commit"], "file_mask_sha256": mask_sha,
                        "parquet_file": f"{p}{SUFFIX}", "parquet_rows": int(m["rows"]), "parquet_bytes": int(m["bytes"]),
                        "parquet_sha256": m["sha256"],
                        "manifest_row": "\t".join(m[c] for c in MAN_COLS),
                        "tools": json.dumps({"cregit_commit": m["cregit_commit"], "ctp_commit": m["ctp_commit"]},
                                            sort_keys=True)})
    have = {r["project"] for r in out}
    for p in sorted(set(names) - have):
        probs.append(f"{p}: no ledger row")
    for x in probs[:30]:
        say("PROBLEM: " + x)
    if probs:
        return 1
    cols = {f.name: [r.get(f.name) for r in out] for f in ref}
    t = pa.Table.from_pydict(cols, schema=ref.remove_metadata())
    pq.write_table(t, a.out, compression="zstd")
    say(f"ledger-rows: {t.num_rows} rows for {len(have)} projects")
    return 0


# ---------------------------------------------------------------------------------------------------- pseudo --
def cmd_pseudo(a) -> int:
    pj = json.loads(Path(a.tom4).read_text())
    feet = T2.read_footers(a.footers)
    new = [r["file"] for r in read_tsv(a.new)]
    reg, probs = {}, []
    for f in new:
        kv = feet[f]["kv"]
        if kv.get("pseudonymization_version") != pj.get("pseudonymization_version"):
            probs.append(f"{f}: pseudonymization_version {kv.get('pseudonymization_version')} is not "
                         f"{pj.get('pseudonymization_version')}")
        reg[project_of(f)] = kv.get("pseudonymization_registry_sha256")
    old = {r.get("registry_sha256") for r in pj.get("registries", [])}
    if any(v is None for v in reg.values()) or set(reg.values()) & old:
        probs.append("a new file has no registry key, or the registry of an earlier write")
    for x in probs[:20]:
        say("PROBLEM: " + x)
    if probs:
        return 1
    vals = sorted(set(reg.values()))
    entry = {"files": len(new), "projects": sorted(reg),
             "scope": "the files of these projects (a later batch, with its own salt and one registry for each project)"}
    if len(vals) == 1:
        entry["registry_sha256"] = vals[0]
    else:
        entry["registry_sha256_by_project"] = dict(sorted(reg.items()))
    pj["registries"] = list(pj.get("registries", [])) + [entry]
    pj["batches"] = SALT_NOTE
    Path(a.out).write_text(json.dumps(pj, indent=1, sort_keys=True) + "\n")
    say(f"pseudo: {len(pj['registries'])} registries; the new batch: {len(new)} files, {len(vals)} registry values")
    return 0


# ------------------------------------------------------------------------------------------------------ base --
def merge_table(old_path, new_paths, out_path, key, only=None):
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    old = pq.read_table(old_path)
    parts = [old]
    for p in new_paths:
        t = pq.read_table(p)
        if not t.schema.remove_metadata().equals(old.schema.remove_metadata()):
            raise SystemExit(f"ABORT: {p}: the schema is not the schema of {Path(old_path).name}")
        t = t.cast(old.schema)
        if only is not None and "project" in t.column_names:
            t = t.filter(pc.is_in(t.column("project"), value_set=pa.array(sorted(only))))
        parts.append(t)
    new = pa.concat_tables(parts[1:]) if len(parts) > 1 else None
    if key and new is not None:
        dup = set(old.column(key).to_pylist()) & set(new.column(key).to_pylist())
        if dup:
            raise SystemExit(f"ABORT: {Path(out_path).name}: rows of {sorted(dup)[:3]} are in TOM-4 and new")
    if key is None and new is not None and "project" not in old.column_names:
        # organization_domains: a domain row in both must be equal; equal rows are not added again
        k0 = old.column_names[0]
        seen = {tuple(r.values()) for r in old.to_pylist()}
        byk = {r[k0]: r for r in old.to_pylist()}
        keep = []
        for r in new.to_pylist():
            if tuple(r.values()) in seen:
                continue
            if r[k0] in byk:
                raise SystemExit(f"ABORT: {Path(out_path).name}: the row of {r[k0]!r} differs from TOM-4")
            keep.append(r)
            seen.add(tuple(r.values()))
        new = pa.Table.from_pylist(keep, schema=old.schema) if keep else None
    merged = pa.concat_tables([old, new]) if new is not None else old
    sort_col = "project" if "project" in old.column_names else old.column_names[0]
    vals = old.column(sort_col).to_pylist()
    if vals == sorted(vals):
        idx = pc.sort_indices(merged, sort_keys=[(sort_col, "ascending")])
        merged = merged.take(idx)  # stable: the order inside a project is kept
    pf = pq.ParquetFile(old_path)
    comp = pf.metadata.row_group(0).column(0).compression.lower() if pf.metadata.num_row_groups else "zstd"
    pq.write_table(merged, out_path, compression=comp if comp in ("zstd", "snappy", "gzip") else "zstd")
    back = pq.read_table(out_path)
    assert back.num_rows == merged.num_rows
    return old.num_rows, back.num_rows


LINK_COLS = ["domain", "firm_based_on_domain", "organisation_kind", "match", "matched_domain", "confidence", "source"]
ERR_COLS = ["domain", "organization_id", "match", "matched_domain", "confidence", "source", "review_path",
            "error_stratum", "p_error"]


def cmd_domains(a) -> int:
    """The published form of the new domain rows: organization_domains.new.parquet of each new-project machine has the
    link schema (domain_links); it moves to organization_domains.linkschema.parquet and the file of the old name gets
    the schema of the TOM-4 table: organization_id = firm_based_on_domain (organisation_kind is the kind of the
    organization in organizations.parquet: it must agree, then it is dropped), and review_path, error_stratum and
    p_error of the error model of TOM 1.0.0 for the new domain (--errors; domainfix/em_newdomains.py of the kit).
    A second run checks that the file of the old name is the one it would write."""
    import pyarrow.parquet as pq
    t4 = Path(a.tom4) / "organizations"
    want = pq.read_schema(t4 / "organization_domains.parquet").remove_metadata()
    errs = {r["domain"]: r for r in read_tsv(a.errors)}
    con = duck()
    con.execute("CREATE TABLE e (domain VARCHAR, organization_id VARCHAR, match VARCHAR, matched_domain VARCHAR, "
                "confidence VARCHAR, source VARCHAR, review_path VARCHAR, error_stratum VARCHAR, p_error DOUBLE)")
    if errs:
        con.executemany("INSERT INTO e VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [[r[c] if c != "p_error" else float(r[c]) for c in ERR_COLS] for r in errs.values()])
    org, dom = str(t4 / "organizations.parquet"), str(t4 / "organization_domains.parquet")
    seen = set()
    for d in a.new_dirs:
        n, ls = Path(d) / "organization_domains.new.parquet", Path(d) / "organization_domains.linkschema.parquet"
        if not ls.exists():
            if not n.exists():
                continue
            got = [f.name for f in pq.read_schema(n)]
            if got != LINK_COLS:
                raise SystemExit(f"ABORT: {n}: columns {got}, not the link schema (and no {ls.name})")
            os.rename(n, ls)
        con.execute(f"CREATE OR REPLACE VIEW l AS SELECT * FROM read_parquet('{ls}')")
        got = [r[0] for r in con.execute("DESCRIBE l").fetchall()]
        if got != LINK_COLS:
            raise SystemExit(f"ABORT: {ls}: columns {got}, not the link schema")
        nrow = con.execute("SELECT count(*) FROM l").fetchone()[0]
        bad = {
            "domains in TOM-4": f"SELECT count(*) FROM l WHERE domain IN (SELECT domain FROM read_parquet('{dom}'))",
            "domains of another machine": f"SELECT count(*) FROM l WHERE domain IN ({','.join(repr(x) for x in seen) or 'NULL'})",
            "repeated domains": "SELECT count(*) - count(DISTINCT domain) FROM l",
            "independent rows": "SELECT count(*) FROM l WHERE firm_based_on_domain = 'independent'",
            "ids not in organizations": f"SELECT count(*) FROM l WHERE firm_based_on_domain NOT IN "
                                        f"(SELECT organization_id FROM read_parquet('{org}'))",
            "kinds not the kind of the organization": f"SELECT count(*) FROM l JOIN read_parquet('{org}') o ON "
                                                      f"o.organization_id = l.firm_based_on_domain WHERE o.kind IS DISTINCT FROM l.organisation_kind",
            "domains without an error row": "SELECT count(*) FROM l WHERE domain NOT IN (SELECT domain FROM e)",
            "error rows with other link values": "SELECT count(*) FROM l JOIN e USING (domain) WHERE "
                                                 "e.organization_id IS DISTINCT FROM l.firm_based_on_domain OR "
                                                 "e.match IS DISTINCT FROM l.match OR e.matched_domain IS DISTINCT FROM l.matched_domain OR "
                                                 "e.confidence IS DISTINCT FROM l.confidence OR e.source IS DISTINCT FROM l.source",
            "NULL values": "SELECT count(*) FROM l JOIN e USING (domain) WHERE e.review_path IS NULL OR "
                           "e.error_stratum IS NULL OR e.p_error IS NULL OR l.domain IS NULL OR l.firm_based_on_domain IS NULL",
        }
        for what, q in bad.items():
            k = con.execute(q).fetchone()[0]
            if k:
                raise SystemExit(f"ABORT: {ls}: {k} {what}")
        seen |= {x for (x,) in con.execute("SELECT domain FROM l").fetchall()}
        sel = ("SELECT l.domain, l.firm_based_on_domain AS organization_id, l.match, l.matched_domain, l.confidence, "
               "l.source, e.review_path, e.error_stratum, e.p_error FROM l JOIN e USING (domain) ORDER BY l.domain")
        tmp = n.with_name(f".{n.name}.tmp")
        con.execute(f"COPY ({sel}) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)")
        if not pq.read_schema(tmp).remove_metadata().equals(want):
            raise SystemExit(f"ABORT: {tmp}: the schema is not the schema of the TOM-4 table")
        rows = pq.read_table(tmp).to_pylist()
        for r in rows:
            if r["p_error"] != float(errs[r["domain"]]["p_error"]):
                raise SystemExit(f"ABORT: {tmp}: p_error of {r['domain']} is not the error row")
        if len(rows) != nrow:
            raise SystemExit(f"ABORT: {tmp}: {len(rows)} rows, not {nrow}")
        if n.exists():
            same = pq.read_table(n).to_pylist() == rows and pq.read_schema(n).remove_metadata().equals(want)
            os.remove(tmp)
            if not same:
                raise SystemExit(f"ABORT: {n} is not the file this step writes ({ls.name} is the input)")
            say(f"{n}: ok, already in the published form ({nrow} rows)")
        else:
            os.replace(tmp, n)
            say(f"{n}: {nrow} rows in the published form, sha256 {sha256(n)[:12]}; the link form is {ls.name} "
                f"(sha256 {sha256(ls)[:12]})")
    if seen != set(errs):
        raise SystemExit(f"ABORT: {len(seen)} new domains, {len(errs)} error rows")
    say(f"domains: {len(seen)} new domain rows in the published form of organization_domains")
    return 0


def cmd_base(a) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq
    t4, out = Path(a.tom4), Path(a.out)
    (out / "organizations").mkdir(parents=True, exist_ok=True)
    (out / "parquet").mkdir(exist_ok=True)
    sums = read_sums(t4 / "SHA256SUMS")
    new = read_tsv(a.new)
    report = {}
    # the documents, links.json and the other TOM-4 files outside parquet/: as they are
    for rel in sorted(sums):
        if rel.startswith("parquet/"):
            continue
        src = t4 / rel
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            os.link(src, dst) if os.stat(src).st_dev == os.stat(dst.parent).st_dev else dst.write_bytes(src.read_bytes())
    # the tables with rows of the new projects
    for t, key in TABLE_KEY.items():
        news = [Path(d) / f"{t}.new.parquet" for d in a.new_dirs if (Path(d) / f"{t}.new.parquet").exists()]
        if t != "organization_domains" and len({r["machine"] for r in new}) and not news:
            raise SystemExit(f"ABORT: no {t}.new.parquet")
        dst = out / "organizations" / f"{t}.parquet"
        dst.unlink()
        n0, n1 = merge_table(t4 / "organizations" / f"{t}.parquet", news, dst, key, {r["project"] for r in new})
        report[t] = [n0, n1]
        sums[f"organizations/{t}.parquet"] = sha256(dst)
    # every project of the new list has its row in the project tables
    want = {r["project"] for r in new}
    for t in ("project_labels", "project_languages", "project_organizations"):
        have = set(pq.read_table(out / "organizations" / f"{t}.parquet", columns=["project"]).column(0).to_pylist())
        if not want <= have:
            raise SystemExit(f"ABORT: {t}: no row for {sorted(want - have)[:5]}")
    # release_info: the rows and sha256 of the changed tables
    ri_path = out / "organizations" / "release_info.parquet"
    ri = pq.read_table(ri_path)
    kv = dict(zip(ri.column("key").to_pylist(), ri.column("value").to_pylist()))
    for t in TABLE_KEY:
        kv[f"{t}_rows"] = str(report[t][1])
        kv[f"{t}_sha256"] = sums[f"organizations/{t}.parquet"]
    ri_path.unlink()
    pq.write_table(pa.table({"key": list(kv), "value": [kv[k] for k in kv]}, schema=ri.schema), ri_path,
                   compression="zstd")
    sums["organizations/release_info.parquet"] = sha256(ri_path)
    # ledgers.parquet: TOM-4 rows, then the rows of the new projects
    lt = pq.read_table(t4 / "ledgers.parquet")
    ln = pq.read_table(a.new_ledgers).cast(lt.schema.remove_metadata())
    if set(ln.column("project").to_pylist()) & set(lt.column("project").to_pylist()):
        raise SystemExit("ABORT: ledger rows of a new project are in TOM-4")
    lm = pa.concat_tables([lt.replace_schema_metadata(None), ln])
    md = dict(lt.schema.metadata or {})
    md[b"projects"] = str(len(set(lm.column("project").to_pylist()))).encode()
    md[b"rows"] = str(lm.num_rows).encode()
    md[b"added_rows"] = f"{ln.num_rows} rows of the ctp metrics ledger (tom6_tools.py ledger-rows)".encode()
    lm = lm.replace_schema_metadata(md)
    (out / "ledgers.parquet").unlink()
    pq.write_table(lm, out / "ledgers.parquet", compression="zstd")
    sums["ledgers.parquet"] = sha256(out / "ledgers.parquet")
    report["ledgers"] = [lt.num_rows, lm.num_rows]
    # pseudonymization.json
    (out / "pseudonymization.json").unlink()
    (out / "pseudonymization.json").write_bytes(Path(a.pseudo).read_bytes())
    sums["pseudonymization.json"] = sha256(out / "pseudonymization.json")
    # MANIFEST.tsv: the TOM-4 rows and the new rows, in path order
    man = read_tsv(t4 / "MANIFEST.tsv") + read_tsv(a.new_manifest)
    man.sort(key=lambda r: r["path"])
    (out / "MANIFEST.tsv").unlink()
    write_tsv(out / "MANIFEST.tsv", man, MAN_COLS)
    sums["MANIFEST.tsv"] = sha256(out / "MANIFEST.tsv")
    # parquet/: links to the local inputs (the new files and the TOM-4 files with a value change)
    for r in new:
        sums[f"parquet/{r['file']}"] = r["sha256"]
        dst = out / "parquet" / r["file"]
        if not dst.exists():
            os.symlink(os.path.join(a.new_files, r["file"]), dst)
    for f in sorted(os.listdir(a.tom4_files)) if a.tom4_files and os.path.isdir(a.tom4_files) else []:
        dst = out / "parquet" / f
        if f.endswith(SUFFIX) and not dst.exists():
            os.symlink(os.path.join(a.tom4_files, f), dst)
    write_sums(out / "SHA256SUMS", sums)
    say("base: " + "; ".join(f"{k} {v[0]:,} -> {v[1]:,}" for k, v in report.items()) +
        f"; MANIFEST {len(man):,} rows; SHA256SUMS {len(sums):,} rows")
    return 0


# -------------------------------------------------------------------------------------------------- manifest --
def cmd_manifest(a) -> int:
    base = read_tsv(a.base_manifest)
    plan = {r["file"]: r for r in T2.read_plan(a.plan)}
    led = T.read_ledger(a.ledger)
    probs, out = [], []
    for r in base:
        f = Path(r["path"]).name
        p = plan.get(f)
        if p is None:
            probs.append(f"{f}: not in the plan")
            continue
        r = dict(r)
        if p["kind"] != "unchanged":
            L = led.get(f)
            if not L or L.get("status") != "OK":
                probs.append(f"{f}: no OK ledger line")
                continue
            r["bytes"], r["sha256"] = str(L["out_bytes"]), L["out_sha256"]
            if int(r["rows"]) != int(L["rows"]):
                probs.append(f"{f}: rows {L['rows']} are not the base row {r['rows']}")
        out.append(r)
    if len(out) != len(plan):
        probs.append(f"{len(out)} rows for {len(plan)} plan files")
    for x in probs[:20]:
        say("PROBLEM: " + x)
    if probs:
        return 1
    write_tsv(a.out, out, MAN_COLS)
    say(f"manifest: {len(out):,} rows ({sum(plan[Path(r['path']).name]['kind'] != 'unchanged' for r in out):,} "
        f"changed files)")
    return 0


# ------------------------------------------------------------------------------------------------------ sums --
def local_files(root: Path) -> list[str]:
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not any(x.startswith(".") or x == "__pycache__" for x in rel.parts) and str(rel) != "SHA256SUMS":
            out.append(str(rel))
    return out


def cmd_sums(a) -> int:
    root = Path(a.root)
    base = read_sums(a.base_sums)
    plan = {r["file"]: r for r in T2.read_plan(a.plan)}
    new = {r["file"] for r in read_tsv(a.new)}
    loc = local_files(root)
    probs = []
    for f, r in plan.items():
        here = (root / "parquet" / f).exists()
        if r["kind"] == "unchanged" and here:
            probs.append(f"{f}: unchanged, but a local copy exists")
        if r["kind"] != "unchanged" and not here:
            probs.append(f"{f}: changed, but no local output")
    extra = [x for x in loc if x.startswith("parquet/") and Path(x).name not in plan]
    probs += [f"{x}: not in the plan" for x in extra]
    if probs:
        for x in probs[:20]:
            say("PROBLEM: " + x)
        return 1
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        dig = dict(zip(loc, ex.map(lambda r: sha256(root / r), loc)))
    sums = {f"parquet/{f}": base[f"parquet/{f}"] for f, r in plan.items() if r["kind"] == "unchanged"}
    sums.update(dig)
    write_sums(root / "SHA256SUMS", sums)
    changed = sorted(r for r in dig if base.get(r) != dig[r])
    gone = sorted(r for r in base if not r.startswith("parquet/") and r not in dig)
    new_unchanged = sorted(f"parquet/{f}" for f, r in plan.items() if r["kind"] == "unchanged" and f in new)
    Path(a.changed_out).write_text("".join(x + "\n" for x in changed))
    Path(a.gone_out).write_text("".join(x + "\n" for x in gone))
    Path(a.new_unchanged_out).write_text("".join(x + "\n" for x in new_unchanged))
    say(f"sums: {len(sums):,} rows ({len(dig):,} local files hashed); changed against the base {len(changed):,}; "
        f"gone {len(gone)}; new unchanged project files {len(new_unchanged)}")
    return 0


# ------------------------------------------------------------------------------------------------------ view --
def cmd_view(a) -> int:
    root, tails, v = Path(a.root), Path(a.tails), Path(a.out)
    feet = T2.read_footers(Path(a.tails) / "footers.jsonl")
    plan = T2.read_plan(a.plan)
    (v / "parquet").mkdir(parents=True, exist_ok=True)
    for rel in local_files(root) + ["SHA256SUMS"]:
        d = v / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        if not d.exists():
            os.link(root / rel, d)
    n = 0
    for r in plan:
        if r["kind"] != "unchanged":
            continue
        f = r["file"]
        fr = feet[f]
        tail = (tails / (f + ".tail")).read_bytes()
        if hashlib.sha256(tail).hexdigest() != fr["tail_sha256"]:
            say(f"PROBLEM: {f}: the tail is not the footer record")
            return 1
        d = v / "parquet" / f
        with open(d, "wb") as o:
            o.write(b"PAR1")
            o.truncate(fr["size"] - len(tail))
            o.seek(fr["size"] - len(tail))
            o.write(tail)
        n += 1
    say(f"view: {sum(1 for _ in v.rglob('*') if _.is_file()):,} files ({n:,} sparse stand-ins)")
    return 0


# ---------------------------------------------------------------------------------------------------- tables --
def cmd_tables(a) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq
    root = Path(a.root)
    org = root / "organizations"
    rows = read_tsv(a.licenses)
    cols = ["project", "license", "confidence", "evidence_kind", "version_choice", "source"]
    keep = [x.strip() for x in open(a.names) if x.strip()]
    have = [r["project"] for r in rows]
    if sorted(have) != sorted(keep) or len(set(have)) != len(have):
        say(f"PROBLEM: project_licenses has {len(have)} rows for {len(keep)} projects")
        return 1
    rows.sort(key=lambda r: r["project"])
    t = pa.table({c: pa.array([r[c] or None for r in rows] if c != "project" and c != "license"
                              else [r[c] for r in rows], type=pa.string()) for c in cols})
    dst = org / "project_licenses.parquet"
    if dst.exists():
        dst.unlink()
    pq.write_table(t, dst, compression="zstd")
    db = org / "dataset.duckdb"
    cwd = os.getcwd()
    os.chdir(root)
    try:
        con = duck(str(db), tmp=a.tmp)
        con.execute('CREATE OR REPLACE VIEW project_licenses AS SELECT * FROM "organizations/project_licenses.parquet"')
        n = con.execute("SELECT count(*), count(DISTINCT project) FROM project_licenses").fetchone()
        con.execute("CHECKPOINT")
        con.close()
    finally:
        os.chdir(cwd)
    if n != (len(rows), len(rows)):
        say(f"PROBLEM: the view project_licenses gives {n}")
        return 1
    ri_path = org / "release_info.parquet"
    ri = pq.read_table(ri_path)
    kv = dict(zip(ri.column("key").to_pylist(), ri.column("value").to_pylist()))
    for p in sorted(org.glob("*.parquet")):
        if p.name == "release_info.parquet":
            continue
        kv[f"{p.stem}_rows"] = str(pq.ParquetFile(p).metadata.num_rows)
        kv[f"{p.stem}_sha256"] = sha256(p)
    kv["dataset_db_sha256"] = sha256(db)
    kv["organization_database_version"] = a.org_db_version
    kv["organization_database_doi"] = a.org_db_doi
    if kv.get("organizations_version") != a.org_build_tag:
        say(f"PROBLEM: release_info organizations_version is {kv.get('organizations_version')}, not {a.org_build_tag}")
        return 1
    ri_path.unlink()
    pq.write_table(pa.table({"key": sorted(kv), "value": [kv[k] for k in sorted(kv)]}, schema=ri.schema), ri_path,
                   compression="zstd")
    say(f"tables: project_licenses {len(rows):,} rows; release_info {len(kv)} keys; dataset_db_sha256 "
        f"{kv['dataset_db_sha256'][:12]}")
    return 0


# ---------------------------------------------------------------------------------------------------- values --
def cmd_values(a) -> int:
    root = Path(a.root).resolve()
    man = read_tsv(root / "MANIFEST.tsv")
    sizes = json.loads(Path(a.sizes).read_text())
    lic = {r["project"]: r for r in read_tsv(a.licenses)}
    fills = read_tsv(a.fills)
    filevals = {r["project"]: r["license"] for r in read_tsv(a.filevals)}
    new = {r["project"] for r in read_tsv(a.new)}
    ob = sum(int(r["bytes"]) for r in man)
    v = {"projects": f"{len(man):,}", "parquet files": f"{len(man):,}", "parquet bytes": f"{ob:,}",
         "parquet GB": f"{ob / 1e9:.1f}", "rows": f"{sum(int(r['rows']) for r in man):,}", "date": a.date,
         "machine": a.machine,
         "root files": f"{sum(1 for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS') + 1:,}"}
    for k in T.SIZE_KEYS:
        v[f"size {k}"] = f"{sizes['size_rule_counts'].get(k, 0):,}"
    for k in ("S", "M", "L"):
        v[f"size_class {k}"] = f"{sizes['size_class_counts'].get(k, 0):,}"
    cwd = os.getcwd()
    os.chdir(root)
    try:
        con = duck(str(root / "organizations" / "dataset.duckdb"), tmp=a.tmp, read_only=True)
        for t in T.TABLES + ["project_languages", "project_labels", "project_licenses"]:
            n = con.execute(f"SELECT count(*) FROM read_parquet('organizations/{t}.parquet')").fetchone()[0]
            v["facts rows" if t == "project_facts" else f"{t} rows"] = f"{n:,}"
        for t in ("project_languages", "project_labels", "project_licenses"):
            v[f"{t} projects"] = f"{con.execute(f'SELECT count(DISTINCT project) FROM {t}').fetchone()[0]:,}"
        v["facts projects"] = f"{con.execute('SELECT count(DISTINCT project) FROM project_facts').fetchone()[0]:,}"
        v["roster_language facts"] = (f"{con.execute('SELECT count(*) FROM project_facts WHERE fact_type = ?', ['roster_language']).fetchone()[0]:,}")
        for view in ("project_hosts", "project_sponsors"):
            n, d = con.execute(f"SELECT count(*), count(DISTINCT project) FROM {view}").fetchone()
            v[f"{view} rows"], v[f"{view} projects"] = f"{n:,}", f"{d:,}"
        con.close()
    finally:
        os.chdir(cwd)
    v["added projects"] = f"{len(new):,}"
    v["license values"] = f"{sum(r['license'] != 'NOASSERTION' for r in lic.values()):,}"
    v["license noassertion"] = f"{sum(r['license'] == 'NOASSERTION' for r in lic.values()):,}"
    v["license new values"] = f"{sum(1 for p, r in lic.items() if r['license'] != 'NOASSERTION' and filevals.get(p) == 'NOASSERTION'):,}"
    v["license changed files"] = f"{len(fills):,}"
    missing = sorted(set(T.KNOWN_KEYS) - set(v))
    if missing:
        say(f"PROBLEM: no value for {missing}")
        return 1
    Path(a.out).write_text(json.dumps(v, indent=1, sort_keys=True))
    say("values: " + "; ".join(f"{k} = {v[k]}" for k in sorted(v)))
    return 0


# ------------------------------------------------------------------------------------------------ check-root --
def cmd_check_root(a) -> int:
    import pyarrow.parquet as pq
    root, view = Path(a.root), Path(a.view)
    probs = []
    plan = {r["file"]: r for r in T2.read_plan(a.plan)}
    base_feet = T2.read_footers(a.footers)
    led = T.read_ledger(a.ledger)
    sums = read_sums(root / "SHA256SUMS")
    lic = {r["project"]: r["license"] for r in read_tsv(a.licenses)}
    fills = {r["project"]: r for r in read_tsv(a.fills)}
    names = sorted(os.listdir(view / "parquet"))
    if names != sorted(plan):
        probs.append(f"parquet/ has {len(names)} files for {len(plan)} plan rows")
    if len(names) != a.expect_files or len(names) >= a.max:
        probs.append(f"parquet/ has {len(names)} files; expected {a.expect_files}, limit {a.max}")
    feet = T2.view_footers(view, a.jobs)
    ref = base_feet[a.ref]
    rows = 0
    for f in names:
        r, b = feet.get(f), base_feet.get(f)
        if r is None or b is None:
            probs.append(f"{f}: no footer")
            continue
        rows += r["rows"]
        if r["schema"] != ref["schema"] or r["columns"] != a.want_columns:
            probs.append(f"{f}: the schema is not the TOM schema")
        if sorted(r["kv"]) != sorted(ref["kv"]):
            probs.append(f"{f}: the footer key set is not the TOM key set")
        same_kv = {k: v for k, v in r["kv"].items() if not k.startswith("pseudonymization_")}
        if same_kv != {k: v for k, v in ref["kv"].items() if not k.startswith("pseudonymization_")}:
            probs.append(f"{f}: a footer value (outside the pseudonymization keys) differs from the TOM files")
        if r["kv"] != b["kv"] or r["rows"] != b["rows"] or r["row_groups"] != b["row_groups"]:
            probs.append(f"{f}: the footer key-values, rows or row groups differ from the input file")
        p = project_of(f)
        want = lic.get(p)
        if want is None or not T2.stats_hold(r["stats"].get("license", []), want):
            probs.append(f"{f}: the license statistics do not hold the column value {want!r}")
        k = plan[f]["kind"]
        if k == "unchanged":
            if r["tail_sha256"] != b["tail_sha256"] or sums.get(f"parquet/{f}") is None:
                probs.append(f"{f}: unchanged, but the footer or the SHA256SUMS row differs")
            if p in fills:
                probs.append(f"{f}: unchanged, but it has a fill")
        else:
            L = led.get(f)
            if not L or L.get("status") != "OK" or sums.get(f"parquet/{f}") != L.get("out_sha256"):
                probs.append(f"{f}: changed, but no OK ledger line with its SHA256SUMS row")
            if p not in fills:
                probs.append(f"{f}: changed, but no fill")
    if a.expect_rows is not None and rows != a.expect_rows:
        probs.append(f"{rows:,} token rows, expected {a.expect_rows:,}")
    vfiles = {str(p.relative_to(view)) for p in view.rglob("*") if p.is_file()}
    if vfiles != set(sums) | {"SHA256SUMS"}:
        probs.append(f"the view files are not the SHA256SUMS rows: {sorted(vfiles ^ (set(sums) | {'SHA256SUMS'}))[:5]}")
    man = read_tsv(root / "MANIFEST.tsv")
    if len(man) != len(names) or any(sums.get(r["path"]) != r["sha256"] for r in man):
        probs.append("MANIFEST.tsv: a row is not its SHA256SUMS row, or the row count differs")
    for r in man:
        fr = feet.get(Path(r["path"]).name)
        if fr and (int(r["bytes"]) != fr["size"] or int(r["rows"]) != fr["rows"]):
            probs.append(f"{r['path']}: the MANIFEST.tsv bytes or rows are not the file")
    keep = {project_of(f) for f in names}
    cwd = os.getcwd()
    os.chdir(view)
    try:
        con = duck(str(root / "organizations" / "dataset.duckdb"), tmp=a.tmp, read_only=True)
        views = [x[0] for x in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()]
        for vw in sorted(set(a.need_views.split()) - set(views)):
            probs.append(f"no view {vw}")
        for vw in views:
            if vw.startswith("tokens"):
                continue
            try:
                con.execute(f"SELECT count(*) FROM {vw}").fetchone()
            except Exception as e:  # noqa: BLE001
                probs.append(f"the view {vw} does not query: {str(e)[:120]}")
        for t in ("project_organizations", "project_languages", "project_labels", "project_licenses"):
            have = {x[0] for x in con.execute(f"SELECT DISTINCT project FROM {t}").fetchall()}
            if have != keep:
                probs.append(f"{t}: {len(have ^ keep)} projects differ from the project files")
        kv = dict(con.execute("SELECT key, value FROM release_info").fetchall())
        con.close()
    finally:
        os.chdir(cwd)
    for p in sorted((root / "organizations").glob("*.parquet")):
        if p.name == "release_info.parquet":
            continue
        if kv.get(f"{p.stem}_rows") != str(pq.ParquetFile(p).metadata.num_rows) or kv.get(f"{p.stem}_sha256") != sha256(p):
            probs.append(f"release_info: the rows or sha256 of {p.name} are not the file")
    if kv.get("dataset_db_sha256") != sha256(root / "organizations" / "dataset.duckdb"):
        probs.append("release_info: dataset_db_sha256 is not the file")
    for k, want in (("organization_database_version", a.org_db_version), ("organization_database_doi", a.org_db_doi),
                    ("organizations_version", a.org_build_tag)):
        if kv.get(k) != want:
            probs.append(f"release_info: {k} is {kv.get(k)!r}, not {want!r}")
    if ref["kv"].get("organizations_version") != a.org_build_tag:
        probs.append(f"the footer key organizations_version is not {a.org_build_tag}")
    if kv.get("ctp_schema_version") != ref["kv"].get("ctp_schema_version"):
        probs.append("release_info: ctp_schema_version is not the footer value")
    lp = set(pq.read_table(root / "ledgers.parquet", columns=["project"]).column(0).to_pylist())
    if not keep <= lp:
        probs.append(f"ledgers.parquet: no rows for {len(keep - lp)} projects")
    left = T.marks_left(root)
    if left and not a.allow_doi:
        probs.append(f"marker words or placeholders left: {left[:5]}")
    rep = {"files": len(names), "rows": rows, "problems": probs[:200], "views": len(views)}
    Path(a.out).write_text(json.dumps(rep, indent=1))
    for x in probs[:30]:
        say("PROBLEM: " + x)
    say(f"check-root: {len(names):,} files, {rows:,} rows, {len(views)} views; problems {len(probs)}")
    return 1 if probs else 0


# --------------------------------------------------------------------------------------------------- hf-push --
def cmd_hf_push(a) -> int:
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi
    root = Path(a.root)
    sums = read_sums(root / "SHA256SUMS")
    sums["SHA256SUMS"] = sha256(root / "SHA256SUMS")
    adds = [x.strip() for x in open(a.adds) if x.strip()]
    for extra in a.extra_roots or []:
        r0, lst = extra.split("=", 1)
        for x in open(lst):
            if x.strip():
                adds.append(f"{r0}::{x.strip()}")
    paths = {}
    for x in adds:
        r0, rel = (x.split("::", 1) if "::" in x else (str(root), x))
        p = Path(r0) / rel
        if sha256(p) != sums.get(rel):
            raise SystemExit(f"ABORT: {rel} is not its SHA256SUMS row")
        paths[rel] = p
    last = [r for r in ("README.md", "SHA256SUMS") if r in paths or r == "SHA256SUMS"]
    paths["SHA256SUMS"] = root / "SHA256SUMS"
    data = [r for r in sorted(paths) if r not in last]
    api = HfApi()
    info = api.repo_info(a.repo, repo_type="dataset")
    vis = "private" if info.private else "public"
    if vis != a.expect:
        raise SystemExit(f"ABORT: the repository is {vis}, expected {a.expect}")
    gone = []
    if getattr(a, "delete_list", None):
        want_gone = [x.strip() for x in open(a.delete_list) if x.strip()]
        on_hub = set(api.list_repo_files(a.repo, repo_type="dataset"))
        gone = [x for x in want_gone if x in on_hub and x not in sums]
        say(f"hf-push: {len(gone)} stale files of the earlier revision are deleted in the first commit: {gone}")
    for i, group in enumerate((data, last), 1):
        if not group:
            continue
        ops = [CommitOperationAdd(path_in_repo=r, path_or_fileobj=str(paths[r])) for r in group]
        if i == 1:
            ops += [CommitOperationDelete(path_in_repo=r) for r in gone]
        t0 = time.time()
        api.create_commit(repo_id=a.repo, repo_type="dataset", operations=ops,
                          commit_message=f"{a.message} ({'data files' if i == 1 else 'card and SHA256SUMS'})")
        say(f"hf commit {i}: {len(ops)} files in {time.time() - t0:.0f} s")
    info = api.repo_info(a.repo, repo_type="dataset")
    if ("private" if info.private else "public") != a.expect:
        raise SystemExit("ABORT: the visibility changed")
    say(f"hf-push DONE: {len(data)} data files, then {last}; revision {info.sha}")
    return 0


EXTRA_KEYS = ["added projects", "license values", "license noassertion", "license new values", "license changed files",
              "project_languages rows", "project_languages projects", "project_labels rows", "project_labels projects",
              "project_licenses rows", "project_licenses projects", "roster_language facts"]


def cmd_keys(a) -> int:
    for k in list(T.KNOWN_KEYS) + EXTRA_KEYS:
        print(k)
    return 0


# ------------------------------------------------------------------------------------------------------ main --
# ------------------------------------------------------------------------------------------------- licmerge --
def cmd_licmerge(a) -> int:
    """project_licenses of the new root: the rows of the base table (unchanged) plus the rows of the new projects (the
    rule of the license pass, 70_values.py). A new project that has a row in the base is an error."""
    import pyarrow.parquet as pq
    cols = ["project", "license", "confidence", "evidence_kind", "version_choice", "source"]
    base = pq.read_table(a.base)
    if base.column_names != cols:
        say(f"PROBLEM: {a.base}: columns {base.column_names}")
        return 1
    rows = [{c: (r[c] if r[c] is not None else "") for c in cols} for r in base.to_pylist()]
    have = {r["project"] for r in rows}
    new = read_tsv(a.new)
    if a.expect_new is not None and len(new) != a.expect_new:
        say(f"PROBLEM: {len(new)} new license rows, expected {a.expect_new}")
        return 1
    dup = sorted(have & {r["project"] for r in new})
    if dup:
        say(f"PROBLEM: the base already has license rows of {dup[:5]}")
        return 1
    rows += [{c: r[c] for c in cols} for r in new]
    rows.sort(key=lambda r: r["project"])
    write_tsv(a.out, rows, cols)
    say(f"licmerge: {len(base)} base rows + {len(new)} new = {len(rows)}")
    return 0


# --------------------------------------------------------------------------------------------------- mapcheck --
def cmd_mapcheck(a) -> int:
    """organizations_mapping_sha256 in the footer of every project file is the mapping_sha256 of release_info."""
    import pyarrow.parquet as pq
    ri = pq.read_table(a.release_info)
    kv = dict(zip(ri.column("key").to_pylist(), ri.column("value").to_pylist()))
    want = kv.get("mapping_sha256")
    if not want:
        say("PROBLEM: release_info has no mapping_sha256")
        return 1
    feet = T2.read_footers(a.footers)
    bad = [f for f, r in feet.items() if r["kv"].get("organizations_mapping_sha256") != want]
    if bad or len(feet) != a.expect_files:
        say(f"PROBLEM: {len(bad)} of {len(feet)} footers (expected {a.expect_files}) lack mapping hash {want[:12]}: {bad[:3]}")
        return 1
    say(f"mapcheck: {len(feet)} footers carry the release_info mapping hash {want[:12]}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("newlist")
    for o in ("--new-projects", "--names", "--removed", "--tom4-manifest", "--out", "--out-manifest"):
        s.add_argument(o, required=True)
    s.add_argument("--run", action="append", required=True, metavar="MACHINE=DIR")
    s.add_argument("--expect", type=int)
    s = sub.add_parser("footfix")
    for o in ("--resolved", "--manifest", "--new-files", "--release-info", "--ref", "--rename-py", "--check-py",
              "--work", "--log"):
        s.add_argument(o, required=True)
    s.add_argument("--jobs", type=int, default=8)
    s = sub.add_parser("footers")
    for o in ("--manifest", "--new", "--out-dir", "--local-new"):
        s.add_argument(o, required=True)
    s.add_argument("--s3")
    s.add_argument("--local-tom4")
    s.add_argument("--jobs", type=int, default=16)
    s.add_argument("--first", type=int, default=262144)
    s = sub.add_parser("shape")
    s.add_argument("--ref", required=True)
    s.add_argument("--columns", type=int, default=53)
    s.add_argument("--list")
    s.add_argument("files", nargs="*")
    s = sub.add_parser("filevals")
    s.add_argument("--footers", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("lscan-list")
    s.add_argument("--manifest", required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("ledger-rows")
    for o in ("--manifest", "--resolved", "--schema-ref", "--out", "--file-mask-sha256"):
        s.add_argument(o, required=True)
    s.add_argument("--run", action="append", required=True)
    s = sub.add_parser("pseudo")
    for o in ("--tom4", "--footers", "--new", "--out"):
        s.add_argument(o, required=True)
    s = sub.add_parser("domains")
    for o in ("--tom4", "--errors"):
        s.add_argument(o, required=True)
    s.add_argument("--new-dirs", nargs="+", required=True)
    s = sub.add_parser("base")
    for o in ("--tom4", "--new", "--new-manifest", "--new-ledgers", "--pseudo", "--new-files", "--out"):
        s.add_argument(o, required=True)
    s.add_argument("--new-dirs", nargs="+", required=True)
    s.add_argument("--tom4-files")
    s = sub.add_parser("manifest")
    for o in ("--base-manifest", "--plan", "--ledger", "--out"):
        s.add_argument(o, required=True)
    s = sub.add_parser("sums")
    for o in ("--root", "--base-sums", "--plan", "--new", "--changed-out", "--gone-out", "--new-unchanged-out"):
        s.add_argument(o, required=True)
    s.add_argument("--jobs", type=int, default=8)
    s = sub.add_parser("view")
    for o in ("--root", "--tails", "--plan", "--out"):
        s.add_argument(o, required=True)
    s = sub.add_parser("tables")
    s.add_argument("--root", required=True)
    s.add_argument("--licenses", required=True)
    s.add_argument("--names", required=True)
    s.add_argument("--org-db-version", required=True)
    s.add_argument("--org-db-doi", required=True)
    s.add_argument("--org-build-tag", required=True)
    s.add_argument("--tmp")
    s = sub.add_parser("values")
    for o in ("--root", "--sizes", "--licenses", "--fills", "--filevals", "--new", "--date", "--machine", "--out"):
        s.add_argument(o, required=True)
    s.add_argument("--tmp")
    s = sub.add_parser("check-root")
    for o in ("--root", "--view", "--plan", "--footers", "--ledger", "--licenses", "--fills", "--ref", "--out"):
        s.add_argument(o, required=True)
    s.add_argument("--need-views", default="")
    s.add_argument("--want-columns", type=int, default=53)
    s.add_argument("--expect-files", type=int, required=True)
    s.add_argument("--expect-rows", type=int)
    s.add_argument("--max", type=int, default=10000)
    s.add_argument("--jobs", type=int, default=8)
    s.add_argument("--tmp")
    s.add_argument("--allow-doi", action="store_true")
    s.add_argument("--org-db-version", required=True)
    s.add_argument("--org-db-doi", required=True)
    s.add_argument("--org-build-tag", required=True)
    s = sub.add_parser("hf-push")
    for o in ("--repo", "--root", "--adds", "--message"):
        s.add_argument(o, required=True)
    s.add_argument("--extra-roots", nargs="*", metavar="ROOT=LIST")
    s.add_argument("--expect", choices=("public", "private"), default="public")
    s.add_argument("--delete-list", help="names of files to delete in the first commit when the Hub holds them and the root does not")
    sub.add_parser("keys")
    s = sub.add_parser("licmerge")
    s.add_argument("--base", required=True)
    s.add_argument("--new", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--expect-new", type=int)
    s = sub.add_parser("mapcheck")
    s.add_argument("--release-info", required=True)
    s.add_argument("--footers", required=True)
    s.add_argument("--expect-files", type=int, required=True)
    a = ap.parse_args(argv)
    return {"keys": cmd_keys, "newlist": cmd_newlist, "footfix": cmd_footfix, "footers": cmd_footers, "shape": cmd_shape, "filevals": cmd_filevals,
            "lscan-list": cmd_lscan_list, "ledger-rows": cmd_ledger_rows, "pseudo": cmd_pseudo, "domains": cmd_domains, "base": cmd_base,
            "manifest": cmd_manifest, "sums": cmd_sums, "view": cmd_view, "tables": cmd_tables, "values": cmd_values,
            "check-root": cmd_check_root, "hf-push": cmd_hf_push, "licmerge": cmd_licmerge, "mapcheck": cmd_mapcheck}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
