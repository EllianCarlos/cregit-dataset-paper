"""Tests of the column audit: the allocation (audit_columns_sample.py), the answers, the carried answers
and the estimator (audit_columns.py), and the checks of the server (audit_columns_serve.py).
Synthetic frames and answers only; no workspace data."""
import csv
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(1, str(Path(__file__).parent.parent))
import audit_columns as ac  # noqa: E402
import audit_columns_sample as acs  # noqa: E402
import audit_columns_serve as srv  # noqa: E402

CERT = ac.CERT


def test_neyman_sum_floor_cap_and_weights():
    spec = {"a": {"N": 10, "w": 1000, "p": 0.5}, "b": {"N": 500, "w": 5000, "p": 0.01},
            "c": {"N": 300, "w": 300, "p": 0.5}, "d": {"N": 3, "w": 3, "p": 0.2}}
    n = acs.neyman(spec, 200, 15)
    assert sum(n.values()) == 200
    assert n["a"] == 10 and n["d"] == 3                    # capped at N_h
    assert all(n[h] >= min(spec[h]["N"], 15) for h in spec)
    # sd 0.5 versus about 0.1: stratum c gets more units per weight than stratum b
    assert n["c"] / 300 > n["b"] / 5000
    assert acs.neyman({"x": {"N": 5, "w": 1, "p": 0.5}}, 50, 15) == {"x": 5}


def test_srs_depends_only_on_the_seed():
    units = [{"unit": f"u{i}"} for i in range(50)]
    a = acs.srs(units, 10, random.Random(3), "unit")
    b = acs.srs(list(reversed(units)), 10, random.Random(3), "unit")
    assert [r["unit"] for r in a] == [r["unit"] for r in b] and len(a) == 10


def test_sample_dom_puts_the_largest_in_the_certainty_stratum():
    r = random.Random(5)
    frame = []
    for i in range(600):
        st = "linked exact curated" if i % 3 else "unmatched tail"
        frame.append({"domain": f"d{i:04d}.example.org", "tokens": int(r.paretovariate(1.2) * 100) + 1, "stratum": st,
                      "state": "linked" if i % 3 else "unmatched"})
    sample, strata = acs.sample_dom(frame, {"linked exact curated": 0.01, "unmatched tail": 0.4}, 120, 10, "t")
    assert len(sample) == 120 and len({s["domain"] for s in sample}) == 120
    top = sorted(frame, key=lambda x: (-x["tokens"], x["domain"]))[:10]
    assert {x["domain"] for x in top} == {s["domain"] for s in sample if s["stratum"] == CERT}
    assert sum(s["n"] for s in strata) == 120


def test_answer_state_and_y_of_the_namespace_part():
    assert ac.answer_state("ns", {"verdict": "right"}) == "decided"
    assert ac.answer_state("ns", {"verdict": "wrong"}) == "open"
    assert ac.answer_state("ns", {"verdict": "wrong", "correct_class": "free-provider"}) == "open"
    assert ac.answer_state("ns", {"verdict": "wrong", "correct_class": "project"}) == "decided"
    assert ac.answer_state("ns", {"verdict": "unsure"}) == "unsure"
    assert ac.answer_state("ns", None) == "open"
    assert ac.y_values("ns", {}, {"verdict": "wrong", "correct_class": "independent"}) == {"wrong": 1}
    assert ac.y_values("ns", {}, {"verdict": "unsure"}) == {}


def test_y_of_the_domain_part():
    linked = {"state": "linked", "kind": "company"}
    unm = {"state": "unmatched", "kind": "independent"}
    assert ac.y_values("dom", linked, {"verdict": "right"}) == {"wrong": 0, "kind": 0, "company": 1}
    w = ac.y_values("dom", linked, {"verdict": "wrong", "correct_class": "other-organisation", "wrong_part": "kind"})
    assert w == {"wrong": 0, "kind": 1, "company": 0}
    assert ac.y_values("dom", linked, {"verdict": "wrong", "correct_class": "independent"})["wrong"] == 1
    # The value independent of an unmatched domain is wrong only for an organisation.
    assert ac.y_values("dom", unm, {"verdict": "wrong", "correct_class": "free-provider"})["wrong"] == 0
    assert ac.y_values("dom", unm, {"verdict": "wrong", "correct_class": "company"}) == {"wrong": 1, "kind": 0, "company": 1}
    assert ac.y_values("dom", unm, {"verdict": "right"}) == {"wrong": 0, "kind": 0, "company": 0}


def _ns_design(n_cert=4, n_a=20, N_a=200):
    return {"ns": {"strata": [
        {"stratum": CERT, "units": n_cert, "projects": 40, "tokens": 4000, "method": "all units (certainty)"},
        {"stratum": "class a", "units": N_a, "projects": 300, "tokens": 3000, "method": "simple random sample"}]}}


def _ns_items(n_cert=4, n_a=20):
    its = [{"item_id": f"N{i:04d}", "stratum": CERT, "projects": 10, "tokens": 1000} for i in range(1, n_cert + 1)]
    its += [{"item_id": f"N{i:04d}", "stratum": "class a", "projects": 1 + (i % 2), "tokens": 10 * i}
            for i in range(n_cert + 1, n_cert + n_a + 1)]
    return its


def test_namespace_estimate_certainty_is_exact_and_srs_has_the_observed_rate():
    items = _ns_items()
    ans = {i["item_id"]: {"verdict": "right"} for i in items}
    ans["N0001"] = {"verdict": "wrong", "correct_class": "project"}
    e = ac.estimate_rate("ns", items, ans, _ns_design(), "wrong", "projects", draws=500)
    rows = {r["stratum"]: r for r in e["rows"]}
    assert rows[CERT]["rate_central"] == pytest.approx(0.25)        # 10 of 40 projects, no sampling error
    assert rows["class a"]["rate_central"] == 0.0                     # 0 wrong: no prior in the central value
    assert e["central"] == pytest.approx(40 * 0.25 / 340)
    assert e["ci95"][0] <= e["central"] <= e["ci95"][1]
    assert e["ci95"][0] == pytest.approx(40 * 0.25 / 340)             # class a has k = 0: its lower limit is 0
    assert e["weight_covered"] == e["weight_total"] == 340


def test_zero_wrong_in_all_strata_gives_central_0_lower_0_upper_above_0():
    items = _ns_items()
    ans = {i["item_id"]: {"verdict": "right"} for i in items}
    for weight in ("projects", "tokens"):
        e = ac.estimate_rate("ns", items, ans, _ns_design(), "wrong", weight, draws=500)
        assert e["central"] == 0.0 and e["lo_all_right"] == 0.0 and e["hi_all_wrong"] == 0.0
        assert e["ci95"][0] == 0.0 and e["ci95"][1] > 0.0 and e["sd"] > 0.0
        assert all(r["rate_central"] == 0.0 for r in e["rows"])
    d = ac.estimate_rate("dom", _dom_items(), {i["item_id"]: {"verdict": "right"} for i in _dom_items()},
                         _dom_design(), draws=500)
    assert d["central"] == 0.0 and d["ci95"][0] == 0.0 and d["ci95"][1] > 0.0


def _one_stratum(n, N=10 ** 9):
    design = {"ns": {"strata": [{"stratum": "s", "units": N, "projects": N, "tokens": N,
                                 "method": "simple random sample"}]}}
    items = [{"item_id": f"N{i:04d}", "stratum": "s", "projects": 1, "tokens": 1} for i in range(1, n + 1)]
    return design, items


def test_one_stratum_gives_the_clopper_pearson_interval():
    # 2 wrong of 20, equal weights, fpc about 1: the exact Clopper-Pearson 95% interval is 1.235% to 31.70%;
    # 0 wrong of 20: 0 to 1 - 0.025^(1/20) = 16.84%.
    design, items = _one_stratum(20)
    ans = {i["item_id"]: {"verdict": "right"} for i in items}
    for k in ("N0001", "N0002"):
        ans[k] = {"verdict": "wrong", "correct_class": "independent"}
    e = ac.estimate_rate("ns", items, ans, design, "wrong", "projects", draws=40000)
    assert e["central"] == pytest.approx(0.1)
    assert e["ci95"][0] == pytest.approx(0.01235, abs=0.002)
    assert e["ci95"][1] == pytest.approx(0.31698, abs=0.005)
    z = ac.estimate_rate("ns", items, {i["item_id"]: {"verdict": "right"} for i in items}, design, "wrong",
                         "projects", draws=40000)
    assert z["central"] == 0.0 and z["ci95"][0] == 0.0
    assert z["ci95"][1] == pytest.approx(1 - 0.025 ** (1 / 20), abs=0.004)


def test_full_count_of_a_stratum_has_no_spread():
    design, items = _one_stratum(20, N=20)                            # all units sampled: fpc = 0
    ans = {i["item_id"]: {"verdict": "right"} for i in items}
    ans["N0001"] = {"verdict": "wrong", "correct_class": "project"}
    e = ac.estimate_rate("ns", items, ans, design, "wrong", "projects", draws=200)
    assert e["central"] == e["ci95"][0] == e["ci95"][1] == pytest.approx(0.05)


def test_neyman_stratum_weights_projects_and_kish_size():
    items = _ns_items()
    ans = {i["item_id"]: {"verdict": "right"} for i in items}
    for i in items:
        if i["stratum"] == "class a" and i["projects"] == 2 and int(i["item_id"][1:]) <= 10:
            ans[i["item_id"]] = {"verdict": "wrong", "correct_class": "unknown"}      # N0005, N0007, N0009
    a = [i for i in items if i["stratum"] == "class a"]
    w = [i["projects"] for i in a]                                                   # ten 1s and ten 2s: 30 projects
    r = 6 / 30                                                                       # 3 wrong units x 2 projects
    n_eff = sum(w) ** 2 / sum(x * x for x in w)                                      # 900 / 50 = 18
    e = ac.estimate_rate("ns", items, ans, _ns_design(), "wrong", "projects", draws=200)
    row = {x["stratum"]: x for x in e["rows"]}["class a"]
    assert row["rate_central"] == pytest.approx(r) and row["n_eff"] == pytest.approx(n_eff)
    assert row["k_eff"] == pytest.approx(r * n_eff)
    assert e["central"] == pytest.approx(300 * r / 340)                              # W = the stratum projects
    t = ac.estimate_rate("ns", items, ans, _ns_design(), "wrong", "tokens", draws=200)
    tw = {i["item_id"]: i["tokens"] for i in a}
    rt = (tw["N0005"] + tw["N0007"] + tw["N0009"]) / sum(tw.values())
    assert t["central"] == pytest.approx(3000 * rt / 7000)


def test_certainty_stratum_alone_is_exact():
    items = _ns_items()
    ans = {i["item_id"]: {"verdict": "right"} for i in items if i["stratum"] == CERT}
    ans["N0001"] = {"verdict": "wrong", "correct_class": "project"}
    e = ac.estimate_rate("ns", items, ans, _ns_design(), "wrong", "projects", draws=200)
    assert e["central"] == e["ci95"][0] == e["ci95"][1] == pytest.approx(0.25) and e["sd"] == 0.0


def test_clopper_pearson_draws_at_the_ends():
    rng = random.Random(1)
    assert ac.cp_draw(0, 10, "lower", rng) == 0.0
    assert ac.cp_draw(10, 10, "upper", rng) == 1.0
    assert 0 < ac.cp_draw(0, 10, "upper", rng) < 1 and 0 < ac.cp_draw(10, 10, "lower", rng) <= 1
    assert ac.cp_draw(0, 0, "upper", rng) == 0.0


def test_unsure_answers_give_a_range():
    items = _ns_items()
    ans = {i["item_id"]: {"verdict": "right"} for i in items}
    for k in ("N0006", "N0007", "N0008"):
        ans[k] = {"verdict": "unsure"}
    e = ac.estimate_rate("ns", items, ans, _ns_design(), "wrong", "projects", draws=500)
    assert e["lo_all_right"] < e["central"] < e["hi_all_wrong"]
    assert e["central"] == pytest.approx(ac.combine(ac.stratum_forms("ns", items, ans, _ns_design(), "wrong", "projects"), 0.5))
    # By hand: class a has 30 projects; the unsure units N0006, N0007, N0008 hold 1 + 2 + 1 = 4 projects.
    assert e["lo_all_right"] == 0.0
    assert e["hi_all_wrong"] == pytest.approx(300 * (4 / 30) / 340)
    assert e["central"] == pytest.approx((e["lo_all_right"] + e["hi_all_wrong"]) / 2)
    # The draws take f ~ Uniform(0, 1): the interval holds the central value, not the full range.
    assert e["ci95"][0] < e["central"] < e["ci95"][1]


def test_open_strata_leave_the_estimate_and_lower_the_coverage():
    items = _ns_items()
    ans = {"N0001": {"verdict": "right"}}
    e = ac.estimate_rate("ns", items, ans, _ns_design(), "wrong", "projects", draws=100)
    assert e["weight_covered"] == 40 and e["central"] == 0.0
    assert ac.estimate_rate("ns", items, {}, _ns_design(), "wrong", "projects")["central"] is None


def _dom_design():
    return {"dom": {"strata": [
        {"stratum": CERT, "units": 2, "tokens": 2000, "method": "all units (certainty)"},
        {"stratum": "linked exact curated", "units": 100, "tokens": 1000, "method": "systematic PPS (tokens)",
         "rest_n": 9, "rest_tokens": 900, "certainty_n": 1},
        {"stratum": "unmatched tail", "units": 400, "tokens": 1000, "method": "systematic PPS (tokens)",
         "rest_n": 10, "rest_tokens": 1000, "certainty_n": 0}]}}


def _dom_items():
    its = [{"item_id": "D0001", "stratum": CERT, "unit": "certainty", "tokens": 1500, "state": "linked", "kind": "company"},
           {"item_id": "D0002", "stratum": CERT, "unit": "certainty", "tokens": 500, "state": "unmatched", "kind": "independent"},
           {"item_id": "D0003", "stratum": "linked exact curated", "unit": "certainty", "tokens": 100, "state": "linked",
            "kind": "company"}]
    its += [{"item_id": f"D{i:04d}", "stratum": "linked exact curated", "unit": "point", "tokens": 5, "state": "linked",
             "kind": "company"} for i in range(4, 13)]
    its += [{"item_id": f"D{i:04d}", "stratum": "unmatched tail", "unit": "point", "tokens": 3, "state": "unmatched",
             "kind": "independent"} for i in range(13, 23)]
    return its


def test_domain_pps_estimate_and_the_state_shares():
    items = _dom_items()
    ans = {i["item_id"]: {"verdict": "right"} for i in items}
    ans["D0002"] = {"verdict": "wrong", "correct_class": "company"}                 # 500 of 2000 certainty tokens
    for k in ("D0013", "D0014", "D0015", "D0016"):
        ans[k] = {"verdict": "wrong", "correct_class": "other-organisation"}       # 4 of 10 points
    e = ac.estimate_rate("dom", items, ans, _dom_design(), draws=500)
    rows = {r["stratum"]: r for r in e["rows"]}
    assert rows[CERT]["rate_central"] == pytest.approx(0.25)
    assert rows["unmatched tail"]["rate_central"] == pytest.approx(4 / 10)         # the observed share, no prior
    assert rows["linked exact curated"]["rate_central"] == 0.0
    assert e["central"] == pytest.approx((2000 * 0.25 + 1000 * 0.4) / 4000)
    assert e["ci95"][0] <= e["central"] <= e["ci95"][1]
    lk = ac.estimate_rate("dom", items, ans, _dom_design(), draws=200, state="linked")
    um = ac.estimate_rate("dom", items, ans, _dom_design(), draws=200, state="unmatched")
    assert lk["central"] + um["central"] == pytest.approx(e["central"])
    # The tail stratum has no linked domain: a structural zero in the linked share.
    assert {r["stratum"]: r for r in lk["rows"]}["unmatched tail"]["rate_central"] == 0.0
    k = ac.estimate_rate("dom", items, ans, _dom_design(), "kind", draws=100)
    assert k["central"] < e["central"]


def test_domain_pps_stratum_with_its_own_certainty_unit():
    # linked exact curated: one certainty unit (100 tokens, right) and 9 points of K = 900 / 9 = 100 tokens.
    # 3 wrong points: R = (0 + 100 x 9 x 3/9) / (100 + 900) = 0.3. With 6 points open: M = 3 answered
    # points, 1 wrong: R = (0 + 100 x 3 x 1/3) / (100 + 300) = 0.25.
    items = _dom_items()
    ans = {i["item_id"]: {"verdict": "right"} for i in items}
    for k in ("D0004", "D0005", "D0006"):
        ans[k] = {"verdict": "wrong", "correct_class": "independent"}
    e = ac.estimate_rate("dom", items, ans, _dom_design(), draws=200)
    row = {r["stratum"]: r for r in e["rows"]}["linked exact curated"]
    assert row["rate_central"] == pytest.approx(0.3) and row["n_eff"] == 9 and row["k_eff"] == 3
    assert e["central"] == pytest.approx(1000 * 0.3 / 4000)
    part = {k: v for k, v in ans.items() if k not in {f"D{i:04d}" for i in range(7, 13)} and k != "D0005"
            and k != "D0006"}
    part["D0007"] = {"verdict": "right"}
    part["D0008"] = {"verdict": "right"}
    p = ac.estimate_rate("dom", items, part, _dom_design(), draws=200)
    assert {r["stratum"]: r for r in p["rows"]}["linked exact curated"]["rate_central"] == pytest.approx(0.25)


def test_parse_after_and_the_pseudo_value():
    assert ac.parse_after("Acme (Paris) (acme, company)") == ("acme", "company")
    assert ac.parse_after("(no row: independent)") == ("", "independent")
    assert ac.parse_after("garbage") is None

    class FakeDb:
        merge = {"old": "acme"}

        def final(self, cid):
            return self.merge.get(cid, cid)
    unm = {"state": "unmatched", "value": {"id": "", "kind": "independent"}}
    lin = {"state": "linked", "value": {"id": "acme", "kind": "company"}}
    assert ac.same_dom_value(unm, "", "independent", FakeDb())
    assert ac.same_dom_value(unm, "person-1", "independent", FakeDb())
    assert not ac.same_dom_value(unm, "acme", "company", FakeDb())
    assert ac.same_dom_value(lin, "old", "company", FakeDb())                     # a merged id
    assert not ac.same_dom_value(lin, "acme", "consultancy", FakeDb())


def test_write_part_keeps_answers_and_adds_carried_rows(tmp_path):
    pf = tmp_path / "ns"
    pf.mkdir()
    with open(pf / "answers.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ac.COLS)
        w.writeheader()
        w.writerow({"item_id": "N0001", "verdict": "wrong", "correct_class": "project", "note": "mine"})
    items = [{"item_id": "N0001", "title": "github.com/a"}, {"item_id": "N0002", "title": "github.com/b"}]
    carried = {"N0001": {"item_id": "N0001", "verdict": "right", "carried": "v47:T1"},
               "N0002": {"item_id": "N0002", "verdict": "right", "carried": "v48:T2"},
               "N0009": {"item_id": "N0009", "verdict": "right", "carried": "v48:T9"}}
    meta = ac.write_part(pf, items, {"part": "ns"}, carried)
    ans = ac.read_answers(pf)
    assert ans["N0001"]["verdict"] == "wrong" and ans["N0001"]["carried"] == ""
    assert ans["N0002"]["carried"] == "v48:T2" and "N0009" not in ans and meta["carried_added"] == 1
    assert (pf / "audit.html").exists() and (pf / "serve_columns.py").exists()


def test_at_sign_stops_and_sample_size_rows():
    with pytest.raises(SystemExit):
        ac.check_no_at({"x": "a" + chr(64) + "b"})
    rows = ac.sample_size_rows("ns", 440, 0.05, (0.03, 0.07))
    assert rows[0]["margin_p50_pct"] == pytest.approx(4.672, abs=0.001)
    assert rows[0]["ci95_half_width_pct"] == pytest.approx(2.0)
    assert [r["basis"] for r in rows] == ["now", "target 440", "target 800"]


def test_server_checks_the_rows():
    ok = [{"item_id": "N0001", "verdict": "wrong", "correct_class": "project", "wrong_part": ""},
          {"item_id": "D0002", "verdict": "right", "correct_class": "", "wrong_part": "kind"}]
    assert srv.check_rows(ok) == ""
    assert srv.check_rows([{"item_id": "X0001", "verdict": "right"}]) == "bad item"
    assert srv.check_rows([{"item_id": "N0001", "verdict": "maybe"}]) == "bad verdict"
    assert srv.check_rows([{"item_id": "N0001", "verdict": "wrong", "correct_class": "x"}]) == "bad class"
    assert srv.check_rows([{"item_id": "D0001", "verdict": "wrong", "wrong_part": "x"}]) == "bad wrong part"
    text = srv.to_csv([{"item_id": "N0001", "note": "a" + chr(64) + "b", "verdict": "right"}])
    assert chr(64) not in text and text.startswith(srv.HEADER)
    assert srv.COLS == ac.COLS
