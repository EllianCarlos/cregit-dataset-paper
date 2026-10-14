#!/usr/bin/env python3
"""ab_compare.py DIR_A DIR_B: compare census batch3a (4 XFS filesystems) with batch3b (RAID0).

Each DIR is a local copy of s3://${RUNNER_BUCKET}/batch3/<a|b>/done/, made with
  aws s3 sync s3://${RUNNER_BUCKET}/batch3/a/done/ ab/a/ --exclude '*.parquet'
(the Parquets are not needed). Per project it reads state/logs/pipeline-*.log (the newest one):
step 2 seconds ("completed in Ns" after the "Step 2" header) and commitsProcessed (blobExec done
line), so step-2 commits/s = commits / seconds. From the ledger.jsonl snapshot it takes the
project's pipeline start and its final row end. Prints per side: projects, median and total
step-2 commits/s, median pipeline minutes, and projects/hour = projects / (last end - first start)
in hours. Read-only; nothing is uploaded.
"""
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

HEADER = re.compile(r"^\s*Step (\d+) — ")
DONE = re.compile(r"✓ completed in (\d+)s")
COMMITS = re.compile(r"blobExec done: commitsProcessed=(\d+)")


def step2(log):
    step, secs, commits = None, None, None
    for line in log.read_text(errors="replace").splitlines():
        m = HEADER.match(line)
        if m:
            step = int(m.group(1))
            continue
        if step == 2:
            c = COMMITS.search(line)
            if c:
                commits = int(c.group(1))
            d = DONE.search(line)
            if d:
                secs = int(d.group(1))
    return commits, secs


def t(s):
    return datetime.fromisoformat(s) if s else None


def side(root):
    rows = []
    for pdir in sorted(Path(root).iterdir()):
        if not (pdir / "OK").exists():
            continue
        logs = sorted((pdir / "state" / "logs").glob("pipeline-2*.log"))
        if not logs:
            continue
        commits, secs = step2(logs[-1])
        start = end = None
        led = pdir / "ledger.jsonl"
        if led.exists():
            for line in led.read_text().splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("project") != pdir.name:
                    continue
                if r.get("step") == "pipeline" and r.get("status") == "started":
                    start = t(r.get("start_utc"))
                if r.get("step") == "project":
                    end = t(r.get("end_utc"))
        rows.append((pdir.name, commits, secs, start, end))
    return rows


def report(label, rows):
    rates = [c / s for _, c, s, _, _ in rows if c and s]
    mins = [(e - s).total_seconds() / 60 for *_, s, e in rows if s and e]
    starts = [s for *_, s, _ in rows if s]
    ends = [e for *_, e in rows if e]
    hours = (max(ends) - min(starts)).total_seconds() / 3600 if starts and ends else 0
    tot_c = sum(c for _, c, s, _, _ in rows if c and s)
    tot_s = sum(s for _, c, s, _, _ in rows if c and s)
    print(f"{label}: {len(rows)} projects"
          f" | step 2 commits/s median {statistics.median(rates):.1f}, pooled {tot_c / tot_s:.1f}" if rates else f"{label}: {len(rows)} projects")
    if mins:
        print(f"   project minutes (pipeline start to final row) median {statistics.median(mins):.1f}")
    if hours:
        print(f"   projects/hour {len(rows) / hours:.1f} over {hours:.2f} h")


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    report("batch3a (4 XFS, 4x5 workers)", side(sys.argv[1]))
    report("batch3b (RAID0, 20 workers)", side(sys.argv[2]))
    print("Compare only projects of similar size; both halves are alternate rows in u order, so S/M mixes are alike.")


if __name__ == "__main__":
    main()
