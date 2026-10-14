#!/usr/bin/env python3
"""List every project that failed at least once in the census, from the ctp ledgers.

    python3 failed_projects.py LEDGER_OR_DIR... > failed-projects.tsv

Reads each ledger.jsonl that it finds (a directory is searched recursively; the done/ copies and
the dry runs are skipped). The same record can be in several copies (live/, backup-ledger/,
final/<instance>/): a record is counted once per (run_id, project, attempt, step, status,
start_utc). The run name is the path of the ledger under the S3 bucket, up to /live, /final or
/backup-ledger.

One output row per (run, project) with at least one failed record:
  outcome   done-after-retry: a later attempt finished the project
            in-progress: an attempt started after the last failure and has not ended
            failed: no attempt finished it and no attempt runs now
The reason column is not here: it comes from the pipeline logs (see failed-projects.md).
"""
import json
import os
import re
import sys
from collections import defaultdict


def ledger_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p, p
            continue
        for root, _dirs, files in os.walk(p):
            rel = os.path.relpath(root, p)
            if "/done/" in f"/{rel}/" or "dryrun" in rel:
                continue
            for f in files:
                if f.startswith("ledger") and f.endswith(".jsonl") or f.endswith("_ledger.jsonl") \
                        or re.match(r".*_ledger\.\w+\.jsonl$", f):
                    yield os.path.join(root, f), os.path.join(rel, f)


def run_name(rel):
    rel = rel.replace(os.sep, "/")
    m = re.match(r"(.*?)/(live|final|backup-ledger)(/|$)", rel)
    if m:
        return m.group(1)
    m = re.match(r"(?:backup-ledger/)?(.*?)_live_ledger(?:\.(\w+))?\.jsonl$", os.path.basename(rel))
    if m:  # flat backup copies: batch3_a_live_ledger.a1.jsonl -> batch3/a1
        base, part = m.group(1).replace("_", "/"), m.group(2)
        if part:
            base = base.rsplit("/", 1)[0] + "/" + part if "/" in base else base + "/" + part
        return base
    return "batch1-local"  # a ledger outside the S3 copy: the local batch 1 run


def main(argv):
    seen = set()
    recs = defaultdict(list)  # (run, project) -> records
    for path, rel in ledger_files(argv):
        run = run_name(rel)
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                proj = d.get("project")
                if not proj:
                    continue
                key = (d.get("run_id"), proj, d.get("attempt"), d.get("step"), d.get("status"),
                       d.get("start_utc"))
                if key in seen:
                    continue
                seen.add(key)
                recs[(run, proj)].append(d)

    cols = ["run", "project", "size_class", "outcome", "failed_attempts", "failed_steps",
            "first_failure_utc", "last_failure_utc", "cregit_commit", "pinned_sha", "snapshot_sha"]
    print("\t".join(cols))
    rows = []
    for (run, proj), rs in recs.items():
        fails = [r for r in rs if r.get("step") == "project" and r.get("status") == "failed"]
        if not fails:
            continue
        done = any(r.get("step") == "project" and r.get("status") == "done" for r in rs)
        steps = sorted({r.get("failed_step") or "?" for r in fails})
        last = max(fails, key=lambda r: r.get("end_utc") or "")
        first = min(fails, key=lambda r: r.get("end_utc") or "")
        later = [r for r in rs if r.get("status") == "started"
                 and (r.get("start_utc") or "") > (last.get("end_utc") or "")]
        outcome = "done-after-retry" if done else "in-progress" if later else "failed"
        rows.append([run, proj, (last.get("manifest_row") or {}).get("size_class", ""),
                     outcome, str(len(fails)), ",".join(steps),
                     first.get("end_utc", ""), last.get("end_utc", ""),
                     ((last.get("tools") or {}).get("cregit_commit") or "")[:7],
                     (last.get("pinned_sha") or "")[:7], (last.get("snapshot_sha") or "")[:7]])
    order = {"failed": 0, "in-progress": 1, "done-after-retry": 2}
    for r in sorted(rows, key=lambda r: (order[r[3]], r[0], r[1])):
        print("\t".join(r))


if __name__ == "__main__":
    main(sys.argv[1:])
