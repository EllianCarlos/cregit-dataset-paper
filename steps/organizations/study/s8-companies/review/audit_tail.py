#!/usr/bin/env python3
"""Tail audit: the audit page items and the estimator of the organisation rate (2026-10-26).

    audit_tail.py build [--folder DIR] [--db companies.v4.8.duckdb]
    audit_tail.py estimate [--folder DIR]

The tail audit (ERROR_MODEL.md section 10a) checks a PPS sample of 60 of the unmatched real mail
domains (the frame and the sample: audit_tail_sample.py). Two AI judges decided the 60 domains with
fetched web evidence (the method of rounds 9 and 10). The user checks all 60 items on the audit page
(hub mount `tail`, folder <ws>/review/audit-tail): right, wrong or unsure, and for wrong the correct
class (company, other organisation, independent, free-provider, none) and the correct organisation.

build     reads FOLDER/sample.csv, FOLDER/out/tail-*.csv (the judge rows), FOLDER/org_index_v48.csv
          and FOLDER/in/tail-*.json, and writes FOLDER/data/items.json and FOLDER/data/meta.json.
estimate  reads FOLDER/data/items.json, FOLDER/answers.csv and FOLDER/design.json and prints the
          estimate (counts only).

The estimator. Each unit gets a class from the AI verdict and the user's answer (unit_class): company,
organisation (another kind), no-organisation (independent, free-provider, none), unsure, or open (no
answer yet, or wrong with no correct class). y = 1 for an organisation of any kind (company included).
With the certainty units C and the systematic PPS points (each with the weight t / pi = step K =
rest_tokens / rest_n), the Horvitz-Thompson (Hansen-Hurwitz) rate is

    R = (sum over C of t y + K x sum over the points of y) / (sum over C of t + K x m),

where only the decided units count (an unsure answer is apart: it leaves both sums) and m is the
number of decided points. With no unsure answer the denominator is the frame tokens. The certainty
units have no sampling error, so R is a monotone function of the point mean p = k / m. The interval
maps the 95% Clopper-Pearson interval of p; the Monte Carlo draws map p ~ Beta(k + 0.5, m - k + 0.5)
(Jeffreys) and the company share among the organisations s ~ Beta(kc + 0.5, k - kc + 0.5), so that
the company rate is never above the organisation rate. The central value is the Jeffreys mean (as for
the audit strata). The bounds of the unsure answers: all of them organisations, or none.

The model (error_model.py, model v4.7) uses the measured rates in place of the type B rates of the
unmatched domains only when the page is complete (each item has an answer). Else the type B rates stay.
No value may hold an at sign. The items hold personal domains: the folder is not in git.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = Path.home() / "Projects/cregit-workspace/companies"
FOLDER_DEFAULT = WS / "review/audit-tail"
AT = chr(64)
COMPANY_KINDS = ("company", "consultancy")
ITEM_PREFIX = "X"
TYPE_CERT = "sampled domain (certainty unit: larger than the sampling step)"
TYPE_POINT = "sampled domain"
# The correct classes that the user can give for a wrong answer, and the class of the estimator.
CORRECT_CLASSES = {"company": "company", "other-organisation": "organisation", "independent": "no-organisation",
                   "free-provider": "no-organisation", "none": "no-organisation"}
AI_CLASSES = dict(CORRECT_CLASSES)        # the class of the AI verdict (ai_class of an item)
ORG_CLASSES = ("company", "organisation")


def clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Exact binomial interval (Beta quantiles by bisection; standard library only)."""
    if n <= 0:
        return 0.0, 1.0
    a = (1 - conf) / 2

    def cdf(x: float, kk: int) -> float:      # P(X <= kk), X ~ Bin(n, x)
        return sum(math.comb(n, i) * x ** i * (1 - x) ** (n - i) for i in range(kk + 1))

    def root(f, lo=0.0, hi=1.0):          # f decreasing on [0, 1]
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid) > 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    lo = 0.0 if k == 0 else root(lambda x: a - (1 - cdf(x, k - 1)))     # P(X >= k) = a
    hi = 1.0 if k == n else root(lambda x: cdf(x, k) - a)              # P(X <= k) = a
    return lo, hi


def ai_class(verdict: str, kind: str) -> str:
    """The class of an AI verdict: company, other-organisation, independent, free-provider, none, unsure."""
    if verdict == "organisation":
        return "company" if kind in COMPANY_KINDS else "other-organisation"
    return verdict if verdict in ("independent", "free-provider", "none") else "unsure"


def unit_class(item: dict, ans: dict | None) -> str:
    """The class of a unit from the AI class of the item and the user's answer.

    right: the AI class (an AI verdict unsure with the answer right gives unsure); wrong: the correct
    class of the answer (none given: open); unsure: unsure; no answer: open."""
    a = ans or {}
    v = a.get("verdict") or ""
    if not v:
        return "open"
    if v == "unsure":
        return "unsure"
    if v == "right":
        return AI_CLASSES.get(item.get("ai_class", ""), "unsure")
    if v == "wrong":
        return CORRECT_CLASSES.get(a.get("correct_class") or "", "open")
    return "open"


def tally(units: list[dict], design: dict, pool: set | None = None) -> dict:
    """The sums of the estimator. units: dicts with unit (certainty or point), tokens, cls, domain.

    pool: the domains of the evaluated E2 pool; a unit outside the pool is out of the domain of the
    estimate (it leaves all sums). None: all units count."""
    K = design["rest_tokens"] / design["rest_n"]
    t = {"K": K, "C_t": 0, "C_o": 0, "C_c": 0, "Cu_t": 0, "m": 0, "k_o": 0, "k_c": 0, "mu": 0, "open": 0,
         "out_of_pool": 0, "n": 0, "unsure": 0}
    for u in units:
        if pool is not None and u.get("domain") not in pool:
            t["out_of_pool"] += 1
            continue
        t["n"] += 1
        cls = u["cls"]
        if cls == "open":
            t["open"] += 1
            continue
        cert = u["unit"] == "certainty"
        if cls == "unsure":
            t["unsure"] += 1
            if cert:
                t["Cu_t"] += u["tokens"]
            else:
                t["mu"] += 1
            continue
        o, c = cls in ORG_CLASSES, cls == "company"
        if cert:
            t["C_t"] += u["tokens"]
            t["C_o"] += u["tokens"] * o
            t["C_c"] += u["tokens"] * c
        else:
            t["m"] += 1
            t["k_o"] += o
            t["k_c"] += c
    t["complete"] = t["open"] == 0 and t["n"] > 0
    return t


def rate_of(t: dict, p: float, cert_y: str = "C_o") -> float:
    """R(p) = (C_y + K m p) / (C_t + K m): the rate for a point mean p."""
    den = t["C_t"] + t["K"] * t["m"]
    return (t[cert_y] + t["K"] * t["m"] * p) / den if den else float("nan")


def central_rates(t: dict) -> tuple[float, float]:
    """(organisation rate, company rate), central values: the Jeffreys means of the point shares."""
    m, ko, kc = t["m"], t["k_o"], t["k_c"]
    po = (ko + 0.5) / (m + 1)
    s = (kc + 0.5) / (ko + 1)
    return rate_of(t, po, "C_o"), rate_of(t, po * s, "C_c")


def draw_rates(t: dict, rng: random.Random) -> tuple[float, float]:
    """One Monte Carlo draw of (organisation rate, company rate)."""
    m, ko, kc = t["m"], t["k_o"], t["k_c"]
    po = rng.betavariate(ko + 0.5, m - ko + 0.5)
    s = rng.betavariate(kc + 0.5, ko - kc + 0.5)
    return rate_of(t, po, "C_o"), rate_of(t, po * s, "C_c")


def estimate(units: list[dict], design: dict, pool: set | None = None) -> dict:
    """The estimate of the organisation and company rates (counts and rates only, no domain)."""
    t = tally(units, design, pool)
    out = dict(t)
    if t["C_t"] + t["m"] == 0:
        out.update(org_rate_ht=None, company_rate_ht=None)
        return out
    m = t["m"]
    out["org_rate_ht"] = rate_of(t, t["k_o"] / m if m else 0.0, "C_o")
    out["company_rate_ht"] = rate_of(t, t["k_c"] / m if m else 0.0, "C_c")
    out["org_rate_central"], out["company_rate_central"] = central_rates(t)
    lo, hi = clopper_pearson(t["k_o"], m) if m else (0.0, 1.0)
    out["org_rate_cp95"] = (rate_of(t, lo, "C_o"), rate_of(t, hi, "C_o"))
    lo, hi = clopper_pearson(t["k_c"], m) if m else (0.0, 1.0)
    out["company_rate_cp95"] = (rate_of(t, lo, "C_c"), rate_of(t, hi, "C_c"))
    # The unsure answers: all of them organisations (upper) or none (lower).
    K, mu = t["K"], t["mu"]
    den = t["C_t"] + t["Cu_t"] + K * (m + mu)
    out["org_rate_unsure_bounds"] = ((t["C_o"] + K * t["k_o"]) / den, (t["C_o"] + t["Cu_t"] + K * (t["k_o"] + mu)) / den)
    return out


def read_answers(folder: Path) -> dict:
    p = Path(folder) / "answers.csv"
    if not p.is_file():
        return {}
    with open(p, newline="", encoding="utf-8") as fh:
        return {r["item_id"]: r for r in csv.DictReader(fh) if r.get("item_id")}


def load(folder: Path) -> tuple[list[dict], dict, dict]:
    """(items, design, answers) of a tail audit folder."""
    folder = Path(folder)
    items = json.loads((folder / "data/items.json").read_text(encoding="utf-8"))
    design = json.loads((folder / "design.json").read_text(encoding="utf-8"))
    return items, design, read_answers(folder)


def units_of(items: list[dict], answers: dict) -> list[dict]:
    return [{"domain": i["domain"], "unit": i["unit"], "tokens": i["tokens"], "cls": unit_class(i, answers.get(i["item_id"]))}
            for i in items]


def analyse(folder: Path, pool: set | None = None) -> dict:
    """The estimate of a folder, with the answer counts and the frame checksum of the design."""
    items, design, answers = load(folder)
    units = units_of(items, answers)
    est = estimate(units, design, pool)
    est.update(items=len(items), answered=sum(1 for i in items if (answers.get(i["item_id"]) or {}).get("verdict")),
               frame_sha256=design["frame_sha256"], frame_tokens=design["frame_tokens"], frame_n=design["frame_n"],
               by_class={c: sum(1 for u in units if u["cls"] == c) for c in
                         ("company", "organisation", "no-organisation", "unsure", "open")})
    return est


# --------------------------------------------------------------------------------------------
# The page items
# --------------------------------------------------------------------------------------------

def clean(s) -> str:
    s = "" if s is None else str(s)
    return s.replace(AT, " ")


def check_no_at(obj) -> None:
    if AT in json.dumps(obj, ensure_ascii=False):
        raise SystemExit("an at sign in the items: stop")


def parse_new_row(s: str) -> dict:
    p = (s or "").split("|")
    if len(p) < 3 or not p[0]:
        return {}
    p += [""] * (5 - len(p))
    return {"id": p[0], "name": p[1], "kind": p[2], "parent": p[3], "country": p[4]}


def build_items(sample: list[dict], judged: dict, index: dict, inputs: dict) -> list[dict]:
    """One item per sampled domain, in sample order (certainty units first)."""
    items = []
    for n, s in enumerate(sample, 1):
        j = judged.get(s["sample_id"]) or {}
        v = (j.get("verdict") or "unsure").strip()
        oid = (j.get("org_id") or "").strip()
        nr = parse_new_row(j.get("new_row", ""))
        org = {}
        if oid.startswith("new:"):
            org = {"id": oid, "name": nr.get("name", ""), "kind": nr.get("kind", ""), "parent": nr.get("parent", ""),
                   "country": nr.get("country", ""), "new": True}
        elif oid:
            r = index.get(oid) or {}
            org = {"id": oid, "name": r.get("name", ""), "kind": r.get("kind", ""), "parent": r.get("parent_company_id", ""),
                   "domains": r.get("domains", ""), "new": False, "in_index": bool(r)}
        kind = org.get("kind", "") if v == "organisation" else ""
        inp = inputs.get(s["sample_id"]) or {}
        dns = inp.get("dns")
        items.append({
            "item_id": f"{ITEM_PREFIX}{n:04d}", "sample_id": s["sample_id"], "domain": s["domain"], "title": s["domain"],
            "type": TYPE_CERT if s["unit"] == "certainty" else TYPE_POINT, "class": "check",
            "unit": s["unit"], "pi": float(s["pi"]), "tokens": int(s["tokens"]), "part": s["part"],
            "tokens_v1": int(s["tokens_v1"]), "tokens_x1k": int(s["tokens_x1k"]),
            "n_projects": int(s["dataset_projects"]), "top_project": s["top_project"],
            "commits_x1k": s.get("commits_x1k", ""), "authors_x1k": s.get("authors_x1k", ""),
            "earlier_review": clean(inp.get("earlier_review", "")),
            "ai_verdict": v, "ai_class": ai_class(v, kind), "confidence": j.get("confidence", ""),
            "organisation": org, "note": clean(j.get("note", "")),
            "sources": [u.strip() for u in (j.get("evidence_urls") or "").split(" ; ") if u.strip()],
            "dns": dns if isinstance(dns, dict) else {}, "judge_chunk": j.get("_chunk", ""),
            "files": [f"review/audit-tail/out/{j.get('_chunk', '')}.csv", "review/audit-tail/sample.csv"],
        })
    return items


def build(folder: Path) -> dict:
    folder = Path(folder)
    with open(folder / "sample.csv", newline="", encoding="utf-8") as fh:
        sample = list(csv.DictReader(fh))
    judged = {}
    for p in sorted((folder / "out").glob("tail-*.csv")):
        with open(p, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                r["_chunk"] = p.stem
                judged[r["item_id"]] = r
    inputs = {}
    for p in sorted((folder / "in").glob("tail-*.json")):
        for r in json.loads(p.read_text(encoding="utf-8")):
            inputs[r["item_id"]] = r
    with open(folder / "org_index_v48.csv", newline="", encoding="utf-8") as fh:
        index = {r["company_id"]: r for r in csv.DictReader(fh)}
    missing = [s["sample_id"] for s in sample if s["sample_id"] not in judged]
    if missing:
        raise SystemExit(f"{len(missing)} sampled domains have no judge row")
    items = build_items(sample, judged, index, inputs)
    design = json.loads((folder / "design.json").read_text(encoding="utf-8"))
    meta = {"generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "n_items": len(items),
            "counts": {"items": len(items), "certainty_units": sum(i["unit"] == "certainty" for i in items),
                       "ai_verdicts": {v: sum(i["ai_verdict"] == v for i in items) for v in
                                       sorted({i["ai_verdict"] for i in items})}},
            "by_type": {t: sum(1 for i in items if i["type"] == t) for t in sorted({i["type"] for i in items})},
            "design": {k: design[k] for k in ("frame_n", "frame_tokens", "n", "certainty_n", "rest_n", "step", "frame_sha256")},
            "inputs": {"sample_csv_sha256": hashlib.sha256((folder / "sample.csv").read_bytes()).hexdigest(),
                       "judge_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in sorted((folder / "out").glob("tail-*.csv"))}}}
    check_no_at(items)
    check_no_at(meta)
    data = folder / "data"
    data.mkdir(parents=True, exist_ok=True)
    body = json.dumps(items, ensure_ascii=False, indent=1)
    meta["items_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    (data / "items.json").write_text(body, encoding="utf-8")
    (data / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=("build", "estimate"))
    ap.add_argument("--folder", type=Path, default=FOLDER_DEFAULT)
    a = ap.parse_args(argv)
    if a.what == "build":
        meta = build(a.folder)
        print(json.dumps(meta["counts"]), f"-> {a.folder}/data/")
    else:
        est = analyse(a.folder)
        print(json.dumps({k: v for k, v in est.items()}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
