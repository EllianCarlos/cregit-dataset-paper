#!/usr/bin/env bash
# post_relaunch.sh a|b INSTANCE_ID: the three steps that must follow every spot relaunch.
# restart_spot.sh runs it at its end; you can also run it by hand (a second run changes nothing).
#   1. spot a: /etc/cregit-census/fed/slots = 12 (a new instance has the default 8).
#   2. both: blameRepo/formatBlame.pl of cregit 57551d7 (sha256 788acb9a...) in the cregit copy of
#      each active b3/b5 part (they start from the AMI copy with the old file bcb80679...). Fed
#      parts get the file from their workload commit; the step only checks them. The template
#      /data/cregit-ec2 is never changed (on spot a the b3 parts run in it: they keep the old file).
#   3. spot a: remove "batch22 a3" and "batch21 a5" from the fed queue (they ran on this machine as
#      census-local-a), under the feeder lock.
# The instance half is scripts/post-relaunch.remote.sh (run as root through scripts/ssm.sh).
# WAIT (seconds, default 600): how long step 2 waits for a part copy that does not exist yet.
# Exit 0 only when every step ended without a failure (a SKIP is not a failure).
set -euo pipefail
cd "$(dirname "$0")"
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
x=${1:-}; id=${2:-}
case $x in a|b) ;; *) echo "usage: $0 a|b INSTANCE_ID" >&2; exit 2 ;; esac
case $id in i-*) ;; *) echo "usage: $0 a|b INSTANCE_ID" >&2; exit 2 ;; esac
WAIT=${WAIT:-600}
echo "post_relaunch $x $id: start $(date -u +%FT%TZ)"
st=$(aws ec2 describe-instances --instance-ids "$id" \
  --query 'Reservations[0].Instances[0].[State.Name, Tags[?Key==`Name`]|[0].Value]' --output text 2>&1) \
  || { echo "post_relaunch $x $id: ABORT: describe-instances failed: $st"; exit 1; }
read -r state name <<<"$st"
[ "$state" = running ] && [ "$name" = "cregit-census-batch3$x" ] \
  || { echo "post_relaunch $x $id: ABORT: state '$state', Name '$name' (want running, cregit-census-batch3$x): nothing changed"; exit 1; }
gen=scripts/post-relaunch-$x.sh
{ echo "X=$x"; echo "WAIT=$WAIT"; cat scripts/post-relaunch.remote.sh; } > "$gen.tmp" && mv -f "$gen.tmp" "$gen"
out=$(cd scripts && I=$id TAILN=200 ./ssm.sh "post-relaunch-$x.sh" 3600 2>&1) || true
echo "$out"
grep -qx 'status Success' <<<"$out" && grep -q "post_relaunch $x .* done rc=0$" <<<"$out" \
  && { echo "post_relaunch $x $id: OK $(date -u +%FT%TZ)"; exit 0; }
echo "post_relaunch $x $id: FAILED or incomplete (see above); run it again by hand: $PWD/post_relaunch.sh $x $id"
exit 1
