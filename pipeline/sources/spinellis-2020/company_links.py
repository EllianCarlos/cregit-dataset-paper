#!/usr/bin/env python3
"""Companies, their domains and their GitHub orgs, defined from Spinellis et al.

Input: enterprise-oss.tar.gz (Zenodo 10.5281/zenodo.3742962, MD5 in FETCH.tsv),
file enterprise_projects.txt. Spinellis et al. found each project from the
e-mail domain of its committers (heuristics sdtc, mcpc, mcve). For a project
of a company that is in the Fortune Global 500 (fg500) or files SEC forms
10-K or 20-F, they give the company name.

Definitions (the "strong" rows are those with fg500, sec10k or sec20f true and
a company name):

  company          a company_name of a strong row
  company domain   a dominant_domain of the strong rows of that company
  project link     a strong row: Spinellis et al. link the project to the company
  org link         a GitHub owner and a company, kept if all rules pass:
    L1  the owner is linked to one company only in the strong rows
        (an owner with several companies is a shared project, e.g. apache)
    L2  the company is on more than half of the owner's rows in the
        enterprise set (rows with no company count against it)
    L3  at the snapshot, the owner is a GitHub Organization, not a User
  corroboration (recorded, not a rule): at the snapshot, GitHub marks the org
  as verified, and the host of its website is a company domain or a subdomain
  of one.

Outputs, in the folder of this script:
  companies.csv    company, fg500, sec10k, sec20f, cik, domains (with row counts),
                   strong rows, owners
  org_links.csv    owner, company, strong rows, rows of the owner, companies of
                   the owner, owner_type, is_verified, website_url,
                   website_on_company_domain, L1, L2, L3, link (kept or not),
                   reason, fetched_at
"""
import csv
import datetime as dt
import json
import subprocess
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
COLS = ("url project_id sdtc mcpc mcve star_number commit_count files lines pull_requests "
        "github_repo_creation earliest_commit most_recent_commit committer_count author_count "
        "dominant_domain dominant_domain_committer_commits dominant_domain_author_commits "
        "dominant_domain_committers dominant_domain_authors cik fg500 sec10k sec20f project_name "
        "owner_login company_name owner_company license").split()


def load():
    with tarfile.open(HERE / "enterprise-oss.tar.gz") as t:
        text = t.extractfile("enterprise_projects.txt").read().decode("utf-8", "replace")
    return [dict(zip(COLS, l.split("\t"))) for l in text.splitlines()]


def owners_on_github(logins):
    """owner type, verified flag and website for each login, at the snapshot."""
    out, logins = {}, sorted(logins)
    for k in range(0, len(logins), 50):
        batch = logins[k:k + 50]
        parts = [f'r{i}: repositoryOwner(login: {json.dumps(l)}) {{ __typename login '
                 f'... on Organization {{ isVerified websiteUrl }} ... on User {{ websiteUrl }} }}'
                 for i, l in enumerate(batch)]
        p = subprocess.run(["gh", "api", "graphql", "-f", "query=query { " + " ".join(parts) + " }"],
                           capture_output=True, text=True)
        d = json.loads(p.stdout or "{}").get("data") or {}
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        for i, l in enumerate(batch):
            x = d.get(f"r{i}")
            out[l] = {"owner_type": x["__typename"] if x else "NOT_FOUND",
                      "is_verified": x.get("isVerified", "") if x else "",
                      "website_url": (x.get("websiteUrl") or "") if x else "", "fetched_at": now}
    return out


def main():
    rows = load()
    strong = [r for r in rows if "t" in (r["fg500"], r["sec10k"], r["sec20f"]) and r["company_name"]]
    rows_of_owner = Counter(r["owner_login"] for r in rows)

    comp = defaultdict(lambda: {"domains": Counter(), "owners": set(), "n": 0, "flags": set(), "cik": set()})
    owner_comp = defaultdict(Counter)
    for r in strong:
        c = comp[r["company_name"]]
        c["domains"][r["dominant_domain"]] += 1
        c["owners"].add(r["owner_login"])
        c["n"] += 1
        c["flags"].update(f for f in ("fg500", "sec10k", "sec20f") if r[f] == "t")
        if r["cik"]:
            c["cik"].add(r["cik"])
        owner_comp[r["owner_login"]][r["company_name"]] += 1

    with (HERE / "companies.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["company", "fg500", "sec10k", "sec20f", "cik", "domains", "strong_rows", "owners"])
        for name in sorted(comp):
            c = comp[name]
            w.writerow([name, "fg500" in c["flags"], "sec10k" in c["flags"], "sec20f" in c["flags"],
                        ";".join(sorted(c["cik"])), ";".join(f"{d}={n}" for d, n in c["domains"].most_common()),
                        c["n"], len(c["owners"])])

    gh = owners_on_github(owner_comp)
    with (HERE / "org_links.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["owner", "company", "strong_rows", "owner_rows", "owner_companies", "owner_type",
                    "is_verified", "website_url", "website_on_company_domain", "L1", "L2", "L3",
                    "link", "reason", "fetched_at"])
        for owner in sorted(owner_comp, key=str.lower):
            cs = owner_comp[owner]
            company, n = cs.most_common(1)[0]
            g = gh[owner]
            host = (urlparse(g["website_url"] if "//" in g["website_url"] else "//" + g["website_url"]).hostname or "").lower()
            doms = {d.lower() for d in comp[company]["domains"] if d}
            on_dom = bool(host) and any(host == d or host.endswith("." + d) for d in doms)
            l1 = len(cs) == 1
            l2 = l1 and n * 2 > rows_of_owner[owner]
            l3 = g["owner_type"] == "Organization"
            why = []
            if not l1:
                why.append(f"L1: linked to {len(cs)} companies")
            elif not l2:
                why.append(f"L2: {n} of the owner's {rows_of_owner[owner]} rows carry the company")
            if not l3:
                why.append(f"L3: owner is {g['owner_type']}")
            w.writerow([owner, company if l1 else ";".join(sorted(cs)), n, rows_of_owner[owner], len(cs),
                        g["owner_type"], g["is_verified"], g["website_url"], on_dom, l1, l2, l3,
                        "kept" if (l1 and l2 and l3) else "not kept", "; ".join(why), g["fetched_at"]])
    print(f"{len(comp)} companies, {len(owner_comp)} owners")


if __name__ == "__main__":
    main()
