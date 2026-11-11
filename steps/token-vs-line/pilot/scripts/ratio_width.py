"""Expected 95% half-width of the token-weighted ratio and of the project mean
for the drawn sample, by simulation: each drawn project gets a value drawn from
the 19 local project values (with replacement); its weight is its TOM row count.
Also the bootstrap interval of the ratio on the 19 local projects.

    python3 -I ratio_width.py
"""
import csv
import random
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
pp = list(csv.DictReader(open(HERE / "tables" / "per-project.tsv"), delimiter="\t"))
v = [100 * float(r["tok_author_diff"]) / float(r["tok_matched"]) for r in pp]
w19 = [float(r["tok_matched"]) for r in pp]
d19 = [float(r["tok_author_diff"]) for r in pp]
rng = random.Random(20261109)
bs = []
for _ in range(10000):
    idx = [rng.randrange(len(pp)) for _ in pp]
    bs.append(100 * sum(d19[i] for i in idx) / sum(w19[i] for i in idx))
bs.sort()
print(f"19 local projects: ratio {100 * sum(d19) / sum(w19):.1f}%, bootstrap 95% {bs[249]:.1f} to {bs[9749]:.1f}")
draw = list(csv.DictReader(open(HERE / "tables" / "plan-sample-random.tsv"), delimiter="\t"))
rows = [int(r["rows"]) for r in draw]
med = st.median([x for x in rows if x > 0])
rows = [x if x > 0 else med for x in rows]
ratios, means = [], []
for _ in range(5000):
    val = [rng.choice(v) for _ in rows]
    ratios.append(sum(a * b for a, b in zip(val, rows)) / sum(rows))
    means.append(st.mean(val))
print(f"drawn n={len(rows)}: simulated 95% half-width: project mean {1.96 * st.stdev(means):.2f} pp, "
      f"token-weighted ratio {1.96 * st.stdev(ratios):.2f} pp")
top = sorted(rows, reverse=True)
print(f"largest project holds {100 * top[0] / sum(rows):.1f}% of the drawn rows; 5 largest {100 * sum(top[:5]) / sum(rows):.1f}%")
