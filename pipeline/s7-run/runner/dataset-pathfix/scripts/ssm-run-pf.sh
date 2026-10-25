#!/usr/bin/env bash
# RUN=<run id> I=<instance id> [TAILN=N] ssm-run-pf.sh SCRIPT [TIMEOUT_S] (this machine): run SCRIPT
# on instance I through scripts/ssm.sh, with PF_RUN=<run id> set at the top of the script. ssm.sh
# sends only the script text, not the environment, so this is how R3-install-pf.sh gets the run id.
# Copy of ~/s3-work/dataset-x1k/scripts/w6/ssm-run.sh. The run id is the NAME of the
# L1-launch-pf.sh instance (dataset-pathfix-b1; after a spot reclaim dataset-pathfix-b1-r1, -r2,
# ...). The script file itself does not change (a copy goes to a new temp dir).
set -euo pipefail
RUN=${RUN:?set RUN=<run id>, the NAME of the instance, for example dataset-pathfix-b1}
[[ $RUN =~ ^dataset-pathfix-b1(-r[0-9]+)?$ ]] || { echo "ABORT: RUN '$RUN' is not dataset-pathfix-b1[-rN]"; exit 1; }
: "${I:?set I=instance-id}"
# Refuse list (as L1-launch-pf.sh): never send a command to these instances.
case $I in ${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}) echo "ABORT: $I is on the refuse list"; exit 1 ;; esac
src=${1:?script}; to=${2:-3600}
H=$(cd "$(dirname "$0")" && pwd)
d=$(mktemp -d)
{ head -1 "$src"; echo "export PF_RUN=$RUN  # added by ssm-run-pf.sh"; tail -n +2 "$src"; } > "$d/$(basename "$src")"
bash -n "$d/$(basename "$src")"
bash "$H/ssm.sh" "$d/$(basename "$src")" "$to"
