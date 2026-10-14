#!/usr/bin/env python3
"""Map Savannah rows of pool.csv to the clone URL that Savannah publishes.

Chain of sources, each kept in pages/ with fetch.tsv: the roster note
(rosters/gnu.csv) names the Savannah group page, or the row itself is the
group page; the group page links its git page (/git/?group=NAME); the git page
gives the anonymous clone URL ("git clone ... https://git.savannah.gnu.org/git/NAME.git").
A row maps only if its git page gives exactly one URL whose NAME is the
repository name of the recorded URL (cgit rows) or the group name (page rows).
If the note names no group page, the GNU package page that the note names is
read for the git page link instead.
clone_url_git is the git:// form of the same repository: the Savannah guide
https://savannah.gnu.org/maintenance/UsingGit/ (fetched, in pages/) publishes
"git clone git://git.savannah.gnu.org/<group>.git", and the path is the one of
clone_url after "/git/". This machine reaches Savannah only over git:// (port
9418; ports 443 and 80 do not connect since 2026-10-09 22:58 UTC).
Output: url_map.tsv (pool_key, recorded_url, clone_url, source_url, fetched_at,
clone_url_git, clone_url_git_source)
and url_unmapped.tsv (pool_key, recorded_url, why).
"""
import csv
import html
import re
from pathlib import Path
from urllib.parse import urljoin

HERE = Path(__file__).resolve().parent
SEL = HERE.parent.parent
fetch = {r["url"]: r for r in csv.DictReader(open(HERE / "fetch.tsv"), delimiter="\t")}


GUIDE = "https://savannah.gnu.org/maintenance/UsingGit/"
GIT_SRC = f"{GUIDE} (fetched {fetch[GUIDE]['utc']}) + the repository path of clone_url"


def git_form(https_url):
    """git://git.savannah.gnu.org/<path> for https://git.savannah.(non)gnu.org/git/<path>."""
    return "git://git.savannah.gnu.org/" + https_url.split("/git/", 1)[1]


def page(url):
    r = fetch.get(url)
    if not r or r["status"] != "200":
        return None, r
    return open(HERE / "pages" / r["file"], encoding="utf-8", errors="replace").read(), r


def main():
    notes = {r["repo_url"].strip(): r for r in csv.DictReader(open(SEL / "rosters/gnu.csv", encoding="utf-8")) if r["repo_url"]}
    rows, miss = [], []
    for p in csv.DictReader(open(SEL / "s2-pool/pool.csv", encoding="utf-8")):
        if "savannah" not in p["host"]:
            continue
        rec = p["repo_url"]
        n = notes[rec]
        m = re.search(r"https?://savannah\.(?:non)?gnu\.org/projects/[^/ ;),\"]+/?", n["note"])
        group_page = m.group(0) if m else (rec if "/projects/" in rec else None)
        if not group_page:  # else the GNU package page that the note names, if it links a git page
            pk = re.search(r"package page (https://www\.gnu\.org/software/[^/ ]+/)", n["note"])
            group_page = pk.group(1) if pk else None
        if not group_page:
            miss.append([p["pool_key"], rec, "the roster note names no Savannah group page"])
            continue
        t, _ = page(group_page)
        if t is None:
            miss.append([p["pool_key"], rec, f"group page not fetched: {group_page}"])
            continue
        links = {urljoin(fetch[group_page]["final_url"] or group_page, html.unescape(x))
                 for x in re.findall(r'href="([^"]*/git/\?group=[^"]*)"', t)}
        if len(links) != 1:
            scm = sorted(set(re.findall(r'href="[^"]*/(cvs|svn|hg|bzr)/\?group=', t)))
            miss.append([p["pool_key"], rec, f"group page links no git page (other SCM: {','.join(scm) or 'none'})"])
            continue
        gp = links.pop()
        t2, r2 = page(gp)
        urls = sorted(set(re.findall(r"https://git\.savannah\.(?:non)?gnu\.org/git/[^\s<\"&]+?\.git", t2 or "")))
        name = re.search(r"/cgit/([^/]+?)\.git", rec)
        name = name.group(1) if name else group_page.rstrip("/").rsplit("/", 1)[1]
        hit = [u for u in urls if u.rsplit("/", 1)[1] == f"{name}.git"]
        if len(hit) != 1:
            miss.append([p["pool_key"], rec, f"git page {gp} gives {urls}, none or many for {name}"])
            continue
        rows.append([p["pool_key"], rec, hit[0], gp, r2["utc"], git_form(hit[0]), GIT_SRC])
    # A row with no mapping here: the GNU roster v2 (rosters/gnu.v2.csv, from the
    # Savannah list of GNU groups) can give its clone URL.
    v2 = {r["repo_url"]: r for r in csv.DictReader(open(SEL / "rosters/gnu.v2.csv", encoding="utf-8"))}
    still = []
    for key, rec, why in miss:
        g = v2.get(rec)
        if g and g["clone_url"]:
            rows.append([key, rec, g["clone_url"], "rosters/gnu.v2.csv: " + g["v2_source"], g["v2_fetched_at"],
                         git_form(g["clone_url"]), GIT_SRC])
        else:
            still.append([key, rec, why])
    miss = still
    with open(HERE / "url_map.tsv", "w") as f:
        f.write("pool_key\trecorded_url\tclone_url\tsource_url\tfetched_at\tclone_url_git\tclone_url_git_source\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    with open(HERE / "url_unmapped.tsv", "w") as f:
        f.write("pool_key\trecorded_url\twhy\n")
        for r in miss:
            f.write("\t".join(r) + "\n")
    print(len(rows), "mapped;", len(miss), "not mapped")
    for r in miss:
        print("  ", r)


if __name__ == "__main__":
    main()
