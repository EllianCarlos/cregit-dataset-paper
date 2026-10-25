#!/usr/bin/env bash
# R10-retry-rust.sh, machine A (root, through scripts/a/ssm-a.sh; 2026-10-23). The aws-sdk-rust row stopped at
# 14:19 UTC: ctp counts each interrupted attempt (the R8 and pull restarts) as a failure, and 11 > --retries 10.
# This script raises RETRIES in run.env to 30 (old file kept as run.env.before-R10), starts the row again (it
# resumes at step 7 with the finished .blame files kept), checks the start line and that blame runs, and only
# then removes the R8 ALERT file and the NO_SHUTDOWN file that R8 set (R8 log: "it existed before: 0").
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
p=awslabs__aws-sdk-rust; L=/data/x1k-long; T=$(readlink -f $L/$p); U=x1k-long@$p
echo "== $(date -u +%FT%TZ) R10 on $IID"
systemctl is-active -q $U && { echo "ABORT: $U is active"; exit 1; }
grep -a -q "$p — failed 11 times .* more than --retries 10; not retried" $T/logs/run.log \
  || { echo "ABORT: the last stop of the row is not the retry limit"; tail -5 $T/logs/run.log; exit 1; }
grep -q '^RETRIES=10$' $T/run.env || { echo "ABORT: run.env has no RETRIES=10"; exit 1; }
[ -f $T/run.env.before-R10 ] || cp -p $T/run.env $T/run.env.before-R10
sed -i 's/^RETRIES=10$/RETRIES=30/' $T/run.env
grep -q '^RETRIES=30$' $T/run.env || { echo "ABORT: run.env not changed"; exit 1; }
echo "run.env: $(tr '\n' ' ' < $T/run.env | sed 's#META=[^ ]*#META=...#')"
n0=$(grep -a -c '=== .* x1k-long' $T/logs/run.log)
systemctl reset-failed $U; systemctl start $U
for i in $(seq 1 24); do [ "$(grep -a -c '=== .* x1k-long' $T/logs/run.log)" -gt "$n0" ] && break; sleep 5; done
sl=$(grep -a '=== .* x1k-long' $T/logs/run.log | tail -1)
echo "start line: $(echo "$sl" | grep -o 'last completed step.*' | cut -c1-160)"
echo "$sl" | grep -q 'from-step 7,' && echo "$sl" | grep -q 'retries 30' \
  || { echo "ERROR: start line is not from-step 7 with retries 30; ALERT and NO_SHUTDOWN kept"; exit 1; }
sleep 60
if ! systemctl is-active -q $U; then echo "ERROR: $U is not active 60 s after the start"; tail -6 $T/logs/run.log; exit 1; fi
nb=$(ps -eo args | awk -v t="$T/" '$1 ~ /git$/ && $0 ~ /blame/ && index($0, t)' | wc -l)
echo "unit active; git blame processes of the row: $nb; .blame files: $(find $T/out/$p/blame -name '*.blame' | wc -l)"
[ "$nb" -gt 0 ] || { echo "ERROR: no git blame process; ALERT and NO_SHUTDOWN kept"; tail -6 $T/logs/run.log; exit 1; }
rm -f $L/rebalance.ALERT /home/ec2-user/NO_SHUTDOWN
echo "rebalance.ALERT and NO_SHUTDOWN removed; R10 done $(date -u +%FT%TZ)"
