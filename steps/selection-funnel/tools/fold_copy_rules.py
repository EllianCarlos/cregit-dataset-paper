#!/usr/bin/env python3
"""The funnel with the GitLab copy rules folded into the earlier steps (coordinator decision 2026-11-08).

New placement:
  "Not a fork"   : the fork flag, then R3 fork (a fork of a pool project by shared root commit).
  "Not a mirror" : the mirror flag, then the copies of another pool project: shared history with a pool row of
                   the same name, R1 copy namespace, R2 same project.
Each rule applies to every GitLab row that reaches its step, with the data that is on record. No repository and no
API is fetched here.

Copy check of the new projects (2026-11-08, copycheck/): copycheck/check.py asked the host APIs for the root and head
commits of the 159 new projects and of their partners (same-name pool and selected rows, and the pool rows that the
GitHub commit search finds for the root commit); copycheck/classify.py applies the rules to that evidence
(copycheck/decisions.tsv). Here a new project of any host (GitLab, GitHub, other hosts) with a fork decision leaves at
"Not a fork" (after the fork flag and R3 on record), and one with a copy decision leaves at "Not a mirror" (with the
shared-history rule, before R1 and R2). R1 matches the lower-case URL, as in decide.py (fixed 2026-11-08: the
GNOME lorry mirrors gitlab.gnome.org/Infrastructure/Mirrors/... did not match before).

User decisions of 2026-11-08 (second version): (1) the copy-check rules apply to GitLab rows only; on GitHub and the
other hosts only the fork and mirror flags remove a row (copycheck/classify.py). (2) An upstream never leaves because
of its own copy, for every row: the shared-history rule on record removes a GitLab row only through a partner that is
selected, or that is not recorded as a copy and holds the head of the row (copycheck/rule2_check.py: rule2.tsv). The
rows that reach the final set again get the copy check of the new projects (copycheck/decisions2.tsv). A rule that needs data that exists only for some rows (root commits, readings by hand, the
shared-history check) is applied where the data exists; the rows without the data are counted as the data gap.

Inputs: row_status.tsv.gz (build_funnel.py: the old exit step of each pool row), work/gitlab_rows.jsonl,
work/gitlab_checks.jsonl, s2-pool/gitlab/decisions.tsv, s2-pool/gitlab/roots.tsv, the pool files (same-name rows).
copycheck/decisions.tsv, the TOM 1.0.0 MANIFEST.tsv (every TOM project must stay).
Writes funnel_counts_folded.json and prints it.
"""
import collections
import csv
import gzip
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
W = HERE / "work"
SEL = Path.home() / "STUDY-REPOSITORY/dataset-selection"
G = SEL / "s2-pool/gitlab"
COPY = re.compile(r"/(mirrors|infrastructure/mirrors|neon/backports-[^/]+|neon/forks|gfx-ci|mesa_ci|openhw-group/backup-\d+)/|invent\.kde\.org/qt/")  # decide.py R1
OLD = ["Pool of all sources (GitLab included)", "Commit on the default branch", "Not archived", "Not a fork", "Not a mirror",
       "Push on or after 2025-04-03 (GitLab: last activity)",
       "tokei rule: the largest programming language is C, C++, Java or Rust",
       "License file, or a near miss C, D or E (DP8L v4)", "1,000 or more commits",
       "GitLab copy rules: shared history with a pool row, R1, R2, R3 (GitLab only)",
       "Has a project file (TOM 1.0.0 rows; new rows are not run yet)"]
NEW = ["Pool of all sources", "Commit on the default branch", "Not archived",
       "Not a fork (GitLab: also a fork of a pool project by shared root commit)",
       "Not a mirror (GitLab: also a copy of another pool project)",
       "Push on or after 2025-04-03 (GitLab: last activity)",
       "tokei rule: the largest programming language is C, C++, Java or Rust",
       "License file, or a near miss C, D or E (DP8L v4)", "1,000 or more commits",
       "Has a project file (TOM 1.0.0 rows; new rows are not run yet)"]
FORK, MIRROR, COPYSTEP = 3, 4, 9
MANIFEST = Path.home() / "s3-work/dataset-tom-4/final/MANIFEST.tsv"


def norm(u):
    return (u or "").strip().lower().replace("http://", "https://").rstrip("/").removesuffix(".git")


def main():
    old_counts = json.load(open(HERE / "funnel_counts.json"))
    status, project = {}, {}
    with gzip.open(HERE / "row_status.tsv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            st = r["new_step"]
            status[(r["pool_key"], r["source"].startswith("gitlab"))] = (OLD.index(st) if st in OLD else (None if st == "" else st), r["new_reason"])
            project[(r["pool_key"], r["source"].startswith("gitlab"))] = r["project"]
    tom = {r["project"] for r in csv.DictReader(open(MANIFEST), delimiter="\t")}
    cc = {r["new"]: r for r in csv.DictReader(open(HERE / "copycheck/decisions.tsv"), delimiter="\t")}
    r2 = {r["row"]: r["still_removed"] == "True" for r in csv.DictReader(open(HERE / "copycheck/rule2.tsv"), delimiter="\t")}
    cc2 = {r["new"]: r for r in csv.DictReader(open(HERE / "copycheck/decisions2.tsv"), delimiter="\t")}
    gl = {json.loads(l)["pool_key"]: json.loads(l) for l in open(W / "gitlab_rows.jsonl")}
    chk = {json.loads(l)["pool_key"]: json.loads(l) for l in open(W / "gitlab_checks.jsonl")}
    decided = {norm(r["url"]) for r in csv.DictReader(open(G / "decisions.tsv"), delimiter="\t")}
    rooted = {norm(r["url"]) for r in csv.DictReader(open(G / "roots.tsv"), delimiter="\t") if r.get("root")}
    by_name = collections.defaultdict(list)
    for fn in ["pool.csv", "v2/pool.supplement.csv"]:
        for r in csv.DictReader(open(SEL / "s2-pool" / fn, encoding="utf-8")):
            nm = (r["name_with_owner"] or r["repo_url"]).rstrip("/").split("/")[-1].lower().removesuffix(".git")
            if r["head_oid"]:
                by_name[nm].append(r["pool_key"])

    # ---- old placement, recomputed from row_status (must equal funnel_counts.json)
    def counts(exit_of, nsteps, keys):
        out = []
        for i in range(nsteps):
            out.append(sum(1 for k in keys if exit_of[k] is None or exit_of[k] > i))
        return out
    pool_keys = [k for k, (e, _) in status.items() if not isinstance(e, str)]
    gl_keys = [k for k in pool_keys if k[1]]
    assert all(k[0] in gl for k in gl_keys)
    old_exit = {k: status[k][0] for k in pool_keys}
    old_all, old_gl = counts(old_exit, len(OLD), pool_keys), counts(old_exit, len(OLD), gl_keys)
    ref = [(s["after"], s["gitlab"]) for s in old_counts["steps"]]
    assert ref == list(zip(old_all, old_gl)), (ref, list(zip(old_all, old_gl)))

    # ---- the rule flags of each GitLab pool row, from the data on record
    flags = {}
    gaps = collections.Counter()
    gap_rows = collections.defaultdict(list)
    for k in gl_keys:
        g, c, e = gl[k[0]], chk.get(k[0], {}), old_exit[k]
        u = norm(g["url"])
        f = {}
        f["r3"] = g["decision"] == "R3 fork"
        f["r2"] = g["decision"] == "R2 same project"
        f["r1"] = g["decision"] == "R1 copy namespace" or bool(COPY.search(g["url"].lower() + "/"))
        f["share"] = g["screen"] == "shares history with a pool row" or bool(c.get("shares_history_with"))
        if k[0] in r2 and not r2[k[0]]:
            f["share"] = False  # decision 2: no partner that removes the row
        flags[k] = f
        nm = g["path"].rstrip("/").split("/")[-1].lower()
        same_name = bool(by_name.get(nm))
        share_checked = (g["screen"] == "shares history with a pool row"
                         or (g["screen_commits"] and int(g["screen_commits"]) >= 5000)
                         or c.get("ge1000") is True or k[0] in cc)
        reach_fork = e is None or e >= FORK
        reach_mirror = e is None or e >= MIRROR
        if reach_fork and not f["r3"] and u not in rooted and k[0] not in cc:
            gaps["fork: no root commit on record"] += 1
        if reach_mirror and not (f["share"] or f["r1"]):
            if not share_checked:
                gaps["mirror: no shared-history check on record"] += 1
                if same_name:
                    gaps["mirror: no shared-history check, and a pool row of the same name exists"] += 1
                    gap_rows[e if isinstance(e, int) else "final"].append(k[0])
            if u not in decided and k[0] not in cc:
                gaps["mirror: no reading by hand (R2)"] += 1

    # ---- new placement
    new_exit, why = {}, collections.Counter()
    for k in pool_keys:
        e = old_exit[k]
        d = cc.get(k[0]) if e is None else None
        if d and d["step"] != "stays" and d["rule"] != "R1 copy namespace":
            st = FORK if d["step"] == "Not a fork" else MIRROR
            f = flags.get(k, {})
            if st == MIRROR and f.get("r3"):
                st = FORK
            if st == FORK and not f.get("r3"):
                new_exit[k] = FORK
                why[("fork", "R3 fork of a pool project (copy check of the new projects)")] += 1
                continue
            if st == MIRROR and not f.get("share"):
                new_exit[k] = MIRROR
                why[("mirror", "share (copy check of the new projects)")] += 1
                continue
        d2 = cc2.get(k[0]) if k[1] and e == COPYSTEP and not flags[k]["share"] else None
        if d2:
            if d2["step"] == "stays":
                new_exit[k] = None
                why[("final", "back by decision 2 (copy check stays)")] += 1
            else:
                new_exit[k] = FORK if d2["step"] == "Not a fork" else MIRROR
                why[("fork" if d2["step"] == "Not a fork" else "mirror",
                     ("R3 fork of a pool project" if d2["step"] == "Not a fork" else "share") + " (copy check of the rows back by decision 2)")] += 1
            continue
        if k[1] and (e is None or e >= FORK):
            f = flags[k]
            if e != FORK and f["r3"]:
                new_exit[k] = FORK
                why[("fork", "R3 fork of a pool project")] += 1
                continue
            if e is None or e >= MIRROR:
                if e != MIRROR:
                    for name in ("share", "r1", "r2"):
                        if f[name]:
                            new_exit[k] = MIRROR
                            why[("mirror", name)] += 1
                            break
                    if k in new_exit:
                        continue
        assert e != COPYSTEP, ("a copy-rule row has no rule flag", k[0])
        new_exit[k] = e if e is None or e < COPYSTEP else e - 1
    new_all, new_gl = counts(new_exit, len(NEW), pool_keys), counts(new_exit, len(NEW), gl_keys)
    final_old = {k for k in pool_keys if old_exit[k] is None}
    final_new = {k for k in pool_keys if new_exit[k] is None}
    tom_final = {k for k in final_new if project[k] in tom}
    assert len(tom_final) == len(tom) == 8449, ("a TOM 1.0.0 project leaves", len(tom_final), len(tom))
    left = sorted(project[k] for k in final_old - final_new)
    cc_left = {d["new"] for d in cc.values() if d["step"] != "stays"}
    assert {k[0] for k in final_old - final_new} == cc_left, "the removed rows differ from copycheck/decisions.tsv"
    back = sorted(project[k] for k in final_new - final_old)
    assert {k[0] for k in final_new - final_old} == {d["new"] for d in cc2.values() if d["step"] == "stays"}
    moved_from = collections.Counter((old_exit[k], new_exit[k]) for k in gl_keys if old_exit[k] != new_exit[k])

    res = dict(
        old=[dict(step=OLD[i], after=old_all[i], removed=(old_all[i - 1] - old_all[i]) if i else None,
                  gitlab_after=old_gl[i], gitlab_removed=(old_gl[i - 1] - old_gl[i]) if i else None)
             for i in range(len(OLD))],
        new=[dict(step=NEW[i], after=new_all[i], removed=(new_all[i - 1] - new_all[i]) if i else None,
                  gitlab_after=new_gl[i], gitlab_removed=(new_gl[i - 1] - new_gl[i]) if i else None)
             for i in range(len(NEW))],
        folded_rule_removals={f"{a}: {b}": n for (a, b), n in sorted(why.items())},
        gitlab_flag_rows={n: sum(1 for f in flags.values() if f[n]) for n in ("r3", "r2", "r1", "share")},
        moved_rows={f"{OLD[a] if isinstance(a, int) else a} -> {NEW[b] if isinstance(b, int) else b}": n
                    for (a, b), n in sorted(moved_from.items(), key=lambda t: str(t))},
        data_gap=dict(gaps),
        data_gap_same_name_by_old_exit={(OLD[e] if isinstance(e, int) else e): len(v) for e, v in gap_rows.items()},
        tokei_out_new={f"{r} ({'GitLab' if gl_ else 'pool'})": n for (r, gl_), n in sorted(
            collections.Counter(("largest language is another one" if status[k][1].startswith("largest language")
                                else status[k][1], k[1]) for k in pool_keys if new_exit[k] == 6).items(), key=lambda t: -t[1])},
        license_out_new={f"{r} ({'GitLab' if gl_ else 'pool'})": n for (r, gl_), n in sorted(
            collections.Counter(("no license file", k[1]) for k in pool_keys if new_exit[k] == 7).items())},
        final_old=len(final_old), final_new=len(final_new), final_same_set=final_old == final_new,
        final_tom=len(tom_final), final_new_projects=len(final_new) - len(tom_final), removed_new_projects=left, back_by_decision_2=back,
        final_gitlab_tom=sum(1 for k in tom_final if k[1]), final_gitlab_new=sum(1 for k in final_new - tom_final if k[1]),
    )
    json.dump(res, open(HERE / "funnel_counts_folded.json", "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
