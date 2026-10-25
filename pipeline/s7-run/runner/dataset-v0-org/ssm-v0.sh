#!/usr/bin/env bash
# I=<id> [TAILN=N] ssm-v0.sh SCRIPT [TIMEOUT_S] (this machine): scripts/ssm.sh for the v0 machine
# (Run=v0-org). It refuses an instance without the tag Run=v0-org, and the machines A and B. It adds
# the line export V0_RUN=<Name tag> to the script.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
script=${1:?script}; to=${2:-3600}
bash -n "$script"
I=${I:?set I=instance-id}
case $I in ${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_BIG}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1}) echo "ABORT: $I is an x1k run machine, the path-fix machine, spot a or the big EC2"; exit 1 ;; esac
run=$(AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER="" aws ec2 describe-instances --instance-ids "$I" \
      --query 'Reservations[0].Instances[0].Tags[?Key==`Run`]|[0].Value' --output text)
[ "$run" = v0-org ] || { echo "ABORT: $I has Run=$run, not v0-org (the v0 machine only)"; exit 1; }
name=$(AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER="" aws ec2 describe-instances --instance-ids "$I" \
      --query 'Reservations[0].Instances[0].Tags[?Key==`Name`]|[0].Value' --output text)
[[ $name =~ ^dataset-v0-org-[0-9]+$ ]] || { echo "ABORT: Name '$name' is not dataset-v0-org-<n>"; exit 1; }
# The script gets V0_RUN=<Name> (the run id) as its second line; the file itself does not change.
d=$(mktemp -d); t=$d/$(basename "$script")
{ head -1 "$script"; echo "export V0_RUN=$name  # added by ssm-x2.sh"; tail -n +2 "$script"; } > "$t"
bash -n "$t"
rc=0; bash "$HOME/s3-work/dataset-x1k/scripts/ssm.sh" "$t" "$to" || rc=$?
rm -f "$t"; rmdir "$d"
exit $rc
