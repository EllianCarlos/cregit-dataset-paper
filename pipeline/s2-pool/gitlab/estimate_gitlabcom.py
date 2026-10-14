#!/usr/bin/env python3
"""Estimate the size of the gitlab.com search without a full sweep (2026-10-13).

The search: GET https://gitlab.com/api/v4/projects with visibility=public, archived=false,
last_activity_after=2025-04-03T00:00:00Z (the DP5 cut of s4-filter/funnel.py),
with_programming_language=<L> for L in C, C++, Java, Rust, keyset pagination by id (100 per page).
gitlab.com gives no x-total for large results. So this script samples the id range: at K points
it asks for the first 100 matches with id > x, and the id span of that page gives the local
density. The integral of the density over the id range is the estimate. It also counts, inside the
samples, the share in group namespaces and the share of forks. Unauthenticated; ~2 s between
requests. Output: gitlabcom.estimate.tsv (one row per sample) and a summary on stdout.
"""
import json, sys, time, urllib.parse, urllib.request
B = "https://gitlab.com/api/v4/projects"
BASE = dict(visibility="public", archived="false", last_activity_after="2025-04-03T00:00:00Z",
            per_page="100", order_by="id", sort="asc", pagination="keyset")
def get(params):
    for t in range(4):
        try:
            with urllib.request.urlopen(B + "?" + urllib.parse.urlencode(params), timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            ra = e.headers.get("Retry-After")
            time.sleep(int(ra) if ra and ra.isdigit() else 10 * (t + 1))
        except Exception:
            time.sleep(10 * (t + 1))
    return None
top = get(dict(order_by="id", sort="desc", per_page="1"))[0]["id"]
K = int(sys.argv[1]) if len(sys.argv) > 1 else 16
out = open("gitlabcom.estimate.tsv", "w"); out.write("lang\tid_after\tn\tlast_id\tgroups\tforks\n")
for lang in ["C", "C++", "Java", "Rust"]:
    est = 0.0; n_all = g_all = f_all = 0; fails = 0
    pts = [int(top * i / K) for i in range(K)]
    for i, x in enumerate(pts):
        d = get(dict(BASE, with_programming_language=lang, id_after=str(x)))
        time.sleep(2)
        if d is None:
            fails += 1; continue
        seg = (pts[i + 1] if i + 1 < K else top) - x
        if not d:
            out.write(f"{lang}\t{x}\t0\t\t0\t0\n"); continue
        last = d[-1]["id"]; span = max(last - x, 1)
        g = sum(p["namespace"]["kind"] == "group" for p in d); f = sum(bool(p.get("forked_from_project")) for p in d)
        n_all += len(d); g_all += g; f_all += f
        dens = len(d) / span if len(d) == 100 else len(d) / seg  # a short page: all matches in the rest
        est += dens * seg if len(d) == 100 else len(d)
        out.write(f"{lang}\t{x}\t{len(d)}\t{last}\t{g}\t{f}\n"); out.flush()
    print(f"{lang}: about {est:,.0f} projects (sampled {n_all}, group share {g_all / max(n_all,1):.0%}, fork share {f_all / max(n_all,1):.0%}, failed samples {fails})", flush=True)
print("top id", top)
