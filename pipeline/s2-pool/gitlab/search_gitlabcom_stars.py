#!/usr/bin/env python3
"""gitlab.com search with the GitHub search bound (user decision 2026-10-14 ~01:00 UTC): stars > 400.

GET https://gitlab.com/api/v4/projects?visibility=public&archived=false&order_by=star_count&sort=desc
&per_page=100&simple=false&page=N (offset pagination), unauthenticated, until a page reaches
star_count <= 400. Then, in order (the first step that removes a row): stars <= 400; last activity
before 2025-04-03 (the DP5 cut); personal namespace; fork; empty repository; no default branch; the
languages API lists none of C, C++, Java, Rust. Output: rows/gitlab.com-search.jsonl (the same
format as list_gitlab.py), with "search": "stars>400".
"""
import json, time, urllib.parse, urllib.request
B = "https://gitlab.com/api/v4"
CUT = "2025-04-03T00:00:00Z"; TARGET = {"C", "C++", "Java", "Rust"}
def get(url):
    for t in range(6):
        try:
            with urllib.request.urlopen(url, timeout=120) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403): raise SystemExit(f"BLOCKED: HTTP {e.code} at {url}: a token is needed")
            ra = e.headers.get("Retry-After"); time.sleep(int(ra) if ra and ra.isdigit() else 15 * (t + 1))
        except Exception: time.sleep(15 * (t + 1))
    raise SystemExit(f"FAIL: {url}")
out = open("rows/gitlab.com-search.jsonl", "w"); n = kept = 0; page = 1; stop = False
while not stop:
    d = get(f"{B}/projects?" + urllib.parse.urlencode(dict(visibility="public", archived="false", order_by="star_count",
                                                            sort="desc", per_page=100, simple="false", page=page)))
    time.sleep(1)
    if not d: break
    for p in d:
        if p.get("star_count", 0) <= 400: stop = True; break
        n += 1; ns = (p.get("namespace") or {}).get("kind")
        r = dict(host="gitlab.com", id=p["id"], path=p["path_with_namespace"], url=p.get("http_url_to_repo"), ns_kind=ns,
                 fork=bool(p.get("forked_from_project")), empty=p.get("empty_repo"), default_branch=p.get("default_branch"),
                 last_activity_at=p.get("last_activity_at"), created_at=p.get("created_at"), stars=p.get("star_count"),
                 mirror=p.get("mirror"), search="stars>400", listed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        why = ("last activity before 2025-04-03" if (r["last_activity_at"] or "") < CUT else "personal namespace" if ns == "user"
               else "fork" if r["fork"] else "empty repository" if r["empty"] else "no default branch" if not r["default_branch"] else None)
        if why is None:
            langs = get(f"{B}/projects/{p['id']}/languages"); time.sleep(0.5)
            r["languages"] = langs or {}
            if not (set(r["languages"]) & TARGET): why = "no C, C++, Java or Rust in the languages API"
        r["removed_by"] = why or ""; kept += why is None
        out.write(json.dumps(r) + "\n")
    page += 1
print(f"gitlab.com search stars>400: listed {n} (pages {page - 1}), kept {kept}")
