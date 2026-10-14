#!/usr/bin/env python3
"""The exclusion reason for each pool row that S3 or the S4 default-branch step
lost, from the classes of ../../clone-failures-20261009 (decided 2026-10-09).

A row that has a GitHub row of the same project in the pool (dupes.tsv) gets
"duplicate of <name_with_owner>". The 19 Savannah rows of url_map.tsv get no
reason here: S3 v2 measures them at the published clone URL, and their reason
comes from that measurement.

Rows that S3 v2 measured and that failed there get the reason of their v2 error.

Output: reasons.tsv (pool_key, reason, basis). funnel.py --v2 reads it and
puts the reason in place of the first-pass text; the step that removes the row
does not change.
"""
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEL = HERE.parent.parent
CF = SEL / "clone-failures-20261009"

BY_CLASS = {
    "github-empty": "empty repository (no commit)",
    "github-no-default-branch": "no default branch commit at the snapshot",
    "org-url-not-repo": "roster names a GitHub organization, not a repository",
    "svn-not-git": "SVN, not git",
    "release-dir-not-repo": "release directory, not a repository",
    "no-head-ref": "empty repository (no refs)",
    "auth-prompt": "private or removed (the host asks for a login)",
    "no-repo-yet": "no repository created (the host says it does not exist yet)",
    "repo-not-found": "moved or removed (the host says not found)",
    "rate-limit-429": "the host blocks our IP address (Codeberg, HTTP 429)",
    "tree-404-commit-gone": "deleted after the snapshot (GitHub 404)",
}
HOST_GONE = {
    "git.apache.org": "host retired (git.apache.org refuses connections)",
    "cgit.kde.org": "host retired (cgit.kde.org has no DNS name)",
    "git.orfeo-toolbox.org": "host retired (git.orfeo-toolbox.org has no DNS name)",
}
SITE = "roster names a site or a group, not a repository"
# The web-page rows: one decision for each recorded URL (pages in pages/, fetch.tsv).
WEB = {
    "http://cgit.openembedded.org": SITE, "https://code.bioconductor.org/": SITE,
    "https://git.adelielinux.org/": SITE, "https://git.archlinux32.org/": SITE,
    "https://git.coretoolchain.dev/": SITE, "https://git.kernel.org/": SITE,
    "https://git.yoctoproject.org/": SITE, "https://gitweb.gentoo.org/": SITE,
    "https://gerrit.o-ran-sc.org/r/": SITE, "https://review.tizen.org/git/": SITE,
    "https://gitlab.archlinux.org/archlinux": SITE, "https://gitlab.com/automotivegradelinux": SITE,
    "https://gitlab.com/cip-project": SITE, "https://gitlab.com/digiagriapp/": SITE,
    "https://gitlab.com/librehealth": SITE, "https://gitlab.com/open19": SITE,
    "https://gitlab.com/smc": SITE, "https://gitlab.com/unimatrix": SITE,
    "https://gitlab.freedesktop.org/groups/xorg": SITE, "https://sourceforge.net/p/mingw/_list/git": SITE,
    "https://carvel.dev": SITE + " (the page links the GitHub organization carvel-dev)",
    "https://score.dev": SITE + " (the page links the GitHub organization score-spec)",
    "https://ccadb.org": "web site; the page names no repository",
    "https://oaca-project.github.io/": "web site; the page names no repository",
    "https://cntt-n.github.io/CNTT/": "web page removed (HTTP 404 on 2026-10-10)",
    "http://rasdaman.org/browser/": "web page removed (HTTP 404 on 2026-10-10)",
    "https://fair.pm": "the page names 2 repositories (fairpm/fair-plugin, fairpm/fair-protocol); "
                       "neither has C, C++, Java or Rust in Linguist",
    "https://trac.osgeo.org/osgeo4w/browser": "Trac browser; the page publishes no git URL",
    "https://sourceforge.net/p/bioweka/code/": "CVS, not git (the SourceForge code page)",
    "http://www.sourceforge.net/projects/skam": "CVS, not git (the roster note)",
    "https://source.squeak.org/inbox.html": "Monticello, not git (the roster note)",
    "http://code.google.com/p/biophp/": "service closed (Google Code archive)",
    "https://doi.org/10.5281/zenodo.4719684": "archive record, not a repository",
    "http://git.linuxfoundation.org/?p=diamon/minicoredumper.git;":
        "host retired (redirects to the GitHub organization linuxfoundation)",
    "http://git.linuxfoundation.org/?p=ltsi-kernel.git;a=summary":
        "host retired (redirects to the GitHub organization linuxfoundation)",
    "https://savannah.gnu.org/projects/acm": "CVS or SVN, not git (the Savannah group page)",
    "https://savannah.gnu.org/projects/cgicc": "CVS, not git (the Savannah group page)",
}


def main():
    dupes = {r["key"]: r["github_row"] for r in csv.DictReader(open(CF / "dupes.tsv"), delimiter="\t")}
    mapped = {r["pool_key"] for r in csv.DictReader(open(HERE / "url_map.tsv"), delimiter="\t")}
    out, missing = [], []
    for r in csv.DictReader(open(CF / "failures.csv")):
        if r["stage"] not in ("S3 measure", "S4 default branch commit"):
            continue
        key, cls, url = r["key"], r["class"], r["url"]
        if key in mapped:
            continue
        if key in dupes:
            reason, basis = f"duplicate of {dupes[key]}", "dupes.tsv (exact-name rule)"
        elif cls in BY_CLASS:
            reason, basis = BY_CLASS[cls], f"class {cls}"
        elif cls == "host-unreachable" and r["host"] in HOST_GONE:
            reason, basis = HOST_GONE[r["host"]], "probes 2026-10-09"
        elif cls == "host-unreachable" and "savannah" in r["host"]:
            reason, basis = "no git page found for this Savannah repository", "url_unmapped.tsv"
        elif cls == "web-page-or-group-url" and url in WEB:
            reason, basis = WEB[url], "pages/ and fetch.tsv, roster note"
        else:
            missing.append((key, cls, url))
            continue
        out.append((key, reason, basis))
    # Rows that S3 v2 measured (the GNU roster v2 and the Savannah rows) and that failed there.
    v2 = {}
    for line in (SEL / "s3-measure/v2/clones.jsonl").open():
        d = __import__("json").loads(line)
        v2[d["pool_key"]] = d
    done = {k for k, _, _ in out}
    for key, d in sorted(v2.items()):
        if d["status"] == "ok" or key in done:
            continue
        e = d.get("error", "")
        if "couldn't find remote ref HEAD" in e:
            reason = "empty repository (no refs)"
        elif "returned error: 500" in e:
            reason = "the host answers HTTP 500"
        elif "dumb http transport does not support shallow" in e:
            reason = "the host serves only dumb HTTP (no shallow fetch, the S3 method)"
        else:
            reason = "clone failed: " + " ".join(e.split())[-80:]
        out.append((key, reason, f"s3-measure/v2/clones.jsonl ({d['repo_url']}, {d['fetched_at']})"))
    with open(HERE / "reasons.tsv", "w") as f:
        f.write("pool_key\treason\tbasis\n")
        for row in out:
            f.write("\t".join(row) + "\n")
    print(len(out), "reasons;", len(mapped), "rows measured again;", len(missing), "with no decision")
    for m in missing:
        print("  no decision:", m)


if __name__ == "__main__":
    main()
