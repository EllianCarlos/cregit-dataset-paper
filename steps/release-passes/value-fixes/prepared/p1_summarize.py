#!/usr/bin/env python3
"""Fix 1 (license outside GitHub): turn the scan lines of p1_scan_outside_github.py into
license_fill_outside_github.tsv (one row per project) and license_fill_outside_github.summary.md.

Usage: python3 -I p1_summarize.py SCAN.jsonl INPUT.tsv OUT.tsv OUT.md

proposed_value: the real SPDX ids that licensee 9.18.0 finds at confidence 98 (GitHub's method and id
style), sorted and ';'-joined like the LICENSES/ rule (build_batch25_inputs.py); empty when none.
Classes (the first that applies; the rules of ../33_license_summary.py, with licensee-98 split):
  licensee-98          every license file licensee matched gives a real id at 98
  licensee-98-partial  licensee gives a real id at 98, but also NOASSERTION/other for another file
  licensee-80          a real id only at confidence 80
  other-scanner        askalono (score >= 0.90) or ScanCode (no LicenseRef) names a real id
  scancode-only        only ScanCode finds something, and only as a LicenseRef or mixed expression
  no-file              no root license file (or LICENSES/ folder) at the pinned commit
  unclear              a license file, but no scanner names an id
  error                the fetch failed
"""
import collections
import json
import sys

BAD = {"NOASSERTION", "NONE", "other", "", None}
PACKAGE = {"Cargo.toml", "package.json", "pom.xml", "setup.cfg", "pyproject.toml", "DESCRIPTION", "meson.build"}


def real(x):
    return x not in BAD and not str(x).startswith("LicenseRef")


def lic_ids(rec, key):
    return sorted({i for i in (rec.get(key) or {}).get("licenses", []) if real(i)})


def lic_partial(rec, key):
    return any(not real(i) for i in (rec.get(key) or {}).get("licenses", []))


def askalono_ids(rec):
    return sorted({v["license"] for v in (rec.get("askalono") or {}).values()
                   if isinstance(v, dict) and v.get("license") and (v.get("score") or 0) >= 0.90})


def lic_files(rec):
    return [f for f in rec.get("files", []) if f.split("/")[-1] not in PACKAGE]


def scancode_ids(rec):
    names = {f.replace("/", "__") for f in lic_files(rec)}
    vals = [v for k, v in (rec.get("scancode") or {}).items() if k in names and isinstance(v, str) and v]
    clean = sorted({v for v in vals if "LicenseRef" not in v})
    mixed = sorted({v for v in vals if "LicenseRef" in v})
    return clean, mixed


def folder_ids(rec):
    """The LICENSES/ rule of the selection (build_batch25_inputs.py): the stems of LICENSES/*.txt|.md, sorted (here also
    names with no .txt or .md extension, which the rule did not meet on GitLab; CMakeLists.txt and READMEs left out)."""
    out = set()
    for f in rec.get("files", []):
        d, _, n = f.rpartition("/")
        if d.lower() in ("licenses", "licences") and n not in ("CMakeLists.txt", "README.md", "README"):
            out.add(n.rsplit(".", 1)[0] if n.lower().endswith((".txt", ".md")) else n)
    return sorted(out)


def classify(rec):
    if "error" in rec:
        return "error"
    l98, l80, ask = lic_ids(rec, "licensee_98"), lic_ids(rec, "licensee_80"), askalono_ids(rec)
    clean, mixed = scancode_ids(rec)
    if l98:
        return "licensee-98-partial" if lic_partial(rec, "licensee_98") else "licensee-98"
    if l80:
        return "licensee-80"
    if ask or clean:
        return "other-scanner"
    if mixed:
        return "scancode-only"
    if not lic_files(rec):
        return "no-file"
    return "unclear"


CLASSES = ["licensee-98", "licensee-98-partial", "licensee-80", "other-scanner", "scancode-only", "no-file",
           "unclear", "error"]


def clean_cell(s):
    return str(s).replace("\t", " ").replace("\n", " ")


def main():
    scan, inp, out_tsv, out_md = sys.argv[1:5]
    recs = {}
    for ln in open(scan, encoding="utf-8"):
        if ln.strip():
            r = json.loads(ln)
            recs[r["project"]] = r
    with open(inp, encoding="utf-8") as fh:
        head = fh.readline().rstrip("\n").split("\t")
        rows = [dict(zip(head, ln.rstrip("\n").split("\t"))) for ln in fh if ln.strip()]
    cols = ["project", "host", "run_commit", "old_value", "proposed_value", "licensee_80_ids", "askalono_ids",
            "scancode_ids", "licenses_folder_ids", "license_files", "class", "fetch"]
    by_class, by_host = collections.Counter(), collections.defaultdict(collections.Counter)
    ids98 = collections.Counter()
    missing = []
    with open(out_tsv, "w", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for row in rows:
            r = recs.get(row["project"])
            if r is None:
                missing.append(row["project"])
                continue
            c = classify(r)
            clean, mixed = scancode_ids(r)
            v = ";".join(lic_ids(r, "licensee_98"))
            vals = dict(project=row["project"], host=row["host"], run_commit=row["run_commit"], old_value="NOASSERTION",
                        proposed_value=v, licensee_80_ids=";".join(lic_ids(r, "licensee_80")),
                        askalono_ids=";".join(askalono_ids(r)), scancode_ids=";".join(clean + mixed), licenses_folder_ids=";".join(folder_ids(r)),
                        license_files=";".join(lic_files(r)), **{"class": c},
                        fetch=r.get("fetch") or ("error: " + r.get("error", "")))
            fh.write("\t".join(clean_cell(vals[k]) for k in cols) + "\n")
            by_class[c] += 1
            by_host[row["host"]][c] += 1
            if v:
                ids98[v] += 1
    n = sum(by_class.values())
    filled = by_class["licensee-98"] + by_class["licensee-98-partial"]
    md = ["# License fill outside GitHub: result classes", "",
          f"Projects: {len(rows)} (NOASSERTION, not on GitHub); scanned: {n}; missing scan lines: {len(missing)}.",
          f"A proposed value (licensee at confidence 98): {filled} of {n}. Personal-account projects: none in this set.",
          f"Projects with a root LICENSES/ folder: {sum(1 for r in recs.values() if folder_ids(r))}; their folder ids "
          "(the selection's LICENSES/ rule) are in the column licenses_folder_ids. licensee does not read those "
          "SPDX-named files, so most of them fall to other-scanner.",
          f"Projects with 12 or more root license files (the fetch cap): "
          f"{sum(1 for r in recs.values() if len(r.get('files', [])) >= 12)}.",
          "", "| class | projects |", "|---|---:|"]
    md += [f"| {k} | {by_class[k]} |" for k in CLASSES]
    md += ["", "## By host", "", "| host | projects | " + " | ".join(CLASSES) + " |",
           "|---|---:|" + "---:|" * len(CLASSES)]
    for h in sorted(by_host, key=lambda h: -sum(by_host[h].values())):
        md.append(f"| {h} | {sum(by_host[h].values())} | " + " | ".join(str(by_host[h][k]) for k in CLASSES) + " |")
    md += ["", "## Proposed values (licensee 98)", "", "| proposed value | projects |", "|---|---:|"]
    md += [f"| {k} | {v} |" for k, v in ids98.most_common()]
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
