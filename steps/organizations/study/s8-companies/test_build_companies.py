"""Tests for build_companies.py (S8, 2026-10-16).

Run: python -I -B -m pytest -q -p no:cacheprovider test_build_companies.py
     (an interpreter with duckdb and pytest)

Most tests use small fixture files in a temporary folder. The names in the fixtures are
invented. The last tests run the build on the real inputs when they are on this machine and
check the main invariants. No test writes outside its temporary folder.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_companies as bc  # noqa: E402

AT = chr(64)  # the '@' character, so that this file holds no address-like text

MAP = """domain,company,kind,source
(none),(Independent),free_provider,builtin
mailfree.example,(Independent),free_provider,builtin
acme.example,Acme,company,gitdm
acme.co.uk,ACME CORP,company,spinellis-sec
mail.acme.example,Acme,company,cncf-gitdm-single
grid.uni.example,"Lab A, Uni B",academic,gitdm
broken.example,Lab C, Uni D,company,gitdm
solo.example,Jane Roe,company,cncf-gitdm-single
withat.example,someone{AT}x.example,company,cncf-gitdm-single
small.example,Small Shop,company,cncf-gitdm-single
group.example,Group Co,company,cncf-gitdm
uni.example,Uni B,academic,patch
selfish.example,(Independent),independent,rich
""".replace("{AT}", AT)

CANON = """firm_raw,firm,decision,note
ACME CORP,Acme,merge,case only
"""

SPIN = """company,fg500,sec10k,sec20f,cik,domains,strong_rows,owners
"ACME CORP, INC.",True,True,False,12345,acme.example=3,3,1
Big Bank,False,True,False,999,mailfree.example=1,1,1
"""

ORG_LINKS = """owner,company,strong_rows,owner_rows,owner_companies,owner_type,is_verified,website_url,website_on_company_domain,L1,L2,L3,link,reason,fetched_at
acmecorp,"ACME CORP, INC.",1,1,1,Organization,True,https://acme.example,True,True,True,True,kept,,2026-10-06T03:58:35+00:00
acme-labs,"ACME CORP, INC.",1,1,1,Organization,False,,False,True,True,True,kept,,2026-10-06T03:58:35+00:00
someuser,"ACME CORP, INC.",1,1,1,User,,,False,True,True,False,not kept,L3: owner is User,2026-10-06T03:58:35+00:00
"""

PAGES = """org,company,page_url,final_url,fetched_at
acme-labs,"ACME CORP, INC.",https://acme.example/oss,https://acme.example/oss,2026-10-06T04:14:46Z
"""

ROSTER = """org_key,org_kind,project,repo_url,github_slug,roster_status,source_url,fetched_at,note
asf,foundation,Thing,https://github.com/apache/thing,apache/thing,,https://projects.example/,2026-10-05T01:00:00Z,
asf,foundation,Other,https://gitlab.example.org/groups/apache-group,,,https://projects.example/,2026-10-05T01:00:00Z,
"""

REDHAT = """org_key,org_kind,project,repo_url,github_slug,roster_status,source_url,fetched_at,note
redhat,company,RedHatOfficial,https://github.com/RedHatOfficial,,,https://redhat.example/,2026-10-05T01:00:00Z,
redhat,company,Shared,https://github.com/shared-org,,,https://redhat.example/,2026-10-05T01:00:00Z,
"""

REVIEW = """domain,tokens,decision,firm,kind,note,proposal_confidence,reviewer
newco.example,10,edit,New Co,company,a note,high,claude-proposal
acme.example,5,edit,Other Co,company,a note,high,claude-proposal
unsure.example,5,unsure,,,,,claude-proposal
bad{AT}domain.example,5,edit,Bad,company,,high,claude-proposal
""".replace("{AT}", AT)

META = {
    "acmecorp__x": {"clone_url": "https://github.com/AcmeCorp/x.git", "owner": "AcmeCorp", "owner_type": "Organization"},
    "apache__thing": {"clone_url": "https://github.com/Apache/thing.git", "owner": "Apache", "owner_type": "Organization"},
    "smallshop__y": {"clone_url": "https://github.com/smallshop/y.git", "owner": "smallshop", "owner_type": "Organization"},
    "nobody__z": {"clone_url": "https://github.com/nobody/z.git", "owner": "nobody", "owner_type": "User"},
    "grp__w": {"clone_url": "https://gitlab.example.org/apache-group/w", "owner": "apache-group", "owner_type": ""},
}

PSL = """// ===BEGIN ICANN DOMAINS===
example
uk
co.uk
*.ck
!www.ck
// ===END ICANN DOMAINS===
// ===BEGIN PRIVATE DOMAINS===
github.io
// ===END PRIVATE DOMAINS===
"""


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def inputs(tmp_path) -> bc.Inputs:
    t = tmp_path
    return bc.Inputs(
        map_csv=write(t / "ctp/affiliation.merged.csv", MAP),
        firm_canonical_csv=write(t / "ctp/firm_canonical.csv", CANON),
        spinellis_companies=write(t / "sp/companies.csv", SPIN),
        spinellis_org_links=write(t / "sp/org_links.csv", ORG_LINKS),
        company_pages=[write(t / "cp/evidence.csv", PAGES)],
        rosters=[write(t / "rosters/asf.csv", ROSTER), write(t / "rosters/redhat.csv", REDHAT)],
        review_csv=write(t / "fd/review.csv", REVIEW),
        project_meta=write(t / "meta.json", json.dumps(META)),
        psl=write(t / "psl.dat", PSL),
        git=False)


@pytest.fixture
def built(inputs):
    tables, b = bc.build(inputs)
    return tables, b


def by(rows, key):
    return {r[key]: r for r in rows}


# -- parsing ---------------------------------------------------------------------------------

def test_the_map_reader_joins_an_unquoted_comma_and_reports_both_kinds(inputs):
    rows, odd = bc.read_map(inputs.map_csv)
    names = {r["domain"]: r["company"] for r in rows}
    assert names["broken.example"] == "Lab C, Uni D"
    assert names["grid.uni.example"] == "Lab A, Uni B"
    hows = {o["domain"]: o["how"] for o in odd}
    assert hows["broken.example"].startswith("unquoted comma")
    assert hows["grid.uni.example"].startswith("quoted comma")
    assert all(r["source"] in bc.CONFIDENCE for r in rows)


@pytest.mark.parametrize("url,want", [
    ("https://github.com/apache/thing", ("github.com", "apache", "repo")),
    ("https://github.com/RedHatOfficial", ("github.com", "RedHatOfficial", "org")),
    ("https://github.com/orgs/acme/repositories", ("github.com", "acme", "org")),
    ("https://www.github.com/aaif/", ("github.com", "aaif", "org")),
    ("https://github.com/topics/x", None),
    ("https://gitlab.freedesktop.org/groups/xorg", ("gitlab.freedesktop.org", "xorg", "org")),
    ("https://gitlab.eclipse.org/eclipse/aidge/aidge", ("gitlab.eclipse.org", "eclipse/aidge", "repo")),
    ("https://gitlab.com/gnutls/gnutls/-/tree/master", ("gitlab.com", "gnutls", "repo")),
    ("https://git.savannah.gnu.org/cgit/3dldf.git", ("git.savannah.gnu.org", "gnu", "repo")),
    ("git://git.sv.gnu.org/gtick.git", ("git.savannah.gnu.org", "gnu", "repo")),
    ("https://www.apache.org/foo", None),
])
def test_namespace_of(url, want):
    assert bc.namespace_of(url) == want


def test_namespace_of_a_dataset_host_uses_the_path_or_the_host():
    hosts = {"sourceware.org", "git.busybox.net"}
    assert bc.namespace_of("git://sourceware.org/git/glibc.git", hosts) == ("sourceware.org", "git", "repo")
    assert bc.namespace_of("https://git.busybox.net/busybox", hosts) == ("git.busybox.net", "git.busybox.net", "repo")


def test_registrable_domain_with_a_suffix_list_and_with_the_fallback():
    psl = bc.load_psl(PSL)
    assert bc.registrable_domain("mail.acme.co.uk", psl) == "acme.co.uk"
    assert bc.registrable_domain("a.b.example", psl) == "b.example"
    assert bc.registrable_domain("x.y.ck", psl) == "x.y.ck"
    assert bc.registrable_domain("www.ck", psl) == "www.ck"
    assert bc.registrable_domain("me.github.io", psl) == "github.io"  # the private section is not used
    assert bc.registrable_domain("co.uk", psl) == ""
    assert bc.registrable_domain("(none)", psl) == ""
    assert bc.registrable_domain("mail.acme.co.uk", None) == "acme.co.uk"
    assert bc.registrable_domain("mail.acme.example", None) == "acme.example"


# -- names ---------------------------------------------------------------------------------

def test_slug_is_lower_case_and_stable():
    assert bc.slug("Red Hat") == "red-hat"
    assert bc.slug("University of São Paulo") == "university-of-sao-paulo"
    assert bc.slug("Australia &amp; New Zealand Banking Group") == "australia-and-new-zealand-banking-group"
    assert bc.slug("(Independent)") == "independent"
    assert bc.slug("华为").startswith("org-") and bc.slug("华为") == bc.slug("华为")


def test_names_agree_on_legal_forms_and_initials_but_not_on_other_firms():
    assert bc.names_agree("Cisco", "CISCO SYSTEMS, INC.")
    assert bc.names_agree("IBM", "INTERNATIONAL BUSINESS MACHINES CORP")
    assert bc.names_agree("Amazon", "AMAZON COM INC")
    assert not bc.names_agree("Tencent", "Tencent Music Entertainment Group")
    assert not bc.names_agree("Google", "Alphabet Inc.")


def test_person_like_names():
    assert bc.person_like("Jane Roe")
    assert not bc.person_like("Red Hat")
    assert not bc.person_like("Small Shop")
    assert not bc.person_like("Acme")


def test_the_canonical_merge_gives_one_company_with_every_raw_spelling(built):
    tables, _ = built
    comp = by(tables["company"], "company_id")
    assert "acme" in comp and "acme-corp" not in comp
    aliases = {(a["alias"], a["company_id"]) for a in tables["company_alias"]}
    assert {("Acme", "acme"), ("ACME CORP", "acme"), ("ACME CORP, INC.", "acme")} <= aliases
    assert comp["acme"]["legal_name"] == "ACME CORP, INC."
    assert comp["acme"]["sec_cik"] == "0000012345"
    assert comp["acme"]["fortune_global_500"] is True
    assert comp["acme"]["kind_basis"].split(",")[:2] == ["sec-filer", "fortune-global-500"]


# -- domains -------------------------------------------------------------------------------

def test_one_domain_one_company_and_the_conflicts_are_reported(built):
    tables, b = built
    doms = by(tables["company_domain"], "domain")
    assert len(doms) == len(tables["company_domain"])
    assert doms["acme.example"]["company_id"] == "acme"  # the map row wins over the proposal
    assert doms["mailfree.example"]["company_id"] == "free-provider"  # builtin wins over Spinellis
    types = {(c["type"], c["key"]) for c in b.conflicts}
    assert ("proposal-differs-from-map", "acme.example") in types
    assert ("domain-two-companies", "mailfree.example") in types
    assert ("spinellis-domain-is-pseudo-org", "mailfree.example") in types


def test_domain_confidence_and_role(built):
    tables, _ = built
    doms = by(tables["company_domain"], "domain")
    assert doms["acme.example"]["confidence"] == "curated"
    assert doms["acme.co.uk"]["confidence"] == "published"
    assert doms["mail.acme.example"]["confidence"] == "single-developer"
    assert doms["group.example"]["confidence"] == "multi-developer"
    assert doms["newco.example"]["confidence"] == "proposed"
    assert doms["acme.example"]["role"] == "main"
    assert doms["mail.acme.example"]["role"] == "alternative"
    assert doms["mail.acme.example"]["registrable_domain"] == "acme.example"
    mains = [d["company_id"] for d in tables["company_domain"] if d["role"] == "main"]
    assert len(mains) == len(set(mains))


def test_person_like_and_at_names_are_withheld_and_only_the_domain_is_reported(built):
    tables, b = built
    names = {c["name"] for c in tables["company"]} | {a["alias"] for a in tables["company_alias"]}
    assert "Jane Roe" not in names
    assert not any(AT in n for n in names)
    doms = by(tables["company_domain"], "domain")
    assert "solo.example" not in doms and "withat.example" not in doms
    kinds = {(c["type"], c["key"]) for c in b.conflicts}
    assert ("withheld-person-like-name", "solo.example") in kinds
    assert ("withheld-name-with-at", "withat.example") in kinds
    assert not any("Jane" in v for c in b.conflicts for v in c.values())


# -- review status, kind, sector ---------------------------------------------------------------

def test_review_status_rules(built):
    tables, _ = built
    comp = by(tables["company"], "company_id")
    assert comp["acme"]["review_status"] == "accepted"          # gitdm, Spinellis, firm_canonical
    assert comp["small-shop"]["review_status"] == "proposed"    # single-developer CNCF row
    assert comp["small-shop"]["reviewer"] == ""
    assert comp["group-co"]["review_status"] == "proposed"      # multi-developer CNCF row
    assert comp["new-co"]["review_status"] == "proposed"        # claude proposal
    assert comp["new-co"]["reviewer"] == "claude-proposal"
    assert comp["other-co"]["review_status"] == "proposed"      # a proposal never becomes accepted
    assert comp["apache-software-foundation"]["review_status"] == "accepted"  # roster org_kind
    assert comp["independent"]["review_status"] == "accepted"
    assert comp["free-provider"]["review_status"] == "accepted"


@pytest.mark.parametrize("kind,is_company,sector", [
    ("company", True, "S.11"), ("consultancy", True, "S.11"), ("foundation", False, "S.15"),
    ("fiscal-sponsor", False, "S.15"), ("nonprofit", False, "S.15"), ("government", False, "S.13"),
    ("academic", False, ""), ("independent", False, "S.14"), ("project", False, ""),
    ("free-provider", False, ""),
])
def test_the_sector_map_of_each_kind(kind, is_company, sector):
    assert (kind in bc.COMPANY_KINDS) is is_company
    assert bc.SECTOR[kind] == sector


def test_is_company_and_sector_in_the_built_rows(built):
    tables, _ = built
    comp = by(tables["company"], "company_id")
    for c in tables["company"]:
        assert c["kind"] in bc.KINDS
        assert c["is_company"] is (c["kind"] in bc.COMPANY_KINDS)
        assert c["sna_sector"] == bc.SECTOR[c["kind"]]
    assert comp["uni-b"]["kind"] == "academic" and comp["uni-b"]["sna_sector"] == ""
    assert "gov-or-edu-domain" not in comp["uni-b"]["kind_basis"]  # uni.example is not .edu
    assert comp["apache-software-foundation"]["sna_sector"] == "S.15"
    assert comp["independent"]["sna_sector"] == "S.14"
    for col in ("country", "ticker", "lei", "wikidata_qid", "status", "website"):
        assert all(c[col] == "" for c in tables["company"])


# -- namespaces ----------------------------------------------------------------------------

def test_namespace_matching_ignores_case_and_keeps_the_dataset_spelling(built):
    tables, b = built
    ns = {(n["host"], n["namespace"], n["company_id"]): n for n in tables["company_namespace"]}
    acme = ns[("github.com", "AcmeCorp", "acme")]
    assert (acme["relation"], acme["evidence"], acme["verified"]) == ("owns", "verified-domain", True)
    labs = ns[("github.com", "acme-labs", "acme")]
    assert labs["relation"] == "owns" and labs["evidence"] == "company-page;spinellis"
    apache = ns[("github.com", "Apache", "apache-software-foundation")]
    assert apache["relation"] == "owns" and apache["evidence"] == "roster"
    grp = ns[("gitlab.example.org", "apache-group", "apache-software-foundation")]
    assert grp["namespace_type"] == "group"
    s = bc.summary(tables, b)
    assert s["dataset_pairs"] == 5
    assert s["dataset_pairs_matched"]["owns/verified-domain"] == 1
    assert s["dataset_pairs_matched"]["owns/roster"] == 2


def test_name_match_gives_only_candidates_and_never_for_a_user(built):
    tables, _ = built
    ns = {(n["host"], n["namespace"], n["company_id"]): n for n in tables["company_namespace"]}
    shop = ns[("github.com", "smallshop", "small-shop")]
    assert (shop["relation"], shop["evidence"]) == ("candidate", "name-match")
    assert not any(n["namespace"] == "nobody" for n in tables["company_namespace"])
    comp = by(tables["company"], "company_id")
    assert comp["small-shop"]["review_status"] == "proposed"


def test_the_red_hat_roster_participates_except_its_own_org(built):
    tables, _ = built
    ns = {(n["namespace"].lower(), n["company_id"]): n for n in tables["company_namespace"]}
    assert ns[("redhatofficial", "red-hat")]["relation"] == "owns"
    assert ns[("shared-org", "red-hat")]["relation"] == "participates"


# -- output --------------------------------------------------------------------------------

def test_no_at_sign_in_any_output_and_the_build_is_deterministic(inputs, tmp_path):
    duckdb = pytest.importorskip("duckdb")
    t1, b1 = bc.build(inputs)
    t2, _ = bc.build(inputs)
    assert t1 == t2
    out = tmp_path / "out"
    bc.write_outputs(t1, b1.conflicts, out, "1GB", 1)
    assert (out / "companies.duckdb").exists() and not (out / "companies.duckdb.tmp").exists()
    con = duckdb.connect(str(out / "companies.duckdb"), read_only=True)
    for table, cols in bc.SCHEMA.items():
        assert con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == len(t1[table])
        pq = out / "export" / f"{table}.parquet"
        assert con.execute("SELECT count(*) FROM read_parquet(?)", [str(pq)]).fetchone()[0] == len(t1[table])
        for c, ty in cols:
            if ty.startswith("VARCHAR"):
                n = con.execute(f"SELECT count(*) FROM {table} WHERE {c} LIKE '%' || chr(64) || '%'").fetchone()[0]
                assert n == 0, (table, c)
    con.close()
    assert AT not in (out / "export/conflicts.csv").read_text()


def test_check_no_at_stops_the_build():
    with pytest.raises(SystemExit):
        bc.check_no_at({"company": [{"name": "x" + AT + "y"}]})


# -- the real inputs -----------------------------------------------------------------------

REAL = bc.Inputs.real()


@pytest.fixture(scope="module")
def real():
    if not REAL.map_csv.exists():
        pytest.skip("the ctp map is not on this machine")
    return bc.build(REAL)


def test_real_build_has_no_e_mail_like_value(real):
    tables, b = real
    bc.check_no_at(tables)
    bc.check_no_at({"conflicts": b.conflicts})


def test_real_build_keys_and_references(real):
    tables, _ = real
    ids = [c["company_id"] for c in tables["company"]]
    assert len(ids) == len(set(ids))
    idset = set(ids)
    doms = [d["domain"] for d in tables["company_domain"]]
    assert len(doms) == len(set(doms))
    for t in ("company_alias", "company_domain", "company_namespace"):
        assert {r["company_id"] for r in tables[t]} <= idset, t
    assert {c["parent_company_id"] for c in tables["company"]} - {""} <= idset
    keys = [(n["host"], n["namespace"].lower(), n["company_id"]) for n in tables["company_namespace"]]
    assert len(keys) == len(set(keys))


def test_real_build_values_are_in_the_allowed_sets(real):
    tables, _ = real
    for c in tables["company"]:
        assert c["kind"] in bc.KINDS
        assert c["is_company"] is (c["kind"] in bc.COMPANY_KINDS)
        # Wikidata can give S.12 (financial) or the control of an academic unit (S.13, S.15).
        allowed = {bc.SECTOR[c["kind"]]} | ({"S.12"} if c["is_company"] else set()) | \
            ({"S.13", "S.15"} if c["kind"] == "academic" else set())
        assert c["sna_sector"] in allowed
        assert c["review_status"] in ("accepted", "proposed")
        basis = [b for b in (c["kind_basis"] or "").split(",") if b]
        assert basis == sorted(basis, key=bc.BASIS_ORDER.index)
        assert c["sec_cik"] == "" or (len(c["sec_cik"]) == 10 and c["sec_cik"].isdigit())
        if c["reviewer"] == "claude-proposal":
            assert c["review_status"] == "proposed"
    assert {d["confidence"] for d in tables["company_domain"]} <= set(bc.CONF_CLASS)
    assert {d["role"] for d in tables["company_domain"]} <= {"main", "alternative"}
    assert {n["relation"] for n in tables["company_namespace"]} <= set(bc.RELATION_RANK)
    for n in tables["company_namespace"]:
        assert set(n["evidence"].split(";")) <= set(bc.EVIDENCE_ORDER)
        if n["evidence"] == "name-match":
            assert n["relation"] == "candidate"


def test_real_build_counts(real):
    tables, b = real
    s = bc.summary(tables, b)
    assert s["map_rows"] == 4041
    assert len(s["map_rows_with_comma_in_name"]) == 3
    if REAL.project_meta and REAL.project_meta.exists():
        assert s["dataset_pairs"] == 2749
    srcs = {r["source_id"] for r in tables["source_registry"]}
    assert {"ctp-affiliation-merged", "ctp-firm-canonical", "spinellis-2020-companies"} <= srcs
    assert all(len(r["sha256"]) == 64 for r in tables["source_registry"])


# -- version 2: the web results (W1-W5) and the proposals of the top unmatched domains -------

MAP_V2 = MAP + "apache.example,Apache,company,gitdm\n"

W1 = [  # requested_login, website_url, website_host, is_verified
    ("AcmeCorp", "https://www.acme.example/oss", "acme.example", True),
    ("acme-tools", "https://tools.acme.example", "tools.acme.example", True),
    ("acme-unverified", "https://acme.co.uk", "acme.co.uk", False),
    ("someproj", "https://someproj.github.io", "someproj.github.io", True),
    ("mailorg", "https://mailfree.example", "mailfree.example", True),
    ("groupy", "https://group.example", "group.example", True),
    ("Apache", "https://apache.example", "apache.example", True),
]
W2 = [  # host, group_path, web_url
    ("gitlab.example.org", "apache-group", "https://gitlab.example.org/groups/apache-group"),
    ("gitlab.example.org", "acme-grp", "https://acme.example/grp"),
]
L = "VARCHAR[]"
ITEM_COLS = [("qid", "VARCHAR"), ("label", "VARCHAR"), ("instance_of_labels", L), ("country_iso2", L),
             ("parent_qids", L), ("tickers", L), ("sec_cik", L), ("lei", L), ("dissolved", L),
             ("fetched_at", "VARCHAR")]
ACME_LEI, NEWCO_LEI, UNIB_LEI = "ACME00000000000000AA", "NEWC00000000000000BB", "UNIB00000000000000CC"
ITEMS = [
    ("Q10", "Acme", ["public company"], ["DE"], [], ["ACM"], ["0000012345"], [ACME_LEI], []),
    ("Q11", "acme-lib", ["Python package"], [], [], [], [], [], []),
    ("Q12", "Acme Labs", ["business"], [], [], [], [], [], []),
    ("Q20", "Uni B", ["public research university"], ["GB"], [], [], [], [UNIB_LEI], []),
    ("Q40", "New Co", ["subsidiary company"], ["FR"], ["Q10"], [], ["99999"], [NEWCO_LEI], ["2020-01-01"]),
    ("Q50", "Lab C", ["nonprofit organization"], [], [], [], [], [], []),
    ("Q60", "Small Shop", ["business"], [], [], [], [], [], []),
    ("Q80", "Lab A one", ["research institute"], [], [], [], [], [], []),
    ("Q81", "Lab A two", ["research institute"], [], [], [], [], [], []),
]
MATCHES = [("Q10", "P856", "acme.example"), ("Q10", "P2037", "AcmeCorp"), ("Q11", "P856", "acme.example"),
           ("Q12", "P856", "acme.co.uk"), ("Q20", "P856", "uni.example"), ("Q40", "P856", "newco.example"),
           ("Q50", "P856", "broken.example"), ("Q60", "P856", "small.example"),
           ("Q80", "P856", "grid.uni.example"), ("Q81", "P856", "grid.uni.example")]
SEC = [("0000012345", "ACME", "ACME CORP INC"), ("0000099999", "NEWC", "NEW CO INC"),
       ("0000099999", "NEWC2", "NEW CO INC")]
GLEIF_ROWS = [(ACME_LEI, "ACME CORPORATION", None), (NEWCO_LEI, "New Co GmbH", ACME_LEI),
              (UNIB_LEI, "Uni B Trust", ACME_LEI)]
PROPOSALS = f"""domain,name,kind,kind_basis,parent_name,certainty,reason
tiny.example,Tiny Labs,company,manual-review,ACME CORP,high,a reason
acme2.example,ACME,company,manual-review,,medium,a reason
me.example,(Independent),independent,manual-review,,high,personal domain
webmail.example,Webmail,free-provider,manual-review,Acme,high,free mail
maybe.example,Maybe Inc,company,manual-review,,low,a guess
google.com%40abcd-1234,,,,,high,git-svn id
jr.example,John Roe,company,manual-review,,high,a person
"""


def parquet(path: Path, cols: list, rows: list) -> Path:
    duckdb = pytest.importorskip("duckdb")
    con = duckdb.connect()
    con.execute(f"CREATE TABLE t ({', '.join(f'{c} {ty}' for c, ty in cols)})")
    if rows:
        con.executemany(f"INSERT INTO t VALUES ({', '.join('?' for _ in cols)})", rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    con.execute(f"COPY t TO '{path}' (FORMAT parquet)")
    con.close()
    return path


@pytest.fixture
def web_inputs(inputs, tmp_path) -> bc.Inputs:
    w = tmp_path / "web"
    ts = "2026-10-16T21:00:00Z"
    parquet(w / "w1_github_orgs.parquet",
            [("requested_login", "VARCHAR"), ("status", "VARCHAR"), ("typename", "VARCHAR"), ("login", "VARCHAR"),
             ("website_url", "VARCHAR"), ("website_host", "VARCHAR"), ("is_verified", "BOOLEAN"),
             ("fetched_at", "VARCHAR")],
            [(lg, "OK", "Organization", lg, url, host, ver, ts) for lg, url, host, ver in W1])
    parquet(w / "w2_gitlab_groups.parquet",
            [("host", "VARCHAR"), ("group_path", "VARCHAR"), ("status", "VARCHAR"), ("full_path", "VARCHAR"),
             ("web_url", "VARCHAR"), ("fetched_at", "VARCHAR")],
            [(h, g, "OK", g, u, ts) for h, g, u in W2])
    parquet(w / "w3_wikidata_items.parquet", ITEM_COLS, [i + (ts,) for i in ITEMS])
    parquet(w / "w3_wikidata_matches.parquet",
            [("qid", "VARCHAR"), ("match_kind", "VARCHAR"), ("match_value", "VARCHAR"), ("fetched_at", "VARCHAR")],
            [m + (ts,) for m in MATCHES])
    parquet(w / "w4_sec_tickers.parquet",
            [("cik", "VARCHAR"), ("ticker", "VARCHAR"), ("title", "VARCHAR"), ("fetched_at", "VARCHAR")],
            [r + (ts,) for r in SEC])
    parquet(w / "w5_gleif.parquet",
            [("status", "VARCHAR"), ("lei", "VARCHAR"), ("legal_name", "VARCHAR"), ("direct_parent_lei", "VARCHAR"),
             ("fetched_at", "VARCHAR")],
            [("OK", lei, n, p, ts) for lei, n, p in GLEIF_ROWS])
    inputs.map_csv = write(tmp_path / "ctp/affiliation.merged.csv", MAP_V2)
    inputs.web_dir = w
    inputs.proposals_v1 = write(tmp_path / "proposals/top_unmatched.v1.csv", PROPOSALS)
    return inputs


@pytest.fixture
def web_built(web_inputs):
    return bc.build(web_inputs)


def nsmap(tables):
    return {(n["host"], n["namespace"].lower(), n["company_id"]): n for n in tables["company_namespace"]}


def test_w1_fills_the_website_of_an_owned_org_on_a_company_domain(web_built):
    tables, _ = web_built
    comp = by(tables["company"], "company_id")
    assert comp["acme"]["website"] == "https://www.acme.example/oss"
    doms = by(tables["company_domain"], "domain")
    assert doms["acme.example"]["role"] == "main"
    assert comp["small-shop"]["website"] == ""


def test_w1_links_an_org_by_its_website_domain(web_built):
    tables, b = web_built
    ns = nsmap(tables)
    tools = ns[("github.com", "acme-tools", "acme")]
    assert (tools["relation"], tools["evidence"], tools["verified"]) == ("owns", "verified-domain", True)
    unv = ns[("github.com", "acme-unverified", "acme")]
    assert (unv["relation"], unv["evidence"]) == ("candidate", "website-domain")
    names = {k[1] for k in ns}
    assert "someproj" not in names            # github.io is a hosting site
    assert "mailorg" not in names             # a free provider is never linked
    assert "groupy" not in names              # group.example is a multi-developer row of another label
    apache = ns[("github.com", "apache", "apache-software-foundation")]
    assert apache["evidence"] == "roster"     # the roster row is not overridden
    assert b.stats["web_namespace_claims"]["roster-row-kept"] == 1


def test_w2_links_a_group_by_its_website_and_not_by_its_own_forge(web_built):
    tables, _ = web_built
    ns = nsmap(tables)
    grp = ns[("gitlab.example.org", "acme-grp", "acme")]
    assert (grp["relation"], grp["evidence"], grp["namespace_type"]) == ("candidate", "website-domain", "group")
    assert ns[("gitlab.example.org", "apache-group", "apache-software-foundation")]["evidence"] == "roster"


def test_w3_takes_the_organisation_item_with_both_matches_and_fills_the_columns(web_built):
    tables, b = web_built
    comp = by(tables["company"], "company_id")
    acme = comp["acme"]
    assert acme["wikidata_qid"] == "Q10"      # not Q11 (a package) and not Q12 (one match only)
    assert acme["country"] == "DE"
    assert acme["lei"] == ACME_LEI
    assert acme["sec_cik"] == "0000012345"
    assert "wikidata-instance-of" in acme["kind_basis"].split(",")
    assert "wikidata:Q10" in acme["kind_basis_pointer"]
    newco = comp["new-co"]
    assert (newco["wikidata_qid"], newco["country"], newco["status"]) == ("Q40", "FR", "defunct")
    assert newco["sec_cik"] == "0000099999"
    assert newco["parent_company_id"] == "acme"          # P749 Q10 is the item of acme
    assert comp["small-shop"]["wikidata_qid"] == ""      # small.example is a single-developer row
    assert comp["lab-a-uni-b"]["wikidata_qid"] == ""     # two items, no tie-break: a conflict
    types = {(c["type"], c["key"]) for c in b.conflicts}
    assert ("wikidata-several-items", "lab-a-uni-b") in types


def test_w3_class_gives_sector_and_kind_conflicts_but_does_not_change_the_kind(web_built):
    tables, b = web_built
    comp = by(tables["company"], "company_id")
    assert comp["uni-b"]["sna_sector"] == "S.13"          # "public research university"
    assert "wikidata-instance-of" in comp["uni-b"]["kind_basis"]
    lab = comp["lab-c-uni-d"]
    assert lab["kind"] == "company" and lab["wikidata_qid"] == "Q50"
    assert "wikidata-instance-of" not in lab["kind_basis"]
    assert any(c["type"] == "kind-differs" and c["key"] == "lab-c-uni-d" and c["source"] == "w3-wikidata-items"
               for c in b.conflicts)


def test_w4_sec_gives_sec_filer_legal_name_and_the_main_ticker(web_built):
    tables, _ = web_built
    comp = by(tables["company"], "company_id")
    newco = comp["new-co"]
    assert "sec-filer" in newco["kind_basis"].split(",")
    assert newco["legal_name"] == "NEW CO INC"
    assert newco["ticker"] == "NEWC"
    assert comp["acme"]["legal_name"] == "ACME CORP, INC."  # not blank, so it stays
    assert comp["acme"]["ticker"] == "ACME"


def test_w5_gleif_gives_registry_id_legal_name_and_parent(web_built):
    tables, _ = web_built
    comp = by(tables["company"], "company_id")
    uni = comp["uni-b"]
    assert "registry-id" in uni["kind_basis"].split(",")
    assert uni["legal_name"] == "Uni B Trust"
    assert uni["parent_company_id"] == "acme"
    assert "w5-gleif" in uni["note"]
    assert comp["new-co"]["parent_company_id"] == "acme"     # W3 came first; GLEIF agrees


def test_kind_basis_is_a_comma_separated_set_in_the_basis_order(web_built):
    tables, _ = web_built
    for c in tables["company"]:
        basis = [x for x in (c["kind_basis"] or "").split(",") if x]
        assert basis == sorted(set(basis), key=bc.BASIS_ORDER.index)
        assert len(basis) == len([p for p in c["kind_basis_pointer"].split(" | ") if p])
    acme = by(tables["company"], "company_id")["acme"]["kind_basis"].split(",")
    assert acme[:4] == ["sec-filer", "fortune-global-500", "registry-id", "wikidata-instance-of"]


def test_the_proposals_of_the_top_unmatched_domains(web_built):
    tables, b = web_built
    comp = by(tables["company"], "company_id")
    doms = by(tables["company_domain"], "domain")
    tiny = comp["tiny-labs"]
    assert (tiny["review_status"], tiny["reviewer"]) == ("proposed", "claude-proposal-v1")
    assert tiny["parent_company_id"] == "acme"
    assert "manual-review" not in tiny["kind_basis"]
    assert doms["tiny.example"]["source"] == "claude-proposal-v1"
    assert doms["tiny.example"]["confidence"] == "proposed"
    assert doms["acme2.example"]["company_id"] == "acme"         # the same normalized name
    assert comp["acme"]["review_status"] == "accepted"
    assert doms["me.example"]["company_id"] == "independent"
    assert doms["webmail.example"]["company_id"] == "free-provider"
    assert "webmail" not in comp
    assert "maybe.example" not in doms and "jr.example" not in doms
    assert "John Roe" not in {c["name"] for c in tables["company"]}
    types = {(c["type"], c["key"]) for c in b.conflicts}
    assert ("proposal-low-certainty", "maybe.example") in types
    assert ("domain-with-at", "google.com") in types
    assert ("withheld-person-like-name", "jr.example") in types
    assert b.stats["proposals_v1"]["used"] == 4
    assert not any("%40" in d for d in doms)


def test_web_files_are_registered_with_their_licence(web_built):
    tables, _ = web_built
    reg = by(tables["source_registry"], "source_id")
    assert reg["w3-wikidata-items"]["licence"] == "CC0"
    assert reg["w5-gleif"]["licence"] == "CC0"
    assert reg["w4-sec-tickers"]["licence"] == "public domain (US government work)"
    assert reg["w1-github-orgs"]["licence"] == "API terms; facts only"
    assert reg["w2-gitlab-groups"]["licence"] == "API terms; facts only"
    assert reg["proposals-top-unmatched-v1"]["sha256"]
    assert all(len(r["sha256"]) == 64 for r in tables["source_registry"])


def test_the_v2_build_is_deterministic_and_has_no_at_sign(web_inputs, tmp_path):
    t1, b1 = bc.build(web_inputs)
    t2, _ = bc.build(web_inputs)
    assert t1 == t2
    bc.check_no_at(t1)
    bc.check_no_at({"conflicts": b1.conflicts})


def test_the_build_works_without_the_web_files_and_the_proposals(built):
    tables, b = built
    assert b.stats["proposals_v1_present"] is False
    assert all(c["wikidata_qid"] == "" for c in tables["company"])


# -- version 3: the second round of proposals, and dataset values with a typo ----------------

PROPOSALS_V2 = """domain,name,kind,kind_basis,parent_name,certainty,reason
tiny.example,Other Name,company,manual-review,,high,in v1 too: v1 wins
intel.example_,Intelish,company,manual-review,,medium,a typo in the dataset value
.lead.example,Leading Labs,company,manual-review,Acme,high,a stray dot
trail.example.,Trail Systems,company,manual-review,,high,a trailing dot
quote.example”,Quote Labs,academic,manual-review,,medium,a stray quote
space .example,Space Labs,company,manual-review,,high,whitespace
freemail2.example,Freemail Two,free-provider,manual-review,Google,high,free mail
me2.example,(Independent),independent,manual-review,,high,personal domain
low2.example,Low Labs,company,manual-review,,low,a guess
unk2.example,,,,,unknown,no idea
"""


@pytest.fixture
def v3_inputs(web_inputs, tmp_path) -> bc.Inputs:
    web_inputs.proposals_v2 = write(tmp_path / "proposals/top_unmatched.v2.csv", PROPOSALS_V2)
    return web_inputs


@pytest.mark.parametrize("value,ok", [
    ("intel.com_", True), ("tue.nl”", True), (".thomsonreuters.com", True), ("monsoon.(none)", True),
    ("inspur.com/cncf/gitdm", True), ("(none)", True), ("a b.example", False), ("x" + AT + "y.example", False),
    ("google.com%40abcd", False), ("tab\t.example", False), ("", False),
])
def test_valid_domain_keeps_odd_dataset_values_but_not_whitespace_or_at(value, ok):
    assert bc.valid_domain(value) is ok


def test_registrable_domain_is_blank_for_a_value_that_is_not_a_host_name():
    psl = bc.load_psl(PSL)
    assert bc.registrable_domain("intel.example_", psl) == ""
    assert bc.registrable_domain(".lead.example", psl) == ""
    assert bc.registrable_domain("x.lead.example", psl) == "lead.example"


def test_the_second_round_of_proposals(v3_inputs):
    tables, b = bc.build(v3_inputs)
    comp = by(tables["company"], "company_id")
    doms = by(tables["company_domain"], "domain")
    assert doms["tiny.example"]["source"] == "claude-proposal-v1"        # v1 wins
    assert "other-name" not in comp
    for d in ("intel.example_", ".lead.example", "trail.example.", "quote.example”"):
        assert doms[d]["source"] == "claude-proposal-v2"                  # the exact value stays
        assert doms[d]["confidence"] == "proposed"
    assert doms["intel.example_"]["registrable_domain"] == ""
    assert "space .example" not in doms
    assert comp["intelish"]["reviewer"] == "claude-proposal-v2"
    assert comp["intelish"]["review_status"] == "proposed"
    assert comp["leading-labs"]["parent_company_id"] == "acme"
    assert comp["quote-labs"]["kind"] == "academic"
    assert doms["freemail2.example"]["company_id"] == "free-provider"
    assert "freemail-two" not in comp
    assert doms["me2.example"]["company_id"] == "independent"
    assert "low2.example" not in doms and "unk2.example" not in doms
    types = {(c["type"], c["key"]) for c in b.conflicts}
    assert ("proposal-low-certainty", "low2.example") in types
    assert ("proposal-low-certainty", "unk2.example") in types
    assert ("proposal-not-usable", "(invalid)") in types                  # the value with a space
    st = b.stats["proposals_v2"]
    assert st["in-earlier-round"] == 1 and st["used"] == 6 and st["low-or-unknown"] == 2
    reg = by(tables["source_registry"], "source_id")
    assert reg["proposals-top-unmatched-v2"]["sha256"]
    bc.check_no_at(tables)


def test_the_build_works_without_the_second_round(web_built):
    _, b = web_built
    assert b.stats["proposals_v2_present"] is False
