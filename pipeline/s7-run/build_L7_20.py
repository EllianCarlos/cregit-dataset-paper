#!/usr/bin/env python3
"""Build the combined L census L7-20: the L projects of batches 7-20 in one queue (2026-10-10).

User decision (~23:50 UTC 2026-10-09): the 55 L projects of batches 7-20 run as ONE census on the big
on-demand EC2 with 6 workers, longest predicted first (LPT). ctp census runs a manifest in its row
order, so the manifest is written in that order.

  build_L7_20.py        writes manifest.L7-20.tsv (the rows of manifest.batch7L.tsv .. manifest.batch20L.tsv,
                   longest predicted first; ties by name) and project_meta.L7-20.json (the records of
                   project_meta.batch7L.json .. batch20L.json, copied unchanged, so the enriched license /
                   owner_type / archived / fork values are kept). Refuses to overwrite.
  build_L7_20.py --v2   (2026-10-10 ~02:50 UTC, coordinator: batch 21's one L project NetBSD__pkgsrc joins
                   the queue while L7-20 has not started) the same over batches 7-21, with frame.batch21.csv
                   for the batch 21 rows that are not in frame.layer1.csv; writes manifest.L7-20.v2.tsv and
                   project_meta.L7-20.v2.json. They are staged and uploaded as manifest.L7-20.tsv and
                   project_meta.L7-20.json (the names the census reads); the v1 files stay as they are.

Predicted time in seconds: exp(-5.846 + 0.5957 ln(commits) + 0.4389 ln(tok_bytes)) from frame.layer1.csv,
the fit of split_batch5.py (354 finished EC2 projects, R^2 0.73); the predictions are inferred and weak
for L projects.
"""
import csv
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIT = (-5.846, 0.5957, 0.4389)


def main(v2: bool) -> None:
    BATCHES = range(7, 22 if v2 else 21)
    sfx = ".v2" if v2 else ""
    out_m, out_p = HERE / f"manifest.L7-20{sfx}.tsv", HERE / f"project_meta.L7-20{sfx}.json"
    for f in (out_m, out_p):
        assert not f.exists(), f"{f.name} exists"
    frame = {}
    for fn in ["frame.layer1.csv"] + (["frame.batch21.csv"] if v2 else []):
        for r in csv.DictReader(open(HERE / fn, encoding="utf-8")):
            k = r["repo_url"].rstrip("/").removesuffix(".git")
            assert frame.get(k, r) == r, (fn, k)
            frame[k] = r
    cols, rows, meta, src = None, [], {}, []
    for n in BATCHES:
        m = HERE / f"manifest.batch{n}L.tsv"
        lines = m.read_text(encoding="utf-8").splitlines()
        c = next(line for line in lines if line.startswith("# Columns:"))
        assert cols in (None, c), m
        cols = c
        r = [line for line in lines if line.strip() and not line.startswith("#")]
        assert all(line.split("\t")[4] == "L" for line in r), m
        rows += [(n, line) for line in r]
        meta.update(json.loads((HERE / f"project_meta.batch{n}L.json").read_text(encoding="utf-8")))
        src.append(f"{m.name} {hashlib.sha256(m.read_bytes()).hexdigest()[:16]}")

    def pred(line: str) -> float:
        f = frame[line.split("\t")[1].rstrip("/").removesuffix(".git")]
        return math.exp(FIT[0] + FIT[1] * math.log(int(f["commits"]))
                        + FIT[2] * math.log(max(int(f["tok_bytes"] or 1), 1)))

    names = [line.split("\t")[0] for _, line in rows]
    assert len(names) == len(set(names)) and set(names) == set(meta), "names and sidecar keys differ"
    order = sorted(rows, key=lambda t: (-pred(t[1]), t[1].split("\t")[0]))
    total = sum(pred(line) for _, line in order) / 3600
    out_m.write_text(
        f"# The L projects of batches 7-{BATCHES[-1]} (manifest.batch7L.tsv .. manifest.batch{BATCHES[-1]}L.tsv) for the census L7-20 on\n"
        "# the big on-demand EC2: 6 workers, longest predicted first (LPT; ctp census runs rows in this order).\n"
        f"# {len(order)} projects, {total:.0f} h predicted in total (inferred). Sources (sha256, first 16 hex):\n"
        + "".join(f"#   {s}\n" for s in src)
        + "# Predicted hours, batch, name, in row order:\n"
        + "".join(f"#   {pred(line) / 3600:6.1f}  batch{n}  {line.split(chr(9))[0]}\n" for n, line in order)
        + f"{cols}\n" + "".join(line + "\n" for _, line in order), encoding="utf-8")
    out_p.write_text(json.dumps({line.split("\t")[0]: meta[line.split("\t")[0]] for _, line in order},
                                indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    # LPT on 6 workers, as a rough end estimate (inferred)
    w = [0.0] * 6
    for _, line in order:
        i = min(range(6), key=lambda k: w[k])
        w[i] += pred(line) / 3600
    print(f"L7-20: {len(order)} projects, {total:.0f} h predicted; LPT on 6 workers: makespan {max(w):.0f} h "
          f"(workers {', '.join(f'{x:.0f}' for x in sorted(w, reverse=True))} h); first: "
          + ", ".join(f"{line.split(chr(9))[0]} {pred(line) / 3600:.1f}" for _, line in order[:3]))


if __name__ == "__main__":
    import sys
    main("--v2" in sys.argv[1:])
