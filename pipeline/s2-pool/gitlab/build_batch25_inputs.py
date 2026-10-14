#!/usr/bin/env python3
"""Write the inputs of supplement batch 25 (the GitLab rows; user decision 2026-10-14 ~01:00 UTC "into v1
as batch 25") for `s7-run/build_run.sh supplement 25 SRC LICENSES` with POOL=../s2-pool/v2/pool.batch25.csv.

Rows: decisions.tsv "keep", minus the rows that fail DP3 or DP8L in measure.jsonl. Refuses to overwrite.
  ../../s4-filter/supplement25.gitlab.csv   frame.csv columns (funnel.py: slug = URL path, u = u_of(slug),
                                            size_class by commits, labels pending, layer "≥ 5,000"), u order
  ../../s4-filter/supplement25.licenses.csv pool_key, slug, license, license_evidence: the names of the
                                            root LICENSES/<id>.txt|.md files (GitLab tree API; the rule of supplement_batch.py), else NOASSERTION;
                                            the evidence is the root license file names
  ../v2/pool.batch25.csv                    pool.csv columns; origins "gitlab:<host>" (instance listing) or
                                            "gitlab-search:stars>400" (gitlab.com search)
The pinned commit is the HEAD that measure_dp.py fetched (measured_at). Snapshot: 2026-10-14.
"""
import csv, glob, json, sys, time, urllib.parse, urllib.request
from pathlib import Path
H = Path(__file__).resolve().parent; DS = H.parent.parent
sys.path.insert(0, str(DS / "s4-filter"))
import funnel  # noqa: E402  u_of, size_class
def norm(u):
    u = (u or "").strip().lower().replace("http://", "https://").rstrip("/")
    return u[:-4] if u.endswith(".git") else u
rows = {}
for f in glob.glob(str(H / "rows/*.jsonl")):
    for l in open(f):
        r = json.loads(l); rows[norm(r["url"])] = r
meas = {json.loads(l)["url"]: json.loads(l) for l in open(H / "measure.jsonl")}
scr = {}
for f in glob.glob(str(H / "screen*.tsv")):
    for r in csv.DictReader(open(f), delimiter="\t"): scr[r["url"]] = r
keep = [r["url"] for r in csv.DictReader(open(H / "decisions.tsv"), delimiter="\t") if r["decision"] == "keep"]
out_f, out_l, out_p = DS / "s4-filter/supplement25.gitlab.csv", DS / "s4-filter/supplement25.licenses.csv", H.parent / "v2/pool.batch25.csv"
for p in (out_f, out_l, out_p): assert not p.exists(), f"{p} exists"
frame, lic, pool, dropped = [], [], [], []
for u in keep:
    m = meas[u]
    if not (m["status"] == "ok" and m["dp3"] and m["dp8l"]):
        dropped.append((u, "DP3" if not m.get("dp3") else "DP8L")); continue
    g = rows[u]; host = g["host"]; path = g["path"]
    web = f"https://{host}/{path}"; key = f"url:{web}"; commits = int(scr[u]["commits"])
    langs = g.get("languages") or {}; prim = max(langs, key=langs.get) if langs else ""
    frame.append(dict(slug=path, host=host, repo_url=web, head_oid=m["head_oid"], u=funnel.u_of(path), size_class=funnel.size_class(commits),
                      labels="pending", layer="≥ 5,000", commits=commits, language=prim, tok_bytes=m["tok_bytes"],
                      tok_vendor_bytes=m["tok_vendor_bytes"], pushed_at="", stars=g.get("stars") or "", pool_key=key))
    ids = []
    if any(n.lower() in ("licenses", "licences") for n in m["license_names"]):
        t = json.load(urllib.request.urlopen(f"https://{host}/api/v4/projects/{g['id']}/repository/tree?" + urllib.parse.urlencode(
            dict(ref=g["default_branch"], path=next(n for n in m["license_names"] if n.lower() in ("licenses", "licences")), per_page=100)), timeout=120))
        ids = sorted(x["name"].rsplit(".", 1)[0] for x in t if x["type"] == "blob" and x["name"].endswith((".txt", ".md"))); time.sleep(0.5)
    lic.append(dict(pool_key=key, slug=path, license=";".join(ids) if ids else "NOASSERTION",
                    license_evidence=";".join(m["license_names"]) + (f" (LICENSES/: {';'.join(ids)})" if ids else "")))
    pool.append(dict(pool_key=key, host=host, database_id=g["id"], name_with_owner="", repo_url=web,
                     origins=("gitlab-search:stars>400" if g.get("search") else f"gitlab:{host}"), input_slugs="", in_search="",
                     archived="False", fork="False", mirror="", empty="False", created_at=g.get("created_at") or "", pushed_at="",
                     stars=g.get("stars") or "", owner_type="", owner_login=path.split("/")[0], license="", primary_language=prim,
                     languages_total_bytes="", languages="", default_branch=g["default_branch"], head_oid=m["head_oid"],
                     head_committed_at="", fetched_at=g["listed_at"], fetched_by="s2-pool/gitlab/" + ("search_gitlabcom_stars.py" if g.get("search") else "list_gitlab.py")))
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
