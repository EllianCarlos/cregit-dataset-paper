#!/usr/bin/env bash
# L1-launch-b.sh (this machine): one spot instance for machine B of the x1k relaunch (user approval
# 2026-10-19; README "Relaunch plan", machine B). Copy of L1-launch.sh with a type list:
#   - an EC2 Fleet of type instant, allocation price-capacity-optimized, launch template
#     cregit-census-batch3-spot $Latest (AMI ${RUNNER_AMI_SPOT}, profile cregit-census-ec2, SG
#     ${RUNNER_SECURITY_GROUP}, IMDSv2, gp3 200 GiB encrypted, shutdown terminates), interruption
#     terminates, no relaunch by the fleet;
#   - one override per type in TYPES and subnet in SUBNETS (default: the B list, 8 instance-store
#     types, in the 4 default subnets 2a/2b/2c/2d, from describe-subnets 2026-10-19);
#   - WeightedCapacity = the ctp workers of the type (96 vCPU: 20, 128 vCPU: 24) and a target of 20,
#     so the fleet compares the price per worker and starts exactly one instance;
#   - MAX_TOTAL_PRICE (optional, $/h): SpotOptions.MaxTotalPrice; unset = no cap (as L1-launch.sh).
# NAME is also the run id of R3-install-b.sh (live/<NAME>/, final/<NAME>/) and gives the slot:
# dataset-x1k-b1 = slot 1 (deal parts 1-4), dataset-x1k-b2 = slot 2 (deal parts 5-8); after a spot
# reclaim: dataset-x1k-b<slot>-r1, -r2, ... (the same slot, a new run id). No default: NAME is
# required. It refuses a NAME that is in instances.txt or on an instance, and it refuses when an
# instance of the same slot (dataset-x1k-b<slot> or dataset-x1k-b<slot>-*) is
# pending/running/stopping/stopped. The other slot's machine does not block it.
# Default TYPES (full pipeline, 2026-10-19): the B types with >= 768 GiB (about 38 GiB or more per
# worker for the firm step and step 10 at --memory-limit 16GB); c6id and m6id (192-512 GiB) only
# with an explicit TYPES.
# Safety: it only creates. It never stops, terminates or changes an instance. Refuse list: the big
# EC2 ${RUNNER_EC2_BIG} (stopped), spot a ${RUNNER_EC2_SPOT_A6}, the first x1k machine
# ${RUNNER_EC2_X1K_A}: their state is the same before and after, and the new id is none of them.
# Prints "INSTANCE_ID TYPE SUBNET" and appends a line to instances.txt.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
H=$(cd "$(dirname "$0")" && pwd)
NAME=${NAME:?set NAME=dataset-x1k-b1|b2 (after a reclaim dataset-x1k-b<slot>-r<n>)}
TYPES=${TYPES:-"i4i.24xlarge r6id.24xlarge i4i.32xlarge r6id.32xlarge"}
SUBNETS=${SUBNETS:-"${RUNNER_SUBNET_AZ_A} ${RUNNER_SUBNET_AZ_B} ${RUNNER_SUBNET_AZ_C} ${RUNNER_SUBNET_AZ_D}"}
MAX_TOTAL_PRICE=${MAX_TOTAL_PRICE:-}
REFUSE="${RUNNER_EC2_BIG} ${RUNNER_EC2_SPOT_A6} ${RUNNER_EC2_X1K_A}"
[[ $NAME =~ ^dataset-x1k-b([12])(-r[0-9]+)?$ ]] || { echo "ABORT: NAME '$NAME' is not dataset-x1k-b1|b2[-rN]"; exit 1; }
SLOT=${BASH_REMATCH[1]}
for t in $TYPES; do
  case $t in c6id.24xlarge|i4i.24xlarge|m6id.24xlarge|r6id.24xlarge|c6id.32xlarge|i4i.32xlarge|m6id.32xlarge|r6id.32xlarge) ;;
    *) echo "ABORT: $t is not in the B list (instance store, 96 or 128 vCPU)"; exit 1 ;; esac
done
# describe with a filter: an id that EC2 no longer shows gives no row, not an error
states() { aws ec2 describe-instances --filters Name=instance-id,Values=$(echo $REFUSE | tr ' ' ',') \
             --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output text | sort; }
before=$(states); echo "refuse list before: $(echo $before)"
grep -q "^$NAME=" "$H/instances.txt" 2>/dev/null && { echo "ABORT: $NAME is in instances.txt (used); take the next NAME"; exit 1; }
live=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=dataset-x1k-b$SLOT,dataset-x1k-b$SLOT-*" Name=instance-state-name,Values=pending,running,stopping,stopped \
       --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`]|[0].Value]' --output text)
[ -z "$live" ] || { echo "ABORT: slot $SLOT has an instance: $live"; exit 1; }
echo "slot $SLOT: no instance; the other B machines: $(aws ec2 describe-instances --filters "Name=tag:Name,Values=dataset-x1k-b*" Name=instance-state-name,Values=pending,running \
       --query 'Reservations[].Instances[].[Tags[?Key==`Name`]|[0].Value,InstanceId]' --output text | tr '\t\n' '= ')"
used=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" --query 'Reservations[].Instances[].InstanceId' --output text)
[ -z "$used" ] || { echo "ABORT: $NAME is the name of $used (also terminated ones count); take the next NAME"; exit 1; }
mkdir -p "$H/fleet"; cd "$H/fleet"
python3 - "$NAME" "$SUBNETS" "$TYPES" "$MAX_TOTAL_PRICE" "$SLOT" > fleet-$NAME.json <<'P'
import json, sys
name, subnets, types, maxp, slot = sys.argv[1], sys.argv[2].split(), sys.argv[3].split(), sys.argv[4], sys.argv[5]
workers = {"24xlarge": 20, "32xlarge": 24}  # 4 parts x 5 (96 vCPU) or x 6 (128 vCPU), as R4-start-b.sh
tags = [{"Key": "Project", "Value": "cregit-dataset"}, {"Key": "Owner", "Value": "${RUNNER_USER}"},
        {"Key": "Run", "Value": "x1k-b"}, {"Key": "Slot", "Value": slot}, {"Key": "Name", "Value": name}]
spot = {"AllocationStrategy": "price-capacity-optimized", "InstanceInterruptionBehavior": "terminate"}
if maxp:
    spot["MaxTotalPrice"] = maxp
print(json.dumps({
    "Type": "instant",
    "SpotOptions": spot,
    "TargetCapacitySpecification": {"TotalTargetCapacity": 20, "DefaultTargetCapacityType": "spot"},
    "LaunchTemplateConfigs": [{"LaunchTemplateSpecification": {"LaunchTemplateName": "cregit-census-batch3-spot", "Version": "$Latest"},
                               "Overrides": [{"InstanceType": t, "SubnetId": s, "WeightedCapacity": float(workers[t.split(".")[1]])}
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
