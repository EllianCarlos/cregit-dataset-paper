#!/usr/bin/env bash
# launch_spot.sh a|b AZ [AMI]: one m6id.24xlarge one-time spot instance for census batch3<a|b>.
# Interruption and shutdown both terminate; no max price (capped at on-demand); IMDSv2;
# encrypted gp3 200 GiB root; tags Project/Owner/Batch=3/Name. Prints the instance id.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION}
x=$1; az=$2; ami=${3:-${RUNNER_AMI_BASE}}
case $x in a|b) ;; *) echo "usage: $0 a|b AZ [AMI]" >&2; exit 2 ;; esac
sub=$(aws ec2 describe-subnets --filters Name=default-for-az,Values=true Name=availability-zone,Values="$az" --query 'Subnets[0].SubnetId' --output text)
tags="{Key=Project,Value=cregit-census},{Key=Owner,Value=${RUNNER_USER}},{Key=Batch,Value=3},{Key=Name,Value=cregit-census-batch3$x}"
aws ec2 run-instances --image-id "$ami" --instance-type m6id.24xlarge --count 1 \
  --subnet-id "$sub" --security-group-ids ${RUNNER_SECURITY_GROUP} \
  --iam-instance-profile Name=cregit-census-ec2 \
  --instance-market-options 'MarketType=spot,SpotOptions={SpotInstanceType=one-time,InstanceInterruptionBehavior=terminate}' \
  --instance-initiated-shutdown-behavior terminate \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1 \
  --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=200,VolumeType=gp3,Encrypted=true,DeleteOnTermination=true}' \
  --tag-specifications "ResourceType=instance,Tags=[$tags]" "ResourceType=volume,Tags=[$tags]" "ResourceType=spot-instances-request,Tags=[$tags]" \
  --query 'Instances[0].InstanceId' --output text
