#!/usr/bin/env python3
"""gitlab.com search size without the language filter (2026-10-13). with_programming_language gives
HTTP 500 after ~15 s (a server statement timeout) for any id_after past the start of the id range, so
the language bound cannot be used server-side. This script samples K points of the id range with
visibility=public, archived=false, last_activity_after=2025-04-03T00:00:00Z, keyset by id, 100 per page,
and integrates the density. It also counts group namespaces and forks inside the samples.
Output: gitlabcom.estimate_nolang.tsv and a summary line."""
import json, sys, time, urllib.parse, urllib.request
B = "https://gitlab.com/api/v4/projects"
def get(p):
    for t in range(3):
        try:
            with urllib.request.urlopen(B + "?" + urllib.parse.urlencode(p), timeout=60) as r: return json.load(r)
        except Exception: time.sleep(10 * (t + 1))
top = get(dict(order_by="id", sort="desc", per_page="1"))[0]["id"]
K = int(sys.argv[1]); pts = [int(top * i / K) for i in range(K)]
out = open("gitlabcom.estimate_nolang.tsv", "w"); out.write("id_after\tn\tlast_id\tgroups\tgroup_nonfork\n")
est = n_all = g_all = gnf_all = 0
for i, x in enumerate(pts):
    d = get(dict(visibility="public", archived="false", last_activity_after="2025-04-03T00:00:00Z", per_page="100",
                 order_by="id", sort="asc", pagination="keyset", id_after=str(x), simple="false")); time.sleep(2)
    if not d: continue
    seg = (pts[i + 1] if i + 1 < K else top) - x; span = max(d[-1]["id"] - x, 1)
    g = sum(p["namespace"]["kind"] == "group" for p in d); gnf = sum(p["namespace"]["kind"] == "group" and not p.get("forked_from_project") for p in d)
    est += len(d) / span * seg if len(d) == 100 else len(d)
    n_all += len(d); g_all += g; gnf_all += gnf
    out.write(f"{x}\t{len(d)}\t{d[-1]['id']}\t{g}\t{gnf}\n"); out.flush()
print(f"top id {top}; about {est:,.0f} public, not archived, active since 2025-04-03; in samples: group {g_all/n_all:.0%}, group and not a fork {gnf_all/n_all:.0%}")
