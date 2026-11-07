#!/usr/bin/env python3
"""Write dataset v0 (S8, decisions D1 and D5): build_v0.py over every v1-raw file (ctp schema 2).

    run_v0.py --v1raw DIR --links DIR --out DIR --dest DEST [--jobs 88] [--threads 1]
              [--memory-limit 5GB] [--only NAME ...] [--limit N] [--min-rows N] [--max-rows N]

--v1raw is the output directory of final_merge.py (results.tsv and parquet/). --links holds
domain_links.parquet, project_links.parquet and links.json of build_links.py (links.json gives
organisations_version and mapping_sha256). For each project of results.tsv, largest first:
  1. check the sha256 of the v1-raw file against results.tsv;
  2. build_v0.py writes OUT/parquet/<p>-dataset.parquet (it checks the 67 kept columns by an
     order-sensitive hash, the column list and the footer); its mapping hash must be the one of
     links.json;
  3. check the row count against results.tsv;
  4. copy the file to DEST/parquet/ and check the size;
  5. append one row to OUT/results.tsv.
A project in OUT/results.tsv is done, so a second start continues. OUT/STOP stops the start of
new projects. At the end: OUT/SHA256SUMS, then SHA256SUMS, results.tsv and the link files go to
DEST. --min-rows and --max-rows select the projects by their row count, so the largest files can
run in their own pass with more memory (V0 runbook); the last pass to end writes SHA256SUMS.
DEST is an s3:// prefix (the aws CLI with the machine role) or a directory (tests).

--pseudonymize --salt-file S --registry R --psl PSL [--anon-dir DIR] [--no-scan] [--no-content-scan] (the final write,
2026-10-25): build_v0.py --pseudonymize for each project (the organisation columns and the pseudonyms
in one write; see build_v0.py). At the start, once: the full digest of the registry, its salt check
against S, its PSL hash, and the registry path must not be under --out or a directory DEST (the
registry holds the real identities and never goes to DEST). Each project then gets
--registry-sha256, and its output must name that registry. --max-failures N (default 20; 0 = no
limit, the default without --pseudonymize) writes OUT/STOP after N failed projects, so a gate that
fails every file stops the run early.
At the end DEST also gets pseudonymization.json (the registry sha256, the salt check, the PSL hash
and the options; no identity, no key).
Exit 0 all done, 1 some failed, 2 usage or a bad input.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "s7-run")]
from final_merge import LOCK, done_projects, log, put, rows_of, sha256  # noqa: E402

FAILS = [0]  # failed projects of this start (--max-failures)
RESULT_COLS = ("project", "input", "input_sha256", "output", "output_sha256", "rows", "input_bytes",
               "output_bytes", "seconds", "finished_utc", "detail")
LINK_FILES = ("domain_links.parquet", "project_links.parquet", "links.json")


def append_result(results: Path, row: dict) -> None:
    with LOCK:
        new = not results.is_file()
        with open(results, "a", newline="") as fh:
            w = csv.DictWriter(fh, RESULT_COLS, delimiter="\t", lineterminator="\n")
            if new:
                w.writeheader()
            w.writerow(row)


def one(row: dict, a) -> bool:
    p, t0 = row["project"], time.time()
    src = a.v1raw / row["output"]
    out = a.out / "parquet" / src.name
    try:
        if out.exists():  # a crash after the write: write it again
            out.unlink()
        got = sha256(src)
        if got != row["output_sha256"]:
            raise RuntimeError(f"v1-raw sha256 {got} is not {row['output_sha256']}")
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, "-I", str(a.build_v0), str(src), str(out), "--project", p,
                            "--project-links", str(a.links / "project_links.parquet"),
                            "--domain-links", str(a.links / "domain_links.parquet"),
                            "--organisations-version", a.organisations_version,
                            "--memory-limit", a.memory_limit, "--threads", str(a.threads)] + a.anon_args,
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"build_v0 rc {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}")
        detail = r.stdout.strip().splitlines()[-1][-300:] if r.stdout.strip() else ""
        if f"mapping {a.mapping_sha256[:12]}" not in detail:
            raise RuntimeError(f"the mapping hash of the output is not the one of links.json: {detail}")
        if a.pseudonymize and f"registry {a.registry_sha256[:12]}" not in detail:
            raise RuntimeError(f"the output does not name the registry {a.registry_sha256[:12]}: {detail}")
        rows = rows_of(out)
        if rows != int(row["rows"]):
            raise RuntimeError(f"{rows} rows, v1-raw results.tsv says {row['rows']}")
        osha, osize = sha256(out), out.stat().st_size
        size = put(out, a.dest, f"parquet/{out.name}")
        if size != osize:
            raise RuntimeError(f"DEST size {size} is not {osize}")
        append_result(a.out / "results.tsv", {
            "project": p, "input": row["output"], "input_sha256": got, "output": f"parquet/{out.name}",
            "output_sha256": osha, "rows": rows, "input_bytes": src.stat().st_size, "output_bytes": osize,
            "seconds": f"{time.time() - t0:.1f}",
            "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "detail": detail})
        log(f"OK {p}: {detail}, {time.time() - t0:.0f} s")
        return True
    except Exception as exc:  # one project fails, the others go on
        log(f"FAIL {p}: {exc}")
        with LOCK, open(a.out / "failed.tsv", "a") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\t{p}\t{str(exc)[:500]}\n")
        out.unlink(missing_ok=True)
        with LOCK:  # (log() takes LOCK too: it is called after the block)
            FAILS[0] += 1
            stop = bool(a.max_failures) and FAILS[0] >= a.max_failures and not (a.out / "STOP").exists()
            if stop:
                (a.out / "STOP").write_text(f"{FAILS[0]} failed projects (--max-failures {a.max_failures})\n")
        if stop:
            log(f"STOP written: {FAILS[0]} failed projects (--max-failures {a.max_failures})")
        return False


def finish(a, rows: list[dict]) -> bool:
    done = done_projects(a.out / "results.tsv")
    if not {r["project"] for r in rows} <= done:
        return False
    with open(a.out / "results.tsv", newline="") as fh:
        res = sorted(csv.DictReader(fh, delimiter="\t"), key=lambda r: r["output"])
    with open(a.out / "SHA256SUMS", "w") as fh:
        for r in res:
            fh.write(f"{r['output_sha256']}  {r['output']}\n")
    for name in LINK_FILES:
        shutil.copyfile(a.links / name, a.out / name)
    extra = ()
    if a.pseudonymize:
        (a.out / "pseudonymization.json").write_text(json.dumps(a.anon_info, indent=1, sort_keys=True) + "\n")
        extra = ("pseudonymization.json",)
    for name in ("SHA256SUMS", "results.tsv") + LINK_FILES + extra:
        put(a.out / name, a.dest, name)
    log(f"DONE: {len(res)} projects; SHA256SUMS and results.tsv are in {a.dest}")
    return True


def parse(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--v1raw", type=Path, required=True)
    ap.add_argument("--links", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dest", required=True, help="s3:// prefix or directory for the outputs")
    ap.add_argument("--jobs", type=int, default=88)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--memory-limit", default="5GB")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-rows", type=int, default=0, help="only projects with at least N rows")
    ap.add_argument("--max-rows", type=int, default=0, help="only projects with at most N rows (0: no limit)")
    ap.add_argument("--build-v0", type=Path, default=HERE / "build_v0.py")
    g = ap.add_argument_group("the fused write with pseudonymize.py (build_v0.py --pseudonymize)")
    g.add_argument("--pseudonymize", action="store_true")
    g.add_argument("--salt-file", type=Path)
    g.add_argument("--registry", type=Path)
    g.add_argument("--psl", type=Path)
    g.add_argument("--anon-dir", type=Path, help="folder of pseudonymize.py (default: build_v0.py's)")
    g.add_argument("--no-scan", action="store_true")
    g.add_argument("--no-content-scan", action="store_true", help="build_v0.py --no-content-scan")
    g.add_argument("--scan-threads", type=int, help="build_v0.py --scan-threads (the leak scan of each job)")
    g.add_argument("--max-failures", type=int, default=None,
                   help="write OUT/STOP after N failed projects (0: never; default 20 with --pseudonymize, else 0)")
    return ap.parse_args(argv)


def prepare_pseudonymize(a) -> str:
    """The checks of --pseudonymize at the start; sets a.anon_args, a.registry_sha256, a.anon_info.
    Returns '' or the text of a usage error (no value, no key in it)."""
    a.anon_args, a.registry_sha256, a.anon_info = [], "", {}
    if not a.pseudonymize:
        if any((a.salt_file, a.registry, a.psl, a.anon_dir, a.no_scan, a.no_content_scan, a.scan_threads)):
            return "--salt-file, --registry, --psl, --anon-dir, --no-scan and --no-content-scan need --pseudonymize"
        return ""
    miss = [o for o, v in (("--salt-file", a.salt_file), ("--registry", a.registry), ("--psl", a.psl)) if not v]
    if miss:
        return f"--pseudonymize needs {', '.join(miss)}"
    for f in (a.registry, a.psl):
        if not f.is_file():
            return f"{f} is not a file"
    import build_v0 as bv
    P = None
    try:
        P = bv.load_pseudonymize(a.anon_dir)
        roots = (str(a.out),) + (() if a.dest.startswith("s3://") else (a.dest,))
        P.check_registry_path(str(a.registry), roots)
        anon = bv.prepare_anon(P, a.salt_file, a.registry, a.psl)  # the full digest, once
    except Exception as exc:
        return P.safe_error(exc, None) if P else str(exc)
    a.registry_sha256 = anon.registry_sha256
    con = bv.duckdb.connect()
    salt_check = P.registry_meta(con, str(a.registry)).get("salt_check")
    con.close()
    a.anon_info = {"pseudonymization_version": P.SCHEME_VERSION, "registry_sha256": anon.registry_sha256,
                   "salt_check": salt_check, "psl_sha256": anon.psl["sha256"],
                   "email_domain": P.DEFAULT_EMAIL_DOMAIN, "person_domain_at": anon.domain_at,
                   "commit_summary": anon.summary_mode, "leak_scan": not a.no_scan,
                   "leak_scan_content_columns": not (a.no_scan or a.no_content_scan)}
    a.anon_args = ["--pseudonymize", "--salt-file", str(a.salt_file), "--registry", str(a.registry),
                   "--registry-sha256", anon.registry_sha256, "--psl", str(a.psl)]
    a.anon_args += (["--anon-dir", str(a.anon_dir)] if a.anon_dir else []) + (["--no-scan"] if a.no_scan else []) \
        + (["--no-content-scan"] if a.no_content_scan else []) \
        + (["--scan-threads", str(a.scan_threads)] if a.scan_threads else [])
    return ""


def main(argv=None) -> int:
    a = parse(argv)
    files = [a.v1raw / "results.tsv", a.build_v0] + [a.links / n for n in LINK_FILES]
    for f in files:
        if not f.is_file():
            print(f"usage: {f} is not a file", file=sys.stderr)
            return 2
    FAILS[0] = 0
    if a.max_failures is None:  # the old path keeps its behaviour
        a.max_failures = 20 if a.pseudonymize else 0
    err = prepare_pseudonymize(a)
    if err:
        print(f"usage: {err}", file=sys.stderr)
        return 2
    lj = json.loads((a.links / "links.json").read_text())
    want = lj["outputs"]
    a.organisations_version, a.mapping_sha256 = lj.get("organisations_version"), lj.get("mapping_sha256")
    if not a.organisations_version or not a.mapping_sha256:
        print("bad input: links.json has no organisations_version or mapping_sha256 (build_links.py of "
              "2026-10-19 or later)", file=sys.stderr)
        return 2
    for name in ("domain_links.parquet", "project_links.parquet"):
        if sha256(a.links / name) != want[name]:
            print(f"bad input: the sha256 of {name} is not the one in links.json", file=sys.stderr)
            return 2
    with open(a.v1raw / "results.tsv", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    if len({r["project"] for r in rows}) != len(rows):
        print("bad input: a project repeats in the v1-raw results.tsv", file=sys.stderr)
        return 2
    a.out.mkdir(parents=True, exist_ok=True)
    done = done_projects(a.out / "results.tsv")
    todo = [r for r in rows if r["project"] not in done and (not a.only or r["project"] in a.only)
            and int(r["rows"]) >= a.min_rows and (not a.max_rows or int(r["rows"]) <= a.max_rows)]
    todo.sort(key=lambda r: -int(r["output_bytes"]))
    if a.limit:
        todo = todo[:a.limit]
    log(f"{len(rows)} projects, {len(done)} done, {len(todo)} to do; jobs {a.jobs}, threads {a.threads}, "
        f"memory {a.memory_limit}" + (f"; pseudonymize, registry {a.registry_sha256[:12]}" if a.pseudonymize else ""))
    ok = True
    with ThreadPoolExecutor(a.jobs) as ex:
        futures = []
        for r in todo:
            if (a.out / "STOP").exists():
                log("STOP file: no new projects")
                break
            futures.append(ex.submit(lambda r=r: (a.out / "STOP").exists() or one(r, a)))
        for f in futures:
            ok = f.result() and ok
    if not (a.only or a.limit):
        finish(a, rows)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
