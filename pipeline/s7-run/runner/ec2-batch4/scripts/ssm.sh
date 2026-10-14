#!/usr/bin/env bash
# I=<id> ssm.sh SCRIPT [TIMEOUT_S]: run SCRIPT as root on instance I via AWS-RunShellScript,
# output to s3://BUCKET/ssm-out/, poll until done, print status and the stdout/stderr tail.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
I=${I:?set I=instance-id}; B=${RUNNER_BUCKET}
script=$1; to=${2:-3600}
params=$(python3 -c '
import json,sys,base64,os
b=base64.b64encode(open(sys.argv[1],"rb").read()).decode(); n=os.path.basename(sys.argv[1])
print(json.dumps({"commands":["set -e","mkdir -p /root/ssm","echo %s | base64 -d > /root/ssm/%s" % (b,n),"bash /root/ssm/%s" % n],"executionTimeout":[sys.argv[2]]}))' "$script" "$to")
cid=$(aws ssm send-command --instance-ids $I --document-name AWS-RunShellScript --parameters "$params" \
  --output-s3-bucket-name $B --output-s3-key-prefix ssm-out --timeout-seconds 600 --comment "$(basename $script)" \
  --query Command.CommandId --output text)
echo "command $cid"
while :; do
  st=$(aws ssm get-command-invocation --command-id $cid --instance-id $I --query Status --output text 2>/dev/null || echo Pending)
  case $st in Pending|InProgress|Delayed) sleep 15 ;; *) break ;; esac
done
echo "status $st"
aws ssm get-command-invocation --command-id $cid --instance-id $I --query '[StandardOutputContent,StandardErrorContent]' --output text | tail -n ${TAILN:-60}
