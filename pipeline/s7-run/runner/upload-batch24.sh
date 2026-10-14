#!/usr/bin/env bash
# The user runs this (Claude's S3 uploads are denied). Uploads the 5 input files of batch 24 (the 32 L7-20b
# rows that census L7-20b had not started, moved to spot b on 2026-10-13), then reads every object back and
# checks the sha256 of each. It also reads back the cregit bundle 57551d7 (already in B/cregit/) and checks it.
set -uo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
U=$HOME/s3-work/ec2-batch24/upload
C=$HOME/s3-work/upload-cregit-blamelimit
(cd $U && [ "$(command ls | wc -l)" -eq 5 ] && sha256sum --quiet -c SHA256SUMS) || { echo "FAIL local files"; exit 1; }
aws s3 ls $B/batch24/input/ >/dev/null 2>&1 && { echo "FAIL: $B/batch24/input/ exists already: nothing uploaded"; exit 1; }
aws s3 cp $U/ $B/batch24/input/ --recursive --only-show-errors || { echo "FAIL upload"; exit 1; }
bad=0
d=$(mktemp -d); aws s3 cp $B/batch24/input/ $d/ --recursive --only-show-errors
if (cd $d && [ "$(command ls | wc -l)" -eq 5 ] && sha256sum --quiet -c SHA256SUMS); then echo "batch24: 5 objects, read-back ok"; else echo "batch24: CHECK FAILED"; bad=1; fi
rm -rf "$d"
d=$(mktemp -d); aws s3 cp $B/cregit/cregit-57551d7.bundle $d/ --only-show-errors; aws s3 cp $B/cregit/SHA256SUMS.57551d7 $d/ --only-show-errors
(cd $d && cmp -s SHA256SUMS.57551d7 $C/SHA256SUMS.57551d7 && sha256sum --quiet -c SHA256SUMS.57551d7) && echo "bundle 57551d7: read-back ok" || { echo "bundle 57551d7: CHECK FAILED"; bad=1; }
rm -rf "$d"
[ $bad = 0 ] && echo "ALL OK" || echo "SOME CHECKS FAILED"
