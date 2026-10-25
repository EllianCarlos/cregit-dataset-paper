#!/usr/bin/env bash
# I=<id> [TAILN=N] ssm-a.sh SCRIPT [TIMEOUT_S] (this machine): scripts/ssm.sh for machine A.
# It sends a small wrapper: the line X1K_VOLS="slot:volume-id ..." of scripts/a/vols.env (written by
# L0/L2; R1 needs it, the other scripts ignore it) and SCRIPT as gzip + base64 (R3 is 20 KB; the
# SSM parameter stays small). The wrapper unpacks SCRIPT to /root/ssm/ and runs it as root with
# bash; the exit code is that of SCRIPT. It refuses an instance without the tag Run=x1k-long.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
script=${1:?script}; to=${2:-3600}
bash -n "$script"
I=${I:?set I=instance-id}
run=$(AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER="" aws ec2 describe-instances --instance-ids "$I" \
      --query 'Reservations[0].Instances[0].Tags[?Key==`Run`]|[0].Value' --output text)
[ "$run" = x1k-long ] || { echo "ABORT: $I has Run=$run, not x1k-long (machine A only)"; exit 1; }
d=$(mktemp -d); n=$(basename "$script"); t=$d/$n
{ echo '#!/usr/bin/env bash'
  echo "# ssm-a wrapper of $n ($(sha256sum "$script" | cut -c1-16)), $(date -u +%FT%TZ)"
  if [ -f "$H/vols.env" ]; then grep '^X1K_VOLS="' "$H/vols.env"; echo "export X1K_VOLS"; fi
  echo "mkdir -p /root/ssm"
  echo "echo '$(gzip -9 -n -c "$script" | base64 -w0)' | base64 -d | gunzip > /root/ssm/$n.inner"
  echo "exec bash /root/ssm/$n.inner"
} > "$t"
bash -n "$t"
echo "sending $n ($(wc -c < "$script") B, wrapper $(wc -c < "$t") B$([ -f "$H/vols.env" ] && echo ", with vols.env"))"
rc=0; bash "$H/../ssm.sh" "$t" "$to" || rc=$?
rm -f "$t"; rmdir "$d"
exit $rc
