#!/usr/bin/env bash
# L1-launch-jv.sh (this machine): extra machines for the aws-sdk-java split (user decision 2026-10-23:
# on-demand extras for aws-sdk-java). Copy of ../rust-split/L1-launch-rs.sh (with its ON_DEMAND option),
# one EC2 Fleet (type instant, target 1) per part:
#   - KS: the parts to launch (default "1 2 3 4"); one machine per part, Name dataset-java-split-<k>
#     and tag Part=<k>. REPLACE=1 launches a new machine for a part whose machine is gone:
#     Name dataset-java-split-<k>-r<n>; S1 then resumes from the batches in S3;
#   - ON_DEMAND: 1 by default (the spot pools were reclaimed every 20 min to 2 h on 2026-10-21).
#     The fleet has DefaultTargetCapacityType on-demand, OnDemandOptions lowest-price with
#     MaxTotalPrice OD_MAX_PRICE (default 12.00 $/h; public prices in ${RUNNER_AWS_REGION}: c7a.48xlarge
#     9.85, m7a.48xlarge 11.13), and no SpotOptions. ON_DEMAND=0 gives the spot fleet of rust-split;
#   - TYPES: default "c7a.48xlarge m7a.48xlarge" (192 vCPU, one core per vCPU; the same speed, so the
#     parts stay even). "c6a.48xlarge m6a.48xlarge" is the other pair. Do not mix the pairs: the
#     parts are equal, and the slow machines then set the end. Lowest-price takes c7a first;
#     TYPES="m7a.48xlarge" gives 768 GiB if E0 shows more than 1.9 GiB per git blame;
#   - SUBNETS: all 4 subnets of the VPC (${RUNNER_AWS_REGION}a, b, c, d);
#   - launch template cregit-census-batch3-spot $Latest (AMI ${RUNNER_AMI_SPOT}, the AMI of machine A;
#     profile cregit-census-ec2, IMDSv2, root gp3 200 GiB, shutdown terminates, no market options);
#     ROOT_GB (optional) sets a larger root (gp3, 6000 IOPS, 500 MB/s) in each override (E1 prints
#     the size it needs);
#   - quota: on-demand: the pending and running on-demand vCPU of the standard families (A C D H I M R
#     T Z) plus 192 per new machine must stay <= the quota L-1216C47A (read with service-quotas;
#     OD_QUOTA if that read fails; 1152 on 2026-10-23: A 192 + 4 x 192 = 960). Spot: SPOT_QUOTA (1152);
#   - MAX_TOTAL_PRICE: the spot cap in $/h for one machine (default 5.00; spot only).
# Tags: Project, Owner, Run=java-split, Name, Part. It refuses a Name that is in instances.txt or on any
# instance, and a part that has a pending/running/stopping/stopped machine.
# Safety: it only creates. It never stops, terminates or changes an instance. Refuse list: machine A,
# the batch 2 machine, the v0 machine, the ids of the earlier refuse lists and the rust-split extras;
# their states are printed before and after.
# It refuses to launch before E1 wrote java-split/input/SHA256SUMS. DRY_RUN=1: writes the fleet
# requests and runs the EC2 DryRun check only.
# Prints "INSTANCE_ID TYPE SUBNET" per part and appends a line to instances.txt.
# Test hooks (test/t_l1.py only): JV_AWS (the aws command), JV_HOME (the kit dir).
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
H=${JV_HOME:-$(cd "$(dirname "$0")" && pwd)}
AWS=${JV_AWS:-aws}
KS=${KS:-"1 2 3 4"}
TYPES=${TYPES:-"c7a.48xlarge m7a.48xlarge"}
SUBNETS=${SUBNETS:-"${RUNNER_SUBNET_AZ_A} ${RUNNER_SUBNET_AZ_B} ${RUNNER_SUBNET_AZ_C} ${RUNNER_SUBNET_AZ_D}"}
MAX_TOTAL_PRICE=${MAX_TOTAL_PRICE:-5.00}
OD_MAX_PRICE=${OD_MAX_PRICE:-12.00}
ROOT_GB=${ROOT_GB:-}
SPOT_QUOTA=${SPOT_QUOTA:-1152}
OD_QUOTA=${OD_QUOTA:-1152}
REPLACE=${REPLACE:-0}
ON_DEMAND=${ON_DEMAND:-1}
REFUSE="${RUNNER_EC2_BIG} ${RUNNER_EC2_SPOT_A6} ${RUNNER_EC2_X1K_A} ${RUNNER_EC2_X1K_LONG_A2} ${RUNNER_EC2_X1K_B1} ${RUNNER_EC2_X1K_B2} ${RUNNER_EC2_X1K_LONG_A4} ${RUNNER_EC2_PATHFIX_B1} ${RUNNER_EC2_V0_ORG_1} ${RUNNER_EC2_X1K_RAW_1} ${RUNNER_EC2_X1K_LONG_A1} ${RUNNER_EC2_X1K_LONG_A3} ${RUNNER_EC2_RUST_SPLIT_1} ${RUNNER_EC2_RUST_SPLIT_2} ${RUNNER_EC2_RUST_SPLIT_3} ${RUNNER_EC2_RUST_SPLIT_4} ${RUNNER_EC2_RUST_SPLIT_5} ${RUNNER_EC2_RUST_SPLIT_1_R1} ${RUNNER_EC2_RUST_SPLIT_2_R1} ${RUNNER_EC2_RUST_SPLIT_3_R1} ${RUNNER_EC2_RUST_SPLIT_5_R1} ${RUNNER_EC2_RUST_SPLIT_2_R2} ${RUNNER_EC2_RUST_SPLIT_4_R1} ${RUNNER_EC2_RUST_SPLIT_5_R2}"
case $ON_DEMAND in 0|1) ;; *) echo "ABORT: ON_DEMAND '$ON_DEMAND' (0 or 1)"; exit 1 ;; esac
fam=""
for t in $TYPES; do
  case $t in c6a.48xlarge|m6a.48xlarge) f=6a ;; c7a.48xlarge|m7a.48xlarge) f=7a ;;
    *) echo "ABORT: $t is not in the list (c6a, m6a, c7a, m7a .48xlarge)"; exit 1 ;; esac
  [ -z "$fam" ] || [ "$fam" = "$f" ] || { echo "ABORT: TYPES mixes the 6a and 7a pairs (the parts are equal; the slow ones set the end)"; exit 1; }
  fam=$f
done
for v in MAX_TOTAL_PRICE OD_MAX_PRICE; do
  [[ ${!v} =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "ABORT: $v '${!v}'"; exit 1; }
done
for v in SPOT_QUOTA OD_QUOTA; do [[ ${!v} =~ ^[0-9]+$ ]] || { echo "ABORT: $v '${!v}'"; exit 1; }; done
[ -z "$ROOT_GB" ] || [[ $ROOT_GB =~ ^[0-9]+$ && $ROOT_GB -ge 200 && $ROOT_GB -le 2000 ]] || { echo "ABORT: ROOT_GB '$ROOT_GB' (200-2000)"; exit 1; }
for k in $KS; do [[ $k =~ ^[0-9]+$ ]] && [ "$k" -ge 1 ] && [ "$k" -le 20 ] || { echo "ABORT: bad part '$k' in KS"; exit 1; }; done
states() { $AWS ec2 describe-instances --filters "Name=instance-id,Values=${REFUSE// /,}" \
             --query 'Reservations[].Instances[].[InstanceId,State.Name]' --output text | sort; }
spot_vcpu() {  # pending and running spot vCPU (vCPU = cores x threads per core)
  $AWS ec2 describe-instances --filters Name=instance-lifecycle,Values=spot Name=instance-state-name,Values=pending,running \
    --query 'Reservations[].Instances[].[CpuOptions.CoreCount,CpuOptions.ThreadsPerCore]' --output text \
    | awk '{s += $1 * $2} END {print s + 0}'
}
od_vcpu() {  # pending and running on-demand vCPU of the standard families (no InstanceLifecycle)
  $AWS ec2 describe-instances --filters Name=instance-state-name,Values=pending,running \
    --query 'Reservations[].Instances[?!InstanceLifecycle][].[InstanceType,CpuOptions.CoreCount,CpuOptions.ThreadsPerCore]' --output text \
    | awk '$1 ~ /^[acdhimrtz]/ {s += $2 * $3} END {print s + 0}'
}
if [ "$ON_DEMAND" = 1 ]; then
  q=$($AWS service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A --query 'Quota.Value' --output text 2>/dev/null || true)
  if [[ $q =~ ^[0-9]+(\.[0-9]+)?$ ]]; then OD_QUOTA=${q%.*}; echo "on-demand quota L-1216C47A: $OD_QUOTA vCPU"
  else echo "on-demand quota: the read failed; OD_QUOTA=$OD_QUOTA"; fi
fi
if [ -z "${DRY_RUN:-}" ]; then
  $AWS s3 ls s3://${RUNNER_BUCKET}/dataset-x1k/java-split/input/SHA256SUMS > /dev/null 2>&1 \
    || { echo "ABORT: no java-split/input/SHA256SUMS: run E1 (and P1) on machine A first"; exit 1; }
fi
before=$(states); echo "refuse list before: $(echo $before)"
mkdir -p "$H/fleet"; cd "$H/fleet"
touch "$H/instances.txt"
for k in $KS; do
  live=$($AWS ec2 describe-instances --filters Name=tag:Run,Values=java-split Name=tag:Part,Values=$k \
         Name=instance-state-name,Values=pending,running,stopping,stopped \
         --query 'Reservations[].Instances[].[InstanceId,Tags[?Key==`Name`]|[0].Value]' --output text)
  [ -z "$live" ] || { echo "ABORT: part $k has a machine: $live"; exit 1; }
  NAME=dataset-java-split-$k
  if [ "$REPLACE" = 1 ]; then
    r=1; while grep -q "^dataset-java-split-$k-r$r=" "$H/instances.txt"; do r=$((r + 1)); done; NAME=dataset-java-split-$k-r$r
  elif grep -q "^$NAME=" "$H/instances.txt"; then
    echo "ABORT: $NAME is in instances.txt (used); REPLACE=1 launches a replacement"; exit 1
  fi
  used=$($AWS ec2 describe-instances --filters "Name=tag:Name,Values=$NAME" --query 'Reservations[].Instances[].InstanceId' --output text)
  [ -z "$used" ] || { echo "ABORT: $NAME is the name of $used (terminated ones count too)"; exit 1; }
  if [ "$ON_DEMAND" = 1 ]; then
    v=$(od_vcpu)
    [ $((v + 192)) -le "$OD_QUOTA" ] || { echo "ABORT: on-demand vCPU in use $v + 192 > quota $OD_QUOTA (part $k not launched)"; exit 1; }
    use="on-demand vCPU in use $v of $OD_QUOTA"
  else
    v=$(spot_vcpu)
    [ $((v + 192)) -le "$SPOT_QUOTA" ] || { echo "ABORT: spot vCPU in use $v + 192 > quota $SPOT_QUOTA (part $k not launched)"; exit 1; }
    use="spot vCPU in use $v of $SPOT_QUOTA"
  fi
  python3 -I - "$NAME" "$k" "$SUBNETS" "$TYPES" "$MAX_TOTAL_PRICE" "$ROOT_GB" "$ON_DEMAND" "$OD_MAX_PRICE" > "fleet-$NAME.json" <<'P'
import json, sys
name, k, subnets, types, maxp, root, od, odmax = sys.argv[1], sys.argv[2], sys.argv[3].split(), sys.argv[4].split(), sys.argv[5], sys.argv[6], sys.argv[7] == "1", sys.argv[8]
tags = [{"Key": "Project", "Value": "cregit-dataset"}, {"Key": "Owner", "Value": "${RUNNER_USER}"},
        {"Key": "Run", "Value": "java-split"}, {"Key": "Name", "Value": name}, {"Key": "Part", "Value": k}]
def ov(t, s):
    o = {"InstanceType": t, "SubnetId": s, "WeightedCapacity": 1.0}
    if root:
        o["BlockDeviceMappings"] = [{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": int(root), "VolumeType": "gp3", "Iops": 6000,
                                     "Throughput": 500, "Encrypted": True, "DeleteOnTermination": True}}]
    return o
req = {
    "Type": "instant",
    "TargetCapacitySpecification": {"TotalTargetCapacity": 1, "DefaultTargetCapacityType": "on-demand" if od else "spot"},
    "LaunchTemplateConfigs": [{"LaunchTemplateSpecification": {"LaunchTemplateName": "cregit-census-batch3-spot", "Version": "$Latest"},
                               "Overrides": [ov(t, s) for t in types for s in subnets]}],
    "TagSpecifications": [{"ResourceType": "instance", "Tags": tags}, {"ResourceType": "fleet", "Tags": tags}],
}
if od:
    req["OnDemandOptions"] = {"AllocationStrategy": "lowest-price", "MaxTotalPrice": odmax}
else:
    req["SpotOptions"] = {"AllocationStrategy": "price-capacity-optimized", "InstanceInterruptionBehavior": "terminate", "MaxTotalPrice": maxp}
print(json.dumps(req, indent=1))
P
  if [ -n "${DRY_RUN:-}" ]; then
    echo "DRY_RUN part $k: fleet request in $H/fleet/fleet-$NAME.json ($([ "$ON_DEMAND" = 1 ] && echo on-demand || echo spot)); $use; EC2 DryRun check:"
    $AWS ec2 create-fleet --cli-input-json "file://fleet-$NAME.json" --dry-run 2>&1 | tail -1 || true
    continue
  fi
  $AWS ec2 create-fleet --cli-input-json "file://fleet-$NAME.json" --output json > "fleet-$NAME.out.json"
  out=$(python3 -I - "fleet-$NAME.out.json" <<'P'
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
  ) || { after=$(states); echo "part $k: no instance; refuse list after: $(echo $after)"; exit 1; }
  echo "$out"
  id=${out%% *}; itype=$(echo "$out" | cut -d' ' -f2)
  case " $REFUSE " in *" $id "*) echo "ABORT: the fleet returned an id of the refuse list: $id"; exit 1 ;; esac
  desc=$($AWS ec2 describe-instances --instance-ids "$id" --query 'Reservations[0].Instances[0].[InstanceType,Placement.AvailabilityZone,ImageId,InstanceLifecycle]' --output text)
  if [ "$ON_DEMAND" = 1 ]; then
    price=on-demand
  else
    price=$($AWS ec2 describe-spot-price-history --instance-types "$itype" --product-descriptions Linux/UNIX \
            --availability-zone "$(echo "$desc" | cut -f2)" --start-time "$(date -u +%FT%TZ)" --query 'SpotPriceHistory[0].SpotPrice' --output text)
  fi
  echo "$NAME=$id $desc part=$k price=$price launched=$(date -u +%FT%TZ)" | tee -a "$H/instances.txt"
done
after=$(states); echo "refuse list after: $(echo $after)"
[ "$before" = "$after" ] || echo "WARNING: the state of an instance of the refuse list changed (not by this script)"
