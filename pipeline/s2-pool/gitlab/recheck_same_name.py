#!/usr/bin/env python3
"""Recheck of the same-name shared-history results (user decision 2026-10-14 ~01:00 UTC: "Recheck every
row that was checked before the GIT_NO_LAZY_FETCH fix"). For every screen row with step_result "shares
history with a pool row": a new commit-only clone (git clone --bare --filter=tree:0), then
`git cat-file -e <pool head_oid>^{commit}` with GIT_NO_LAZY_FETCH=1 for the pool row of the cluster
entry. Output: recheck.tsv (url, pool_key, confirmed yes/no, commits, rechecked_at). The clone is
deleted at once. All rows are rechecked (also the ones after the fix), so the result does not depend
on the time of the first check."""
import csv, glob, os, subprocess, tempfile, time
from pathlib import Path
H = Path(__file__).resolve().parent
heads = {}
for f in glob.glob(str(H / "clusters*.tsv")):
    for l in open(f):
        p = l.rstrip("\n").split("\t")
        if len(p) >= 4: heads[p[0].lower().rstrip("/").removesuffix(".git")] = (p[1], p[3])
rows = []
for f in glob.glob(str(H / "screen*.tsv")):
    for r in csv.DictReader(open(f), delimiter="\t"):
        if r["step_result"] == "shares history with a pool row": rows.append(r)
out_p = H / "recheck.tsv"; done = set()
if out_p.exists(): done = {l.split("\t")[0] for l in out_p.read_text().splitlines()[1:]}
else: out_p.write_text("url\tpool_key\tconfirmed\tcommits\trechecked_at\n")
out = open(out_p, "a"); env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
for r in rows:
    u = r["url"]
    if u in done: continue
    pk, oid = heads.get(u, ("", ""))
    t = tempfile.mkdtemp(dir=os.path.expanduser("~/tmp-gitlab")); g = Path(t) / "r.git"
    p = subprocess.run(["git", "clone", "-q", "--bare", "--filter=tree:0", u + ".git", str(g)], capture_output=True, env=env, timeout=7200)
    if p.returncode: res, n = "clone failed", ""
    else:
        n = subprocess.run(["git", "-C", str(g), "rev-list", "--count", "HEAD"], capture_output=True, text=True).stdout.strip()
        ok = oid and subprocess.run(["git", "-C", str(g), "cat-file", "-e", oid + "^{commit}"], capture_output=True, env=env).returncode == 0
        res = "yes" if ok else "no"
    subprocess.run(["find", t, "-delete"])
    out.write(f"{u}\t{pk}\t{res}\t{n}\t{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"); out.flush()
