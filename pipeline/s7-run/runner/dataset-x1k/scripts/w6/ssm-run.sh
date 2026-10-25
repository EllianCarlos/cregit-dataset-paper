#!/usr/bin/env bash
# RUN=<run id> I=<instance id> [TAILN=N] ssm-run.sh SCRIPT [TIMEOUT_S] (this machine): run SCRIPT on
# instance I through scripts/ssm.sh, with X1K_RUN=<run id> set at the top of the script. ssm.sh sends
# only the script text, not the environment, so this is how R3-install-b.sh gets the run id.
# The run id is the NAME of the L1-launch-b.sh instance (dataset-x1k-b1 or dataset-x1k-b2; after
# a spot reclaim dataset-x1k-b<slot>-r1, -r2, ...). The script file itself does not change (a copy goes to a new temp dir).
set -euo pipefail
RUN=${RUN:?set RUN=<run id>, the NAME of the instance, for example dataset-x1k-b1}
[[ $RUN =~ ^dataset-x1k-b[12](-r[0-9]+)?$ ]] || { echo "ABORT: RUN '$RUN' is not dataset-x1k-b1|b2[-rN]"; exit 1; }
: "${I:?set I=instance-id}"
src=${1:?script}; to=${2:-3600}
H=$(cd "$(dirname "$0")/.." && pwd)
d=$(mktemp -d)
{ head -1 "$src"; echo "export X1K_RUN=$RUN  # added by ssm-run.sh"; tail -n +2 "$src"; } > "$d/$(basename "$src")"
bash -n "$d/$(basename "$src")"
bash "$H/ssm.sh" "$d/$(basename "$src")" "$to"
