#!/usr/bin/env bash
# U2-upload-tools.sh (this machine, run by the user): the merge tools and the v1 sidecar to s3://.../dataset-v1/tools/,
# then U1 again for the new input list (mongodb__mongo is now the post-fixed file; the other 1,001 files are in S3 already).
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
H=$HOME/s3-work/dataset-v1
(cd $H/tools && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: tools/SHA256SUMS"; exit 1; }
aws s3 sync "$H/tools/" "$B/dataset-v1/tools/" --only-show-errors --exact-timestamps
aws s3 ls "$B/dataset-v1/tools/"
bash $H/U1-upload-inputs.sh
