#!/usr/bin/env python3
"""DP3 and DP8L for the kept layer 1 rows (decisions.tsv decision "keep"), with the frame's own code:
s3-measure/measure_clones.py count() (the same mask, vendor rule and bytes by extension) on a depth-1
fetch of the default branch HEAD, and the DP3 test of s4-filter/funnel.py (non-vendored tokenizable
bytes >= 5% of the programming-language bytes, prog_exts.programming_extensions). DP8L: the root rule of
s4-filter/dp8l_rule.py on the root listing (git ls-tree HEAD). The fetched HEAD is the pinned commit.
Output: measure.jsonl (one row per url; resumable)."""
import csv, datetime as dt, json, os, subprocess, sys, tempfile
from pathlib import Path
H = Path(__file__).resolve().parent; DS = H.parent.parent
sys.path.insert(0, str(DS / "s3-measure")); sys.path.insert(0, str(DS / "s4-filter"))
from measure_clones import count  # noqa: E402
from prog_exts import programming_extensions  # noqa: E402
import dp8l_rule  # noqa: E402
PROG = programming_extensions(); SHARE_MIN = 0.05
env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
def git(a, cwd=None): return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, env=env, timeout=7200)
urls = [r["url"] for r in csv.DictReader(open(H / "decisions.tsv"), delimiter="\t") if r["decision"] == "keep"] + sys.argv[1:]
out_p = H / "measure.jsonl"; done = {json.loads(l)["url"] for l in open(out_p)} if out_p.exists() else set()
out = open(out_p, "a")
for u in urls:
    if u in done: continue
    t = tempfile.mkdtemp(dir="/local/home/ellianco/tmp-gitlab"); d = Path(t) / "r.git"
    rec = dict(url=u)
    try:
        git(["init", "-q", "--bare", str(d)])
        r = git(["fetch", "-q", "--depth", "1", u + ".git", "HEAD"], cwd=d)
        if r.returncode: rec.update(status="fetch-failed", error=r.stderr[-300:])
        else:
            head = git(["rev-parse", "FETCH_HEAD"], cwd=d).stdout.strip()
            m = count(git(["ls-tree", "-r", "-l", "--full-tree", head], cwd=d).stdout)
            root = git(["ls-tree", head], cwd=d).stdout.splitlines()
            names = [(l.split("\t", 1)[1], l.split()[1]) for l in root if "\t" in l]
            lic = any((ty == "blob" and dp8l_rule.is_license_file(n)) or (ty == "tree" and dp8l_rule.is_license_dir(n)) for n, ty in names)
            code = sum(v for k, v in m["by_ext"].items() if k in PROG); own = m["tok_bytes"] - m["tok_vendor_bytes"]
            rec.update(status="ok", head_oid=head, tok_bytes=m["tok_bytes"], tok_vendor_bytes=m["tok_vendor_bytes"], code_bytes=code,
                       dp3=bool(code) and own >= SHARE_MIN * code, dp8l=lic, license_names=[n for n, _ in names if dp8l_rule.is_license_name(n)],
                       est_hours=round(m["tok_bytes"] / 1e6 * 63 / 3600, 2))
    finally:
        subprocess.run(["find", t, "-delete"])
    rec["measured_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    out.write(json.dumps(rec) + "\n"); out.flush()
    print(u, rec.get("status"), rec.get("dp3"), rec.get("dp8l"), rec.get("est_hours"), flush=True)
