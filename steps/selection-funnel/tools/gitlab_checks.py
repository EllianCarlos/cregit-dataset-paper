#!/usr/bin/env python3
"""GitLab rows that pass the tokei rule and DP8L v4 but have no commit count of 1,000 or more on record (the GitLab
screen read only "< 5,000 commits" or nothing), and the copy checks that the GitLab screen ran only for rows with
5,000 or more commits.

For each such row (read-only GitLab API v4, unauthenticated, one call at a time per host, 0.5 s apart):
  1. commit probe: GET /projects/:id/repository/commits?ref_name=<default>&per_page=1&page=1000. A non-empty page
     means 1,000 or more commits (the screen_layer1.py probe, with page 1000 in place of 5000).
  2. for a row with 1,000 or more commits and no shared-history check on record: the duplicate check of
     screen_layer1.py, with the API in place of a commit-only clone (no history is cloned here): for each pool row
     whose repository name (last path part, lower case) is equal, GET /projects/:id/repository/commits/<pool head_oid>.
     HTTP 200 means that the pool head commit is in the GitLab repository: the rows share history (pool merge).
  3. the R1 copy namespace pattern of decide.py, on the lower-case URL (as decide.py; fixed 2026-11-08).
Output: work/gitlab_checks.jsonl (one line per row; resumable).
"""
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
W = HERE / "work"
SEL = Path.home() / "STUDY-REPOSITORY/dataset-selection"
G = SEL / "s2-pool/gitlab"
sys.path.insert(0, str(G))
COPY = re.compile(r"/(mirrors|infrastructure/mirrors|neon/backports-[^/]+|neon/forks|gfx-ci|mesa_ci|openhw-group/backup-\d+)/|invent\.kde\.org/qt/")  # decide.py R1
PASS = {"A1", "A2", "C", "D", "E"}


def get(url, tries=5):
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, None
            ra = e.headers.get("Retry-After")
            time.sleep(int(ra) if ra and ra.isdigit() else 15 * (t + 1))
        except Exception:  # noqa: BLE001
            time.sleep(15 * (t + 1))
    return None, "FAIL"


def main():
    rows = {json.loads(l)["pool_key"]: json.loads(l) for l in open(W / "gitlab_rows.jsonl")}
    meas = {}
    for l in open(W / "gitlab.out.jsonl"):
        d = json.loads(l)
        meas[d["pool_key"]] = d
    by_name = {}
    for f in ["pool.csv", "v2/pool.supplement.csv"]:
        for r in csv.DictReader(open(SEL / "s2-pool" / f, encoding="utf-8")):
            nm = (r["name_with_owner"] or r["repo_url"]).rstrip("/").split("/")[-1].lower().removesuffix(".git")
            if r["head_oid"]:
                by_name.setdefault(nm, []).append((r["pool_key"], r["head_oid"]))
    out = W / "gitlab_checks.jsonl"
    done = {json.loads(l)["pool_key"] for l in out.open()} if out.exists() else set()
    todo = []
    for k, m in meas.items():
        x = rows.get(k)
        if not x or not m.get("rule"):
            continue
        lic = m.get("dp8l_class") in PASS
        if not lic:
            continue
        sc = x.get("screen_commits")
        if sc and int(sc) >= 5000:
            continue  # count on record, screened for shared history, R1-R5 decided
        if k not in done:
            todo.append(x)
    print(f"{len(todo)} rows to check", flush=True)
    import collections, threading
    by_host = collections.defaultdict(list)
    for x in todo:
        by_host[x["host"]].append(x)
    lock = threading.Lock()
    f = out.open("a")

    def host_job(xs):
        for x in xs:
            pause = 0.25 if x["host"] == "gitlab.com" else 0.5  # gitlab.com: 500 unauthenticated calls per minute
            api = f"https://{x['host']}/api/v4/projects/{x['id']}"
            st, d = get(f"{api}/repository/commits?" + urllib.parse.urlencode(dict(per_page=1, page=1000)))
            time.sleep(pause)
            res = dict(pool_key=x["pool_key"], url=x["url"], probe_status=st)
            res["ge1000"] = None if d == "FAIL" or st != 200 else bool(d)
            res["r1_copy_namespace"] = bool(COPY.search(x["url"].lower() + "/"))  # decide.py matches lower-case URLs
            hits = []
            if res["ge1000"]:
                nm = x["path"].rstrip("/").split("/")[-1].lower()
                for key, oid in by_name.get(nm, []):
                    s2, _ = get(f"{api}/repository/commits/{oid}")
                    time.sleep(pause)
                    if s2 == 200:
                        hits.append(key)
            res["shares_history_with"] = hits
            res["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with lock:
                f.write(json.dumps(res) + "\n")
                f.flush()

    th = [threading.Thread(target=host_job, args=(v,)) for v in by_host.values()]
    for t in th:
        t.start()
    for t in th:
        t.join()
    print("end", flush=True)


if __name__ == "__main__":
    main()
