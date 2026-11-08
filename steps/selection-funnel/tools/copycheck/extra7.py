#!/usr/bin/env python3
"""The GitLab rows that decision 2 (2026-11-08) brings back into the final set: one row each in the new_projects.tsv
format (build_funnel.py fields and hours model). Input: copycheck/decisions2.tsv (rows that stay). Output: the path
given as the first argument."""
import csv, json, sys
from pathlib import Path
D = Path(__file__).resolve().parent
sys.path.insert(0, str(D.parent))
import build_funnel as bf
keep = [r["new"] for r in csv.DictReader(open(D / "decisions2.tsv"), delimiter="\t") if r["step"] == "stays"]
gl = {json.loads(l)["pool_key"]: json.loads(l) for l in open(bf.W / "gitlab_rows.jsonl")}
meas = bf.load_jsonl(bf.W / "gitlab.out.jsonl", "pool_key")
chk = bf.load_jsonl(bf.W / "gitlab_checks.jsonl", "pool_key")
snap = {}
for l in open(bf.W / "gitlab_snapshot_pin.jsonl"):
    d = json.loads(l)
    if d.get("snapshot_commit"):
        snap[d["pool_key"]] = d["snapshot_commit"]
tom_inp = {r["pool_key"]: r for r in csv.DictReader(open(bf.PINNED / "inputs.tsv"), delimiter="\t")}
model = bf.hours_model(tom_inp)
out = [["name", "host", "pinned_commit", "pinned_source", "commits", "tokei_largest", "share_c_cpp_java_rust",
        "dropped_by", "license", "tok_bytes", "est_pipeline_hours"]]
for k in keep:
    g, m = gl[k], meas[k]
    sp = snap.get(k)
    psrc = ("GitLab measure.jsonl head (2026-10-14)" if g["pinned_commit"] else
            "GitLab API: default branch commit at the listing time (2026-10-13/14)" if sp and m.get("commit") == sp
            else "MISMATCH")
    assert psrc != "MISMATCH", k
    sc = g.get("screen_commits")
    commits = int(sc) if sc and int(sc) >= 5000 else (">= 1,000 (probe)" if (chk.get(k) or {}).get("ge1000") else None)
    assert commits is not None and m.get("rule") and m.get("dp8l_class") in bf.PASS_CLASSES, k
    cn = commits if isinstance(commits, int) else 1000
    out.append([g["path"], g["host"], m.get("commit") or g["pinned_commit"], psrc, commits, m["largest"], f"{m['target_share']:.4f}",
                "gitlab copy rules: shared history with a pool row; back by decision 2 (2026-11-08)",
                f"class {m['dp8l_class']}", m.get("tok_bytes"), f"{model(m.get('tok_bytes') or 0, cn):.3f}"])
open(sys.argv[1], "w").write("".join("\t".join(str(c) for c in r) + "\n" for r in out))
print(len(out) - 1, "rows")
