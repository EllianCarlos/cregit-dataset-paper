#!/usr/bin/env bash
# The user runs this (Claude's S3 uploads are denied). Uploads the cregit bundles of the blame time
# limit: 57551d7 (on 1f17663, batches 7-22, L7-20, L22) and 9ccead6 (on 95cdc88, batches 1-6, batch5L),
# with their SHA256SUMS, then reads every object back and checks it.
set -uo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
U=$HOME/s3-work/upload-cregit-blamelimit
for c in 57551d7 9ccead6; do
  aws s3 cp $U/cregit-$c.bundle $B/cregit/cregit-$c.bundle --only-show-errors || { echo "FAIL bundle $c"; exit 1; }
  aws s3 cp $U/SHA256SUMS.$c $B/cregit/SHA256SUMS.$c --only-show-errors || { echo "FAIL bundle sums $c"; exit 1; }
done
bad=0
for c in 57551d7 9ccead6; do
  d=$(mktemp -d); aws s3 cp $B/cregit/cregit-$c.bundle $d/ --only-show-errors; aws s3 cp $B/cregit/SHA256SUMS.$c $d/ --only-show-errors
  (cd $d && cmp -s SHA256SUMS.$c $U/SHA256SUMS.$c && sha256sum --quiet -c SHA256SUMS.$c) && echo "bundle $c: read-back ok" || { echo "bundle $c: CHECK FAILED"; bad=1; }
  rm -rf "$d"
done
[ $bad = 0 ] && echo "ALL OK" || echo "SOME CHECKS FAILED"
