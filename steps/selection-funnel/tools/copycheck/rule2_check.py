#!/usr/bin/env python3
"""Decision 2 of 2026-11-08 ("an upstream never leaves because of its own copy") applied to the GitLab rows that the
shared-history rule on record removes (the GitLab screen and gitlab_checks.py: the head of a same-name pool row is in
the GitLab row, so the pool row is behind the GitLab row).

For each such row whose partners are not selected (rule2_rows.json, from the classification in this folder):
  1. a partner that is recorded as a copy (fork flag, mirror flag, R1, or it left at a fork or copy step) does not
     count; another partner counts only if it holds the head of the row (the snapshot pin of
     work/gitlab_snapshot_pin.jsonl): then the row is behind the partner, so the row is the copy.
  2. a row that no partner removes and that reached the old copy-rules step (it passed the tokei, license and commit
     steps) gets the copy check of the new projects (check.py: root, GitHub root search, same-name partners, the four
     questions per pair). classify.py rules then decide it.
Writes rule2.tsv (step 1), rule2_new.jsonl, rule2_partners.jsonl, evidence2.tsv, roots2.tsv (step 2).
"""
import csv
import json
import re
import collections
from pathlib import Path

import check

D = Path(__file__).resolve().parent
H = D.parent
COPY = re.compile(r"/(mirrors|infrastructure/mirrors|neon/backports-[^/]+|neon/forks|gfx-ci|mesa_ci|openhw-group/backup-\d+)/|invent\.kde\.org/qt/")


def recorded_copy(q):
    return (q["fork"] or q["mirror"] or bool(COPY.search(q["url"].lower() + "/"))
            or q["exit"] in ("Not a fork", "Not a mirror") or q["exit"].startswith("GitLab copy rules"))


def nm(path):
    return path.rstrip("/").split("/")[-1].lower().removesuffix(".git")


def main():
    rows = json.load(open(D / "rows.json"))
    gl = {json.loads(l)["pool_key"]: json.loads(l) for l in open(H / "work/gitlab_rows.jsonl")}
    chk = {json.loads(l)["pool_key"]: json.loads(l) for l in open(H / "work/gitlab_checks.jsonl")}
    snap = {}
    for l in open(H / "work/gitlab_snapshot_pin.jsonl"):
        d = json.loads(l)
        if d.get("snapshot_commit"):
            snap[d["pool_key"]] = d["snapshot_commit"]
    need = json.load(open(D / "rule2_rows.json"))
    out = []
    for k in need:
        g, r = gl[k], rows[k]
        ps = ([g["dup_of"]] if g["screen"] == "shares history with a pool row" else []) + chk.get(k, {}).get("shares_history_with", [])
        head = snap[k]
        res = []
        for p in ps:
            q = rows[p]
            if q["exit"] == "":
                res.append((p, "selected", True))
            elif recorded_copy(q):
                res.append((p, "recorded copy", False))
            else:
                h = check.has(q, head)
                res.append((p, f"left at {q['exit']}; holds the row head: {h}", h is True))
        removes = any(x[2] for x in res)
        out.append(dict(row=k, url=r["url"], old_exit=r["exit"], head=head, still_removed=removes,
                        partners="; ".join(f"{rows[p]['host']}/{rows[p]['path']} ({w})" for p, w, _ in res)))
        print(r["url"], removes, out[-1]["partners"][:160], flush=True)
    with open(D / "rule2.tsv", "w") as f:
        cols = list(out[0])
        f.write("\t".join(cols) + "\n")
        for o in out:
            f.write("\t".join(str(o[c]) for c in cols) + "\n")
    back = [o["row"] for o in out if not o["still_removed"] and o["old_exit"].startswith("GitLab copy rules")]
    print(len(back), "rows reach the final set again before their copy check", flush=True)
    # step 2: the copy check of these rows, as for the new projects
    by_name = collections.defaultdict(list)
    for kk, rr in rows.items():
        by_name[nm(rr["path"])].append(kk)
    gh_pool = {}
    for kk, rr in rows.items():
        if rr["host"] == "github.com":
            gh_pool.setdefault(rr["path"].lower(), []).append(kk)
    newrows, pairs = [], {}
    for k in back:
        p = dict(rows[k])
        p["pinned"] = snap[k]
        rt = check.root_of(p)
        p["_root"] = rt
        newrows.append(p)
        for kk in by_name[nm(p["path"])]:
            if kk != k:
                pairs.setdefault((k, kk), set()).add("same name")
        if rt.get("root"):
            s = check.gh_search(rt["root"])
            p["_search"] = s
            for name in s.get("repos", []):
                for kk in gh_pool.get(name.lower(), []):
                    if kk != k:
                        pairs.setdefault((k, kk), set()).add("root search")
        print("root", p["url"], rt.get("root", rt), flush=True)
    with open(D / "rule2_new.jsonl", "w") as f:
        for p in newrows:
            f.write(json.dumps({a: b for a, b in p.items() if not a.startswith("_")}) + "\n")
    with open(D / "roots2.tsv", "w") as f:
        f.write("row\thost\tpath\tpinned\troot\troot_parentless\tcommits_listed\tsearch_total\n")
        for p in newrows:
            rt, s = p["_root"], p.get("_search", {})
            f.write(f"{p['key']}\t{p['host']}\t{p['path']}\t{p['pinned']}\t{rt.get('root', '')}\t{rt.get('parentless', '')}\t"
                    f"{rt.get('commits_listed', '')}\t{s.get('total', '')}\n")
    by_key = {p["key"]: p for p in newrows}
    cols = ["new", "partner", "found_by", "partner_host", "partner_path", "same_name", "partner_selected", "partner_tom",
            "partner_exit", "partner_fork_flag", "partner_mirror_flag", "root_new", "root_partner", "root_equal",
            "partner_has_root_new", "new_has_root_partner", "head_new", "head_partner", "new_has_head_partner",
            "partner_has_head_new", "matched_sha"]
    ev = open(D / "evidence2.tsv", "w")
    ev.write("\t".join(cols) + "\n")
    for (a, b), why in sorted(pairs.items()):
        p, q = by_key[a], rows[b]
        rp = p["_root"].get("root", "")
        rq_d = check.root_of(q)
        rq = rq_d.get("root", "")
        hp, hq = p["pinned"], q.get("head") or rq_d.get("head", "")
        e = dict(new=a, partner=b, found_by="+".join(sorted(why)), partner_host=q["host"], partner_path=q["path"],
                 same_name=nm(p["path"]) == nm(q["path"]), partner_selected=q["selected"], partner_tom=q["tom"],
                 partner_exit=q["exit"] or "selected", partner_fork_flag=q["fork"], partner_mirror_flag=q["mirror"],
                 root_new=rp, root_partner=rq if rq else f"lookup failed ({rq_d.get('status')})",
                 root_equal=bool(rp and rq and rp == rq))
        e["partner_has_root_new"] = True if e["root_equal"] else check.has(q, rp)
        e["new_has_root_partner"] = True if e["root_equal"] else check.has(p, rq)
        e["head_new"], e["head_partner"] = hp, hq
        e["new_has_head_partner"] = check.has(p, hq)
        e["partner_has_head_new"] = check.has(q, hp)
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
        ev.write("\t".join(str(e[c]) for c in cols) + "\n")
        ev.flush()
        print(f"pair {p['path']} ~ {q['host']}/{q['path']}: {e['matched_sha'] or '-'}", flush=True)
    print("end", flush=True)


if __name__ == "__main__":
    main()
