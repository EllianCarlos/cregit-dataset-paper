"""The items of the license audit page: one per project of work/values/sample100.tsv.

  python3 -I 80_audit_items.py      -> work/audit/items.json

For each project: the links to the repository and to each evidence file at the pinned commit (raw file
URLs where the host has them), a short excerpt of the matched lines from the stored key files, and the
proposed value. Copyright lines (with the lines that follow them up to a blank line), lines with an e-mail
address and author lines are replaced by "[line omitted]": the page shows no person data.
"""
import csv
import gzip
import json
import os
import re
import tarfile
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = f"{HERE}/work"
COPYRIGHT_LINE = re.compile(r"(?i)^[\s#/*;!%'\"-]*(copyright\b|\(c\)|©|portions\s+copyright)")
PERSON = re.compile(r"(?i)@|\bauthors?\s*:|\bwritten by\b|\bmaintained by\b|\bcontributors?\s*:|\(c\)\s*\d|©|"
                    r"copyright\s+(\(c\)\s*)?\d|\b[a-z0-9._%+-]+\s*(\[at\]|\(at\))\s*[a-z0-9.-]+")
EXCERPT_LINES = 12
GITLAB_HOSTS = ("gitlab.", "invent.kde.org", "salsa.debian.org", "framagit.org", "code.videolan.org",
                "foss.heptapod.net", "git.pleroma.social", "dev.gajim.org", "gitlab")
GITEA_HOSTS = ("codeberg.org", "opendev.org", "gitea.", "git.osgeo.org")


def repo_links(clone_url, commit):
    """(tree URL at the commit, function path -> (view URL, raw URL))."""
    u = re.sub(r"\.git/?$", "", clone_url.strip())
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)$", u)
    if m:
        o, r = m.groups()
        return (f"https://github.com/{o}/{r}/tree/{commit}",
                lambda p: (f"https://github.com/{o}/{r}/blob/{commit}/{quote(p)}",
                           f"https://raw.githubusercontent.com/{o}/{r}/{commit}/{quote(p)}"))
    m = re.match(r"https://([^/]+)/(.+)$", u)
    if m and any(h in m.group(1) for h in GITLAB_HOSTS):
        base = u
        return (f"{base}/-/tree/{commit}",
                lambda p: (f"{base}/-/blob/{commit}/{quote(p)}", f"{base}/-/raw/{commit}/{quote(p)}"))
    if m and any(h in m.group(1) for h in GITEA_HOSTS):
        base = u
        return (f"{base}/src/commit/{commit}",
                lambda p: (f"{base}/src/commit/{commit}/{quote(p)}", f"{base}/raw/commit/{commit}/{quote(p)}"))
    m = re.match(r"(?:https|git)://git\.savannah\.(?:gnu|nongnu)\.org/(?:git/)?(.+)$", clone_url.strip())
    if m:
        repo = m.group(1) if m.group(1).endswith(".git") else m.group(1) + ".git"
        base = f"https://git.savannah.gnu.org/cgit/{repo}"
        return (f"{base}/tree/?id={commit}",
                lambda p: (f"{base}/tree/{quote(p)}?id={commit}", f"{base}/plain/{quote(p)}?id={commit}"))
    return (clone_url, lambda p: (None, None))


def stage_text(pdir, path):
    try:
        with tarfile.open(f"{pdir}/stage.tar.gz", "r:gz") as t:
            f = t.extractfile(path)
            return f.read(400_000).decode("utf-8", errors="replace") if f else None
    except (KeyError, OSError, tarfile.TarError):
        return None


def scan_lines(scan, path):
    out = []
    for f in scan.get("files", []):
        if f.get("path") == path:
            for det in f.get("license_detections") or []:
                for m in det.get("matches") or []:
                    out.append((int(m.get("start_line") or 0), int(m.get("end_line") or 0),
                                m.get("license_expression_spdx"), float(m.get("score") or 0)))
    return sorted(out)


def excerpt(text, spans, kind):
    if text is None:
        return "(file text not stored)"
    lines = text.splitlines()
    if not spans:
        pick = [i for i, l in enumerate(lines) if re.search(r"(?i)licen[cs]|spdx", l)][:EXCERPT_LINES]
        rng = pick or list(range(min(EXCERPT_LINES, len(lines))))
    else:
        pick = [spans[0]]
        big = max(spans, key=lambda x: x[1] - x[0])
        if big != spans[0]:
            pick.append(big)
        rng = []
        for lo, hi in pick:
            hi = min(hi, lo + (EXCERPT_LINES - 1 if kind == "text" else 6))
            rng += [i for i in range(max(lo - 3, 1) - 1, min(hi + 2, len(lines))) if i not in rng]
        rng = sorted(rng)[:2 * EXCERPT_LINES + 6]
    hide, in_block = set(), False
    for i, line in enumerate(lines):
        if COPYRIGHT_LINE.search(line) or PERSON.search(line):
            hide.add(i)
            in_block = True
        elif in_block and line.strip():
            hide.add(i)   # the names that follow a copyright line
        else:
            in_block = False
    out, last = [], None
    for i in rng:
        if last is not None and i != last + 1:
            out.append("...")
        line = lines[i] if i < len(lines) else ""
        out.append(f"{i + 1:>4}  " + ("[line omitted]" if i in hide else line[:220]))
        last = i
    return "\n".join(out)


def main():
    os.makedirs(f"{WORK}/audit", exist_ok=True)
    with open(f"{WORK}/values/sample100.tsv", newline="") as f:
        sample = list(csv.DictReader(f, delimiter="\t"))
    items = []
    for s in sample:
        p = s["project"]
        pdir = f"{WORK}/out/projects/{p}"
        dec = json.load(open(f"{pdir}/result.json"))["decision"]
        with gzip.open(f"{pdir}/scancode.json.gz", "rt") as f:
            scan = json.load(f)
        tree, links = repo_links(s["clone_url"], s["commit"])
        files, seen = [], set()
        for e in dec.get("evidence", []):
            path = e.get("path")
            if not path or path in seen:
                continue
            seen.add(path)
            spans = [(a, b) for a, b, _, sc in scan_lines(scan, path) if sc >= 50]
            if e.get("matches"):
                spans = sorted(tuple(m["lines"]) for m in e["matches"] if m.get("lines")) or spans
            kind = "text" if e.get("term") and e.get("role") in ("primary", "alt", "named", "secondary", "reuse",
                                                                 "sub") else "notice"
            view, raw = links(path)
            files.append({"path": path, "role": e.get("role"), "says": e.get("term") or e.get("expression") or "",
                          "use": e.get("use") or "license text", "view": view, "raw": raw,
                          "excerpt": excerpt(stage_text(pdir, path), spans, kind)})
        items.append({"project": p, "commit": s["commit"], "repo": tree, "value": s["new"],
                      "confidence": s["confidence"], "evidence_kind": s["evidence_kind"],
                      "version_choice": s["version_choice"], "stratum": s["stratum"],
                      "stratum_size": int(s["stratum_size"]), "stratum_n": int(s["stratum_n"]),
                      "other": dec.get("other_licenses", []), "files": files})
    with open(f"{WORK}/audit/items.json", "w") as f:
        json.dump(items, f, indent=1)
    print(f"wrote {len(items)} items to {WORK}/audit/items.json; no raw link for "
          f"{sum(1 for i in items for x in i['files'] if not x['raw'])} files")


if __name__ == "__main__":
    main()
