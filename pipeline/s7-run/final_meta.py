#!/usr/bin/env python3
"""Write the final sidecar: the enriched sidecar plus source, the S6 label columns and the S5 roster names.
Usage: final_meta.py [--sidecar S ...] --out project_meta.layer1.final.json
       [--labels ../s6-labels/labels.csv] [--evidence ../s5-evidence/evidence.csv]
       [--frame F ...] [--pool P ...] [--license-values CSV ...]

The inputs cover dataset version 1, that is batches 1-22 (3,379 projects; 2026-10-11). Each
option that takes several files replaces its default list; give it once for each file.
  --sidecar         project_meta.layer1.enriched.json (batches 1-20), project_meta.batch21.json,
                    project_meta.batch22.json. A key must not repeat; the output keeps this order.
  --frame           ../s4-filter/frame.csv (batches 1-20), frame.batch21.csv, frame.batch22.csv
  --pool            ../s2-pool/pool.csv, ../s2-pool/v2/pool.batch22.csv. A key in two pool files
                    must have the same values in both.
  --license-values  ../s4-filter/dp8l-audit/licenses.csv (batch 21) and
                    ../s4-filter/supplement22.licenses.csv (batch 22): the license values that
                    build_run.sh supplement gave to the rows whose pool license is blank
                    (enrich_meta.apply_license_values, the same rule)

The final sidecar is the input of rewrite_meta_columns.py, which then fills all 11 changed
columns of each finished Parquet in one pass. The columns and where they come from:

  license, owner_type, archived, fork   as in the input sidecar (enrich_meta.py)
  source        pool.csv origins, by enrich_meta.enrich (the same join and checks)
  stratum       the S6 label
  fact          the S6 label_basis: each fact that set the label, sorted, ';'-joined
  contested     the S6 contested facts (non-empty only when the label is contested)
  label_date    the S6 label date
  roster_name   each roster that names the repository itself, as '<org_key>:<project name as the
                roster spells it>', sorted, joined by '; ' (no roster name holds ';')
  roster_lang   the same for the language that the roster names; only the ASF DOAP files name
                one (S5), so most values are ''

Two host rules (decisions of the user, 2026-10-11). They use the host of the frame row:
  license       a project that is not on GitHub and has a blank license gets NOASSERTION. pool.csv
                has no license value for such a project (GitHub's detector did not read it), and
                NOASSERTION is the value that the GitHub rows use for "no detected license".
  owner         a project on git.savannah.gnu.org gets the owner gnu. build_manifest.py takes the
                owner from the slug (git/<name> gives git) or the host (<name> alone), and neither
                names the owner. HOST_OWNER holds the rule.

Checks, or nothing is written: every sidecar key is in labels.csv and labels.csv has no other
key; pool_key agrees; the input fields that this fills are '' or already hold the same value;
every other field and the key order stay, except the fields that a host rule changes. --out
refuses an existing file."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import enrich_meta  # noqa: E402

LABEL_FIELDS = {"stratum": "label", "fact": "label_basis", "contested": "contested",
                "label_date": "label_date"}
ROSTER_TYPES = {"roster", "fiscal_sponsor", "roster_affiliated", "company_roster"}
NEW_FIELDS = (enrich_meta.SOURCE,) + tuple(LABEL_FIELDS) + ("roster_name", "roster_lang")
SEL = HERE.parent
SIDECARS = [HERE / f for f in ("project_meta.layer1.enriched.json", "project_meta.batch21.json",
                               "project_meta.batch22.json")]
FRAMES = [SEL / "s4-filter" / "frame.csv", HERE / "frame.batch21.csv", HERE / "frame.batch22.csv"]
POOLS = [SEL / "s2-pool" / "pool.csv", SEL / "s2-pool" / "v2" / "pool.batch22.csv"]
LICENSES = [SEL / "s4-filter" / "dp8l-audit" / "licenses.csv",
            SEL / "s4-filter" / "supplement22.licenses.csv"]


NOT_GITHUB_LICENSE = "NOASSERTION"
HOST_OWNER = {"git.savannah.gnu.org": "gnu"}


def host_rules(rec: dict, frame_row: dict) -> tuple[dict, set[str]]:
    """(the record after the two host rules, the fields that they changed)."""
    host = frame_row["host"].strip().lower() or enrich_meta.DEFAULT_HOST
    new, changed = dict(rec), set()
    if host != enrich_meta.DEFAULT_HOST and rec["license"] == "":
        new["license"] = NOT_GITHUB_LICENSE
        changed.add("license")
    if host in HOST_OWNER and rec["owner"] != HOST_OWNER[host]:
        new["owner"] = HOST_OWNER[host]
        changed.add("owner")
    return new, changed


def merge(parts: list[dict], what: str) -> dict:
    """One dict from several, in order. A key must not repeat with another value."""
    out: dict = {}
    for part in parts:
        for k, v in part.items():
            if k in out and out[k] != v:
                raise ValueError(f"{what}: the key {k} repeats with other values")
            out.setdefault(k, v)
    return out


def roster_columns(evidence: Path) -> dict[str, dict[str, str]]:
    """project -> {roster_name, roster_lang} from the repository-level roster facts."""
    names, langs = defaultdict(set), defaultdict(set)
    with evidence.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["fact_type"] in ROSTER_TYPES:
                for part in (r["subject"], r["name"]):
                    if ";" in part:
                        raise ValueError(f"{evidence}: {part!r} holds ';'")
                if r["name"]:
                    names[r["project"]].add(f"{r['subject']}:{r['name']}")
                if r["language"]:
                    langs[r["project"]].add(f"{r['subject']}:{r['language']}")
    out = {}
    for p in set(names) | set(langs):
        out[p] = {"roster_name": "; ".join(sorted(names[p])),
                  "roster_lang": "; ".join(sorted(langs[p]))}
    return out


def finalize(meta: dict, labels: dict[str, dict], rosters: dict[str, dict],
             frame: dict[str, dict]) -> tuple[dict, list[str]]:
    problems: list[str] = []
    extra = sorted(set(labels) - set(meta))
    if extra:
        problems.append(f"labels.csv has {len(extra)} keys that the sidecar has not: {extra[:5]}")
    out = {}
    for name, rec in meta.items():
        lab = labels.get(name)
        if lab is None:
            problems.append(f"{name}: no label")
            continue
        if frame.get(name, {}).get("pool_key") != lab["pool_key"]:
            problems.append(f"{name}: labels.csv pool_key {lab['pool_key']} is not the frame's")
            continue
        new = dict(rec)
        vals = {f: lab[c] for f, c in LABEL_FIELDS.items()}
        vals.update(rosters.get(name, {"roster_name": "", "roster_lang": ""}))
        for f, v in vals.items():
            if f not in rec:
                problems.append(f"{name}: the sidecar has no {f} field")
            elif rec[f] not in ("", v):
                problems.append(f"{name}: {f} is already {rec[f]!r}, the new value is {v!r}")
            new[f] = v
        out[name] = new
    return out, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sidecar", type=Path, action="append")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--labels", type=Path, default=HERE.parent / "s6-labels" / "labels.csv")
    ap.add_argument("--evidence", type=Path, default=HERE.parent / "s5-evidence" / "evidence.csv")
    ap.add_argument("--frame", type=Path, action="append")
    ap.add_argument("--pool", type=Path, action="append")
    ap.add_argument("--license-values", type=Path, action="append")
    args = ap.parse_args(argv)
    if args.out.exists():
        print(f"FAIL {args.out} exists", file=sys.stderr)
        return 1

    sidecars = [json.loads(p.read_text(encoding="utf-8")) for p in args.sidecar or SIDECARS]
    n_keys = sum(len(s) for s in sidecars)
    meta = merge(sidecars, "the sidecars")
    if len(meta) != n_keys:
        print(f"FAIL {n_keys - len(meta)} keys repeat in the sidecars", file=sys.stderr)
        return 1
    frames = [enrich_meta.frame_index(p) for p in args.frame or FRAMES]
    frame = merge(frames, "the frames")
    if len(frame) != sum(len(f) for f in frames):
        print("FAIL a name repeats in the frames", file=sys.stderr)
        return 1
    wanted = {frame[n]["pool_key"] for n in meta if n in frame}
    pool = merge([enrich_meta.pool_values(p, wanted) for p in args.pool or POOLS], "the pools")
    problems = []
    for p in args.license_values if args.license_values is not None else LICENSES:
        problems += enrich_meta.apply_license_values(pool, p)
    sourced, more = enrich_meta.enrich(meta, frame, pool)
    problems += more
    with args.labels.open(newline="", encoding="utf-8") as fh:
        labels = {r["project"]: r for r in csv.DictReader(fh)}
    final, more = finalize(sourced, labels, roster_columns(args.evidence), frame)
    problems += more
    by_rule: dict[str, set[str]] = {}
    for k in final:
        final[k], by_rule[k] = host_rules(final[k], frame[k])
    if not problems:
        for k in meta:
            changed = {f for f in meta[k] if meta[k][f] != final[k][f]}
            if list(meta[k]) != list(final[k]) or not changed <= set(NEW_FIELDS) | by_rule[k]:
                problems.append(f"{k}: fields other than the new ones changed: {sorted(changed)}")
    if problems:
        print(f"FAIL {len(problems)} problems:", file=sys.stderr)
        for p in problems[:50]:
            print(f"  {p}", file=sys.stderr)
        return 1
    tmp = args.out.with_name(f".{args.out.name}.tmp")
    tmp.write_text(json.dumps(final, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, args.out)
    digest = hashlib.sha256(args.out.read_bytes()).hexdigest()
    filled = {f: sum(1 for r in final.values() if r[f]) for f in NEW_FIELDS}
    rules = {f: sum(1 for c in by_rule.values() if f in c) for f in ("license", "owner")}
    print(f"OK {args.out}: {len(final)} keys; sha256 {digest}; non-blank: "
          + ", ".join(f"{f} {n}" for f, n in filled.items())
          + "; host rules changed: " + ", ".join(f"{f} {n}" for f, n in rules.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
