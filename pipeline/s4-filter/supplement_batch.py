#!/usr/bin/env python3
"""The inputs of supplement batch N for `s7-run/build_run.sh supplement N SRC LICENSES`
(batch 22, 2026-10-10: the new layer 1 rows of the GNU roster v2, and any other new
layer 1 row of supplement.v3.csv).

  python3 supplement_batch.py N [V]

V is the funnel version, v3 (the default) or v4 (batch 23, 2026-10-11: supplement.v4.csv of
funnel.py --near-miss, DP8L v4). The file names below use V in place of v3.

Writes (refuses to overwrite):
  supplementN.v3.csv        the layer 1 rows of supplement.v3.csv whose manifest name and
                            URL are in no manifest of batches 1..N-1 (s7-run/manifest.batchK.tsv),
                            in u order (frame.csv columns);
  supplementN.licenses.csv  pool_key, slug, license, license_evidence for its rows whose pool
                            license is blank: the SPDX names of the license files found at the
                            root (LICENSES/<id>.txt), else NOASSERTION; the evidence is the
                            file names (clone_facts license_files, or dp8l-audit/licenses.csv);
                            a near-miss row of DP8L v4 (dp8l-audit/results.csv, category C, D or E)
                            gets NOASSERTION, and the evidence is "<class>: <file names>";
  ../s2-pool/v2/pool.batchN.csv  the pool rows of these keys, from pool.csv and
                            pool.supplement.csv (POOL= for build_run.sh, so enrich_meta.py
                            finds the new rows).
"""
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEL = HERE.parent
sys.path.insert(0, str(SEL / "s7-run"))
from enrich_meta import project_name  # noqa: E402


def manifest_rows(n):
    names, urls = set(), set()
    for k in range(1, n):
        p = SEL / f"s7-run/manifest.batch{k}.tsv"
        if not p.exists():
            raise SystemExit(f"FAIL {p} is missing")
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                f = line.split("\t")
                names.add(f[0])
                urls.add(f[1].lower().removesuffix(".git").rstrip("/"))
    return names, urls


def last_rows(path, key):
    out = {}
    if path.exists():
        for line in path.open():
            d = json.loads(line)
            out[d[key]] = d
    return out


NEAR_MISS_FILES = {"C": "root_near_names", "D": "package_files", "E": "subfolder_examples"}


def main(n, v="v3"):
    assert v in ("v3", "v4"), v
    outs = [HERE / f"supplement{n}.{v}.csv", HERE / f"supplement{n}.licenses.csv", SEL / f"s2-pool/v2/pool.batch{n}.csv"]
    for o in outs:
        if o.exists():
            raise SystemExit(f"FAIL {o} exists")
    names, urls = manifest_rows(n)
    rows = []
    for r in csv.DictReader(open(HERE / f"supplement.{v}.csv", encoding="utf-8")):
        if r["layer"] != "≥ 5,000":
            continue
        name = project_name(r["host"].strip().lower() or "github.com", r["slug"])
        url = r["repo_url"].lower().removesuffix(".git").rstrip("/")
        if name in names or url in urls:
            continue
        rows.append(r)
    assert all(float(rows[i]["u"]) <= float(rows[i + 1]["u"]) for i in range(len(rows) - 1)), "not in u order"
    keys = {r["pool_key"] for r in rows}
    pool = {}
    for src in (SEL / "s2-pool/pool.csv", SEL / "s2-pool/v2/pool.supplement.csv"):
        for p in csv.DictReader(open(src, encoding="utf-8")):
            if p["pool_key"] in keys:
                assert p["pool_key"] not in pool, p["pool_key"]
                pool[p["pool_key"]] = p
    assert set(pool) == keys, keys - set(pool)
    cf = last_rows(SEL / "s3-measure/clone_facts.jsonl", "pool_key")
    cf.update(last_rows(SEL / "s3-measure/v2/clone_facts.jsonl", "pool_key"))
    audit = {r["pool_key"]: r for r in csv.DictReader(open(HERE / "dp8l-audit/licenses.csv", encoding="utf-8"))}
    near = {r["pool_key"]: r for r in csv.DictReader(open(HERE / "dp8l-audit/results.csv", encoding="utf-8"))
            if v == "v4" and r["category"][:1] in NEAR_MISS_FILES}
    lic = []
    for r in rows:
        k = r["pool_key"]
        if pool[k]["license"]:
            continue
        if k in audit:
            lic.append([k, r["slug"], audit[k]["license"], audit[k]["license_evidence"]])
            continue
        if k in near:
            c = near[k]["category"]
            lic.append([k, r["slug"], "NOASSERTION", f"{c}: {near[k][NEAR_MISS_FILES[c[0]]]}"])
            continue
        files = (cf.get(k) or {}).get("license_files") or []
        spdx = sorted({m.group(1) for f in files for m in [re.match(r"^LICENSES/(.+?)\.(?:txt|md)$", f)] if m})
        lic.append([k, r["slug"], ";".join(spdx) or "NOASSERTION", ";".join(files)])
    with open(outs[0], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with open(outs[1], "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["pool_key", "slug", "license", "license_evidence"])
        w.writerows(lic)
    cols = list(next(iter(pool.values())).keys())
    with open(outs[2], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(pool[r["pool_key"]] for r in rows)
    print(f"batch {n}: {len(rows)} new layer 1 rows; {len(lic)} license values; pool rows {len(pool)}")


if __name__ == "__main__":
    main(int(sys.argv[1]), *sys.argv[2:3])
