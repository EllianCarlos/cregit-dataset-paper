#!/usr/bin/env python3
"""Give each fetched project of the big EC2 runs its own ledger rows and its pinned commit.

Usage: split_run_ledgers.py [--ledgers DIR_OR_FILE ...] [--cloud DIR] [--runs RUN ...] [--dry-run]

Why. On the big EC2 (batch2, batch3L, batch4 p1-p3, batch5L, batch6L), the census uploaded
no ledger.jsonl into done/<project>/. The run ledgers are in S3: <run>/live/ledger*.jsonl and
<run>/[<part>/]backup-ledger/ledger.jsonl. This tool reads local copies of them (read-only).

What it writes, for each folder <cloud>/<run>/[<part>/]done/<project>/ with a row in
<cloud>/verified.tsv:
 - ledger.from-run.jsonl: the rows of that project in the census run (run_id) whose
   "project done" row has the sha256 of the fetched Parquet, in ledger order, each row once.
 - pin.from-run.json: run_id, attempt, pinned_sha, branch, url and cregit_commit of the attempt
   that finished, its parquet sha256, and the "pin" record of its clone step (pin.py's result).
It never creates or changes a file named ledger.jsonl (fetch_done.sh syncs S3 into that tree).
A file is written only when its content changes. A folder with no matching "project done" row
gets no file and is listed as "no match".
Exit 0, or 2 on a usage error."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HOME = Path.home()
CLOUD = HOME / "Projects/cregit-workspace/census-cloud"
LEDGERS = HOME / "Projects/cregit-workspace/run-ledgers"
RUNS = ("batch2", "batch3L", "batch4", "batch5L", "batch6L")
LEDGER_OUT = "ledger.from-run.jsonl"
PIN_OUT = "pin.from-run.json"


def ledger_files(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out.extend(sorted(f for f in p.rglob("*.jsonl") if "dryrun" not in f.parts))
    return out


def rows_by_project(files: list[Path], names: set[str]) -> dict[str, list[tuple[str, dict]]]:
    """(line, row) per project, in file order; a line that two copies hold is kept once."""
    seen, out = set(), {}
    for f in files:
        with f.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line in seen:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue            # a live ledger can end in a partial line
                name = row.get("project")
                if name not in names:
                    continue
                seen.add(line)
                out.setdefault(name, []).append((line, row))
    return out


def finished(rows: list[tuple[str, dict]], parquet_sha: str) -> dict | None:
    """The "project done" row whose Parquet has this sha256 (the last one if two)."""
    hit = None
    for _, r in rows:
        if r.get("step") == "project" and r.get("status") == "done" \
                and (r.get("parquet") or {}).get("sha256") == parquet_sha:
            hit = r
    return hit


def pin_record(rows: list[tuple[str, dict]], done: dict, parquet_sha: str) -> dict:
    pin = {}
    for _, r in rows:
        if r.get("run_id") == done["run_id"] and r.get("attempt") == done.get("attempt") \
                and r.get("step") == "clone" and r.get("status") == "ok" and r.get("pin"):
            pin = r["pin"]
    resolve = {}
    for _, r in rows:
        if r.get("run_id") == done["run_id"] and r.get("step") == "resolve" and r.get("resolve"):
            resolve = r["resolve"]
    return {
        "source": "split_run_ledgers.py",
        "run_id": done["run_id"],
        "attempt": done.get("attempt"),
        "pinned_sha": done.get("pinned_sha") or pin.get("pinned_sha"),
        "branch": pin.get("branch") or resolve.get("branch"),
        "url": pin.get("url") or resolve.get("url") or (done.get("manifest_row") or {}).get("url"),
        "cregit_commit": (done.get("tools") or {}).get("cregit_commit"),
        "parquet_sha256": parquet_sha,
        "pin": pin,
    }


def write_if_changed(path: Path, text: str, dry_run: bool) -> bool:
    if path.name == "ledger.jsonl":
        raise ValueError(f"refusing to write {path}")
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    if not dry_run:
        tmp = path.with_name(f".{path.name}.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ledgers", type=Path, action="append",
                    help=f"ledger file or directory (repeat; default {LEDGERS})")
    ap.add_argument("--cloud", type=Path, default=CLOUD)
    ap.add_argument("--runs", nargs="+", default=list(RUNS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    folders = []
    for line in (args.cloud / "verified.tsv").read_text(encoding="utf-8").splitlines():
        _, rel, sha = line.split("\t")
        if rel.split("/")[0] in args.runs:
            folders.append((rel, sha))
    names = {rel.rsplit("/", 1)[1] for rel, _ in folders}
    files = ledger_files(args.ledgers or [LEDGERS])
    if not files:
        print("no ledger files", file=sys.stderr)
        return 2
    rows = rows_by_project(files, names)
    written = same = 0
    missing = []
    done_rels = set()
    for rel, sha in folders:
        if rel in done_rels:
            continue
        done_rels.add(rel)
        name = rel.rsplit("/", 1)[1]
        mine = rows.get(name, [])
        done = finished(mine, sha)
        if done is None:
            missing.append(rel)
            continue
        folder = args.cloud / rel
        lines = [ln for ln, r in mine if r.get("run_id") == done["run_id"]]
        changed = write_if_changed(folder / LEDGER_OUT, "\n".join(lines) + "\n", args.dry_run)
        pin = json.dumps(pin_record(mine, done, sha), indent=1, sort_keys=True) + "\n"
        changed |= write_if_changed(folder / PIN_OUT, pin, args.dry_run)
        written += changed
        same += not changed
    print(f"{len(files)} ledger files; {len(done_rels)} folders: {written} written, "
          f"{same} unchanged, {len(missing)} no match")
    for rel in missing:
        print(f"no match: {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
