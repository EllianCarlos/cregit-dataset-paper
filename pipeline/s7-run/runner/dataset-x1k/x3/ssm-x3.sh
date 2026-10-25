#!/usr/bin/env bash
# I=<id> [TAILN=N] ssm-x3.sh SCRIPT [TIMEOUT_S] (this machine): ../scripts/ssm.sh for the x1k links
# machine (kit x3). It refuses an instance without the tag Run=x1k-links, and the machines of the refuse
# list (L1-launch-x3.sh). It adds the line export X3_RUN=<Name tag> to the script (the file itself does
# not change). The scripts print counts and names of files only, never an address (ssm.sh prints the
# stdout tail here).
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
script=${1:?script}; to=${2:-3600}
bash -n "$script"
I=${I:?set I=instance-id}
case $I in ${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_BIG}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1}|${RUNNER_EC2_X1K_RAW_1}|${RUNNER_EC2_X1K_RAW_2}|${RUNNER_EC2_V0_ORG_1})
  echo "ABORT: $I is on the refuse list (an x1k run, merge or v0 machine, the path-fix machine, spot a or the big EC2)"; exit 1 ;; esac
run=$(AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER="" aws ec2 describe-instances --instance-ids "$I" \
      --query 'Reservations[0].Instances[0].Tags[?Key==`Run`]|[0].Value' --output text)
[ "$run" = x1k-links ] || { echo "ABORT: $I has Run=$run, not x1k-links (the x3 links machine only)"; exit 1; }
name=$(AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER="" aws ec2 describe-instances --instance-ids "$I" \
      --query 'Reservations[0].Instances[0].Tags[?Key==`Name`]|[0].Value' --output text)
[[ $name =~ ^dataset-x1k-links-[0-9]+$ ]] || { echo "ABORT: Name '$name' is not dataset-x1k-links-<n>"; exit 1; }
d=$(mktemp -d); t=$d/$(basename "$script")
{ head -1 "$script"; echo "export X3_RUN=$name  # added by ssm-x3.sh"; tail -n +2 "$script"; } > "$t"
bash -n "$t"
rc=0; bash "$H/../scripts/ssm.sh" "$t" "$to" || rc=$?
rm -f "$t"; rmdir "$d"
exit $rc
