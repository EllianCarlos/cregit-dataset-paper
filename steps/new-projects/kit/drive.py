#!/usr/bin/env python3
"""Run the projects of a manifest through ctp, one systemd unit for each, and
measure each one.

    drive.py --manifest M.tsv --ctp-dir DIR --ctp-config CFG --out-dir OUT
             --metrics metrics.tsv [--parallel N] [--order FILE] [--user]
             [--uid USER] [--only A,B] [--stop-file F] -- <ctp run options>

Each project runs as `ctp.py run --manifest M.tsv --only NAME <options>` in a
transient unit (systemd-run --wait, CPU and memory accounting). At the end the
unit writes its cgroup counters (cpu.stat usage_usec, memory.peak). One row of
metrics.tsv for each project:

  project rc wall_s cpu_s mem_peak_bytes max_tree_rss_mb rows alive_rows
  removed_rows bytes history_paths replay_s build_s generate_s blame_s
  tokenize_s blame_tool widest_commit start_utc end_utc

The step times come from OUT/NAME/pipeline.log (the runner's step lines and
the time stamps of the token history lines). max_tree_rss_mb is the largest
tree RSS that ctp sampled (resources.tsv). memory.peak also counts the page
cache of the unit. The projects start in the order of --order (one name per
line; default: the manifest order), N at a time. A project with a metrics row
is not run again.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ("project", "rc", "wall_s", "cpu_s", "mem_peak_bytes", "max_tree_rss_mb", "rows",
          "alive_rows", "removed_rows", "bytes", "history_paths", "replay_s", "build_s",
          "generate_s", "blame_s", "tokenize_s", "blame_tool", "widest_commit",
          "start_utc", "end_utc")
LOCK = threading.Lock()
STAMP = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] (.*)$")
STEP_DONE = re.compile(r"^\s+✓ completed in (\d+)s")
STEP_NAME = re.compile(r"^\s+Step (\d+) — ")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def step_times(log: Path) -> dict:
    """Seconds of the runner steps of the last attempt, and of the token
    history parts of step 10 (from the log time stamps)."""
    out = {}
    if not log.is_file():
        return out
    step, steps, stamps = None, {}, []
    for line in log.read_text(errors="replace").splitlines():
        m = STEP_NAME.match(line)
        if m:
            step = int(m.group(1))
            if step == 1:
                steps, stamps = {}, []
        m = STEP_DONE.match(line)
        if m and step is not None:
            steps[step] = int(m.group(1))
        m = STAMP.match(line)
        if m:
            stamps.append((datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), m.group(2)))
    out["tokenize_s"] = steps.get(2, "")
    out["blame_s"] = steps.get(7, "")
    # the last replay of the log, then the first build line and the dataset line after it
    idx = [i for i, (_, msg) in enumerate(stamps) if msg.startswith("token history: replay of")]
    if idx:
        tail = stamps[idx[-1]:]
        t_replay = tail[0][0]
        t_build = next((t for t, msg in tail if msg.startswith("build: ") and "token rows" in msg), None)
        t_wrote = next((t for t, msg in tail if msg.startswith("build: wrote ")), None)
        t_done = next((t for t, msg in tail if msg.startswith("dataset written")), None)
        if t_build:
            out["replay_s"] = int((t_build - t_replay).total_seconds())
        if t_build and t_wrote:
            out["build_s"] = int((t_wrote - t_build).total_seconds())
        if t_wrote and t_done:
            out["generate_s"] = int((t_done - t_wrote).total_seconds())
    elif 10 in steps:
        out["generate_s"] = steps[10]
    return out


def file_counts(path: Path) -> dict:
    if not path.is_file():
        return {}
    import duckdb
    rows, alive = duckdb.execute(
        "SELECT count(*), count(*) FILTER (WHERE token_index IS NOT NULL) "
        "FROM read_parquet(?)", [str(path)]).fetchone()
    return {"rows": rows, "alive_rows": alive, "removed_rows": rows - alive,
            "bytes": path.stat().st_size}


def max_rss(ctp_dir: Path, name: str) -> str:
    f = ctp_dir / "resources.tsv"
    if not f.is_file():
        return ""
    best = 0
    with f.open() as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r.get("project") == name:
                best = max(best, int(float(r.get("tree_rss_mb") or 0)))
    return str(best)


def run_one(args, name: str, ctp_args: list[str]) -> dict:
    out_dir = Path(args.out_dir)
    probe = out_dir / ".units"
    probe.mkdir(parents=True, exist_ok=True)
    if args.uid:  # the unit runs as that user and writes its log and counters here
        import shutil
        shutil.chown(probe, args.uid)
    counters = probe / f"{name}.cgroup"
    counters.unlink(missing_ok=True)
    cmd = " ".join(map(sh, [sys.executable if not args.python else args.python,
                            str(Path(args.ctp_dir) / "ctp.py"), "run",
                            "--manifest", str(Path(args.manifest).resolve()),
                            "--only", name, *ctp_args]))
    body = (f"cd {sh(args.ctp_dir)} && {cmd} >> {sh(str(probe / (name + '.log')))} 2>&1; rc=$?; "
            f"cg=/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup); "
            f"echo \"cpu_usec $(awk '/usage_usec/{{print $2}}' $cg/cpu.stat) "
            f"mem_peak $(cat $cg/memory.peak 2>/dev/null || echo 0) rc $rc\" > {sh(str(counters))}; "
            f"exit $rc")
    unit = "ta-" + re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    sr = ["systemd-run", "--wait", "--collect", "--unit", unit, "-p", "CPUAccounting=yes",
          "-p", "MemoryAccounting=yes", "--setenv", f"CTP_CONFIG={args.ctp_config}"]
    if not args.uid:  # with --uid, --setenv gives PATH and HOME of that user
        sr += ["--setenv", f"PATH={os.environ['PATH']}", "--setenv", f"HOME={os.environ['HOME']}"]
    if args.user:
        sr.insert(1, "--user")
    if args.uid:
        sr += ["--uid", args.uid]
    for kv in args.setenv:
        sr += ["--setenv", kv]
    t0, start = time.time(), now()
    proc = subprocess.run(sr + ["bash", "-c", body], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    wall = round(time.time() - t0)
    got = dict(zip(*[iter(counters.read_text().split())] * 2)) if counters.is_file() else {}
    row = {"project": name, "rc": got.get("rc", proc.returncode), "wall_s": wall,
           "cpu_s": round(int(got.get("cpu_usec", 0)) / 1e6),
           "mem_peak_bytes": got.get("mem_peak", ""), "start_utc": start, "end_utc": now(),
           "max_tree_rss_mb": max_rss(Path(args.ctp_dir), name)}
    work = out_dir / name
    try:
        row.update(step_times(work / "pipeline.log"))
    except Exception as e:  # a log that cannot be read must not lose the row
        print(f"[{now()}] {name}: step times: {type(e).__name__}: {e}", flush=True)
    if str(row["rc"]) == "0":
        try:
            row.update(file_counts(work / f"{name}-dataset.parquet"))
        except Exception as e:
            print(f"[{now()}] {name}: file counts: {type(e).__name__}: {e}", flush=True)
    done = work / "history" / "paths-done.txt"
    if done.is_file():
        row["history_paths"] = sum(1 for line in done.open() if line.strip())
    shape = Path(args.ctp_dir) / "state" / name / "shape.json"
    if shape.is_file():
        s = json.loads(shape.read_text())
        row["blame_tool"], row["widest_commit"] = s["tool"], s["widest_commit"]
    return row


def sh(s: str) -> str:
    return "'" + str(s).replace("'", "'\\''") + "'"


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    ctp_args = []
    if "--" in argv:
        i = argv.index("--")
        argv, ctp_args = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--ctp-dir", required=True)
    ap.add_argument("--ctp-config", required=True)
    ap.add_argument("--out-dir", required=True, help="the output_dir of the ctp config")
    ap.add_argument("--metrics", required=True)
    ap.add_argument("--parallel", type=int, default=1)
    ap.add_argument("--order", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--user", action="store_true", help="systemd-run --user")
    ap.add_argument("--uid", default="", help="systemd-run --uid (as root)")
    ap.add_argument("--python", default="", help="the python of ctp.py (default: this one)")
    ap.add_argument("--setenv", action="append", default=[])
    ap.add_argument("--stop-file", default="",
                    help="when this file exists, start no new project")
    args = ap.parse_args(argv)
    names = [line.split("\t")[0] for line in open(args.manifest)
             if line.strip() and not line.startswith("#")]
    if args.order:
        order = [n.strip() for n in open(args.order) if n.strip()]
        names = [n for n in order if n in names] + [n for n in names if n not in order]
    if args.only:
        keep = set(args.only.split(","))
        names = [n for n in names if n in keep]
    metrics = Path(args.metrics)
    done = set()
    if metrics.is_file():
        done = {r["project"] for r in csv.DictReader(metrics.open(), delimiter="\t")
                if str(r.get("rc")) == "0"}
    todo = [n for n in names if n not in done]
    print(f"[{now()}] drive: {len(todo)} projects ({len(done)} done), {args.parallel} at a time",
          flush=True)

    def task(name):
        if args.stop_file and os.path.exists(args.stop_file):
            print(f"[{now()}] stop file: {name} not started", flush=True)
            return {"project": name, "rc": "stopped"}
        print(f"[{now()}] start {name}", flush=True)
        try:
            row = run_one(args, name, ctp_args)
        except Exception as e:
            print(f"[{now()}] {name}: {type(e).__name__}: {e}", flush=True)
            row = {"project": name, "rc": "error"}
        with LOCK:
            new = not metrics.is_file()
            with metrics.open("a") as f:
                if new:
                    f.write("\t".join(FIELDS) + "\n")
                f.write("\t".join(str(row.get(k, "")) for k in FIELDS) + "\n")
        print(f"[{now()}] end {name} rc={row['rc']} wall={row['wall_s']}s cpu={row['cpu_s']}s "
              f"rows={row.get('rows', '')}", flush=True)
        return row

    with ThreadPoolExecutor(args.parallel) as pool:
        rows = list(pool.map(task, todo))
    bad = [r["project"] for r in rows if str(r["rc"]) != "0"]
    print(f"[{now()}] drive: done, {len(rows) - len(bad)} ok, {len(bad)} failed {bad}", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
