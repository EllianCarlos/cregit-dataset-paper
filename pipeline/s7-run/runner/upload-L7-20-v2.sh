#!/usr/bin/env bash
# upload-L7-20-v2.sh (run by the user; 2026-10-10): replace the inputs of census L7-20 (not started yet)
# with v2, which adds batch 21's L project NetBSD__pkgsrc. First the v1 objects are kept in S3 as
# L7-20/input-v1/, then the 3 staged files of ~/s3-work/ec2-L7-20/upload-v2/ go to L7-20/input/, then
# all are read back and checked against the staged SHA256SUMS. On the big EC2, census-L7-20-v2swap sees
# the v2 SHA256SUMS in S3, copies the inputs, checks them and lifts the hold of the L7-20 waiter.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
U=$HOME/s3-work/ec2-L7-20/upload-v2
(cd "$U" && sha256sum --quiet -c SHA256SUMS) || { echo "staged files differ from their SHA256SUMS"; exit 1; }
aws s3 ls "$B/L7-20/input-v1/SHA256SUMS" >/dev/null 2>&1 || aws s3 cp "$B/L7-20/input/" "$B/L7-20/input-v1/" --recursive --only-show-errors
for f in manifest.L7-20.tsv project_meta.L7-20.json SHA256SUMS; do aws s3 cp "$U/$f" "$B/L7-20/input/$f" --only-show-errors; done
T=$(mktemp -d); trap 'rm -r "$T"' EXIT
aws s3 cp "$B/L7-20/input/" "$T/" --recursive --only-show-errors
cmp "$T/SHA256SUMS" "$U/SHA256SUMS" && (cd "$T" && sha256sum --quiet -c SHA256SUMS) && echo "read-back OK: $(aws s3 ls "$B/L7-20/input/" | wc -l) objects in L7-20/input/, v1 kept in L7-20/input-v1/ ($(aws s3 ls "$B/L7-20/input-v1/" | wc -l) objects)"
