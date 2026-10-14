#!/usr/bin/env python3
"""Fill license, owner_type, archived, fork and source in a project_meta sidecar from s2-pool/pool.csv.
Usage: enrich_meta.py SIDECAR.json (--out NEW.json | --in-place)
       [--frame ../s4-filter/frame.csv] [--pool ../s2-pool/pool.csv] [--license-values CSV]

Why (2026-10-09): s4-filter/funnel.py reads these 4 pool columns to filter, but writes only
15 columns to frame.csv, so build_manifest.py (which copies frame columns by name) leaves them
blank in every sidecar, and cregit's generate_dataset.py writes the blanks to the Parquet.

Join: sidecar key (the manifest name, owner__repo on GitHub, host__owner__repo elsewhere, as
build_manifest.project_name makes it) -> the frame row with that host and slug -> its pool_key
-> the pool.csv row with that pool_key. Every sidecar key must match, or nothing is written.
As a check, the sidecar's clone_url must equal the frame row's repo_url.

source (added 2026-10-09) is the pool.csv column origins, copied as pool.csv writes it: the
S1 sources that found the project, as tokens joined by ';', each token once, in Python sort
order (build_pool.py writes ';'.join(sorted(set))). The tokens are 'search' (the GitHub
search), 'spinellis-2020:enterprise', 'cncf-landscape:hosted' or 'cncf-landscape:not-hosted',
'company-org:<org login>' and 'rosters/<roster file>:<org key>'. A value that is not sorted
and unique is a problem, so the format is checked, not assumed.

Values are copied from pool.csv as they are, as strings: NOASSERTION stays NOASSERTION,
archived and fork are 'True' or 'False', and the non-GitHub rows, which pool.csv leaves blank,
stay ''. generate_dataset.py writes every sidecar field as VARCHAR (str(value)), and a missing
value as '', so '' and not null is what the schema expects.

Only the 5 fields change; every other field and the key order stay as they were, and the file
is written in build_manifest.py's format (indent 1, ensure_ascii off, final newline).
--out refuses an existing file. --in-place refuses a file listed in SHA256SUMS next to it,
because the sidecars recorded there are frozen (batches 1-5: write NEW.enriched.json instead).

--license-values CSV (added 2026-10-10 for batch 21, the DP8L supplement): a CSV with the columns
pool_key, license, license_evidence (../s4-filter/dp8l-audit/licenses.csv). For its keys the
license value comes from the CSV, but only where the pool value is blank: the DP8L rows that
come back have a license file that GitHub's detector does not know, so pool.csv has no value.
A key whose pool value is not blank and differs from the CSV value is a problem. The evidence
column stays in the CSV; the sidecar gets no new field (the Parquet schema does not change)."""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = ("license", "owner_type", "archived", "fork")
SOURCE = "source"  # the sidecar field; its pool.csv column is ORIGINS
ORIGINS = "origins"
FILLED = FIELDS + (SOURCE,)
DEFAULT_HOST = "github.com"
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def project_name(host: str, slug: str) -> str:
    """The manifest name, as build_manifest.project_name builds it."""
    parts = [p for p in slug.strip("/").split("/") if p]
    if host != DEFAULT_HOST:
        parts.insert(0, host)
    name = "__".join(parts)
    if not NAME_RE.match(name) or ".." in name:
        raise ValueError(f"slug {slug!r} on {host} gives the name {name!r}")
    return name


def frame_index(frame: Path) -> dict[str, dict]:
    """manifest name -> frame row (host, slug, repo_url, pool_key)."""
    index: dict[str, dict] = {}
    with frame.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            host = (row["host"].strip().lower() or DEFAULT_HOST)
            name = project_name(host, row["slug"].strip())
            if name in index:
                raise ValueError(f"{frame}: the name {name} repeats")
            index[name] = row
    return index


def pool_values(pool: Path, keys: set[str]) -> dict[str, dict]:
    """pool_key -> the 5 fields, for the wanted keys only (the pool has 400k+ rows)."""
    out: dict[str, dict] = {}
    with pool.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = row["pool_key"]
            if key in keys:
                if key in out:
                    raise ValueError(f"{pool}: pool_key {key} repeats")
                out[key] = {**{f: row[f] for f in FIELDS}, SOURCE: row[ORIGINS]}
    return out


def enrich(meta: dict, frame: dict[str, dict], pool: dict[str, dict]) -> tuple[dict, list[str]]:
    """(enriched copy, problems). A problem is a key that does not join, or that disagrees."""
    problems: list[str] = []
    out: dict = {}
    for name, rec in meta.items():
        row = frame.get(name)
        if row is None:
            problems.append(f"{name}: not in the frame")
            continue
        if rec.get("clone_url", "") != row["repo_url"].strip():
            problems.append(f"{name}: clone_url {rec.get('clone_url')!r} is not the frame's "
                            f"repo_url {row['repo_url']!r}")
            continue
        values = pool.get(row["pool_key"])
        if values is None:
            problems.append(f"{name}: pool_key {row['pool_key']} is not in the pool")
            continue
        if SOURCE not in rec:
            problems.append(f"{name}: the sidecar has no {SOURCE} field")
            continue
        tokens = values[SOURCE].split(";")
        if not values[SOURCE] or tokens != sorted(set(tokens)) or "" in tokens:
            problems.append(f"{name}: pool origins {values[SOURCE]!r} is not a sorted list of "
                            "unique tokens")
            continue
        for f in FILLED:
            if rec.get(f, "") not in ("", values[f]):
                problems.append(f"{name}: {f} is already {rec[f]!r}, the pool says {values[f]!r}")
        new = dict(rec)
        for f in FILLED:
            new[f] = values[f]
        out[name] = new
    return out, problems


def apply_license_values(pool: dict[str, dict], path: Path) -> list[str]:
    """Fill the blank pool license values from the --license-values CSV; return the problems."""
    problems: list[str] = []
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    seen: set[str] = set()
    for row in rows:
        key, value = row["pool_key"], row["license"].strip()
        if key in seen:
            problems.append(f"{path}: pool_key {key} repeats")
            continue
        seen.add(key)
        if not value:
            problems.append(f"{path}: pool_key {key} has a blank license value")
            continue
        if key not in pool:
            continue
        if pool[key]["license"] not in ("", value):
            problems.append(f"{key}: pool license {pool[key]['license']!r}, the CSV says {value!r}")
            continue
        pool[key]["license"] = value
    return problems


def frozen_names(sidecar: Path) -> set[str]:
    sums = sidecar.parent / "SHA256SUMS"
    if not sums.exists():
        return set()
    return {line.split(None, 1)[1].strip() for line in sums.read_text().splitlines() if line.strip()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sidecar", type=Path)
    dest = ap.add_mutually_exclusive_group(required=True)
    dest.add_argument("--out", type=Path)
    dest.add_argument("--in-place", action="store_true")
    ap.add_argument("--frame", type=Path, default=HERE.parent / "s4-filter" / "frame.csv")
    ap.add_argument("--pool", type=Path, default=HERE.parent / "s2-pool" / "pool.csv")
    ap.add_argument("--license-values", type=Path, help="CSV pool_key,license,license_evidence: "
                    "fills the blank pool license values (see the module doc)")
    args = ap.parse_args(argv)

    if args.in_place:
        target = args.sidecar
        if args.sidecar.name in frozen_names(args.sidecar):
            print(f"FAIL {args.sidecar} is listed in SHA256SUMS; write a new file with --out",
                  file=sys.stderr)
            return 1
    else:
        target = args.out
        if target.exists():
            print(f"FAIL {target} exists", file=sys.stderr)
            return 1

    meta = json.loads(args.sidecar.read_text(encoding="utf-8"))
    frame = frame_index(args.frame)
    wanted = {frame[n]["pool_key"] for n in meta if n in frame}
    pool = pool_values(args.pool, wanted)
    problems = apply_license_values(pool, args.license_values) if args.license_values else []
    if not problems:
        out, problems = enrich(meta, frame, pool)
    if problems:
        print(f"FAIL {args.sidecar}: {len(problems)} of {len(meta)} keys do not join:",
              file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1

    tmp = target.with_name(f".{target.name}.tmp")
    tmp.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    filled = sum(1 for r in out.values() if r["license"])
    print(f"OK {target}: {len(out)} of {len(meta)} keys joined; {filled} with a license value, "
          f"{len(out) - filled} with a blank license; {len(out)} with a source value")
    return 0


if __name__ == "__main__":
    sys.exit(main())
