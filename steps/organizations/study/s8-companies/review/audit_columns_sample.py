#!/usr/bin/env python3
"""Frames and stratified samples of the column audit: the namespace column and the domain column (2026-10-26).

    audit_columns_sample.py [--ws DIR] [--db companies.v4.9.duckdb] [--links DIR] [--x1k FILE]
                            [--model-out DIR] [--n-ns 800] [--n-dom 800] [--cert-ns 60] [--cert-dom 60]
                            [--seed-text 20261026:columns] [--out DIR]

The user decided (2026-10-26): the error numbers of the paper come from a measured audit sample of
each organisation column, with at least 440 decided units per column and 800 at best. This script
makes the two frames and the two samples. audit_columns.py makes the page items and the estimate.

Namespace part. The unit is one owner namespace: host/namespace and its owner organisation (an owns
row of the namespace column, firm_based_on_namespace). The frame is every owns row of the evaluated
links; the projects of one namespace share the unit. The strata follow the terms of the namespace
error of error_model.py (model v4.7): one stratum for each class (evidence type x owner kind) that
has a type B bound, one for each later AI round (rounds 10 and 11), and one for round 12 with the
user decisions. Before them, a certainty stratum takes the largest namespaces by tokens. In each
other stratum the script draws a simple random sample of units. Allocation: Neyman on the project
weight, n_h proportional to M_h x sqrt(p_h (1 - p_h)), with M_h the projects of the stratum and p_h
the prior wrong-owner share of the model (B/2 of a class, q of a round); each stratum gets at least
min(N_h, 15) units and at most N_h. The bound classes with B = 100% get the largest p_h (0.5), so the
allocation gives them the most units for their size.

Domain part. The unit is one real mail domain and its value in the domain column. The frame is
every real domain with tokens in the dataset: the linked domains of the evaluated links, and the
unmatched real domains (no link; the column gives independent). The tokens with no real domain have
the value unknown, which is right by definition: they are out of the frame. The column error is a
token-weighted rate, and the tokens of the domains span six orders of magnitude. A certainty stratum
takes the largest domains by tokens. In each other stratum (linked exact curated, linked exact other
confidence, linked suffix, unmatched with an AI proposal, unmatched tail) the script draws a
systematic sample with probability proportional to tokens (PPS, the method of audit_tail_sample.py;
units larger than the step are certainty units of the stratum). Why PPS: for a token-weighted rate a
PPS draw represents the same tokens each, so the variance is about p (1 - p) / n; a simple random
draw has the design effect N x sum(t^2) / (sum t)^2 (design.json gives it per stratum). Allocation:
Neyman on the token weight, n_h proportional to T_h x sqrt(p_h (1 - p_h)), with p_h the token-
weighted mean of the link error p_error of the model (linked strata) or the organisation rate of the
tail audit and of the AI proposals (unmatched strata); at least min(N_h, 40) units per stratum.

Output (OUT, in the workspace, not in git: the frames hold personal domains):
  ns/frame.csv, ns/sample.csv, dom/frame.csv, dom/sample.csv, design.json
No value may hold an at sign: the script stops.
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
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(1, str(HERE))

from audit_tail_sample import pps_systematic, seed_fraction  # noqa: E402

AT = chr(64)
SEED_TEXT = "20261026:columns"
N_NS, N_DOM, CERT_NS, CERT_DOM = 800, 800, 60, 60
MIN_NS, MIN_DOM = 15, 40
WS_DEFAULT = Path.home() / "Projects/cregit-workspace/companies"
LINKS_DEFAULT = Path.home() / "Projects/cregit-workspace/final-work/dataset-final-2/m0/links-final"
MODEL_OUT_DEFAULT = WS_DEFAULT / "error-model-v4.9-final-20261026"
OUT_DEFAULT = WS_DEFAULT / "review/audit-columns-v4.9"
CERT_STRATUM = "00 largest by tokens (certainty)"
NS_LAYER_STRATA = {"r10": "round 10 layer", "r11": "round 11 layer", "r12": "round 12 layer or user decision",
                   "user": "round 12 layer or user decision"}
DOM_STRATA = ("linked exact curated", "linked exact other confidence", "linked suffix",
              "unmatched with an AI proposal", "unmatched tail")


def check_no_at(obj) -> None:
    if AT in json.dumps(obj, ensure_ascii=False, default=str):
        raise SystemExit("an at sign in the output: stop")


def unit_sha256(rows: list[dict], key: str, weight: str = "tokens") -> str:
    """Checksum of a frame: the lines 'key<TAB>weight<TAB>stratum' sorted by key."""
    h = hashlib.sha256()
    for r in sorted(rows, key=lambda r: r[key]):
        h.update(f"{r[key]}\t{int(r[weight])}\t{r['stratum']}\n".encode())
    return h.hexdigest()


def neyman(strata: dict, n: int, floor: int) -> dict:
    """n_h for each stratum: proportional to weight x sd, at least min(N_h, floor), at most N_h.

    strata: name -> {"N": units, "w": weight, "p": prior}. The rounding gives the remainder to the
    largest fractions. Returns name -> n_h with sum n (or the sum of N_h if that is smaller)."""
    cap = {h: s["N"] for h, s in strata.items()}
    n = min(n, sum(cap.values()))
    fixed: dict[str, int] = {}
    while True:
        free = [h for h in strata if h not in fixed]
        left = n - sum(fixed.values())
        score = {h: strata[h]["w"] * math.sqrt(max(strata[h]["p"], 1e-6) * (1 - min(strata[h]["p"], 1 - 1e-6)))
                 for h in free}
        tot = sum(score.values())
        raw = {h: left * score[h] / tot if tot else left / len(free) for h in free}
        change = False
        for h in free:
            lo = min(cap[h], floor)
            if raw[h] < lo:
                fixed[h] = lo
                change = True
            elif raw[h] > cap[h]:
                fixed[h] = cap[h]
                change = True
        if not change:
            break
    base = {h: int(raw[h]) for h in free}
    rest = n - sum(fixed.values()) - sum(base.values())
    for h in sorted(free, key=lambda h: -(raw[h] - int(raw[h])))[:rest]:
        base[h] += 1
    return {**fixed, **base}


def srs(units: list[dict], n: int, rng: random.Random, key: str) -> list[dict]:
    """A simple random sample of n units (sorted by key first, so the draw depends only on the seed)."""
    pool = sorted(units, key=lambda r: r[key])
    return sorted(rng.sample(pool, n), key=lambda r: r[key]) if n < len(pool) else pool


# --------------------------------------------------------------------------------------------
# The frames
# --------------------------------------------------------------------------------------------

def load_data(ws: Path, db: Path, links: Path, x1k: Path | None):
    import error_model as em
    import audit_analysis as aa
    d = em.Data(ws, db=db, links=links, model="v4.7", x1k=x1k)
    checks = {}
    for (ptr,) in d.q("""SELECT DISTINCT regexp_extract(source_pointer, '^[^#]*') FROM cur.company_domain
                         UNION SELECT DISTINCT regexp_extract(source_pointer, '^[^#]*') FROM cur.company_namespace"""):
        lay = em.later_layer(ptr)
        if lay is not None and lay[1] not in checks:
            checks[lay[1]] = aa.round_check(d.ws / "review" / f"audit-{lay[0].replace('.', '')}")
    d.decide_keys = set().union(*(c["decide_keys"] for c in checks.values())) if checks else set()
    return d


def ns_frame(d) -> list[dict]:
    """One row per owner namespace (unit) with its term of the model, projects and tokens."""
    import error_model as em
    path = em.later_org_paths(d, em.org_paths(d))
    _, _, ns = em.namespace_model(d, path)
    units: dict[str, dict] = {}
    for p in ns["per"]:
        if p["relation"] != "owns":
            continue
        lay = em.later_layer(p["ptr"])
        if lay is not None:
            term = "user" if p["ns"] in d.decide_keys else lay[1]
            stratum = NS_LAYER_STRATA.get(term, f"{lay[1]} layer")
        else:
            term = f"{p['evidence']}|{p['owner_kind']}"
            stratum = f"class {p['evidence']}, {p['owner_kind']}"
        u = units.setdefault(p["ns_key"], {"unit": p["ns_key"], "ns": p["ns"], "org": p["org"], "term": term,
                                           "stratum": stratum, "evidence": p["evidence"],
                                           "owner_kind": p["owner_kind"], "ptr": p["ptr"], "projects": 0,
                                           "tokens": 0, "project_list": []})
        if u["term"] != term:
            raise SystemExit(f"a namespace with two terms: {p['ns_key']}")
        u["projects"] += 1
        u["tokens"] += int(p["tokens"])
        u["project_list"].append((p["project"], int(p["tokens"])))
    return list(units.values())


def ns_priors(model_out: Path) -> dict:
    """term -> prior wrong-owner share, from namespace_error.csv of the model (default 0.5)."""
    pri = {}
    p = Path(model_out) / "namespace_error.csv"
    if not p.exists():
        return pri
    with open(p, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m = r["measure"]
            if m.startswith("owns, ") and ": bound B" in m:
                ev, kind = m[len("owns, "):-len(": bound B")].split(", ")
                pri[f"{ev}|{kind}"] = float(r["mean_wrong_pct"]) / 100
            elif m.startswith("owns, later AI layer, round "):
                pri["r" + m.rsplit(" ", 1)[1]] = float(r["mean_wrong_pct"]) / 100
            elif m.startswith("owns, user decision"):
                pri["user"] = float(r["mean_wrong_pct"]) / 100
    return pri


def dom_frame(d) -> list[dict]:
    """One row per real domain with tokens: linked (domain_links of the links) or unmatched."""
    import error_model as em
    prop = em.unmatched_proposals(d)
    conf = dict(d.q(f"SELECT domain, confidence FROM read_parquet('{d.links / 'domain_links.parquet'}')"))
    rows = []
    for dom, org, kind, match, md, tok in d.q("""SELECT lc.domain, lc.org, lc.kind, lc.match, lc.md, t.tokens
                                                 FROM lc JOIN tok_ev t USING (domain) WHERE t.tokens > 0"""):
        c = conf.get(dom) or ""
        st = "linked suffix" if match == "suffix" else \
            "linked exact curated" if c == "curated" else "linked exact other confidence"
        rows.append({"domain": dom, "tokens": int(tok), "state": "linked", "org": org or "", "kind": kind or "",
                     "match": match or "", "matched_domain": md or "", "confidence": c, "stratum": st,
                     "key_hash": em.key_hash(dom)})
    for dom, tok, part in em.unmatched_rows(d, prop):
        if part == "no_real_domain" or tok <= 0:
            continue
        rows.append({"domain": dom, "tokens": int(tok), "state": "unmatched", "org": "", "kind": "independent",
                     "match": "", "matched_domain": "", "confidence": "", "part": part,
                     "stratum": "unmatched with an AI proposal" if part == "proposed" else "unmatched tail",
                     "key_hash": em.key_hash(dom)})
    return rows


def dom_priors(d, frame: list[dict], model_out: Path) -> dict:
    """stratum -> prior error rate (token-weighted): p_error of the model for linked domains; the
    organisation rate of the tail audit (summary.json) and of the AI proposals for unmatched domains."""
    import duckdb
    import error_model as em
    pe = {}
    p = Path(model_out) / "organisation_domains_p_error.parquet"
    if p.exists():
        pe = dict(duckdb.connect().execute(f"SELECT key_hash, p_error FROM read_parquet('{p}')").fetchall())
    s = {}
    sp = Path(model_out) / "summary.json"
    if sp.exists():
        s = json.loads(sp.read_text())
    tail = float(s.get("tail_org_rate_pct") or 41.7) / 100
    unm = em.unmatched(d)
    o_prop = unm.get("proposed_org", 0) / unm["proposed"] if unm.get("proposed") else tail
    acc = defaultdict(lambda: [0.0, 0])
    for r in frame:
        if r["state"] == "linked":
            acc[r["stratum"]][0] += r["tokens"] * pe.get(r["key_hash"], 0.01)
            acc[r["stratum"]][1] += r["tokens"]
    pri = {h: a[0] / a[1] for h, a in acc.items() if a[1]}
    pri["unmatched with an AI proposal"] = o_prop
    pri["unmatched tail"] = tail
    return pri


def deff_srs(tokens: list[int]) -> float:
    """Design effect of a simple random draw for a token-weighted mean: N sum(t^2) / (sum t)^2."""
    t = sum(tokens)
    return len(tokens) * sum(x * x for x in tokens) / (t * t) if t else 0.0


# --------------------------------------------------------------------------------------------
# The samples
# --------------------------------------------------------------------------------------------

def sample_ns(units: list[dict], priors: dict, n: int, cert: int, rng: random.Random) -> tuple[list[dict], list[dict]]:
    """(sample rows, strata rows) of the namespace part."""
    by_tok = sorted(units, key=lambda r: (-r["tokens"], r["unit"]))
    for r in by_tok[:cert]:
        r["stratum"] = CERT_STRATUM
    groups = defaultdict(list)
    for r in units:
        groups[r["stratum"]].append(r)
    rest = {h: g for h, g in groups.items() if h != CERT_STRATUM}
    spec = {}
    for h, g in rest.items():
        terms = {r["term"] for r in g}
        p = max(priors.get(t, 0.5) for t in terms)
        spec[h] = {"N": len(g), "w": sum(r["projects"] for r in g), "p": p}
    alloc = neyman(spec, n - len(groups.get(CERT_STRATUM, [])), MIN_NS)
    sample, strata = [], []
    for h in sorted(groups):
        g = groups[h]
        nh = len(g) if h == CERT_STRATUM else alloc[h]
        s = sorted(g, key=lambda r: (-r["tokens"], r["unit"])) if h == CERT_STRATUM else srs(g, nh, rng, "unit")
        for r in s:
            sample.append(dict(r, pi=nh / len(g)))
        strata.append({"stratum": h, "units": len(g), "projects": sum(r["projects"] for r in g),
                       "tokens": sum(r["tokens"] for r in g), "n": nh,
                       "prior_wrong": round(spec[h]["p"], 5) if h in spec else "",
                       "method": "all units (certainty)" if h == CERT_STRATUM else "simple random sample"})
    return sample, strata


def sample_dom(frame: list[dict], priors: dict, n: int, cert: int, seed_text: str) -> tuple[list[dict], list[dict]]:
    """(sample rows, strata rows) of the domain part."""
    by_tok = sorted(frame, key=lambda r: (-r["tokens"], r["domain"]))
    for r in by_tok[:cert]:
        r["stratum"] = CERT_STRATUM
    groups = defaultdict(list)
    for r in frame:
        groups[r["stratum"]].append(r)
    T = sum(r["tokens"] for r in frame)
    spec = {h: {"N": len(g), "w": sum(r["tokens"] for r in g) / T, "p": priors.get(h, 0.05)}
            for h, g in groups.items() if h != CERT_STRATUM}
    alloc = neyman(spec, n - len(groups.get(CERT_STRATUM, [])), MIN_DOM)
    sample, strata = [], []
    for h in [CERT_STRATUM] + [x for x in DOM_STRATA if x in groups]:
        g = groups[h]
        if h == CERT_STRATUM:
            for r in sorted(g, key=lambda r: (-r["tokens"], r["domain"])):
                sample.append(dict(r, unit="certainty", pi=1.0, point=""))
            strata.append({"stratum": h, "units": len(g), "tokens": sum(r["tokens"] for r in g), "n": len(g),
                           "method": "all units (certainty)", "rest_n": 0, "rest_tokens": 0, "step": "",
                           "start": "", "certainty_n": len(g), "prior_wrong": "", "deff_srs": ""})
            continue
        nh = alloc[h]
        u = seed_fraction(f"{seed_text}:{h}")
        if nh >= len(g):
            s = {"certainty": [dict(r, unit="certainty", pi=1.0, point="") for r in g], "points": [],
                 "rest_n": 0, "rest_tokens": 0, "step": 0.0, "start": 0.0}
        else:
            s = pps_systematic(g, nh, u)
        for r in s["certainty"] + s["points"]:
            sample.append(r)
        strata.append({"stratum": h, "units": len(g), "tokens": sum(r["tokens"] for r in g), "n": nh,
                       "method": "systematic PPS (tokens)", "rest_n": s["rest_n"], "rest_tokens": s["rest_tokens"],
                       "step": s["step"], "start": s["start"], "certainty_n": len(s["certainty"]),
                       "seed_fraction": u, "prior_wrong": round(spec[h]["p"], 5),
                       "deff_srs": round(deff_srs([r["tokens"] for r in g]), 1)})
    return sample, strata


def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ws", type=Path, default=WS_DEFAULT)
    ap.add_argument("--db", type=Path, default=WS_DEFAULT / "companies.v4.9.duckdb")
    ap.add_argument("--links", type=Path, default=LINKS_DEFAULT)
    ap.add_argument("--x1k", type=Path, help="default: the model v4.7 extension counts of error_model.py")
    ap.add_argument("--model-out", type=Path, default=MODEL_OUT_DEFAULT, help="the error model output (priors)")
    ap.add_argument("--n-ns", type=int, default=N_NS)
    ap.add_argument("--n-dom", type=int, default=N_DOM)
    ap.add_argument("--cert-ns", type=int, default=CERT_NS)
    ap.add_argument("--cert-dom", type=int, default=CERT_DOM)
    ap.add_argument("--seed-text", default=SEED_TEXT)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    a = ap.parse_args(argv)
    import error_model as em
    d = load_data(a.ws, a.db, a.links, a.x1k)
    rng = random.Random(int(hashlib.sha256(f"{a.seed_text}:ns".encode()).hexdigest()[:16], 16))
    units = ns_frame(d)
    ns_s, ns_st = sample_ns(units, ns_priors(a.model_out), a.n_ns, a.cert_ns, rng)
    frame = dom_frame(d)
    dom_s, dom_st = sample_dom(frame, dom_priors(d, frame, a.model_out), a.n_dom, a.cert_dom, a.seed_text)
    for i, r in enumerate(ns_s, 1):
        r["sample_id"] = f"N{i:04d}"
        r["top_projects"] = " ".join(p for p, _ in sorted(r["project_list"], key=lambda x: (-x[1], x[0]))[:8])
    for i, r in enumerate(dom_s, 1):
        r["sample_id"] = f"D{i:04d}"
    check_no_at([r["unit"] for r in units] + [r["domain"] for r in frame])
    check_no_at(ns_s)
    check_no_at(dom_s)
    out = a.out
    ncols = ["unit", "stratum", "term", "org", "evidence", "owner_kind", "projects", "tokens"]
    write_csv(out / "ns/frame.csv", sorted(units, key=lambda r: (-r["tokens"], r["unit"])), ncols)
    write_csv(out / "ns/sample.csv", ns_s, ["sample_id", "stratum", "pi"] + ncols[:1] + ncols[2:] +
              ["ns", "ptr", "top_projects"])
    dcols = ["domain", "stratum", "state", "org", "kind", "match", "matched_domain", "confidence", "tokens"]
    write_csv(out / "dom/frame.csv", sorted(frame, key=lambda r: (-r["tokens"], r["domain"])), dcols)
    write_csv(out / "dom/sample.csv", dom_s, ["sample_id", "stratum", "unit", "pi", "point"] + dcols[:1] + dcols[2:])
    T_dom = sum(r["tokens"] for r in frame)
    design = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": "measured error rates of the namespace column and the domain column (user decision 2026-10-26: "
                   "at least 440 decided units per column, 800 at best)",
        "seed_text": a.seed_text,
        "inputs": {"db": str(a.db), "db_sha256": em.sha256_file(a.db), "links": str(a.links),
                   "links_json_sha256": em.sha256_file(a.links / "links.json"), "x1k": str(d.x1k),
                   "evaluated_tokens": d.total, "model_out": str(a.model_out)},
        "ns": {"unit": "owner namespace (host/namespace#organisation)", "frame_units": len(units),
               "frame_projects": sum(r["projects"] for r in units), "frame_tokens": sum(r["tokens"] for r in units),
               "frame_sha256": unit_sha256(units, "unit"), "n": len(ns_s), "certainty_n": a.cert_ns,
               "allocation": "Neyman on projects, floor min(N_h, 15)", "strata": ns_st},
        "dom": {"unit": "real mail domain and its column value", "frame_units": len(frame), "frame_tokens": T_dom,
                "no_real_domain_tokens_out_of_frame": d.total - T_dom,
                "frame_sha256": unit_sha256(frame, "domain"), "n": len(dom_s), "certainty_n": a.cert_dom,
                "allocation": "Neyman on tokens, floor min(N_h, 40)", "strata": dom_st},
    }
    check_no_at(design)
    (out / "design.json").write_text(json.dumps(design, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"ns": {k: design["ns"][k] for k in ("frame_units", "frame_projects", "frame_tokens", "n")},
                      "dom": {k: design["dom"][k] for k in ("frame_units", "frame_tokens", "n")}}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
