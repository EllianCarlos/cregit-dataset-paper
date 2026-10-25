#!/usr/bin/env bash
# V3-fetch-sample.sh (the user, this machine): step 7 of README.md. Copies 5 small v0 files of
# s3://.../dataset-v0-org/parquet/ (the 5 smallest files of 1 MB or more, by the S3 listing) to
# ${RUNNER_PROJECTS_TILDE}/cregit-workspace/companies/v0-check-v4.5/parquet/ and checks their sha256 against the
# SHA256SUMS of the run. The files hold identity columns, so they stay in the workspace (never in git).
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}/dataset-v0-org
R=${RUNNER_PROJECTS}/cregit-workspace/companies/v0-check-v4.5
mkdir -p "$R/parquet"
aws s3 cp "$B/SHA256SUMS" "$R/SHA256SUMS.run" --only-show-errors
names=$(aws s3 ls "$B/parquet/" | awk '$3 >= 1000000 {print $3, $4}' | sort -n | awk 'NR <= 5 {print $2}')
for f in $names; do aws s3 cp "$B/parquet/$f" "$R/parquet/$f" --only-show-errors; done
cd "$R/parquet"
n=0; for f in $names; do
  want=$(awk -v f="$f" '{g=$2; sub(/^.*\//, "", g); if (g == f && !n++) print $1}' "$R/SHA256SUMS.run")
  got=$(sha256sum "$f" | cut -d' ' -f1)
  if [ -n "$want" ] && [ "$want" = "$got" ]; then n=$((n+1)); else echo "MISMATCH: $f"; fi
done
echo "V3: $n of 5 files copied with the sha256 of the run, in $R/parquet"
