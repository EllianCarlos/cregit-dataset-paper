# Census batch 4 on EC2 (2026-10-09)

Batch 4 = rows 493-656 of `frame.layer1.csv` (`rows[3*limit:4*limit]`, limit 164), all size
classes, 164 projects. The manifests are in ${RUNNER_STUDY_REPO} `dataset-selection/s7-run`, commit
526e437 (`build_run.sh` + `split_batch4.py`). Account ${RUNNER_AWS_ACCOUNT}, ${RUNNER_AWS_REGION}, profile
`${RUNNER_AWS_PROFILE}`. Bucket `s3://${RUNNER_BUCKET}` (B below). Every command:
`export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""` first. The shell's
default profile is another account.

It runs on the batch 2 on-demand instance ${RUNNER_EC2_BIG} (m6id.24xlarge, ${RUNNER_AWS_REGION}a). It runs
next to census-batch2 and census-batch3L, and neither of those was restarted or changed.

| part | projects | S | M | L | filesystem | ctp clone | output |
|---|---|---|---|---|---|---|---|
| batch4p1 | 55 (rows 1, 4, 7 ...) | 47 | 7 | 1 (microsoft__lvbs-linux) | /b4p1 | /b4p1/ctp | /b4p1/census-2026-10-batch4 |
| batch4p2 | 55 (rows 2, 5, 8 ...) | 43 | 10 | 2 (llvm-mos__llvm-mos, ceph__ceph) | /b4p2 | /b4p2/ctp | /b4p2/census-2026-10-batch4 |
| batch4p3 | 54 (rows 3, 6, 9 ...) | 47 | 7 | 0 | /b4p3 | /b4p3/ctp | /b4p3/census-2026-10-batch4 |

Started at 13:19:01 UTC (measured). The units are `census-batch4p1`, `census-batch4p2` and `census-batch4p3`.
Each runs `/usr/local/bin/census-batch4-run K` with:
`--workers 4 --retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300`
and `OOMPolicy=continue`.
- Same cregit build 95cdc88: /data/cregit-ec2 until 13:39 UTC, since then a per-part copy
  /b4pK/cregit-ec2 (see "Per-part cregit copies").
- Same ctp: ca113e3, from `batch2/input/ctp.bundle`, with its own venv (Python 3.12.14, duckdb 1.5.5).
- Inputs: `~ec2-user/batch4-input`, copied from `batch4/input/`. sha256sum -c passed on the instance.
- Logs: `/data/logs/batch4pK.log`.

## Why loop filesystems

Step 2 on this instance waits on cross-directory `rename()`, which is serialised per filesystem
(`s_vfs_rename_mutex`). See `s7-run/ec2-load-20261009.md`.

Each part therefore has its own filesystem: a sparse 1200 GiB image `/data/loop/b4pK.img`, formatted
mkfs.xfs and loop-mounted at `/b4pK`. Each image is a separate superblock (measured 13:08):
- stat -f fsid 70000000000 / 70100000000 / 70200000000, against /data 90000000000;
- devices loop0, loop1, loop2.

The RAID0 /data itself was not changed. The fstab lines are
`/data/loop/b4pK.img /b4pK xfs loop,noatime,discard,nofail,x-systemd.requires-mounts-for=/data 0 0`,
so the mounts come back after a reboot. The censuses do not restart on their own after a reboot.

### Sizing

- **Linux fork in p1:** torvalds/linux used 435 GB in batch 1. The 1200 GiB image with the 300 GB floor
  leaves about 900 GB before p1 stops starting new projects. Finished projects shrink to about
  1 GB (measured on batch3L).
- **llvm-mos in p2:** llvm__llvm-project used 133 GB on batch3L at 13:05, still running.
- **Disk floor:** ctp measures it with `shutil.disk_usage(OUT)`, and OUT is on the loop filesystem
  (ctp.py lines 982 and 1511), so the floor applies to the loop filesystem, not to /data.
- **Inferred peak:** about 600 GB on p1 and about 450 GB on p2.

### Guard for /data

The images are sparse, so they take /data space only as they are written.
`census-batch4-guard.timer` (root, every 10 min) does two things:

1. `fstrim` on each /b4pK. This hands the blocks of deleted clones back to /data. Measured 13:12:
   the discard mount option alone did not shrink the image after a 2 GiB write and rm; fstrim did,
   from 2649M to 696M.
2. If /data has less than 800 GiB free, it writes STOP in all three batch 4 ctp clones and
   `batch4/live/GUARD`. Then batch 4 cannot fill /data under batch 2 and batch 3L.

/data had 4780 GiB free at 13:19.

## Identity check (before the start)

The libexpat check ran on /b4p1, with its own clone `/b4p1/ctp-check` and a scratch output
`/b4p1/libexpat-check/out`. It used the batch 2 flags:
`--workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10`.

Result: Parquet sha256 40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d, which
equals the reference (measured 13:12, 146 s). The log is `/data/logs/check-b4.log`.

## Watch

    aws s3 cp s3://${RUNNER_BUCKET}/batch4/live/progress.txt - | head -40
    aws s3 cp s3://${RUNNER_BUCKET}/batch4/live/steps.txt -    # per part, L projects first
    aws s3 ls  s3://${RUNNER_BUCKET}/batch4/live/

`census-batch4-live.timer` (every 10 min) writes these files:
- `progress.txt`. Its first line is
  `as of <ts>  census-batch4: active ( p1=active p2=active p3=active )  finalize=inactive`; the local
  watchdog greps for ": active". Then come the batch 2 and 3L states, load, memory, /data free, the
  guard line, and per part: unit state, free space on /b4pK, ctp progress and the step table.
- `steps.txt`
- `batch4pK.log.tail`
- `ledger.pK.jsonl`
- `system.txt` (PSI, meminfo, df, and the image sizes)

## Stop

Run as root via SSM, with a one-line script: `I=${RUNNER_EC2_BIG} scripts/ssm.sh <script>`.

- All of batch 4 after the running projects: `for k in 1 2 3; do touch /b4p$k/ctp/STOP; done`.
  Then the finalize copies and writes DONE.
- One part: `touch /b4pK/ctp/STOP`.
- Resume a part later: remove its STOP and `systemctl start census-batch4pK`.
- Keep the instance up after every census: `touch /home/ec2-user/NO_SHUTDOWN`. This also holds the
  batch 2 and 3L finalizes.

## Finalize and the power-off rule

- **When it runs.** Every part has `OnSuccess=`/`OnFailure=census-batch4-finalize.service`. The finalize
  waits until no part is active, so the first part to end does not finalize alone.
- **What it does.** It copies all parts to `batch4/final/`: Parquet and .validated per project, then
  each part's ledger, duckdb, state json and logs, then the logs and manifests. It checks every
  object (key and size) and that SHA256SUMS reads back byte-identical, then writes `batch4/final/DONE`.
- **Power-off rule (2026-10-09).** The instance powers off (stop, not terminate) only when EVERY census
  on it has finalized:
  - batch2: `batch2/final/DONE` exists and `census-batch2` is not active;
  - batch3L: `batch3L/final/DONE` exists and `census-batch3L-wait` and `census-batch3L` are not active;
  - batch4: `batch4/final/DONE` exists and `census-batch4p1`, `p2` and `p3` are not active.

  `/usr/local/bin/census-other-done SELF` checks all the censuses except SELF. Each finalize writes
  its own DONE before it asks, so only the last one powers off.
- **Old guards kept.** There is no power-off if the check fails, if the census (for batch 4: its
  longest part) ran < 1 h, or if `/home/ec2-user/NO_SHUTDOWN` exists.
- **Interface unchanged.** census-other-done keeps its interface (`batch2|batch3L`, plus `batch4`).
  The batch 2 and batch 3L finalize scripts were therefore not edited:
  - census-batch2-finalize sha256 dbd1050b... and census-batch3L-finalize ec8b3b4d..., both checked
    before the install;
  - their only caller of the new rule is the existing `census-other-done $SELF` call;
  - the old 2-census version is kept as `/usr/local/bin/census-other-done.orig-2census` (sha256 36c27cd7...).
- **Test overrides:** `DONE_URL_<census>` and `UNITS_<census>` (empty = no units).

Tests, 13:18 UTC (measured). Nothing powered off, and batch 2 and 3L kept running:

| test | case | result |
|---|---|---|
| T1-T3 | each census asked with the real state | rc 1 (batch 2 or batch 3L active) |
| T4 | batch2, with batch3L faked done | rc 1 (`batch4/final/DONE` missing): the new rule |
| T5 | batch4, with batch2 and batch3L faked done (`*/dryrun/DONE`, no units) | rc 0 |
| T6 | batch3L, with batch2 and batch4 faked done | rc 0 |
| T7 | bad argument | rc 2 |
| T8 | `--decide-only` of all three finalizes | "no power-off" each |
| T9 | `census-batch4-finalize --dry-run` on the libexpat check output (p2 and p3 empty) | 20 objects in `batch4/dryrun/`, check ok, DONE, "no power-off" |

### daemon-reload

New unit files needed a daemon-reload. It was done only after checking that `NeedDaemonReload=no`
for every batch 2 and batch 3L unit, so the reload re-read the same files and changed nothing.
A reload never restarts a running service. The MainPID and start time of census-batch2 (79486,
02:52:35) and census-batch3L (3564058, 07:25:11) were the same before and after (measured).
Both still run with OOMPolicy=stop, as before.

## Per-part cregit copies (restart 13:33-13:39 UTC)

**Why.** `tokenWorker.pl` makes its temp dirs in `$RealBin/build`. With the shared build that was
`/data/cregit-ec2/tokenizeByBlobId/build`, one directory used by every census (batch 2, 3L and 4).
So the loop filesystems did not separate that directory's lock. At 13:22, about 360 batch 4 and 40
batch3L perl workers were blocked (D state) in mkdir, rmdir, unlink and rename there (measured).

**Fix (user decision 13:35).** Each part now has its own copy of the checked build at
`/b4pK/cregit-ec2`, with an empty `tokenizeByBlobId/build`. Each part's config has `cregit_dir`
pointing at its copy; the old configs are kept as `census-batch4pK.cfg.data-cregit`.

**How the copy was made (measured).**
- Made with tar (`-p`), leaving out the temp entries in `build/`. Owner is ec2-user.
- HEAD is 95cdc88 and `git status` is clean in each copy.
- The blobExec jar sha256 is the same in all copies.
- `diff -rq` against /data/cregit-ec2, ignoring build/ and .devenv, shows only `.git/index`. That is
  index stat data, not content.

**Checks on /b4p1/cregit-ec2 (measured).**
- Via the copy's own devenv shell, libsrcml.so.1.1.0 is in
  `/nix/store/g6xii595...-srcml-1.1.0-unstable-2026-10-04` with sha256
  dea4467b...55f3, equal to the reference.
- libexpat check with a fresh clone `/b4p1/ctp-check2`, scratch output `/b4p1/libexpat-check2/out`
  and the same flags: Parquet sha256 40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d,
  identical (236 s).

**Hold during the restart.** I did not use a mask, because the unit file is in /etc/systemd/system,
where `systemctl mask` cannot add its link. Instead, `census-batch4-finalize` honours a hold flag
`/run/census-batch4-hold`: while it exists, a real finalize logs "hold ... no finalize" and exits.
`census-batch4-live` then writes `census-batch4: restarting (hold: ...)` as the first line.
- When the three parts ended at 13:39:14, the finalize ran three times and held each time (journal).
- `batch4/final/` stayed empty.
- The flag was removed before the restart. /run is cleared at reboot, so it cannot stick.

**Stop and restart.**
- 13:33:17: STOP written in /b4pK/ctp; no new projects started.
- 13:38:24: SIGTERM to each ctp main process (`systemctl kill --kill-whom=main`). With STOP already
  set, this terminates the running projects, and ctp records them as failed.
- 13:39:14: all three parts ended; restarted at 13:39:25. `OOMPolicy=continue` is unchanged.
- Projects finished before the stop: p1 7, p2 5, p3 2. Running at STOP and the ones terminated are
  recorded in `/data/logs/batch4-restart-20261009.txt`.
- Terminated: net-snmp__net-snmp, CrispStrobe__CrispASR (p1); rism-digital__verovio,
  projectacrn__acrn-libvirt, apache__camel-spring-boot (p2); kovidgoyal__kitty, peercoin__peercoin (p3).
- testng, moveit2, gnome-commander, ocornut__imgui and pytorch__FBGEMM finished before the SIGTERM.

**The step-2 resume did not work (measured).**
- The 7 terminated projects resumed at step 2 as expected, but each failed at once. blobExec stores
  the tokenizer command path in the blob map and refuses an incremental run with another one:
  `meta mismatch on 'command': stored='/data/cregit-ec2/tokenizeByBlobId/tokenBySha.pl',
  requested='/b4p1/cregit-ec2/...'`.
- At 13:44 their work dirs were moved to `<out>/.superseded-20261009/<project>`. The finalize skips
  dot dirs; the pinned repos in `.ctp-pinned` stay. Their queued retry (attempt 3 of 4; each has 2
  failures so far) therefore starts from step 1.
- These retries run after the rest of each part's queue.
- If one of them fails twice more, ctp gives it up. A later run would need its ledger history
  handled.

**Tokenizer workers after the restart (measured, 13:41-13:46).**
- Each part's perl workers run in its own copy: about 290-390 per part, in `/b4pK/cregit-ec2`.
  batch3L's 194 stay in `/data/cregit-ec2`.
- D-state: before the stop, at 13:38 with 679 workers all in /data/cregit-ec2, there was 1. That is
  bursty; the earlier readings were 13:22: 362 batch 4 + 40 batch3L, and 13:27: 68 batch 4.
- After the restart: 13:41 2; 13:42 77 p1 + 88 p3; 13:45-13:46 between 4 and 144, always in batch 4
  units only, with batch3L 0.
- So batch 4 no longer contends with batch3L on that directory. Within a part, its 4 projects still
  share one build dir.

After the restart, `--decide-only` of all three finalizes and `census-other-done batch4` all said
no power-off (rc 1, batch 2 active).

## Costs (inferred)

- **Price.** The instance costs about $5.70/h on demand, whether or not batch 4 runs. Batch 4 uses
  the spare slots: batch 2 had 3 projects left and batch3L 4.
- **What it costs extra.** Batch 4 extends the instance's life only if it ends after LineageOS
  (batch 2) and the batch3L L projects.
- **How long it may run.** Linux took a 1,500 min pipeline locally in batch 1, with the older code.
  lvbs-linux is a Linux fork, so batch 4 may well run 10-25 h, which is $57-143 at $5.70/h.
- **Storage.** The loop images live on the instance-store RAID0. A stop loses them, so the finalize
  must have copied everything first.

## Files

- `upload/`: the batch 4 inputs as uploaded to `batch4/input/` (with SHA256SUMS).
- `scripts/remote/`: everything installed on the instance:
  - `census-other-done` (all censuses);
  - `census-batch4-run`, `census-batch4-live`, `census-batch4-finalize`, `census-batch4-guard`;
  - the units `census-batch4p{1,2,3}.service`, `census-batch4-finalize.service`,
    `census-batch4-live.{service,timer}` and `census-batch4-guard.{service,timer}`.
- `scripts/p*.sh`: the SSM steps in order:
  - p1-probe;
  - p3-setup (images, fstab, inputs, clones, configs);
  - p4-check (libexpat);
  - p5-install (install + power-off tests; output `p5-install.out`);
  - p6-start (output `p6-start.out`);
  - q1-q7 for the copy restart: q2 hold + STOP + copy + check (`q2.out`); q3 stop/restart
    (`q3.out`); q6 moving the terminated work dirs aside; q7 decide-only. The pre-hold scripts
    are in `scripts/old/`.
- `scripts/ssm.sh` (with `AWS_PAGER=""`) and `scripts/mkinstall.sh`, from batch 3.
