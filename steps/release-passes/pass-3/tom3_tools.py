#!/usr/bin/env python3
"""The tools of the third TOM release pass (kit dataset-tom-3). Subcommands:
  keep        the project files of the TOM-2 root: every parquet/ row of its SHA256SUMS, against its MANIFEST.tsv
              (sha256, bytes, project); writes keep.tsv (project, file, sha256, bytes), keep.pf.tsv and plan.tsv (the
              kit-2 plan form, kind "value" for every file: tom2_tools.py manifest and sums read it).
  prove       the proof of the drop, one process per file (DuckDB, full rows): the copy columns equal their source
              columns with the fixed text change (0 rows differ), cregit_commit_sha is one to one with
              original_commit_sha, repo_tag is empty, archived and fork hold only the allowed values, roster_lang has
              one value; one JSON line per file (log/proof.jsonl). No output holds a value of a person column.
  proof-sum   all proofs together: every file has an OK proof line, the rows, the files per archived and fork value
              and the roster_lang facts are the expected ones.
  pass        the drop, one process per file: input sha256 = the TOM-2 row, an OK proof line, parquet_rename.py
              --drop (chunk copy), parquet_rename_check.py, the output footer (53 columns, the input key-values, rows),
              the output sha256; one ledger line per file. --only-list runs the canary.
  facts       project_facts.parquet: the TOM-2 rows and one roster_language row per project with a roster_lang value.
  release-info  release_info.parquet: the TOM-2 keys; project_facts_rows and project_facts_sha256 measured again.
  values      the measured values of the placeholders.
  keys        the known placeholder keys.
  check-root  the checks of the new root (footers of all files against the TOM-2 footers, SHA256SUMS, MANIFEST.tsv,
              tables, every view of organizations/dataset.duckdb, release_info).
No output holds the at sign: each log and report line is masked before it is written.
"""
from __future__ import annotations
import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tom_tools as T  # noqa: E402  (the tools of the first pass, staged with their sha256)
import tom2_tools as T2  # noqa: E402  (the tools of the second pass, staged with their sha256)
mask, jline, utc, sha256, read_sums, project_of = T.mask, T.jline, T.utc, T.sha256, T.read_sums, T.project_of
SUFFIX = T.SUFFIX
NEW_KEYS = ["project_languages rows", "project_languages projects", "project_labels rows", "project_labels projects",
            "columns", "dropped columns", "changed files", "roster_language facts", "proved rows",
            "previous parquet bytes", "dropped bytes"]
KNOWN_KEYS = list(T.KNOWN_KEYS) + NEW_KEYS
# The drop columns and the source columns that the proof reads (with their Arrow types in the TOM-2 files).
PROOF_TYPES = {"person_name": "string", "person_email": "string", "footer_person_names": "list<element: string>",
               "cregit_commit_sha": "string", "repo_tag": "string", "archived": "string", "fork": "string",
               "roster_lang": "string", "personid": "string", "author_email": "string",
               "footer_personids": "list<element: string>", "original_commit_sha": "string"}
Q_ROWS = """SELECT count(*),
 count(*) FILTER (WHERE person_name IS DISTINCT FROM replace(personid, 'author ', 'Author ')),
 count(*) FILTER (WHERE person_email IS DISTINCT FROM CASE WHEN personid IS NOT NULL THEN author_email END),
 count(*) FILTER (WHERE footer_person_names IS DISTINCT FROM
                  list_transform(footer_personids, x -> replace(x, 'author ', 'Author '))),
 count(*) FILTER (WHERE repo_tag IS DISTINCT FROM '')
FROM read_parquet(?)"""
Q_ROWS_KEYS = ["rows", "person_name_differs", "person_email_differs", "footer_person_names_differs",
               "repo_tag_not_empty"]
Q_MAP = """SELECT count(*), count(DISTINCT o) + coalesce(max((o IS NULL)::INT), 0),
 count(DISTINCT c) + coalesce(max((c IS NULL)::INT), 0), count(*) FILTER (WHERE o IS NULL OR c IS NULL)
FROM (SELECT DISTINCT original_commit_sha AS o, cregit_commit_sha AS c FROM read_parquet(?))"""
Q_CONST = "SELECT archived, fork, roster_lang, count(*) FROM read_parquet(?) GROUP BY ALL ORDER BY ALL"
RULES = {
    "person_name": "person_name = replace(personid, 'author ', 'Author ') in every row (NULL with NULL)",
    "person_email": "person_email = CASE WHEN personid IS NOT NULL THEN author_email END in every row",
    "footer_person_names": "footer_person_names = list_transform(footer_personids, x -> replace(x, 'author ', "
                           "'Author ')) in every row",
    "cregit_commit_sha": "the distinct pairs (original_commit_sha, cregit_commit_sha) = the distinct values of each",
    "repo_tag": "repo_tag = '' in every row",
    "archived": "archived holds only the allowed values (never True)",
    "fork": "fork holds only the allowed values (never True)",
    "roster_lang": "roster_lang has one value in the file (it goes to project_facts)",
}


def say(text: str) -> None:
    print(mask(text), flush=True)


def conf_list(text: str) -> list[str]:
    return [x for x in (text or "").split() if x]


def read_keep(path) -> list[dict]:
    out = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            p, f, d, n = line.split("\t")
            out.append({"project": p, "file": f, "sha256": d, "bytes": int(n)})
    return out


def read_jsonl_last(path) -> dict[str, dict]:
    """The last line per file of a JSON-lines log (a new start appends)."""
    out = {}
    if os.path.exists(path):
        for x in Path(path).read_text().splitlines():
            if x.strip():
                r = json.loads(x)
                if "file" in r:
                    out[r["file"]] = r
    return out


def only_names(path) -> set[str]:
    return {x.strip() for x in Path(path).read_text().splitlines() if x.strip()} if path else set()


def arrow_footer(path: str) -> dict:
    import pyarrow.parquet as pq
    md = pq.read_metadata(path)
    sch = md.schema.to_arrow_schema()
    kv = {k.decode(): v.decode() for k, v in (md.metadata or {}).items() if k != b"ARROW:schema"}
    return {"rows": md.num_rows, "row_groups": md.num_row_groups, "columns": [f.name for f in sch],
            "types": {f.name: str(f.type) for f in sch}, "kv": kv, "created_by": md.created_by}


# ---------------------------------------------------------------------------------------------------- keep --
def cmd_keep(a) -> int:
    sums = read_sums(a.sums)
    head, rows = T2.tsv_lines(a.manifest)
    ix = {c: i for i, c in enumerate(head)}
    for c in ("path", "project", "bytes", "sha256"):
        if c not in ix:
            say(f"PROBLEM: MANIFEST.tsv has no column {c}")
            return 1
    man = {r[ix["path"]]: r for r in rows}
    probs, keep = [], []
    pq_rows = sorted(r for r in sums if r.startswith("parquet/"))
    for rel in pq_rows:
        f = rel[len("parquet/"):]
        if "/" in f or not f.endswith(SUFFIX) or not re.fullmatch(r"[A-Za-z0-9._-]+", f):
            probs.append(f"{rel}: not a project file name")
            continue
        m = man.get(rel)
        if m is None:
            probs.append(f"{rel}: no MANIFEST.tsv row")
            continue
        if m[ix["sha256"]] != sums[rel] or m[ix["project"]] != project_of(f):
            probs.append(f"{rel}: the MANIFEST.tsv row is not the SHA256SUMS row (sha256 or project)")
            continue
        keep.append({"project": project_of(f), "file": f, "sha256": sums[rel], "bytes": int(m[ix["bytes"]])})
    extra = sorted(set(man) - set(pq_rows))
    if extra:
        probs.append(f"MANIFEST.tsv rows without a SHA256SUMS row: {extra[:3]}")
    if a.expect and len(keep) != a.expect:
        probs.append(f"{len(keep)} project files, expected {a.expect}")
    if len(keep) > a.max:
        probs.append(f"{len(keep)} project files, more than {a.max}")
    for x in probs[:30]:
        say("PROBLEM: " + x)
    if probs:
        return 1
    out = Path(a.out_dir)
    (out / "keep.tsv").write_text("".join(f"{k['project']}\t{k['file']}\t{k['sha256']}\t{k['bytes']}\n" for k in keep))
    (out / "keep.pf.tsv").write_text("".join(f"{k['project']}\t{k['file']}\n" for k in keep))
    (out / "keep.names").write_text("".join(f"{k['project']}\n" for k in keep))
    (out / "plan.tsv").write_text("file\tproject\tkind\tvalues\n" + "".join(f"{k['file']}\t{k['project']}\tvalue\t{{}}\n" for k in keep))
    say(f"keep: {len(keep):,} project files, {sum(k['bytes'] for k in keep):,} B (SHA256SUMS = MANIFEST.tsv)")
    return 0


# --------------------------------------------------------------------------------------------------- prove --
def prove_one(job: dict) -> dict:
    import duckdb
    f, src = job["file"], job["src"]
    rec = {"v": 1, "file": f, "project": project_of(f), "start_utc": utc(), "status": "ERROR", "problems": []}
    t0 = time.time()
    try:
        rec["in_bytes"] = os.path.getsize(src)
        if rec["in_bytes"] != job["bytes"]:
            rec["problems"].append(f"the input has {rec['in_bytes']} B, the TOM-2 MANIFEST.tsv {job['bytes']} B")
            return rec
        ft = arrow_footer(src)
        for c, t in PROOF_TYPES.items():
            if ft["types"].get(c) != t:
                rec["problems"].append(f"the column {c} is {ft['types'].get(c)}, not {t}")
        if len(ft["columns"]) != job["in_columns"]:
            rec["problems"].append(f"{len(ft['columns'])} columns, not {job['in_columns']}")
        if rec["problems"]:
            return rec
        con = duckdb.connect(config={"threads": job["threads"], "memory_limit": job["mem"],
                                     "preserve_insertion_order": False})
        r = con.execute(Q_ROWS, [src]).fetchone()
        rec.update(dict(zip(Q_ROWS_KEYS, (int(x) for x in r))))
        pairs, originals, cregits, nulls = (int(x) for x in con.execute(Q_MAP, [src]).fetchone())
        rec.update({"commit_pairs": pairs, "original_commits": originals, "cregit_commits": cregits,
                    "commit_pairs_with_null": nulls})
        groups = con.execute(Q_CONST, [src]).fetchall()
        con.close()
        allowed = job["archived_values"]
        arch = sorted({g[0] for g in groups}, key=str)
        fork = sorted({g[1] for g in groups}, key=str)
        roster = sorted({g[2] for g in groups}, key=str)
        rec.update({"archived": arch, "fork": fork, "roster_lang_values": len(roster),
                    "roster_lang": roster[0] if len(roster) == 1 else None})
        if rec["rows"] != ft["rows"] or sum(int(g[3]) for g in groups) != ft["rows"]:
            rec["problems"].append("the rows are not the footer rows")
        for k in Q_ROWS_KEYS[1:]:
            if rec[k]:
                c = k.rsplit("_", 1)[0] if k != "repo_tag_not_empty" else "repo_tag"
                c = c.replace("_differs", "")
                rec["problems"].append(f"{rec[k]:,} rows break the rule: {RULES[c]}")
        if not (pairs == originals == cregits):
            rec["problems"].append(f"{RULES['cregit_commit_sha']}: pairs {pairs:,}, original {originals:,}, "
                                   f"cregit {cregits:,}")
        for name, vals in (("archived", arch), ("fork", fork)):
            bad = [v for v in vals if v not in allowed]
            if bad:
                rec["problems"].append(f"{RULES[name]}: values {bad}")
        if len(roster) != 1 or roster[0] is None:
            rec["problems"].append(f"{RULES['roster_lang']}: {len(roster)} values (or NULL)")
        if not rec["problems"]:
            rec["status"] = "OK"
    except Exception as e:  # noqa: BLE001  (one file fails, the driver goes on)
        rec["problems"].append(f"{type(e).__name__}: {str(e)[:400]}")
    finally:
        rec["prove_s"] = round(time.time() - t0, 2)
        rec["end_utc"] = utc()
    return rec


def run_pool(jobs: list[dict], fn, ledger: str, n: int, stop_file: str | None, progress: str | None, what: str):
    """Largest first, n at a time; one JSON line per file to ledger (fsync); returns (records, stopped)."""
    jobs.sort(key=lambda j: -j["bytes"])
    queue, running, recs, stopped = list(jobs), {}, [], False
    total, t0 = len(jobs), time.time()
    total_bytes, done_bytes, started = sum(j["bytes"] for j in jobs), 0, {}
    with open(ledger, "a") as led, cf.ProcessPoolExecutor(max_workers=n) as ex:
        while queue or running:
            if stop_file and os.path.exists(stop_file) and queue:
                stopped, queue = True, []
                say(f"{what}: STOP file: no new file")
            while queue and len(running) < n:
                j = queue.pop(0)
                started[j["file"]] = time.time()
                running[ex.submit(fn, j)] = j
            done, _ = cf.wait(list(running), return_when=cf.FIRST_COMPLETED)
            for fut in done:
                j = running.pop(fut)
                try:
                    rec = fut.result()
                except Exception as e:  # noqa: BLE001
                    rec = {"v": 1, "file": j["file"], "status": "ERROR", "problems": [f"worker: {e}"], "end_utc": utc()}
                led.write(jline(rec) + "\n")
                led.flush()
                os.fsync(led.fileno())
                recs.append(rec)
                if rec["status"] != "OK":
                    say(f"{what} FAIL {rec['file']}: {'; '.join(rec.get('problems', []))[:600]}")
                done_bytes += j["bytes"]
                if progress:
                    ok = sum(r["status"] == "OK" for r in recs)
                    now = time.time()
                    Path(progress).write_text(json.dumps({
                        "what": what, "utc": utc(), "done": len(recs), "ok": ok, "failed": len(recs) - ok,
                        "total": total, "done_bytes": done_bytes, "total_bytes": total_bytes,
                        "elapsed_s": round(now - t0), "final": not queue and len(running) == 0,
                        "running": [{"file": x["file"], "bytes": x["bytes"], "elapsed_s": round(now - started[x["file"]])}
                                    for x in running.values()]}))
    return recs, stopped


def cmd_prove(a) -> int:
    keep = read_keep(a.keep)
    only = only_names(a.only_list)
    if only:
        keep = [k for k in keep if k["file"] in only]
        if len(keep) != len(only):
            say(f"ABORT: {len(only) - len(keep)} files of the list are not kept")
            return 2
    done = read_jsonl_last(a.out)
    allowed = [v for v in a.archived_values.split("|")]
    jobs = []
    for k in keep:
        src = os.path.join(a.src_dir, k["file"])
        r = done.get(k["file"])
        if r and r.get("status") == "OK" and r.get("in_bytes") == k["bytes"] and os.path.exists(src) \
                and os.path.getsize(src) == k["bytes"]:
            continue
        if not os.path.exists(src):
            say(f"ABORT: no input {src}")
            return 2
        jobs.append(dict(k, src=src, threads=a.threads, mem=a.mem, archived_values=allowed, in_columns=a.in_columns))
    say(f"prove: {len(jobs)} files to prove, {len(keep) - len(jobs)} already proved; jobs {a.jobs}, threads {a.threads}")
    t0 = time.time()
    recs, stopped = run_pool(jobs, prove_one, a.out, a.jobs, a.stop_file, a.progress, "prove")
    bad = [r for r in recs if r["status"] != "OK"]
    say(f"prove summary: {len(recs) - len(bad)} OK, {len(bad)} failed, {len(keep) - len(jobs)} earlier; "
        f"{time.time() - t0:.0f} s; rows {sum(r.get('rows', 0) for r in recs):,}")
    return 1 if bad else (3 if stopped else 0)


def cmd_proof_sum(a) -> int:
    keep = read_keep(a.keep)
    proof = read_jsonl_last(a.proof)
    probs = []
    rows = 0
    counts = {"archived": {}, "fork": {}}
    roster = 0
    sums = {k: 0 for k in Q_ROWS_KEYS[1:] + ["commit_pairs", "original_commits", "cregit_commits"]}
    for k in keep:
        r = proof.get(k["file"])
        if not r or r.get("status") != "OK" or r.get("in_bytes") != k["bytes"]:
            probs.append(f"{k['file']}: no OK proof line for the TOM-2 bytes")
            continue
        rows += r["rows"]
        for c in counts:
            key = "|".join(r[c])
            counts[c][key] = counts[c].get(key, 0) + 1
        roster += r["roster_lang"] != ""
        for s in sums:
            sums[s] += r[s]
    if len(proof) != len(keep) and not probs:
        extra = sorted(set(proof) - {k["file"] for k in keep})
        if extra:
            probs.append(f"proof lines for files that are not kept: {extra[:3]}")
    for c, want_text in (("archived", a.expect_archived), ("fork", a.expect_fork)):
        want = {}
        for item in conf_list(want_text):
            v, _, n = item.rpartition("=")
            want[v] = int(n)
        if counts[c] != want:
            probs.append(f"{c}: files per value {counts[c]}, expected {want}")
    if a.expect_rows and rows != a.expect_rows:
        probs.append(f"proved rows {rows:,}, expected {a.expect_rows:,}")
    if roster != a.expect_roster:
        probs.append(f"{roster} files with a roster_lang value, expected {a.expect_roster}")
    if any(sums[k] for k in Q_ROWS_KEYS[1:]):
        probs.append(f"rows that break a rule: {sums}")
    rep = {"utc": utc(), "files": len(keep), "rows": rows, "files_per_value": counts, "roster_lang_files": roster,
           "sums": sums, "rules": RULES, "problems": probs[:50]}
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True))
    for x in probs[:30]:
        say("PROBLEM: " + x)
    say(f"proof-sum: {len(keep):,} files, {rows:,} rows, 0 rows break a rule: {not any(sums[k] for k in Q_ROWS_KEYS[1:])}; "
        f"commits {sums['commit_pairs']:,} pairs = original {sums['original_commits']:,} = cregit "
        f"{sums['cregit_commits']:,}; archived {counts['archived']}; fork {counts['fork']}; roster_lang {roster}; "
        f"problems {len(probs)}")
    return 1 if probs else 0


# ---------------------------------------------------------------------------------------------------- pass --
def pass_one(job: dict) -> dict:
    f, src, dst = job["file"], job["src"], job["dst"]
    rec = {"v": 1, "file": f, "project": project_of(f), "start_utc": utc(), "status": "ERROR", "problems": []}
    t0 = time.time()
    part = dst + ".part"
    try:
        rec["in_bytes"] = os.path.getsize(src)
        rec["in_sha256"] = sha256(src)
        rec["want_in_sha256"] = job["sha256"]
        if rec["in_sha256"] != job["sha256"]:
            rec["problems"].append("the input sha256 is not the TOM-2 SHA256SUMS row")
            return rec
        if not job["proof_ok"]:
            rec["problems"].append("no OK proof line for this input")
            return rec
        if os.path.exists(part):
            os.remove(part)
        env = dict(os.environ, OMP_NUM_THREADS=str(job["threads"]), PYTHONDONTWRITEBYTECODE="1")
        drops = [x for c in job["drops"] for x in ("--drop", c)]
        rc, out, err, secs, rss = T.run_child([sys.executable, "-I", "-B", job["rename_py"], src, part, *drops,
                                               "--copy", job["copy_mode"]], env)
        rec.update({"rename_s": round(secs, 2), "rename_rc": rc})
        try:
            rec["rename"] = {k: v for k, v in json.loads(out.strip().splitlines()[-1]).items()
                             if k in ("bytes_in", "bytes_out", "dropped", "copy", "regions", "row_groups")}
        except Exception:  # noqa: BLE001
            rec["rename"] = None
        if rc != 0:
            rec["problems"].append(f"parquet_rename.py rc {rc}: {mask(err.strip()[-400:])}")
            return rec
        rc, out, err, secs, rss2 = T.run_child([sys.executable, "-I", "-B", job["check_py"], *drops, src, part], env)
        rec.update({"check_s": round(secs, 2), "check_rc": rc})
        try:
            rep = json.loads(out.strip().splitlines()[-1])
        except Exception:  # noqa: BLE001
            rep = {}
        if job.get("check_dir"):
            Path(job["check_dir"], f"{rec['project']}.json").write_text(mask(out))
        rec["check"] = {k: rep.get(k) for k in ("ok", "problems", "column_chunks_identical", "page_index_pages",
                                                  "row_groups", "rows")}
        if rc != 0 or rep.get("ok") is not True:
            rec["problems"].append(f"parquet_rename_check.py rc {rc}: {mask(json.dumps(rep.get('problems'))[:400])}")
            return rec
        old, new = arrow_footer(src), arrow_footer(part)
        want_cols = [c for c in old["columns"] if c not in job["drops"]]
        if new["columns"] != want_cols or len(new["columns"]) != job["want_columns"]:
            rec["problems"].append(f"the output has {len(new['columns'])} columns, not the {job['want_columns']} kept ones")
        if new["kv"] != old["kv"]:
            rec["problems"].append("the output footer key-values are not the input ones")
        if (new["rows"], new["row_groups"], new["created_by"]) != (old["rows"], old["row_groups"], old["created_by"]):
            rec["problems"].append("the output rows, row groups or created_by differ from the input")
        if any(new["types"][c] != old["types"][c] for c in want_cols if c in new["types"]):
            rec["problems"].append("a kept column changed its type")
        if rec["problems"]:
            return rec
        os.replace(part, dst)
        rec.update({"out_bytes": os.path.getsize(dst), "out_sha256": sha256(dst), "rows": new["rows"],
                    "columns": len(new["columns"]), "peak_rss_bytes": max(rss, rss2), "status": "OK"})
    except Exception as e:  # noqa: BLE001
        rec["problems"].append(f"{type(e).__name__}: {str(e)[:400]}")
    finally:
        rec["total_s"] = round(time.time() - t0, 2)
        rec["end_utc"] = utc()
    return rec


def cmd_pass(a) -> int:
    keep = read_keep(a.keep)
    only = only_names(a.only_list)
    if only:
        keep = [k for k in keep if k["file"] in only]
        if len(keep) != len(only):
            say(f"ABORT: {len(only) - len(keep)} files of the list are not kept")
            return 2
    proof = read_jsonl_last(a.proof)
    done = T.read_ledger(a.ledger)
    drops = conf_list(a.drop_columns)
    jobs = []
    for k in keep:
        src, dst = os.path.join(a.src_dir, k["file"]), os.path.join(a.dst, k["file"])
        r = done.get(k["file"])
        if r and r.get("status") == "OK" and os.path.exists(dst) and os.path.getsize(dst) == r.get("out_bytes"):
            continue
        if not os.path.exists(src):
            say(f"ABORT: no input {src}")
            return 2
        p = proof.get(k["file"]) or {}
        jobs.append(dict(k, src=src, dst=dst, drops=drops, threads=a.threads, copy_mode=a.copy_mode,
                         rename_py=a.rename_py, check_py=a.check_py, check_dir=a.check_dir, want_columns=a.want_columns,
                         proof_ok=p.get("status") == "OK" and p.get("in_bytes") == k["bytes"]))
    say(f"pass: {len(jobs)} files to drop, {len(keep) - len(jobs)} done earlier; jobs {a.jobs}, threads {a.threads}")
    t0 = time.time()
    recs, stopped = run_pool(jobs, pass_one, a.ledger, a.jobs, a.stop_file, a.progress, "pass")
    bad = [r for r in recs if r["status"] != "OK"]
    ib = sum(r.get("in_bytes", 0) for r in recs if r["status"] == "OK")
    ob = sum(r.get("out_bytes", 0) for r in recs if r["status"] == "OK")
    say(f"pass summary: {len(recs) - len(bad)} OK, {len(bad)} failed, {len(keep) - len(jobs)} earlier; "
        f"{time.time() - t0:.0f} s; {ib:,} B -> {ob:,} B")
    return 1 if bad else (3 if stopped else 0)


# --------------------------------------------------------------------------------------------------- facts --
def cmd_facts(a) -> int:
    import pyarrow as pa
    import pyarrow.parquet as pq
    t2 = pq.read_table(a.tom2_facts)
    if t2.column_names != ["project", "fact_type", "fact_value"]:
        say(f"ABORT: the TOM-2 project_facts columns are {t2.column_names}")
        return 1
    rows = t2.to_pylist()
    projects = [r["project"] for r in rows]
    if projects != sorted(projects):
        say("ABORT: the TOM-2 project_facts rows are not in project order")
        return 1
    if any(r["fact_type"] == a.fact_type for r in rows):
        say(f"ABORT: the TOM-2 project_facts has rows of fact_type {a.fact_type}")
        return 1
    keep = read_keep(a.keep)
    kept = {k["project"] for k in keep}
    if not set(projects) <= kept:
        say("ABORT: TOM-2 project_facts has projects that are not kept")
        return 1
    proof = read_jsonl_last(a.proof)
    new = []
    for k in keep:
        r = proof.get(k["file"])
        if not r or r.get("status") != "OK":
            say(f"ABORT: {k['file']}: no OK proof line")
            return 1
        if r["roster_lang"]:
            new.append({"project": k["project"], "fact_type": a.fact_type, "fact_value": r["roster_lang"]})
    if len(new) != a.expect:
        say(f"ABORT: {len(new)} {a.fact_type} facts, expected {a.expect}")
        return 1
    out = sorted(rows + new, key=lambda r: r["project"])  # stable: the TOM-2 rows of a project stay first
    tbl = pa.Table.from_pylist(out, schema=t2.schema)
    T2.write_pq(tbl, a.out)
    back = pq.read_table(a.out).to_pylist()
    if [r for r in back if r["fact_type"] != a.fact_type] != rows:
        say("ABORT: the TOM-2 rows did not stay in their order")
        return 1
    types = {}
    for r in out:
        types[r["fact_type"]] = types.get(r["fact_type"], 0) + 1
    say(f"project_facts: {len(rows):,} TOM-2 rows + {len(new)} {a.fact_type} rows = {len(out):,} rows, "
        f"{len({r['project'] for r in out}):,} projects; types {types}; sha256 {sha256(a.out)[:12]}")
    return 0


# -------------------------------------------------------------------------------------------- release-info --
def read_ri(path) -> dict[str, str]:
    import duckdb
    return dict(duckdb.connect().execute("SELECT key, value FROM read_parquet(?)", [str(path)]).fetchall())


def cmd_release_info(a) -> int:
    import duckdb
    root, t2root = Path(a.root).resolve(), Path(a.tom2_root).resolve()
    rel = Path("organizations/release_info.parquet")
    info, t2info = read_ri(root / rel), read_ri(t2root / rel)
    if info != t2info:
        say("ABORT: the release_info of the root is not the TOM-2 copy")
        return 1
    changed = conf_list(a.changed)
    new = dict(info)
    for k in changed:
        base, _, kind = k.rpartition("_")
        p = root / f"organizations/{base}.parquet"
        if k not in info or not p.exists():
            say(f"ABORT: the key {k} or organizations/{base}.parquet is not there")
            return 1
        if kind == "rows":
            new[k] = str(duckdb.connect().execute("SELECT count(*) FROM read_parquet(?)", [str(p)]).fetchone()[0])
        elif kind == "sha256":
            new[k] = sha256(p)
        else:
            say(f"ABORT: {k} is not a _rows or _sha256 key")
            return 1
    db = root / a.db_rel
    if sha256(db) != info.get("dataset_db_sha256"):
        say("ABORT: organizations/dataset.duckdb is not the dataset_db_sha256 of TOM-2 (this pass does not change it)")
        return 1
    if new.get("ctp_schema_version") != a.schema_version:
        say(f"ABORT: ctp_schema_version is {new.get('ctp_schema_version')}, not {a.schema_version}")
        return 1
    if len(new) != a.expect_keys:
        say(f"ABORT: {len(new)} keys, expected {a.expect_keys}")
        return 1
    con = duckdb.connect()
    con.execute("CREATE TABLE ri(key VARCHAR, value VARCHAR)")
    con.executemany("INSERT INTO ri VALUES (?, ?)", sorted(new.items()))
    tmp = root / "organizations/ri.tmp"
    con.execute(f"COPY (SELECT * FROM ri ORDER BY key) TO '{tmp}' (FORMAT parquet, COMPRESSION zstd)")
    con.close()
    os.replace(tmp, root / rel)
    if read_ri(root / rel) != new:
        say("ABORT: the read back of release_info.parquet")
        return 1
    diff = {k: (info[k][:12], new[k][:12]) for k in new if new[k] != info[k]}
    say(f"release_info: {len(new)} keys; changed {diff}; the other {len(new) - len(diff)} keys = TOM-2; "
        f"ctp_schema_version {new['ctp_schema_version']}; dataset_db_sha256 = the DB ({info['dataset_db_sha256'][:12]})")
    return 0


# -------------------------------------------------------------------------------------------------- values --
def cmd_values(a) -> int:
    import duckdb
    root = Path(a.root).resolve()
    keep = read_keep(a.keep)
    led = T.read_ledger(a.ledger)
    proof = read_jsonl_last(a.proof)
    probs, nbytes, rows, prev, proved = [], 0, 0, 0, 0
    cols = set()
    for k in keep:
        rec = led.get(k["file"]) or {}
        if rec.get("status") != "OK":
            probs.append(f"{k['file']}: no OK ledger line")
            continue
        size = os.path.getsize(root / "parquet" / k["file"])
        if size != rec["out_bytes"]:
            probs.append(f"{k['file']}: the size is not the ledger out_bytes")
        nbytes += size
        rows += rec["rows"]
        prev += k["bytes"]
        cols.add(rec["columns"])
        proved += (proof.get(k["file"]) or {}).get("rows", 0)
    sizes = json.loads(Path(a.sizes).read_text())
    n_local = len(T2.local_files(root))
    v = {"projects": f"{len(keep):,}", "parquet files": f"{len(keep):,}", "parquet bytes": f"{nbytes:,}",
         "parquet GB": f"{nbytes / 1e9:.1f}", "rows": f"{rows:,}", "date": a.date, "machine": a.machine,
         "root files": f"{n_local + 1:,}", "columns": ",".join(str(c) for c in sorted(cols)),
         "dropped columns": f"{len(conf_list(a.drop_columns))}", "changed files": f"{len(keep):,}",
         "proved rows": f"{proved:,}", "previous parquet bytes": f"{prev:,}", "dropped bytes": f"{prev - nbytes:,}"}
    for k in T.SIZE_KEYS:
        v[f"size {k}"] = f"{sizes['size_rule_counts'].get(k, 0):,}"
    for k in ("S", "M", "L"):
        v[f"size_class {k}"] = f"{sizes['size_class_counts'].get(k, 0):,}"
    cwd = os.getcwd()
    os.chdir(root)
    try:
        con = duckdb.connect(str(root / a.db_rel), read_only=True)
        for t in T.TABLES + ["project_languages", "project_labels"]:
            n = con.execute(f"SELECT count(*) FROM read_parquet('organizations/{t}.parquet')").fetchone()[0]
            v["facts rows" if t == "project_facts" else f"{t} rows"] = f"{n:,}"
        v["facts projects"] = f"{con.execute('SELECT count(DISTINCT project) FROM project_facts').fetchone()[0]:,}"
        v["roster_language facts"] = f"{con.execute('SELECT count(*) FROM project_facts WHERE fact_type = ?', [a.fact_type]).fetchone()[0]:,}"
        for view in ("project_hosts", "project_sponsors", "project_languages", "project_labels"):
            n, nd = con.execute(f"SELECT count(*), count(DISTINCT project) FROM {view}").fetchone()
            v[f"{view} rows"], v[f"{view} projects"] = f"{n:,}", f"{nd:,}"
        con.close()
    finally:
        os.chdir(cwd)
    if len(cols) != 1:
        probs.append(f"the files have {sorted(cols)} columns")
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
def footers_of(folder: Path, names: list[str], jobs: int) -> dict[str, dict]:
    def one(f):
        return f, arrow_footer(str(folder / f))
    with cf.ThreadPoolExecutor(max_workers=jobs) as ex:
        return dict(ex.map(one, names))


def cmd_check_root(a) -> int:
    import duckdb
    root, t2root = Path(a.root).resolve(), Path(a.tom2_root).resolve()
    keep = read_keep(a.keep)
    names = [k["file"] for k in keep]
    drops = conf_list(a.drop_columns)
    led = T.read_ledger(a.ledger)
    proof = read_jsonl_last(a.proof)
    probs, rep = [], {"utc": utc()}
    have = sorted(os.listdir(root / "parquet"))
    if have != sorted(names):
        probs.append(f"parquet/ holds {len(have)} files, not the {len(names)} kept ones")
    if len(have) > a.max or (a.expect_files and len(have) != a.expect_files):
        probs.append(f"parquet/ holds {len(have)} files (expected {a.expect_files}, max {a.max})")
    # footers: each output against its own TOM-2 input
    new = footers_of(root / "parquet", names, a.jobs)
    old = footers_of(Path(a.src_dir), names, a.jobs)
    rows = 0
    ref_cols = None
    for f in names:
        n, o = new[f], old[f]
        want = [c for c in o["columns"] if c not in drops]
        if n["columns"] != want or len(want) != a.want_columns:
            probs.append(f"{f}: {len(n['columns'])} columns, not the {a.want_columns} kept columns")
        if ref_cols is None:
            ref_cols = n["columns"]
        elif n["columns"] != ref_cols:
            probs.append(f"{f}: the column list is not the one of {names[0]}")
        if any(d in n["types"] for d in drops):
            probs.append(f"{f}: a dropped column is in the footer")
        if n["kv"] != o["kv"]:
            probs.append(f"{f}: the footer key-values are not the TOM-2 ones of this file")
        if n["kv"].get("ctp_schema_version") != a.schema_version:
            probs.append(f"{f}: ctp_schema_version is {n['kv'].get('ctp_schema_version')}")
        if (n["rows"], n["row_groups"]) != (o["rows"], o["row_groups"]):
            probs.append(f"{f}: rows or row groups differ from TOM-2")
        if any(n["types"][c] != o["types"][c] for c in n["columns"]):
            probs.append(f"{f}: a column type differs from TOM-2")
        r = led.get(f) or {}
        if r.get("status") != "OK" or r.get("rows") != n["rows"] or r.get("out_bytes") != os.path.getsize(root / "parquet" / f):
            probs.append(f"{f}: no OK ledger line for this output")
        p = proof.get(f) or {}
        if p.get("status") != "OK" or p.get("rows") != o["rows"]:
            probs.append(f"{f}: no OK proof line")
        rows += n["rows"]
    rep["rows"] = rows
    rep["columns"] = len(ref_cols or [])
    if a.expect_rows and rows != a.expect_rows:
        probs.append(f"rows {rows:,}, expected {a.expect_rows:,}")
    # SHA256SUMS
    sums = read_sums(root / "SHA256SUMS")
    t2sums = read_sums(a.tom2_sums)
    local = T2.local_files(root)
    if sorted(sums) != local:
        probs.append(f"SHA256SUMS has {len(sums)} rows for {len(local)} local files")
    for f in names:
        if sums.get(f"parquet/{f}") != (led.get(f) or {}).get("out_sha256"):
            probs.append(f"parquet/{f}: the SHA256SUMS row is not the ledger output")
        if sums.get(f"parquet/{f}") == t2sums.get(f"parquet/{f}"):
            probs.append(f"parquet/{f}: the same sha256 as TOM-2")
    allow_gone = set(conf_list(a.allow_gone))
    gone = sorted(set(t2sums) - set(sums))
    if set(gone) - allow_gone:
        probs.append(f"TOM-2 files that are gone: {sorted(set(gone) - allow_gone)[:5]}")
    other_changed = sorted(r for r in sums if not r.startswith("parquet/") and sums[r] != t2sums.get(r))
    must_same = ["ledgers.parquet", "links.json", "pseudonymization.json", a.db_rel] + \
        [r for r in t2sums if r.startswith("organizations/") and r not in
         ("organizations/project_facts.parquet", "organizations/release_info.parquet")]
    for r in must_same:
        if r in t2sums and sums.get(r) != t2sums[r]:
            probs.append(f"{r}: not the TOM-2 bytes")
    rep["other_changed"] = other_changed
    rep["gone"] = gone
    # MANIFEST.tsv
    head, mrows = T2.tsv_lines(root / "MANIFEST.tsv")
    h2, m2 = T2.tsv_lines(t2root / "MANIFEST.tsv")
    if head != h2:
        probs.append("MANIFEST.tsv: the header is not the TOM-2 header")
    ix = {c: i for i, c in enumerate(head)}
    by2 = {r[ix["path"]]: r for r in m2}
    if sorted(r[ix["path"]] for r in mrows) != sorted(f"parquet/{f}" for f in names) or len(mrows) != len(names):
        probs.append("MANIFEST.tsv: not one row per project file")
    for r in mrows:
        path = r[ix["path"]]
        f = path[len("parquet/"):]
        if r[ix["sha256"]] != sums.get(path):
            probs.append(f"MANIFEST.tsv {path}: sha256 is not the SHA256SUMS row")
        if f in new and (int(r[ix["bytes"]]) != os.path.getsize(root / path)):
            probs.append(f"MANIFEST.tsv {path}: bytes is not the file size")
        if "rows" in ix and f in new and int(r[ix["rows"]]) != new[f]["rows"]:
            probs.append(f"MANIFEST.tsv {path}: rows is not the footer rows")
        o = by2.get(path)
        if o is None or any(r[ix[c]] != o[ix[c]] for c in head if c not in ("bytes", "sha256")):
            probs.append(f"MANIFEST.tsv {path}: differs from TOM-2 in more than bytes and sha256")
    # tables and views
    cwd = os.getcwd()
    os.chdir(root)
    try:
        con = duckdb.connect(str(root / a.db_rel), read_only=True)
        views = con.execute("SELECT view_name, sql FROM duckdb_views() WHERE NOT internal ORDER BY 1").fetchall()
        rep["views"] = {}
        word = re.compile(r"\b(" + "|".join(re.escape(d) for d in drops) + r")\b")
        for name, sql in views:
            try:
                res = con.execute(f"SELECT * FROM {name} LIMIT 1")
                cols = [d[0] for d in res.description]
                res.fetchall()
                hit = sorted(set(cols) & set(drops))
                if hit:
                    probs.append(f"the view {name} has the dropped columns {hit}")
                if word.search(sql or ""):
                    probs.append(f"the view {name} names a dropped column in its SQL")
                rep["views"][name] = len(cols)
            except Exception as e:  # noqa: BLE001
                probs.append(f"the view {name} fails: {str(e)[:200]}")
        for v in conf_list(a.need_views):
            if v not in rep["views"]:
                probs.append(f"no view {v}")
        if "tokens" in rep["views"] and rep["views"]["tokens"] != a.want_columns + 1:
            probs.append(f"the view tokens has {rep['views']['tokens']} columns, not {a.want_columns} + filename")
        n_tok = con.execute("SELECT count(*) FROM tokens").fetchone()[0]
        if n_tok != rows:
            probs.append(f"the view tokens has {n_tok:,} rows, the footers {rows:,}")
        # project_facts: the TOM-2 rows (same order) plus the roster facts of the proof
        f2 = con.execute("SELECT project, fact_type, fact_value FROM read_parquet(?)",
                         [str(t2root / "organizations/project_facts.parquet")]).fetchall()
        f3 = con.execute("SELECT project, fact_type, fact_value FROM project_facts").fetchall()
        if [r for r in f3 if r[1] != a.fact_type] != f2:
            probs.append("project_facts: the TOM-2 rows are not kept in their order")
        want_r = sorted((k["project"], a.fact_type, proof[k["file"]]["roster_lang"]) for k in keep
                        if (proof.get(k["file"]) or {}).get("roster_lang"))
        got_r = sorted(r for r in f3 if r[1] == a.fact_type)
        if got_r != want_r:
            probs.append(f"project_facts: {len(got_r)} {a.fact_type} rows, the proof gives {len(want_r)}")
        if a.expect_roster and len(got_r) != a.expect_roster:
            probs.append(f"project_facts: {len(got_r)} {a.fact_type} rows, expected {a.expect_roster}")
        kept = {k["project"] for k in keep}
        if not {r[0] for r in f3} <= kept:
            probs.append("project_facts: a project that is not kept")
        rep["roster_facts"] = len(got_r)
        for t in ("project_languages", "project_labels", "project_organizations"):
            ps = [r[0] for r in con.execute(f"SELECT project FROM read_parquet('organizations/{t}.parquet') ORDER BY 1").fetchall()]
            if ps != sorted(kept):
                probs.append(f"{t}: not the {len(kept)} kept projects")
        led_p = {r[0] for r in con.execute("SELECT DISTINCT project FROM read_parquet('ledgers.parquet')").fetchall()}
        if led_p != kept:
            probs.append("ledgers.parquet: not the kept projects")
        # release_info: every key against its measured value; the keys of RI_CHANGED changed, the others = TOM-2
        info = dict(con.execute("SELECT key, value FROM release_info").fetchall())
        t2info = read_ri(t2root / "organizations/release_info.parquet")
        kv = new[names[0]]["kv"] if names else {}
        p2, st = T2.release_info_problems(root, info, t2info, kv, con)
        probs += p2
        rep["release_info"] = st
        if len(info) != a.expect_ri_keys:
            probs.append(f"release_info: {len(info)} keys, expected {a.expect_ri_keys}")
        if info.get("ctp_schema_version") != a.schema_version:
            probs.append(f"release_info: ctp_schema_version is {info.get('ctp_schema_version')}")
        for k in sorted(set(info) | set(t2info)):
            if k not in conf_list(a.ri_changed) and info.get(k) != t2info.get(k):
                probs.append(f"release_info: {k} differs from TOM-2")
        con.close()
    finally:
        os.chdir(cwd)
    left = T.marks_left(root)
    if left:
        probs.append(f"marker words or placeholders left: {left[:10]}")
    rep["problems"] = probs[:200]
    rep["n_problems"] = len(probs)
    Path(a.out).write_text(mask(json.dumps(rep, indent=1, sort_keys=True)))
    for x in probs[:40]:
        say("PROBLEM: " + x)
    say(f"check-root: {len(names):,} files, {rows:,} rows, {rep['columns']} columns; views {len(rep.get('views', {}))}; "
        f"roster facts {rep.get('roster_facts')}; release_info {rep.get('release_info')}; other changed files "
        f"{len(other_changed)}; gone {len(gone)}; problems {len(probs)}")
    return 1 if probs else 0


# ---------------------------------------------------------------------------------------------------- main --
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("keep")
    for k in ("sums", "manifest", "out-dir"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--expect", type=int, default=0)
    s.add_argument("--max", type=int, default=9999)
    s = sub.add_parser("prove")
    for k in ("keep", "src-dir", "out", "archived-values"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--in-columns", type=int, required=True)
    s.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) // 4))
    s.add_argument("--threads", type=int, default=4)
    s.add_argument("--mem", default="8GB")
    for k in ("only-list", "progress", "stop-file"):
        s.add_argument(f"--{k}")
    s = sub.add_parser("proof-sum")
    for k in ("keep", "proof", "out", "expect-archived", "expect-fork"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--expect-rows", type=int, default=0)
    s.add_argument("--expect-roster", type=int, required=True)
    s = sub.add_parser("pass")
    for k in ("keep", "proof", "src-dir", "dst", "ledger", "rename-py", "check-py", "drop-columns"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--want-columns", type=int, required=True)
    s.add_argument("--copy-mode", default="read-write")
    s.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    s.add_argument("--threads", type=int, default=2)
    for k in ("only-list", "progress", "stop-file", "check-dir"):
        s.add_argument(f"--{k}")
    s = sub.add_parser("facts")
    for k in ("tom2-facts", "proof", "keep", "fact-type", "out"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--expect", type=int, required=True)
    s = sub.add_parser("release-info")
    for k in ("root", "tom2-root", "changed", "db-rel", "schema-version"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--expect-keys", type=int, required=True)
    s = sub.add_parser("values")
    for k in ("root", "keep", "ledger", "proof", "sizes", "db-rel", "date", "machine", "out", "drop-columns", "fact-type"):
        s.add_argument(f"--{k}", required=True)
    sub.add_parser("keys")
    s = sub.add_parser("check-root")
    for k in ("root", "tom2-root", "src-dir", "keep", "ledger", "proof", "tom2-sums", "db-rel", "out", "drop-columns",
              "schema-version", "fact-type"):
        s.add_argument(f"--{k}", required=True)
    for k in ("need-views", "allow-gone", "ri-changed"):
        s.add_argument(f"--{k}", default="")
    for k, d in (("max", 9999), ("want-columns", 0), ("expect-files", 0), ("expect-rows", 0), ("expect-roster", 0),
                 ("expect-ri-keys", 0), ("jobs", 8)):
        s.add_argument(f"--{k}", type=int, default=d)
    a = ap.parse_args(argv)
    for k, v in list(vars(a).items()):
        setattr(a, k.replace("-", "_"), v)
    return {"keep": cmd_keep, "prove": cmd_prove, "proof-sum": cmd_proof_sum, "pass": cmd_pass, "facts": cmd_facts,
            "release-info": cmd_release_info, "values": cmd_values, "keys": cmd_keys,
            "check-root": cmd_check_root}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
