"""What-if of stricter language rules at the pinned run commit, over all the run input rows.

  python3 pinned.py inputs    write inputs.tsv (10,763 rows: the manifest rows + the frame rows with no file)
  TMPDIR=<work folder> python3 pinned.py measure    measure each row at its pinned commit (resumable)
  python3 pinned.py whatif    projects.tsv and the tables (results.txt)

The measure is the S3 code, unchanged: measure_trees.measure (one GitHub tree call at the commit) and,
for truncated trees and other hosts, measure_clones.measure (a fetch of one commit with depth 1, then
git ls-tree; the temporary folder is removed by measure_clones). An S3 record is reused when its
commit is the pinned commit and it is complete (tree: HTTP 200, not truncated; clone: ok).
Output: measure.jsonl (one line for each project; paths are not kept, only sizes by extension).
"""
import csv
import datetime as dt
import json
import lzma
import os
import queue
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
P = Path(os.environ.get("PAPER_PIPELINE", Path(__file__).resolve().parents[3] / "pipeline"))
S3 = P / "s3-measure"
MAN = Path(os.environ.get("RELEASE_MANIFEST", "MANIFEST.tsv"))  # MANIFEST.tsv of the release root
sys.path.insert(0, str(S3))
from prog_exts import programming_extensions  # noqa: E402

LOG = HERE / "run.log"
OUT = Path(os.environ.get("PINNED_OUT", HERE / "measure.jsonl"))
INPUTS = HERE / "inputs.tsv"
LAYER = {"≥ 5,000": "v1", "1,000–4,999": "x1k"}
BRLCAD_NEW = "https://git.brlcad.org/BRL-CAD/brlcad.git"

# The 9 frame rows with no file (LIMITATIONS.md section 1). The pinned commit is the pinned_sha of the
# last run attempt in the run ledgers (release-work/ledgers-20261028, */ledger*.jsonl).
NO_FILE = {
    "signalwire__freeswitch": ("12ac48ab9e692d645b91b83bab89a85abdc3af53", "ledger batch7/a3"),
    "kitao__pyxel": ("50f9bd77780c993aca62b5b221766bde5791081d", "ledger batch19 (= frame commit; repository gone, nothing checked out)"),
    "googleapis__discovery-artifact-manager": ("bb221e1f67161c059cd3780eccce6118c37da22c", "ledger batch6/a4, run 20261012T003950Z"),
    "Librelancer__Librelancer": ("c113747dbcca92eadae09e569f7383a338460c83", "ledger dataset-x1k"),
    "vllm-project__semantic-router": ("c9b65d59aae54621f6d0831a661b407edc823adb", "ledger dataset-x1k"),
    "visgl__loaders.gl": ("6773abca212dc20c07ae243d5f47c56b6bd174d5", "ledger dataset-x1k"),
    "greta-dev__greta": ("c656bd5917ea53bb0f11c53d2cafca780924ec22", "ledger dataset-x1k"),
    "notnotype__neuro-book": ("532ebb8a09c430003c24cd69cdbdc856a14a4737", "ledger dataset-x1k (final-a)"),
    "pur1fying__blue_archive_auto_script": ("0d57f4725b7c063a4b66235b61b2517248154fa0", "ledger dataset-x1k (final-a)"),
}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


_loglock = threading.Lock()


def log(msg):
    line = f"{now()} {msg}"
    with _loglock:
        print(line, flush=True)
        with LOG.open("a") as f:
            f.write(line + "\n")


def n(u):
    return u.lower().rstrip("/").removesuffix(".git").replace("http://", "https://")


def jl(path, key):
    op = lzma.open if path.suffix == ".xz" else open
    d = {}
    if path.exists():
        for line in op(path, "rt"):
            r = json.loads(line)
            if r.get(key):
                d[r[key]] = r
    return d


def s3_records():
    """The S3 records, read as whatif.py reads them (the later file wins)."""
    trees = {k.lower(): v for k, v in jl(S3 / "trees.jsonl.xz", "name_with_owner").items()}
    trees.update({k.lower(): v for k, v in jl(S3 / "v2/trees.jsonl", "name_with_owner").items()})
    clones = jl(S3 / "clones.jsonl.xz", "pool_key")
    clones.update({k: v for k, v in jl(S3 / "v2/clones.jsonl", "pool_key").items() if v.get("by_ext")})
    return trees, clones


def frame_rows():
    fr = [r for r in csv.DictReader(open(P / "s4-filter/frame.v4.csv")) if r["layer"] in LAYER]
    for f in ("supplement25.gitlab.csv", "supplement26.gitlab.csv"):
        fr += list(csv.DictReader(open(P / "s4-filter" / f)))
    return fr


def cmd_inputs():
    fr = frame_rows()
    byurl = {n(r["repo_url"]): r for r in fr}
    assert len(byurl) == len(fr)
    man = list(csv.DictReader(open(MAN), delimiter="\t"))
    used, out = set(), []
    for m in man:
        f = byurl[n(m["clone_url"])]
        used.add(n(f["repo_url"]))
        lay = LAYER.get(f["layer"], "v1")
        assert lay == m["layer"], (m["project"], f["layer"], m["layer"])
        assert f["head_oid"] == m["frame_commit"], m["project"]
        out.append(dict(project=m["project"], layer=m["layer"], host=f["host"], repo_url=f["repo_url"],
                        pool_key=f["pool_key"], frame_commit=m["frame_commit"], pinned_commit=m["run_commit"],
                        pinned_source="manifest run_commit", rows=m["rows"], has_file="yes"))
    for f in fr:
        if n(f["repo_url"]) in used:
            continue
        proj = f["slug"].replace("/", "__")
        pin, src = NO_FILE[proj]
        out.append(dict(project=proj, layer=LAYER.get(f["layer"], "v1"), host=f["host"], repo_url=f["repo_url"],
                        pool_key=f["pool_key"], frame_commit=f["head_oid"], pinned_commit=pin, pinned_source=src,
                        rows="0", has_file="no"))
    with INPUTS.open("w") as fo:
        w = csv.DictWriter(fo, fieldnames=list(out[0]), delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    c = Counter((r["layer"], r["has_file"]) for r in out)
    print(f"{len(out)} rows: {dict(c)}; frame rows {len(fr)}; pinned != frame: "
          f"{sum(r['pinned_commit'] != r['frame_commit'] for r in out)}")


def load_inputs():
    return list(csv.DictReader(open(INPUTS), delimiter="\t"))


def nwo_of(r):
    u = n(r["repo_url"])
    return u.split("github.com/", 1)[1] if r["host"] == "github.com" else None


KEEP = ("status", "head_oid", "truncated", "total_bytes", "n_blobs", "tok_bytes", "n_tok", "tok_vendor_bytes",
        "by_ext", "vendor_by_ext", "error")


def slim(m):
    return {k: m[k] for k in KEEP if k in m}


def reusable(r, trees, clones):
    pin, nwo = r["pinned_commit"], nwo_of(r)
    t = trees.get(nwo) if nwo else None
    if t and t.get("status") == 200 and not t.get("truncated") and t.get("head_oid") == pin:
        return "s3 tree", t
    c = clones.get(r["pool_key"])
    if (not nwo or (t and t.get("truncated"))) and c and c.get("status") == "ok" and c.get("head_oid") == pin:
        return "s3 clone", c
    return None, None


class Pacer:
    """At most one tree call each MIN_GAP seconds; wait for the reset when the quota runs low."""
    MIN_GAP = 0.8

    def __init__(self):
        self.last, self.calls = 0.0, 0

    def quota(self):
        r = subprocess.run(["gh", "api", "rate_limit", "--jq", ".resources.core"], capture_output=True, text=True)
        try:
            return json.loads(r.stdout)
        except ValueError:
            return None

    lock = threading.Lock()

    def wait(self):
        with self.lock:
            self._wait()

    def _wait(self):
        if self.calls % 200 == 0:
            q = self.quota()
            if q and q["remaining"] < 250:
                s = q["reset"] - time.time() + 10
                log(f"quota {q['remaining']} left, waiting {int(s)}s for the reset")
                time.sleep(max(s, 10))
        gap = time.time() - self.last
        if gap < self.MIN_GAP:
            time.sleep(self.MIN_GAP - gap)
        self.last = time.time()
        self.calls += 1


def cmd_measure():
    import measure_clones
    import measure_trees
    measure_trees.log = log  # keep the S3 run.log unchanged
    measure_clones.log = log
    measure_clones.WORK.mkdir(parents=True, exist_ok=True)
    log(f"start; clone work dir {measure_clones.WORK}; git {measure_clones.git(['--version']).stdout.strip()}")
    rows = load_inputs()
    done = {}
    if OUT.exists():
        for line in OUT.open():
            d = json.loads(line)
            done[d["project"]] = d
    trees, clones = s3_records()
    wlock = threading.Lock()
    stats = Counter()

    def write(r, method, m, extra=None):
        rec = dict(project=r["project"], layer=r["layer"], pinned_commit=r["pinned_commit"], method=method,
                   ok=bool(m) and (m.get("status") in (200, "ok")) and not m.get("truncated"), fetched_at=now())
        rec.update(extra or {})
        if m:
            rec["measure"] = slim(m)
        with wlock:
            with OUT.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            stats[method] += 1

    q = queue.Queue()

    def clone_worker():
        while True:
            item = q.get()
            if item is None:
                return
            r, url, extra = item
            free = os.statvfs(measure_clones.WORK)
            if free.f_bavail * free.f_frsize < 200e9:
                log("less than 200 GB free; clone worker stops")
                write(r, "clone", None, dict(extra, note="not measured: disk guard"))
                continue
            t0 = time.time()
            m = measure_clones.measure({"pool_key": r["pool_key"], "url": url, "kind": "pinned", "head_oid": r["pinned_commit"]})
            stats["fetches"] += 1
            if m.get("status") == "ok" and m.get("head_oid") != r["pinned_commit"]:
                m = dict(m, status="head-mismatch")
            write(r, "clone", m, dict(extra, clone_url=url))
            log(f"clone {r['project']}: {m.get('status')} {int(time.time() - t0)}s {m.get('error', '')[-150:]}")

    workers = [threading.Thread(target=clone_worker, daemon=True) for _ in range(3)]
    for w in workers:
        w.start()
    pacer = Pacer()
    todo = [r for r in rows if r["project"] not in done]
    if os.environ.get("PINNED_TEST"):  # a few rows of each kind, for a test run
        pick = os.environ["PINNED_TEST"].split(",")
        todo = [r for r in todo if r["project"] in pick]
    log(f"{len(rows)} rows, {len(done)} done, {len(todo)} to go")
    def handle(item):
        i, r = item
        how, m = reusable(r, trees, clones)
        if how:
            write(r, how, m)
            return
        nwo = nwo_of(r)
        if not nwo:
            q.put((r, r["repo_url"], {}))
            return
        pacer.wait()
        t = measure_trees.measure(nwo, r["pinned_commit"])
        stats["tree_calls"] += 1
        if t["status"] == 200 and not t.get("truncated"):
            write(r, "tree", t)
        elif t["status"] == 200:
            q.put((r, r["repo_url"], {"tree": "truncated", "tree_n_blobs": t.get("n_blobs")}))
        elif r["project"] == "BRL-CAD__brlcad":
            q.put((r, BRLCAD_NEW, {"tree": f"HTTP {t['status']}", "note": "GitHub hides the repository; the run used the new host"}))
        else:
            write(r, "tree", t)
        if i % 250 == 0:
            log(f"{i}/{len(todo)}; {dict(stats)}; clone queue {q.qsize()}")

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as ex:  # 3 tree calls in flight; the pacer keeps the rate under the quota
        list(ex.map(handle, enumerate(todo, 1)))
    for _ in workers:
        q.put(None)
    for w in workers:
        w.join()
    log(f"end; {dict(stats)}; tree calls this session {pacer.calls}")


# --- what-if -----------------------------------------------------------------------------------------
EXTRA = {"ts": "TypeScript", "tsx": "TypeScript", "mts": "TypeScript", "cts": "TypeScript", "mm": "Objective-C++"}
TARGET = {"c": "C", "h": "C", "c++": "C++", "cc": "C++", "cp": "C++", "cpp": "C++", "cxx": "C++",
          "h++": "C++", "hh": "C++", "hpp": "C++", "hxx": "C++", "tcc": "C++", "java": "Java", "rs": "Rust"}
TL = {"C", "C++", "Java", "Rust"}


def ext_lang(prog):
    """whatif.py ext_lang, with the extension set as a parameter."""
    out, lang, cur, in_ext = {}, None, [], False
    for line in open(S3 / "languages.yml"):
        if re.match(r"^[^\s#][^:]*:\s*$", line):
            for x in cur:
                out.setdefault(x, set()).add(lang)
            lang, cur, in_ext = line[:-2], [], False
            continue
        if re.match(r"^  extensions:", line):
            in_ext = True
            continue
        if in_ext:
            m = re.match(r'^  - "\.(.+)"', line)
            if m:
                cur.append(m.group(1).lower())
                continue
            in_ext = False
    for x in cur:
        out.setdefault(x, set()).add(lang)
    m = {x: (TARGET[x] if x in TARGET else sorted(v)[0] if len(v) == 1 else "/".join(sorted(v)))
         for x, v in out.items() if x in prog}
    m.update(TARGET)
    m.update({k: v for k, v in EXTRA.items() if k in prog})
    return m


BASE = programming_extensions()
VARIANTS = {"linguist": (BASE, ext_lang(BASE)), "with_ts": (BASE | set(EXTRA), ext_lang(BASE | set(EXTRA)))}
RULES = [("share >= 5% (DP3)", "r5"), ("share >= 30%", "r30"), ("share >= 50%", "r50"),
         ("largest language is C, C++, Java or Rust", "lang"), ("target group > any other single language", "grp")]


def evaluate(m, variant):
    if m.get("share_only"):
        if variant != "linguist":
            return None
        own, code = m["tok_bytes"] - m["tok_vendor_bytes"], m["code_bytes"]
        share = own / code if code else 0.0
        return dict(share=share, top=None, r5=share >= 0.05, r30=share >= 0.30, r50=share >= 0.50, lang=None, grp=None)
    prog, E = VARIANTS[variant]
    be, ve = m["by_ext"], m.get("vendor_by_ext", {})
    code = sum(v for k, v in be.items() if k in prog)
    own = m["tok_bytes"] - m.get("tok_vendor_bytes", 0)
    lang = defaultdict(int)
    for k, v in be.items():
        if k in prog:
            lang[E.get(k, k)] += v - ve.get(k, 0)
    top = max(lang.items(), key=lambda kv: kv[1]) if lang else ("", 0)
    tgt = sum(v for k, v in lang.items() if k in TL)
    other = max([v for k, v in lang.items() if k not in TL] or [0])
    share = own / code if code else 0.0
    return dict(share=share, top=top[0], r5=share >= 0.05, r30=share >= 0.30, r50=share >= 0.50,
                lang=top[0] in TL, grp=tgt > other)


GITLAB = {n(d["url"]): d for d in map(json.loads, open(P / "s2-pool/gitlab/measure.jsonl")) if d["status"] == "ok"}


def frame_measure(r, trees, clones):
    """The frame-commit record, chosen as whatif.py chooses it. The GitLab supplement rows (measure_dp.py)
    kept only code and tokenizable bytes, so they give the share rules of the Linguist variant only."""
    g = GITLAB.get(n(r["repo_url"]))
    if g and g["head_oid"] == r["frame_commit"]:
        return {"share_only": True, **g}
    nwo = nwo_of(r)
    t = trees.get(nwo) if nwo else None
    if t and t.get("status") == 200 and not t.get("truncated"):
        return t
    c = clones.get(r["pool_key"])
    return c if c and c.get("status") == "ok" else None


def cmd_whatif():
    rows = load_inputs()
    meas = {}
    for line in OUT.open():
        d = json.loads(line)
        meas[d["project"]] = d
    trees, clones = s3_records()
    recs = []
    for r in rows:
        d = meas.get(r["project"])
        rec = dict(project=r["project"], layer=r["layer"], has_file=r["has_file"], rows=int(r["rows"]),
                   pinned_commit=r["pinned_commit"], frame_commit=r["frame_commit"],
                   method=d["method"] if d else "", measured=bool(d and d["ok"]))
        if not rec["measured"]:
            m = (d or {}).get("measure") or {}
            rec["why_not"] = (d or {}).get("note") or f"{d['method'] if d else 'no record'}: {m.get('status', '')} {m.get('error', '')[:80]}".strip()
        fm = frame_measure(r, trees, clones)
        rec["frame_measured"] = bool(fm)
        for v in VARIANTS:
            if rec["measured"]:
                rec[v] = evaluate(d["measure"], v)
            if fm and evaluate(fm, v):
                rec["frame_" + v] = evaluate(fm, v)
        recs.append(rec)
    json.dump(recs, open(HERE / "rows.json", "w"))

    cols = ["project", "layer", "has_file", "rows", "pinned_commit", "frame_commit", "pinned_equals_frame",
            "method", "measured"]
    for v in VARIANTS:
        cols += [f"share_{v}", f"largest_{v}"] + [f"{k}_{v}" for _, k in RULES]
    cols += ["frame_share_linguist", "frame_share_with_ts", "why_not_measured"]
    with (HERE / "projects.tsv").open("w") as fo:
        fo.write("\t".join(cols) + "\n")
        for x in recs:
            row = [x["project"], x["layer"], x["has_file"], str(x["rows"]), x["pinned_commit"], x["frame_commit"],
                   str(x["pinned_commit"] == x["frame_commit"]).lower(), x["method"], str(x["measured"]).lower()]
            for v in VARIANTS:
                e = x.get(v)
                row += [f"{e['share']:.6f}", e["top"]] + [str(e[k]).lower() for _, k in RULES] if e else [""] * (2 + len(RULES))
            row += [f"{x['frame_' + v]['share']:.6f}" if x.get("frame_" + v) else "" for v in VARIANTS]
            row.append(x.get("why_not", ""))
            fo.write("\t".join(row) + "\n")

    out = []
    p = out.append
    c = Counter((x["layer"], x["has_file"]) for x in recs)
    p(f"input rows {len(recs)}: " + ", ".join(f"{k[0]} {'with' if k[1] == 'yes' else 'without'} file {v}" for k, v in sorted(c.items())))
    p(f"pinned commit != frame commit: {sum(x['pinned_commit'] != x['frame_commit'] for x in recs)}")
    p("method: " + ", ".join(f"{k} {v}" for k, v in Counter(x["method"] for x in recs).most_common()))
    p(f"measured at the pinned commit: {sum(x['measured'] for x in recs)}; not measured: {sum(not x['measured'] for x in recs)}")
    for x in recs:
        if not x["measured"]:
            p(f"  not measured: {x['project']} ({x['layer']}, file {x['has_file']}): {x['why_not']}")
    for v in VARIANTS:
        p("")
        p(f"== variant {v} (pinned commit) ==")
        p("rule\tlayer\tprojects kept\tof measured\ttoken rows kept\tof token rows (measured)\tshare of token rows")
        for name, k in RULES:
            for lay in ("v1", "x1k", "all"):
                sel = [x for x in recs if x["measured"] and (lay == "all" or x["layer"] == lay)]
                kept = [x for x in sel if x[v][k]]
                tr, kr = sum(x["rows"] for x in sel), sum(x["rows"] for x in kept)
                p(f"{name}\t{lay}\t{len(kept):,}\t{len(sel):,}\t{kr:,}\t{tr:,}\t{100 * kr / tr if tr else 0:.1f}%")
        low = sorted((x for x in recs if x["measured"] and not x[v]["r5"]), key=lambda x: x[v]["share"])
        p(f"share < 5% at the pinned commit ({v}): {len(low)} projects "
          f"(v1 {sum(x['layer'] == 'v1' for x in low)}, x1k {sum(x['layer'] == 'x1k' for x in low)}; "
          f"with a file {sum(x['has_file'] == 'yes' for x in low)}, token rows {sum(x['rows'] for x in low):,})")
        p("largest language of the projects that fail 'largest language is C, C++, Java or Rust': "
          + str(Counter(x[v]["top"] for x in recs if x["measured"] and not x[v]["lang"]).most_common(10)))
        with (HERE / f"below5.{v}.tsv").open("w") as fo:
            fo.write("project\tlayer\thas_file\trows\tpinned_commit\tshare_pinned\tshare_frame\tlargest_pinned\n")
            for x in low:
                fs = x.get("frame_" + v)
                fo.write(f"{x['project']}\t{x['layer']}\t{x['has_file']}\t{x['rows']}\t{x['pinned_commit']}\t"
                         f"{x[v]['share']:.6f}\t{fs['share']:.6f}\t{x[v]['top']}\n" if fs else
                         f"{x['project']}\t{x['layer']}\t{x['has_file']}\t{x['rows']}\t{x['pinned_commit']}\t"
                         f"{x[v]['share']:.6f}\t\t{x[v]['top']}\n")
    for v in VARIANTS:
        p("")
        p(f"== variant {v}, frame commit, manifest rows (check against ../result*.txt) ==")
        for name, k in RULES:
            sel = [x for x in recs if x["has_file"] == "yes" and x.get("frame_" + v) and x["frame_" + v][k] is not None]
            kept = [x for x in sel if x["frame_" + v][k]]
            tr, kr = sum(x["rows"] for x in sel), sum(x["rows"] for x in kept)
            p(f"{name}\tall\t{len(kept):,}\t{len(sel):,}\t{kr:,}\t{100 * kr / tr if tr else 0:.1f}%")
    p("")
    p("== frame commit vs pinned commit (projects measured at both) ==")
    p("variant\trule\tlayer\tboth measured\tsame result\tkept at frame, dropped at pinned\tdropped at frame, kept at pinned")
    for v in VARIANTS:
        for name, k in RULES:
            for lay in ("v1", "x1k", "all"):
                sel = [x for x in recs if x["measured"] and x.get("frame_" + v) and x["frame_" + v][k] is not None
                       and (lay == "all" or x["layer"] == lay)]
                a = sum(x["frame_" + v][k] and not x[v][k] for x in sel)
                b = sum(not x["frame_" + v][k] and x[v][k] for x in sel)
                p(f"{v}\t{name}\t{lay}\t{len(sel):,}\t{len(sel) - a - b:,}\t{a:,}\t{b:,}")
    (HERE / "results.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


def cmd_retry():
    """Once more for the clone-failed rows. A host that refuses a fetch by SHA ("unadvertised object") gets
    the default branch HEAD at depth 1, deepened (at most 4,000 commits) until the pinned commit is there;
    then the same ls-tree and count() of measure_clones. Like measure_v2.facts_from_head. A new line is
    appended; the last line of a project is the one that counts."""
    import shutil
    import tempfile
    import measure_clones as mc
    mc.log = log
    mc.WORK.mkdir(parents=True, exist_ok=True)
    rows = {r["project"]: r for r in load_inputs()}
    last = {}
    for line in OUT.open():
        d = json.loads(line)
        last[d["project"]] = d
    for proj, d in last.items():
        if d["ok"] or d["method"] != "clone":
            continue
        r = rows[proj]
        url = d.get("clone_url") or r["repo_url"]
        m = mc.measure({"pool_key": r["pool_key"], "url": url, "kind": "pinned-retry", "head_oid": r["pinned_commit"]})
        how = "clone"
        if m.get("status") == "clone-failed" and "unadvertised object" in m.get("error", ""):
            how = "clone (default branch, deepened)"
            dd = Path(tempfile.mkdtemp(dir=mc.WORK))
            try:
                mc.git(["init", "-q", "--bare", str(dd)])
                f = mc.git(["fetch", "-q", "--depth", "1", url, "HEAD"], cwd=dd)
                depth = 1
                while not f.returncode and mc.git(["cat-file", "-e", r["pinned_commit"] + "^{commit}"], cwd=dd).returncode and depth < 4000:
                    depth *= 4
                    f = mc.git(["fetch", "-q", "--depth", str(depth), url, "HEAD"], cwd=dd)
                if f.returncode:
                    m = dict(m, status="clone-failed", error=f.stderr.strip()[-300:])
                elif mc.git(["cat-file", "-e", r["pinned_commit"] + "^{commit}"], cwd=dd).returncode:
                    m = dict(m, status="pinned-not-in-history", error=f"not in the last {depth} commits")
                else:
                    ls = mc.git(["ls-tree", "-r", "-l", "--full-tree", r["pinned_commit"]], cwd=dd)
                    m = dict(m, status="ok", head_oid=r["pinned_commit"], fetch_depth=depth, **mc.count(ls.stdout))
            finally:
                shutil.rmtree(dd, ignore_errors=True)
        ok = m.get("status") == "ok" and m.get("head_oid") == r["pinned_commit"]
        rec = dict(project=proj, layer=r["layer"], pinned_commit=r["pinned_commit"], method=how, ok=ok,
                   fetched_at=now(), clone_url=url, retry=True, measure=slim(m))
        with OUT.open("a") as fo:
            fo.write(json.dumps(rec) + "\n")
        log(f"retry {proj}: {m.get('status')} {m.get('error', '')[-150:]}")


if __name__ == "__main__":
    {"inputs": cmd_inputs, "measure": cmd_measure, "retry": cmd_retry, "whatif": cmd_whatif}[sys.argv[1]]()
