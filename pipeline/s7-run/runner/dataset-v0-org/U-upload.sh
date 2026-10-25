#!/usr/bin/env bash
# U-upload.sh (the user, this machine): upload stage/ to s3://.../dataset-v0-org/inputs/ and check it.
# The link files hold domains, organisation ids and project names only (no address).
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
H=$HOME/s3-work/dataset-v0-org
(cd $H/stage && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: stage/SHA256SUMS"; exit 1; }
aws s3 sync "$H/stage/" "$B/dataset-v0-org/inputs/" --only-show-errors --exact-timestamps --delete
mkdir -p $H/check && aws s3 cp --recursive --only-show-errors "$B/dataset-v0-org/inputs/" $H/check/
(cd $H/check && sha256sum --quiet -c SHA256SUMS) && echo "ALL OK: v0-org inputs in S3 equal $(cat $H/stage/SOURCE)"
