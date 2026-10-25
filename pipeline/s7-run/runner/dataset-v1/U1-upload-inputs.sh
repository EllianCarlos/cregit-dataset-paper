#!/usr/bin/env bash
# U1-upload-inputs.sh (this machine, run by the user): upload the 1,001 v1 input files that exist only here
# (931 post-fixed files, local-a..d) and inputs.tsv to s3://.../dataset-v1/. Spot a reads them for the merge.
# A staging tree of hard links gives the S3 keys; then one `aws s3 sync`; then a size check of every key.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
H=$HOME/s3-work/dataset-v1
S=$H/stage
[ -s $H/upload.tsv ] && [ -s $H/inputs.tsv ] || { echo "ABORT: run build_inputs.py first"; exit 1; }
mkdir -p $S
n=0
while IFS=$'\t' read -r path key sha; do
  mkdir -p "$S/$(dirname "$key")"
  [ -e "$S/$key" ] || ln "$path" "$S/$key"
  n=$((n+1))
done < $H/upload.tsv
echo "staged $n files"
(cd $H && sha256sum inputs.tsv build_inputs.py upload.tsv > SHA256SUMS)
aws s3 sync "$S/dataset-v1/inputs/" "$B/dataset-v1/inputs/" --only-show-errors
for f in inputs.tsv build_inputs.py upload.tsv SHA256SUMS; do aws s3 cp "$H/$f" "$B/dataset-v1/$f" --only-show-errors; done
# check: every key is in S3 with the local size
aws s3 ls "$B/dataset-v1/inputs/" --recursive | awk '{print $4"\t"$3}' | sort > $H/s3-list.tsv
(cd $S && find dataset-v1/inputs -type f -printf '%p\t%s\n' | sort) > $H/local-list.tsv
if cmp -s $H/s3-list.tsv $H/local-list.tsv; then
  echo "ALL OK: $(wc -l < $H/local-list.tsv) files, $(awk -F'\t' '{s+=$2} END {printf "%.1f GB", s/1e9}' $H/local-list.tsv)"
else
  echo "DIFFER: compare $H/s3-list.tsv and $H/local-list.tsv"; exit 1
fi
