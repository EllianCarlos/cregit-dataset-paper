"""Unit tests of error_model.py (no workspace data needed)."""
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import error_model as em  # noqa: E402


def test_wilson_known_value():
    lo, hi = em.wilson(10, 100)
    assert lo == pytest.approx(0.0552, abs=1e-4)
    assert hi == pytest.approx(0.1744, abs=1e-4)


def test_wilson_zero_and_empty():
    lo, hi = em.wilson(0, 50)
    assert lo == pytest.approx(0.0, abs=1e-12) and 0.06 < hi < 0.08
    assert em.wilson(0, 0) == (0.0, 1.0)


def test_lincoln_petersen_and_chapman():
    assert em.lincoln_petersen(100, 80, 40) == 200
    assert math.isinf(em.lincoln_petersen(10, 10, 0))
    n, var = em.chapman(100, 80, 40)
    assert n == pytest.approx(101 * 81 / 41 - 1)
    assert var > 0
    n0, var0 = em.chapman(10, 10, 10)          # every error found twice: nothing missed
    assert n0 == pytest.approx(10.0) and var0 == 0


def test_removal_two_pass():
    # N = 100, p = 0.8: pass 1 finds 80, pass 2 finds 16 of the 20 left.
    p, n = em.removal_two_pass(80, 16)
    assert p == pytest.approx(0.8)
    assert n == pytest.approx(100)
    p, n = em.removal_two_pass(5, 5)
    assert math.isnan(p) and math.isinf(n)


def test_two_rater_independent_recovers_rates():
    a, b = 0.10, 0.06
    x, y, z = a * (1 - b), b * (1 - a), a * b
    t = em.two_rater(x, y, 0.0)
    assert t["a"] == pytest.approx(a, abs=1e-6)
    assert t["b"] == pytest.approx(b, abs=1e-6)
    assert t["agree_wrong"] == pytest.approx(z / (1 - x - y), abs=1e-6)


def test_two_rater_w_above_root_gives_zero_agreed_wrong():
    t = em.two_rater(0.09, 0.05, 0.02)       # both-wrong disagreements exceed the independent product
    assert t["z"] == pytest.approx(0.02)
    assert t["agree_wrong"] == 0.0


def test_two_rater_correlation_raises_agreed_wrong_and_has_a_limit():
    lo = em.two_rater(0.0866, 0.0589, 0.0047, 0.0)["agree_wrong"]
    hi = em.two_rater(0.0866, 0.0589, 0.0047, 0.25)["agree_wrong"]
    assert hi > lo > 0
    assert math.isnan(em.two_rater(0.0866, 0.0589, 0.0047, 0.99)["agree_wrong"])
    r = em.rho_max(0.0866, 0.0589, 0.0047)
    assert 0.5 < r < 0.9
    assert em.rho_min(0.0866, 0.0589, 0.0047) == 0.0
    assert em.rho_min(0.09, 0.05, 0.02) > 0


def test_rho_for_error_monotone():
    x, y, w = 0.0866, 0.0589, 0.0047
    base = em.two_rater(x, y, w, 0.0)
    assert em.rho_for_error(x, y, w, 0.01) == 0.0
    r = em.rho_for_error(x, y, w, 0.10)
    t = em.two_rater(x, y, w, r)
    assert (t["a"] + t["b"]) / 2 == pytest.approx(0.10, abs=1e-6)
    assert (base["a"] + base["b"]) / 2 < 0.10


def test_residual_and_chain():
    assert em.residual(0.0, 0.9) == 0.0
    assert em.residual(0.5, 0.0) == pytest.approx(0.5)
    assert em.residual(0.5, 0.9) == pytest.approx(0.05 / 0.55)
    assert em.combine_se([0.9, 0.5]) == pytest.approx(0.95)
    assert em.combine_se([]) == 0.0
    assert em.raw_from_detected(0.09, 0.9) == pytest.approx(0.1)
    assert em.raw_from_detected(0.95, 0.5) == 1.0
    assert em.raw_from_detected(0.2, 0.0) == 0.2


def test_uncertainty_helpers():
    assert em.rectangular_u(math.sqrt(3)) == pytest.approx(1.0)
    assert em.combined_u([3, 4]) == pytest.approx(5.0)


def test_rogan_gladen_inverts_misclassification():
    true, se, sp = 0.30, 0.95, 0.98
    obs = true * se + (1 - true) * (1 - sp)
    assert em.rogan_gladen(obs, se, sp) == pytest.approx(true)
    with pytest.raises(ValueError):
        em.rogan_gladen(0.3, 0.4, 0.5)


def test_matrix_correct_matches_rogan_gladen_for_two_classes():
    se, sp, true = 0.9, 0.97, [0.4, 0.6]
    m = [[se, 1 - se], [1 - sp, sp]]           # m[i][j] = P(observed j | true i)
    obs = [sum(true[i] * m[i][j] for i in range(2)) for j in range(2)]
    got = em.matrix_correct(obs, m)
    assert got == pytest.approx(true)
    assert got[0] == pytest.approx(em.rogan_gladen(obs[0], se, sp))


def test_solve_three_by_three_and_singular():
    x = em.solve([[2, 1, 0], [1, 3, 1], [0, 1, 4]], [3, 9.5, 14])
    assert x == pytest.approx([0.5, 2.0, 3.0])
    with pytest.raises(ValueError):
        em.solve([[1, 2], [2, 4]], [1, 2])


def test_beta_jeffreys_is_deterministic_with_a_seed():
    a = [em.beta_jeffreys(random.Random(7), 3, 40) for _ in range(3)]
    b = [em.beta_jeffreys(random.Random(7), 3, 40) for _ in range(3)]
    assert a == b
    draws = [em.beta_jeffreys(random.Random(i), 3, 40) for i in range(2000)]
    assert sum(draws) / len(draws) == pytest.approx(3.5 / 41, abs=0.01)


def test_band_group_class_and_strata():
    assert em.band(2_000_000) == "B1 >=1M"
    assert em.band(10_000) == "B2 10k-1M"
    assert em.band(9_999) == "B3 <10k"
    assert em.group_of("cncf-gitdm-single") == "G3 cncf-gitdm single"
    assert em.group_of("patch") == "G1 gitdm curated"
    assert em.group_of(None) == "G0 none"
    assert em.group_of("something-new") == "G11 other"
    assert em.kclass("free-provider") == "free-provider"
    assert em.kclass("company") == "organisation"
    counts = {("G1", "B1", "organisation"): {"n": 3}, ("G1", "B1", "*"): {"n": 12}, ("G1", "all", "*"): {"n": 99}}
    assert em.stratum_key(counts, "G1", "B1", "organisation") == ("G1", "B1", "*")
    assert em.stratum_key(counts, "G1", "B3", "organisation") == ("G1", "all", "*")


def test_change_state_and_origin():
    assert em.change_state(None, None, None) == "none"
    assert em.change_state(None, None, "acme") == "added"
    assert em.change_state("acme", "acme", None) == "dropped"
    assert em.change_state("old", "acme", "acme") == "same"      # a merge is not a change
    assert em.change_state("acme", "acme", "independent") == "moved"
    assert em.origin_of("moved", "review-7#link=x", "gitdm") == "r7"
    assert em.origin_of("moved", "review-4d#link=x", "gitdm") == "r4d"
    assert em.origin_of("added", "review:ai/part-9.csv:conflict:1", "x") == "r5"
    assert em.origin_of("added", "review:ai/part-8.csv:conflict:1", "x") == "AB"
    assert em.origin_of("moved", "manual/v4_new_orgs.csv", "x") == "user"
    assert em.origin_of("moved", "ctp-affiliation-merged", "gitdm") == "AB"
    assert em.origin_of("same", "ctp-affiliation-merged", "gitdm") == "source"


def test_transition():
    c = Counter({(True, True): 1, (True, False): 2, (True, None): 1})
    assert em.transition(c, True) == (0.25, 0.5, 0.25)
    assert em.transition(c, False) == (0.5, 0.5, 0.0)


def test_md_table_and_key_hash_hold_no_domain():
    t = em.md_table([{"a": 1, "b": 0.5}, {"a": 2000, "c": "x"}])
    assert "| a | b | c |" in t and "2,000" in t
    h = em.key_hash("example.org")
    assert len(h) == 16 and "example" not in h
    assert em.key_hash("example.org") == h


def test_write_csv_union_of_columns(tmp_path):
    p = tmp_path / "t.csv"
    em.write_csv(p, [{"a": 1}, {"a": 2, "b": 0.123456789}])
    text = p.read_text().splitlines()
    assert text[0] == "a,b"
    assert text[2] == "2,0.12345679"


# --- helpers of the namespace column and of the side study --------------------------------------

def test_uniform_and_product_moments():
    assert em.uniform_moments(0, 1) == pytest.approx((0.5, 1 / 12))
    assert em.uniform_moments(0.6, 1) == pytest.approx((0.8, 0.16 / 12))
    m, v = em.product_moments(*em.uniform_moments(0, 1), *em.uniform_moments(0, 1))
    assert m == pytest.approx(0.25) and v == pytest.approx(1 / 9 - 1 / 16)
    rng = random.Random(3)
    xs = [rng.uniform(0, 1) * rng.uniform(0.5, 1) for _ in range(200_000)]
    m, v = em.product_moments(*em.uniform_moments(0, 1), *em.uniform_moments(0.5, 1))
    mean = sum(xs) / len(xs)
    assert mean == pytest.approx(m, abs=2e-3)
    assert sum((x - mean) ** 2 for x in xs) / len(xs) == pytest.approx(v, rel=2e-2)


def test_namespace_review_candidates_rules():
    base = {"evidence": "roster", "tokens": 10}
    per = [
        dict(base, project="p1", org="o1", relation="owns", owner_kind="company", own_share=0.0, changed=False),
        dict(base, project="p2", org="o2", relation="owns", owner_kind="company", own_share=0.3, changed=True),
        dict(base, project="p3", org="o3", relation="owns", owner_kind="foundation-or-other", own_share=0.0,
             changed=True),
        dict(base, project="p4", org="o4", relation="owns", owner_kind="foundation-or-other", own_share=0.0,
             changed=False),
        dict(base, project="p5", org="o5", relation="candidate", owner_kind="company", own_share=0.10),
        dict(base, project="p6", org="o6", relation="candidate", owner_kind="company", own_share=0.0999),
        dict(base, project="p7", org="o7", relation="participates", owner_kind="company", own_share=0.9),
    ]
    out = em.namespace_review_candidates(per)
    assert [r["project"] for r in out] == ["p1", "p3", "p5"]
    assert {r["relation"] for r in out} == {"owns", "candidate"}
    assert set(out[0]) == {"project", "organisation_id", "relation", "evidence", "token_share", "reason"}


# --- user decisions of 2026-10-19 ------------------------------------------------------------

def _dec(item, utc, **answer):
    return dict({"item_id": item, "decided_utc": utc}, **answer)


def test_reversal_count_uses_the_answer_of_each_decided_utc():
    snap1 = [_dec("company:a", "t1", action="accept"), _dec("company:b", "t1", action="accept"),
             _dec("company:w", "t1", action="accept")]
    final = [_dec("company:a", "t1", action="accept"), _dec("company:b", "t2", action="edit", merge_into="c")]
    chat = [_dec("company:a", "t3", action="edit", parent_company_id="p")]
    dom = [{"link_id": "domain:o:example.org", "action": "move", "move_to": "free-provider", "decided_utc": "t4"}]
    rec = em.reversal_records([("item", snap1), ("item", final), ("item", chat), ("domain", dom)])
    final_items = {"item:company:a", "item:company:b", "domain:domain:o:example.org"}
    c = em.count_reversals(rec, final_items)
    # a: accept then a parent edit; b: accept then a merge; w: taken back (not a reversal)
    assert c == {"k": 2, "n": 4, "withdrawn": 1}
    # the same row again in a later snapshot is one decision, not two
    rec2 = em.reversal_records([("item", snap1), ("item", snap1)])
    assert em.count_reversals(rec2)["k"] == 0


def test_reversal_term_rate_and_rule_of_three():
    t = em.reversal_term(3, 196)
    assert t["r"] == pytest.approx(3 / 196)
    assert t["u"] == pytest.approx(math.sqrt((3 / 196) * (1 - 3 / 196) / 196))
    z = em.reversal_term(0, 300)
    assert z["hi"] == pytest.approx(0.01) and z["r"] == pytest.approx(0.005)
    assert z["u"] == pytest.approx(0.01 / math.sqrt(12))
    assert "rule of three" in z["basis"]
    assert em.reversal_term(0, 0)["r"] == 0.0


def test_reversal_draw_has_the_mean_and_sd_of_the_term():
    t = em.reversal_term(3, 196)
    rng = random.Random(5)
    xs = [em.reversal_draw(rng, t) for _ in range(100_000)]
    mean = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
    assert mean == pytest.approx(t["r"], rel=2e-2)
    assert sd == pytest.approx(t["u"], rel=3e-2)
    z = em.reversal_term(0, 300)
    assert all(0 <= em.reversal_draw(rng, z) <= z["hi"] for _ in range(1000))
    a = [em.reversal_draw(random.Random(9), t) for _ in range(3)]
    b = [em.reversal_draw(random.Random(9), t) for _ in range(3)]
    assert a == b


def test_error_stratum_matches_the_audit_cells():
    assert em.error_stratum("source", "B1 >=1M", "company", "exact") == "source/B1 >=1M/organisation/exact"
    assert em.error_stratum("r4f", "B3 <10k", "independent", "suffix") == "r4d/r4f/B3 <10k/independent/suffix"
    assert em.error_stratum("r6", "B2 10k-1M", "free-provider", None) == "r5/r6/B2 10k-1M/free-provider/"


def test_p_error_rows_one_per_link_with_a_hashed_key():
    central = {"se_mid": 0.9, "se_lo": 0.9, "se_hi": 0.9, "rho_hi": 0.0, "ab_conflict": {"x": 0.05, "y": 0.05,
               "w": 0.0, "n": 100}, "ab_company": {"x": 0.05, "y": 0.05, "w": 0.0, "n": 100}, "user_cal": (1, 99),
               "phi_kind": (1, 3), "q4": {"k": 0, "n": 10}, "q7_hi": 0.1, "user_rev": em.reversal_term(1, 50),
               "suffix": {"k": 1, "n": 30}, "detected": {}, "pooled": (5, 100), "pooled_nbar": 1.0,
               "f_prop": 0.1, "f_lo": 0.0, "f_hi": 0.2, "tail_lo": 0.0, "tail_hi": 0.2, "o_prop": 0.12}
    P = em.Params(central)
    assert P.q_user == pytest.approx(0.02)
    assert P.o_unmatched == pytest.approx(0.12) and P.o_tail == pytest.approx(0.12)
    base = {"band": "B3 <10k", "match41": "exact", "later": [], "skey": None}
    chain = [dict(base, domain="b.example.org", o41="o1", kind41="company", origin="user"),
             dict(base, domain="a.example.org", o41="o2", kind41="independent", origin="r7", match41="suffix"),
             dict(base, domain="c.example.org", o41=None, kind41=None, origin="dropped")]
    rows = em.p_error_rows(chain, P, {})
    assert len(rows) == 2 and rows == sorted(rows)
    by = {r[1]: r for r in rows}
    assert by["user/B3 <10k/organisation/exact"][2] == pytest.approx(0.02)
    assert by["r7/B3 <10k/independent/suffix"][2] == pytest.approx(1 - (1 - 0.05) * (1 - 1.5 / 31))
    assert all("example" not in r[0] and len(r[0]) == 16 for r in rows)


def test_unmatched_kinds_shares_and_classes():
    unm = {"proposed": 100, "kind:company": 10, "kind_n:company": 2, "kind:(blank)": 50, "kind_n:(blank)": 5,
           "kind:independent": 30, "kind_n:independent": 3, "kind:academic": 10, "kind_n:academic": 1}
    rows = em.unmatched_kinds(unm)
    assert [r["proposed_kind"] for r in rows][:2] == ["(blank)", "independent"]     # by tokens
    cls = {r["proposed_kind"]: r["class"] for r in rows}
    assert cls == {"(blank)": "no answer", "independent": "pseudo", "academic": "other organisation",
                   "company": "company"}
    assert sum(r["share_of_proposed_pct"] for r in rows) == pytest.approx(100.0)


def test_pseudo_ids_have_no_kind_error():
    """independent, free-provider and unknown name no organisation: their kind cannot be wrong
    (user decision of 2026-10-19). A real organisation keeps the kind error of its review path."""
    class P:
        q_user, kind_agreed, kind_single = 0.015, 0.002, 0.03
    for org in ("independent", "free-provider", "unknown"):
        for path in ("user-or-curated", "agreed (A=B)", "unreviewed"):
            assert em.kind_error(org, org, path, P) == 0.0
    assert em.kind_error("acme", "company", "user-or-curated", P) == 0.015
    assert em.kind_error("acme", "company", "agreed (A=B)", P) == 0.002
    assert em.kind_error("acme", "company", "single AI review", P) == 0.03
    assert set(em.NO_KIND_ERROR) == {"independent", "free-provider", "unknown"}


def test_clopper_pearson_known_values():
    lo, hi = em.clopper_pearson(5, 20)
    assert abs(lo - 0.0866) < 1e-4 and abs(hi - 0.4910) < 1e-4
    assert em.clopper_pearson(0, 62)[0] == 0.0 and abs(em.clopper_pearson(0, 62)[1] - (1 - 0.025 ** (1 / 62))) < 1e-9
    assert em.clopper_pearson(3, 3)[1] == 1.0 and em.clopper_pearson(0, 0) == (0.0, 1.0)


def test_ai_round_check_counts_the_check_sample(tmp_path):
    """Round 9: only the check items count; unsure is left out of n; a naming-only wrong answer
    does not count after the relation rename (the user, 2026-10-20)."""
    a = tmp_path / "review/audit-v44"
    (a / "data").mkdir(parents=True)
    items = [{"item_id": "R1", "class": "decide", "title": "x"},
             {"item_id": "R2", "class": "check", "title": "github.com/napari"},
             {"item_id": "R3", "class": "check", "title": "a.org"},
             {"item_id": "R4", "class": "check", "title": "b.org"},
             {"item_id": "R5", "class": "check", "title": "c.org"}]
    (a / "data/items.json").write_text(json.dumps(items))
    (a / "answers.csv").write_text("item_id,type,title,verdict,note,answered_utc,items_sha256\n"
                                   "R1,t,x,wrong,,,\nR2,t,n,wrong,,,\nR3,t,a,right,,,\nR4,t,b,right,,,\nR5,t,c,unsure,,,\n")
    r = em.ai_round_check(tmp_path)
    assert (r["right"], r["wrong"], r["unsure"], r["n"], r["k"], r["k_rule"]) == (2, 1, 1, 3, 1, 0)
    assert r["rule3"] == 1.0 and r["cp"] == em.clopper_pearson(1, 3)
    assert em.ai_round_check(tmp_path / "none")["n"] == 0


# --------------------------------------------------------------------------------------------
# The evaluated layer and the later layers (v4.2 user audited, v4.4 AI round 9), 2026-10-20
# --------------------------------------------------------------------------------------------

def _central(**kw):
    c = {"se_mid": 0.9, "se_lo": 0.9, "se_hi": 0.9, "rho_hi": 0.0, "ab_conflict": {"x": 0.05, "y": 0.05,
         "w": 0.0, "n": 100}, "ab_company": {"x": 0.05, "y": 0.05, "w": 0.0, "n": 100}, "user_cal": (1, 99),
         "phi_kind": (1, 3), "q4": {"k": 0, "n": 10}, "q7_hi": 0.1, "user_rev": em.reversal_term(1, 50),
         "suffix": {"k": 1, "n": 30}, "detected": {}, "pooled": (5, 100), "pooled_nbar": 1.0,
         "f_prop": 0.1, "f_lo": 0.0, "f_hi": 0.2, "tail_lo": 0.0, "tail_hi": 0.2, "o_prop": 0.12}
    c.update(kw)
    return c


R9_CHECK = {"n": 62, "k": 1, "k_rule": 0}


def test_origin_of_the_later_layers():
    assert em.origin_of("same", "manual/v44_domains.csv#domain=a.example.org", None) == "r9"
    assert em.origin_of("moved", "manual/v42_domains.csv#domain=a.example.org", None) == "user"
    assert em.origin_of("same", "manual/v4_new_orgs.csv#x", None) == "user"
    assert em.AFTER["r9"] == [] and em.AFTER["user"] == []


def _r41(**kw):
    return dict({"o41": "old", "origin": "r7", "later": ["r8"]}, **kw)


def test_current_origin_keeps_the_v41_origin_of_the_same_row():
    a = dict(md="a.example.org", md41="a.example.org", ptr41="p", merge_cur={}, m42=set(), m44=set())
    assert em.current_origin("same", "p", "gitdm", "old", _r41(), **a) == ("r7", ["r8"], False, "same row as v4.1")
    # A v4.4 merge on the merge path of the v4.1 id adds the round 9 term.
    m = {"old": "mid", "mid": "new"}
    assert em.current_origin("same", "p", "gitdm", "new", _r41(), **dict(a, merge_cur=m, m44={"mid"})) == \
        ("r7", ["r8"], True, "same row as v4.1, v4.4 merge (+ q_r9)")
    # A v4.2 merge adds nothing: the user audited it.
    assert em.current_origin("same", "p", "gitdm", "new", _r41(), **dict(a, merge_cur=m, m42={"old"})) == \
        ("r7", ["r8"], False, "same row as v4.1, v4.2 merge")
    # The same row with another id (the pseudo id of an old file): the origin stays, no term.
    assert em.current_origin("moved", "p", "x", "pre-git-import", _r41(o41="project"), **a) == \
        ("r7", ["r8"], False, "same row as v4.1, other id change")


def test_current_origin_of_rows_of_a_later_layer_and_of_new_rows():
    a = dict(md="a.example.org", md41="a.example.org", ptr41="p", merge_cur={}, m42=set(), m44=set())
    assert em.current_origin("moved", "manual/v44_domains.csv#d", None, "new", _r41(), **a) == \
        ("r9", None, False, "v4.4 row (round 9)")
    assert em.current_origin("added", "manual/v42_domains.csv#d", None, "infn", None,
                             **dict(a, md41=None, ptr41=None)) == ("user", None, False, "v4.2 row (user audited)")
    assert em.current_origin("dropped", None, None, None, _r41(), **a)[0] == "dropped"
    # Another matched row: the general rule (origin_of), and the checks come from AFTER.
    assert em.current_origin("moved", "review-7#x", "review-7", "o", _r41(), **dict(a, md="b.example.org")) == \
        ("r7", None, False, "other new or changed row")
    assert set(em.LAYER_RULES) >= {"same row as v4.1", "v4.4 row (round 9)", "dropped"}


def test_merge_walk_and_merge_ids(tmp_path):
    assert em.merge_walk("a", {"a": "b", "b": "c"}) == ["a", "b", "c"]
    assert em.merge_walk("a", {"a": "b", "b": "a"}) == ["a", "b"]
    assert em.merge_walk(None, {}) == [None]
    f = tmp_path / "v44_merges.csv"
    f.write_text("merge_id,into_id,kept_name,decided_by,reason,source_url\nx,y,,claude-main,r,u\n")
    assert em.merge_ids(f) == {"x"} and em.merge_ids(tmp_path / "none.csv") == set()


def test_q_r9_from_the_check_sample_on_its_own_stream():
    c = _central(ai_check=R9_CHECK)
    P = em.Params(c)
    assert P.q_r9 == pytest.approx(0.5 / 63)
    assert P.kind_r9 == pytest.approx(P.q_r9 * P.phi)
    # No check sample: the error of one AI answer.
    P0 = em.Params(_central())
    assert P0.q_r9 == P0.q_single
    # The round 9 draw has its own stream, so the other draws stay the same.
    a = em.Params(c, random.Random(5))
    b = em.Params(c, random.Random(5), random.Random(14))
    other = lambda p: {k: v for k, v in vars(p).items() if k not in ("q_r9", "kind_r9")}  # noqa: E731
    assert other(a) == other(b)
    assert b.q_r9 == em.beta_jeffreys(random.Random(14), 0, 62)


def test_link_p_of_round_9_and_the_merge_term():
    P = em.Params(_central(ai_check=R9_CHECK))
    base = {"band": "B3 <10k", "match41": "exact", "later": [], "skey": None}
    assert em.link_p(dict(base, origin="r9"), P, {}) == pytest.approx(P.q_r9)
    u = em.link_p(dict(base, origin="user"), P, {})
    assert u == pytest.approx(P.q_user)
    assert em.link_p(dict(base, origin="user", r9_merge=True), P, {}) == pytest.approx(1 - (1 - u) * (1 - P.q_r9))
    s = em.link_p(dict(base, origin="r9", match41="suffix", r9_merge=True), P, {})
    assert s == pytest.approx(1 - (1 - P.q_r9) * (1 - P.p_suffix) * (1 - P.q_r9))
    assert em.error_stratum("r9", "B3 <10k", "company", "exact") == "r9/B3 <10k/organisation/exact"


def _q(con):
    return lambda sql, *a: con.execute(sql, *a).fetchall()


def test_org_paths_of_the_later_layers():
    import duckdb
    from types import SimpleNamespace
    con = duckdb.connect()
    con.execute("CREATE SCHEMA cur")
    con.execute("CREATE TABLE cur.company (company_id VARCHAR, reviewer VARCHAR, review_status VARCHAR, "
                "review_date DATE)")
    con.execute("""INSERT INTO cur.company VALUES ('a', 'claude-main', 'accepted', '2026-10-20'),
                   ('b', 'claude-main', 'accepted', '2026-10-19'), ('c', 'claude-main', 'accepted', '2026-10-19'),
                   ('d', 'claude-main', 'accepted', '2026-10-18'), ('e', 'user', 'accepted', '2026-10-17'),
                   ('f', NULL, 'accepted', NULL)""")
    d = SimpleNamespace(q=_q(con), compare={}, r42={"b", "d"})
    path = em.org_paths(d)
    assert path["a"] == em.R9_PATH                 # round 9 set the row
    assert path["b"] == "user-or-curated"          # v4.2 changed the row; the user audited it
    assert path["c"] == "single AI review"         # the same stamp, but not a v4.2 row (v4.3)
    assert path["d"] == "single AI review"         # a v4.2 id with an older stamp: not changed by v4.2
    assert path["e"] == "user-or-curated" and path["f"] == "unreviewed"
    assert path["independent"] == "user-or-curated"
    P = em.Params(_central(ai_check=R9_CHECK))
    assert em.kind_error("a", "company", path["a"], P) == pytest.approx(P.kind_r9)
    assert em.kind_error("independent", "independent", em.R9_PATH, P) == 0.0


def _layer_fixture(tmp_path):
    """A tiny evaluated layer: new link files, an old v3 project file and a database."""
    import duckdb
    new, old = tmp_path / "links-new", tmp_path / "links-old"
    new.mkdir()
    old.mkdir()
    db = tmp_path / "cur.duckdb"
    w = duckdb.connect(str(db))
    w.execute("CREATE TABLE company (company_id VARCHAR, kind VARCHAR, parent_company_id VARCHAR, "
              "review_status VARCHAR, reviewer VARCHAR, review_date DATE, status VARCHAR)")
    w.execute("""INSERT INTO company VALUES ('acme', 'company', NULL, 'accepted', 'user', NULL, 'active'),
                 ('fnd', 'foundation', NULL, 'accepted', 'user', NULL, 'active'),
                 ('host', 'company', NULL, 'accepted', 'user', NULL, 'active')""")
    w.execute("CREATE TABLE company_namespace (host VARCHAR, namespace VARCHAR, company_id VARCHAR, relation VARCHAR, "
              "evidence VARCHAR, verified BOOLEAN, source_pointer VARCHAR)")
    w.execute("""INSERT INTO company_namespace VALUES
                 ('github.com', 'acme', 'acme', 'owns', 'verified-domain', true, 'manual/v43_namespaces.csv#x'),
                 ('github.com', 'acme', 'fnd', 'participates', 'roster', false, 'roster-x'),
                 ('github.com', 'tool', 'fnd', 'participates', 'roster', false, 'roster-x'),
                 ('github.com', 'tool', 'host', 'hosted_by', 'company-page', true, 'manual/v44_namespaces.csv#y')""")
    w.close()
    c = duckdb.connect()
    c.execute(f"""COPY (SELECT * FROM (VALUES ('a.example.org', 'acme', 'company', 'exact', 'a.example.org', 'high', 's'),
                  ('b.example.org', 'independent', 'independent', 'exact', 'b.example.org', 'high', 's'))
                  t(domain, firm_based_on_domain, organisation_kind, match, matched_domain, confidence, source))
                  TO '{new / 'domain_links.parquet'}' (FORMAT parquet)""")
    c.execute(f"""COPY (SELECT * FROM (VALUES ('github.com/acme/x', 'github.com', 'acme', 'acme', true, 'owner'),
                  ('github.com/tool/y', 'github.com', 'tool', NULL, false, 'none'))
                  t(project, host, namespace, firm_based_on_namespace, project_enterprise_driven,
                    project_enterprise_basis)) TO '{new / 'project_links.parquet'}' (FORMAT parquet)""")
    c.execute(f"""COPY (SELECT * FROM (VALUES ('github.com/acme/x', 'github.com', 'acme', 'fnd', 'participates', 'roster',
                  false, 'none'), ('github.com/tool/y', 'github.com', 'tool', NULL, NULL, NULL, false, 'none'))
                  t(project, host, namespace, namespace_company_id, namespace_company_relation,
                    namespace_company_evidence, project_enterprise_driven, project_enterprise_basis))
                  TO '{old / 'project_links.parquet'}' (FORMAT parquet)""")
    c.execute("""CREATE TABLE tok_pd AS SELECT * FROM (VALUES ('github.com__acme__x', 'a.example.org', 30::BIGINT),
                 ('github.com__acme__x', 'b.example.org', 10::BIGINT), ('github.com__tool__y', 'b.example.org', 5::BIGINT))
                 t(proj, domain, tokens)""")
    c.execute("CREATE VIEW tok_pd_ev AS SELECT * FROM tok_pd")     # the evaluated layer (Data, model v4.6)
    c.execute("CREATE TABLE mmc (old VARCHAR, new VARCHAR)")
    em.attach_ro(c, db, "cur")
    em.domain_link_table(c, "lc", new)
    em.project_link_table(c, "pc", new, "cur")
    em.project_link_table(c, "p3", old)
    return c, db


def test_a_link_with_no_tokens_gets_a_chain_row_and_a_p_error_row(tmp_path):
    c, _ = _layer_fixture(tmp_path)
    # The token tables of the model know a.example.org only; the link folder also links b.example.org
    # (a domain that only the final write counts).
    c.execute("CREATE TABLE tok_ev AS SELECT * FROM (VALUES ('a.example.org', 30::BIGINT), ('', 7::BIGINT)) "
              "t(domain, tokens)")
    assert em.chain_domain_table(c) == 1
    assert c.execute("SELECT domain, tokens FROM tok_chain ORDER BY 1").fetchall() == [
        ("", 7), ("a.example.org", 30), ("b.example.org", 0)]
    # The row of 0 tokens has the band of the smallest links and gets its p_error by the same rule.
    assert em.band(0) == "B3 <10k"
    P = em.Params(_central())
    base = {"band": em.band(0), "match41": "exact", "later": [], "skey": None}
    chain = [dict(base, domain="a.example.org", o41="acme", kind41="company", origin="user"),
             dict(base, domain="b.example.org", o41="independent", kind41="independent", origin="user")]
    n_links = c.execute("SELECT count(DISTINCT domain) FROM lc").fetchone()[0]
    assert em.write_p_error(tmp_path / "p.parquet", chain, P, {}, n_links) == 2


def test_p_error_stops_when_a_link_has_no_row(tmp_path):
    em.check_p_error_rows(16119, 16119)
    with pytest.raises(SystemExit, match="16116 rows for 16119 links"):
        em.check_p_error_rows(16116, 16119)
    P = em.Params(_central())
    chain = [{"band": "B3 <10k", "match41": "exact", "later": [], "skey": None, "domain": "a.example.org",
              "o41": "acme", "kind41": "company", "origin": "user"}]
    with pytest.raises(SystemExit):
        em.write_p_error(tmp_path / "p.parquet", chain, P, {}, 2)
    assert not (tmp_path / "p.parquet").exists()


def test_the_reader_of_the_new_link_columns(tmp_path):
    c, db = _layer_fixture(tmp_path)
    assert c.execute("SELECT domain, org, kind, match, md FROM lc ORDER BY 1").fetchall() == [
        ("a.example.org", "acme", "company", "exact", "a.example.org"),
        ("b.example.org", "independent", "independent", "exact", "b.example.org")]
    # The best namespace row comes from the database; hosted_by never counts.
    assert c.execute("SELECT project, firm_based_on_namespace, namespace_organisation_id, namespace_relation, "
                     "namespace_evidence FROM pc ORDER BY 1").fetchall() == [
        ("github.com/acme/x", "acme", "acme", "owns", "verified-domain"),
        ("github.com/tool/y", None, "fnd", "participates", "roster")]
    assert c.execute("SELECT namespace_organisation_id, namespace_relation FROM p3 ORDER BY project").fetchall() == [
        ("fnd", "participates"), (None, None)]
    # A file that is already attached gets a schema of views.
    em.attach_ro(c, db, "again")
    assert c.execute("SELECT count(*) FROM again.company").fetchone()[0] == 3


def test_namespace_model_reads_the_evaluated_layer(tmp_path):
    from types import SimpleNamespace
    c, _ = _layer_fixture(tmp_path)
    d = SimpleNamespace(q=_q(c))
    rows, ev_rows, ns = em.namespace_model(d, {"acme": "user-or-curated"})
    per = {p["project"]: p for p in ns["per"]}
    assert per["github.com/acme/x"]["relation"] == "owns" and per["github.com/acme/x"]["own_share"] == 0.75
    assert per["github.com/acme/x"]["changed"]           # v3 had fnd, participates
    assert per["github.com/acme/x"]["layer"] == "v4.3 namespace rework"
    assert per["github.com/tool/y"]["layer"] == "v4.1 or earlier"   # not an owns row
    assert per["github.com/tool/y"]["relation"] == "participates" and per["github.com/tool/y"]["own_share"] == 0.0
    assert {r["relation"] for r in ev_rows} == {"owns", "participates", "hosted_by"}
    owns = [r for r in rows if r["relation"] == "owns"]
    assert owns[0]["owner_kind"] == "company" and owns[0]["changed_v3_v41"] == 1
    review = em.namespace_review_candidates(ns["per"], "v4.5")
    assert all("v4.1" not in r["reason"] for r in review)


def test_layer_version_label(tmp_path):
    (tmp_path / "links.json").write_text(json.dumps({"organisations_version": "v4.5"}))
    assert em.layer_version(Path("x/companies.v4.duckdb"), tmp_path) == "v4.5"
    assert em.layer_version(Path("x/companies.v4.duckdb"), tmp_path / "none") == "v4.1"
    assert em.layer_version(Path("x/companies.v4.5.duckdb"), tmp_path / "none") == "v4.5"
    assert em.layer_version(Path("x/companies.duckdb"), tmp_path / "none") == "v3"


def test_namespace_layer_of_an_owns_row():
    assert em.namespace_layer("manual/v43_namespaces.csv#ns=a") == "v4.3 namespace rework"
    assert em.namespace_layer("manual/v44_namespaces.csv#ns=a") == "v4.4 round 9"
    assert em.namespace_layer("manual/v45_namespaces.csv#ns=a") == "v4.5 user rule"
    assert em.namespace_layer("manual/v46_namespaces.csv#ns=a") == "v4.6 user rule"
    assert em.namespace_layer("roster-asf") == em.namespace_layer(None) == "v4.1 or earlier"


# --------------------------------------------------------------------------------------------
# Model v4.7 (2026-10-25): both layers, the later AI layers, phi on the user path, the audit values
# --------------------------------------------------------------------------------------------

def _central47(**kw):
    c = dict(ai_check=R9_CHECK, ai_layers={"r10": {"k": 1, "n": 40}}, later_pool={"k": 1, "n": 40},
             phi_user=True, audit={"D11": (0, 111)})
    c.update(kw)
    return _central(**c)


def test_later_layer_and_later_origin():
    assert em.later_layer("manual/v47_domains.csv#domain=a.example.org") == ("v4.7", "r10")
    assert em.later_layer("review/v47_domains.private.csv#x") == ("v4.7", "r10")
    assert em.later_layer("manual/v48_namespaces.csv#x") == ("v4.8", "r11")
    for ptr in ("manual/v44_domains.csv#x", "manual/v42_new_orgs.csv", "manual/v4_new_orgs.csv#x", "", None,
                "review-decisions.csv"):
        assert em.later_layer(ptr) is None
    assert em.later_origin("manual/v47_domains.csv#x", {"a.example.org"}, set()) == ("r10", "v4.7 row (round 10)")
    o, rule = em.later_origin("manual/v47_domains.csv#x", {"a.example.org", None}, {"a.example.org"})
    assert o == "user" and "could not decide" in rule
    assert em.later_origin("manual/v44_domains.csv#x", {"a.example.org"}, {"a.example.org"}) is None
    assert em.namespace_layer("manual/v47_namespaces.csv#x") == "v4.7 round 10"
    assert em.namespace_layer("manual/v46_namespaces.csv#x") == "v4.6 user rule"


def test_params_of_model_v47_use_their_own_stream():
    c46, c47 = _central(ai_check=R9_CHECK), _central47()
    P = em.Params(c47)
    assert P.q_layer["r10"] == pytest.approx(1.5 / 41)
    assert P.q_later == P.q_layer["r10"] and P.kind_later == pytest.approx(P.q_later * P.phi)
    assert P.kind_user == pytest.approx(P.q_user * P.phi)
    assert P.audit["D11"] == pytest.approx(0.5 / 112)
    # No check answer yet: q_r9.
    P0 = em.Params(_central47(ai_layers={"r10": {"k": 0, "n": 0}}))
    assert P0.q_layer["r10"] == P0.q_r9
    # Model v4.6: none of the new attributes, so the v4.6 outputs stay the same.
    assert not any(hasattr(em.Params(c46), a) for a in ("q_layer", "q_later", "kind_user", "audit"))
    # The draws of model v4.7 come from rngx: the other draws are those of model v4.6.
    a = em.Params(c46, random.Random(5), random.Random(14))
    b = em.Params(c47, random.Random(5), random.Random(14), random.Random(15))
    new = ("q_layer", "q_later", "kind_later", "kind_user", "audit")
    assert {k: v for k, v in vars(b).items() if k not in new} == vars(a)
    r = random.Random(15)
    assert b.q_layer["r10"] == em.beta_jeffreys(r, 1, 40)


def test_kind_error_of_the_user_path_and_of_the_later_rounds():
    P46, P47 = em.Params(_central(ai_check=R9_CHECK)), em.Params(_central47())
    assert em.kind_error("acme", "company", "user-or-curated", P46) == pytest.approx(P46.q_user)
    assert em.kind_error("acme", "company", "user-or-curated", P47) == pytest.approx(P47.q_user * P47.phi)
    assert em.kind_error("acme", "company", em.LATER_PATH, P47) == pytest.approx(P47.q_later * P47.phi)
    assert em.kind_error("independent", "independent", em.LATER_PATH, P47) == 0.0


def test_link_p_of_a_later_layer_and_the_audit_factor():
    P = em.Params(_central47())
    base = {"band": "B1 >=1M", "match41": "exact", "later": [], "skey": None}
    assert em.link_p(dict(base, origin="r10"), P, {}) == pytest.approx(P.q_layer["r10"])
    # Three links of stratum D11 with model errors 1:2:3 and one link outside: the factor makes the
    # mean unit error of D11 the measured value and keeps the ratios.
    links = [dict(base, origin=o, astratum=h) for o, h in (("r9", "D11"), ("r10", "D11"), ("user", "D11"), ("r9", None))]
    pm = [em.link_p(r, P, {}) for r in links]
    fac = em.audit_factors(list(zip(links, pm)), P)
    assert set(fac) == {"D11"}
    used = [min(1.0, p * fac["D11"]) if r["astratum"] else p for r, p in zip(links, pm)]
    assert sum(used[:3]) / 3 == pytest.approx(P.audit["D11"])
    assert used[1] / used[0] == pytest.approx(pm[1] / pm[0]) and used[3] == pm[3]
    P.audit_fac = fac
    assert [em.link_p_used(r, P, {}) for r in links] == pytest.approx(used)
    # Model v4.6 (no audit): link_p_used is link_p.
    P46 = em.Params(_central(ai_check=R9_CHECK))
    assert em.audit_factors(list(zip(links, pm)), P46) == {}
    assert em.link_p_used(links[0], P46, {}) == em.link_p(links[0], P46, {})


def test_evaluate_uses_the_measured_value_of_a_stratum():
    P = em.Params(_central47(audit={"D11": (2, 100)}))
    kc = {"link": Counter(), "org": Counter()}
    row = {"o41": "acme", "kind41": "company", "group41": "G1 gitdm curated", "band": "B1 >=1M", "match41": "exact",
           "later": [], "skey": None}
    chain = [dict(row, domain="a", tokens=100, origin="r9", astratum="D11"),
             dict(row, domain="b", tokens=300, origin="r9", astratum="D11"),
             dict(row, domain="c", tokens=600, origin="r9")]
    e = em.evaluate(chain, P, {}, {"acme": "user-or-curated"}, kc, {}, 1000)
    theta = 2.5 / 101
    assert e["E_all"] == pytest.approx((theta * 400 + P.q_r9 * 600) / 1000)
    assert e["err_tok_model"] == pytest.approx(P.q_r9 * 1000)
    a = e["per_astratum"]["D11"]
    assert a[0] == 2 and a[2] == 400 and a[4] == pytest.approx(theta * 400)


def test_beta_from_moments():
    a, b = em.beta_from_moments(0.1, 0.03)
    assert a / (a + b) == pytest.approx(0.1)
    assert (a * b / ((a + b) ** 2 * (a + b + 1))) ** 0.5 == pytest.approx(0.03)
    assert em.beta_from_moments(None, 0.1) is None and em.beta_from_moments(0.1, 0.0) is None
    assert em.beta_from_moments(0.5, 0.6) is None          # wider than any Beta


def test_add_db_links_follows_the_exact_rule_of_build_links(tmp_path):
    import duckdb
    db = tmp_path / "cur.duckdb"
    w = duckdb.connect(str(db))
    w.execute("CREATE TABLE company (company_id VARCHAR, kind VARCHAR, review_status VARCHAR)")
    w.execute("""INSERT INTO company VALUES ('acme', 'company', 'accepted'), ('old', 'company', 'rejected'),
                 ('independent', 'independent', 'accepted'), ('uni', 'academic', 'accepted')""")
    w.execute("CREATE TABLE company_domain (domain VARCHAR, company_id VARCHAR, source_pointer VARCHAR)")
    w.execute("""INSERT INTO company_domain VALUES ('a.example.org', 'acme', 'manual/v47_domains.csv#a'),
                 ('r.example.org', 'old', 'x'), ('p.example.org', 'independent', 'review/v47_x#p'),
                 ('cs.example.edu', 'acme', 'x'), ('u.example.edu', 'uni', 'x'), ('d.example.org', 'acme', 'x'),
                 ('l.example.org', 'acme', 'x')""")
    w.execute("CREATE TABLE company_domain_dropped (domain VARCHAR)")
    w.execute("INSERT INTO company_domain_dropped VALUES ('d.example.org')")
    w.close()
    c = duckdb.connect()
    em.attach_ro(c, db, "cur")
    c.execute("""CREATE TABLE tok_ev AS SELECT * FROM (VALUES ('a.example.org', 5::BIGINT), ('r.example.org', 5::BIGINT),
                 ('p.example.org', 5::BIGINT), ('cs.example.edu', 5::BIGINT), ('u.example.edu', 5::BIGINT),
                 ('d.example.org', 5::BIGINT), ('l.example.org', 5::BIGINT), ('', 5::BIGINT)) t(domain, tokens)""")
    c.execute("CREATE TABLE lc (domain VARCHAR, org VARCHAR, kind VARCHAR, match VARCHAR, md VARCHAR)")
    c.execute("INSERT INTO lc VALUES ('l.example.org', 'acme', 'company', 'exact', 'l.example.org')")
    added = em.add_db_links(c)
    assert sorted(added) == ["a.example.org", "p.example.org", "u.example.edu"]
    got = {d: (o, k) for d, o, k in c.execute("SELECT domain, org, kind FROM lc").fetchall()}
    assert got["a.example.org"] == ("acme", "company") and got["p.example.org"] == ("independent", "independent")
    assert got["u.example.edu"] == ("uni", "academic") and len(got) == 4


def test_later_org_paths_keep_the_v46_path_of_an_unchanged_organisation():
    import duckdb
    from types import SimpleNamespace
    con = duckdb.connect()
    for sch in ("cur", "prev"):
        con.execute(f"CREATE SCHEMA {sch}")
        con.execute(f"CREATE TABLE {sch}.company (company_id VARCHAR, kind VARCHAR, reviewer VARCHAR, "
                    "review_status VARCHAR, review_date DATE)")
    con.execute("""INSERT INTO prev.company VALUES ('a', 'company', 'user', 'accepted', '2026-10-17'),
                   ('b', 'company', 'user', 'accepted', '2026-10-17')""")
    con.execute("""INSERT INTO cur.company VALUES ('a', 'company', 'claude-main', 'accepted', '2026-10-25'),
                   ('b', 'foundation', 'claude-main', 'accepted', '2026-10-25'),
                   ('n', 'company', 'claude-main', 'accepted', '2026-10-25'),
                   ('r9', 'company', 'claude-main', 'accepted', '2026-10-20')""")
    d = SimpleNamespace(q=_q(con), compare={}, r42=set(), has_prev=True)
    path = em.later_org_paths(d, em.org_paths(d))
    assert path["a"] == "user-or-curated"           # same kind as in v4.6: the v4.6 path
    assert path["b"] == em.LATER_PATH               # the round changed the kind
    assert path["n"] == em.LATER_PATH               # a new organisation of the round
    assert path["r9"] == em.R9_PATH


def test_namespace_model_v47_counts_a_change_only_for_version_1_projects(tmp_path):
    from types import SimpleNamespace
    c, _ = _layer_fixture(tmp_path)
    # Model v4.7: github.com/tool/y has no v3 row in this variant of the fixture.
    c.execute("DELETE FROM p3 WHERE project = 'github.com/tool/y'")
    d = SimpleNamespace(q=_q(c), model="v4.7")
    rows, _, ns = em.namespace_model(d, {"acme": "user-or-curated"})
    per = {p["project"]: p for p in ns["per"]}
    assert per["github.com/acme/x"]["changed"] and not per["github.com/tool/y"]["changed"]
    assert per["github.com/acme/x"]["ns_key"] == "github.com/acme#acme"
    owns = [r for r in rows if r["relation"] == "owns"]
    assert owns[0]["projects_v1"] == 1
    d46 = SimpleNamespace(q=_q(c))
    rows46, _, _ = em.namespace_model(d46, {"acme": "user-or-curated"})
    assert "projects_v1" not in rows46[0]


def test_audit_tables_state_each_stratum_and_the_variants():
    aud = {"strata": [
        {"error_stratum": "D11", "population": "domain", "origin": "source", "band": "B1 >=1M", "class": "organisation",
         "match": "exact", "evidence": "", "owner_kind": "", "wrong": 0, "n_decided": 10, "right": 10, "unsure": 1,
         "answered": 11, "n_sample": 11, "complete": True, "p_pred_pct": 0.06, "rate_pct": 0.0, "jeffreys_pct": 4.5,
         "cp_lo_pct": 0.0, "cp_hi_pct": 30.8},
        {"error_stratum": "N03", "population": "namespace", "origin": "", "band": "", "class": "", "match": "",
         "evidence": "roster", "owner_kind": "foundation-or-other", "wrong": 1, "n_decided": 6, "right": 5,
         "unsure": 0, "answered": 6, "n_sample": 30, "complete": False, "p_pred_pct": 1.6, "rate_pct": 16.7,
         "jeffreys_pct": 21.4, "cp_lo_pct": 0.4, "cp_hi_pct": 64.1}]}
    pa = {"D11": [2, 0.002, 400, 0.4, 0.4]}
    base = {"per_astratum": pa, "err_tok_model": 1.0, "linked": 900, "E_unmatched": 0.001}
    sims = [{"per_astratum": {"D11": [2, 0.002 * f, 400, 0.4 * f, 0.4 * f]}, "err_tok_model": 1.0 * f,
             "linked": 900, "E_unmatched": 0.001} for f in (0.5, 1.0, 1.5, 2.0)]
    rows, upd, _ = em.audit_tables(aud, base, sims, {"D11": (0, 10)}, 1000, 1, {"N03": [4, 0.08, 0.04]},
                                   "complete stratum")
    r = {x["error_stratum"]: x for x in rows}
    assert r["D11"]["used"].startswith("yes") and r["N03"]["used"].startswith("no")
    assert r["D11"]["model_value_pct"] == pytest.approx(0.1) and r["N03"]["model_value_pct"] == pytest.approx(2.0)
    assert "q_r9" not in r["D11"]["parameter"] and r["N03"]["parameter"].startswith("bound B")
    assert [u["variant"].split(":")[0] for u in upd] == ["model only (no audit value)", "main", "update",
                                                        "measured values of every stratum with an answer (Jeffreys, no prior; partial strata)"]
    # main: the model error tokens of D11 (0.4) become 0.4 x theta / m = 0.4 x (0.5 / 11) / 0.001
    theta = 0.5 / 11
    assert upd[1]["E_all_pct"] == pytest.approx(round(100 * (1.0 - 0.4 + 0.4 * theta / 0.001) / 1000, 3))
    assert upd[0]["E_all_pct"] == pytest.approx(0.1)


# --------------------------------------------------------------------------------------------
# The tail audit (2026-10-26): measured rates of the unmatched real domains
# --------------------------------------------------------------------------------------------

TAIL = {"K": 1000.0, "C_t": 5000, "C_o": 2000, "C_c": 1000, "m": 50, "k_o": 8, "k_c": 5}


def test_params_use_the_tail_audit_rates_on_their_own_stream():
    import audit_tail as at
    c47 = _central47()
    ct = _central47(tail_audit=TAIL)
    P0, Pt = em.Params(c47), em.Params(ct)
    o, f = at.central_rates(TAIL)
    assert Pt.o_unmatched == Pt.o_tail == pytest.approx(o) and Pt.f_unmatched == Pt.f_tail == pytest.approx(f)
    assert P0.o_unmatched != Pt.o_unmatched          # without the audit: the type B rates
    # The draws: the other parameters stay the same; the rates come from rngt.
    a = em.Params(c47, random.Random(5), random.Random(14), random.Random(15))
    b = em.Params(ct, random.Random(5), random.Random(14), random.Random(15), random.Random(16))
    tail = ("o_unmatched", "o_tail", "f_unmatched", "f_tail")
    assert {k: v for k, v in vars(b).items() if k not in tail} == {k: v for k, v in vars(a).items() if k not in tail}
    assert (b.o_unmatched, b.f_unmatched) == pytest.approx(at.draw_rates(TAIL, random.Random(16)))
    # evaluate: the error of the unmatched domains is the measured rate times their tokens.
    kc = {"link": Counter(), "org": Counter()}
    row = {"o41": "acme", "kind41": "company", "group41": "G1 gitdm curated", "band": "B1 >=1M", "match41": "exact",
           "later": [], "skey": None, "domain": "a", "tokens": 100, "origin": "r9"}
    e = em.evaluate([row], Pt, {}, {"acme": "user-or-curated"}, kc, {"proposed": 300, "tail": 700}, 10_000)
    assert e["E_unmatched"] == pytest.approx(o * 1000 / 10_000)
    assert e["fn_unmatched"] == pytest.approx(f * 1000 / 10_000)


def test_tail_audit_rows_hold_counts_and_rates_only():
    st = {"items": 60, "answered": 60, "complete": True, "used": True, "frame_n": 900, "frame_tokens": 10**6,
          "frame_match": True, "pool_n": 900, "pool_tokens": 10**6, "pool_tokens_in_frame": 10**6, "out_of_pool": 0,
          "by_class": {"company": 5, "organisation": 3, "no-organisation": 50, "unsure": 2, "open": 0},
          "C_t": 5000, "m": 50, "k_o": 8, "k_c": 5, "K": 1000.0, "org_rate_ht": 0.2, "org_rate_central": 0.21,
          "org_rate_cp95": (0.1, 0.3), "org_rate_unsure_bounds": (0.19, 0.25), "company_rate_ht": 0.1,
          "company_rate_central": 0.11, "company_rate_cp95": (0.05, 0.2)}
    rows = em.tail_audit_rows(st)
    assert len(rows) == 1 and rows[0]["org_rate_cp95_pct"] == "10.0 to 30.0" and rows[0]["pool_tokens_in_frame_pct"] == 100.0
    assert "domain" not in json.dumps(rows).replace("frame_domains", "").replace("pool_domains", "")
    # An empty state (no decided unit yet) still gives a row.
    st2 = dict(st, org_rate_ht=None, org_rate_cp95=None, org_rate_unsure_bounds=None, company_rate_cp95=None,
               company_rate_ht=None, used=False, complete=False)
    st2.pop("org_rate_central")
    assert em.tail_audit_rows(st2)[0]["org_rate_ht_pct"] == ""


def _col_res(ns_dec, dom_dec):
    def e(c, sd=0.01):
        return {"central": c, "lo_all_right": c - 0.002, "hi_all_wrong": c + 0.002, "sd": sd, "ci95": (c - 0.02, c + 0.02),
                "weight_covered": 90, "weight_total": 100,
                "rows": [{"stratum": "s1", "W": 90, "units": 9, "n": 5, "decided": 4, "unsure": 1, "open": 0, "carried": 1,
                          "rate_central": c}]}
    return {"use_min": 440, "sample_size": [{"part": "ns", "n": ns_dec, "basis": "now"}], "parts": {
        "ns": {"items": 800, "decided": ns_dec, "decided_own": ns_dec - 5, "decided_carried": 5, "unsure": 1, "open": 0,
               "used": ns_dec >= 440, "wrong_projects": e(0.03), "wrong_tokens": e(0.04)},
        "dom": {"items": 800, "decided": dom_dec, "decided_own": dom_dec, "decided_carried": 0, "unsure": 0, "open": 0,
                "used": dom_dec >= 440, "frame_tokens": 900, "wrong_tokens": e(0.02), "kind_tokens": e(0.001),
                "company_tokens": e(0.3), "wrong_tokens_linked_share": e(0.005), "wrong_tokens_unmatched_share": e(0.015)}}}


def test_column_audit_keeps_the_model_values_until_440_decided_answers():
    s0 = {"namespace_wrong_owner_projects_pct": 4.801, "namespace_wrong_owner_projects_U_pct": 2.405,
          "namespace_wrong_owner_tokens_pct": 6.105, "E_dataset_pct": 1.936, "E_dataset_U_pct": 0.526,
          "E_dataset_mc95": "1.442 to 2.465", "E_all_pct": 0.147, "E_unmatched_pct": 1.789, "E_linked_pct": 0.158,
          "linked_tokens": 800}
    s, t = dict(s0), {}
    em.column_audit_update(s, t, _col_res(300, 100), 1000, "audit-columns")
    for k, v in s0.items():
        assert s[k] == v
    assert s["namespace_error_basis"].startswith("model") and s["domain_error_basis"].startswith("model")
    assert s["column_audit_ns_decided"] == 300 and not s["column_audit_ns_used"]
    assert {"column_audit_state", "column_audit_estimate", "column_audit_strata", "column_audit_sample_size"} <= set(t)
    s, t = dict(s0), {}
    em.column_audit_update(s, t, _col_res(450, 500), 1000, "audit-columns")
    assert s["namespace_wrong_owner_projects_pct"] == 3.0 and s["namespace_wrong_owner_projects_model_pct"] == 4.801
    assert s["namespace_wrong_owner_tokens_pct"] == 4.0 and s["namespace_error_basis"] == "measured: column audit"
    # domain: the frame rate x frame tokens / evaluated tokens (900 / 1000)
    assert s["E_dataset_pct"] == pytest.approx(1.8) and s["E_dataset_model_pct"] == 1.936
    assert s["E_unmatched_pct"] == pytest.approx(1.35) and s["E_all_pct"] == pytest.approx(0.45)
    assert s["E_linked_pct"] == pytest.approx(100 * 0.005 * 900 / 800, abs=1e-3)
    assert s["E_dataset_mc95_model"] == "1.442 to 2.465" and s["company_share_column_audit_pct"] == pytest.approx(27.0)
