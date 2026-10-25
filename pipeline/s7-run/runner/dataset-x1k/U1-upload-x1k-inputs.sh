#!/usr/bin/env bash
# U1-upload-x1k-inputs.sh (this machine, run by the user): the x1k test-run inputs (stage/: the
# 7,215-row manifest, its 4 part manifests, the sidecar project_meta.x1k.json, the parts table,
# the ctp patch ctp-no-firm.patch with the sha256 of the patched files, SOURCE, SHA256SUMS) to
# s3://.../dataset-x1k/inputs/. A new prefix: nothing is deleted or overwritten elsewhere.
# The sidecar holds project names, URLs, licenses and pool facts only: no e-mail address.
# Then a download check into check/ (a new folder per run) that must print ALL OK.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
H=$HOME/s3-work/dataset-x1k
(cd $H/stage && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: stage/SHA256SUMS"; exit 1; }
aws s3 cp --recursive --only-show-errors "$H/stage/" "$B/dataset-x1k/inputs/"
C=$H/check/$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$C"
aws s3 cp --recursive --only-show-errors "$B/dataset-x1k/inputs/" "$C/"
(cd "$C" && sha256sum --quiet -c SHA256SUMS) && cmp -s "$C/SHA256SUMS" "$H/stage/SHA256SUMS" \
  && echo "ALL OK: $(wc -l < "$C/SHA256SUMS") x1k input files in $B/dataset-x1k/inputs/ equal stage/ ($(head -1 "$H/stage/SOURCE"))"
