"""Tests of the tail audit: the PPS sample (audit_tail_sample.py) and the estimator (audit_tail.py).
Synthetic frames and answers only; no workspace data."""
import csv
import json
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(1, str(Path(__file__).parent.parent))
import audit_tail as at  # noqa: E402
import audit_tail_sample as ats  # noqa: E402


def _frame(n=400, seed=1):
    r = random.Random(seed)
    fr = [{"domain": f"d{i:04d}.example.org", "tokens": int(r.paretovariate(1.1) * 1000)} for i in range(n)]
    fr[0]["tokens"] = 4_000_000          # two units larger than any step: certainty units
    fr[1]["tokens"] = 2_500_000
    return fr


def test_seed_fraction_is_fixed_and_in_unit_interval():
    u = ats.seed_fraction("20261026:tail")
    assert 0 <= u < 1 and u == ats.seed_fraction("20261026:tail") and u != ats.seed_fraction("x")


def test_pps_certainty_units_and_inclusion_probabilities():
    fr = _frame()
    s = ats.pps_systematic(fr, 60, 0.37)
    cert, pts = s["certainty"], s["points"]
    assert {r["domain"] for r in cert} >= {"d0000.example.org", "d0001.example.org"}
    assert len(cert) + len(pts) == 60 and len({r["domain"] for r in cert + pts}) == 60
    assert all(r["tokens"] >= s["step"] for r in cert) and all(r["tokens"] < s["step"] for r in pts)
    assert s["rest_tokens"] + sum(r["tokens"] for r in cert) == s["total"] == sum(r["tokens"] for r in fr)
    for r in pts:
        assert r["pi"] == pytest.approx(s["rest_n"] * r["tokens"] / s["rest_tokens"]) and 0 < r["pi"] < 1
    # The weights t / pi of the points are all the step.
    assert all(r["tokens"] / r["pi"] == pytest.approx(s["step"]) for r in pts)
    # The same start gives the same sample.
    assert [r["domain"] for r in ats.pps_systematic(fr, 60, 0.37)["points"]] == [r["domain"] for r in pts]


def test_pps_rejects_bad_sizes():
    with pytest.raises(ValueError):
        ats.pps_systematic(_frame(10), 10, 0.5)
    with pytest.raises(ValueError):
        ats.pps_systematic([], 5, 0.5)


def test_frame_checksum_ignores_the_order():
    fr = _frame(20)
    assert ats.frame_sha256(fr) == ats.frame_sha256(list(reversed(fr)))
    fr2 = [dict(r) for r in fr]
    fr2[3]["tokens"] += 1
    assert ats.frame_sha256(fr2) != ats.frame_sha256(fr)


def test_unit_class_of_each_answer():
    org_c = {"ai_class": "company"}
    org_o = {"ai_class": "other-organisation"}
    ind = {"ai_class": "independent"}
    uns = {"ai_class": "unsure"}
    assert at.unit_class(org_c, {"verdict": "right"}) == "company"
    assert at.unit_class(org_o, {"verdict": "right"}) == "organisation"
    assert at.unit_class(ind, {"verdict": "right"}) == "no-organisation"
    assert at.unit_class({"ai_class": "free-provider"}, {"verdict": "right"}) == "no-organisation"
    assert at.unit_class(uns, {"verdict": "right"}) == "unsure"          # right of "could not decide": no information
    assert at.unit_class(ind, {"verdict": "wrong", "correct_class": "company"}) == "company"
    assert at.unit_class(org_c, {"verdict": "wrong", "correct_class": "independent"}) == "no-organisation"
    assert at.unit_class(uns, {"verdict": "wrong", "correct_class": "other-organisation"}) == "organisation"
    assert at.unit_class(ind, {"verdict": "wrong"}) == "open"           # wrong with no class: not complete
    assert at.unit_class(ind, {"verdict": "unsure"}) == "unsure"
    assert at.unit_class(ind, None) == "open" and at.unit_class(ind, {"verdict": ""}) == "open"
    assert at.ai_class("organisation", "consultancy") == "company"
    assert at.ai_class("organisation", "academic") == "other-organisation"
    assert at.ai_class("none", "") == "none" and at.ai_class("weird", "") == "unsure"


def _units(s, cls_of):
    return [{"domain": r["domain"], "unit": "certainty" if r in s["certainty"] else "point", "tokens": r["tokens"],
             "cls": cls_of(r)} for r in s["certainty"] + s["points"]]


def _design(s):
    return {"rest_tokens": s["rest_tokens"], "rest_n": s["rest_n"]}


def test_estimate_identities():
    fr = _frame()
    s = ats.pps_systematic(fr, 60, 0.5)
    # All organisations: rate 1; none: rate 0; no unsure answer: the denominator is the frame tokens.
    e1 = at.estimate(_units(s, lambda r: "company"), _design(s))
    assert e1["org_rate_ht"] == pytest.approx(1.0) and e1["company_rate_ht"] == pytest.approx(1.0)
    assert e1["C_t"] + e1["K"] * e1["m"] == pytest.approx(s["total"])
    e0 = at.estimate(_units(s, lambda r: "no-organisation"), _design(s))
    assert e0["org_rate_ht"] == 0.0 and e0["complete"]
    # Certainty units: exact. The first certainty unit is an organisation, all else not.
    big = s["certainty"][0]["domain"]
    e = at.estimate(_units(s, lambda r: "organisation" if r["domain"] == big else "no-organisation"), _design(s))
    assert e["org_rate_ht"] == pytest.approx(s["certainty"][0]["tokens"] / s["total"])
    assert e["company_rate_ht"] == 0.0
    lo, hi = e["org_rate_cp95"]
    assert lo == pytest.approx(e["org_rate_ht"]) and hi > lo      # 0 of m points: the lower bound is the certainty part


def test_estimate_is_unbiased_over_random_starts():
    fr = _frame(300, seed=7)
    rng = random.Random(3)
    y = {r["domain"]: rng.random() < 0.25 for r in fr}
    y["d0000.example.org"] = True
    true = sum(r["tokens"] for r in fr if y[r["domain"]]) / sum(r["tokens"] for r in fr)
    est = []
    for k in range(400):
        s = ats.pps_systematic(fr, 30, (k + 0.5) / 400)
        est.append(at.estimate(_units(s, lambda r: "company" if y[r["domain"]] else "no-organisation"),
                               _design(s))["org_rate_ht"])
    assert sum(est) / len(est) == pytest.approx(true, abs=0.01)


def test_unsure_answers_are_apart_and_bound_the_rate():
    fr = _frame()
    s = ats.pps_systematic(fr, 60, 0.5)
    pts = s["points"]
    uns = {pts[0]["domain"], pts[1]["domain"], s["certainty"][-1]["domain"]}
    orgs = {r["domain"] for r in pts[2:12]}
    e = at.estimate(_units(s, lambda r: "unsure" if r["domain"] in uns else "organisation" if r["domain"] in orgs
                           else "no-organisation"), _design(s))
    assert e["unsure"] == 3 and e["mu"] == 2 and e["complete"]
    lo, hi = e["org_rate_unsure_bounds"]
    assert lo <= e["org_rate_ht"] <= hi and hi - lo > 0
    # Open answers make the estimate incomplete.
    e2 = at.estimate(_units(s, lambda r: "open" if r["domain"] == pts[5]["domain"] else "no-organisation"), _design(s))
    assert not e2["complete"] and e2["open"] == 1


def test_units_outside_the_pool_leave_the_estimate():
    fr = _frame()
    s = ats.pps_systematic(fr, 60, 0.5)
    units = _units(s, lambda r: "company")
    pool = {u["domain"] for u in units[5:]}
    e = at.estimate(units, _design(s), pool)
    assert e["out_of_pool"] == 5 and e["n"] == 55 and e["org_rate_ht"] == pytest.approx(1.0)


def test_central_and_draws_keep_company_below_organisation():
    t = {"K": 1000.0, "C_t": 5000, "C_o": 2000, "C_c": 1000, "m": 50, "k_o": 8, "k_c": 5}
    o, c = at.central_rates(t)
    po = 8.5 / 51
    assert o == pytest.approx((2000 + 1000 * 50 * po) / (5000 + 50_000))
    assert c == pytest.approx((1000 + 1000 * 50 * po * 5.5 / 9) / 55_000)
    rng = random.Random(11)
    draws = [at.draw_rates(t, rng) for _ in range(3000)]
    assert all(cc <= oo + 1e-12 for oo, cc in draws)
    assert sum(d[0] for d in draws) / len(draws) == pytest.approx(o, rel=0.03)


def test_analyse_reads_a_folder(tmp_path):
    fr = _frame()
    s = ats.pps_systematic(fr, 60, 0.5)
    sample = s["certainty"] + s["points"]
    items = [{"item_id": f"X{n:04d}", "domain": r["domain"], "title": r["domain"], "type": "t",
              "unit": "certainty" if r in s["certainty"] else "point", "tokens": r["tokens"],
              "ai_class": "independent" if n % 3 else "company", "ai_verdict": "x"} for n, r in enumerate(sample, 1)]
    (tmp_path / "data").mkdir()
    (tmp_path / "data/items.json").write_text(json.dumps(items))
    design = {"rest_tokens": s["rest_tokens"], "rest_n": s["rest_n"], "frame_sha256": ats.frame_sha256(fr),
              "frame_tokens": s["total"], "frame_n": s["frame_n"]}
    (tmp_path / "design.json").write_text(json.dumps(design))
    # Half of the items answered right: not complete.
    with open(tmp_path / "answers.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["item_id", "verdict", "correct_class"])
        w.writeheader()
        for i in items[:30]:
            w.writerow({"item_id": i["item_id"], "verdict": "right", "correct_class": ""})
    e = at.analyse(tmp_path)
    assert e["answered"] == 30 and not e["complete"] and e["by_class"]["open"] == 30
    # All answered: right, except one wrong with a class.
    with open(tmp_path / "answers.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, ["item_id", "verdict", "correct_class"])
        w.writeheader()
        for i in items:
            w.writerow({"item_id": i["item_id"], "verdict": "right", "correct_class": ""})
        w.writerow({"item_id": items[1]["item_id"], "verdict": "wrong", "correct_class": "other-organisation"})
    e = at.analyse(tmp_path)
    assert e["complete"] and e["answered"] == 60
    assert e["by_class"]["company"] == 20 and e["by_class"]["organisation"] == 1
    assert 0 < e["company_rate_ht"] <= e["org_rate_ht"] < 1


def test_build_items_classes_and_no_at_sign():
    sample = [{"sample_id": "S01", "unit": "certainty", "domain": "a.example.org", "tokens": "10", "pi": "1.0",
               "part": "tail", "tokens_v1": "4", "tokens_x1k": "6", "dataset_projects": "1", "top_project": "o__r",
               "commits_x1k": "", "authors_x1k": ""},
              {"sample_id": "S02", "unit": "point", "domain": "b.example.org", "tokens": "5", "pi": "0.5",
               "part": "proposed", "tokens_v1": "5", "tokens_x1k": "0", "dataset_projects": "2", "top_project": "",
               "commits_x1k": "", "authors_x1k": ""}]
    judged = {"S01": {"verdict": "organisation", "org_id": "acme", "new_row": "", "evidence_urls": "https://a.example.org/ ; https://b",
                      "note": "x", "confidence": "high", "_chunk": "tail-01"},
              "S02": {"verdict": "organisation", "org_id": "new:uni-x", "new_row": "uni-x|Uni X|academic||DE",
                      "evidence_urls": "", "note": "", "confidence": "medium", "_chunk": "tail-02"}}
    index = {"acme": {"name": "Acme", "kind": "consultancy", "parent_company_id": "", "domains": "acme.example"}}
    items = at.build_items(sample, judged, index, {})
    assert [i["item_id"] for i in items] == ["X0001", "X0002"]
    assert items[0]["ai_class"] == "company" and items[1]["ai_class"] == "other-organisation"
    assert items[0]["sources"] == ["https://a.example.org/", "https://b"] and items[1]["organisation"]["new"]
    at.check_no_at(items)
    with pytest.raises(SystemExit):
        at.check_no_at([{"note": "x" + chr(64) + "y"}])
