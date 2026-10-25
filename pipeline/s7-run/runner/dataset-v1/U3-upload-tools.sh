#!/usr/bin/env bash
# U3-upload-tools.sh (this machine, run by the user): the fixed rewrite_meta_columns.py (one spill directory per
# output, ${RUNNER_STUDY_REPO} 17bc439) and the other merge tools to s3://.../dataset-v1/tools/. Inputs do not change.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
H=$HOME/s3-work/dataset-v1
(cd $H/tools && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: tools/SHA256SUMS"; exit 1; }
aws s3 sync "$H/tools/" "$B/dataset-v1/tools/" --only-show-errors --exact-timestamps
mkdir -p $H/check && aws s3 cp --recursive --only-show-errors "$B/dataset-v1/tools/" $H/check/
(cd $H/check && sha256sum --quiet -c SHA256SUMS) && echo "ALL OK: tools in S3 equal $(cat $H/tools/SOURCE)"
