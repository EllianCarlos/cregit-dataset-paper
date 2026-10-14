#!/usr/bin/env python3
"""S5 evidence: one row for each fact about each project of the frames (default: dataset version 1).
Usage: build_evidence.py [--frame F ...] [--pool P ...] [--out evidence.csv] [--counts counts.txt]

The script reads only files that are already in this folder tree. It fetches nothing.

Inputs (relative to dataset-selection/):
  s7-run/frame.layer1.csv        the projects (slug, host, repo_url, pool_key): batches 1-20
  s7-run/frame.batch21.csv       batch 21 (2026-10-10): the DP8L supplement and BusyBox
  s7-run/frame.batch22.csv       batch 22 (2026-10-10): the GNU roster v2 supplement
                                 (--frame replaces the three; give it once for each frame)
  s2-pool/pool.csv               origins, input_slugs, owner_type, owner_login, fetched_at
  s2-pool/v2/pool.batch22.csv    the pool rows of batch 22, in the columns of pool.csv
                                 (--pool replaces the two). A key in two pool files must have
                                 the same values in both; the first file gives the pointer.
  s2-pool/roster_orgs.csv        roster rows that name a GitHub organization, not a repository
  rosters/<org>.csv              the rosters (org_kind, project, github_slug, roster_status, ...)
  rosters/<org>.repos.csv        home page -> repository lookups (obf, sfc, spi, numfocus, psf-sponsored)
  rosters/raw/asf/projects.json  the ASF DOAP files: the language each DOAP names
  sources/spinellis-2020/        enterprise-oss.tar.gz, FETCH.tsv, org_links.csv
  sources/company-pages/         evidence.csv, browser/evidence_browser.csv

Fact types (SELECTION-STAGES.md section 7; the extra types are marked +):
  roster:<org>               a foundation roster names the repository
  roster_org:<org>           a foundation roster names the GitHub org of the repository
  fiscal_sponsor:<org>       a fiscal sponsor roster names the repository (or its org, level=org)
  roster_affiliated:<org>  + a fiscal sponsor roster names the repository with a status that is
                             not a sponsorship (NumFOCUS "affiliated"); S6 does not use it
  company_roster:<org>     + a company roster names the repository (mozilla)
  company_roster_org:<org> + a company roster names the GitHub org of the repository (redhat)
  company_pool:spinellis     the repository is in the Spinellis enterprise set, with a company
  company_org:<org>          a kept company org, with a company page (strength=page) or GitHub
                             verified with its website on the company domain (strength=verified-domain)
  company_org_candidate:<org> + a kept company org with neither; S6 does not use it
  owner_kind:user|org        GitHub owner type

Output columns: project (the manifest and sidecar key), pool_key, fact_type, fact, subject,
name (the project name as the source spells it), status (the source's status, or the strength),
language (the language the source names), source (the file in this repository), source_url
(the URL that the source file records as read), fetched_at (UTC, as the source file records
it), pointer (file:line of the row that holds the fact), note.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "s7-run"))
from enrich_meta import project_name  # noqa: E402

COLS = ["project", "pool_key", "fact_type", "fact", "subject", "name", "status", "language",
        "source", "source_url", "fetched_at", "pointer", "note"]
GH_URL = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+)")
GRAPHQL = "https://api.github.com/graphql"
# NumFOCUS lists "sponsored" (fiscally sponsored) and "affiliated" projects. Its own page says
# that affiliated projects are not fiscally sponsored, so the status decides the fact type.
NOT_SPONSORED = {("numfocus", "affiliated")}
# A roster file that is a later fetch of another roster file (2026-10-10: gnu.v2.csv is
# gnu.csv fetched again, with the same 388 rows and more repositories). A pool row from before
# the later fetch names only the earlier file in origins. So for such a row the join check
# accepts the later file next to the earlier one, and writes an info line.
LATER_FETCH = {"rosters/gnu.v2.csv:gnu": "rosters/gnu.csv:gnu"}
FRAMES = [ROOT / "s7-run" / f for f in ("frame.layer1.csv", "frame.batch21.csv", "frame.batch22.csv")]
POOLS = [ROOT / "s2-pool" / "pool.csv", ROOT / "s2-pool" / "v2" / "pool.batch22.csv"]


def norm_url(u: str) -> str:
    """The normalized URL that s2-pool/build_pool.py uses as the key of a non-GitHub row."""
    u = u.strip().rstrip("/")
    u = re.sub(r"^http://", "https://", u, flags=re.I)
    u = re.sub(r"\.git$", "", u)
    return u.lower()


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def read_csv(path: Path):
    """(line, row) for each row; line is the 1-based physical line where the row ends."""
    with path.open(newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            yield rd.line_num, row


# ----------------------------------------------------------------------------- the frame

def load_frame(*frames: Path) -> list[dict]:
    """The rows of the frames, in order. A name or a pool key must not repeat in or across them."""
    out = []
    for frame in frames:
        for _, r in read_csv(frame):
            host = r["host"].strip().lower() or "github.com"
            out.append({"project": project_name(host, r["slug"].strip()), "pool_key": r["pool_key"],
                        "host": host, "slug": r["slug"].strip(), "repo_url": r["repo_url"].strip()})
    names = Counter(x["project"] for x in out)
    keys = Counter(x["pool_key"] for x in out)
    dup = [n for n, k in names.items() if k > 1] + [k for k, v in keys.items() if v > 1]
    if dup:
        raise ValueError(f"{', '.join(map(str, frames))}: repeated names or pool keys: {dup[:5]}")
    return out


def load_pool(pools, keys: set[str]) -> dict[str, dict]:
    """pool_key -> row (with _file and _line) for the wanted keys. A key in two files must have
    the same values in both; the first file keeps the row."""
    out = {}
    for pool in [pools] if isinstance(pools, Path) else pools:
        for line, r in read_csv(pool):
            k = r["pool_key"]
            if k not in keys:
                continue
            if k in out:
                old = {c: v for c, v in out[k].items() if not c.startswith("_")}
                if old != r:
                    raise ValueError(f"{pool}:{line}: pool_key {k} has other values in "
                                     f"{out[k]['_file']}")
                continue
            out[k] = dict(r, _file=Path(pool).resolve(), _line=line)
    return out


# ----------------------------------------------------------------------------- rosters

def roster_rows(rosters: Path):
    """Every roster row, with its kind and status. The *.repos.csv files take the kind of the
    main file and the status of the main file's row for the same project."""
    main: dict[str, list[tuple[int, dict]]] = {}
    for f in sorted(rosters.glob("*.csv")):
        if f.name.endswith((".orig.csv", ".repos.csv")):
            continue
        main[f.name] = list(read_csv(f))
    for name, rows in main.items():
        for line, r in rows:
            yield {"file": rosters / name, "line": line, "org": r["org_key"], "kind": r["org_kind"],
                   "project": r["project"], "repo_url": r["repo_url"].strip(),
                   "slug": r["github_slug"].strip(), "status": r["roster_status"],
                   "source_url": r["source_url"], "fetched_at": r["fetched_at"], "note": r["note"]}
    for f in sorted(rosters.glob("*.repos.csv")):
        base = f.name.replace(".repos.csv", ".csv")
        rows = main.get(base, [])
        kinds = {r["org_kind"] for _, r in rows}
        if len(kinds) != 1:
            raise ValueError(f"{f}: the main file {base} has kinds {kinds}")
        status = defaultdict(set)
        for _, r in rows:
            status[r["project"]].add(r["roster_status"])
        for line, r in read_csv(f):
            st = sorted(status.get(r["project"], set()))
            if len(st) > 1:
                raise ValueError(f"{f}:{line}: project {r['project']!r} has statuses {st} in {base}")
            yield {"file": f, "line": line, "org": r["org_key"], "kind": next(iter(kinds)),
                   "project": r["project"], "repo_url": r["repo_url"].strip(),
                   "slug": r["github_slug"].strip(), "status": st[0] if st else "",
                   "source_url": r["lookup_url"], "fetched_at": r["fetched_at"],
                   "note": f"repository from the home page lookup; roster {rel(rosters / base)}"
                           + (f"; {r['note']}" if r["note"] else "")}


def org_login(url: str) -> tuple[str, str]:
    """(login, '') for a URL that names a GitHub account; ('', why) otherwise."""
    m = re.match(r"^https?://(?:www\.)?github\.com/(.*)$", url.strip(), re.I)
    if not m:
        return "", "not a github.com URL"
    path = [p.strip() for p in m.group(1).split("?")[0].split("#")[0].split("/") if p.strip()]
    if len(path) >= 2 and path[0].lower() == "orgs":
        path = path[1:]
    if not path:
        return "", "no account in the URL"
    if path[0].lower() in {"topics", "search", "marketplace", "features"}:
        return "", f"a GitHub {path[0]} page, not an account"
    if len(path) > 1:
        return "", "names a repository with a broken URL, not an account"
    return path[0].lower(), ""


# ----------------------------------------------------------------------------- ASF DOAP language

def asf_languages(projects_json: Path) -> dict[str, str]:
    """DOAP project name -> programming-language, as the DOAP file spells it. Names that repeat
    with different languages are left out."""
    d = json.loads(projects_json.read_text(encoding="utf-8"))
    seen: dict[str, set] = defaultdict(set)
    for p in d.values():
        lang = p.get("programming-language")
        if isinstance(lang, list):
            lang = ", ".join(lang)
        seen[p.get("name", "")].add(lang or "")
    return {n: next(iter(v)) for n, v in seen.items() if n and len(v) == 1 and next(iter(v))}


# ----------------------------------------------------------------------------- Spinellis

SP_COLS = ("url project_id sdtc mcpc mcve star_number commit_count files lines pull_requests "
           "github_repo_creation earliest_commit most_recent_commit committer_count author_count "
           "dominant_domain dominant_domain_committer_commits dominant_domain_author_commits "
           "dominant_domain_committers dominant_domain_authors cik fg500 sec10k sec20f project_name "
           "owner_login company_name owner_company license").split()


def spinellis_rows(sp: Path):
    """slug_lower -> [(line, row)] of enterprise_projects.txt."""
    with tarfile.open(sp / "enterprise-oss.tar.gz") as t:
        text = t.extractfile("enterprise_projects.txt").read().decode("utf-8", "replace")
    out = defaultdict(list)
    for i, l in enumerate(text.splitlines(), 1):
        r = dict(zip(SP_COLS, l.split("\t")))
        m = GH_URL.match(r["url"].strip())
        if m:
            out[f"{m.group(1)}/{m.group(2)}".lower()].append((i, r))
    return out


def fetch_tsv(path: Path) -> dict[str, str]:
    return dict(l.rstrip("\n").split("\t", 1) for l in path.read_text().splitlines() if "\t" in l)


# ----------------------------------------------------------------------------- build

def build(frame_rows: list[dict], root: Path = ROOT, pools=None) -> tuple[list[dict], list[str]]:
    """(fact rows, check problems). A problem is a disagreement between this join and the
    origins column of the pool; it is reported, not fatal. pools: the pool files (default:
    POOLS under root)."""
    if pools is None:
        pools = [root / p.relative_to(ROOT) for p in POOLS]
    pool = load_pool(pools, {x["pool_key"] for x in frame_rows})
    missing = [x["pool_key"] for x in frame_rows if x["pool_key"] not in pool]
    if missing:
        raise ValueError(f"pool keys not in the pool files: {missing[:5]}")
    rosters = root / "rosters"
    langs = asf_languages(rosters / "raw" / "asf" / "projects.json")

    by_slug: dict[str, list[dict]] = defaultdict(list)
    by_url: dict[str, list[dict]] = defaultdict(list)
    org_rows: dict[str, list[dict]] = defaultdict(list)
    skipped_org_urls = []
    for r in roster_rows(rosters):
        if r["slug"]:
            by_slug[r["slug"].lower()].append(r)
        elif re.match(r"^https?://(www\.)?github\.com/", r["repo_url"], re.I):
            login, why = org_login(r["repo_url"])
            if login:
                org_rows[login].append(r)
            else:
                skipped_org_urls.append((r, why))
        elif r["repo_url"]:
            by_url[norm_url(r["repo_url"])].append(r)

    sp = root / "sources" / "spinellis-2020"
    sp_rows = spinellis_rows(sp)
    sp_fetch = fetch_tsv(sp / "FETCH.tsv")
    links = {}
    for line, r in read_csv(sp / "org_links.csv"):
        if r["link"] == "kept":
            links[r["owner"].lower()] = dict(r, _line=line)
    pages = defaultdict(list)
    cp = root / "sources" / "company-pages"
    for f in (cp / "evidence.csv", cp / "browser" / "evidence_browser.csv"):
        for line, r in read_csv(f):
            pages[r["org"].lower()].append(dict(r, _file=f, _line=line))

    facts: list[dict] = []
    problems: list[str] = []
    for x in frame_rows:
        p = pool[x["pool_key"]]
        base = {"project": x["project"], "pool_key": x["pool_key"]}

        def add(**kw):
            row = {c: "" for c in COLS}
            row.update(base, **kw)
            facts.append(row)

        # Roster facts: the repository itself.
        matched = []
        if x["pool_key"].startswith("gh:"):
            for s in filter(None, p["input_slugs"].split(";")):
                matched += by_slug.get(s.lower(), [])
        else:
            matched += by_url.get(x["pool_key"][4:], [])
        seen_origin = set()
        for r in matched:
            seen_origin.add(f"rosters/{r['file'].name}:{r['org']}")
            kind, org = r["kind"], r["org"]
            if kind == "foundation":
                ft = "roster"
            elif kind == "fiscal-sponsor":
                ft = "roster_affiliated" if (org, r["status"]) in NOT_SPONSORED else "fiscal_sponsor"
            elif kind == "company":
                ft = "company_roster"
            else:
                raise ValueError(f"{r['file']}:{r['line']}: org_kind {kind!r}")
            # Only an ASF row that comes from a DOAP repository entry (rows A of asf.method.md)
            # has a DOAP of its own; rows B carry only the PMC name.
            lang = langs.get(r["project"], "") if org == "asf" and "DOAP repository" in r["note"] else ""
            add(fact_type=ft, fact=f"{ft}:{org}", subject=org, name=r["project"], status=r["status"],
                language=lang, source=rel(r["file"]), source_url=r["source_url"],
                fetched_at=r["fetched_at"], pointer=f"{rel(r['file'])}:{r['line']}",
                note=r["note"] + ("; language from rosters/raw/asf/projects.json" if lang else ""))
        want = {o for o in p["origins"].split(";") if o.startswith("rosters/")}
        later = {o for o in seen_origin - want if LATER_FETCH.get(o) in want}
        if want != seen_origin - later:
            problems.append(f"{x['project']}: roster origins {sorted(want)} but joined {sorted(seen_origin)}")
        for o in sorted(later):
            problems.append(f"info: {x['project']}: joined {o} too, a later fetch of {LATER_FETCH[o]}; "
                            f"the pool row names only {LATER_FETCH[o]}")

        login = (p["owner_login"] or "").lower()
        # Roster facts: the org of the repository.
        for r in org_rows.get(login, []) if login else []:
            kind, org = r["kind"], r["org"]
            if kind == "foundation":
                ft = "roster_org"
            elif kind == "fiscal-sponsor":
                ft = "roster_affiliated" if (org, r["status"]) in NOT_SPONSORED else "fiscal_sponsor"
            else:
                ft = "company_roster_org"
            add(fact_type=ft, fact=f"{ft}:{org}", subject=org, name=r["project"], status=r["status"],
                source=rel(r["file"]), source_url=r["source_url"], fetched_at=r["fetched_at"],
                pointer=f"{rel(r['file'])}:{r['line']}",
                note=f"level=org; the roster names {r['repo_url']}" + (f"; {r['note']}" if r["note"] else ""))

        # Spinellis enterprise set, with a company.
        sp_hit = False
        for s in filter(None, p["input_slugs"].split(";")):
            for line, r in sp_rows.get(s.lower(), []):
                sp_hit = True
                if not r["company_name"]:
                    continue
                flags = ",".join(f for f in ("fg500", "sec10k", "sec20f") if r[f] == "t")
                add(fact_type="company_pool", fact="company_pool:spinellis", subject=r["company_name"],
                    name=r["project_name"], status=flags,
                    source="sources/spinellis-2020/enterprise-oss.tar.gz", source_url=sp_fetch["url"],
                    fetched_at=sp_fetch["fetched_at"],
                    pointer=f"sources/spinellis-2020/enterprise-oss.tar.gz:enterprise_projects.txt:{line}",
                    note=f"Spinellis et al. 2020 (Zenodo 3742962 v1.1.0.0); row {r['url']}; "
                         f"dominant_domain {r['dominant_domain']}; the link comes from committer "
                         "e-mail domains, not from the ownership of the org")
        if ("spinellis-2020:enterprise" in p["origins"].split(";")) != sp_hit:
            problems.append(f"{x['project']}: Spinellis origin {'spinellis-2020:enterprise' in p['origins']}"
                            f" but joined {sp_hit}")

        # Company org.
        link = links.get(login) if login and p["owner_type"] == "Organization" else None
        org_origin = any(o.lower() == f"company-org:{login}" for o in p["origins"].split(";"))
        if bool(link) != org_origin and login:
            problems.append(f"{x['project']}: company-org origin {org_origin} but kept link {bool(link)}")
        if link:
            strong = pages.get(login, [])
            for r in strong:
                add(fact_type="company_org", fact=f"company_org:{link['owner']}", subject=link["company"],
                    name=link["owner"], status="page", source=rel(r["_file"]),
                    source_url=r["final_url"] or r["page_url"], fetched_at=r["fetched_at"],
                    pointer=f"{rel(r['_file'])}:{r['_line']}",
                    note=f"the page {r['page_url']} (the website in the org's GitHub profile) "
                         f"links to github.com/{link['owner']}" + (f"; read with {r['method']}"
                                                                    if r.get("method") else ""))
            verified = link["is_verified"] == "True" and link["website_on_company_domain"] == "True"
            if verified:
                add(fact_type="company_org", fact=f"company_org:{link['owner']}", subject=link["company"],
                    name=link["owner"], status="verified-domain",
                    source="sources/spinellis-2020/org_links.csv", source_url=GRAPHQL,
                    fetched_at=link["fetched_at"],
                    pointer=f"sources/spinellis-2020/org_links.csv:{link['_line']}",
                    note=f"GitHub isVerified=true; websiteUrl {link['website_url']} is on a domain "
                         f"of {link['company']}")
            if not strong and not verified:
                add(fact_type="company_org_candidate", fact=f"company_org_candidate:{link['owner']}",
                    subject=link["company"], name=link["owner"], status="candidate",
                    source="sources/spinellis-2020/org_links.csv", source_url=GRAPHQL,
                    fetched_at=link["fetched_at"],
                    pointer=f"sources/spinellis-2020/org_links.csv:{link['_line']}",
                    note=f"kept org link (rules L1-L3) with no company page and not "
                         f"(verified and website on a company domain): is_verified={link['is_verified']}, "
                         f"website_url={link['website_url'] or '-'}")

        # Owner kind.
        ot = p["owner_type"]
        if ot:
            kind = {"User": "user", "Organization": "org"}.get(ot)
            if kind is None:
                raise ValueError(f"{x['pool_key']}: owner_type {ot!r}")
            add(fact_type="owner_kind", fact=f"owner_kind:{kind}", subject=p["owner_login"], status=ot,
                source=rel(p["_file"]), source_url=GRAPHQL, fetched_at=p["fetched_at"],
                pointer=f"{rel(p['_file'])}:{p['_line']}", note=f"read by {p['fetched_by']}")
    notes = [f"info: roster URL gives no GitHub account ({why}), not used: "
             f"{rel(r['file'])}:{r['line']} {r['repo_url']}" for r, why in skipped_org_urls]
    return facts, problems + notes


def counts_text(frame_rows: list[dict], facts: list[dict]) -> str:
    n = len(frame_rows)
    by_type = Counter(f["fact_type"] for f in facts)
    proj_type = defaultdict(set)
    by_fact = defaultdict(set)
    for f in facts:
        proj_type[f["fact_type"]].add(f["project"])
        by_fact[f["fact"]].add(f["project"])
    lines = [f"projects: {n}", f"fact rows: {len(facts)}", "",
             "fact_type: rows, projects"]
    for t in sorted(by_type):
        lines.append(f"  {t}: {by_type[t]}, {len(proj_type[t])}")
    lines += ["", "fact: projects"]
    for k in sorted(by_fact, key=lambda k: (-len(by_fact[k]), k)):
        lines.append(f"  {k}: {len(by_fact[k])}")
    st = Counter(f["status"] for f in facts if f["fact_type"] == "company_org")
    lines += ["", "company_org rows by strength: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items()))]
    with_any = {f["project"] for f in facts if f["fact_type"] != "owner_kind"}
    lines.append(f"projects with a fact other than owner_kind: {len(with_any)}")
    lines.append(f"projects with no owner_kind (not on GitHub): "
                 f"{n - len(proj_type['owner_kind'])}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--frame", type=Path, action="append",
                    help="a frame CSV; give it once for each frame (default: the three of FRAMES)")
    ap.add_argument("--pool", type=Path, action="append",
                    help="a pool CSV; give it once for each file (default: the two of POOLS)")
    ap.add_argument("--out", type=Path, default=HERE / "evidence.csv")
    ap.add_argument("--counts", type=Path, default=HERE / "counts.txt")
    ap.add_argument("--checks", type=Path, default=HERE / "checks.txt")
    args = ap.parse_args(argv)

    frames = args.frame or FRAMES
    frame_rows = load_frame(*frames)
    facts, problems = build(frame_rows, pools=args.pool or POOLS)
    facts.sort(key=lambda f: (f["project"], f["fact_type"], f["fact"], f["status"], f["pointer"]))
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(facts)
    shown = ", ".join(rel(f.resolve()) if f.resolve().is_relative_to(ROOT) else str(f) for f in frames)
    args.counts.write_text(f"frame: {shown}\n"
                           + counts_text(frame_rows, facts), encoding="utf-8")
    args.checks.write_text("".join(p + "\n" for p in problems) or "no problems\n", encoding="utf-8")
    bad = [p for p in problems if not p.startswith("info:")]
    print(f"OK {args.out}: {len(facts)} facts for {len(frame_rows)} projects; "
          f"{len(bad)} join checks differ, {len(problems) - len(bad)} info lines (see {args.checks.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
