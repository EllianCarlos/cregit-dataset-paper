#!/usr/bin/env python3
"""Build the company database (S8). Version 3 (2026-10-16): offline sources, web results, and
two rounds of proposals for the top unmatched domains.

    build_companies.py [--out DIR] [--ctp DIR] [--ds DIR] [--psl FILE] [--web DIR]
                       [--memory-limit 3GB] [--threads 2]

This script reads only local files. It does not fetch from the web. The web results
(W1 GitHub orgs, W2 GitLab groups, W3 Wikidata, W4 SEC tickers, W5 GLEIF) come from the files
that fetch/s8_fetch.py wrote to ~/Projects/cregit-workspace/companies/fetch/normalized/.
The build also works without them, and without proposals/top_unmatched.v1.csv and .v2.csv.

Output (DIR is ~/Projects/cregit-workspace/companies by default):
  DIR/companies.duckdb        the tables company, company_alias, company_domain,
                              company_namespace and source_registry
  DIR/export/<table>.parquet  one Parquet file for each table
  DIR/export/conflicts.csv    the conflicts and the rows that the build did not use

The script writes each file to a temporary name first, then renames it. The rows are
sorted, so two runs on the same inputs give the same rows.

The tables follow PROPOSAL.md (sections 1, 3 and 4.1) and DECISIONS.md (D1 to D3).
README.md tells the inputs, the rules and the limits.

Rules for personal data: no table holds an e-mail address or a person name. The build
stops if a value of a table holds '@'. A company name from a source that nobody
reviewed (the CNCF rows and the proposals) is not used when it has the form of a
person name; conflicts.csv gives its domain only.
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import html
import io
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

HOME = Path.home()
DS_DEFAULT = HOME / "STUDY-REPOSITORY/dataset-selection"
CTP_DEFAULT = HOME / "Projects/cregit-token-pipeline"
OUT_DEFAULT = HOME / "Projects/cregit-workspace/companies"
WEB_DEFAULT = OUT_DEFAULT / "fetch/normalized"
PSL_GLOB = "/nix/store/*-publicsuffix-list-*/share/publicsuffix/public_suffix_list.dat"

KINDS = ("company", "consultancy", "foundation", "fiscal-sponsor", "nonprofit", "government",
         "academic", "project", "free-provider", "independent")
COMPANY_KINDS = ("company", "consultancy")
SECTOR = {"company": "S.11", "consultancy": "S.11", "foundation": "S.15",
          "fiscal-sponsor": "S.15", "nonprofit": "S.15", "government": "S.13",
          "academic": "", "independent": "S.14", "project": "", "free-provider": ""}
KIND_ALIAS = {"free_provider": "free-provider", "fiscal_sponsor": "fiscal-sponsor",
              "import": "project"}
BASIS_ORDER = ("sec-filer", "fortune-global-500", "registry-id", "wikidata-instance-of",
               "legal-form-in-name", "foundation-registry", "gov-or-edu-domain", "roster",
               "manual-review")

# Sources of the ctp map. CURATED rows are reviewed by a person; their companies are accepted.
CURATED = {"gitdm", "patch", "rich", "correction"}
ACCEPTING_MAP_SOURCES = CURATED | {"builtin", "spinellis-sec", "spinellis-sec-self-reference"}
CONFIDENCE = {"gitdm": "curated", "patch": "curated", "rich": "curated", "correction": "curated",
              "builtin": "curated", "cncf-gitdm": "multi-developer",
              "cncf-gitdm-self-reference": "multi-developer",
              "cncf-gitdm-single": "single-developer",
              "cncf-gitdm-single-self-reference": "single-developer",
              "spinellis-sec": "published", "spinellis-sec-self-reference": "published",
              "spinellis-2020": "published", "claude-proposal": "proposed", "claude-proposal-v1": "proposed",
              "claude-proposal-v2": "proposed"}
# Lower number = stronger claim on a domain.
DOMAIN_RANK = {"correction": 1, "gitdm": 2, "patch": 2, "rich": 2, "builtin": 3,
               "spinellis-sec": 4, "spinellis-sec-self-reference": 4, "spinellis-2020": 4,
               "cncf-gitdm": 5, "cncf-gitdm-self-reference": 5, "cncf-gitdm-single": 6,
               "cncf-gitdm-single-self-reference": 6, "claude-proposal": 7, "claude-proposal-v1": 8,
               "claude-proposal-v2": 9}
# Lower number = stronger claim on the kind of a company.
KIND_RANK = {"roster": 1, "correction": 2, "curated-deliberate": 3, "spinellis": 4,
             "curated-company": 5, "builtin": 6, "claude-proposal": 7, "claude-proposal-v1": 7.5,
             "claude-proposal-v2": 7.7,
             "cncf-gitdm": 8, "cncf-gitdm-single": 9}
CONF_CLASS = {"curated": 0, "published": 0, "multi-developer": 1, "proposed": 1, "single-developer": 2}
RELATION_RANK = {"owns": 1, "participates": 2, "candidate": 3}
EVIDENCE_ORDER = ("company-page", "verified-domain", "roster", "spinellis", "website-domain", "name-match")
PSEUDO_IDS = {"independent", "free-provider", "pre-git-import"}
NO_LINK_KINDS = {"free-provider", "independent", "project"}   # never linked by a website (W1, W2)

# Web results (W1-W5): source id, file name, licence.
WEB_FILES = {
    "w1-github-orgs": ("w1_github_orgs.parquet", "API terms; facts only"),
    "w2-gitlab-groups": ("w2_gitlab_groups.parquet", "API terms; facts only"),
    "w3-wikidata-matches": ("w3_wikidata_matches.parquet", "CC0"),
    "w3-wikidata-items": ("w3_wikidata_items.parquet", "CC0"),
    "w3-properties": ("w3_properties.parquet", "CC0"),
    "w4-sec-tickers": ("w4_sec_tickers.parquet", "public domain (US government work)"),
    "w5-gleif": ("w5_gleif.parquet", "CC0"),
}
WEB_URLS = {"w1-github-orgs": "https://api.github.com/graphql", "w2-gitlab-groups": "GitLab Groups API",
            "w3-wikidata-matches": "https://query.wikidata.org/sparql",
            "w3-wikidata-items": "https://query.wikidata.org/sparql",
            "w3-properties": "https://query.wikidata.org/sparql",
            "w4-sec-tickers": "https://www.sec.gov/files/company_tickers.json",
            "w5-gleif": "https://api.gleif.org/api/v1/lei-records/"}
# A website on one of these hosts names a hosting site, not the owner of the org.
HOSTING = {"github.io", "github.com", "gitlab.io", "gitlab.com", "readthedocs.io", "readthedocs.org",
           "rtfd.io", "sourceforge.net", "sourceforge.io", "sf.net", "bitbucket.org", "bitbucket.io",
           "netlify.app", "netlify.com", "vercel.app", "herokuapp.com", "pages.dev", "gitee.com",
           "gitee.io", "codeberg.org", "codeberg.page", "medium.com", "wordpress.com", "blogspot.com",
           "substack.com", "notion.site", "linktr.ee", "twitter.com", "x.com", "linkedin.com",
           "facebook.com", "youtube.com", "discord.gg", "discord.com", "t.me", "googlegroups.com",
           "sites.google.com", "wixsite.com", "squarespace.com", "carrd.co", "about.me",
           "opencollective.com", "patreon.com", "hackmd.io", "gitbook.io", "npmjs.com", "pypi.org",
           "crates.io", "docs.rs", "huggingface.co", "zenodo.org", "osf.io", "launchpad.net",
           "savannah.gnu.org", "savannah.nongnu.org"}
# Wikidata classes (English labels of P31), by the kind they support.
WD_CLASS = (
    ("academic", re.compile(r"(?i)universit|college|research institut|research institution|research cent|"
                            r"research organi|laborator|school|academy|educational institution|polytechnic")),
    ("government", re.compile(r"(?i)government|ministry|public body|public agency|state agency|federal agency|"
                              r"national agency|regulatory|space agency")),
    ("nonprofit", re.compile(r"(?i)non-?profit|foundation|charit|association|learned society|scientific society|"
                             r"professional society|consortium|non-governmental|standards organi|"
                             r"open-source software organi|free software organi")),
    ("business", re.compile(r"(?i)compan|business|enterprise|corporation|\bfirm\b|subsidiar|conglomerate|"
                            r"manufacturer|video game developer|video game publisher|publisher|\bbank\b|"
                            r"startup|holding|cooperative|stock exchange")),
    ("organisation", re.compile(r"(?i)organi[sz]ation|institution|\bagency\b|\bunit\b")),
)
WD_FINANCIAL = re.compile(r"(?i)\bbank\b|insurance|financial services|investment (?:company|bank|management)|"
                          r"asset management|stock exchange|credit (?:union|card)")
WD_PUBLIC = re.compile(r"(?i)\bpublic\b.*(universit|college|education|research|school)|state universit|"
                       r"(universit|college).*\bpublic\b")
WD_PRIVATE = re.compile(r"(?i)\bprivate\b.*(universit|college|education|research|school)")
KIND_FOR_CLASS = {"business": set(COMPANY_KINDS), "nonprofit": {"foundation", "fiscal-sponsor", "nonprofit"},
                  "academic": {"academic"}, "government": {"government"}}

# Organisations of the rosters (DS/rosters/*.csv). The names and the aliases are a manual
# table: an alias is a spelling of the same organisation in the ctp map or in the proposals.
ROSTER_ORGS = {
    "asf": ("Apache Software Foundation", ("Apache",)),
    "asf-attic": ("Apache Software Foundation", ()),
    "asf-incubator": ("Apache Software Foundation", ()),
    "bytecodealliance": ("Bytecode Alliance", ()),
    "cncf": ("Cloud Native Computing Foundation", ("CNCF",)),
    "documentfoundation": ("The Document Foundation", ()),
    "eclipse": ("Eclipse Foundation", ()),
    "freebsd": ("FreeBSD Foundation", ("FreeBSD",)),
    "gnome": ("GNOME Foundation", ("GNOME",)),
    "gnu": ("GNU Project", ()),
    "kde": ("KDE e.V.", ("KDE",)),
    "lf": ("Linux Foundation", ("The Linux Foundation",)),
    "lfai": ("LF AI & Data", ()),
    "lfedge": ("LF Edge", ()),
    "lfnetworking": ("LF Networking", ()),
    "mozilla": ("Mozilla", ()),
    "netbsd": ("The NetBSD Foundation", ("NetBSD",)),
    "numfocus": ("NumFOCUS", ()),
    "obf": ("Open Bioinformatics Foundation", ()),
    "openinfra": ("OpenInfra Foundation", ("OpenStack Foundation",)),
    "openjs": ("OpenJS Foundation", ()),
    "openssf": ("OpenSSF", ()),
    "osgeo": ("OSGeo", ()),
    "psf": ("Python Software Foundation", ()),
    "psf-sponsored": ("Python Software Foundation", ()),
    "redhat": ("Red Hat", ()),
    "rust-foundation": ("Rust Foundation", ()),
    "sfc": ("Software Freedom Conservancy", ()),
    "spi": ("Software in the Public Interest", ()),
    "xorg": ("X.Org Foundation", ()),
}
# Rows of rosters/lf.csv that name a sub-foundation; their note gives legal_parent.
LF_CHILD_SLUGS = {"cncf": "cncf", "lfai": "lf-ai-foundation", "lfedge": "lfedge",
                  "lfnetworking": "lfn", "openssf": "openssf", "openjs": "ojsf"}
# The Red Hat roster lists the orgs of projects that Red Hat takes part in (redhat.method.md).
PARTICIPATES_ROSTERS = {"redhat"}
# A roster that is the repository listing of one org (mozilla.method.md): it shows who owns the org.
ORG_LISTING_ROSTERS = {"mozilla": "mozilla"}
# The description of this org says "The GitHub organization for Red Hat".
OWNED_IN_PARTICIPATES = {("redhat", "redhatofficial")}

PSEUDO = {"independent": ("(Independent)", "independent"),
          "free-provider": ("(Free e-mail provider)", "free-provider")}

FORGE_HOSTS = {"github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "opendev.org",
               "invent.kde.org", "git.sr.ht", "salsa.debian.org", "pagure.io", "framagit.org"}
HOST_ALIAS = {"www.github.com": "github.com", "git.sv.gnu.org": "git.savannah.gnu.org"}
SAVANNAH = {"git.savannah.gnu.org": "gnu"}  # the owner rule of s7-run (final_meta.HOST_OWNER)
GITHUB_RESERVED = {"topics", "search", "sponsors", "features", "marketplace", "collections",
                   "enterprise", "about", "settings", "apps", "site", "explore", "login"}

FALLBACK_2LD = {"co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "ltd.uk", "plc.uk", "com.au",
                "net.au", "org.au", "edu.au", "gov.au", "co.jp", "ne.jp", "or.jp", "ac.jp",
                "com.br", "org.br", "gov.br", "edu.br", "net.br", "com.cn", "net.cn", "org.cn",
                "edu.cn", "gov.cn", "ac.cn", "co.in", "co.kr", "or.kr", "ac.kr", "co.nz",
                "co.za", "com.tw", "edu.tw", "com.mx", "com.ar", "com.tr", "co.il", "ac.il",
                "com.sg", "com.hk", "com.ua", "co.id", "com.my", "com.pl"}

LEGAL_FORM = re.compile(r"(?i)(?:^|[\s,])(inc\.?|incorporated|corp\.?|corporation|ltd\.?|limited|"
                        r"llc\.?|l\.l\.c\.|gmbh|ag|s\.a\.?|sa|s\.a\.s\.?|sas|s\.r\.l\.?|srl|"
                        r"s\.r\.o\.?|a/s|ab|oy|oyj|plc|b\.v\.?|bv|n\.v\.?|nv|kk|k\.k\.|co\.|"
                        r"pty|e\.v\.|pbc|spa|s\.p\.a\.)(?=$|[\s,.)])")
LEGAL_WORDS = {"inc", "incorporated", "corp", "corporation", "co", "ltd", "limited", "llc",
               "plc", "gmbh", "ag", "sa", "sas", "srl", "sro", "nv", "bv", "ab", "oy", "oyj",
               "as", "kk", "pty", "pbc", "spa", "the", "group", "holdings", "holding",
               "company", "de", "mo", "com", "se"}
GENERIC_TAIL = {"technology", "technologies", "systems", "system", "solutions", "semiconductors",
                "semiconductor", "electronics", "software", "networks", "network",
                "international", "engineering", "entreprise", "incorporated"}

# Words that show an organisation. A name of 2 or 3 words with none of these words, and each
# word in the form "Xxxx", can be a person name.
ORG_WORDS = set("""inc ltd llc gmbh ag sa sas srl bv nv ab oy as plc corp co company group labs
lab technologies technology tech systems system software solutions hat foundation network
networks cloud data media studio studios games game digital consulting consultants consultancy
bank university universidad universitat universite institute institut project team open linux
security services service partners industries industry electronics communications computing
computer computers research engineering design development devices micro semiconductor
semiconductors energy health medical financial capital ventures international global holdings
interactive innovation innovations analytics robotics works trust society association council
ministry government agency school college academy center centre laboratory laboratories
platform platforms apps app web online mobile telecom wireless motors automotive insurance store
shop market markets marketing payments pay entertainment music video art arts graphics hosting
host hub net code coding dev devops ops ai ml iot storage power wind audio exchange internet
desktop cable times reply swarm logic squad operations africa unicom box buy remedies knowledge
dynamics partnership convergence informatique electronique systemtechnik nixdorf river
microelectronics microsystems embedded collins logics archive fusion sigma bahn electric
worldwide black guardian libre linpro dream august universitet""".split())
PERSON_WORD = re.compile(r"^[A-Z][a-z]+(?:-[A-Z][a-z]+)?$|^[A-Z]\.$")
STRICT_DOMAIN = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*$")
BAD_DOMAIN_CHAR = re.compile(r"[\s@\x00-\x1f\x7f]")
EDU_GOV = re.compile(r"(?:^|\.)(edu|gov|gouv|mil|ac|edu\.[a-z]{2}|gov\.[a-z]{2}|ac\.[a-z]{2})$")


# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------

def tilde(p: Path | str) -> str:
    s = str(p)
    for home in {str(HOME), os.path.realpath(HOME)}:
        if s.startswith(home + "/"):
            return "~" + s[len(home):]
    return s


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def slug(name: str) -> str:
    """A stable, lower-case id from a name: 'Red Hat' -> 'red-hat'."""
    s = html.unescape(name)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ").replace("+", " plus ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        s = "org-" + hashlib.sha1(name.encode()).hexdigest()[:10]
    return s


def norm_name(name: str) -> str:
    """A name without case, accents, punctuation and legal forms, for comparisons only."""
    s = html.unescape(name)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"/[a-z]{2}/", " ", s)
    s = s.replace("&", " and ")
    words = [w for w in re.split(r"[^a-z0-9]+", s.replace(".", "")) if w]
    return " ".join(w for w in words if w not in LEGAL_WORDS)


def names_agree(short: str, legal: str) -> bool:
    """True when `legal` is the legal name of the organisation `short` (case, legal form,
    initials or a generic last word: 'Cisco' and 'CISCO SYSTEMS, INC.')."""
    a, b = norm_name(short).split(), norm_name(legal).split()
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) == 1 and len(b) > 1 and a[0] == "".join(w[0] for w in b):
        return True
    if b[:len(a)] == a and all(w in GENERIC_TAIL for w in b[len(a):]):
        return True
    return False


def person_like(name: str) -> bool:
    """True when the name can be a person name ('Jane Roe'). Many company names also match;
    the build uses this test only on names that no person reviewed."""
    words = name.split()
    if not 2 <= len(words) <= 3:
        return False
    if any(w.lower().strip(".,") in ORG_WORDS for w in words):
        return False
    return all(PERSON_WORD.match(w) for w in words)


def pad_cik(cik) -> str:
    """The CIK with 10 digits, as the SEC writes it ('796343' -> '0000796343')."""
    c = str(cik or "").strip()
    return c.zfill(10) if c.isdigit() else ""


def clean_kind(kind: str) -> str:
    k = kind.strip().lower()
    return KIND_ALIAS.get(k, k)


def norm_domain(d: str) -> str:
    return d.strip().lower().rstrip(".")


def valid_domain(d: str) -> bool:
    """A value that can be a domain value of the dataset. The dataset holds values with a typo
    or a stray character ('intel.com_', 'tue.nl\u201d', '.thomsonreuters.com'), and the link step
    matches the exact value, so these stay. A value with whitespace, '@', '%40' or a control
    character is refused."""
    return bool(d) and not BAD_DOMAIN_CHAR.search(d) and "%40" not in d


def iso(ts: str) -> str:
    """'2026-10-06T03:58:35+00:00' or '...Z' -> '2026-10-06T03:58:35Z'."""
    ts = (ts or "").strip()
    if not ts:
        return ""
    ts = ts.replace("+00:00", "Z")
    return ts if ts.endswith("Z") or "T" not in ts else ts + "Z"


def git_info(path: Path) -> tuple[str, str]:
    """(commit, commit date) of the last commit of a file, and '' when the file is not clean."""
    try:
        d = str(path.parent)
        out = subprocess.run(["git", "-C", d, "log", "-1", "--format=%H %cs", "--", path.name],
                             capture_output=True, text=True, timeout=30).stdout.split()
        dirty = subprocess.run(["git", "-C", d, "status", "--porcelain", "--", path.name],
                               capture_output=True, text=True, timeout=30).stdout.strip()
        if len(out) == 2 and not dirty:
            return out[0], out[1]
    except (OSError, subprocess.SubprocessError):
        pass
    return "", ""


# ---------------------------------------------------------------------------------------------
# Public Suffix List
# ---------------------------------------------------------------------------------------------

def find_psl() -> Path | None:
    found = sorted(glob.glob(PSL_GLOB), key=lambda p: (Path(p).parents[2].name.split("-unstable-")[-1], p))
    return Path(found[-1]) if found else None


def load_psl(text: str) -> tuple[set, set, set]:
    """The ICANN section only: (rules, wildcard rules, exception rules)."""
    rules, wild, exc = set(), set(), set()
    icann = False
    for line in text.splitlines():
        line = line.strip()
        if "===BEGIN ICANN DOMAINS===" in line:
            icann = True
        elif "===END ICANN DOMAINS===" in line:
            icann = False
        if not icann or not line or line.startswith("//"):
            continue
        rule = line.split()[0].lower()
        rule = rule.encode("idna").decode() if not rule.isascii() and not rule.startswith(("*", "!")) else rule
        if rule.startswith("!"):
            exc.add(rule[1:])
        elif rule.startswith("*."):
            wild.add(rule[2:])
        else:
            rules.add(rule)
    return rules, wild, exc


def registrable_domain(domain: str, psl: tuple[set, set, set] | None) -> str:
    """The registrable domain ('mail.redhat.com' -> 'redhat.com'); '' when there is none."""
    if not domain or not STRICT_DOMAIN.match(domain) or "." not in domain:
        return ""
    labels = domain.split(".")
    if psl is None:
        last2 = ".".join(labels[-2:])
        n = 3 if last2 in FALLBACK_2LD else 2
        return ".".join(labels[-n:]) if len(labels) >= n else ""
    rules, wild, exc = psl
    suffix_len = 1
    for i in range(len(labels)):
        cand = ".".join(labels[i:])
        if cand in exc:
            suffix_len = len(labels) - i - 1
            break
        parent = ".".join(labels[i + 1:])
        if cand in rules or (parent and parent in wild):
            suffix_len = len(labels) - i
            break
    if suffix_len >= len(labels):
        return ""
    return ".".join(labels[-(suffix_len + 1):])


# ---------------------------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------------------------

def read_map(path: Path) -> tuple[list[dict], list[dict]]:
    """Rows of affiliation.merged.csv (domain,company,kind,source) and a list of the rows
    that have a comma in the company name. A row with an unquoted comma has more than 4
    fields: the extra fields go back into the company name."""
    rows, odd = [], []
    lines = path.read_text(encoding="utf-8").splitlines()
    header = next(csv.reader([lines[0]]))
    n = len(header)
    ci = header.index("company")
    tail = n - ci - 1
    for lineno, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        fields = next(csv.reader([line]))
        if len(fields) > n:
            fields = fields[:ci] + [",".join(fields[ci:len(fields) - tail])] + fields[len(fields) - tail:]
            odd.append({"line": lineno, "domain": fields[0], "how": "unquoted comma, fields joined"})
        elif len(line.split(",")) != n:
            odd.append({"line": lineno, "domain": fields[0], "how": "quoted comma, read by csv"})
        if len(fields) != n:
            odd.append({"line": lineno, "domain": "", "how": f"{len(fields)} fields, row not used"})
            continue
        r = dict(zip(header, fields))
        r["line"] = lineno
        rows.append(r)
    return rows, odd


def read_csv(path: Path, delimiter: str = ",") -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        out = []
        for i, r in enumerate(csv.DictReader(f, delimiter=delimiter), start=2):
            r = {k: (v or "") for k, v in r.items() if k is not None}
            r["line"] = i
            out.append(r)
        return out


def namespace_of(url: str, extra_hosts: set = frozenset()) -> tuple[str, str, str] | None:
    """(host, namespace, level) of a repository or account URL; level is 'org' when the URL
    names the account or group, 'repo' when it names a repository. None for other URLs.
    For GitLab-style hosts the namespace is the group path (as in the dataset owner)."""
    u = (url or "").strip()
    if not u:
        return None
    if "://" not in u:
        if re.match(r"^[\w.-]+@[\w.-]+:", u):
            u = "ssh://" + u.split("@", 1)[1].replace(":", "/", 1)
        else:
            u = "https://" + u
    try:
        p = urlsplit(u)
    except ValueError:
        return None
    host = (p.hostname or "").lower()
    host = HOST_ALIAS.get(host, host)
    if not host:
        return None
    gitlab_like = host.startswith(("gitlab.", "gitea.")) or host in FORGE_HOSTS
    if not (gitlab_like or host in extra_hosts or host in SAVANNAH):
        return None
    path = p.path.split("/-/")[0]
    parts = [x for x in path.split("/") if x]
    if parts and parts[-1].endswith(".git"):
        parts[-1] = parts[-1][:-4]
    if host in SAVANNAH:
        return (host, SAVANNAH[host], "repo") if parts else None
    if host == "github.com":
        if not parts or parts[0].lower() in GITHUB_RESERVED:
            return None
        if parts[0].lower() == "orgs":
            return ("github.com", parts[1], "org") if len(parts) > 1 else None
        return ("github.com", parts[0], "org") if len(parts) == 1 else ("github.com", parts[0], "repo")
    if gitlab_like:
        if parts and parts[0] == "groups":
            return (host, "/".join(parts[1:]), "org") if len(parts) > 1 else None
        if not parts:
            return None
        return (host, parts[0], "org") if len(parts) == 1 else (host, "/".join(parts[:-1]), "repo")
    if not parts:
        return None
    return (host, host, "repo") if len(parts) == 1 else (host, "/".join(parts[:-1]), "repo")


@dataclass
class Inputs:
    map_csv: Path
    corrections_csv: Path | None = None
    firm_canonical_csv: Path | None = None
    spinellis_companies: Path | None = None
    spinellis_org_links: Path | None = None
    spinellis_fetch: Path | None = None
    spinellis_archive: Path | None = None
    company_pages: list[Path] = field(default_factory=list)
    rosters: list[Path] = field(default_factory=list)
    review_csv: Path | None = None
    map_suspects_csv: Path | None = None
    canonical_proposals_csv: Path | None = None
    map_firms_tsv: Path | None = None
    domain_counts_csv: Path | None = None
    project_meta: Path | None = None
    web_dir: Path | None = None              # the normalized web results (W1-W5)
    proposals_v1: Path | None = None         # proposals/top_unmatched.v1.csv (optional)
    proposals_v2: Path | None = None         # proposals/top_unmatched.v2.csv (optional)
    psl: Path | None = None
    script: Path | None = None
    git: bool = True  # read commit ids with git (off in the fixture tests)

    @classmethod
    def real(cls, ctp: Path = CTP_DEFAULT, ds: Path = DS_DEFAULT, psl: Path | None = None,
             web: Path | None = WEB_DEFAULT) -> "Inputs":
        sp = ds / "sources/spinellis-2020"
        cp = ds / "sources/company-pages"
        fd = ds / "firm-domains"
        rosters = sorted(p for p in (ds / "rosters").glob("*.csv") if not p.name.endswith(".orig.csv"))
        return cls(map_csv=ctp / "data/affiliation.merged.csv",
                   corrections_csv=ctp / "data/affiliation.corrections.csv",
                   firm_canonical_csv=ctp / "data/firm_canonical.csv",
                   spinellis_companies=sp / "companies.csv", spinellis_org_links=sp / "org_links.csv",
                   spinellis_fetch=sp / "FETCH.tsv", spinellis_archive=sp / "enterprise-oss.tar.gz",
                   company_pages=[cp / "evidence.csv", cp / "browser/evidence_browser.csv"],
                   rosters=rosters, review_csv=fd / "review.csv",
                   map_suspects_csv=fd / "map_suspects.csv",
                   canonical_proposals_csv=fd / "canonical_proposals.csv",
                   map_firms_tsv=fd / "work/map_firms.tsv",
                   domain_counts_csv=fd / "domains.csv",
                   project_meta=ds / "s7-run/project_meta.v1.final.json",
                   web_dir=web, proposals_v1=ds / "s8-companies/proposals/top_unmatched.v1.csv",
                   proposals_v2=ds / "s8-companies/proposals/top_unmatched.v2.csv",
                   psl=psl or find_psl(), script=Path(__file__).resolve())


# ---------------------------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------------------------

@dataclass
class Org:
    company_id: str
    names: Counter = field(default_factory=Counter)        # (rank, name) -> rows
    kinds: list = field(default_factory=list)               # (rank, kind, basis, pointer, tag)
    accept: list = field(default_factory=list)              # (rank, reviewer, date)
    proposed_by: set = field(default_factory=set)
    legal_name: str = ""
    sec_cik: str = ""
    fg500: bool | None = None
    bases: list = field(default_factory=list)               # (basis, kind or '', pointer)
    notes: list = field(default_factory=list)
    web: dict = field(default_factory=dict)                 # columns from the web results
    proposed_parent: tuple = ()                             # (company_id, pointer) from a proposal


def qkey(q: str):
    """Sort key of a Wikidata id: Q2 before Q10."""
    return (len(q), q)


def wd_classes(item: dict) -> set:
    """The kinds of organisation that the P31 labels of an item give; empty when no label is an
    organisation class (software, products and packages give nothing)."""
    out = set()
    for label in item.get("instance_of_labels") or []:
        for cat, rx in WD_CLASS:
            if rx.search(label or ""):
                out.add(cat)
                break
    return out


def trusted_domain(row: dict) -> bool:
    """A domain row that can show the owner of a website: curated, published or proposed, or the
    label of its registrable domain is the company id ('expedia.com' for expedia). A CNCF row can
    give the employer of one developer on a domain that the employer does not own."""
    if row["confidence"] in ("curated", "published", "proposed"):
        return True
    g = row["registrable_domain"] or row["domain"]
    return g.split(".")[0].replace("-", "") == row["company_id"].replace("-", "")


def best_name(o: Org) -> str:
    """The name of the strongest source; then the most rows; then the first in order."""
    return min(o.names, key=lambda k: (k[0], -o.names[k], k[1]))[1] if o.names else ""


class Builder:
    def __init__(self, inp: Inputs):
        self.inp = inp
        self.orgs: dict[str, Org] = {}
        self.alias: dict[str, tuple[str, str]] = {}          # alias -> (company_id, source)
        self.alias_rows: set = set()
        self.alias_redirect: dict[str, str] = {}             # name -> canonical name
        self.canon: dict[str, str] = {}
        self.domain_claims: dict[str, list] = defaultdict(list)
        self.ns_claims: list = []
        self.conflicts: list = []
        self.registry: list = []
        self.dates: dict[str, str] = {}
        self.stats: dict = {}
        self.psl = None
        self.dataset_pairs: dict = {}
        self.parents: dict = {}                              # child id -> (parent id, pointer)
        self.web: dict = {}
        self.web_verified: dict = {}
        self.web_sites: dict = {}

    # -- registry --------------------------------------------------------------------------
    def register(self, sid: str, path: Path | None, url: str = "", licence: str = "",
                 fetched_at: str = "", date: str = "") -> None:
        if path is None or not Path(path).exists():
            return
        commit, cdate = git_info(Path(path)) if self.inp.git else ("", "")
        if commit and not url:
            url = f"git:{commit}"
        self.registry.append({"source_id": sid, "path": tilde(path), "sha256": sha256(Path(path)),
                              "url": url, "licence": licence, "fetched_at": iso(fetched_at)})
        self.dates[sid] = date or cdate or (fetched_at or "")[:10]

    # -- names and organisations ------------------------------------------------------------
    def resolve(self, raw: str) -> str:
        """Canonical name of a raw spelling: firm_canonical, then the roster aliases and the
        accepted alias table."""
        name = html.unescape(raw.strip())
        name = self.canon.get(raw.strip(), self.canon.get(name, name))
        return self.alias_redirect.get(name, name)

    def org(self, name: str) -> Org:
        cid = slug(name)
        if cid not in self.orgs:
            self.orgs[cid] = Org(cid)
        return self.orgs[cid]

    def add_alias(self, alias: str, cid: str, source: str) -> None:
        alias = alias.strip()
        if not alias or "@" in alias:
            return
        old = self.alias.get(alias)
        if old and old[0] != cid:
            self.conflicts.append({"type": "alias-two-companies", "key": alias, "kept": old[0],
                                   "other": cid, "source": source, "detail": ""})
            return
        self.alias.setdefault(alias, (cid, source))
        self.alias_rows.add((alias, cid, source))

    def pseudo(self, kind: str) -> Org | None:
        if kind not in PSEUDO:
            return None
        name, cid = PSEUDO[kind]
        if cid not in self.orgs:
            self.orgs[cid] = Org(cid)
        self.orgs[cid].names[(0, name)] += 1
        return self.orgs[cid]

    # -- step 1: the ctp map ---------------------------------------------------------------
    def load_canonical(self) -> None:
        if self.inp.firm_canonical_csv and self.inp.firm_canonical_csv.exists():
            self.register("ctp-firm-canonical", self.inp.firm_canonical_csv)
            for r in read_csv(self.inp.firm_canonical_csv):
                self.canon[r["firm_raw"].strip()] = r["firm"].strip()
        for key, (name, aliases) in ROSTER_ORGS.items():
            for a in aliases:
                self.alias_redirect[a] = name

    def load_map(self) -> None:
        inp = self.inp
        self.register("ctp-affiliation-merged", inp.map_csv)
        rows, odd = read_map(inp.map_csv)
        self.stats["map_rows"] = len(rows)
        self.stats["map_odd_rows"] = odd
        corr = {}
        if inp.corrections_csv and inp.corrections_csv.exists():
            self.register("ctp-affiliation-corrections", inp.corrections_csv)
            for r in read_csv(inp.corrections_csv):
                corr[norm_domain(r["domain"])] = r
        self.accepted_map_names = {self.resolve(r["company"]) for r in rows
                                   if r["source"].strip() in ACCEPTING_MAP_SOURCES}
        self.accepted_map_names |= {self.resolve(c["company"]) for c in corr.values()}
        seen = set()
        for r in rows:
            d = norm_domain(r["domain"])
            c = corr.get(d)
            if c and (c["company"], clean_kind(c["kind"])) != (r["company"], clean_kind(r["kind"])):
                self.conflicts.append({"type": "correction-differs-from-map", "key": d,
                                       "kept": slug(self.resolve(c["company"])),
                                       "other": slug(self.resolve(r["company"])),
                                       "source": "ctp-affiliation-corrections", "detail": ""})
                r = dict(r, company=c["company"], kind=c["kind"], source="correction")
            seen.add(d)
            self.map_row(r, d, f"ctp-affiliation-merged#domain={d}")
        for d, c in sorted(corr.items()):
            if d not in seen:
                self.map_row(dict(c, source="correction"), d, f"ctp-affiliation-corrections#domain={d}")

    def map_row(self, r: dict, d: str, pointer: str) -> None:
        src, kind, raw = r["source"].strip(), clean_kind(r["kind"]), r["company"].strip()
        if not valid_domain(d):
            self.conflicts.append({"type": "invalid-domain", "key": d if "@" not in d else "(withheld)",
                                   "kept": "", "other": "", "source": src, "detail": pointer.split("#")[0]})
            return
        if kind not in KINDS:
            self.conflicts.append({"type": "unknown-kind", "key": d, "kept": "", "other": kind,
                                   "source": src, "detail": ""})
            return
        if "@" in raw:
            self.conflicts.append({"type": "withheld-name-with-at", "key": d, "kept": "", "other": "",
                                   "source": src, "detail": f"{pointer.split('#')[0]} line {r.get('line', '')}"})
            self.stats["withheld_at"] = self.stats.get("withheld_at", 0) + 1
            return
        pseudo =raw == "(Independent)" or kind == "free-provider"
        if pseudo:
            o = self.pseudo("free-provider" if kind == "free-provider" else "independent")
            name = None
        else:
            name = self.resolve(raw)
            if src not in ACCEPTING_MAP_SOURCES and person_like(name) and not self.accepted_name(name):
                self.conflicts.append({"type": "withheld-person-like-name", "key": d, "kept": "",
                                       "other": "", "source": src,
                                       "detail": "the company name of this row can be a person name"})
                self.stats["withheld"] = self.stats.get("withheld", 0) + 1
                return
            o = self.org(name)
            o.names[(2 if src in ACCEPTING_MAP_SOURCES else 5, name)] += 1
            if raw == "(Pre-git import)" or r["kind"].strip() == "import":
                o.notes.append("The ctp map gives kind 'import' (history from before git); here kind 'project'.")
        cid = o.company_id
        if o.company_id == "free-provider":
            self.add_alias(PSEUDO["free-provider"][0], cid, "build-script")
        elif raw:
            self.add_alias(raw, cid, "ctp-affiliation-merged")
        tag = ("correction" if src == "correction" else
               ("curated-company" if kind == "company" else "curated-deliberate") if src in CURATED else
               "spinellis" if src.startswith("spinellis-sec") else
               "builtin" if src == "builtin" else
               "cncf-gitdm-single" if src.startswith("cncf-gitdm-single") else "cncf-gitdm")
        o.kinds.append((KIND_RANK[tag], kind, "manual-review" if tag in ("correction", "curated-deliberate") else "",
                        pointer, src))
        if src in ACCEPTING_MAP_SOURCES:
            sid = pointer.split("#")[0]
            o.accept.append((3 if src in CURATED else 5, f"source:{src}", self.dates.get(sid, "")))
        self.domain_claims[d].append((DOMAIN_RANK.get(src, 9), cid, src, CONFIDENCE.get(src, "proposed"), pointer))

    def accepted_name(self, name: str) -> bool:
        return (name in self.canon.values() or name in self.alias_redirect.values()
                or name in self.accepted_map_names)

    # -- step 2: Spinellis et al. 2020 ------------------------------------------------------
    def domain_owner(self, d: str) -> str | None:
        claims = sorted(self.domain_claims.get(d, []))
        return claims[0][1] if claims else None

    def load_spinellis(self) -> None:
        inp = self.inp
        if not (inp.spinellis_companies and inp.spinellis_companies.exists()):
            return
        fetched = ""
        if inp.spinellis_fetch and inp.spinellis_fetch.exists():
            kv = dict(line.split("\t", 1) for line in inp.spinellis_fetch.read_text().splitlines() if "\t" in line)
            fetched = kv.get("fetched_at", "")
            self.register("spinellis-2020-archive", inp.spinellis_archive or inp.spinellis_fetch,
                          url="https://doi.org/10.5281/zenodo.3742962", licence="CC-BY-4.0",
                          fetched_at=fetched, date="2020-04-21")
        self.register("spinellis-2020-companies", inp.spinellis_companies,
                      licence="CC-BY-4.0 (derived from Zenodo 3742962)", fetched_at=fetched, date="2020-04-21")
        self.spin_ids = {}
        by_norm = defaultdict(set)
        for cid, o in self.orgs.items():
            for (_, n) in o.names:
                by_norm[norm_name(n)].add(cid)
        for r in read_csv(inp.spinellis_companies):
            sec = r["company"].strip()
            legal = html.unescape(sec)
            doms = [norm_domain(x.split("=")[0]) for x in r["domains"].split(";") if x.strip()]
            pointer = f"spinellis-2020-companies#cik={r['cik']}" if r["cik"] else \
                f"spinellis-2020-companies#line={r['line']}"
            cid = None
            for d in doms:
                c = self.domain_owner(d)
                if c and c not in ("independent", "free-provider"):
                    cid = c
                    break
                if c:
                    self.conflicts.append({"type": "spinellis-domain-is-pseudo-org", "key": d, "kept": c,
                                           "other": legal, "source": "spinellis-2020-companies",
                                           "detail": "the domain stays with the pseudo organisation"})
            if cid is None:
                hits = sorted(by_norm.get(norm_name(self.resolve(legal)), set()) - {"independent", "free-provider"})
                cid = hits[0] if hits else self.org(self.resolve(legal)).company_id
                if not hits:
                    self.orgs[cid].names[(4, self.resolve(legal))] += 1
            o = self.orgs[cid]
            self.spin_ids[sec] = cid
            self.add_alias(sec, cid, "spinellis-2020-companies")
            short = best_name(o) or legal
            fg = r["fg500"] == "True"
            filer = r["sec10k"] == "True" or r["sec20f"] == "True"
            if names_agree(short, legal) or norm_name(short) == norm_name(legal):
                o.legal_name = o.legal_name or legal
                o.sec_cik = o.sec_cik or pad_cik(r["cik"])
                o.fg500 = fg if o.fg500 is None else (o.fg500 or fg)
            else:
                o.notes.append(f"Spinellis et al. 2020 give the filer '{legal}' (CIK {r['cik'] or 'none'}, "
                               f"FG500 {fg}) for this domain. The filer can be a parent company: "
                               f"check legal_name, sec_cik and parent_company_id.")
                self.conflicts.append({"type": "spinellis-name-differs", "key": ";".join(doms), "kept": cid,
                                       "other": legal, "source": "spinellis-2020-companies",
                                       "detail": "sec_cik and legal_name stay blank"})
            if filer:
                o.bases.append(("sec-filer", "company", pointer))
            if fg:
                o.bases.append(("fortune-global-500", "company", pointer))
            o.kinds.append((KIND_RANK["spinellis"], "company", "", pointer, "spinellis-2020"))
            o.accept.append((4, "source:spinellis-2020", "2020-04-21"))
            for d in doms:
                if valid_domain(d):
                    self.domain_claims[d].append((DOMAIN_RANK["spinellis-2020"], cid, "spinellis-2020",
                                                  "published", pointer))

    # -- step 3: rosters ---------------------------------------------------------------------
    def load_rosters(self, extra_hosts: set) -> None:
        kinds = {}
        files = [p for p in self.inp.rosters if not p.name.endswith(".repos.csv")]
        files += [p for p in self.inp.rosters if p.name.endswith(".repos.csv")]
        for p in files:
            rows = read_csv(p)
            sid = f"roster-{p.stem}"
            fetched = max((r.get("fetched_at", "") for r in rows), default="")
            urls = sorted({r.get("source_url", "") for r in rows if r.get("source_url")})
            self.register(sid, p, url=urls[0] if len(urls) == 1 else "", fetched_at=fetched)
            for r in rows:
                key = r.get("org_key", "").strip()
                kind = clean_kind(r.get("org_kind", "") or kinds.get(key, ""))
                if not kind:
                    continue
                kinds.setdefault(key, kind)
                if key not in ROSTER_ORGS:
                    self.conflicts.append({"type": "roster-org-not-in-table", "key": key, "kept": "",
                                           "other": "", "source": sid, "detail": ""})
                    continue
                name = ROSTER_ORGS[key][0]
                main_key = next(k for k, v in ROSTER_ORGS.items() if v[0] == name)
                krank = KIND_RANK["roster"] if key == main_key else KIND_RANK["roster"] + 0.5
                o = self.org(name)
                if o.names[(1, name)] == 0:
                    o.names[(1, name)] += 1
                    o.kinds.append((krank, kind, "roster", f"{sid}#org_key={key}", "roster"))
                    o.bases.append(("roster", kind, f"{sid}#org_key={key}"))
                    o.accept.append((krank, f"source:roster-{main_key}", (fetched or "")[:10]))
                    self.add_alias(name, o.company_id, "roster-table")
                    for a in ROSTER_ORGS[key][1]:
                        self.add_alias(a, o.company_id, "roster-table")
                elif not any(k[2] == "roster" and k[1] == kind and k[0] == krank for k in o.kinds):
                    o.kinds.append((krank, kind, "roster", f"{sid}#org_key={key}", "roster"))
                    o.bases.append(("roster", kind, f"{sid}#org_key={key}"))
                if key == "lf":
                    self.lf_parent_row(r, sid)
                got = []
                slug_ = r.get("github_slug", "").strip()
                if "/" in slug_:
                    got.append(("github.com", slug_.split("/")[0], "repo"))
                for col in ("repo_url", "clone_url"):
                    ns = namespace_of(r.get(col, ""), extra_hosts)
                    if ns:
                        got.append(ns)
                if not got and (r.get("repo_url") or r.get("github_slug")):
                    self.stats["roster_urls_not_forge"] = self.stats.get("roster_urls_not_forge", 0) + 1
                for host, ns, level in dict.fromkeys(got):
                    rel = "owns"
                    if key in PARTICIPATES_ROSTERS and (key, ns.lower()) not in OWNED_IN_PARTICIPATES:
                        rel = "participates"
                    ns_type = "group" if host != "github.com" else ("org" if key == "redhat" else "")
                    self.ns_claims.append({"host": host, "namespace": ns, "namespace_type": ns_type,
                                           "company_id": o.company_id, "relation": rel, "evidence": "roster",
                                           "verified": None, "source_pointer": f"{sid}#line={r['line']}",
                                           "fetched_at": iso(r.get("fetched_at", "")), "level": level})

    def lf_parent_row(self, r: dict, sid: str) -> None:
        """A row of lf.csv for a sub-foundation gives its legal parent (e.g. CNCF)."""
        m = re.search(r"lfx_slug=([^;]+)", r.get("note", ""))
        lp = re.search(r"legal_parent=([^;]+)", r.get("note", ""))
        if not (m and lp):
            return
        for key, lfx in LF_CHILD_SLUGS.items():
            if m.group(1).strip() == lfx:
                parent = slug(self.resolve(lp.group(1).strip()))
                child = slug(ROSTER_ORGS[key][0])
                self.parents[child] = (parent, f"{sid}#line={r['line']}")

    # -- step 4: proposals -------------------------------------------------------------------
    def load_proposals(self) -> None:
        inp = self.inp
        if inp.canonical_proposals_csv and inp.canonical_proposals_csv.exists():
            self.register("firm-domains-canonical-proposals", inp.canonical_proposals_csv)
            for r in read_csv(inp.canonical_proposals_csv):
                if r["decision"].strip() != "merge":
                    continue
                src_id, dst = slug(self.resolve(r["firm_raw"])), r["firm"].strip()
                dst_id = slug(self.resolve(dst))
                if src_id not in self.orgs:
                    continue
                if dst_id in self.orgs and dst_id != src_id:
                    self.conflicts.append({"type": "proposed-merge-not-applied", "key": r["firm_raw"],
                                           "kept": src_id, "other": dst_id,
                                           "source": "firm-domains-canonical-proposals",
                                           "detail": "both names are companies; a person must decide"})
                    continue
                self.alias_redirect.setdefault(dst, self.resolve(r["firm_raw"]))
                self.add_alias(dst, src_id, "firm-domains-canonical-proposals")
                self.orgs[src_id].notes.append(f"Proposed canonical name: '{dst}' (claude-proposal).")
        when = {}
        for sid, p in (("firm-domains-review", inp.review_csv), ("firm-domains-map-suspects", inp.map_suspects_csv)):
            if not (p and p.exists()):
                continue
            self.register(sid, p)
            for r in read_csv(p):
                if r.get("decision", "").strip() not in ("accept", "edit") or not r.get("firm", "").strip():
                    continue
                d = norm_domain(r["domain"])
                if not valid_domain(d):
                    self.stats["proposal_invalid_domain"] = self.stats.get("proposal_invalid_domain", 0) + 1
                    continue
                kind = clean_kind(r.get("kind", ""))
                if kind not in KINDS:
                    self.conflicts.append({"type": "unknown-kind", "key": d, "kept": "", "other": kind,
                                           "source": sid, "detail": ""})
                    continue
                pointer = f"{sid}#domain={d}"
                raw = r["firm"].strip()
                if "@" in raw:
                    self.conflicts.append({"type": "withheld-name-with-at", "key": d, "kept": "", "other": "",
                                           "source": sid, "detail": ""})
                    continue
                if raw == "(Independent)" or kind in ("free-provider", "independent"):
                    o = self.pseudo("free-provider" if kind == "free-provider" else "independent")
                else:
                    name = self.resolve(raw)
                    if person_like(name) and slug(name) not in self.orgs:
                        self.conflicts.append({"type": "withheld-person-like-name", "key": d, "kept": "",
                                               "other": "", "source": sid,
                                               "detail": "the proposed name can be a person name"})
                        self.stats["withheld"] = self.stats.get("withheld", 0) + 1
                        continue
                    o = self.org(name)
                    o.names[(6, name)] += 1
                    self.add_alias(raw, o.company_id, sid)
                o.proposed_by.add("claude-proposal")
                o.kinds.append((KIND_RANK["claude-proposal"], kind, "", pointer, "claude-proposal"))
                owner = self.domain_owner(d)
                if owner and owner != o.company_id:
                    self.conflicts.append({"type": "proposal-differs-from-map", "key": d, "kept": owner,
                                           "other": o.company_id, "source": sid,
                                           "detail": "the map row stays; a person must decide"})
                    continue
                if owner:
                    continue
                self.domain_claims[d].append((DOMAIN_RANK["claude-proposal"], o.company_id,
                                              "claude-proposal", "proposed", pointer))
        if inp.map_firms_tsv and inp.map_firms_tsv.exists():
            self.register("firm-domains-map-firms", inp.map_firms_tsv)
            names = {r["firm"] for r in read_csv(inp.map_firms_tsv, "\t")}
            missing = sorted(n for n in names if slug(self.resolve(n)) not in self.orgs
                             and n != "(Independent)")
            self.stats["map_firms_not_found"] = len(missing)

    # -- step 5: namespaces from Spinellis and company pages ---------------------------------
    def load_org_links(self) -> None:
        inp = self.inp
        spin = getattr(self, "spin_ids", {})
        if inp.spinellis_org_links and inp.spinellis_org_links.exists():
            rows = read_csv(inp.spinellis_org_links)
            self.register("spinellis-2020-org-links", inp.spinellis_org_links,
                          licence="CC-BY-4.0 (derived from Zenodo 3742962)",
                          fetched_at=max((r["fetched_at"] for r in rows), default=""))
            self.stats["org_links_not_kept"] = sum(1 for r in rows if r["link"] != "kept")
            for r in rows:
                if r["link"] != "kept":
                    continue
                cid = spin.get(r["company"].strip()) or self.orgs.get(slug(self.resolve(r["company"])), Org("")).company_id
                if not cid:
                    continue
                ver = {"True": True, "False": False}.get(r["is_verified"])
                strong = ver is True and r["website_on_company_domain"] == "True"
                self.ns_claims.append({"host": "github.com", "namespace": r["owner"],
                                       "namespace_type": "org" if r["owner_type"] == "Organization" else "",
                                       "company_id": cid, "relation": "owns" if strong else "candidate",
                                       "evidence": "verified-domain" if strong else "spinellis",
                                       "verified": ver,
                                       "source_pointer": f"spinellis-2020-org-links#owner={r['owner']}",
                                       "fetched_at": iso(r["fetched_at"]), "level": "org"})
        for i, p in enumerate(inp.company_pages):
            if not p.exists():
                continue
            sid = "company-pages-evidence" if i == 0 else "company-pages-browser"
            rows = read_csv(p)
            self.register(sid, p, fetched_at=max((r["fetched_at"] for r in rows), default=""))
            for r in rows:
                cid = spin.get(r["company"].strip()) or slug(self.resolve(r["company"]))
                if cid not in self.orgs:
                    self.conflicts.append({"type": "company-page-company-unknown", "key": r["org"], "kept": "",
                                           "other": r["company"], "source": sid, "detail": ""})
                    continue
                self.ns_claims.append({"host": "github.com", "namespace": r["org"], "namespace_type": "org",
                                       "company_id": cid, "relation": "owns", "evidence": "company-page",
                                       "verified": None,
                                       "source_pointer": r.get("final_url") or r.get("page_url") or f"{sid}#line={r['line']}",
                                       "fetched_at": iso(r["fetched_at"]), "level": "org"})

    # -- dataset namespaces -------------------------------------------------------------------
    def load_dataset(self) -> set:
        p = self.inp.project_meta
        hosts = set()
        if not (p and p.exists()):
            return hosts
        self.register("dataset-project-meta", p)
        meta = json.loads(p.read_text(encoding="utf-8"))
        pairs = {}
        for key in sorted(meta):
            rec = meta[key]
            host = (urlsplit(rec.get("clone_url", "")).hostname or "").lower()
            owner = rec.get("owner", "")
            if not host or not owner:
                continue
            hosts.add(host)
            k = (host, owner.lower())
            t = {"Organization": "org", "User": "user"}.get(rec.get("owner_type", ""), "")
            if host != "github.com" and not t:
                t = "group"
            pairs.setdefault(k, {"host": host, "namespace": owner, "namespace_type": t, "projects": 0})
            pairs[k]["projects"] += 1
        self.dataset_pairs = pairs
        return hosts

    def load_domain_counts(self) -> None:
        """Tokens of the dataset for each e-mail domain (firm-domains/domains.csv; only the
        rows with a valid domain are read)."""
        self.tokens = {}
        p = self.inp.domain_counts_csv
        if not (p and p.exists()):
            return
        self.register("firm-domains-domain-counts", p)
        for r in read_csv(p):
            d = norm_domain(r.get("domain", ""))
            if valid_domain(d) and r.get("tokens", "").isdigit():
                self.tokens[d] = int(r["tokens"])

    # -- step 6: proposals of the top unmatched domains (optional) ----------------------------
    def load_top_unmatched(self, p: Path | None, round_: str, skip: set = frozenset()) -> set:
        """proposals/top_unmatched.<round>.csv: rows with certainty high or medium only. A domain
        in `skip` (the domains of an earlier round) is not read again. Returns the domains of
        the file. The domain value stays exactly as the file gives it (no case or dot change)."""
        key = f"proposals_{round_}"
        self.stats[key + "_present"] = bool(p and p.exists())
        if not (p and p.exists()):
            return set()
        sid, tag = f"proposals-top-unmatched-{round_}", f"claude-proposal-{round_}"
        name_rank = {"v1": 7, "v2": 8}.get(round_, 9)
        self.register(sid, p)
        used = Counter()
        seen = set()
        by_norm = defaultdict(set)
        for cid, o in self.orgs.items():
            if cid not in PSEUDO_IDS:
                for (_, n) in o.names:
                    by_norm[norm_name(n)].add(cid)

        def existing(name: str) -> str | None:
            name = self.resolve(name)
            if slug(name) in self.orgs and slug(name) not in PSEUDO_IDS:
                return slug(name)
            hits = sorted(by_norm.get(norm_name(name), set()))
            return hits[0] if hits and norm_name(name) else None

        for r in read_csv(p):
            raw_d = r.get("domain", "").strip()
            seen.add(raw_d)
            if raw_d in skip:
                used["in-earlier-round"] += 1
                continue
            if "%40" in raw_d or "@" in raw_d:
                self.conflicts.append({"type": "domain-with-at", "key": norm_domain(re.split(r"%40|@", raw_d)[0]),
                                       "kept": "", "other": "", "source": sid,
                                       "detail": "a git-svn id, not an e-mail domain"})
                used["domain-with-at"] += 1
                continue
            d = raw_d
            name, kind = r.get("name", "").strip(), clean_kind(r.get("kind", ""))
            cert = r.get("certainty", "").strip().lower()
            safe = name if name and "@" not in name and not person_like(name) else ""
            if cert not in ("high", "medium"):
                self.conflicts.append({"type": "proposal-low-certainty", "key": d if valid_domain(d) else "(invalid)",
                                       "kept": "", "other": safe, "source": sid, "detail": f"certainty {cert or 'blank'}"})
                used["low-or-unknown"] += 1
                continue
            if not valid_domain(d) or kind not in KINDS or not name or "@" in name:
                self.conflicts.append({"type": "proposal-not-usable", "key": d if valid_domain(d) else "(invalid)",
                                       "kept": "", "other": safe, "source": sid, "detail": f"kind {kind or 'blank'}"})
                used["not-usable"] += 1
                continue
            pointer = f"{sid}#domain={d}"
            if kind == "free-provider":
                o = self.pseudo("free-provider")
            elif kind == "independent" or name == "(Independent)":
                o = self.pseudo("independent")
            else:
                cid = existing(name)
                if cid is None and person_like(self.resolve(name)):
                    self.conflicts.append({"type": "withheld-person-like-name", "key": d, "kept": "", "other": "",
                                           "source": sid, "detail": "the proposed name can be a person name"})
                    used["withheld"] += 1
                    continue
                o = self.orgs[cid] if cid else self.org(self.resolve(name))
                if not cid:
                    o.names[(name_rank, self.resolve(name))] += 1
                    by_norm[norm_name(self.resolve(name))].add(o.company_id)
                self.add_alias(name, o.company_id, sid)
                parent = r.get("parent_name", "").strip()
                pid = existing(parent) if parent and "@" not in parent else None
                if pid and pid != o.company_id and not o.proposed_parent:
                    o.proposed_parent = (pid, pointer, tag)
            o.proposed_by.add(tag)
            o.kinds.append((KIND_RANK[tag], kind, "", pointer, tag))
            owner = self.domain_owner(d)
            if owner and owner != o.company_id:
                self.conflicts.append({"type": "proposal-differs-from-map", "key": d, "kept": owner,
                                       "other": o.company_id, "source": sid,
                                       "detail": "the existing row stays; a person must decide"})
                used["domain-has-owner"] += 1
                continue
            used["used"] += 1
            if not owner:
                self.domain_claims[d].append((DOMAIN_RANK[tag], o.company_id, tag, "proposed", pointer))
        self.stats[key] = dict(sorted(used.items()))
        return seen

    # -- web results (W1-W5) -------------------------------------------------------------------
    def load_web(self) -> None:
        """Read the normalized web files that exist; register each one."""
        self.web = {}
        d = self.inp.web_dir
        if not d:
            return
        import duckdb
        con = duckdb.connect(config={"memory_limit": "3GB", "threads": 2})
        for sid, (fname, licence) in WEB_FILES.items():
            path = Path(d) / fname
            if not path.exists():
                continue
            cur = con.execute(f"SELECT * FROM read_parquet('{path}')")
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, t)) for t in cur.fetchall()]
            fetched = max((str(r.get("fetched_at") or "") for r in rows), default="")
            self.register(sid, path, url=WEB_URLS.get(sid, ""), licence=licence, fetched_at=fetched)
            self.web[sid] = rows
        con.close()
        self.stats["web_files"] = sorted(self.web)

    # -- web merge ------------------------------------------------------------------------------
    def hosting(self, whost: str, forge_host: str = "") -> bool:
        """True when a website host is a hosting site, or the forge of the namespace itself."""
        if any(whost == h or whost.endswith("." + h) for h in HOSTING):
            return True
        return bool(forge_host) and registrable_domain(whost, self.psl) == registrable_domain(forge_host, self.psl)

    def web_namespace_claims(self, dom_owner: dict, kind_of: dict) -> None:
        """W1 and W2: an org or group whose website is on the domain of exactly one company."""
        roster = defaultdict(set)
        for c in self.ns_claims:
            if c["evidence"] == "roster":
                roster[(c["host"].lower(), c["namespace"].lower())].add(c["company_id"])
        self.web_verified, self.web_sites = {}, {}
        got = Counter()
        rows = []
        for r in self.web.get("w1-github-orgs", []):
            if r.get("status") != "OK" or r.get("typename") != "Organization":
                continue
            login = r.get("login") or r.get("requested_login") or ""
            rows.append(("github.com", login, r.get("website_url") or "", r.get("website_host") or "",
                         r.get("is_verified"), f"w1-github-orgs#login={login}", r.get("fetched_at") or ""))
        for r in self.web.get("w2-gitlab-groups", []):
            if r.get("status") != "OK":
                continue
            path = r.get("full_path") or r.get("group_path") or ""
            url = r.get("web_url") or ""
            whost = (urlsplit(url).hostname or "").lower().removeprefix("www.") if url else ""
            rows.append((r.get("host") or "", path, url, whost, None,
                         f"w2-gitlab-groups#group={r.get('host')}/{path}", r.get("fetched_at") or ""))
        for host, ns, url, whost, ver, pointer, fetched in sorted(rows, key=lambda x: (x[0], x[1].lower(), x[5])):
            if not ns or "@" in url:
                continue
            k = (host.lower(), ns.lower())
            if ver is not None:
                self.web_verified[k] = bool(ver)
            if not whost:
                got["no-website"] += 1
                continue
            self.web_sites[k] = (url, whost)
            if self.hosting(whost, host):
                got["hosting-site"] += 1
                continue
            reg = registrable_domain(whost, self.psl)
            owners = {dom_owner[x] for x in {whost, reg} if x in dom_owner}
            if len(owners) != 1:
                got["no-company-domain" if not owners else "several-companies"] += 1
                continue
            cid = owners.pop()
            if cid in PSEUDO_IDS or kind_of.get(cid) in NO_LINK_KINDS:
                got["not-linked-kind"] += 1
                continue
            if cid in roster.get(k, set()):
                got["roster-row-kept"] += 1
                continue
            rel, ev = ("owns", "verified-domain") if ver is True else ("candidate", "website-domain")
            if rel == "owns" and roster.get(k):
                rel = "candidate"            # a roster gives the namespace to another organisation
            got[f"{rel}/{ev}"] += 1
            self.ns_claims.append({"host": host, "namespace": ns, "namespace_type": "org" if host == "github.com" else "group",
                                   "company_id": cid, "relation": rel, "evidence": ev,
                                   "verified": ver if host == "github.com" else None, "source_pointer": pointer,
                                   "fetched_at": iso(str(fetched)), "level": "org"})
        self.stats["web_namespace_claims"] = dict(sorted(got.items()))

    def enrich(self, domains: list, ns_rows: list, kind_of: dict) -> None:
        """W1 website, W3 Wikidata, W4 SEC, W5 GLEIF and the proposal parents, into Org.web."""
        dom_owner = {r["domain"]: r["company_id"] for r in domains if trusted_domain(r)}
        doms = defaultdict(set)
        main = {}
        for r in domains:
            if trusted_domain(r):
                doms[r["company_id"]].add(r["domain"])
            if r["role"] == "main":
                main[r["company_id"]] = r["domain"]
        owned, gh_owner = defaultdict(set), defaultdict(set)
        for n in ns_rows:
            if n["relation"] == "owns":
                owned[n["company_id"]].add((n["host"], n["namespace"].lower()))
            if n["relation"] != "participates" and n["host"] == "github.com":
                gh_owner[n["namespace"].lower()].add(n["company_id"])
        got = Counter()
        # W1, W2: the website of an owned org, when its host is a domain of the company.
        for cid in sorted(owned):
            if cid in PSEUDO_IDS or cid not in self.orgs:
                continue
            cands = []
            for k in owned[cid]:
                site = self.web_sites.get(k)
                if not site or self.hosting(site[1], k[0]):
                    continue
                reg = registrable_domain(site[1], self.psl)
                hit = site[1] if site[1] in doms[cid] else (reg if reg in doms[cid] else None)
                if hit:
                    cands.append((hit != main.get(cid), site[1] != hit, not self.web_verified.get(k, False),
                                  len(site[1]), k, site[0], hit))
            if cands:
                best = min(cands)
                self.orgs[cid].web.update(website=best[5], website_domain=best[6])
                got["website"] += 1
        # W3: Wikidata items of organisation classes.
        items = {r["qid"]: r for r in self.web.get("w3-wikidata-items", []) if r.get("qid")}
        classes = {q: wd_classes(it) for q, it in items.items()}
        support = defaultdict(lambda: defaultdict(set))
        for m in self.web.get("w3-wikidata-matches", []):
            q, mk, mv = m.get("qid"), m.get("match_kind"), (m.get("match_value") or "")
            if q not in items:
                continue
            if not classes[q]:
                got["match-not-organisation"] += 1
                continue
            cids = {dom_owner.get(norm_domain(mv))} if mk == "P856" else gh_owner.get(mv.lower(), set())
            for cid in cids:
                if cid and cid not in PSEUDO_IDS:
                    support[cid][q].add(mk)
        chosen = {}
        for cid in sorted(support):
            qs = support[cid]
            if len(qs) == 1:
                chosen[cid] = next(iter(qs))
                continue
            both = sorted(q for q, k in qs.items() if len(k) == 2)
            pool = both or sorted(qs)
            ids_ = [q for q in pool if items[q].get("sec_cik") or items[q].get("lei")]
            alive = [q for q in ids_ if not items[q].get("dissolved")]
            pick = (both[0] if len(both) == 1 else ids_[0] if len(ids_) == 1 else
                    alive[0] if len(alive) == 1 else None)
            if pick:
                chosen[cid] = pick
            else:
                self.conflicts.append({"type": "wikidata-several-items", "key": cid, "kept": "",
                                       "other": ";".join(sorted(qs, key=qkey)), "source": "w3-wikidata-matches",
                                       "detail": "no single item has both matches, or a CIK or LEI"})
        by_q = defaultdict(list)
        for cid, q in chosen.items():
            by_q[q].append(cid)
        for q, cids in sorted(by_q.items()):
            if len(cids) > 1:
                both = [c for c in cids if len(support[c][q]) == 2]
                keep = both[0] if len(both) == 1 else ""
                self.conflicts.append({"type": "wikidata-item-two-companies", "key": q, "kept": keep,
                                       "other": ";".join(sorted(c for c in cids if c != keep)),
                                       "source": "w3-wikidata-matches", "detail": ""})
                for c in cids:
                    if c != keep:
                        del chosen[c]
        for cid, q in sorted(chosen.items()):
            it, o, kind = items[q], self.orgs[cid], kind_of[cid]
            w = o.web
            w["wikidata_qid"] = q
            iso2 = sorted({x.upper() for x in (it.get("country_iso2") or []) if x and len(x) == 2})
            if len(iso2) == 1:
                w["country"] = iso2[0]
            elif iso2:
                got["country-several"] += 1
            ciks = sorted({pad_cik(x) for x in (it.get("sec_cik") or []) if pad_cik(x)})
            if len(ciks) == 1:
                if o.sec_cik and o.sec_cik != ciks[0]:
                    self.conflicts.append({"type": "sec-cik-differs", "key": cid, "kept": o.sec_cik, "other": ciks[0],
                                           "source": "w3-wikidata-items", "detail": q})
                elif not o.sec_cik:
                    o.sec_cik = ciks[0]
            leis = sorted({x for x in (it.get("lei") or []) if x})
            if len(leis) == 1:
                w["lei"] = leis[0]
            tick = sorted({x for x in (it.get("tickers") or []) if x})
            if len(tick) == 1:
                w["ticker"] = tick[0]
            if it.get("dissolved"):
                w["status"] = "defunct"
            cats = classes[q] - {"organisation"}
            if any(kind in KIND_FOR_CLASS[c] for c in cats):
                o.bases.append(("wikidata-instance-of", kind, f"wikidata:{q}"))
            labels = " | ".join(it.get("instance_of_labels") or [])
            if kind in COMPANY_KINDS and cats & {"nonprofit", "academic", "government"} and "business" not in cats \
                    or kind in ("foundation", "fiscal-sponsor", "nonprofit", "academic", "government") and cats == {"business"}:
                self.conflicts.append({"type": "kind-differs", "key": cid, "kept": kind, "other": ";".join(sorted(cats)),
                                       "source": "w3-wikidata-items", "detail": f"wikidata:{q}"})
                o.notes.append(f"Wikidata {q} gives the class {', '.join(sorted(cats))}.")
            if kind in COMPANY_KINDS and WD_FINANCIAL.search(labels):
                w["sector"] = "S.12"
            if kind == "academic":
                if WD_PUBLIC.search(labels) and not WD_PRIVATE.search(labels):
                    w["sector"] = "S.13"
                elif WD_PRIVATE.search(labels) and not WD_PUBLIC.search(labels):
                    w["sector"] = "S.15"
        q2c = {q: c for c, q in chosen.items()}
        for cid, q in sorted(chosen.items()):
            if cid in self.parents:
                continue
            for pq in sorted(items[q].get("parent_qids") or [], key=qkey):
                pc = q2c.get(pq)
                if pc and pc != cid:
                    self.orgs[cid].web["parent"] = (pc, f"wikidata:{q} P749 {pq}")
                    break
        # W4: SEC tickers by CIK (the first row of a CIK is its main ticker).
        sec = {}
        for r in self.web.get("w4-sec-tickers", []):
            if r.get("cik"):
                sec.setdefault(pad_cik(r["cik"]), r)
        for cid, o in sorted(self.orgs.items()):
            r = sec.get(o.sec_cik) if o.sec_cik else None
            if not r:
                continue
            got["sec-filer"] += 1
            o.bases.append(("sec-filer", "company", f"w4-sec-tickers#cik={o.sec_cik}"))
            if not o.legal_name and r.get("title") and "@" not in r["title"]:
                o.legal_name = r["title"]
            if r.get("ticker"):
                o.web["ticker"] = r["ticker"]        # the SEC main ticker wins over Wikidata
        # W5: GLEIF records by LEI.
        gleif = {r["lei"]: r for r in self.web.get("w5-gleif", []) if r.get("status") == "OK" and r.get("lei")}
        lei2c = {o.web["lei"]: c for c, o in self.orgs.items() if o.web.get("lei")}
        for cid, o in sorted(self.orgs.items()):
            r = gleif.get(o.web.get("lei", ""))
            if not r:
                continue
            got["registry-id"] += 1
            o.bases.append(("registry-id", "", f"w5-gleif#lei={r['lei']}"))
            if not o.legal_name and r.get("legal_name") and "@" not in r["legal_name"]:
                o.legal_name = r["legal_name"]
            pc = lei2c.get(r.get("direct_parent_lei") or "")
            if pc and pc != cid and cid not in self.parents and "parent" not in o.web:
                o.web["parent"] = (pc, f"w5-gleif#lei={r['lei']} direct parent {r['direct_parent_lei']}")
        # Proposal parents (top_unmatched.v1.csv), last.
        for cid, o in sorted(self.orgs.items()):
            if o.proposed_parent and cid not in self.parents and "parent" not in o.web:
                o.web["parent"] = (o.proposed_parent[0], f"{o.proposed_parent[1]} ({o.proposed_parent[2]})")
        self.stats["web_merge"] = dict(sorted(got.items()))

    # -- finish ---------------------------------------------------------------------------------
    def finish(self) -> dict:
        # company_domain: one domain, one company.
        domains = []
        for d in sorted(self.domain_claims):
            claims = sorted(self.domain_claims[d])
            rank, cid, src, conf, pointer = claims[0]
            for c in claims[1:]:
                if c[1] != cid:
                    self.conflicts.append({"type": "domain-two-companies", "key": d, "kept": cid, "other": c[1],
                                           "source": c[2], "detail": f"kept source {src}"})
            domains.append({"domain": d, "registrable_domain": registrable_domain(d, self.psl),
                            "company_id": cid, "role": "alternative", "confidence": conf,
                            "source": src, "source_pointer": pointer, "_rank": rank})
        by_company = defaultdict(list)
        for row in domains:
            by_company[row["company_id"]].append(row)
        tokens = getattr(self, "tokens", {})
        for cid, rows in by_company.items():
            # main: (1) the label of the registrable domain is the company id ('redhat.com'
            # for red-hat); (2) the stronger confidence; (3) the most map rows with the same
            # registrable domain; (4) the registrable domain itself, not a subdomain; (5) the
            # shortest subdomain; (6) the most token rows of the dataset; (7) the first in order.
            groups = Counter(r["registrable_domain"] or r["domain"] for r in rows)
            key = cid.replace("-", "")

            def order(r):
                g = r["registrable_domain"] or r["domain"]
                label = g.split(".")[0].replace("-", "")
                return (label != key, CONF_CLASS.get(r["confidence"], 3), -groups[g], r["domain"] != g,
                        len(r["domain"]) if r["domain"] != g else 0, -tokens.get(r["domain"], 0), r["domain"])
            min(rows, key=order)["role"] = "main"
        # The kind of each organisation, then the web merge (it needs domains and namespaces).
        kind_of = {cid: (sorted(o.kinds) or [(99, "company")])[0][1] for cid, o in self.orgs.items() if o.names}
        ids = set(kind_of)
        self.web_namespace_claims({r["domain"]: r["company_id"] for r in domains if trusted_domain(r)}, kind_of)
        ns_rows = self.namespaces(ids)
        for n in ns_rows:
            v = self.web_verified.get((n["host"], n["namespace"].lower()))
            if n["verified"] is None and v is not None:
                n["verified"] = v
        self.enrich(domains, ns_rows, kind_of)
        for cid, rows in by_company.items():
            wd = self.orgs[cid].web.get("website_domain") if cid in self.orgs else None
            if wd and any(r["domain"] == wd for r in rows):
                for r in rows:
                    r["role"] = "main" if r["domain"] == wd else "alternative"
        # kind and the other company columns.
        companies = []
        for cid in sorted(self.orgs):
            o = self.orgs[cid]
            if not o.names:
                continue
            name = best_name(o)
            kinds = sorted(o.kinds) or [(99, "company", "", "", "")]
            kind = kinds[0][1]
            other = sorted({k[1] for k in kinds if k[1] != kind})
            if other:
                self.conflicts.append({"type": "kind-differs", "key": cid, "kept": kind, "other": ";".join(other),
                                       "source": kinds[0][4], "detail": "the strongest source gives the kind"})
                o.notes.append(f"Other sources give kind {', '.join(other)}.")
            bases = {}
            for k in kinds:
                if k[2] and k[1] == kind:
                    bases.setdefault(k[2], k[3])
            for b, bk, ptr in o.bases:
                if bk in ("", kind) or (b in ("sec-filer", "fortune-global-500") and kind in COMPANY_KINDS) \
                        or (b == "wikidata-instance-of" and kind == bk):
                    bases.setdefault(b, ptr)
            if kind in COMPANY_KINDS:
                for (rank, n) in sorted(o.names):
                    if LEGAL_FORM.search(n):
                        bases.setdefault("legal-form-in-name", f"company_alias#alias={n}")
                        break
                else:
                    if o.legal_name and LEGAL_FORM.search(o.legal_name):
                        bases.setdefault("legal-form-in-name", f"company#legal_name={o.legal_name}")
            if kind in ("academic", "government"):
                for r in sorted(by_company.get(cid, []), key=lambda r: r["domain"]):
                    if EDU_GOV.search(r["domain"]):
                        bases.setdefault("gov-or-edu-domain", f"company_domain#domain={r['domain']}")
                        break
            order = [b for b in BASIS_ORDER if b in bases]
            w = o.web
            parent = self.parents.get(cid) or w.get("parent") or ("", "")
            if parent[0]:
                o.notes.append(f"parent_company_id from {parent[1]}." if cid not in self.parents else
                               f"parent_company_id from {parent[1]} (legal_parent).")
            accepted = sorted(o.accept)
            status = "accepted" if accepted else "proposed"
            if status == "accepted":
                reviewer, rdate = accepted[0][1], accepted[0][2]
            else:
                reviewer = next((t for t in ("claude-proposal", "claude-proposal-v1", "claude-proposal-v2")
                                 if t in o.proposed_by), "")
                rdate = (self.dates.get("firm-domains-review", "") if reviewer == "claude-proposal" else
                         self.dates.get("proposals-top-unmatched-" + reviewer[-2:], "") if reviewer else "")
            if cid in self.canon_targets:
                if status == "proposed":
                    status, reviewer, rdate = "accepted", "source:firm_canonical", self.dates.get("ctp-firm-canonical", "")
            companies.append({
                "company_id": cid, "name": name, "legal_name": o.legal_name, "kind": kind,
                "is_company": kind in COMPANY_KINDS, "sna_sector": w.get("sector") or SECTOR[kind],
                "kind_basis": ",".join(order), "kind_basis_pointer": " | ".join(bases[b] for b in order),
                "parent_company_id": parent[0], "country": w.get("country", ""),
                "website": w.get("website", ""), "wikidata_qid": w.get("wikidata_qid", ""),
                "sec_cik": o.sec_cik, "ticker": w.get("ticker", ""), "lei": w.get("lei", ""),
                "fortune_global_500": o.fg500, "status": w.get("status", ""), "review_status": status, "reviewer": reviewer, "review_date": rdate or None,
                "note": " ".join(dict.fromkeys(o.notes))})
        ids = {c["company_id"] for c in companies}
        for c in companies:
            if c["parent_company_id"] and c["parent_company_id"] not in ids:
                c["parent_company_id"] = ""
        # Possible duplicates: the same name without case, punctuation and legal forms.
        seen = defaultdict(list)
        for c in companies:
            seen[norm_name(c["name"]).replace(" ", "")].append(c["company_id"])
        for k, v in sorted(seen.items()):
            if k and len(v) > 1:
                self.conflicts.append({"type": "possible-duplicate", "key": k, "kept": v[0],
                                       "other": ";".join(v[1:]), "source": "", "detail": "not merged"})
        aliases = sorted({(a, c, s) for (a, c, s) in self.alias_rows if c in ids})
        for r in domains:
            r.pop("_rank", None)
        tables = {
            "company": companies,
            "company_alias": [{"alias": a, "company_id": c, "source": s} for a, c, s in aliases],
            "company_domain": [r for r in domains if r["company_id"] in ids],
            "company_namespace": ns_rows,
            "source_registry": sorted(self.registry, key=lambda r: r["source_id"]),
        }
        self.conflicts = sorted({tuple(sorted(c.items())): c for c in self.conflicts}.values(),
                                key=lambda c: (c["type"], c["key"], c["kept"], c["other"], c["source"]))
        return tables

    def namespaces(self, ids: set) -> list[dict]:
        users = {k for k, v in self.dataset_pairs.items() if v["namespace_type"] == "user"}
        skipped_users = 0
        claims = []
        for c in self.ns_claims:
            k = (c["host"].lower(), c["namespace"].lower())
            if c["company_id"] not in ids:
                continue
            if c["evidence"] == "roster" and k in users:
                skipped_users += 1
                continue
            claims.append(c)
        self.stats["roster_user_namespaces_skipped"] = skipped_users
        strong = defaultdict(set)
        for c in claims:
            listing = (c["evidence"] == "roster" and
                       ORG_LISTING_ROSTERS.get(c["source_pointer"].split("#")[0].removeprefix("roster-")) == c["namespace"].lower())
            if (c["evidence"] in ("company-page", "verified-domain") or listing) and c["relation"] == "owns":
                strong[(c["host"].lower(), c["namespace"].lower())].add(c["company_id"])
        for c in claims:
            k = (c["host"].lower(), c["namespace"].lower())
            if (c["evidence"] == "roster" and c["level"] == "repo" and c["relation"] == "owns"
                    and strong.get(k) and c["company_id"] not in strong[k]):
                c["relation"] = "participates"
                self.stats["roster_owns_to_participates"] = self.stats.get("roster_owns_to_participates", 0) + 1
        # Name-match candidates for the dataset namespaces with no claim.
        claimed = {(c["host"].lower(), c["namespace"].lower()) for c in claims}
        by_name = defaultdict(set)
        for cid in ids:
            if cid in ("independent", "free-provider"):
                continue
            o = self.orgs[cid]
            for (_, n) in o.names:
                key = norm_name(n).replace(" ", "")
                if len(key) >= 4:
                    by_name[key].add(cid)
        for k, v in sorted(self.dataset_pairs.items()):
            if k in claimed or v["namespace_type"] == "user":
                continue
            last = v["namespace"].split("/")[-1].lower()
            key = re.sub(r"[^a-z0-9]", "", last)
            hits = by_name.get(key) or by_name.get(re.sub(r"(hq|inc|oss|opensource|official|labs)$", "", key)) or set()
            for cid in sorted(hits):
                claims.append({"host": v["host"], "namespace": v["namespace"], "namespace_type": v["namespace_type"],
                               "company_id": cid, "relation": "candidate", "evidence": "name-match", "verified": None,
                               "source_pointer": f"dataset-project-meta#owner={v['namespace']}",
                               "fetched_at": "", "level": "org"})
        grouped = defaultdict(list)
        for c in claims:
            grouped[(c["host"].lower(), c["namespace"].lower(), c["company_id"])].append(c)
        rows = []
        for (h, n, cid), cs in sorted(grouped.items()):
            cs.sort(key=lambda c: (RELATION_RANK[c["relation"]], EVIDENCE_ORDER.index(c["evidence"]),
                                   c["source_pointer"]))
            best = cs[0]
            dp = self.dataset_pairs.get((h, n))
            ev = [e for e in EVIDENCE_ORDER if any(c["evidence"] == e for c in cs)]
            vers = [c["verified"] for c in cs if c["verified"] is not None]
            types = [c["namespace_type"] for c in cs if c["namespace_type"]]
            rows.append({"host": best["host"].lower(), "namespace": dp["namespace"] if dp else best["namespace"],
                         "namespace_type": (dp["namespace_type"] if dp and dp["namespace_type"] else
                                            (types[0] if types else "")),
                         "company_id": cid, "relation": best["relation"], "evidence": ";".join(ev),
                         "verified": (True in vers) if vers else None,
                         "source_pointer": best["source_pointer"], "fetched_at": best["fetched_at"]})
        owners = defaultdict(list)
        for r in rows:
            if r["relation"] == "owns":
                owners[(r["host"], r["namespace"].lower())].append(r["company_id"])
        for (h, n), cids in sorted(owners.items()):
            cids = [c for c in cids if not any(self.parents.get(x, ("",))[0] == c for x in cids)]
            if len(cids) > 1:
                self.conflicts.append({"type": "namespace-two-owners", "key": f"{h}/{n}", "kept": "",
                                       "other": ";".join(sorted(cids)), "source": "", "detail": "all rows kept"})
        return rows

    def run(self) -> dict:
        inp = self.inp
        if inp.psl and Path(inp.psl).exists():
            text = Path(inp.psl).read_text(encoding="utf-8")
            self.psl = load_psl(text)
            m = re.search(r"unstable-(\d{4}-\d{2}-\d{2})", str(inp.psl))
            self.register("public-suffix-list", Path(inp.psl), url="https://publicsuffix.org/list/public_suffix_list.dat",
                          licence="MPL-2.0", fetched_at=m.group(1) if m else "")
        if inp.script and inp.script.exists():
            self.register("build-script", inp.script)
        self.load_canonical()
        self.canon_targets = {slug(v) for v in self.canon.values()}
        hosts = self.load_dataset()
        self.load_map()
        for raw, firm in self.canon.items():
            if slug(firm) in self.orgs:
                self.add_alias(raw, slug(firm), "ctp-firm-canonical")
        self.load_spinellis()
        self.load_rosters(hosts)
        self.load_proposals()
        v1 = self.load_top_unmatched(self.inp.proposals_v1, "v1")
        self.load_top_unmatched(self.inp.proposals_v2, "v2", skip=v1)
        self.load_org_links()
        self.load_domain_counts()
        self.load_web()
        tables = self.finish()
        check_no_at(tables)
        check_no_at({"conflicts": self.conflicts})
        return tables


def check_no_at(tables: dict) -> None:
    """Stop when a value holds '@' (an e-mail address must never reach a table)."""
    for t, rows in tables.items():
        for r in rows:
            for k, v in r.items():
                if isinstance(v, str) and "@" in v:
                    raise SystemExit(f"refused: table {t} column {k} holds '@'")


def build(inp: Inputs) -> tuple[dict, Builder]:
    b = Builder(inp)
    return b.run(), b


# ---------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------

SCHEMA = {
    "company": [("company_id", "VARCHAR PRIMARY KEY"), ("name", "VARCHAR NOT NULL"), ("legal_name", "VARCHAR"),
                ("kind", "VARCHAR NOT NULL"), ("is_company", "BOOLEAN NOT NULL"), ("sna_sector", "VARCHAR"),
                ("kind_basis", "VARCHAR"), ("kind_basis_pointer", "VARCHAR"), ("parent_company_id", "VARCHAR"),
                ("country", "VARCHAR"), ("website", "VARCHAR"), ("wikidata_qid", "VARCHAR"), ("sec_cik", "VARCHAR"),
                ("ticker", "VARCHAR"), ("lei", "VARCHAR"), ("fortune_global_500", "BOOLEAN"), ("status", "VARCHAR"),
                ("review_status", "VARCHAR NOT NULL"), ("reviewer", "VARCHAR"), ("review_date", "DATE"),
                ("note", "VARCHAR")],
    "company_alias": [("alias", "VARCHAR NOT NULL"), ("company_id", "VARCHAR NOT NULL"), ("source", "VARCHAR NOT NULL")],
    "company_domain": [("domain", "VARCHAR PRIMARY KEY"), ("registrable_domain", "VARCHAR"),
                       ("company_id", "VARCHAR NOT NULL"), ("role", "VARCHAR NOT NULL"),
                       ("confidence", "VARCHAR NOT NULL"), ("source", "VARCHAR NOT NULL"), ("source_pointer", "VARCHAR")],
    "company_namespace": [("host", "VARCHAR NOT NULL"), ("namespace", "VARCHAR NOT NULL"), ("namespace_type", "VARCHAR"),
                          ("company_id", "VARCHAR NOT NULL"), ("relation", "VARCHAR NOT NULL"),
                          ("evidence", "VARCHAR NOT NULL"), ("verified", "BOOLEAN"), ("source_pointer", "VARCHAR"),
                          ("fetched_at", "VARCHAR")],
    "source_registry": [("source_id", "VARCHAR PRIMARY KEY"), ("path", "VARCHAR"), ("sha256", "VARCHAR"),
                        ("url", "VARCHAR"), ("licence", "VARCHAR"), ("fetched_at", "VARCHAR")],
}
ORDER = {"company": "company_id", "company_alias": "alias, company_id, source", "company_domain": "domain",
         "company_namespace": "host, lower(namespace), company_id", "source_registry": "source_id"}


def write_outputs(tables: dict, conflicts: list, out: Path, memory_limit: str = "3GB", threads: int = 2) -> None:
    import duckdb
    out.mkdir(parents=True, exist_ok=True)
    export = out / "export"
    export.mkdir(exist_ok=True)
    tmp = out / "companies.duckdb.tmp"
    for p in (tmp, Path(str(tmp) + ".wal")):
        if p.exists():
            p.unlink()
    con = duckdb.connect(str(tmp), config={"memory_limit": memory_limit, "threads": threads})
    for t, cols in SCHEMA.items():
        con.execute(f"CREATE TABLE {t} ({', '.join(f'{c} {ty}' for c, ty in cols)})")
        names = [c for c, _ in cols]
        data = [tuple(None if r.get(c) == "" else r.get(c) for c in names) for r in tables[t]]
        if data:
            con.executemany(f"INSERT INTO {t} VALUES ({', '.join('?' for _ in names)})", data)
    for t in SCHEMA:
        dst = export / f"{t}.parquet"
        part = export / f"{t}.parquet.tmp"
        con.execute(f"COPY (SELECT * FROM {t} ORDER BY {ORDER[t]}) TO '{part}' (FORMAT parquet)")
        os.replace(part, dst)
    con.close()
    os.replace(tmp, out / "companies.duckdb")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["type", "key", "kept", "other", "source", "detail"], lineterminator="\n")
    w.writeheader()
    w.writerows(conflicts)
    part = export / "conflicts.csv.tmp"
    part.write_text(buf.getvalue(), encoding="utf-8")
    os.replace(part, export / "conflicts.csv")


def summary(tables: dict, b: Builder) -> dict:
    s = {t: len(rows) for t, rows in tables.items()}
    comp = tables["company"]
    s["kind"] = dict(sorted(Counter(c["kind"] for c in comp).items()))
    s["review_status"] = dict(sorted(Counter(c["review_status"] for c in comp).items()))
    s["is_company"] = sum(1 for c in comp if c["is_company"])
    s["confidence"] = dict(sorted(Counter(d["confidence"] for d in tables["company_domain"]).items()))
    s["role"] = dict(sorted(Counter(d["role"] for d in tables["company_domain"]).items()))
    s["relation"] = dict(sorted(Counter(n["relation"] for n in tables["company_namespace"]).items()))
    s["evidence"] = dict(sorted(Counter(n["evidence"].split(";")[0] for n in tables["company_namespace"]).items()))
    s["conflicts"] = dict(sorted(Counter(c["type"] for c in b.conflicts).items()))
    # The dataset (host, owner) pairs.
    best = {}
    for n in tables["company_namespace"]:
        k = (n["host"], n["namespace"].lower())
        cand = (RELATION_RANK[n["relation"]], EVIDENCE_ORDER.index(n["evidence"].split(";")[0]))
        if k not in best or cand < best[k]:
            best[k] = cand
    pairs = b.dataset_pairs
    hit = Counter()
    for k in pairs:
        if k in best:
            rel = [r for r, v in RELATION_RANK.items() if v == best[k][0]][0]
            hit[f"{rel}/{EVIDENCE_ORDER[best[k][1]]}"] += 1
    s["dataset_pairs"] = len(pairs)
    s["dataset_pairs_matched"] = dict(sorted(hit.items()))
    s["dataset_pairs_without_any_row"] = sum(1 for k in pairs if k not in best)
    s["dataset_pairs_without_owns_or_participates"] = sum(1 for k in pairs if k not in best or best[k][0] == 3)
    s["dataset_projects_without_owns_or_participates"] = sum(
        v["projects"] for k, v in pairs.items() if k not in best or best[k][0] == 3)
    s["dataset_projects"] = sum(v["projects"] for v in pairs.values())
    s["map_rows"] = b.stats.get("map_rows")
    s["map_rows_with_comma_in_name"] = b.stats.get("map_odd_rows")
    s["withheld_person_like_names"] = b.stats.get("withheld", 0)
    s["withheld_names_with_at"] = b.stats.get("withheld_at", 0)
    s["roster_user_namespaces_skipped"] = b.stats.get("roster_user_namespaces_skipped", 0)
    s["roster_urls_not_forge"] = b.stats.get("roster_urls_not_forge", 0)
    s["org_links_not_kept"] = b.stats.get("org_links_not_kept", 0)
    s["roster_owns_to_participates"] = b.stats.get("roster_owns_to_participates", 0)
    s["parents"] = {k: v[0] for k, v in sorted(b.parents.items())}
    s["map_firms_not_found"] = b.stats.get("map_firms_not_found")
    s["proposal_invalid_domain"] = b.stats.get("proposal_invalid_domain", 0)
    s["kind_basis"] = dict(sorted(Counter(b for c in comp for b in (c["kind_basis"] or "").split(",") if b).items()))
    s["filled"] = {col: sum(1 for c in comp if c[col] not in ("", None))
                   for col in ("wikidata_qid", "country", "website", "sec_cik", "ticker", "lei", "legal_name",
                               "parent_company_id", "status")}
    s["sna_sector"] = dict(sorted(Counter(c["sna_sector"] or "" for c in comp).items()))
    s["namespace_relation_evidence"] = dict(sorted(Counter(
        f"{n['relation']}/{n['evidence'].split(';')[0]}" for n in tables["company_namespace"]).items()))
    s["web_files"] = b.stats.get("web_files", [])
    s["web_namespace_claims"] = b.stats.get("web_namespace_claims", {})
    s["web_merge"] = b.stats.get("web_merge", {})
    s["proposals_v1_present"] = b.stats.get("proposals_v1_present", False)
    s["proposals_v1"] = b.stats.get("proposals_v1", {})
    s["proposals_v2_present"] = b.stats.get("proposals_v2_present", False)
    s["proposals_v2"] = b.stats.get("proposals_v2", {})
    s["reviewer"] = dict(sorted(Counter(c["reviewer"] or "" for c in comp).items()))
    s["psl"] = "local Public Suffix List (ICANN section)" if b.psl else "fallback rule (last two labels + list)"
    return s


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--version" in argv:
        i = argv.index("--version")
        version = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i:i + 2]
        if version == "v4":   # v4 = the v3 database plus the review (build_companies_v4.py)
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import build_companies_v4
            return build_companies_v4.main(argv)
        if version != "v3":
            raise SystemExit("--version takes v3 (the default) or v4")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--ctp", type=Path, default=CTP_DEFAULT)
    ap.add_argument("--ds", type=Path, default=DS_DEFAULT)
    ap.add_argument("--psl", type=Path, default=None)
    ap.add_argument("--web", type=Path, default=WEB_DEFAULT, help="the normalized web results (W1-W5)")
    ap.add_argument("--memory-limit", default="3GB")
    ap.add_argument("--threads", type=int, default=2)
    a = ap.parse_args(argv)
    inp = Inputs.real(a.ctp, a.ds, a.psl, a.web)
    tables, b = build(inp)
    write_outputs(tables, b.conflicts, a.out, a.memory_limit, a.threads)
    print(json.dumps(summary(tables, b), indent=1, ensure_ascii=False))
    print(f"wrote {tilde(a.out / 'companies.duckdb')} and {tilde(a.out / 'export')}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
