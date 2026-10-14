#!/usr/bin/env python3
"""S5 evidence: pages from the company itself that link to its GitHub orgs.

Inputs: ../spinellis-2020/companies.csv (company domains) and
../spinellis-2020/org_links.csv (kept org links).

For each company, the script fetches a fixed list of URLs with curl, one at a
time, 2 s apart:
  - the website of each kept org of the company, as the org publishes it in
    its GitHub profile, if its host is a company domain or a subdomain of one.
No URL is guessed (decided 2026-10-06). The first run of 2026-10-06 also
fetched guessed patterns (opensource.<domain>, <domain>/opensource, ...);
their rows stay in fetch.tsv and raw/ as a record, but they give no evidence.
It saves each response unchanged (body and headers) in raw/, and writes one row
for each fetch to fetch.tsv. Then it reads each saved page for links to
github.com/<login>. An org gets company-page evidence only if a page that the
company serves (final URL on a company domain) links to its login.

Outputs: raw/, fetch.tsv, evidence.csv (org, company, page_url, final_url,
fetched_at), no_page.csv (kept orgs with no such page; the browser step
reads these). Resumable: a URL that is in fetch.tsv is not fetched again.
"""
import csv
import datetime as dt
import hashlib
import re
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
SP = HERE.parent / "spinellis-2020"
RAW = HERE / "raw"
UA = "Mozilla/5.0 (X11; Linux x86_64) research-dataset-fetch (cregit MSR dataset)"
GH_LINK = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9-]*)", re.I)


def host_of(u):
    return (urlparse(u if "//" in u else "//" + u).hostname or "").lower()


def on_domains(host, doms):
    return any(host == d or host.endswith("." + d) for d in doms)


def fetch(url, rows):
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    t = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    w = subprocess.run(["curl", "-sS", "-L", "--max-redirs", "5", "--max-time", "30", "-A", UA,
                        "-D", str(RAW / f"{key}.headers"), "-o", str(RAW / f"{key}.html"),
                        "-w", "%{http_code}\t%{url_effective}\t%{size_download}", url],
                       capture_output=True, text=True).stdout or "000\t\t0"
    status, final, size = (w.split("\t") + ["", "", ""])[:3]
    row = {"url": url, "status": status, "final_url": final, "bytes": size, "file": key, "fetched_at": t}
    with (HERE / "fetch.tsv").open("a") as f:
        f.write("\t".join(row[c] for c in ("url", "status", "final_url", "bytes", "file", "fetched_at")) + "\n")
    rows[url] = row
    time.sleep(2)


def main():
    RAW.mkdir(exist_ok=True)
    doms = {}
    for r in csv.DictReader(open(SP / "companies.csv", encoding="utf-8")):
        doms[r["company"]] = {re.sub(r"^www\.", "", d.split("=")[0].lower())
                              for d in r["domains"].split(";") if d.split("=")[0]}
    orgs = defaultdict(list)
    for r in csv.DictReader(open(SP / "org_links.csv", encoding="utf-8")):
        if r["link"] == "kept":
            orgs[r["company"]].append(r)

    rows = {}
    if (HERE / "fetch.tsv").exists():
        for l in open(HERE / "fetch.tsv"):
            u, s, fu, b, k, t = l.rstrip("\n").split("\t")
            rows[u] = {"url": u, "status": s, "final_url": fu, "bytes": b, "file": k, "fetched_at": t}

    plan = defaultdict(list)  # company -> urls
    for c in sorted(orgs):
        for o in orgs[c]:
            if o["website_url"] and on_domains(host_of(o["website_url"]), doms.get(c, ())):
                plan[c].append(o["website_url"])
        plan[c] = list(dict.fromkeys(plan[c]))
    total = sum(len(v) for v in plan.values())
    print(f"{len(plan)} companies, {total} URLs, {len(rows)} already fetched", flush=True)
    for c, urls in plan.items():
        for u in urls:
            if u not in rows:
                fetch(u, rows)

    ev, found = [], set()
    for c, urls in plan.items():
        logins = {o["owner"].lower(): o["owner"] for o in orgs[c]}
        for u in urls:
            r = rows[u]
            if r["status"] != "200" or not on_domains(host_of(r["final_url"]), doms.get(c, ())):
                continue
            html = (RAW / f"{r['file']}.html").read_text(errors="replace")
            for m in set(x.lower() for x in GH_LINK.findall(html)):
                if m in logins:
                    ev.append([logins[m], c, u, r["final_url"], r["fetched_at"]])
                    found.add((logins[m], c))
    with (HERE / "evidence.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["org", "company", "page_url", "final_url", "fetched_at"])
        w.writerows(sorted(ev))
    with (HERE / "no_page.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["org", "company", "website_url", "is_verified"])
        for c in sorted(orgs):
            for o in orgs[c]:
                if (o["owner"], c) not in found:
                    w.writerow([o["owner"], c, o["website_url"], o["is_verified"]])
    print(f"evidence rows {len(ev)}; orgs with a company page {len(found)}; "
          f"orgs without {sum(len(v) for v in orgs.values()) - len(found)}")


if __name__ == "__main__":
    main()
