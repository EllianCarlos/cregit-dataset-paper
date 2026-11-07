"""Build the tables of RESULTS.md from the outputs of extract_linux_orgs.py and compare.py.

Usage (from the duckdb-workbench nix shell, in this folder):
    nice -n 15 python3 -I make_tables.py
Writes: our_top20.md, main_table.md, main_table.csv, correlations.md
"""
import pathlib

import numpy as np
import pandas as pd

here = pathlib.Path(__file__).resolve().parent
day = pd.read_csv(here / "linux_org_day.csv", parse_dates=["committer_day"])
names = day.drop_duplicates("organization_id").set_index("organization_id")["name"]
src = pd.read_csv(here / "source_tables.csv", dtype={"organization_ids": str}, keep_default_na=False)
win = pd.read_csv(here / "source_windows.csv", parse_dates=["start", "end"]).set_index("source")
PSEUDO = ["independent", "free-provider", "unknown", "pre-git-import"]
rng = np.random.default_rng(20261107)


def shares(rows, value="tokens"):
    s = rows.groupby("organization_id")[value].sum()
    return 100 * s / s.sum()


def window(source):
    w = win.loc[source]
    return day[(day.committer_day >= w.start) & (day.committer_day < w.end)]


def spearman_p(a, b, n_perm=20000):
    ra, rb = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    rho = np.corrcoef(ra, rb)[0, 1]
    perm = np.array([np.corrcoef(ra, rng.permutation(rb))[0, 1] for _ in range(n_perm)])
    return rho, (np.sum(np.abs(perm) >= abs(rho) - 1e-12) + 1) / (n_perm + 1)


# Our top 20, whole file and without the pre-git import.
alive = shares(day)
named = alive.drop(PSEUDO, errors="ignore").sort_values(ascending=False)
no_pregit = shares(day[day.organization_id != "pre-git-import"])
w73 = shares(window("lwn-7.3"))
lines = ["| Rank | Organization | Share of alive code tokens (%) | Without the pre-git import (%) | Alive tokens with committer date in the 7.3 window (%) |",
         "|---:|---|---:|---:|---:|"]
for i, (org, v) in enumerate(named.head(20).items(), 1):
    lines.append(f"| {i} | {names[org]} | {v:.2f} | {no_pregit.get(org, 0):.2f} | {w73.get(org, 0):.2f} |")
for org in PSEUDO:
    lines.append(f"| | {names[org]} | {alive.get(org, 0):.2f} | {no_pregit.get(org, 0):.2f} | {w73.get(org, 0):.2f} |")
nn = ["independent", "free-provider", "unknown"]
lines.append(f"| | No organization (three pseudo ids above, without pre-git) | {sum(alive.get(o, 0) for o in nn):.2f} | "
             f"{sum(no_pregit.get(o, 0) for o in nn):.2f} | {sum(w73.get(o, 0) for o in nn):.2f} |")
(here / "our_top20.md").write_text("\n".join(lines) + "\n")

# Main table: the source rows next to ours.
pairs = [
    ("lwn-7.3", "lines", "tokens", "LWN 7.3 lines changed", "Ours: alive tokens, 7.3 window"),
    ("lwn-7.3", "changesets", "commits", "LWN 7.3 changesets", "Ours: surviving commits, 7.3 window"),
    ("lwn-6.13-6.18", "lines", "tokens", "LWN 6.13-6.18 lines changed", "Ours: alive tokens, 6.13-6.18 window"),
    ("lf-2020", "commits", "commits", "LF commits 2007-2019", "Ours: surviving commits, 2007-2019"),
]
src["employer_ids"] = src.organization_ids
rows = {}
ours_by_pair = {}
ids_of = dict(zip(src.employer, src.organization_ids))
corr = ["| Source table | Our measure | n | Spearman rho (all listed) | permutation p | rho, top 10 of the source | mean abs. difference, top 10 (points) |",
        "|---|---|---:|---:|---:|---:|---:|"]
for source, table, value, slabel, olabel in pairs:
    ours = shares(window(source), value)
    t = src[(src.source == source) & (src.table == table) & (src.organization_ids != "")].copy()
    t["ours"] = [sum(ours.get(i, 0.0) for i in ids.split("+")) for ids in t.organization_ids]
    for _, r in t.iterrows():
        rows.setdefault(r.employer, {})[slabel] = r.percent
    ours_by_pair[olabel] = ours
    rho, p = spearman_p(t.percent, t.ours)
    top = t.head(10)
    corr.append(f"| {slabel} | {olabel} | {len(t)} | {rho:.2f} | {p:.4f} | {top.percent.rank().corr(top.ours.rank()):.2f} | "
                f"{(top.percent - top.ours).abs().mean():.2f} |")
    # Ours for the whole file too, the measure the dataset gives without a period.
    rho_all, p_all = spearman_p(t.percent, [sum(alive.get(i, 0.0) for i in ids.split("+")) for ids in t.organization_ids])
    corr.append(f"| {slabel} | Ours: all alive tokens (no period) | {len(t)} | {rho_all:.2f} | {p_all:.4f} | | |")
    pseudo = src[(src.source == source) & (src.table == table) & (src.organization_ids == "")]
    rows.setdefault("(No organization: Unknown, None, Consultant, Academia)", {})[slabel] = pseudo.percent.sum()
(here / "correlations.md").write_text("\n".join(corr) + "\n")

NOORG = "(No organization: Unknown, None, Consultant, Academia)"


def ours_for(series, employer):
    if employer == NOORG:
        return sum(series.get(o, 0.0) for o in nn)
    return sum(series.get(i, 0.0) for i in ids_of[employer].split("+"))


main = pd.DataFrame.from_dict(rows, orient="index")
for p in pairs:
    main[p[4]] = [ours_for(ours_by_pair[p[4]], e) for e in main.index]
main["Ours: all alive tokens"] = [ours_for(alive, e) for e in main.index]
cols = ["Ours: all alive tokens"] + [c for p in pairs for c in (p[3], p[4])]
main = main[cols]
main = main.sort_values(cols[0], ascending=False)
pseudo_row = main.loc[[NOORG]]
main = pd.concat([main.drop(pseudo_row.index), pseudo_row])
main.to_csv(here / "main_table.csv", float_format="%.2f")
md = ["| Employer | " + " | ".join(main.columns) + " |", "|---|" + "---:|" * len(main.columns)]
for e, r in main.iterrows():
    md.append(f"| {e} | " + " | ".join("n.l." if pd.isna(v) else f"{v:.1f}" for v in r) + " |")
(here / "main_table.md").write_text("\n".join(md) + "\n")
print((here / "our_top20.md").read_text(), (here / "correlations.md").read_text(), (here / "main_table.md").read_text(), sep="\n")
