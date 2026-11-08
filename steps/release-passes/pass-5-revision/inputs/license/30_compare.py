"""Compare the license pass with the current TOM value and with the rescan of 2026-11-07.

  python3 30_compare.py RUN_DIR [LIST ...]
RUN_DIR has results.tsv (license_scan.py collect). Writes RUN_DIR/compare.tsv and prints the tables
(markdown) for each list (default: lists/test_hand.tsv lists/test_disagree.tsv lists/test_random.tsv).

Classes (on the base ids: -only, -or-later and + dropped; exceptions dropped):
  same            the same base ids, and the same text after the id style is normalized
  same-ids        the same base ids, but the -only/-or-later choice or the operator differs
  new-value       TOM has NOASSERTION (or no value); the pass gives a value
  no-value        the pass gives NOASSERTION; TOM has a value
  both-none       both NOASSERTION
  subset          the pass ids are a strict subset of the TOM ids (TOM lists more licenses)
  superset        the pass ids are a strict superset of the TOM ids
  overlap         some ids in common
  different       no id in common
"""
import csv
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.expanduser("~/Projects/ctp-license-scan"))
import license_rules as R  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESCAN = os.path.expanduser("~/Projects/cregit-workspace/license-rescan-1.1.0/results.tsv")


def norm_text(v):
    if not v or v in ("NOASSERTION", "(missing)"):
        return "NOASSERTION"
    try:
        ids = R.license_ids(v)
    except R.ExpressionError:
        ids = v.split(";")
    return " ".join(sorted(R.base_id(i) for i in ids))


def klass(ours, tom):
    a, b = R.base_set(ours) if ours != "NOASSERTION" else frozenset(), R.split_value(tom)
    if not a and not b:
        return "both-none"
    if not b:
        return "new-value"
    if not a:
        return "no-value"
    if a == b:
        o = ours.replace("-only", "").replace("-or-later", "")
        t = (tom or "").replace("-only", "").replace("-or-later", "").replace("+", "")
        return "same" if o == t or len(a) == 1 and ours == tom else "same-ids"
    if a < b:
        return "subset"
    if a > b:
        return "superset"
    if a & b:
        return "overlap"
    return "different"


def load(path, key="project"):
    with open(path, newline="") as f:
        return {r[key]: r for r in csv.DictReader(f, delimiter="\t")}


def main():
    run = sys.argv[1]
    lists = sys.argv[2:] or [f"{HERE}/lists/{n}.tsv" for n in ("test_hand", "test_disagree", "test_random")]
    res = load(f"{run}/results.tsv")
    tom = {p: r["license"] for p, r in load(f"{HERE}/lists/tom_license_values.tsv").items()}
    resc = load(RESCAN)
    out = []
    for p, r in sorted(res.items()):
        rs = resc.get(p, {})
        out.append({"project": p, "ours": r["license"], "confidence": r["confidence"],
                    "version_choice": r["version_choice"], "evidence_kind": r["evidence_kind"],
                    "tom": tom.get(p, "(missing)"), "vs_tom": klass(r["license"], tom.get(p)),
                    "rescan_licensee98": rs.get("licensee98_value", ""), "rescan_strict": rs.get("strict_value", ""),
                    "rescan_class": rs.get("class", ""),
                    "vs_rescan_strict": klass(r["license"], rs.get("strict_value")) if rs else "",
                    "licensee": r["licensee"], "licensee_agreement": r["licensee_agreement"],
                    "askalono": r["askalono"], "askalono_agreement": r["askalono_agreement"],
                    "evidence_files": r["evidence_files"], "flags": r["flags"]})
    cols = list(out[0])
    with open(f"{run}/compare.tsv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    by = {r["project"]: r for r in out}
    for lp in lists:
        names = [r["project"] for r in csv.DictReader(open(lp), delimiter="\t")]
        rows = [by[n] for n in names if n in by]
        print(f"\n### {os.path.basename(lp)} ({len(rows)} of {len(names)} projects)\n")
        for col, title in (("vs_tom", "against the TOM value"), ("confidence", "confidence"),
                           ("licensee_agreement", "licensee 10.1.0"), ("askalono_agreement", "askalono 0.5.0")):
            c = Counter(r[col] for r in rows)
            print(f"| {title} | " + " | ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda x: -x[1])) + " |")
        if any(r["rescan_class"] for r in rows):
            c = Counter(r["vs_rescan_strict"] for r in rows if r["rescan_class"])
            print("| against the rescan strict value | " + " | ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda x: -x[1])) + " |")
    print(f"\nwrote {run}/compare.tsv ({len(out)} rows)")


if __name__ == "__main__":
    main()
