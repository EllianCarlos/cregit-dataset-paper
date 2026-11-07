#!/usr/bin/env python3
"""Analysis of the audit answers and of the check samples of the AI rounds (2026-10-25).

    audit_analysis.py [--ws DIR] [--sample DIR] [--round DIR ...] [--out DIR]
                      [--draws 20000] [--seed 20261025]

The script reads the answer files at the time of the run, so a run after the last answer gives the
final values with no change of code.

1. The stratified audit sample (AUDIT_SAMPLE.md, "Analysis after the audit"; default
   <ws>/review/audit-sample-v4.6): strata.csv, sample.csv, frame.csv, meta.json and answers.csv.
   For each stratum h:
     - the error rate k_h / n_h, where n_h counts the answers right and wrong (not unsure);
     - the 95% Clopper-Pearson interval and the Jeffreys mean (k + 0.5) / (n + 1);
     - an exact binomial test against the predicted error of the stratum (p_pred_links_pct of
       strata.csv): the upper tail P(X >= k), the lower tail P(X <= k) and the two-sided p value;
     - the unsure answers apart, and the worst case (k + unsure) / (n + unsure).
   For each population (domains, namespaces), the column error: each stratum weighted by its share
   of the tokens (domains) or of the dataset projects (namespaces) (strata.csv weight_share_pct),
   and the design-based estimate with the design weight N_h / n_h on the items with an answer.
   Interval: a Monte Carlo of the Jeffreys posterior of each stratum (JCGM 101:2008), and the
   stratified standard error with the finite population correction.
2. The check sample of an AI round (default <ws>/review/audit-v47, round 10; more with --round):
   data/items.json (class check: a seeded 10% sample of the decided rows; class decide: the rows that
   the AI could not decide) and answers.csv. The error q of one AI answer of the round: k wrong of n
   (right + wrong) answers of class check; central value the Jeffreys mean, 95% Clopper-Pearson
   interval. The rows of class decide are user decisions (they are counted, not used for q).

Answers are read only. An answer of the sample whose data_sha256 is not the data_sha256 of meta.json
(an answer on another database) does not count; nor does an answer of a check page whose items_sha256
is not that of data/meta.json. The outputs (--out, default <ws>/review/audit-analysis) hold counts
only: no domain, no namespace, no organisation id, no item key. No value may hold an at sign.
error_model.py imports this module.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

WS_DEFAULT = Path.home() / "Projects/cregit-workspace/companies"
SAMPLE_DEFAULT = "review/audit-sample-v4.6"
ROUNDS_DEFAULT = ("review/audit-v47",)
VERDICTS = ("right", "wrong", "unsure")
AT = chr(64)        # the at sign; no file of this study holds it literally
ALPHA = 0.05


# --------------------------------------------------------------------------------------------
# Statistics (pure functions)
# --------------------------------------------------------------------------------------------

def binom_pmf(i: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 1.0 if i == 0 else 0.0
    if p >= 1.0:
        return 1.0 if i == n else 0.0
    return math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1)
                    + i * math.log(p) + (n - i) * math.log1p(-p))


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if k < 0:
        return 0.0
    return min(1.0, sum(binom_pmf(i, n, p) for i in range(0, min(k, n) + 1)))


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if k <= 0:
        return 1.0
    return min(1.0, sum(binom_pmf(i, n, p) for i in range(k, n + 1)))


def binom_test(k: int, n: int, p: float) -> float:
    """Exact two-sided binomial test: the sum of the outcomes not more probable than k (as R binom.test)."""
    if n <= 0:
        return 1.0
    d = binom_pmf(k, n, p) * (1 + 1e-7)
    return min(1.0, sum(q for q in (binom_pmf(i, n, p) for i in range(n + 1)) if q <= d))


def clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Clopper and Pearson (1934) exact two-sided interval of k/n (bisection)."""
    if n <= 0:
        return (0.0, 1.0)
    a = (1 - conf) / 2

    def root(f) -> float:
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
        return (lo + hi) / 2
    low = 0.0 if k == 0 else root(lambda p: a - binom_sf(k, n, p))
    high = 1.0 if k == n else root(lambda p: binom_cdf(k, n, p) - a)
    return (low, high)


def jeffreys(k: float, n: float) -> float:
    """Mean of the Jeffreys posterior Beta(k + 1/2, n - k + 1/2)."""
    return (k + 0.5) / (n + 1)


def jeffreys_sd(k: float, n: float) -> float:
    a, b = k + 0.5, n - k + 0.5
    return math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))


def binomial_label(k: int, n: int, p: float) -> str:
    """'higher' or 'lower' than the prediction at the 5% level (one tail each), else 'consistent'."""
    if n <= 0:
        return "no answer"
    if binom_sf(k, n, p) < ALPHA:
        return "higher than predicted"
    if binom_cdf(k, n, p) < ALPHA:
        return "lower than predicted"
    return "consistent"


# --------------------------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def latest_answers(rows: list[dict]) -> dict:
    """item_id -> the last answer (largest answered_utc; at equal times the later row)."""
    out = {}
    for i, r in enumerate(rows):
        iid = r.get("item_id") or ""
        if not iid:
            continue
        key = (r.get("answered_utc") or "", i)
        if iid not in out or key >= out[iid][0]:
            out[iid] = (key, r)
    return {k: v[1] for k, v in out.items()}


def fnum(x, default=0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


class Sample:
    """The audit sample of one folder (strata, items, frame, answers)."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.meta = json.loads((self.folder / "meta.json").read_text())
        self.strata = {r["error_stratum"]: r for r in read_csv(self.folder / "strata.csv")}
        self.items = {r["item_id"]: r for r in read_csv(self.folder / "sample.csv")}
        ans = self.folder / "answers.csv"
        rows = read_csv(ans) if ans.exists() else []
        self.answers, self.stale, self.unknown = {}, 0, 0
        for iid, r in latest_answers(rows).items():
            if iid not in self.items:
                self.unknown += 1
                continue
            if r.get("data_sha256") and r["data_sha256"] != self.meta.get("data_sha256"):
                self.stale += 1
                continue
            if (r.get("verdict") or "") in VERDICTS:
                self.answers[iid] = r

    def frame(self) -> dict:
        """population -> {lower key: (stratum, organisation id)} of the frame (all units)."""
        out = defaultdict(dict)
        for r in read_csv(self.folder / "frame.csv"):
            out[r["population"]][r["key"].lower()] = (r["error_stratum"], r["organisation_id"])
        return dict(out)


# --------------------------------------------------------------------------------------------
# Analysis of the sample
# --------------------------------------------------------------------------------------------

def stratum_rows(s: Sample, predicted: dict | None = None) -> list[dict]:
    """One row per stratum. predicted: stratum -> predicted unit error (share); default strata.csv."""
    cnt = defaultdict(Counter)
    tok = defaultdict(lambda: [0.0, 0.0])        # the weight of the items with a decided answer, of the wrong ones
    for iid, a in s.answers.items():
        it = s.items[iid]
        h = it["error_stratum"]
        v = a["verdict"]
        cnt[h][v] += 1
        if v == "wrong":
            oid = (a.get("correct_organisation_id") or "").strip()
            cnt[h]["wrong_same_org" if oid and oid == it.get("organisation_id") else "wrong_org"] += 1
        if v in ("right", "wrong"):
            w = fnum(it.get("tokens")) if it["population"] == "domain" else fnum(it.get("projects"))
            tok[h][0] += w
            tok[h][1] += w if v == "wrong" else 0.0
    planned = Counter(it["error_stratum"] for it in s.items.values())
    out = []
    for h, st in sorted(s.strata.items()):
        c = cnt[h]
        k, n, u = c["wrong"], c["right"] + c["wrong"], c["unsure"]
        p_pred = (predicted or {}).get(h, fnum(st.get("p_pred_links_pct")) / 100)
        lo, hi = clopper_pearson(k, n) if n else (0.0, 1.0)
        answered = n + u
        out.append({
            "error_stratum": h, "population": st["population"], "origin": st.get("origin", ""),
            "band": st.get("band", ""), "class": st.get("class", ""), "match": st.get("match", ""),
            "evidence": st.get("evidence", ""), "owner_kind": st.get("owner_kind", ""),
            "units": int(fnum(st["units"])), "n_sample": planned[h], "answered": answered,
            "complete": answered == planned[h] and planned[h] > 0,
            "right": c["right"], "wrong": k, "unsure": u, "n_decided": n,
            "wrong_other_organisation": c["wrong_org"], "wrong_same_organisation": c["wrong_same_org"],
            "rate_pct": round(100 * k / n, 4) if n else "",
            "cp_lo_pct": round(100 * lo, 4), "cp_hi_pct": round(100 * hi, 4),
            "jeffreys_pct": round(100 * jeffreys(k, n), 4) if n else "",
            "worst_case_pct": round(100 * (k + u) / (n + u), 4) if n + u else "",
            "p_pred_pct": round(100 * p_pred, 4),
            "p_upper": round(binom_sf(k, n, p_pred), 5) if n else "",
            "p_lower": round(binom_cdf(k, n, p_pred), 5) if n else "",
            "p_two_sided": round(binom_test(k, n, p_pred), 5) if n else "",
            "test": binomial_label(k, n, p_pred),
            "weight": fnum(st.get("weight")), "weight_unit": st.get("weight_unit", ""),
            "weight_share_pct": fnum(st.get("weight_share_pct")),
            "decided_weight": tok[h][0], "wrong_weight": tok[h][1],
        })
    return out


def population_estimate(rows: list[dict], population: str, draws: int = 20000, seed: int = 20261025) -> dict:
    """The column error of one population from the strata rows (stratum_rows).

    by value: each stratum weighted by its share of the tokens or projects (weight_share_pct);
    by unit: each stratum weighted by N_h / N (the share of database rows);
    design: sum_h (N_h / n_h) sum_i w_i e_i over the items with a decided answer, divided by the
      weight of the strata with an answer (Horvitz-Thompson within the stratum).
    Each value is given for the strata with a decided answer (coverage: their share of the weight).
    'with prediction' fills the strata with no answer with the predicted error (p_pred_pct).
    Monte Carlo: Beta(k + 1/2, n - k + 1/2) for each stratum with an answer, the prediction fixed
    for the others; the 95% interval is the 2.5 and 97.5 percentiles."""
    rs = [r for r in rows if r["population"] == population]
    tot_w = sum(r["weight"] for r in rs)
    tot_n = sum(r["units"] for r in rs)
    ans = [r for r in rs if r["n_decided"] > 0]
    out = {"population": population, "strata": len(rs), "strata_with_answers": len(ans),
           "strata_complete": sum(r["complete"] for r in rs),
           "items": sum(r["n_sample"] for r in rs), "answered": sum(r["answered"] for r in rs),
           "decided": sum(r["n_decided"] for r in rs), "wrong": sum(r["wrong"] for r in rs),
           "unsure": sum(r["unsure"] for r in rs)}
    for basis, wf, tot in (("value", lambda r: r["weight"], tot_w), ("unit", lambda r: r["units"], tot_n)):
        cov_w = sum(wf(r) for r in ans)
        cov = cov_w / tot if tot else 0.0
        est = sum(wf(r) * r["wrong"] / r["n_decided"] for r in ans) / cov_w if cov_w else None
        fill = (sum(wf(r) * r["wrong"] / r["n_decided"] for r in ans)
                + sum(wf(r) * r["p_pred_pct"] / 100 for r in rs if r["n_decided"] == 0)) / tot if tot else None
        var = 0.0
        for r in ans:
            n, N = r["n_decided"], r["units"]
            p = r["wrong"] / n
            if n > 1:
                var += (wf(r) / cov_w) ** 2 * (1 - min(1.0, n / N)) * p * (1 - p) / (n - 1)
        rng = random.Random(seed)
        sims, sims_fill = [], []
        for _ in range(draws):
            a = sum(wf(r) * rng.betavariate(r["wrong"] + 0.5, r["n_decided"] - r["wrong"] + 0.5) for r in ans)
            sims.append(a / cov_w if cov_w else 0.0)
            sims_fill.append((a + sum(wf(r) * r["p_pred_pct"] / 100 for r in rs if r["n_decided"] == 0)) / tot
                             if tot else 0.0)
        sims.sort()
        sims_fill.sort()
        lo, hi = int(0.025 * draws), int(0.975 * draws) - 1
        out[basis] = {
            "coverage_pct": round(100 * cov, 4),
            "estimate_pct": round(100 * est, 5) if est is not None else "",
            "se_pct": round(100 * math.sqrt(var), 5) if ans else "",
            "mc_mean_pct": round(100 * statistics.mean(sims), 5) if ans else "",
            "mc95_pct": f"{round(100 * sims[lo], 5)} to {round(100 * sims[hi], 5)}" if ans else "",
            "with_prediction_pct": round(100 * fill, 5) if fill is not None else "",
            "with_prediction_mc95_pct": f"{round(100 * sims_fill[lo], 5)} to {round(100 * sims_fill[hi], 5)}",
        }
    # Horvitz-Thompson within the strata with an answer: sum_h (N_h / n_h) sum_i w_i e_i / W_covered.
    ht_num = sum(r["units"] / r["n_decided"] * r["wrong_weight"] for r in ans)
    cov_w = sum(r["weight"] for r in ans)
    out["design_pct"] = round(100 * ht_num / cov_w, 5) if cov_w else ""
    return out


def analyse_sample(folder: Path, draws: int = 20000, seed: int = 20261025, predicted: dict | None = None) -> dict:
    s = Sample(folder)
    rows = stratum_rows(s, predicted)
    pops = [population_estimate(rows, p, draws, seed) for p in ("domain", "namespace")]
    return {"folder": str(folder), "data_sha256": s.meta.get("data_sha256", ""), "items": len(s.items),
            "answers": len(s.answers), "stale_answers": s.stale, "unknown_answers": s.unknown,
            "strata": rows, "populations": pops, "sample": s}


# --------------------------------------------------------------------------------------------
# Check samples of the AI rounds
# --------------------------------------------------------------------------------------------

def item_keys(i: dict) -> set:
    """The lower keys of a check-page item: its domain, and host/namespace."""
    keys = set()
    if i.get("domain"):
        keys.add(str(i["domain"]).lower())
    if i.get("host") and i.get("namespace"):
        keys.add(f"{i['host']}/{i['namespace']}".lower())
    return keys


def round_check(folder: Path) -> dict:
    """Counts of an AI round check page; q of one AI answer from its class check (Jeffreys, Clopper-Pearson)."""
    folder = Path(folder)
    ip, mp, ap = folder / "data/items.json", folder / "data/meta.json", folder / "answers.csv"
    if not ip.exists():
        return {"folder": folder.name, "exists": False, "n": 0, "k": 0, "unsure": 0, "decide_keys": set(),
                "decide_items": 0, "decide_answered": 0, "check_items": 0, "by_type": {}}
    items = {i["item_id"]: i for i in json.loads(ip.read_text(encoding="utf-8"))}
    sha = json.loads(mp.read_text()).get("items_sha256", "") if mp.exists() else ""
    cnt = defaultdict(Counter)
    stale = 0
    for iid, r in latest_answers(read_csv(ap) if ap.exists() else []).items():
        i = items.get(iid)
        if i is None:
            continue
        if sha and r.get("items_sha256") and r["items_sha256"] != sha:
            stale += 1
            continue
        v = r.get("verdict") or ""
        if v in VERDICTS:
            cnt[(i.get("class"), i.get("type"))][v] += 1
    check = Counter()
    by_type = {}
    for (cls, typ), c in sorted(cnt.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        by_type[f"{cls}: {typ}"] = dict(c)
        if cls == "check":
            check.update(c)
    k, n = check["wrong"], check["right"] + check["wrong"]
    decide = [i for i in items.values() if i.get("class") == "decide"]
    keys = set()
    for i in decide:
        keys |= item_keys(i)
    lo, hi = clopper_pearson(k, n) if n else (0.0, 1.0)
    return {"folder": folder.name, "exists": True, "items_sha256": sha, "stale_answers": stale,
            "check_items": sum(1 for i in items.values() if i.get("class") == "check"),
            "decide_items": len(decide), "decide_answered": sum(sum(c.values()) for (cl, _), c in cnt.items() if cl == "decide"),
            "right": check["right"], "wrong": k, "unsure": check["unsure"], "n": n, "k": k,
            "q_jeffreys": jeffreys(k, n) if n else None, "cp": (lo, hi),
            "rule3": 3 / n if n else 1.0, "by_type": by_type, "decide_keys": keys}


# --------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------

STRATUM_COLS = ["error_stratum", "population", "origin", "band", "class", "match", "evidence", "owner_kind",
                "units", "n_sample", "answered", "complete", "right", "wrong", "unsure", "n_decided",
                "wrong_other_organisation", "wrong_same_organisation", "rate_pct", "cp_lo_pct", "cp_hi_pct",
                "jeffreys_pct", "worst_case_pct", "p_pred_pct", "p_upper", "p_lower", "p_two_sided", "test",
                "weight_unit", "weight_share_pct"]


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def population_rows(pops: list[dict]) -> list[dict]:
    out = []
    for p in pops:
        for basis in ("value", "unit"):
            b = p[basis]
            out.append({"population": p["population"],
                        "weight": ("tokens" if p["population"] == "domain" else "dataset projects") if basis == "value"
                        else "database rows",
                        "strata": p["strata"], "strata_with_answers": p["strata_with_answers"],
                        "strata_complete": p["strata_complete"], "items": p["items"], "answered": p["answered"],
                        "decided": p["decided"], "wrong": p["wrong"], "unsure": p["unsure"], **b,
                        "design_pct": p["design_pct"] if basis == "value" else ""})
    return out


def report(res: dict, rounds: list[dict], out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "audit_strata.csv", res["strata"], STRATUM_COLS)
    prow = population_rows(res["populations"])
    write_csv(out / "audit_population.csv", prow, list(prow[0].keys()) if prow else ["population"])
    rrows = [{"page": r["folder"], "check_items": r["check_items"], "right": r.get("right", 0), "wrong": r["k"],
              "unsure": r["unsure"], "n": r["n"],
              "q_jeffreys_pct": round(100 * r["q_jeffreys"], 4) if r.get("q_jeffreys") is not None else "",
              "cp95_pct": f"{round(100 * r['cp'][0], 4)} to {round(100 * r['cp'][1], 4)}" if r["n"] else "",
              "decide_items": r["decide_items"], "decide_answered": r["decide_answered"]} for r in rounds]
    write_csv(out / "round_checks.csv", rrows, list(rrows[0].keys()) if rrows else ["page"])
    summary = {"sample": Path(res["folder"]).name, "data_sha256": res["data_sha256"], "items": res["items"],
               "answers": res["answers"], "stale_answers": res["stale_answers"],
               "unknown_answers": res["unknown_answers"], "populations": res["populations"],
               "rounds": [{k: v for k, v in r.items() if k not in ("decide_keys",)} for r in rounds]}
    body = json.dumps(summary, indent=1, sort_keys=True, default=list)
    md = ["# Audit analysis (counts only; interim until every stratum is complete)", "",
          f"Sample {summary['sample']}: {res['answers']} of {res['items']} items answered "
          f"({res['stale_answers']} answers on another database not counted).", "",
          "## Strata", "", md_table(res["strata"], ["error_stratum", "units", "n_sample", "answered", "right", "wrong",
                                                       "unsure", "rate_pct", "cp_lo_pct", "cp_hi_pct", "p_pred_pct",
                                                       "p_upper", "p_two_sided", "test", "weight_share_pct"]),
          "", "## Column error", "", md_table(prow), "", "## AI round checks", "", md_table(rrows)]
    text = "\n".join(md) + "\n"
    for name, t in (("audit_summary.json", body), ("audit.md", text)):
        if AT in t:
            raise SystemExit(f"{name}: a value holds an at sign")
        (out / name).write_text(t, encoding="utf-8")
    for name in ("audit_strata.csv", "audit_population.csv", "round_checks.csv"):
        if AT in (out / name).read_text(encoding="utf-8"):
            raise SystemExit(f"{name}: a value holds an at sign")
    return summary


def md_table(rows: list[dict], cols: list[str] | None = None) -> str:
    if not rows:
        return "(none)"
    cols = cols or list(rows[0].keys())
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ws", type=Path, default=WS_DEFAULT)
    ap.add_argument("--sample", type=Path, help=f"the audit sample folder (default <ws>/{SAMPLE_DEFAULT})")
    ap.add_argument("--round", type=Path, action="append",
                    help=f"an AI round check page (default <ws>/{ROUNDS_DEFAULT[0]}); repeat for more")
    ap.add_argument("--out", type=Path, help="default <ws>/review/audit-analysis")
    ap.add_argument("--draws", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=20261025)
    a = ap.parse_args(argv)
    res = analyse_sample(a.sample or a.ws / SAMPLE_DEFAULT, a.draws, a.seed)
    rounds = [round_check(p) for p in (a.round or [a.ws / r for r in ROUNDS_DEFAULT])]
    summary = report(res, rounds, a.out or a.ws / "review/audit-analysis")
    print(json.dumps({k: summary[k] for k in ("sample", "items", "answers", "stale_answers")}, indent=1))
    for p in summary["populations"]:
        print(p["population"], {k: p[k] for k in ("decided", "wrong", "unsure", "strata_complete")},
              {b: {k: p[b][k] for k in ("coverage_pct", "estimate_pct", "mc95_pct")} for b in ("value", "unit")})
    for r in summary["rounds"]:
        print(r["folder"], {k: r.get(k) for k in ("n", "k", "unsure", "decide_items", "decide_answered")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
