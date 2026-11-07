"""What-if: stricter code-share rules on the released projects.

Rules (each one is stricter than DP3, so each one keeps a subset of the release):
  share>=X  non-vendored tokenizable bytes >= X of the code bytes (the DP3 measure)
  pred_lang the largest single language (non-vendored bytes) is C, C++, Java or Rust
  pred_grp  the target group (C+C+++Java+Rust) has more bytes than any other single language
Bytes come from the S3 measure (by_ext at the measured commit). Tokens are the release rows.
"""
import csv, json, lzma, os, re, sys
from collections import Counter, defaultdict
from pathlib import Path

P = Path(os.environ.get("PAPER_PIPELINE", Path(__file__).resolve().parents[2] / "pipeline"))
S3 = P / "s3-measure"
MAN = Path(os.environ.get("RELEASE_MANIFEST", "MANIFEST.tsv"))  # MANIFEST.tsv of the release root
sys.path.insert(0, str(S3))
from prog_exts import programming_extensions  # noqa: E402

import os
EXTRA = {"ts": "TypeScript", "tsx": "TypeScript", "mts": "TypeScript", "cts": "TypeScript", "mm": "Objective-C++"}
PROG = programming_extensions() | (set(EXTRA) if os.environ.get("WITH_TS") else set())
TARGET = {"c": "C", "h": "C", "c++": "C++", "cc": "C++", "cp": "C++", "cpp": "C++", "cxx": "C++",
          "h++": "C++", "hh": "C++", "hpp": "C++", "hxx": "C++", "tcc": "C++", "java": "Java", "rs": "Rust"}


def ext_lang():
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
         for x, v in out.items() if x in PROG}
    m.update(TARGET)
    m.update({k: v for k, v in EXTRA.items() if k in PROG})
    return m


def jl(path, key):
    op = lzma.open if path.suffix == ".xz" else open
    d = {}
    if path.exists():
        for line in op(path, "rt"):
            r = json.loads(line)
            if r.get(key):
                d[r[key]] = r
    return d


def n(u):
    return u.lower().rstrip("/").removesuffix(".git").replace("http://", "https://")


def main():
    E = ext_lang()
    trees = {k.lower(): v for k, v in jl(S3 / "trees.jsonl.xz", "name_with_owner").items()}
    trees.update({k.lower(): v for k, v in jl(S3 / "v2/trees.jsonl", "name_with_owner").items()})
    clones = jl(S3 / "clones.jsonl.xz", "pool_key")
    clones.update({k: v for k, v in jl(S3 / "v2/clones.jsonl", "pool_key").items() if v.get("by_ext")})
    frame = {n(r["repo_url"]): r for r in csv.DictReader(open(P / "s4-filter/frame.v4.csv"))}
    rows = list(csv.DictReader(open(MAN), delimiter="\t"))
    out = []
    for r in rows:
        f = frame.get(n(r["clone_url"]))
        m = None
        if f:
            u = n(f["repo_url"])
            nwo = u.split("github.com/", 1)[1] if "github.com/" in u else None
            t = trees.get(nwo) if nwo else None
            if t and t.get("status") == 200 and not t.get("truncated"):
                m = t
            else:
                c = clones.get(f["pool_key"])
                m = c if c and c.get("status") == "ok" else None
        rec = {"project": r["project"], "layer": r["layer"], "rows": int(r["rows"]), "measured": bool(m)}
        if m:
            be, ve = m["by_ext"], m.get("vendor_by_ext", {})
            code = sum(v for k, v in be.items() if k in PROG)
            own = m["tok_bytes"] - m.get("tok_vendor_bytes", 0)
            lang = defaultdict(int)
            for k, v in be.items():
                if k in PROG:
                    lang[E.get(k, k)] += v - ve.get(k, 0)
            top = max(lang.items(), key=lambda kv: kv[1])
            tgt = sum(v for k, v in lang.items() if k in {"C", "C++", "Java", "Rust"})
            other = max([v for k, v in lang.items() if k not in {"C", "C++", "Java", "Rust"}] or [0])
            rec.update(share=own / code if code else 0.0, top=top[0], pred_lang=top[0] in {"C", "C++", "Java", "Rust"},
                       pred_grp=tgt > other)
        out.append(rec)
    json.dump(out, open(Path(__file__).with_name("rows.ts.json" if os.environ.get("WITH_TS") else "rows.json"), "w"))
    meas = [x for x in out if x["measured"]]
    tot_rows = sum(x["rows"] for x in out)
    print(f"projects {len(out)}, measured {len(meas)}, tokens {tot_rows:,}")
    print(f"sanity: measured with share >= 5%: {sum(x['share'] >= 0.05 for x in meas)}")
    rules = [("share >= 5% (DP3, now)", lambda x: x["share"] >= 0.05),
             ("share >= 30%", lambda x: x["share"] >= 0.30),
             ("share >= 50%", lambda x: x["share"] >= 0.50),
             ("largest language is a target", lambda x: x["pred_lang"]),
             ("target group > any other language", lambda x: x["pred_grp"])]
    print("rule\tlayer\tprojects kept\tof\ttokens kept\tshare of tokens")
    for name, fn in rules:
        for lay in ("v1", "x1k", "all"):
            sel = [x for x in meas if lay == "all" or x["layer"] == lay]
            k = [x for x in sel if fn(x)]
            tr = sum(x["rows"] for x in sel)
            kr = sum(x["rows"] for x in k)
            print(f"{name}\t{lay}\t{len(k):,}\t{len(sel):,}\t{kr:,}\t{100*kr/tr:.1f}%")
    print("largest language of the dropped projects (largest language is a target):",
          Counter(x["top"] for x in meas if not x["pred_lang"]).most_common(10))


main()
