#!/usr/bin/env python3
"""Census funnel: for each batch, how many manifest projects passed each ctp stage.

Reads the local batch 1 ledger and, with --s3, copies the EC2 ledgers from the
census bucket into a temporary directory (read-only for the bucket). A project
counts at a stage when the ledger of its batch has an `ok` row for that stage
(distinct projects; repeated attempts count once). `done` is the ledger's
`project done` row. The S3 runs also count the `done/<project>/OK` markers,
because a spot restart starts a fresh ledger.

  python3 census_funnel.py --s3            # print the Markdown tables
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def projects_dir():
    """CREGIT_PROJECTS: the directory that holds cregit-workspace and the clones of ctp and cregit.
    Default: the nearest parent directory of this file that holds cregit-workspace."""
    if os.environ.get("CREGIT_PROJECTS"):
        return os.environ["CREGIT_PROJECTS"]
    d = HERE
    while d != os.path.dirname(d) and not os.path.isdir(os.path.join(d, "cregit-workspace")):
        d = os.path.dirname(d)
    return d


def runner_value(name):
    """The value of NAME: the environment, else runner/runner.env (local only; the file
    runner/runner.env.example gives the names). Lines are NAME=VALUE or NAME='VALUE'."""
    if os.environ.get(name):
        return os.environ[name]
    path = os.path.join(HERE, "runner", "runner.env")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key == name:
                    return value[1:-1] if len(value) >= 2 and value[0] == value[-1] == "'" else value
    sys.exit(f"error: set {name}, or give it in {path} (see runner/runner.env.example)")


LOCAL_LEDGER = os.path.join(
    projects_dir(), "cregit-token-pipeline/.claude/worktrees/agent-a0a3254f563a6a4b5/ledger.jsonl")
BUCKET = "s3://" + runner_value("RUNNER_BUCKET")
STAGES = ["resolve", "clone", "pipeline", "firm", "validate", "schema", "join"]

# batch -> (manifests, local ledgers, S3 prefixes). Under each prefix the script reads every
# live ledger (`*/live/ledger*.jsonl`, not the `.test.` copies) and every `done/<project>/OK`
# marker. batch1rest is the rest of batch 1, moved to the spot instances on 2026-10-09.
BATCHES = [
    ("1", ["manifest.batch1.tsv"], [LOCAL_LEDGER], ["batch1rest/"]),
    ("2", ["manifest.batch2.tsv"], [], ["batch2/"]),
    ("3 L", ["manifest.batch3L.tsv"], [], ["batch3L/"]),
    ("3a", ["manifest.batch3a.tsv"], [], ["batch3/a/"]),
    ("3b", ["manifest.batch3b.tsv"], [], ["batch3/b/"]),
    ("4", [f"manifest.batch4p{k}.tsv" for k in (1, 2, 3)], [], ["batch4/"]),
    ("5", ["manifest.batch5.tsv"], [], ["batch5/", "batch5L/"]),
]


def aws(*args):
    env = dict(os.environ, AWS_PROFILE=runner_value("RUNNER_AWS_PROFILE"), AWS_REGION="us-west-2", AWS_PAGER="")
    return subprocess.run(["aws", *args], env=env, capture_output=True, text=True)


def manifest_names(paths):
    names = []
    for p in paths:
        with open(os.path.join(HERE, p), encoding="utf-8") as f:
            rows = [l for l in f if l.strip() and not l.startswith("#")]
        for row in csv.reader(rows, delimiter="\t"):
            if row and row[0] != "name":
                names.append(row[0])
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s3", action="store_true", help="also read the EC2 ledgers from S3")
    args = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="census-funnel-")
    total = defaultdict(int)
    out = []
    listing = []
    if args.s3:
        r = aws("s3", "ls", f"{BUCKET}/", "--recursive")
        listing = [line.split()[-1] for line in r.stdout.splitlines() if line.strip()]
    for batch, manifests, local, prefixes in BATCHES:
        names = set(manifest_names(manifests))
        ledgers = list(local)
        ok = defaultdict(set)
        if prefixes and not args.s3:
            continue
        for key in listing:
            if not any(key.startswith(p) for p in prefixes):
                continue
            base = key.rsplit("/", 1)[-1]
            if "/live/" in key and base.startswith("ledger") and base.endswith(".jsonl") and ".test." not in base:
                dst = os.path.join(tmp, key.replace("/", "_"))
                if aws("s3", "cp", f"{BUCKET}/{key}", dst, "--only-show-errors").returncode == 0:
                    ledgers.append(dst)
            elif "/done/" in key and base == "OK":
                ok["done"].add(key.split("/")[-2])
        started, failed = set(), set()
        for path in ledgers:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    p, step, st = r.get("project"), r.get("step"), r.get("status")
                    if p not in names:
                        continue
                    if st == "started":
                        started.add(p)
                    if step == "project" and st == "done":
                        ok["done"].add(p)
                    elif step == "project" and st == "failed":
                        failed.add(p)
                    elif st == "ok" and step in STAGES:
                        ok[step].add(p)
        done = ok["done"] & names
        # a done project passed every stage, even if this ledger misses the row
        counts = {s: len((ok[s] | done) & names) for s in STAGES}
        counts.update(manifest=len(names), started=len((started | done) & names), done=len(done),
                      failed_not_done=len((failed & names) - done),
                      running_or_queued=len(names - done))
        out.append((batch, counts))
        for k, v in counts.items():
            total[k] += v
    cols = ["manifest", "started", *STAGES, "done", "failed_not_done", "running_or_queued"]
    print("| batch | " + " | ".join(cols) + " |")
    print("| --- |" + " ---: |" * len(cols))
    for batch, c in out + [("**total**", total)]:
        print(f"| {batch} | " + " | ".join(str(c[k]) for k in cols) + " |")


if __name__ == "__main__":
    sys.exit(main())
