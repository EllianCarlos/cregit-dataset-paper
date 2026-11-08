#!/usr/bin/env python3
"""Shared-history check of the 159 new projects against the pool and the selected rows (host APIs only).

No history is cloned or fetched. For each new project P:
  1. the root commit of P: the last commit of the default-branch listing (GitHub REST: the Link "last" page with
     per_page=1; GitLab API v4: the last non-empty page with per_page=100, found by doubling and bisection; Gitea:
     X-Total-Count). The head of P is its pinned commit (new_projects.tsv).
  2. the GitHub commit search q=hash:<root of P> (up to 3 pages of 100, the roots_check.py method): every pool row
     that holds the root commit of P is a partner ("root search"), with any name.
  3. the partners with the same repository name (copycheck/partners.py: pool rows and selected rows).
For each pair (P, Q): the root and head of Q, then four questions to the hosts: does Q hold the root of P, does P hold
the root of Q, does P hold the head of Q (the gitlab_checks.py question), does Q hold the head of P.
Output: copycheck/evidence.tsv (one line per pair) and copycheck/roots.tsv (one line per new project).
Requests go one at a time: GitHub 0.2 s apart (search 2.2 s), GitLab and Gitea 0.6 s apart. Every answer is
cached in copycheck/cache.jsonl, so a rerun asks nothing twice.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

D = Path(__file__).resolve().parent
CACHE = D / "cache.jsonl"
cache = {}
if CACHE.exists():
    for l in CACHE.open():
        d = json.loads(l)
        cache[d["k"]] = d["v"]
cf = CACHE.open("a")


def cached(key, fn):
    if key in cache:
        return cache[key]
    v = fn()
    cache[key] = v
    cf.write(json.dumps(dict(k=key, v=v, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))) + "\n")
    cf.flush()
    return v


# ---------------- GitHub (gh CLI)
def gh(path, headers=False, pause=0.2):
    for t in range(4):
        p = subprocess.run(["gh", "api", "-X", "GET"] + (["-i"] if headers else []) + [path], capture_output=True, text=True)
        time.sleep(pause)
        err = p.stderr + p.stdout[:300]
        if p.returncode == 0:
            return 200, p.stdout
        for code in (404, 409, 422, 451):
            if f"HTTP {code}" in err:
                return code, None
        if "rate limit" in err.lower() or "HTTP 403" in err or "HTTP 5" in err:
            time.sleep(60 * (t + 1))
            continue
        time.sleep(10 * (t + 1))
    return None, None


def gh_root(repo):
    def f():
        st, out = gh(f"repos/{repo}/commits?per_page=1", headers=True)
        if st != 200:
            return dict(status=st)
        head_part, _, body = out.partition("\r\n\r\n")
        if not body:
            head_part, _, body = out.partition("\n\n")
        last = 1
        for line in head_part.splitlines():
            if line.lower().startswith("link:"):
                for part in line.split(":", 1)[1].split(","):
                    if 'rel="last"' in part:
                        u = part.split(";")[0].strip(" <>")
                        last = int(urllib.parse.parse_qs(urllib.parse.urlparse(u).query)["page"][0])
        top = json.loads(body)
        st, out = gh(f"repos/{repo}/commits?per_page=1&page={last}")
        if st != 200 or not json.loads(out):
            return dict(status=st, pages=last)
        c = json.loads(out)[0]
        return dict(status=200, root=c["sha"], parentless=not c["parents"], commits_listed=last, head=top[0]["sha"] if top else "")
    return cached(f"gh_root {repo}", f)


def gh_has(repo, sha):
    def f():
        st, out = gh(f"repos/{repo}/commits/{sha}")
        return {200: True, 422: False, 404: "repo or commit not found", 409: "empty"}.get(st, f"error {st}")
    return cached(f"gh_has {repo} {sha}", f)


def gh_search(sha):
    def f():
        tot, names = 0, []
        for pg in (1, 2, 3):
            st, out = gh(f"search/commits?q=hash:{sha}&per_page=100&page={pg}", pause=2.2)
            if st != 200:
                return dict(status=st, total=tot, repos=names)
            j = json.loads(out)
            tot = j["total_count"]
            names += [i["repository"]["full_name"] for i in j["items"]]
            if pg * 100 >= tot:
                break
        return dict(status=200, total=tot, repos=sorted(set(names)))
    return cached(f"gh_search {sha}", f)


# ---------------- GitLab API v4 and Gitea (unauthenticated)
def http(url, pause=0.6):
    for t in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tom-funnel-copycheck (read-only, one request at a time)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                body = json.load(r)
                time.sleep(pause)
                return r.status, body, dict(r.headers)
        except urllib.error.HTTPError as e:
            time.sleep(pause)
            if e.code in (404, 422):
                return e.code, None, {}
            ra = e.headers.get("Retry-After")
            time.sleep(int(ra) if ra and ra.isdigit() else 20 * (t + 1))
        except Exception:  # noqa: BLE001
            time.sleep(20 * (t + 1))
    return None, None, {}


def gl_api(host, pid):
    return f"https://{host}/api/v4/projects/{urllib.parse.quote(str(pid), safe='')}"


def gl_root(host, pid):
    def f():
        api = gl_api(host, pid)
        def page(n):
            st, body, _ = http(f"{api}/repository/commits?per_page=100&page={n}")
            return st, body
        st, first = page(1)
        if st != 200:
            return dict(status=st)
        if not first:
            return dict(status=200, empty=True)
        head = first[0]["id"]
        lo, hi = 1, 2  # lo: a page known non-empty; hi: a page to test
        while True:
            st, b = page(hi)
            if st != 200:
                return dict(status=st)
            if not b:
                break
            lo, hi = hi, hi * 2
        while hi - lo > 1:  # lo non-empty, hi empty
            mid = (lo + hi) // 2
            st, b = page(mid)
            if st != 200:
                return dict(status=st)
            if b:
                lo = mid
            else:
                hi = mid
        st, b = page(lo)
        c = b[-1]
        return dict(status=200, root=c["id"], parentless=not c["parent_ids"], commits_listed=(lo - 1) * 100 + len(b), head=head)
    return cached(f"gl_root {host} {pid}", f)


def gl_has(host, pid, sha):
    def f():
        st, _, _ = http(f"{gl_api(host, pid)}/repository/commits/{sha}")
        return {200: True, 404: False}.get(st, f"error {st}")
    return cached(f"gl_has {host} {pid} {sha}", f)


def gitea_root(host, repo):
    def f():
        api = f"https://{host}/api/v1/repos/{repo}/commits"
        st, b, h = http(f"{api}?limit=1&page=1&stat=false&verification=false&files=false")
        if st != 200 or not b:
            return dict(status=st)
        n = int(h.get("X-Total-Count") or h.get("x-total-count"))
        st, c, _ = http(f"{api}?limit=1&page={n}&stat=false&verification=false&files=false")
        c = c[0]
        return dict(status=200, root=c["sha"], parentless=not c["parents"], commits_listed=n, head=b[0]["sha"])
    return cached(f"gitea_root {host} {repo}", f)


def gitea_has(host, repo, sha):
    def f():
        st, _, _ = http(f"https://{host}/api/v1/repos/{repo}/git/commits/{sha}?stat=false&verification=false&files=false")
        return {200: True, 404: False, 422: False}.get(st, f"error {st}")
    return cached(f"gitea_has {host} {repo} {sha}", f)


GITEA = {"codeberg.org"}


def kind(r):
    if r["host"] == "github.com":
        return "github"
    if r["host"] in GITEA:
        return "gitea"
    if r.get("gl_id") is not None or r["key"].startswith("gitlab:"):
        return "gitlab"
    return "gitlab-path"  # an other-host pool row on a GitLab instance (url: key): ask by its path


def repo_path(r):
    return r["path"] if r["host"] != "github.com" else r["path"]


def root_of(r):
    k = kind(r)
    if k == "github":
        return gh_root(r["path"])
    if k == "gitea":
        return gitea_root(r["host"], r["path"])
    return gl_root(r["host"], r.get("gl_id") or r["path"])


def has(r, sha):
    if not sha:
        return ""
    k = kind(r)
    if k == "github":
        return gh_has(r["path"], sha)
    if k == "gitea":
        return gitea_has(r["host"], r["path"], sha)
    return gl_has(r["host"], r.get("gl_id") or r["path"], sha)


def main():
    rows = json.load(open(D / "rows.json"))
    new = [json.loads(l) for l in open(D / "new.jsonl")]
    gh_pool = {}
    for k, r in rows.items():
        if r["host"] == "github.com":
            gh_pool.setdefault(r["path"].lower(), []).append(k)
    pairs = {}
    for l in open(D / "partners.jsonl"):
        d = json.loads(l)
        pairs[(d["new"], d["partner"])] = {"same name"}
    rootrows = []
    for i, p in enumerate(new):
        rt = root_of(p)
        p["_root"] = rt
        rootrows.append(p)
        print(f"[{i + 1}/{len(new)}] root {p['host']}/{p['path']}: {rt.get('root', rt)}", flush=True)
        if rt.get("root"):
            s = gh_search(rt["root"])
            p["_search"] = s
            for name in s.get("repos", []):
                for k in gh_pool.get(name.lower(), []):
                    if k != p["key"]:
                        pairs.setdefault((p["key"], k), set()).add("root search")
    with open(D / "roots.tsv", "w") as f:
        f.write("new\thost\tpath\tpinned\troot\troot_parentless\tcommits_listed\tapi_head\tsearch_total\tsearch_pool_hits\n")
        for p in rootrows:
            rt, s = p["_root"], p.get("_search", {})
            hits = sorted({rows[k]["path"] for (a, k) in pairs if a == p["key"] and "root search" in pairs[(a, k)]})
            f.write(f"{p['key']}\t{p['host']}\t{p['path']}\t{p.get('pinned', '')}\t{rt.get('root', '')}\t{rt.get('parentless', '')}\t"
                    f"{rt.get('commits_listed', '')}\t{rt.get('head', '')}\t{s.get('total', '')}\t{','.join(hits)}\n")
    by_key = {p["key"]: p for p in new}
    cols = ["new", "partner", "found_by", "partner_host", "partner_path", "same_name", "partner_selected", "partner_tom",
            "partner_exit", "partner_fork_flag", "partner_mirror_flag", "root_new", "root_partner", "root_equal",
            "partner_has_root_new", "new_has_root_partner", "head_new", "head_partner", "new_has_head_partner",
            "partner_has_head_new", "matched_sha"]
    out = open(D / "evidence.tsv", "w")
    out.write("\t".join(cols) + "\n")
    for n, ((a, b), why) in enumerate(sorted(pairs.items())):
        p, q = by_key[a], rows[b]
        rp = p["_root"].get("root", "")
        rq_d = root_of(q)
        rq = rq_d.get("root", "")
        hp = p.get("pinned") or p["_root"].get("head", "")
        hq = q.get("head") or rq_d.get("head", "")
        e = dict(new=a, partner=b, found_by="+".join(sorted(why)), partner_host=q["host"], partner_path=q["path"],
                 same_name=p["path"].rstrip("/").split("/")[-1].lower().removesuffix(".git") ==
                 q["path"].rstrip("/").split("/")[-1].lower().removesuffix(".git"),
                 partner_selected=q["selected"], partner_tom=q["tom"], partner_exit=q["exit"] or "selected",
                 partner_fork_flag=q["fork"], partner_mirror_flag=q["mirror"], root_new=rp, root_partner=rq,
                 root_equal=bool(rp and rq and rp == rq))
        if not rq_d.get("root") and rq_d.get("status") != 200:
            e["root_partner"] = f"lookup failed ({rq_d.get('status')})"
        e["partner_has_root_new"] = True if e["root_equal"] else has(q, rp)
        e["new_has_root_partner"] = True if e["root_equal"] else has(p, rq)
        e["head_new"], e["head_partner"] = hp, hq
        e["new_has_head_partner"] = has(p, hq)
        e["partner_has_head_new"] = has(q, hp)
        m = []
        if e["root_equal"]:
            m.append(f"root {rp}")
        else:
            if e["partner_has_root_new"] is True:
                m.append(f"root of new {rp}")
            if e["new_has_root_partner"] is True:
                m.append(f"root of partner {rq}")
        if e["new_has_head_partner"] is True:
            m.append(f"head of partner {hq}")
        if e["partner_has_head_new"] is True:
            m.append(f"head of new {hp}")
        e["matched_sha"] = "; ".join(m)
        out.write("\t".join(str(e[c]) for c in cols) + "\n")
        out.flush()
        print(f"pair {n + 1}/{len(pairs)} {p['path']} ~ {q['host']}/{q['path']}: {e['matched_sha'] or '-'}", flush=True)
    print("end", flush=True)


if __name__ == "__main__":
    sys.exit(main())
