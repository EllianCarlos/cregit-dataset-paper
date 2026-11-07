"""Tests of build_companies_v4.py (v4 = v3 plus the review) on a small v3 database and review set."""
import csv
import json
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import build_companies as bc  # noqa: E402
import build_companies_v4 as v4  # noqa: E402

AT = chr(64)   # this file holds no literal address character
ITEM_COLS = "item_id,type,key,action,kind,name,parent_company_id,merge_into,sna_sector,qid,note,confidence,decided_by"
DEC_COLS = "item_id,type,key,action,kind,name,parent_company_id,merge_into,sna_sector,qid,note,decided_by,decided_utc"
LINK_COLS = "link_id,company_id,domain,action,move_to,confidence,note,decided_by"


def comp(cid, name, kind="company", status="proposed", **kw):
    r = {c: "" for c, _ in bc.SCHEMA["company"]}
    r.update(company_id=cid, name=name, kind=kind, is_company=kind in bc.COMPANY_KINDS,
             sna_sector=bc.SECTOR.get(kind, ""), review_status=status, fortune_global_500=None)
    r.update(kw)
    return r


def dom(d, cid, role="main", confidence="curated", source="gitdm"):
    return {"domain": d, "registrable_domain": d, "company_id": cid, "role": role, "confidence": confidence,
            "source": source, "source_pointer": ""}


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text.strip() + "\n", encoding="utf-8")
    return p


def rows_csv(header: str, rows: list[list[str]]) -> str:
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header.split(","))
    w.writerows(rows)
    return buf.getvalue()


def item(iid, act, kind="", name="", parent="", merge="", sector="", qid="", by="claude-review-v3", **kw):
    t = "company" if iid.startswith("company:") else "conflict"
    return [iid, t, iid.split(":", 1)[1], act, kind, name, parent, merge, sector, qid, "", "high", by]


def dec(iid, act, kind="", name="", parent="", merge="", sector="", qid="", by="user"):
    t = "company" if iid.startswith("company:") else "conflict"
    return [iid, t, iid.split(":", 1)[1], act, kind, name, parent, merge, sector, qid, "", by, "2026-10-17T10:00:00Z"]


V3_COMPANIES = [
    comp("free-provider", "(Free e-mail provider)", "free-provider", "accepted"),
    comp("independent", "(Independent)", "independent", "accepted"),
    comp("acme", "Acme", status="accepted"),
    comp("acme-dup", "Acme Duplicate"),
    comp("beta", "Beta"), comp("gamma", "Gamma"), comp("delta", "Delta"), comp("eps", "Eps"),
    comp("lab", "Big Lab", "government"), comp("lab2", "Other Lab", "government"),
    comp("uni-a", "Uni A", "academic", sna_sector="S.13"),
    comp("child", "Child"), comp("child2", "Child Two"), comp("child3", "Child Three"),
    comp("twin1", "Twin"), comp("twin2", "Twin"),
    comp("rej", "Rejected Co"), comp("lonely", "Lonely Co"), comp("mover", "Mover"), comp("qco", "Q Co"),
]
V3_DOMAINS = [
    dom("acme.com", "acme"), dom("acme-old.com", "acme-dup"), dom("wrongco.com", "acme-dup", "alternative"),
    dom("beta.io", "beta"), dom("gamma.io", "gamma"), dom("delta.io", "delta"), dom("eps.io", "eps"),
    dom("biglab.gov", "lab"), dom("otherlab.gov", "lab2"), dom("uni-a.ac.uk", "uni-a"),
    dom("rej.com", "rej"), dom("lonely.com", "lonely"), dom("mover.com", "mover"),
    dom("other-brand.com", "mover", "alternative"), dom("newbrand.com", "mover", "alternative"),
    dom("qco.com", "qco"), dom("gmail.com", "free-provider"),
]
V3_CONFLICTS = [
    {"type": "proposal-low-certainty", "key": "newdom.com", "kept": "", "other": "Newco",
     "source": "proposals-top-unmatched-v2", "detail": "certainty low"},
    {"type": "kind-differs", "key": "eps", "kept": "company", "other": "project", "source": "x", "detail": ""},
    {"type": "possible-duplicate", "key": "twin1", "kept": "twin1", "other": "twin2", "source": "", "detail": ""},
]


@pytest.fixture
def inputs(tmp_path):
    v3 = tmp_path / "v3"
    tables = {"company": V3_COMPANIES, "company_alias": [{"alias": "Acme", "company_id": "acme", "source": "x"}],
              "company_domain": V3_DOMAINS, "company_namespace": [], "source_registry": []}
    bc.write_outputs(tables, V3_CONFLICTS, v3, "1GB", 1)
    rd = tmp_path / "review"
    items = [{"id": f"conflict:{i}", "type": "conflict", "conflict_type": c["type"], "key": c["key"],
              "kept": c["kept"], "other": c["other"], "source": c["source"]} for i, c in enumerate(V3_CONFLICTS)]
    items += [{"id": f"company:{c['company_id']}", "type": "company", "key": c["company_id"]} for c in V3_COMPANIES]
    write(rd / "review_items.json", json.dumps({"items": items}))
    write(rd / "ai/part-1.csv", rows_csv(ITEM_COLS, [item("company:beta", "edit", name="Beta One", by="claude-review-v1")]))
    write(rd / "ai/part-2.csv", rows_csv(ITEM_COLS, [item("company:eps", "accept", by="claude-review-v1")]))
    write(rd / "ai/part-8.csv", rows_csv(ITEM_COLS, [
        item("company:child", "edit", parent="ACME"), item("company:child2", "edit", parent="Twin"),
        item("company:child3", "edit", parent="Nobody Inc"), item("company:rej", "reject"),
        item("conflict:0", "accept"), item("conflict:2", "edit", merge="twin1"),
        item("company:acme-dup", "reject", merge="acme-typo-unknown")]))
    write(rd / "ai/part-9.csv", rows_csv(ITEM_COLS, [
        item("company:beta", "edit", kind="consultancy", by="claude-review-v5"),
        item("company:gamma", "edit", kind="consultancy", by="claude-review-v5"),
        item("company:acme", "accept", qid="Q1", by="claude-review-v5"),
        item("company:qco", "edit", qid="Q999", by="claude-review-v5")]))
    write(rd / "ai/part-10.csv", rows_csv(ITEM_COLS + ",university_id", [
        item("company:lab", "edit", kind="public-research", sector="S.13", by="claude-review-v6") + ["uni-a"],
        item("company:lab2", "edit", kind="public-research", sector="S.13", by="claude-review-v6") + ["acme"]]))
    write(rd / "decisions.chat.csv", rows_csv(DEC_COLS, [dec("company:gamma", "edit", name="Gamma Chat"),
                                                         dec("company:delta", "edit", sector="S.12")]))
    write(rd / "decisions.csv", rows_csv(DEC_COLS, [dec("company:gamma", "accept"),
                                                    dec("company:eps", "reject", by="claude-review-v1")]))
    write(rd / "ai/domain_links_review.csv", rows_csv(LINK_COLS, [
        ["domain:acme-dup:wrongco.com", "acme-dup", "wrongco.com", "drop", "", "high", "", "claude-review-v4"],
        ["domain:lonely:lonely.com", "lonely", "lonely.com", "drop", "", "high", "", "claude-review-v4"],
        ["domain:mover:other-brand.com", "mover", "other-brand.com", "move", "acme", "high", "", "claude-review-v4"],
        ["domain:acme:sub.acme.com", "acme", "sub.acme.com", "move", "free-provider", "high", "", "claude-review-v4"]]))
    write(rd / "ai/lookalike_review.csv", rows_csv(LINK_COLS, [
        ["domain:beta:beta.io", "beta", "beta.io", "drop", "", "high", "", "claude-review-v4"]]))
    write(rd / "ai/rule_corrections.csv", rows_csv("file,link_or_item_id,field,from,to,reason,corrected_by,corrected_utc", [
        ["r4/lookalike-out-01.csv", "domain:beta:beta.io", "action", "drop", "keep", "test", "claude-main", ""]]))
    write(rd / "decisions.domains.chat.csv", rows_csv("link_id,company_id,domain,action,move_to,note,decided_by,decided_utc", [
        ["domain:mover:newbrand.com", "mover", "newbrand.com", "move", "New Org", "", "user", "2026-10-17T10:00:00Z"]]))
    md = tmp_path / "manual"
    write(md / "v4_new_orgs.csv", rows_csv(
        "company_id,name,kind,sna_sector,country,parent_company_id,domains,aliases,decided_by,reason", [
            ["new-org", "New Org", "company", "S.11", "", "acme", "neworg.com", "", "user", "test"],
            ["gov-x", "Gov X", "government", "S.13", "XX", "", "", "", "claude-main", "test"]]))
    write(md / "v4_merges.csv", rows_csv("merge_id,into_id,kept_name,decided_by,reason",
                                         [["acme-dup", "acme", "", "claude-main", "test"]]))
    write(md / "v4_edits.csv", rows_csv(ITEM_COLS.replace(",confidence", ""), []))
    write(md / "v4_public_research.csv", rows_csv("company_id,parent_company_id,university_id,basis",
                                                  [["lab", "gov-x", "", "test"]]))
    prop = write(tmp_path / "top_unmatched.v2.csv", "domain,name,kind,kind_basis,parent_name,certainty,reason\n"
                 "newdom.com,Newco,company,manual-review,,low,test")
    w3 = tmp_path / "w3_wikidata_items.parquet"
    c = duckdb.connect()
    c.execute("CREATE TABLE t (qid VARCHAR, label VARCHAR, instance_of_labels VARCHAR[])")
    c.execute("INSERT INTO t VALUES ('Q1', 'Acme Inc.', ['business'])")
    c.execute(f"COPY t TO '{w3}' (FORMAT parquet)")
    return v4.Inputs(v3_db=v3 / "companies.duckdb", review_dir=rd, manual_dir=md,
                     v3_conflicts=v3 / "export/conflicts.csv", w3_items=w3,
                     proposals=(("proposals-top-unmatched-v2", prop),), git=False)


@pytest.fixture
def built(inputs):
    return v4.build(inputs)


def by(rows, key):
    return {r[key]: r for r in rows}


def ctypes(conflicts):
    return {(c["type"], c["key"]) for c in conflicts}


def test_precedence(built):
    t, conf, v = built
    c = by(t["company"], "company_id")
    # A higher part wins as a whole: part-9 sets the kind; the name of part-1 is not used.
    assert c["beta"]["kind"] == "consultancy" and c["beta"]["name"] == "Beta"
    assert c["beta"]["review_status"] == "ai-reviewed" and c["beta"]["reviewer"] == "claude-review-v5"
    assert c["beta"]["is_company"] is True and c["beta"]["sna_sector"] == "S.11"
    # decisions.csv wins over the chat and the AI: accept, no change.
    assert c["gamma"]["kind"] == "company" and c["gamma"]["name"] == "Gamma"
    assert c["gamma"]["review_status"] == "accepted" and c["gamma"]["reviewer"] == "user"
    assert c["gamma"]["review_date"] == "2026-10-17"
    # A chat decision wins over v3.
    assert c["delta"]["sna_sector"] == "S.12" and c["delta"]["reviewer"] == "user"
    # An AI suggestion in decisions.csv is not a decision: the AI accept of part-2 applies.
    assert "eps" in c and c["eps"]["review_status"] == "accepted-ai"


def test_merge_without_wrong_domains(built):
    t, conf, v = built
    c = by(t["company"], "company_id")
    d = by(t["company_domain"], "domain")
    assert "acme-dup" not in c                      # merged (manual merge wins over the AI typo)
    assert d["acme-old.com"]["company_id"] == "acme" and d["acme-old.com"]["role"] == "alternative"
    assert d["acme.com"]["role"] == "main"
    assert "wrongco.com" not in d                   # dropped before the merge, not moved to acme
    assert by(t["company_domain_dropped"], "domain")["wrongco.com"]["company_id"] == "acme-dup"
    al = {(a["alias"], a["company_id"]) for a in t["company_alias"]}
    assert ("acme-dup", "acme") in al and ("Acme Duplicate", "acme") in al
    # A conflict decision merges the duplicate twin2 into twin1.
    assert "twin2" not in c and ("twin2", "twin1") in al


def test_domain_moves(built):
    t, conf, v = built
    d = by(t["company_domain"], "domain")
    assert d["other-brand.com"]["company_id"] == "acme"
    assert d["newbrand.com"]["company_id"] == "new-org"           # the user's move, to a typed name
    assert d["newbrand.com"]["source_pointer"].startswith("review-user")
    assert d["neworg.com"]["company_id"] == "new-org"
    assert d["sub.acme.com"]["company_id"] == "free-provider"     # a suffix match gets its own row
    assert d["beta.io"]["company_id"] == "beta"                   # the rule correction turned drop into keep
    assert v.stats["rule_corrections_applied"] == 1
    assert "lonely.com" not in d
    assert ("organisation-lost-all-domains", "lonely") in ctypes(conf)
    assert by(t["company"], "company_id")["new-org"]["parent_company_id"] == "acme"


def test_public_research_and_university(built):
    t, conf, v = built
    c = by(t["company"], "company_id")
    lab = c["lab"]
    assert lab["kind"] == "public-research" and lab["is_company"] is False and lab["sna_sector"] == "S.13"
    assert lab["university_id"] == "uni-a" and lab["parent_company_id"] == "gov-x"
    assert c["gov-x"]["kind"] == "government"
    assert c["lab2"]["university_id"] == ""                       # acme is not academic
    assert ("university-not-academic", "lab2") in ctypes(conf)
    assert ("public-research-without-parent", "lab2") in ctypes(conf)
    assert c["uni-a"]["sna_sector"] == "S.15"                     # a UK university
    assert [n for n, _ in v4.SCHEMA["company"]].index("university_id") == \
        [n for n, _ in v4.SCHEMA["company"]].index("parent_company_id") + 1


def test_typed_names(built):
    t, conf, v = built
    c = by(t["company"], "company_id")
    assert c["child"]["parent_company_id"] == "acme"             # exact name, without case
    assert c["child2"]["parent_company_id"] == "" and c["child3"]["parent_company_id"] == ""
    ct = ctypes(conf)
    assert ("unresolved-name", "Nobody Inc") in ct
    assert ("unresolved-name", "acme-typo-unknown") in ct


def test_rejects_qids_and_proposals(built):
    t, conf, v = built
    c = by(t["company"], "company_id")
    d = by(t["company_domain"], "domain")
    assert "rej" not in c and "rej.com" not in d
    assert ("domain-of-rejected-organisation", "rej.com") in ctypes(conf)
    assert c["acme"]["wikidata_qid"] == "Q1"                      # in W3, an organisation, the label agrees
    assert c["qco"]["wikidata_qid"] == ""                         # not in W3: not trusted
    assert ("qid-unverified", "qco") in ctypes(conf) and "Q999" in v.unverified
    assert d["newdom.com"]["company_id"] == "newco" and c["newco"]["review_status"] == "accepted-ai"
    # The decided v3 conflicts are gone; the others stay.
    assert ("proposal-low-certainty", "newdom.com") not in ctypes(conf)
    assert ("kind-differs", "eps") in ctypes(conf)


def test_twin_ambiguous_name_is_a_conflict(built):
    t, conf, v = built
    assert any(c["type"] == "unresolved-name" and c["key"] == "Twin" and c["other"] == "twin1;twin2" for c in conf)


def test_at_stops_the_build(inputs):
    p = inputs.review_dir / "ai/part-9.csv"
    p.write_text(p.read_text() + rows_csv(ITEM_COLS, [item("company:eps", "edit", name=f"x{AT}y.com")]).split("\n", 1)[1])
    with pytest.raises(SystemExit, match="holds '@'"):
        v4.build(inputs)


def test_outputs_and_determinism(inputs, tmp_path):
    t1, c1, v1 = v4.build(inputs)
    t2, c2, v2 = v4.build(inputs)
    assert t1 == t2 and c1 == c2
    out = tmp_path / "out"
    v4.write_outputs(t1, c1, v1, out, "1GB", 1)
    con = duckdb.connect(str(out / "companies.v4.duckdb"), read_only=True)
    cols = [r[0] for r in con.execute("DESCRIBE company").fetchall()]
    assert "university_id" in cols
    assert con.execute("SELECT count(*) FROM company_domain_dropped").fetchone()[0] >= 2
    stats = json.loads((out / "export-v4/v4_stats.json").read_text())
    assert stats["kind"]["public-research"] == 2 and stats["conflicts"]["qid-unverified"] == 1
    assert (out / "export-v4/conflicts.csv").exists() and (out / "export-v4/qids_unverified.csv").exists()
    assert not (out / "companies.duckdb").exists()                # v4 never writes the v3 file
    for p in (out / "export-v4").iterdir():
        if p.suffix == ".csv":
            assert AT not in p.read_text()


def test_version_flag_runs_v4(inputs, tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(v4, "main", lambda argv: seen.setdefault("argv", argv) and 0)
    assert bc.main(["--version", "v4", "--out", str(tmp_path)]) == 0
    assert seen["argv"] == ["--out", str(tmp_path)]
    with pytest.raises(SystemExit):
        bc.main(["--version", "v9"])


def test_typed_name_file_pseudo_merge_and_later_user_domain_decision(inputs):
    md, rd = inputs.manual_dir, inputs.review_dir
    write(md / "v4_typed_names.csv", "typed,company_id,decided_by,reason\nacme-typo-unknown,acme,claude-main,test")
    with open(md / "v4_merges.csv", "a", encoding="utf-8") as f:
        f.write("qco,independent,,claude-main,test\n")
    # The user accepted a proposal for a domain in decisions.csv, and later moved it in chat.
    v3c = inputs.v3_conflicts.read_text() + "proposal-differs-from-map,eps.io,eps,acme,x,\n"
    inputs.v3_conflicts.write_text(v3c)
    items = json.loads((rd / "review_items.json").read_text())
    items["items"].append({"id": "conflict:3", "type": "conflict", "conflict_type": "proposal-differs-from-map",
                           "key": "eps.io", "kept": "eps", "other": "acme", "source": "x"})
    write(rd / "review_items.json", json.dumps(items))
    with open(rd / "decisions.csv", "a", encoding="utf-8") as f:
        f.write(",".join(dec("conflict:3", "accept")) + "\n")
    with open(rd / "decisions.domains.chat.csv", "a", encoding="utf-8") as f:
        f.write("domain:eps:eps.io,eps,eps.io,move,free-provider,,user,2026-10-18T09:00:00Z\n")
    t, conf, v = v4.build(inputs)
    c = by(t["company"], "company_id")
    d = by(t["company_domain"], "domain")
    assert ("unresolved-name", "acme-typo-unknown") not in ctypes(conf)
    assert "qco" not in c and d["qco.com"]["company_id"] == "independent"
    assert c["independent"]["wikidata_qid"] == "" and c["independent"]["kind"] == "independent"
    assert d["eps.io"]["company_id"] == "free-provider"
    assert not any(x["type"] == "domain-decisions-disagree" and x["key"] == "eps.io" for x in conf)


def test_round7_sweep_runs_after_merges_and_user_wins(inputs):
    rd = inputs.review_dir
    with open(rd / "decisions.domains.chat.csv", "a", encoding="utf-8") as f:
        f.write("domain:eps:eps.io,eps,eps.io,move,free-provider,,user,2026-10-18T09:00:00Z\n")
    write(rd / "ai/sweep_review.csv", rows_csv(LINK_COLS, [
        # acme-dup merges into acme, so the sweep (made from v4) names acme for acme-old.com
        ["sweep:acme:acme-old.com", "acme", "acme-old.com", "move", "independent", "high", "personal domain", "claude-review-v7"],
        ["sweep:gamma:gamma.io", "gamma", "gamma.io", "drop", "", "high", "another firm", "claude-review-v7"],
        ["sweep:eps:eps.io", "eps", "eps.io", "keep", "", "high", "", "claude-review-v7"],
        ["sweep:beta:delta.io", "beta", "delta.io", "move", "independent", "high", "stale row", "claude-review-v7"],
    ]))
    t, conf, v = v4.build(inputs)
    d = by(t["company_domain"], "domain")
    assert d["acme-old.com"]["company_id"] == "independent"
    assert "gamma.io" not in d
    assert d["eps.io"]["company_id"] == "free-provider"            # the user's decision wins over the sweep
    assert v.stats["sweep_rows_superseded_by_user"] == 1
    assert d["delta.io"]["company_id"] == "delta"                  # a row for another organisation changes nothing
    assert any(x["type"] == "domain-decision-company-differs" and x["key"] == "delta.io" for x in conf)


def test_later_chat_decision_wins_over_earlier_review_decision(inputs):
    rd = inputs.review_dir
    with open(rd / "decisions.csv", "a", encoding="utf-8") as f:
        f.write(",".join(dec("company:gamma", "accept")) + "\n")          # 2026-10-17T10:00:00Z
    row = dec("company:gamma", "edit", parent="acme")
    row[-1] = "2026-10-18T12:00:00Z"
    with open(rd / "decisions.chat.csv", "a", encoding="utf-8") as f:
        f.write(",".join(row) + "\n")
    t, conf, v = v4.build(inputs)
    assert by(t["company"], "company_id")["gamma"]["parent_company_id"] == "acme"
    assert v.stats["user_decisions_replaced_by_later_chat"] >= 1


def test_user_keep_after_merge_and_keep_without_row(inputs):
    rd = inputs.review_dir
    with open(rd / "decisions.domains.chat.csv", "a", encoding="utf-8") as f:
        # acme-dup merges into acme later in the build: the keep names the kept id
        f.write("domain:acme:acme-old.com,acme,acme-old.com,keep,,,user,2026-10-18T09:00:00Z\n")
        # a domain with no row: the user's keep gives it one
        f.write("domain:beta:beta-new.io,beta,beta-new.io,keep,,,user,2026-10-18T09:00:00Z\n")
    t, conf, v = v4.build(inputs)
    d = by(t["company_domain"], "domain")
    assert d["acme-old.com"]["company_id"] == "acme"
    assert d["beta-new.io"]["company_id"] == "beta"
    assert not any(x["type"] == "domain-decision-company-differs" and x["key"] == "acme-old.com" for x in conf)


# ---------------------------------------------------------------- v4.2 layer (2026-10-19)

def v42_files(md: Path) -> None:
    write(md / "v42_new_orgs.csv", rows_csv(
        "company_id,name,kind,sna_sector,country,parent_company_id,domains,aliases,decided_by,reason,source_url", [
            ["holdco", "Holdco", "company", "S.11", "US", "", "holdco.example.org", "", "claude-main", "test",
             "https://example.org/holdco"]]))
    write(md / "v42_merges.csv", rows_csv("merge_id,into_id,kept_name,decided_by,reason,source_url",
                                          [["child3", "beta", "", "claude-main", "test", "https://example.org/m"]]))
    cols = "company_id,field,value,decided_by,reason,source_url"
    write(md / "v42_fields.csv", rows_csv(cols, [
        ["beta", "parent_company_id", "Holdco", "claude-main", "a typed name resolves", "https://example.org/a"],
        ["acme", "lei", "LEI0000000000000001", "claude-main", "test", "https://example.org/b"],
        ["child2", "parent_company_id", "beta", "claude-main", "the user's parent wins", "https://example.org/c"],
        ["gamma", "name", "Gamma New", "claude-main", "a rename keeps the old name as an alias", "https://example.org/c"],
        ["beta", "wikidata_qid", "Q1", "claude-main", "acme holds Q1", "https://example.org/d"],
        ["delta", "parent_company_id", "delta", "claude-main", "self", "https://example.org/e"],
        ["child3", "country", "DE", "claude-main", "a merged id goes to the kept id", "https://example.org/f"],
        ["acme", "kind", "academic", "claude-main", "not a v4.2 field", "https://example.org/g"]]))
    write(md / "v42_domains.csv", rows_csv("domain,company_id,action,decided_by,reason,source_url", [
        ["other-brand.com", "beta", "move", "claude-main", "test", "https://example.org/h"],
        ["fresh.example.org", "beta", "add", "claude-main", "test", "https://example.org/i"],
        ["newbrand.com", "beta", "move", "claude-main", "a user domain decision wins", "https://example.org/j"],
        ["nowhere.example.org", "beta", "move", "claude-main", "no row", "https://example.org/k"]]))


def test_v42_layer_patches_after_all_steps(inputs):
    with open(inputs.review_dir / "decisions.csv", "a", encoding="utf-8") as f:
        f.write(",".join(dec("company:child2", "edit", parent="acme")) + "\n")
    t0, _, _ = v4.build(inputs)
    v42_files(inputs.manual_dir)
    t, conf, v = v4.build(inputs)
    co, dm = by(t["company"], "company_id"), by(t["company_domain"], "domain")
    assert co["holdco"]["review_date"] == v4.V42_DATE and dm["holdco.example.org"]["company_id"] == "holdco"
    assert "child3" not in co and "child3" in by(t0["company"], "company_id")
    assert co["beta"]["parent_company_id"] == "holdco"
    assert (co["beta"]["review_status"], co["beta"]["reviewer"], co["beta"]["review_date"]) == \
        ("ai-reviewed", "claude-main", v4.V42_DATE)
    assert co["beta"]["country"] == "DE"
    assert co["acme"]["lei"] == "LEI0000000000000001" and co["acme"]["kind"] == by(t0["company"], "company_id")["acme"]["kind"]
    assert co["child2"]["parent_company_id"] == "acme" and co["gamma"]["name"] == "Gamma New"
    old = by(t0["company"], "company_id")["gamma"]["name"]
    assert any(a["alias"] == old and a["company_id"] == "gamma" for a in t["company_alias"])
    assert co["beta"]["wikidata_qid"] != "Q1" and co["delta"]["parent_company_id"] in ("", None)
    assert dm["other-brand.com"]["company_id"] == "beta" and dm["fresh.example.org"]["company_id"] == "beta"
    assert dm["newbrand.com"]["company_id"] == "new-org" and "nowhere.example.org" not in dm
    c = ctypes(conf)
    assert {("v42-user-decision-wins", "child2"), ("v42-qid-in-use", "beta"), ("v42-self-reference", "delta"),
            ("unknown-field", "acme"), ("v42-user-decision-wins", "newbrand.com"),
            ("v42-domain-missing", "nowhere.example.org")} <= c
    assert v.stats["v42_domains_move"] == 1 and v.stats["v42_domains_add"] == 1
    ids = {r["source_id"] for r in t["source_registry"]}
    assert {"manual-v42-new-orgs", "manual-v42-merges", "manual-v42-fields", "manual-v42-domains"} <= ids


def test_v42_without_files_changes_nothing(inputs):
    t0, c0, _ = v4.build(inputs)
    write(inputs.manual_dir / "v42_fields.csv", "company_id,field,value,decided_by,reason,source_url\n")
    t1, c1, _ = v4.build(inputs)
    assert t0["company"] == t1["company"] and t0["company_domain"] == t1["company_domain"] and c0 == c1


def test_db_and_export_names(inputs, tmp_path):
    t, conf, v = v4.build(inputs)
    out = tmp_path / "out42"
    v4.write_outputs(t, conf, v, out, "1GB", 1, db_name="companies.v4.2.duckdb", export_name="export-v4.2")
    assert (out / "companies.v4.2.duckdb").exists() and (out / "export-v4.2/company.parquet").exists()
    assert not (out / "companies.v4.duckdb").exists() and not (out / "export-v4").exists()


NS_COLS = "host,namespace,company_id,relation,class,verified,decided_by,evidence,source_url"


def v43_files(inputs) -> None:
    """Namespace rows in the v3 database and the v4.3 manual files (the namespace rule of 2026-10-19)."""
    con = duckdb.connect(str(inputs.v3_db))
    cols = [c for c, _ in bc.SCHEMA["company_namespace"]]
    rows = [("github.com", "Acme-Org", "org", "delta", "owns", "roster", None, "roster-x#line=2", ""),
            ("github.com", "acme-org", "org", "acme", "candidate", "spinellis", False, "s", ""),
            ("github.com", "proj", "org", "delta", "owns", "roster", None, "roster-x#line=3", ""),
            ("github.com", "unsure-ns", "org", "delta", "owns", "roster", None, "roster-x#line=4", ""),
            ("github.com", "one-person", "", "delta", "owns", "roster", None, "roster-x#line=5", "")]
    con.executemany(f"INSERT INTO company_namespace ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)
    con.close()
    md, rd = inputs.manual_dir, inputs.review_dir
    write(md / "v43_new_orgs.csv", rows_csv(
        "company_id,name,kind,sna_sector,country,parent_company_id,domains,aliases,decided_by,reason,source_url", [
            ["proj-x", "Proj X", "project", "", "", "delta", "", "", "claude-main", "a project account", "https://example.org/p"],
            ["beta", "Beta Again", "project", "", "", "", "", "", "claude-main", "id in use", ""]]))
    write(md / "v43_fields.csv", rows_csv("company_id,field,value,decided_by,reason,source_url", [
        ["lonely", "parent_company_id", "delta", "claude-main", "hosting foundation", "https://example.org/f"]]))
    write(md / "v43_namespaces.csv", rows_csv(NS_COLS, [
        ["github.com", "acme-org", "delta", "hosted_by", "company", "", "claude-main", "roster line", "https://example.org/1"],
        ["github.com", "acme-org", "acme", "owns", "company", "True", "claude-main", "website of acme", "https://example.org/1"],
        ["github.com", "proj", "delta", "hosted_by", "project", "", "claude-main", "a project account", ""],
        ["github.com", "proj", "proj-x", "owns", "project", "False", "claude-main", "a project account", ""],
        ["github.com", "unsure-ns", "delta", "owns", "unclear", "", "claude-main", "not clear", ""],
        ["github.com", "proj", "delta", "sponsors", "project", "", "claude-main", "bad value", ""]]))
    write(rd / "v43_namespaces.private.csv", rows_csv(NS_COLS, [
        ["github.com", "one-person", "delta", "hosted_by", "person", "", "claude-main", "a user account", ""]]))


def test_v43_layer_sets_the_controller_and_hosted_by(inputs):
    v43_files(inputs)
    t, conf, v = v4.build(inputs)
    ns = {(n["namespace"].lower(), n["company_id"]): n for n in t["company_namespace"]}
    assert ns[("acme-org", "delta")]["relation"] == "hosted_by"
    assert ns[("acme-org", "acme")]["relation"] == "owns"          # the candidate row becomes owns
    assert ns[("proj", "delta")]["relation"] == "hosted_by"
    p = ns[("proj", "proj-x")]
    assert (p["relation"], p["evidence"], p["verified"], p["namespace"]) == ("owns", "account-profile", False, "proj")
    assert ns[("unsure-ns", "delta")]["relation"] == "owns"        # unclear: no change, a review conflict
    assert ns[("one-person", "delta")]["relation"] == "hosted_by"  # the private file
    assert not any(n["relation"] == "owns" for k, n in ns.items() if k[0] == "one-person")
    co = by(t["company"], "company_id")
    assert co["proj-x"]["kind"] == "project" and co["proj-x"]["parent_company_id"] == "delta"
    assert co["proj-x"]["review_date"] == v4.V43_DATE and co["beta"]["name"] != "Beta Again"
    assert co["lonely"]["parent_company_id"] == "delta"
    c = ctypes(conf)
    assert {("v43-namespace-review", "github.com/unsure-ns"), ("new-organisation-exists", "beta"),
            ("v43-unknown-value", "github.com/proj")} <= c
    assert v.stats["v43_relation:owns->hosted_by"] == 3 and v.stats["v43_added:owns"] == 1
    assert v.stats["v43_relation:candidate->owns"] == 1
    ids = {r["source_id"] for r in t["source_registry"]}
    assert {"manual-v43-new-orgs", "manual-v43-fields", "manual-v43-namespaces", "review-v43-namespaces-private"} <= ids


def test_v43_layer_left_out_gives_the_v42_tables(inputs):
    v43_files(inputs)
    inputs.layer = "v4.2"
    t, conf, _ = v4.build(inputs)
    assert all(n["relation"] in ("owns", "candidate") for n in t["company_namespace"])
    assert "proj-x" not in by(t["company"], "company_id")
    assert not any(c["type"].startswith("v43") for c in conf)
    inputs.layer = "v9"
    with pytest.raises(SystemExit):
        v4.build(inputs)


def test_dedupe_keeps_owns_over_hosted_by(inputs):
    v43_files(inputs)
    v = v4.V4(inputs)
    v.comp = {"delta": {}}
    v.ns = [{"host": "github.com", "namespace": "x", "company_id": "delta", "relation": "hosted_by"},
            {"host": "github.com", "namespace": "X", "company_id": "delta", "relation": "owns"},
            {"host": "github.com", "namespace": "y", "company_id": "delta", "relation": "hosted_by"},
            {"host": "github.com", "namespace": "y", "company_id": "delta", "relation": "candidate"}]
    got = {n["namespace"].lower(): n["relation"] for n in v.dedupe_ns()}
    assert got == {"x": "owns", "y": "hosted_by"}


def v44_files(inputs) -> None:
    """The v4.3 files and the v4.4 manual files (the web checks of round 9, 2026-10-20)."""
    v43_files(inputs)
    md = inputs.manual_dir
    hdr = "company_id,name,kind,sna_sector,country,parent_company_id,domains,aliases,decided_by,reason,source_url"
    write(md / "v44_new_orgs.csv", rows_csv(hdr, [
        ["qco-parent", "Qco Parent", "company", "S.11", "FR", "", "", "", "claude-main", "a buyer", "https://example.org/b"],
        ["eps", "Eps Again", "project", "", "", "", "", "", "claude-main", "an id in use", ""],
        ["twin2", "Twin Again", "project", "", "", "", "", "", "claude-main", "a merged id", ""]]))
    write(md / "v44_merges.csv", rows_csv("merge_id,into_id,kept_name,decided_by,reason,source_url", [
        ["eps", "acme", "", "claude-main", "brand gone", "https://example.org/m"],
        ["nobody-id", "acme", "", "claude-main", "bad id", ""]]))
    write(md / "v44_fields.csv", rows_csv("company_id,field,value,decided_by,reason,source_url", [
        ["gamma", "kind", "project", "claude-main", "a project", "https://example.org/k"],
        ["beta", "kind", "foundation", "claude-main", "a foundation", "https://example.org/k"],
        ["beta", "sna_sector", "S.13", "claude-main", "sector after kind", "https://example.org/k"],
        ["qco", "parent_company_id", "qco-parent", "claude-main", "the buyer", "https://example.org/b"],
        ["qco", "sna_sector", "S.99", "claude-main", "bad sector", ""],
        ["qco", "kind", "spaceship", "claude-main", "bad kind", ""]]))
    write(md / "v44_domains.csv", rows_csv("domain,company_id,action,decided_by,reason,source_url", [
        ["qco.com", "qco-parent", "move", "claude-main", "domain move", "https://example.org/d"],
        ["delta.io", "delta", "drop", "claude-main", "a parked domain", "https://example.org/d"],
        ["mover.com", "acme", "drop", "claude-main", "another owner", ""],
        ["newbrand.com", "acme", "move", "claude-main", "a user decision holds it", ""]]))
    write(md / "v44_namespaces.csv", rows_csv(NS_COLS, [
        ["github.com", "acme-org", "delta", "(remove)", "company", "", "claude-main", "one repository only", "https://example.org/n"],
        ["github.com", "unsure-ns", "delta", "hosted_by", "project", "", "claude-main", "decided", "https://example.org/n"],
        ["github.com", "unsure-ns", "proj-x", "owns", "project", "", "claude-main", "decided", "https://example.org/n"],
        ["github.com", "no-such-ns", "delta", "(remove)", "company", "", "claude-main", "nothing", ""]]))
    write(inputs.review_dir / "v44_namespaces.private.csv", rows_csv(NS_COLS, [
        ["github.com", "one-person", "delta", "(remove)", "person", "", "claude-main", "a user account", ""]]))


def test_v44_layer_applies_round9(inputs):
    v44_files(inputs)
    t, conf, v = v4.build(inputs)
    co, dm = by(t["company"], "company_id"), by(t["company_domain"], "domain")
    ns = {(n["namespace"].lower(), n["company_id"]): n for n in t["company_namespace"]}
    assert ("acme-org", "delta") not in ns and ns[("acme-org", "acme")]["relation"] == "owns"
    assert ns[("unsure-ns", "delta")]["relation"] == "hosted_by"
    assert ns[("unsure-ns", "proj-x")]["relation"] == "owns" and ns[("unsure-ns", "proj-x")]["fetched_at"] == v4.V44_DATE
    assert "eps" not in co and dm["eps.io"]["company_id"] == "acme"
    assert (co["gamma"]["kind"], co["gamma"]["sna_sector"], co["gamma"]["is_company"]) == ("project", "", False)
    assert (co["beta"]["kind"], co["beta"]["sna_sector"]) == ("foundation", "S.13")
    assert co["qco"]["parent_company_id"] == "qco-parent" and co["qco"]["kind"] == "company"
    assert co["qco-parent"]["review_date"] == v4.V44_DATE and dm["qco.com"]["company_id"] == "qco-parent"
    assert "delta.io" not in dm and "delta.io" in by(t["company_domain_dropped"], "domain")
    assert dm["mover.com"]["company_id"] == "mover" and dm["newbrand.com"]["company_id"] != "acme"
    c = ctypes(conf)
    assert {("v44-merge-unknown-id", "nobody-id"), ("v44-unknown-sector", "qco"), ("unknown-kind", "qco"),
            ("v44-domain-owner-differs", "mover.com"), ("v44-user-decision-wins", "newbrand.com"),
            ("v44-namespace-row-missing", "github.com/no-such-ns"), ("new-organisation-exists", "eps"), ("new-organisation-exists", "twin2")} <= c
    assert any(x["key"] == "twin2" and x["detail"] == "the id is a merged id" for x in conf)
    assert ("v43-namespace-review", "github.com/unsure-ns") not in c and v.stats["v44_closed_v43_reviews"] == 1
    assert not any(k[0] == "one-person" for k in ns)
    assert v.stats["v44_removed:hosted_by"] == 2 and v.stats["v44_merges"] == 1 and v.stats["v44_domains_drop"] == 1
    ids = {r["source_id"] for r in t["source_registry"]}
    assert {"manual-v44-new-orgs", "manual-v44-merges", "manual-v44-fields", "manual-v44-domains",
            "manual-v44-namespaces", "review-v44-namespaces-private"} <= ids


def test_v44_layer_left_out_gives_the_v43_tables(inputs):
    v43_files(inputs)
    t43, c43, _ = v4.build(inputs)
    v44_files(inputs)
    inputs.layer = "v4.3"
    t, conf, _ = v4.build(inputs)
    assert t["company"] == t43["company"] and t["company_namespace"] == t43["company_namespace"] and conf == c43
    assert not any(c["type"].startswith("v44") for c in conf)


def v45_files(inputs) -> None:
    """The v4.4 files and the v4.5 manual files (the user's answers to the v4.4 audit, 2026-10-20)."""
    v44_files(inputs)
    md = inputs.manual_dir
    write(md / "v45_fields.csv", rows_csv("company_id,field,value,decided_by,reason,source_url", [
        ["delta", "kind", "fiscal-sponsor", "claude-main", "a fiscal sponsor", "https://example.org/k"],
        ["proj-x", "parent_company_id", "acme", "claude-main", "the main developer", "https://example.org/p"]]))
    write(md / "v45_namespaces.csv", rows_csv(NS_COLS, [
        ["github.com", "proj", "delta", "(remove)", "project", "", "claude-main", "a community project", "https://example.org/n"],
        ["github.com", "new-ns", "delta", "hosted_by", "project", "", "claude-main", "on the sponsor list", "https://example.org/n"],
        ["github.com", "fs-own", "delta", "owns", "project", "", "claude-main", "a roster row", "https://example.org/n"]]))
    write(inputs.review_dir / "v45_namespaces.private.csv", rows_csv(NS_COLS, [
        ["github.com", "no-such-ns", "delta", "(remove)", "person", "", "claude-main", "nothing", ""]]))


def test_v45_layer_moves_fiscal_sponsors_to_sponsored_by(inputs):
    v45_files(inputs)
    t, conf, v = v4.build(inputs)
    co = by(t["company"], "company_id")
    ns = {(n["namespace"].lower(), n["company_id"]): n for n in t["company_namespace"]}
    assert co["delta"]["kind"] == "fiscal-sponsor" and co["proj-x"]["parent_company_id"] == "acme"
    assert ("proj", "delta") not in ns and ns[("proj", "proj-x")]["relation"] == "owns"
    assert ns[("unsure-ns", "delta")]["relation"] == "sponsored_by"       # a v4.4 hosted_by row
    assert ns[("new-ns", "delta")]["relation"] == "sponsored_by"          # a v4.5 row, renamed after
    assert ns[("fs-own", "delta")]["relation"] == "sponsored_by"          # a fiscal sponsor never owns
    assert not any(n["relation"] in ("owns", "hosted_by") for n in t["company_namespace"] if n["company_id"] == "delta")
    assert v.stats["v45_relation:hosted_by->sponsored_by"] == 2 and v.stats["v45_relation:owns->sponsored_by"] == 1
    assert v.stats["v45_removed:hosted_by"] == 1
    assert ("v45-namespace-row-missing", "github.com/no-such-ns") in ctypes(conf)
    ids = {r["source_id"] for r in t["source_registry"]}
    assert {"manual-v45-fields", "manual-v45-namespaces", "review-v45-namespaces-private"} <= ids


def test_v45_layer_left_out_gives_the_v44_tables(inputs):
    v44_files(inputs)
    inputs.layer = "v4.4"
    t44, c44, _ = v4.build(inputs)
    v45_files(inputs)
    t, conf, _ = v4.build(inputs)
    assert t["company"] == t44["company"] and t["company_namespace"] == t44["company_namespace"] and conf == c44
    assert not any(c["type"].startswith("v45") for c in conf)
    assert "sponsored_by" not in {n["relation"] for n in t["company_namespace"]}


NS46_COLS = NS_COLS + ",row_evidence,namespace_type,source_pointer,fetched_at"


def v46_files(inputs) -> None:
    """The v4.5 files and the v4.6 manual files (the new rule N2 of the user, 2026-10-21)."""
    v45_files(inputs)
    write(inputs.manual_dir / "v46_namespaces.csv", rows_csv(NS46_COLS, [
        ["github.com", "proj", "acme", "hosted_by", "project", "False", "claude-main", "restored", "https://example.org/n",
         "roster", "org", "roster-x#line=3", "2026-10-05T01:38:05Z"],
        ["github.com", "gone-ns", "acme", "hosted_by", "project", "", "claude-main", "restored", "https://example.org/n",
         "", "", "", ""],
        ["github.com", "proj-x-ns", "no-such-id", "hosted_by", "project", "", "claude-main", "unknown id", ""
         , "", "", "", ""]]))
    write(inputs.review_dir / "v46_namespaces.private.csv", rows_csv(NS46_COLS, [
        ["github.com", "proj", "delta", "hosted_by", "person", "", "claude-main", "restored", "",
         "roster", "", "roster-x#line=3", "2026-10-05T01:38:05Z"]]))


def test_v46_layer_adds_back_hosted_by_rows_with_their_fields(inputs):
    v46_files(inputs)
    t, conf, v = v4.build(inputs)
    co = by(t["company"], "company_id")
    ns = {(n["namespace"].lower(), n["company_id"]): n for n in t["company_namespace"]}
    back = ns[("proj", "acme")]
    assert back["relation"] == "hosted_by" and back["evidence"] == "roster" and back["namespace_type"] == "org"
    assert back["verified"] is False and back["source_pointer"] == "roster-x#line=3"
    assert back["fetched_at"] == "2026-10-05T01:38:05Z"
    new = ns[("gone-ns", "acme")]                        # no optional fields: the defaults of a manual row
    assert new["evidence"] == v4.V43_EVIDENCE and new["source_pointer"] == "manual/v46_namespaces.csv#github.com/gone-ns"
    assert new["fetched_at"] == v4.V46_DATE and new["verified"] is None and new["namespace_type"] is None  # a blank column
    assert ns[("proj", "delta")]["relation"] == "sponsored_by"   # the fiscal-sponsor rule runs after the rows
    assert ns[("proj", "proj-x")]["relation"] == "owns"           # the owner and the v4.5 parent stay
    assert co["proj-x"]["parent_company_id"] == "acme"
    assert v.stats["v46_added:hosted_by"] == 3 and v.stats["v46_relation:hosted_by->sponsored_by"] == 1
    ids = {r["source_id"] for r in t["source_registry"]}
    assert {"manual-v46-namespaces", "review-v46-namespaces-private"} <= ids
    assert not any(n["company_id"] == "no-such-id" for n in t["company_namespace"])


def test_v46_layer_left_out_gives_the_v45_tables(inputs):
    v45_files(inputs)
    inputs.layer = "v4.5"
    t45, c45, _ = v4.build(inputs)
    v46_files(inputs)
    t, conf, _ = v4.build(inputs)
    assert t["company"] == t45["company"] and t["company_namespace"] == t45["company_namespace"] and conf == c45
    assert not any(c["type"].startswith("v46") for c in conf)


def v47_files(inputs) -> None:
    """The v4.6 files and the v4.7 files (AI round 10: the new domains and namespaces of the
    1,000-4,999 commit layer, 2026-10-25)."""
    v46_files(inputs)
    md, rd = inputs.manual_dir, inputs.review_dir
    hdr = "company_id,name,kind,sna_sector,country,parent_company_id,domains,aliases,decided_by,reason,source_url"
    write(md / "v47_new_orgs.csv", rows_csv(hdr, [
        ["newfirm", "New Firm", "company", "S.11", "DE", "", "", "", "claude-main", "a firm of the layer", "https://example.org/f"],
        ["newproj", "New Project", "project", "", "", "acme", "", "", "claude-main", "a project account", "https://example.org/p"],
        ["acme", "Acme Again", "company", "S.11", "", "", "", "", "claude-main", "an id in use", ""]]))
    write(md / "v47_merges.csv", rows_csv("merge_id,into_id,kept_name,decided_by,reason,source_url", [
        ["lonely", "beta", "", "claude-main", "one firm", "https://example.org/m"]]))
    write(md / "v47_fields.csv", rows_csv("company_id,field,value,decided_by,reason,source_url", [
        ["gamma", "country", "FR", "claude-main", "the imprint", "https://example.org/g"]]))
    write(md / "v47_domains.csv", rows_csv("domain,company_id,action,decided_by,reason,source_url", [
        ["newfirm.de", "newfirm", "add", "claude-main", "the firm's site", "https://example.org/f"],
        ["mail.newfirm.de", "newfirm", "add", "claude-main", "a subdomain", "https://example.org/f"],
        ["acme.com", "beta", "add", "claude-main", "add over another owner", ""],
        ["webmail-x.net", "free-provider", "add", "claude-main", "a mail service", "https://example.org/w"]]))
    write(rd / "v47_domains.private.csv", rows_csv("domain,company_id,action,decided_by,reason,source_url", [
        ["someone-x.name", "independent", "add", "claude-main", "personal domain", ""]]))
    write(md / "v47_namespaces.csv", rows_csv(NS46_COLS, [
        ["github.com", "newfirm-gh", "newfirm", "owns", "company", "", "claude-main", "the account site", "https://example.org/f",
         "", "org", "", ""],
        ["github.com", "newproj", "newproj", "owns", "project", "", "claude-main", "the project account", "https://example.org/p",
         "", "org", "", ""],
        ["github.com", "newproj", "delta", "hosted_by", "project", "", "claude-main", "a sponsored project", "https://example.org/p",
         "roster", "org", "", ""],
        ["github.com", "gone-ns", "acme", "(remove)", "project", "", "claude-main", "not on the list", "https://example.org/n",
         "", "", "", ""]]))
    write(rd / "v47_namespaces.private.csv", rows_csv(NS46_COLS, [
        ["github.com", "solo-dev", "acme", "hosted_by", "person", "", "claude-main", "on the foundation list", "https://example.org/l",
         "roster", "user", "", ""]]))


def test_v47_layer_applies_round10(inputs):
    v47_files(inputs)
    t, conf, v = v4.build(inputs)
    co = by(t["company"], "company_id")
    dm = by(t["company_domain"], "domain")
    ns = {(n["namespace"].lower(), n["company_id"]): n for n in t["company_namespace"]}
    assert co["newfirm"]["kind"] == "company" and co["newfirm"]["country"] == "DE"
    assert co["newproj"]["kind"] == "project" and co["newproj"]["parent_company_id"] == "acme"
    assert co["acme"]["name"] == "Acme" and ("new-organisation-exists", "acme") in ctypes(conf)
    assert "lonely" not in co and co["gamma"]["country"] == "FR"
    assert dm["newfirm.de"]["company_id"] == "newfirm" and dm["mail.newfirm.de"]["company_id"] == "newfirm"
    assert dm["webmail-x.net"]["company_id"] == "free-provider"
    assert dm["someone-x.name"]["company_id"] == "independent"               # the private file
    assert dm["someone-x.name"]["source_pointer"] == "review/v47_domains.private.csv#domain=someone-x.name"
    assert dm["acme.com"]["company_id"] == "acme" and ("v47-domain-exists", "acme.com") in ctypes(conf)
    assert ns[("newfirm-gh", "newfirm")]["relation"] == "owns" and ns[("newfirm-gh", "newfirm")]["namespace_type"] == "org"
    assert ns[("newproj", "newproj")]["relation"] == "owns"
    assert ns[("newproj", "delta")]["relation"] == "sponsored_by"            # delta is a fiscal sponsor (v4.5)
    assert ns[("newproj", "delta")]["evidence"] == "roster"
    assert ("gone-ns", "acme") not in ns
    assert ns[("solo-dev", "acme")]["relation"] == "hosted_by"
    assert v.stats["v47_added:owns"] == 2 and v.stats["v47_removed:hosted_by"] == 1 and v.stats["v47_merges"] == 1
    assert v.stats["v47_domains_add"] == 4
    ids = {r["source_id"] for r in t["source_registry"]}
    assert {"manual-v47-new-orgs", "manual-v47-merges", "manual-v47-fields", "manual-v47-domains",
            "review-v47-domains-private", "manual-v47-namespaces", "review-v47-namespaces-private"} <= ids


def test_v47_layer_left_out_gives_the_v46_tables(inputs):
    v46_files(inputs)
    inputs.layer = "v4.6"
    t46, c46, _ = v4.build(inputs)
    v47_files(inputs)
    t, conf, _ = v4.build(inputs)
    assert t["company"] == t46["company"] and t["company_namespace"] == t46["company_namespace"] and conf == c46
    assert t["company_domain"] == t46["company_domain"]
    assert not any(c["type"].startswith("v47") for c in conf)


def v48_files(inputs) -> None:
    """The v4.7 files and the v4.8 files (AI round 11: the organisation accounts of the 5,000+ layer)."""
    v47_files(inputs)
    md, rd = inputs.manual_dir, inputs.review_dir
    hdr = "company_id,name,kind,sna_sector,country,parent_company_id,domains,aliases,decided_by,reason,source_url"
    write(md / "v48_new_orgs.csv", rows_csv(hdr, [
        ["oldproj", "Old Project", "project", "", "", "newfirm", "", "", "claude-main", "a project account", "https://example.org/o"]]))
    write(md / "v48_namespaces.csv", rows_csv(NS46_COLS, [
        ["github.com", "oldproj", "oldproj", "owns", "project", "", "claude-main", "the project account", "https://example.org/o",
         "", "org", "", ""],
        ["github.com", "acme-org", "acme", "owns", "company", "", "claude-main", "the firm's account", "https://example.org/a",
         "", "org", "", ""]]))
    write(md / "v48_fields.csv", rows_csv("company_id,field,value,decided_by,reason,source_url", [
        ["newproj", "country", "NL", "claude-main", "the project site", "https://example.org/p"]]))


def test_v48_layer_applies_round11(inputs):
    v48_files(inputs)
    t, conf, v = v4.build(inputs)
    co = by(t["company"], "company_id")
    ns = {(n["namespace"].lower(), n["company_id"]): n for n in t["company_namespace"]}
    assert co["oldproj"]["kind"] == "project" and co["oldproj"]["parent_company_id"] == "newfirm"
    assert co["newproj"]["country"] == "NL"
    assert ns[("oldproj", "oldproj")]["relation"] == "owns" and ns[("acme-org", "acme")]["relation"] == "owns"
    assert v.stats["v48_added:owns"] >= 1   # acme-org may already have a row of acme (then the relation changes)
    ids = {r["source_id"] for r in t["source_registry"]}
    assert {"manual-v48-new-orgs", "manual-v48-namespaces", "manual-v48-fields"} <= ids


def test_v48_layer_left_out_gives_the_v47_tables(inputs):
    v47_files(inputs)
    inputs.layer = "v4.7"
    t47, c47, _ = v4.build(inputs)
    v48_files(inputs)
    t, conf, _ = v4.build(inputs)
    assert t["company"] == t47["company"] and t["company_namespace"] == t47["company_namespace"] and conf == c47
    assert not any(c["type"].startswith("v48") for c in conf)


def v49_files(inputs) -> None:
    """The v4.8 files and the v4.9 files (the user's answers of the audit pages v47 and v48, 2026-10-25):
    a merge, a move of a domain to independent, a hosted_by move to another foundation, a parent."""
    v48_files(inputs)
    md = inputs.manual_dir
    hdr = "company_id,name,kind,sna_sector,country,parent_company_id,domains,aliases,decided_by,reason,source_url"
    write(md / "v49_new_orgs.csv", rows_csv(hdr, [
        ["sub-found", "Sub Foundation", "foundation", "S.15", "US", "delta", "", "", "claude-main", "a sub-foundation",
         "https://example.org/s"]]))
    write(md / "v49_merges.csv", rows_csv("merge_id,into_id,kept_name,decided_by,reason,source_url", [
        ["oldproj", "newproj", "", "claude-main", "the user: one project", "https://example.org/m"]]))
    write(md / "v49_fields.csv", rows_csv("company_id,field,value,decided_by,reason,source_url", [
        ["newfirm", "parent_company_id", "acme", "claude-main", "the user: the current owner", "https://example.org/o"]]))
    write(md / "v49_domains.csv", rows_csv("domain,company_id,action,decided_by,reason,source_url", [
        ["newfirm.de", "independent", "move", "claude-main", "the user's rule: an account-only organisation", ""]]))
    write(md / "v49_namespaces.csv", rows_csv(NS46_COLS, [
        ["github.com", "newproj", "delta", "(remove)", "project", "", "claude-main", "the sub-foundation hosts it",
         "https://example.org/s", "", "org", "", ""],
        ["github.com", "newproj", "sub-found", "hosted_by", "project", "", "claude-main", "the sub-foundation list",
         "https://example.org/s", "roster", "org", "", ""]]))


def test_v49_layer_applies_the_audit_answers(inputs):
    v49_files(inputs)
    t, conf, v = v4.build(inputs)
    co = by(t["company"], "company_id")
    dm = by(t["company_domain"], "domain")
    ns = {(n["namespace"].lower(), n["company_id"]): n for n in t["company_namespace"]}
    assert "oldproj" not in co and co["newfirm"]["parent_company_id"] == "acme"
    assert co["sub-found"]["kind"] == "foundation" and co["sub-found"]["parent_company_id"] == "delta"
    assert dm["newfirm.de"]["company_id"] == "independent"
    assert ("newproj", "delta") not in ns and ns[("newproj", "sub-found")]["relation"] == "hosted_by"
    assert ns[("oldproj", "newproj")]["relation"] == "owns"        # the merge moves the owns row
    assert v.stats["v49_merges"] == 1
    ids = {r["source_id"] for r in t["source_registry"]}
    assert {"manual-v49-new-orgs", "manual-v49-merges", "manual-v49-fields", "manual-v49-domains",
            "manual-v49-namespaces"} <= ids


def test_v49_layer_left_out_gives_the_v48_tables(inputs):
    v48_files(inputs)
    inputs.layer = "v4.8"
    t48, c48, _ = v4.build(inputs)
    v49_files(inputs)
    t, conf, _ = v4.build(inputs)
    assert t["company"] == t48["company"] and t["company_namespace"] == t48["company_namespace"] and conf == c48
    assert t["company_domain"] == t48["company_domain"]
    assert not any(c["type"].startswith("v49") for c in conf)
