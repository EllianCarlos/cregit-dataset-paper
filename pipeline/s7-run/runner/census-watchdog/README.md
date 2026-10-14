# Census watchdog (2026-10-09)

Approved by the user at about 12:45 UTC.

- `watchdog.sh` runs every 15 min from the transient user timer `census-watchdog.timer`
  (`systemd-run --user --on-calendar='*:0/15'`). A reboot removes the timer: start it again with
  `systemd-run --user --unit=census-watchdog --on-calendar='*:0/15' --timer-property=AccuracySec=30s --setenv=HOME=$HOME --setenv=PATH="$PATH" ~/s3-work/census-watchdog/watchdog.sh`.
- Automatic action: if batch 3 spot half a or b has no `final/DONE` and no live instance, it runs
  `~/s3-work/ec2-batch3/restart_spot.sh a|b`. At most 3 restarts per half (`restarts.a`, `restarts.b`;
  set the file back to 0 to allow more). Output in `restart-a.log`, `restart-b.log`.
- Alerts only: local batch 1 not active with work left; an EC2 census (batch2, batch3L, batch4) not
  active or with a live status older than 25 min. They go to `alerts.log`.
- The Claude session checks `alerts.log` at :23 and :53 (a session cron, gone when the session ends,
  7-day limit) and analyses and fixes each stop (restart or fix), as the user approved.
- Log of every check: `watchdog.log`.
- Stop it: `systemctl --user stop census-watchdog.timer`.
- 2026-10-09 14:37 UTC: batch 1 STOP set on purpose (rest moved to EC2); the watchdog logs it and does not alert.
- 2026-10-09 ~16:45 UTC (batch 5): a spot half counts as done only when EVERY workload on it is done:
  `restart_spot.sh --remaining a|b` (batch 3 rest plus the batch5 / batch1rest parts, each share
  minus done/OK). A lost half with work left is relaunched with all its workloads; the cap stays 3
  per half. New checks: batch5L in the EC2 list, and the combined live view
  `batch5/<a|b>1/live/progress.txt` of each spot instance that is up (ok: ": active", or ": finalized"
  while batch 3 still runs). The previous script is `watchdog.sh.orig-b3only`. Tested with stubs
  (see ~/s3-work/ec2-batch5/README.md).
- 2026-10-09 17:35 UTC: alert once when foxhound has ended and tracy still runs (tracy denylist plan).
