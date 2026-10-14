#!/usr/bin/env bash
# The user runs this (Claude's S3 uploads are denied). Uploads the 8 input files of batch 23 (the DP8L v4
# near-miss supplement, 2026-10-11, with the batch23L files), then reads every object back and checks the
# sha256 of each. The cregit bundle 57551d7 is already in B/cregit/ (upload-cregit-blamelimit.sh, 20:05 UTC);
# this script reads it back and checks it too.
set -uo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
U=$HOME/s3-work/ec2-batch23/upload
C=$HOME/s3-work/upload-cregit-blamelimit
(cd $U && [ "$(command ls | wc -l)" -eq 8 ] && sha256sum --quiet -c SHA256SUMS) || { echo "FAIL local files"; exit 1; }
aws s3 cp $U/ $B/batch23/input/ --recursive --only-show-errors || { echo "FAIL upload"; exit 1; }
bad=0
d=$(mktemp -d); aws s3 cp $B/batch23/input/ $d/ --recursive --only-show-errors
if (cd $d && [ "$(command ls | wc -l)" -eq 8 ] && sha256sum --quiet -c SHA256SUMS); then echo "batch23: 8 objects, read-back ok"; else echo "batch23: CHECK FAILED"; bad=1; fi
rm -rf "$d"
d=$(mktemp -d); aws s3 cp $B/cregit/cregit-57551d7.bundle $d/ --only-show-errors; aws s3 cp $B/cregit/SHA256SUMS.57551d7 $d/ --only-show-errors
(cd $d && cmp -s SHA256SUMS.57551d7 $C/SHA256SUMS.57551d7 && sha256sum --quiet -c SHA256SUMS.57551d7) && echo "bundle 57551d7: read-back ok" || { echo "bundle 57551d7: CHECK FAILED"; bad=1; }
rm -rf "$d"
[ $bad = 0 ] && echo "ALL OK" || echo "SOME CHECKS FAILED"
