#!/usr/bin/env bash
# I=<id> [TAILN=N] ssm-rs.sh SCRIPT [TIMEOUT_S] (this machine): scripts/ssm.sh for an extra machine of
# the aws-sdk-rust split. It refuses the refuse list and any instance without the tag Run=rust-split,
# a Name dataset-rust-split-<k> (or -<k>-r<n>) and the tag Part=<k>. It sends a wrapper that sets
# "export RS_PART=<k> RS_NAME=<Name>" and runs the script; the file itself does not change.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
script=${1:?script}; to=${2:-3600}
bash -n "$script"
I=${I:?set I=instance-id}
case $I in ${RUNNER_EC2_BIG}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1}|${RUNNER_EC2_V0_ORG_1}|${RUNNER_EC2_X1K_RAW_1}|${RUNNER_EC2_X1K_LONG_A1}|${RUNNER_EC2_X1K_LONG_A3})
  echo "ABORT: $I is on the refuse list (machine A, the batch 2 machine, the v0 machine, the other runs)"; exit 1 ;; esac
tags=$(AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER="" aws ec2 describe-instances --instance-ids "$I" \
  --query 'Reservations[0].Instances[0].[Tags[?Key==`Run`]|[0].Value,Tags[?Key==`Name`]|[0].Value,Tags[?Key==`Part`]|[0].Value]' --output text)
read -r run name part <<< "$tags"
[ "$run" = rust-split ] || { echo "ABORT: $I has Run=$run, not rust-split"; exit 1; }
[[ $name =~ ^dataset-rust-split-([0-9]+)(-r[0-9]+)?$ ]] || { echo "ABORT: Name '$name' is not dataset-rust-split-<k>"; exit 1; }
[ "${BASH_REMATCH[1]}" = "$part" ] || { echo "ABORT: Name $name and Part=$part do not agree"; exit 1; }
d=$(mktemp -d); t=$d/$(basename "$script")
# Optional settings for S1 (ssm.sh passes no environment): RS_JOBS, RS_MARGIN, RS_UPLOAD_EVERY,
# RS_GATE_FAIL_HOLD, RS_MEM_PER_JOB_GIB become JOBS, MARGIN, ... in the script.
extra=""
for v in JOBS MARGIN UPLOAD_EVERY GATE_FAIL_HOLD MEM_PER_JOB_GIB; do
  rv=RS_$v; val=${!rv:-}
  [ -z "$val" ] && continue
  [[ $val =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "ABORT: $rv=$val is not a number"; exit 1; }
  extra="$extra $v=$val"
done
# As ssm-a.sh: a small wrapper with the script as gzip + base64 (S1 is about 30 KB), run as root by bash.
n=$(basename "$script")
{ echo '#!/usr/bin/env bash'
  echo "# ssm-rs wrapper of $n ($(sha256sum "$script" | cut -c1-16)), $(date -u +%FT%TZ)"
  echo "export RS_PART=$part RS_NAME=$name$extra"
  echo "mkdir -p /root/ssm"
  echo "echo '$(gzip -9 -n -c "$script" | base64 -w0)' | base64 -d | gunzip > /root/ssm/$n.inner"
  echo "exec bash /root/ssm/$n.inner"
} > "$t"
bash -n "$t"
echo "sending $n ($(wc -c < "$script") B, wrapper $(wc -c < "$t") B) to part $part ($name)"
rc=0; bash "$H/../scripts/ssm.sh" "$t" "$to" || rc=$?
rm -f "$t"; rmdir "$d"
exit $rc
