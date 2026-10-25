#!/usr/bin/env bash
# U1-upload-pathfix.sh (this machine, run by the user: Claude's S3 uploads are denied).
# Run it after S1-stage-cregit.sh (and, for the inputs, after S2-stage-inputs.sh).
#   1. the cregit bundle of the path-quoting fix: stage/cregit-<sha7>.bundle and
#      stage/SHA256SUMS.<sha7> -> s3://B/cregit/ (next to cregit-57551d7.bundle). New keys only:
#      the script stops if a key exists already.
#   2. if stage/inputs/ exists: the rerun inputs (manifest, seeds, parts, sidecars.tsv, SHA256SUMS)
#      and the v1 sidecar (as it is, from its own path) -> s3://B/dataset-x1k/inputs-pathfix/
#      (a new prefix; nothing else is touched).
#   3. reads every object back into a new folder check/<time>/ and compares the sha256.
# The inputs hold project names, URLs and commits; the sidecar holds licenses and pool facts: no e-mail address.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
H=$HOME/s3-work/dataset-pathfix
cd "$H/stage"
n=$(find . -maxdepth 1 -name 'cregit-*.bundle' | wc -l)
[ "$n" = 1 ] || { echo "ABORT: want 1 cregit bundle in $H/stage, found $n"; exit 1; }
BF=$(basename "$(find . -maxdepth 1 -name 'cregit-*.bundle')")
S7=${BF#cregit-}; S7=${S7%.bundle}
SUMS=SHA256SUMS.$S7
sha256sum --quiet -c "$SUMS" || { echo "ABORT: $SUMS does not match $BF"; exit 1; }
for k in "$BF" "$SUMS"; do
  if aws s3 ls "$B/cregit/$k" >/dev/null 2>&1; then echo "ABORT: $B/cregit/$k exists already"; exit 1; fi
done
aws s3 cp --only-show-errors "$BF" "$B/cregit/$BF"
aws s3 cp --only-show-errors "$SUMS" "$B/cregit/$SUMS"
echo "uploaded $BF and $SUMS to $B/cregit/"
if [ -d inputs ]; then
  (cd inputs && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: stage/inputs/SHA256SUMS"; exit 1; }
  if [ -n "$(aws s3 ls "$B/dataset-x1k/inputs-pathfix/" 2>/dev/null)" ]; then
    echo "ABORT: $B/dataset-x1k/inputs-pathfix/ is not empty"; exit 1; fi
  aws s3 cp --recursive --only-show-errors inputs/ "$B/dataset-x1k/inputs-pathfix/"
  echo "uploaded $(wc -l < inputs/SHA256SUMS) input files to $B/dataset-x1k/inputs-pathfix/"
  # The v1 sidecar as it is (from its own path; sha256 of sidecars.tsv). The x1k sidecar is in
  # dataset-x1k/inputs/ already (sha256 4ae4ad9f..., the B run).
  awk -F'\t' 'NR>1 && $2=="project_meta.v1.final.json" {print $3"\t"$4}' inputs/sidecars.tsv | sort -u | \
  while IFS=$'\t' read -r sha path; do
    [ "$(sha256sum "$path" | cut -d' ' -f1)" = "$sha" ] || { echo "ABORT: $path is not $sha"; exit 1; }
    aws s3 cp --only-show-errors "$path" "$B/dataset-x1k/inputs-pathfix/sidecar/project_meta.v1.final.json"
    echo "uploaded the v1 sidecar ($sha)"
  done
fi
C=$H/check/$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$C/cregit"
aws s3 cp --only-show-errors "$B/cregit/$BF" "$C/cregit/"
aws s3 cp --only-show-errors "$B/cregit/$SUMS" "$C/cregit/"
ok=1
(cd "$C/cregit" && cmp -s "$SUMS" "$H/stage/$SUMS" && sha256sum --quiet -c "$SUMS") \
  && echo "bundle $BF: read-back ok" || { echo "bundle $BF: CHECK FAILED"; ok=0; }
if [ -d inputs ]; then
  mkdir -p "$C/inputs"
  aws s3 cp --recursive --only-show-errors "$B/dataset-x1k/inputs-pathfix/" "$C/inputs/"
  (cd "$C/inputs" && cmp -s SHA256SUMS "$H/stage/inputs/SHA256SUMS" && sha256sum --quiet -c SHA256SUMS) \
    && echo "inputs: read-back ok" || { echo "inputs: CHECK FAILED"; ok=0; }
  want=$(awk -F'\t' 'NR>1 && $2=="project_meta.v1.final.json" {print $3; exit}' inputs/sidecars.tsv)
  [ "$(sha256sum "$C/inputs/sidecar/project_meta.v1.final.json" | cut -d' ' -f1)" = "$want" ] \
    && echo "v1 sidecar: read-back ok" || { echo "v1 sidecar: CHECK FAILED"; ok=0; }
fi
[ $ok = 1 ] && echo "ALL OK: $BF ($(cut -d' ' -f1 "$SUMS"))" || { echo "SOME CHECKS FAILED"; exit 1; }
