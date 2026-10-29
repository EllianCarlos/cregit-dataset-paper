#!/usr/bin/env bash
# Bring the googleapis/google-cloud-java -C100 re-blame result off the SSM box.
# v2 -- run from YOUR OWN terminal (the agent session is denied SSM by policy).
#
# Changes from v1, both of which were real bugs:
#   * v1 packaged /root/cregit-reblame/scrcpy-blame-out -- the 278-file REHEARSAL.
#     Directory selection is now explicit and guarded: it refuses to package any
#     tree with fewer than MIN_FILES .blame files, and prints every candidate.
#   * v1 granted the instance role s3:PutObject. That can never work: the role
#     carries a permissions boundary that excludes S3, and
#     a boundary caps a principal regardless of what you attach (a same-account
#     bucket policy would not escape it either). S3 is dropped from the path.
#
# New route: the box serves the parts over loopback HTTP, this script opens an
# SSM port-forward to it, and the agent curls them straight onto the dev-desk.
# No IAM, no presigning, no S3, one hop instead of two.
#
# Usage:
#   ./fetch-gcj-result.sh package   # verify + tar + split   (long: ~21 GB)
#   ./fetch-gcj-result.sh serve     # start HTTP + tunnel, leave running
#   ./fetch-gcj-result.sh stop      # stop the box when the agent says done

set -uo pipefail

# Account-specific values (see ../../README.md). The names of the first two are the
# tokens of s7-run/runner/runner.env.example.
PROFILE=${RUNNER_AWS_PROFILE:?set RUNNER_AWS_PROFILE to the AWS CLI profile}
REGION=${RUNNER_AWS_REGION:?set RUNNER_AWS_REGION to the AWS region}
INSTANCE=${GCJ_INSTANCE:?set GCJ_INSTANCE to the EC2 id of the re-blame machine}
ROLE=${GCJ_ROLE:-<instance-role>}
REMOTE_PORT=8371
LOCAL_PORT=8371
PART_SIZE=2000M
MIN_FILES=100000          # the real result has 131,366; the rehearsal has 278
STAGE=/root/cregit-reblame/_xfer

A="aws --region $REGION --profile $PROFILE"
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

ensure_online() {
  local state
  state=$($A ec2 describe-instances --instance-ids "$INSTANCE" \
          --query 'Reservations[0].Instances[0].State.Name' --output text)
  if [ "$state" != running ]; then
    say "starting $INSTANCE (was $state)"
    $A ec2 start-instances --instance-ids "$INSTANCE" >/dev/null
    $A ec2 wait instance-running --instance-ids "$INSTANCE"
  fi
  printf 'waiting for SSM agent'
  for _ in $(seq 1 60); do
    if [ "$($A ssm describe-instance-information \
          --filters "Key=InstanceIds,Values=$INSTANCE" \
          --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null)" = Online ]; then
      echo " online"; return 0
    fi
    printf '.'; sleep 5
  done
  echo " TIMED OUT"; return 1
}

# run a script on the box, stream stdout back, propagate failure
ssmrun() {
  local label=$1 b64 cid status
  b64=$(base64 -w0)
  cid=$($A ssm send-command --instance-ids "$INSTANCE" \
        --document-name AWS-RunShellScript \
        --parameters "commands=[\"export HOME=/root; echo $b64 | base64 -d > /tmp/_step.sh; bash /tmp/_step.sh 2>&1\"]" \
        --timeout-seconds 7200 \
        --query 'Command.CommandId' --output text) || return 1
  printf '%s (command %s)' "$label" "$cid"
  while :; do
    status=$($A ssm get-command-invocation --command-id "$cid" \
             --instance-id "$INSTANCE" --query 'Status' --output text 2>/dev/null || echo Pending)
    case "$status" in Success|Failed|Cancelled|TimedOut) break;; esac
    printf '.'; sleep 15
  done
  echo " -> $status"
  $A ssm get-command-invocation --command-id "$cid" --instance-id "$INSTANCE" \
     --query 'StandardOutputContent' --output text
  [ "$status" = Success ]
}

# --------------------------------------------------------------------- package
do_package() {
  ensure_online || exit 1

  say "locating the result tree (guarded: needs >= $MIN_FILES .blame files)"
  ssmrun "scanning" <<REMOTE
set -euo pipefail
echo "--- every candidate tree, with its .blame count ---"
mapfile -t CAND < <(find / -maxdepth 5 -type d \\( -name '*blame-out*' -o -name 'blame' \\) 2>/dev/null)
BEST=""; BESTN=0
for d in "\${CAND[@]}"; do
  n=\$(find "\$d" -name '*.blame' 2>/dev/null | wc -l)
  printf '%8d  %s\n' "\$n" "\$d"
  if [ "\$n" -gt "\$BESTN" ]; then BESTN=\$n; BEST=\$d; fi
done
echo
echo "selected=\$BEST"
echo "selected_count=\$BESTN"
if [ "\$BESTN" -lt $MIN_FILES ]; then
  echo "ABORT: largest tree has \$BESTN .blame files, below the $MIN_FILES floor."
  echo "That means the real google-cloud-java output is not where we expect."
  exit 1
fi
echo "\$BEST" > /root/.xfer_src
REMOTE
  [ $? -eq 0 ] || { echo "!! discovery failed or tripped the guard -- stopping"; exit 1; }

  say "verification (handoff section 7) on the SELECTED tree"
  ssmrun "verifying" <<'REMOTE'
set -uo pipefail
OUT=$(cat /root/.xfer_src)
REPO=$(find / -maxdepth 5 -type d -name '*google-cloud-java-cregit' 2>/dev/null | head -1)
echo "out_dir=$OUT"
echo "repo=$REPO"
echo

echo "--- driver summary + done marker ---"
ls -la /root/*.done /root/*out*.txt /root/*.log 2>/dev/null
for f in /root/*out*.txt; do [ -s "$f" ] && { echo "[$f]"; tail -5 "$f"; }; done
LOG=$(ls -t /root/*.log 2>/dev/null | head -1)
[ -n "$LOG" ] && { echo "[$LOG tail]"; tail -3 "$LOG"; }
echo

echo "--- check 1: counts ---"
if [ -n "$REPO" ]; then
  git config --global --add safe.directory '*' 2>/dev/null
  cd "$REPO"
  echo "mask_selected=$(git ls-files | grep -icE '\.(c|c\+\+|cc|cp|cpp|cxx|h|h\+\+|hh|hpp|hxx|java|rs|tcc)$')"
fi
echo "blame_files=$(find "$OUT" -name '*.blame' | wc -l)"
echo
echo "--- check 2: empty outputs (want 0) ---"
echo "empty=$(find "$OUT" -name '*.blame' -size 0 | wc -l)"
echo
echo "--- check 3: format <sha>;;<TAB><token> ---"
find "$OUT" -name '*.blame' -size +2k | head -1 | while read -r f; do
  echo "[$f]"; head -3 "$f" | cat -A | sed 's/\$$//'
done
echo
echo "--- check 4: distinct shas in samples (>1 = -C100 spread attribution) ---"
find "$OUT" -name '*.blame' -size +20k | head -3 | while read -r f; do
  echo "$(basename "$f"): $(cut -d';' -f1 "$f" | sort -u | wc -l)"
done
echo
echo "--- check 5: non-progress lines in log (want 0) ---"
[ -n "$LOG" ] && grep -cvE '^[0-9]+: ' "$LOG"
echo "out_dir_size=$(du -sh "$OUT" | cut -f1)"
REMOTE

  say "tar + split into $PART_SIZE parts (the long step)"
  ssmrun "packaging" <<REMOTE
set -euo pipefail
OUT=\$(cat /root/.xfer_src)
BASE=\$(basename "\$OUT"); PARENT=\$(dirname "\$OUT")
echo "packaging \$OUT"
command -v pigz >/dev/null || dnf install -y pigz >/dev/null 2>&1 || true
if command -v pigz >/dev/null; then Z="pigz -p \$(nproc)"; else Z=gzip; fi
echo "compressor: \$Z"
rm -rf $STAGE; mkdir -p $STAGE
cd "\$PARENT"
tar -cf - "\$BASE" | \$Z | split -b $PART_SIZE -d -a 3 - $STAGE/gcj-blame.tar.gz.part
cd $STAGE
sha256sum gcj-blame.tar.gz.part* > SHA256SUMS
cat gcj-blame.tar.gz.part* | sha256sum | awk '{print \$1"  WHOLE-STREAM"}' >> SHA256SUMS
ls -l; echo; cat SHA256SUMS
du -sh $STAGE
REMOTE
  [ $? -eq 0 ] || { echo "!! packaging failed -- stopping"; exit 1; }

  echo
  echo "packaged. now run:  $0 serve"
}

# ----------------------------------------------------------------------- serve
do_serve() {
  ensure_online || exit 1
  say "starting loopback HTTP server on the box (port $REMOTE_PORT)"
  ssmrun "serving" <<REMOTE
set -euo pipefail
pkill -f "http.server $REMOTE_PORT" 2>/dev/null || true
cd $STAGE
setsid nohup python3 -m http.server $REMOTE_PORT --bind 127.0.0.1 \
  > /tmp/httpd.log 2>&1 < /dev/null &
sleep 2
curl -s -o /dev/null -w 'local probe: HTTP %{http_code}\n' http://127.0.0.1:$REMOTE_PORT/SHA256SUMS
ls $STAGE
REMOTE
  [ $? -eq 0 ] || { echo "!! could not start the server"; exit 1; }

  cat <<EOF

================================================================
Opening the SSM port-forward now. LEAVE THIS RUNNING.
Then tell the agent: "tunnel is up on $LOCAL_PORT"

It will pull http://127.0.0.1:$LOCAL_PORT/<part> onto the dev-desk,
check SHA256SUMS, reassemble and extract.

When it reports success:   $0 stop
================================================================

EOF
  $A ssm start-session --target "$INSTANCE" \
    --document-name AWS-StartPortForwardingSession \
    --parameters "portNumber=$REMOTE_PORT,localPortNumber=$LOCAL_PORT"
}

# ------------------------------------------------------------------------ stop
do_stop() {
  say "stopping $INSTANCE"
  $A ec2 stop-instances --instance-ids "$INSTANCE" \
    --query 'StoppingInstances[0].CurrentState.Name' --output text
  cat <<EOF

Also remove the dead inline policy v1 attached (the boundary blocks it anyway,
so it grants nothing -- but leaving it is misleading):

  aws iam delete-role-policy --role-name $ROLE \\
    --policy-name cregit-reblame-upload --profile $PROFILE
EOF
}

case "${1:-}" in
  package) do_package ;;
  serve)   do_serve ;;
  stop)    do_stop ;;
  *) echo "usage: $0 {package|serve|stop}"; exit 2 ;;
esac
