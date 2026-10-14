#!/usr/bin/env bash
# launch_fleet.sh a|b [TYPES...]: one one-time spot instance for census batch3<a|b> through an EC2
# Fleet of type instant, allocation strategy price-capacity-optimized, over every (type, AZ) pair of
# TYPES (default: the x86 NVMe list below) in the 4 ${RUNNER_AWS_REGION} default subnets. Launch template
# cregit-census-batch3-spot (AMI ${RUNNER_AMI_SPOT}, IMDSv2, gp3 200 GiB encrypted, shutdown
# terminates); no max price (capped at on-demand); interruption terminates. Tags Project, Owner,
# Batch=3, Name=cregit-census-batch3<a|b>. Prints "INSTANCE_ID TYPE AZ", or the fleet errors.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION}
x=${1:-}; case $x in a|b) shift ;; *) echo "usage: $0 a|b [TYPES...]" >&2; exit 2 ;; esac
types=${*:-m6id.24xlarge c6id.32xlarge r6id.24xlarge m6idn.24xlarge r6idn.24xlarge i4i.24xlarge m5d.24xlarge m5dn.24xlarge}
cd "$(dirname "$0")/fleet"
subnets=$(aws ec2 describe-subnets --filters Name=default-for-az,Values=true --query 'Subnets[].SubnetId' --output text)
python3 - "$x" "$types" "$subnets" > fleet-$x.json <<'P'
import json, sys
x, types, subnets = sys.argv[1], sys.argv[2].split(), sys.argv[3].split()
tags = [{"Key": "Project", "Value": "cregit-census"}, {"Key": "Owner", "Value": "${RUNNER_USER}"},
        {"Key": "Batch", "Value": "3"}, {"Key": "Name", "Value": f"cregit-census-batch3{x}"}]
print(json.dumps({
    "Type": "instant",
    "SpotOptions": {"AllocationStrategy": "price-capacity-optimized", "InstanceInterruptionBehavior": "terminate"},
    "TargetCapacitySpecification": {"TotalTargetCapacity": 1, "DefaultTargetCapacityType": "spot"},
    "LaunchTemplateConfigs": [{"LaunchTemplateSpecification": {"LaunchTemplateName": "cregit-census-batch3-spot", "Version": "$Latest"},
                               "Overrides": [{"InstanceType": t, "SubnetId": s} for t in types for s in subnets]}],
    "TagSpecifications": [{"ResourceType": "instance", "Tags": tags}, {"ResourceType": "fleet", "Tags": tags}],
}, indent=1))
P
aws ec2 create-fleet --cli-input-json file://fleet-$x.json --output json > fleet-$x.out.json
python3 - fleet-$x.out.json <<'P'
import json, sys
r = json.load(open(sys.argv[1]))
ids = [i for g in r.get("Instances", []) for i in g.get("InstanceIds", [])]
if ids:
    g = r["Instances"][0]
    print(ids[0], g["LaunchTemplateAndOverrides"]["Overrides"]["InstanceType"], g["LaunchTemplateAndOverrides"]["Overrides"]["SubnetId"])
else:
    errs = sorted({(e.get("ErrorCode"), e["LaunchTemplateAndOverrides"]["Overrides"].get("InstanceType")) for e in r.get("Errors", [])})
    print("NO INSTANCE; fleet", r.get("FleetId"), "errors:", errs, file=sys.stderr); sys.exit(1)
P
