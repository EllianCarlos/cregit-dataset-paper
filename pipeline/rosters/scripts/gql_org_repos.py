#!/usr/bin/env python3
"""List all public repositories of GitHub orgs via GraphQL (not REST).
usage: gql_org_repos.py OUTDIR org1 org2 ...   (writes OUTDIR/<org>.json)"""
import json, subprocess, sys, os, time
out = sys.argv[1]; orgs = sys.argv[2:]
os.makedirs(out, exist_ok=True)
F = "nodes{name nameWithOwner url isArchived isFork isMirror} pageInfo{hasNextPage endCursor}"
def q(query):
    for attempt in range(4):
        r = subprocess.run(["gh", "api", "graphql", "-f", "query=" + query], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
        except Exception:
            d = None
        if d and "data" in d:
            return d
        time.sleep(5 * (attempt + 1))
    raise SystemExit("graphql failed: " + r.stdout[:500] + r.stderr[:500])
calls = 0
todo = [o for o in orgs if not os.path.exists(os.path.join(out, o + ".json"))]
for i in range(0, len(todo), 15):
    batch = todo[i:i+15]
    parts = ['o%d: repositoryOwner(login: %s) { login __typename repositories(first: 100, privacy: PUBLIC, orderBy:{field:NAME,direction:ASC}) { totalCount %s } }' % (j, json.dumps(o), F) for j, o in enumerate(batch)]
    d = q("{ %s rateLimit{remaining} }" % " ".join(parts)); calls += 1
    for j, o in enumerate(batch):
        node = d["data"].get("o%d" % j)
        rec = {"org": o, "found": node is not None, "type": node and node["__typename"], "repos": []}
        if node:
            conn = node["repositories"]; rec["totalCount"] = conn["totalCount"]; rec["repos"] += conn["nodes"]
            while conn["pageInfo"]["hasNextPage"]:
                d2 = q('{ repositoryOwner(login: %s) { repositories(first: 100, privacy: PUBLIC, orderBy:{field:NAME,direction:ASC}, after: %s) { totalCount %s } } }' % (json.dumps(o), json.dumps(conn["pageInfo"]["endCursor"]), F)); calls += 1
                conn = d2["data"]["repositoryOwner"]["repositories"]; rec["repos"] += conn["nodes"]
        rec["fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        json.dump(rec, open(os.path.join(out, o + ".json"), "w"), indent=1)
    print("batch", i // 15, "remaining", d["data"]["rateLimit"]["remaining"], file=sys.stderr)
print("graphql calls", calls, file=sys.stderr)
