"""Summaries of the token-against-line run on the random sample (no person data in input or output).

Input: per-project.tsv, limits.tsv, status.tsv, failures.tsv of the run (tables-after-repair/), and the draw table
plan.tsv. Output: one markdown file with all tables and one TSV with the estimates.

    python3 -I analyze.py --tables DIR --plan plan.tsv --frame 8598 --out-md results.md --out-tsv estimates.tsv

Estimates
  project mean   mean over the projects of the share of tokens, with the 95% interval
                 mean +- t(0.975, n-1) * s / sqrt(n) * sqrt((N - n) / (N - 1))  (finite population correction)
  weighted ratio sum of the tokens with another author over the sum of the blamed tokens, with the 95%
                 percentile interval of a bootstrap over the projects (10,000 draws, seed 20261109)
The value of a project is over the tokens that the blame covers (tokens in files without that blame are not in the
denominator); a project with no covered token has no value and is not in the mean (it is listed).
"""
import argparse
import csv
import math
import random
import statistics
from pathlib import Path

CUT_LIMIT_PCT = 10.0


def tquant(df, p=0.975):
    z = statistics.NormalDist().inv_cdf(p)
    return z + (z ** 3 + z) / (4 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96 * df ** 2)


def mean_ci(v, N):
    n = len(v)
    m = sum(v) / n
    if n < 2:
        return m, float("nan"), float("nan"), n
    s = statistics.stdev(v)
    h = tquant(n - 1) * s / math.sqrt(n) * math.sqrt(max(N - n, 0) / (N - 1)) if N > 1 else 0.0
    return m, m - h, m + h, n


def boot_ratio(num, den, reps=10000, seed=20261109):
    rng = random.Random(seed)
    n = len(num)
    tot = sum(num) / sum(den)
    out = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        d = sum(den[i] for i in idx)
        if d:
            out.append(sum(num[i] for i in idx) / d)
    out.sort()
    return tot, out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


def rd(path):
    with open(path) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def fl(r, k):
    v = r.get(k, "")
    try:
        return float(v)
    except ValueError:
        return float("nan")


def fl0(r, k):
    v = fl(r, k)
    return 0.0 if v != v else v


def md(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def p2(x):
    return "n/a" if x != x else f"{x:.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--frame", type=int, default=8598)
    ap.add_argument("--out-md", required=True)
    ap.add_argument("--out-tsv", required=True)
    ap.add_argument("--cut-pct", type=float, default=CUT_LIMIT_PCT)
    a = ap.parse_args()
    T = Path(a.tables)
    N = a.frame
    pp = rd(T / "per-project.tsv")
    plan = {r["project"]: r for r in rd(a.plan)}
    status = rd(T / "status.tsv")
    fails = rd(T / "failures.tsv")
    lim = rd(T / "limits.tsv")
    out, est = [], []

    def add(name, group, n, mean, lo, hi, pooled=None, plo=None, phi=None):
        est.append((name, group, str(n), f"{mean:.4f}", f"{lo:.4f}", f"{hi:.4f}",
                    "" if pooled is None else f"{pooled:.4f}", "" if plo is None else f"{plo:.4f}",
                    "" if phi is None else f"{phi:.4f}"))

    for r in pp:
        r["_tokens"] = fl(r, "tokens")
        r["_cut_pct"] = 100.0 * (1 - fl(r, "tok_matched") / r["_tokens"]) if r["_tokens"] else float("nan")
        r["_cut_any_pct"] = fl(r, "pct_tok_in_limit_any")
        for bl, col in (("plain", "tok_matched"), ("w", "tok_matched_w"), ("wmc", "tok_matched_wmc")):
            r["_cut_" + bl] = 100.0 * (1 - fl(r, col) / r["_tokens"]) if r["_tokens"] else float("nan")
    big_cut = [r for r in pp if r["_cut_pct"] > a.cut_pct]
    keep = [r for r in pp if not (r["_cut_pct"] > a.cut_pct)]

    st_counts = {}
    for r in status:
        st_counts[r["state"]] = st_counts.get(r["state"], 0) + 1
    out.append("## Run state\n")
    out.append(md(["state", "projects"], sorted(st_counts.items())))
    out.append(f"\nProjects in the per-project table: {len(pp)}. Clone and copy failures (failures.tsv rows): {len(fails)}.\n")

    # ---- token level
    specs = [("another author, plain line blame", "tok_author_diff", "tok_matched", "plain"),
             ("another author, line blame -w", "tok_author_diff_w", "tok_matched_w", "w"),
             ("another author, line blame -w -M -C", "tok_author_diff_wmc", "tok_matched_wmc", "wmc"),
             ("another commit, plain", "tok_commit_diff", "tok_matched", "plain"),
             ("another commit, -w -M -C", "tok_commit_diff_wmc", "tok_matched_wmc", "wmc"),
             ("another organization, plain", "tok_firm_diff", "tok_matched", "plain"),
             ("another organization, -w -M -C", "tok_firm_diff_wmc", "tok_matched_wmc", "wmc")]
    for title, rows_, tag in (("All projects with a value", pp, "all"),
                              (f"Without projects with more than {a.cut_pct:g}% of the tokens cut", keep, "keep")):
        out.append(f"## Token level: {title}\n")
        tab = []
        for name, num, den, bl in specs:
            rr = [r for r in rows_ if fl(r, den) > 0 and (tag == "all" or not r["_cut_" + bl] > a.cut_pct)]
            v = [100 * fl(r, num) / fl(r, den) for r in rr]
            m, lo, hi, n = mean_ci(v, N)
            nu, de = [fl(r, num) for r in rr], [fl(r, den) for r in rr]
            tot, blo, bhi = boot_ratio(nu, de)
            med = statistics.median(v)
            tab.append([name, n, f"{m:.2f} ({lo:.2f} to {hi:.2f})", f"{100 * tot:.2f} ({100 * blo:.2f} to {100 * bhi:.2f})", f"{med:.2f}"])
            add(name, tag, n, m, lo, hi, 100 * tot, 100 * blo, 100 * bhi)
        out.append(md(["share of tokens with", "projects", "project mean % (95% interval)",
                       "token-weighted % (95% bootstrap interval)", "project median %"], tab))
        out.append("")

    # ---- cut
    out.append("## Tokens cut or not blamed\n")
    tt = sum(r["_tokens"] for r in pp)
    out.append(md(["blame", "tokens of the sample without this blame", "share of all tokens %", "projects with a cut above "
                   f"{a.cut_pct:g}%"],
                  [[bl, f"{int(sum(r['_tokens'] * r['_cut_' + bl] / 100 for r in pp if r['_cut_' + bl] == r['_cut_' + bl])):,}",
                    f"{sum(r['_tokens'] * r['_cut_' + bl] / 100 for r in pp if r['_cut_' + bl] == r['_cut_' + bl]) / tt * 100:.2f}",
                    ", ".join(r["project"] for r in pp if r["_cut_" + bl] > a.cut_pct) or "none"]
                   for bl in ("plain", "w", "wmc")]))
    out.append(f"\nAll tokens of the sample: {int(tt):,} in {len(pp)} projects. Projects with a plain-blame value in the mean: see the token tables.\n")
    cuts = sorted(pp, key=lambda r: -r["_cut_pct"])
    out.append(f"Projects with more than {a.cut_pct:g}% of the tokens in files without a plain line blame: {len(big_cut)}.\n")
    out.append(md(["project", "language", "draw band", "tokens", "files", "files cut", "tokens without plain blame %",
                   "tokens in files over any limit or cap %"],
                  [[r["project"], plan.get(r["project"], {}).get("language", ""), plan.get(r["project"], {}).get("band", ""),
                    f"{int(r['_tokens']):,}", r["files"], r.get("files_limit_any", ""), p2(r["_cut_pct"]), p2(r["_cut_any_pct"])]
                   for r in cuts if r["_cut_pct"] > a.cut_pct or r["_cut_any_pct"] > a.cut_pct]))
    out.append("")
    nzero = [r["project"] for r in pp if fl(r, "tok_matched") == 0]
    out.append(f"Projects with no token covered by the plain blame (no value): {len(nzero)} ({', '.join(nzero) or 'none'}).\n")
    bands = [("no cut", lambda c: c == 0), ("0 to 1%", lambda c: 0 < c <= 1), ("1 to 10%", lambda c: 1 < c <= 10),
             ("10 to 50%", lambda c: 10 < c <= 50), ("more than 50%", lambda c: c > 50)]
    out.append(md(["share of tokens without plain blame", "projects"],
                  [[n, sum(1 for r in pp if f(r["_cut_pct"]))] for n, f in bands]))
    out.append("")
    tl = {}
    for r in lim:
        tl[r["blame"]] = tl.get(r["blame"], 0) + 1
    out.append("Files over a limit (limits.tsv), by blame: " + ", ".join(f"{k} {v}" for k, v in sorted(tl.items())) +
               f". Projects with at least one file over a limit: {len(set(r['project'] for r in lim))}.\n")
    perp = {}
    for r in lim:
        perp.setdefault(r["project"], {}).setdefault(r["blame"], 0)
        perp[r["project"]][r["blame"]] += 1
    top = sorted(perp.items(), key=lambda kv: -sum(kv[1].values()))[:15]
    out.append(md(["project", "files over the plain limit", "over the -w limit", "over the -w -M -C limit", "cut at the run cap"],
                  [[p, v.get("plain", 0), v.get("w", 0), v.get("wmc", 0), v.get("cap", 0)] for p, v in top]))
    out.append("")

    # ---- other levels (project mean, all with a value; and without large cuts)
    lv = [("code lines with tokens from 2 or more authors, %", lambda r: 100 * fl(r, "mixed_author_lines") / fl(r, "code_lines")),
          ("files with the same top author (tokens against plain lines), %", lambda r: 100 * fl(r, "file_top1_same") / fl(r, "files_cmp")),
          ("files with the same top-3 author set, plain, %", lambda r: 100 * fl(r, "file_top3_same") / fl(r, "files_cmp")),
          ("files with the same top author, -w -M -C, %", lambda r: 100 * fl(r, "file_top1_same_wmc") / fl(r, "files_cmp_wmc")),
          ("project: author share TVD, plain, pp", lambda r: fl(r, "author_tvd_pp")),
          ("project: author share TVD, -w -M -C, pp", lambda r: fl(r, "author_tvd_pp_wmc")),
          ("project: author share Spearman, plain", lambda r: fl(r, "author_spearman")),
          ("project: same top author, plain, share of projects", lambda r: 100 * fl(r, "author_top_same")),
          ("project: organization share TVD, plain, pp", lambda r: fl(r, "firm_tvd_pp")),
          ("project: organization share Spearman, plain", lambda r: fl(r, "firm_spearman")),
          ("project: same top organization, share of projects", lambda r: 100 * fl(r, "firm_top_same"))]
    out.append("## Other levels (project means)\n")
    tab = []
    for name, f in lv:
        cells = [name]
        for rows_, tag in ((pp, "all"), (keep, "keep")):
            v = [f(r) for r in rows_ if fl(r, "tok_matched") > 0]
            v = [x for x in v if x == x]
            m, lo, hi, n = mean_ci(v, N)
            if "%" in name or "share of projects" in name:
                lo, hi = max(lo, 0.0), min(hi, 100.0)
            cells.append(f"{m:.2f} ({lo:.2f} to {hi:.2f}), n {n}")
            add(name, tag, n, m, lo, hi)
        tab.append(cells)
    out.append(md(["level", "all projects with a value", f"without projects with a cut above {a.cut_pct:g}%"], tab))
    out.append("")

    # ---- causes
    out.append("## Causes of tokens with another author (plain line blame)\n")
    causes = ["whitespace", "move_copy_line", "part_line", "layout", "other"]
    tot_all = sum(fl(r, "tok_author_diff") for r in pp)
    tab = []
    for c in causes:
        s = sum(fl(r, f"cause_{c}") for r in pp)
        g = sum(fl(r, f"cause_{c}_gen") for r in pp)
        tab.append([c, f"{int(s):,}", f"{100 * s / tot_all:.1f}", f"{100 * g / s:.1f}" if s else "n/a"])
    out.append(md(["cause", "tokens", "% of tokens with another author", "% of them in generated files"], tab))
    out.append("\n(The token plain blame was not run: a cause `move_copy_token` does not exist in this run; its tokens fall into the later rules.)\n")

    # ---- identity residual
    out.append("## Identity residual\n")
    ln = sum(fl(r, "lines_blamed") for r in pp)
    out.append(md(["value", "number"], [
        ["blamed lines (plain)", f"{int(ln):,}"],
        ["lines whose commit TOM does not credit", f"{int(sum(fl(r, 'lines_commit_not_in_tom') for r in pp)):,}"],
        ["of them identified by the e-mail map", f"{int(sum(fl(r, 'lines_id_email') for r in pp)):,}"],
        ["of them with no TOM identity (own id)", f"{int(sum(fl(r, 'lines_id_unmapped') for r in pp)):,} ({100 * sum(fl(r, 'lines_id_unmapped') for r in pp) / ln:.4f}%)"],
        ["largest project share of lines with no TOM identity %", f"{max(fl(r, 'pct_lines_id_unmapped') for r in pp):.3f}"],
        ["TOM-credited commits with no personid", f"{int(sum(fl0(r, 'commits_tom_null_personid') for r in pp))}"],
        ["commits whose rows have more than one personid", f"{int(sum(fl0(r, 'commits_multi_personid') for r in pp))}"],
        ["e-mail addresses with more than one personid", f"{int(sum(fl0(r, 'emails_multi_personid') for r in pp))}"],
    ]))
    out.append("")

    # ---- by language and band
    out.append("## Project mean of tokens with another author (plain), by language and draw band\n")
    for key, nm in (("language", "language"), ("band", "commit band")):
        groups = {}
        for r in pp:
            if fl(r, "tok_matched") > 0:
                groups.setdefault(plan.get(r["project"], {}).get(key, "?"), []).append(100 * fl(r, "tok_author_diff") / fl(r, "tok_matched"))
        out.append(md([nm, "projects", "mean %", "median %", "standard deviation"],
                      [[k, len(v), f"{sum(v) / len(v):.2f}", f"{statistics.median(v):.2f}",
                        f"{statistics.stdev(v):.2f}" if len(v) > 1 else "n/a"] for k, v in sorted(groups.items())]))
        out.append("")

    # ---- checks on the main value
    out.append("## Checks on the main value\n")
    val = [(r["project"], 100 * fl(r, "tok_author_diff") / fl(r, "tok_matched"), fl(r, "tok_matched"), fl(r, "tok_author_diff"))
           for r in pp if fl(r, "tok_matched") > 0]
    rng = random.Random(20261109)
    bm = sorted(sum(val[rng.randrange(len(val))][1] for _ in val) / len(val) for _ in range(10000))
    m, lo, hi, n = mean_ci([x[1] for x in val], N)
    out.append(f"- Bootstrap 95% interval of the project mean (10,000 draws): {bm[250]:.2f} to {bm[9749]:.2f}; the t interval with the finite population correction: {lo:.2f} to {hi:.2f}.")
    out.append(f"- Without the correction the half-width is {tquant(n - 1) * statistics.stdev([x[1] for x in val]) / math.sqrt(n):.2f} pp; with it {(hi - lo) / 2:.2f} pp.")
    tm = sum(x[2] for x in val)
    big = sorted(val, key=lambda x: -x[2])[:5]
    out.append(f"- The 5 projects with most blamed tokens hold {100 * sum(x[2] for x in big) / tm:.1f}% of the blamed tokens; the largest holds {100 * big[0][2] / tm:.1f}%.")
    out.append(md(["project", "blamed tokens", "share of blamed tokens %", "tokens with another author %"],
                  [[x[0], f"{int(x[2]):,}", f"{100 * x[2] / tm:.1f}", f"{x[1]:.2f}"] for x in big]))
    out.append("")
    srt = sorted(x[1] for x in val)
    out.append(f"- Quartiles of the project values: {srt[len(srt) // 4]:.2f}, {statistics.median(srt):.2f}, {srt[3 * len(srt) // 4]:.2f}; minimum {srt[0]:.2f}, maximum {srt[-1]:.2f}; standard deviation {statistics.stdev(srt):.2f} (the planning value was 16.26).")
    out.append(f"- Projects with a value above 50%: {sum(1 for x in srt if x > 50)}; below 5%: {sum(1 for x in srt if x < 5)}.")
    out.append("")

    # ---- run facts
    out.append("## Costs of the run (blame CPU)\n")
    bm = rd(T / "blame-meta.tsv")
    cpu = {k: sum(fl(r, k) for r in bm) / 3600 for k in ("plain_s", "w_s", "wmc_s")}
    out.append(md(["blame", "CPU hours"], [[k[:-2], f"{v:.1f}"] for k, v in cpu.items()]))
    out.append("")
    with open(a.out_md, "w") as f:
        f.write("\n".join(out) + "\n")
    with open(a.out_tsv, "w") as f:
        f.write("estimate\tgroup\tprojects\tproject_mean\tlow95\thigh95\tweighted\tweighted_low95\tweighted_high95\n")
        for e in est:
            f.write("\t".join(e) + "\n")


if __name__ == "__main__":
    main()
