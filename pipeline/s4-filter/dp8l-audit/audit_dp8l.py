#!/usr/bin/env python3
"""DP8L audit: do the rows that S4 removed as "no license file" have one?

The S4 funnel (../funnel.py) removed 2,898 rows at DP8L (28,161 -> 25,263):
2,897 with the reason "no license file" and 1 with "clone facts: fetch-failed".
For GitHub rows the funnel used the pool column `license` (GraphQL
`licenseInfo.spdxId`); it is empty when GitHub detects no license. For other
hosts it used the top-level names from `git ls-tree --name-only` with the name
rule NAME_RULE below (../../s3-measure/clone_facts.py).

This script applies the same name rule to the GitHub rows, at the snapshot
commit (pool.csv head_oid). It only reads from the GitHub REST API, one call at
a time, and keeps each response in raw/:

  fetch   1. root tree:       GET /repos/{nwo}/git/trees/{head_oid}           -> raw/root_tree.jsonl
          For the rows with no root entry that matches NAME_RULE (near misses):
          2. README:          GET /repos/{nwo}/readme?ref={head_oid}          -> raw/readme.jsonl
          3. recursive tree:  GET /repos/{nwo}/git/trees/{head_oid}?recursive=1 -> raw/tree_recursive.jsonl
          4. package files:   GET /repos/{nwo}/git/blobs/{sha}, for the root
             entries Cargo.toml, pom.xml, meson.build, vcpkg.json, library.json;
             the sha comes from the root tree                                 -> raw/package_blobs.jsonl
          5. license folders: GET /repos/{nwo}/git/trees/{sha}, for each root folder named LICENSES, LICENSE,
             LICENCES or LICENCE (any case), all GitHub rows                  -> raw/license_folders.jsonl
  report  reads raw/ only (no network) and writes results.csv, results.md and returned_frame.csv.

Each raw line: pool_key, name_with_owner, head_oid, kind, url (the URL that was
called), final_url (after redirects), fetched_at (UTC), http_status,
x_github_request_id, body (the exact response text). fetch is resumable: a key
that has a line with a final status is not fetched again.

  extract writes raw/tree_recursive.extract.jsonl from raw/tree_recursive.jsonl (see extract()).

  fetch-frame (2026-10-10) reads the root names of the 24,498 GitHub frame rows (GraphQL, see fetch_frame()),
  roots    writes roots.csv, the DP8L input of ../funnel.py --dp8l (see roots_table()).
  licenses writes licenses.csv, the license values of the rows that come back (see licenses_table()).

Usage: python3 audit_dp8l.py fetch | extract | report | fetch-frame | roots | licenses
"""
import base64
import csv
import datetime as dt
import hashlib
import json
import lzma
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEL = HERE.parent.parent  # dataset-selection/
sys.path.insert(0, str(HERE.parent))
import dp8l_rule  # noqa: E402  the DP8L rule of 2026-10-10 (../dp8l_rule.py)
RAW = HERE / "raw"
API = "https://api.github.com"
NAME_RULE = re.compile(r"^(licen[cs]e|copying|unlicense)", re.I)  # clone_facts.py, same rule
# The name rule is a prefix rule, so it also matches names such as licenseregistry.cpp or license-api/.
# A root entry that matches it counts as a license file (A1) or a license folder (A2) only with these names:
LICENSE_FILE, LICENSE_DIR, CODE_EXT = dp8l_rule.LICENSE_FILE, dp8l_rule.LICENSE_DIR, dp8l_rule.CODE_EXT
# near misses at the root: other names of license or legal files
ROOT_NEAR = re.compile(r"(licen[cs]|copying|copyright|notice|legal|patents|eula)"
                       r"|^(a?gpl|lgpl|epl|mpl|apache|mit|bsd|cddl)([-_. ]?v?[0-9.]*)?(\.(txt|md|html?|rst))?$", re.I)
THIRD_PARTY = re.compile(r"(^|/)(third[-_]?party|3rd[-_]?party|thirdparty|vendor|vendored|external|externals|extern|"
                         r"deps|dependencies|contrib|node_modules|submodules)(/|$)", re.I)
PACKAGE_FILES = {"Cargo.toml": re.compile(r"^\s*license(-file)?\s*=", re.M),
                 "pom.xml": re.compile(r"<licenses?>", re.I),
                 "meson.build": re.compile(r"\blicense\s*:", re.I),
                 "vcpkg.json": re.compile(r'"license"\s*:'),
                 "library.json": re.compile(r'"license"\s*:')}
README_LICENSE = re.compile(r"licen[cs]|spdx-license-identifier", re.I)
SALT = "20261110:"  # u_of() in ../funnel.py and build_manifest.py
LAYERS = [(5000, "≥ 5,000"), (1000, "1,000–4,999"), (500, "500–999"), (100, "100–499"), (0, "< 100")]
MIN_REMAINING = 1000  # leave this part of the hourly REST quota to the other users of the token
PAUSE = 0.5  # seconds between two calls
FINAL = {200, 404, 409, 422, 451}


def u_of(slug):
    return (int.from_bytes(hashlib.sha256((SALT + slug).encode()).digest()[:8], "big") >> 11) / 2**53


def size_class(commits):
    return "S" if commits < 30000 else ("M" if commits <= 150000 else "L")


def layer_of(commits):
    return next(name for lo, name in LAYERS if commits >= lo)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def log(msg):
    line = f"{now()} {msg}"
    print(line, flush=True)
    with (HERE / "fetch.log").open("a") as f:
        f.write(line + "\n")


def lines(path):
    """The lines of a JSONL file, or of its .xz copy (the tracked form) when the plain file is not there."""
    xz = path.with_name(path.name + ".xz")
    if path.exists():
        return path.open(encoding="utf-8")
    if xz.exists():
        return lzma.open(xz, "rt", encoding="utf-8")
    return iter(())


def load_jsonl(path, key):
    out = {}
    for line in lines(path):
        d = json.loads(line)
        out[d[key]] = d  # the last line wins
    return out


def selection():
    """The rows that S4 removed at DP8L, with their pool rows, in pool order."""
    st = {r["pool_key"]: r for r in csv.DictReader(open(SEL / "s4-filter/frame_status.csv", encoding="utf-8"))}  # from funnel.py
    keep = {"no license file", "clone facts: fetch-failed"}
    rows = [r for r in csv.DictReader(lines(SEL / "s2-pool/pool.csv"))
            if st[r["pool_key"]]["excluded_because"] in keep]
    for r in rows:
        r["excluded_because"] = st[r["pool_key"]]["excluded_because"]
    return rows


class Client:
    def __init__(self):
        self.token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True).stdout.strip()

    def get(self, path):
        url = API + path
        for attempt in range(8):
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token}",
                                                       "Accept": "application/vnd.github+json",
                                                       "X-GitHub-Api-Version": "2022-11-28",
                                                       "User-Agent": "dp8l-audit (read-only, one call at a time)"})
            fetched = now()
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    status, headers, body, final = r.status, r.headers, r.read(), r.geturl()
            except urllib.error.HTTPError as e:
                status, headers, body, final = e.code, e.headers, e.read(), url
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                log(f"network error {e!r} on {url}, retry in 30 s")
                time.sleep(30)
                continue
            remaining = int(headers.get("X-RateLimit-Remaining", "5000"))
            reset = int(headers.get("X-RateLimit-Reset", "0"))
            if status in (403, 429) and (remaining == 0 or "Retry-After" in headers):
                wait = int(headers.get("Retry-After") or max(reset - time.time(), 0) + 5)
                log(f"HTTP {status} rate limit on {url}, wait {wait} s")
                time.sleep(wait)
                continue
            if status >= 500:
                log(f"HTTP {status} on {url}, retry in {30 * (attempt + 1)} s")
                time.sleep(30 * (attempt + 1))
                continue
            if remaining < MIN_REMAINING:
                wait = max(reset - time.time(), 0) + 5
                log(f"quota {remaining} < {MIN_REMAINING}, wait {int(wait)} s until the reset")
                time.sleep(wait)
            time.sleep(PAUSE)
            return {"url": url, "final_url": final, "fetched_at": fetched, "http_status": status,
                    "x_github_request_id": headers.get("X-GitHub-Request-Id"),
                    "body": body.decode("utf-8", "replace")}
        raise RuntimeError(f"{url}: no final answer after 8 tries")


def nwo_path(nwo):
    owner, repo = nwo.split("/", 1)
    return f"/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"


def fetch_kind(client, rows, kind, path_of):
    """One call for each (row, item) that has no final line yet in raw/{kind}.jsonl."""
    out = RAW / f"{kind}.jsonl"
    done = {(d["pool_key"], d.get("item", "")) for d in map(json.loads, out.open(encoding="utf-8"))
            if d["http_status"] in FINAL} if out.exists() else set()
    todo = [(r, item, p) for r in rows for item, p in path_of(r) if (r["pool_key"], item) not in done]
    log(f"{kind}: {len(todo)} calls to do, {len(done)} done before")
    with out.open("a", encoding="utf-8") as f:
        for i, (r, item, p) in enumerate(todo, 1):
            rec = {"pool_key": r["pool_key"], "name_with_owner": r["name_with_owner"], "head_oid": r["head_oid"],
                   "kind": kind, "item": item, **client.get(p)}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if rec["http_status"] != 200:
                log(f"{kind} {r['name_with_owner']} {item}: HTTP {rec['http_status']}")
            if i % 200 == 0:
                log(f"{kind}: {i}/{len(todo)}")


def root_entries(rec):
    if not rec or rec["http_status"] != 200:
        return None
    return json.loads(rec["body"])["tree"]


def frame_github_rows():
    """The GitHub rows of the frame (../frame_status.csv, no excluded_because), with their pool rows."""
    st = {r["pool_key"]: r for r in csv.DictReader(open(SEL / "s4-filter/frame_status.csv", encoding="utf-8"))}
    return [r for r in csv.DictReader(lines(SEL / "s2-pool/pool.csv"))
            if r["host"] == "github.com" and st[r["pool_key"]]["excluded_because"] == ""]


def gql_post(client, query):
    url = API + "/graphql"
    body = json.dumps({"query": query}).encode()
    for attempt in range(8):
        req = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {client.token}",
                                                              "Content-Type": "application/json",
                                                              "User-Agent": "dp8l-audit (read-only, one call at a time)"})
        fetched = now()
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                status, headers, text = r.status, r.headers, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            status, headers, text = e.code, e.headers, e.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            log(f"network error {e!r} on GraphQL, retry in 30 s")
            time.sleep(30)
            continue
        if status in (403, 429, 502, 503, 504):
            wait = int(headers.get("Retry-After") or 30 * (attempt + 1))
            log(f"GraphQL HTTP {status}, retry in {wait} s")
            time.sleep(wait)
            continue
        rl = (json.loads(text).get("data") or {}).get("rateLimit") if status == 200 else None
        if rl and rl["remaining"] < 500:
            wait = (dt.datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00"))
                    - dt.datetime.now(dt.timezone.utc)).total_seconds() + 5
            log(f"GraphQL quota {rl['remaining']}, wait {int(wait)} s")
            time.sleep(max(wait, 5))
        time.sleep(PAUSE)
        return {"url": url, "fetched_at": fetched, "http_status": status,
                "x_github_request_id": headers.get("X-GitHub-Request-Id"), "body": text}
    raise RuntimeError("GraphQL: no answer after 8 tries")


def fetch_frame():
    """The root names of the GitHub frame rows at the snapshot commit, so that the corrected DP8L rule can be applied
    to them too (decided 2026-10-10). GraphQL, 50 rows in one query, one query at a time:
    repository(owner, name) { databaseId object(oid: head_oid) { ... on Commit { tree { entries { name type } } } } }
    -> raw/frame_roots.jsonl (one line for each query: items, query, url, fetched_at, http_status, body).
    The rows that GraphQL does not answer get the REST root tree call of step 1 -> raw/frame_roots_rest.jsonl."""
    RAW.mkdir(exist_ok=True)
    rows = frame_github_rows()
    client = Client()
    out = RAW / "frame_roots.jsonl"
    done = set()
    for line in lines(out):
        d = json.loads(line)
        if d["http_status"] == 200:
            done.update(d["items"])
    todo = [r for r in rows if r["pool_key"] not in done]
    log(f"frame_roots: {len(todo)} rows to do, {len(done)} done before")
    with out.open("a", encoding="utf-8") as f:
        for i in range(0, len(todo), 50):
            part = todo[i:i + 50]
            q = "query {\n" + "\n".join(
                f'  r{j}: repository(owner: {json.dumps(r["name_with_owner"].split("/", 1)[0])}, '
                f'name: {json.dumps(r["name_with_owner"].split("/", 1)[1])}) {{ databaseId object(oid: "{r["head_oid"]}") '
                "{ ... on Commit { tree { entries { name type } } } } }" for j, r in enumerate(part)) + \
                "\n  rateLimit { cost remaining resetAt }\n}"
            rec = {"kind": "frame_roots", "items": [r["pool_key"] for r in part], **gql_post(client, q), "query": q}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            if (i // 50) % 40 == 0:
                log(f"frame_roots: {i + len(part)}/{len(todo)}")
    roots = frame_roots()
    miss = [r for r in rows if r["pool_key"] not in roots]
    log(f"frame_roots: {len(miss)} rows without a GraphQL answer; REST root tree for them")
    fetch_kind(client, miss, "frame_roots_rest",
               lambda r: [("", f"{nwo_path(r['name_with_owner'])}/git/trees/{r['head_oid']}")])
    # The rows whose root has a license folder but no license file: list the folder, so that the rule
    # "a folder that holds at least one file" is tested as for the DP8L rows (step 5).
    roots = frame_roots()
    only_dir = [r for r in rows if r["pool_key"] in roots
                and not any(t == "blob" and dp8l_rule.is_license_file(n) for n, t in roots[r["pool_key"]])
                and any(t == "tree" and dp8l_rule.is_license_dir(n) for n, t in roots[r["pool_key"]])]
    for r in only_dir:
        r["_dirs"] = [n for n, t in roots[r["pool_key"]] if t == "tree" and dp8l_rule.is_license_dir(n)]
    fetch_kind(client, only_dir, "frame_license_folders",
               lambda r: [(n, f"{nwo_path(r['name_with_owner'])}/contents/{urllib.parse.quote(n)}?ref={r['head_oid']}")
                          for n in r["_dirs"]])
    log("fetch-frame done")


def spdx_ids():
    """lower-case id -> SPDX id, from raw/spdx/ (license-list-data, the tag in raw/spdx/SOURCE.tsv): licenses and
    exceptions."""
    lic = json.load(open(RAW / "spdx/licenses.json", encoding="utf-8"))["licenses"]
    exc = json.load(open(RAW / "spdx/exceptions.json", encoding="utf-8"))["exceptions"]
    return {x["licenseId"].lower(): x["licenseId"] for x in lic} | {x["licenseExceptionId"].lower(): x["licenseExceptionId"]
                                                                  for x in exc}


def licenses_table():
    """licenses.csv (decided 2026-10-10): the license value for each row that comes back (A1 and A2 of
    results.csv) and for the rows of ../supplement.v2.csv: the SPDX ids that are the names of the files in the
    root folder LICENSES (REUSE; file name without its extension; an SPDX license or exception id, or LicenseRef-...),
    sorted and joined by ';'; else NOASSERTION. license_evidence: the folder files or root files used."""
    ids = spdx_ids()
    folders = {}
    for line in lines(RAW / "license_folders.jsonl"):
        d = json.loads(line)
        if d["http_status"] == 200:
            folders.setdefault(d["pool_key"], {})[d["item"]] = [e["path"] for e in json.loads(d["body"])["tree"]
                                                                if e["type"] == "blob"]
    out = []

    def value(key, files, dirs):
        found, used = set(), []
        for dname in dirs:
            if dname != "LICENSES":  # only the REUSE folder names its files by SPDX id; licenses/ of
                continue             # NetBSD/pkgsrc, for example, holds the licenses of the packaged software
            for fname in (folders.get(key) or {}).get(dname, []):
                stem = fname.rsplit(".", 1)[0] if "." in fname else fname
                sid = ids.get(stem.lower()) or (stem if re.fullmatch(r"LicenseRef-[A-Za-z0-9.-]+", stem) else None)
                if sid:
                    found.add(sid)
                    used.append(f"{dname}/{fname}")
        if found:
            return ";".join(sorted(found)), ";".join(used)
        return "NOASSERTION", ";".join(files) or ";".join(d + "/" for d in dirs)

    for r in csv.DictReader(open(HERE / "results.csv", encoding="utf-8")):
        if r["category"].startswith(("A1 ", "A2 ")):
            files = [x for x in r["root_license_files"].split(";") if x]
            dirs = [x for x in r["root_rule_folders"].split(";") if x and LICENSE_DIR.match(x)]
            lic, ev = value(r["pool_key"], files, dirs)
            out.append({"pool_key": r["pool_key"], "slug": r["slug"], "license": lic, "license_evidence": ev})
    cf = load_jsonl(SEL / "s3-measure/clone_facts.jsonl", "pool_key")
    cf.update(load_jsonl(SEL / "s3-measure/v2/clone_facts.jsonl", "pool_key"))
    for r in csv.DictReader(open(SEL / "s4-filter/supplement.v2.csv", encoding="utf-8")):
        names = [x for x in (cf.get(r["pool_key"]) or {}).get("license_files", []) if dp8l_rule.is_license_name(x)]
        assert names, r["pool_key"]
        out.append({"pool_key": r["pool_key"], "slug": r["slug"], "license": "NOASSERTION",
                    "license_evidence": ";".join(names)})
    with (HERE / "licenses.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["pool_key", "slug", "license", "license_evidence"], lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print(f"licenses.csv: {len(out)} rows, {sum(o['license'] == 'NOASSERTION' for o in out)} NOASSERTION")


REASON = {"P": "no license file (the prefix rule matches only a name that is not a license file)",
          "C": "no license file (near miss: other root name)",
          "D": "no license file (near miss: a package file declares a license)",
          "E": "no license file (near miss: license file only in a subfolder)",
          "F": "no license file (near miss: only the README names a license)",
          "G": "no license file (license files only in third-party folders)",
          "H": "no license file (no license evidence found)"}


def roots_table():
    """roots.csv: the DP8L input of ../funnel.py --dp8l for every GitHub row that reaches DP8L (the 2,692 DP8L
    rows of results.csv and the 24,498 GitHub rows of the frame): pool_key, has_license, evidence, reason, source."""
    out = []
    for r in csv.DictReader(open(HERE / "results.csv", encoding="utf-8")):
        if r["host"] != "github.com":
            continue
        cat = r["category"]
        has = cat.startswith(("A1 ", "A2 "))
        ev = r["root_license_files"] or (r["root_license_folders"] + "/" if r["root_license_folders"] else "")
        reason = "" if has else REASON.get(cat[0], cat)
        out.append({"pool_key": r["pool_key"], "name_with_owner": r["name_with_owner"], "has_license": has,
                    "evidence": ev if has else (r["root_rule_blobs"] or r["root_near_names"] or r["package_files"]
                                                or r["subfolder_examples"]),
                    "reason": reason, "source": "dp8l_rows"})
    roots = frame_roots()
    folders = {}
    for line in lines(RAW / "frame_license_folders.jsonl"):
        d = json.loads(line)
        if d["http_status"] == 200:
            folders[(d["pool_key"], d["item"])] = [e["name"] for e in json.loads(d["body"]) if e["type"] == "file"]
    for r in frame_github_rows():
        key = r["pool_key"]
        ents = roots.get(key)
        if ents is None:
            out.append({"pool_key": key, "name_with_owner": r["name_with_owner"], "has_license": False,
                        "evidence": "", "reason": "root tree not read", "source": "frame_rows"})
            continue
        files = [n for n, t in ents if t == "blob" and dp8l_rule.is_license_file(n)]
        dirs = [n for n, t in ents if t == "tree" and dp8l_rule.is_license_dir(n) and folders.get((key, n))]
        has = bool(files or dirs)
        out.append({"pool_key": key, "name_with_owner": r["name_with_owner"], "has_license": has,
                    "evidence": ";".join(files) or ";".join(d + "/" for d in dirs) or
                    ";".join(n for n, _ in ents if ROOT_NEAR.search(n)),
                    "reason": "" if has else f"no license file at the root (GitHub licenseInfo {r['license']})",
                    "source": "frame_rows"})
    with (HERE / "roots.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["pool_key", "name_with_owner", "has_license", "evidence", "reason", "source"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    c = Counter((o["source"], o["has_license"]) for o in out)
    print(f"roots.csv: {len(out)} rows; " + ", ".join(f"{k[0]} {k[1]}: {v}" for k, v in sorted(c.items())))


def frame_roots():
    """pool_key -> [(name, type)] of the root at the snapshot commit, from raw/frame_roots*.jsonl."""
    pool = {r["pool_key"]: r for r in frame_github_rows()}
    out = {}
    for line in lines(RAW / "frame_roots.jsonl"):
        d = json.loads(line)
        if d["http_status"] != 200:
            continue
        data = json.loads(d["body"]).get("data") or {}
        for j, key in enumerate(d["items"]):
            repo = data.get(f"r{j}")
            obj = (repo or {}).get("object")
            if repo and str(repo["databaseId"]) == pool[key]["database_id"] and obj and obj.get("tree"):
                out[key] = [(e["name"], "blob" if e["type"] == "blob" else e["type"]) for e in obj["tree"]["entries"]]
    for line in lines(RAW / "frame_roots_rest.jsonl"):
        d = json.loads(line)
        if d["http_status"] == 200:
            out[d["pool_key"]] = [(e["path"], e["type"]) for e in json.loads(d["body"])["tree"]]
    return out


def fetch():
    RAW.mkdir(exist_ok=True)
    gh = [r for r in selection() if r["host"] == "github.com"]
    client = Client()
    fetch_kind(client, gh, "root_tree", lambda r: [("", f"{nwo_path(r['name_with_owner'])}/git/trees/{r['head_oid']}")])
    roots = load_jsonl(RAW / "root_tree.jsonl", "pool_key")
    near = []
    for r in gh:
        ents = root_entries(roots.get(r["pool_key"]))
        if ents is not None and not any(NAME_RULE.match(e["path"]) for e in ents):
            r["_root"] = ents
            near.append(r)
    log(f"{len(near)} rows have a root tree and no root entry that matches the name rule")
    fetch_kind(client, near, "readme", lambda r: [("", f"{nwo_path(r['name_with_owner'])}/readme?ref={r['head_oid']}")])
    fetch_kind(client, near, "tree_recursive",
               lambda r: [("", f"{nwo_path(r['name_with_owner'])}/git/trees/{r['head_oid']}?recursive=1")])
    fetch_kind(client, near, "package_blobs",
               lambda r: [(e["path"], f"{nwo_path(r['name_with_owner'])}/git/blobs/{e['sha']}")
                          for e in r["_root"] if e["type"] == "blob" and e["path"] in PACKAGE_FILES])
    # 5. the content of each root license folder (A2): GET /repos/{nwo}/git/trees/{sha}, sha from the root tree
    folders = []
    for r in gh:
        ents = root_entries(roots.get(r["pool_key"])) or []
        r["_dirs"] = [e for e in ents if e["type"] == "tree" and LICENSE_DIR.match(e["path"])]
        if r["_dirs"]:
            folders.append(r)
    fetch_kind(client, folders, "license_folders",
               lambda r: [(e["path"], f"{nwo_path(r['name_with_owner'])}/git/trees/{e['sha']}") for e in r["_dirs"]])
    log("fetch done")


def extract():
    """raw/tree_recursive.extract.jsonl: the recursive trees are too large for the repository (about 1.2 GB), so
    the repository keeps, for each response, its metadata, the sha256 and size of the body, the truncated flag, the
    number of entries and the paths of the files below the root whose name matches NAME_RULE. A tree at a commit
    does not change, so the same URL gives the same body again; the sha256 checks it."""
    with (RAW / "tree_recursive.extract.jsonl").open("w", encoding="utf-8") as f:
        for line in lines(RAW / "tree_recursive.jsonl"):
            d = json.loads(line)
            body = d.pop("body")
            d["body_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
            d["body_bytes"] = len(body.encode("utf-8"))
            if d["http_status"] == 200:
                t = json.loads(body)
                d["truncated"] = t.get("truncated", False)
                d["n_entries"] = len(t["tree"])
                d["license_paths"] = [e["path"] for e in t["tree"] if "/" in e["path"] and e["type"] == "blob"
                                      and NAME_RULE.match(e["path"].rsplit("/", 1)[1])]
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def blob_text(rec):
    d = json.loads(rec["body"])
    return base64.b64decode(d.get("content", "")).decode("utf-8", "replace") if d.get("encoding") == "base64" else ""


def report():
    rows = selection()
    roots = load_jsonl(RAW / "root_tree.jsonl", "pool_key")
    readmes = load_jsonl(RAW / "readme.jsonl", "pool_key")
    rtrees = load_jsonl(RAW / "tree_recursive.extract.jsonl", "pool_key")
    pkgs, lfolders = {}, {}
    for line in lines(RAW / "package_blobs.jsonl"):
        d = json.loads(line)
        pkgs.setdefault(d["pool_key"], {})[d["item"]] = d
    for line in lines(RAW / "license_folders.jsonl"):
        d = json.loads(line)
        lfolders.setdefault(d["pool_key"], {})[d["item"]] = d
    commits = load_jsonl(SEL / "s3-measure/commits.jsonl", "name_with_owner")
    clones = load_jsonl(SEL / "s3-measure/clones.jsonl", "pool_key")
    cfacts = load_jsonl(SEL / "s3-measure/clone_facts.jsonl", "pool_key")
    by_oid = {}
    for c in clones.values():
        if c.get("kind") == "other-host" and c.get("status") == "ok" and c.get("head_oid"):
            by_oid.setdefault(c["head_oid"], []).append(c["pool_key"])
    out = []
    for r in rows:
        key, nwo, gh = r["pool_key"], r["name_with_owner"], r["host"] == "github.com"
        res = {"pool_key": key, "name_with_owner": nwo, "host": r["host"], "head_oid": r["head_oid"],
               "excluded_because": r["excluded_because"], "pool_license": r["license"],
               "other_host_copy": ";".join(by_oid.get(r["head_oid"], [])) if r["host"] == "github.com" else ""}
        if gh:
            n = (commits.get(nwo) or {}).get("commits")
            slug = nwo
        else:
            f = cfacts.get(key) or {}
            n = f.get("commits")
            c = clones.get(key) or {}
            res["head_oid"] = c.get("head_oid", "")
            slug = r["repo_url"].split("://", 1)[1].split("/", 1)[1].strip("/").removesuffix(".git")
        res.update(commits=n if n is not None else "", layer=layer_of(n) if n is not None else "unknown",
                   size_class=size_class(n) if n is not None else "", u=repr(u_of(slug)), slug=slug)
        root_rule_blob, root_rule_tree, root_near, sub_own, sub_third, readme_hit, pkg_hit = [], [], [], [], [], "", []
        lic_files, lic_dirs, folder_files = [], [], []
        tree_status = readme_status = rtree_status = ""
        if gh:
            rec = roots.get(key)
            tree_status = rec["http_status"] if rec else "not fetched"
            ents = root_entries(rec) or []
            for e in ents:
                if NAME_RULE.match(e["path"]):
                    (root_rule_blob if e["type"] == "blob" else root_rule_tree).append(e["path"])
                    if e["type"] == "blob" and LICENSE_FILE.match(e["path"]) and not CODE_EXT.search(e["path"]):
                        lic_files.append(e["path"])
                    elif e["type"] == "tree" and LICENSE_DIR.match(e["path"]):
                        fr = (lfolders.get(key) or {}).get(e["path"])
                        files = [x["path"] for x in json.loads(fr["body"])["tree"]
                                 if x["type"] == "blob"] if fr and fr["http_status"] == 200 else []
                        if files:
                            lic_dirs.append(e["path"])
                            folder_files += [f"{e['path']}/{x}" for x in files]
                elif ROOT_NEAR.search(e["path"]):
                    root_near.append(e["path"])
            if ents and not (root_rule_blob or root_rule_tree):
                rd = readmes.get(key)
                readme_status = rd["http_status"] if rd else "not fetched"
                if rd and rd["http_status"] == 200:
                    for line in blob_text(rd).splitlines():
                        if README_LICENSE.search(line):
                            readme_hit = line.strip()[:160]
                            break
                rt = rtrees.get(key)
                rtree_status = rt["http_status"] if rt else "not fetched"
                if rt and rt["http_status"] == 200:
                    if rt["truncated"]:
                        rtree_status = "200 truncated"
                    for path in rt["license_paths"]:
                        (sub_third if THIRD_PARTY.search(path) else sub_own).append(path)
                for name, prec in (pkgs.get(key) or {}).items():
                    if prec["http_status"] == 200 and PACKAGE_FILES[name].search(blob_text(prec)):
                        pkg_hit.append(name)
        if lic_files:
            cat = "A1 root license file"
        elif lic_dirs:
            cat = "A2 root license folder (no root license file)"
        elif root_rule_blob or root_rule_tree:
            cat = "P name rule matches, but no license file"
        elif not gh:
            cat = "other host: checked in S3" if r["excluded_because"] == "no license file" else "other host: not checked (fetch failed)"
        elif tree_status != 200:
            cat = f"root tree not read (HTTP {tree_status})"
        elif root_near:
            cat = "C near miss: other root name"
        elif pkg_hit:
            cat = "D near miss: package file declares a license"
        elif sub_own:
            cat = "E near miss: license file in a subfolder"
        elif readme_hit:
            cat = "F near miss: README names a license"
        elif sub_third:
            cat = "G license files in third-party folders only"
        else:
            cat = "H no license evidence found"
        res.update(category=cat, root_rule_blobs=";".join(root_rule_blob), root_rule_folders=";".join(root_rule_tree),
                   root_license_files=";".join(lic_files), root_license_folders=";".join(lic_dirs),
                   license_folder_files=";".join(folder_files[:6]) + (";..." if len(folder_files) > 6 else ""),
                   root_near_names=";".join(root_near), package_files=";".join(pkg_hit),
                   subfolder_license_files=len(sub_own), subfolder_examples=";".join(sub_own[:3]),
                   third_party_license_files=len(sub_third), readme_line=readme_hit,
                   root_tree_status=tree_status, readme_status=readme_status, recursive_tree_status=rtree_status)
        out.append(res)
    cols = ["pool_key", "name_with_owner", "host", "head_oid", "excluded_because", "pool_license", "other_host_copy", "category",
            "commits", "layer", "size_class", "u", "slug", "root_rule_blobs", "root_rule_folders", "root_license_files",
            "root_license_folders", "license_folder_files", "root_near_names",
            "package_files", "subfolder_license_files", "subfolder_examples", "third_party_license_files",
            "readme_line", "root_tree_status", "readme_status", "recursive_tree_status"]
    with (HERE / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    write_returned(out, rows)
    write_md(out)


def write_returned(out, rows):
    """returned_frame.csv: the rows of categories A and B as frame rows, with the columns of ../frame.csv and the
    values that funnel.py would give them (S3 measures, pool facts), in run order: layer, then u. GitHub rows only."""
    trees = load_jsonl(SEL / "s3-measure/trees.jsonl", "name_with_owner")
    clones = load_jsonl(SEL / "s3-measure/clones.jsonl", "pool_key")
    pool = {r["pool_key"]: r for r in rows}
    rank = {name: i for i, (_, name) in enumerate(LAYERS)}
    frame = []
    for res in out:
        if not res["category"].startswith(("A1 ", "A2 ")):
            continue
        r = pool[res["pool_key"]]
        t = trees.get(r["name_with_owner"])
        m = clones.get(r["pool_key"]) if t and t.get("truncated") else t  # the same choice as funnel.py
        n = int(res["commits"])
        frame.append({"slug": r["name_with_owner"], "host": r["host"],
                      "repo_url": f"https://github.com/{r['name_with_owner']}.git", "head_oid": r["head_oid"],
                      "u": res["u"], "size_class": size_class(n), "labels": "pending", "layer": layer_of(n),
                      "commits": n, "language": r["primary_language"], "tok_bytes": m["tok_bytes"],
                      "tok_vendor_bytes": m.get("tok_vendor_bytes", 0), "pushed_at": r["pushed_at"],
                      "stars": r["stars"], "pool_key": r["pool_key"]})
    frame.sort(key=lambda f: (rank[f["layer"]], float(f["u"]), f["slug"]))
    cols = ["slug", "host", "repo_url", "head_oid", "u", "size_class", "labels", "layer", "commits", "language",
            "tok_bytes", "tok_vendor_bytes", "pushed_at", "stars", "pool_key"]
    with (HERE / "returned_frame.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(frame)


def batch_of(u, l1):
    """The built batch whose u range holds u: batch k holds rows (k-1)*164+1 .. k*164 of frame.layer1.csv."""
    limit = 164
    pos = sum(1 for x in l1 if x < u)  # rows of frame.layer1.csv before this u
    return pos, pos // limit + 1


def write_md(out):
    l1 = sorted(float(r["u"]) for r in csv.DictReader(open(SEL / "s7-run/frame.layer1.csv", encoding="utf-8")))
    cats = Counter(r["category"] for r in out)
    back = [r for r in out if r["category"].startswith(("A1 ", "A2 "))]
    md = ["# DP8L audit: results", "",
          f"Computed {now()} by `audit_dp8l.py report` from `raw/` (no network). Rows: the {len(out):,} rows that "
          "S4 removed at DP8L (`../frame_status.csv`). Method: `method.md`.", "",
          "## Rows by category", "", "| Category | Rows | of them in layer 1 (≥ 5,000 commits) |", "| --- | ---: | ---: |"]
    for k in sorted(cats):
        md.append(f"| {k} | {cats[k]:,} | {sum(1 for r in out if r['category'] == k and r['layer'] == '≥ 5,000'):,} |")
    md += [f"| all | {len(out):,} | {sum(1 for r in out if r['layer'] == '≥ 5,000'):,} |", "",
           "## Rows that come back (A1 and A2) by run layer (DP7)", "",
           "All of them passed every other S4 filter: DP8L is the last step, and each row has the first step that "
           "removes it.", "",
           "| Layer (commits) | A1 root license file | A2 root license folder only | Total | of them: same head commit as an other-host row |",
           "| --- | ---: | ---: | ---: | ---: |"]
    for name in [n for _, n in LAYERS] + ["all"]:
        rs = [r for r in back if name in ("all", r["layer"])]
        a1 = sum(1 for r in rs if r["category"].startswith("A1 "))
        md.append(f"| {name} | {a1:,} | {len(rs) - a1:,} | {len(rs):,} | {sum(1 for r in rs if r['other_host_copy']):,} |")
    lay1 = sorted((r for r in back if r["layer"] == "≥ 5,000"), key=lambda r: float(r["u"]))
    md += ["", "## Layer 1 projects that come back, in u order", "",
           "`row` = the number of rows of `frame.layer1.csv` with a smaller u; `u batch` = the built or planned batch "
           "of 164 rows whose u range holds this u. These projects are in no batch now.", "",
           "| # | Project | Commits | Size class | Evidence | Copy on another host | u | row | u batch |",
           "| ---: | --- | ---: | :---: | --- | --- | ---: | ---: | ---: |"]
    for i, r in enumerate(lay1, 1):
        pos, b = batch_of(float(r["u"]), l1)
        ev = r["root_license_files"] or (r["root_license_folders"] + "/ (" + r["license_folder_files"].split(";")[0] + ")")
        md.append(f"| {i} | {r['name_with_owner']} | {int(r['commits']):,} | {r['size_class']} | {ev} | "
                  f"{r['other_host_copy']} | {float(r['u']):.6f} | {pos} | {b} |")
    sc = Counter(r["size_class"] for r in lay1)
    bb = Counter(batch_of(float(r["u"]), l1)[1] for r in lay1)
    md += ["", f"Layer 1 by size class: S {sc['S']}, M {sc['M']}, L {sc['L']}.",
           "Layer 1 by u batch: " + ", ".join(f"{k}: {bb[k]}" for k in sorted(bb)) + ".", "",
           "## P: the name rule matches, but the entry is not a license file", "",
           "| Project | Layer | Root entries that match the prefix rule |", "| --- | --- | --- |"]
    for r in out:
        if r["category"].startswith("P "):
            md.append(f"| {r['name_with_owner']} | {r['layer']} | {(r['root_rule_blobs'] + ';' + r['root_rule_folders']).strip(';')} |")
    (HERE / "results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:45]))

if __name__ == "__main__":
    {"fetch": fetch, "fetch-frame": fetch_frame, "roots": roots_table, "licenses": licenses_table, "extract": extract, "report": report}[sys.argv[1]]()
