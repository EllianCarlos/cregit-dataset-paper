"""The tables of REPORT.md: the full ScanCode license pass against the TOM 1.0.0 license value.

  python3 -I 60_report.py [RUN_DIR]      (default run-license-scancode-1/results)

TOM 1.0.0 value = lists/tom_license_values.tsv (column-review-app project_values.parquet, the values
before the release pass) with the 149 license fills of the release pass (dataset-tom-2 inputs/fills.tsv).
4 projects have no value in these files ("(missing)"); the rescan counted them with the NOASSERTION set.
Writes analysis/compare_tom.tsv and analysis/review.tsv, prints markdown tables.
"""
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.expanduser("CTP-CHECKOUT"))
import license_rules as R  # noqa: E402
from importlib import import_module  # noqa: E402
C = import_module("30_compare")

RUN = sys.argv[1] if len(sys.argv) > 1 else f"{HERE}/run-license-scancode-1/results"
FILLS = os.path.expanduser("~/s3-work/dataset-tom-2/stage/inputs/fills.tsv")
RESCAN = os.path.expanduser("WORK-FOLDER/license-rescan")
OUT = f"{HERE}/analysis"
GNU = re.compile(r"^(A?GPL|LGPL|GFDL)-\d")


def rd(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def tbl(title, counter, order=None):
    keys = order or [k for k, _ in counter.most_common()]
    print(f"\n| {title} | projects |\n|---|---:|")
    for k in keys:
        print(f"| {k or '(empty)'} | {counter.get(k, 0):,} |")
    print(f"| total | {sum(counter.values()):,} |")


def xtab(title, rows, a, b, akeys, bkeys):
    c = Counter((r[a], r[b]) for r in rows)
    print(f"\n| {title} | " + " | ".join(bkeys) + " | total |\n|---|" + "---:|" * (len(bkeys) + 1))
    for k in akeys:
        print(f"| {k} | " + " | ".join(f"{c.get((k, j), 0):,}" for j in bkeys) +
              f" | {sum(c.get((k, j), 0) for j in bkeys):,} |")


def ids(v):
    try:
        return R.license_ids(v)
    except R.ExpressionError:
        return v.split(";")


def main():
    os.makedirs(OUT, exist_ok=True)
    res = rd(f"{RUN}/results.tsv")
    tom = {r["project"]: r["license"] for r in rd(f"{HERE}/lists/tom_license_values.tsv")}
    fills = [r for r in rd(FILLS) if r["column"] == "license"]
    for r in fills:
        tom[r["project"]] = r["new"]
    urls = {r["project"]: r["clone_url"] for r in rd(f"{HERE}/lists/tom.tsv")}
    print(f"license fills of the release pass: {len(fills)}")

    # coverage and time
    tbl("status", Counter(r["status"] for r in res))
    fin, tot = [], []
    with open(f"{RUN}/results.jsonl") as f:
        for line in f:
            d = json.loads(line)
            tot.append(d.get("times", {}).get("total", 0))
            if d.get("finished"):
                fin.append(datetime.fromisoformat(d["finished"].replace("Z", "+00:00")))
    tot.sort()
    print(f"\nproject seconds (final attempt): sum {sum(tot)/3600:.1f} h, median {tot[len(tot)//2]:.1f}, "
          f"p95 {tot[int(len(tot)*.95)]:.1f}, max {tot[-1]:.0f}; last finish {max(fin)}")

    # against TOM 1.0.0
    out = []
    for r in res:
        p = r["project"]
        t = tom.get(p, "(missing)")
        gh = urls[p].startswith("https://github.com/")
        tnone = t in ("NOASSERTION", "", "(missing)")
        out.append({**r, "tom": t, "on_github": "yes" if gh else "no",
                    "tom_none": "yes" if tnone else "no", "vs_tom": C.klass(r["license"], t)})
    with open(f"{OUT}/compare_tom.tsv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    tbl("TOM value", Counter(("NOASSERTION/missing" if r["tom_none"] == "yes" else "a value") +
                             (" (GitHub)" if r["on_github"] == "yes" else " (other host)") for r in out))
    tbl("TOM value (exact)", Counter(r["tom"] for r in out if r["tom_none"] == "yes"))
    order = ["same", "same-ids", "superset", "subset", "overlap", "different", "no-value", "new-value", "both-none"]
    tbl("pass against TOM 1.0.0", Counter(r["vs_tom"] for r in out), order)
    conf = ["high", "medium", "low", "none"]
    xtab("vs TOM x confidence", out, "vs_tom", "confidence", order, conf)
    none = [r for r in out if r["tom_none"] == "yes"]
    xtab("TOM NOASSERTION/missing: host x confidence", none, "on_github", "confidence", ["yes", "no"], conf)
    xtab("TOM NOASSERTION/missing: evidence x confidence", none, "evidence_kind", "confidence",
         [k for k, _ in Counter(r["evidence_kind"] for r in none).most_common()], conf)
    for k in ("different", "subset", "overlap", "no-value"):
        print(f"\n{k}: " + "; ".join(f"{r['project']} TOM {r['tom']} -> {r['license']} ({r['confidence']})"
                                      for r in out if r["vs_tom"] == k)[:6000])
    sid = Counter((r["tom"], r["license"]) for r in out if r["vs_tom"] == "same-ids")
    print("\nsame-ids top pairs: " + "; ".join(f"{a} -> {b} {n}" for (a, b), n in sid.most_common(12)))
    sup = Counter((r["tom"], r["license"]) for r in out if r["vs_tom"] == "superset")
    print("\nsuperset top pairs: " + "; ".join(f"{a} -> {b} {n}" for (a, b), n in sup.most_common(12)))

    # quality
    ok = [r for r in out if r["status"] == "ok"]
    ag = ["agree", "partial", "disagree", "none"]
    xtab("confidence x licensee", ok, "confidence", "licensee_agreement", conf, ag)
    xtab("confidence x askalono", ok, "confidence", "askalono_agreement", conf, ag)
    both_dis = [r for r in ok if r["licensee_agreement"] == "disagree" and r["askalono_agreement"] == "disagree"]
    print(f"\nboth second opinions disagree: {len(both_dis)}; licensee disagree and askalono none: "
          f"{sum(1 for r in ok if r['licensee_agreement']=='disagree' and r['askalono_agreement']=='none')}")
    print(f"no second opinion at all (both none): {sum(1 for r in ok if r['licensee_agreement']=='none' and r['askalono_agreement']=='none')}")

    review = []

    def add(kind, r, note=""):
        review.append({"kind": kind, "project": r["project"], "license": r["license"], "confidence": r["confidence"],
                       "tom": r["tom"], "evidence_kind": r["evidence_kind"], "licensee": r["licensee"],
                       "askalono": r["askalono"], "flags": r["flags"], "note": note})

    for r in ok:
        v = r["license"]
        if v == "NOASSERTION":
            continue
        n = len(set(ids(v)))
        kernel = re.search(r"linux|kernel|u-boot|openwrt|lede|buildroot|busybox", r["project"], re.I)
        if "Linux-syscall-note" in v and not kernel:
            add("syscall-note-non-kernel", r)
        if "LicenseRef-" in v:
            add("licenseref", r)
        if " AND " in v and n >= 4:
            add("long-and", r, f"{n} ids")
        if r["licensee_agreement"] == "disagree" or r["askalono_agreement"] == "disagree":
            add("disagree", r, f"licensee {r['licensee_agreement']}, askalono {r['askalono_agreement']}")
        if r["confidence"] == "low":
            add("low", r)
        if r["vs_tom"] in ("different", "subset", "overlap"):
            add(f"tom-{r['vs_tom']}", r)
        if set(ids(v)) == {"Apache-2.0", "MIT"} and " AND " in v:
            add("apache-and-mit", r, "usually a dual license (OR)")
        if r["evidence_kind"] in ("readme", "manifest", "notice-file", "license-file-notice", "sub-folder") \
                and " AND " in v:
            add("and-from-declaration", r)
    for r in out:
        if r["status"] != "ok":
            add("failed", r, r["status"])
    with open(f"{OUT}/review.tsv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(review[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(review)
    kinds = Counter(x["kind"] for x in review)
    tbl("review cases (a project can be in several kinds)", kinds)
    print(f"distinct projects in review.tsv: {len({x['project'] for x in review}):,}; "
          f"of them TOM NOASSERTION/missing: {len({x['project'] for x in review if x['tom'] in ('NOASSERTION','','(missing)')}):,}")
    lr = Counter(i for r in ok for i in ids(r["license"]) if i.startswith("LicenseRef-"))
    print("\nLicenseRef ids: " + "; ".join(f"{k} {v}" for k, v in lr.most_common(15)))
    sc = [x for x in review if x["kind"] == "syscall-note-non-kernel"]
    print("\nsyscall note non-kernel: " + "; ".join(f"{x['project']} {x['license']} ({x['confidence']})" for x in sc[:40]))
    la = Counter(int(x["note"].split()[0]) for x in review if x["kind"] == "long-and")
    print("\nlong AND id counts: " + ", ".join(f"{k}: {v}" for k, v in sorted(la.items())))

    # hand 30 and disagreement 58
    by = {r["project"]: r for r in out}
    resc = {r["project"]: r for r in rd(f"{RESCAN}/results.tsv")}
    for name in ("test_hand", "test_disagree"):
        names = [r["project"] for r in rd(f"{HERE}/lists/{name}.tsv")]
        rows = [by[n] for n in names]
        print(f"\n### {name} ({len(rows)})")
        tbl("confidence", Counter(r["confidence"] for r in rows), conf)
        print("\n| project | rescan class | rescan strict | pass value | confidence | licensee | askalono |\n|---|---|---|---|---|---|---|")
        for r in rows:
            s = resc.get(r["project"], {})
            print(f"| {r['project']} | {s.get('class','')} | {s.get('strict_value','') or '-'} | {r['license']} | "
                  f"{r['confidence']} | {r['licensee_agreement']} | {r['askalono_agreement']} |")

    # question data
    def bare(v):
        return [i for i in ids(v) if GNU.match(i) and not i.endswith(("-only", "-or-later", "+"))]
    b = [r for r in ok if r["license"] != "NOASSERTION" and bare(r["license"])]
    print(f"\n(a) values with a bare GNU id: {len(b)}; of them TOM none: {sum(r['tom_none']=='yes' for r in b)}; "
          f"conf {Counter(r['confidence'] for r in b)}; ids {Counter(i for r in b for i in bare(r['license'])).most_common(8)}")
    print(f"(a) version_choice over ok: {Counter(r['version_choice'] for r in ok)}")
    gnu_any = [r for r in ok if any(GNU.match(i) for i in ids(r['license'])) and r['license'] != 'NOASSERTION']
    print(f"(a) values with any GNU id: {len(gnu_any)}")
    reuse = [r for r in ok if r["evidence_kind"] == "reuse"]
    print(f"\n(b) reuse evidence: {len(reuse)}; with AND: {sum(' AND ' in r['license'] for r in reuse)}; "
          f"with OR: {sum(' OR ' in r['license'] for r in reuse)}; single id: {sum(len(ids(r['license']))==1 for r in reuse)}; "
          f"TOM none: {sum(r['tom_none']=='yes' for r in reuse)}; conf {Counter(r['confidence'] for r in reuse)}; "
          f"ids per value {Counter(len(set(ids(r['license']))) for r in reuse)}")
    print(f"(b) reuse vs TOM: {Counter(r['vs_tom'] for r in reuse)}")
    decl = [r for r in ok if r["evidence_kind"] in ("readme", "manifest", "notice-file", "license-file-notice", "sub-folder")
            and " AND " in r["license"]]
    print(f"\n(c) AND values from a declaration (readme/manifest/notice/sub-folder): {len(decl)}; by kind "
          f"{Counter(r['evidence_kind'] for r in decl)}; conf {Counter(r['confidence'] for r in decl)}; "
          f"TOM none {sum(r['tom_none']=='yes' for r in decl)}")
    pair = [r for r in ok if set(ids(r["license"])) in ({"Apache-2.0", "MIT"},) and " AND " in r["license"]]
    print(f"(c) 'Apache-2.0 AND MIT' values: {len(pair)}; by kind {Counter(r['evidence_kind'] for r in pair)}; "
          f"conf {Counter(r['confidence'] for r in pair)}; TOM {Counter(r['tom'] for r in pair).most_common(5)}")
    orv = [r for r in ok if " OR " in r["license"]]
    print(f"(c) values with OR: {len(orv)}; 'Apache-2.0 OR MIT': {sum(set(ids(r['license']))=={'Apache-2.0','MIT'} for r in orv)}")
    for k in ("readme",):
        sample = [f"{r['project']} {r['license']}" for r in decl if r["evidence_kind"] == k][:15]
        print(f"(c) {k} sample: " + "; ".join(sample))
    low = [r for r in ok if r["confidence"] == "low"]
    print(f"\n(d) low: {len(low)}; TOM none {sum(r['tom_none']=='yes' for r in low)}; vs TOM {Counter(r['vs_tom'] for r in low)}; "
          f"evidence {Counter(r['evidence_kind'] for r in low)}")
    med = [r for r in ok if r["confidence"] == "medium"]
    print(f"(d) medium: {len(med)}; TOM none {sum(r['tom_none']=='yes' for r in med)}; vs TOM {Counter(r['vs_tom'] for r in med)}")
    print(f"\n(e) licensee answered (not none): {sum(r['licensee_agreement']!='none' for r in ok)}; "
          f"confidence lowered by licensee disagree (licensee disagree and askalono disagree/none): "
          f"{sum(r['licensee_agreement']=='disagree' and r['askalono_agreement'] in ('disagree','none') for r in ok)}")

    # the proposal: publish high/medium values off the review list; hold the review list; low and none
    # keep the TOM value (NOASSERTION when TOM has none)
    held = {x["project"] for x in review if x["kind"] not in ("low", "failed")}
    tiers = Counter()
    for r in out:
        tn = r["tom_none"] == "yes"
        if r["status"] != "ok" or r["confidence"] == "none":
            t = "keep TOM value" if not tn else "NOASSERTION"
            tiers[("no pass value", t)] += 1
        elif r["confidence"] == "low":
            tiers[("low", "keep TOM value" if not tn else "NOASSERTION")] += 1
        elif r["project"] in held:
            tiers[(f"{r['confidence']}, review list", "keep TOM value" if not tn else "NOASSERTION until checked")] += 1
        else:
            tiers[(f"{r['confidence']}, not on review list",
                   "pass value (NOASSERTION in TOM)" if tn else
                   ("pass value (same ids as TOM)" if r["vs_tom"] in ("same", "same-ids") else
                    f"pass value (TOM differs: {r['vs_tom']})"))] += 1
    print("\n| group | column value | projects |\n|---|---|---:|")
    for (g, t), n in sorted(tiers.items()):
        print(f"| {g} | {t} | {n:,} |")
    print(f"| total | | {sum(tiers.values()):,} |")
    pub_none = sum(n for (g, t), n in tiers.items() if t == "pass value (NOASSERTION in TOM)")
    print(f"\nTOM NOASSERTION/missing that get a value under the proposal: {pub_none:,} of {len(none):,}")
    held_none = [r for r in out if r["project"] in held and r["tom_none"] == "yes" and r["confidence"] in ("high", "medium")]
    print(f"held NOASSERTION projects (high/medium on the review list): {len(held_none)}; by conf "
          f"{Counter(r['confidence'] for r in held_none)}")


if __name__ == "__main__":
    main()
