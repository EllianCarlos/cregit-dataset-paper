"""Bootstrap (over projects, 10,000 draws, seed 20261109) 95% intervals for the
project mean and median of the main values.

    python3 -I bootstrap.py > ../tables/bootstrap.tsv
"""
import csv
import random
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
rows = list(csv.DictReader(open(HERE / "tables" / "per-project.tsv"), delimiter="\t"))
f = lambda r, k: float(r[k])  # noqa: E731
vals = {
    "token author diff, line plain %": [100 * f(r, "tok_author_diff") / f(r, "tok_matched") for r in rows],
    "token author diff, line -w -M -C %": [100 * f(r, "tok_author_diff_wmc") / f(r, "tok_matched") for r in rows],
    "token commit diff, line plain %": [100 * f(r, "tok_commit_diff") / f(r, "tok_matched") for r in rows],
    "token organization diff, line plain %": [100 * f(r, "tok_firm_diff") / f(r, "tok_matched") for r in rows],
    "file top-1 author same %": [100 * f(r, "file_top1_same") / f(r, "files_cmp") for r in rows],
    "project author TVD pp": [f(r, "author_tvd_pp") for r in rows],
    "project organization TVD pp": [f(r, "firm_tvd_pp") for r in rows],
    "project author Spearman": [f(r, "author_spearman") for r in rows],
}
rng = random.Random(20261109)
print("value\tprojects\tmean\tmean_lo\tmean_hi\tmedian\tmedian_lo\tmedian_hi")
for k, v in vals.items():
    ms, md = [], []
    for _ in range(10000):
        s = [rng.choice(v) for _ in v]
        ms.append(st.mean(s))
        md.append(st.median(s))
    ms.sort()
    md.sort()
    print(f"{k}\t{len(v)}\t{st.mean(v):.2f}\t{ms[249]:.2f}\t{ms[9749]:.2f}\t{st.median(v):.2f}\t{md[249]:.2f}\t{md[9749]:.2f}")
