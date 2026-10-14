#!/usr/bin/env bash
# The user runs this (Claude's S3 uploads are denied). Uploads the inputs of batches 7-20 and the
# cregit bundle of 1f17663 (one trailer entry per person), then reads every object back and checks it.
set -uo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
U=$HOME/s3-work/ec2-batch6/upload-cregit
for n in $(seq 7 20); do
  aws s3 cp ~/s3-work/ec2-batch$n/upload/ $B/batch$n/input/ --recursive --only-show-errors || { echo "FAIL batch$n"; exit 1; }
done
aws s3 cp $U/cregit-1f17663.bundle $B/cregit/cregit-1f17663.bundle --only-show-errors || { echo "FAIL bundle"; exit 1; }
aws s3 cp $U/SHA256SUMS.1f17663 $B/cregit/SHA256SUMS.1f17663 --only-show-errors || { echo "FAIL bundle sums"; exit 1; }
bad=0
for n in $(seq 7 20); do
  d=$(mktemp -d); aws s3 cp $B/batch$n/input/ $d/ --recursive --only-show-errors
  if (cd $d && [ "$(ls | wc -l)" -eq 8 ] && sha256sum --quiet -c SHA256SUMS); then echo "batch$n: 8 objects, read-back ok"; else echo "batch$n: CHECK FAILED"; bad=1; fi
  rm -rf "$d"
done
d=$(mktemp -d); aws s3 cp $B/cregit/cregit-1f17663.bundle $d/ --only-show-errors
(cd $d && grep cregit-1f17663.bundle $U/SHA256SUMS.1f17663 | sha256sum --quiet -c -) && echo "bundle 1f17663: read-back ok" || { echo "bundle: CHECK FAILED"; bad=1; }
rm -rf "$d"
[ $bad = 0 ] && echo "ALL OK" || echo "SOME CHECKS FAILED"
