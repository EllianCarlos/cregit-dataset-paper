#!/usr/bin/env bash
# The user runs this (Claude's S3 uploads are denied). Uploads the 8 input files of batch 21 (the DP8L
# supplement, 2026-10-10), then reads every object back and checks the sha256 of each.
set -uo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
U=$HOME/s3-work/ec2-batch21/upload
(cd $U && [ "$(ls | wc -l)" -eq 8 ] && sha256sum --quiet -c SHA256SUMS) || { echo "FAIL local files"; exit 1; }
aws s3 cp $U/ $B/batch21/input/ --recursive --only-show-errors || { echo "FAIL upload"; exit 1; }
d=$(mktemp -d); aws s3 cp $B/batch21/input/ $d/ --recursive --only-show-errors
if (cd $d && [ "$(ls | wc -l)" -eq 8 ] && sha256sum --quiet -c SHA256SUMS); then echo "batch21: 8 objects, read-back ok"; else echo "batch21: CHECK FAILED"; fi
rm -rf "$d"
