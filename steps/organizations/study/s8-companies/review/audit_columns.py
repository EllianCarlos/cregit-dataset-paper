#!/usr/bin/env python3
"""Column audit: the page items, the carried answers and the estimator of both columns (2026-10-26).

    audit_columns.py build [--folder DIR] [--db companies.v4.9.duckdb] [--links DIR]
    audit_columns.py estimate [--folder DIR] [--draws 4000]

The column audit measures the error of the two organisation columns of the dataset: the namespace
column (firm_based_on_namespace) and the author e-mail domain column (firm_based_on_domain). The
frames and the stratified samples come from audit_columns_sample.py (FOLDER/design.json,
FOLDER/ns/sample.csv, FOLDER/dom/sample.csv). Each part is one page of the audit hub: mount col-ns
(folder FOLDER/ns) and mount col-dom (folder FOLDER/dom).

build     writes FOLDER/<part>/data/items.json and meta.json, copies the page (audit_columns.html)
          and the server (audit_columns_serve.py as serve_columns.py) into each part folder, and adds
          the carried answers to FOLDER/<part>/answers.csv. A carried answer is an earlier answer of
          the user (audits sample46, v47, v48, tail) to the same question: the same namespace or
          domain AND the same organisation and kind now. Its field carried names the audit and the
          item. The user sees it on the page and can change it. An answer that is in answers.csv
          already stays: build never overwrites an answer.
estimate  prints the estimate of both parts (counts and rates only, no domain).

The answers. Namespace: right (the organisation owns the namespace), wrong with the correct class
(other-organisation, independent, project, unknown), or unsure. Domain: right, wrong with the
correct class (company, other-organisation, independent, free-provider, none) and the part that is
wrong (organisation, or only the kind), or unsure. A wrong answer with no class is open.

The wrong share y of a unit. Namespace: y = 1 for wrong. Domain: y = 1 when the column names the
wrong organisation: a wrong answer for a linked domain (part organisation), or for a domain with no
link (value independent) a correct class of an organisation (company or other-organisation). A wrong
answer for only the kind is a kind error (y_kind = 1), not an organisation error. The model of
error_model.py uses the same definition: an unmatched domain is wrong only for the tokens of an
organisation.

The estimator. Each stratum h reduces to a linear form R_h = A_h + B_h p_h, with p_h = k_h / n_h the
observed wrong share of its sampled part (n_h the effective size, k_h the effective wrong count) and
the finite-population correction fpc_h = 1 - n_h / N_h:
  - a certainty stratum (all units): B = 0, A = the weighted share of the answered units;
  - a stratified simple random stratum (namespace part): the ratio estimator, A = 0, B = 1, with the
    Kish effective size n = (sum w)^2 / sum w^2 of the answered units and k = n x the weighted share;
  - a PPS stratum (domain part): the certainty units C of the stratum and the points with the weight
    K = rest_tokens / rest_n: R_h = (sum_C t y + K M p) / (sum_C t + K M), M the answered points, n = M.
The central value is the design-weighted observed rate sum W_h R_h / sum W_h over the strata with
answers (W_h = the projects or the tokens of the stratum). It has no prior: with 0 wrong answers it
is 0. The 95% interval is a stratified Clopper-Pearson interval with the effective size of each
stratum (the effective-size form of Korn and Graubard 1998), by Monte Carlo: the lower limit is the
2.5 percentile of sum W_h (A_h + B_h p_h) / sum W_h with p_h from Beta(k_h, n_h - k_h + 1) (0 when
k_h = 0), the upper limit the 97.5 percentile with p_h from Beta(k_h + 1, n_h - k_h). The fpc scales
the distance of each draw from the observed share. With 0 wrong answers the lower limit is 0 and the
upper limit is above 0. An unsure answer is unknown, not right: with f the wrong share of the unsure
units, the estimate has the range f = 0 (all right) to f = 1 (all wrong), and the central value takes
f = 0.5. The Monte Carlo draws take f ~ Uniform(0, 1) (one f for all unsure units: a rectangular
term). sd is the standard deviation of all draws of both limits. The estimate counts the carried
answers apart.

error_model.py (option --column-audit) uses the measured rates in place of the model terms of a
column only when its part has at least 440 decided answers (USE_MIN); else it reports the partial
state and keeps the model values. No value may hold an at sign. The items hold personal domains:
the folder is not in git.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import shutil
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(1, str(HERE))

WS = Path.home() / "Projects/cregit-workspace/companies"
FOLDER_DEFAULT = WS / "review/audit-columns-v4.9"
LINKS_DEFAULT = Path.home() / "Projects/cregit-workspace/final-work/dataset-final-2/m0/links-final"
AT = chr(64)
USE_MIN = 440            # decided answers of a part before the model uses its measured rates (user decision)
TARGETS = (440, 800)
PARTS = ("ns", "dom")
COMPANY_KINDS = ("company", "consultancy")
PSEUDO = ("independent", "free-provider")
NS_CLASSES = ("other-organisation", "independent", "project", "unknown")
DOM_CLASSES = ("company", "other-organisation", "independent", "free-provider", "none")
ORG_CLASSES = ("company", "other-organisation")
COLS = ["item_id", "part", "type", "title", "verdict", "correct_class", "wrong_part", "correct_org", "note",
        "carried", "answered_utc", "items_sha256"]
CERT = "00 largest by tokens (certainty)"
AFTER_RE = re.compile(r"^(.*) \(([^,()]+), ([^,()]+)\)$")


def check_no_at(obj) -> None:
    if AT in json.dumps(obj, ensure_ascii=False, default=str):
        raise SystemExit("an at sign in the output: stop")


def clean(s) -> str:
    return ("" if s is None else str(s)).replace(AT, " ")


def read_csv(path: Path) -> list[dict]:
    if not Path(path).is_file():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_answers(folder: Path) -> dict:
    return {r["item_id"]: r for r in read_csv(Path(folder) / "answers.csv") if r.get("item_id")}


def write_answers(folder: Path, rows: dict) -> None:
    p = Path(folder) / "answers.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for k in sorted(rows):
            w.writerow({c: ("" if AT in (rows[k].get(c) or "") else rows[k].get(c) or "") for c in COLS})


# --------------------------------------------------------------------------------------------
# The class of a unit from its answer
# --------------------------------------------------------------------------------------------

def answer_state(part: str, ans: dict | None) -> str:
    """decided, unsure or open."""
    a = ans or {}
    v = a.get("verdict") or ""
    if v == "right":
        return "decided"
    if v == "unsure":
        return "unsure"
    if v == "wrong":
        classes = NS_CLASSES if part == "ns" else DOM_CLASSES
        return "decided" if (a.get("correct_class") or "") in classes else "open"
    return "open"


def y_values(part: str, item: dict, ans: dict | None) -> dict:
    """The 0/1 values of a decided unit: wrong (organisation error), kind (kind-only error) and
    company (the true class is company or consultancy). None for an unsure or open unit."""
    if answer_state(part, ans) != "decided":
        return {}
    a = ans or {}
    wrong = a.get("verdict") == "wrong"
    if part == "ns":
        return {"wrong": int(wrong)}
    shown_company = item.get("kind") in COMPANY_KINDS
    if not wrong:
        return {"wrong": 0, "kind": 0, "company": int(shown_company)}
    cls = a.get("correct_class") or ""
    true_company = int(cls == "company")
    if (a.get("wrong_part") or "organisation") == "kind" and item.get("state") == "linked":
        return {"wrong": 0, "kind": 1, "company": true_company}
    if item.get("state") == "unmatched" or item.get("kind") in PSEUDO:
        # The column gives a pseudo value (independent or free-provider): wrong only for an organisation.
        return {"wrong": int(cls in ORG_CLASSES), "kind": 0, "company": true_company}
    return {"wrong": 1, "kind": 0, "company": true_company}


# --------------------------------------------------------------------------------------------
# The estimator
# --------------------------------------------------------------------------------------------

def stratum_forms(part: str, items: list[dict], answers: dict, design: dict, yname: str, weight: str,
                  state: str | None = None) -> list[dict]:
    """For each stratum with answers: the weight W and a function f -> (A, B, k, n, fpc), plus counts.

    The rate of the stratum is A + B p, with p the wrong share k / n of its sampled part (n the
    effective size, k the effective wrong count) and fpc the finite-population correction of p.

    state (domain part): the share of the frame rate that comes from the domains of one state (linked
    or unmatched). A stratum of the other state gives 0 with no spread (a structural zero, not a
    measured zero); in the certainty stratum a unit of the other state has y = 0."""
    by = defaultdict(list)
    for it in items:
        by[it["stratum"]].append(it)
    spec = {s["stratum"]: s for s in design[part]["strata"]}
    out = []
    for h, its in sorted(by.items()):
        s = spec[h]
        W = s["projects"] if (part == "ns" and weight == "projects") else s["tokens"]
        dec, uns = [], []
        for it in its:
            a = answers.get(it["item_id"])
            st = answer_state(part, a)
            if state is not None and it.get("state") != state:
                if st != "open":
                    dec.append((it, 0))           # y x 1[state] = 0, whatever the answer
            elif st == "decided":
                dec.append((it, y_values(part, it, a)[yname]))
            elif st == "unsure":
                uns.append(it)
        other = state is not None and h != CERT and s.get("method") != "all units (certainty)" and \
            all(it.get("state") != state for it in its)
        row = {"stratum": h, "W": W, "units": s["units"], "n": len(its), "decided": len(dec), "unsure": len(uns),
               "open": len(its) - len(dec) - len(uns),
               "carried": sum(1 for it, _ in dec if (answers.get(it["item_id"]) or {}).get("carried"))}
        if not dec and not uns:
            row["form"] = None
            out.append(row)
            continue
        w = (lambda it: it["projects"]) if (part == "ns" and weight == "projects") else (lambda it: it["tokens"])
        if other:
            def form(f):
                return 0.0, 0.0, 0.0, 0.0, 0.0
        elif h == CERT or s.get("method") == "all units (certainty)":
            def form(f, dec=dec, uns=uns, w=w):
                den = sum(w(it) for it, _ in dec) + sum(w(it) for it in uns)
                num = sum(w(it) * y for it, y in dec) + f * sum(w(it) for it in uns)
                return (num / den if den else 0.0), 0.0, 0.0, 0.0, 0.0
        elif part == "ns":
            def form(f, dec=dec, uns=uns, w=w, N=s["units"]):
                ws = [w(it) for it, _ in dec] + [w(it) for it in uns]
                ys = [y for _, y in dec] + [f] * len(uns)
                sw = sum(ws)
                r = sum(a * b for a, b in zip(ws, ys)) / sw if sw else 0.0
                n_eff = sw * sw / sum(x * x for x in ws) if sw else 0.0
                return 0.0, 1.0, r * n_eff, n_eff, max(0.0, 1 - len(ws) / N)
        else:
            K = s["rest_tokens"] / s["rest_n"] if s.get("rest_n") else 0.0
            rest_units = s["units"] - s.get("certainty_n", 0)

            def form(f, dec=dec, uns=uns, K=K, rest_units=rest_units):
                ct = cy = 0.0
                k = 0.0
                m = 0
                for it, y in dec:
                    if it["unit"] == "certainty":
                        ct += it["tokens"]
                        cy += it["tokens"] * y
                    else:
                        m += 1
                        k += y
                for it in uns:
                    if it["unit"] == "certainty":
                        ct += it["tokens"]
                        cy += it["tokens"] * f
                    else:
                        m += 1
                        k += f
                den = ct + K * m
                if not den:
                    return 0.0, 0.0, 0.0, 0.0, 0.0
                fpc = max(0.0, 1 - m / rest_units) if rest_units else 0.0
                return cy / den, K * m / den, k, float(m), fpc
        row["form"] = form
        out.append(row)
    return out


EPS = 1e-9


def share(k: float, n: float) -> float:
    """The observed wrong share k / n of the sampled part of a stratum (0 when n = 0)."""
    return k / n if n > 0 else 0.0


def stratum_rate(form: tuple) -> float:
    """The design-weighted observed rate A + B k / n of one stratum (no prior)."""
    A, B, k, n, _ = form
    return A + B * share(k, n)


def combine(rows: list[dict], f: float) -> float | None:
    """The design-weighted observed rate sum W_h R_h / sum W_h, with f the wrong share of the unsure units."""
    use = [r for r in rows if r.get("form")]
    tw = sum(r["W"] for r in use)
    if not tw:
        return None
    return sum(r["W"] * stratum_rate(r["form"](f)) for r in use) / tw


def cp_draw(k: float, n: float, side: str, rng: random.Random) -> float:
    """One draw of the Clopper-Pearson limit distribution of k wrong of n: Beta(k, n - k + 1) for the
    lower limit (0 when k = 0), Beta(k + 1, n - k) for the upper limit (1 when k = n). The 2.5 percentile
    of the lower distribution and the 97.5 percentile of the upper distribution are the 95% limits."""
    if n <= 0:
        return 0.0
    k = min(max(k, 0.0), n)
    if side == "lower":
        return 0.0 if k <= EPS else rng.betavariate(k, n - k + 1)
    return 1.0 if n - k <= EPS else rng.betavariate(k + 1, n - k)


def draw(rows: list[dict], rng: random.Random, side: str) -> float | None:
    """One Monte Carlo draw of the rate for the lower or the upper 95% limit. Each stratum takes a
    Clopper-Pearson limit draw x of its share; the finite-population correction scales the distance
    from the observed share r: p = r + sqrt(fpc) (x - r). The unsure units take one f ~ Uniform(0, 1)."""
    use = [r for r in rows if r.get("form")]
    tw = sum(r["W"] for r in use)
    if not tw:
        return None
    f = rng.random()
    tot = 0.0
    for r in use:
        A, B, k, n, fpc = r["form"](f)
        p = 0.0
        if B:
            obs = share(k, n)
            p = min(1.0, max(0.0, obs + math.sqrt(fpc) * (cp_draw(k, n, side, rng) - obs)))
        tot += r["W"] * (A + B * p)
    return tot / tw


def estimate_rate(part: str, items: list[dict], answers: dict, design: dict, yname: str = "wrong",
                  weight: str = "tokens", draws: int = 4000, seed: int = 20261026, state: str | None = None) -> dict:
    """The rate of one part, one y and one weight: central, range, sd, 95% interval, coverage.

    central: the design-weighted observed rate (unsure units at f = 0.5). ci95: the stratified
    Clopper-Pearson interval with the effective size of each stratum, by Monte Carlo (see draw).
    sd: the standard deviation of all draws of both limits."""
    rows = stratum_forms(part, items, answers, design, yname, weight, state)
    total_w = sum(s["projects"] if (part == "ns" and weight == "projects") else s["tokens"]
                  for s in design[part]["strata"])
    out = {"part": part, "y": yname, "weight": weight, "strata_with_answers": sum(1 for r in rows if r.get("form")),
           "strata": len(rows), "weight_covered": sum(r["W"] for r in rows if r.get("form")), "weight_total": total_w}
    c = combine(rows, 0.5)
    if c is None:
        out.update(central=None)
        return out
    rng = random.Random(seed)
    lo = sorted(x for x in (draw(rows, rng, "lower") for _ in range(draws)) if x is not None)
    hi = sorted(x for x in (draw(rows, rng, "upper") for _ in range(draws)) if x is not None)
    out.update(central=c, lo_all_right=combine(rows, 0.0), hi_all_wrong=combine(rows, 1.0),
               sd=statistics.pstdev(lo + hi) if len(lo) + len(hi) > 1 else 0.0,
               ci95=(lo[int(0.025 * len(lo))], hi[min(len(hi) - 1, int(0.975 * len(hi)))]))
    out["rows"] = [{k: r[k] for k in ("stratum", "W", "units", "n", "decided", "unsure", "open", "carried")} |
                   ({"rate_central": stratum_rate(r["form"](0.5)), "k_eff": r["form"](0.5)[2],
                     "n_eff": r["form"](0.5)[3]} if r.get("form") else {})
                   for r in rows]
    return out


def margin(p: float, n: int) -> float:
    return 1.96 * math.sqrt(p * (1 - p) / n) if n else float("nan")


def sample_size_rows(part: str, n_decided: int, p_obs: float | None, ci: tuple | None) -> list[dict]:
    rows = [{"part": part, "n": n_decided, "basis": "now", "margin_p50_pct": round(100 * margin(0.5, n_decided), 3)
             if n_decided else "", "observed_p_pct": round(100 * p_obs, 3) if p_obs is not None else "",
             "margin_observed_pct": round(100 * margin(p_obs, n_decided), 3) if p_obs is not None and n_decided else "",
             "ci95_half_width_pct": round(50 * (ci[1] - ci[0]), 3) if ci else ""}]
    for t in TARGETS:
        rows.append({"part": part, "n": t, "basis": f"target {t}", "margin_p50_pct": round(100 * margin(0.5, t), 3),
                     "observed_p_pct": round(100 * p_obs, 3) if p_obs is not None else "",
                     "margin_observed_pct": round(100 * margin(p_obs, t), 3) if p_obs is not None else "",
                     "ci95_half_width_pct": ""})
    return rows


def load_part(folder: Path, part: str) -> tuple[list[dict], dict]:
    pf = Path(folder) / part
    items = json.loads((pf / "data/items.json").read_text(encoding="utf-8"))
    return items, read_answers(pf)


def analyse(folder: Path, draws: int = 4000) -> dict:
    """The estimate of both parts (counts and rates only)."""
    folder = Path(folder)
    design = json.loads((folder / "design.json").read_text(encoding="utf-8"))
    res = {"design_ns_frame_sha256": design["ns"]["frame_sha256"],
           "design_dom_frame_sha256": design["dom"]["frame_sha256"], "use_min": USE_MIN, "parts": {}, "sample_size": []}
    for part in PARTS:
        if not (folder / part / "data/items.json").exists():
            continue
        items, ans = load_part(folder, part)
        states = [answer_state(part, ans.get(i["item_id"])) for i in items]
        n_dec = states.count("decided")
        carried = sum(1 for i, s in zip(items, states) if s == "decided" and (ans.get(i["item_id"]) or {}).get("carried"))
        p = {"items": len(items), "decided": n_dec, "unsure": states.count("unsure"), "open": states.count("open"),
             "decided_carried": carried, "decided_own": n_dec - carried, "used": n_dec >= USE_MIN}
        if part == "ns":
            p["wrong_projects"] = estimate_rate(part, items, ans, design, "wrong", "projects", draws)
            p["wrong_tokens"] = estimate_rate(part, items, ans, design, "wrong", "tokens", draws)
            main = p["wrong_projects"]
            p["frame_projects"] = design["ns"]["frame_projects"]
            p["frame_tokens"] = design["ns"]["frame_tokens"]
        else:
            p["wrong_tokens"] = estimate_rate(part, items, ans, design, "wrong", "tokens", draws)
            p["kind_tokens"] = estimate_rate(part, items, ans, design, "kind", "tokens", draws)
            p["company_tokens"] = estimate_rate(part, items, ans, design, "company", "tokens", draws)
            for st in ("linked", "unmatched"):
                p[f"wrong_tokens_{st}_share"] = estimate_rate(part, items, ans, design, "wrong", "tokens", draws,
                                                              state=st)
            main = p["wrong_tokens"]
            p["frame_tokens"] = design["dom"]["frame_tokens"]
            p["no_real_domain_tokens"] = design["dom"]["no_real_domain_tokens_out_of_frame"]
        res["parts"][part] = p
        res["sample_size"] += sample_size_rows(part, n_dec, main.get("central"), main.get("ci95"))
    return res


# --------------------------------------------------------------------------------------------
# The items
# --------------------------------------------------------------------------------------------

def dns_index(ws: Path) -> dict:
    """domain -> the short DNS record of the page (the last record of the evidence files wins)."""
    out = {}
    for p in (ws / "dns/evidence.jsonl", ws / "dns-db/evidence.jsonl", ws / "dns-x1k/evidence.jsonl",
              ws / "review/audit-tail/dns/evidence.jsonl"):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            web, cert, dm, spf = r.get("web") or {}, r.get("cert") or {}, r.get("dmarc") or {}, r.get("spf") or {}
            rec = {"web_final_host": web.get("final_host"), "web_status": web.get("status"), "mx": r.get("mx") or [],
                   "spf_include": spf.get("include") or [], "dmarc_p": dm.get("p"), "dmarc_rua": dm.get("rua") or [],
                   "cert_subject_o": cert.get("subject_o"), "cert_subject_cn": cert.get("subject_cn"),
                   "san_first20": (cert.get("san") or [])[:20], "www_cname": r.get("www_cname") or []}
            if AT not in json.dumps(rec, default=str) and r.get("domain"):
                out[r["domain"]] = rec
    return out


def profile_index(ws: Path) -> dict:
    """(host, namespace in lower case) -> the stored account profile of the judge inputs of rounds 9-11."""
    out = {}
    for pat in ("review/ai/r9/in/*.json", "review/ai/r10/in/*.json", "review/ai/r11/in/*.json",
                "review/ai/v47check/in/*.json"):
        for p in sorted(ws.glob(pat)):
            try:
                rows = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            for r in rows if isinstance(rows, list) else []:
                if not isinstance(r, dict) or not r.get("namespace") or not isinstance(r.get("account"), dict):
                    continue
                a = r["account"]
                prof = {"type": a.get("type") or a.get("__typename") or "", "name": clean(a.get("name")),
                        "websiteUrl": clean(a.get("websiteUrl")), "description": clean(a.get("description")),
                        "isVerified": a.get("isVerified"), "createdAt": a.get("createdAt") or "",
                        "repos": [clean(x.get("name") if isinstance(x, dict) else x) for x in (r.get("repos") or [])[:8]],
                        "source": str(p.relative_to(ws))}
                out[((r.get("host") or "github.com").lower(), r["namespace"].lower())] = prof
    return out


class Db:
    """The organisations and rows of the evaluated database."""

    def __init__(self, db: Path):
        import duckdb
        c = self.c = duckdb.connect(str(db), read_only=True)
        self.org = {}
        for r in c.execute("""SELECT o.company_id, o.name, o.legal_name, o.kind, o.parent_company_id, p.name,
                                     o.country, o.website, o.wikidata_qid, o.review_status, o.kind_basis,
                                     o.kind_basis_pointer
                              FROM company o LEFT JOIN company p ON p.company_id = o.parent_company_id""").fetchall():
            self.org[r[0]] = {"id": r[0], "name": clean(r[1]), "legal_name": clean(r[2]), "kind": r[3] or "",
                              "parent": r[4] or "", "parent_name": clean(r[5]), "country": r[6] or "",
                              "website": clean(r[7]), "wikidata": r[8] or "", "review_status": r[9] or "",
                              "kind_basis": r[10] or "", "kind_basis_pointer": clean(r[11])}
        self.merge = dict(c.execute("SELECT alias, company_id FROM company_alias WHERE source = 'v4-merge-id'").fetchall())
        self.ns_rows = defaultdict(list)
        for h, n, t, cid, rel, ev, ver, ptr, fat in c.execute(
                "SELECT host, namespace, namespace_type, company_id, relation, evidence, verified, source_pointer, "
                "fetched_at FROM company_namespace").fetchall():
            self.ns_rows[f"{h}/{n}".lower()].append({"organisation": cid, "name": self.org.get(cid, {}).get("name", ""),
                                                      "relation": rel, "evidence": ev or "", "verified": bool(ver),
                                                      "namespace_type": t or "", "source_pointer": clean(ptr),
                                                      "fetched_at": fat or ""})
        self.dom_rows = defaultdict(list)
        for dom, cid, role, conf, src, ptr in c.execute(
                "SELECT domain, company_id, role, confidence, source, source_pointer FROM company_domain").fetchall():
            self.dom_rows[dom].append({"organisation": cid, "name": self.org.get(cid, {}).get("name", ""),
                                       "role": role or "", "confidence": conf or "", "source": src or "",
                                       "source_pointer": clean(ptr)})

    def final(self, cid: str) -> str:
        seen = set()
        while cid in self.merge and cid not in seen:
            seen.add(cid)
            cid = self.merge[cid]
        return cid


def ns_items(sample: list[dict], db: Db, prof: dict) -> list[dict]:
    items = []
    for s in sample:
        host, rest = s["ns"].split("/", 1)
        o = db.org.get(s["org"], {"id": s["org"]})
        projects = s["top_projects"].split() if s.get("top_projects") else []
        items.append({
            "item_id": s["sample_id"], "part": "ns", "sample_id": s["sample_id"], "stratum": s["stratum"],
            "unit_key": s["unit"], "title": s["ns"], "host": host, "namespace": rest,
            "type": "namespace taken with certainty (largest by tokens)" if s["stratum"] == CERT else "sampled namespace",
            "pi": float(s["pi"]), "projects": int(s["projects"]), "tokens": int(s["tokens"]),
            "term": s["term"], "evidence": s["evidence"], "owner_kind": s["owner_kind"], "ptr": clean(s["ptr"]),
            "organisation": o, "kind": o.get("kind", ""),
            "ns_rows": db.ns_rows.get(s["ns"], []), "top_projects": projects,
            "profile": prof.get((host.lower(), rest.lower()), {}),
        })
    return items


def dom_items(sample: list[dict], db: Db, d, dns: dict, prop: dict) -> list[dict]:
    doms = sorted({s["domain"] for s in sample})
    c = d.con
    c.execute("CREATE OR REPLACE TEMP TABLE sd (domain VARCHAR)")
    c.executemany("INSERT INTO sd VALUES (?)", [(x,) for x in doms])
    v1 = dict(c.execute("SELECT t.domain, t.tokens FROM tok t JOIN sd USING (domain)").fetchall())
    proj = {dom: (n, top) for dom, n, top in c.execute(
        "SELECT domain, count(*), list(proj ORDER BY tokens DESC, proj)[1] FROM tok_pd_ev JOIN sd USING (domain) GROUP BY 1").fetchall()}
    src = dict(c.execute(f"SELECT domain, source FROM read_parquet('{d.links / 'domain_links.parquet'}') "
                         "WHERE domain IN (SELECT domain FROM sd)").fetchall())
    items = []
    for s in sample:
        dom = s["domain"]
        linked = s["state"] == "linked"
        o = db.org.get(s["org"], {}) if linked and s["org"] not in PSEUDO else {}
        value = ({"id": s["org"], "name": o.get("name", "") or s["org"], "kind": s["kind"], "parent": o.get("parent", ""),
                  "parent_name": o.get("parent_name", ""), "country": o.get("country", ""), "website": o.get("website", ""),
                  "wikidata": o.get("wikidata", ""), "legal_name": o.get("legal_name", "")} if linked else
                 {"id": "", "name": "(no row: independent)", "kind": "independent"})
        n, top = proj.get(dom, (0, ""))
        pr = prop.get(dom.lower()) if not linked else None
        items.append({
            "item_id": s["sample_id"], "part": "dom", "sample_id": s["sample_id"], "stratum": s["stratum"],
            "domain": dom, "title": dom, "state": s["state"], "kind": s["kind"],
            "type": "domain taken with certainty" if s["unit"] == "certainty" else "sampled domain",
            "unit": s["unit"], "pi": float(s["pi"]), "tokens": int(s["tokens"]), "tokens_v1": int(v1.get(dom, 0)),
            "tokens_x1k": int(s["tokens"]) - int(v1.get(dom, 0)), "n_projects": n, "top_project": top,
            "value": value, "match": s["match"], "matched_domain": s["matched_domain"], "confidence": s["confidence"],
            "link_source": src.get(dom, ""), "db_rows": db.dom_rows.get(dom, []) + (
                db.dom_rows.get(s["matched_domain"], []) if s["matched_domain"] and s["matched_domain"] != dom else []),
            "proposal": {k: clean(pr.get(k)) for k in ("name", "kind", "parent_name", "certainty", "reason")} if pr else {},
            "dns": dns.get(dom, {}),
        })
    return items


# --------------------------------------------------------------------------------------------
# The carried answers
# --------------------------------------------------------------------------------------------

def parse_after(text: str) -> tuple[str, str] | None:
    """(id, kind) of a value 'Name (id, kind)'; ('', 'independent') for '(no row: independent)'."""
    t = (text or "").strip()
    if t == "(no row: independent)":
        return "", "independent"
    m = AFTER_RE.match(t)
    return (m.group(2), m.group(3)) if m else None


def same_dom_value(item: dict, oid: str, kind: str, db: Db) -> bool:
    """Is (oid, kind) the value that the domain column shows now for the item?"""
    v = item["value"]
    if item["state"] == "unmatched" or v["kind"] in PSEUDO or kind in PSEUDO:
        return kind == v["kind"]          # a pseudo value: the column shows the same text whatever the row id
    return db.final(oid) == v["id"] and kind == v["kind"]


def carry_answers(folder_ws: Path, ns: list[dict], dom: list[dict], db: Db) -> dict:
    """item_id -> the carried answer row (COLS) for the items that ask the same question again."""
    rv = folder_ws / "review"
    by_ns = {i["unit_key"]: i for i in ns}
    by_ns_key = defaultdict(list)
    for i in ns:
        by_ns_key[i["title"].lower()].append(i)
    by_dom = {i["domain"]: i for i in dom}
    out: dict = {}
    counts = defaultdict(int)

    def put(item, src, verdict, note="", cclass="", corg=""):
        if item["item_id"] in out or verdict not in ("right", "wrong", "unsure"):
            return
        out[item["item_id"]] = {"item_id": item["item_id"], "part": item["part"], "type": item["type"],
                                "title": item["title"], "verdict": verdict, "correct_class": cclass, "wrong_part": "",
                                "correct_org": clean(corg), "note": clean(note), "carried": src,
                                "answered_utc": "", "items_sha256": ""}
        counts[src.split(":")[0]] += 1

    # sample46: domains and namespaces of the audit sample of v4.6 (the value of the item).
    f = rv / "audit-sample-v4.6"
    if (f / "data/items.json").exists():
        ans = read_answers(f)
        for it in json.loads((f / "data/items.json").read_text(encoding="utf-8")):
            a = ans.get(it["item_id"]) or {}
            o = it.get("organisation") or {}
            if not a.get("verdict"):
                continue
            if it["population"] == "domain" and it["key"] in by_dom:
                tgt = by_dom[it["key"]]
                if same_dom_value(tgt, o.get("company_id", ""), o.get("kind", ""), db):
                    put(tgt, f"sample46:{it['item_id']}", a["verdict"], a.get("note", ""))
            elif it["population"] != "domain":
                key = it["key"].lower()
                host_ns, _, oid = key.partition("#")
                tgt = by_ns.get(f"{host_ns}#{db.final(oid)}".lower())
                if tgt and tgt["organisation"].get("kind", "") == o.get("kind", ""):
                    put(tgt, f"sample46:{it['item_id']}", a["verdict"], a.get("note", ""))
    # v47, v48: the check items (the value after the layer, from the item).
    for name in ("audit-v47", "audit-v48"):
        f = rv / name
        if not (f / "data/items.json").exists():
            continue
        ans = read_answers(f)
        for it in json.loads((f / "data/items.json").read_text(encoding="utf-8")):
            a = ans.get(it["item_id"]) or {}
            if it.get("class") != "check" or not a.get("verdict"):
                continue
            src = f"{name.replace('audit-', '')}:{it['item_id']}"
            after = it.get("after") or {}
            if it.get("domain"):
                tgt = by_dom.get(it["domain"])
                v = parse_after(after.get("organisation of the domain", ""))
                if tgt and v and same_dom_value(tgt, v[0], v[1], db):
                    put(tgt, src, a["verdict"], a.get("note", ""))
            elif it.get("namespace"):
                owns = [parse_after(k) for k, rel in after.items() if rel == "owns"]
                owns = [x for x in owns if x]
                for tgt in by_ns_key.get(f"{it['host']}/{it['namespace']}".lower(), []):
                    if any(db.final(oid) == tgt["organisation"].get("id") and kind == tgt["organisation"].get("kind")
                           for oid, kind in owns):
                        put(tgt, src, a["verdict"], a.get("note", ""))
    # tail: the AI claim of the item is the question; carry it when the column shows that claim now.
    f = rv / "audit-tail"
    if (f / "data/items.json").exists():
        ans = read_answers(f)
        for it in json.loads((f / "data/items.json").read_text(encoding="utf-8")):
            a = ans.get(it["item_id"]) or {}
            tgt = by_dom.get(it["domain"])
            if not tgt or not a.get("verdict"):
                continue
            ac = it.get("ai_class", "")
            o = it.get("organisation") or {}
            if ac in ("company", "other-organisation"):
                same = tgt["state"] == "linked" and db.final(o.get("id", "")) == tgt["value"]["id"]
            elif ac in ("independent", "free-provider"):
                same = tgt["kind"] == ac
            else:
                same = False
            if same:
                put(tgt, f"tail:{it['item_id']}", a["verdict"], a.get("note", ""),
                    a.get("correct_class", "") if a["verdict"] == "wrong" else "",
                    a.get("correct_org", "") if a["verdict"] == "wrong" else "")
    out["_counts"] = dict(counts)
    return out


# --------------------------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------------------------

def write_part(pf: Path, items: list[dict], meta: dict, carried: dict) -> dict:
    check_no_at(items)
    check_no_at(meta)
    (pf / "data").mkdir(parents=True, exist_ok=True)
    body = json.dumps(items, ensure_ascii=False, indent=1)
    meta["items_sha256"] = hashlib.sha256(body.encode()).hexdigest()
    (pf / "data/items.json").write_text(body, encoding="utf-8")
    page = (HERE / "audit_columns.html").read_text(encoding="utf-8")
    name = "namespace column" if meta.get("part") == "ns" else "domain column"
    (pf / "audit.html").write_text(page.replace("<title>S8 column audit</title>",
                                                f"<title>S8 column audit: the {name}</title>"), encoding="utf-8")
    shutil.copyfile(HERE / "audit_columns_serve.py", pf / "serve_columns.py")
    ans = read_answers(pf)
    added = 0
    ids = {i["item_id"] for i in items}
    for k, row in carried.items():
        if k in ids and k not in ans:
            ans[k] = dict(row, items_sha256=meta["items_sha256"])
            added += 1
    write_answers(pf, ans)
    meta["carried_added"] = added
    meta["answers"] = len(ans)
    (pf / "data/meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def build(folder: Path, db_path: Path, links: Path, ws: Path = WS) -> dict:
    import error_model as em
    folder = Path(folder)
    design = json.loads((folder / "design.json").read_text(encoding="utf-8"))
    db = Db(db_path)
    d = em.Data(ws, db=db_path, links=links, model="v4.7")
    ns = ns_items(read_csv(folder / "ns/sample.csv"), db, profile_index(ws))
    dom = dom_items(read_csv(folder / "dom/sample.csv"), db, d, dns_index(ws), em.unmatched_proposals(d))
    carried = carry_answers(ws, ns, dom, db)
    counts = carried.pop("_counts")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    metas = {}
    for part, items in (("ns", ns), ("dom", dom)):
        strata = sorted({i["stratum"] for i in items})
        meta = {"generated_utc": now, "part": part, "n_items": len(items), "use_min": USE_MIN,
                "title": "namespace column: is the organisation the owner of the namespace?" if part == "ns" else
                         "domain column: is the organisation of the author e-mail domain right?",
                "classes": list(NS_CLASSES if part == "ns" else DOM_CLASSES),
                "strata": {h: sum(1 for i in items if i["stratum"] == h) for h in strata},
                "design": {k: design[part][k] for k in ("frame_units", "frame_tokens", "frame_sha256", "n")},
                "inputs": {"sample_csv_sha256": hashlib.sha256((folder / part / "sample.csv").read_bytes()).hexdigest(),
                           "db_sha256": design["inputs"]["db_sha256"],
                           "links_json_sha256": design["inputs"]["links_json_sha256"]}}
        metas[part] = write_part(folder / part, items, meta, {k: v for k, v in carried.items() if v["part"] == part})
    return {"counts": counts, "ns": {k: metas["ns"][k] for k in ("n_items", "carried_added", "answers")},
            "dom": {k: metas["dom"][k] for k in ("n_items", "carried_added", "answers")}}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=("build", "estimate"))
    ap.add_argument("--folder", type=Path, default=FOLDER_DEFAULT)
    ap.add_argument("--db", type=Path, default=WS / "companies.v4.9.duckdb")
    ap.add_argument("--links", type=Path, default=LINKS_DEFAULT)
    ap.add_argument("--draws", type=int, default=4000)
    a = ap.parse_args(argv)
    if a.what == "build":
        print(json.dumps(build(a.folder, a.db, a.links)))
    else:
        res = analyse(a.folder, a.draws)
        print(json.dumps(res, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
