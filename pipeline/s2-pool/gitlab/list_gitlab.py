#!/usr/bin/env python3
"""List GitLab projects for the pool extension measurement (2026-10-13, read-only, counts only).

  list_gitlab.py instance HOST        all public projects of a self-hosted GitLab instance
  list_gitlab.py group gitlab.com G   all public projects of one gitlab.com group (with subgroups)

API (GitLab v4, documented): GET /api/v4/projects (keyset pagination by id, 100 per page) or
GET /api/v4/groups/:id/projects?include_subgroups=true; then, for the rows that pass the cheap steps,
GET /api/v4/projects/:id/languages. Unauthenticated. One request at a time per host, 0.5 s apart;
429 and 5xx: wait (Retry-After) and retry.

Server-side filters: visibility=public, archived=false, last_activity_after=2025-04-03T00:00:00Z
(the DP5 cut of s4-filter/funnel.py; GitLab's last_activity_at also moves on issue/MR activity, so
this bound is wider than a push date). Client-side steps, in order, each row gets the first that
removes it: personal namespace (namespace.kind=user); fork (forked_from_project); empty repository
(empty_repo); no default branch; languages API lists none of C, C++, Java, Rust.
Output: rows/<host>[__<group>].jsonl (one JSON object per listed project with a "removed_by" key).
"""
import json, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
CUT = "2025-04-03T00:00:00Z"
TARGET = {"C", "C++", "Java", "Rust"}
def get(url, tries=6):
    for t in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                link = r.headers.get("Link", "")
                return json.load(r), link
        except urllib.error.HTTPError as e:
            if e.code == 404: return None, ""
            ra = e.headers.get("Retry-After")
            time.sleep(int(ra) if ra and ra.isdigit() else 15 * (t + 1))
        except Exception:
            time.sleep(15 * (t + 1))
    raise SystemExit(f"FAIL after {tries} tries: {url}")
def next_link(link):
    for part in link.split(","):
        if 'rel="next"' in part: return part[part.index("<") + 1:part.index(">")]
    return None
mode, host = sys.argv[1], sys.argv[2]
api = f"https://{host}/api/v4"
q = dict(visibility="public", archived="false", last_activity_after=CUT, per_page="100", simple="false")
if mode == "instance":
    url = f"{api}/projects?" + urllib.parse.urlencode(dict(q, order_by="id", sort="asc", pagination="keyset"))
    name = host
else:
    grp = sys.argv[3]
    url = f"{api}/groups/{urllib.parse.quote(grp, safe='')}/projects?" + urllib.parse.urlencode(dict(q, include_subgroups="true"))
    name = f"{host}__{grp.replace('/', '__')}"
Path("rows").mkdir(exist_ok=True)
out = open(f"rows/{name}.jsonl", "w"); n = kept = 0
while url:
    d, link = get(url); time.sleep(0.5)
    if d is None: print(f"{name}: not found (404)"); break
    for p in d:
        n += 1
        ns = (p.get("namespace") or {}).get("kind")
        r = dict(host=host, id=p["id"], path=p["path_with_namespace"], url=p.get("http_url_to_repo"), ns_kind=ns,
                 fork=bool(p.get("forked_from_project")), empty=p.get("empty_repo"), default_branch=p.get("default_branch"),
                 last_activity_at=p.get("last_activity_at"), created_at=p.get("created_at"), stars=p.get("star_count"),
                 mirror=p.get("mirror"), listed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        why = ("personal namespace" if ns == "user" else "fork" if r["fork"] else "empty repository" if r["empty"]
               else "no default branch" if not r["default_branch"] else None)
        if why is None:
            langs, _ = get(f"{api}/projects/{p['id']}/languages"); time.sleep(0.5)
            r["languages"] = langs or {}
            if not (set(r["languages"]) & TARGET): why = "no C, C++, Java or Rust in the languages API"
        r["removed_by"] = why or ""
        kept += why is None
        out.write(json.dumps(r) + "\n")
    out.flush()
    url = next_link(link)
print(f"{name}: listed {n}, kept {kept}", flush=True)
