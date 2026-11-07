#!/usr/bin/env python3
"""Fix 1 (license outside GitHub): fetch the ROOT license files of each NOASSERTION project that is not on
GitHub at its pinned run_commit, scan them with licensee (98 and 80), askalono and ScanCode, and write one
JSON line per project. The method is the one of ../32_fetch_license_files.py (other hosts), run in parallel.

Usage (inside nix-shell ../shell.nix):
  nice -n 10 python3 -I p1_scan_outside_github.py INPUT.tsv OUT.jsonl WORKROOT [WORKERS]
INPUT.tsv columns: project, display, host, clone_url, run_commit.

Fetch: a depth-1 fetch of the one pinned commit (no history), with no blobs where the host allows it; else
the one commit with its blobs. When the host refuses a fetch by SHA, a ref whose tip is the pinned commit
(git ls-remote) is fetched at depth 1. One fetch at a time per host. Each project gets its own new empty
folder under WORKROOT, deleted after the scan. No copyright line or file text is written, only file names
and scanner ids.
"""
import collections
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request

LICENSE_RE = re.compile(r"(?i)^(licen[cs]e|copying|copyright|unlicense|notice|legal|mit-license|"
                        r"gpl|lgpl|apache|bsd|mpl|eula|patents)([-._ ].*)?$")
FOLDER_RE = re.compile(r"(?i)^(licen[cs]es?|legal)$")
PACKAGE = {"Cargo.toml", "package.json", "pom.xml", "setup.cfg", "pyproject.toml", "DESCRIPTION", "meson.build"}
MAX_FILES = 12
HOST_LOCKS = collections.defaultdict(threading.Lock)
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="/bin/false")
# the host answers 403 or refuses a fetch by SHA: fetch the same commit from a GitHub mirror (same SHA, same tree)
MIRROR = {"git.libreoffice.org__libvisio": "https://github.com/LibreOffice/libvisio.git",
          "git.libreoffice.org__libetonyek": "https://github.com/LibreOffice/libetonyek.git",
          "git.busybox.net__busybox": "https://github.com/mirror/busybox.git"}
NO_FILTER = set()  # the earlier Savannah hang was port 443 of git.savannah.gnu.org, not the filter
GITWEB = {"git.savannah.gnu.org": "https://git.savannah.gnu.org/gitweb/"}


def fetch_url(row):
    """git.savannah.gnu.org: port 443 of the main host does not answer this machine, and git:// refuses a
    fetch by SHA; the host's smart-HTTP name https.git.savannah.gnu.org serves the same repositories."""
    if row["project"] in MIRROR:
        return MIRROR[row["project"]]
    if row["host"] == "git.savannah.gnu.org":
        name = row["clone_url"].rstrip("/").split("/")[-1]
        return "https://https.git.savannah.gnu.org/git/" + (name if name.endswith(".git") else name + ".git")
    return row["clone_url"]


class Refused(RuntimeError):
    pass


def run(cmd, cwd=None, timeout=600):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, errors="replace", timeout=timeout, env=ENV)


def pick(entries):
    files = [p for p, t in entries if t == "blob" and LICENSE_RE.match(p)]
    folders = [p for p, t in entries if t == "tree" and FOLDER_RE.match(p)]
    pkgs = [p for p, t in entries if t == "blob" and p in PACKAGE]
    return files, folders, pkgs


def fetch(g, row):
    sha, url = row["run_commit"], fetch_url(row)
    base = ["git", "--git-dir", g, "fetch", "-q", "--no-tags", "--depth", "1"]
    if row["host"] not in NO_FILTER:
        try:
            f = run(base + ["--filter=blob:none", "origin", sha], timeout=300)
            if f.returncode == 0:
                return "depth-1 fetch of the pinned commit, no blobs"
        except subprocess.TimeoutExpired:
            pass
    run(["git", "--git-dir", g, "config", "--unset", "remote.origin.promisor"])
    run(["git", "--git-dir", g, "config", "--unset", "remote.origin.partialclonefilter"])
    f = run(base + ["origin", sha], timeout=3600)
    if f.returncode == 0:
        return "depth-1 fetch of the pinned commit"
    err = f.stderr.strip()
    if "unadvertised" in err or "not our ref" in err:
        ls = run(["git", "ls-remote", url], timeout=600)
        refs = [ln.split("\t")[1] for ln in ls.stdout.splitlines() if ln.startswith(sha + "\t")]
        for ref in refs[:1]:
            f = run(base + ["origin", ref], timeout=3600)
            if f.returncode == 0 and run(["git", "--git-dir", g, "cat-file", "-e", sha]).returncode == 0:
                return f"depth-1 fetch of the ref {ref} (its tip is the pinned commit)"
        if not refs:
            raise Refused("fetch: the host refuses a fetch by SHA and no ref has the pinned commit as tip")
    raise RuntimeError("fetch: " + err[-200:])


def other(row, folder):
    g = os.path.join(folder, "git")
    os.makedirs(g)
    run(["git", "init", "-q", "--bare", g])
    run(["git", "--git-dir", g, "remote", "add", "origin", fetch_url(row)])
    run(["git", "--git-dir", g, "config", "remote.origin.promisor", "true"])
    run(["git", "--git-dir", g, "config", "remote.origin.partialclonefilter", "blob:none"])
    with HOST_LOCKS[row["host"]]:
        try:
            method = fetch(g, row)
        except Refused:
            if row["host"] not in GITWEB:
                raise
            shutil.rmtree(g, ignore_errors=True)
            return gitweb(row, folder)
        if fetch_url(row) != row["clone_url"]:
            method += " from " + fetch_url(row)
        sha = row["run_commit"]
        ls = run(["git", "--git-dir", g, "ls-tree", sha])
        if ls.returncode:
            raise RuntimeError("ls-tree: " + ls.stderr.strip()[-200:])
        entries = []
        for line in ls.stdout.splitlines():
            meta, p = line.split("\t", 1)
            entries.append((p, meta.split()[1]))
        files, folders, pkgs = pick(entries)
        for d in folders[:1]:
            sub = run(["git", "--git-dir", g, "ls-tree", f"{sha}:{d}"])
            for line in sub.stdout.splitlines():
                meta, p = line.split("\t", 1)
                if meta.split()[1] == "blob":
                    files.append(d + "/" + p)
        got = []
        for p in (files + pkgs)[:MAX_FILES]:
            c = subprocess.run(["git", "--git-dir", g, "cat-file", "blob", f"{sha}:{p}"], capture_output=True,
                               timeout=600, env=ENV)
            if c.returncode == 0:
                with open(os.path.join(folder, p.replace("/", "__")), "wb") as fh:
                    fh.write(c.stdout[:2_000_000])
                got.append(p)
    shutil.rmtree(g, ignore_errors=True)
    return method, entries, got


def web_get(url, tries=4):
    err = None
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                return resp.read(2_000_000)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(10 * (k + 1))
    raise RuntimeError(f"web: {err}"[:200])


def gitweb_tree(base, repo, sha, sub=None):
    q = f"p={repo};a=tree;hb={sha}" + (f";f={urllib.parse.quote(sub)}" if sub else "")
    html = web_get(base + "?" + q).decode("utf-8", "replace")
    out = {}
    for kind, name in re.findall(r'href="[^"]*;a=(blob|tree);f=([^;"]+);h=[0-9a-f]+;hb=' + sha, html):
        name = urllib.parse.unquote(name)
        if sub:
            name = name.split("/")[-1]
        out[name] = "blob" if kind == "blob" else "tree"
    return list(out.items())


def gitweb(row, folder):
    """The host refuses a fetch by SHA: read the root tree and the license blobs of the pinned commit
    from its gitweb (a=tree / a=blob_plain with hb=<commit>). No history is read."""
    base = GITWEB[row["host"]]
    repo = row["clone_url"].rstrip("/").split("/")[-1]
    repo = repo if repo.endswith(".git") else repo + ".git"
    sha = row["run_commit"]
    with HOST_LOCKS[row["host"]]:
        entries = gitweb_tree(base, repo, sha)
        if not entries:
            raise RuntimeError("gitweb: empty root tree")
        files, folders, pkgs = pick(entries)
        for d in folders[:1]:
            files += [d + "/" + n for n, t in gitweb_tree(base, repo, sha, d) if t == "blob"]
        got = []
        for p in (files + pkgs)[:MAX_FILES]:
            data = web_get(base + "?" + f"p={repo};a=blob_plain;f={urllib.parse.quote(p)};hb={sha}")
            with open(os.path.join(folder, p.replace("/", "__")), "wb") as fh:
                fh.write(data)
            got.append(p)
    return "gitweb of the host at the pinned commit (the host refuses a fetch by SHA)", entries, got


def askalono(folder, names):
    out = {}
    for n in names:
        p = os.path.join(folder, n.replace("/", "__"))
        r = run(["askalono", "--format", "json", "identify", "--optimize", p], timeout=120)
        try:
            j = json.loads(r.stdout.strip().splitlines()[-1])
            res = j.get("result") or {}
            lic = (res.get("license") or {}).get("name")
            score = res.get("score")
            out[n] = {"license": lic, "score": round(score, 3) if score is not None else None}
        except Exception as e:  # noqa: BLE001
            out[n] = {"error": str(e)[:100]}
    return out


def licensee(folder, confidence):
    r = run(["licensee", "detect", folder, "--json", "--confidence", str(confidence)], timeout=300)
    try:
        j = json.loads(r.stdout)
    except Exception:  # noqa: BLE001
        return {"error": (r.stderr or r.stdout)[-150:]}
    return {"licenses": [x.get("spdx_id") for x in j.get("licenses", [])],
            "files": [{"file": f.get("filename"), "spdx": (f.get("matched_license") or "")}
                      for f in j.get("matched_files", [])]}


def scancode(folder, names):
    if not names:
        return {}
    outj = folder + ".scancode.json"
    r = run(["scancode", "--license", "--quiet", "-n", "2", "--json", outj, folder], timeout=1800)
    try:
        with open(outj, encoding="utf-8") as fh:
            j = json.load(fh)
    except Exception:  # noqa: BLE001
        return {"error": (r.stderr or r.stdout)[-150:]}
    finally:
        if os.path.exists(outj):
            os.remove(outj)
    res = {}
    for f in j.get("files", []):
        if f.get("type") == "file":
            res[os.path.basename(f["path"])] = f.get("detected_license_expression_spdx")
    return res


def one(i, row, root):
    folder = tempfile.mkdtemp(prefix=f"lic{i:03d}-", dir=root)
    rec = {"n": i, "project": row["project"], "display": row["display"], "host": row["host"],
           "run_commit": row["run_commit"]}
    t0 = time.time()
    try:
        method, entries, got = other(row, folder)
        rec["fetch"] = method
        rec["root_entries"] = len(entries)
        rec["license_like_root"] = [p for p, t in entries if LICENSE_RE.match(p) or FOLDER_RE.match(p)]
        rec["files"] = got
        lic_files = [x for x in got if os.path.basename(x) not in PACKAGE]
        rec["askalono"] = askalono(folder, lic_files)
        rec["licensee_98"] = licensee(folder, 98)
        rec["licensee_80"] = licensee(folder, 80)
        rec["scancode"] = scancode(folder, lic_files)
    except Exception as e:  # noqa: BLE001
        rec["error"] = str(e)[:300]
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def main():
    inp, outp, root = sys.argv[1], sys.argv[2], sys.argv[3]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 6
    with open(inp, encoding="utf-8") as fh:
        head = fh.readline().rstrip("\n").split("\t")
        rows = [dict(zip(head, ln.rstrip("\n").split("\t"))) for ln in fh if ln.strip()]
    done = set()
    if os.path.exists(outp):
        done = {json.loads(ln)["project"] for ln in open(outp, encoding="utf-8") if ln.strip()}
    todo = [(i, r) for i, r in enumerate(rows, 1) if r["project"] not in done]
    # interleave hosts so that the per-host lock does not idle the workers
    by = collections.defaultdict(list)
    for i, r in todo:
        by[r["host"]].append((i, r))
    order = []
    while any(by.values()):
        for h in sorted(by, key=lambda h: -len(by[h])):
            if by[h]:
                order.append(by[h].pop(0))
    os.makedirs(root, exist_ok=True)
    t0 = time.time()
    print(f"{len(rows)} projects, {len(done)} done, {len(order)} to do, {workers} workers", flush=True)
    with open(outp, "a", encoding="utf-8") as out, cf.ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(one, i, r, root) for i, r in order]
        for k, fu in enumerate(cf.as_completed(futs), 1):
            rec = fu.result()
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print(f"{k}/{len(order)} {rec['host']} files={len(rec.get('files', []))} t={rec['seconds']} "
                  f"{'ERR ' + rec['error'][:100] if 'error' in rec else ''}", flush=True)
    print(f"end: wall_s={round(time.time() - t0)}", flush=True)


if __name__ == "__main__":
    main()
