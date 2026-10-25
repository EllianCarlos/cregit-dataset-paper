#!/usr/bin/env bash
# L0-volumes.sh (this machine): the 4 EBS work volumes of machine A (the x1k long rows), made once,
# before the first launch. gp3, encrypted, 12,000 IOPS, 500 MiB/s, ${RUNNER_AWS_REGION}d (the AZ of the A
# fleet; a volume cannot move to another AZ). Sizes: Slot 1 3,000 GiB (asuswrt-merlin.ng), Slots 2-4
# 2,000 GiB. Tags: Project=cregit-dataset, Owner=${RUNNER_USER}, Run=x1k-long, Slot=K, Name=x1k-long-K.
# They are not attached here (L2-attach.sh attaches them with DeleteOnTermination false). Cost while
# they exist: about $1.32/h (9,000 GiB x $0.08/GB-month + IOPS and throughput above the free level).
# Default: it prints the commands only (DRY_RUN=1: also the EC2 DryRun check). RUN=1 runs them. It refuses if a volume with Run=x1k-long
# exists (any state). It never deletes a volume; the user deletes them after the final check.
# Result: a-volumes.txt (Slot, volume id) and scripts/a/vols.env (X1K_VOLS for R1 through ssm-a.sh).
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
H=$(cd "$(dirname "$0")" && pwd)
AZ=${AZ:-${RUNNER_AWS_REGION}d}
SIZES=(3000 2000 2000 2000)
have=$(aws ec2 describe-volumes --filters Name=tag:Run,Values=x1k-long --query 'Volumes[].[VolumeId,State,AvailabilityZone]' --output text)
[ -z "$have" ] || { echo "ABORT: volumes with Run=x1k-long exist already:"; echo "$have"; exit 1; }
cmd() {  # cmd K SIZE
  echo aws ec2 create-volume --availability-zone $AZ --volume-type gp3 --size $2 --iops 12000 --throughput 500 --encrypted \
    --tag-specifications "'ResourceType=volume,Tags=[{Key=Project,Value=cregit-dataset},{Key=Owner,Value=${RUNNER_USER}},{Key=Run,Value=x1k-long},{Key=Slot,Value=$1},{Key=Name,Value=x1k-long-$1}]'" \
    --query VolumeId --output text
}
if [ "${RUN:-0}" != 1 ]; then
  echo "# The commands (not run; RUN=1 bash $0 runs them):"
  for K in 1 2 3 4; do cmd $K ${SIZES[$((K-1))]}; done
  if [ "${DRY_RUN:-0}" = 1 ]; then  # the EC2 DryRun check of each command: no volume
    for K in 1 2 3 4; do echo "slot $K: $(eval "$(cmd $K ${SIZES[$((K-1))]} | sed 's/^aws ec2 create-volume /aws ec2 create-volume --dry-run /')" 2>&1 | tail -1)"; done
  fi
  exit 0
fi
: > "$H/a-volumes.txt.new"
for K in 1 2 3 4; do
  v=$(eval "$(cmd $K ${SIZES[$((K-1))]})")
  echo "slot $K $v ${SIZES[$((K-1))]} GiB" | tee -a "$H/a-volumes.txt.new"
done
aws ec2 wait volume-available --volume-ids $(awk '{print $3}' "$H/a-volumes.txt.new")
mv -f "$H/a-volumes.txt.new" "$H/a-volumes.txt"
echo "X1K_VOLS=\"$(awk '{printf "%s%s:%s", (NR > 1 ? " " : ""), $2, $3}' "$H/a-volumes.txt")\"" > "$H/scripts/a/vols.env"
aws ec2 describe-volumes --volume-ids $(awk '{print $3}' "$H/a-volumes.txt") \
  --query 'Volumes[].[Tags[?Key==`Slot`]|[0].Value,VolumeId,Size,Iops,Throughput,Encrypted,AvailabilityZone,State]' --output text | sort
echo "L0 done $(date -u +%FT%TZ): $(cat "$H/scripts/a/vols.env")"
