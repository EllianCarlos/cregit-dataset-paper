#!/usr/bin/env python3
"""Error model of the S8 organisation columns, built from the acquisition process (2026-10-18).

    error_model.py [--ws DIR] [--db FILE] [--links DIR] [--out DIR] [--draws 2000] [--seed 20261018]

The model is bottom-up: every link has a provenance path (its first source, then the checks that
saw it). The script estimates the raw error of each source from the changes that later checks made,
the detection of each check from pairs of checks on the same links, and the residual error of each
link from its path. It then propagates the parameters to the token-weighted error of the columns
and to the share of tokens by organisation kind (Monte Carlo, JCGM 101:2008). ERROR_MODEL.md
explains the model; every number in it comes from the tables that this script writes.

Inputs (read only, all under --ws, default ~/Projects/cregit-workspace/companies):
  companies.duckdb (v3), v4.0-20261018/, companies.v4.duckdb (v4.1), links/, links-v4/ (the history
  that gives the parameters), companies.v4.2.duckdb (only the review stamps of its organisations),
  the evaluated layer (--db, default companies.v4.6.duckdb; --links, default links-v4.6/),
  manual/v42_merges.csv and manual/v44_merges.csv of the study folder,
  review/ai/{compare-0-4,part-1..9,domain_links_review,lookalike_review,sweep_review,
  conflict_domains,rule_corrections}.csv, review/ai/r4/out-*.csv, review/decisions.csv,
  review/history/decisions.*.csv, review/decisions.chat.csv, review/decisions.domains.chat.csv,
  review/audit-final/verdicts.csv and its history (the user's reversal count; counts only),
  review/audit-v44/answers.csv and data/items.json (the user's check of round 9; counts only),
  cache/*.parquet (only the columns domain and tokens; never the address column),
  proposals/top_unmatched.v1.csv and .v2.csv of the study folder.
Outputs (--out, default <ws>/error-model): CSV tables, link_error.parquet (one row per dataset
domain, with a hashed key and no domain or organisation id), organisation_domains_p_error.parquet
(the p_error column of the organisation_domains reference table: hashed key, error_stratum,
p_error), summary.json and tables.md.
No output holds a domain, an address or a person name. Only namespace_review_candidates.csv holds
project names and organisation ids (the review list of the namespace column; not in tables.md).

The measurand of firm_based_on_domain (user decision of 2026-10-19) is the organisation of the
address that the author chose for the commit. A personal or free address, and a real domain with
no row in the database, mean that the author acted as an independent person (value `independent`).
A token with no real domain (blank, no dot, a git-svn id) gets the value `unknown` (the user,
2026-10-19): the address is not known, so the value has no mapping error.
The ids `independent`, `free-provider` and `unknown` are not organisations, so they have no kind
error (user decision of 2026-10-19): only the link error applies to them.
The employer of the author is a side study: side/employer_model.py imports this module.

Two layers (2026-10-20). The parameters come from the history v3 -> v4.0 -> v4.1 (companies.v4.duckdb,
links-v4/): the raw error of each source, the detection of each check, the rater model, the
capture-recapture, the user reversals and the kind transitions. The model applies them to the
evaluated layer (--db and --links; by default the final v4.6; the database is attached as `cur`):
the chain of each dataset domain, the tokens, the unmatched domains, the namespace column, the suffix
and partner terms and the two parquet files. link_format.py reads the link folders of both formats.
The chain fields o41, kind41, match41, group41 and kc41 keep their names (and so do the columns
group41, match41 and kind41 of link_error.parquet, which review/audit_sample.py reads). In the
evaluated chain they hold the evaluated layer. The later layers (V4_TODO.md) get these origins:
  a domain row with the pointer manual/v42_ (v4.2; the user audited every change): `user`;
  a domain row with the pointer manual/v44_ (v4.4, AI round 9 with a web check): `r9`, with the
  round 9 error q_r9 (ai_round_check: Jeffreys on k_rule wrong of n);
  the same domain row as in v4.1 (a later merge only renamed the organisation): the v4.1 origin. A
  v4.4 merge on the way adds the round 9 term, p = 1 - (1 - p)(1 - q_r9); a v4.2 merge adds nothing.
The kind of an organisation that v4.2 changed is a user decision. The kind of an organisation that
round 9 set (reviewer claude-main, review date 2026-10-20) has the error q_r9 times phi.

Two models (--model, 2026-10-25). `--model v4.6` is the published model of database v4.6: version 1
of the dataset only, and every output byte as before. `--model v4.7` (the default) is the model of
database v4.7 and later (--db; for v4.8 give --db companies.v4.8.duckdb and its links):
  - both layers of the dataset: the tokens of the evaluated layer are the version 1 cache plus the
    domain counts of the extension (--x1k-counts; 32,626,028,860 tokens in all). The parameters still
    come from the history of version 1 (the table tok); only the propagation uses both layers;
  - the merged links of both layers (--links). A domain with an exact row in the database and no row
    in the link folder (links older than the database) gets the exact link of build_links.py, so that
    the rows of a newer database enter the model before its links are built (summary key
    links_added_from_db_rows; 0 when the links come from the same database). A link with no tokens
    in the token tables (a domain that only the final write counts) gets a chain row with tokens 0 and
    its p_error by the same rule (summary key links_with_no_tokens);
  - the later AI layers (v4.7 = round 10, v4.8 = round 11, ...): a row with the pointer
    manual/v4N_ or review/v4N_ (N >= 7) has the origin r(N+3) with the error q of the check sample
    of its audit page (review/audit-v4N; Jeffreys central value, Clopper-Pearson interval; q_r9 when
    the page has no answer yet). A row whose key is an item of class decide of that page (the AI
    could not decide) is a user decision (origin user). An organisation that a later round stamped
    (claude-main, a review date after 2026-10-20) keeps the review path of database v4.6 when it was
    there with the same kind; else its kind error is q of the later rounds times phi;
  - the kind error of the user or curated path is q_user times phi (sections 4.4 and 4.6; the v4.6
    model used q_user);
  - the audit sample (--audit-sample, review/audit_analysis.py): in a stratum of the audit that is
    complete (every sampled item has an answer; --audit-min-n N lowers the rule to N decided
    answers), the measured value (type A: Jeffreys posterior of k wrong of n decided answers)
    replaces the model value: the link error becomes p x theta / m (m: the mean model error of the
    links of the stratum; audit_factors), so the mean unit error of the stratum is the measured
    value. A link is in a stratum when its domain is a unit of the frame with the same organisation.
    In a complete namespace stratum the measured value replaces the class bound of its owns rows. The table audit_replacements.csv states each replacement; the
    sensitivity table audit_update.csv gives the column error with all answers so far, each stratum
    updated from the model value (Beta prior with the Monte Carlo mean and variance of the model).
  - the tail audit (--tail-audit, default review/audit-tail; --no-tail-audit; review/audit_tail.py,
    2026-10-26): a PPS sample of 60 of the unmatched real domains (the pool of unmatched_rows) that
    the user checks. When its page is complete, its measured organisation and company rates (Horvitz-
    Thompson, Jeffreys draws on their own stream seed + 11) replace the type B rates of the unmatched
    real domains (o_unmatched, o_tail, f_unmatched, f_tail). Table tail_audit.csv (counts only).
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import random
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE / "review"))
from link_format import check_owns_agree, domain_links_sql, project_links_sql  # noqa: E402
import audit_analysis as aa  # noqa: E402
import audit_tail as at  # noqa: E402

WS_DEFAULT = Path.home() / "Projects/cregit-workspace/companies"
# The evaluated layer (under --ws): the final database and its link folder.
DB_DEFAULT = "companies.v4.6.duckdb"
LINKS_DEFAULT = "links-v4.6"
# The models (--model). v4.6: the published model (version 1 only). v4.7: both layers, the later AI
# layers, phi on the user path and the audit values (module docstring).
MODELS = ("v4.6", "v4.7")
MODEL_DEFAULT = "v4.7"
DEFAULTS = {
    "v4.6": {"db": DB_DEFAULT, "links": LINKS_DEFAULT, "x1k": None, "out": "error-model"},
    "v4.7": {"db": "companies.v4.7.duckdb", "links": "x1k-links/dataset-x1k-links-1/links-merged",
             "x1k": "x1k-links/dataset-x1k-links-1/domain_counts.x1k.parquet", "out": "error-model-{version}"},
}
AUDIT_SAMPLE_DEFAULT = "review/audit-sample-v4.6"
TAIL_AUDIT_DEFAULT = "review/audit-tail"      # the tail audit of the unmatched real domains (model v4.7)
PREV_DB = "companies.v4.6.duckdb"      # the review paths of the organisations before the later AI rounds
DATASET_TOKENS = 32_626_028_860        # version 1 + extension (x1k-links run dataset-x1k-links-1)
# DATASET_TOKENS is the sum of the token tables of the model (tok_ev), not the count of the final write
# (32,626,508,161 tokens in 10,753 files; 479,301 more). A link of the final write with no tokens in these
# tables gets tokens 0 (chain_domain_table).
# Later AI layers: a source pointer manual/v4N_ or review/v4N_ with N >= 7 (v4.7 = round 10).
LATER_PTR = re.compile(r"^(?:manual|review)/v4(\d+)_")
LATER_MIN = 7
LATER_STAMP_AFTER = "2026-10-20"       # claude-main stamps after round 9: the later AI rounds
LATER_PATH = "AI web check (round 10 or later)"
# The later layers (V4_TODO.md). The source pointer of a domain row names the layer that set it.
PTR_V42 = "manual/v42_"        # v4.2: fixes with web sources; the user audited every change
PTR_V44 = "manual/v44_"        # v4.4: AI round 9, one web check per fact
# Review stamps (reviewer, review date) of the organisation rows that a later layer changed.
R42_STAMP = ("claude-main", "2026-10-19")    # v4.2 (read in companies.v4.2.duckdb; v4.3 used it too)
R9_STAMP = ("claude-main", "2026-10-20")     # v4.4, AI round 9
R9_PATH = "AI web check (round 9)"
PSEUDO = ("independent", "free-provider")
# The pseudo ids of firm_based_on_domain. They name no organisation, so they cannot have a kind error.
NO_KIND_ERROR = PSEUDO + ("unknown",)
COMPANY_KINDS = ("company", "consultancy")
Z95 = 1.959963984540054
AT = chr(64)        # the at sign; no file of this study holds it literally

# First source of a domain row -> source group (the "instrument" that made the link).
SOURCE_GROUP = {
    "gitdm": "G1 gitdm curated", "patch": "G1 gitdm curated", "rich": "G1 gitdm curated",
    "builtin": "G1 gitdm curated", "correction": "G1 gitdm curated",
    "cncf-gitdm": "G2 cncf-gitdm multi", "cncf-gitdm-self-reference": "G2 cncf-gitdm multi",
    "cncf-gitdm-single": "G3 cncf-gitdm single", "cncf-gitdm-single-self-reference": "G3 cncf-gitdm single",
    "spinellis-2020": "G4 Spinellis 2020",
    "claude-proposal": "G5 AI firm-domains", "claude-proposal-v1": "G6 AI proposal v1",
    "claude-proposal-v2": "G7 AI proposal v2",
    "review-ai-part-8.csv": "G8 AI review (rounds 3-5)", "review-ai-part-9.csv": "G8 AI review (rounds 3-5)",
    "review-4d": "G9 AI link check", "review-4f": "G9 AI link check", "review-7": "G9 AI link check",
    "review-8": "G9 AI link check",
    "review-user": "G10 user or manual", "review-decisions.csv": "G10 user or manual",
    "manual-v4-new-orgs": "G10 user or manual",
}
BANDS = ((1_000_000, "B1 >=1M"), (10_000, "B2 10k-1M"), (0, "B3 <10k"))


# --------------------------------------------------------------------------------------------
# Statistics (pure functions; test_error_model.py tests them)
# --------------------------------------------------------------------------------------------

def wilson(k: float, n: float, z: float = Z95) -> tuple[float, float]:
    """Wilson (1927) score interval of a binomial share k/n."""
    if n <= 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))


def clopper_pearson(k: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Clopper and Pearson (1934) exact two-sided interval of a binomial share k/n (bisection)."""
    if n <= 0:
        return (0.0, 1.0)
    a = (1 - conf) / 2

    def root(f) -> float:          # f is monotone and changes sign on (0, 1)
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
        return (lo + hi) / 2
    low = 0.0 if k == 0 else root(lambda p: a - (1 - binom_cdf(k - 1, n, p)))
    high = 1.0 if k == n else root(lambda p: binom_cdf(k, n, p) - a)
    return (low, high)


# Round 9 (web checks, 2026-10-20): the check items that the user marked wrong only because of the
# name of the relation. The user's decision 1 of 2026-10-20 renames the relation of a fiscal sponsor
# from hosted_by to sponsored_by (layer v4.5), so the fact of the AI answer (napari is a NumFOCUS
# sponsored project) is right.
R9_NAMING_ONLY = ("github.com/napari",)


def ai_round_check(ws: Path, audit: str = "review/audit-v44") -> dict:
    """The error of one AI answer of round 9, from the user's check sample on the v4.4 audit page.

    The page shows a seeded 10% sample (class check) of the rows that round 9 decided. Returns the
    counts (right, wrong, unsure), the error k/n as answered (n = right + wrong) with its 95%
    Clopper-Pearson interval, and the error after the relation rename (the wrong answers of
    R9_NAMING_ONLY do not count) with the upper bound of the rule of three (3 / n) when k = 0.
    The user saw the AI verdict, so the rate is a lower bound by anchoring, as for user_calibration.
    """
    items_p, ans_p = ws / audit / "data/items.json", ws / audit / "answers.csv"
    if not items_p.exists() or not ans_p.exists():
        return {"n": 0, "k": 0, "k_rule": 0, "right": 0, "wrong": 0, "unsure": 0,
                "cp": (0.0, 1.0), "cp_rule": (0.0, 1.0), "rule3": 1.0}
    items = {i["item_id"]: i for i in json.loads(items_p.read_text())}
    cnt = Counter()
    k_rule = 0
    for r in read_csv(ans_p):
        i = items.get(r["item_id"])
        if i is None or i.get("class") != "check" or r.get("verdict") not in ("right", "wrong", "unsure"):
            continue
        cnt[r["verdict"]] += 1
        if r["verdict"] == "wrong" and i.get("title") not in R9_NAMING_ONLY:
            k_rule += 1
    n, k = cnt["right"] + cnt["wrong"], cnt["wrong"]
    return {"n": n, "k": k, "k_rule": k_rule, "right": cnt["right"], "wrong": cnt["wrong"], "unsure": cnt["unsure"],
            "cp": clopper_pearson(k, n), "cp_rule": clopper_pearson(k_rule, n),
            "rule3": 3 / n if n else 1.0}


def lincoln_petersen(n1: int, n2: int, m: int) -> float:
    """Lincoln-Petersen estimate of the population size; inf when no recapture."""
    return math.inf if m == 0 else n1 * n2 / m


def chapman(n1: int, n2: int, m: int) -> tuple[float, float]:
    """Chapman (1951) estimate of the population size and its variance (Seber 1982)."""
    n = (n1 + 1) * (n2 + 1) / (m + 1) - 1
    var = (n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m) / ((m + 1) ** 2 * (m + 2))
    return n, var


def removal_two_pass(n1: int, n2: int) -> tuple[float, float]:
    """Two-pass removal estimate (Zippin 1956; Seber and Le Cren 1967).

    Pass 1 finds n1 errors, pass 2 finds n2 of the errors that pass 1 left. With one detection
    probability p for both passes: p = 1 - n2/n1 and N = n1^2 / (n1 - n2). Returns (p, N).
    """
    if n1 <= n2:
        return (float("nan"), math.inf)
    return (1 - n2 / n1, n1 * n1 / (n1 - n2))


def _s(a: float, b: float) -> float:
    return math.sqrt(max(0.0, a * (1 - a) * b * (1 - b)))


def _first_root(g, lo: float, hi: float, steps: int = 4000) -> float | None:
    """The smallest z in [lo, hi] with g(z) = 0 after g > 0 (grid scan, then bisection)."""
    prev = lo
    if g(lo) <= 0:
        return lo
    for i in range(1, steps + 1):
        z = lo + (hi - lo) * i / steps
        if g(z) <= 0:
            a, b = prev, z
            for _ in range(100):
                m = (a + b) / 2
                if g(m) > 0:
                    a = m
                else:
                    b = m
            return (a + b) / 2
        prev = z
    return None


def two_rater(x: float, y: float, w: float, rho: float = 0.0) -> dict:
    """Error rates of two reviews A and B from the adjudicated disagreements.

    x: share of items where only A is wrong (the adjudicator took B); y: only B is wrong (took A);
    w: both wrong and they disagree (the adjudicator wrote a third answer). Unknown z: the share
    where both are wrong (z >= w). Model: a = x + z, b = y + z and z = a*b + rho*sqrt(a(1-a)b(1-b)),
    with rho the correlation of the two error indicators (rho = 0: conditional independence).
    z is the smallest root; if it is below w, the data say that rho is larger, and z = w.
    Returns a, b, z, and agree_wrong = (z - w) / (1 - x - y - w), the share of the agreed items
    that are wrong. With no root (rho too large for the observed disagreements) the values are nan.
    """
    hi = 1 - max(x, y)

    def g(z):
        a, b = x + z, y + z
        return a * b + rho * _s(a, b) - z

    r0 = _first_root(g, 0.0, hi)
    agree = 1 - x - y - w
    if r0 is None:
        nan = float("nan")
        return {"a": nan, "b": nan, "z": nan, "agree": agree, "agree_wrong": nan, "root": nan}
    z = max(r0, w)
    return {"a": x + z, "b": y + z, "z": z, "agree": agree, "root": r0,
            "agree_wrong": (z - w) / agree if agree > 0 else float("nan")}


def rho_min(x: float, y: float, w: float) -> float:
    """The smallest error correlation that explains the observed both-wrong share w (root = w)."""
    if two_rater(x, y, w, 0.0)["root"] >= w:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        m = (lo + hi) / 2
        r = two_rater(x, y, w, m)["root"]
        if r != r or r >= w:      # nan (infeasible) or enough
            hi = m
        else:
            lo = m
    return hi


def rho_max(x: float, y: float, w: float) -> float:
    """The largest error correlation that the observed disagreements allow (a root exists)."""
    lo, hi = 0.0, 1.0
    for _ in range(60):
        m = (lo + hi) / 2
        if two_rater(x, y, w, m)["root"] != two_rater(x, y, w, m)["root"]:
            hi = m
        else:
            lo = m
    return lo


def residual(prior: float, se: float) -> float:
    """Probability that a link is wrong after a check with sensitivity se left it unchanged.

    Bayes: prior (1 - se) / (prior (1 - se) + 1 - prior). A false-change rate of zero on right links
    makes the value a little larger, so the formula errs on the safe side.
    """
    if prior <= 0:
        return 0.0
    num = prior * (1 - se)
    return num / (num + (1 - prior))


def combine_se(ses) -> float:
    """Sensitivity of a chain of independent checks: 1 - prod(1 - se_i)."""
    out = 1.0
    for s in ses:
        out *= (1 - s)
    return 1 - out


def raw_from_detected(d: float, se: float) -> float:
    """Raw error rate of a source from its detected change rate d and the chain sensitivity se."""
    if se <= 0:
        return d
    return min(1.0, d / se)


def rectangular_u(half_width: float) -> float:
    """Standard uncertainty of a rectangular distribution (GUM 4.3.7)."""
    return half_width / math.sqrt(3)


def combined_u(us) -> float:
    """Root sum of squares of uncorrelated standard uncertainties (GUM 5.1.2)."""
    return math.sqrt(sum(u * u for u in us))


def uniform_moments(lo: float, hi: float) -> tuple[float, float]:
    """Mean and variance of a rectangular distribution from lo to hi (GUM 4.3.7)."""
    return (lo + hi) / 2, (hi - lo) ** 2 / 12


def product_moments(m1: float, v1: float, m2: float, v2: float) -> tuple[float, float]:
    """Mean and variance of the product of two independent quantities."""
    return m1 * m2, (v1 + m1 * m1) * (v2 + m2 * m2) - (m1 * m2) ** 2


def rogan_gladen(p_obs: float, se: float, sp: float) -> float:
    """Rogan and Gladen (1978): true share from an observed share with known Se and Sp."""
    den = se + sp - 1
    if den <= 0:
        raise ValueError("Se + Sp must exceed 1")
    return (p_obs + sp - 1) / den


def solve(m: list[list[float]], v: list[float]) -> list[float]:
    """Solve m x = v by Gauss-Jordan elimination with partial pivots (small matrices)."""
    n = len(v)
    a = [list(map(float, row)) + [float(v[i])] for i, row in enumerate(m)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(a[r][c]))
        if abs(a[p][c]) < 1e-15:
            raise ValueError("singular matrix")
        a[c], a[p] = a[p], a[c]
        piv = a[c][c]
        a[c] = [x / piv for x in a[c]]
        for r in range(n):
            if r != c and a[r][c] != 0:
                f = a[r][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [a[i][n] for i in range(n)]


def matrix_correct(obs: list[float], p_obs_given_true: list[list[float]]) -> list[float]:
    """Misclassification correction: obs = M^T true, M[i][j] = P(observed j | true i)."""
    n = len(obs)
    mt = [[p_obs_given_true[i][j] for i in range(n)] for j in range(n)]
    return solve(mt, obs)


def beta_jeffreys(rng: random.Random, k: float, n: float) -> float:
    """A draw of a binomial share from its Jeffreys posterior Beta(k + 1/2, n - k + 1/2)."""
    return rng.betavariate(k + 0.5, n - k + 0.5)


def band(tokens: float) -> str:
    for lo, name in BANDS:
        if tokens >= lo:
            return name
    return BANDS[-1][1]


def kclass(kind: str | None) -> str:
    """Kind class of a link for the strata: the two pseudo kinds, or an organisation."""
    return kind if kind in PSEUDO else "organisation"


MIN_N = 10


def stratum_key(counts: dict, group: str, band_: str, kc: str) -> tuple:
    """The finest stratum with at least MIN_N v3 links: (group, band, class), then coarser."""
    for key in ((group, band_, kc), (group, band_, "*"), (group, "all", kc), (group, "all", "*")):
        if counts.get(key, {}).get("n", 0) >= MIN_N:
            return key
    return (group, "all", "*")


def group_of(source: str | None) -> str:
    if not source:
        return "G0 none"
    return SOURCE_GROUP.get(source, "G11 other")


def origin_of(state: str, pointer: str | None, src41: str | None) -> str:
    """The step that set the value of a link: its first source, or a check that changed it."""
    p = pointer or ""
    for chk in ("review-4d", "review-4f", "review-7", "review-8", "review-user"):
        if p.startswith(chk):
            return {"review-user": "user"}.get(chk, chk.replace("review-", "r"))
    if p.startswith("review:ai/part-9"):
        return "r5"
    if p.startswith("review:ai/part-10"):
        return "r6"
    if p.startswith("review:ai/part-11"):
        return "r8"
    if p.startswith("review:ai/part-"):
        return "AB"
    if p.startswith(PTR_V44):
        return "r9"          # AI round 9 (v4.4) set the row with a web check
    if p.startswith("review:decisions") or p.startswith("manual/"):
        return "user"        # also manual/v42_: the user audited every change of v4.2
    if state == "moved":
        return "AB"          # an organisation-level answer of rounds 1-5 changed the link
    return "source"


def change_state(o3: str | None, o3_final: str | None, o41: str | None) -> str:
    if o3 is None and o41 is None:
        return "none"
    if o3 is None:
        return "added"
    if o41 is None:
        return "dropped"
    return "same" if o3_final == o41 else "moved"


def md_table(rows: list[dict], cols: list[str] | None = None) -> str:
    if not rows:
        return "(no rows)\n"
    cols = cols or list(dict.fromkeys(k for r in rows for k in r))
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        out.append("| " + " | ".join(fmt(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out) + "\n"


def fmt(v) -> str:
    if isinstance(v, float):
        if math.isnan(v):
            return "n/a"
        if math.isinf(v):
            return "inf"
        if abs(v) >= 1000:
            return f"{v:,.0f}"
        return f"{v:.4g}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def key_hash(domain: str) -> str:
    return hashlib.sha256(("s8-error-model:" + domain).encode()).hexdigest()[:16]


def pct(x: float, d: int = 3) -> float:
    return round(100 * x, d)


# --------------------------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: (round(v, 8) if isinstance(v, float) else v) for c, v in r.items()})


def attach_ro(c, path: Path, alias: str) -> None:
    """ATTACH a database read only. DuckDB attaches one file only once, so a file that is already
    attached gets a schema `alias` of views on it instead (the same names: alias.table)."""
    path = Path(path).resolve()
    for name, p in c.execute("SELECT database_name, path FROM duckdb_databases() WHERE path IS NOT NULL").fetchall():
        if p and Path(p).resolve() == path:
            c.execute(f"CREATE SCHEMA {alias}")
            for (t,) in c.execute("SELECT table_name FROM duckdb_tables() WHERE database_name = ?", [name]).fetchall():
                c.execute(f"CREATE VIEW {alias}.{t} AS SELECT * FROM {name}.main.{t}")
            return
    c.execute(f"ATTACH '{path}' AS {alias} (READ_ONLY)")


def layer_version(db: Path, links: Path) -> str:
    """The version label of the evaluated layer: links.json, else the name of the database file."""
    lj = Path(links) / "links.json"
    if lj.exists():
        v = json.loads(lj.read_text()).get("organisations_version")
        if v:
            return v
    name = Path(db).name
    if name == "companies.v4.duckdb":
        return "v4.1"
    if name == "companies.duckdb":
        return "v3"
    return name.removeprefix("companies.").removesuffix(".duckdb")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def domain_link_table(c, name: str, folder: Path) -> None:
    """Table `name` (domain, org, kind, match, md) of the domain links of a folder of either format
    (link_format.py). org is firm_based_on_domain: the organisation id, or the pseudo id."""
    c.execute(f"CREATE TABLE {name} AS SELECT domain, firm_based_on_domain AS org, organisation_kind AS kind, "
              f"match, matched_domain AS md FROM ({domain_links_sql(c, Path(folder) / 'domain_links.parquet')})")


def project_link_table(c, name: str, folder: Path, db: str | None = None) -> None:
    """Table `name` of the project links of a folder (the columns of link_format.NEW_PROJECT_COLS).

    With a database alias `db`, the best namespace row (namespace_organisation_id, namespace_relation,
    namespace_evidence) of a new file comes from its company_namespace table. Stops when an owns
    value (firm_based_on_namespace) is not the best namespace row."""
    c.execute(f"CREATE TABLE {name} AS {project_links_sql(c, Path(folder) / 'project_links.parquet', db)}")
    bad = check_owns_agree(c, f"SELECT * FROM {name}")
    if bad:
        raise SystemExit(f"{folder}: {bad} projects have an owns value that is not the best namespace row")


def merge_ids(path: Path) -> set:
    """The merged ids (merge_id) of a merges file of a later layer (manual/v42_merges.csv, ...)."""
    return {r["merge_id"] for r in read_csv(path)} if path.exists() else set()


def add_db_links(c) -> list[str]:
    """Model v4.7: add to the table lc the exact links of the evaluated database that the link folder lacks.

    The link folder can be older than the database (the merged links of both layers were built with
    v4.6). A dataset domain with no link and an exact row in the database (cur) gets the link that
    build_links.py gives it: the organisation is not rejected; an academic or government domain never
    matches a company or consultancy; a dropped domain matches nothing; a free-provider domain gives
    free-provider; a pseudo organisation gives its pseudo id. Suffix matches of new rows are not added
    (they stay unmatched until the links are built again). Returns the domains of the links added."""
    from build_links import COMPANY_KINDS as LINK_COMPANY_KINDS, EDU_GOV_SQL, FREE_SUFFIXES, PSEUDO_KINDS
    free = " OR ".join(f"t.domain = '{s}' OR t.domain LIKE '%.{s}'" for s in FREE_SUFFIXES)
    edu = EDU_GOV_SQL.format(d="t.domain")
    kinds = ", ".join(f"'{k}'" for k in LINK_COMPANY_KINDS)
    pk = ", ".join(f"'{k}'" for k in PSEUDO_KINDS)
    try:
        c.execute("SELECT 1 FROM cur.company_domain_dropped LIMIT 1")
        not_dropped = "AND t.domain NOT IN (SELECT domain FROM cur.company_domain_dropped)"
    except Exception:          # an older database has no table of dropped domains
        not_dropped = ""
    c.execute(f"""
      CREATE TEMP TABLE lc_added AS
      SELECT t.domain,
             CASE WHEN {free} THEN 'free-provider' WHEN o.kind IN ({pk}) THEN o.kind ELSE o.company_id END,
             CASE WHEN {free} THEN 'free-provider' ELSE o.kind END, 'exact', t.domain
      FROM tok_ev t JOIN cur.company_domain d ON d.domain = t.domain
      JOIN cur.company o ON o.company_id = d.company_id
      WHERE o.review_status <> 'rejected' AND t.domain LIKE '%.%' AND NOT contains(t.domain, chr(64))
        AND NOT ({edu} AND o.kind IN ({kinds})) {not_dropped}
        AND t.domain NOT IN (SELECT domain FROM lc)""")
    c.execute("INSERT INTO lc (domain, org, kind, match, md) SELECT * FROM lc_added")
    return [x for (x,) in c.execute("SELECT domain FROM lc_added").fetchall()]


def chain_domain_table(c) -> int:
    """The table tok_chain (domain, tokens): the domains of the chain of the evaluated layer.

    Each domain of tok_ev with tokens, plus each domain of lc that has no tokens in tok_ev, with
    tokens 0. The link folder can hold a domain that the token tables of the model do not have: the
    final write counts its own tokens (on 2026-10-27, 3 links of 16,119). Such a link gets its chain
    row and its p_error by the rule of the other rows (current_origin; band of 0 tokens); its 0 tokens
    change no token share. Returns the number of links with tokens 0."""
    c.execute("""CREATE TABLE tok_chain AS
      SELECT domain, tokens FROM tok_ev WHERE tokens > 0
      UNION ALL
      SELECT DISTINCT domain, 0::BIGINT FROM lc
      WHERE domain NOT IN (SELECT domain FROM tok_ev WHERE tokens > 0)""")
    return c.execute("SELECT count(*) FROM tok_chain WHERE tokens = 0").fetchone()[0]


def later_layer(ptr: str | None) -> tuple[str, str] | None:
    """(layer, origin) of a row of a later AI layer from its source pointer: manual/v4N_ or review/v4N_
    with N >= 7 gives (v4.N, r(N+3)); v4.7 is round 10. Other pointers: None."""
    m = LATER_PTR.match(ptr or "")
    if not m or int(m.group(1)) < LATER_MIN:
        return None
    n = int(m.group(1))
    return f"v4.{n}", f"r{n + 3}"


def later_origin(ptr: str | None, keys: set, decide_keys: set) -> tuple[str, str] | None:
    """(origin, rule) of a row of a later AI layer (model v4.7), else None. A row whose key the AI
    could not decide (an item of class decide of the check page of the round) is a user decision."""
    lay = later_layer(ptr)
    if lay is None:
        return None
    if keys & decide_keys:
        return "user", f"{lay[0]} row (user decision: the AI could not decide)"
    return lay[1], f"{lay[0]} row (round {lay[1][1:]})"


class Data:
    """Everything the model reads, loaded once."""

    def __init__(self, ws: Path, study: Path = HERE, db: Path | None = None, links: Path | None = None,
                 model: str = "v4.6", x1k: Path | None = None):
        import duckdb
        self.ws, self.study, self.model = ws, study, model
        dflt = DEFAULTS[model]
        self.db = Path(db) if db else ws / dflt["db"]
        self.links = Path(links) if links else ws / dflt["links"]
        self.x1k = (Path(x1k) if x1k else ws / dflt["x1k"]) if model != "v4.6" else None
        # The label of the evaluated layer: the database (model v4.7: the links may be older).
        self.version = layer_version(self.db, self.links) if model == "v4.6" else \
            layer_version(self.db, Path("/nonexistent"))
        c = self.con = duckdb.connect()
        c.execute("SET threads TO 2")
        c.execute(f"ATTACH '{ws / 'companies.duckdb'}' AS v3 (READ_ONLY)")
        c.execute(f"ATTACH '{ws / 'v4.0-20261018/companies.v4.duckdb'}' AS v40 (READ_ONLY)")
        c.execute(f"ATTACH '{ws / 'companies.v4.duckdb'}' AS v41 (READ_ONLY)")
        attach_ro(c, self.db, "cur")            # the evaluated layer
        # Tokens: only the columns domain and tokens of the cache, plus the file name (the project).
        c.execute(f"""CREATE TABLE tok_pd AS SELECT regexp_extract(filename, '([^/]+)\\.parquet$', 1) AS proj,
                      coalesce(domain, '') AS domain, sum(tokens)::BIGINT AS tokens
                      FROM read_parquet('{ws / 'cache'}/*.parquet', filename = true) GROUP BY ALL""")
        c.execute("CREATE TABLE tok AS SELECT domain, sum(tokens)::BIGINT AS tokens FROM tok_pd GROUP BY 1")
        # The tokens of the evaluated layer (tok_ev, tok_pd_ev): version 1 (model v4.6), or version 1
        # plus the domain counts of the extension (model v4.7). tok and tok_pd stay version 1: the
        # history that gives the parameters.
        if self.x1k is None:
            c.execute("CREATE VIEW tok_pd_ev AS SELECT * FROM tok_pd")
            c.execute("CREATE VIEW tok_ev AS SELECT * FROM tok")
        else:
            c.execute(f"""CREATE TABLE tok_pd_ev AS SELECT proj, domain, sum(tokens)::BIGINT AS tokens FROM (
                            SELECT proj, domain, tokens FROM tok_pd UNION ALL
                            SELECT replace(project, '/', '__') AS proj, coalesce(domain, '') AS domain, tokens
                            FROM read_parquet('{self.x1k}')) GROUP BY ALL""")
            c.execute("CREATE TABLE tok_ev AS SELECT domain, sum(tokens)::BIGINT AS tokens FROM tok_pd_ev GROUP BY 1")
        self.total_v1 = c.execute("SELECT sum(tokens) FROM tok").fetchone()[0]
        self.total = c.execute("SELECT sum(tokens) FROM tok_ev").fetchone()[0]
        # Domain links: l3, l40, l41 (the history) and lc (the evaluated layer), in the new names of
        # link_format.py. org: the organisation id (an old file has only the kind of a pseudo id).
        for v, p in (("l3", ws / "links"), ("l40", ws / "v4.0-20261018/links-v4"), ("l41", ws / "links-v4"),
                     ("lc", self.links)):
            domain_link_table(c, v, p)
        self.added_domains = set(add_db_links(c)) if model != "v4.6" else set()
        self.links_added = len(self.added_domains)
        self.links_no_tokens = chain_domain_table(c)
        # Project links: p3 (v3, for the comparison) and pc (the evaluated layer; the best namespace
        # row comes from the company_namespace table of the evaluated database).
        project_link_table(c, "p3", ws / "links")
        project_link_table(c, "pc", self.links, "cur")
        # Model v4.7: the review paths of the organisations before the later AI rounds (database v4.6).
        self.has_prev = False
        prev = ws / PREV_DB
        if model != "v4.6" and prev.exists() and prev.resolve() != self.db.resolve():
            attach_ro(c, prev, "prev")
            self.has_prev = True
        alias = c.execute("SELECT alias, company_id FROM v41.company_alias WHERE source = 'v4-merge-id'").fetchall()
        self.merge = dict(alias)
        alias = c.execute("SELECT alias, company_id FROM cur.company_alias WHERE source = 'v4-merge-id'").fetchall()
        self.merge_cur = dict(alias)
        # The merges of the later layers (the user audited v4.2; round 9 decided v4.4).
        self.m42 = merge_ids(study / "manual/v42_merges.csv")
        self.m44 = merge_ids(study / "manual/v44_merges.csv")
        # The organisations that v4.2 changed: the stamp R42_STAMP in companies.v4.2.duckdb.
        self.r42 = set()
        p42 = ws / "companies.v4.2.duckdb"
        if p42.exists():
            attach_ro(c, p42, "v42")
            self.r42 = {x for (x,) in c.execute("SELECT company_id FROM v42.company WHERE reviewer = ? AND "
                                                "review_date::VARCHAR = ?", list(R42_STAMP)).fetchall()}
        ids3 = [r[0] for r in c.execute("SELECT company_id FROM v3.company").fetchall()]
        c.execute("CREATE TABLE mm (old VARCHAR, new VARCHAR)")
        c.executemany("INSERT INTO mm VALUES (?, ?)", [(i, self.final(i)) for i in ids3])
        c.execute("CREATE TABLE mmc (old VARCHAR, new VARCHAR)")
        c.executemany("INSERT INTO mmc VALUES (?, ?)", [(i, self.final_cur(i)) for i in ids3])
        rd = ws / "review"
        corr = read_csv(rd / "ai/rule_corrections.csv")
        self.corrections = corr
        self.checks = {}
        for name, f in (("r4d", "domain_links_review"), ("r4f", "lookalike_review"), ("r7", "sweep_review"),
                        ("r8", "conflict_domains")):
            self.checks[name] = {r["domain"]: r for r in read_csv(rd / f"ai/{f}.csv")}
        self.user_dom = {r["domain"]: r for r in read_csv(rd / "decisions.domains.chat.csv")}
        self.compare = {r["item_id"]: r for r in read_csv(rd / "ai/compare-0-4.csv")}
        self.r5 = {r["item_id"]: r for r in read_csv(rd / "ai/part-9.csv")}
        self.part = {}
        for i in range(1, 9):
            for r in read_csv(rd / f"ai/part-{i}.csv"):
                self.part[r["item_id"]] = r
        self.r4 = {}
        for f in sorted(glob.glob(str(rd / "ai/r4/out-*.csv"))):
            for r in read_csv(Path(f)):
                self.r4[r["item_id"]] = r

    def final(self, cid: str | None) -> str | None:
        """The organisation of an id after the merges of v4.1."""
        seen = set()
        while cid in self.merge and cid not in seen:
            seen.add(cid)
            cid = self.merge[cid]
        return cid

    def final_cur(self, cid: str | None) -> str | None:
        """The organisation of an id after the merges of the evaluated layer."""
        return merge_walk(cid, self.merge_cur)[-1]

    def q(self, sql: str, *a):
        return self.con.execute(sql, *a).fetchall()


def merge_walk(cid: str | None, merge: dict) -> list:
    """The ids on the merge path of cid: cid, the id it merged into, ..., the final id."""
    out, seen = [cid], {cid}
    while cid in merge and merge[cid] not in seen:
        cid = merge[cid]
        seen.add(cid)
        out.append(cid)
    return out


# --------------------------------------------------------------------------------------------
# Model steps
# --------------------------------------------------------------------------------------------

# The checks that came after the step that set a value (r9 and the user decisions: none).
AFTER = {"source": ["r4d", "r4f", "r7", "r8"], "r4d": ["r7", "r8"], "r4f": ["r7", "r8"],
         "AB": ["r7", "r8"], "r5": ["r7", "r8"], "r6": ["r7", "r8"], "r7": ["r8"],
         "r8": [], "r9": [], "user": [], "dropped": []}


def link_chain(d: Data) -> list[dict]:
    """One row per dataset domain with tokens: its link in v3, v4.0 and v4.1 and its path."""
    rows = d.q("""
      SELECT t.domain, t.tokens,
             l3.org, l3.kind, l3.md, s3.source, coalesce(mm.new, l3.org),
             l40.md,
             l41.org, l41.kind, l41.match, l41.md, s41.source, s41.source_pointer
      FROM tok t
      LEFT JOIN l3 USING (domain) LEFT JOIN v3.company_domain s3 ON s3.domain = l3.md
      LEFT JOIN mm ON mm.old = l3.org
      LEFT JOIN l40 USING (domain)
      LEFT JOIN l41 USING (domain) LEFT JOIN v41.company_domain s41 ON s41.domain = l41.md
      WHERE t.tokens > 0 ORDER BY t.domain""")
    out = []
    ck = d.checks
    for (dom, tokens, o3, k3, md3, src3, o3f, md40, o41, k41, m41, md41, src41, ptr41) in rows:
        st = change_state(o3, o3f, o41)
        if st == "none":
            continue
        keys = {k for k in (md3, md40, md41, dom) if k}
        seen = {c: any(k in ck[c] for k in keys) for c in ("r4d", "r4f", "r7", "r8")}
        seen["user"] = any(k in d.user_dom for k in keys)
        r7 = next((ck["r7"][k] for k in (md40, md41, md3) if k and k in ck["r7"]), None)
        # Checks after the step that set the current value.
        origin = origin_of(st, ptr41, src41) if o41 is not None else "dropped"
        after = AFTER[origin]
        later = [c for c in after if seen[c]]
        out.append({
            "domain": dom, "tokens": int(tokens), "band": band(tokens), "state": st,
            "o3": o3, "o3f": o3f, "kind3": k3, "src3": src3, "group3": group_of(src3) if o3 else None,
            "o41": o41, "kind41": k41, "match41": m41, "src41": src41,
            "group41": group_of(src41) if o41 else None, "origin": origin,
            "seen": seen, "later": later, "r7_action": r7["action"] if r7 else "",
            "kc3": kclass(k3), "kc41": kclass(k41),
        })
    return out


# The rule that set the origin of a link of the evaluated layer (the table later_layers).
LAYER_RULES = ("same row as v4.1", "same row as v4.1, v4.4 merge (+ q_r9)", "same row as v4.1, v4.2 merge",
               "same row as v4.1, other id change", "v4.2 row (user audited)", "v4.4 row (round 9)",
               "other new or changed row", "dropped")


def current_origin(st: str, ptr: str | None, src: str | None, oc: str | None, r41: dict | None,
                   md: str | None, md41: str | None, ptr41: str | None, merge_cur: dict, m42: set, m44: set):
    """(origin, later checks or None, round 9 merge term, rule) of one link of the evaluated layer.

    A row of a later layer (pointer manual/v42_ or manual/v44_) takes the origin of that layer. The
    same domain row as in v4.1 (same matched domain and pointer) keeps the v4.1 origin and checks:
    a later merge only renamed its organisation. A v4.4 merge on the merge path of the v4.1 id adds
    the round 9 term; a v4.2 merge adds nothing (the user audited it). Other rows: origin_of."""
    p = ptr or ""
    if oc is None:
        return "dropped", None, False, "dropped"
    if p.startswith(PTR_V44):
        return origin_of(st, ptr, src), None, False, "v4.4 row (round 9)"
    if p.startswith(PTR_V42):
        return origin_of(st, ptr, src), None, False, "v4.2 row (user audited)"
    if r41 is not None and r41["o41"] is not None and md == md41 and ptr == ptr41:
        o41 = r41["o41"]
        if oc == o41:
            return r41["origin"], r41["later"], False, "same row as v4.1"
        walk = merge_walk(o41, merge_cur)
        if walk[-1] == oc and len(walk) > 1:
            if any(x in m44 for x in walk[:-1]):
                return r41["origin"], r41["later"], True, "same row as v4.1, v4.4 merge (+ q_r9)"
            if any(x in m42 for x in walk[:-1]):
                return r41["origin"], r41["later"], False, "same row as v4.1, v4.2 merge"
        return r41["origin"], r41["later"], False, "same row as v4.1, other id change"
    return origin_of(st, ptr, src), None, False, "other new or changed row"


def current_chain(d: Data, chain41: list[dict]) -> list[dict]:
    """The chain of the evaluated layer: one row per dataset domain with tokens or a link (the propagation).

    The v3 fields are those of link_chain (o3f after the merges of the evaluated layer). The fields
    o41, kind41, match41, src41, group41 and kc41 hold the evaluated layer (the names stay for the
    readers). origin, later and r9_merge: current_origin."""
    by41 = {r["domain"]: r for r in chain41}
    rows = d.q("""
      SELECT t.domain, t.tokens,
             l3.org, l3.kind, l3.md, s3.source, coalesce(mmc.new, l3.org),
             l40.md, l41.md, s41.source_pointer,
             lc.org, lc.kind, lc.match, lc.md, sc.source, sc.source_pointer
      FROM tok_chain t
      LEFT JOIN l3 USING (domain) LEFT JOIN v3.company_domain s3 ON s3.domain = l3.md
      LEFT JOIN mmc ON mmc.old = l3.org
      LEFT JOIN l40 USING (domain)
      LEFT JOIN l41 USING (domain) LEFT JOIN v41.company_domain s41 ON s41.domain = l41.md
      LEFT JOIN lc USING (domain) LEFT JOIN cur.company_domain sc ON sc.domain = lc.md
      ORDER BY t.domain""")
    out = []
    ck = d.checks
    for (dom, tokens, o3, k3, md3, src3, o3f, md40, md41, ptr41, oc, kc_, mc, mdc, srcc, ptrc) in rows:
        st = change_state(o3, o3f, oc)
        if st == "none":
            continue
        keys = {k for k in (md3, md40, md41, mdc, dom) if k}
        seen = {c: any(k in ck[c] for k in keys) for c in ("r4d", "r4f", "r7", "r8")}
        seen["user"] = any(k in d.user_dom for k in keys)
        r7 = next((ck["r7"][k] for k in (md40, mdc, md41, md3) if k and k in ck["r7"]), None)
        origin, later, r9m, rule = current_origin(st, ptrc, srcc, oc, by41.get(dom), mdc, md41, ptr41,
                                                  d.merge_cur, d.m42, d.m44)
        lo = later_origin(ptrc, {dom, mdc}, getattr(d, "decide_keys", set())) \
            if getattr(d, "model", "v4.6") != "v4.6" and oc is not None else None
        if lo is not None:
            origin, rule = lo
            later, r9m = [], False
        if later is None:
            later = [c for c in AFTER[origin] if seen[c]]
        out.append({
            "domain": dom, "tokens": int(tokens), "band": band(tokens), "state": st,
            "o3": o3, "o3f": o3f, "kind3": k3, "src3": src3, "group3": group_of(src3) if o3 else None,
            "o41": oc, "kind41": kc_, "match41": mc, "src41": srcc,
            "group41": group_of(srcc) if oc else None, "origin": origin,
            "seen": seen, "later": later, "r7_action": r7["action"] if r7 else "",
            "kc3": kclass(k3), "kc41": kclass(kc_), "r9_merge": r9m, "layer_rule": rule,
        })
    return out


def source_raw_error(chain: list[dict]) -> tuple[list[dict], dict]:
    """Detected change share of each source on its v3 links (raw error lower bound)."""
    agg = defaultdict(lambda: Counter())
    for r in chain:
        if r["o3"] is None:
            continue
        g, b, kc = r["group3"], r["band"], r["kc3"]
        for key in ((g, b, kc), (g, b, "*"), (g, "all", kc), (g, "all", "*")):
            a = agg[key]
            a["n"] += 1
            a["tok"] += r["tokens"]
            if r["state"] in ("moved", "dropped"):
                a["k"] += 1
                a["ktok"] += r["tokens"]
                a["k_" + r["state"]] += 1
                if r["state"] == "moved" and r["o41"] in PSEUDO:
                    a["k_to_pseudo"] += 1
    rows = []
    for (g, b, kc), a in sorted(agg.items()):
        if kc != "*" and b != "all":
            continue
        lo, hi = wilson(a["k"], a["n"])
        rows.append({"group": g, "band": b, "class": kc, "links": a["n"], "tokens": a["tok"], "changed": a["k"],
                     "moved": a["k_moved"], "dropped": a["k_dropped"], "to_pseudo": a["k_to_pseudo"],
                     "share_links_pct": pct(a["k"] / a["n"]), "wilson_lo_pct": pct(lo), "wilson_hi_pct": pct(hi),
                     "share_tokens_pct": pct(a["ktok"] / a["tok"]) if a["tok"] else 0.0})
    return rows, {k: dict(v) for k, v in agg.items()}


def source_raw_error_rows(d: Data) -> list[dict]:
    """The same at the level of the database rows (all v3 domain rows, also rows with no tokens)."""
    rows = d.q("""SELECT c3.domain, c3.source, c3.company_id, c41.company_id, dr.source
                  FROM v3.company_domain c3 LEFT JOIN v41.company_domain c41 USING (domain)
                  LEFT JOIN v41.company_domain_dropped dr USING (domain)""")
    agg = defaultdict(Counter)
    for dom, src, c3, c41, drop in rows:
        g = group_of(src)
        a = agg[g]
        a["n"] += 1
        f3 = d.final(c3)
        if c41 is None:
            a["dropped"] += 1
        elif c41 != f3:
            a["moved"] += 1
            if c41 in PSEUDO:
                a["to_pseudo"] += 1
    out = []
    for g, a in sorted(agg.items()):
        k = a["dropped"] + a["moved"]
        lo, hi = wilson(k, a["n"])
        out.append({"group": g, "rows": a["n"], "changed": k, "moved": a["moved"], "dropped": a["dropped"],
                    "to_pseudo": a["to_pseudo"], "share_pct": pct(k / a["n"]), "wilson_lo_pct": pct(lo),
                    "wilson_hi_pct": pct(hi)})
    return out


def row_tokens(d: Data, version: str) -> dict:
    """Tokens of each database domain row: the dataset domains that the row matched in a version."""
    t = {"v3": "l3", "v40": "l40", "v41": "l41"}[version]
    return dict(d.q(f"SELECT {t}.md, sum(tok.tokens) FROM {t} JOIN tok USING (domain) GROUP BY 1"))


def check_rates(d: Data) -> list[dict]:
    """Change share of each link check on the rows it saw, and the reversed changes."""
    t3, t40, t41 = row_tokens(d, "v3"), row_tokens(d, "v40"), row_tokens(d, "v41")
    rev = Counter()
    for c in d.corrections:
        f = c["file"]
        rev["r7" if f.startswith("r7/") else "r4f" if "lookalike" in f else "r4d" if "domains" in f else "r8"] += 1
    out = []
    for name, rows in d.checks.items():
        tt = {"r7": t40, "r8": t41}.get(name, t3)
        n = len(rows)
        acts = Counter(r["action"] for r in rows.values())
        ch = n - acts.get("keep", 0)
        tok = sum(tt.get(k, 0) for k in rows)
        chtok = sum(tt.get(k, 0) for k, r in rows.items() if r["action"] != "keep")
        raw = ch + rev[name]          # the corrected rows were changes before the correction
        lo, hi = wilson(ch, n)
        out.append({"check": name, "rows_seen": n, "keep": acts.get("keep", 0), "move": acts.get("move", 0),
                    "drop": acts.get("drop", 0), "change_pct": pct(ch / n), "wilson_lo_pct": pct(lo),
                    "wilson_hi_pct": pct(hi), "tokens_seen": tok,
                    "change_tokens_pct": pct(chtok / tok) if tok else 0.0,
                    "reversed_by_rule_corrections": rev[name],
                    "reversed_share_of_raw_changes_pct": pct(rev[name] / raw) if raw else 0.0,
                    "note": "the file holds only the domain answers of 801 conflicts, so every row is a change"
                    if name == "r8" else ""})
    u = d.user_dom
    ua = Counter(r["action"] for r in u.values())
    out.append({"check": "user (chat)", "rows_seen": len(u), "keep": ua.get("keep", 0), "move": ua.get("move", 0),
                "drop": ua.get("drop", 0), "change_pct": pct((len(u) - ua.get("keep", 0)) / len(u)) if u else 0.0,
                "tokens_seen": sum(t41.get(k, t3.get(k, 0)) for k in u), "note": "the user's domain decisions"})
    return out


def check_pairs(d: Data) -> tuple[list[dict], dict]:
    """Round 4d or 4f, then round 7 on the same rows: a two-pass removal design."""
    ck = d.checks
    out, par = [], {}
    for first in ("r4d", "r4f"):
        rows = ck[first]
        n = len(rows)
        n1 = sum(1 for r in rows.values() if r["action"] != "keep")
        kept = [k for k, r in rows.items() if r["action"] == "keep"]
        kept_seen = [k for k in kept if k in ck["r7"]]
        n2 = sum(1 for k in kept_seen if ck["r7"][k]["action"] != "keep")
        moved = [r for r in rows.values() if r["action"] == "move"]
        moved_seen = [r for r in moved if r["domain"] in ck["r7"]]
        moved_changed = sum(1 for r in moved_seen if ck["r7"][r["domain"]]["action"] != "keep")
        p, n0 = removal_two_pass(n1, n2)
        out.append({"pair": f"{first} then r7", "rows": n, "pass1_changes": n1, "kept": len(kept),
                    "kept_seen_by_r7": len(kept_seen), "pass2_changes": n2,
                    "pass2_share_pct": pct(n2 / len(kept_seen)) if kept_seen else 0.0,
                    "removal_p": round(p, 4), "removal_N0": round(n0, 2),
                    "residual_errors": round(n0 - n1 - n2, 2),
                    "moves_seen_by_r7": len(moved_seen), "moves_r7_changed": moved_changed})
        par[first] = {"n1": n1, "n2": n2, "kept_seen": len(kept_seen), "moves_seen": len(moved_seen),
                      "moves_changed": moved_changed}
    return out, par


def items_ab(d: Data) -> tuple[list[dict], dict]:
    """Rounds 3 (A, not blind: it had an old hint) and 4 (B, blind), adjudicated by round 5."""
    groups = defaultdict(Counter)
    for iid, c in d.compare.items():
        typ = iid.split(":", 1)[0]
        tok = float(c["tokens"] or 0)
        if c["state"] in ("agree", "agree-high"):
            cls = "agree"
        else:
            note = d.r5.get(iid, {}).get("note", "")
            head = note.split(":", 1)[0].strip()
            cls = {"A=B": "form", "A": "A_right", "B": "B_right", "new": "both_wrong"}.get(head, "unknown")
        for g in (typ, "all"):
            groups[g][cls] += 1
            groups[g][cls + "_tok"] += tok
            groups[g]["n"] += 1
            groups[g]["tok"] += tok
    out, par = [], {}
    for g in ("all", "company", "conflict"):
        a = groups[g]
        for w_name, suf, tot in (("items", "", a["n"]), ("tokens", "_tok", a["tok"])):
            x = a["B_right" + suf] / tot   # only A wrong
            y = a["A_right" + suf] / tot   # only B wrong
            w = a["both_wrong" + suf] / tot
            res = {rho: two_rater(x, y, w, rho) for rho in (0.0, 0.25, 0.5, 1.0)}
            out.append({"items": g, "weight": w_name, "n": a["n"], "agree": a["agree"], "form_only": a["form"],
                        "rho_min": round(rho_min(x, y, w), 4), "rho_max": round(rho_max(x, y, w), 4),
                        "A_right": a["A_right"], "B_right": a["B_right"], "both_wrong": a["both_wrong"],
                        "a_err_pct": pct(res[0.0]["a"]), "b_err_pct": pct(res[0.0]["b"]),
                        "agreed_wrong_rho0_pct": pct(res[0.0]["agree_wrong"]),
                        "agreed_wrong_rho0.25_pct": pct(res[0.25]["agree_wrong"]),
                        "agreed_wrong_rho0.5_pct": pct(res[0.5]["agree_wrong"]),
                        "agreed_wrong_rho1_pct": pct(res[1.0]["agree_wrong"])})
            par[(g, w_name)] = {"x": x, "y": y, "w": w, "n": tot, **res[0.0]}
    return out, par


def items_lp(d: Data) -> tuple[list[dict], dict]:
    """Capture-recapture of the errors in the v3 organisation rows: A and B are the two samples."""
    def change(r):
        return r is not None and r.get("action") in ("edit", "reject")
    out, par = [], {}
    for typ in ("company",):
        n1 = n2 = m = fp_a = fp_b = 0
        for iid, c in d.compare.items():
            if not iid.startswith(typ + ":"):
                continue
            a, b = d.part.get(iid), d.r4.get(iid)
            fin = d.r5.get(iid) if c["state"] == "differ" else a
            if not change(fin):
                fp_a += change(a)
                fp_b += change(b)
                continue
            ca, cb = change(a), change(b)
            n1 += ca
            n2 += cb
            m += ca and cb
        lp = lincoln_petersen(n1, n2, m)
        nc, var = chapman(n1, n2, m)
        seen = n1 + n2 - m
        out.append({"items": typ, "errors_found_by_A": n1, "errors_found_by_B": n2, "by_both": m,
                    "found_by_either": seen, "lincoln_petersen_N": round(lp, 1), "chapman_N": round(nc, 1),
                    "chapman_sd": round(math.sqrt(var), 1), "missed_by_both": round(nc - seen, 1),
                    "missed_share_of_errors_pct": pct((nc - seen) / nc),
                    "p_A": round(m / n2, 4), "p_B": round(m / n1, 4),
                    "false_changes_A": fp_a, "false_changes_B": fp_b})
        par[typ] = {"pA": m / n2, "pB": m / n1, "missed": nc - seen, "N": nc, "var": var, "seen": seen}
    return out, par


ANSWER_FIELDS = ("action", "kind", "name", "parent_company_id", "merge_into", "sna_sector", "qid")


def user_calibration(d: Data) -> tuple[int, int]:
    """The user's decisions against the AI suggestion of rounds 1-2 for the same item.

    The user saw the suggestion (so the share is a lower bound of the AI error, by anchoring).
    Returns (decisions that differ from the suggestion, decisions with a suggestion).
    """
    sugg = {}
    for i in range(1, 8):
        for r in read_csv(d.ws / f"review/ai/part-{i}.csv"):
            sugg[r["item_id"]] = r          # the later part wins
    k = n = 0
    for r in read_csv(d.ws / "review/decisions.csv"):
        a = sugg.get(r["item_id"])
        if a is None:
            continue
        n += 1
        k += tuple(a.get(f, "") for f in ANSWER_FIELDS) != tuple(r.get(f, "") for f in ANSWER_FIELDS)
    return k, n


DOMAIN_ANSWER_FIELDS = ("action", "move_to")


def reversal_records(files: list[tuple[str, list[dict]]]) -> dict:
    """All answers of each item: {item: {decided_utc: answer}} over the decision files.

    files: (kind, rows) with kind "item" (organisation items; key item_id) or "domain" (domain
    decisions; key link_id). A snapshot of the history holds the same row again; the same
    decided_utc with the same answer is one decision."""
    rec = defaultdict(dict)
    for kind, rows in files:
        fields, key = (ANSWER_FIELDS, "item_id") if kind == "item" else (DOMAIN_ANSWER_FIELDS, "link_id")
        for r in rows:
            item = kind + ":" + r.get(key, "")
            rec[item][r.get("decided_utc", "")] = tuple((r.get(f) or "").strip() for f in fields)
    return dict(rec)


def count_reversals(rec: dict, final_items: set | None = None) -> dict:
    """k = items with two or more different answers (the later decided_utc wins); N = items.

    withdrawn = items of an earlier snapshot with no row in the final files (a decision taken
    back with no new answer). They are not in k; the parameters table gives them apart."""
    k = sum(1 for v in rec.values() if len(set(v.values())) > 1)
    withdrawn = 0 if final_items is None else sum(1 for i in rec if i not in final_items)
    return {"k": k, "n": len(rec), "withdrawn": withdrawn}


def user_reversals(ws: Path) -> tuple[int, int, dict]:
    """The user's reversal count from the decision files and their saved history (counts only).

    Reads review/decisions.csv, review/history/decisions.*.csv, review/decisions.chat.csv and
    review/decisions.domains.chat.csv. The final audit (review/audit-final/verdicts.csv and its
    history) changed no definite answer: its changes are from "unsure" (no answer) to "ok", and its
    comments correct database rows, not earlier decisions of the user. The function counts its
    sheets with two different definite answers, so that a later change shows.
    Returns (k, N, detail)."""
    rd = ws / "review"
    hist = sorted(glob.glob(str(rd / "history/decisions.*.csv")))
    final = read_csv(rd / "decisions.csv")
    chat = read_csv(rd / "decisions.chat.csv") if (rd / "decisions.chat.csv").exists() else []
    dchat = read_csv(rd / "decisions.domains.chat.csv") if (rd / "decisions.domains.chat.csv").exists() else []
    files = [("item", read_csv(Path(f))) for f in hist] + [("item", final), ("item", chat), ("domain", dchat)]
    rec = reversal_records(files)
    final_items = {"item:" + r["item_id"] for r in final + chat} | {"domain:" + r["link_id"] for r in dchat}
    c = count_reversals(rec, final_items)
    vfiles = sorted(glob.glob(str(rd / "audit-final/history/verdicts.*.csv"))) + [str(rd / "audit-final/verdicts.csv")]
    vrec = defaultdict(set)
    for f in vfiles:
        if Path(f).exists():
            for r in read_csv(Path(f)):
                if r.get("verdict") in ("ok", "wrong"):      # definite answers only
                    vrec[(r.get("view"), r.get("key"))].add((r["verdict"], r.get("right_value", "")))
    c.update({"snapshots": len(hist), "audit_sheets": len(vrec),
              "audit_sheets_changed": sum(1 for v in vrec.values() if len(v) > 1)})
    return c["k"], c["n"], c


def reversal_term(k: int, n: int) -> dict:
    """The error of one user decision: the reversal rate r = k / N, u = sqrt(r (1 - r) / N).

    With k = 0 the rate has no spread; the rule of three gives the 95% upper bound 3 / N, and the
    term is rectangular from 0 to 3 / N (mean 1.5 / N, u = 3 / (N sqrt 12))."""
    if n <= 0:
        return {"k": k, "n": n, "r": 0.0, "u": 0.0, "basis": "no decisions"}
    if k == 0:
        hi = 3.0 / n
        return {"k": 0, "n": n, "r": hi / 2, "u": rectangular_u(hi / 2), "hi": hi,
                "basis": f"k = 0: rule of three, rectangular 0 to {round(hi, 5)}"}
    r = k / n
    return {"k": k, "n": n, "r": r, "u": math.sqrt(r * (1 - r) / n), "basis": "binomial rate, u = sqrt(r(1-r)/N)"}


def reversal_draw(rng: random.Random, t: dict) -> float:
    """One draw of the user error: a Beta with mean r and standard deviation u (method of moments:
    Beta(r (N - 1), (1 - r) (N - 1))); with k = 0, rectangular from 0 to 3 / N."""
    if t["n"] <= 1:
        return t["r"]
    if t["k"] == 0:
        return rng.uniform(0.0, t["hi"])
    return rng.betavariate(t["r"] * (t["n"] - 1), (1 - t["r"]) * (t["n"] - 1))


def phi_kind(d: Data) -> tuple[int, int]:
    """Share of the real disagreements on organisation items that involve the kind."""
    k = n = 0
    for iid, c in d.compare.items():
        if not iid.startswith("company:") or c["state"] != "differ":
            continue
        head = d.r5.get(iid, {}).get("note", "").split(":", 1)[0].strip()
        if head == "A=B":
            continue
        n += 1
        k += "kind" in (c["differs"] or "").split(";")
    return k, n


def rho_for_error(x: float, y: float, w: float, target: float) -> float:
    """The error correlation at which the mean single-review error (a + b) / 2 equals target."""
    if (two_rater(x, y, w, 0.0)["a"] + two_rater(x, y, w, 0.0)["b"]) / 2 >= target:
        return 0.0
    lo, hi = 0.0, rho_max(x, y, w)
    for _ in range(60):
        m = (lo + hi) / 2
        t = two_rater(x, y, w, m)
        if (t["a"] + t["b"]) / 2 < target:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def org_paths(d: Data, db: str = "cur") -> dict:
    """The review path of each organisation of the evaluated layer (for the residual error of its kind).

    A row that round 9 set (R9_STAMP) has the path R9_PATH. A row that v4.2 changed (R42_STAMP, and
    the same stamp in companies.v4.2.duckdb) is a user decision: the user audited every change."""
    path = {}
    for cid, rev, status, rdate in d.q("SELECT company_id, coalesce(reviewer, ''), review_status, "
                                       f"coalesce(review_date::VARCHAR, '') FROM {db}.company"):
        item = d.compare.get("company:" + cid)
        if (rev, rdate) == R9_STAMP:
            p = R9_PATH
        elif (rev, rdate) == R42_STAMP and cid in d.r42:
            p = "user-or-curated"
        elif rev == "user" or rev.startswith("source:") and status == "accepted" and item is None:
            p = "user-or-curated"
        elif rev in ("claude-review-v6", "claude-review-v8", "claude-main"):
            p = "single AI review"
        elif item is not None and item["state"] == "differ":
            p = "adjudicated (r5)"
        elif item is not None:
            p = "agreed (A=B)"
        elif rev.startswith("claude-review"):
            p = "agreed (A=B)"
        else:
            p = "unreviewed"
        path[cid] = p
    for p in PSEUDO:
        path[p] = "user-or-curated"
    return path


def later_org_paths(d: Data, path: dict) -> dict:
    """Model v4.7: the review path of an organisation that a later AI round stamped (claude-main, a
    review date after round 9). It keeps its path of database v4.6 when it was there with the same
    kind (the round only added a domain or a namespace row to it). Else the round set the row: the
    path LATER_PATH (kind error: q of the later rounds times phi)."""
    has_prev = getattr(d, "has_prev", False)
    prev_path = org_paths(d, "prev") if has_prev else {}
    prev_kind = dict(d.q("SELECT company_id, kind FROM prev.company")) if has_prev else {}
    out = dict(path)
    for cid, kind, rev, rdate in d.q("SELECT company_id, kind, coalesce(reviewer, ''), "
                                     "coalesce(review_date::VARCHAR, '') FROM cur.company"):
        if rev == "claude-main" and rdate > LATER_STAMP_AFTER:
            out[cid] = prev_path[cid] if cid in prev_path and prev_kind.get(cid) == kind else LATER_PATH
    return out


def kind_changes(chain: list[dict]) -> dict:
    """Detected errors of the kind: link moves (kind3 -> kind41) and kind edits of one organisation."""
    link = Counter()
    org = Counter()
    for r in chain:
        if r["state"] == "moved":
            link[(r["kind3"] in COMPANY_KINDS, r["kind41"] in COMPANY_KINDS)] += 1
        elif r["state"] == "same" and r["kind3"] != r["kind41"]:
            org[(r["kind3"] in COMPANY_KINDS, r["kind41"] in COMPANY_KINDS)] += 1
        elif r["state"] == "dropped":
            link[(r["kind3"] in COMPANY_KINDS, None)] += 1
    org_same = Counter()
    for r in chain:
        if r["state"] == "same":
            org_same[r["kind3"] in COMPANY_KINDS] += 1
    return {"link": link, "org": org, "org_same": org_same}


def transition(cnt: Counter, shown_company: bool) -> tuple[float, float, float]:
    """P(true company), P(true not company), P(unknown) of a detected error of a shown class."""
    a = cnt.get((shown_company, True), 0)
    b = cnt.get((shown_company, False), 0)
    u = cnt.get((shown_company, None), 0)
    n = a + b + u
    if n == 0:
        return (0.5, 0.5, 0.0)
    return (a / n, b / n, u / n)


def unmatched_proposals(d: Data) -> dict:
    """The AI proposals of the unmatched domains, by domain (proposals/top_unmatched.v1.csv wins over v2)."""
    prop = {}
    for v in ("v2", "v1"):      # v1 wins over v2 (README)
        p = d.study / f"proposals/top_unmatched.{v}.csv"
        if p.exists():
            for r in read_csv(p):
                prop[r["domain"].lower()] = r
    return prop


def unmatched_rows(d: Data, prop: dict | None = None) -> list[tuple[str, int, str]]:
    """(domain, tokens, part) of each domain of the evaluated tokens with no link: the E2 pool.

    part: no_real_domain (blank, no dot, an at sign), proposed (a real domain with an AI proposal) or
    tail (a real domain with no proposal). The real domains (proposed and tail) are the unmatched real
    domains of the E2 term. The tail audit (review/audit_tail_sample.py) uses them as its frame."""
    prop = unmatched_proposals(d) if prop is None else prop
    rows = d.q("SELECT t.domain, t.tokens FROM tok_ev t LEFT JOIN lc USING (domain) WHERE lc.domain IS NULL")
    out = []
    for dom, tok in rows:
        if not dom or "." not in dom or AT in dom:
            out.append((dom, tok, "no_real_domain"))
        else:
            out.append((dom, tok, "proposed" if dom.lower() in prop else "tail"))
    return out


def unmatched(d: Data) -> dict:
    """Tokens with no link: no real domain, a domain with an AI proposal, and the tail."""
    prop = unmatched_proposals(d)
    c = Counter()
    for dom, tok, part in unmatched_rows(d, prop):
        if part == "no_real_domain":
            c["no_real_domain"] += tok
            continue
        pr = prop.get(dom.lower())
        if pr is None:
            c["tail"] += tok
            c["tail_n"] += 1
            continue
        k = pr.get("kind", "")
        pseudo = k in PSEUDO or pr.get("name") == "(Independent)"
        c["proposed"] += tok
        c["proposed_n"] += 1
        c["proposed_company"] += tok if k in COMPANY_KINDS else 0
        c["proposed_pseudo"] += tok if pseudo else 0
        # An organisation of any kind: not a pseudo kind and not blank (a blank kind is no answer).
        c["proposed_org"] += tok if k and not pseudo else 0
        c["kind:" + ("independent" if pseudo and k not in PSEUDO else (k or "(blank)"))] += tok
        c["kind_n:" + ("independent" if pseudo and k not in PSEUDO else (k or "(blank)"))] += 1
    return dict(c)


def unmatched_kinds(unm: dict) -> list[dict]:
    """Token share of each proposed kind among the unmatched domains with an AI proposal (counts only)."""
    tot = unm.get("proposed", 0)
    rows = []
    for key in sorted(k for k in unm if k.startswith("kind:")):
        kind = key.split(":", 1)[1]
        rows.append({"proposed_kind": kind, "domains": unm.get("kind_n:" + kind, 0), "tokens": unm[key],
                     "share_of_proposed_pct": pct(unm[key] / tot) if tot else 0.0,
                     "class": "company" if kind in COMPANY_KINDS else "pseudo" if kind in PSEUDO
                     else "no answer" if kind == "(blank)" else "other organisation"})
    rows.sort(key=lambda r: -r["tokens"])
    return rows


# The layer that set an owns row of the namespace table (its source pointer).
NS_LAYERS = (("manual/v43_", "v4.3 namespace rework"), ("manual/v44_", "v4.4 round 9"),
             ("manual/v45_", "v4.5 user rule"), ("manual/v46_", "v4.6 user rule"))


def namespace_layer(ptr: str | None) -> str:
    """The layer of an owns row from its source pointer: a later layer, or v4.1 or earlier."""
    for pre, name in NS_LAYERS:
        if (ptr or "").startswith(pre):
            return name
    lay = later_layer(ptr)
    if lay is not None:                  # a later AI layer (v4.7 = round 10, ...)
        return f"{lay[0]} round {lay[1][1:]}"
    return "v4.1 or earlier"


def namespace_model(d: Data, path: dict) -> tuple[list[dict], list[dict], dict]:
    """The namespace column: evidence of each owner row and the own-domain share of its projects."""
    # The evaluated layer (pc: the best namespace row; its owns rows are firm_based_on_namespace).
    proj = d.q("""SELECT p.project, p.namespace_organisation_id, p.namespace_relation,
                         p.namespace_evidence, o.kind, o.parent_company_id, pt.tokens,
                         coalesce(mmc.new, p3.namespace_organisation_id), p3.namespace_relation, np.ptr,
                         p.host, p.namespace, p3.project IS NOT NULL
                  FROM pc p LEFT JOIN cur.company o ON o.company_id = p.namespace_organisation_id
                  LEFT JOIN (SELECT host, lower(namespace) AS ns, company_id, min(source_pointer) AS ptr
                             FROM cur.company_namespace WHERE relation = 'owns' GROUP BY ALL) np
                         ON np.host = p.host AND np.ns = lower(p.namespace)
                        AND np.company_id = p.namespace_organisation_id AND p.namespace_relation = 'owns'
                  LEFT JOIN (SELECT proj, sum(tokens) AS tokens FROM tok_pd_ev GROUP BY 1) pt
                         ON pt.proj = replace(p.project, '/', '__')
                  LEFT JOIN p3 USING (project) LEFT JOIN mmc ON mmc.old = p3.namespace_organisation_id""")
    parent = dict(d.q("SELECT company_id, parent_company_id FROM cur.company WHERE parent_company_id IS NOT NULL"))
    children = defaultdict(set)
    for c, p in parent.items():
        children[p].add(c)
    own = defaultdict(lambda: defaultdict(int))
    for pr, org, tok in d.q("""SELECT t.proj, lc.org, sum(t.tokens) FROM tok_pd_ev t JOIN lc USING (domain)
                               GROUP BY ALL"""):
        own[pr][org] += tok
    agg = defaultdict(Counter)
    per = []
    v47 = getattr(d, "model", "v4.6") != "v4.6"
    for (project, oid, rel, ev, kind, par, tok, o3, rel3, ptr, host, nsp, in3) in proj:
        tok = tok or 0
        if oid is None:
            agg[("none", "-", "-")]["n"] += 1
            agg[("none", "-", "-")]["tok"] += tok
            continue
        fam = {oid} | children.get(oid, set()) | ({par} if par else set())
        o = own.get(project.replace("/", "__"), {})
        share = sum(v for k, v in o.items() if k in fam) / tok if tok else 0.0
        ev = ev or ""
        evc = "verified-domain" if "verified-domain" in ev else "company-page" if "company-page" in ev else \
            "roster" if "roster" in ev else ev.split(";")[0]
        kcls = "company" if kind in COMPANY_KINDS else "foundation-or-other"
        key = (rel, evc, kcls)
        # A change from v3: model v4.7 counts it only for a project of version 1 (an extension project
        # has no v3 row, so it has no change).
        changed = ((o3 != oid) or (rel3 != rel)) and (in3 or not v47)
        a = agg[key]
        a["n"] += 1
        a["tok"] += tok
        a["zero"] += share == 0
        a["zero_tok"] += tok if share == 0 else 0
        a["ge10"] += share >= 0.10
        a["changed"] += changed
        a["n3"] += bool(in3)
        a["reviewed_org"] += path.get(oid, "unreviewed") != "unreviewed"
        per.append({"project_hash": key_hash(project), "relation": rel, "evidence": evc, "owner_kind": kcls,
                    "tokens": tok, "own_share": share, "changed": changed,
                    "layer": namespace_layer(ptr), "ptr": ptr or "",
                    "ns_key": f"{host}/{nsp}#{oid}".lower(), "ns": f"{host}/{nsp}".lower(),
                    "project": project, "org": oid})   # project and org: only for the review list
    rows = []
    for (rel, evc, kcls), a in sorted(agg.items()):
        n = a["n"]
        lo, hi = wilson(a["zero"], n) if n else (0, 0)
        rows.append({"relation": rel, "evidence": evc, "owner_kind": kcls, "projects": n, "tokens": a["tok"],
                     "zero_own_share": a["zero"], "zero_own_pct": pct(a["zero"] / n) if n else 0.0,
                     "zero_wilson_hi_pct": pct(hi), "own_share_ge10_pct": pct(a["ge10"] / n) if n else 0.0,
                     "changed_v3_v41": a["changed"], "owner_reviewed": a["reviewed_org"]})
        if v47:      # the projects of version 1: the denominator of the share that the process changed
            rows[-1]["projects_v1"] = a["n3"]
    ev_rows = [{"relation": r, "evidence": e, "verified": str(v), "rows": n}
               for r, e, v, n in d.q("""SELECT relation, evidence, verified, count(*) FROM cur.company_namespace
                                        GROUP BY ALL ORDER BY 4 DESC, 1, 2, 3""")]
    return rows, ev_rows, {"per": per, "agg": agg}


def namespace_review_candidates(per: list[dict], version: str = "v4.1") -> list[dict]:
    """Review list of the namespace column (owns rows only, user decision of 2026-10-19).

    1. The owns rows that the bound of the wrong-owner share counts (the model marks them suspect):
       a company owner with no token from its own domains, or another owner that the process
       changed from v3 to the evaluated layer (`version`).
    2. The candidate rows whose organisation wrote 10% or more of the tokens (probable missed owners).
    The rows hold project names and organisation ids, no domain and no person data."""
    out = []
    for p in per:
        if p["relation"] == "owns":
            if p["owner_kind"] == "company" and p["own_share"] == 0:
                reason = "owns row, company owner with no token from its own domains"
            elif p["owner_kind"] != "company" and p.get("changed"):
                reason = f"owns row, owner or relation changed from v3 to {version}"
            else:
                continue
        elif p["relation"] == "candidate" and p["own_share"] >= 0.10:
            reason = "candidate row, the organisation wrote 10% or more of the tokens"
        else:
            continue
        out.append({"project": p["project"], "organisation_id": p["org"], "relation": p["relation"],
                    "evidence": p["evidence"], "token_share": round(p["own_share"], 4), "reason": reason})
    out.sort(key=lambda r: (r["relation"] != "owns", r["reason"], -r["token_share"], r["project"]))
    return out


# --------------------------------------------------------------------------------------------
# Propagation
# --------------------------------------------------------------------------------------------

class Params:
    """One draw of the model parameters (or their central values)."""

    def __init__(self, central: dict, rng: random.Random | None = None, rng9: random.Random | None = None,
                 rngx: random.Random | None = None, rngt: random.Random | None = None):
        c = central
        r = rng
        self.se = c["se_mid"] if r is None else r.uniform(c["se_lo"], c["se_hi"])
        # Error correlation of two AI reviews: type B, uniform from 0 to the value that the user's
        # own decisions allow (rho_cal; see user_calibration).
        self.rho = c["rho_hi"] / 2 if r is None else r.uniform(0.0, c["rho_hi"])

        def draw(ab):
            x, y, w, n = ab["x"], ab["y"], ab["w"], ab["n"]
            if r is not None:      # resample the adjudicated shares (Jeffreys)
                x, y, w = (beta_jeffreys(r, v * n, n) for v in (x, y, w))
            t = two_rater(x, y, w, self.rho)
            return t["agree_wrong"] if t["agree_wrong"] == t["agree_wrong"] else two_rater(x, y, w, 0.0)["agree_wrong"]

        self.q_agreed = draw(c["ab_conflict"])
        uk, un = c["user_cal"]
        # One AI answer that no second review confirmed (adjudications, rounds 6 and 8): the share
        # of AI suggestions that the user changed (calibration against the user's decisions).
        # Round 9 has its own error q_r9 from the user's check sample (at the end of this method, so
        # that the draws above keep their order). It is also a cross-check of q_single.
        self.q_single = (uk + 0.5) / (un + 1) if r is None else beta_jeffreys(r, uk, un)
        fk, fn = c["phi_kind"]
        self.phi = (fk + 0.5) / (fn + 1) if r is None else beta_jeffreys(r, fk, fn)
        self.kind_agreed = draw(c["ab_company"]) * self.phi
        self.kind_single = self.q_single * self.phi
        q4 = c["q4"]
        self.q4 = (q4["k"] + 0.5) / (q4["n"] + 1) / self.se if r is None else \
            min(1.0, beta_jeffreys(r, q4["k"], q4["n"]) / self.se)
        self.q7 = c["q7_hi"] / 2 if r is None else r.uniform(0.0, c["q7_hi"])
        # A user or manual decision is wrong with the user's reversal rate (mean r, standard deviation u).
        self.q_user = c["user_rev"]["r"] if r is None else reversal_draw(r, c["user_rev"])
        sf = c["suffix"]
        self.p_suffix = (sf["k"] + 0.5) / (sf["n"] + 1) if r is None else beta_jeffreys(r, sf["k"], sf["n"])
        self.d = {}
        for key, a in c["detected"].items():
            k, n = a.get("k", 0), a.get("n", 0)
            self.d[key] = (k + 0.5) / (n + 1) if r is None else beta_jeffreys(r, k, n)
        # A source with no v3 links to learn from: the pooled raw error of all v3 links.
        pk, pn = c["pooled"]
        self.d_default = raw_from_detected((pk + 0.5) / (pn + 1) if r is None else beta_jeffreys(r, pk, pn),
                                           1 - (1 - self.se) ** c["pooled_nbar"])
        self.drop_c = 0.5 if r is None else r.uniform(0.0, 1.0)
        self.f_unmatched = c["f_prop"] if r is None else r.uniform(c["f_lo"], c["f_hi"])
        self.f_tail = 0.5 * (c["tail_lo"] + c["tail_hi"]) if r is None else r.uniform(c["tail_lo"], c["tail_hi"])
        # Organisations of any kind among the unmatched domains (the column says independent for them):
        # the company draw times the ratio of organisation to company proposals, so that the two terms
        # stay consistent (an organisation share never below the company share). No new random draw.
        ratio = c["o_prop"] / c["f_prop"] if c.get("f_prop") else 0.0
        self.o_unmatched = min(1.0, self.f_unmatched * ratio)
        self.o_tail = min(1.0, self.f_tail * ratio)
        if "tail_audit" in c:
            # Model v4.7 with a complete tail audit (review/audit_tail.py): the measured organisation and
            # company rates of the unmatched real domains (type A) replace the type B rates above, for
            # both parts (with a proposal and the tail). The draws use their own stream rngt (compute:
            # seed + 11); the uniform draws above still run, so the other draws stay the same.
            ta = c["tail_audit"]
            o, f = at.central_rates(ta) if r is None else at.draw_rates(ta, rngt or r)
            self.o_unmatched = self.o_tail = min(1.0, o)
            self.f_unmatched = self.f_tail = min(1.0, f)
        # AI round 9 (v4.4, one web check per fact): the user's check sample (ai_round_check, central
        # "ai_check"): k_rule wrong of n decided answers, Jeffreys like the other counts. It is the error
        # of the links and organisation rows that round 9 set, and of the v4.4 merges. Its draw uses its
        # own stream rng9 when given (compute: seed + 9), so the draws of the other parameters are the
        # same as before round 9 entered the model.
        ac = c.get("ai_check") or {}
        if ac.get("n"):
            k9, n9 = ac["k_rule"], ac["n"]
            self.q_r9 = (k9 + 0.5) / (n9 + 1) if r is None else beta_jeffreys(rng9 or r, k9, n9)
        else:
            self.q_r9 = self.q_single      # no check sample: the error of one AI answer
        self.kind_r9 = self.q_r9 * self.phi
        # Model v4.7 only (central keys ai_layers, later_pool, phi_user, audit). The draws use their own
        # stream rngx (compute: seed + 10), so the draws above stay those of model v4.6.
        rx = rngx or r
        if "ai_layers" in c:
            # A later AI layer (v4.7 = round 10, ...): k wrong of n decided answers of its check sample
            # (Jeffreys); no answer yet: q_r9, the error of the last round with a check.
            self.q_layer = {}
            for o, a in sorted(c["ai_layers"].items()):
                if a.get("n"):
                    self.q_layer[o] = (a["k"] + 0.5) / (a["n"] + 1) if r is None else beta_jeffreys(rx, a["k"], a["n"])
                else:
                    self.q_layer[o] = self.q_r9
            # The kind of an organisation that a later round set: the pooled check of the later rounds.
            lp = c.get("later_pool") or {}
            if len(self.q_layer) == 1:
                self.q_later = next(iter(self.q_layer.values()))
            elif lp.get("n"):
                self.q_later = (lp["k"] + 0.5) / (lp["n"] + 1) if r is None else beta_jeffreys(rx, lp["k"], lp["n"])
            else:
                self.q_later = self.q_r9
            self.kind_later = self.q_later * self.phi
        if c.get("phi_user"):
            # The kind error of a user or curated organisation (sections 4.4 and 4.6): q_user x phi.
            self.kind_user = self.q_user * self.phi
        if "audit" in c:
            # The measured link error of a complete audit stratum (type A): Jeffreys on k wrong of n.
            self.audit = {}
            for h, (k, n) in sorted(c["audit"].items()):
                self.audit[h] = (k + 0.5) / (n + 1) if r is None else beta_jeffreys(rx, k, n)


def link_p(r: dict, P: Params, d_se: dict) -> float:
    """Residual error probability of one link from its path (origin, later checks, match, merges)."""
    o = r["origin"]
    ses = [P.se for _ in r["later"]]
    if o == "source":
        key = r["skey"]
        nbar = d_se.get(key, 0.0)          # mean number of checks that the v3 links of the stratum saw
        if key in P.d and nbar > 0:
            prior = raw_from_detected(P.d[key], 1 - (1 - P.se) ** nbar)
        else:
            prior = P.d_default
    elif o in ("r4d", "r4f"):
        prior = P.q4
    elif o == "r7":
        prior = P.q7
    elif o in ("r8", "r6", "r5"):
        prior = P.q_single
    elif o == "AB":
        prior = P.q_agreed
    elif o == "r9":
        prior = P.q_r9
    elif o in getattr(P, "q_layer", {}):     # a later AI layer (model v4.7)
        prior = P.q_layer[o]
    else:   # user, manual
        prior = P.q_user
    p = residual(prior, combine_se(ses)) if ses else prior
    if r["match41"] == "suffix":
        p = 1 - (1 - p) * (1 - P.p_suffix)
    if r.get("r9_merge"):            # a v4.4 merge (round 9) renamed the organisation of the link
        p = 1 - (1 - p) * (1 - P.q_r9)
    return p


def audit_factors(rows: list[tuple[dict, float]], P: Params) -> dict:
    """Model v4.7: the factor theta_h / m_h of each audit stratum h whose measured value the model
    uses (Params.audit). theta_h is the measured error of a unit of the stratum; m_h is the mean model
    error of its links (rows: (link, model p)). The link error becomes min(1, p x factor): the mean
    unit error of the stratum is then the measured value, and the model keeps the relative error of
    the links in the stratum (a ratio estimator with the model as the auxiliary value). Without it, a
    flat value would give a small link the error of a large one, and the strata of large links have
    the lower errors."""
    a = getattr(P, "audit", None)
    if not a:
        return {}
    um = defaultdict(lambda: [0, 0.0])
    for r, pm in rows:
        h = r.get("astratum")
        if h in a:
            um[h][0] += 1
            um[h][1] += pm
    return {h: a[h] / (v[1] / v[0]) for h, v in um.items() if v[1] > 0}


def link_p_used(r: dict, P: Params, d_se: dict) -> float:
    """The error of one link that the model uses: link_p, scaled by the factor of its audit stratum
    when the model uses the measured value of the stratum (model v4.7, Params.audit_fac)."""
    p = link_p(r, P, d_se)
    h = r.get("astratum")
    f = getattr(P, "audit_fac", None)
    if h is not None and f and h in f:
        return min(1.0, p * f[h])
    return p


def kind_error(org: str | None, kind: str | None, org_path: str, P: Params) -> float:
    """Probability that the kind of the linked organisation is wrong, from the review path of the
    organisation. A pseudo id (independent, free-provider, unknown) is not an organisation, so its
    kind cannot be wrong (user decision of 2026-10-19); only its link error counts."""
    if org in NO_KIND_ERROR or kind in NO_KIND_ERROR:
        return 0.0
    if org_path == R9_PATH:
        return P.kind_r9
    if org_path == LATER_PATH:
        return P.kind_later
    # The user or curated path: q_user times phi in model v4.7 (kind_user); q_user in model v4.6.
    return {"user-or-curated": getattr(P, "kind_user", P.q_user), "agreed (A=B)": P.kind_agreed, "adjudicated (r5)": P.kind_single,
            "single AI review": P.kind_single, "unreviewed": P.kind_single}[org_path]


def evaluate(chain: list[dict], P: Params, d_se: dict, path: dict, kc: dict, unm: dict, total: int) -> dict:
    """Column error and the corrected company share for one parameter draw."""
    err_tok = 0.0
    linked = 0
    obs_c = 0.0
    fp = fn = 0.0
    tl_c = transition(kc["link"], True)
    tl_n = transition(kc["link"], False)
    # Kind transitions of detected kind edits; denominators are the organisations kept the same.
    ko_c = transition(kc["org"], True)
    ko_n = transition(kc["org"], False)
    per_group = defaultdict(lambda: [0.0, 0.0])
    # Model v4.7: per audit stratum, units, sum of the model p, tokens, model error tokens, used error tokens.
    per_ast = defaultdict(lambda: [0, 0.0, 0, 0.0, 0.0])
    err_model = 0.0
    rows = [(r, link_p(r, P, d_se)) for r in chain if r["o41"] is not None]
    fac = audit_factors(rows, P)
    for r, pm in rows:
        t = r["tokens"]
        h = r.get("astratum")
        p = min(1.0, pm * fac[h]) if h in fac else pm
        if h is not None:
            a = per_ast[h]
            a[0] += 1
            a[1] += pm
            a[2] += t
            a[3] += pm * t
            a[4] += p * t
        err_model += pm * t
        linked += t
        err_tok += p * t
        g = per_group[(r["group41"], r["origin"], r["band"], r["match41"])]
        g[0] += t
        g[1] += p * t
        shown_c = r["kind41"] in COMPANY_KINDS
        pk = kind_error(r["o41"], r["kind41"], path.get(r["o41"], "unreviewed"), P)
        if shown_c:
            obs_c += t
            # a wrong link shown as a company is truly a non-company with tl_c[1]; a dropped link has an
            # unknown kind: it is a company with drop_c (type B, uniform 0 to 1)
            fp += t * (p * (tl_c[1] + (1 - P.drop_c) * tl_c[2]) + (1 - p) * pk * ko_c[1])
        else:
            fn += t * (p * (tl_n[0] + P.drop_c * tl_n[2]) + (1 - p) * pk * ko_n[0])
    fn_unm = unm.get("proposed", 0) * P.f_unmatched + unm.get("tail", 0) * P.f_tail
    # The column gives `independent` to every token whose real domain has no row. It is wrong for the
    # organisations among these domains. A token with no real domain gets `unknown` (the user,
    # 2026-10-19): the value says that the address is not known, so it has no mapping error.
    err_unm = unm.get("proposed", 0) * P.o_unmatched + unm.get("tail", 0) * P.o_tail
    true_c = obs_c - fp + fn
    tp = obs_c - fp
    se_c = tp / (tp + fn + fn_unm) if tp + fn + fn_unm else 1.0
    tn = total - obs_c - fn - fn_unm
    sp_c = tn / (tn + fp) if tn + fp else 1.0
    return {"E_linked": err_tok / linked, "E_all": err_tok / total, "err_tok": err_tok, "linked": linked,
            "err_unm": err_unm, "E_dataset": (err_tok + err_unm) / total, "E_unmatched": err_unm / total,
            "obs_company": obs_c / total, "fp": fp / total, "fn": fn / total, "fn_unmatched": fn_unm / total,
            "true_company_E1": true_c / total, "true_company": (true_c + fn_unm) / total,
            "Se": se_c, "Sp": sp_c, "per_group": per_group, "per_astratum": dict(per_ast), "err_tok_model": err_model}


def later_layers(chain: list[dict], P0: Params, d_se: dict, linked: int) -> list[dict]:
    """Links and tokens of the evaluated layer by the rule that set their origin (current_origin)."""
    agg = defaultdict(lambda: [0, 0, 0.0])
    for r in chain:
        a = agg[r["layer_rule"]]
        a[0] += 1
        a[1] += r["tokens"]
        a[2] += link_p_used(r, P0, d_se) * r["tokens"] if r["o41"] is not None else 0.0
    rules = LAYER_RULES + tuple(sorted(set(agg) - set(LAYER_RULES)))     # model v4.7: the later AI layers
    return [{"rule": k, "links": agg[k][0], "tokens": agg[k][1],
             "share_of_linked_pct": pct(agg[k][1] / linked) if k != "dropped" else "",
             "error_tokens": int(agg[k][2]),
             "error_pct": pct(agg[k][2] / agg[k][1]) if agg[k][1] and k != "dropped" else ""}
            for k in rules if k in agg]


def sensitivity_r9(chain, central, ai_chk, d_se, path, kc, unm, total) -> list[dict]:
    """Central values with the round 9 count after the relation rename (the model) and as answered."""
    out = []
    for name, k in (("after the relation rename (model)", ai_chk["k_rule"]), ("as answered", ai_chk["k"])):
        P = Params(dict(central, ai_check=dict(ai_chk, k_rule=k)))
        e = evaluate(chain, P, d_se, path, kc, unm, total)
        out.append({"round 9 count": name, "wrong": k, "of": ai_chk["n"], "q_r9_pct": pct(P.q_r9),
                    "E_all_pct": pct(e["E_all"], 4), "E_dataset_pct": pct(e["E_dataset"], 4),
                    "company_share_E1E4_pct": pct(e["true_company_E1"], 4)})
    return out


# The model parameter that an audit stratum measures (its origin; ERROR_MODEL.md section 10a).
AUDIT_PARAMETER = {
    "source": "raw error of the first source (group, band, class) after the later checks (se)",
    "AB": "q_agreed: agreed answer of two AI reviews (two-rater model, rho)",
    "r4d/r4f": "q4: a move of link check 4d or 4f",
    "r5/r6": "q_single: one adjudication answer (round 5 or 6)",
    "r7": "q7: a change of the sweep (rectangular 0 to the reversal bound)",
    "r8": "q_single: one answer of the conflict round (round 8)",
    "r9": "q_r9: one answer of round 9 (its check sample)",
    "user": "q_user: the reversal rate of the user",
}


def audit_parameter(row: dict) -> str:
    """The model parameter that an audit stratum measures."""
    if row["population"] == "namespace":
        return "bound B of the namespace class (rectangular 0 to B)"
    if (row.get("band") or "").startswith("B0"):
        return "no tokens in version 1: the band B3 value of the same origin"
    return AUDIT_PARAMETER.get(row.get("origin") or "", "link error of the path")


def beta_from_moments(mu: float | None, sd: float) -> tuple[float, float] | None:
    """Beta(a, b) with mean mu and standard deviation sd; None when no such Beta exists."""
    if mu is None or not 0 < mu < 1 or sd <= 0:
        return None
    nu = mu * (1 - mu) / (sd * sd) - 1
    return (mu * nu, (1 - mu) * nu) if nu > 0 else None


def audit_tables(aud: dict, base: dict, sims: list[dict], used: dict, total: int, seed: int,
                 ns_model: dict, rule: str) -> tuple[list[dict], list[dict], dict]:
    """Model v4.7: audit_replacements (one row per audit stratum: the parameter that it measures, the
    model value, the audit value, n, the binomial test and whether the measured value replaces the
    model value) and audit_update (sensitivity: the column error with the audit values).

    used: stratum -> (k, n) of the strata whose measured value the model uses. ns_model: namespace
    stratum -> [projects, sum of B/2, sum of u] of the class bounds of its projects."""
    pa0 = base["per_astratum"]
    mstat = {}
    for r in aud["strata"]:
        h = r["error_stratum"]
        if r["population"] == "domain":
            vals = [e["per_astratum"][h][1] / e["per_astratum"][h][0] for e in sims
                    if h in e["per_astratum"] and e["per_astratum"][h][0]]
            c = pa0.get(h)
            mstat[h] = (c[1] / c[0] if c and c[0] else None, statistics.stdev(vals) if len(vals) > 1 else 0.0,
                        c[0] if c else 0, c[2] if c else 0)
        else:
            c = ns_model.get(h)
            mstat[h] = (c[1] / c[0] if c and c[0] else None, c[2] / c[0] if c and c[0] else 0.0,
                        c[0] if c else 0, c[0] if c else 0)
    rows, prior = [], {}
    for r in aud["strata"]:
        h = r["error_stratum"]
        k, n = r["wrong"], r["n_decided"]
        mu, sd, units, weight = mstat[h]
        ab = beta_from_moments(mu, sd) or (0.5, 0.5)
        prior[h] = ab
        cells = "/".join(x for x in (r["origin"], r["band"], r["class"], r["match"]) if x) \
            if r["population"] == "domain" else "/".join(x for x in (r["evidence"], r["owner_kind"]) if x)
        rows.append({
            "error_stratum": h, "population": r["population"], "cells": cells, "parameter": audit_parameter(r),
            "units_in_model": units, ("tokens_in_model" if r["population"] == "domain" else "projects_in_model"): weight,
            "model_value_pct": pct(mu) if mu is not None else "", "model_sd_pct": pct(sd),
            "v46_prediction_pct": r["p_pred_pct"], "n_sample": r["n_sample"], "answered": r["answered"],
            "right": r["right"], "wrong": k, "unsure": r["unsure"], "n_decided": n,
            "audit_rate_pct": r["rate_pct"], "audit_jeffreys_pct": r["jeffreys_pct"],
            "audit_cp95_pct": f"{r['cp_lo_pct']} to {r['cp_hi_pct']}" if n else "",
            "p_upper_vs_model": round(aa.binom_sf(k, n, mu), 5) if n and mu is not None else "",
            "p_two_sided_vs_model": round(aa.binom_test(k, n, mu), 5) if n and mu is not None else "",
            "test_vs_model": aa.binomial_label(k, n, mu) if n and mu is not None else "no answer",
            "used": f"yes ({rule}): the measured value replaces the model value" if h in used
            else f"no: {r['answered']} of {r['n_sample']} items answered, {n} decided ({rule} needed)",
            "updated_value_pct": pct((ab[0] + k) / (ab[0] + ab[1] + n)) if n else "",
        })
    # Sensitivity of the domain column: every domain stratum with a decided answer takes a value from
    # the audit, (a) the Beta posterior with the model as prior, (b) the Jeffreys posterior alone.
    A = sorted(r["error_stratum"] for r in aud["strata"] if r["population"] == "domain" and r["n_decided"] > 0)
    dom = {r["error_stratum"] for r in aud["strata"] if r["population"] == "domain"}
    used_d = {h: v for h, v in used.items() if h in dom}
    kn = {r["error_stratum"]: (r["wrong"], r["n_decided"]) for r in aud["strata"]}

    def err(e, th):
        x = e["err_tok_model"]
        for h in th:
            a = e["per_astratum"].get(h)
            if a and a[1] > 0:
                x += a[3] * (th[h] / (a[1] / a[0]) - 1)     # the ratio of audit_factors
        return x

    def variant(name, hs, central_th, draw):
        rng = random.Random(seed + 12)
        c = err(base, central_th)
        va, vl, vd = [], [], []
        for e in sims:
            th = {h: draw(rng, h) for h in hs}
            x = err(e, th)
            va.append(x / total)
            vl.append(x / e["linked"])
            vd.append(x / total + e["E_unmatched"])
        vd_s = sorted(vd)
        sd = statistics.stdev(vd) if len(vd) > 1 else 0.0
        return {"variant": name, "strata_from_the_audit": " ".join(hs) or "(none)",
                "decided_answers": sum(kn[h][1] for h in hs), "wrong_answers": sum(kn[h][0] for h in hs),
                "E_linked_pct": pct(c / base["linked"]), "E_all_pct": pct(c / total),
                "E_dataset_pct": pct(c / total + base["E_unmatched"]),
                "E_linked_U_pct": pct(2 * statistics.stdev(vl)) if len(vl) > 1 else "",
                "E_dataset_U_pct": pct(2 * sd),
                "E_dataset_mc95": f"{pct(vd_s[int(0.025 * len(vd_s))])} to {pct(vd_s[int(0.975 * len(vd_s)) - 1])}"
                if vd_s else ""}

    def post(h):
        a0, b0 = prior[h]
        k, n = kn[h]
        return a0 + k, b0 + n - k
    upd = [
        variant("model only (no audit value)", [], {}, None),
        variant(f"main: measured values of the domain strata that pass the rule ({rule})", sorted(used_d),
                {h: (k + 0.5) / (n + 1) for h, (k, n) in used_d.items()},
                lambda g, h: g.betavariate(used_d[h][0] + 0.5, used_d[h][1] - used_d[h][0] + 0.5)),
        variant("update: every stratum with an answer, Beta posterior with the model value as prior", A,
                {h: post(h)[0] / sum(post(h)) for h in A}, lambda g, h: g.betavariate(*post(h))),
        variant("measured values of every stratum with an answer (Jeffreys, no prior; partial strata)", A,
                {h: (kn[h][0] + 0.5) / (kn[h][1] + 1) for h in A},
                lambda g, h: g.betavariate(kn[h][0] + 0.5, kn[h][1] - kn[h][0] + 0.5)),
    ]
    return rows, upd, {"strata_with_answers": A}


TAIL_KEYS = ("K", "C_t", "C_o", "C_c", "m", "k_o", "k_c")


def tail_audit_state(d: Data, folder: Path) -> dict | None:
    """Model v4.7: the estimate of the tail audit for the evaluated pool of unmatched real domains.

    None when the folder has no items or no design yet. The units of the sample that are not in the
    evaluated pool (for example a domain that a later link build matches) leave the estimate; the pool
    tokens outside the frame take the same rate. used: the page is complete."""
    folder = Path(folder)
    if not ((folder / "data/items.json").exists() and (folder / "design.json").exists()):
        return None
    import audit_tail_sample as ats
    rows = [(x, t) for x, t, part in unmatched_rows(d) if part != "no_real_domain"]
    pool = {x for x, _ in rows}
    st = at.analyse(folder, pool)
    frame = set()
    fp = folder / "frame.csv"
    if fp.exists():
        frame = {r["domain"] for r in read_csv(fp)}
    st["frame_match"] = ats.frame_sha256([{"domain": x, "tokens": t} for x, t in rows]) == st["frame_sha256"]
    st["pool_n"], st["pool_tokens"] = len(rows), sum(t for _, t in rows)
    st["pool_tokens_in_frame"] = sum(t for x, t in rows if x in frame)
    st["used"] = bool(st["complete"]) and st["C_t"] + st["m"] > 0
    return st


def tail_audit_rows(st: dict) -> list[dict]:
    """The table tail_audit.csv: the state of the tail audit (counts and rates only, no domain)."""
    def p(x):
        return pct(x) if isinstance(x, (int, float)) and x == x else ""
    cp, cc, ub = st.get("org_rate_cp95") or ("", ""), st.get("company_rate_cp95") or ("", ""), \
        st.get("org_rate_unsure_bounds") or ("", "")
    return [{"items": st["items"], "answered": st["answered"], "complete": st["complete"], "used": st["used"],
             "frame_domains": st["frame_n"], "frame_tokens": st["frame_tokens"], "frame_match": st["frame_match"],
             "pool_domains": st["pool_n"], "pool_tokens": st["pool_tokens"],
             "pool_tokens_in_frame_pct": p(st["pool_tokens_in_frame"] / st["pool_tokens"]) if st["pool_tokens"] else "",
             "units_out_of_pool": st["out_of_pool"],
             "company": st["by_class"]["company"], "other_organisation": st["by_class"]["organisation"],
             "no_organisation": st["by_class"]["no-organisation"], "unsure": st["by_class"]["unsure"],
             "open": st["by_class"]["open"], "certainty_tokens_decided": st["C_t"], "points_decided": st["m"],
             "points_organisation": st["k_o"], "points_company": st["k_c"], "step_tokens": round(st["K"]),
             "org_rate_ht_pct": p(st.get("org_rate_ht")), "org_rate_central_pct": p(st.get("org_rate_central")),
             "org_rate_cp95_pct": f"{p(cp[0])} to {p(cp[1])}" if cp[0] != "" else "",
             "org_rate_unsure_bounds_pct": f"{p(ub[0])} to {p(ub[1])}" if ub[0] != "" else "",
             "company_rate_ht_pct": p(st.get("company_rate_ht")), "company_rate_central_pct": p(st.get("company_rate_central")),
             "company_rate_cp95_pct": f"{p(cc[0])} to {p(cc[1])}" if cc[0] != "" else ""}]


def compute(d: Data, draws: int, seed: int, audit: Path | None = None, audit_min_n: int = 0,
            tail_audit: Path | None = None, column_audit: Path | None = None) -> dict:
    """All tables of the dataset error budget; the writers and the side study use the result.

    Model v4.7 (d.model): audit is the folder of the audit sample (None: no audit value); a stratum
    gives its measured value when it is complete, or with audit_min_n > 0 when it has at least
    audit_min_n decided answers. tail_audit is the folder of the tail audit (None: no tail audit):
    when its page is complete, its measured rates replace the type B rates of the unmatched real
    domains (tail_audit_state). column_audit is the folder of the column audit (None: no column
    audit): a part with at least audit_columns.USE_MIN decided answers gives the measured error of its
    column in place of the model terms (column_audit_update)."""
    total = d.total
    v47 = getattr(d, "model", "v4.6") != "v4.6"
    chain41 = link_chain(d)              # the history v3 -> v4.0 -> v4.1: the parameters
    # Model v4.7: the later AI layers of the evaluated database and the check pages of their rounds.
    layer_checks = {}
    if v47:
        for (ptr,) in d.q("""SELECT DISTINCT regexp_extract(source_pointer, '^[^#]*') FROM cur.company_domain
                             UNION SELECT DISTINCT regexp_extract(source_pointer, '^[^#]*') FROM cur.company_namespace"""):
            lay = later_layer(ptr)
            if lay is not None and lay[1] not in layer_checks:
                folder = d.ws / "review" / f"audit-{lay[0].replace('.', '')}"
                layer_checks[lay[1]] = dict(aa.round_check(folder), layer=lay[0])
        d.decide_keys = set().union(*(c["decide_keys"] for c in layer_checks.values())) if layer_checks else set()
    chain = current_chain(d, chain41)    # the evaluated layer: the propagation
    tables = {}
    # Model v4.7: the audit sample. A link is in an audit stratum when its domain is a unit of the
    # frame with the same organisation (the audited value).
    aud, frame, used_dom, used_ns = None, {}, {}, {}
    if v47 and audit is not None and (Path(audit) / "strata.csv").exists():
        aud = aa.analyse_sample(Path(audit))
        frame = aud["sample"].frame()
        fd = frame.get("domain", {})
        for r in chain:
            if r["o41"] is not None:
                f = fd.get(r["domain"])
                if f is not None and f[1] == r["o41"]:
                    r["astratum"] = f[0]
        for row in aud["strata"]:
            ok = row["complete"] if audit_min_n <= 0 else row["n_decided"] >= audit_min_n
            if ok and row["n_decided"] > 0:
                (used_dom if row["population"] == "domain" else used_ns)[row["error_stratum"]] = \
                    (row["wrong"], row["n_decided"])

    raw, raw_agg = source_raw_error(chain41)
    tables["source_raw_error"] = raw
    tables["source_raw_error_rows"] = source_raw_error_rows(d)
    tables["checks"] = check_rates(d)
    pairs, pair_par = check_pairs(d)
    tables["check_pairs"] = pairs
    ab_rows, ab_par = items_ab(d)
    tables["rater_model"] = ab_rows
    lp_rows, lp_par = items_lp(d)
    tables["capture_recapture"] = lp_rows

    # Sensitivity of one AI link check: two process-based estimates (type B rectangular between).
    se_removal = min(p for p in (removal_two_pass(pair_par[k]["n1"], pair_par[k]["n2"])[0]
                                  for k in ("r4d", "r4f")) if not math.isnan(p))
    se_lp = min(lp_par["company"]["pA"], lp_par["company"]["pB"])
    se_lo, se_hi = sorted((se_lp, se_removal))
    # Number of checks the links of each (group, band) saw before the end, as a mean.
    nchk = defaultdict(list)
    for r in chain41:
        if r["o3"] is not None:
            n = sum(r["seen"][c] for c in ("r4d", "r4f", "r7", "r8"))
            g, b, kc = r["group3"], r["band"], r["kc3"]
            for key in ((g, b, kc), (g, b, "*"), (g, "all", kc), (g, "all", "*")):
                nchk[key].append(n)
    d_se = {k: statistics.mean(v) for k, v in nchk.items()}
    detected = {k: {"k": v.get("k", 0), "n": v.get("n", 0)} for k, v in raw_agg.items()}
    # A source with no v3 links (v4 additions) uses its own group "all", or 5% if none.
    q4n = pair_par["r4d"]["moves_seen"] + pair_par["r4f"]["moves_seen"]
    q4k = pair_par["r4d"]["moves_changed"] + pair_par["r4f"]["moves_changed"]
    r7 = next(r for r in tables["checks"] if r["check"] == "r7")
    q7_hi = r7["reversed_share_of_raw_changes_pct"] / 100
    # Suffix matches: round 7 changes on database rows that are subdomains of another row.
    sub = d.q("""SELECT domain FROM v40.company_domain WHERE domain <> registrable_domain""")
    sub_seen = [x for (x,) in sub if x in d.checks["r7"]]
    sub_k = sum(1 for x in sub_seen if d.checks["r7"][x]["action"] != "keep")
    unm = unmatched(d)
    tail = tail_audit_state(d, tail_audit) if v47 and tail_audit is not None else None
    f_prop = unm.get("proposed_company", 0) / unm["proposed"] if unm.get("proposed") else 0.0
    # Unmatched domains map to independent (user decision of 2026-10-19). The column is wrong for
    # the tokens of an organisation among them. The rate of the AI proposals is the process estimate.
    o_prop = unm.get("proposed_org", 0) / unm["proposed"] if unm.get("proposed") else 0.0
    path = org_paths(d)
    if v47:
        path = later_org_paths(d, path)
    kc = kind_changes(chain41)
    uk, un = user_calibration(d)
    ai_chk = ai_round_check(d.ws)
    # Error of the user's own decisions: the reversal rate of the user (user decision of 2026-10-19).
    rk, rn, rdet = user_reversals(d.ws)
    rev = dict(reversal_term(rk, rn), detail=rdet)
    ab_all = ab_par[("all", "items")]
    rho_hi = rho_for_error(ab_all["x"], ab_all["y"], ab_all["w"], wilson(uk, un)[1])
    fk, fn = phi_kind(d)
    central = {"se_lo": se_lo, "se_hi": se_hi, "se_mid": (se_lo + se_hi) / 2, "rho_hi": rho_hi,
               "user_cal": (uk, un), "phi_kind": (fk, fn), "ai_check": ai_chk,
               "ab_conflict": ab_par[("conflict", "items")], "ab_company": ab_par[("company", "items")],
               "q4": {"k": q4k, "n": q4n}, "q7_hi": q7_hi, "suffix": {"k": sub_k, "n": len(sub_seen)},
               "detected": detected, "f_prop": f_prop, "f_lo": 0.0, "f_hi": min(1.0, 2 * f_prop),
               "tail_lo": 0.0, "tail_hi": min(1.0, 2 * f_prop),
               "o_prop": o_prop, "o_hi": min(1.0, 2 * o_prop), "user_rev": rev,
               "pooled": (sum(v["k"] for k, v in detected.items() if k[1:] == ("all", "*")),
                          sum(v["n"] for k, v in detected.items() if k[1:] == ("all", "*"))),
               "pooled_nbar": statistics.mean(x for k, v in nchk.items() if k[1:] == ("all", "*") for x in v)}
    if v47:
        central["ai_layers"] = {o: {"k": c["k"], "n": c["n"]} for o, c in layer_checks.items()}
        central["later_pool"] = {"k": sum(c["k"] for c in layer_checks.values()),
                                 "n": sum(c["n"] for c in layer_checks.values())}
        central["phi_user"] = True
        central["audit"] = used_dom
        if tail and tail["used"]:
            central["tail_audit"] = {k: tail[k] for k in TAIL_KEYS}
    for r in chain:
        if r["o41"] is not None:
            r["skey"] = stratum_key(detected, r["group41"], r["band"], r["kc41"])
    P0 = Params(central)
    if v47:
        P0.audit_fac = audit_factors([(r, link_p(r, P0, d_se)) for r in chain if r["o41"] is not None], P0)
    base = evaluate(chain, P0, d_se, path, kc, unm, total)
    rng = random.Random(seed)
    rng9 = random.Random(seed + 9)      # the round 9 error q_r9 (Params)
    rngx = random.Random(seed + 10) if v47 else None    # model v4.7: later layers and audit values
    rngt = random.Random(seed + 11) if "tail_audit" in central else None    # model v4.7: the tail audit
    sims = []
    for _ in range(draws):
        P = Params(central, rng, rng9, rngx, rngt)
        e = evaluate(chain, P, d_se, path, kc, unm, total)
        e.pop("per_group")
        sims.append(e)

    def ci(key):
        v = sorted(s[key] for s in sims)
        return statistics.mean(v), statistics.stdev(v), v[int(0.025 * len(v))], v[int(0.975 * len(v)) - 1]

    # Sensitivity: the central values with a fixed se of the AI checks and a fixed rho.
    sens = []
    for se_v in (0.5, 0.7, se_lo, (se_lo + se_hi) / 2, se_hi):
        for rho_v in (0.0, rho_hi, 0.5):
            cc = dict(central, se_mid=se_v, rho_hi=2 * rho_v)
            e = evaluate(chain, Params(cc), d_se, path, kc, unm, total)
            sens.append({"se": round(se_v, 4), "rho": round(rho_v, 4), "E_linked_pct": pct(e["E_linked"]),
                         "E_dataset_pct": pct(e["E_dataset"]), "company_share_E1E4_pct": pct(e["true_company_E1"])})
    tables["sensitivity"] = sens
    # Sensitivity to the error of the user's decisions (central values of all other parameters).
    w = rev["detail"]["withdrawn"]
    sens_u = []
    for name, t in (("0: the user is the reference by definition", {"k": 0, "n": 0, "r": 0.0, "u": 0.0}),
                    (f"reversal rate {rev['k']} of {rev['n']} (main)", rev),
                    (f"reversals + withdrawn decisions, {rev['k'] + w} of {rev['n']}", reversal_term(rev["k"] + w, rev["n"])),
                    ("old type B term: uniform 0 to 2% (mean 1%)", {"k": 1, "n": 2, "r": 0.01, "u": 0.0})):
        e = evaluate(chain, Params(dict(central, user_rev=t)), d_se, path, kc, unm, total)
        sens_u.append({"user_error": name, "q_user_pct": pct(t["r"]), "E_linked_pct": pct(e["E_linked"]),
                       "E_dataset_pct": pct(e["E_dataset"]), "company_share_E1E4_pct": pct(e["true_company_E1"])})
    tables["sensitivity_user"] = sens_u
    # Sensitivity of the unmatched-domain term (central values). Main: a blank proposal kind is no
    # organisation. Variant: the blank answers have the mix of the answered proposals. Bounds: 0 to 1.
    answered = unm.get("proposed", 0) - unm.get("kind:(blank)", 0)
    f_ans = unm.get("proposed_company", 0) / answered if answered else 0.0
    o_ans = unm.get("proposed_org", 0) / answered if answered else 0.0
    sens_m = []
    for name, f_c, o_c in (("main: a blank kind is no organisation; 0 to 2 x the proposal rate", f_prop, o_prop),
                           ("blank kinds have the mix of the answered proposals; 0 to 2 x that rate", f_ans, o_ans),
                           ("hard bounds: 0 to 1 (mean 0.5)", 0.5, 0.5)):
        cc = dict(central, f_prop=f_c, f_hi=min(1.0, 2 * f_c), tail_hi=min(1.0, 2 * f_c), o_prop=o_c)
        cc.pop("tail_audit", None)      # the type B variants (the measured rates are the row below)
        e = evaluate(chain, Params(cc), d_se, path, kc, unm, total)
        sens_m.append({"variant": name, "company_rate_pct": pct(f_c), "organisation_rate_pct": pct(o_c),
                       "E_unmatched_pct": pct(e["E_unmatched"]), "E_dataset_pct": pct(e["E_dataset"]),
                       "company_share_pct": pct(e["true_company"])})
    if "tail_audit" in central:
        sens_m.append({"variant": "measured: the tail audit (PPS sample; Jeffreys central values; used)",
                       "company_rate_pct": pct(P0.f_unmatched), "organisation_rate_pct": pct(P0.o_unmatched),
                       "E_unmatched_pct": pct(base["E_unmatched"]), "E_dataset_pct": pct(base["E_dataset"]),
                       "company_share_pct": pct(base["true_company"])})
    tables["sensitivity_unmatched"] = sens_m

    # Strata table (central values) and per-link file.
    strata = []
    for (g, o, b, m), (t, e) in sorted(base["per_group"].items(), key=lambda kv: -kv[1][1]):
        strata.append({"group": g, "origin": o, "band": b, "match": m, "tokens": int(t),
                       "token_share_pct": pct(t / total), "error_pct": pct(e / t) if t else 0.0,
                       "error_tokens": int(e), "error_share_of_all_pct": pct(e / total, 4)})
    tables["link_strata"] = strata
    cov = defaultdict(lambda: [0, 0])
    for r in chain:
        if r["o41"] is None:
            continue
        chk = "+".join(c for c in ("r4d", "r4f", "r7", "r8", "user") if r["seen"][c]) or "(none)"
        cov[(r["origin"], chk)][0] += 1
        cov[(r["origin"], chk)][1] += r["tokens"]
    tables["chain_coverage"] = [{"origin": o, "checks_seen": c, "links": v[0], "tokens": v[1],
                                 "share_of_linked_pct": pct(v[1] / base["linked"])}
                                for (o, c), v in sorted(cov.items(), key=lambda kv: -kv[1][1])]
    tables["later_layers"] = later_layers(chain, P0, d_se, base["linked"])
    tables["sensitivity_r9"] = sensitivity_r9(chain, central, ai_chk, d_se, path, kc, unm, total)
    stratum_sum = defaultdict(lambda: [0.0, 0.0])
    for s in strata:
        for key in (("group", s["group"]), ("origin", s["origin"]), ("band", s["band"]), ("match", s["match"])):
            stratum_sum[key][0] += s["tokens"]
            stratum_sum[key][1] += s["error_tokens"]
    tables["link_strata_margins"] = [{"by": k[0], "value": k[1], "tokens": int(v[0]), "token_share_pct": pct(v[0] / total),
                                      "error_pct": pct(v[1] / v[0]) if v[0] else 0.0,
                                      "error_share_of_all_pct": pct(v[1] / total, 4)}
                                     for k, v in sorted(stratum_sum.items())]

    # Budget of the company-kind share (M3).
    E_mean, E_sd, E_lo, E_hi = ci("E_linked")
    Ea_mean, Ea_sd, Ea_lo, Ea_hi = ci("E_all")
    Ed_mean, Ed_sd, Ed_lo, Ed_hi = ci("E_dataset")
    Eu_mean, Eu_sd, Eu_lo, Eu_hi = ci("E_unmatched")
    tc_mean, tc_sd, tc_lo, tc_hi = ci("true_company_E1")
    fu_mean, fu_sd, fu_lo, fu_hi = ci("fn_unmatched")
    tot_mean, tot_sd, tot_lo, tot_hi = ci("true_company")
    unm_share = (unm.get("proposed", 0) + unm.get("tail", 0)) / total
    u_e2_hard = rectangular_u(unm_share / 2)
    rg = rogan_gladen(base["obs_company"], base["Se"], base["Sp"])
    budget = [
        {"line": 1, "component": f"observed company-kind share ({d.version}; a token with no row counts as independent or unknown)",
         "type": "-", "value_pct": pct(base["obs_company"]), "u_pct": 0.0},
        {"line": 2, "component": "E1 + E4: link and kind residual errors (Monte Carlo)", "type": "B from process counts",
         "value_pct": pct(tc_mean - base["obs_company"]), "u_pct": pct(tc_sd)},
        {"line": 3, "component": "share corrected for E1 + E4 only", "type": "combined",
         "value_pct": pct(tc_mean), "u_pct": pct(tc_sd), "U_k2_pct": pct(2 * tc_sd),
         "mc95": f"{pct(tc_lo)} to {pct(tc_hi)}"},
        {"line": 4, "component": "E2: companies among the unmatched real domains (now independent), " +
                                 ("company share measured by the tail audit (PPS sample)" if "tail_audit" in central
                                  else "company share uniform 0 to 2 x proposals"),
         "type": "B", "value_pct": pct(fu_mean), "u_pct": pct(fu_sd), "mc95": f"{pct(fu_lo)} to {pct(fu_hi)}"},
        {"line": 5, "component": "dataset value: line 3 + line 4 (Monte Carlo)", "type": "combined",
         "value_pct": pct(tot_mean), "u_pct": pct(tot_sd), "U_k2_pct": pct(2 * tot_sd),
         "mc95": f"{pct(tot_lo)} to {pct(tot_hi)}"},
        {"line": 6, "component": "sensitivity: unmatched real domains, company share uniform 0 to 1 (hard bounds)",
         "type": "B", "value_pct": pct(unm_share / 2), "u_pct": pct(u_e2_hard)},
        {"line": 7, "component": "line 3 + line 6", "type": "combined", "value_pct": pct(tc_mean + unm_share / 2),
         "u_pct": pct(combined_u([tc_sd, u_e2_hard])), "U_k2_pct": pct(2 * combined_u([tc_sd, u_e2_hard])),
         "mc95": f"hard bounds {pct(tc_lo)} to {pct(tc_hi + unm_share)}"},
        {"line": 8, "component": "check: Rogan-Gladen with the Se and Sp of the central values", "type": "check",
         "value_pct": pct(rg), "u_pct": 0.0, "mc95": f"direct central value {pct(base['true_company'])}; "
                                                       f"Se {round(base['Se'], 5)}, Sp {round(base['Sp'], 5)}"},
    ]
    tables["budget_company_share"] = budget
    tables["column_error"] = [
        {"measure": "dataset: error of firm_based_on_domain, all tokens (a token with no row is independent or unknown; central)",
         "value_pct": pct(base["E_dataset"]), "u_pct": pct(Ed_sd), "U_k2_pct": pct(2 * Ed_sd),
         "mc95_lo_pct": pct(Ed_lo), "mc95_hi_pct": pct(Ed_hi)},
        {"measure": "of this: link errors (rows of the database), share of all tokens", "value_pct": pct(base["E_all"]),
         "u_pct": pct(Ea_sd), "U_k2_pct": pct(2 * Ea_sd), "mc95_lo_pct": pct(Ea_lo), "mc95_hi_pct": pct(Ea_hi)},
        {"measure": "of this: organisations among the unmatched real domains, share of all tokens",
         "value_pct": pct(base["E_unmatched"]), "u_pct": pct(Eu_sd), "U_k2_pct": pct(2 * Eu_sd),
         "mc95_lo_pct": pct(Eu_lo), "mc95_hi_pct": pct(Eu_hi)},
        {"measure": "link errors, share of the linked tokens (central)",
         "value_pct": pct(base["E_linked"]), "u_pct": pct(E_sd), "U_k2_pct": pct(2 * E_sd),
         "mc95_lo_pct": pct(E_lo), "mc95_hi_pct": pct(E_hi)},
        {"measure": "Monte Carlo mean, dataset, all tokens", "value_pct": pct(Ed_mean), "u_pct": pct(Ed_sd),
         "U_k2_pct": pct(2 * Ed_sd), "mc95_lo_pct": pct(Ed_lo), "mc95_hi_pct": pct(Ed_hi)},
        {"measure": "Monte Carlo mean, linked tokens", "value_pct": pct(E_mean), "u_pct": pct(E_sd),
         "U_k2_pct": pct(2 * E_sd), "mc95_lo_pct": pct(E_lo), "mc95_hi_pct": pct(E_hi)},
    ]
    params = [
        {"parameter": "se of one AI link check, removal estimate (r4d/r4f then r7)", "value": round(se_removal, 4)},
        {"parameter": "se of one AI review, capture-recapture (rounds 3, 4; min of p_A, p_B)", "value": round(se_lp, 4)},
        {"parameter": "q4: wrong share of r4d/r4f moves (r7 changed k of n)", "value": f"{q4k} of {q4n}"},
        {"parameter": "q7 upper bound: r7 changes reversed by rule corrections", "value": round(q7_hi, 4)},
        {"parameter": "suffix: r7 changes on subdomain rows", "value": f"{sub_k} of {len(sub_seen)}"},
        {"parameter": "conflict items: agreed answers wrong, rho = 0 (two-rater)",
         "value": round(two_rater(**{k: ab_par[('conflict', 'items')][k] for k in ('x', 'y', 'w')})["agree_wrong"], 5)},
        {"parameter": "company items: agreed answers wrong, rho = 0 (two-rater)",
         "value": round(two_rater(**{k: ab_par[('company', 'items')][k] for k in ('x', 'y', 'w')})["agree_wrong"], 5)},
        {"parameter": "user calibration: user decisions that differ from the AI suggestion", "value": f"{uk} of {un}"},
        {"parameter": "AI round 9 (one web check per fact), user check sample: wrong of decided answers "
                      "(the round 9 error q_r9; also a cross-check of the single-review error)",
         "value": f"{ai_chk['k']} of {ai_chk['n']} as answered (95% Clopper-Pearson {round(ai_chk['cp'][0], 4)} to "
                  f"{round(ai_chk['cp'][1], 4)}); {ai_chk['k_rule']} of {ai_chk['n']} after the relation rename "
                  f"(rule of three upper {round(ai_chk['rule3'], 4)}); {ai_chk['unsure']} unsure not counted"},
        {"parameter": "q_r9: error of a link or organisation row that round 9 set, and of a v4.4 merge "
                      "(Jeffreys on the count after the rename; central (k + 0.5) / (n + 1))",
         "value": round(P0.q_r9, 5)},
        {"parameter": "rho_cal: rho at which the mean single-review error equals the Wilson upper bound of the user calibration",
         "value": round(rho_hi, 4)},
        {"parameter": "rho (correlation of the errors of two AI reviews), type B", "value": f"uniform 0 to {round(rho_hi, 4)}"},
        {"parameter": "agreed answers wrong at rho_cal: conflict items, company items",
         "value": f"{round(two_rater(**{k: ab_par[('conflict', 'items')][k] for k in ('x', 'y', 'w')}, rho=rho_hi)['agree_wrong'], 5)}, "
                  f"{round(two_rater(**{k: ab_par[('company', 'items')][k] for k in ('x', 'y', 'w')}, rho=rho_hi)['agree_wrong'], 5)}"},
        {"parameter": "phi: share of real disagreements on organisation items that involve the kind", "value": f"{fk} of {fn}"},
        {"parameter": "user or manual decision wrong: the user's reversal rate r = k / N (items decided twice "
                      "with different answers)", "value": f"{rev['k']} of {rev['n']}: r {round(rev['r'], 5)}, "
                                                          f"u {round(rev['u'], 5)} ({rev['basis']})"},
        {"parameter": "user reversals: detail (history snapshots read; decisions withdrawn with no new answer, not in k; "
                      "final-audit sheets with a definite answer, and of them changed)",
         "value": f"{rev['detail']['snapshots']} snapshots; {rev['detail']['withdrawn']} withdrawn; "
                  f"{rev['detail']['audit_sheets']} sheets, {rev['detail']['audit_sheets_changed']} changed"},
        {"parameter": "unmatched with a proposal: company share of the proposed kinds (tokens)", "value": round(f_prop, 4)},
        {"parameter": "unmatched with a proposal: organisation share of the proposed kinds (tokens; not independent, "
                      "not free-provider, not blank)", "value": round(o_prop, 4)},
        {"parameter": "organisations among the unmatched real domains, type B", "value":
            f"uniform 0 to {round(min(1.0, 2 * o_prop), 4)} (the company draw x {round(o_prop / f_prop, 4) if f_prop else 0})"},
        {"parameter": "Monte Carlo draws, seed", "value": f"{draws}, {seed}"},
    ]
    tables["parameters"] = params
    kc_rows = []
    for name in ("link", "org"):
        for (a, b), n in sorted(kc[name].items(), key=lambda kv: str(kv[0])):
            kc_rows.append({"detected": name, "shown_company": a, "true_company": b, "count": n})
    tables["kind_transitions"] = kc_rows

    # Other error sources. The employer terms (staff with a personal address, time after a purchase)
    # are a side study (side/employer_model.py); they are not errors of the dataset measurand.
    def tok_where(sql):
        return d.q(f"SELECT coalesce(sum(t.tokens), 0) FROM tok_ev t JOIN lc USING (domain) WHERE {sql}")[0][0]
    other = [
        {"source": "no real domain (blank, no dot, a git-svn id), now unknown",
         "tokens": unm.get("no_real_domain", 0), "share_pct": pct(unm.get("no_real_domain", 0) / total)},
        {"source": "no row, now independent: real domain with an AI proposal (low certainty)",
         "tokens": unm.get("proposed", 0), "share_pct": pct(unm.get("proposed", 0) / total),
         "domains": unm.get("proposed_n", 0), "company_share_of_proposals_pct": pct(f_prop),
         "organisation_share_of_proposals_pct": pct(o_prop)},
        {"source": "no row, now independent: real domain, no proposal (tail)", "tokens": unm.get("tail", 0),
         "share_pct": pct(unm.get("tail", 0) / total), "domains": unm.get("tail_n", 0)},
        {"source": "suffix matches", "tokens": tok_where("lc.match = 'suffix'"),
         "share_pct": pct(tok_where("lc.match = 'suffix'") / total)},
        {"source": "partner addresses under a company domain (corp-partner)",
         "tokens": tok_where("domain LIKE '%corp-partner%'"),
         "share_pct": pct(tok_where("domain LIKE '%corp-partner%'") / total)},
    ]
    tables["other_sources"] = other
    tables["unmatched_kinds"] = unmatched_kinds(unm)

    ns_rows, ns_ev, ns = namespace_model(d, path)
    tables["namespace_owner_check"] = ns_rows
    tables["namespace_rows"] = ns_ev
    # Namespace column error: owns rows only. Bounds per evidence: 0 (no detected error) to the
    # zero-own-share rate of company owners (a project of a company with no token of that company).
    ns_err = []
    owns = [p for p in ns["per"] if p["relation"] == "owns"]
    n_none = ns["agg"][("none", "-", "-")]["n"]
    tot_p = len(ns["per"]) + n_none
    tot_t = sum(p["tokens"] for p in ns["per"]) + ns["agg"][("none", "-", "-")]["tok"]
    # Bound B of the wrong-owner share per class (type B, rectangular 0 to B):
    #   company owner: the Wilson upper bound of the share of its projects with no token of the owner;
    #   other owners (foundations, projects): the Wilson upper bound of the share that the process changed.
    # Model v4.7: an owns row that a measured value (a complete audit stratum) or a later AI layer
    # covers gets that error; the class bound B applies to the other projects of its class only.
    rest_n, rest_t = Counter(), Counter()
    terms = defaultdict(lambda: [0, 0])
    fns = frame.get("namespace", {})
    proj_h = []                          # (class, audit stratum) of each owns project in the frame
    if v47:
        for p in owns:
            cls = (p["evidence"], p["owner_kind"])
            f = fns.get(p["ns_key"])
            lay = later_layer(p["ptr"])
            if f is not None:
                proj_h.append((cls, f[0]))
            if f is not None and f[0] in used_ns:
                term = ("audit", f[0])
            elif lay is not None:
                term = ("user", "") if p["ns"] in d.decide_keys else ("layer", lay[1])
            else:
                rest_n[cls] += 1
                rest_t[cls] += p["tokens"]
                continue
            terms[term][0] += 1
            terms[term][1] += p["tokens"]
    var_p = var_t = mean_p = mean_t = 0.0
    bnd_cls = {}
    for row in ns_rows:
        if row["relation"] != "owns":
            continue
        n = row["projects"]
        k = row["zero_own_share"] if row["owner_kind"] == "company" else row["changed_v3_v41"]
        # Model v4.7: only a project of version 1 can have a change from v3, so the share that the
        # process changed has the version 1 projects of the class as its denominator (all projects
        # of the class when it has no version 1 project).
        n_b = (row.get("projects_v1") or n) if v47 and row["owner_kind"] != "company" else n
        bnd = wilson(k, n_b)[1]
        cls = (row["evidence"], row["owner_kind"])
        bnd_cls[cls] = bnd
        cls_t = row["tokens"]
        n_use = rest_n[cls] if v47 else n
        t_use = rest_t[cls] if v47 else cls_t
        mean_p += n_use * bnd / 2
        mean_t += t_use * bnd / 2
        var_p += (n_use * rectangular_u(bnd / 2)) ** 2
        var_t += (t_use * rectangular_u(bnd / 2)) ** 2
        er = {"measure": f"owns, {row['evidence']}, {row['owner_kind']}: bound B",
              "basis": "zero own-domain tokens" if row["owner_kind"] == "company" else "changed by the process",
              "k": k, "n": n, "B_pct": pct(bnd), "mean_wrong_pct": pct(bnd / 2),
              "u_pct": pct(rectangular_u(bnd / 2))}
        if v47:
            er["projects_with_the_bound"] = n_use
            er["n_of_the_bound"] = n_b
        ns_err.append(er)
    tm_p = tv_p = tm_t = tv_t = 0.0
    for (tk, h), (np_, nt_) in sorted(terms.items()):
        if tk == "audit":
            k_, n_ = used_ns[h]
            m, u = aa.jeffreys(k_, n_), aa.jeffreys_sd(k_, n_)
            basis, name = f"audit stratum {h}: {k_} wrong of {n_} decided (Jeffreys)", f"measured value, {h}"
        elif tk == "layer":
            c_ = layer_checks[h]
            m = P0.q_layer[h]
            u = aa.jeffreys_sd(c_["k"], c_["n"]) if c_["n"] else aa.jeffreys_sd(ai_chk["k_rule"], ai_chk["n"])
            basis = (f"round {h[1:]} check: {c_['k']} wrong of {c_['n']} (Jeffreys)" if c_["n"]
                     else f"round {h[1:]} check: no answer yet, q_r9")
            name = f"later AI layer, round {h[1:]}"
        else:
            m, u = P0.q_user, rev["u"]
            basis, name = "the AI could not decide: q_user", "user decision of a later AI layer"
        tm_p += np_ * m
        tv_p += (np_ * u) ** 2
        tm_t += nt_ * m
        tv_t += (nt_ * u) ** 2
        ns_err.append({"measure": f"owns, {name}", "basis": basis, "k": round(np_ * m, 2), "n": np_,
                       "B_pct": "", "mean_wrong_pct": pct(m), "u_pct": pct(u), "projects_with_the_bound": 0})
    mean_p += tm_p
    var_p += tv_p
    mean_t += tm_t
    var_t += tv_t
    n_owns = len(owns)
    t_owns = sum(p["tokens"] for p in owns)
    ns_err.append({"measure": "owns rows: wrong-owner share (project-weighted)", "basis": "sum of classes",
                   "k": round(mean_p, 1), "n": n_owns, "B_pct": "", "mean_wrong_pct": pct(mean_p / n_owns),
                   "u_pct": pct(math.sqrt(var_p) / n_owns), "U_k2_pct": pct(2 * math.sqrt(var_p) / n_owns)})
    ns_err.append({"measure": "owns rows: wrong-owner share (token-weighted)", "basis": "sum of classes",
                   "k": "", "n": n_owns, "B_pct": "", "mean_wrong_pct": pct(mean_t / t_owns),
                   "u_pct": pct(math.sqrt(var_t) / t_owns), "U_k2_pct": pct(2 * math.sqrt(var_t) / t_owns)})
    # Sensitivity: a change that a later layer made (v4.3 rework, v4.4 round 9, v4.5 and v4.6 user rules) is no
    # sign of a wrong owner. Same classes and bounds, k without those changes (other owners only).
    later = Counter((p["evidence"], p["owner_kind"]) for p in owns
                    if p["changed"] and p.get("layer", "v4.1 or earlier") != "v4.1 or earlier")
    ms_p = ms_t = vs_p = vs_t = 0.0
    for row in ns_rows:
        if row["relation"] != "owns":
            continue
        n = row["projects"]
        k = row["zero_own_share"] if row["owner_kind"] == "company" else \
            row["changed_v3_v41"] - later[(row["evidence"], row["owner_kind"])]
        n_b = (row.get("projects_v1") or n) if v47 and row["owner_kind"] != "company" else n
        bnd = wilson(k, n_b)[1]
        cls = (row["evidence"], row["owner_kind"])
        n_use = rest_n[cls] if v47 else n
        t_use = rest_t[cls] if v47 else row["tokens"]
        ms_p += n_use * bnd / 2
        ms_t += t_use * bnd / 2
        vs_p += (n_use * rectangular_u(bnd / 2)) ** 2
        vs_t += (t_use * rectangular_u(bnd / 2)) ** 2
    ms_p += tm_p
    vs_p += tv_p
    ms_t += tm_t
    vs_t += tv_t
    # The text of model v4.6 stays as published (it named v4.3 to v4.5; the code counted v4.3 to v4.6).
    later_text = "later layer (v4.3 to v4.5)" if not v47 else "later layer (v4.3 or later)"
    for unit, m, v, den in (("project", ms_p, vs_p, n_owns), ("token", ms_t, vs_t, t_owns)):
        ns_err.append({"measure": f"owns rows: wrong-owner share ({unit}-weighted), sensitivity: a change by a "
                                  f"{later_text} is not counted",
                       "basis": "sum of classes", "k": round(m, 1) if unit == "project" else "", "n": n_owns,
                       "B_pct": "", "mean_wrong_pct": pct(m / den), "u_pct": pct(math.sqrt(v) / den),
                       "U_k2_pct": pct(2 * math.sqrt(v) / den)})
    cand = [p for p in ns["per"] if p["relation"] in ("candidate", "participates")]
    cand_strong = [p for p in cand if p["relation"] == "candidate" and p["own_share"] >= 0.10]
    ns_err.append({"measure": "missed owners: candidate rows whose organisation wrote >= 10% of the tokens",
                   "basis": "own-domain share", "k": len(cand_strong), "n": tot_p,
                   "B_pct": "", "mean_wrong_pct": pct(len(cand_strong) / tot_p),
                   "tokens_pct": pct(sum(p["tokens"] for p in cand_strong) / tot_t)})
    ns_err.append({"measure": "projects with no namespace row", "basis": "-", "k": n_none, "n": tot_p,
                   "B_pct": "", "mean_wrong_pct": pct(n_none / tot_p)})
    n_empty = tot_p - n_owns
    t_empty = tot_t - t_owns
    ns_err.append({"measure": "projects with no owns row (the column is empty under the owns rule)", "basis": "-",
                   "k": n_empty, "n": tot_p, "B_pct": "", "mean_wrong_pct": pct(n_empty / tot_p),
                   "tokens_pct": pct(t_empty / tot_t)})
    tables["namespace_error"] = ns_err
    lay = defaultdict(lambda: [0, 0])
    for p in owns:
        a = lay[(p["owner_kind"], p.get("layer", "v4.1 or earlier"), bool(p["changed"]))]
        a[0] += 1
        a[1] += p["tokens"]
    tables["namespace_owns_by_layer"] = [
        {"owner_kind": k, "layer": la, "changed_from_v3": ch, "projects": v[0], "tokens": v[1],
         "share_of_owns_projects_pct": pct(v[0] / n_owns)} for (k, la, ch), v in sorted(lay.items())]
    review = namespace_review_candidates(ns["per"], d.version)
    rc = Counter(r["reason"] for r in review)
    tables["namespace_review_counts"] = [{"reason": k, "rows": v} for k, v in sorted(rc.items())]

    summary = {
        "namespace_review_rows": len(review),
        "total_tokens": total, "linked_tokens": base["linked"], "links": sum(1 for r in chain if r["o41"]),
        "unmatched_tokens": total - base["linked"],
        "E_linked_pct": pct(base["E_linked"]), "E_linked_u_pct": pct(E_sd), "E_linked_U_pct": pct(2 * E_sd),
        "E_all_pct": pct(base["E_all"]), "E_all_U_pct": pct(2 * Ea_sd),
        "E_dataset_pct": pct(base["E_dataset"]), "E_dataset_u_pct": pct(Ed_sd), "E_dataset_U_pct": pct(2 * Ed_sd),
        "E_dataset_mc95": f"{pct(Ed_lo)} to {pct(Ed_hi)}",
        "E_unmatched_pct": pct(base["err_unm"] / total), "E_unmatched_U_pct": pct(2 * Eu_sd),
        "company_share_obs_pct": pct(base["obs_company"]), "company_share_E1E4_pct": pct(tc_mean),
        "company_share_E1E4_U_pct": pct(2 * tc_sd), "company_share_dataset_pct": pct(tot_mean),
        "company_share_dataset_U_pct": pct(2 * tot_sd), "company_share_hard_bounds_pct": pct(tc_mean + unm_share / 2),
        "company_share_hard_bounds_U_pct": pct(2 * combined_u([tc_sd, u_e2_hard])),
        "user_reversals_k": rev["k"], "user_reversals_n": rev["n"], "user_reversal_rate_pct": pct(rev["r"]),
        "user_reversal_u_pct": pct(rev["u"]),
        "se_lo": se_lo, "se_hi": se_hi, "draws": draws, "seed": seed,
        "q_r9_pct": pct(P0.q_r9), "r9_check_k_rule": ai_chk["k_rule"], "r9_check_k": ai_chk["k"],
        "r9_check_n": ai_chk["n"],
        "organisations_version": d.version, "organisations_db": d.db.name,
        "organisations_db_sha256": sha256_file(d.db), "links_dir": d.links.name,
        "links_json_sha256": sha256_file(d.links / "links.json") if (d.links / "links.json").exists() else "",
        "parameters_layer": "v3 -> v4.0 -> v4.1 (companies.v4.duckdb, links-v4)",
    }
    if v47:
        ns_model = defaultdict(lambda: [0, 0.0, 0.0])
        for cls, h in proj_h:
            b = bnd_cls.get(cls, 0.0)
            ns_model[h][0] += 1
            ns_model[h][1] += b / 2
            ns_model[h][2] += rectangular_u(b / 2)
        rule = "complete stratum" if audit_min_n <= 0 else f"at least {audit_min_n} decided answers"
        if aud is not None:
            rep_rows, upd_rows, _ = audit_tables(aud, base, sims, {**used_dom, **used_ns}, total, seed, ns_model, rule)
        else:
            rep_rows, upd_rows = [], []
        tables["audit_replacements"] = rep_rows
        tables["audit_update"] = upd_rows
        lay_rows = []
        for o, c in sorted(layer_checks.items()):
            lay_rows.append({"layer": c["layer"], "origin": o, "check_page": c["folder"], "check_items": c["check_items"],
                             "right": c.get("right", 0), "wrong": c["k"], "unsure": c["unsure"], "n_decided": c["n"],
                             "q_central": round(P0.q_layer[o], 5),
                             "q_basis": "Jeffreys (k + 0.5) / (n + 1)" if c["n"] else "no answer yet: q_r9",
                             "cp95": f"{round(c['cp'][0], 5)} to {round(c['cp'][1], 5)}" if c["n"] else "",
                             "decide_items": c["decide_items"], "decide_answered": c["decide_answered"],
                             "links": sum(1 for r in chain if r["origin"] == o),
                             "link_tokens": sum(r["tokens"] for r in chain if r["origin"] == o),
                             "owns_projects": terms.get(("layer", o), [0, 0])[0]})
        tables["later_ai_layers"] = lay_rows
        lj = d.links / "links.json"
        lmeta = json.loads(lj.read_text()) if lj.exists() else {}
        ldb = (lmeta.get("inputs") or {}).get("db_sha256", "")
        dbsha = summary["organisations_db_sha256"]
        upd_main = upd_rows[1] if len(upd_rows) > 1 else {}
        summary.update({
            "model": d.model, "total_tokens_version1": d.total_v1, "total_tokens_extension": total - d.total_v1,
            "total_tokens_expected": DATASET_TOKENS, "total_tokens_ok": total == DATASET_TOKENS,
            "x1k_counts": d.x1k.name if d.x1k else "",
            "links_db_sha256": ldb, "links_built_with_this_db": bool(ldb) and ldb == dbsha,
            "links_added_from_db_rows": d.links_added,
            "links_added_tokens": sum(r["tokens"] for r in chain if r["domain"] in d.added_domains),
            "links_with_no_tokens": d.links_no_tokens,
            "later_layers": {o: {"k": c["k"], "n": c["n"], "q_pct": pct(P0.q_layer[o]),
                                 "decide_items": c["decide_items"]} for o, c in layer_checks.items()},
            "q_later_pct": pct(P0.q_later), "kind_user_pct": pct(P0.kind_user),
            "audit_sample": Path(audit).name if aud else "", "audit_answers": aud["answers"] if aud else 0,
            "audit_rule": rule, "audit_strata_used": sorted({**used_dom, **used_ns}),
            "audit_links_in_frame": sum(1 for r in chain if r.get("astratum")),
            "audit_tokens_in_frame": sum(r["tokens"] for r in chain if r.get("astratum")),
            "E_dataset_update_pct": upd_rows[2]["E_dataset_pct"] if len(upd_rows) > 2 else "",
            "E_dataset_update_U_pct": upd_rows[2]["E_dataset_U_pct"] if len(upd_rows) > 2 else "",
            "E_dataset_main_check_pct": upd_main.get("E_dataset_pct", ""),
            "namespace_wrong_owner_projects_pct": pct(mean_p / n_owns), "namespace_wrong_owner_projects_U_pct":
                pct(2 * math.sqrt(var_p) / n_owns),
            "namespace_wrong_owner_tokens_pct": pct(mean_t / t_owns), "namespace_wrong_owner_tokens_U_pct":
                pct(2 * math.sqrt(var_t) / t_owns),
            "namespace_no_change_projects_pct": pct(ms_p / n_owns), "namespace_no_change_projects_U_pct":
                pct(2 * math.sqrt(vs_p) / n_owns),
            "namespace_owns_projects": n_owns,
        })
        summary["parameters_layer"] = summary["parameters_layer"] + "; propagation: both layers"
        params.extend([
            {"parameter": f"later AI layer {o} ({c['layer']}): wrong of decided answers of its check sample",
             "value": (f"{c['k']} of {c['n']}; q {round(P0.q_layer[o], 5)} (Jeffreys); 95% Clopper-Pearson "
                       f"{round(c['cp'][0], 4)} to {round(c['cp'][1], 4)}") if c["n"]
             else f"no answer yet; q = q_r9 = {round(P0.q_layer[o], 5)}"} for o, c in sorted(layer_checks.items())])
        params.append({"parameter": "kind error of the user or curated path: q_user x phi", "value": round(P0.kind_user, 5)})
        params.append({"parameter": "audit values: rule, strata used", "value":
                       f"{rule}; {', '.join(sorted({**used_dom, **used_ns})) or 'none yet'}"})
        if tail is not None:
            tables["tail_audit"] = tail_audit_rows(tail)
            params.append({"parameter": "organisations among the unmatched real domains: the tail audit", "value":
                           (f"used: organisation rate {round(P0.o_unmatched, 5)}, company rate {round(P0.f_unmatched, 5)} "
                            f"(Jeffreys); 95% Clopper-Pearson {round(tail['org_rate_cp95'][0], 4)} to "
                            f"{round(tail['org_rate_cp95'][1], 4)}") if tail["used"] else
                           f"not used ({tail['answered']} of {tail['items']} items answered); the type B rate stays"})
            summary.update({
                "tail_audit": Path(tail_audit).name, "tail_audit_items": tail["items"],
                "tail_audit_answered": tail["answered"], "tail_audit_complete": tail["complete"],
                "tail_audit_used": tail["used"], "tail_audit_frame_match": tail["frame_match"],
                "tail_audit_pool_tokens_in_frame_pct": pct(tail["pool_tokens_in_frame"] / tail["pool_tokens"])
                if tail["pool_tokens"] else 0.0,
                "tail_org_rate_pct": pct(P0.o_unmatched) if tail["used"] else "",
                "tail_company_rate_pct": pct(P0.f_unmatched) if tail["used"] else "",
            })
    if v47 and column_audit is not None and (Path(column_audit) / "design.json").exists():
        import audit_columns as ac
        column_audit_update(summary, tables, ac.analyse(Path(column_audit)), total, Path(column_audit).name)
    tables["summary"] = [summary]
    return {"d": d, "chain": chain, "chain41": chain41, "total": total, "base": base, "sims": sims, "P0": P0, "d_se": d_se,
            "path": path, "tc": (tc_mean, tc_sd), "unm": unm, "unm_share": unm_share, "u_e2_hard": u_e2_hard,
            "tables": tables, "summary": summary, "review": review, "draws": draws, "seed": seed}


def column_audit_update(summary: dict, tables: dict, res: dict, total: int, name: str) -> None:
    """Model v4.7 with a column audit (review/audit_columns.py): its tables, and the measured error of
    each column whose part has at least use_min decided answers in place of the model values.

    The model values stay under the keys *_model_pct. The domain part measures the token-weighted
    wrong share of the real domains (its frame); the dataset share is that rate x frame tokens /
    the evaluated tokens (the tokens with no real domain have the value unknown, which is right).
    The company share of the audit is reported apart; it does not replace the model value."""
    import audit_columns as ac
    parts = res["parts"]
    state, est, strata = [], [], []
    for part in ac.PARTS:
        p = parts.get(part)
        if not p:
            continue
        state.append({"part": part, "items": p["items"], "decided": p["decided"], "decided_own": p["decided_own"],
                      "decided_carried": p["decided_carried"], "unsure": p["unsure"], "open": p["open"],
                      "use_min": res["use_min"], "used": p["used"]})
        for key in [k for k in p if isinstance(p[k], dict) and "central" in p[k]]:
            e = p[key]
            c = e.get("central")
            est.append({"part": part, "measure": key, "central_pct": pct(c) if c is not None else "",
                        "all_unsure_right_pct": pct(e["lo_all_right"]) if c is not None else "",
                        "all_unsure_wrong_pct": pct(e["hi_all_wrong"]) if c is not None else "",
                        "u_pct": pct(e["sd"]) if c is not None else "",
                        "ci95_pct": f"{pct(e['ci95'][0])} to {pct(e['ci95'][1])}" if c is not None else "",
                        "weight_covered_pct": pct(e["weight_covered"] / e["weight_total"]) if e["weight_total"] else ""})
            if key in ("wrong_projects", "wrong_tokens") and c is not None:
                for r in e["rows"]:
                    strata.append({"part": part, "measure": key, **{k: r[k] for k in ("stratum", "units", "n", "decided",
                                                                                     "unsure", "open", "carried")},
                                   "weight": r["W"], "rate_central_pct": pct(r["rate_central"]) if "rate_central" in r else ""})
    tables["column_audit_state"] = state
    tables["column_audit_estimate"] = est
    tables["column_audit_strata"] = strata
    tables["column_audit_sample_size"] = res["sample_size"]
    summary.update({"column_audit": name, "column_audit_use_min": res["use_min"],
                    "namespace_error_basis": "model (type B bounds and AI-round checks)",
                    "domain_error_basis": "model (propagation and tail audit)"})
    for part in ac.PARTS:
        p = parts.get(part) or {}
        summary[f"column_audit_{part}_decided"] = p.get("decided", 0)
        summary[f"column_audit_{part}_decided_carried"] = p.get("decided_carried", 0)
        summary[f"column_audit_{part}_used"] = bool(p.get("used"))
    ns, dom = parts.get("ns") or {}, parts.get("dom") or {}
    if ns.get("used"):
        for unit in ("projects", "tokens"):
            e = ns[f"wrong_{unit}"]
            k = f"namespace_wrong_owner_{unit}"
            summary[f"{k}_model_pct"] = summary.get(f"{k}_pct", "")
            summary[f"{k}_model_U_pct"] = summary.get(f"{k}_U_pct", "")
            summary[f"{k}_pct"] = pct(e["central"])
            summary[f"{k}_U_pct"] = pct(2 * e["sd"])
            summary[f"{k}_ci95"] = f"{pct(e['ci95'][0])} to {pct(e['ci95'][1])}"
            summary[f"{k}_unsure_range"] = f"{pct(e['lo_all_right'])} to {pct(e['hi_all_wrong'])}"
        summary["namespace_error_basis"] = "measured: column audit"
    if dom.get("used"):
        sc = dom["frame_tokens"] / total
        e, el, eu = dom["wrong_tokens"], dom["wrong_tokens_linked_share"], dom["wrong_tokens_unmatched_share"]
        for k in ("E_dataset_pct", "E_dataset_U_pct", "E_dataset_mc95", "E_all_pct", "E_unmatched_pct", "E_linked_pct"):
            summary[k.replace("_pct", "_model_pct") if k.endswith("_pct") else k + "_model"] = summary.get(k, "")
        summary["E_dataset_pct"] = pct(e["central"] * sc)
        summary["E_dataset_U_pct"] = pct(2 * e["sd"] * sc)
        summary["E_dataset_mc95"] = f"{pct(e['ci95'][0] * sc)} to {pct(e['ci95'][1] * sc)}"
        summary["E_dataset_unsure_range"] = f"{pct(e['lo_all_right'] * sc)} to {pct(e['hi_all_wrong'] * sc)}"
        summary["E_all_pct"] = pct(el["central"] * sc)
        summary["E_unmatched_pct"] = pct(eu["central"] * sc)
        lt = summary.get("linked_tokens") or 0
        summary["E_linked_pct"] = pct(el["central"] * dom["frame_tokens"] / lt) if lt else ""
        summary["company_share_column_audit_pct"] = pct(dom["company_tokens"]["central"] * sc)
        summary["domain_error_basis"] = "measured: column audit"


def write_outputs(out: Path, tables: dict, summary: dict, title: str) -> None:
    """The CSV tables, summary.json and tables.md; stop if any text holds the at sign."""
    out.mkdir(parents=True, exist_ok=True)
    md = [f"# {title}\n"]
    for name, rows in tables.items():
        md.append(f"## {name}\n")
        md.append(md_table(rows))
    text = "\n".join(md)
    if AT in text or AT in json.dumps(summary):
        raise SystemExit("an output holds the at sign")
    for name, rows in tables.items():
        write_csv(out / f"{name}.csv", rows)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    (out / "tables.md").write_text(text)


def write_link_error(path: Path, chain: list[dict], P0: Params, d_se: dict) -> None:
    """One row per dataset domain of the chain: a hashed key, the path and the error probability."""
    import duckdb
    lc = duckdb.connect()
    lc.execute("CREATE TABLE link_error (key_hash VARCHAR, tokens BIGINT, band VARCHAR, state VARCHAR, "
               "group3 VARCHAR, group41 VARCHAR, origin VARCHAR, match41 VARCHAR, kind3 VARCHAR, kind41 VARCHAR, "
               "checks VARCHAR, p_error DOUBLE)")
    lc.executemany("INSERT INTO link_error VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        (key_hash(r["domain"]), r["tokens"], r["band"], r["state"], r["group3"], r["group41"], r["origin"],
         r["match41"], r["kind3"], r["kind41"], "+".join(c for c in ("r4d", "r4f", "r7", "r8", "user") if r["seen"][c]),
         link_p_used(r, P0, d_se) if r["o41"] is not None else None) for r in chain])
    lc.execute(f"COPY (SELECT * FROM link_error ORDER BY key_hash) TO '{path}' (FORMAT parquet)")


def error_stratum(origin: str, band_: str, kind: str | None, match: str | None) -> str:
    """The cell of a link: origin group / token band / kind class / match.

    The same cell as the "cells" column of the audit sample (review/audit_sample.py, strata.csv), so
    an audit stratum (a union of cells) joins to the domains by this text."""
    og = {"r4d": "r4d/r4f", "r4f": "r4d/r4f", "r5": "r5/r6", "r6": "r5/r6"}.get(origin, origin)
    return "/".join((og, band_, kclass(kind), match or ""))


def p_error_rows(chain: list[dict], P0: Params, d_se: dict) -> list[tuple]:
    """(key_hash, error_stratum, p_error) of each dataset domain with a link in the evaluated layer.

    p_error is the probability that the link names the wrong organisation, from the path of the
    link (section 4.5 of ERROR_MODEL.md). A domain with no link has no row: the column gives it
    `independent`, and its error is the stratum value of the unmatched domains (unmatched_kinds.csv)."""
    rows = [(key_hash(r["domain"]), error_stratum(r["origin"], r["band"], r["kind41"], r["match41"]),
             link_p_used(r, P0, d_se)) for r in chain if r["o41"] is not None]
    return sorted(rows)


def check_p_error_rows(n_rows: int, n_links: int) -> None:
    """Stop when the p_error rows are not one for each link of the evaluated layer (lc).

    build_organisations.py gives each row of domain_links.parquet its p_error by the hashed domain;
    a link with no row stops that build ("domains without p_error")."""
    if n_rows != n_links:
        raise SystemExit(f"organisation_domains_p_error: {n_rows} rows for {n_links} links "
                         f"({n_links - n_rows} links have no p_error)")


def write_p_error(path: Path, chain: list[dict], P0: Params, d_se: dict, n_links: int | None = None) -> int:
    """organisation_domains_p_error.parquet: the p_error column of the organisation_domains table.

    n_links: the number of links of the evaluated layer; the file is not written when the rows differ."""
    import duckdb
    rows = p_error_rows(chain, P0, d_se)
    if n_links is not None:
        check_p_error_rows(len(rows), n_links)
    lc = duckdb.connect()
    lc.execute("CREATE TABLE p (key_hash VARCHAR, error_stratum VARCHAR, p_error DOUBLE)")
    lc.executemany("INSERT INTO p VALUES (?,?,?)", rows)
    lc.execute(f"COPY (SELECT * FROM p ORDER BY key_hash) TO '{path}' (FORMAT parquet)")
    return len(rows)


def run(ws: Path, out: Path, draws: int, seed: int, db: Path | None = None, links: Path | None = None,
        model: str = "v4.6", x1k: Path | None = None, audit: Path | None = None, audit_min_n: int = 0,
        tail_audit: Path | None = None, column_audit: Path | None = None) -> dict:
    d = Data(ws, db=db, links=links, model=model, x1k=x1k)
    out.mkdir(parents=True, exist_ok=True)
    ctx = compute(d, draws, seed, audit=audit, audit_min_n=audit_min_n, tail_audit=tail_audit,
                  column_audit=column_audit)
    # Not in tables.md: this list holds project names and organisation ids (no domain, no person data).
    write_csv(out / "namespace_review_candidates.csv", ctx["review"])
    if AT in (out / "namespace_review_candidates.csv").read_text():
        raise SystemExit("namespace_review_candidates.csv holds the at sign")
    write_link_error(out / "link_error.parquet", ctx["chain"], ctx["P0"], ctx["d_se"])
    n_links = d.q("SELECT count(DISTINCT domain) FROM lc")[0][0]
    n = write_p_error(out / "organisation_domains_p_error.parquet", ctx["chain"], ctx["P0"], ctx["d_se"], n_links)
    ctx["summary"]["p_error_rows"] = n
    title = "S8 error model: tables (written by error_model.py; do not edit)" if model == "v4.6" else \
        f"S8 error model, model {model}, database {d.version}: tables (written by error_model.py; do not edit)"
    write_outputs(out, ctx["tables"], ctx["summary"], title)
    return ctx["summary"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ws", type=Path, default=WS_DEFAULT)
    ap.add_argument("--model", choices=MODELS, default=MODEL_DEFAULT,
                    help="v4.6: the published model (version 1 only); v4.7: both layers and the audit values")
    ap.add_argument("--db", type=Path, help="the evaluated database (default <ws>/" +
                    ", ".join(f"{DEFAULTS[m]['db']} for model {m}" for m in MODELS) + ")")
    ap.add_argument("--links", type=Path, help="the evaluated link folder (default <ws>/" +
                    ", ".join(f"{DEFAULTS[m]['links']} for model {m}" for m in MODELS) + ")")
    ap.add_argument("--x1k-counts", type=Path,
                    help=f"model v4.7: the domain counts of the extension (default <ws>/{DEFAULTS['v4.7']['x1k']})")
    ap.add_argument("--audit-sample", type=Path,
                    help=f"model v4.7: the audit sample folder (default <ws>/{AUDIT_SAMPLE_DEFAULT})")
    ap.add_argument("--audit-min-n", type=int, default=0,
                    help="model v4.7: a stratum gives its measured value with this many decided answers "
                         "(default 0: only a complete stratum)")
    ap.add_argument("--no-audit", action="store_true", help="model v4.7 with no audit value")
    ap.add_argument("--tail-audit", type=Path,
                    help=f"model v4.7: the tail audit folder (default <ws>/{TAIL_AUDIT_DEFAULT}); its measured rates "
                         "replace the type B rates of the unmatched real domains when its page is complete")
    ap.add_argument("--column-audit", type=Path,
                    help="model v4.7: the folder of the column audit (review/audit_columns.py); a part with at "
                         "least 440 decided answers gives the measured error of its column")
    ap.add_argument("--no-tail-audit", action="store_true",
                    help="model v4.7: keep the type B rates of the unmatched real domains (no tail audit)")
    ap.add_argument("--out", type=Path, help="default <ws>/error-model (model v4.6) or "
                                             "<ws>/error-model-<database version> (model v4.7)")
    ap.add_argument("--draws", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20261018)
    a = ap.parse_args(argv)
    dflt = DEFAULTS[a.model]
    db = a.db or a.ws / dflt["db"]
    out = a.out or a.ws / dflt["out"].format(version=layer_version(db, Path("/nonexistent")))
    audit = None if a.model == "v4.6" or a.no_audit else (a.audit_sample or a.ws / AUDIT_SAMPLE_DEFAULT)
    tail = None if a.model == "v4.6" or a.no_tail_audit else (a.tail_audit or a.ws / TAIL_AUDIT_DEFAULT)
    col = a.column_audit if a.model != "v4.6" else None
    s = run(a.ws, out, a.draws, a.seed, a.db, a.links, a.model, a.x1k_counts, audit, a.audit_min_n, tail, col)
    print(json.dumps(s, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
