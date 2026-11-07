#!/usr/bin/env python3
"""Build the company database v4 (S8): version 3 plus the review (2026-10-18).

    build_companies_v4.py [--out DIR] [--v3-db FILE] [--review DIR] [--manual DIR] [--ds DIR]
                          [--ctp DIR] [--web DIR] [--psl FILE] [--memory-limit 3GB] [--threads 2]
    build_companies.py --version v4 [the same options]

v4 reads the v3 database (DIR/companies.duckdb, which it does not change) and applies, for one item,
the first of: the user's decisions (review/decisions.csv wins over review/decisions.chat.csv), the
main session's fixes (manual/v4_edits.csv, manual/v4_merges.csv), the final AI answers
(review/ai/part-1..10.csv, a higher part wins), and v3. The domain decisions (rounds 4d and 4f
after review/ai/rule_corrections.csv, and the user's review/decisions.domains.chat.csv, which wins)
are applied before the merges, so that a merge never moves a dropped domain to the kept id.
New organisations come from manual/v4_new_orgs.csv, and the parents and universities of the
public-research rows from manual/v4_public_research.csv. README.md (section "Version 4") gives
the rules. v4.2 (2026-10-19) adds the fixes of the ownership and DNS studies: manual/v42_new_orgs.csv
(read with v4_new_orgs.csv), manual/v42_merges.csv (read with v4_merges.csv), and
manual/v42_fields.csv and manual/v42_domains.csv (field patches and domain moves after all v4.1
steps; a field that a user decision set keeps the user's value). v4.3 (2026-10-19) applies the
namespace rule of the user (firm_based_on_namespace names the organisation that controls the
account; a hosting foundation is the relation hosted_by): manual/v43_namespaces.csv and the private
review/v43_namespaces.private.csv (the relation of each namespace and organisation pair),
manual/v43_new_orgs.csv (the project rows and foundations that control an account) and
manual/v43_fields.csv (the parents of existing project rows). It runs after the v4.2 step.
v4.4 (2026-10-20) applies the web checks of round 9 (the v4.3 audit items and the DNS review lists):
manual/v44_new_orgs.csv, manual/v44_merges.csv, manual/v44_fields.csv (also kind and sna_sector),
manual/v44_domains.csv (move, add or drop) and manual/v44_namespaces.csv (the columns of
v43_namespaces.csv; the relation (remove) removes the row of the pair). It runs after the v4.3 step.
v4.5 (2026-10-20) applies the user's answers to the v4.4 audit: a fiscal sponsor
has the relation sponsored_by (each hosted_by or owns row of an organisation of kind fiscal-sponsor
becomes sponsored_by), an OSGeo community project or a project that the OSGeo directory only lists
is not hosted (manual/v45_namespaces.csv and the private review/v45_namespaces.private.csv remove
those hosted_by rows), and manual/v45_fields.csv sets the parents of the two project rows that lose
OSGeo. It runs after the v4.4 step.
v4.6 (2026-10-21, the final v4 layer) applies the new rule N2 of the user: OSGeo hosts every project
of its directory (official, incubating, community and listed). manual/v46_namespaces.csv and the
private review/v46_namespaces.private.csv add back the 48 hosted_by rows of OSGeo that v4.5 removed,
as they were in v4.4 (the optional columns row_evidence, namespace_type, source_pointer and
fetched_at give the fields of the row). The parents that v4.5 set stay. It runs after the v4.5 step.
v4.7 (2026-10-25) applies AI round 10: the web checks of the new domains and namespaces of the
1,000-4,999 commit layer of the dataset (review/AI_ROUNDS.md, round 10). manual/v47_new_orgs.csv,
manual/v47_merges.csv, manual/v47_fields.csv, manual/v47_domains.csv (add, move or drop) with the
private review/v47_domains.private.csv (the personal domains, which go to the row independent), and
manual/v47_namespaces.csv with the private review/v47_namespaces.private.csv (the accounts of
persons). It runs after the v4.6 step.
v4.8 (2026-10-25) applies AI round 11: the organisation accounts of the 5,000+ commit layer with no
owns row in v4.7, judged with the same class rule (the user: both layers use one rule). The files are
manual/v48_*.csv and the private review/v48_namespaces.private.csv (the same columns as v4.7). It
runs after the v4.7 step.
v4.9 (2026-10-25, trial) applies the user's answers of the audit pages v47 and v48 and the second
check of the unsure items: manual/v49_*.csv and the private review/v49_*.private.csv (the same
columns as v4.7). It runs after the v4.8 step.
--layer v4.2 leaves the v4.3 to v4.9 steps out (the v4.2 tables); --layer v4.3 leaves v4.4 to v4.9
out; --layer v4.4 leaves v4.5 to v4.9 out; --layer v4.5 leaves v4.6 to v4.9 out; --layer v4.6
leaves v4.7 to v4.9 out (the v4.6 tables); --layer v4.7 leaves v4.8 and v4.9 out (the v4.7 tables);
--layer v4.8 leaves v4.9 out (the v4.8 tables).

Output (--db-name and --export-name change the two names): DIR/companies.v4.duckdb, DIR/export-v4/<table>.parquet, DIR/export-v4/conflicts.csv,
DIR/export-v4/v4_stats.json, DIR/export-v4/deferred.csv and DIR/export-v4/qids_unverified.csv.
No value may hold '@': the build stops if one does.
"""
from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_companies as bc  # noqa: E402

V4_DATE = "2026-10-18"
V42_DATE = "2026-10-19"
V43_DATE = "2026-10-19"
V44_DATE = "2026-10-20"
V45_DATE = "2026-10-20"
V46_DATE = "2026-10-21"
V47_DATE = "2026-10-25"
V48_DATE = "2026-10-25"
V49_DATE = "2026-10-25"
LAYERS = ("v4.2", "v4.3", "v4.4", "v4.5", "v4.6", "v4.7", "v4.8", "v4.9")
NS_REMOVE = "(remove)"     # manual/v44_namespaces.csv: remove the row of the (namespace, organisation) pair
# Relations of company_namespace. hosted_by (v4.3): a foundation hosts a project of the namespace,
# but the account is not the foundation's (the user, 2026-10-19). sponsored_by (v4.5): a fiscal sponsor
# sponsors a project of the namespace (the user, 2026-10-20); a fiscal sponsor is never owns or hosted_by.
# Only owns gives firm_based_on_namespace.
NS_RELATIONS = ("owns", "hosted_by", "sponsored_by", "participates", "candidate")
REL_RANK = dict(bc.RELATION_RANK, hosted_by=1.5, sponsored_by=1.6)
FISCAL_SPONSOR = "fiscal-sponsor"     # the kind of a fiscal sponsor (K6)
# The classes of manual/v43_namespaces.csv: who controls the account.
V43_CLASSES = ("foundation", "company", "organisation", "project", "person", "unclear")
V43_EVIDENCE = "account-profile"
# The fields that manual/v42_fields.csv can set.
V42_FIELDS = ("parent_company_id", "university_id", "lei", "legal_name", "sec_cik", "country", "name",
              "status", "wikidata_qid")
# manual/v44_fields.csv can also set the kind (a kind change sets the sector of the kind; a later
# sna_sector row of the file wins) and the sector.
V44_FIELDS = V42_FIELDS + ("kind", "sna_sector")
KINDS = bc.KINDS + ("public-research",)
COMPANY_KINDS = bc.COMPANY_KINDS
SECTOR = dict(bc.SECTOR, **{"public-research": "S.13"})
SECTOR_RX = re.compile(r"^S\.1[1-5]$")
BLANK = "(blank)"
FIELDS = ("kind", "name", "parent_company_id", "merge_into", "sna_sector", "qid", "university_id")
DOMAIN_CONFLICTS = ("proposal-low-certainty", "withheld-person-like-name", "proposal-differs-from-map",
                    "domain-two-companies", "spinellis-domain-is-pseudo-org")
CLAIM_BY_ID_ONLY = ("domain-two-companies", "spinellis-domain-is-pseudo-org")   # accept keeps the kept row
USER = ("user", "user (ai)")
RANK_USER, RANK_CHAT, RANK_MANUAL = 1000, 900, 500     # AI part N has rank N
DOMAIN_SOURCES = (("ai/domain_links_review.csv", "review-4d", 10), ("ai/lookalike_review.csv", "review-4f", 11),
                  ("decisions.domains.chat.csv", "review-user", RANK_USER))
# Round 7 (the user's final audit, 2026-10-18): a blind sweep of every domain row of v4. It runs
# after the merges, so its company_id is the final organisation of the domain.
# The user's domain decisions run again in this pass: a decision that names the organisation after
# a merge (kernel.org -> linux-foundation) only matches here.
# Round 8 (the open conflicts of v4.1): domain answers and the own domains of kept organisations.
SWEEP_SOURCES = (("ai/sweep_review.csv", "review-7", 12), ("ai/conflict_domains.csv", "review-8", 13),
                 ("decisions.domains.chat.csv", "review-user", RANK_USER))
CORRECTION_FILE = {"r4/lookalike-out": "ai/lookalike_review.csv", "r4/domains-out": "ai/domain_links_review.csv",
                   "r7/sweep-out": "ai/sweep_review.csv", "r8/conflicts-out": "ai/conflict_domains.csv"}

SCHEMA = copy.deepcopy(bc.SCHEMA)
_i = [c for c, _ in SCHEMA["company"]].index("parent_company_id") + 1
SCHEMA["company"].insert(_i, ("university_id", "VARCHAR"))
SCHEMA["company_domain_dropped"] = [("domain", "VARCHAR PRIMARY KEY"), ("company_id", "VARCHAR"),
                                    ("reason", "VARCHAR NOT NULL"), ("source", "VARCHAR NOT NULL")]
ORDER = dict(bc.ORDER, company_domain_dropped="domain")
CONFLICT_COLS = ["type", "key", "kept", "other", "source", "detail"]
# conflicts.csv also says how each conflict ended (round 8, the user's final audit, 2026-10-18)
CONFLICT_OUT_COLS = CONFLICT_COLS + ["state", "resolution", "resolved_by"]
STATE_RESOLVES = ("domain-of-rejected-organisation",)   # the end state of the domain is the resolution


SMALL_WORDS = {"and", "of", "the", "for", "de", "la", "le", "du", "des", "der", "und", "y", "e"}


def label_agrees(name: str, label: str) -> bool:
    """True when a Wikidata label names the organisation `name`: the same normalised words, a legal
    or generic-word variant (build_companies.names_agree), one word list a prefix of the other
    ('Infor' and 'Infor Global Solutions'), or initials without small words ('CSIRO')."""
    if not name or not label:
        return False
    a, b = bc.norm_name(name).split(), bc.norm_name(label).split()
    if not a or not b:
        return False
    if a == b or bc.names_agree(name, label) or bc.names_agree(label, name):
        return True
    if a[:len(b)] == b or b[:len(a)] == a:
        return True
    for x, y in ((a, b), (b, a)):
        if len(x) == 1 and len(y) > 1 and x[0] == "".join(w[0] for w in y if w not in SMALL_WORDS):
            return True
    return False


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@dataclass
class Inputs:
    v3_db: Path
    review_dir: Path
    manual_dir: Path
    v3_conflicts: Path | None = None
    w3_items: Path | None = None
    proposals: tuple = ()                 # (source_id, path) of the proposal files
    firm_review_csv: Path | None = None
    map_suspects_csv: Path | None = None
    map_csv: Path | None = None
    psl: Path | None = None
    script: Path | None = None
    git: bool = True
    layer: str = "v4.9"

    @classmethod
    def real(cls, out: Path, ds: Path = bc.DS_DEFAULT, ctp: Path = bc.CTP_DEFAULT, web: Path = bc.WEB_DEFAULT,
             psl: Path | None = None, v3_db: Path | None = None, review: Path | None = None,
             manual: Path | None = None) -> "Inputs":
        s8 = ds / "s8-companies"
        v3_db = v3_db or out / "companies.duckdb"
        return cls(v3_db=v3_db, review_dir=review or v3_db.parent / "review",
                   manual_dir=manual or s8 / "manual", v3_conflicts=v3_db.parent / "export/conflicts.csv",
                   w3_items=web / "w3_wikidata_items.parquet",
                   proposals=(("proposals-top-unmatched-v1", s8 / "proposals/top_unmatched.v1.csv"),
                              ("proposals-top-unmatched-v2", s8 / "proposals/top_unmatched.v2.csv")),
                   firm_review_csv=ds / "firm-domains/review.csv", map_suspects_csv=ds / "firm-domains/map_suspects.csv",
                   map_csv=ctp / "data/affiliation.merged.csv", psl=psl or bc.find_psl(),
                   script=Path(__file__).resolve())


class V4:
    def __init__(self, inp: Inputs):
        self.inp = inp
        self.conf: list[dict] = []
        self.stats: Counter = Counter()
        self.deferred: list[dict] = []
        self.unverified: dict[str, dict] = {}
        self.registry: list[dict] = []
        self.field_rank: dict = {}
        self.merge_req: dict[str, list] = defaultdict(list)
        self.keep_ids: dict[str, int] = {}
        self.rejected: dict[str, str] = {}
        self.reject_rank: dict[str, int] = {}
        self.merge_to: dict[str, str] = {}
        self.merge_ctx: dict[str, str] = {}
        self.kept_name: dict[str, str] = {}
        self.manual_domains: set[str] = set()
        self.typed: dict[str, str] = {}
        self.dropped: dict[str, dict] = {}
        self.domain_dec: dict[str, dict] = {}
        self.user_dom_done: set[str] = set()
        self.late_merges: list[tuple] = []
        self.psl = bc.load_psl(Path(inp.psl).read_text(encoding="utf-8")) if inp.psl else None

    # -- small helpers -------------------------------------------------------------------------
    def conflict(self, t: str, key: str, kept: str = "", other: str = "", source: str = "", detail: str = "") -> None:
        self.conf.append({"type": t, "key": key or "", "kept": kept or "", "other": other or "",
                          "source": source or "", "detail": detail or ""})

    def register(self, sid: str, path: Path | None) -> None:
        if path is None or not Path(path).exists():
            return
        url = ""
        if self.inp.git:
            commit, _ = bc.git_info(Path(path))
            url = f"git:{commit}" if commit else ""
        self.registry.append({"source_id": sid, "path": bc.tilde(path), "sha256": bc.sha256(Path(path)),
                              "url": url, "licence": "", "fetched_at": ""})

    def index_add(self, name: str, cid: str) -> None:
        if name:
            self.names[name.strip().lower()].add(cid)

    def resolve(self, value: str, context: str = "", quiet: bool = False) -> str | None:
        """A typed id or name -> an id: the id itself, else the one organisation with that exact name
        or alias (without case). None, and a conflict row, when no or several organisations match."""
        v = (value or "").strip()
        if not v or v == BLANK:
            return None
        if v in self.comp:
            return v
        if v.lower() in self.typed and self.typed[v.lower()] in self.comp:
            self.stats["typed_names_resolved_by_file"] += 1
            return self.typed[v.lower()]
        hits = sorted(self.names.get(v.lower(), set()) & set(self.comp))
        if len(hits) == 1:
            if not quiet:
                self.stats["typed_names_resolved"] += 1
            return hits[0]
        if not quiet:
            self.conflict("unresolved-name", v, "", ";".join(hits), context,
                          "several organisations have this name" if hits else "no organisation has this name or id")
        return None

    def final_id(self, cid: str | None) -> str | None:
        seen = set()
        while cid in self.merge_to and cid not in seen:
            seen.add(cid)
            cid = self.merge_to[cid]
        return cid

    # -- load ----------------------------------------------------------------------------------
    def load(self) -> None:
        import duckdb
        con = duckdb.connect(str(self.inp.v3_db), read_only=True)

        def rows(t: str) -> list[dict]:
            cols = [c for c, _ in bc.SCHEMA[t]]
            out = []
            for r in con.execute(f"SELECT {', '.join(cols)} FROM {t} ORDER BY {bc.ORDER[t]}").fetchall():
                d = {}
                for c, v in zip(cols, r):
                    d[c] = v.isoformat() if hasattr(v, "isoformat") else ("" if v is None else v)
                out.append(d)
            return out
        self.comp = {r["company_id"]: dict(r, university_id="") for r in rows("company")}
        self.alias = rows("company_alias")
        self.dom = {r["domain"]: r for r in rows("company_domain")}
        self.ns = rows("company_namespace")
        self.registry = rows("source_registry")
        con.close()
        self.v3_kind = {c: r["kind"] for c, r in self.comp.items()}
        self.v3_status = {c: r["review_status"] for c, r in self.comp.items()}
        self.v3_owner = {d: r["company_id"] for d, r in self.dom.items()}
        self.v3_main = {d for d, r in self.dom.items() if r["role"] == "main"}
        self.v3_ndom = Counter(self.v3_owner.values())
        self.names: dict[str, set] = defaultdict(set)
        for c, r in self.comp.items():
            self.index_add(r["name"], c)
        for a in self.alias:
            self.index_add(a["alias"], a["company_id"])
        self.register("v3-company-db", self.inp.v3_db)
        self.v3_conflicts = read_csv(self.inp.v3_conflicts) if self.inp.v3_conflicts and Path(
            self.inp.v3_conflicts).exists() else []
        self.w3 = {}
        if self.inp.w3_items and Path(self.inp.w3_items).exists():
            con = duckdb.connect()
            cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{self.inp.w3_items}')").fetchall()}
            iso2 = "country_iso2" if "country_iso2" in cols else "NULL::VARCHAR[]"
            for q, label, labels, cc in con.execute(f"SELECT qid, label, instance_of_labels, {iso2} FROM "
                                                    f"read_parquet('{self.inp.w3_items}')").fetchall():
                self.w3[q] = {"label": label or "", "instance_of_labels": list(labels or []), "country": list(cc or [])}
            con.close()
        self.load_proposals()

    def load_proposals(self) -> None:
        """(source, domain) -> (name, kind, parent name) of the rows that v3 did not use."""
        self.prop = {}
        for sid, p in self.inp.proposals:
            if p and Path(p).exists():
                for r in read_csv(Path(p)):
                    self.prop[(sid, bc.norm_domain(r["domain"]))] = (r["name"].strip(), r["kind"].strip(),
                                                                     r.get("parent_name", "").strip())
        for sid, p in (("firm-domains-review", self.inp.firm_review_csv),
                       ("firm-domains-map-suspects", self.inp.map_suspects_csv)):
            if p and Path(p).exists():
                for r in read_csv(Path(p)):
                    self.prop[(sid, bc.norm_domain(r["domain"]))] = (r["firm"].strip(), r["kind"].strip(), "")
        if self.inp.map_csv and Path(self.inp.map_csv).exists():
            rows, _ = bc.read_map(Path(self.inp.map_csv))
            for r in rows:
                self.prop.setdefault((r["source"].strip(), bc.norm_domain(r["domain"])),
                                     (r["company"].strip(), r["kind"].strip(), ""))

    # -- answers -------------------------------------------------------------------------------
    def load_answers(self) -> dict:
        rd, md = self.inp.review_dir, self.inp.manual_dir
        items = json.loads((rd / "review_items.json").read_text(encoding="utf-8"))["items"]
        self.items = {i["id"]: i for i in items}
        self.register("review-items", rd / "review_items.json")
        layers = []
        parts = sorted((rd / "ai").glob("part-*.csv"), key=lambda p: int(p.stem.split("-")[1]))
        for p in parts:
            layers.append((int(p.stem.split("-")[1]), f"ai/{p.name}", p))
        layers += [(RANK_MANUAL, "manual/v4_edits.csv", md / "v4_edits.csv"),
                   (RANK_CHAT, "decisions.chat.csv", rd / "decisions.chat.csv"),
                   (RANK_USER, "decisions.csv", rd / "decisions.csv")]
        final = {}
        for rank, label, p in layers:
            if not p.exists():
                continue
            self.register("review-" + label.replace("/", "-").removesuffix(".csv"), p)
            for r in read_csv(p):
                by = (r.get("decided_by") or "").strip()
                if label.startswith("decisions") and by not in USER:
                    continue     # an AI suggestion in decisions.csv is not a decision
                r = {k: (v or "").strip() for k, v in r.items() if k}
                r.update(_rank=rank, _src=label, _user=by in USER)
                old = final.get(r["item_id"])
                if old and old["_user"] and r["_user"] and old.get("decided_utc", "") > r.get("decided_utc", ""):
                    self.stats["user_decisions_replaced_by_later_chat"] += 1
                    continue     # two user decisions: the later one wins (a chat answer after a review.html save)
                final[r["item_id"]] = r
                self.stats[f"answers_read:{label}"] += 1
        self.stats["items_with_answer"] = len(final)
        return final

    def reviewer(self, ans: dict) -> tuple[str, str]:
        if ans["_user"]:
            return "user", (ans.get("decided_utc") or V4_DATE)[:10]
        return ans.get("decided_by") or "claude-main", V4_DATE

    def mark(self, cid: str, ans: dict, changed: bool) -> None:
        r = self.comp.get(cid)
        if r is None:
            return
        who, date = self.reviewer(ans)
        if changed:
            r["review_status"] = "ai-reviewed"
        elif ans["action"] == "accept":
            if ans["_user"]:
                r["review_status"] = "accepted"
            elif r["review_status"] != "accepted":
                r["review_status"] = "accepted-ai"
            else:
                return
        else:
            return
        r["reviewer"], r["review_date"] = who, date

    # -- new organisations ---------------------------------------------------------------------
    def new_org(self, cid: str, name: str, kind: str, sector: str, by: str, pointer: str, status: str = "",
                country: str = "", date: str = V4_DATE) -> str:
        self.comp[cid] = {c: "" for c, _ in SCHEMA["company"]}
        self.comp[cid].update(company_id=cid, name=name, kind=kind, is_company=kind in COMPANY_KINDS,
                              sna_sector=sector, kind_basis="manual-review", kind_basis_pointer=pointer,
                              country=country, review_status=status or ("accepted" if by in USER else "ai-reviewed"),
                              reviewer="user" if by in USER else by, review_date=date, fortune_global_500=None)
        self.index_add(name, cid)
        self.alias.append({"alias": name, "company_id": cid, "source": "v4-new-organisation"})
        self.stats["new_organisations"] += 1
        return cid

    def load_typed_names(self) -> None:
        """manual/v4_typed_names.csv: the main session's reading of a typed name that is no name or
        alias of the database (rule 1 of V4_TODO)."""
        self.typed = {}
        p = self.inp.manual_dir / "v4_typed_names.csv"
        if p.exists():
            self.register("manual-v4-typed-names", p)
            for r in read_csv(p):
                self.typed[r["typed"].strip().lower()] = r["company_id"].strip()

    def add_new_orgs(self) -> None:
        for fname, sid, date in (("v4_new_orgs.csv", "manual-v4-new-orgs", V4_DATE),
                                 ("v42_new_orgs.csv", "manual-v42-new-orgs", V42_DATE)):
            self.add_new_orgs_file(fname, sid, date)

    def add_new_orgs_file(self, fname: str, sid: str, date: str) -> None:
        p = self.inp.manual_dir / fname
        if not p.exists():
            return
        self.register(sid, p)
        rows = read_csv(p)
        for r in rows:
            cid = r["company_id"].strip()
            if cid in self.comp:
                self.conflict("new-organisation-exists", cid, cid, "", f"manual/{fname}", "the id is in v3")
                continue
            if cid in getattr(self, "merge_to", {}):
                self.conflict("new-organisation-exists", cid, self.final_id(cid), "", f"manual/{fname}",
                              "the id is a merged id")
                continue
            kind = bc.clean_kind(r["kind"])
            if kind not in KINDS:
                self.conflict("unknown-kind", cid, "", kind, f"manual/{fname}", "")
                continue
            self.new_org(cid, r["name"].strip(), kind, r["sna_sector"].strip(), r["decided_by"].strip(),
                         f"manual/{fname}#company_id={cid}", country=r["country"].strip(), date=date)
            self.stats["new_organisations_manual"] += 1
            for a in [x.strip() for x in r["aliases"].split(";") if x.strip()]:
                moved = [x for x in self.alias if x["alias"] == a]
                for x in moved:
                    self.names[a.lower()].discard(x["company_id"])
                    x["company_id"] = cid
                if not moved:
                    self.alias.append({"alias": a, "company_id": cid, "source": "v4-new-organisation"})
                self.index_add(a, cid)
            for d in [x.strip() for x in r["domains"].split(";") if x.strip()]:
                if d.startswith("*."):
                    for dd in sorted(x for x in self.dom if x.endswith(d[1:])):
                        self.assign(dd, cid, "curated", sid, f"manual/{fname}#domain={d}")
                else:
                    self.assign(d, cid, "curated", sid, f"manual/{fname}#domain={d}")
        for r in rows:     # parents after all rows exist
            cid, par = r["company_id"].strip(), r["parent_company_id"].strip()
            if par and cid in self.comp:
                pid = self.resolve(par, f"manual/{fname}:{cid}")
                if pid:
                    self.comp[cid]["parent_company_id"] = pid

    # -- domains -------------------------------------------------------------------------------
    def assign(self, d: str, cid: str, confidence: str, source: str, pointer: str) -> None:
        """Give the domain d to cid: move its row, or add a row (a domain that v3 matched by a suffix)."""
        d = bc.norm_domain(d)
        if not bc.valid_domain(d):
            self.conflict("invalid-domain", d if "@" not in d else "(withheld)", "", cid, source, "")
            return
        self.dropped.pop(d, None)
        if source in ("manual-v4-new-orgs", "manual-v42-new-orgs"):
            self.manual_domains.add(d)
        r = self.dom.get(d)
        if r is not None:
            if r["company_id"] != cid:
                r["company_id"], r["role"] = cid, "alternative"
                r["source_pointer"] = pointer
                self.stats["domains_moved"] += 1
            return
        self.dom[d] = {"domain": d, "registrable_domain": bc.registrable_domain(d, self.psl) or "",
                       "company_id": cid, "role": "alternative", "confidence": confidence, "source": source,
                       "source_pointer": pointer}
        self.stats["domains_added"] += 1

    def drop(self, d: str, cid: str, reason: str, source: str) -> None:
        if d in self.dom:
            del self.dom[d]
        self.dropped[d] = {"domain": d, "company_id": cid, "reason": reason, "source": source}
        self.stats[f"domains_dropped:{reason}"] += 1

    def domain_decisions(self, sources=DOMAIN_SOURCES) -> None:
        rd = self.inp.review_dir
        files = {f for f, _, _ in sources}
        corr = rd / "ai/rule_corrections.csv"
        fixes = defaultdict(list)
        if corr.exists():
            self.register("review-ai-rule-corrections", corr)
            for c in read_csv(corr):
                f = next((v for k, v in CORRECTION_FILE.items() if c["file"].startswith(k)), None)
                if f in files:
                    fixes[(f, c["link_or_item_id"])].append(c)
                elif f is None and sources is DOMAIN_SOURCES:
                    self.conflict("rule-correction-not-applied", c["link_or_item_id"], "", "", c["file"],
                                  "the file of the correction is not a domain review")
        dec = {}
        for fname, src, rank in sources:
            p = rd / fname
            if not p.exists():
                continue
            self.register(src, p)
            for r in read_csv(p):
                r = {k: (v or "").strip() for k, v in r.items() if k}
                for c in fixes.pop((fname, r["link_id"]), []):
                    want = c["from"].split(" ", 1)
                    have = (r["action"], r.get("move_to", "")) if r["action"] == "move" else (r["action"],)
                    to = c["to"].split(" ", 1)
                    if tuple(want) == have or tuple(to) == have:
                        r["action"], r["move_to"] = to[0], (to[1] if len(to) > 1 else "")
                        self.stats["rule_corrections_applied"] += 1
                    else:
                        self.conflict("rule-correction-not-applied", r["link_id"], " ".join(have), c["to"], fname,
                                      "the row does not hold the value that the correction expects")
                r.update(_rank=rank, _src=src, _user=rank == RANK_USER)
                d = bc.norm_domain(r["domain"])
                if d in dec and dec[d]["_rank"] > rank:
                    continue
                if d in dec and sources is not DOMAIN_SOURCES and r["_user"] and not dec[d]["_user"]:
                    self.stats["sweep_rows_superseded_by_user"] += 1     # a user decision wins over the sweep
                dec[d] = r
        for (fname, lid), cs in sorted(fixes.items()):
            self.conflict("rule-correction-not-applied", lid, "", "", fname, "no row has this link_id")
        for d in sorted(dec):
            r = dec[d]
            cid = r["company_id"]
            if sources is not DOMAIN_SOURCES and cid in self.merge_to:
                cid = self.final_id(cid)      # the row names an organisation that merged into another
                r = dict(r, company_id=cid)
            cur = self.dom[d]["company_id"] if d in self.dom else None
            if d in self.manual_domains:
                self.stats["domain_decisions_superseded_by_new_orgs"] += 1
                continue
            if r["_user"] and d in self.user_dom_done:
                continue     # the first pass applied it
            if sources is not DOMAIN_SOURCES and d in self.domain_dec and self.domain_dec[d]["_user"]:
                self.stats["sweep_rows_superseded_by_user"] += 1     # a user decision wins over the sweep
                continue
            if cur is not None and cur != cid and r["_user"] and sources is DOMAIN_SOURCES:
                self.stats["user_domain_decisions_for_the_second_pass"] += 1
                continue     # the organisation can match after the merges
            if cur is not None and cur != cid:
                self.conflict("domain-decision-company-differs", d, cur, cid, r["_src"],
                              f"{r['action']}: the decision names another organisation; no change")
                continue
            self.domain_dec[d] = r
            if r["_user"]:
                self.user_dom_done.add(d)
            act = r["action"]
            self.stats[f"domain_decisions:{act}"] += 1
            if act == "keep":
                if cur is None and r["_user"]:   # the user keeps a domain that has no row (yet): give it the row
                    self.assign(d, cid, "curated", r["_src"], f"{r['_src']}#link={r['link_id']}")
                continue
            if act == "drop":
                self.drop(d, cid, "domain-decision", r["_src"])
            elif act == "move":
                tgt = self.resolve(r["move_to"], f"{r['_src']}:{r['link_id']}")
                if tgt is None:
                    del self.domain_dec[d]
                    continue
                self.assign(d, tgt, "curated" if r["_user"] else "proposed", r["_src"], f"{r['_src']}#link={r['link_id']}")
                self.stats["domain_moves"] += 1
            else:
                self.conflict("unknown-action", d, "", act, r["_src"], "")

    # -- fields --------------------------------------------------------------------------------
    def set_field(self, cid: str, f: str, value, ans: dict) -> bool:
        k = (cid, f)
        if self.field_rank.get(k, -1) > ans["_rank"]:
            return False
        r = self.comp[cid]
        if r[f] == value:
            return False
        self.field_rank[k] = ans["_rank"]
        r[f] = value
        self.stats[f"field_changed:{f}"] += 1
        return True

    def apply_fields(self, cid: str, ans: dict, ctx: str) -> bool:
        r = self.comp.get(cid)
        if r is None:
            self.conflict("unknown-id", cid, "", "", ctx, "the decision names an id that is not in the database")
            return False
        changed = False
        kind = ans.get("kind", "")
        if kind:
            k = bc.clean_kind(kind)
            if k not in KINDS:
                self.conflict("unknown-kind", cid, r["kind"], kind, ctx, "")
            elif k != r["kind"] and self.set_field(cid, "kind", k, ans):
                changed = True
                r["is_company"] = k in COMPANY_KINDS
                r["kind_basis"], r["kind_basis_pointer"] = "manual-review", f"review:{ctx}"
                if not ans.get("sna_sector"):
                    self.set_field(cid, "sna_sector", SECTOR[k], ans)
        name = ans.get("name", "")
        if name == BLANK:
            self.conflict("decision-not-applied", cid, r["name"], BLANK, ctx, "a name cannot be blank")
        elif name and name != r["name"]:
            old = r["name"]
            if self.set_field(cid, "name", name, ans):
                changed = True
                self.alias.append({"alias": old, "company_id": cid, "source": "v3-name"})
                self.alias.append({"alias": name, "company_id": cid, "source": "v4-review"})
                self.index_add(name, cid)
        sec = ans.get("sna_sector", "")
        if sec:
            v = "" if sec == BLANK else sec
            if v and not SECTOR_RX.match(v):
                self.conflict("unknown-sector", cid, r["sna_sector"], sec, ctx, "")
            elif self.set_field(cid, "sna_sector", v, ans):
                changed = True
        for f in ("parent_company_id", "university_id"):
            v = ans.get(f, "")
            if not v:
                continue
            if v == BLANK:
                changed |= self.set_field(cid, f, "", ans)
                continue
            pid = self.resolve(v, ctx)
            if pid is None:
                continue
            if pid == cid:
                self.conflict("reference-to-self", cid, "", pid, ctx, f)
                continue
            changed |= self.set_field(cid, f, pid, ans)
        q = ans.get("qid", "")
        if q:
            changed |= self.apply_qid(cid, q, ans, ctx)
        return changed

    def apply_qid(self, cid: str, q: str, ans: dict, ctx: str) -> bool:
        r = self.comp[cid]
        if q == BLANK:
            return self.set_field(cid, "wikidata_qid", "", ans)
        q = q.strip().upper()
        if not re.fullmatch(r"Q\d+", q):
            self.conflict("qid-check-failed", cid, r["wikidata_qid"], q, ctx, "not a Wikidata id")
            return False
        if q == r["wikidata_qid"]:
            return False
        item = self.w3.get(q)
        if item is None:
            self.conflict("qid-unverified", cid, r["wikidata_qid"], q, ctx,
                          "the item is not in w3_wikidata_items.parquet; fetch it (s8_fetch.py w3 --qids) and check it")
            self.unverified[q] = {"qid": q, "company_id": cid, "current_qid": r["wikidata_qid"], "source": ctx}
            return False
        names = [r["name"], r["legal_name"]] + [a["alias"] for a in self.alias if a["company_id"] == cid]
        label = item["label"]
        agree = any(label_agrees(n, label) for n in names)
        if not bc.wd_classes(item):
            self.conflict("qid-check-failed", cid, r["wikidata_qid"], q, ctx, "the item has no organisation class")
            return False
        if not agree:
            self.conflict("qid-check-failed", cid, r["wikidata_qid"], q, ctx, "the item label differs from the names")
            return False
        if r["country"] and item.get("country") and r["country"] not in item["country"]:
            self.conflict("qid-check-failed", cid, r["wikidata_qid"], q, ctx, "the item country differs")
            return False
        other = [c for c, x in self.comp.items() if x["wikidata_qid"] == q and c != cid]
        if other:
            self.conflict("wikidata-item-two-companies", q, cid, ";".join(sorted(other)), ctx, "the QID was not set")
            return False
        self.stats["qids_set"] += 1
        return self.set_field(cid, "wikidata_qid", q, ans)

    # -- items ---------------------------------------------------------------------------------
    def request_merge(self, x: str, k: str, rank: int, ctx: str) -> None:
        if x == k:
            return
        if x in bc.PSEUDO_IDS:
            self.conflict("decision-not-applied", x, "", k, ctx, "a pseudo organisation is never merged")
            return
        self.merge_req[x].append((rank, k, ctx))

    def company_item(self, iid: str, ans: dict) -> None:
        cid = iid.split(":", 1)[1]
        ctx = f"{ans['_src']}:{iid}"
        if cid not in self.comp:
            self.conflict("unknown-id", cid, "", "", ctx, "the item names an id that is not in the database")
            return
        act = ans["action"]
        mi = ans.get("merge_into", "")
        if mi and mi != BLANK:
            k = self.resolve(mi, ctx, quiet=True)
            if k:
                self.request_merge(cid, k, ans["_rank"], ctx)
                self.stats["merge_requests"] += 1
                return
            # the target can be a new organisation that a domain conflict adds later: try again then
            self.late_merges.append((cid, mi, ans["_rank"], ctx))
            if act == "reject":
                return            # an unresolved duplicate: the conflict row asks for the id
        if act == "reject":
            if cid in bc.PSEUDO_IDS:
                self.conflict("decision-not-applied", cid, "", "", ctx, "a pseudo organisation is never rejected")
                return
            self.rejected[cid] = ctx
            self.reject_rank[cid] = ans["_rank"]
            return
        if act in ("accept", "edit"):
            changed = self.apply_fields(cid, ans, ctx)
            self.mark(cid, ans, changed)
            self.stats[f"company_items:{act}{'-changed' if changed else ''}"] += 1
        else:
            self.conflict("unknown-action", cid, "", act, ctx, "")

    def proposal_of(self, item: dict) -> tuple[str, str, str]:
        return self.prop.get((item.get("source", ""), bc.norm_domain(item["key"])), ("", "", ""))

    def claim_of(self, item: dict, ans: dict) -> dict | None:
        """The organisation that a decision on a domain conflict gives the domain (None: no change)."""
        ct, act, ctx = item["conflict_type"], ans["action"], f"{ans['_src']}:{item['id']}"
        if act == "reject":
            return None
        mi = ans.get("merge_into", "")
        if mi and mi != BLANK:
            tgt = self.resolve(mi, ctx)
            return {"id": tgt, "ctx": ctx, "ans": ans} if tgt else None
        if ct in CLAIM_BY_ID_ONLY:
            if act == "edit":
                self.conflict("decision-not-applied", item["key"], item.get("kept", ""), item.get("other", ""), ctx,
                              "an edit without a target organisation")
            return None
        pname, pkind, pparent = self.proposal_of(item)
        if ct == "proposal-differs-from-map" and not ans.get("name"):
            if act == "edit" and not ans.get("kind"):
                self.conflict("decision-not-applied", item["key"], item.get("kept", ""), item.get("other", ""), ctx,
                              "an edit without a target organisation")
                return None
            tgt = self.resolve(item.get("other", ""), ctx, quiet=True)
            if tgt and act == "accept":
                return {"id": tgt, "ctx": ctx, "ans": ans}
        name = ans.get("name") or pname or (item.get("other", "") if ct != "withheld-person-like-name" else "")
        kind = bc.clean_kind(ans.get("kind") or pkind or "company")
        if kind == "free-provider" or name == bc.PSEUDO["free-provider"][0]:
            return {"id": "free-provider", "ctx": ctx, "ans": ans}
        if kind == "independent" or name == bc.PSEUDO["independent"][0]:
            return {"id": "independent", "ctx": ctx, "ans": ans}
        if not name or name == BLANK:
            self.conflict("decision-not-applied", item["key"], "", "", ctx, "the proposal has no name")
            return None
        tgt = self.resolve(name, ctx, quiet=True)
        if tgt is None and bc.slug(name) in self.comp:
            tgt = bc.slug(name)
        if tgt:
            return {"id": tgt, "ctx": ctx, "ans": ans}
        if kind not in KINDS:
            self.conflict("unknown-kind", item["key"], "", kind, ctx, "")
            return None
        return {"id": None, "new": (bc.slug(name), name, kind, pparent), "ctx": ctx, "ans": ans}

    def domain_conflicts(self, todo: list) -> None:
        claims = defaultdict(list)
        for item, ans in todo:
            c = self.claim_of(item, ans)
            if c:
                claims[bc.norm_domain(item["key"])].append(c)
        for d in sorted(claims):
            cs = sorted(claims[d], key=lambda c: -c["ans"]["_rank"])
            win = cs[0]
            dd = self.domain_dec.get(d)
            tid = lambda c: c["id"] or c["new"][0]  # noqa: E731
            both_user = dd is not None and dd["_user"] and win["ans"]["_user"]
            dd_later = both_user and dd.get("decided_utc", "") >= win["ans"].get("decided_utc", "")
            if dd_later:
                # The user's later domain decision replaces the user's earlier item decision.
                self.stats["user_item_decisions_replaced_by_later_domain_decision"] += 1
                continue
            if dd is not None and not both_user and not (win["ans"]["_user"] and not dd["_user"]):
                eff = {"keep": dd["company_id"], "drop": "", "move": self.resolve(dd["move_to"], "", True) or ""}[dd["action"]]
                if tid(win) != eff:
                    self.conflict("domain-decisions-disagree", d, eff or "(dropped)", tid(win), dd["_src"],
                                  f"the domain decision wins over {win['ctx']}")
                continue
            for c in cs[1:]:
                if tid(c) != tid(win):
                    self.conflict("domain-decisions-disagree", d, tid(win), tid(c), win["ctx"], f"the first wins over {c['ctx']}")
            ans = win["ans"]
            if win["id"] is None and win["new"][0] in self.comp:
                win["id"] = win["new"][0]
            if win["id"] is None:
                cid, name, kind, pparent = win["new"]
                by = ans.get("decided_by", "")
                status = ("accepted" if ans["_user"] else "accepted-ai") if ans["action"] == "accept" else ""
                who, date = self.reviewer(ans)
                self.new_org(cid, name, kind, ans.get("sna_sector", "") if ans.get("sna_sector") != BLANK else "",
                             "user" if ans["_user"] else by, f"review:{win['ctx']}",
                             status=status, date=date)
                self.comp[cid]["reviewer"] = who
                if not self.comp[cid]["sna_sector"]:
                    self.comp[cid]["sna_sector"] = SECTOR.get(kind, "")
                self.stats["new_organisations_from_proposals"] += 1
                par = ans.get("parent_company_id") or pparent
                if par and par != BLANK:
                    pid = self.resolve(par, win["ctx"])
                    if pid and pid != cid:
                        self.comp[cid]["parent_company_id"] = pid
                tgt = cid
            else:
                tgt = win["id"]
                k = bc.clean_kind(ans.get("kind", "")) if ans.get("kind") else ""
                if k and k != self.comp[tgt]["kind"]:
                    if not ans.get("name") and k in KINDS and tgt not in bc.PSEUDO_IDS:
                        # The answer names no other organisation, so its kind is the kind of the target.
                        sub = {"kind": k, "sna_sector": ans.get("sna_sector", ""), "_rank": ans["_rank"],
                               "_src": ans["_src"], "_user": ans["_user"], "action": "edit",
                               "decided_by": ans.get("decided_by", ""), "decided_utc": ans.get("decided_utc", "")}
                        changed = self.apply_fields(tgt, sub, win["ctx"])
                        self.mark(tgt, sub, changed)
                        if not changed:
                            self.conflict("kind-differs", tgt, self.comp[tgt]["kind"], k, win["ctx"],
                                          "a higher decision set the kind; the kind stays")
                    else:
                        self.conflict("kind-differs", tgt, self.comp[tgt]["kind"], k, win["ctx"],
                                      "the decision names another organisation that is merged into this one; the kind stays")
            src = win["ctx"].split(":")[0]
            self.assign(d, tgt, "curated" if ans["_user"] else "proposed", "review-" + src.replace("/", "-"),
                        f"review:{win['ctx']}")
            self.stats["domain_conflicts_applied"] += 1

    def namespace_decision(self, item: dict, ans: dict, ctx: str) -> None:
        host, _, nspace = item["key"].partition("/")
        others = [o for o in item.get("other", "").split(";") if o]
        m = re.search(r"\b[Oo]wner:?\s+([a-z0-9][a-z0-9-]*)", ans.get("note", ""))
        owner = m.group(1) if m else ""
        if not owner or owner not in self.comp:
            self.conflict("decision-not-applied", item["key"], "", item.get("other", ""), ctx,
                          "the note names no owner id of the database")
            return
        rows = [n for n in self.ns if n["host"] == host and n["namespace"].lower() == nspace.lower()]
        have = {n["company_id"] for n in rows}
        if owner not in have:
            base = rows[0] if rows else {"namespace_type": "", "verified": None, "fetched_at": ""}
            self.ns.append({"host": host, "namespace": rows[0]["namespace"] if rows else nspace,
                            "namespace_type": base["namespace_type"], "company_id": owner, "relation": "owns",
                            "evidence": "roster", "verified": base["verified"], "source_pointer": f"review:{ctx}",
                            "fetched_at": base["fetched_at"]})
        note = ans.get("note", "")
        for n in list(rows):
            if n["company_id"] == owner:
                n["relation"] = "owns"
            elif re.search(re.escape(n["company_id"]) + r"[^.;]*\bparticipates", note) or n["company_id"] not in note:
                n["relation"] = "participates"
            else:
                self.ns.remove(n)
                self.stats["namespace_rows_removed"] += 1
        self.stats["namespace_decisions"] += 1

    def conflict_item(self, item: dict, ans: dict) -> str:
        ct, act, ctx = item["conflict_type"], ans["action"], f"{ans['_src']}:{item['id']}"
        key = item["key"]
        if ct in ("kind-differs", "wikidata-several-items", "sec-cik-differs"):
            if act in ("accept", "edit") and any(ans.get(f) for f in FIELDS):
                changed = self.apply_fields(key, ans, ctx)
                self.mark(key, ans, changed)
            return "applied"
        if ct == "spinellis-name-differs":
            if act == "edit" and any(ans.get(f) for f in FIELDS):
                self.mark(item.get("kept", ""), ans, self.apply_fields(item.get("kept", ""), ans, ctx))
            return "applied"
        if ct == "possible-duplicate":
            mi = ans.get("merge_into", "")
            if mi and mi != BLANK:
                k = self.resolve(mi, ctx)
                pair = {item.get("kept", ""), item.get("other", "")}
                if k in pair:
                    for x in sorted(pair - {k}):
                        self.request_merge(x, k, ans["_rank"], ctx)
                        self.stats["merge_requests"] += 1
            return "applied"
        if ct == "namespace-two-owners":
            if act == "edit":
                self.namespace_decision(item, ans, ctx)
            return "applied"
        if act == "edit":
            self.conflict("decision-not-applied", key, item.get("kept", ""), item.get("other", ""), ctx,
                          f"no rule applies an edit of a {ct} row")
        return "applied"

    def decisions(self, final: dict) -> None:
        dom_todo = []
        for iid in sorted(final):
            ans = final[iid]
            item = self.items.get(iid)
            if item is None and not iid.startswith("company:"):
                self.conflict("unknown-item", iid, "", "", ans["_src"], "the item id is not in review_items.json")
                continue
            self.stats[f"final_answers:{ans['_src']}"] += 1
            if ans["action"] == "defer":
                self.deferred.append({"item_id": iid, "type": (item or {}).get("conflict_type") or "company",
                                      "key": (item or {}).get("key") or iid.split(":", 1)[1], "source": ans["_src"]})
                continue
            if iid.startswith("company:"):
                self.company_item(iid, ans)
            elif item["conflict_type"] in DOMAIN_CONFLICTS:
                dom_todo.append((item, ans))
            else:
                self.conflict_item(item, ans)
        self.domain_conflicts(dom_todo)
        for cid, mi, rank, ctx in self.late_merges:
            k = self.resolve(mi, ctx)     # a conflict row when the name is still unknown
            if k:
                self.request_merge(cid, k, rank, ctx)
                self.stats["merge_requests_after_new_orgs"] += 1

    def manual_merges(self) -> None:
        for fname, sid in (("v4_merges.csv", "manual-v4-merges"), ("v42_merges.csv", "manual-v42-merges")):
            self.manual_merges_file(fname, sid)

    def manual_merges_file(self, fname: str, sid: str) -> None:
        p = self.inp.manual_dir / fname
        if not p.exists():
            return
        self.register(sid, p)
        for r in read_csv(p):
            x, k = r["merge_id"].strip(), r["into_id"].strip()
            for c in (x, k):
                if c not in self.comp:
                    self.conflict("unknown-id", c, "", "", f"manual/{fname}", "")
            if x in self.comp and k in self.comp:
                self.request_merge(x, k, RANK_MANUAL, f"manual/{fname}")
                self.keep_ids[k] = RANK_MANUAL
                if r.get("kept_name", "").strip():
                    self.kept_name[k] = r["kept_name"].strip()

    # -- merges and rejects --------------------------------------------------------------------
    def merges(self) -> None:
        self.merge_to = {}
        for x in sorted(self.merge_req):
            reqs = sorted(self.merge_req[x], key=lambda t: (-t[0], t[1]))
            rank, k, ctx = reqs[0]
            if self.keep_ids.get(x, -1) > rank:
                self.stats["merges_overridden_by_kept_id"] += 1
                continue
            for r2, k2, c2 in reqs[1:]:
                if k2 != k:
                    self.conflict("merge-targets-differ", x, k, k2, ctx, f"the first wins over {c2}")
            if x in self.rejected:
                if self.reject_rank.get(x, -1) > rank:
                    self.conflict("merge-overridden-by-reject", x, "", k, self.rejected[x], f"the reject wins over {ctx}")
                    continue
                del self.rejected[x]
            self.merge_to[x] = k
            self.merge_ctx[x] = ctx
        # Cycles: no merge in a cycle.
        for x in sorted(self.merge_to):
            seen, c = [], x
            while c in self.merge_to and c not in seen:
                seen.append(c)
                c = self.merge_to[c]
            if c in seen:
                cyc = seen[seen.index(c):]
                for y in cyc:
                    self.merge_to.pop(y, None)
                self.conflict("merge-cycle", x, "", ";".join(sorted(cyc)), "", "the ids merge into each other; no merge")
        for x in sorted(self.merge_to):
            k = self.final_id(x)
            if k in self.rejected:
                self.conflict("merge-into-rejected", x, k, "", self.merge_ctx.get(x, ""), "both are rejected")
                self.rejected[x] = self.merge_ctx.get(x, "")
                continue
            self.merge_one(x, k)
        for x in [x for x in self.merge_to if x in self.rejected]:
            del self.merge_to[x]
        for k, name in sorted(self.kept_name.items()):
            if k in self.comp and self.comp[k]["name"] != name:
                self.alias.append({"alias": self.comp[k]["name"], "company_id": k, "source": "v3-name"})
                self.comp[k]["name"] = name

    def merge_one(self, x: str, k: str) -> None:
        if x not in self.comp or k not in self.comp:
            self.conflict("unknown-id", x, k, "", "merge", "")
            return
        xr = self.comp.pop(x)
        self.alias.append({"alias": xr["name"], "company_id": k, "source": "v4-merge"})
        self.alias.append({"alias": x, "company_id": k, "source": "v4-merge-id"})
        for a in self.alias:
            if a["company_id"] == x:
                a["company_id"] = k
        for d, r in self.dom.items():
            if r["company_id"] == x:
                r["company_id"], r["role"] = k, "alternative"
                self.stats["domains_moved_by_merge"] += 1
        for n in self.ns:
            if n["company_id"] == x:
                n["company_id"] = k
        for r in self.comp.values():
            for f in ("parent_company_id", "university_id"):
                if r[f] == x:
                    r[f] = k
        kr = self.comp[k]
        for f in () if k in bc.PSEUDO_IDS else ("wikidata_qid", "sec_cik", "lei", "country", "website", "legal_name"):
            if not kr[f] and xr[f] and not (f == "wikidata_qid" and any(r["wikidata_qid"] == xr[f] for r in self.comp.values())):
                kr[f] = xr[f]
        self.stats["merges"] += 1

    def rejects(self) -> None:
        for x in sorted(self.rejected):
            if x not in self.comp:
                continue
            ctx = self.rejected[x]
            for d in sorted(d for d, r in self.dom.items() if r["company_id"] == x):
                self.conflict("domain-of-rejected-organisation", d, "", x, ctx, "the domain row was dropped")
                self.drop(d, x, "organisation-rejected", ctx)
            n0 = len(self.ns)
            self.ns = [n for n in self.ns if n["company_id"] != x]
            self.stats["namespace_rows_of_rejected"] += n0 - len(self.ns)
            self.alias = [a for a in self.alias if a["company_id"] != x]
            for c, r in self.comp.items():
                for f in ("parent_company_id", "university_id"):
                    if r[f] == x:
                        self.conflict("reference-to-rejected", c, x, "", ctx, f"{f} cleared")
                        r[f] = ""
            del self.comp[x]
            self.stats["rejected"] += 1

    # -- the rest ------------------------------------------------------------------------------
    def public_research(self) -> None:
        p = self.inp.manual_dir / "v4_public_research.csv"
        if not p.exists():
            return
        self.register("manual-v4-public-research", p)
        for r in read_csv(p):
            cid = self.final_id(r["company_id"].strip())
            if cid not in self.comp:
                self.conflict("unknown-id", r["company_id"], "", "", "manual/v4_public_research.csv", "")
                continue
            for f in ("parent_company_id", "university_id"):
                v = r[f].strip()
                if not v:
                    continue
                pid = self.final_id(self.resolve(v, f"manual/v4_public_research.csv:{cid}"))
                if pid and self.comp[cid][f] != pid:
                    if self.comp[cid][f]:
                        self.stats[f"public_research_{f}_replaced"] += 1
                    self.comp[cid][f] = pid
                    self.stats[f"public_research_{f}_set"] += 1

    # -- v4.2: the fixes of the ownership and DNS studies (2026-10-19) ---------------------------
    def v42_mark(self, cid: str, by: str, date: str = V42_DATE) -> None:
        r = self.comp[cid]
        r["review_status"], r["reviewer"], r["review_date"] = "ai-reviewed", by or "claude-main", date

    def v42_id(self, value: str, src: str) -> str | None:
        """An id, a merged id (-> the kept id) or a name -> the final id."""
        v = (value or "").strip()
        if v in self.merge_to:
            return self.final_id(v)
        return self.final_id(self.resolve(v, src))

    def v42_fixes(self) -> None:
        """manual/v42_fields.csv (company_id, field, value) and manual/v42_domains.csv (domain,
        company_id, action move or add). They run after all v4.1 steps, on the final ids. A field that
        a user decision set (rank of decisions.csv or decisions.chat.csv) keeps the user's value."""
        self.field_file("v42_fields.csv", "manual-v42-fields", "v42", V42_DATE)
        self.domain_file("v42_domains.csv", "manual-v42-domains", "v42", V42_DATE)

    def domain_file(self, fname: str, sid: str, tag: str, date: str, actions=("move", "add"),
                    path: Path | None = None) -> None:
        """A domain file (domain, company_id, action, decided_by, reason, source_url) on the final ids.
        move: the domain row goes to company_id; add: a new row; drop (v4.4 and later): the row of
        company_id goes to company_domain_dropped. A domain of a user domain decision is not changed.
        path: a file outside manual/ (v4.7: the private file of the personal domains)."""
        p = path or self.inp.manual_dir / fname
        if not p.exists():
            return
        self.register(sid, p)
        pu = self.inp.review_dir / "decisions.domains.chat.csv"
        user_domains = {bc.norm_domain(x.get("domain", "")) for x in read_csv(pu)} if pu.exists() else set()
        label = tag.replace("v4", "v4.", 1)
        for r in read_csv(p):
            d, act = bc.norm_domain(r["domain"]), r["action"].strip()
            src = f"{'review' if path else 'manual'}/{fname}#domain={d}"
            cid = self.v42_id(r["company_id"], src)
            if cid not in self.comp:
                continue
            cur = self.dom.get(d)
            if d in user_domains:
                self.conflict(f"{tag}-user-decision-wins", d, cur["company_id"] if cur else "", cid, src,
                              f"a user domain decision holds this domain; the {label} move is not applied")
                continue
            if act not in actions:
                self.conflict("unknown-action", d, "", act, src, "")
                continue
            if act in ("move", "drop") and cur is None:
                self.conflict(f"{tag}-domain-missing", d, "", cid, src, f"a {act} needs a domain row")
                continue
            if act == "drop":
                if cur["company_id"] != cid:
                    self.conflict(f"{tag}-domain-owner-differs", d, cur["company_id"], cid, src, "the drop names another owner")
                    continue
                self.drop(d, cid, (r.get("reason") or "")[:200] or f"{tag}-drop", sid)
                self.stats[f"{tag}_domains_drop"] += 1
                self.v42_mark(cid, r.get("decided_by", "").strip(), date)
                continue
            if act == "add" and cur is not None and cur["company_id"] != cid:
                self.conflict(f"{tag}-domain-exists", d, cur["company_id"], cid, src, "use move")
                continue
            if cur is not None and cur["company_id"] == cid:
                self.stats[f"{tag}_domains_unchanged"] += 1
                continue
            self.assign(d, cid, "curated", sid, src)
            self.stats[f"{tag}_domains_{act}"] += 1
            self.v42_mark(cid, r.get("decided_by", "").strip(), date)

    def field_file(self, fname: str, sid: str, tag: str, date: str, allowed=V42_FIELDS) -> None:
        """A field patch file (company_id, field, value, decided_by, reason, source_url) on the final ids.
        A field that a user decision set keeps the user's value (conflict TAG-user-decision-wins)."""
        p = self.inp.manual_dir / fname
        if p.exists():
            self.register(sid, p)
            for r in read_csv(p):
                f, v = r["field"].strip(), r["value"].strip()
                src = f"manual/{fname}#{r['company_id'].strip()}.{f}"
                cid = self.v42_id(r["company_id"], src)
                if cid not in self.comp:
                    continue
                if f not in allowed:
                    self.conflict("unknown-field", cid, "", f, src, "")
                    continue
                if f == "kind":
                    v = bc.clean_kind(v)
                    if v not in KINDS:
                        self.conflict("unknown-kind", cid, "", v, src, "")
                        continue
                if f == "sna_sector" and v != BLANK and not SECTOR_RX.match(v):
                    self.conflict(f"{tag}-unknown-sector", cid, "", v, src, "")
                    continue
                if self.field_rank.get((cid, f), -1) >= RANK_CHAT:
                    self.conflict(f"{tag}-user-decision-wins", cid, self.comp[cid][f] or "", v, src,
                                  f"a user decision set this field; the {tag} value is not applied")
                    continue
                if v == BLANK:
                    v = ""
                elif f in ("parent_company_id", "university_id"):
                    v = self.v42_id(v, src)
                    if not v:
                        continue
                    if v == cid:
                        self.conflict(f"{tag}-self-reference", cid, "", v, src, "")
                        continue
                elif f == "wikidata_qid":
                    other = [c for c, x in self.comp.items() if x["wikidata_qid"] == v and c != cid]
                    if other:
                        self.conflict(f"{tag}-qid-in-use", cid, other[0], v, src, "another row holds this QID")
                        continue
                old = self.comp[cid][f]
                if old == v:
                    self.stats[f"{tag}_fields_unchanged"] += 1
                    continue
                if f == "name":
                    if old:
                        self.alias.append({"alias": old, "company_id": cid, "source": "v3-name"})
                    self.alias.append({"alias": v, "company_id": cid, "source": "v4-review"})
                    self.index_add(v, cid)
                if f == "kind":
                    self.comp[cid]["is_company"] = v in COMPANY_KINDS
                    self.comp[cid]["sna_sector"] = SECTOR.get(v, "")
                self.comp[cid][f] = v
                self.field_rank[(cid, f)] = RANK_MANUAL
                self.stats[f"{tag}_field_changed:{f}"] += 1
                self.v42_mark(cid, r.get("decided_by", "").strip(), date)

    def v43_fixes(self) -> None:
        """The namespace rule of 2026-10-19 (DEFINITIONS.md section 4): firm_based_on_namespace names
        the organisation that controls the account; a foundation that only hosts a project of the
        namespace has the relation hosted_by. Steps, on the final ids after the v4.2 step:
          1. manual/v43_new_orgs.csv: the project rows and foundations that control an account (same
             columns as v42_new_orgs.csv; parents after all rows exist);
          2. manual/v43_fields.csv: field patches (the parents of existing project rows);
          3. manual/v43_namespaces.csv and REVIEW/v43_namespaces.private.csv (host, namespace,
             company_id, relation, class, verified, decided_by, evidence, source_url): set the relation
             of the (namespace, organisation) pair, or add the row (an added owns row has the evidence
             account-profile). Class unclear changes nothing and writes a v43-namespace-review conflict.
             The private file holds the accounts of persons (no person account is named in git)."""
        p = self.inp.manual_dir / "v43_new_orgs.csv"
        if p.exists():
            self.register("manual-v43-new-orgs", p)
            rows, added = read_csv(p), set()
            for r in rows:
                cid, kind = r["company_id"].strip(), bc.clean_kind(r["kind"])
                if cid in self.comp or cid in self.merge_to:
                    self.conflict("new-organisation-exists", cid, cid, "", "manual/v43_new_orgs.csv", "the id is in v4.2")
                    continue
                if kind not in KINDS:
                    self.conflict("unknown-kind", cid, "", kind, "manual/v43_new_orgs.csv", "")
                    continue
                self.new_org(cid, r["name"].strip(), kind, r["sna_sector"].strip(), r["decided_by"].strip(),
                             f"manual/v43_new_orgs.csv#company_id={cid}", country=r["country"].strip(), date=V43_DATE)
                self.stats["v43_new_organisations"] += 1
                added.add(cid)
            for r in rows:     # parents after all rows exist
                cid, par = r["company_id"].strip(), r["parent_company_id"].strip()
                if par and cid in added:
                    pid = self.v42_id(par, f"manual/v43_new_orgs.csv:{cid}")
                    if pid and pid != cid:
                        self.comp[cid]["parent_company_id"] = pid
        self.field_file("v43_fields.csv", "manual-v43-fields", "v43", V43_DATE)
        for p, sid, name in ((self.inp.manual_dir / "v43_namespaces.csv", "manual-v43-namespaces", "manual/v43_namespaces.csv"),
                             (self.inp.review_dir / "v43_namespaces.private.csv", "review-v43-namespaces-private",
                              "review/v43_namespaces.private.csv")):
            if p.exists():
                self.register(sid, p)
                for r in read_csv(p):
                    self.v43_namespace_row(r, name)

    def v43_namespace_row(self, r: dict, fname: str, tag: str = "v43", date: str = V43_DATE) -> None:
        host, nspace = r["host"].strip().lower(), r["namespace"].strip()
        rel, cls = r["relation"].strip(), r["class"].strip()
        key = f"{host}/{nspace}"
        src = f"{fname}#{key}"
        cid = self.v42_id(r["company_id"], src)
        if cid not in self.comp:
            return
        rows = [n for n in self.ns if n["host"] == host and n["namespace"].lower() == nspace.lower() and n["company_id"] == cid]
        if tag != "v43" and rel == NS_REMOVE:
            if not rows:
                self.conflict(f"{tag}-namespace-row-missing", key, cid, "", src, "nothing to remove")
                return
            for n in rows:
                self.ns.remove(n)
                self.stats[f"{tag}_removed:{n['relation']}"] += 1
            return
        if rel not in NS_RELATIONS or cls not in V43_CLASSES:
            self.conflict(f"{tag}-unknown-value", key, cid, f"{rel}/{cls}", src, "")
            return
        if cls == "unclear":
            self.conflict(f"{tag}-namespace-review", key, cid, "", src, (r.get("evidence") or "")[:300])
            self.stats[f"{tag}_namespaces_review"] += 1
            return
        if rows:
            changed = 0
            for n in rows:
                if n["relation"] != rel:
                    self.stats[f"{tag}_relation:{n['relation']}->{rel}"] += 1
                    n["relation"] = rel
                    changed += 1
            if not changed:
                self.stats[f"{tag}_namespaces_unchanged"] += 1
            return
        same = [n for n in self.ns if n["host"] == host and n["namespace"].lower() == nspace.lower()]
        ver = {"True": True, "False": False}.get((r.get("verified") or "").strip())
        # Optional columns (v4.6, a row that comes back as it was): the fields of the new row.
        ntype = same[0]["namespace_type"] if same else ""
        if "namespace_type" in r:
            ntype = (r["namespace_type"] or "").strip() or None
        self.ns.append({"host": host, "namespace": same[0]["namespace"] if same else nspace,
                        "namespace_type": ntype, "company_id": cid, "relation": rel,
                        "evidence": (r.get("row_evidence") or "").strip() or V43_EVIDENCE, "verified": ver,
                        "source_pointer": (r.get("source_pointer") or "").strip() or src,
                        "fetched_at": (r.get("fetched_at") or "").strip() or date})
        self.stats[f"{tag}_added:{rel}"] += 1

    def v44_fixes(self) -> None:
        """The web checks of round 9 (2026-10-20): the v4.3 audit items and the DNS review lists. Steps,
        on the final ids after the v4.3 step:
          1. manual/v44_new_orgs.csv: new rows (the columns of v42_new_orgs.csv; domains move to the row);
          2. manual/v44_merges.csv (merge_id, into_id, kept_name, ...): a bought firm whose brand is gone;
          3. manual/v44_fields.csv: field patches, also kind and sna_sector (V44_FIELDS);
          4. manual/v44_domains.csv: domain moves, adds and drops;
          5. manual/v44_namespaces.csv and REVIEW/v44_namespaces.private.csv (the accounts of persons;
             the columns of v43_namespaces.csv): set, add or (remove) the relation of a (namespace,
             organisation) pair. A row closes the v43-namespace-review conflict of its namespace."""
        self.add_new_orgs_file("v44_new_orgs.csv", "manual-v44-new-orgs", V44_DATE)
        p = self.inp.manual_dir / "v44_merges.csv"
        if p.exists():
            self.register("manual-v44-merges", p)
            for r in read_csv(p):
                src = f"manual/v44_merges.csv#{r['merge_id'].strip()}"
                x, k = self.v42_id(r["merge_id"], src), self.v42_id(r["into_id"], src)
                if not x or not k or x == k or x not in self.comp or k not in self.comp:
                    self.conflict("v44-merge-unknown-id", r["merge_id"].strip(), r["into_id"].strip(), "", src, "")
                    continue
                self.merge_one(x, k)
                self.merge_to[x] = k
                name = (r.get("kept_name") or "").strip()
                if name and self.comp[k]["name"] != name:
                    self.alias.append({"alias": self.comp[k]["name"], "company_id": k, "source": "v3-name"})
                    self.comp[k]["name"] = name
                self.stats["v44_merges"] += 1
                self.v42_mark(k, r.get("decided_by", "").strip(), V44_DATE)
        self.field_file("v44_fields.csv", "manual-v44-fields", "v44", V44_DATE, allowed=V44_FIELDS)
        self.domain_file("v44_domains.csv", "manual-v44-domains", "v44", V44_DATE, actions=("move", "add", "drop"))
        done = set()
        for p, sid, name in ((self.inp.manual_dir / "v44_namespaces.csv", "manual-v44-namespaces", "manual/v44_namespaces.csv"),
                             (self.inp.review_dir / "v44_namespaces.private.csv", "review-v44-namespaces-private",
                              "review/v44_namespaces.private.csv")):
            if p.exists():
                self.register(sid, p)
                for r in read_csv(p):
                    self.v43_namespace_row(r, name, tag="v44", date=V44_DATE)
                    done.add(f"{r['host'].strip().lower()}/{r['namespace'].strip()}".lower())
        if done:
            before = len(self.conf)
            self.conf = [c for c in self.conf if not (c["type"] == "v43-namespace-review" and c["key"].lower() in done)]
            self.stats["v44_closed_v43_reviews"] += before - len(self.conf)

    def v45_fixes(self) -> None:
        """The user's answers to the v4.4 audit (2026-10-20). Steps, on the final ids after the v4.4 step:
          1. manual/v45_fields.csv: field patches (V44_FIELDS; the parents of the project rows that lose
             the OSGeo relation);
          2. manual/v45_namespaces.csv and REVIEW/v45_namespaces.private.csv (the columns of
             v43_namespaces.csv): set, add or (remove) the relation of a (namespace, organisation) pair;
             here the hosted_by rows of OSGeo community projects and of projects that the OSGeo
             directory only lists (the old rule N2 of 2026-10-20; the v4.6 step adds them back);
          3. the relation sponsored_by: each hosted_by or owns row of an organisation of kind
             fiscal-sponsor becomes sponsored_by (rule N1; a fiscal sponsor never owns an account). The
             step runs last, so a namespace row of step 2 that names a fiscal sponsor is renamed too."""
        self.field_file("v45_fields.csv", "manual-v45-fields", "v45", V45_DATE, allowed=V44_FIELDS)
        for p, sid, name in ((self.inp.manual_dir / "v45_namespaces.csv", "manual-v45-namespaces", "manual/v45_namespaces.csv"),
                             (self.inp.review_dir / "v45_namespaces.private.csv", "review-v45-namespaces-private",
                              "review/v45_namespaces.private.csv")):
            if p.exists():
                self.register(sid, p)
                for r in read_csv(p):
                    self.v43_namespace_row(r, name, tag="v45", date=V45_DATE)
        self.fiscal_sponsor_relations("v45")

    def fiscal_sponsor_relations(self, tag: str) -> None:
        """Each hosted_by or owns row of an organisation of kind fiscal-sponsor becomes sponsored_by."""
        for n in self.ns:
            c = self.comp.get(n["company_id"])
            if c and c["kind"] == FISCAL_SPONSOR and n["relation"] in ("hosted_by", "owns"):
                self.stats[f"{tag}_relation:{n['relation']}->sponsored_by"] += 1
                n["relation"] = "sponsored_by"

    def v46_fixes(self) -> None:
        """The new rule N2 of the user (2026-10-21): OSGeo hosts every project of its directory
        (https://www.osgeo.org/projects/): official, incubating, community and listed projects.
        manual/v46_namespaces.csv and REVIEW/v46_namespaces.private.csv (the columns of
        v43_namespaces.csv, and the optional row_evidence, namespace_type, source_pointer and
        fetched_at) add back the hosted_by rows that the v4.5 step removed, with the fields of v4.4.
        hosted_by gives no firm_based_on_namespace (rule N1). The parents of v45_fields.csv stay. The
        fiscal-sponsor rule of v4.5 runs again at the end, so a row of a fiscal sponsor is sponsored_by."""
        for p, sid, name in ((self.inp.manual_dir / "v46_namespaces.csv", "manual-v46-namespaces", "manual/v46_namespaces.csv"),
                             (self.inp.review_dir / "v46_namespaces.private.csv", "review-v46-namespaces-private",
                              "review/v46_namespaces.private.csv")):
            if p.exists():
                self.register(sid, p)
                for r in read_csv(p):
                    self.v43_namespace_row(r, name, tag="v46", date=V46_DATE)
        self.fiscal_sponsor_relations("v46")

    def v47_fixes(self) -> None:
        self.review_layer("v47", V47_DATE)

    def v48_fixes(self) -> None:
        """AI round 11 (2026-10-25): the organisation accounts of the 5,000+ commit layer with no owns row in
        v4.7, judged with the class rule of DEFINITIONS.md section 4 (the user: both layers use one rule).
        The same steps and columns as v4.7, with the files v48_*."""
        self.review_layer("v48", V48_DATE)

    def v49_fixes(self) -> None:
        """The user's answers of the audit pages v47 and v48 (2026-10-25) and the second check of the
        unsure items of v47. The same steps and columns as v4.7, with the files v49_*."""
        self.review_layer("v49", V49_DATE)

    def review_layer(self, tag: str, date: str) -> None:
        """AI round 10 (2026-10-25): the new domains and namespaces of the 1,000-4,999 commit layer of
        the dataset, checked with one fetched URL for each fact. Steps, on the final ids after the v4.6
        step:
          1. manual/v47_new_orgs.csv: new rows (the columns of v42_new_orgs.csv);
          2. manual/v47_merges.csv (merge_id, into_id, kept_name, ...);
          3. manual/v47_fields.csv: field patches (V44_FIELDS);
          4. manual/v47_domains.csv and REVIEW/v47_domains.private.csv (the personal domains, to the
             row independent; never in git): domain adds, moves and drops;
          5. manual/v47_namespaces.csv and REVIEW/v47_namespaces.private.csv (the accounts of persons;
             the columns of v43_namespaces.csv, and the optional row_evidence, namespace_type,
             source_pointer and fetched_at): set, add or (remove) the relation of a (namespace,
             organisation) pair;
          6. the fiscal-sponsor rule of v4.5 runs again, so a row of a fiscal sponsor is sponsored_by."""
        self.add_new_orgs_file(f"{tag}_new_orgs.csv", f"manual-{tag}-new-orgs", date)
        p = self.inp.manual_dir / f"{tag}_merges.csv"
        if p.exists():
            self.register(f"manual-{tag}-merges", p)
            for r in read_csv(p):
                src = f"manual/{tag}_merges.csv#{r['merge_id'].strip()}"
                x, k = self.v42_id(r["merge_id"], src), self.v42_id(r["into_id"], src)
                if not x or not k or x == k or x not in self.comp or k not in self.comp:
                    self.conflict(f"{tag}-merge-unknown-id", r["merge_id"].strip(), r["into_id"].strip(), "", src, "")
                    continue
                self.merge_one(x, k)
                self.merge_to[x] = k
                name = (r.get("kept_name") or "").strip()
                if name and self.comp[k]["name"] != name:
                    self.alias.append({"alias": self.comp[k]["name"], "company_id": k, "source": "v3-name"})
                    self.comp[k]["name"] = name
                self.stats[f"{tag}_merges"] += 1
                self.v42_mark(k, r.get("decided_by", "").strip(), date)
        self.field_file(f"{tag}_fields.csv", f"manual-{tag}-fields", tag, date, allowed=V44_FIELDS)
        self.domain_file(f"{tag}_domains.csv", f"manual-{tag}-domains", tag, date, actions=("move", "add", "drop"))
        self.domain_file(f"{tag}_domains.private.csv", f"review-{tag}-domains-private", tag, date,
                         actions=("move", "add", "drop"), path=self.inp.review_dir / f"{tag}_domains.private.csv")
        for p, sid, name in ((self.inp.manual_dir / f"{tag}_namespaces.csv", f"manual-{tag}-namespaces", f"manual/{tag}_namespaces.csv"),
                             (self.inp.review_dir / f"{tag}_namespaces.private.csv", f"review-{tag}-namespaces-private",
                              f"review/{tag}_namespaces.private.csv")):
            if p.exists():
                self.register(sid, p)
                for r in read_csv(p):
                    self.v43_namespace_row(r, name, tag=tag, date=date)
        self.fiscal_sponsor_relations(tag)

    def validate(self) -> None:
        for cid in sorted(self.comp):
            r = self.comp[cid]
            if r["kind"] not in KINDS:
                self.conflict("unknown-kind", cid, "", r["kind"], "", "")
            r["is_company"] = r["kind"] in COMPANY_KINDS
            for f in ("parent_company_id", "university_id"):
                v = self.final_id(r[f]) if r[f] else ""
                if v and v not in self.comp:
                    self.conflict("reference-to-unknown-id", cid, "", v, "", f"{f} cleared")
                    v = ""
                if v == cid:
                    self.conflict("reference-to-self", cid, "", v, "", f"{f} cleared")
                    v = ""
                if f == "university_id" and v and self.comp[v]["kind"] != "academic":
                    self.conflict("university-not-academic", cid, "", v, "", f"university_id cleared (kind {self.comp[v]['kind']})")
                    v = ""
                r[f] = v
            if r["kind"] == "public-research":
                if not r["parent_company_id"]:
                    self.conflict("public-research-without-parent", cid, "", "", "", "no government body")
                if not r["university_id"]:
                    self.conflict("public-research-without-university", cid, "", "", "", "no single main university")
            elif r["university_id"]:
                self.conflict("university-id-on-other-kind", cid, r["kind"], r["university_id"], "", "kept")
        # UK universities -> S.15
        uk = defaultdict(bool)
        for d, x in self.dom.items():
            if d.endswith(".ac.uk") or d == "ac.uk":
                uk[x["company_id"]] = True
        for cid, r in self.comp.items():
            if r["kind"] == "academic" and (r["country"] == "GB" or uk[cid]) and r["sna_sector"] != "S.15":
                r["sna_sector"] = "S.15"
                self.stats["uk_universities_set_to_S15"] += 1

    def roles(self) -> None:
        by = defaultdict(list)
        for d, r in self.dom.items():
            by[r["company_id"]].append(r)
        for cid, rows in by.items():
            mains = [r for r in rows if r["role"] == "main"]
            if len(mains) == 1:
                continue

            def rank(r):
                reg = r["registrable_domain"] or r["domain"]
                return (r["domain"] not in self.v3_main or self.v3_owner.get(r["domain"]) != cid,
                        reg.split(".")[0] != cid, bc.CONF_CLASS.get(r["confidence"], 3),
                        r["domain"] != reg, len(r["domain"]), r["domain"])
            best = min(mains or rows, key=rank)
            for r in rows:
                r["role"] = "main" if r is best else "alternative"
            self.stats["roles_fixed"] += 1

    def cross_check(self) -> None:
        """Rule 8: every organisation that loses all its domains (the rejected ones are listed by domain)."""
        now = Counter(r["company_id"] for r in self.dom.values())
        for cid in sorted(self.v3_ndom):
            k = self.final_id(cid)
            if k in self.comp and k == cid and not now[cid]:
                self.conflict("organisation-lost-all-domains", cid, "", "", "", f"v3 had {self.v3_ndom[cid]} domain rows")

    def v3_open_conflicts(self, final: dict) -> list[dict]:
        decided = {}
        for iid, ans in final.items():
            if iid.startswith("conflict:") and ans["action"] != "defer":
                decided[int(iid.split(":")[1])] = True
        out = []
        for i, c in enumerate(self.v3_conflicts):
            it = self.items.get(f"conflict:{i}")
            if i in decided and it and (it.get("conflict_type"), it.get("key")) != (c["type"], c["key"]):
                self.stats["v3_conflict_index_mismatch"] += 1
                out.append(c)
                continue
            if i in decided:
                self.stats["v3_conflicts_decided"] += 1
                continue
            out.append(c)
        return out

    def run(self) -> tuple[dict, list]:
        self.load()
        self.load_typed_names()
        self.add_new_orgs()
        final = self.load_answers()
        self.domain_decisions()
        self.decisions(final)
        self.manual_merges()
        self.merges()
        self.rejects()
        self.public_research()
        self.domain_decisions(SWEEP_SOURCES)
        self.v42_fixes()
        if self.inp.layer not in LAYERS:
            raise SystemExit(f"usage: --layer must be one of {', '.join(LAYERS)}")
        last = LAYERS.index(self.inp.layer)        # each layer runs the layers before it
        if last >= LAYERS.index("v4.3"):
            self.v43_fixes()
        if last >= LAYERS.index("v4.4"):
            self.v44_fixes()
        if last >= LAYERS.index("v4.5"):
            self.v45_fixes()
        if last >= LAYERS.index("v4.6"):
            self.v46_fixes()
        if last >= LAYERS.index("v4.7"):
            self.v47_fixes()
        if last >= LAYERS.index("v4.8"):
            self.v48_fixes()
        if last >= LAYERS.index("v4.9"):
            self.v49_fixes()
        self.validate()
        self.roles()
        self.cross_check()
        for d in list(self.dropped):
            if d in self.dom:
                del self.dropped[d]
        if self.inp.script:
            self.register("build-script-v4", self.inp.script)
            self.register("build-script", Path(self.inp.script).parent / "build_companies.py")
        reg = {}
        for r in self.registry:
            reg[r["source_id"]] = r
        seen, alias = set(), []
        for a in self.alias:
            k = (a["alias"], a["company_id"], a["source"])
            if a["alias"] and a["company_id"] in self.comp and k not in seen:
                seen.add(k)
                alias.append(a)
        tables = {
            "company": [self.comp[c] for c in sorted(self.comp)],
            "company_alias": sorted(alias, key=lambda a: (a["alias"], a["company_id"], a["source"])),
            "company_domain": [self.dom[d] for d in sorted(self.dom)],
            "company_namespace": self.dedupe_ns(),
            "source_registry": [reg[k] for k in sorted(reg)],
            "company_domain_dropped": [self.dropped[d] for d in sorted(self.dropped)],
        }
        bad = [r["company_id"] for r in tables["company_domain"] if r["company_id"] not in self.comp]
        if bad:
            raise SystemExit(f"refused: {len(bad)} domain rows name an unknown id, for example {bad[0]}")
        conflicts = self.v3_open_conflicts(final) + self.conf
        conflicts = sorted({tuple(c[k] for k in CONFLICT_COLS): c for c in conflicts}.values(),
                           key=lambda c: tuple(c[k] for k in CONFLICT_COLS))
        self.final = final
        self.annotate_conflicts(conflicts, tables)
        bc.check_no_at(tables)
        bc.check_no_at({"conflicts": conflicts, "deferred": self.deferred,
                        "qids_unverified": list(self.unverified.values())})
        return tables, conflicts

    def annotate_conflicts(self, conflicts: list, tables: dict) -> None:
        """state: where the key ended in this build; resolution and resolved_by: the round 8 answer
        (ai/r*/conflicts-out-*.csv), or the end state for the types in STATE_RESOLVES. A conflict
        with an empty resolved_by is open."""
        ans = {}
        for f in sorted(self.inp.review_dir.glob("ai/r*/conflicts-out-*.csv")):
            for r in read_csv(f):
                ans[(r["type"], r["key"])] = r
        owner = {r["domain"]: r["company_id"] for r in tables["company_domain"]}
        for c in conflicts:
            k = c["key"]
            if k in self.comp:
                st = f"organisation kept ({self.comp[k]['kind']})"
            elif k in self.merge_to:
                st = f"organisation merged into {self.final_id(k)}"
            elif k in self.rejected:
                st = "organisation rejected"
            elif k in owner:
                st = f"domain -> {owner[k]}"
            elif k in self.dropped:
                st = "domain unmatched (dropped)"
            elif "." in k and " " not in k:
                st = "domain unmatched"
            else:
                st = ""
            a = ans.get((c["type"], k))
            c["state"] = st
            if a:
                c["resolution"] = " ".join(x for x in (a.get("action", ""), a.get("target", "")) if x)
                c["resolved_by"] = a.get("decided_by", "")
            elif c["type"] in STATE_RESOLVES and st:
                c["resolution"], c["resolved_by"] = st, "build state"
            else:
                c["resolution"], c["resolved_by"] = "", ""
            self.stats["conflicts_open" if not c["resolved_by"] else "conflicts_resolved"] += 1

    def dedupe_ns(self) -> list[dict]:
        best = {}
        for n in self.ns:
            if n["company_id"] not in self.comp:
                continue
            k = (n["host"], n["namespace"].lower(), n["company_id"])
            if k not in best or REL_RANK[n["relation"]] < REL_RANK[best[k]["relation"]]:
                best[k] = n
        return [best[k] for k in sorted(best)]


def write_outputs(tables: dict, conflicts: list, v: V4, out: Path, memory_limit: str = "3GB", threads: int = 2,
                  db_name: str = "companies.v4.duckdb", export_name: str = "export-v4") -> None:
    import duckdb
    out.mkdir(parents=True, exist_ok=True)
    export = out / export_name
    export.mkdir(exist_ok=True)
    dst = out / db_name
    tmp = out / f"{db_name}.tmp"
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
        part = export / f"{t}.parquet.tmp"
        con.execute(f"COPY (SELECT * FROM {t} ORDER BY {ORDER[t]}) TO '{part}' (FORMAT parquet)")
        os.replace(part, export / f"{t}.parquet")
    con.close()
    os.replace(tmp, dst)

    def write_csv(name: str, cols: list, rows: list) -> None:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
        part = export / f"{name}.tmp"
        part.write_text(buf.getvalue(), encoding="utf-8")
        os.replace(part, export / name)
    write_csv("conflicts.csv", CONFLICT_OUT_COLS, conflicts)
    write_csv("deferred.csv", ["item_id", "type", "key", "source"], v.deferred)
    write_csv("qids_unverified.csv", ["qid", "company_id", "current_qid", "source"],
              [v.unverified[q] for q in sorted(v.unverified, key=bc.qkey)])
    part = export / "v4_stats.json.tmp"
    part.write_text(json.dumps(summary(tables, conflicts, v), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(part, export / "v4_stats.json")


def summary(tables: dict, conflicts: list, v: V4) -> dict:
    comp = tables["company"]
    s = {t: len(rows) for t, rows in tables.items()}
    s["kind"] = dict(sorted(Counter(c["kind"] for c in comp).items()))
    s["kind_v3"] = dict(sorted(Counter(v.v3_kind.values()).items()))
    s["review_status"] = dict(sorted(Counter(c["review_status"] for c in comp).items()))
    s["review_status_v3"] = dict(sorted(Counter(v.v3_status.values()).items()))
    s["reviewer"] = dict(sorted(Counter(c["reviewer"] or "" for c in comp).items()))
    s["is_company"] = sum(1 for c in comp if c["is_company"])
    s["sna_sector"] = dict(sorted(Counter(c["sna_sector"] or "" for c in comp).items()))
    s["confidence"] = dict(sorted(Counter(d["confidence"] for d in tables["company_domain"]).items()))
    s["role"] = dict(sorted(Counter(d["role"] for d in tables["company_domain"]).items()))
    s["relation"] = dict(sorted(Counter(n["relation"] for n in tables["company_namespace"]).items()))
    s["domains_v3"] = len(v.v3_owner)
    s["domains_dropped_by_reason"] = dict(sorted(Counter(d["reason"] for d in tables["company_domain_dropped"]).items()))
    s["conflicts"] = dict(sorted(Counter(c["type"] for c in conflicts).items()))
    s["conflicts_total"] = len(conflicts)
    s["deferred"] = dict(sorted(Counter(d["type"] for d in v.deferred).items()))
    s["deferred_total"] = len(v.deferred)
    s["qids_unverified"] = len(v.unverified)
    s["public_research"] = {"rows": sum(1 for c in comp if c["kind"] == "public-research"),
                            "with_parent": sum(1 for c in comp if c["kind"] == "public-research" and c["parent_company_id"]),
                            "with_university": sum(1 for c in comp if c["kind"] == "public-research" and c["university_id"])}
    s["university_id_filled"] = sum(1 for c in comp if c["university_id"])
    s["filled"] = {col: sum(1 for c in comp if c[col] not in ("", None))
                   for col in ("wikidata_qid", "country", "parent_company_id", "university_id", "sna_sector")}
    s["build"] = dict(sorted(v.stats.items()))
    return s


def build(inp: Inputs) -> tuple[dict, list, V4]:
    v = V4(inp)
    tables, conflicts = v.run()
    return tables, conflicts, v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=bc.OUT_DEFAULT)
    ap.add_argument("--v3-db", type=Path, default=None, help="default OUT/companies.duckdb")
    ap.add_argument("--review", type=Path, default=None, help="default OUT/review")
    ap.add_argument("--manual", type=Path, default=None, help="default DS/s8-companies/manual")
    ap.add_argument("--ctp", type=Path, default=bc.CTP_DEFAULT)
    ap.add_argument("--ds", type=Path, default=bc.DS_DEFAULT)
    ap.add_argument("--psl", type=Path, default=None)
    ap.add_argument("--web", type=Path, default=bc.WEB_DEFAULT)
    ap.add_argument("--memory-limit", default="3GB")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--db-name", default="companies.v4.duckdb", help="file name of the database in OUT")
    ap.add_argument("--export-name", default="export-v4", help="folder name of the export in OUT")
    ap.add_argument("--layer", default="v4.9", choices=LAYERS,
                    help="the last layer of manual files (v4.2 leaves v4.3 to v4.9 out)")
    a = ap.parse_args(argv)
    inp = Inputs.real(a.out, a.ds, a.ctp, a.web, a.psl, a.v3_db, a.review, a.manual)
    inp.layer = a.layer
    tables, conflicts, v = build(inp)
    write_outputs(tables, conflicts, v, a.out, a.memory_limit, a.threads, a.db_name, a.export_name)
    s = summary(tables, conflicts, v)
    print(json.dumps({k: s[k] for k in ("company", "company_domain", "company_domain_dropped", "kind", "review_status",
                                         "conflicts", "deferred_total", "qids_unverified")}, indent=1))
    print(f"wrote {bc.tilde(a.out / a.db_name)} and {bc.tilde(a.out / a.export_name)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
