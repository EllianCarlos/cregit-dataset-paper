"""Tests of audit_analysis.py on synthetic answers (no file of the real audit is read)."""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_analysis as aa  # noqa: E402

SHA = "d" * 64


def _write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def _sample(tmp_path: Path, answers: list[dict]) -> Path:
    """Two domain strata (A: 100 units, 10 items, 90% of the tokens; B: 50 units, 5 items, 10%) and
    one namespace stratum (N: 20 units, 4 items)."""
    f = tmp_path / "s"
    f.mkdir(parents=True)
    (f / "meta.json").write_text(json.dumps({"data_sha256": SHA}))
    _write(f / "strata.csv", [
        {"error_stratum": "A", "population": "domain", "origin": "source", "band": "B1 >=1M", "class": "organisation",
         "match": "exact", "evidence": "", "owner_kind": "", "units": 100, "weight": 900, "weight_unit": "tokens",
         "weight_share_pct": 90.0, "p_pred_links_pct": 1.0},
        {"error_stratum": "B", "population": "domain", "origin": "r7", "band": "B3 <10k", "class": "organisation",
         "match": "exact", "evidence": "", "owner_kind": "", "units": 50, "weight": 100, "weight_unit": "tokens",
         "weight_share_pct": 10.0, "p_pred_links_pct": 5.0},
        {"error_stratum": "N", "population": "namespace", "origin": "", "band": "", "class": "", "match": "",
         "evidence": "roster", "owner_kind": "company", "units": 20, "weight": 40, "weight_unit": "dataset projects",
         "weight_share_pct": 100.0, "p_pred_links_pct": 2.0}])
    items = [{"item_id": f"A{i}", "population": "domain", "key": f"a{i}.example.org", "error_stratum": "A",
              "organisation_id": "acme", "tokens": 10 * (i + 1), "projects": ""} for i in range(10)]
    items += [{"item_id": f"B{i}", "population": "domain", "key": f"b{i}.example.org", "error_stratum": "B",
               "organisation_id": "beta", "tokens": 2, "projects": ""} for i in range(5)]
    items += [{"item_id": f"N{i}", "population": "namespace", "key": f"github.com/n{i}#acme", "error_stratum": "N",
               "organisation_id": "acme", "tokens": "", "projects": 2} for i in range(4)]
    _write(f / "sample.csv", items)
    _write(f / "frame.csv", [{"population": i["population"], "key": i["key"], "error_stratum": i["error_stratum"],
                              "organisation_id": i["organisation_id"]} for i in items])
    if answers:
        _write(f / "answers.csv", [dict({"item_id": "", "verdict": "", "correct_organisation_id": "",
                                         "answered_utc": "2026-10-25T10:00:00Z", "data_sha256": SHA}, **a)
                                   for a in answers])
    return f


def test_binomial_helpers_known_values():
    assert aa.binom_cdf(0, 10, 0.1) == pytest.approx(0.9 ** 10)
    assert aa.binom_sf(1, 10, 0.1) == pytest.approx(1 - 0.9 ** 10)
    assert aa.binom_sf(0, 10, 0.1) == 1.0
    # R: binom.test(1, 15, 0.036)$p.value = 0.4202 (the tail of 1 and more; 0 is more probable)
    assert aa.binom_test(1, 15, 0.036) == pytest.approx(1 - 0.964 ** 15, rel=1e-6)
    assert aa.binom_test(5, 10, 0.5) == pytest.approx(1.0)
    lo, hi = aa.clopper_pearson(0, 30)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** (1 / 30), rel=1e-6)
    lo, hi = aa.clopper_pearson(1, 10)       # R: 0.002528 to 0.445016
    assert lo == pytest.approx(0.002528, abs=1e-6) and hi == pytest.approx(0.445016, abs=1e-6)
    assert aa.jeffreys(0, 62) == pytest.approx(0.5 / 63)
    assert aa.jeffreys_sd(0, 0) == pytest.approx((1 / 8) ** 0.5)
    assert aa.binomial_label(3, 10, 0.01) == "higher than predicted"
    assert aa.binomial_label(0, 100, 0.2) == "lower than predicted"
    assert aa.binomial_label(0, 5, 0.01) == "consistent"
    assert aa.binomial_label(0, 0, 0.01) == "no answer"


def test_latest_answer_wins_and_stale_answers_do_not_count(tmp_path):
    f = _sample(tmp_path, [
        {"item_id": "A0", "verdict": "wrong", "answered_utc": "2026-10-25T09:00:00Z"},
        {"item_id": "A0", "verdict": "right", "answered_utc": "2026-10-25T11:00:00Z"},     # later: wins
        {"item_id": "A1", "verdict": "wrong", "data_sha256": "e" * 64},                   # other database
        {"item_id": "Z9", "verdict": "wrong"},                                             # not in the sample
        {"item_id": "A2", "verdict": ""}])                                                 # no answer
    s = aa.Sample(f)
    assert set(s.answers) == {"A0"} and s.answers["A0"]["verdict"] == "right"
    assert s.stale == 1 and s.unknown == 1
    assert s.frame()["domain"]["a3.example.org"] == ("A", "acme")


def test_stratum_rows_rates_tests_and_unsure_apart(tmp_path):
    ans = [{"item_id": f"A{i}", "verdict": "right"} for i in range(8)]
    ans += [{"item_id": "A8", "verdict": "wrong", "correct_organisation_id": "other"},
            {"item_id": "A9", "verdict": "unsure"}]
    ans += [{"item_id": "B0", "verdict": "wrong", "correct_organisation_id": "beta"},
            {"item_id": "B1", "verdict": "right"}]
    rows = {r["error_stratum"]: r for r in aa.stratum_rows(aa.Sample(_sample(tmp_path, ans)))}
    a = rows["A"]
    assert (a["right"], a["wrong"], a["unsure"], a["n_decided"], a["answered"]) == (8, 1, 1, 9, 10)
    assert a["complete"] and a["rate_pct"] == pytest.approx(100 / 9, abs=1e-3)
    assert a["worst_case_pct"] == pytest.approx(20.0)
    assert a["p_upper"] == pytest.approx(aa.binom_sf(1, 9, 0.01), abs=1e-5)
    assert a["wrong_other_organisation"] == 1 and a["wrong_same_organisation"] == 0
    b = rows["B"]
    assert not b["complete"] and b["n_decided"] == 2 and b["wrong_same_organisation"] == 1
    assert rows["N"]["test"] == "no answer" and rows["N"]["rate_pct"] == ""
    # A given prediction replaces the one of strata.csv.
    rows2 = {r["error_stratum"]: r for r in aa.stratum_rows(aa.Sample(_sample(tmp_path / "x", ans)), {"A": 0.2})}
    assert rows2["A"]["p_pred_pct"] == 20.0


def test_population_estimate_weights_and_coverage(tmp_path):
    (tmp_path / "x").mkdir()
    ans = [{"item_id": f"A{i}", "verdict": "right"} for i in range(10)]
    ans += [{"item_id": "B0", "verdict": "wrong"}, {"item_id": "B1", "verdict": "right"}]
    rows = aa.stratum_rows(aa.Sample(_sample(tmp_path / "x", ans)))
    p = aa.population_estimate(rows, "domain", draws=2000, seed=1)
    # by value: 0.9 x 0 + 0.1 x 1/2; by unit: (100 x 0 + 50 x 1/2) / 150
    assert p["value"]["estimate_pct"] == pytest.approx(5.0)
    assert p["unit"]["estimate_pct"] == pytest.approx(100 * 25 / 150, abs=1e-4)
    assert p["value"]["coverage_pct"] == 100.0 and p["strata_with_answers"] == 2 and p["strata_complete"] == 1
    lo, hi = (float(x) for x in p["value"]["mc95_pct"].split(" to "))
    assert lo < 5.0 < hi
    # design: (100 / 10) x 0 + (50 / 2) x 2 tokens wrong = 50 of 1,000 tokens
    assert p["design_pct"] == pytest.approx(5.0)
    # No answer in a population: no estimate; the prediction fills the strata.
    n = aa.population_estimate(rows, "namespace", draws=100, seed=1)
    assert n["value"]["estimate_pct"] == "" and n["value"]["with_prediction_pct"] == pytest.approx(2.0)


def _round_page(tmp_path: Path, answers: list[dict], sha: str = "f" * 64) -> Path:
    f = tmp_path / "audit-v47"
    (f / "data").mkdir(parents=True)
    items = [{"item_id": f"C{i}", "class": "check", "type": "domain of the new layer", "domain": f"c{i}.example.org"}
             for i in range(6)]
    items += [{"item_id": "U1", "class": "decide", "type": "domain of the new layer", "domain": "U.example.org"},
              {"item_id": "U2", "class": "decide", "type": "namespace of the new layer", "host": "github.com",
               "namespace": "Acme"}]
    (f / "data/items.json").write_text(json.dumps(items))
    (f / "data/meta.json").write_text(json.dumps({"items_sha256": sha}))
    if answers:
        _write(f / "answers.csv", [dict({"item_id": "", "verdict": "", "answered_utc": "2026-10-25T10:00:00Z",
                                         "items_sha256": sha}, **a) for a in answers])
    return f


def test_round_check_counts_the_check_class_only(tmp_path):
    f = _round_page(tmp_path, [{"item_id": "C0", "verdict": "right"}, {"item_id": "C1", "verdict": "right"},
                               {"item_id": "C2", "verdict": "wrong"}, {"item_id": "C3", "verdict": "unsure"},
                               {"item_id": "C4", "verdict": "wrong", "items_sha256": "0" * 64},   # other page
                               {"item_id": "U1", "verdict": "right"}])
    r = aa.round_check(f)
    assert (r["n"], r["k"], r["unsure"], r["stale_answers"]) == (3, 1, 1, 1)
    assert r["q_jeffreys"] == pytest.approx(1.5 / 4)
    assert r["cp"] == pytest.approx(aa.clopper_pearson(1, 3))
    assert r["check_items"] == 6 and r["decide_items"] == 2 and r["decide_answered"] == 1
    assert r["decide_keys"] == {"u.example.org", "github.com/acme"}


def test_round_check_with_no_page_or_no_answer(tmp_path):
    r = aa.round_check(tmp_path / "missing")
    assert not r["exists"] and r["n"] == 0 and r["decide_keys"] == set()
    r = aa.round_check(_round_page(tmp_path, []))
    assert r["exists"] and r["n"] == 0 and r["q_jeffreys"] is None and r["rule3"] == 1.0


def test_report_writes_counts_only(tmp_path):
    ans = [{"item_id": f"A{i}", "verdict": "right"} for i in range(10)]
    res = aa.analyse_sample(_sample(tmp_path, ans), draws=200, seed=1)
    out = tmp_path / "out"
    summary = aa.report(res, [aa.round_check(_round_page(tmp_path, []))], out)
    assert summary["answers"] == 10
    for name in ("audit_strata.csv", "audit_population.csv", "round_checks.csv", "audit_summary.json", "audit.md"):
        text = (out / name).read_text()
        assert "example.org" not in text and "acme" not in text.lower() and aa.AT not in text
