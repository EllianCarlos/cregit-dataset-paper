#!/usr/bin/env python3
"""Write the inputs of supplement batch 26 (user decision 2026-10-14 ~16:40 UTC, "yes to mutt": the DP8L v4
near-miss classes C, D and E also pass GitLab rows) for `s7-run/build_run.sh supplement 26 SRC LICENSES`
with POOL=../s2-pool/v2/pool.batch26.csv.

Rows: decisions.tsv "keep" rows that pass DP3 and fail DP8L in measure.jsonl, and that pass a near-miss class in
near_miss.tsv (near_miss_gitlab.py). The columns and rules are those of build_batch25_inputs.py. The license
value is NOASSERTION, and the evidence is "<class>: <names>", the form of s4-filter/supplement_batch.py for the
near-miss rows of batch 23. Refuses to overwrite.
  ../../s4-filter/supplement26.gitlab.csv, ../../s4-filter/supplement26.licenses.csv, ../v2/pool.batch26.csv
The pinned commit is the HEAD that measure_dp.py fetched (measured_at). Snapshot: 2026-10-14.
"""
import csv, glob, json, sys
from pathlib import Path
H = Path(__file__).resolve().parent; DS = H.parent.parent
sys.path.insert(0, str(DS / "s4-filter"))
import funnel  # noqa: E402  u_of, size_class
CAT = {"C": ("C near miss: other root name", "root_near_names"),
       "D": ("D near miss: package file declares a license", "package_files"),
       "E": ("E near miss: license file in a subfolder", "subfolder_examples")}  # audit_dp8l.py report() names
def norm(u):
    u = (u or "").strip().lower().replace("http://", "https://").rstrip("/")
    return u[:-4] if u.endswith(".git") else u
rows = {}
for f in sorted(glob.glob(str(H / "rows/*.jsonl"))):
    for l in open(f):
        r = json.loads(l)
        if not r.get("removed_by"): rows[norm(r["url"])] = r  # the row of the round that kept it
meas = {json.loads(l)["url"]: json.loads(l) for l in open(H / "measure.jsonl")}
near = {r["url"]: r for r in csv.DictReader(open(H / "near_miss.tsv"), delimiter="\t")}
scr = {}
for f in glob.glob(str(H / "screen*.tsv")):
    for r in csv.DictReader(open(f), delimiter="\t"): scr[r["url"]] = r
keep = [r["url"] for r in csv.DictReader(open(H / "decisions.tsv"), delimiter="\t") if r["decision"] == "keep"]
out_f, out_l, out_p = DS / "s4-filter/supplement26.gitlab.csv", DS / "s4-filter/supplement26.licenses.csv", H.parent / "v2/pool.batch26.csv"
for p in (out_f, out_l, out_p): assert not p.exists(), f"{p} exists"
frame, lic, pool, dropped = [], [], [], []
for u in keep:
    m = meas[u]
    if not (m["status"] == "ok" and m["dp3"] and not m["dp8l"]): continue  # batch 25 has the DP8L rows
    n = near[u]
    if n["passes"] != "True": dropped.append((u, f"class {n['cls']}")); continue
    assert n["head_oid"] == m["head_oid"], u
    g = rows[u]; host = g["host"]; path = g["path"]
    web = f"https://{host}/{path}"; key = f"url:{web}"; commits = int(scr[u]["commits"])
    langs = g.get("languages") or {}; prim = max(langs, key=langs.get) if langs else ""
    frame.append(dict(slug=path, host=host, repo_url=web, head_oid=m["head_oid"], u=funnel.u_of(path), size_class=funnel.size_class(commits),
                      labels="pending", layer="≥ 5,000", commits=commits, language=prim, tok_bytes=m["tok_bytes"],
                      tok_vendor_bytes=m["tok_vendor_bytes"], pushed_at="", stars=g.get("stars") or "", pool_key=key))
    c, col = CAT[n["cls"]]
    lic.append(dict(pool_key=key, slug=path, license="NOASSERTION", license_evidence=f"{c}: {n[col]}"))
    pool.append(dict(pool_key=key, host=host, database_id=g["id"], name_with_owner="", repo_url=web,
                     origins=("gitlab-search:" + g["search"] if g.get("search") else f"gitlab:{host}"), input_slugs="", in_search="",
                     archived="False", fork="False", mirror="", empty="False", created_at=g.get("created_at") or "", pushed_at="",
                     stars=g.get("stars") or "", owner_type="", owner_login=path.split("/")[0], license="", primary_language=prim,
                     languages_total_bytes="", languages="", default_branch=g["default_branch"], head_oid=m["head_oid"],
                     head_committed_at="", fetched_at=g["listed_at"], fetched_by="s2-pool/gitlab/" + ("personal_rows.py" if "personal" in (g.get("search") or "") else "search_gitlabcom_stars.py" if g.get("search") else "list_gitlab.py")))
frame.sort(key=lambda r: (r["u"], r["slug"]))
cols = ["slug", "host", "repo_url", "head_oid", "u", "size_class", "labels", "layer", "commits", "language", "tok_bytes", "tok_vendor_bytes", "pushed_at", "stars", "pool_key"]
with open(out_f, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, cols, lineterminator="\n"); w.writeheader(); w.writerows({**r, "u": repr(r["u"])} for r in frame)
with open(out_l, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, ["pool_key", "slug", "license", "license_evidence"], lineterminator="\n"); w.writeheader(); w.writerows(lic)
pcols = next(csv.reader(open(H.parent / "pool.csv")))
with open(out_p, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, pcols, lineterminator="\n"); w.writeheader(); w.writerows(pool)
print(f"{len(frame)} rows; dropped {dropped}; size classes", {k: sum(r['size_class'] == k for r in frame) for k in 'SML'})
