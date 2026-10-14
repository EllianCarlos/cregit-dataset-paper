#!/usr/bin/env python3
"""Screen the listed GitLab rows (rows/*.jsonl, removed_by == "") for layer 1 and for duplicates.

Steps for each kept row, in order (2026-10-13, read-only, counts only):
  1. already in the pool: the normalized URL equals the repo_url of a pool row (pool.csv and the
     v2 supplement / batch22 / batch23 pool files). Not new.
  2. commit screen (GitLab API v4): GET /projects/:id/repository/commits?ref_name=<default>&per_page=1
     &page=5000. An empty page means < 5,000 commits: the row cannot enter layer 1 (DP7).
  3. for a row with >= 5,000 commits: a commit-only clone (git clone --bare --filter=tree:0) in a temp
     dir, then `git rev-list --count HEAD` (the DP7 count, as for the other hosts), and the duplicate
     check: for each pool row whose repository name (last path part, lower case) is equal, test
     `git cat-file -e <pool head_oid>` with GIT_NO_LAZY_FETCH=1 (a partial clone
     must not fetch a missing object from the remote: that made each test a network round trip). If the pool head commit is in the GitLab history, the two rows
     share history: "skip the GitLab copy" (user decision 2026-10-13). The clone is deleted at once.
  4. DP8L (other-host rule of s4-filter/dp8l_rule.py, root names only): GET /projects/:id/repository/tree
     at the default branch, root level; LICENSE*/LICENCE*/COPYING*/UNLICENSE* file or a LICENSES folder.
Output: screen.tsv (one row per kept row) and clusters.tsv (GitLab URL -> pool row, shared history).
Usage: [SCREEN_OUT=screen.<host>.tsv CLUSTERS_OUT=clusters.<host>.tsv] screen_layer1.py rows/<file>.jsonl ...
(rows already in the output file are skipped: resumable; one process per host)
"""
import csv, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
POOL = Path(__file__).resolve().parent.parent
def norm(u):
    u = (u or "").strip().lower().replace("http://", "https://").rstrip("/")
    return u[:-4] if u.endswith(".git") else u
url_in_pool, by_name = {}, {}
for f in ["pool.csv", "v2/pool.supplement.csv", "v2/pool.batch22.csv", "v2/pool.batch23.csv"]:
    for r in csv.DictReader(open(POOL / f)):
        url_in_pool[norm(r["repo_url"])] = r["pool_key"]
        nm = (r["name_with_owner"] or r["repo_url"]).rstrip("/").split("/")[-1].lower()
        if nm.endswith(".git"): nm = nm[:-4]
        if r["head_oid"]: by_name.setdefault(nm, []).append((r["pool_key"], r["head_oid"], r["repo_url"]))
def get(url, tries=5):
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            ra = e.headers.get("Retry-After"); time.sleep(int(ra) if ra and ra.isdigit() else 15 * (t + 1))
        except Exception: time.sleep(15 * (t + 1))
    return "FAIL"
LIC = ("license", "licence", "copying", "unlicense")
done = set()
sp = Path(os.environ.get("SCREEN_OUT", "screen.tsv"))
if sp.exists(): done = {l.split("\t")[1] for l in sp.read_text().splitlines()[1:]}
else: sp.write_text("host\turl\tstep_result\tcommits\tdup_of\tdp8l\tscreened_at\n")
out = open(sp, "a"); cl = open(os.environ.get("CLUSTERS_OUT", "clusters.tsv"), "a")
for f in sys.argv[1:]:
    for l in open(f):
        r = json.loads(l)
        if r["removed_by"] or norm(r["url"]) in done: continue
        api = f"https://{r['host']}/api/v4/projects/{r['id']}"
        u = norm(r["url"]); res = commits = dup = dp8l = ""
        if u in url_in_pool: res = "already in the pool"
        else:
            d = get(f"{api}/repository/commits?" + urllib.parse.urlencode(dict(ref_name=r["default_branch"], per_page=1, page=5000)))
            time.sleep(0.5)
            if d == "FAIL" or d is None: res = "commit screen failed"
            elif not d: res = "< 5,000 commits"
            else:
                t = tempfile.mkdtemp(dir="/local/home/ellianco/tmp-gitlab") 
                g = Path(t) / "r.git"
                p = subprocess.run(["git", "clone", "-q", "--bare", "--filter=tree:0", r["url"], str(g)], capture_output=True, timeout=3600)
                if p.returncode: res = "clone failed"
                else:
                    commits = subprocess.run(["git", "-C", str(g), "rev-list", "--count", "HEAD"], capture_output=True, text=True).stdout.strip()
                    nm = r["path"].split("/")[-1].lower()
                    for pk, oid, purl in by_name.get(nm, []):
                        if subprocess.run(["git", "-C", str(g), "cat-file", "-e", oid + "^{commit}"], capture_output=True, env=dict(os.environ, GIT_NO_LAZY_FETCH="1")).returncode == 0:
                            dup = pk; cl.write(f"{r['url']}\t{pk}\t{purl}\t{oid}\n"); cl.flush(); break
                    res = "shares history with a pool row" if dup else ("layer 1 candidate" if int(commits or 0) >= 5000 else "< 5,000 commits (clone count)")
                subprocess.run(["find", t, "-delete"])
                if res == "layer 1 candidate":
                    tr = get(f"{api}/repository/tree?" + urllib.parse.urlencode(dict(ref=r["default_branch"], per_page=100)))
                    names = [(x["name"].lower(), x["type"]) for x in tr] if isinstance(tr, list) else []
                    dp8l = "yes" if any(n.startswith(LIC) and ty == "blob" or (n == "licenses" and ty == "tree") for n, ty in names) else ("no" if names else "unknown")
        out.write(f"{r['host']}\t{u}\t{res}\t{commits}\t{dup}\t{dp8l}\t{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"); out.flush()
        done.add(u)
