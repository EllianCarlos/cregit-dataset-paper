"""Draw the simple random sample of the token-against-line run from the frame table.

The frame is `tables/frame.tsv`: the 8,598 projects of TOM 1.0.0 sorted by project name (columns: project,
language, band, commits, rows, pipeline_s, time_source, clone_url, run_commit). The draw is one random
permutation of the frame (Python `random.Random(20261109).shuffle`); the sample is the first N projects of the
permutation (column draw_rank), so a top-up takes the next projects of the same permutation.

    python3 -I draw_sample.py --frame tables/frame.tsv --n 250 > tables/plan-sample-random.tsv
"""
import argparse
import csv
import random

SEED = 20261109

ap = argparse.ArgumentParser()
ap.add_argument("--frame", required=True)
ap.add_argument("--n", type=int, default=250)
a = ap.parse_args()
fr = list(csv.DictReader(open(a.frame), delimiter="\t"))
fr.sort(key=lambda r: r["project"])
perm = list(fr)
random.Random(SEED).shuffle(perm)
for i, r in enumerate(perm):
    r["draw_rank"] = i + 1
pick = sorted(perm[:a.n], key=lambda r: -float(r["pipeline_s"]))
cols = ["draw_rank", "project", "language", "band", "commits", "rows", "pipeline_s", "time_source", "clone_url", "run_commit"]
print("\t".join(cols))
for r in pick:
    print("\t".join(str(r[c]) for c in cols))
