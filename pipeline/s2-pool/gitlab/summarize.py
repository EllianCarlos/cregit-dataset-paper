#!/usr/bin/env python3
"""Summary of the GitLab pool extension measurement (2026-10-14). Reads rows/*.jsonl, screen*.tsv,
roots.tsv, frame_object_hits.tsv and ../../s4-filter/frame.v4.csv; writes summary.md (the count tables)
and candidates.tsv (the layer 1 candidates with their class). Counts only: nothing goes to the pool."""
import collections, csv, glob, json, statistics
from pathlib import Path
H = Path(__file__).resolve().parent; S4 = H.parent.parent / "s4-filter"
def norm(u):
    u = (u or "").strip().lower().replace("http://", "https://").rstrip("/")
    return u[:-4] if u.endswith(".git") else u
lst = collections.defaultdict(collections.Counter); host_of = {}
for f in sorted(glob.glob(str(H / "rows/*.jsonl"))):
    key = Path(f).stem.split("__")[0]
    key = "gitlab.com (roster groups)" if key == "gitlab.com" else key
    for l in open(f):
        r = json.loads(l); lst[key]["listed"] += 1; lst[key][r["removed_by"] or "kept"] += 1; host_of[norm(r["url"])] = key
scr = collections.defaultdict(collections.Counter); sc = {}
for f in glob.glob(str(H / "screen*.tsv")):
    for r in csv.DictReader(open(f), delimiter="\t"):
        k = host_of.get(r["url"], r["host"]); scr[k][r["step_result"]] += 1; sc[r["url"]] = r
roots = {r["url"]: r for r in csv.DictReader(open(H / "roots.tsv"), delimiter="\t")}
obj = collections.defaultdict(set)
for l in open(H / "frame_object_hits.tsv"):
    x, slug, layer = l.rstrip("\n").split("\t"); obj[x].add(slug)
frame = list(csv.DictReader(open(S4 / "frame.v4.csv")))
nongh = collections.defaultdict(list)
for r in frame:
    if r["host"] != "github.com": nongh[r["slug"].rstrip("/").split("/")[-1].lower()].append(r["slug"])
# hours per commit bucket from the layer 1 frame (63 s per tokenizable MB, as funnel.py)
b = collections.defaultdict(list)
def bucket(n): return "5k-20k" if n < 20000 else "20k-100k" if n < 100000 else "100k-500k" if n < 500000 else ">=500k"
for r in frame:
    if r["layer"].startswith("≥") and r["commits"] and r["tok_bytes"]:
        b[bucket(int(r["commits"]))].append(int(r["tok_bytes"]) / 1e6 * 63 / 3600)
med = {k: statistics.median(v) for k, v in b.items()}
rows = []
for u, s in sc.items():
    if s["step_result"] != "layer 1 candidate": continue
    rt = roots.get(u, {}); root = rt.get("root", "")
    fh = rt.get("frame_hits", "") or ",".join(sorted(obj.get(root, ())))
    if fh: cls = "skip: shares history with a frame row"
    elif rt.get("pool_hits"): cls = "skip: shares history with a pool row (not in the frame)"
    else: cls = "new"
    name = u.split("/")[-1]
    rows.append(dict(host=host_of.get(u, s["host"]), url=u, commits=int(s["commits"]), dp8l=s["dp8l"], root=root,
                     github_total=rt.get("github_total", ""), frame_hits=fh, pool_hits=rt.get("pool_hits", ""),
                     cls=cls, nongh_frame_same_name=",".join(nongh.get(name.lower(), [])),
                     est_hours=round(med[bucket(int(s["commits"]))], 1)))
# clusters among the new rows: one history per root
new = [r for r in rows if r["cls"] == "new"]
by_root = collections.defaultdict(list)
for r in new: by_root[r["root"]].append(r)
for root, rs in by_root.items():
    rs.sort(key=lambda r: (-r["commits"], r["url"]))
    for i, r in enumerate(rs): r["root_cluster"] = f"{len(rs)} rows" + ("" if i == 0 else " (not first)")
with open(H / "candidates.tsv", "w") as fo:
    keys = ["host", "url", "commits", "dp8l", "cls", "root_cluster", "github_total", "frame_hits", "pool_hits", "nongh_frame_same_name", "est_hours", "root"]
    fo.write("\t".join(keys) + "\n")
    for r in sorted(rows, key=lambda r: (r["cls"], r["host"], r["url"])): fo.write("\t".join(str(r.get(k, "")) for k in keys) + "\n")
L = ["# GitLab pool extension: measurement (counts only)", "", "Computed by summarize.py. Each row gets the first step that removes it.", "",
     "## Listing (server filters: public, not archived, last activity on or after 2025-04-03)", "",
     "| Host | Listed | Personal namespace | Fork | Empty | No default branch | No C/C++/Java/Rust | Kept |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
T = collections.Counter()
for k in sorted(lst):
    c = lst[k]; v = [c["listed"], c["personal namespace"], c["fork"], c["empty repository"], c["no default branch"], c["no C, C++, Java or Rust in the languages API"], c["kept"]]
    for i, x in enumerate(v): T[i] += x
    L.append(f"| {k} | " + " | ".join(f"{x:,}" for x in v) + " |")
L.append("| **total** | " + " | ".join(f"**{T[i]:,}**" for i in range(7)) + " |")
L += ["", "## Screen of the kept rows", "", "| Host | Already in the pool | < 5,000 commits | Shares history (same name) | Failed | Layer 1 candidate |", "|---|---:|---:|---:|---:|---:|"]
T = collections.Counter()
for k in sorted(scr):
    c = scr[k]; v = [c["already in the pool"], c["< 5,000 commits"] + c["< 5,000 commits (clone count)"], c["shares history with a pool row"],
                     c["clone failed"] + c["commit screen failed"], c["layer 1 candidate"]]
    for i, x in enumerate(v): T[i] += x
    L.append(f"| {k} | " + " | ".join(f"{x:,}" for x in v) + " |")
L.append("| **total** | " + " | ".join(f"**{T[i]:,}**" for i in range(5)) + " |")
cc = collections.Counter(r["cls"] for r in rows)
L += ["", "## Layer 1 candidates by shared history (root commit)", ""] + [f"- {k}: {v}" for k, v in sorted(cc.items())]
L += [f"- new rows in {len(by_root)} distinct histories (root commits); the largest clusters: " +
      ", ".join(f"{len(v)} x {v[0]['url'].split('/', 3)[3]}" for v in sorted(by_root.values(), key=len, reverse=True)[:6])]
nd = [r for r in new if r.get("root_cluster", "").endswith("rows")]
dp = collections.Counter(r["dp8l"] for r in nd)
L += ["", f"New, one row per history: {len(nd)} (DP8L root check: {dict(dp)}). Same name as a non-GitHub frame row: "
      f"{sum(1 for r in nd if r['nongh_frame_same_name'])}.",
      f"Expected after DP3 (80.3% pass rate of the GitHub layer 1 rows): about {round(len(nd) * 0.803)}.",
      f"Estimated serial pipeline hours (median hours of the layer 1 frame per commit bucket, {', '.join(f'{k} {v:.1f} h' for k, v in sorted(med.items()))}): "
      f"about {sum(r['est_hours'] for r in nd):,.0f} h before DP3."]
L += ["", "Note (2026-10-14): the row gitlab.com-search-personal lists again the 18 personal-namespace rows that the row gitlab.com-search removes (user decision ~15:35 UTC: the search takes personal namespaces too); in the screen table both search files count under gitlab.com-search. Of the 10 kept personal rows, 8 have fewer than 5,000 commits, OpenRGB shares history with the frame row CalcProgrammer1/OpenRGB (same project), and muttmua/mutt (8,687 commits; upstream of the frame row neomutt/neomutt) fails DP8L (root files COPYRIGHT and GPL only). So no personal row entered v1 at first. Since ~16:40 UTC (user: \"yes to mutt\") the DP8L v4 near misses also pass GitLab rows: mutt (class C) enters v1 as batch 26 (near_miss.tsv, README.md fourth round)."]
(H / "summary.md").write_text("\n".join(L) + "\n"); print("\n".join(L))
