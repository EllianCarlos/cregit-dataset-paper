#!/usr/bin/env bash
# L1-launch.sh (this machine): one one-time spot c6id.32xlarge for the x1k test run (user decision
# 2026-10-17: a NEW c6id.32xlarge spot in ${RUNNER_AWS_REGION}, about $1.25/h). The launch method of the v1
# spot machines (~/s3-work/ec2-batch3/launch_fleet.sh): an EC2 Fleet of type instant, allocation
# price-capacity-optimized, launch template cregit-census-batch3-spot $Latest (version 1: AMI
# ${RUNNER_AMI_SPOT}, profile cregit-census-ec2, SG ${RUNNER_SECURITY_GROUP}, IMDSv2, gp3 200 GiB
# encrypted, no user data, shutdown terminates), interruption terminates, no max price.
# Override: TYPE (default c6id.32xlarge) in SUBNETS (default the ${RUNNER_AWS_REGION}d default subnet, the AZ
# with the $1.25/h price on 2026-10-17; the other AZs were $2.2-2.7/h). Default subnets per AZ:
# 2a ${RUNNER_SUBNET_AZ_A}, 2b ${RUNNER_SUBNET_AZ_B}, 2c ${RUNNER_SUBNET_AZ_C},
# 2d ${RUNNER_SUBNET_AZ_D}. A type other than c6id.32xlarge needs the user's yes, and the part
# workers in R3-start.sh (WORKERS) must fit its vCPUs and memory. Tags: Project=cregit-dataset,
# Owner=${RUNNER_USER}, Run=x1k, Name=$NAME (default dataset-x1k-a).
# Safety: it only creates. It refuses if an instance named $NAME is pending/running/stopping, and
# it checks before and after that spot a (${RUNNER_EC2_SPOT_A6}) and the big EC2 (${RUNNER_EC2_BIG})
# keep their state and are not the new instance. Prints "INSTANCE_ID TYPE SUBNET".
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
H=$(cd "$(dirname "$0")" && pwd)
NAME=${NAME:-dataset-x1k-a}
SUBNETS=${SUBNETS:-${RUNNER_SUBNET_AZ_D}}
TYPE=${TYPE:-c6id.32xlarge}
KEEP="${RUNNER_EC2_SPOT_A6} ${RUNNER_EC2_BIG}"
states() { aws ec2 describe-instances --instance-ids $KEEP --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output text | sort; }
before=$(states); echo "before: $(echo $before)"
live=$(aws ec2 describe-instances --filters Name=tag:Name,Values=$NAME Name=instance-state-name,Values=pending,running,stopping \
       --query 'Reservations[].Instances[].InstanceId' --output text)
[ -z "$live" ] || { echo "ABORT: $NAME already has an instance: $live"; exit 1; }
cd "$H/fleet"
python3 - "$NAME" "$SUBNETS" "$TYPE" > fleet-$NAME.json <<'P'
import json, sys
name, subnets, itype = sys.argv[1], sys.argv[2].split(), sys.argv[3]
tags = [{"Key": "Project", "Value": "cregit-dataset"}, {"Key": "Owner", "Value": "${RUNNER_USER}"},
        {"Key": "Run", "Value": "x1k"}, {"Key": "Name", "Value": name}]
print(json.dumps({
    "Type": "instant",
    "SpotOptions": {"AllocationStrategy": "price-capacity-optimized", "InstanceInterruptionBehavior": "terminate"},
    "TargetCapacitySpecification": {"TotalTargetCapacity": 1, "DefaultTargetCapacityType": "spot"},
    "LaunchTemplateConfigs": [{"LaunchTemplateSpecification": {"LaunchTemplateName": "cregit-census-batch3-spot", "Version": "$Latest"},
                               "Overrides": [{"InstanceType": itype, "SubnetId": s} for s in subnets]}],
    "TagSpecifications": [{"ResourceType": "instance", "Tags": tags}, {"ResourceType": "fleet", "Tags": tags}],
}, indent=1))
P
aws ec2 create-fleet --cli-input-json file://fleet-$NAME.json --output json > fleet-$NAME.out.json
out=$(python3 - fleet-$NAME.out.json <<'P'
import json, sys
r = json.load(open(sys.argv[1]))
ids = [i for g in r.get("Instances", []) for i in g.get("InstanceIds", [])]
if ids:
    o = r["Instances"][0]["LaunchTemplateAndOverrides"]["Overrides"]
    print(ids[0], o["InstanceType"], o["SubnetId"])
else:
    errs = sorted({(e.get("ErrorCode"), e.get("ErrorMessage", "")[:120]) for e in r.get("Errors", [])})
    print("NO INSTANCE; fleet", r.get("FleetId"), "errors:", errs, file=sys.stderr); sys.exit(1)
P
) || { after=$(states); echo "after: $(echo $after)"; exit 1; }
echo "$out"
id=${out%% *}
case " $KEEP " in *" $id "*) echo "ABORT: the fleet returned a kept instance id $id"; exit 1 ;; esac
after=$(states); echo "after: $(echo $after)"
[ "$before" = "$after" ] || echo "WARNING: the state of a kept instance changed (not by this script)"
desc=$(aws ec2 describe-instances --instance-ids $id --query 'Reservations[0].Instances[0].[InstanceType,Placement.AvailabilityZone,ImageId,IamInstanceProfile.Arn,InstanceLifecycle]' --output text)
price=$(aws ec2 describe-spot-price-history --instance-types $TYPE --product-descriptions Linux/UNIX \
        --availability-zone "$(echo $desc | cut -d' ' -f2)" --start-time "$(date -u +%FT%TZ)" --query 'SpotPriceHistory[0].SpotPrice' --output text)
echo "$NAME=$id $desc price=$price launched=$(date -u +%FT%TZ)" | tee -a "$H/instances.txt"
