#!/usr/bin/env bash
# L2-attach.sh (this machine; I=<instance id>): attach the 4 volumes of machine A (tag Run=x1k-long,
# Slot=1..4) to instance I as /dev/sdf, /dev/sdg, /dev/sdh, /dev/sdi (Slot 1..4), DeleteOnTermination
# false (the default of attach-volume; checked after). Refuses: I in the refuse list (the big EC2,
# spot a, an instance with Run=x1k), I without Run=x1k-long, not 4 volumes, a volume in another AZ,
# a volume attached to another instance. A volume attached to I already is skipped. Writes
# scripts/a/vols.env (X1K_VOLS "slot:volume-id ..." for R1 through scripts/a/ssm-a.sh).
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
H=$(cd "$(dirname "$0")" && pwd)
I=${I:?set I=instance-id}
case $I in ${RUNNER_EC2_BIG}|${RUNNER_EC2_SPOT_A6}) echo "ABORT: $I is the big EC2 or spot a"; exit 1 ;; esac
read -r run state az <<<"$(aws ec2 describe-instances --instance-ids $I --query 'Reservations[0].Instances[0].[Tags[?Key==`Run`]|[0].Value,State.Name,Placement.AvailabilityZone]' --output text)"
[ "$run" = x1k-long ] || { echo "ABORT: $I has Run=$run, not x1k-long"; exit 1; }
[ "$state" = running ] || { echo "ABORT: $I is $state, not running"; exit 1; }
vols=$(aws ec2 describe-volumes --filters Name=tag:Run,Values=x1k-long \
       --query 'Volumes[].[Tags[?Key==`Slot`]|[0].Value,VolumeId,AvailabilityZone,State,Attachments[0].InstanceId]' --output text | sort)
echo "$vols"
[ "$(echo "$vols" | awk 'NF' | wc -l)" = 4 ] || { echo "ABORT: expected 4 volumes with Run=x1k-long"; exit 1; }
echo "$vols" | awk '{print $1}' | tr '\n' ' ' | grep -qx '1 2 3 4 ' || { echo "ABORT: the Slot tags are not 1 2 3 4"; exit 1; }
dev=(x /dev/sdf /dev/sdg /dev/sdh /dev/sdi)
while read -r slot v vaz vstate att; do
  [ "$vaz" = "$az" ] || { echo "ABORT: slot $slot $v is in $vaz, the instance in $az"; exit 1; }
  if [ "$vstate" = in-use ]; then
    [ "$att" = "$I" ] || { echo "ABORT: slot $slot $v is attached to $att"; exit 1; }
    echo "slot $slot $v: attached to $I already"; continue
  fi
  [ "$vstate" = available ] || { echo "ABORT: slot $slot $v is $vstate"; exit 1; }
done <<<"$vols"
while read -r slot v vaz vstate att; do
  [ "$vstate" = available ] || continue
  aws ec2 attach-volume --volume-id $v --instance-id $I --device ${dev[$slot]} --query State --output text
done <<<"$vols"
aws ec2 wait volume-in-use --volume-ids $(echo "$vols" | awk '{print $2}')
aws ec2 describe-volumes --volume-ids $(echo "$vols" | awk '{print $2}') \
  --query 'Volumes[].[Tags[?Key==`Slot`]|[0].Value,VolumeId,Attachments[0].InstanceId,Attachments[0].Device,Attachments[0].State,Attachments[0].DeleteOnTermination]' --output text | sort | tee /tmp/x1k-long-attach.txt
awk -v i=$I '$3 != i || $6 != "False" {bad=1} END {exit bad}' /tmp/x1k-long-attach.txt || { echo "ABORT: an attachment is not on $I or has DeleteOnTermination true"; exit 1; }
echo "X1K_VOLS=\"$(echo "$vols" | awk '{printf "%s%s:%s", (NR > 1 ? " " : ""), $1, $2}')\"" > "$H/scripts/a/vols.env"
echo "L2 done $(date -u +%FT%TZ): $(cat "$H/scripts/a/vols.env"). Next: wait for SSM Online, then I=$I bash $H/scripts/a/ssm-a.sh $H/scripts/a/R1-setup.sh 3600"
