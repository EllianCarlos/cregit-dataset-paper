#!/usr/bin/env bash
# Census watchdog (approved by the user 2026-10-09 ~12:45 UTC). Runs every 15 min from the
# user unit census-watchdog.timer. Writes one line per check to watchdog.log, alerts to alerts.log.
# Actions it takes by itself:
#   - spot half a|b: if the half has work left in ANY of its workloads (batch 3 rest, and since
#     2026-10-09 ~17:00 UTC the batch5 / batch1rest parts; restart_spot.sh --remaining counts every
#     share minus done/OK) and no live instance, run ~/s3-work/ec2-batch3/restart_spot.sh <a|b>,
#     which relaunches all of them; at most 3 restarts per half (counter files).
# Everything else (local batch 1 stopped, an EC2 census unit not active, a STALE live status)
# is only written to alerts.log; the Claude session analyses and fixes those.
# 2026-10-09 ~20:30 UTC: the fed parts (batch 6 and later) count as work of a half (restart_spot.sh
# --remaining includes them; a relaunch queues them again), section 5 checks their live view, and
# batch6L (big EC2) is checked like the other on-demand censuses ("waiting" is ok while its waiter holds).
# 2026-10-10 ~02:50 UTC: batch 21 (DP8L supplement) is a fed workload like batches 6-20 (feed.tsv); its
# L project NetBSD__pkgsrc is in the L7-20 queue (v2 inputs), whose hold is checked in section 3.
# 2026-10-11 ~19:20 UTC: census L7-20b (rows 17-56 of the L7-20 queue, big EC2) is checked like L22. Its live
# status carries the line of the split watcher census-L7-20-split; one alert per kind for a double start
# (DOUBLE START / SPLIT CLASH), a split error, and rows before the split that L7-20 did not finish.
set -uo pipefail
here=$(dirname "$(readlink -f "$0")")
exec 9>"$here/.lock"; flock -n 9 || { echo "$(date -u +%FT%TZ) previous check still running" >> "$here/watchdog.log"; exit 0; }
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION}
export AWS_PAGER=""  # no pager for aws output
B=s3://${RUNNER_BUCKET}
S7=${RUNNER_PROJECTS}/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection/s7-run
MAXR=${MAXR:-10}  # 3 -> 6 (user, 2026-10-10 17:10 UTC), 6 -> 10 (user, 2026-10-12 ~01:40 UTC; spot a used 4)
ts() { date -u +%FT%TZ; }
alert() { echo "$(ts) ALERT $*" | tee -a "$here/alerts.log" >> "$here/watchdog.log"; }
log() { echo "$(ts) $*" >> "$here/watchdog.log"; }

# 1. spot halves (every workload of the half)
for x in a b; do
  rem=$("$HOME/s3-work/ec2-batch3/restart_spot.sh" --remaining "$x" 2>&1) || { alert "spot $x: restart_spot.sh --remaining failed: $rem"; continue; }
  left=$(sed -n 's/.* total \([0-9]*\)$/\1/p' <<<"$rem" | tail -1)
  [ -n "$left" ] || { alert "spot $x: cannot read the remaining work: $rem"; continue; }
  if [ "$left" = 0 ]; then log "spot $x: every workload DONE"; continue; fi
  live=$(aws ec2 describe-instances --filters Name=tag:Name,Values=cregit-census-batch3$x \
         Name=instance-state-name,Values=pending,running,stopping --query 'Reservations[].Instances[].InstanceId' --output text 2>&1) \
    || { alert "spot $x: describe-instances failed: $live"; continue; }
  if [ -n "$live" ]; then log "spot $x: running on $live ($left projects left: ${rem#spot $x remaining: })"; continue; fi
  n=$(cat "$here/restarts.$x" 2>/dev/null || echo 0)
  if [ "$n" -ge "$MAXR" ]; then alert "spot $x: no instance, $left projects left, restart cap $MAXR reached"; continue; fi
  echo $((n + 1)) > "$here/restarts.$x"
  alert "spot $x: no instance and $left projects left; restart $((n + 1)) of $MAXR"
  if "$HOME/s3-work/ec2-batch3/restart_spot.sh" "$x" >> "$here/restart-$x.log" 2>&1; then
    log "spot $x: restart_spot.sh ok"
  else
    alert "spot $x: restart_spot.sh failed (rc=$?), see restart-$x.log"
  fi
done

# 2. local batch 1
st=$(systemctl --user is-active census-batch1 2>/dev/null)
# 2026-10-09 14:37 UTC: the user moved batch 1's unstarted projects to EC2; STOP is on purpose.
if [ -e "${RUNNER_PROJECTS}/cregit-token-pipeline/.claude/worktrees/agent-a0a3254f563a6a4b5/STOP" ]; then
  log "batch1: $st, STOP set on purpose (rest moved to EC2)"
elif [ "$st" != active ]; then
  left=$("$S7/status.sh" 2>/dev/null | sed -n 's/.* \([0-9]*\)\/164 .*/\1/p' | head -1)
  [ "${left:-0}" -lt 164 ] && alert "batch1 (local): census-batch1 is $st with work left (${left:-?}/164 done)"
else log "batch1: active"; fi

# 2b. tracy plan (user-approved 2026-10-09 17:35 UTC): when foxhound has ended and tracy is still
# running (blame of TracyMicroArchitecture.cpp), alert once so the session applies the denylist plan.
run1=$("$S7/status.sh" 2>/dev/null | sed -n '/^running/,/^$/p')
if ! grep -q SAP__project-foxhound <<<"$run1" && grep -q wolfpld__tracy <<<"$run1" && [ ! -e "$here/.tracy-alerted" ]; then
  touch "$here/.tracy-alerted"
  alert "batch1: foxhound has ended and tracy still runs: apply the tracy denylist plan (TracyMicroArchitecture.cpp)"
fi

# 3. EC2 censuses: unit state line and age of the live status
now=$(date -u +%s)
for run in batch2 batch3L batch4 batch5L batch6L L7-20 L22 L7-20b L23 L1r; do
  line=$(aws s3 ls "$B/$run/live/progress.txt" 2>/dev/null) || { log "$run: no live status"; continue; }
  t=$(date -u -d "$(awk '{print $1" "$2}' <<<"$line")" +%s); age=$(( (now - t) / 60 ))
  head1=$(aws s3 cp "$B/$run/live/progress.txt" - 2>/dev/null | head -1)
  aws s3 ls "$B/$run/final/DONE" >/dev/null 2>&1 && { log "$run: DONE"; continue; }
  [ "$age" -gt 25 ] && { alert "$run: live status STALE (${age} min)"; continue; }
  # batch6L, L7-20, L22: "waiting" while their waiter holds the start (slots, memory, identity gate)
  grep -q -e ': active' -e ': waiting' <<<"$head1" || { alert "$run: census not active: $head1"; continue; }
  # L7-20 (2026-10-10 ~02:50 UTC): held by /bL7/ctp/STOP until census-L7-20's v2 inputs (NetBSD/pkgsrc
  # added) are uploaded; an alert if the hold is still there 1 h after the v2 SHA256SUMS is in S3
  if [ "$run" = L7-20 ] && aws s3 cp "$B/$run/live/progress.txt" - 2>/dev/null | grep -q 'STOP exists in /bL7/ctp: holding'; then
    v2=$(aws s3 ls "$B/L7-20/input/SHA256SUMS" 2>/dev/null); vt=$(date -u -d "$(awk '{print $1" "$2}' <<<"$v2")" +%s 2>/dev/null || echo "$now")
    if [ "$(aws s3 cp "$B/L7-20/input/SHA256SUMS" - 2>/dev/null | sha256sum | cut -c1-16)" = bfa9fae7123f4bba ] && [ $(( (now - vt) / 60 )) -gt 60 ]; then
      alert "L7-20: v2 inputs in S3 for $(( (now - vt) / 60 )) min but the waiter is still held (cregit-L7-20-v2swap on the big EC2)"; continue; fi
    log "$run: ok (${age} min), held until its v2 inputs are uploaded"; continue
  fi
  # L7-20b (2026-10-11): the split watcher line ("split: ...") in its progress.txt; one alert per kind
  if [ "$run" = L7-20b ]; then
    sl=$(aws s3 cp "$B/$run/live/progress.txt" - 2>/dev/null | grep -m1 '^split: ')
    for k in 'DOUBLE START' 'SPLIT CLASH' 'NOT DONE IN L7-20' 'ERROR'; do
      f="$here/.l720b-$(tr ' ' '-' <<<"$k")-alerted"
      if grep -q "$k" <<<"$sl" && [ ! -e "$f" ]; then touch "$f"; alert "L7-20b split: ${sl:0:300}"; fi
    done
    log "$run: ok (${age} min); ${sl:0:160}"; continue
  fi
  log "$run: ok (${age} min)"
done

# 4. batch5 / batch1rest parts on the spot instances: the combined live view (batch5/<x>1/live/progress.txt)
#    of an instance that is up. ok: ": active"; or ": finalized" while batch 3 still runs there.
for x in a b; do
  live=$(aws ec2 describe-instances --filters Name=tag:Name,Values=cregit-census-batch3$x Name=instance-state-name,Values=running \
         --query 'Reservations[].Instances[].InstanceId' --output text 2>/dev/null)
  [ -n "$live" ] || continue
  line=$(aws s3 ls "$B/batch5/${x}1/live/progress.txt" 2>/dev/null) || { log "spot $x b5: no live status"; continue; }
  t=$(date -u -d "$(awk '{print $1" "$2}' <<<"$line")" +%s); age=$(( (now - t) / 60 ))
  head1=$(aws s3 cp "$B/batch5/${x}1/live/progress.txt" - 2>/dev/null | head -1)
  grep -q "census-b5 on $live" <<<"$head1" || { log "spot $x b5: live status is from another instance ($live is up): ${head1:0:120}"; continue; }
  [ "$age" -gt 25 ] && { alert "spot $x b5: live status STALE (${age} min)"; continue; }
  fedh=$(aws s3 cp "$B/feed/$x/live/progress.txt" - 2>/dev/null | head -1)
  if grep -q ': active' <<<"$head1"; then log "spot $x b5: ok (${age} min)"
  elif grep -q ': finalized' <<<"$head1" && grep -q 'batch3=active' <<<"$head1"; then log "spot $x b5: finalized, batch 3 still running (${age} min)"
  elif grep -q ': finalized' <<<"$head1" && grep -q -e ': active' -e ': waiting' <<<"$fedh"; then log "spot $x b5: finalized, fed parts running or queued (${age} min)"
  else alert "spot $x b5: not active: $head1"; fi
done

# 5. fed parts (batch 6 and later; since 2026-10-09 ~20:30 UTC) on the spot instances: the combined view
#    feed/<x>/live/progress.txt of an instance that is up. ok: ": active" or ": waiting" (queued parts
#    wait for a slot, memory or their workload's cregit commit); ": finalized" is ok (the instance
#    terminates when its last census finalizes). ": paused" (a failed part-init or identity check),
#    ": stopped" and ": interrupted" are alerts. A "waiting" for a pending cregit commit is logged.
for x in a b; do
  live=$(aws ec2 describe-instances --filters Name=tag:Name,Values=cregit-census-batch3$x Name=instance-state-name,Values=running \
         --query 'Reservations[].Instances[].InstanceId' --output text 2>/dev/null)
  [ -n "$live" ] || continue
  line=$(aws s3 ls "$B/feed/$x/live/progress.txt" 2>/dev/null) || { log "spot $x fed: no live status"; continue; }
  t=$(date -u -d "$(awk '{print $1" "$2}' <<<"$line")" +%s); age=$(( (now - t) / 60 ))
  head1=$(aws s3 cp "$B/feed/$x/live/progress.txt" - 2>/dev/null | head -1)
  grep -q "census-fed on $live" <<<"$head1" || { log "spot $x fed: live status is from another instance ($live is up): ${head1:0:120}"; continue; }
  [ "$age" -gt 25 ] && { alert "spot $x fed: live status STALE (${age} min)"; continue; }
  if grep -q -e ': active' -e ': finalized' <<<"$head1"; then log "spot $x fed: ok (${age} min): ${head1:0:160}"
  elif grep -q ': waiting' <<<"$head1"; then log "spot $x fed: waiting (${age} min): $(sed -n 's/.*feeder: \(.*\)  b5=.*/\1/p' <<<"$head1" | cut -c1-140)"
  else alert "spot $x fed: $head1"; fi
done
