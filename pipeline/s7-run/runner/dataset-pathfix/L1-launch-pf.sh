#!/usr/bin/env bash
# L1-launch-pf.sh (this machine): one spot instance for the cregit path-fix rerun (user decisions
# 2026-10-20: rerun with cregit 14b8db4; 35 rows, no AliSQL). Copy of
# ~/s3-work/dataset-x1k/L1-launch-b.sh with these changes:
#   - NAME=dataset-pathfix-b1 (after a spot reclaim dataset-pathfix-b1-r1, -r2, ...). NAME is also
#     the run id of scripts/R3-install-pf.sh (live/<NAME>/ and final/<NAME>/ under dataset-x1k/).
#   - own instances.txt ($H/instances.txt) and own fleet/ folder;
#   - one machine for all rows (no slots): it refuses when an instance with the tag Name
#     dataset-pathfix-b1 or dataset-pathfix-b1-* is pending/running/stopping/stopped;
#   - WeightedCapacity 1 per instance and a target of 1: the rerun has a fixed 8 workers (2 parts
#     x 4), so the fleet compares the price per instance;
#   - MAX_TOTAL_PRICE default 3.50 ($/h, SpotOptions.MaxTotalPrice); MAX_TOTAL_PRICE= (empty) = no cap.
# The rest as B: an EC2 Fleet of type instant, allocation price-capacity-optimized, launch template
# cregit-census-batch3-spot $Latest (AMI ${RUNNER_AMI_SPOT}, profile cregit-census-ec2, SG
# ${RUNNER_SECURITY_GROUP}, IMDSv2, gp3 200 GiB encrypted, shutdown terminates), interruption
# terminates, no relaunch by the fleet; one override per type in TYPES and subnet in SUBNETS
# (default: the B types with >= 768 GiB, in the 4 default subnets 2a/2b/2c/2d).
# Safety: it only creates. It never stops, terminates or changes an instance. Refuse list: the big
# EC2 ${RUNNER_EC2_BIG} (stopped, batch 2), machine A of x1k ${RUNNER_EC2_X1K_LONG_A4} (on-demand, it
# runs), spot a ${RUNNER_EC2_SPOT_A6}, the first x1k machine ${RUNNER_EC2_X1K_A}: their state is the
# same before and after, and the new id is none of them.
# DRY_RUN=1: writes the fleet request and does only the EC2 DryRun check.
# Prints "INSTANCE_ID TYPE SUBNET" and appends a line to instances.txt.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
H=$(cd "$(dirname "$0")" && pwd)
NAME=${NAME:?set NAME=dataset-pathfix-b1 (after a reclaim dataset-pathfix-b1-r<n>)}
TYPES=${TYPES:-"i4i.24xlarge r6id.24xlarge i4i.32xlarge r6id.32xlarge"}
SUBNETS=${SUBNETS:-"${RUNNER_SUBNET_AZ_A} ${RUNNER_SUBNET_AZ_B} ${RUNNER_SUBNET_AZ_C} ${RUNNER_SUBNET_AZ_D}"}
MAX_TOTAL_PRICE=${MAX_TOTAL_PRICE-3.50}
REFUSE="${RUNNER_EC2_BIG} ${RUNNER_EC2_X1K_LONG_A4} ${RUNNER_EC2_SPOT_A6} ${RUNNER_EC2_X1K_A}"
[[ $NAME =~ ^dataset-pathfix-b1(-r[0-9]+)?$ ]] || { echo "ABORT: NAME '$NAME' is not dataset-pathfix-b1[-rN]"; exit 1; }
for t in $TYPES; do
  case $t in i4i.24xlarge|r6id.24xlarge|i4i.32xlarge|r6id.32xlarge) ;;
    *) echo "ABORT: $t is not in the list (instance store, >= 768 GiB)"; exit 1 ;; esac
done
# describe with a filter: an id that EC2 no longer shows gives no row, not an error
states() { aws ec2 describe-instances --filters Name=instance-id,Values=$(echo $REFUSE | tr ' ' ',') \
             --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output text | sort; }
before=$(states); echo "refuse list before: $(echo $before)"
grep -q "^$NAME=" "$H/instances.txt" 2>/dev/null && { echo "ABORT: $NAME is in instances.txt (used); take the next NAME"; exit 1; }
live=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=dataset-pathfix-b1,dataset-pathfix-b1-*" Name=instance-state-name,Values=pending,running,stopping,stopped \
       --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`]|[0].Value]' --output text)
[ -z "$live" ] || { echo "ABORT: a path-fix instance exists: $live"; exit 1; }
used=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" --query 'Reservations[].Instances[].InstanceId' --output text)
[ -z "$used" ] || { echo "ABORT: $NAME is the name of $used (also terminated ones count); take the next NAME"; exit 1; }
mkdir -p "$H/fleet"; cd "$H/fleet"
python3 - "$NAME" "$SUBNETS" "$TYPES" "$MAX_TOTAL_PRICE" > fleet-$NAME.json <<'P'
import json, sys
name, subnets, types, maxp = sys.argv[1], sys.argv[2].split(), sys.argv[3].split(), sys.argv[4]
tags = [{"Key": "Project", "Value": "cregit-dataset"}, {"Key": "Owner", "Value": "${RUNNER_USER}"},
        {"Key": "Run", "Value": "pathfix"}, {"Key": "Name", "Value": name}]
spot = {"AllocationStrategy": "price-capacity-optimized", "InstanceInterruptionBehavior": "terminate"}
if maxp:
    spot["MaxTotalPrice"] = maxp
print(json.dumps({
    "Type": "instant",
    "SpotOptions": spot,
    "TargetCapacitySpecification": {"TotalTargetCapacity": 1, "DefaultTargetCapacityType": "spot"},
    "LaunchTemplateConfigs": [{"LaunchTemplateSpecification": {"LaunchTemplateName": "cregit-census-batch3-spot", "Version": "$Latest"},
                               "Overrides": [{"InstanceType": t, "SubnetId": s, "WeightedCapacity": 1.0}
                                             for t in types for s in subnets]}],
    "TagSpecifications": [{"ResourceType": "instance", "Tags": tags}, {"ResourceType": "fleet", "Tags": tags}],
}, indent=1))
P
if [ -n "${DRY_RUN:-}" ]; then
  echo "DRY_RUN: fleet request in $H/fleet/fleet-$NAME.json; EC2 DryRun check:"
  aws ec2 create-fleet --cli-input-json file://fleet-$NAME.json --dry-run 2>&1 | tail -1 || true
  exit 0
fi
aws ec2 create-fleet --cli-input-json file://fleet-$NAME.json --output json > fleet-$NAME.out.json
out=$(python3 - fleet-$NAME.out.json <<'P'
import json, sys
r = json.load(open(sys.argv[1]))
ids = [i for g in r.get("Instances", []) for i in g.get("InstanceIds", [])]
if len(ids) > 1:
    print("MORE THAN ONE INSTANCE:", ids, "fleet", r.get("FleetId"), file=sys.stderr)
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
case " $REFUSE " in *" $id "*) echo "ABORT: the fleet returned an id of the refuse list: $id"; exit 1 ;; esac
after=$(states); echo "refuse list after: $(echo $after)"
[ "$before" = "$after" ] || echo "WARNING: the state of an instance of the refuse list changed (not by this script)"
desc=$(aws ec2 describe-instances --instance-ids $id --query 'Reservations[0].Instances[0].[InstanceType,Placement.AvailabilityZone,ImageId,IamInstanceProfile.Arn,InstanceLifecycle]' --output text)
price=$(aws ec2 describe-spot-price-history --instance-types $itype --product-descriptions Linux/UNIX \
        --availability-zone "$(echo $desc | cut -d' ' -f2)" --start-time "$(date -u +%FT%TZ)" --query 'SpotPriceHistory[0].SpotPrice' --output text)
echo "$NAME=$id $desc price=$price launched=$(date -u +%FT%TZ)" | tee -a "$H/instances.txt"
