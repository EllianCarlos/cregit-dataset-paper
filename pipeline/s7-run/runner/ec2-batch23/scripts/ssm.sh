#!/usr/bin/env bash
# I=<id> ssm.sh SCRIPT [TIMEOUT_S]: run SCRIPT as root on instance I (spot a, spot b or the big EC2) via AWS-RunShellScript. The script lines
# go into the "commands" list of a parameters JSON file (file://), no base64: a heredoc writes them
# to /root/ssm/<name> and bash runs that file. Polls until done, prints
# the status and the stdout/stderr tail.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
I=${I:?set I=instance-id}; B=${RUNNER_BUCKET}
script=$1; to=${2:-3600}
pj=$(mktemp /tmp/ssm-params.XXXX.json)
python3 -I -c '
import json,sys
lines=open(sys.argv[1]).read().rstrip("\n").split("\n")
assert "EOF_SSM_SCRIPT" not in lines
n="/root/ssm/"+sys.argv[4]
q=chr(39)
cmd=["set -e","mkdir -p /root/ssm","cat > %s <<%sEOF_SSM_SCRIPT%s" % (n,q,q)]+lines+["EOF_SSM_SCRIPT","bash %s" % n]
json.dump({"commands":cmd,"executionTimeout":[sys.argv[2]]},open(sys.argv[3],"w"))' "$script" "$to" "$pj" "$(basename "$script")"
cid=$(aws ssm send-command --instance-ids $I --document-name AWS-RunShellScript --parameters file://$pj \
  --output-s3-bucket-name $B --output-s3-key-prefix ssm-out --timeout-seconds 600 --comment "$(basename $script)" \
  --query Command.CommandId --output text)
rm -f $pj
echo "command $cid"
while :; do
  st=$(aws ssm get-command-invocation --command-id $cid --instance-id $I --query Status --output text 2>/dev/null || echo Pending)
  case $st in Pending|InProgress|Delayed) sleep 10 ;; *) break ;; esac
done
echo "status $st"
# the full stdout/stderr from the S3 output (the API copy is cut at 24,000 characters)
pre=s3://$B/ssm-out/$cid/$I/awsrunShellScript/0.awsrunShellScript
if aws s3 cp $pre/stdout - 2>/dev/null | tail -n ${TAILN:-80}; then aws s3 cp $pre/stderr - 2>/dev/null | tail -n 20
else aws ssm get-command-invocation --command-id $cid --instance-id $I --query '[StandardOutputContent,StandardErrorContent]' --output text | tail -n ${TAILN:-80}; fi
