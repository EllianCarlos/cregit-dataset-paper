#!/usr/bin/env bash
# U1-upload-x3.sh (run by the user: `! bash ~/s3-work/dataset-x1k/x3/U1-upload-x3.sh`): uploads stage/
# (S0-x3-stage.sh: the tools, companies.v4.6.duckdb and ref-links/ = links-v4.6) to
# s3://BUCKET/dataset-x1k/links-tools/ for the x3 links machine. It checks the sha256 of each file and
# of SHA256SUMS before, and the sizes after. No file of stage/ holds an e-mail address (the database
# and the link files have domains and organisation ids only). It writes nothing else.
# The sidecars are in S3 already (dataset-v1/raw/, dataset-x1k/raw/; R1/x3_run.sh check their sha256).
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
ST=$(cd "$(dirname "$0")" && pwd)/stage
D=s3://${RUNNER_BUCKET}/dataset-x1k/links-tools
WANT_SUMS=7dba806bb9e3a1f78eb2da654f7daa870978637bff687ad6ae49ef8f9e60ba2b
[ "$(sha256sum $ST/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: stage/SHA256SUMS is not $WANT_SUMS (S0 ran again: update WANT_SUMS in U1, R1 and M1)"; exit 1; }
(cd $ST && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a stage file does not match SHA256SUMS"; exit 1; }
aws s3 cp --recursive $ST/ $D/ --only-show-errors
for f in $(cut -d' ' -f3 $ST/SHA256SUMS) SHA256SUMS SOURCE; do
  [ "$(aws s3 ls $D/$f | awk '{print $3}')" = "$(stat -c %s $ST/$f)" ] || { echo "ABORT: size check of $f"; exit 1; }
done
echo "uploaded $(($(wc -l < $ST/SHA256SUMS) + 2)) files ($(du -sb $ST | cut -f1) B) to $D/"
echo "U1-x3 done"
