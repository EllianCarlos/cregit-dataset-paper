#!/usr/bin/env python3
"""Parse the raw downloads under ~/tmp/rosters/raw/<org>/ into ~/tmp/rosters/<org>.csv.
Re-runnable offline: reads only files saved under raw/. fetched_at = file mtime (UTC)."""
import csv, glob, html, json, os, re, sys, time
import yaml

R = os.path.expanduser("~/tmp/rosters")
RAW = os.path.join(R, "raw")
HDR = ["org_key", "org_kind", "project", "repo_url", "github_slug", "roster_status", "source_url", "fetched_at", "note"]
STATS = {}


def ts(path):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.path.getmtime(path)))


def write(org, rows):
    seen, out = set(), []
    for r in rows:
        k = (r["project"], r["repo_url"], r.get("_dedup", ""))
        if r["repo_url"] and k in seen:
            continue
        seen.add(k)
        out.append(r)
    with open(os.path.join(R, org + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=HDR, extrasaction="ignore")
        w.writeheader()
        for r in out:
            r.setdefault("org_key", org)
            r.setdefault("org_kind", "foundation")
            w.writerow({k: (r.get(k) or "") for k in HDR})
    STATS[org] = {
        "projects": len({r["project"] for r in out}),
        "rows": len(out),
        "with_repo": sum(1 for r in out if r.get("repo_url")),
        "with_slug": sum(1 for r in out if r.get("github_slug")),
    }


def gh_slug(url):
    """owner/repo from a github.com URL naming a repository (two path segments)."""
    if not url:
        return ""
    m = re.match(r"^(?:git\+)?(?:https?|git)://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+)", url.strip()) or \
        re.match(r"^(?:https?://)?git@github\.com:([^/\s]+)/([^/\s#?]+)", url.strip())
    if not m:
        return ""
    owner, repo = m.group(1), re.sub(r"\.git$", "", m.group(2))
    if not repo or owner.lower() in ("orgs", "apache?q=datasketches"):
        return ""
    return owner + "/" + repo


# ---------------------------------------------------------------- ASF family
ASF = os.path.join(RAW, "asf")
U_PROJ = "https://projects.apache.org/json/foundation/projects.json"
U_REPO = "https://projects.apache.org/json/foundation/repositories.json"
U_COMM = "https://projects.apache.org/json/foundation/committees.json"
U_POD = "https://whimsy.apache.org/public/public_podlings.json"
U_RET = "https://whimsy.apache.org/public/committee-retired.json"

projects = json.load(open(os.path.join(ASF, "projects.json")))
repos = json.load(open(os.path.join(ASF, "repositories.json")))
committees = json.load(open(os.path.join(ASF, "committees.json")))
podlings = json.load(open(os.path.join(RAW, "asf-incubator", "public_podlings.json")))["podling"]
retired = json.load(open(os.path.join(RAW, "asf-attic", "committee-retired.json")))["retired"]
T_PROJ, T_REPO = ts(os.path.join(ASF, "projects.json")), ts(os.path.join(ASF, "repositories.json"))
T_POD = ts(os.path.join(RAW, "asf-incubator", "public_podlings.json"))
T_RET = ts(os.path.join(RAW, "asf-attic", "committee-retired.json"))
cname = {c["id"]: c["name"] for c in committees}
cids = sorted(cname, key=len, reverse=True)
rids = sorted(retired, key=len, reverse=True)
pids = sorted(podlings, key=len, reverse=True)


def longest_prefix(key, ids):
    for i in ids:
        if key == i or key.startswith(i + "-"):
            return i
    return None


def asf_repo_name(url):
    """Repository name from an apache.org git URL (gitbox, git-wip-us, git.apache.org)."""
    u = re.sub(r"^git:(?=https?:)", "", url.strip())
    if not re.search(r"(gitbox|git-wip-us|git)\.apache\.org", u):
        return None
    m = re.search(r"[?;&]p=([^;&]+?)(?:\.git)?(?:[;&]|$)", u) or re.search(r"/repos/asf/([^/?]+?)(?:\.git)?/?$", u) \
        or re.search(r"git\.apache\.org/([^/?]+?)(?:\.git)?/?$", u)
    return m.group(1) if m else None


def asf_repo_row(url):
    """(repo_url, github_slug, note, repositories.json key or None) for a DOAP repository entry."""
    u = re.sub(r"^git:(?=https?:)", "", url.strip())
    name = asf_repo_name(u)
    if name and name in repos and "gitbox.apache.org" in repos[name]:
        note = "" if "gitbox" in u else "DOAP gives legacy URL %s; matched repositories.json key %s" % (u, name)
        return repos[name], "apache/" + name, note, name
    if name:
        return u, "", "apache.org git URL not found in repositories.json; no slug", None
    s = gh_slug(u)
    if s:
        key = s.split("/", 1)[1] if s.lower().startswith("apache/") else None
        return "https://github.com/" + s, s, "", key if key in repos else None
    return u, "", "svn or non-git URL; no GitHub slug" if "svn" in u else "", None


covered = set()   # repositories.json keys named by some DOAP file
asf_rows, attic_doap = [], {}
for key, p in projects.items():
    reps = [x for x in p.get("repository", []) if isinstance(x, str)]
    odd = [x for x in p.get("repository", []) if not isinstance(x, str)]
    pmc = p["pmc"]
    if pmc == "attic":
        attic_doap[key] = p
        for x in reps:
            r = asf_repo_row(x)
            if r[3]:
                covered.add(r[3])
        continue
    base = "PMC %s" % pmc + ("" if key == pmc else "; sub-project of PMC")
    if not reps:
        n = base + "; DOAP lists no repository" + ("; non-URL repository entries: %s" % json.dumps(odd) if odd else "")
        asf_rows.append(dict(project=p["name"], repo_url="", github_slug="", roster_status="", source_url=U_PROJ, fetched_at=T_PROJ, note=n))
    for x in reps:
        url, slug, note, rk = asf_repo_row(x)
        if rk:
            covered.add(rk)
        asf_rows.append(dict(project=p["name"], repo_url=url, github_slug=slug, roster_status="", source_url=U_PROJ,
                             fetched_at=T_PROJ, note="; ".join(filter(None, [base, "DOAP repository", note]))))

uncl = {"none": []}
pod_repos, attic_repos = {}, {}
for k, url in sorted(repos.items()):
    slug = "apache/" + k if "gitbox.apache.org" in url else ""
    c = longest_prefix(k, cids)
    if c:
        if k in covered:
            continue
        asf_rows.append(dict(project=cname[c], repo_url=url, github_slug=slug, roster_status="", source_url=U_REPO, fetched_at=T_REPO,
                             note="PMC %s; repositories.json key %s assigned to PMC by name prefix (not named in any DOAP)" % (c, k)))
        continue
    r = longest_prefix(k, rids)
    if r:
        attic_repos.setdefault(r, []).append((k, url, slug))
        continue
    p = longest_prefix(k, pids)
    if p:
        pod_repos.setdefault(p, []).append((k, url, slug))
        continue
    uncl["none"].append(k)
write("asf", asf_rows)
STATS["asf"]["unassigned_repos"] = len(uncl["none"])
STATS["asf"]["unassigned_examples"] = uncl["none"][:8]

# asf-incubator
rows = []
for k, p in sorted(podlings.items()):
    st = p.get("status", "")
    dates = "start %s, end %s" % (p.get("startdate", ""), p.get("enddate", "")) if p.get("enddate") else "start %s" % p.get("startdate", "")
    if k in pod_repos:
        for rk, url, slug in pod_repos[k]:
            rows.append(dict(project=p["name"], repo_url=url, github_slug=slug, roster_status=st, source_url=U_POD, fetched_at=T_POD,
                             note="podling id %s; %s; repo from %s key %s by name prefix" % (k, dates, U_REPO, rk)))
    elif st == "graduated" and k in repos:
        url = repos[k]
        slug = "apache/" + k if "gitbox.apache.org" in url else ""
        owner = "TLP %s" % k if k in cname else ("Attic project %s" % k if k in retired else "repositories.json")
        rows.append(dict(project=p["name"], repo_url=url, github_slug=slug, roster_status=st, source_url=U_POD, fetched_at=T_POD,
                         note="podling id %s; %s; graduated: repo is repositories.json key %s, now under %s" % (k, dates, k, owner)))
    else:
        rows.append(dict(project=p["name"], repo_url="", github_slug="", roster_status=st, source_url=U_POD, fetched_at=T_POD,
                         note="podling id %s; %s; no repositories.json key matches this podling id" % (k, dates)))
write("asf-incubator", rows)

# asf-attic
rows = []
doap_by_id = {}
for key, p in attic_doap.items():
    rid = key[len("attic-"):] if key.startswith("attic-") else key
    doap_by_id.setdefault(rid, []).append(p)
for k, v in sorted(retired.items()):
    base = "retired %s; established %s" % (v.get("retired_date") or v.get("retired", ""), v.get("established_date") or v.get("established", ""))
    got = False
    for rk, url, slug in attic_repos.get(k, []):
        rows.append(dict(project=v["display_name"], repo_url=url, github_slug=slug, roster_status="attic", source_url=U_RET, fetched_at=T_RET,
                         note=base + "; repo from %s key %s by name prefix" % (U_REPO, rk)))
        got = True
    for p in doap_by_id.get(k, []):
        for x in [x for x in p.get("repository", []) if isinstance(x, str)]:
            url, slug, note, rk = asf_repo_row(x)
            if rk and any(rk == a[0] for a in attic_repos.get(k, [])):
                continue
            rows.append(dict(project=v["display_name"], repo_url=url, github_slug=slug, roster_status="attic", source_url=U_RET, fetched_at=T_RET,
                             note="; ".join(filter(None, [base, "repo from DOAP in %s (pmc attic)" % U_PROJ, note]))))
            got = True
    if not got:
        rows.append(dict(project=v["display_name"], repo_url="", github_slug="", roster_status="attic", source_url=U_RET, fetched_at=T_RET,
                         note=base + "; no repository found in repositories.json or attic DOAP"))
for rid in sorted(set(doap_by_id) - set(retired)):
    for p in doap_by_id[rid]:
        reps = [x for x in p.get("repository", []) if isinstance(x, str)]
        for x in reps or [""]:
            url, slug, note, rk = asf_repo_row(x) if x else ("", "", "DOAP lists no repository", None)
            rows.append(dict(project=p["name"], repo_url=url, github_slug=slug, roster_status="attic", source_url=U_PROJ, fetched_at=T_PROJ,
                             note="; ".join(filter(None, ["projects.json key attic-%s has pmc attic; not a retired committee in committee-retired.json (retired sub-project)" % rid, note]))))
write("asf-attic", rows)
STATS["asf-attic"]["doap_ids_not_in_retired"] = sorted(set(doap_by_id) - set(retired))

# ---------------------------------------------------------------- Eclipse
E = os.path.join(RAW, "eclipse")
rows = []
nproj = 0
for n in range(1, 100):
    f = os.path.join(E, "p%d.json" % n)
    if not os.path.exists(f):
        break
    src = "https://projects.eclipse.org/api/projects?page=%d&pagesize=100" % n
    T = ts(f)
    for p in json.load(open(f)):
        nproj += 1
        base = "project_id %s; top_level_project %s" % (p["project_id"], p.get("top_level_project", ""))
        prow = []
        for r in p.get("github_repos") or []:
            u = r["url"].rstrip("/")
            prow.append(dict(repo_url=u, github_slug=gh_slug(u), note=base + "; github_repos"))
        org = (p.get("github") or {}).get("org") or ""
        if org:
            ign = set(x.lower() for x in (p["github"].get("ignored_repos") or []))
            g = json.load(open(os.path.join(E, "github-orgs", org + ".json")))
            if not g["found"]:
                prow.append(dict(repo_url="https://github.com/" + org, github_slug="", note=base + "; github.org declared but org not found on GitHub"))
            for r in g["repos"]:
                if r["nameWithOwner"].lower() in ign or r["name"].lower() in ign:
                    continue
                flags = ",".join(x for x, b in (("archived", r["isArchived"]), ("fork", r["isFork"]), ("mirror", r["isMirror"])) if b)
                prow.append(dict(repo_url=r["url"], github_slug=r["nameWithOwner"],
                                 note=base + "; repo of declared github.org %s listed via GitHub GraphQL %s%s" % (org, g["fetched_at"], "; " + flags if flags else "")))
        grp = (p.get("gitlab") or {}).get("project_group") or ""
        if grp:
            ign = [x for x in (p["gitlab"].get("ignored_sub_groups") or [])]
            gl = json.load(open(os.path.join(E, "gitlab-groups", grp.replace("/", "_") + ".json")))
            kept = [x for x in gl if not any(x["path_with_namespace"] == i or x["path_with_namespace"].startswith(i + "/") for i in ign)]
            for x in kept:
                prow.append(dict(repo_url=x["web_url"], github_slug="",
                                 note=base + "; repo of declared gitlab.project_group %s listed via gitlab.eclipse.org API%s" % (grp, "; archived" if x.get("archived") else "")))
            if not kept:
                prow.append(dict(repo_url="https://gitlab.eclipse.org/" + grp, github_slug="", note=base + "; gitlab.project_group declared, API lists no projects in it"))
        if not prow:
            prow.append(dict(repo_url="", github_slug="", note=base + "; API gives no github_repos, github.org or gitlab group"))
        for r in prow:
            r.update(project=p["name"], roster_status=p.get("state", ""), source_url=src, fetched_at=T)
            rows.append(r)
write("eclipse", rows)
STATS["eclipse"]["api_projects"] = nproj

# ---------------------------------------------------------------- OpenInfra
O = os.path.join(RAW, "openinfra")
U_GOV = "https://opendev.org/openstack/governance/raw/branch/master/reference/"
MIRROR = "GitHub mirror per openstack/project-config job openstack-upload-github-mirror ('Mirrors official projects to github's openstack org') and playbooks/maintain-github-mirror/github_manager.py"
rows = []
gov = yaml.safe_load(open(os.path.join(O, "projects.yaml")))
for team, v in gov.items():
    for dn, d in (v.get("deliverables") or {}).items():
        for r in d.get("repos", []):
            st = "deprecated" if d.get("deprecated") else ""
            slug = r if r.startswith("openstack/") else ""
            rows.append(dict(project=team, repo_url="https://opendev.org/" + r, github_slug=slug, roster_status=st,
                             source_url=U_GOV + "projects.yaml", fetched_at=ts(os.path.join(O, "projects.yaml")),
                             note="OpenStack project team; deliverable %s; leadership_type %s%s; %s" % (dn, v.get("leadership_type", ""), "; deprecated %s" % d["deprecated"] if d.get("deprecated") else "", MIRROR)))
for fn, kind in (("sigs-repos.yaml", "OpenStack SIG"), ("technical-committee-repos.yaml", "OpenStack Technical Committee")):
    y = yaml.safe_load(open(os.path.join(O, fn)))
    for grp, lst in y.items():
        for e in lst:
            r = e["repo"]
            rows.append(dict(project=grp, repo_url="https://opendev.org/" + r, github_slug=r if r.startswith("openstack/") else "",
                             roster_status="", source_url=U_GOV + fn, fetched_at=ts(os.path.join(O, fn)),
                             note="%s repository; %s" % (kind, MIRROR)))
U_OI = "https://openinfra.org/projects/"
T_OI = ts(os.path.join(O, "openinfra-projects.html"))
k = json.load(open(os.path.join(O, "github-orgs", "kata-containers.json")))
for r in k["repos"]:
    flags = ",".join(x for x, b in (("archived", r["isArchived"]), ("fork", r["isFork"])) if b)
    rows.append(dict(project="Kata Containers", repo_url=r["url"], github_slug=r["nameWithOwner"], roster_status="confirmed project", source_url=U_OI, fetched_at=T_OI,
                     note="openinfra.org 'Code' link is https://github.com/kata-containers; repo listed via GitHub GraphQL %s%s" % (k["fetched_at"], "; " + flags if flags else "")))
for proj, org, why in (("StarlingX", "starlingx", "openinfra.org 'Code' link is https://opendev.org/starlingx"),
                       ("Zuul", "zuul", "openinfra.org 'Code' link https://git.zuul-ci.org/ redirects to opendev.org/; zuul-ci.org links https://opendev.org/zuul/zuul, so the opendev org zuul is used")):
    for f in sorted(glob.glob(os.path.join(O, "opendev-%s-repos-p*.json" % org))):
        for r in json.load(open(f)):
            rows.append(dict(project=proj, repo_url=r["html_url"], github_slug="", roster_status="confirmed project", source_url=U_OI, fetched_at=T_OI,
                             note="%s; repo listed via https://opendev.org/api/v1/orgs/%s/repos%s; no GitHub mirror named" % (why, org, "; archived" if r.get("archived") else "")))
write("openinfra", rows)

# ---------------------------------------------------------------- The Document Foundation
D = os.path.join(RAW, "documentfoundation")
gp = json.loads(open(os.path.join(D, "gerrit-projects.json"), encoding="utf-8").read()[4:])
rows = []
U_G = "https://gerrit.libreoffice.org/projects/?d&t"
U_W = "https://wiki.documentfoundation.org/Development/Git_For_LibreOffice_Developers/en"
for pid, v in sorted(gp.items()):
    if pid in ("All-Projects", "All-Users") or pid.endswith("-ACL-Template"):
        continue
    desc = (v.get("description") or "").replace("\n", " ").strip()
    slug, note = "", ""
    if pid == "core":
        slug, note = "libreoffice/core", "GitHub mirror named on %s ('the LibreOffice mirror in GitHub': https://github.com/libreoffice/core)" % U_W
    m = re.search(r"https://github\.com/([^/\s]+/[^/\s]+)", desc)
    if m:
        slug, note = m.group(1), "Gerrit description points to GitHub"
    rows.append(dict(project=pid, repo_url="https://git.libreoffice.org/" + pid, github_slug=slug, roster_status=v.get("state", ""),
                     source_url=U_G, fetched_at=ts(os.path.join(D, "gerrit-projects.json")),
                     note="; ".join(filter(None, ["Gerrit project on gerrit.libreoffice.org", "description: " + desc[:120] if desc else "", note]))))
write("documentfoundation", rows)

# ---------------------------------------------------------------- NetBSD
N = os.path.join(RAW, "netbsd")
U_NW = "https://wiki.netbsd.org/github/"
T_N = ts(os.path.join(N, "wiki.netbsd.org_github.html"))
rows = []
for mod in ("src", "xsrc", "pkgsrc"):
    rows.append(dict(project=mod, repo_url="anoncvs@anoncvs.NetBSD.org:/cvsroot", github_slug="NetBSD/" + mod, roster_status="", source_url=U_NW, fetched_at=T_N,
                     note="canonical repo is CVS module %s (CVSROOT from https://www.netbsd.org/docs/guide/en/chap-fetch.html); wiki lists read-only official GitHub copy https://github.com/NetBSD/%s and Fossil https://%s.fossil.NetBSD.org/" % (mod, mod, mod)))
write("netbsd", rows)

# ---------------------------------------------------------------- FreeBSD
U_FB = "https://docs.freebsd.org/en/books/handbook/mirrors/"
T_FB = ts(os.path.join(RAW, "freebsd", "handbook-mirrors.html"))
rows = [dict(project=r, repo_url="https://git.FreeBSD.org/%s.git" % r, github_slug="freebsd/freebsd-" + r, roster_status="", source_url=U_FB, fetched_at=T_FB,
             note="Handbook Table 1 (git.FreeBSD.org); 'External mirrors ... maintained by the project members' lists https://github.com/freebsd/freebsd-%s" % r)
        for r in ("src", "doc", "ports")]
write("freebsd", rows)

# ---------------------------------------------------------------- OSGeo
G = os.path.join(RAW, "osgeo")
U_OS = "https://www.osgeo.org/wp-admin/admin-ajax.php?action=getItems&postType=project&limit=50&offset=%d"
U_WI = "https://wiki.osgeo.org/w/index.php?title=Incubation_Committee&action=raw"
wk = open(os.path.join(G, "wiki-Incubation_Committee.wikitext"), encoding="utf-8").read()
inc_sec = wk[wk.index("== Incubation =="):wk.index("== Graduated ==")]
incub = re.findall(r"^=== (.+?) ===", inc_sec, re.M)
grad_sec = wk[wk.index("== Graduated =="):wk.index("== Withdrawn ==")]
TYPE = {"osgeo": "OSGeo Project (projectType osgeo)", "community": "OSGeo Community (projectType community)"}
rows, listed = [], set()
for f in sorted(glob.glob(os.path.join(G, "ajax-getItems-offset*.json")), key=lambda x: int(re.search(r"offset(\d+)", x).group(1))):
    off = int(re.search(r"offset(\d+)", f).group(1))
    for it in json.load(open(f))["data"]:
        title = html.unescape(it["title"])
        listed.add(title.lower())
        src = (it.get("sourceUrl") or "").strip()
        notes = ["site page %s" % it["permalink"], "projectType %s" % it.get("projectType")]
        if it.get("projectType") not in ("osgeo", "community"):
            notes.append("listed on osgeo.org but not badged OSGeo Project or OSGeo Community")
        if any(t.lower() == title.lower() or t.lower().replace(" ", "") == title.lower().replace(" ", "") for t in incub):
            notes.append("in incubation per wiki Incubation_Committee")
        slug = gh_slug(src)
        if src and not slug and "github.com" in src:
            notes.append("sourceUrl is a GitHub org/user page, not a repository")
        st = TYPE.get(it.get("projectType"), it.get("projectType") or "")
        if "in incubation per wiki Incubation_Committee" in notes:
            st = "incubating"
        rows.append(dict(project=title, repo_url=src, github_slug=slug, roster_status=st, source_url=U_OS % off, fetched_at=ts(f), note="; ".join(notes)))
for t in incub:
    if t.lower() not in listed and t.lower().replace(" ", "") not in {x.replace(" ", "") for x in listed}:
        rows.append(dict(project=t, repo_url="", github_slug="", roster_status="incubating", source_url=U_WI, fetched_at=ts(os.path.join(G, "wiki-Incubation_Committee.wikitext")),
                         note="listed under '== Incubation ==' on wiki Incubation_Committee but not in osgeo.org project directory; wiki gives no repository"))
write("osgeo", rows)
STATS["osgeo"]["wiki_incubating"] = incub

# ---------------------------------------------------------------- OBF
B = os.path.join(RAW, "obf")
U_OB = "https://www.open-bio.org/projects/"
t = open(os.path.join(B, "projects.html"), encoding="utf-8").read()
body = t[t.find("<body"):]
start = body.find("Member Projects")
end = body.find("</ul>", body.find("Retired Projects"))
sec = body[start:end]
parts = re.split(r"<h\d[^>]*>(.*?)</h\d>", sec)
STATUS = {"Member Projects": "member", "Affiliated Projects": "affiliated", "Other Related Projects": "other related", "Retired Projects": "retired"}
rows = []
blocks = [("Member Projects", parts[0])] + [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
for head, blk in blocks:
    st = STATUS.get(re.sub(r"<[^>]+>", "", head).strip(), head)
    items = re.findall(r"<(?:p|li)>(.*?)</(?:p|li)>", blk, re.S)
    for it in items:
        anchors = re.findall(r'<a\s[^>]*?href=("[^"]*"|[^\s>]+)[^>]*>(.*?)</a>', it, re.S)
        text = html.unescape(re.sub(r"<[^>]+>", "", it)).strip()
        if st == "retired" or st == "other related":
            name = text.split(":")[0].strip()
            a = [x for x in anchors if html.unescape(re.sub(r"<[^>]+>", "", x[1])).strip() == name]
        else:
            if not anchors:
                continue
            first = anchors[0]
            name = html.unescape(re.sub(r"<[^>]+>", "", first[1])).strip()
            if name in ("Perl",):
                continue
            a = [first]
        if not name:
            continue
        home = a[0][0].strip('"') if a else ""
        repo, slug, note = "", "", ""
        for href, _ in anchors:
            href = href.strip('"')
            s = gh_slug(href)
            if s:
                repo, slug = "https://github.com/" + s, s
                note = "repository taken from link %s on the page" % href
                break
        rows.append(dict(project=name, repo_url=repo, github_slug=slug, roster_status=st, source_url=U_OB, fetched_at=ts(os.path.join(B, "projects.html")),
                         note="; ".join(filter(None, ["page links %s" % home if home and home != repo else "", note, "" if repo else "page gives no repository"]))))
write("obf", rows)

# ---------------------------------------------------------------- X.Org
X = os.path.join(RAW, "xorg")
rows = []
for f in sorted(glob.glob(os.path.join(X, "projects-p*.json"))):
    pg = int(re.search(r"-p(\d+)", f).group(1))
    for p in json.load(open(f)):
        rows.append(dict(project=p["path_with_namespace"], repo_url=p["web_url"], github_slug="", roster_status="archived" if p.get("archived") else "active",
                         source_url="https://gitlab.freedesktop.org/api/v4/groups/xorg/projects?include_subgroups=true&per_page=100&page=%d" % pg, fetched_at=ts(f),
                         note="freedesktop GitLab group xorg ('X.Org and X11 protocol, server, driver, library, and application development'), subgroup %s; no GitHub mirror named" % p["namespace"]["full_path"]))
write("xorg", rows)

json.dump(STATS, open(os.path.join(R, "raw", "foundations-stats.json"), "w"), indent=1)
print(json.dumps(STATS, indent=1))
