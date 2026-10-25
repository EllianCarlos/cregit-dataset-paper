#!/usr/bin/env bash
# V1-list-a-volumes.sh (run by the user: `! bash ~/s3-work/dataset-x1k/scripts/a/V1-list-a-volumes.sh`;
# 2026-10-23). Read-only: it deletes and changes nothing. Machine A (${RUNNER_EC2_X1K_LONG_A4}) is terminated.
# This script lists:
#   1. the EBS volumes named in scripts/a/vols.env (the 4 data volumes of machine A): id, state, size,
#      zone, attachment, Name tag;
#   2. every volume of the account in the state "available" (attached to no instance; it still costs
#      money), with its size, creation date and Name tag;
#   3. the monthly cost estimate of the available volumes (gp3: 0.08 USD per GiB-month, list price).
set -uo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
D=$(cd "$(dirname "$0")" && pwd)
V=$(grep -o 'vol-[0-9a-f]*' "$D/vols.env" | sort -u | tr '\n' ' ')
echo "== 1. the volumes of vols.env: ${V:-none found}"
if [ -n "$V" ]; then
  # shellcheck disable=SC2086
  aws ec2 describe-volumes --volume-ids $V \
    --query 'Volumes[].[VolumeId,State,Size,VolumeType,AvailabilityZone,Attachments[0].InstanceId||`-`,Tags[?Key==`Name`]|[0].Value||`-`]' \
    --output table 2>&1 | sed 's/@//g'
fi
echo "== 2. all volumes in the state available (no instance)"
aws ec2 describe-volumes --filters Name=status,Values=available \
  --query 'Volumes[].[VolumeId,Size,VolumeType,CreateTime,Tags[?Key==`Name`]|[0].Value||`-`]' \
  --output table 2>&1 | sed 's/@//g'
echo "== 3. cost estimate of the available volumes"
aws ec2 describe-volumes --filters Name=status,Values=available --query 'Volumes[].Size' --output text \
  | tr '\t' '\n' | awk 'NF {n++; s+=$1} END {printf "%d volumes, %d GiB, about %.0f USD a month at the gp3 list price\n", n, s, s*0.08}'
echo "V1 done (read-only)"
