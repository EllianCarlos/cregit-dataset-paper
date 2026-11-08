"""The license values of the new TOM revision from the re-decided license pass, and the audit sample.

  python3 -I 70_values.py [RESULTS_TSV]   (default work/out/results.tsv)

Publish rule (REPORT.md section 5, accepted 2026-11-08): the pass value when the confidence is high or
medium and the project is not on the review list; else the TOM 1.0.0 value (';' lists written with AND),
or NOASSERTION when TOM has none. Writes work/values/:
  project_licenses.tsv   the side table: project, license, confidence, evidence_kind, version_choice, source
  license_column.tsv     project, tom_1_0_0, license (the new column value), changed
  decisions.tsv          all fields: pass value, confidence, review kinds, TOM value, class
  sample100.tsv          the audit sample: 100 new values (TOM NOASSERTION -> a value), seed 20261108,
                         stratified by confidence and evidence kind
"""
import csv
import hashlib
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.expanduser("CTP-CHECKOUT"))
import license_rules as R  # noqa: E402
from importlib import import_module  # noqa: E402
C = import_module("30_compare")

import argparse  # noqa: E402

AP = argparse.ArgumentParser()
AP.add_argument("results", nargs="?", default=f"{HERE}/work/out/results.tsv")
AP.add_argument("--tom-values", help="project<TAB>license: the values in the files (on the machine); default: the "
                "local tables (lists/tom_license_values.tsv plus the license fills of the release pass)")
AP.add_argument("--projects", help="project<TAB>clone_url list (default lists/tom.tsv)")
AP.add_argument("--out", default=f"{HERE}/work/values")
AP.add_argument("--no-sample", action="store_true")
AP.add_argument("--corrections", help="project<TAB>correct_value: the hand-check corrections (a value, or 'hold' to "
                "keep the earlier value); applied after the publish rule")
AP.add_argument("--require-audit-ok", metavar="FILE", help="refuse to run when FILE (the audit flag) is missing")
ARGS = AP.parse_args()
RES = ARGS.results
FILLS = os.path.expanduser("~/s3-work/dataset-tom-2/stage/inputs/fills.tsv")
OUT = ARGS.out
SEED = "20261108"
N_SAMPLE = 100
KERNEL = re.compile(r"(?i)(^|__|[-_.])(linux|kernel|lustre|amdgpu)([-_.]|$)")


def rd(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def wr(p, rows, cols):
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def ids(v):
    try:
        return R.license_ids(v)
    except R.ExpressionError:
        return v.split(";")


def tom_style(v):
    """A TOM 1.0.0 value as an SPDX expression: 'A;B' -> 'A AND B'."""
    if not v or v in ("NOASSERTION", "(missing)"):
        return "NOASSERTION"
    if ";" in v:
        out = " AND ".join(p.strip() for p in v.split(";") if p.strip())
        R.parse(out)
        return out
    return v


def review_kinds(r):
    v, k = r["license"], []
    if r["status"] != "ok" or v == "NOASSERTION":
        return k
    n = len(set(ids(v)))
    if "LicenseRef-" in v:
        k.append("licenseref")
    if " AND " in v and n >= 4:
        k.append("long-and")
    if "disagree" in (r["licensee_agreement"], r["askalono_agreement"]):
        k.append("disagree")
    if r["vs_tom"] in ("different", "subset", "overlap"):
        k.append(f"tom-{r['vs_tom']}")
    if set(ids(v)) == {"Apache-2.0", "MIT"} and " AND " in v:
        k.append("apache-and-mit")
    if r["evidence_kind"] in ("readme", "manifest", "notice-file", "license-file-notice", "sub-folder") \
            and " AND " in v:
        k.append("and-from-declaration")
    if "Linux-syscall-note" in v and not KERNEL.search(r["project"]):
        k.append("syscall-note-non-kernel")
    for fl in r["flags"].split():
        if fl.startswith("review-"):
            k.append(fl.split(":")[0])
    return k


def main():
    if ARGS.require_audit_ok and not os.path.isfile(ARGS.require_audit_ok):
        print(f"ABORT: no audit flag {ARGS.require_audit_ok}: the hand check of the new values is not done")
        sys.exit(2)
    os.makedirs(OUT, exist_ok=True)
    res = rd(RES)
    corr = {}
    if ARGS.corrections:
        for r in rd(ARGS.corrections):
            v = (r.get("correct_value") or "").strip()
            if not v:
                continue
            if v != "hold":
                R.parse(v)
            corr[r["project"]] = v
    names = {r["project"] for r in res}
    unknown = sorted(set(corr) - names)
    if unknown:
        print(f"ABORT: corrections for projects without a result: {unknown[:5]}")
        sys.exit(2)
    if ARGS.tom_values:
        tom = {r["project"]: r["license"] for r in rd(ARGS.tom_values)}
    else:
        tom = {r["project"]: r["license"] for r in rd(f"{HERE}/lists/tom_license_values.tsv")}
        for r in rd(FILLS):
            if r["column"] == "license":
                tom[r["project"]] = r["new"]
    urls = {r["project"]: r for r in rd(ARGS.projects or f"{HERE}/lists/tom.tsv")}
    rows = []
    for r in res:
        p = r["project"]
        t = tom.get(p, "(missing)")
        r = dict(r, tom=t, vs_tom=C.klass(r["license"], t), clone_url=urls[p]["clone_url"],
                 tom_none="yes" if t in ("NOASSERTION", "", "(missing)") else "no")
        kinds = review_kinds(r)
        if t == "(missing)" and ARGS.tom_values:
            print(f"ABORT: {p} has no value in {ARGS.tom_values}")
            sys.exit(2)
        if t == "(missing)":
            kinds.append("tom-value-not-local")  # the 4 files whose TOM value is not in the local tables
        r["review"] = " ".join(kinds)
        publish = r["status"] == "ok" and r["confidence"] in ("high", "medium") and not kinds
        if publish:
            r.update(new=r["license"], source="pass", pub_confidence=r["confidence"],
                     pub_evidence=r["evidence_kind"], pub_choice=r["version_choice"])
        else:
            r.update(new=tom_style(t), source="tom-1.0.0" if r["tom_none"] == "no" else "none",
                     pub_confidence="" if r["tom_none"] == "no" else "none", pub_evidence="", pub_choice="")
            if r["tom_none"] == "yes":
                r["pub_confidence"] = "none"
        c = corr.get(p)
        if c == "hold" and r["source"] == "pass":
            r.update(new=tom_style(t), source="tom-1.0.0" if r["tom_none"] == "no" else "none",
                     pub_confidence="" if r["tom_none"] == "no" else "none", pub_evidence="", pub_choice="")
            kinds.append("audit-hold")
            r["review"] = " ".join(kinds)
        elif c and c != "hold":
            r.update(new=c, source="audit", pub_confidence="checked", pub_evidence=r["evidence_kind"],
                     pub_choice=r["version_choice"])
        r["group"] = ("no pass value" if r["status"] != "ok" or r["confidence"] == "none" else
                      "low" if r["confidence"] == "low" else
                      f"{r['confidence']}, review list" if kinds else f"{r['confidence']}, published")
        rows.append(r)
    # the side table and the column
    side = [{"project": r["project"], "license": r["new"], "confidence": r["pub_confidence"] if r["source"] in ("pass", "audit")
             else ("" if r["source"] == "tom-1.0.0" else "none"),
             "evidence_kind": r["pub_evidence"], "version_choice": r["pub_choice"], "source": r["source"]}
            for r in rows]
    wr(f"{OUT}/project_licenses.tsv", side, ["project", "license", "confidence", "evidence_kind", "version_choice",
                                              "source"])
    for r in rows:
        if r["tom"] == "(missing)":
            r.update(new="(file value)", source="tom-1.0.0", pub_confidence="")
    for s_ in side:
        if s_["project"] in {r["project"] for r in rows if r["tom"] == "(missing)"}:
            s_.update(license="(file value)", confidence="", source="tom-1.0.0")
    col = [{"project": r["project"], "tom_1_0_0": r["tom"], "license": r["new"],
            "changed": "no" if r["new"] in (r["tom"], "(file value)") else "yes"} for r in rows]
    wr(f"{OUT}/license_column.tsv", col, ["project", "tom_1_0_0", "license", "changed"])
    dcols = ["project", "status", "license", "confidence", "evidence_kind", "version_choice", "evidence_files",
             "licensee", "licensee_agreement", "askalono", "askalono_agreement", "flags", "tom", "vs_tom",
             "review", "group", "new", "source"]
    wr(f"{OUT}/decisions.tsv", rows, dcols)

    print("| group | TOM had a value | TOM NOASSERTION | total |\n|---|---:|---:|---:|")
    g = Counter((r["group"], r["tom_none"]) for r in rows)
    for k in sorted({a for a, _ in g}):
        print(f"| {k} | {g[(k, 'no')]:,} | {g[(k, 'yes')]:,} | {g[(k, 'no')] + g[(k, 'yes')]:,} |")
    print(f"| total | {sum(v for (a, b), v in g.items() if b == 'no'):,} | "
          f"{sum(v for (a, b), v in g.items() if b == 'yes'):,} | {len(rows):,} |")
    print(f"\nconfidence: {Counter(r['confidence'] for r in rows)}")
    print(f"vs TOM: {Counter(r['vs_tom'] for r in rows)}")
    print(f"review kinds: {Counter(k for r in rows for k in r['review'].split())}")
    print(f"column: changed {sum(c['changed'] == 'yes' for c in col):,}; NOASSERTION "
          f"{sum(c['license'] == 'NOASSERTION' for c in col):,} (TOM 1.0.0 "
          f"{sum(c['tom_1_0_0'] == 'NOASSERTION' for c in col):,}); source {Counter(r['source'] for r in rows)}")
    print(f"';' lists written with AND: {sum(1 for r in rows if r['source'] == 'tom-1.0.0' and ';' in r['tom'])}")

    fills = [{"project": r["project"], "column": "license", "old": r["tom"], "new": r["new"],
              "basis": f"license pass {r['source']} {r['pub_confidence']}".strip()}
             for r in rows if r["new"] not in (r["tom"], "(file value)")]
    wr(f"{OUT}/license_fills.tsv", fills, ["project", "column", "old", "new", "basis"])
    print(f"license fills (the value pass input): {len(fills):,}")
    if ARGS.no_sample:
        return
    # the audit sample: new values only
    pop = [r for r in rows if r["source"] == "pass" and r["tom_none"] == "yes"]
    strata = defaultdict(list)
    for r in pop:
        strata[(r["confidence"], r["evidence_kind"])].append(r)
    for k in strata:
        strata[k].sort(key=lambda r: hashlib.sha256(f"{SEED}:{r['project']}".encode()).hexdigest())
    # proportional allocation, at least 1 per stratum, largest remainder
    alloc = {k: 1 for k in strata}
    left = N_SAMPLE - len(alloc)
    share = {k: len(v) / len(pop) * left for k, v in strata.items()}
    for k in strata:
        alloc[k] += int(share[k])
    rest = N_SAMPLE - sum(alloc.values())
    for k in sorted(strata, key=lambda k: -(share[k] - int(share[k])))[:rest]:
        alloc[k] += 1
    sample = []
    for k, n in alloc.items():
        for r in strata[k][:min(n, len(strata[k]))]:
            sample.append(dict(r, stratum=f"{k[0]}/{k[1]}", stratum_size=len(strata[k]), stratum_n=alloc[k]))
    sample.sort(key=lambda r: hashlib.sha256(f"{SEED}:order:{r['project']}".encode()).hexdigest())
    wr(f"{OUT}/sample100.tsv", sample, ["project", "clone_url", "commit", "new", "confidence", "evidence_kind",
                                        "version_choice", "evidence_files", "stratum", "stratum_size", "stratum_n"])
    print(f"\nsample: {len(sample)} of {len(pop)} new values; strata: " +
          "; ".join(f"{k[0]}/{k[1]} {alloc[k]} of {len(v)}" for k, v in sorted(strata.items())))


if __name__ == "__main__":
    main()
