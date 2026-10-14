#!/usr/bin/env python3
"""Shared-history check by root commit for the layer 1 candidates (2026-10-13, read-only).

The name-based check in screen_layer1.py misses copies with another name (drm/kernel is a Linux tree,
wine-gecko is a Firefox tree). This script:
  1. gets the oldest commit of each candidate: GitLab API v4 GET /projects/:id/repository/commits
     ?ref_name=<default>&per_page=1&page=<commit count> (the last page of the history listing;
     normally a root commit, parent_ids empty);
  2. for each distinct root, asks the GitHub commit search (gh api search/commits, q=hash:<root>;
     it covers the default branches of public repositories, forks only in special cases), up to 3
     pages of 100, and intersects the repositories with the pool (pool.csv + v2 files) and with the
     frame (s4-filter/frame.v4.csv);
  3. writes roots.tsv: url, root, root_is_parentless, github_total, pool_hits, frame_hits.
GitHub search limit: 30 requests per minute; the script sleeps 2.2 s between requests.
Resumable: rows already in roots.tsv are skipped.
"""
import csv, glob, json, subprocess, sys, time, urllib.parse, urllib.request
from pathlib import Path
H = Path(__file__).resolve().parent; POOL = H.parent; S4 = POOL.parent / "s4-filter"
def norm(u):
    u = (u or "").strip().lower().replace("http://", "https://").rstrip("/")
    return u[:-4] if u.endswith(".git") else u
pool = set()
for f in ["pool.csv", "v2/pool.supplement.csv", "v2/pool.batch22.csv", "v2/pool.batch23.csv"]:
    for r in csv.DictReader(open(POOL / f)): pool.add(r["name_with_owner"].lower())
frame = {r["slug"].lower(): ("L1" if r["layer"].startswith("≥") else "lower") for r in csv.DictReader(open(S4 / "frame.v4.csv"))}
rows = {}
for f in glob.glob(str(H / "rows/*.jsonl")):
    for l in open(f):
        r = json.loads(l); rows[norm(r["url"])] = r
cands = []
for f in glob.glob(str(H / "screen*.tsv")):
    for r in csv.DictReader(open(f), delimiter="\t"):
        if r["step_result"] == "layer 1 candidate": cands.append((r["url"], int(r["commits"])))
out_p = H / "roots.tsv"
done = set()
if out_p.exists(): done = {l.split("\t")[0] for l in out_p.read_text().splitlines()[1:]}
else: out_p.write_text("url\troot\troot_is_parentless\tgithub_total\tpool_hits\tframe_hits\tchecked_at\n")
out = open(out_p, "a"); seen = {}
for l in out_p.read_text().splitlines()[1:]:
    p = l.split("\t"); seen[p[1]] = p[3:6]
def api(url):
    for t in range(4):
        try:
            with urllib.request.urlopen(url, timeout=300) as r: return json.load(r)
        except Exception: time.sleep(15 * (t + 1))
    return None
for url, n in cands:
    if url in done: continue
    r = rows[url]
    d = api(f"https://{r['host']}/api/v4/projects/{r['id']}/repository/commits?" + urllib.parse.urlencode(dict(ref_name=r["default_branch"], per_page=1, page=n)))
    time.sleep(0.5)
    if not d: out.write(f"{url}\t\t\t\t\t\tlookup failed\n"); continue
    root, parentless = d[0]["id"], not d[0]["parent_ids"]
    if root not in seen:
        tot, names = 0, set()
        for pg in (1, 2, 3):
            p = subprocess.run(["gh", "api", "-X", "GET", "search/commits", "-f", f"q=hash:{root}", "-f", "per_page=100", "-f", f"page={pg}"],
                               capture_output=True, text=True); time.sleep(2.2)
            if p.returncode: break
            j = json.loads(p.stdout); tot = j["total_count"]
            names |= {i["repository"]["full_name"].lower() for i in j["items"]}
            if pg * 100 >= tot: break
        seen[root] = [str(tot), ",".join(sorted(names & pool)), ",".join(sorted(f"{x}({frame[x]})" for x in names if x in frame))]
    g = seen[root]
    out.write(f"{url}\t{root}\t{parentless}\t{g[0]}\t{g[1]}\t{g[2]}\t{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"); out.flush()
