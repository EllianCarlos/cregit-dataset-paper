"""Compare the organization shares of the Linux kernel file with public employer tables.

Usage (from the duckdb-workbench nix shell, in this folder):
    nice -n 15 python3 -I compare.py

Inputs (all organization level, in this folder):
    linux_org_day.csv      from extract_linux_orgs.py
    source_tables.csv      the published employer tables, typed from the sources
                           columns: source, table, employer, organization_ids, value, percent
                           organization_ids: our ids, joined with '+', empty for pseudo rows
    source_windows.csv     columns: source, start, end (committer days, start inclusive, end exclusive)
Outputs:
    comparison_<source>__<table>.csv and comparison_summary.csv
"""
import pathlib

import pandas as pd

here = pathlib.Path(__file__).resolve().parent
day = pd.read_csv(here / "linux_org_day.csv", parse_dates=["committer_day"])
src = pd.read_csv(here / "source_tables.csv", dtype={"organization_ids": str}, keep_default_na=False)
win = pd.read_csv(here / "source_windows.csv", parse_dates=["start", "end"])

PSEUDO = {"independent", "free-provider", "unknown", "pre-git-import", "kernel-org-address"}
day["organization_id_kernel_org_apart"] = day.organization_id.where(~day.kernel_org_address, "kernel-org-address")


def our_shares(rows: pd.DataFrame, value: str = "tokens", org: str = "organization_id") -> pd.Series:
    by_org = rows.groupby(org)[value].sum()
    return 100 * by_org / by_org.sum()


def spearman(a: pd.Series, b: pd.Series) -> float:
    return a.rank().corr(b.rank())


summary = []
for (source, table), t in src.groupby(["source", "table"], sort=False):
    w = win[win.source == source].iloc[0]
    in_window = day[(day.committer_day >= w.start) & (day.committer_day < w.end)]
    no_pregit = day[day.organization_id != "pre-git-import"]
    scopes = {
        "tokens_all": (day, "tokens"),
        "tokens_all_kernel_org_apart": (day, "tokens", "organization_id_kernel_org_apart"),
        "tokens_all_no_pregit": (no_pregit, "tokens"),
        "tokens_all_no_pregit_no_amd_headers": (no_pregit[~no_pregit.amd_register_header], "tokens"),
        "tokens_in_window": (in_window, "tokens"),
        "tokens_in_window_no_amd_headers": (in_window[~in_window.amd_register_header], "tokens"),
        "tokens_in_window_kernel_org_apart": (in_window, "tokens", "organization_id_kernel_org_apart"),
        "commits_in_window": (in_window, "commits"),
        "commits_in_window_kernel_org_apart": (in_window, "commits", "organization_id_kernel_org_apart"),
    }
    shares = {k: our_shares(*v) for k, v in scopes.items()}
    named = t[t.organization_ids != ""].copy()
    for k, s in shares.items():
        named[k] = [sum(s.get(i, 0.0) for i in ids.split("+")) for ids in named.organization_ids]
        named[k + "_rank"] = named[k].rank(ascending=False, method="min").astype(int)
    named["source_rank"] = named["percent"].rank(ascending=False, method="min").astype(int)
    named.to_csv(here / f"comparison_{source}__{table}.csv", index=False, float_format="%.3f")
    for k in shares:
        top10 = named.nsmallest(10, "source_rank")
        summary.append({
            "source": source, "table": table, "our_scope": k,
            "n_employers": len(named),
            "spearman_all_listed": round(spearman(named["percent"], named[k]), 3),
            "spearman_top10": round(spearman(top10["percent"], top10[k]), 3),
            "mean_abs_diff_top10_points": round((top10["percent"] - top10[k]).abs().mean(), 2),
            "sum_listed_source_pct": round(named["percent"].sum(), 1),
            "sum_listed_our_pct": round(named[k].sum(), 1),
            "our_no_org_pct": round(sum(shares[k].get(i, 0.0) for i in PSEUDO - {"pre-git-import"}), 1),
            "our_total": int(scopes[k][0][scopes[k][1]].sum()),
            "our_kernel_org_pct": round(shares[k].get("kernel-org-address", 0.0), 1),
        })

pd.DataFrame(summary).to_csv(here / "comparison_summary.csv", index=False)
print(pd.DataFrame(summary).to_string(index=False))
