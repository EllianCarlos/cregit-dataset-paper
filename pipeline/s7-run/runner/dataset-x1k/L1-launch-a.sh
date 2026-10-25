#!/usr/bin/env bash
# L1-launch-a.sh (this machine): machine A of the x1k relaunch (the 11 long rows). One instance
# through an EC2 Fleet of type instant (as L1-launch.sh): launch template cregit-census-batch3-spot
# $Latest (AMI ${RUNNER_AMI_SPOT}, profile cregit-census-ec2, root gp3 200 GiB, no market options,
# shutdown terminates), one override per type in ONE subnet: ${RUNNER_AWS_REGION}d (the AZ of the EBS volumes).
#   TYPES   default the A list: m6i.32xlarge r6i.32xlarge m6a.48xlarge c6a.48xlarge m7i.48xlarge
#           m8i.48xlarge c7i.48xlarge (128 or 192 vCPU; R4 scales the blame jobs from nproc).
#   MARKET  spot (default; price-capacity-optimized, interruption terminates, no max price) or
#           on-demand (the fallback only: lowest-price; default TYPES m6a.48xlarge, $8.29/h, 192 vCPU,
#           768 GiB; with the whole A list, lowest-price would choose m6i.32xlarge with 128 vCPU).
#   SUBNET  default ${RUNNER_SUBNET_AZ_D} (${RUNNER_AWS_REGION}d). Another AZ is refused: the volumes stay there.
#   NAME    default dataset-x1k-long-a; tags Project=cregit-dataset, Owner=${RUNNER_USER}, Run=x1k-long.
# Safety: it only creates. Refuses if an instance with Run=x1k-long or Name=$NAME is pending, running,
# stopping or stopped. Refuse list (checked before and after; never the new id): the big EC2
# ${RUNNER_EC2_BIG} (stopped), spot a ${RUNNER_EC2_SPOT_A6}, and every instance with Run=x1k or
# Run=x1k-b or Name dataset-x1k-b* (the light-row machines B and the earlier x1k machine). Prints "INSTANCE_ID TYPE SUBNET" and appends
# instances.txt. Next: L2-attach.sh (I=<id>). DRY_RUN=1: write the request, run only the EC2 DryRun check.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
H=$(cd "$(dirname "$0")" && pwd)
NAME=${NAME:-dataset-x1k-long-a}
SUBNET=${SUBNET:-${RUNNER_SUBNET_AZ_D}}
MARKET=${MARKET:-spot}
case $MARKET in spot|on-demand) ;; *) echo "ABORT: MARKET must be spot or on-demand"; exit 1 ;; esac
if [ $MARKET = spot ]; then TYPES=${TYPES:-m6i.32xlarge r6i.32xlarge m6a.48xlarge c6a.48xlarge m7i.48xlarge m8i.48xlarge c7i.48xlarge}
else TYPES=${TYPES:-m6a.48xlarge}; fi
echo "market $MARKET, types: $TYPES, subnet $SUBNET"
az=$(aws ec2 describe-subnets --subnet-ids $SUBNET --query 'Subnets[0].AvailabilityZone' --output text)
[ "$az" = ${RUNNER_AWS_REGION}d ] || { echo "ABORT: $SUBNET is in $az, not ${RUNNER_AWS_REGION}d (the volumes are in ${RUNNER_AWS_REGION}d)"; exit 1; }
B_IDS=$(aws ec2 describe-instances --filters Name=tag:Run,Values=x1k,x1k-b Name=instance-state-name,Values=pending,running,stopping,stopped \
        --query 'Reservations[].Instances[].InstanceId' --output text)
B_IDS="$B_IDS $(aws ec2 describe-instances --filters 'Name=tag:Name,Values=dataset-x1k-b*' Name=instance-state-name,Values=pending,running,stopping,stopped \
        --query 'Reservations[].Instances[].InstanceId' --output text)"
KEEP="${RUNNER_EC2_BIG} ${RUNNER_EC2_SPOT_A6} $B_IDS"
# a filter, not --instance-ids: an id that no longer exists (spot a) must not fail the call
states() { aws ec2 describe-instances --filters "Name=instance-id,Values=$(echo $KEEP | tr ' ' ',')" --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output text | sort; }
before=$(states); echo "refuse list before: $(echo $before)"
live=$(aws ec2 describe-instances --filters Name=tag:Run,Values=x1k-long Name=instance-state-name,Values=pending,running,stopping,stopped \
       --query 'Reservations[].Instances[].InstanceId' --output text)
live2=$(aws ec2 describe-instances --filters Name=tag:Name,Values=$NAME Name=instance-state-name,Values=pending,running,stopping,stopped \
       --query 'Reservations[].Instances[].InstanceId' --output text)
[ -z "$live$live2" ] || { echo "ABORT: machine A has an instance already: $live $live2"; exit 1; }
mkdir -p "$H/fleet"; cd "$H/fleet"
F=fleet-$NAME-$(date -u +%Y%m%dT%H%M%SZ)
python3 - "$NAME" "$SUBNET" "$TYPES" "$MARKET" > $F.json <<'P'
import json, sys
name, subnet, types, market = sys.argv[1], sys.argv[2], sys.argv[3].split(), sys.argv[4]
tags = [{"Key": "Project", "Value": "cregit-dataset"}, {"Key": "Owner", "Value": "${RUNNER_USER}"},
        {"Key": "Run", "Value": "x1k-long"}, {"Key": "Name", "Value": name}]
spec = {
    "Type": "instant",
    "TargetCapacitySpecification": {"TotalTargetCapacity": 1, "DefaultTargetCapacityType": market},
    "LaunchTemplateConfigs": [{"LaunchTemplateSpecification": {"LaunchTemplateName": "cregit-census-batch3-spot", "Version": "$Latest"},
                               "Overrides": [{"InstanceType": t, "SubnetId": subnet} for t in types]}],
    "TagSpecifications": [{"ResourceType": "instance", "Tags": tags}, {"ResourceType": "fleet", "Tags": tags}],
}
if market == "spot":
    spec["SpotOptions"] = {"AllocationStrategy": "price-capacity-optimized", "InstanceInterruptionBehavior": "terminate"}
else:
    spec["OnDemandOptions"] = {"AllocationStrategy": "lowest-price"}
print(json.dumps(spec, indent=1))
P
if [ "${DRY_RUN:-0}" = 1 ]; then  # the EC2 DryRun check only: no fleet, no instance
  aws ec2 create-fleet --dry-run --cli-input-json file://$F.json --output json 2>&1 | tail -2; exit 0
fi
aws ec2 create-fleet --cli-input-json file://$F.json --output json > $F.out.json
out=$(python3 - $F.out.json <<'P'
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
) || { after=$(states); echo "refuse list after: $(echo $after)"; exit 1; }
echo "$out"
id=${out%% *}; itype=$(echo $out | cut -d' ' -f2)
case " $KEEP " in *" $id "*) echo "ABORT: the fleet returned an id of the refuse list: $id"; exit 1 ;; esac
after=$(states); echo "refuse list after: $(echo $after)"
[ "$before" = "$after" ] || echo "WARNING: the state of an instance of the refuse list changed (not by this script)"
desc=$(aws ec2 describe-instances --instance-ids $id --query 'Reservations[0].Instances[0].[InstanceType,Placement.AvailabilityZone,ImageId,InstanceLifecycle]' --output text)
price=on-demand
[ $MARKET = spot ] && price=$(aws ec2 describe-spot-price-history --instance-types $itype --product-descriptions Linux/UNIX \
        --availability-zone ${RUNNER_AWS_REGION}d --start-time "$(date -u +%FT%TZ)" --query 'SpotPriceHistory[0].SpotPrice' --output text)
echo "$NAME=$id $desc market=$MARKET price=$price launched=$(date -u +%FT%TZ)" | tee -a "$H/instances.txt"
echo "next: I=$id bash $H/L2-attach.sh"
