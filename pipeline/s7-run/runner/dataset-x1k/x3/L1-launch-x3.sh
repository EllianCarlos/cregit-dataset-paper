#!/usr/bin/env bash
# L1-launch-x3.sh (this machine; the main session runs it): one spot instance for kit x3 (the x1k domain
# cache, the merged links of v1 + x1k and the PLAIN-BLAME count). Copy of ../x2/L1-launch-x2.sh:
#   - an EC2 Fleet of type instant, allocation price-capacity-optimized, launch template
#     cregit-census-batch3-spot $Latest (AMI ${RUNNER_AMI_SPOT}, profile cregit-census-ec2, SG
#     ${RUNNER_SECURITY_GROUP}, IMDSv2, gp3 200 GiB encrypted, shutdown terminates), interruption
#     terminates, no relaunch by the fleet;
#   - one override per type in TYPES and subnet in SUBNETS (default: 4 instance-store types with
#     >= 256 GiB memory and >= 1.9 TB instance store, the 4 default subnets 2a/2b/2c/2d); target 1,
#     weight 1 (one instance). The run downloads 164 GB (v1 127 GB + x1k 37 GB) to the instance store;
#   - MAX_TOTAL_PRICE (optional, $/h).
# NAME (default dataset-x1k-links-1; a new start: dataset-x1k-links-2, ...) is the run id of the x3 scripts.
# Tags: Project, Owner, Run=x1k-links, Name. It refuses a NAME that is in ../instances.txt or on an
# instance, and it refuses when an instance with Run=x1k-links is pending/running/stopping/stopped.
# Safety: it only creates. It never stops, terminates or changes an instance. Refuse list: the big
# EC2, spot a, the x1k machines A and B, the two x1k-raw merge machines and the v0-org machine; their
# state is the same before and after.
# DRY_RUN=1: writes the fleet request and runs the EC2 DryRun check only.
# Prints "INSTANCE_ID TYPE SUBNET" and appends a line to ../instances.txt.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
H=$(cd "$(dirname "$0")" && pwd); R=$(cd "$H/.." && pwd)
NAME=${NAME:-dataset-x1k-links-1}
TYPES=${TYPES:-"i4i.8xlarge i4i.16xlarge r6id.8xlarge r6id.16xlarge"}
SUBNETS=${SUBNETS:-"${RUNNER_SUBNET_AZ_A} ${RUNNER_SUBNET_AZ_B} ${RUNNER_SUBNET_AZ_C} ${RUNNER_SUBNET_AZ_D}"}
MAX_TOTAL_PRICE=${MAX_TOTAL_PRICE:-}
REFUSE="${RUNNER_EC2_BIG} ${RUNNER_EC2_SPOT_A6} ${RUNNER_EC2_X1K_A} ${RUNNER_EC2_X1K_LONG_A2} ${RUNNER_EC2_X1K_B1} ${RUNNER_EC2_X1K_B2} ${RUNNER_EC2_X1K_LONG_A4} ${RUNNER_EC2_PATHFIX_B1} ${RUNNER_EC2_X1K_RAW_1} ${RUNNER_EC2_X1K_RAW_2} ${RUNNER_EC2_V0_ORG_1}"
[[ $NAME =~ ^dataset-x1k-links-[0-9]+$ ]] || { echo "ABORT: NAME '$NAME' is not dataset-x1k-links-<n>"; exit 1; }
for t in $TYPES; do
  case $t in i4i.8xlarge|i4i.16xlarge|i4i.24xlarge|r6id.8xlarge|r6id.16xlarge|r6id.24xlarge) ;;
    *) echo "ABORT: $t is not in the x3 list (instance store >= 1.9 TB, >= 256 GiB)"; exit 1 ;; esac
done
states() { aws ec2 describe-instances --filters Name=instance-id,Values=$(echo $REFUSE | tr ' ' ',') \
             --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output text | sort; }
before=$(states); echo "refuse list before: $(echo $before)"
grep -q "^$NAME=" "$R/instances.txt" 2>/dev/null && { echo "ABORT: $NAME is in instances.txt (used); take the next NAME"; exit 1; }
live=$(aws ec2 describe-instances --filters Name=tag:Run,Values=x1k-links Name=instance-state-name,Values=pending,running,stopping,stopped \
       --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`]|[0].Value]' --output text)
[ -z "$live" ] || { echo "ABORT: an x3 links machine exists: $live"; exit 1; }
used=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" --query 'Reservations[].Instances[].InstanceId' --output text)
[ -z "$used" ] || { echo "ABORT: $NAME is the name of $used (also terminated ones count); take the next NAME"; exit 1; }
mkdir -p "$H/fleet"; cd "$H/fleet"
python3 - "$NAME" "$SUBNETS" "$TYPES" "$MAX_TOTAL_PRICE" > fleet-$NAME.json <<'P'
import json, sys
name, subnets, types, maxp = sys.argv[1], sys.argv[2].split(), sys.argv[3].split(), sys.argv[4]
tags = [{"Key": "Project", "Value": "cregit-dataset"}, {"Key": "Owner", "Value": "${RUNNER_USER}"},
        {"Key": "Run", "Value": "x1k-links"}, {"Key": "Name", "Value": name}]
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
echo "$NAME=$id $desc price=$price launched=$(date -u +%FT%TZ)" | tee -a "$R/instances.txt"
