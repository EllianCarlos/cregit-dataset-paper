#!/usr/bin/env python3
"""Run rewrite_footer_columns.py on each finished census Parquet that cregit 95cdc88 wrote.

Usage: footer_fix_batches.py [--list | --pending] [--only NAME ...] [--limit N] [--jobs 2]
       [--retry-failed | --retry-transient] [--out-root DIR] [--cloud DIR]

Scope. The rows of census-cloud/verified.tsv of the runs in RUNS. The ledger rows of the
project (done/<project>/ledger.jsonl from S3, else ledger.from-run.jsonl that
split_run_ledgers.py writes for the big EC2 runs) must name cregit 95cdc88. A folder with
neither file counts as 95cdc88, as runs-20261009.md records. A project that also has a Parquet
in census-2026-10 (the local batch 1, cregit 157cf8b) is out of scope.

The clone. When the pinned commit is known (state/pin.json, else pin.from-run.json), the tool
gets a commit-only clone with only that branch at that commit, as pin.py makes it. pinned_clone
fetches the commit by its hash when the branch no longer holds it (an upstream history rewrite).
Else the tool clones clone_url itself.

Output. OUT_ROOT/<relative path of the done folder>/<project>-dataset.parquet and a copy of
<project>-persons.db. The original files are only read. OUT_ROOT/manifest.tsv gets one row for
each attempt (append only; the last row of a path counts). OUT_ROOT/logs/<project>.log holds
the tool's output, OUT_ROOT/reports/<project>.tsv its report row.

The persons DB. The spot runs (batch1rest, batch3, batch5, batch6) did not upload
<project>-persons.db. For those, this script builds it again as step 5 of
run_pipeline_process.sh does (the persons one-jar on the original bare repository), on a clone
that holds what the census clone held (pin.py): one branch, at the pinned commit of
state/pin.json, and no other ref. A commit-only clone (--filter=tree:0) is enough. Measured on
Activiti__Activiti: the emails and persons tables are equal to the census DB except the
emails.dateadded time. The tool then checks the DB against the person columns of every author
of the file and refuses the file when one differs. The manifest note says "persons_db=rebuilt".

Run it again for new arrivals: a path with an "ok" row and its output file is skipped. A path
with another status is skipped too, except with --retry-failed (all of them) or
--retry-transient (the statuses in TRANSIENT; not "refused" or "compare_failed"). A file
OUT_ROOT/STOP stops the start of new projects. --pending prints the projects of the run
manifests (MANIFESTS) that are not settled yet and exits 0 when there is none: settled is ok
or refused here, failed in failed-projects.tsv, or a local batch 1 project. A project with more than BIG_COMMITS commits runs alone (memory)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HOME = Path.home()
HERE = Path(__file__).resolve().parent
TOOL = HERE / "rewrite_footer_columns.py"
PERSONS_JAR = Path(os.environ.get(
    "PERSONS_JAR", HOME / "Projects/cregit-ec2/persons/target/scala-2.10/"
    "persons_2.10-0.1-SNAPSHOT-one-jar.jar"))
CLOUD = HOME / "Projects/cregit-workspace/census-cloud"
LOCAL = HOME / "Projects/cregit-workspace/census-2026-10"
OUT_ROOT = HOME / "Projects/cregit-workspace/census-cloud-fixed"
RUNS = ("batch1rest", "batch2", "batch3", "batch3L", "batch4", "batch5", "batch5L", "batch6",
        "batch6L")
OLD_CREGIT = "95cdc88"
TRANSIENT = ("clone_failed", "error", "no_persons_db", "input_mismatch")
MANIFESTS = ("manifest.batch1rest.tsv", "manifest.batch2.tsv", "manifest.batch3.tsv",
             "manifest.batch4.tsv", "manifest.batch5.tsv", "manifest.batch6.tsv")
BIG_COMMITS = 300_000
MANIFEST_COLS = ("project", "run", "rel_path", "cregit", "input_sha256", "output_sha256",
                 "rows", "commits", "changed_commits", "before", "after", "status", "seconds",
                 "clone_s", "parse_s", "rewrite_s", "finished_utc", "note")
FOOTERS = ("footer_signed_off_by", "footer_co_authored_by", "footer_co_developed_by",
           "footer_reviewed_by", "footer_acked_by", "footer_tested_by", "footer_reported_by",
           "footer_suggested_by", "footer_based_on_patch_by", "footer_helped_by",
           "footer_mentored_by", "footer_assisted_by", "footer_thanks_to", "footer_personids",
           "footer_person_names")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def ledger_cregit(done: Path, name: str) -> str:
    led = done / "ledger.jsonl"
    if not led.is_file():
        led = done / "ledger.from-run.jsonl"
    if not led.is_file():
        return "noledger"
    seen = set()
    with led.open(encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            if d.get("project") == name and "tools" in d:
                seen.add(d["tools"]["cregit_commit"][:7])
    return ",".join(sorted(seen)) or "noledger"


def inputs(cloud: Path) -> list[dict]:
    local = {p.name.removesuffix("-dataset.parquet") for p in LOCAL.rglob("*-dataset.parquet")}
    out, seen = [], set()
    for line in (cloud / "verified.tsv").read_text(encoding="utf-8").splitlines():
        _, rel, sha = line.split("\t")
        run = rel.split("/")[0]
        name = rel.rsplit("/", 1)[1]
        if run not in RUNS or rel in seen:
            continue
        seen.add(rel)
        done = cloud / rel
        src = done / f"{name}-dataset.parquet"
        cregit = ledger_cregit(done, name)
        if name in local or not src.is_file():
            continue
        if cregit not in (OLD_CREGIT, "noledger"):
            continue
        persons = done / f"{name}-persons.db"
        out.append(dict(project=name, run=run, rel=rel, sha=sha, src=src, cregit=cregit,
                        size=src.stat().st_size, persons=persons if persons.is_file() else None,
                        pin=read_pin(done)))
    return out


def read_pin(done: Path) -> dict | None:
    """state/pin.json (spot runs), else pin.from-run.json (split_run_ledgers.py)."""
    pin = done / "state" / "pin.json"
    if pin.is_file():
        return json.loads(pin.read_text())
    pin = done / "pin.from-run.json"
    if pin.is_file():
        d = json.loads(pin.read_text())
        if d.get("pinned_sha") and d.get("url"):
            return {"url": d["url"], "pinned_sha": d["pinned_sha"], "branch": d.get("branch")}
    return None


def pending(out_root: Path) -> list[str]:
    """Projects of MANIFESTS that are not settled (see the module text)."""
    want = set()
    for m in MANIFESTS:
        for line in (HERE / m).read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                want.add(line.split("\t")[0])
    settled = {p.name.removesuffix("-dataset.parquet") for p in LOCAL.rglob("*-dataset.parquet")}
    for row in read_manifest(out_root / "manifest.tsv").values():
        if row["status"] in ("ok", "refused"):
            settled.add(row["project"])
    failed = HERE / "failed-projects.tsv"
    if failed.is_file():
        lines = failed.read_text(encoding="utf-8").splitlines()
        cols = lines[0].split("\t")
        for line in lines[1:]:
            d = dict(zip(cols, line.split("\t")))
            if d.get("outcome") == "failed":
                settled.add(d["project"])
    return sorted(want - settled)


def read_manifest(path: Path) -> dict:
    last = {}
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[1:]:
            row = dict(zip(MANIFEST_COLS, line.split("\t")))
            last[row["rel_path"]] = row
    return last


LOCK = threading.Lock()


def append_manifest(path: Path, row: dict) -> None:
    with LOCK:
        new = not path.exists() or path.stat().st_size == 0
        with path.open("a", encoding="utf-8") as fh:
            if new:
                fh.write("\t".join(MANIFEST_COLS) + "\n")
            fh.write("\t".join(str(row.get(c, "")).replace("\t", " ").replace("\n", " ")
                               for c in MANIFEST_COLS) + "\n")


class Slots:
    """Two slots; a big project takes both."""

    def __init__(self, n: int):
        self.free, self.cv = n, threading.Condition()

    def take(self, k: int):
        with self.cv:
            self.cv.wait_for(lambda: self.free >= k)
            self.free -= k

    def give(self, k: int):
        with self.cv:
            self.free += k
            self.cv.notify_all()


def git(args: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {r.stderr.strip()[-300:]}")
    return r.stdout


def pinned_clone(pin: dict, dest: Path) -> None:
    """What pin.py leaves: a bare clone with one branch at pinned_sha and no other ref; here
    with the commits only."""
    sha, branch = pin["pinned_sha"], pin.get("branch") or "master"
    git(["clone", "-q", "--bare", "--filter=tree:0", pin["url"], str(dest)])
    if subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=dest).returncode:
        git(["fetch", "-q", "--no-tags", "--filter=tree:0", "origin", sha], cwd=dest)
    for ref in git(["for-each-ref", "--format=%(refname)"], cwd=dest).splitlines():
        git(["update-ref", "-d", ref], cwd=dest)
    git(["update-ref", f"refs/heads/{branch}", sha], cwd=dest)
    git(["symbolic-ref", "HEAD", f"refs/heads/{branch}"], cwd=dest)
    if git(["rev-parse", "HEAD"], cwd=dest).strip() != sha:
        raise RuntimeError(f"pinned clone HEAD is not {sha}")


def rebuild_persons(git_dir: Path, db: Path, java_opts: str) -> None:
    """Step 5 of run_pipeline_process.sh: java -jar PERSONS_JAR REPO XLS DB."""
    r = subprocess.run(["java", *java_opts.split(), "-jar", str(PERSONS_JAR), str(git_dir),
                        str(db.with_suffix(".xls")), str(db)], capture_output=True, text=True)
    if r.returncode != 0 or not db.is_file():
        raise RuntimeError(f"persons jar failed (exit {r.returncode}): "
                           f"{(r.stdout + r.stderr).strip()[-300:]}")


def commits_of(con, src: Path) -> int:
    return con.execute("SELECT max(try_cast(commits AS BIGINT)) FROM read_parquet($p)",
                       {"p": str(src)}).fetchone()[0] or 0


def changed_commits(src: Path, dst: Path, memory_limit: str, spill: Path) -> int:
    """Commits whose 15 footer values differ between the two files (one tuple per commit)."""
    import duckdb

    con = duckdb.connect(config={"memory_limit": memory_limit, "threads": 2,
                                 "temp_directory": str(spill)})
    try:
        cols = ", ".join(f'"{c}"' for c in FOOTERS)
        return con.execute(
            f"SELECT count(DISTINCT original_commit_sha) FROM ("
            f"SELECT DISTINCT original_commit_sha, {cols} FROM read_parquet($d) EXCEPT "
            f"SELECT DISTINCT original_commit_sha, {cols} FROM read_parquet($s))",
            {"s": str(src), "d": str(dst)}).fetchone()[0]
    finally:
        con.close()
        shutil.rmtree(spill, ignore_errors=True)


def one(item: dict, args, slots: Slots) -> dict:
    out_dir = args.out_root / item["rel"]
    name = item["project"]
    final = out_dir / f"{name}-dataset.parquet"
    part = out_dir / f".{name}-dataset.parquet.partial"
    work = args.out_root / ".work" / name
    log = args.out_root / "logs" / f"{name}.log"
    rep = args.out_root / "reports" / f"{name}.tsv"
    row = dict(project=name, run=item["run"], rel_path=item["rel"], cregit=item["cregit"])
    k = 2 if item["big"] else 1
    slots.take(k)
    t0 = time.monotonic()
    try:
        if (args.out_root / "STOP").exists():
            row.update(status="stopped")
            return row
        print(f"{time.strftime('%H:%M:%S')} start {item['rel']} ({item['size'] / 1e6:.0f} MB, "
              f"{'alone' if item['big'] else 'shared'})", flush=True)
        row["input_sha256"] = sha256(item["src"])
        if row["input_sha256"] != item["sha"]:
            row.update(status="input_mismatch", note=f"verified.tsv has {item['sha']}")
            return row
        out_dir.mkdir(parents=True, exist_ok=True)
        log.parent.mkdir(parents=True, exist_ok=True)
        rep.parent.mkdir(parents=True, exist_ok=True)
        part.unlink(missing_ok=True)
        rep.unlink(missing_ok=True)
        shutil.rmtree(out_dir / ".footer-spill", ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="1",
                   GIT_CONFIG_KEY_0="url.git://git.savannah.gnu.org/.insteadOf",
                   GIT_CONFIG_VALUE_0="https://git.savannah.gnu.org/git/")
        cmd = [sys.executable, "-I", str(TOOL), str(item["src"]), "--out", str(part),
               "--work-dir", str(work / "tool"), f"--java-opts={args.java_opts}",
               "--memory-limit", args.memory_limit, "--threads", str(args.threads),
               "--report", str(rep)]
        persons = item["persons"]
        if persons is None and item["pin"] is None:
            row.update(status="no_persons_db", note="no persons DB and no pinned commit")
            return row
        if item["pin"] is not None:
            work.mkdir(parents=True)
            git_dir = work / f"{name}.git"
            try:
                pinned_clone(item["pin"], git_dir)
            except RuntimeError as e:
                row.update(status="clone_failed", note=str(e)[:400])
                return row
            cmd += ["--git-dir", str(git_dir)]
            row["note"] = "pinned"
        if persons is None:
            persons = work / f"{name}-persons.db"
            rebuild_persons(git_dir, persons, args.java_opts)
            cmd += ["--persons-db", str(persons)]
            row["note"] = "pinned persons_db=rebuilt"
        with log.open("w", encoding="utf-8") as fh:
            fh.write(" ".join(cmd) + "\n")
            fh.flush()
            r = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, env=env)
        text = log.read_text(encoding="utf-8", errors="replace")
        if r.returncode != 0 or not part.is_file():
            fail = [ln for ln in text.splitlines() if ln.startswith("FAIL")]
            note = (fail[-1] if fail else (text.strip().splitlines() or [""])[-1])[:400]
            status = ("clone_failed" if "git clone" in note else
                      "compare_failed" if "does not match" in note else
                      "refused" if fail else f"error_rc{r.returncode}")
            part.unlink(missing_ok=True)
            row.update(status=status, note=(row.get("note", "") + " " + note).strip())
            return row
        rec = {}
        if rep.is_file():
            lines = rep.read_text(encoding="utf-8").splitlines()
            rec = dict(zip(lines[0].split("\t"), lines[-1].split("\t")))
        row.update(rows=rec.get("rows", ""), commits=rec.get("commits", ""),
                   before=rec.get("before", ""), after=rec.get("after", ""),
                   clone_s=rec.get("clone_s", ""), parse_s=rec.get("parse_s", ""),
                   rewrite_s=rec.get("rewrite_s", ""))
        row["changed_commits"] = changed_commits(item["src"], part, args.memory_limit,
                                                 args.out_root / ".work" / f"{name}.spill")
        row["output_sha256"] = sha256(part)
        shutil.copy2(persons, out_dir / f"{name}-persons.db")
        os.replace(part, final)
        row.update(status="ok")
        return row
    except Exception as e:  # recorded; the job goes on
        part.unlink(missing_ok=True)
        row.update(status="error", note=f"{type(e).__name__}: {e}"[:400])
        return row
    finally:
        shutil.rmtree(work, ignore_errors=True)
        row["seconds"] = round(time.monotonic() - t0, 1)
        row["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if row.get("status") != "stopped":
            append_manifest(args.out_root / "manifest.tsv", row)
            print(f"{time.strftime('%H:%M:%S')} {row['status']} {item['rel']} "
                  f"{row['seconds']} s changed={row.get('changed_commits', '')} "
                  f"{row.get('note', '')}", flush=True)
        slots.give(k)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cloud", type=Path, default=CLOUD)
    ap.add_argument("--out-root", type=Path, default=OUT_ROOT)
    ap.add_argument("--list", action="store_true", help="print the counts and exit")
    ap.add_argument("--only", action="append", default=[], help="project name (repeat)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=2)
    retry = ap.add_mutually_exclusive_group()
    retry.add_argument("--retry-failed", action="store_true", help="retry every status")
    retry.add_argument("--retry-transient", action="store_true",
                       help="retry only the statuses in TRANSIENT")
    ap.add_argument("--pending", action="store_true",
                    help="print the projects that are not settled; exit 0 when none")
    ap.add_argument("--java-opts", default="-Xmx3g")
    ap.add_argument("--memory-limit", default="3GB")
    ap.add_argument("--threads", type=int, default=2)
    args = ap.parse_args(argv)

    if args.pending:
        left = pending(args.out_root)
        for name in left:
            print(name)
        print(f"{len(left)} projects not settled", flush=True)
        return 0 if not left else 3

    import duckdb

    items = inputs(args.cloud)
    last = read_manifest(args.out_root / "manifest.tsv")
    todo, counts = [], {}
    for it in items:
        c = counts.setdefault(it["run"], {"in_scope": 0, "ok": 0, "failed": 0, "todo": 0})
        c["in_scope"] += 1
        prev = last.get(it["rel"])
        final = args.out_root / it["rel"] / f"{it['project']}-dataset.parquet"
        if prev and prev["status"] == "ok" and final.is_file():
            c["ok"] += 1
            continue
        if prev and prev["status"] != "ok" and not (
                args.retry_failed or (args.retry_transient and (
                    prev["status"] in TRANSIENT or prev["status"].startswith("error")))):
            c["failed"] += 1
            continue
        if args.only and it["project"] not in args.only:
            continue
        c["todo"] += 1
        todo.append(it)
    print("run\tin_scope\tok\tfailed\ttodo")
    for run in RUNS:
        c = counts.get(run, {"in_scope": 0, "ok": 0, "failed": 0, "todo": 0})
        print(f"{run}\t{c['in_scope']}\t{c['ok']}\t{c['failed']}\t{c['todo']}")
    print(f"total\t{sum(c['in_scope'] for c in counts.values())}\t"
          f"{sum(c['ok'] for c in counts.values())}\t"
          f"{sum(c['failed'] for c in counts.values())}\t{len(todo)}", flush=True)
    if args.list:
        return 0
    todo.sort(key=lambda it: it["size"])
    if args.limit:
        todo = todo[:args.limit]
    con = duckdb.connect(config={"threads": 2, "memory_limit": "1GB"})
    for it in todo:
        it["big"] = commits_of(con, it["src"]) > BIG_COMMITS
    con.close()
    args.out_root.mkdir(parents=True, exist_ok=True)
    slots = Slots(args.jobs)
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        rows = list(ex.map(lambda it: one(it, args, slots), todo))
    bad = [r for r in rows if r.get("status") not in ("ok", "stopped")]
    print(f"done: {len(rows) - len(bad)} ok or stopped, {len(bad)} not ok", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
