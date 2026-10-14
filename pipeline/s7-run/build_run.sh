#!/usr/bin/env bash
# S7 (2026-10-06): split ../s4-filter/frame.csv into the five run layers (DP7,
# largest first) and build one manifest for each layer with build_manifest.py
# from cregit-token-pipeline. Inside a layer the manifest is in u order.
# batch1 = the first 5% of layer 1 (>= 5,000 commits), rounded up.
set -euo pipefail
cd "$(dirname "$0")"
# CREGIT_PROJECTS: the directory that holds cregit-workspace and the clones of ctp and cregit.
# Default: the nearest parent directory of this script that holds cregit-workspace.
if [ -z "${CREGIT_PROJECTS:-}" ]; then
  CREGIT_PROJECTS=$(pwd)
  while [ "$CREGIT_PROJECTS" != / ] && [ ! -d "$CREGIT_PROJECTS/cregit-workspace" ]; do
    CREGIT_PROJECTS=$(dirname "$CREGIT_PROJECTS")
  done
fi
CTP=${CTP:-$CREGIT_PROJECTS/cregit-token-pipeline/.claude/worktrees/agent-a0a3254f563a6a4b5}
# batch6..batch20 (2026-10-09): `bash build_run.sh batch N` builds batch N alone and exits. It takes
# rows (N-1)*limit+1 .. N*limit of frame.layer1.csv (batch 20 gets the 149 left), builds the
# manifest and sidecar with build_manifest.py, then enrich_meta.py --in-place fills license,
# owner_type, archived and fork from ../s2-pool/pool.csv (frame.csv has no such columns, so the
# sidecar would leave them blank in the Parquet), and source from the pool.csv column origins
# (since 2026-10-09 20:15 UTC, so from batch 7 on; batch 6 was built before and has source ''),
# and appends the sha256 of the 4 new files to SHA256SUMS. It refuses to overwrite a file. A
# split script that copies records from project_meta.batchN.json passes the 5 values on to the parts. Without arguments the script
# rebuilds layers and batches 1-5 as below; note that its last line rewrites SHA256SUMS.
# batch21 (2026-10-10, the DP8L supplement): `bash build_run.sh supplement N SRC.csv LICENSES.csv` builds the
# supplement batch N (N >= 21) from the layer 1 rows of SRC.csv (frame.csv columns, u order;
# ../s4-filter/supplement.v3.csv), with the same tools as batches 7-20: build_manifest.py, then enrich_meta.py
# --in-place --frame frame.batchN.csv --license-values LICENSES.csv (the license values of the rows whose pool
# license is blank, ../s4-filter/dp8l-audit/licenses.csv), and appends the sha256 of the 4 new files to SHA256SUMS.
# It refuses to overwrite a file. Then split_batchN.py N makes the L list and the parts, as for batches 6-20.
# POOL=FILE (batch 22, 2026-10-10): enrich_meta.py reads that pool file instead of ../s2-pool/pool.csv, for
# rows that are in a pool supplement (../s2-pool/v2/pool.supplement.csv, the GNU roster v2).
if [[ ${1:-} == supplement ]]; then
  n=${2:-}; src=${3:-}; lic=${4:-}
  if ! [[ $n =~ ^[0-9]+$ ]] || (( n < 21 )) || [[ ! -f $src || ! -f $lic ]]; then
    echo "usage: build_run.sh supplement N SRC.csv LICENSES.csv, with N >= 21 and both files present" >&2
    exit 2
  fi
  out=(frame.batch$n.csv manifest.batch$n.tsv manifest.batch$n.order.tsv project_meta.batch$n.json)
  for f in "${out[@]}"; do
    if [[ -e $f ]]; then echo "FAIL $f exists" >&2; exit 1; fi
  done
  python3 - "$src" "$n" <<'P'
import csv, sys
src, n = sys.argv[1], int(sys.argv[2])
rows = [r for r in csv.DictReader(open(src, encoding="utf-8")) if r["layer"] == "≥ 5,000"]
assert rows and all(float(rows[i]["u"]) <= float(rows[i + 1]["u"]) for i in range(len(rows) - 1)), "not in u order"
with open(f"frame.batch{n}.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
print(f"frame.batch{n}.csv: {len(rows)} layer 1 rows of {src}")
P
  python3 "$CTP/build_manifest.py" "frame.batch$n.csv" --manifest "manifest.batch$n.tsv" \
      --project-meta "project_meta.batch$n.json"
  python3 enrich_meta.py "project_meta.batch$n.json" --in-place --frame "frame.batch$n.csv" --license-values "$lic" \
      ${POOL:+--pool "$POOL"}
  sha256sum "${out[@]}" >> SHA256SUMS
  exit 0
fi
if [[ ${1:-} == batch ]]; then
  n=${2:-}
  if ! [[ $n =~ ^[0-9]+$ ]] || (( n < 6 || n > 20 )); then
    echo "usage: build_run.sh batch N, with N in 6..20" >&2
    exit 2
  fi
  out=(frame.batch$n.csv manifest.batch$n.tsv manifest.batch$n.order.tsv project_meta.batch$n.json)
  for f in "${out[@]}"; do
    if [[ -e $f ]]; then echo "FAIL $f exists" >&2; exit 1; fi
  done
  total=$(($(wc -l < frame.layer1.csv) - 1))
  limit=$(( (total * 5 + 99) / 100 ))
  python3 - "$limit" "$n" <<'P'
import csv, sys
limit, n = int(sys.argv[1]), int(sys.argv[2])
rows = list(csv.DictReader(open("frame.layer1.csv", encoding="utf-8")))
with open(f"frame.batch{n}.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
    w.writeheader()
    w.writerows(rows[(n - 1) * limit:n * limit])
P
  python3 "$CTP/build_manifest.py" "frame.batch$n.csv" --manifest "manifest.batch$n.tsv" \
      --project-meta "project_meta.batch$n.json"
  python3 enrich_meta.py "project_meta.batch$n.json" --in-place
  sha256sum "${out[@]}" >> SHA256SUMS
  exit 0
fi
python3 - <<'P'
import csv
names = {"≥ 5,000": "layer1", "1,000–4,999": "layer2", "500–999": "layer3", "100–499": "layer4", "< 100": "layer5"}
rows = list(csv.DictReader(open("../s4-filter/frame.csv", encoding="utf-8")))
for layer, name in names.items():
    with open(f"frame.{name}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
        w.writeheader()
        w.writerows(r for r in rows if r["layer"] == layer)
P
for n in 1 2 3 4 5; do
  python3 "$CTP/build_manifest.py" frame.layer$n.csv --manifest manifest.layer$n.tsv \
      --project-meta project_meta.layer$n.json
done
total=$(($(wc -l < frame.layer1.csv) - 1))
limit=$(( (total * 5 + 99) / 100 ))
python3 "$CTP/build_manifest.py" frame.layer1.csv --manifest manifest.batch1.tsv \
    --project-meta project_meta.batch1.json --limit "$limit"
sha256sum ../s4-filter/frame.csv frame.layer*.csv manifest.*.tsv project_meta.*.json > SHA256SUMS
# batch2 (2026-10-09) = the next 5% of layer 1 (frame.layer1.csv rows limit+1 .. 2*limit),
# for the EC2 run in the AWS account of the dataset build (m6id.24xlarge, us-west-2).
python3 - "$limit" <<'P'
import csv, sys
limit = int(sys.argv[1])
rows = list(csv.DictReader(open("frame.layer1.csv", encoding="utf-8")))
with open("frame.batch2.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
    w.writeheader()
    w.writerows(rows[limit:2 * limit])
P
python3 "$CTP/build_manifest.py" frame.batch2.csv --manifest manifest.batch2.tsv \
    --project-meta project_meta.batch2.json
# batch3 (2026-10-09) = the next 5% of layer 1 (rows 2*limit+1 .. 3*limit). split_batch3.py
# splits it into batch3L (the L projects, on the batch 2 on-demand instance) and batch3a /
# batch3b (the S and M projects by alternate rows in u order, on two EC2 spot instances).
python3 - "$limit" <<'P'
import csv, sys
limit = int(sys.argv[1])
rows = list(csv.DictReader(open("frame.layer1.csv", encoding="utf-8")))
with open("frame.batch3.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
    w.writeheader()
    w.writerows(rows[2 * limit:3 * limit])
P
python3 "$CTP/build_manifest.py" frame.batch3.csv --manifest manifest.batch3.tsv \
    --project-meta project_meta.batch3.json
python3 split_batch3.py
# batch4 (2026-10-09) = the next 5% of layer 1 (rows 3*limit+1 .. 4*limit), all S+M+L, on the
# batch 2 on-demand instance next to batch 2 and batch 3L. split_batch4.py splits it into 3
# census parts batch4p1..p3 by alternate rows in u order, one per loop-mounted XFS filesystem.
python3 - "$limit" <<'P'
import csv, sys
limit = int(sys.argv[1])
rows = list(csv.DictReader(open("frame.layer1.csv", encoding="utf-8")))
with open("frame.batch4.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
    w.writeheader()
    w.writerows(rows[3 * limit:4 * limit])
P
python3 "$CTP/build_manifest.py" frame.batch4.csv --manifest manifest.batch4.tsv \
    --project-meta project_meta.batch4.json
python3 split_batch4.py
# batch5 (2026-10-09) = the next 5% of layer 1 (rows 4*limit+1 .. 5*limit), on the tails of the two
# batch 3 spot instances (S and M) and the batch 2 on-demand instance (L). split_batch5.py also
# builds batch1rest (the batch 1 projects that did not finish locally, without the two that
# finish there) and splits both into the spot parts and the L census.
python3 - "$limit" <<'P'
import csv, sys
limit = int(sys.argv[1])
rows = list(csv.DictReader(open("frame.layer1.csv", encoding="utf-8")))
with open("frame.batch5.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, rows[0].keys(), lineterminator="\n")
    w.writeheader()
    w.writerows(rows[4 * limit:5 * limit])
P
python3 "$CTP/build_manifest.py" frame.batch5.csv --manifest manifest.batch5.tsv \
    --project-meta project_meta.batch5.json
python3 split_batch5.py
sha256sum ../s4-filter/frame.csv frame.layer*.csv frame.batch2.csv frame.batch3.csv frame.batch4.csv frame.batch5.csv manifest.*.tsv project_meta.*.json > SHA256SUMS
