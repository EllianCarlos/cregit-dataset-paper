#!/usr/bin/env bash
# R6-more-jobs.sh, machine A (root, through scripts/a/ssm-a.sh; written 2026-10-20; user decision
# 2026-10-20 "More jobs + merge without them"). Gives the slow step-7 rows more blame jobs:
#   1. checks: asuswrt-merlin.ng and google-cloud-rust are uploaded (done-full OK) and inactive;
#   2. touches /home/ec2-user/NO_SHUTDOWN (so no finalize can power off during the change);
#   3. for each row of NEWJOBS that is active and in step 7: systemctl stop (SIGTERM to ctp, which only
#      stops new projects; SIGKILL to all after TimeoutStopSec=60; the runner's clean-up trap acts only
#      with FROM_STEP=1, and these runs have --from-step 7), JOBS= in run.env (old file kept as
#      run.env.before-R6), reset-failed, start; then it checks the new start line: "from-step 7" and
#      "blame-jobs <new>";
#   4. removes NO_SHUTDOWN only when every change passed; else it keeps it and says so.
# tencentcloud-sdk-cpp keeps 16 jobs. Total blame jobs after the change: 176 of 192 vCPU.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}) echo "ABORT: $IID is not machine A"; exit 1 ;; esac
L=/data/x1k-long
NEWJOBS="awslabs__aws-sdk-rust:64 aws__aws-sdk-java:44 metashell__metashell:20 autc04__Retro68:20 microsoftgraph__msgraph-beta-sdk-java:12"
echo "== $(date -u +%FT%TZ) R6 on $IID"
for p in RMerl__asuswrt-merlin.ng googleapis__google-cloud-rust; do
  T=$(readlink -f $L/$p)
  if systemctl is-active -q x1k-long@$p || [ ! -e $T/uploaded/$p ]; then echo "ABORT: $p is not done (unit $(systemctl is-active x1k-long@$p), uploaded: $([ -e $T/uploaded/$p ] && echo yes || echo no))"; exit 1; fi
  echo "$p: done and uploaded"
done
echo "memory before: $(free -g | sed -n 2p)"
had=0; [ -e /home/ec2-user/NO_SHUTDOWN ] && had=1
touch /home/ec2-user/NO_SHUTDOWN; echo "NO_SHUTDOWN set (it existed before: $had)"
bad=0
for pj in $NEWJOBS; do p=${pj%%:*}; j=${pj##*:}; T=$(readlink -f $L/$p); PL=$T/out/$p/pipeline.log
  old=$(sed -n 's/^JOBS=//p' $T/run.env)
  if ! systemctl is-active -q x1k-long@$p; then echo "$p: unit not active, skipped"; continue; fi
  st=$(grep -a -E '^  Step [0-9]+ ' $PL | tail -1 | awk '{print $2}')
  if [ "$st" != 7 ]; then echo "$p: newest step heading is $st, not 7: skipped"; continue; fi
  if [ "$old" = "$j" ]; then echo "$p: JOBS is already $j, skipped"; continue; fi
  nb0=$(find $T/out/$p/blame -name '*.blame' 2>/dev/null | wc -l)
  echo "$p: stop (JOBS $old -> $j; .blame $nb0) at $(date -u +%T)"
  systemctl stop x1k-long@$p
  for i in $(seq 1 30); do systemctl is-active -q x1k-long@$p || break; sleep 5; done
  if systemctl is-active -q x1k-long@$p; then echo "  ERROR: $p still active; not changed"; bad=1; continue; fi
  left=$(ps -eo args | awk -v t="$T/" 'index($0, t) && $1 != "awk"' | wc -l)
  echo "  stopped at $(date -u +%T); processes with the tree path left: $left"
  [ -f $T/run.env.before-R6 ] || cp -p $T/run.env $T/run.env.before-R6
  sed -i "s/^JOBS=.*/JOBS=$j/" $T/run.env
  grep -q "^JOBS=$j\$" $T/run.env || { echo "  ERROR: run.env not changed"; bad=1; continue; }
  n0=$(grep -a -c '=== .* x1k-long' $T/logs/run.log)
  systemctl reset-failed x1k-long@$p 2>/dev/null; systemctl start x1k-long@$p
  for i in $(seq 1 24); do [ "$(grep -a -c '=== .* x1k-long' $T/logs/run.log)" -gt "$n0" ] && break; sleep 5; done
  sl=$(grep -a '=== .* x1k-long' $T/logs/run.log | tail -1)
  echo "  start line: $(echo "$sl" | cut -c1-80) ... $(echo "$sl" | grep -o 'last completed step.*')"
  if echo "$sl" | grep -q "from-step 7," && echo "$sl" | grep -q "blame-jobs $j,"; then
    sleep 20; echo "  OK: unit $(systemctl is-active x1k-long@$p); .blame $(find $T/out/$p/blame -name '*.blame' | wc -l)"
  else echo "  ERROR: start line is not 'from-step 7' with 'blame-jobs $j'"; bad=1; fi
done
sleep 60
echo "git blame processes per volume now:"; for K in 1 2 3 4; do echo "  /data$K: $(ps -eo args | awk -v k="/data$K/" '$1=="git" && $0 ~ "blame" && $0 ~ k' | wc -l)"; done
echo "memory after: $(free -g | sed -n 2p)"; uptime
if [ $bad = 0 ] && [ $had = 0 ]; then rm -f /home/ec2-user/NO_SHUTDOWN; echo "NO_SHUTDOWN removed: the finalize can power off again"
elif [ $bad = 0 ]; then echo "NO_SHUTDOWN existed before R6: kept"
else echo "WARNING: a change failed: NO_SHUTDOWN kept; check and remove it by hand"; fi
echo "R6 (machine A) done, errors $bad"
exit $bad
