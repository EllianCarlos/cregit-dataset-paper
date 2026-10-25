#!/usr/bin/env bash
# F1-x3-fetch.sh RUN (this machine; the user or the main session runs it after DONE): downloads the
# outputs of s3://BUCKET/dataset-x1k/links-work/RUN/ (small files: the merged links, the counts, the
# PLAIN-BLAME table; no address: the machine checked each file for the at sign before the upload) to
# ${RUNNER_PROJECTS_TILDE}/cregit-workspace/companies/x1k-links/RUN/ and checks them again here (x3_report.py no-at).
# It never downloads a cache or a dataset file (only links-work/RUN/).
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
RUN=${1:?usage: F1-x3-fetch.sh dataset-x1k-links-N}
[[ $RUN =~ ^dataset-x1k-links-[0-9]+$ ]] || { echo "ABORT: $RUN is not dataset-x1k-links-<n>"; exit 1; }
H=$(cd "$(dirname "$0")" && pwd)
S=s3://${RUNNER_BUCKET}/dataset-x1k/links-work/$RUN
D=${RUNNER_PROJECTS}/cregit-workspace/companies/x1k-links/$RUN
PY=${RUNNER_PROJECTS}/cregit-workspace/census-local-a/ctp/.venv/bin/python
aws s3 ls $S/DONE >/dev/null || { echo "ABORT: no $S/DONE (see ALERT: aws s3 ls $S/)"; exit 1; }
mkdir -p $D
aws s3 cp --recursive $S/ $D/ --only-show-errors --exclude '*' --include '*.parquet' --include '*.tsv' \
  --include '*.json' --include '*.txt' --include '*.log' --include 'DONE'
(cd /tmp && $PY -I $H/x3_report.py no-at $(find $D -type f | sort)) | tail -1
cat $D/DONE
echo "gate: $(grep -h mapping_sha256 $D/gate-v1.txt)"
echo "merged: $(python3 -c 'import json,sys; j=json.load(open(sys.argv[1])); print(j["projects"], "projects,", j["domain_links"], "domain links, mapping", j["mapping_sha256"][:12])' $D/links-merged/links.json)"
echo "fetched to $D"
