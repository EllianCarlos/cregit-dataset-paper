#!/usr/bin/env python3
"""x3_plainblame.py: the PLAIN-BLAME count of the x1k files (kit x3, 2026-10-23).

    x3_plainblame.py --results RESULTS.tsv --logs ROOT --out plainblame.x1k.tsv --summary plainblame.x1k.json

RESULTS is results.tsv of the x1k merge (dataset-x1k/raw/): one row per file of the dataset; its
column `source` gives the rule (the rules of ../M0-plainblame-count.sh, the user, 2026-10-23):
  x1k-b        the newest log ROOT/done-full/<p>/state/logs/pipeline-2*.log: a retry starts again at
               step 2 and drops blame/, so the newest attempt made the Parquet;
  x1k-a        all logs ROOT/done-full/<p>/state/logs/pipeline-2*.log: resumed attempts keep blame/
               from step 7, so each attempt adds files;
  x1k-pathfix  the newest log ROOT/done-pathfix/<p>/state/logs/pipeline-2*.log (the path-fix rerun made
               the Parquet of these rows, not the done-full run).
The extra machines blamed parts of two machine A rows; their files are not in the logs of A:
ROOT/rust-split/out/<k>/plainblame.log add to awslabs__aws-sdk-rust and ROOT/java-split/out/<k>/
plainblame.log to aws__aws-sdk-java. A PLAIN-BLAME line is a line that holds 'PLAIN-BLAME ' (as
grep -a -c 'PLAIN-BLAME ' of M0). cregit prints "PLAIN-BLAME <file> after <N> s of -C100" (57551d7,
14b8db4; 23e4ccb also "... after git exit 128 of -C100"). The count is the number of DISTINCT files
(the main session, 2026-10-23): a file that falls back in two attempts of an x1k-a row counts once.
For x1k-a the set is the union over all logs of the row and its extra-machine logs. The line count
stays in a second column, so both are visible.
Output columns: project, source, rule, log_dir, logs, newest_log, plain_blame_newest (distinct
files of the newest log), plain_blame_newest_lines, plain_blame_all_logs (distinct files of all
logs), plain_blame_all_logs_lines, plain_blame_extra (distinct files of the extra-machine logs),
plain_blame_extra_lines, plain_blame (the value of the rule: distinct files, the extra files in the
union) and plain_blame_lines (the lines of the rule plus the extra lines).
A row with no log has NA. The summary has the totals per source and the rows with no log. The files
hold counts and log names only (no file path of a project, no person data).
Exit 0 written (also with rows that have no log: see the summary), 2 usage.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

MARK = b"PLAIN-BLAME "
TAIL = re.compile(rb" after (?:[0-9]+ s|git exit [0-9]+) of -C100\s*$")
EXTRA = {"rust-split": "awslabs__aws-sdk-rust", "java-split": "aws__aws-sdk-java"}
RULES = {"x1k-b": ("newest", "done-full"), "x1k-a": ("all", "done-full"), "x1k-pathfix": ("newest", "done-pathfix")}
COLS = ("project", "source", "rule", "log_dir", "logs", "newest_log", "plain_blame_newest",
        "plain_blame_newest_lines", "plain_blame_all_logs", "plain_blame_all_logs_lines",
        "plain_blame_extra", "plain_blame_extra_lines", "plain_blame", "plain_blame_lines")


def scan(files) -> tuple[set, int]:
    """The distinct file paths of the PLAIN-BLAME lines of FILES, and the number of such lines."""
    names, lines = set(), 0
    for f in files:
        with open(f, "rb") as fh:
            for line in fh:
                i = line.find(MARK)
                if i < 0:
                    continue
                lines += 1
                rest = line[i + len(MARK):].rstrip(b"\r\n")
                names.add(TAIL.sub(b"", rest).strip())
    return names, lines


def extras(root: Path) -> dict[str, dict]:
    out = {}
    for d, project in EXTRA.items():
        logs = sorted((root / d / "out").glob("*/plainblame.log"))
        names, lines = scan(logs)
        out[project] = {"parts": len(logs), "lines": lines, "files": len(names), "names": names}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--logs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--summary", type=Path, required=True)
    a = ap.parse_args(argv)
    with open(a.results, newline="") as fh:
        res = list(csv.DictReader(fh, delimiter="\t"))
    if not res or not {"project", "source"} <= set(res[0]):
        print(f"usage: {a.results} needs the columns project and source", file=sys.stderr)
        return 2
    unknown = sorted({r["source"] for r in res} - set(RULES))
    if unknown:
        print(f"usage: unknown source values {unknown}", file=sys.stderr)
        return 2
    ex = extras(a.logs)
    for project in ex:
        src = next((r["source"] for r in res if r["project"] == project), None)
        if src not in (None, "x1k-a"):
            print(f"usage: {project} has source {src}, not x1k-a", file=sys.stderr)
            return 2
    rows, nolog = [], []
    for r in sorted(res, key=lambda r: r["project"]):
        p, src = r["project"], r["source"]
        rule, d = RULES[src]
        logs = sorted((a.logs / d / p / "state" / "logs").glob("pipeline-2*.log"))
        xn, xl = ex.get(p, {}).get("names", set()), ex.get(p, {}).get("lines", 0)
        if not logs:
            nolog.append(p)
            rows.append((p, src, rule, d, 0, "-", "NA", "NA", "NA", "NA", len(xn), xl, "NA", "NA"))
            continue
        nn, nl = scan(logs[-1:])
        an, al = scan(logs)
        chosen, lines = (nn, nl) if rule == "newest" else (an, al)
        rows.append((p, src, rule, d, len(logs), logs[-1].name, len(nn), nl, len(an), al, len(xn), xl,
                     len(chosen | xn), lines + xl))
    tmp = a.out.with_name(f".{a.out.name}.tmp")
    with open(tmp, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(COLS)
        w.writerows(rows)
    os.replace(tmp, a.out)
    by = {}
    for row in rows:
        b = by.setdefault(row[1], {"projects": 0, "with_plain_blame": 0, "files": 0, "lines": 0, "no_log": 0})
        b["projects"] += 1
        if row[12] == "NA":
            b["no_log"] += 1
        else:
            b["files"] += row[12]
            b["lines"] += row[13]
            b["with_plain_blame"] += row[12] > 0
    ex = {k: {kk: vv for kk, vv in v.items() if kk != "names"} for k, v in ex.items()}  # counts only
    s = {"projects": len(rows), "files": sum(b["files"] for b in by.values()),
         "lines": sum(b["lines"] for b in by.values()),
         "projects_with_plain_blame": sum(b["with_plain_blame"] for b in by.values()),
         "by_source": by, "extra_machines": ex, "no_log": nolog,
         "rule": {k: f"{v[0]} log(s) of {v[1]}" for k, v in RULES.items()},
         "count": "distinct files (a file that falls back in two attempts counts once); lines: all PLAIN-BLAME lines"}
    tmp = a.summary.with_name(f".{a.summary.name}.tmp")
    tmp.write_text(json.dumps(s, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, a.summary)
    print(f"plainblame: {s['projects']} projects, {s['projects_with_plain_blame']} with PLAIN-BLAME, "
          f"{s['files']} distinct files ({s['lines']} lines); no log {len(nolog)}; extra machines {ex}")
    for k, b in sorted(by.items()):
        print(f"  {k}: {b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
