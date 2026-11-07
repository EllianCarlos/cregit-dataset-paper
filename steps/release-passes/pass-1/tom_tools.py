#!/usr/bin/env python3
"""The tools of the TOM release pass (kit dataset-tom). Subcommands:

  count      the files, footer rows and bytes of the kept files of a folder against the expected values.
  keep       resolve the project list against the source SHA256SUMS: one project per line (owner__repo, a file
             name or a file stem; a tab ends the name; # and empty lines are skipped), minus DROP_PROJECTS; refuses
             an unknown, ambiguous or repeated name and a list of MAX or more files.
  pass       the drop + rename pass, one process per file, largest first: the input sha256 against the source
             SHA256SUMS, the audit of the dropped columns (DuckDB: each must hold the value the review found, else
             the file fails), parquet_rename.py, parquet_rename_check.py (the proof), the output sha256; one ledger
             line per file (file, in_sha256, out_sha256, check). --only NAME runs one file (the canary). Resumes:
             a file with an OK line and an output of the logged size is skipped.
  facts      organizations/project_facts.parquet (project, fact_type, fact_value: one row per project and fact,
             from the fact values of the ledger; the round trip to the fact text is checked) and the view in
             organizations/dataset.duckdb.
  orgs       project_organizations.parquet with the rows of the kept projects only; release_info.parquet with the
             new rows and sha256 of project_organizations and project_facts (ORGS=subset).
  ledgers    ledgers.parquet with only the rows of the kept projects, and ledger.project.jsonl (the finished
             'project' records, tools as JSON objects) for fill_release.py manifest.
  sizes      the counts of the size rule (commits of the source MANIFEST.tsv) and of size_class.
  values     the measured values of the placeholders (the built root: parquet/, organizations/, the views).
  keys       the known placeholder keys.
  markers    fills the placeholders [[tom: KEY]] and TODO-DATE of the *.md, *.cff and *.lock files of the root
             (not *.before-*), logs each fill; then only TODO-DOI may be left.
  check-root the TOM checks of the built root (schema, footer, counts, MANIFEST.tsv, SHA256SUMS, ledger, facts,
             views, placeholders).
No output holds the at sign: each log and report line is masked before it is written.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

AT = chr(64)
SUFFIX = "-dataset.parquet"
PH = re.compile(r"\[\[tom: ([A-Za-z0-9 _-]+)\]\]")
PH_ANY = re.compile(r"\[\[(tom|reencode):")


def mask(text: str) -> str:
    return text.replace(AT, "(at)")


def jline(rec: dict) -> str:
    return mask(json.dumps(rec, sort_keys=True))


def utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(16 << 20)
            if not b:
                return h.hexdigest()
            h.update(b)


def read_sums(path: str | Path) -> dict[str, str]:
    out = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            digest, rel = line.split("  ", 1)
            out[rel] = digest
    return out


def project_of(file_name: str) -> str:
    if not file_name.endswith(SUFFIX):
        raise ValueError(f"not a project file: {file_name}")
    return file_name[: -len(SUFFIX)]


def read_keep(path: str | Path) -> list[tuple[str, str]]:
    """keep.resolved.tsv: project<TAB>file lines."""
    out = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            p, f = line.split("\t")
            out.append((p, f))
    return out


def conf_list(text: str) -> list[str]:
    return [x for x in text.split() if x]


# ----------------------------------------------------------------------------------------------------- keep --
def cmd_keep(a) -> int:
    sums = read_sums(a.sums)
    files = {Path(r).name for r in sums if r.startswith("parquet/") and r.endswith(SUFFIX)}
    projects = {project_of(f): f for f in files}
    drop = set(conf_list(a.drop))
    bad_drop = sorted(drop - set(projects))
    problems, seen, keep = [], {}, []
    for n, raw in enumerate(Path(a.list).read_text().splitlines(), 1):
        name = raw.split("\t")[0].strip()
        if not name or name.startswith("#"):
            continue
        cands = {name, name.replace("/", "__")}
        for c in list(cands):
            if c.endswith(".parquet"):
                cands.add(c[: -len(".parquet")])
        hits = set()
        for c in cands:
            if c in projects:
                hits.add(c)
            if c.endswith("-dataset") and c[: -len("-dataset")] in projects and c + ".parquet" in files:
                hits.add(c[: -len("-dataset")])
        if len(hits) != 1:
            problems.append(f"line {n}: {'no project' if not hits else 'ambiguous: ' + ' '.join(sorted(hits))} for {name!r}")
            continue
        p = hits.pop()
        if p in seen:
            problems.append(f"line {n}: {p} repeats line {seen[p]}")
            continue
        seen[p] = n
        keep.append(p)
    dropped = sorted(set(keep) & drop)
    keep = sorted(set(keep) - drop)
    print(f"list {a.list}: {len(seen)} projects ({len(problems)} problems); the drop list removes {len(dropped)} "
          f"({' '.join(dropped) or 'none'}); kept {len(keep)} of {len(projects)}")
    if bad_drop:
        print(f"note: drop names not in the source: {' '.join(bad_drop)}")
    for p in problems[:20]:
        print("PROBLEM:", mask(p))
    if problems:
        return 1
    if not keep:
        print("PROBLEM: no project is kept")
        return 1
    if len(keep) > a.max:
        print(f"PROBLEM: {len(keep)} files is more than {a.max} (the Hub limit of one folder)")
        return 1
    with open(a.out, "w") as f:
        for p in keep:
            f.write(f"{p}\t{projects[p]}\n")
    return 0


def cmd_count(a) -> int:
    """The files, the footer rows and the bytes of the kept files in a folder, against the expected values."""
    import pyarrow.parquet as pq
    keep = read_keep(a.keep)

    def one_footer(f):
        p = Path(a.dir) / f
        return os.path.getsize(p), pq.ParquetFile(p).metadata.num_rows

    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        got = list(ex.map(one_footer, [f for _, f in keep]))
    n, rows, nb = len(got), sum(r for _, r in got), sum(b for b, _ in got)
    probs = []
    for what, have, want in (("files", n, a.expect_files), ("rows", rows, a.expect_rows), ("bytes", nb, a.expect_bytes)):
        if want and have != want:
            probs.append(f"{what} {have:,} != expected {want:,}")
    print(f"count {a.dir}: {n:,} files, {rows:,} rows, {nb:,} B; {'; '.join(probs) or 'as expected'}")
    if a.out:
        Path(a.out).write_text(json.dumps({"files": n, "rows": rows, "bytes": nb, "problems": probs}, indent=1))
    return 1 if probs else 0


# ----------------------------------------------------------------------------------------------------- pass --
def run_child(argv: list[str], env: dict) -> tuple[int, str, str, float, int]:
    """Runs argv; returns (rc, stdout, stderr, wall seconds, peak RSS bytes of that child)."""
    import tempfile
    t = time.time()
    with tempfile.TemporaryFile() as fo, tempfile.TemporaryFile() as fe:
        p = subprocess.Popen(argv, stdout=fo, stderr=fe, env=env)
        _, status, ru = os.wait4(p.pid, 0)
        p.returncode = os.waitstatus_to_exitcode(status)
        fo.seek(0)
        fe.seek(0)
        return (p.returncode, fo.read().decode(errors="replace"), fe.read().decode(errors="replace"),
                time.time() - t, ru.ru_maxrss << 10)


def audit(src: str, project: str, cfg: dict, threads: int) -> tuple[list[str], dict]:
    """The dropped columns must hold the values the review found; returns (problems, values)."""
    import duckdb
    drops = cfg["drop_columns"]
    con = duckdb.connect()
    con.execute(f"SET threads={int(threads)}")
    cols = ", ".join(f'"{c}"' for c in drops + ["repo_name"])
    rows = con.execute(f"SELECT {cols}, count(*) FROM read_parquet(?) GROUP BY ALL", [src]).fetchall()
    con.close()
    problems, vals = [], {}
    if len(rows) != 1:
        problems.append(f"the dropped columns and repo_name hold {len(rows)} value combinations, not 1")
    for i, c in enumerate(drops + ["repo_name"]):
        v = sorted({r[i] for r in rows}, key=lambda x: (x is None, str(x)))
        vals[c] = v[0] if len(v) == 1 else v
    for c in cfg["expect_empty"]:
        if vals.get(c) != "":
            problems.append(f"{c} is not the empty string in every row")
    if vals.get("manifest_category") != cfg["expect_manifest_category"]:
        problems.append("manifest_category is not the expected value in every row")
    if vals.get("file_mask") != cfg["expect_file_mask"]:
        problems.append("file_mask is not the expected mask in every row")
    if vals.get("repo_name") != project:
        problems.append("repo_name is not the project of the file name")
    if not isinstance(vals.get("fact"), str):
        problems.append("fact is not one text value")
    return problems, {"fact": vals.get("fact"), "rows_audited": sum(r[-1] for r in rows)}


def one(job: dict) -> dict:
    src, dst, cfg = job["src"], job["dst"], job["cfg"]
    name = os.path.basename(src)
    rec = {"v": 1, "file": name, "project": project_of(name), "start_utc": utc(), "status": "ERROR",
           "problems": []}
    t0 = time.time()
    try:
        rec["in_bytes"] = os.path.getsize(src)
        rec["in_sha256"] = sha256(src)
        rec["want_in_sha256"] = job["want"]
        if rec["in_sha256"] != job["want"]:
            rec["problems"].append("the input sha256 is not the source SHA256SUMS row")
            return rec
        ta = time.time()
        aprob, avals = audit(src, rec["project"], cfg, cfg["threads"])
        rec["audit"] = avals
        rec["audit_s"] = round(time.time() - ta, 2)
        if aprob:
            rec["problems"] += aprob
            return rec
        part = dst + ".part"
        if os.path.exists(part):
            os.remove(part)
        env = dict(os.environ, OMP_NUM_THREADS=str(cfg["threads"]), PYTHONDONTWRITEBYTECODE="1")
        maps = [x for c in cfg["drop_columns"] for x in ("--drop", c)] + \
               [x for r in cfg["rename"] for x in ("--rename", r)] + \
               [x for kv in cfg["set_kv"] for x in ("--set-kv", kv)]
        rc, out, err, dt, rss0 = run_child([cfg["py"], "-I", "-B", cfg["rename_py"], src, part, *maps,
                                         "--copy", cfg["copy_mode"]], env)
        rec["rename_s"] = round(dt, 2)
        rec["rename_rc"] = rc
        try:
            rr = json.loads(out.strip().splitlines()[-1])
            rec["rename"] = {k: rr.get(k) for k in ("dropped", "renamed", "kv_set", "column_chunks_renamed", "arrow_schema",
                                                     "mentions_kept", "in_size", "out_size", "copy") if k in rr}
        except Exception:
            rec["rename"] = None
        if rc != 0:
            rec["problems"].append(f"parquet_rename.py rc {rc}: {err.strip().splitlines()[-1][:300] if err.strip() else ''}")
            return rec
        rc, out, err, dt, rss = run_child([cfg["py"], "-I", "-B", cfg["check_py"], *maps, src, part], env)
        rec["check_s"] = round(dt, 2)
        rec["check_rc"] = rc
        rep = {}
        try:
            rep = json.loads(out.strip().splitlines()[-1])
        except Exception:
            pass
        if job.get("check_dir"):
            Path(job["check_dir"], rec["project"] + ".json").write_text(mask(out))
        rec["check"] = {"ok": rep.get("ok"), "problems": rep.get("problems"), "kv_set": rep.get("kv_set"),
                        "column_chunks_identical": rep.get("column_chunks_identical"),
                        "page_index_pages": rep.get("page_index_pages"), "row_groups": rep.get("row_groups"),
                        "rows": rep.get("rows"), "report_sha256": hashlib.sha256(out.encode()).hexdigest()}
        if rc != 0 or rep.get("ok") is not True:
            rec["problems"].append(f"parquet_rename_check.py rc {rc}, ok {rep.get('ok')}: "
                                   f"{str(rep.get('problems'))[:300]} {err.strip()[-300:]}")
            return rec
        os.replace(part, dst)
        rec["out_bytes"] = os.path.getsize(dst)
        rec["out_sha256"] = sha256(dst)
        rec["rows"] = rep.get("rows")
        rec["peak_rss_bytes"] = max(rss, rss0)
        rec["status"] = "OK"
    except Exception as e:  # the file fails, the driver goes on
        rec["problems"].append(f"{type(e).__name__}: {str(e)[:400]}")
    finally:
        rec["total_s"] = round(time.time() - t0, 2)
        rec["end_utc"] = utc()
    return rec


def read_ledger(path: str | Path) -> dict[str, dict]:
    last = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                last[r["file"]] = r
    return last


def cmd_pass(a) -> int:
    conf = dict(drop_columns=conf_list(a.drop_columns), rename=conf_list(a.rename), set_kv=conf_list(a.set_kv),
                expect_empty=conf_list(a.expect_empty), expect_manifest_category=a.expect_manifest_category,
                expect_file_mask=a.expect_file_mask, py=sys.executable, rename_py=a.rename_py,
                check_py=a.check_py, copy_mode=a.copy_mode, threads=a.threads)
    sums = read_sums(a.sums)
    keep = read_keep(a.keep)
    if a.only:
        keep = [(p, f) for p, f in keep if p == a.only]
        if not keep:
            print(f"ABORT: {a.only} is not kept")
            return 2
    os.makedirs(a.dst, exist_ok=True)
    if a.check_dir:
        os.makedirs(a.check_dir, exist_ok=True)
    done = read_ledger(a.ledger)
    todo, skipped = [], 0
    for p, f in keep:
        r = done.get(f)
        d = os.path.join(a.dst, f)
        if r and r.get("status") == "OK" and os.path.exists(d) and os.path.getsize(d) == r.get("out_bytes"):
            skipped += 1
            continue
        s = os.path.join(a.src, f)
        if not os.path.exists(s):
            print(f"ABORT: no input {s}")
            return 2
        todo.append({"src": s, "dst": d, "want": sums.get(f"parquet/{f}"), "cfg": conf, "check_dir": a.check_dir})
    todo.sort(key=lambda j: -os.path.getsize(j["src"]))
    todo_bytes = sum(os.path.getsize(j["src"]) for j in todo)
    print(f"pass: {len(todo)} files to do ({todo_bytes} B), {skipped} done before; jobs {a.jobs}, threads {a.threads}",
          flush=True)
    t0 = time.time()
    counts, done_bytes, failures, running, stopped = {}, 0, [], {}, False
    last_progress = 0.0

    def progress(final=False):
        if not a.progress:
            return
        now = time.time()
        Path(a.progress + ".tmp").write_text(json.dumps({
            "utc": utc(), "todo": len(todo), "finished": sum(counts.values()), "counts": counts,
            "skipped": skipped, "todo_in_bytes": todo_bytes, "done_in_bytes": done_bytes,
            "elapsed_s": round(now - t0, 1), "final": final, "stopped": stopped,
            "running": [{"file": j["src"].rsplit("/", 1)[-1], "in_bytes": os.path.getsize(j["src"]),
                         "elapsed_s": round(now - st, 1)} for j, st in running.values()]}, indent=1))
        os.replace(a.progress + ".tmp", a.progress)

    with open(a.ledger, "a") as led, cf.ProcessPoolExecutor(max_workers=a.jobs) as pool:
        queue = list(todo)
        while queue or running:
            if a.stop_file and os.path.exists(a.stop_file) and queue:
                stopped = True
                queue = []
            while queue and len(running) < a.jobs:
                j = queue.pop(0)
                running[pool.submit(one, j)] = (j, time.time())
            if not running:
                break
            fin, _ = cf.wait(list(running), timeout=30, return_when=cf.FIRST_COMPLETED)
            for fu in fin:
                j, _ = running.pop(fu)
                try:
                    rec = fu.result()
                except Exception as e:
                    rec = {"v": 1, "file": os.path.basename(j["src"]), "status": "ERROR",
                           "problems": [f"worker: {type(e).__name__}: {str(e)[:300]}"], "end_utc": utc()}
                led.write(jline(rec) + "\n")
                led.flush()
                os.fsync(led.fileno())
                counts[rec["status"]] = counts.get(rec["status"], 0) + 1
                done_bytes += os.path.getsize(j["src"])
                if rec["status"] != "OK":
                    failures.append(rec["file"])
                    print(mask(f"FAIL {rec['file']}: {'; '.join(rec.get('problems', []))[:600]}"), flush=True)
            if time.time() - last_progress > 30:
                progress()
                last_progress = time.time()
    progress(final=True)
    wall = time.time() - t0
    print(f"pass summary: {sum(counts.values())} files {counts}, skipped {skipped}, failures {len(failures)}"
          f"{' first ' + ' '.join(failures[:5]) if failures else ''}; wall {wall:.0f} s{'; STOPPED' if stopped else ''}",
          flush=True)
    if failures:
        return 1
    return 3 if stopped else 0


# ---------------------------------------------------------------------------------------------------- facts --
def split_fact(text: str) -> list[tuple[str, str | None]]:
    out = []
    for item in text.split(";"):
        if item == "":
            continue
        t, sep, v = item.partition(":")
        out.append((t, v if sep else None))
    return out


def join_fact(items: list[tuple[str, str | None]]) -> str:
    return ";".join(t if v is None else f"{t}:{v}" for t, v in items)


def cmd_facts(a) -> int:
    import duckdb
    import pyarrow as pa
    import pyarrow.parquet as pq
    keep = read_keep(a.keep)
    led = read_ledger(a.ledger)
    proj, typ, val, bad, nofact = [], [], [], [], 0
    for p, f in keep:
        r = led.get(f)
        if not r or r.get("status") != "OK":
            bad.append(f"{p}: no OK ledger line")
            continue
        text = r["audit"]["fact"]
        items = split_fact(text)
        if join_fact(items) != text:
            bad.append(f"{p}: the fact text does not round trip")
        if not items:
            nofact += 1
        for t, v in items:
            proj.append(p)
            typ.append(t)
            val.append(v)
    if bad:
        for b in bad[:20]:
            print("PROBLEM:", mask(b))
        return 1
    tbl = pa.table({"project": pa.array(proj, pa.string()), "fact_type": pa.array(typ, pa.string()),
                    "fact_value": pa.array(val, pa.string())})
    out = Path(a.root) / a.facts_rel
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tbl, out, compression="zstd", compression_level=19, use_dictionary=True, write_statistics=True)
    back = pq.read_table(out)
    assert back.equals(tbl), "project_facts does not read back"
    types = {}
    for t in typ:
        types[t] = types.get(t, 0) + 1
    print(f"{a.facts_rel}: {tbl.num_rows} rows, {len(set(proj))} projects with a fact, {nofact} without; "
          f"types {json.dumps(dict(sorted(types.items())))}; no value {sum(v is None for v in val)}")
    # the view in dataset.duckdb (relative path from the root, as the other views)
    db = Path(a.root).resolve() / a.db_rel
    report = Path(a.report).resolve()
    os.chdir(a.root)  # the views read relative paths from the root
    con = duckdb.connect(str(db))
    old = {r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
    if a.view in old:
        print(f"PROBLEM: {a.db_rel} already has a view {a.view}")
        return 1
    rel = a.facts_rel.replace('"', '""')
    con.execute(f'CREATE VIEW {a.view} AS SELECT * FROM "{rel}"')
    con.execute("CHECKPOINT")
    con.close()
    report.write_text(json.dumps({"rows": tbl.num_rows, "projects_with_fact": len(set(proj)),
                                          "projects_without_fact": nofact, "types": types,
                                          "views_before": sorted(old)}, indent=1))
    print(f"{a.db_rel}: view {a.view} added ({len(old)} views before)")
    return 0


# ----------------------------------------------------------------------------------------------------- orgs --
def cmd_orgs(a) -> int:
    """project_organizations.parquet with the rows of the kept projects only, and release_info.parquet with the
    rows and sha256 of that table and of project_facts.parquet (DuckDB writes both, ZSTD, as the source tables)."""
    import duckdb
    org = Path(a.root) / "organizations"
    keep = sorted(p for p, _ in read_keep(a.keep))
    con = duckdb.connect()
    con.execute("CREATE TABLE k(project VARCHAR)")
    con.executemany("INSERT INTO k VALUES (?)", [(p,) for p in keep])
    src_po = str(Path(a.src_root) / "organizations" / "project_organizations.parquet")
    n_all = con.execute("SELECT count(*) FROM read_parquet(?)", [src_po]).fetchone()[0]
    miss = con.execute("SELECT count(*) FROM k WHERE project NOT IN (SELECT project FROM read_parquet(?))", [src_po]).fetchone()[0]
    if miss:
        print(f"PROBLEM: {miss} kept projects have no row in project_organizations.parquet")
        return 1
    po = org / "project_organizations.parquet"
    tmp = str(po) + ".tmp"
    con.execute(f"COPY (SELECT p.* FROM read_parquet(?) p SEMI JOIN k USING (project) ORDER BY p.project, p.host, "
                f"p.namespace) TO '{tmp}' (FORMAT parquet, COMPRESSION zstd)", [src_po])
    os.replace(tmp, po)
    n_po = con.execute("SELECT count(*) FROM read_parquet(?)", [str(po)]).fetchone()[0]
    d_po = con.execute("SELECT count(DISTINCT project) FROM read_parquet(?)", [str(po)]).fetchone()[0]
    if d_po != len(keep):
        print(f"PROBLEM: project_organizations.parquet has {d_po} projects, not {len(keep)}")
        return 1
    same = con.execute("SELECT count(*) FROM (SELECT * FROM read_parquet(?) SEMI JOIN k USING (project) EXCEPT ALL "
                       "SELECT * FROM read_parquet(?))", [src_po, str(po)]).fetchone()[0]
    if same:
        print(f"PROBLEM: {same} kept rows of project_organizations differ from the source")
        return 1
    facts = org / Path(a.facts_rel).name
    n_f = con.execute("SELECT count(*) FROM read_parquet(?)", [str(facts)]).fetchone()[0]
    src_ri = str(Path(a.src_root) / "organizations" / "release_info.parquet")
    info = dict(con.execute("SELECT key, value FROM read_parquet(?)", [src_ri]).fetchall())
    old = dict(info)
    info["project_organizations_rows"] = str(n_po)
    info["project_organizations_sha256"] = sha256(po)
    info["project_facts_rows"] = str(n_f)
    info["project_facts_sha256"] = sha256(facts)
    con.execute("CREATE TABLE ri(key VARCHAR, value VARCHAR)")
    con.executemany("INSERT INTO ri VALUES (?, ?)", sorted(info.items()))
    ri = org / "release_info.parquet"
    con.execute(f"COPY (SELECT * FROM ri ORDER BY key) TO '{str(ri) + '.tmp'}' (FORMAT parquet, COMPRESSION zstd)")
    os.replace(str(ri) + ".tmp", ri)
    con.close()
    changed = sorted(k for k in info if old.get(k) != info[k])
    print(f"project_organizations.parquet: {n_po} of {n_all} rows ({d_po} projects); release_info.parquet: "
          f"{len(info)} keys, changed or new: {' '.join(changed)}")
    return 0


# -------------------------------------------------------------------------------------------------- ledgers --
def cmd_ledgers(a) -> int:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    keep = {p for p, _ in read_keep(a.keep)}
    t = pq.read_table(a.src)
    have = set(t.column("project").to_pylist())
    miss = sorted(keep - have)
    if miss:
        print(f"PROBLEM: {len(miss)} kept projects have no ledger row, first {miss[:5]}")
        return 1
    sub = t.filter(pc.is_in(t.column("project"), value_set=pa.array(sorted(keep))))
    if a.mode == "subset":
        pf = pq.ParquetFile(a.src)
        comp = pf.metadata.row_group(0).column(0).compression.lower() if pf.metadata.num_row_groups else "zstd"
        pq.write_table(sub, a.out, compression=comp if comp in ("zstd", "snappy", "gzip") else "zstd")
        back = pq.read_table(a.out)
        assert back.schema.equals(t.schema) and back.num_rows == sub.num_rows, "ledgers.parquet does not read back"
        print(f"ledgers.parquet: {sub.num_rows} of {t.num_rows} rows ({len(keep)} of {len(have)} projects), "
              f"compression {comp}")
    else:
        import shutil
        shutil.copyfile(a.src, a.out)
        print(f"ledgers.parquet: copied ({t.num_rows} rows, {len(have)} projects)")
    n = 0
    with open(a.jsonl, "w") as f:
        for r in sub.to_pylist():
            if r.get("step") != "project" or r.get("status") != "done":
                continue
            for k in ("tools", "flags", "extra", "manifest_row"):
                if isinstance(r.get(k), str) and r[k][:1] in "{[":
                    try:
                        r[k] = json.loads(r[k])
                    except json.JSONDecodeError:
                        pass
            f.write(jline(r) + "\n")
            n += 1
    print(f"{a.jsonl}: {n} finished project records")
    return 0


# ---------------------------------------------------------------------------------------------------- sizes --
def cmd_sizes(a) -> int:
    keep = {p for p, _ in read_keep(a.keep)}
    rule = []
    for item in conf_list(a.rule):
        k, lo, hi = item.split(":")
        rule.append((k, int(lo), None if hi == "-" else int(hi)))
    counts = {k: 0 for k, _, _ in rule}
    old = {}
    with open(a.manifest) as f:
        rows = [r for r in csv.DictReader(f, delimiter="\t") if r["project"] in keep]
    for r in rows:
        c = int(r["commits"])
        hit = [k for k, lo, hi in rule if c >= lo and (hi is None or c <= hi)]
        if len(hit) != 1:
            print(f"PROBLEM: {r['project']} commits {c} is in {len(hit)} classes")
            return 1
        counts[hit[0]] += 1
        old[r["size_class"]] = old.get(r["size_class"], 0) + 1
    if len(rows) != len(keep):
        print(f"PROBLEM: the source MANIFEST.tsv has {len(rows)} of {len(keep)} kept projects")
        return 1
    rep = {"projects": len(rows), "rule": a.rule, "size_rule_counts": counts, "size_class_counts": dict(sorted(old.items())),
           "commits_min": min(int(r["commits"]) for r in rows), "commits_max": max(int(r["commits"]) for r in rows)}
    Path(a.out).write_text(json.dumps(rep, indent=1))
    print(f"size rule on {len(rows)} projects: {counts}; size_class {rep['size_class_counts']}")
    return 0


# -------------------------------------------------------------------------------------------------- markers --
# The placeholders that only the pass can fill: [[tom: KEY]] with one of these keys, and the literal TODO-DATE (the
# UTC date of the root build). TODO-DOI stays (the user makes the DOI later); any other marker word left fails.
MARK = "TO" + "DO"
DATE_MARK = MARK + "-DATE"
DOI_MARK = MARK + "-DOI"
SIZE_KEYS = ["SS", "S", "M", "L", "XL", "XXL"]
TABLES = ["organizations", "organization_domains", "organization_namespaces", "project_organizations", "project_facts",
          "link_error", "release_info"]
KNOWN_KEYS = (["projects", "parquet files", "parquet bytes", "parquet GB", "rows", "date", "machine", "root files",
               "facts rows", "facts projects", "project_hosts rows", "project_hosts projects", "project_sponsors rows",
               "project_sponsors projects"] + [f"{t} rows" for t in TABLES if t != "project_facts"]
              + [f"size {k}" for k in SIZE_KEYS] + [f"size_class {k}" for k in ("S", "M", "L")])


def text_files(root: Path) -> list[Path]:
    """The documents: *.md, *.cff and *.lock files outside parquet/ and organizations/ (not *.before-*)."""
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and rel.parts[0] not in ("parquet", "organizations") and p.suffix in (".md", ".cff", ".lock") \
                and ".before-" not in p.name:
            out.append(p)
    return out


def marks_left(root: Path) -> list[str]:
    """Lines of the text files (the suffixes of fill_release.py check) with a marker word other than TODO-DOI,
    or a placeholder."""
    out = []
    suffixes = {".md", ".cff", ".tsv", ".txt", ".lock", ".py", ".json", ".sh"}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if not p.is_file() or rel.parts[0] == "parquet" or (p.suffix not in suffixes and p.name != "SHA256SUMS"):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if MARK in line.replace(DOI_MARK, "") or PH_ANY.search(line):
                out.append(f"{rel}:{i}")
    return out


def cmd_keys(a) -> int:
    print("\n".join(KNOWN_KEYS))
    return 0


def cmd_markers(a) -> int:
    vals = {k: str(v) for k, v in json.loads(Path(a.values).read_text()).items()}
    root = Path(a.root)
    unknown, fills = set(), []
    new_text = {}
    for p in text_files(root):
        rel = str(p.relative_to(root))
        lines = p.read_text(encoding="utf-8").split("\n")
        changed = False
        for i, line in enumerate(lines):
            for k in PH.findall(line):
                if k in vals:
                    fills.append(f"{rel}:{i + 1}: [[tom: {k}]] -> {vals[k]}")
                else:
                    unknown.add(k)
            n_date = line.count(DATE_MARK)
            if n_date:
                fills.append(f"{rel}:{i + 1}: {DATE_MARK} -> {vals['date']}" + (f" ({n_date} times)" if n_date > 1 else ""))
            new = PH.sub(lambda m: vals.get(m.group(1), m.group(0)), line).replace(DATE_MARK, vals["date"])
            if new != line:
                lines[i] = new
                changed = True
        if changed:
            new_text[p] = "\n".join(lines)
    for f in fills:
        print("FILL", mask(f))
    if unknown:
        print(f"PROBLEM: unknown placeholder keys: {sorted(unknown)} (known: {KNOWN_KEYS})")
        return 1
    if a.apply:
        for p, t in new_text.items():
            p.write_text(t, encoding="utf-8")
    left = [x for x in marks_left(root) if a.apply]
    if left:
        print(f"PROBLEM: marker words or placeholders left (only {DOI_MARK} may stay): {left[:20]}")
        return 1
    print(f"markers: {len(fills)} fills in {len(new_text)} files {'written' if a.apply else '(dry run)'}; "
          f"{DOI_MARK} lines left: {sum(1 for p in text_files(root) for l in p.read_text().splitlines() if DOI_MARK in l)}")
    return 0


def cmd_values(a) -> int:
    import duckdb
    led = read_ledger(a.ledger)
    keep = read_keep(a.keep)
    ok = [led[f] for _, f in keep if f in led and led[f].get("status") == "OK"]
    if len(ok) != len(keep):
        print(f"PROBLEM: {len(ok)} OK ledger lines for {len(keep)} kept files")
        return 1
    sizes = json.loads(Path(a.sizes).read_text())
    root = Path(a.root).resolve()
    ob = sum(os.path.getsize(root / "parquet" / r["file"]) for r in ok)
    if ob != sum(r["out_bytes"] for r in ok):
        print("PROBLEM: the output sizes are not the ledger out_bytes")
        return 1
    rows = sum(r["rows"] for r in ok)
    v = {"projects": f"{len(ok):,}", "parquet files": f"{len(ok):,}", "parquet bytes": f"{ob:,}",
         "parquet GB": f"{ob / 1e9:.1f}", "rows": f"{rows:,}", "date": a.date, "machine": a.machine,
         "root files": f"{sum(1 for p in root.rglob('*') if p.is_file() and p.name != 'SHA256SUMS') + 1:,}"}
    for k in SIZE_KEYS:
        v[f"size {k}"] = f"{sizes['size_rule_counts'].get(k, 0):,}"
    for k in ("S", "M", "L"):
        v[f"size_class {k}"] = f"{sizes['size_class_counts'].get(k, 0):,}"
    cwd = os.getcwd()
    os.chdir(root)
    con = duckdb.connect(str(root / a.db_rel), read_only=True)
    for t in TABLES:
        n = con.execute(f"SELECT count(*) FROM read_parquet('organizations/{t}.parquet')").fetchone()[0]
        v["facts rows" if t == "project_facts" else f"{t} rows"] = f"{n:,}"
    v["facts projects"] = f"{con.execute('SELECT count(DISTINCT project) FROM project_facts').fetchone()[0]:,}"
    for view in ("project_hosts", "project_sponsors"):
        n, d = con.execute(f"SELECT count(*), count(DISTINCT project) FROM {view}").fetchone()
        v[f"{view} rows"], v[f"{view} projects"] = f"{n:,}", f"{d:,}"
    con.close()
    os.chdir(cwd)
    missing = sorted(set(KNOWN_KEYS) - set(v))
    if missing:
        print(f"PROBLEM: no value for {missing}")
        return 1
    Path(a.out).write_text(json.dumps(v, indent=1, sort_keys=True))
    print("values: " + "; ".join(f"{k} = {v[k]}" for k in KNOWN_KEYS))
    return 0


# ----------------------------------------------------------------------------------------------- check-root --
def expected_schema(src_file: str, drops: list[str], rename: dict[str, str]) -> list[tuple[str, str]]:
    import pyarrow.parquet as pq
    s = pq.read_schema(src_file)
    return [(rename.get(f.name, f.name), str(f.type)) for f in s if f.name not in drops]


def footer_of(path: str) -> tuple[list[tuple[str, str]], dict, int]:
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    kv = {k.decode(): v.decode(errors="replace") for k, v in (pf.metadata.metadata or {}).items()}
    return [(f.name, str(f.type)) for f in pf.schema_arrow], kv, pf.metadata.num_rows


def cmd_check_root(a) -> int:
    import duckdb
    root = Path(a.root)
    drops = conf_list(a.drop_columns)
    rename = dict(r.split("=", 1) for r in conf_list(a.rename))
    setkv = dict(r.split("=", 1) for r in conf_list(a.set_kv))
    keep = read_keep(a.keep)
    kfiles = {f for _, f in keep}
    led = read_ledger(a.ledger)
    probs: list[str] = []
    rep: dict = {}
    pq_files = sorted(p.name for p in (root / "parquet").iterdir())
    rep["parquet_entries"] = len(pq_files)
    if set(pq_files) != kfiles:
        probs.append(f"parquet/ has {len(pq_files)} entries; {len(set(pq_files) - kfiles)} not kept, "
                     f"{len(kfiles - set(pq_files))} kept files missing")
    if len(pq_files) > a.max:
        probs.append(f"parquet/ has {len(pq_files)} entries, the limit is {a.max}")
    for d in conf_list(a.drop_projects):
        if d + SUFFIX in pq_files:
            probs.append(f"the dropped project {d} is in parquet/")
    others = [str(p.relative_to(root)) for p in root.rglob("*" + SUFFIX) if p.parent != root / "parquet"]
    if others:
        probs.append(f"project files outside parquet/: {others[:3]}")
    # schema and footer of every file against its source file
    want = expected_schema(str(Path(a.src) / a.schema_from), drops, rename)
    rep["columns"] = len(want)
    if a.want_columns and len(want) != a.want_columns:
        probs.append(f"the TOM schema has {len(want)} columns, want {a.want_columns}")

    def chk(f):
        out = []
        got, kv, rows = footer_of(str(root / "parquet" / f))
        _, kv0, rows0 = footer_of(str(Path(a.src) / f))
        if got != want:
            out.append(f"{f}: the schema is not the TOM schema")
        want_kv = dict(kv0, **setkv)
        if kv != want_kv:
            diff = sorted(k for k in set(kv) | set(want_kv) if kv.get(k) != want_kv.get(k))
            out.append(f"{f}: the footer key-values are not the source ones with {setkv}: {diff}")
        if rows != rows0:
            out.append(f"{f}: rows {rows} != source {rows0}")
        r = led.get(f) or {}
        if r.get("status") != "OK" or r.get("rows") != rows:
            out.append(f"{f}: no OK ledger line with these rows")
        return f, rows, out

    total_rows = 0
    with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for f, rows, out in ex.map(chk, sorted(kfiles & set(pq_files))):
            total_rows += rows
            probs += out
    rep["rows"] = total_rows
    # SHA256SUMS and the ledger
    sums = read_sums(root / "SHA256SUMS")
    allf = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    if sorted(sums) != allf:
        probs.append(f"SHA256SUMS has {len(sums)} rows for {len(allf)} files (not the same set)")
    for f in kfiles:
        r = led.get(f) or {}
        if sums.get(f"parquet/{f}") != r.get("out_sha256"):
            probs.append(f"{f}: SHA256SUMS row is not the ledger out_sha256")
    # MANIFEST.tsv against the source MANIFEST.tsv
    with open(root / "MANIFEST.tsv") as fh:
        mrows = list(csv.DictReader(fh, delimiter="\t"))
        hdr = next(csv.reader(open(root / "MANIFEST.tsv"), delimiter="\t"))
    with open(Path(a.src_root) / "MANIFEST.tsv") as fh:
        srows = {r["project"]: r for r in csv.DictReader(fh, delimiter="\t")}
        shdr = next(csv.reader(open(Path(a.src_root) / "MANIFEST.tsv"), delimiter="\t"))
    want_hdr = [c for c in shdr if c != "layer"]
    if hdr != want_hdr:
        probs.append(f"MANIFEST.tsv header {hdr} is not the source header without layer")
    if "layer" in hdr:
        probs.append("MANIFEST.tsv has the layer column")
    if len(mrows) != len(kfiles):
        probs.append(f"MANIFEST.tsv has {len(mrows)} rows for {len(kfiles)} files")
    for r in mrows:
        s = srows.get(r["project"])
        f = r["project"] + SUFFIX
        if not s:
            probs.append(f"MANIFEST.tsv: {r['project']} is not in the source MANIFEST.tsv")
            continue
        for c in want_hdr:
            if c in ("bytes", "sha256"):
                continue
            if r[c] != s[c]:
                probs.append(f"MANIFEST.tsv: {r['project']} {c} {r[c]!r} != source {s[c]!r}")
        if r["sha256"] != sums.get(r["path"]) or r["path"] != f"parquet/{f}":
            probs.append(f"MANIFEST.tsv: {r['project']} sha256 or path is not SHA256SUMS")
        if str(os.path.getsize(root / r["path"])) != r["bytes"]:
            probs.append(f"MANIFEST.tsv: {r['project']} bytes is not the file size")
    # project_facts and the views
    con = duckdb.connect(str(root / a.db_rel), read_only=True)
    os.chdir(root)
    views = [r[0] for r in con.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal ORDER BY 1").fetchall()]
    rep["views"] = views
    for v in views:
        try:
            con.execute(f'SELECT * FROM "{v}" LIMIT 1').fetchall()
        except Exception as e:
            probs.append(f"view {v}: {type(e).__name__}: {str(e)[:200]}")
    if a.view not in views:
        probs.append(f"no view {a.view} in {a.db_rel}")
    else:
        n = con.execute(f'SELECT count(*), count(DISTINCT project) FROM "{a.view}"').fetchone()
        rep["facts"] = {"rows": n[0], "projects": n[1]}
        extra = con.execute(f'SELECT count(DISTINCT project) FROM "{a.view}" WHERE project NOT IN '
                            f'(SELECT * FROM (VALUES {",".join("(?)" for _ in keep)}))', [p for p, _ in keep]).fetchone()[0]
        if extra:
            probs.append(f"project_facts has {extra} projects that are not kept")
        nt = con.execute("SELECT count(*) FROM tokens").fetchone()[0]
        rep["tokens_view_rows"] = nt
        if nt != total_rows:
            probs.append(f"the tokens view has {nt} rows, the files {total_rows}")
    con.close()
    # ledgers.parquet
    if a.ledgers_mode == "subset":
        import pyarrow.parquet as pq
        lp = set(pq.read_table(root / "ledgers.parquet", columns=["project"]).column("project").to_pylist())
        if lp != {p for p, _ in keep}:
            probs.append(f"ledgers.parquet has {len(lp)} projects, not the {len(keep)} kept")
    # marker words (only TODO-DOI may stay) and placeholders
    left = marks_left(root)
    if left:
        probs.append(f"marker words or placeholders left: {left[:20]}")
    rep["problems"] = len(probs)
    Path(a.out).write_text(mask(json.dumps({"report": rep, "problems": probs[:500]}, indent=1)))
    for p in probs[:30]:
        print("PROBLEM:", mask(p))
    print(f"check-root: {len(kfiles)} files, {rep['columns']} columns, {total_rows} rows, views {len(views)}; "
          f"{len(probs)} problems")
    return 1 if probs else 0


# ----------------------------------------------------------------------------------------------------- main --
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("keep")
    s.add_argument("--list", required=True)
    s.add_argument("--sums", required=True)
    s.add_argument("--drop", default="")
    s.add_argument("--max", type=int, default=9999)
    s.add_argument("--out", required=True)
    s = sub.add_parser("count")
    s.add_argument("--dir", required=True)
    s.add_argument("--keep", required=True)
    s.add_argument("--expect-files", type=int, default=0)
    s.add_argument("--expect-rows", type=int, default=0)
    s.add_argument("--expect-bytes", type=int, default=0)
    s.add_argument("--jobs", type=int, default=16)
    s.add_argument("--out")
    s = sub.add_parser("pass")
    for k in ("src", "dst", "keep", "sums", "ledger", "rename-py", "check-py"):
        s.add_argument(f"--{k}", required=True)
    for k in ("drop-columns", "rename", "expect-empty", "expect-manifest-category", "expect-file-mask"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--set-kv", default="", help="KEY=VALUE items (space separated) for parquet_rename.py --set-kv")
    s.add_argument("--copy-mode", default="read-write")
    s.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    s.add_argument("--threads", type=int, default=2)
    s.add_argument("--only")
    s.add_argument("--progress")
    s.add_argument("--stop-file")
    s.add_argument("--check-dir")
    s = sub.add_parser("facts")
    for k in ("root", "keep", "ledger", "facts-rel", "db-rel", "view", "report"):
        s.add_argument(f"--{k}", required=True)
    s = sub.add_parser("orgs")
    for k in ("root", "src-root", "keep", "facts-rel"):
        s.add_argument(f"--{k}", required=True)
    s = sub.add_parser("ledgers")
    for k in ("src", "keep", "out", "jsonl"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--mode", choices=("subset", "copy"), default="subset")
    s = sub.add_parser("sizes")
    for k in ("manifest", "keep", "rule", "out"):
        s.add_argument(f"--{k}", required=True)
    s = sub.add_parser("values")
    for k in ("root", "ledger", "keep", "sizes", "db-rel", "date", "machine", "out"):
        s.add_argument(f"--{k}", required=True)
    s = sub.add_parser("keys")
    s = sub.add_parser("markers")
    s.add_argument("--root", required=True)
    s.add_argument("--values", required=True)
    s.add_argument("--apply", action="store_true")
    s = sub.add_parser("check-root")
    for k in ("root", "src", "src-root", "keep", "ledger", "schema-from", "drop-columns", "rename", "db-rel", "view",
              "out"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--drop-projects", default="")
    s.add_argument("--set-kv", default="")
    s.add_argument("--ledgers-mode", default="subset")
    s.add_argument("--max", type=int, default=9999)
    s.add_argument("--want-columns", type=int, default=0)
    s.add_argument("--jobs", type=int, default=8)
    a = ap.parse_args(argv)
    for k, v in list(vars(a).items()):
        setattr(a, k.replace("-", "_"), v)
    return {"keep": cmd_keep, "count": cmd_count, "pass": cmd_pass, "facts": cmd_facts, "orgs": cmd_orgs, "ledgers": cmd_ledgers, "sizes": cmd_sizes,
            "values": cmd_values, "keys": cmd_keys, "markers": cmd_markers, "check-root": cmd_check_root}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
