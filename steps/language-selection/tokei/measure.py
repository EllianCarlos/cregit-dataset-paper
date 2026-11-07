#!/usr/bin/env python3
"""Language mix of every input project of the cregit token dataset, measured with tokei at the pinned run commit.

Steps (python3 measure.py <step>):
  langs   build languages.tsv: each tokei 14.0.0 language, whether it counts as a programming language, and how
          that was decided (name match against Linguist's languages.yml, or a hand mapping listed in HAND).
  sample  write sample30.tsv: the 30 test projects (10 largest by rows, 10 random, 10 random of the 400 rows
          whose two byte-based results differ).
  run     measure the projects (--sample or --all) with --workers N parallel workers. One JSON line per project
          is appended to measure.jsonl as it ends; a restart skips the projects whose last line is final.
  report  write projects.tsv and summary.json from measure.jsonl.

Per project: git init, git fetch --depth 1 <url> <pinned sha>, git checkout, delete .git, remove the vendored
directories (the selection's vendor rule, measure_trees.VENDOR), remove the Qt translation .ts files, run tokei
--hidden --no-ignore -o json, keep only per-language code counts, delete the temporary folder.
The outputs hold no paths, no file names and no person data.
"""
import argparse
import collections
import contextlib
import csv
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WHATIF = HERE.parent
PINNED = WHATIF / "pinned"
MANIFEST = Path(os.environ.get("RELEASE_MANIFEST", "MANIFEST.tsv"))  # MANIFEST.tsv of the release root
S3 = Path(os.environ.get("PAPER_PIPELINE", HERE.parents[2] / "pipeline")) / "s3-measure"
LANGUAGES_YML = S3 / "languages.yml"
WORK = Path(os.environ.get("TOKEI_WORK", Path(tempfile.gettempdir()) / "tokei-work"))
TOKEI = "/nix/store/m5547wgcn4izfrvm2rvd52f42xrdb00f-tokei-14.0.0/bin/tokei"
OUT = HERE / "measure.jsonl"

# The selection's vendor rule, copied from s3-measure/measure_trees.py (VENDOR). A path is vendored when one of
# its directory components is one of these names, case-insensitive.
VENDOR = re.compile(r"(^|/)(vendor|vendored|third_party|third-party|thirdparty|3rdparty|external|deps)/", re.I)
VENDOR_DIRS = {"vendor", "vendored", "third_party", "third-party", "thirdparty", "3rdparty", "external", "deps"}
TARGET = ("C", "C++", "Java", "Rust")
MERGE = {"C Header": "C", "C++ Header": "C++"}
DROPPED = {"dust-tt__dust", "abgox__PSCompletions", "milisp__codexia"}
GITHUB_MIRROR = {"git.libreoffice.org__libvisio": "https://github.com/LibreOffice/libvisio.git"}
DEEPEN = {"git.busybox.net__busybox"}  # the host refuses a fetch by SHA
QT_TS = (b"<?xml", b"<!DOCTYPE TS", b"<TS")

# tokei languages whose name is not a Linguist language name (case-insensitive), decided by hand:
# name -> (programming?, the Linguist language it was mapped to, or "none" with the reason).
HAND = {
    "Alex": (True, "Lex"), "Arduino C++": (True, "C++"), "Ark TypeScript": (True, "ArkTS"),
    "Arturo": (True, "none: general-purpose language"), "ASP": (True, "Classic ASP"),
    "GNU Style Assembly": (True, "Unix Assembly"), "Autoconf": (True, "M4Sugar"), "Automake": (True, "Makefile"),
    "AXAML": (False, "XML"), "BASH": (True, "Shell"), "Batch": (True, "Batchfile"), "Bazel": (True, "Starlark"),
    "Bean": (False, "none: Beancount ledger data"), "C Header": (True, "C"), "C++ Header": (True, "C++"),
    "C Shell": (True, "Tcsh"), "Cabal": (False, "Cabal Config"), "Cassius": (False, "none: CSS template"),
    "CIL (SELinux)": (False, "CIL"), "ClojureC": (True, "Clojure"), "ClojureScript": (True, "Clojure"),
    "Cogent": (True, "none: general-purpose language"), "ColdFusion CFScript": (True, "ColdFusion CFC"),
    "Coq": (True, "Rocq Prover"), "C++ Module": (True, "C++"), "DAML": (True, "none: smart-contract language"),
    "Device Tree": (False, "none: hardware description data"), ".NET Resource": (False, "XML"),
    "Dream Maker": (True, "DM"), "Dust.js": (False, "none: HTML template"),
    "EdgeDB Schema Definition": (True, "EdgeQL"), "Ebuild": (True, "Gentoo Ebuild"),
    "8th": (True, "none: general-purpose language"), "Emacs Dev Env": (True, "Emacs Lisp"),
    "Emojicode": (True, "none: general-purpose language"), "FEN": (False, "none: chess position data"),
    "FlatBuffers Schema": (False, "FlatBuffers"), "Forge Config": (False, "none: configuration data"),
    "FORTRAN Legacy": (True, "Fortran"), "FORTRAN Modern": (True, "Fortran Free Form"),
    "GDB Script": (True, "GDB"), "Gherkin (Cucumber)": (True, "Gherkin"), "Gml": (True, "Game Maker Language"),
    "Go HTML": (False, "Go Template"), "Gwion": (True, "none: general-purpose language"),
    "Hamlet": (False, "none: HTML template"), "Happy": (True, "Yacc"),
    "Headache": (True, "none: general-purpose language"), "HEX": (False, "none: hex data"),
    "Hex0": (False, "none: hex data"), "Hex1": (False, "none: hex data"), "Hex2": (False, "none: hex data"),
    "HICAD": (True, "none: CAD macro language"), "hledger": (False, "none: ledger data"),
    "Intel HEX": (False, "none: hex data"), "JSLT": (True, "none: JSON transform language, like jq"),
    "Jinja2": (False, "Jinja"), "JSX": (True, "JavaScript"), "Julius": (True, "JavaScript"),
    "Jupyter Notebooks": (False, "Jupyter Notebook"), "K": (True, "none: array language"),
    "Kaem": (True, "none: bootstrap shell"), "Kakoune script": (True, "KakouneScript"),
    "Korn shell": (True, "Shell"), "KV Language": (False, "kvlang"), "LALRPOP": (True, "Yacc"),
    "Lingua Franca": (True, "none: general-purpose language"), "LD Script": (True, "Linker Script"),
    "Lucius": (False, "none: CSS template"), "M1 Assembly": (True, "Assembly"),
    "Madlang": (True, "none: text-generation language"), "Menhir": (True, "Yacc"),
    "Metal Shading Language": (True, "Metal"), "Mlatu": (True, "none: general-purpose language"),
    "Module-Definition": (False, "none: Windows .def export list"), "MSBuild": (False, "XML"),
    "Not Quite Perl": (True, "Raku"), "NuGet Config": (False, "XML"),
    "Lauterbach PRACTICE Script": (True, "none: debugger script language"), "PRQL": (False, "SQL (data)"),
    "PSL Assertion": (True, "none: hardware property language"), "Pacman's makepkg": (True, "Shell"),
    "Pest": (True, "none: PEG grammar, like Yacc"), "Phix": (True, "none: general-purpose language"),
    "PO File": (False, "Gettext Catalog"), "Poke": (True, "none: GNU poke language"),
    "Polly": (True, "none: general-purpose language"), "Protocol Buffers": (False, "Protocol Buffer"),
    "QCL": (True, "none: quantum programming language"), "Rusty Object Notation": (False, "RON"),
    "RPM Specfile": (False, "RPM Spec"), "Rakefile": (True, "Ruby"), "Razor": (False, "HTML+Razor"),
    "Ruby HTML": (False, "HTML+ERB"), "SIL": (True, "none: general-purpose language"), "Scons": (True, "Python"),
    "Standard ML (SML)": (True, "Standard ML"), "Specman e": (True, "none: hardware verification language"),
    "Spice Netlist": (False, "none: circuit netlist data"), "Stratego/XT": (True, "none: transformation language"),
    "Tera": (False, "none: HTML template"), "Plain Text": (False, "Text"),
    "TTCN-3": (True, "none: test language"), "UMPL": (True, "none: general-purpose language"),
    "Uiua": (True, "none: array language"), "Unison": (True, "none: general-purpose language"),
    "Unreal Markdown": (False, "Markdown"), "Unreal Plugin": (False, "JSON"), "Unreal Project": (False, "JSON"),
    "Unreal Script": (True, "UnrealScript"), "Unreal Shader": (True, "HLSL"), "Unreal Shader Header": (True, "HLSL"),
    "Ur/Web": (True, "UrWeb"), "Ur/Web Project": (False, "none: project file data"), "VB6/VBA": (True, "VBA"),
    "Apache Velocity": (False, "Velocity Template Language"), "Verilog Args File": (False, "none: argument list"),
    "Virgil": (True, "none: general-purpose language"), "Visual Basic": (True, "Visual Basic .NET"),
    "Visual Studio Project": (False, "XML"), "Visual Studio Solution": (False, "Microsoft Visual Studio Solution"),
    "WebGPU Shader Language": (True, "WGSL"), "The WenYan Programming Language": (True, "none: general-purpose language"),
    "Wolfram": (True, "Wolfram Language"), "XSL": (True, "XSLT"), "XAML": (False, "XML"),
    "Xcode Config": (False, "none: build configuration data"), "ZenCode": (True, "ZenScript"),
    "ZoKrates": (True, "none: zero-knowledge proof language"), "Zsh": (True, "Shell"),
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(msg):
    print(f"[{now()}] {msg}", flush=True)


# ---------------------------------------------------------------- languages

def tokei_languages():
    out = subprocess.run([TOKEI, "-l"], capture_output=True, text=True, check=True).stdout.splitlines()
    head = next(l for l in out if "Language" in l and "Extensions" in l)
    a, b = head.index("Language"), head.index("Extensions")
    names = []
    for l in out:
        if not l.startswith("┃") or l is head or "━" in l:
            continue
        name = l[a:b].strip()
        if name and name != "Language":
            names.append(name)
    return names


def linguist():
    """Name -> (type, aliases) from languages.yml (a plain parse of the top-level keys)."""
    langs, cur, in_alias = {}, None, False
    for line in LANGUAGES_YML.read_text().splitlines():
        if not line or line.startswith("#") or line.startswith("---"):
            continue
        if not line.startswith(" ") and line.rstrip().endswith(":"):
            cur = line.rstrip()[:-1].strip().strip('"').strip("'")
            langs[cur] = {"type": None, "aliases": []}
            in_alias = False
        elif cur and line.startswith("  type:"):
            langs[cur]["type"] = line.split(":", 1)[1].strip()
            in_alias = False
        elif cur and line.startswith("  aliases:"):
            in_alias = True
        elif cur and in_alias and line.startswith("  - "):
            langs[cur]["aliases"].append(line[4:].strip().strip('"').strip("'"))
        elif line.startswith("  ") and not line.startswith("  - "):
            in_alias = False
    return langs


def cmd_langs():
    lg = linguist()
    lower = {k.lower(): k for k in lg}
    rows, unmapped = [], []
    for name in tokei_languages():
        if name.lower() in lower:
            k = lower[name.lower()]
            t = lg[k]["type"]
            rows.append((name, "yes" if t == "programming" else "no", "name", f"{k} ({t})"))
        elif name in HAND:
            prog, why = HAND[name]
            if why in lg:
                why = f"{why} ({lg[why]['type']})"
            rows.append((name, "yes" if prog else "no", "hand", why))
        else:
            unmapped.append(name)
            rows.append((name, "no", "unmapped", ""))
    with open(HERE / "languages.tsv", "w") as f:
        f.write("tokei_language\tprogramming\tdecided_by\tlinguist\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    c = collections.Counter((r[2], r[1]) for r in rows)
    log(f"{len(rows)} tokei languages: {dict(c)}")
    if unmapped:
        log("UNMAPPED (need a HAND entry): " + "; ".join(unmapped))
    unused = sorted(set(HAND) - {r[0] for r in rows})
    if unused:
        log("HAND entries that are not tokei names: " + "; ".join(unused))


def load_prog():
    m = {}
    for r in csv.DictReader(open(HERE / "languages.tsv"), delimiter="\t"):
        m[r["tokei_language"]] = r["programming"] == "yes"
    return m


# ---------------------------------------------------------------- inputs

def inputs():
    inp = {r["project"]: r for r in csv.DictReader(open(PINNED / "inputs.tsv"), delimiter="\t")}
    clone_url = {}
    for l in open(PINNED / "measure.jsonl"):
        d = json.loads(l)
        if d.get("clone_url"):
            clone_url[d["project"]] = d["clone_url"]
    prj = {r["project"]: r for r in csv.DictReader(open(PINNED / "projects.tsv"), delimiter="\t")}
    for p, r in inp.items():
        r["url"] = GITHUB_MIRROR.get(p) or clone_url.get(p) or r["repo_url"]
        r["lang_linguist"] = prj[p]["lang_linguist"]
        r["lang_with_ts"] = prj[p]["lang_with_ts"]
        r["largest_linguist"] = prj[p]["largest_linguist"]
        r["largest_with_ts"] = prj[p]["largest_with_ts"]
    return inp


def cmd_sample():
    inp = inputs()
    live = [r for r in inp.values() if r["project"] not in DROPPED]
    big = sorted(live, key=lambda r: -int(r["rows"] or 0))[:10]
    rng = random.Random(20261107)
    rest = [r for r in live if r not in big]
    rnd = rng.sample(sorted(rest, key=lambda r: r["project"]), 10)
    diff = [r for r in rest if r not in rnd and r["lang_linguist"] != r["lang_with_ts"]]
    dif = rng.sample(sorted(diff, key=lambda r: r["project"]), 10)
    with open(HERE / "sample30.tsv", "w") as f:
        f.write("project\tgroup\n")
        for g, rs in (("largest", big), ("random", rnd), ("differing", dif)):
            for r in rs:
                f.write(f"{r['project']}\t{g}\n")
    log(f"sample30.tsv: {len(big)} largest, {len(rnd)} random, {len(dif)} of {len(diff)} differing")


# ---------------------------------------------------------------- measure

HOST_LOCKS = collections.defaultdict(threading.Lock)


def env():
    home = WORK / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0", "GIT_ALLOW_PROTOCOL": "https:http:git", "GIT_LFS_SKIP_SMUDGE": "1",
            "RAYON_NUM_THREADS": "2", "TMPDIR": "/tmp", "LC_ALL": "C"}


def git(args, cwd, timeout=3 * 3600):
    return subprocess.run(["git", "-c", "pack.threads=2", "-c", "index.threads=2", "-c", "core.symlinks=true",
                           "-c", "checkout.workers=2"] + args, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=env())


def du(p):
    r = subprocess.run(["du", "-sb", str(p)], capture_output=True, text=True)
    try:
        return int(r.stdout.split()[0])
    except (ValueError, IndexError):
        return 0


def clean_err(s, tmp):
    return s.replace(str(tmp), "<tmp>").strip()[-300:]


def fetch(r, w):  # w: the bare git dir
    """Fetch the pinned commit into w (depth 1). Returns (method, error, extra)."""
    url, sha, host = r["url"], r["pinned_commit"], r["host"]
    p = r["project"]
    if p in DEEPEN:
        with HOST_LOCKS[host]:
            depth = 1
            while depth <= 4096:
                f = git(["fetch", "-q", "--no-tags", "--depth", str(depth), url, "HEAD"], cwd=w)
                if f.returncode:
                    return None, clean_err(f.stderr, w), {}
                if git(["cat-file", "-e", sha + "^{commit}"], cwd=w).returncode == 0:
                    return f"default branch fetched with depth {depth} (host refuses a fetch by SHA)", None, \
                        {"fetch_depth": depth}
                depth *= 2
            return None, "pinned commit not within depth 4096 of the default branch", {}
    err = None
    for attempt in range(4):
        with HOST_LOCKS[host] if host != "github.com" else contextlib.nullcontext():
            f = git(["fetch", "-q", "--no-tags", "--depth", "1", url, sha], cwd=w)
        if f.returncode == 0:
            m = "depth-1 fetch of the pinned commit"
            if p in GITHUB_MIRROR:
                m += " from the GitHub mirror (the host answers 403)"
            if attempt:
                m += f" (attempt {attempt + 1})"
            return m, None, {}
        err = clean_err(f.stderr, w)
        if "not found" in err.lower() and "repository" in err.lower():
            break
        time.sleep(30 * (attempt + 1) if ("429" in err or "500" in err or "502" in err or "503" in err) else 5)
    return None, err, {}


# Extensions tokei 14.0.0 never counts (tested: a file of each, lower and upper case, gave no lines). tokei picks
# a language by file name, by extension, or by a shebang only when there is no extension, so leaving these files
# out does not change any count. It only saves disk writes.
NEVER = set("""png jpg jpeg gif bmp ico icns tif tiff webp psd xcf mp3 ogg wav flac aac m4a mp4 mov avi mkv webm ttf
otf woff woff2 eot jar war zip gz tgz bz2 xz 7z rar zst pdf exe dll so dylib a o obj lib class pyc pyo bin dat db
sqlite sqlite3 npy npz pkl h5 onnx pt pth ckpt safetensors parquet iso img dmg deb rpm apk aar nupkg whl pcap blend
fbx glb stl dds ktx tga exr wasm swf mid midi sf2 msi cab jfif heic avif opus wma flv wmv 3gp mpg mpeg m4v caf aiff
aif snd""".split())


def ext_of(name):
    """The extension as Rust's Path::extension gives it (None for '.bashrc'), lower case."""
    base = name.rsplit("/", 1)[-1]
    i = base.rfind(".")
    return None if i <= 0 else base[i + 1:].lower()


def extract(gitdir, commit, w):
    """Write the blobs of commit into w, the way a checkout would, minus the files that cannot count:
    vendored paths (the selection's rule), symbolic links and submodules (tokei does not follow links), files with
    an extension in NEVER, and Qt translation .ts files. Returns counts only (no names)."""
    ls = subprocess.run(["git", "--git-dir", str(gitdir), "ls-tree", "-r", "-l", "-z", "--full-tree", commit],
                        capture_output=True, timeout=3 * 3600, env=env())
    if ls.returncode:
        raise RuntimeError("ls-tree failed: " + ls.stderr.decode(errors="replace")[-200:])
    c = collections.Counter()
    want = []
    for ent in ls.stdout.split(b"\0"):
        if not ent:
            continue
        meta, path = ent.split(b"\t", 1)
        mode, typ, oid, size = meta.split()
        path = path.decode("utf-8", "surrogateescape")
        c["entries"] += 1
        if typ != b"blob" or mode not in (b"100644", b"100755"):
            c["links_or_submodules"] += 1
            continue
        parts = path.split("/")
        if any(p in ("", ".", "..") or p.lower() == ".git" for p in parts):
            c["unsafe_paths"] += 1
            continue
        sz = int(size)
        c["tree_bytes"] += sz
        if VENDOR.search(path):
            c["vendored_files"] += 1
            c["vendored_bytes"] += sz
            continue
        if ext_of(path) in NEVER:
            c["never_counted_files"] += 1
            c["never_counted_bytes"] += sz
            continue
        want.append((oid, path, sz))
    made = set()
    proc = subprocess.Popen(["git", "--git-dir", str(gitdir), "cat-file", "--batch"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, env=env())

    def feed():
        try:
            for oid, _, _ in want:
                proc.stdin.write(oid + b"\n")
        finally:
            proc.stdin.close()

    th = threading.Thread(target=feed, daemon=True)
    th.start()
    out = proc.stdout
    for oid, path, sz in want:
        head = out.readline().split()
        if len(head) != 3 or head[1] != b"blob":
            raise RuntimeError(f"cat-file answered {head[:2]!r}")
        n = int(head[2])
        data = out.read(n)
        out.read(1)
        if path.lower().endswith(".ts"):
            h = data[:8192]
            h = h[3:] if h.startswith(b"\xef\xbb\xbf") else h
            if h.lstrip().startswith(QT_TS):
                c["qt_ts_removed"] += 1
                continue
            if b"\x00" in data[:8192]:
                c["ts_binary_kept"] += 1
        full = os.path.join(w, path)
        dn = os.path.dirname(full)
        if dn not in made:
            os.makedirs(dn, exist_ok=True)
            made.add(dn)
        with open(full, "wb") as fh:
            fh.write(data)
        c["written_files"] += 1
        c["written_bytes"] += n
    th.join()
    proc.wait()
    return dict(c)


def summ(stats):
    return stats["code"] + sum(summ(b) for b in stats.get("blobs", {}).values())


def run_tokei(w, cwd):
    t = subprocess.run(["nice", "-n", "5", TOKEI, "--hidden", "--no-ignore", "-o", "json", str(w)], cwd=cwd,
                       capture_output=True, timeout=3 * 3600, env=env())
    if t.returncode:
        raise RuntimeError("tokei failed: " + t.stderr.decode(errors="replace")[-300:])
    d = json.loads(t.stdout)
    total = d.pop("Total", None)
    code, inaccurate = {}, False
    for lang, v in d.items():
        c = v["code"] + sum(summ(rep["stats"]) for reps in v.get("children", {}).values() for rep in reps)
        if c:
            code[lang] = code.get(lang, 0) + c
        inaccurate |= bool(v.get("inaccurate"))
    tot = total["code"] if total else None
    return code, tot, inaccurate


def classify(code, prog):
    merged = collections.Counter()
    for lang, c in code.items():
        merged[MERGE.get(lang, lang)] += c
    progc = {k: v for k, v in merged.items() if prog.get(k, False)}
    nonprog = sum(v for k, v in merged.items() if not prog.get(k, False))
    unknown = sorted(k for k in merged if k not in prog)
    allp = sum(progc.values())
    if allp:
        top = max(progc.values())
        tied = sorted(k for k, v in progc.items() if v == top)
        largest = tied[0]
        share = sum(progc.get(t, 0) for t in TARGET) / allp
        rule = largest in TARGET
    else:
        tied, largest, share, rule = [], None, None, False
    return dict(code_prog=dict(sorted(progc.items(), key=lambda kv: -kv[1])), code_nonprog_total=nonprog,
                code_prog_total=allp, largest=largest, largest_tied=tied if len(tied) > 1 else [],
                target_share=round(share, 6) if share is not None else None, rule=rule,
                unknown_langs=unknown)


def measure_one(r, prog, inflight):
    base = dict(project=r["project"], layer=r["layer"], host=r["host"], has_file=r["has_file"], rows=r["rows"],
                pinned_commit=r["pinned_commit"])
    if r["project"] in DROPPED:
        return dict(base, status="dropped: repository gone", final=True, measured_at=now())
    tmp = Path(tempfile.mkdtemp(dir=WORK, prefix="m."))
    g, w = tmp / "g", tmp / "w"
    t0 = time.time()
    try:
        i = git(["init", "-q", "--bare", str(g)], cwd=tmp)
        if i.returncode:
            return dict(base, status="git init failed", error=clean_err(i.stderr, tmp), final=False)
        method, err, extra = fetch(r, g)
        t1 = time.time()
        if not method:
            return dict(base, status="fetch failed", error=err, fetch_s=round(t1 - t0, 1), final=False,
                        measured_at=now())
        pack = du(g)
        inflight[r["project"]] = pack
        commit = r["pinned_commit"] if r["project"] in DEEPEN else \
            git(["rev-parse", "FETCH_HEAD"], cwd=g).stdout.strip()
        w.mkdir()
        st = extract(g, commit, w)
        inflight[r["project"]] = pack + st.get("written_bytes", 0)
        shutil.rmtree(g)
        t2 = time.time()
        code, tot, inacc = run_tokei(w, tmp)
        t3 = time.time()
        cl = classify(code, prog)
        check = sum(code.values())
        return dict(base, status="ok", final=True, method=method, head_ok=commit == r["pinned_commit"], **extra,
                    fetch_bytes=pack, peak_bytes=pack + st.get("written_bytes", 0), fetch_s=round(t1 - t0, 1),
                    extract_s=round(t2 - t1, 1), tokei_s=round(t3 - t2, 1), extract=st,
                    qt_ts_removed=st.get("qt_ts_removed", 0), ts_binary_kept=st.get("ts_binary_kept", 0), **cl,
                    tokei_total_code=tot, total_check=(tot == check), tokei_inaccurate=inacc, measured_at=now())
    except subprocess.TimeoutExpired as e:
        return dict(base, status="timeout", error=str(e.cmd[:6]), final=False, measured_at=now())
    except Exception as e:  # noqa: BLE001  (record and go on; a restart retries)
        return dict(base, status="error", error=clean_err(repr(e), tmp), final=False, measured_at=now())
    finally:
        inflight.pop(r["project"], None)
        shutil.rmtree(tmp, ignore_errors=True)


def done_set(path=OUT):
    last = {}
    if path.exists():
        for l in open(path):
            try:
                d = json.loads(l)
            except json.JSONDecodeError:
                continue
            last[d["project"]] = d
    return last


def cmd_run(a):
    prog = load_prog()
    inp = inputs()
    if a.sample:
        names = [r["project"] for r in csv.DictReader(open(HERE / "sample30.tsv"), delimiter="\t")]
    else:
        size = {}
        for l in open(PINNED / "measure.jsonl"):
            d = json.loads(l)
            size[d["project"]] = (d.get("measure") or {}).get("total_bytes") or 0
        names = sorted(inp, key=lambda p: (-size.get(p, 0), p))  # largest tree first: the long ones start early
    out = HERE / a.out
    last = done_set(out)
    todo = [p for p in names if not (p in last and last[p].get("final"))]
    if a.limit:
        todo = todo[:a.limit]
    log(f"{len(names)} projects, {len(names) - len(todo)} already final, {len(todo)} to do, {a.workers} workers")
    WORK.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()
    stop = threading.Event()
    peak = {"bytes": 0, "at": None}
    inflight = {}

    def sampler():
        while not stop.wait(a.sample_every):
            b = sum(inflight.values())
            if b > peak["bytes"]:
                peak.update(bytes=b, at=now())

    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    t0 = time.time()
    n = [0]

    def job(p):
        if (WORK / a.stop_file).exists():
            return
        res = measure_one(inp[p], prog, inflight)
        with lock:
            with open(out, "a") as f:
                f.write(json.dumps(res) + "\n")
            n[0] += 1
            log(f"{n[0]}/{len(todo)} {p} {res['status']} fetch={res.get('fetch_bytes')} "
                f"t={res.get('fetch_s')}/{res.get('extract_s')}/{res.get('tokei_s')} largest={res.get('largest')}"
                + (f" err={res.get('error')}" if res.get("error") else ""))

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(job, todo))
    stop.set()
    wall = time.time() - t0
    stats = dict(ended=now(), wall_s=round(wall, 1), workers=a.workers, done=n[0], peak_disk_bytes=peak["bytes"],
                 peak_at=peak["at"])
    with open(HERE / ("run-stats.sample.jsonl" if a.sample else "run-stats.all.jsonl"), "a") as f:
        stats["out"] = a.out
        f.write(json.dumps(stats) + "\n")
    log(f"end: {stats}")


# ---------------------------------------------------------------- report

def manifest():
    return {r["project"]: r for r in csv.DictReader(open(MANIFEST), delimiter="\t")}


def cmd_report(a):
    inp = inputs()
    last = done_set()
    man = manifest()
    cols = ["project", "layer", "has_file", "rows", "pinned_commit", "status", "largest_tokei", "target_share",
            "rule_tokei", "qt_ts_removed", "method", "lang_linguist", "lang_with_ts", "largest_linguist",
            "largest_with_ts"]
    with open(HERE / "projects.tsv", "w") as f:
        f.write("\t".join(cols) + "\n")
        for p in sorted(inp):
            r, d = inp[p], last.get(p, {})
            ok = d.get("status") == "ok"
            row = dict(project=p, layer=r["layer"], has_file=r["has_file"], rows=r["rows"],
                       pinned_commit=r["pinned_commit"], status=d.get("status", "not measured yet"),
                       largest_tokei=(d.get("largest") or "") if ok else "",
                       target_share="" if not ok or d.get("target_share") is None else f"{d['target_share']:.6f}",
                       rule_tokei=("true" if d.get("rule") else "false") if ok else "",
                       qt_ts_removed=str(d.get("qt_ts_removed", "")) if ok else "", method=d.get("method", ""),
                       lang_linguist=r["lang_linguist"], lang_with_ts=r["lang_with_ts"],
                       largest_linguist=r["largest_linguist"], largest_with_ts=r["largest_with_ts"])
            f.write("\t".join(str(row[c]) for c in cols) + "\n")
    log("wrote projects.tsv")
    summary(inp, last, man)


def summary(inp, last, man):
    def kept(p):
        d = last.get(p, {})
        return d.get("status") == "ok" and d.get("rule")

    measured = [p for p in inp if last.get(p, {}).get("status") == "ok"]
    s = {"input_rows": len(inp), "measured": len(measured),
         "status": dict(collections.Counter(last.get(p, {}).get("status", "not measured yet") for p in inp))}
    for scope, ps in (("all input rows", list(inp)), ("projects with a file", [p for p in inp if inp[p]["has_file"] == "yes"])):
        for layer in ("v1", "x1k", "all"):
            q = [p for p in ps if layer == "all" or inp[p]["layer"] == layer]
            k = [p for p in q if kept(p)]
            m = [p for p in q if last.get(p, {}).get("status") == "ok"]
            s[f"{scope} / {layer}"] = dict(
                rows=len(q), measured=len(m), kept=len(k), dropped_measured=len(m) - len(k),
                not_measured=len(q) - len(m),
                token_rows_kept=sum(int(inp[p]["rows"] or 0) for p in k),
                token_rows_measured=sum(int(inp[p]["rows"] or 0) for p in m),
                bytes_kept=sum(int(man[p]["bytes"]) for p in k if p in man),
                bytes_measured=sum(int(man[p]["bytes"]) for p in m if p in man))
    drop = collections.Counter(last[p].get("largest") or "(no programming code)" for p in measured if not kept(p))
    s["dropped_by_largest"] = drop.most_common()
    keep = collections.Counter(last[p]["largest"] for p in measured if kept(p))
    s["kept_by_largest"] = keep.most_common()
    diff = [p for p in measured if inp[p]["lang_linguist"] != inp[p]["lang_with_ts"]]
    s["differing_400"] = dict(total=sum(1 for p in inp if inp[p]["lang_linguist"] != inp[p]["lang_with_ts"]),
                              measured=len(diff), kept=sum(1 for p in diff if kept(p)))
    for var in ("linguist", "with_ts"):
        a = [p for p in measured if (inp[p][f"lang_{var}"] == "true") != bool(kept(p))]
        tk = sorted([p for p in a if kept(p)])
        bk = sorted([p for p in a if not kept(p)])
        rng = random.Random(7)
        s[f"differs_from_{var}"] = dict(
            total=len(a), tokei_keeps_bytes_drop=len(tk), tokei_drops_bytes_keep=len(bk),
            examples=[dict(project=p, largest_bytes=inp[p][f"largest_{var}"], largest_tokei=last[p].get("largest"),
                           target_share_tokei=last[p].get("target_share"))
                      for p in sorted(rng.sample(a, min(10, len(a))))])
    s["qt_ts_removed_total"] = sum(last[p].get("qt_ts_removed", 0) for p in measured)
    s["projects_with_qt_ts_removed"] = sum(1 for p in measured if last[p].get("qt_ts_removed"))
    s["ts_binary_kept_total"] = sum(last[p].get("ts_binary_kept", 0) for p in measured)
    s["projects_with_binary_ts"] = sum(1 for p in measured if last[p].get("ts_binary_kept"))
    s["largest_ties"] = sorted(p for p in measured if last[p].get("largest_tied"))
    s["total_check_failed"] = sorted(p for p in measured if not last[p].get("total_check"))
    s["head_mismatch"] = sorted(p for p in measured if not last[p].get("head_ok"))
    s["no_programming_code"] = sorted(p for p in measured if not last[p].get("largest"))
    s["not_measured"] = {p: dict(status=last.get(p, {}).get("status", "not measured yet"),
                                 error=last.get(p, {}).get("error")) for p in inp if p not in measured}
    s["methods"] = dict(collections.Counter(last[p].get("method") for p in measured))
    s["fetch_bytes_total"] = sum(last[p].get("fetch_bytes", 0) for p in measured)
    tot = collections.Counter()
    for p in measured:
        tot.update(last[p]["code_prog"])
    s["prog_code_by_language_top20"] = tot.most_common(20)
    with open(HERE / "summary.json", "w") as f:
        json.dump(s, f, indent=1)
    log("wrote summary.json")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("langs")
    sub.add_parser("sample")
    r = sub.add_parser("run")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", action="store_true")
    g.add_argument("--all", action="store_true")
    r.add_argument("--workers", type=int, default=8)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--sample-every", type=int, default=15)
    r.add_argument("--out", default="measure.jsonl")
    r.add_argument("--stop-file", default="STOP")
    sub.add_parser("report")
    a = ap.parse_args()
    {"langs": lambda: cmd_langs(), "sample": lambda: cmd_sample(), "run": lambda: cmd_run(a),
     "report": lambda: cmd_report(a)}[a.cmd]()


if __name__ == "__main__":
    main()
