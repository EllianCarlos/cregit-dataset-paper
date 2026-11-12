#!/usr/bin/env bash
# check-stage-hashes.sh: check the copied stage outputs against the sha256 that each stage
# recorded when it ran.
#
# Usage: scripts/check-stage-hashes.sh
# - S1-S4: the recorded value is the sha256 of the uncompressed file. The repository holds
#   the .xz file, so the script decompresses it to a pipe and compares.
# - S7: pipeline/s7-run/SHA256SUMS lists the frames, the sidecars, the manifests and the parts
#   of every batch. Its row for ../s4-filter/frame.csv is checked through frame.csv.xz above.
set -euo pipefail

source "$(dirname "$0")/left-out.sh"
cd "$(dirname "$0")/../pipeline"
fail=0
# compressed file : checksum file : name in the checksum file (empty = the only row)
for spec in \
  "s1-search/repos.jsonl.xz:s1-search/repos.jsonl.sha256:" \
  "sources/company-orgs/repos.jsonl.xz:sources/company-orgs/repos.jsonl.sha256:" \
  "s2-pool/resolve.jsonl.xz:s2-pool/checksums.sha256:resolve.jsonl" \
  "s2-pool/pool.csv.xz:s2-pool/checksums.sha256:pool.csv" \
  "s3-measure/trees.jsonl.xz:s3-measure/trees.jsonl.sha256:" \
  "s3-measure/commits.jsonl.xz:s3-measure/commits.jsonl.sha256:" \
  "s3-measure/clones.jsonl.xz:s3-measure/clones.jsonl.sha256:" \
  "s3-measure/clone_facts.jsonl.xz:s3-measure/clone_facts.jsonl.sha256:" \
  "s4-filter/frame.csv.xz:s4-filter/frame.csv.sha256:"; do
  IFS=: read -r xzf sums name <<< "$spec"
  if [ ! -f "$xzf" ] && left_out "pipeline/$xzf"; then echo "SKIP $xzf (not in the Zenodo zip; it is in the GitHub repository)"; continue; fi
  got=$(xz -dc "$xzf" | sha256sum | cut -c1-64)
  if [ -n "$name" ]; then want=$(awk -v n="$name" '$2 == n { print $1 }' "$sums"); else want=$(cut -c1-64 "$sums"); fi
  if [ "$got" = "$want" ]; then echo "OK   $xzf"; else echo "FAIL $xzf (sha256 $got, want $want)"; fail=1; fi
done
# S4: frame.csv appears in s7-run/SHA256SUMS too; the value must be the same.
want=$(awk '$2 == "../s4-filter/frame.csv" { print $1 }' s7-run/SHA256SUMS)
[ "$want" = "$(cut -c1-64 s4-filter/frame.csv.sha256)" ] || { echo "FAIL s7-run/SHA256SUMS and s4-filter/frame.csv.sha256 differ"; fail=1; }
# S7.
n=$(grep -v -c -E '  \.\./' s7-run/SHA256SUMS)
if (cd s7-run && grep -v -E '  \.\./' SHA256SUMS | sha256sum --check --quiet --strict -); then
  echo "OK   s7-run/SHA256SUMS ($n files)"
else
  echo "FAIL s7-run/SHA256SUMS"; fail=1
fi
[ "$fail" -eq 0 ] && echo "OK: the stage outputs match their recorded sha256"
exit "$fail"
