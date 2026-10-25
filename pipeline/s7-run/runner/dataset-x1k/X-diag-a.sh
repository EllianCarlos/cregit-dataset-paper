#!/usr/bin/env bash
# X-diag-a.sh (the user, this machine; read-only): why machine A is slow.
#   1. the EBS volumes of machine A: size, IOPS, throughput (the gp3 default is 3000 IOPS, 125 MB/s);
#   2. scripts/a/D7-io.sh on machine A through scripts/a/ssm-a.sh: CPU, disk wait, disk use.
# It changes nothing. Output: the screen and /tmp/x-diag-a.txt (lines with an at sign are dropped).
set -uo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
H=$(cd "$(dirname "$0")" && pwd)
I=${RUNNER_EC2_X1K_LONG_A4}
{
  echo "== EBS volumes of $I (VolumeId Size_GiB Type IOPS Throughput_MBps Device)"
  aws ec2 describe-volumes --filters Name=attachment.instance-id,Values=$I \
    --query 'Volumes[].[VolumeId,Size,VolumeType,Iops,Throughput,Attachments[0].Device]' --output text
  echo "== D7-io.sh on $I"
  I=$I TAILN=80 bash "$H/scripts/a/ssm-a.sh" "$H/scripts/a/D7-io.sh" 300
} 2>&1 | grep -v -F '@' | tee /tmp/x-diag-a.txt
