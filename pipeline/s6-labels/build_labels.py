#!/usr/bin/env python3
"""S6 labels: one governance label for each project, from the S5 facts only.
Usage: build_labels.py [--evidence ../s5-evidence/evidence.csv] [--frame F ...]
       [--date YYYY-MM-DD] [--prior OLD.csv] [--out labels.csv] [--counts counts.txt]

The frames are the projects, in order (default: dataset version 1, the frames of
s5-evidence/build_evidence.py: frame.layer1.csv, frame.batch21.csv, frame.batch22.csv and
frame.batch23.csv of s7-run). --frame replaces them; give it once for each frame.

label_date is the date when the label got its present value. --date gives it to each row.
--prior OLD.csv (added 2026-10-11) keeps the label_date of OLD.csv for each project whose row in
OLD.csv has the same values in all the other columns. The other rows get --date. So a new run
over more projects does not change the rows of the projects that it labels as before.

The rules are those of SELECTION-STAGES.md section 7, applied in this order. The first rule
that matches sets the label:

  1 government      a government fact
  2 contested       a foundation fact (roster, roster_org) and a company fact together
  3 foundation      a foundation fact
  4 contested       a fiscal_sponsor fact and a company fact together (method.md, case C2)
  5 fiscal-sponsor  a fiscal_sponsor fact
  6 company         a company fact: company_pool:spinellis, company_org (page or
                    verified-domain), company_roster (a company's own roster, mozilla),
                    company_roster_org (the Red Hat "All projects" table; user decision
                    2026-10-09: the table says that Red Hat takes part in the project, and
                    the user chose to count it as a company fact)
  7 community       a governance document fact (not collected: no project gets it)
  8 personal        owner_kind:user, and no other fact
  9 unknown         everything else. No label is the residual of other rules.

Facts that S5 records but that set no label: owner_kind:org, roster_affiliated
(NumFOCUS "affiliated"), company_org_candidate (a kept org link with no page and no
verified domain). They are kept in the column other_facts.

Output columns: project, pool_key, label, label_basis (each fact that set the label, sorted,
';'-joined), contested (the facts in conflict; non-empty only for a contested label),
other_facts (the facts that set no label), size_class, language, label_date.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "s7-run"))
from enrich_meta import project_name  # noqa: E402

FRAMES = [ROOT / "s7-run" / f for f in ("frame.layer1.csv", "frame.batch21.csv", "frame.batch22.csv",
                                        "frame.batch23.csv")]

LABELS = ("foundation", "company", "contested", "government", "fiscal-sponsor", "personal",
          "community", "unknown")
FOUNDATION = {"roster", "roster_org"}
COMPANY = {"company_pool", "company_org", "company_roster", "company_roster_org"}
SPONSOR = {"fiscal_sponsor"}
GOVERNMENT = {"government"}
COMMUNITY = {"governance_doc"}
NO_LABEL = {"owner_kind", "roster_affiliated", "company_org_candidate"}
COLS = ["project", "pool_key", "label", "label_basis", "contested", "other_facts", "size_class",
        "language", "label_date"]


def join(facts) -> str:
    return ";".join(sorted(set(facts)))


def label(facts: list[tuple[str, str]]) -> tuple[str, list[str], list[str], list[str]]:
    """(label, basis, contested, other) from [(fact_type, fact)] of one project."""
    by = defaultdict(set)
    for t, f in facts:
        known = FOUNDATION | COMPANY | SPONSOR | GOVERNMENT | COMMUNITY | NO_LABEL
        if t not in known:
            raise ValueError(f"fact type {t!r} has no rule")
        by[t].add(f)

    def of(types):
        return sorted(f for t in types for f in by.get(t, ()))

    fnd, com, spo, gov, cmy = (of(FOUNDATION), of(COMPANY), of(SPONSOR), of(GOVERNMENT),
                               of(COMMUNITY))
    user = "owner_kind:user" in by.get("owner_kind", set())
    if gov:
        lab, basis, cont = "government", gov, []
    elif fnd and com:
        lab, basis, cont = "contested", fnd + com, fnd + com
    elif fnd:
        lab, basis, cont = "foundation", fnd, []
    elif spo and com:
        lab, basis, cont = "contested", spo + com, spo + com
    elif spo:
        lab, basis, cont = "fiscal-sponsor", spo, []
    elif com:
        lab, basis, cont = "company", com, []
    elif cmy:
        lab, basis, cont = "community", cmy, []
    elif user and {f for _, f in facts} == {"owner_kind:user"}:
        lab, basis, cont = "personal", ["owner_kind:user"], []
    else:
        lab, basis, cont = "unknown", [], []
    other = sorted({f for _, f in facts} - set(basis))
    return lab, basis, cont, other


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evidence", type=Path, default=ROOT / "s5-evidence" / "evidence.csv")
    ap.add_argument("--frame", type=Path, action="append",
                    help="a frame CSV; give it once for each frame (default: the four of FRAMES)")
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
                    help="the label date (default: today, UTC)")
    ap.add_argument("--prior", type=Path, help="an older labels.csv: keep its label_date for "
                    "each row that does not change (see the module doc)")
    ap.add_argument("--out", type=Path, default=HERE / "labels.csv")
    ap.add_argument("--counts", type=Path, default=HERE / "counts.txt")
    args = ap.parse_args(argv)
    dt.date.fromisoformat(args.date)

    frame = []
    for path in args.frame or FRAMES:
        with path.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                host = r["host"].strip().lower() or "github.com"
                frame.append(dict(r, project=project_name(host, r["slug"].strip())))
    dup = [n for n, k in Counter(x["project"] for x in frame).items() if k > 1]
    if dup:
        print(f"FAIL {len(dup)} projects repeat in the frames: {dup[:5]}", file=sys.stderr)
        return 1
    facts = defaultdict(list)
    with args.evidence.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            facts[r["project"]].append((r["fact_type"], r["fact"]))
    names = {x["project"] for x in frame}
    stray = sorted(set(facts) - names)
    if stray:
        print(f"FAIL {len(stray)} evidence projects are not in the frame: {stray[:5]}", file=sys.stderr)
        return 1

    prior = {}
    if args.prior:
        with args.prior.open(newline="", encoding="utf-8") as fh:
            prior = {r["project"]: r for r in csv.DictReader(fh)}
    out = []
    for x in frame:
        lab, basis, cont, other = label(facts.get(x["project"], []))
        row = {"project": x["project"], "pool_key": x["pool_key"], "label": lab,
               "label_basis": join(basis), "contested": join(cont), "other_facts": join(other),
               "size_class": x["size_class"], "language": x["language"], "label_date": args.date}
        old = prior.get(x["project"])
        if old is not None and all(old[c] == row[c] for c in COLS if c != "label_date"):
            row["label_date"] = old["label_date"]
        out.append(row)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    args.counts.write_text(counts_text(out), encoding="utf-8")
    print(f"OK {args.out}: {len(out)} labels; " + ", ".join(
        f"{k} {v}" for k, v in Counter(r["label"] for r in out).most_common()))
    return 0


def counts_text(out: list[dict]) -> str:
    sizes = sorted({r["size_class"] for r in out})
    lab = Counter(r["label"] for r in out)
    cell = Counter((r["label"], r["size_class"]) for r in out)
    dates = Counter(r["label_date"] for r in out)
    lines = [f"projects: {len(out)}; label_date: "
             + ", ".join(f"{d} ({n})" if len(dates) > 1 else d for d, n in sorted(dates.items())), "",
             "| label | " + " | ".join(sizes) + " | total |",
             "| --- | " + " | ".join("---:" for _ in sizes) + " | ---: |"]
    for k in LABELS:
        lines.append(f"| {k} | " + " | ".join(str(cell[(k, s)]) for s in sizes) + f" | {lab[k]} |")
    lines.append("| **total** | " + " | ".join(str(sum(cell[(k, s)] for k in LABELS)) for s in sizes)
                 + f" | {len(out)} |")
    basis = Counter(r["label_basis"] for r in out if r["label"] == "company")
    alone = sum(v for k, v in basis.items() if k == "company_pool:spinellis")
    lines += ["", f"company labels that rest on company_pool:spinellis alone: {alone}",
              "company labels by the kinds of fact in label_basis:"]
    kinds = Counter(";".join(sorted({f.split(":")[0] for f in r["label_basis"].split(";")}))
                    for r in out if r["label"] == "company")
    lines += [f"  {k}: {v}" for k, v in kinds.most_common()]
    pairs = Counter(";".join(sorted({f.split(":")[0] for f in r["contested"].split(";")}))
                    for r in out if r["label"] == "contested")
    lines += ["contested labels by the kinds of fact in conflict:"]
    lines += [f"  {k}: {v}" for k, v in pairs.most_common()]
    unk = Counter(";".join(sorted({f.split(":")[0] for f in r["other_facts"].split(";")}))
                  if r["other_facts"] else "(no fact)" for r in out if r["label"] == "unknown")
    lines += ["unknown labels by the kinds of fact that set no label:"]
    lines += [f"  {k}: {v}" for k, v in unk.most_common()]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
