#!/usr/bin/env python3
"""Frame and PPS sample of the tail audit: the unmatched real domains of the E2 term (2026-10-26).

    audit_tail_sample.py [--ws DIR] [--db companies.v4.8.duckdb] [--links DIR] [--x1k FILE]
                         [--n 60] [--seed-text 20261026:tail] [--out DIR]

The user agreed (2026-10-26): add a random sample of about 60 domains from the unreviewed tail of the
real mail domains (no organisation row in the database) to phase 2 of the audit. Its purpose: a
measured, token-weighted organisation rate of these domains in place of the assumed rate of the E2
term of error_model.py (ERROR_MODEL.md sections 6.3 and 10a).

The frame is the E2 pool of error_model.py, model v4.7: the domains of the evaluated tokens (the
version 1 cache plus the domain counts of the extension) with no link in the link folder after the
exact links of the database (add_db_links), minus the tokens with no real domain. The script takes the
pool from error_model.unmatched_rows, so the frame and the E2 term are the same set, one for one.

Design: systematic PPS (probability proportional to tokens). Sort the frame by tokens (descending;
then by domain), take as certainty units each domain with tokens >= the step (repeat with the rest
until no domain is larger than the step), then put n - (certainty units) points on the cumulative
tokens of the rest: start u x step, step = rest tokens / rest n, u from sha256(seed text). The
inclusion probability of a non-certainty unit is (rest n) x tokens / (rest tokens).

Output (OUT, in the workspace, not in git, because the frame holds personal domains):
  frame.csv    domain, tokens, part (proposed or tail), tokens_v1, tokens_x1k
  design.json  frame size and tokens, step, start, certainty units, inclusion probabilities, checksums
  sample.csv   one row per sampled domain (item order: certainty units first, then the points)
No value may hold an at sign: the script stops.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(1, str(HERE))

AT = chr(64)
SEED_TEXT = "20261026:tail"
N_DEFAULT = 60


def seed_fraction(text: str) -> float:
    """A number in [0, 1) from the first 64 bits of sha256(text)."""
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16) / 2 ** 64


def frame_sha256(frame: list[dict]) -> str:
    """Checksum of the frame: the lines 'domain<TAB>tokens' sorted by domain."""
    h = hashlib.sha256()
    for r in sorted(frame, key=lambda r: r["domain"]):
        h.update(f"{r['domain']}\t{int(r['tokens'])}\n".encode())
    return h.hexdigest()


def pps_systematic(frame: list[dict], n: int, u: float) -> dict:
    """Systematic PPS sample of n units from frame (dicts with domain and tokens > 0).

    Returns {"certainty": [...], "points": [...], "step", "start", "rest_tokens", "rest_n", "total"}.
    Each sampled row gets pi (inclusion probability) and the field unit ("certainty" or "point")."""
    rows = sorted((dict(r) for r in frame if r["tokens"] > 0), key=lambda r: (-r["tokens"], r["domain"]))
    total = sum(r["tokens"] for r in rows)
    if n <= 0 or not rows:
        raise ValueError("an empty frame or n <= 0")
    if n >= len(rows):
        raise ValueError("n is not smaller than the frame")
    cert: list[dict] = []
    rest = rows
    while True:
        rest_n = n - len(cert)
        rest_t = sum(r["tokens"] for r in rest)
        step = rest_t / rest_n
        big = [r for r in rest if r["tokens"] >= step]
        if not big:
            break
        cert += big
        rest = [r for r in rest if r["tokens"] < step]
        if len(cert) >= n:
            raise ValueError("the certainty units fill the sample")
    for r in cert:
        r.update(unit="certainty", pi=1.0, point="")
    start = u * step
    pts = [start + i * step for i in range(rest_n)]
    chosen, cum, j = [], 0.0, 0
    for r in rest:
        lo, hi = cum, cum + r["tokens"]
        cum = hi
        while j < len(pts) and pts[j] < hi:
            if pts[j] >= lo:
                chosen.append(dict(r, unit="point", pi=rest_n * r["tokens"] / rest_t, point=round(pts[j], 3)))
            j += 1
    if len(chosen) != rest_n or len({r["domain"] for r in chosen}) != rest_n:
        raise AssertionError("systematic draw did not give rest_n distinct units")
    return {"certainty": cert, "points": chosen, "step": step, "start": start, "rest_tokens": rest_t,
            "rest_n": rest_n, "total": total, "frame_n": len(rows)}


def check_no_at(obj) -> None:
    s = json.dumps(obj, ensure_ascii=False)
    if AT in s:
        raise SystemExit("an at sign in the output: stop")


def load_frame(ws: Path, db: Path, links: Path | None, x1k: Path | None) -> tuple[list[dict], dict]:
    """The frame from error_model.Data (model v4.7) and unmatched_rows, with per-domain extras."""
    import error_model as em
    d = em.Data(ws, db=db, links=links, model="v4.7", x1k=x1k)
    rows = em.unmatched_rows(d)
    real = [(dom, tok, part) for dom, tok, part in rows if part != "no_real_domain"]
    no_real = sum(tok for _, tok, part in rows if part == "no_real_domain")
    doms = {dom for dom, _, _ in real}
    c = d.con
    c.execute("CREATE TEMP TABLE fr (domain VARCHAR)")
    c.executemany("INSERT INTO fr VALUES (?)", [(x,) for x in sorted(doms)])
    v1 = dict(c.execute("SELECT t.domain, t.tokens FROM tok t JOIN fr USING (domain)").fetchall())
    proj = {}
    for dom, n, top, top_t in c.execute("""
        SELECT domain, count(*) AS n, arg_max(proj, tokens) AS top, max(tokens) FROM tok_pd_ev JOIN fr USING (domain)
        GROUP BY 1""").fetchall():
        proj[dom] = (n, top, top_t)
    x1kc = {}
    if d.x1k is not None and Path(d.x1k).exists():
        for dom, cm, au in c.execute(f"""SELECT domain, sum(commits), sum(authors) FROM read_parquet('{d.x1k}')
                                         WHERE domain IN (SELECT domain FROM fr) GROUP BY 1""").fetchall():
            x1kc[dom] = (cm, au)
    dropped = set()
    try:
        dropped = {x for (x,) in c.execute("SELECT domain FROM cur.company_domain_dropped").fetchall()} & doms
    except Exception:
        pass
    from build_links import FREE_SUFFIXES
    free = {x for x in doms if any(x == s or x.endswith("." + s) for s in FREE_SUFFIXES)}
    frame = []
    for dom, tok, part in real:
        n, top, _ = proj.get(dom, (0, "", 0))
        cm, au = x1kc.get(dom, ("", ""))
        frame.append({"domain": dom, "tokens": int(tok), "part": part, "tokens_v1": int(v1.get(dom, 0)),
                      "tokens_x1k": int(tok) - int(v1.get(dom, 0)), "dataset_projects": n, "top_project": top,
                      "commits_x1k": cm, "authors_x1k": au, "dropped_in_db": dom in dropped})
    info = {"evaluated_tokens": d.total, "no_real_domain_tokens": no_real, "links_added_from_db_rows": d.links_added,
            "db": str(d.db), "links": str(d.links), "x1k": str(d.x1k), "frame_dropped_domains": len(dropped),
            "frame_free_suffix_domains": len(free),
            "db_sha256": em.sha256_file(d.db)}
    return frame, info


def main(argv: list[str] | None = None) -> int:
    ws_default = Path.home() / "Projects/cregit-workspace/companies"
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ws", type=Path, default=ws_default)
    ap.add_argument("--db", type=Path, default=ws_default / "companies.v4.8.duckdb")
    ap.add_argument("--links", type=Path, help="default: the model v4.7 link folder of error_model.py")
    ap.add_argument("--x1k", type=Path, help="default: the model v4.7 extension counts of error_model.py")
    ap.add_argument("--n", type=int, default=N_DEFAULT)
    ap.add_argument("--seed-text", default=SEED_TEXT)
    ap.add_argument("--out", type=Path, default=ws_default / "review/audit-tail")
    a = ap.parse_args(argv)
    frame, info = load_frame(a.ws, a.db, a.links, a.x1k)
    u = seed_fraction(a.seed_text)
    s = pps_systematic(frame, a.n, u)
    sample = s["certainty"] + s["points"]
    for i, r in enumerate(sample, 1):
        r["sample_id"] = f"S{i:02d}"
    a.out.mkdir(parents=True, exist_ok=True)
    fcols = ["domain", "tokens", "part", "tokens_v1", "tokens_x1k", "dataset_projects", "dropped_in_db"]
    scols = ["sample_id", "unit", "domain", "tokens", "pi", "point", "part", "tokens_v1", "tokens_x1k",
             "dataset_projects", "top_project", "commits_x1k", "authors_x1k", "dropped_in_db"]
    check_no_at(sample)
    check_no_at([r["domain"] for r in frame])
    with open(a.out / "frame.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fcols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(frame, key=lambda r: (-r["tokens"], r["domain"])))
    with open(a.out / "sample.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, scols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(sample)
    parts = {p: {"domains": sum(r["part"] == p for r in frame), "tokens": sum(r["tokens"] for r in frame if r["part"] == p)}
             for p in ("proposed", "tail")}
    design = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": "token-weighted organisation rate of the unmatched real domains (E2 term of error_model.py)",
        "frame_definition": "error_model.unmatched_rows (model v4.7): domains of the evaluated tokens with no link "
                            "after add_db_links, parts proposed and tail (a real domain: not blank, a dot, no at sign)",
        "frame_n": s["frame_n"], "frame_tokens": s["total"], "frame_parts": parts,
        "frame_sha256": frame_sha256(frame), "frame_csv_sha256": hashlib.sha256((a.out / "frame.csv").read_bytes()).hexdigest(),
        "n": a.n, "seed_text": a.seed_text, "seed_fraction": u,
        "method": "systematic PPS on the cumulative tokens (sorted by tokens descending, then domain), certainty units apart",
        "certainty_n": len(s["certainty"]), "certainty_tokens": sum(r["tokens"] for r in s["certainty"]),
        "certainty_units": [{"sample_id": r["sample_id"], "domain": r["domain"], "tokens": r["tokens"], "pi": 1.0}
                            for r in s["certainty"]],
        "rest_n": s["rest_n"], "rest_tokens": s["rest_tokens"], "step": s["step"], "start": s["start"],
        "points": [{"sample_id": r["sample_id"], "domain": r["domain"], "tokens": r["tokens"], "pi": r["pi"],
                    "point": r["point"]} for r in s["points"]],
        "estimator": "Horvitz-Thompson: rate = (sum over certainty units of t y + rest_tokens x mean of y over the "
                     "points) / frame_tokens (the points have equal weight t / pi = step)",
        "inputs": info,
        "sample_csv_sha256": hashlib.sha256((a.out / "sample.csv").read_bytes()).hexdigest(),
    }
    check_no_at(design)
    (a.out / "design.json").write_text(json.dumps(design, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: design[k] for k in ("frame_n", "frame_tokens", "certainty_n", "certainty_tokens", "rest_n",
                                              "step", "frame_sha256")}), file=sys.stderr)
    print(json.dumps(design["frame_parts"]), json.dumps(info, default=str), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
