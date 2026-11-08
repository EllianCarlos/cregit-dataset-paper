#!/usr/bin/env python3
"""Apply the folded copy rules to the shared-history evidence of the new projects (copycheck/evidence.tsv).

A partner Q can be the original of a new project P only when nothing records Q as a copy: no fork flag, no mirror
flag, its URL is not in a copy namespace (R1, lower-case URL as in decide.py), and Q did not leave at a fork or
copy step (the fork step, the mirror step, or the old GitLab copy-rules step; for example invent.kde.org/office/
ghostwriter left there because it shares history with the pool row KDE/ghostwriter, so that pool row stays).
When Q is also a new project, P is the copy only if Q holds the head of P (P is behind Q or equal).
User decisions of 2026-11-08 (second version of this file; the first version is decisions.v1.tsv):
  1. Host: these rules apply to GitLab rows only. On GitHub and the other hosts only the fork flag (and the mirror
     flag) removes a row, as for the TOM 1.0.0 projects.
  2. An upstream never leaves because of its own copy: a partner that left the funnel at any other step counts only
     if it holds the head of P (then P is behind it, so P is the copy). Example: nnsuite/orc left at the push step
     and does not hold the head of gstreamer/orc, so gstreamer/orc stays.
For each pair (P, Q) with such a Q:
  shared history: Q holds the root of P, or P holds the root of Q, or P holds the head of Q, or Q holds the head of
                  P (a commit in both repositories; a shared commit means a shared root commit).
  copy (step "Not a mirror", rule "shared history with a pool row of the same name"): shared history, the same
                  repository name, and one repository holds the head of the other.
  fork (step "Not a fork", rule R3 "a fork of a pool project by shared root commit"): shared history, and not a copy.
A new project leaves at the first step that one of its pairs fails (the fork step comes before the mirror step).
R1 copy namespace (lower-case URL) also applies to every new project at the mirror step.
Writes copycheck/decisions.tsv (one line per new project) and prints a summary.
With the argument "rule2" it reads rule2_new.jsonl and evidence2.tsv (the GitLab rows that decision 2 brings back
before the shared-history rule; rule2_check.py) and writes decisions2.tsv.
"""
import sys
import csv
import json
import re
import collections
from pathlib import Path

D = Path(__file__).resolve().parent
COPY = re.compile(r"/(mirrors|infrastructure/mirrors|neon/backports-[^/]+|neon/forks|gfx-ci|mesa_ci|openhw-group/backup-\d+)/|invent\.kde\.org/qt/")  # decide.py R1
T = "True"
LINUX = "1da177e4c3f41524e886b7f1b8a0c1fc7321cac2"  # decide.py: a row with this root is a Linux tree (R3; torvalds/linux is selected)


def main():
    rows = json.load(open(D / "rows.json"))
    r2 = sys.argv[1:] == ["rule2"]
    new = [json.loads(l) for l in open(D / ("rule2_new.jsonl" if r2 else "new.jsonl"))]
    ev = list(csv.DictReader(open(D / ("evidence2.tsv" if r2 else "evidence.tsv")), delimiter="\t"))
    r1 = {k for k, r in rows.items() if COPY.search(r["url"].lower() + "/")}
    pairs = collections.defaultdict(list)
    for e in ev:
        q = rows[e["partner"]]
        tests = [e["partner_has_root_new"], e["new_has_root_partner"], e["new_has_head_partner"], e["partner_has_head_new"]]
        shared = e["root_equal"] == T or T in tests
        contain = T in (e["new_has_head_partner"], e["partner_has_head_new"])
        copy_by_host = (q["fork"] or q["mirror"] or e["partner"] in r1
                        or q["exit"] in ("Not a fork", "Not a mirror") or q["exit"].startswith("GitLab copy rules"))
        rel = ""
        if shared:
            rel = "copy" if (e["same_name"] == T and contain) else "fork"
        e["relation"] = rel
        e["partner_is_a_copy_by_host"] = copy_by_host
        e["counts"] = bool(rel) and not copy_by_host
        if e["counts"] and e["partner_selected"] != T and e["partner_has_head_new"] != T:
            e["counts"] = False  # decision 2: the partner left the funnel and P is not behind it
        both_new = e["partner_selected"] == T and e["partner_tom"] != T
        if e["counts"] and both_new:
            assert rel == "copy", ("two new projects share a root and neither is a copy", e["new"], e["partner"])
            e["counts"] = e["partner_has_head_new"] == T
        pairs[e["new"]].append(e)
    out = []
    for p in new:
        ps = pairs.get(p["key"], []) if p["key"].startswith("gitlab:") else []  # decision 1: GitLab rows only
        forks = [e for e in ps if e["counts"] and e["relation"] == "fork"]
        copies = [e for e in ps if e["counts"] and e["relation"] == "copy"]
        linux = p["key"].startswith("gitlab:") and any(e["root_new"] == LINUX for e in ps)
        if forks:
            step, rule, ev_ = "Not a fork", "fork of a pool project by shared root commit (R3)", forks
        elif linux:
            step, rule, ev_ = "Not a fork", "fork of a pool project by shared root commit (R3): a Linux tree (decide.py root rule)", []
        elif copies:
            step, rule, ev_ = "Not a mirror", "shared history with a pool row of the same name", copies
        elif p["key"] in r1:
            step, rule, ev_ = "Not a mirror", "R1 copy namespace", []
        else:
            step, rule, ev_ = "", "", []
        other = [e for e in ps if e["relation"] and not e["counts"]]
        out.append(dict(new=p["key"], host=p["host"], path=p["path"], step=step or "stays", rule=rule,
                        partners="; ".join(f"{rows[e['partner']]['host']}/{rows[e['partner']]['path']} "
                                           f"({'selected' if e['partner_selected'] == T else e['partner_exit']}; {e['relation']}; {e['matched_sha']})"
                                           for e in ev_),
                        partner_tom=any(e["partner_tom"] == T for e in ev_),
                        partner_new=any(e["partner_selected"] == T and e["partner_tom"] != T for e in ev_),
                        ignored_copy_partners="; ".join(f"{rows[e['partner']]['host']}/{rows[e['partner']]['path']} ({e['relation']})" for e in other)))
    cols = list(out[0])
    with open(D / ("decisions2.tsv" if r2 else "decisions.tsv"), "w") as f:
        f.write("\t".join(cols) + "\n")
        for o in out:
            f.write("\t".join(str(o[c]) for c in cols) + "\n")
    print(collections.Counter((o["step"], o["rule"]) for o in out))
    for o in out:
        if o["step"] != "stays" or o["ignored_copy_partners"]:
            print(o["path"], "|", o["step"], "|", o["rule"], "|", o["partners"][:300], "| ignored:", o["ignored_copy_partners"][:200])


if __name__ == "__main__":
    main()
