#!/usr/bin/env python3
"""DP8L v4 near misses for the GitLab rows that fail only DP8L (user decision 2026-10-14 ~16:40 UTC, "yes to mutt":
the near-miss classes C, D and E of DP8L v4 now also pass GitLab rows).

The rows: measure.jsonl rows with status ok, dp3 true and dp8l false. For each row, a depth-1 fetch of the pinned
head_oid of measure.jsonl gives the trees. The classes are the classes of s4-filter/dp8l-audit/audit_dp8l.py
report(), with its own patterns (NAME_RULE, ROOT_NEAR, THIRD_PARTY, PACKAGE_FILES) and its order:
  P  a root entry matches NAME_RULE, but it is no license file or folder (not a near miss)
  C  a root entry matches ROOT_NEAR (other root name)
  D  a root package file (PACKAGE_FILES) declares a license
  E  a file below the root, outside a third-party folder, matches NAME_RULE (license file in a subfolder)
  F  only the first root README names a license; G  license files only in third-party folders; H  no evidence
  (F, G and H do not pass)
Here git trees replace the GitHub REST responses of the audit. Output: near_miss.tsv.
"""
import csv, json, os, subprocess, sys, tempfile
from pathlib import Path
H = Path(__file__).resolve().parent; DS = H.parent.parent
sys.path.insert(0, str(DS / "s4-filter")); sys.path.insert(0, str(DS / "s4-filter/dp8l-audit"))
from audit_dp8l import NAME_RULE, ROOT_NEAR, THIRD_PARTY, PACKAGE_FILES, README_LICENSE, REASON  # noqa: E402
import dp8l_rule  # noqa: E402
from funnel import NEAR_MISS  # noqa: E402
env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
def git(a, cwd): return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env=env, timeout=7200)
rows = [json.loads(l) for l in open(H / "measure.jsonl")]
rows = [r for r in rows if r.get("status") == "ok" and r["dp3"] and not r["dp8l"]]
out = []
for r in rows:
    t = tempfile.mkdtemp(dir=os.path.expanduser("~/tmp-gitlab")); d = Path(t) / "r.git"
    try:
        git(["init", "-q", "--bare", str(d)], cwd=t)
        oid = r["head_oid"]
        if git(["fetch", "-q", "--depth", "1", r["url"] + ".git", oid], cwd=d).returncode:
            sys.exit(f"fetch of {oid} failed: {r['url']}")
        root = [l.split("\t", 1) for l in git(["ls-tree", oid], cwd=d).stdout.splitlines()]
        ents = [(p, meta.split()[1], meta.split()[2]) for meta, p in root]  # path, type, sha
        allb = [l.split("\t", 1)[1] for l in git(["ls-tree", "-r", oid], cwd=d).stdout.splitlines()]
        rule_b = [p for p, ty, _ in ents if NAME_RULE.match(p) and ty == "blob"]
        rule_t = [p for p, ty, _ in ents if NAME_RULE.match(p) and ty == "tree"]
        lic = [p for p in rule_b if dp8l_rule.is_license_file(p)] + [p for p in rule_t if dp8l_rule.is_license_dir(p)]
        near = [p for p, _, _ in ents if not NAME_RULE.match(p) and ROOT_NEAR.search(p)]
        pkg, own, third, readme = [], [], [], ""
        if not (rule_b or rule_t):
            rd = sorted(p for p, ty, _ in ents if ty == "blob" and p.lower().startswith("readme"))
            if rd:  # the GitHub readme endpoint picks one README; here the first root README by name
                sha = next(s for p, _, s in ents if p == rd[0])
                readme = next((l.strip()[:160] for l in git(["cat-file", "-p", sha], cwd=d).stdout.splitlines()
                               if README_LICENSE.search(l)), "")
            for p, ty, sha in ents:
                if ty == "blob" and p in PACKAGE_FILES and PACKAGE_FILES[p].search(git(["cat-file", "-p", sha], cwd=d).stdout):
                    pkg.append(p)
            for p in allb:
                if "/" in p and NAME_RULE.match(p.rsplit("/", 1)[1]):
                    (third if THIRD_PARTY.search(p) else own).append(p)
        cat = ("A" if lic else "P" if rule_b or rule_t else "C" if near else "D" if pkg else "E" if own
               else "F" if readme else "G" if third else "H")
        reason = REASON.get(cat, "has a license file")
        out.append(dict(url=r["url"], head_oid=oid, cls=cat, reason=reason, passes=reason in NEAR_MISS,
                        root_near_names=";".join(near), package_files=";".join(pkg),
                        subfolder_examples=";".join(own[:3]), subfolder_files=len(own), third_party_files=len(third), readme_line=readme))
    finally:
        subprocess.run(["find", t, "-delete"])
with open(H / "near_miss.tsv", "w", newline="") as f:
    w = csv.DictWriter(f, list(out[0]), delimiter="\t", lineterminator="\n"); w.writeheader(); w.writerows(out)
for o in out: print(o)
