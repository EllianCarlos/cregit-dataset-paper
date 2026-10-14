# Census batch 6 and the part feeder (2026-10-09)

The user approved this at about 19:25 UTC ("Prepare now, start as parts drain"). Account ${RUNNER_AWS_ACCOUNT},
${RUNNER_AWS_REGION}, profile `${RUNNER_AWS_PROFILE}`. Bucket `s3://${RUNNER_BUCKET}` (B below).

Run `export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""` before every command,
because the shell's default profile belongs to another account.

## State at 20:40 UTC

Measured unless marked.

- **The feeder is armed on both spot instances.** It holds batch 6 until the new cregit commit is set.
  - **Decision at ~19:55 UTC (the user's):** batches 6-20 run on a new cregit commit. That commit makes `generate_dataset.py` read the commit trailers from the step 3 original DB. It is on branch `fix/trailers-original-db` in `${RUNNER_PROJECTS_TILDE}/cregit-trailers`, off 95cdc88, and has its own libexpat gate sha256.
  - **Until the coordinator sends the commit and the gate sha256:**
    - the batch 6 workload on each spot instance has `CREGIT_COMMIT=pending`;
    - the batch6L waiter on the big EC2 finds no passed gate.
  - **So nothing of batch 6 has started.**
- **The first free slot:** census-b5@batch5b2 on spot b ended at 20:15:04 UTC. The b5 finalize waits for the other 4 parts.
- **No running census unit was changed:** b3, b5, batch2, batch3L, batch4 and batch5L keep 95cdc88. Every daemon-reload ran only after NeedDaemonReload=no on every loaded census unit. The MainPID and start time of the running units were the same before and after each reload.

## Batch 6

Built in ${RUNNER_STUDY_REPO} `dataset-selection/s7-run`, commit c9e635d.

- **Rows:** 821-984 of frame.layer1.csv. The workload was built only with `bash build_run.sh batch 6`, so the sidecar carries license, owner_type, archived and fork.
- **Size:** 164 projects (S 137, M 24, L 3), with 0 names shared with batches 1-5.
- **Split:** `split_batchN.py 6`. It works for any N >= 6.
  - The 3 L projects go to **batch6L**: rockchip-linux__kernel, beagleboard__linux, Xilinx__llvm-aie. Predicted 34.7, 39.4 and 16.2 h (inferred).
  - The 161 S and M projects go to 10 parts of 4 workers: a1-a5 for spot a, b1-b5 for spot b.
  - The balancing is LPT over all 40 workers, on the predicted time of split_batch5.py.
  - Each part keeps u order.
  - In each half, part 1 has the longest predicted wall time, so the feeder starts it first.

  | part | projects | predicted work / wall (inferred) |
  |---|---|---|
  | a1 | 4 (4 M) | 15.9 h / 5.0 h |
  | a2 | 9 | 6.9 / 1.8 |
  | a3 | 23 | 6.8 / 1.7 |
  | a4 | 19 | 6.9 / 1.7 |
  | a5 | 20 | 6.8 / 1.7 |
  | b1 | 4 (4 M) | 9.2 / 2.8 |
  | b2 | 20 | 6.9 / 1.7 |
  | b3 | 22 | 6.8 / 1.7 |
  | b4 | 24 | 6.9 / 1.7 |
  | b5 | 16 | 6.9 / 1.7 |

- **Inputs:** `B/batch6/input/`, 8 objects. They are the files of `upload/`, with SHA256SUMS. The user uploaded them at 19:49:43 UTC, and a read-back check passed.
- **On the instances:** `census-fed-derive` (a copy of split_batchN.py, run as `--derive DIR batch6`) rebuilds the part manifests. On both spot instances, 5 of 5 sha256 equal `parts.batch6.tsv`.

## The feeder (spot instances)

All paths below are on the instance. The files are in `scripts/remote-spot/`; `scripts/gen-s6-files.sh` builds `s6-files-0/1/2.sh`.

**State files.**
- `/etc/cregit-census/fed/half`: the half, a or b.
- `/etc/cregit-census/fed/queue`: one `<workload> <part>` per line, next first.
- `/etc/cregit-census/fed/started`: the started ids, in order.
- `/etc/cregit-census/fed/<id>.env` and `<id>.cfg`.
- `/etc/cregit-census/fed/wl/<workload>.env`: the workload's cregit commit (see below).
- `/etc/cregit-census/fed/PAUSE`.
- `/etc/cregit-census/fed/slots` (default 5).

**census-fed-feeder** runs from `census-fed-feeder.timer` every minute, and also from each fed finalize.
- It counts the running parts: `census-b5@<id>` plus `census-fed@<id>`. The batch 3 tail does not count.
- While fewer than `slots` (5) run and the queue is not empty, it takes the head part and does these steps in order:
  1. Its workload's commit must be set: `pending` waits.
  2. `census-fed-part-init` builds the part's environment:
     - its own sparse loop-XFS image, 1200G. On a it goes on the /dataK with the most free space; on b on the RAID0 /data. It is mounted at `/w/<id>`.
     - its own ctp clone, ca113e3;
     - its own cregit copy `/w/<id>/cregit-ec2`, a tar of /data/cregit-ec2 with an empty `tokenizeByBlobId/build`. The copy is checked out at the workload's `CREGIT_COMMIT`, from the git bundle in S3 (sha256-checked). Its path and commit are fixed before the census starts.
  3. The run manifest is the part manifest minus every project with done/OK.
  4. **`census-fed-check`** runs the identity gate on this new copy, for every part:
     - the copy is at the workload's commit;
     - libsrcml sha256;
     - the libexpat Parquet sha256 equals the workload's `WANT_PQ`;
     - the blobExec jar equals /data/cregit-ec2.
  5. The id is appended to `started`, then removed from `queue`, then `census-fed@<id>` starts.
- The census flags are those of the b5 parts: `--workers 4 --retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb min(300, size/4)`, with `OOMPolicy=continue`.
- **It holds:**
  - after a spot notice (`/run/census-spot-interrupted`);
  - while PAUSE exists;
  - while MemAvailable < 64 GiB.
- **A failed part-init or gate** writes PAUSE and leaves the part at the head of the queue. The watchdog alerts on "paused". Look at the reason, then `rm /etc/cregit-census/fed/PAUSE`.

**census-fed-finalize@<id>** runs on OnSuccess and OnFailure of each part, one part at a time (made from census-b5-finalize).
- It copies the part to `B/<wl>/<part>/final/<iid>/` and writes DONE there.
- When every project of the part has done/OK, it also writes `B/<wl>/<part>/final/DONE`.
- Then it runs the feeder (the next queued part starts in this slot) and asks census-spot-decide.

**Uploads.**
- `census-fed-upload` (every minute) writes `B/<wl>/<part>/done/<project>/`. It is census-b5-upload with only `parts()` changed.
- `census-fed-live` (every 10 min) writes the combined view `B/feed/<x>/live/progress.txt`, and the same files in each started part's `B/<wl>/<part>/live/`.
- The first line of the combined view is: `as of <ts>  census-fed on <iid> (spot <x>): active|waiting|paused|interrupted|finalized|stopped ( <id>=<state> ... )  queue=<n> (<next>)  feeder: <status>  b5=<active>/<n>  batch3=<state>`.

**Spot notice.** `census-fed-watch` (IMDSv2 every 5 s) handles it:
- it writes `/run/census-spot-interrupted`;
- it writes STOP into every started fed clone;
- it writes INTERRUPTED and the ledger to `live/`;
- it runs one upload pass.

**Workload commit.** `census-fed-workload <wl>` sets it, in one of three forms:
- `--commit SHA --bundle S3URL --bundle-sha256 H --want-pq H [--want-srcml H]`;
- `--base` (95cdc88 with the batch 5 values);
- `--pending`.

It refuses to change the commit once a part of that workload has started.

**Batch 7 and later:**
1. Build and split the batch: `build_run.sh batch 7`, then `split_batchN.py 7`.
2. Stage and have the user upload `B/batch7/input/`.
3. Add a line to `feed.tsv`.
4. Run on each spot instance: `census-fed-workload batch7 ...`, then `census-fed-enqueue batch7`.

## Termination rule (spot)

`/etc/cregit-census/censuses` is now `b3 b5 fed` on both instances.

`census-spot-decide` (new; the old one is kept as `census-spot-decide.orig-b3b5`) counts **fed** as finalized only when ALL of these hold:
- the queue is empty;
- no `census-fed@<id>` of the started list is active;
- `B/<wl>/<part>/final/<iid>/DONE` exists for every started part.

A part being started is always seen: it is in `started` before it leaves `queue`. Each finalize (b3, b5, fed) asks the decide script after writing its own DONE, so the last one terminates the instance. The guards are kept:
- `NO_SHUTDOWN`;
- a failed copy;
- `--dry-run`;
- a part that ran < 1 h with no done/OK.

## batch6L on the big EC2 (${RUNNER_EC2_BIG})

**Layout.**
- Loop XFS `/data/loop/b6L.img` (2000G sparse) at `/b6L`, fsid 70400000000.
- ctp clone `/b6L/ctp` (ca113e3) and cregit copy `/b6L/cregit-ec2`.
- Output `/b6L/census-2026-10-batch6L`, log `/data/logs/batch6L.log`, inputs `~ec2-user/batch6-input`.
- `census-batch6L.service` has `OOMPolicy=continue` and `--workers 3`.

**Identity gate at 95cdc88**, 19:55-20:00 UTC: libsrcml dea4467b…55f3, libexpat 40511e0d…fc5d (259 s), jar 3daa1201…, tree diff 1 line (.git/index).

**Commit.** The census needs the new commit: `census-batch6L-cregit --commit ... | --base` checks the copy out and gates it again, and writes `/etc/cregit-census/batch6L.gate`.

**census-batch6L-wait** (active since 20:23 UTC) starts census-batch6L once ALL of these hold:
1. Batch 4 has no project it has not started (each part inactive, or `census-steps --counts` shows 0 not started).
2. At most 16 projects run on the instance, so 19 at most with the 3 L projects. That is about the 20 slots of batches 2-4.
3. MemAvailable ≥ 120 GiB.
4. /data has ≥ 1500 GiB free, well above the 800 GiB guard.
5. The gate file's last line is `CHECK OK … cregit <the copy's HEAD>`.

Why this rule: it is the safe rule the user asked for at ~20:15 UTC. The L projects of batches 6-20 may finish as late as 2026-10-20 20:00 UTC, so the L start waits for free slots and memory instead of pushing the instance. At 20:23 the measured values were: 20 running, 22 batch 4 projects not started, 188 GiB available. No new machine.

**Power-off.**
- `census-other-done` (new; the original is kept as `.orig-4census`) lists batch2, batch3L, batch4, batch5L and batch6L. For batch6L the units are `census-batch6L-wait.service` and `census-batch6L.service`, so a waiting waiter also blocks the power-off.
- The guard (`.orig-b5L`) fstrims /b6L. Below 800 GiB it writes `/b6L/ctp/STOP` (which also holds the waiter) and `batch6L/live/GUARD`.
- `census-backup` (`.orig-b5L`) has the RUNS line `batch6L|/b6L/census-2026-10-batch6L|/b6L/ctp`.

**Cost (inferred).** The big EC2, at about $5.70/h on demand, stays up until batch6L ends. batch6L starts once batch 4 drains, and beagleboard__linux is predicted at 39.4 h, which is a weak prediction for L. So batch6L can add about 1.5-2 days, about $200-280, beyond the end of batches 2-5L. It should still end well before 2026-10-20.

## Restart and watchdog (local)

**`~/s3-work/ec2-batch3/restart_spot.sh`** (the old version is kept as `.orig-b3b5`):
- `--remaining` also counts fed: for each line of `feed.tsv`, the parts' assigned projects minus done/OK.
- A relaunch always installs `s6-files-0/1/2.sh`. If fed has work left, it also runs `s6-relaunch-<x>.sh`, which sets each workload's commit from `feed.tsv` and runs `census-fed-enqueue`.

**`feed.tsv`** columns are: workload, local dir of its parts files, commit (`pending` | `base` | SHA), bundle URL, bundle sha256, `WANT_PQ`.

**`~/s3-work/census-watchdog/watchdog.sh`** (the old version is kept as `.orig-b5`):
- It checks batch6L like the other on-demand censuses; `waiting` is ok.
- When b5 says "finalized", fed active or waiting is ok.
- The new section 5 checks `feed/<x>/live/` and alerts on paused, stopped, interrupted or STALE.

## Tests (all measured, 20:09-20:32 UTC; nothing terminated or powered off, and no census unit changed)

| test | where | result |
|---|---|---|
| D0-D8 census-spot-decide with fed (queued / missing DONE / fake DONE / active unit / b3+b5+fed / unknown word) | a, b | rc 1 / 1 / 0 / 1 / 1 / 2 as expected |
| F1-F9 feeder with stub parts (transient `sleep` units), 2 slots: pending commit waits; dry run; memory floor; PAUSE; 3 queued → 2 start; a3 starts when a1 ends; idle when empty; failed check → PAUSE, part stays queued | a (b: all but F7, whose slots were full) | as expected |
| T2 real part-init and gate on test part batch99i1 (base commit), then census-fed-upload and census-fed-finalize --dry-run on its check output | b | image 1200G, ctp ca113e3, cregit 95cdc88 clean; CHECK OK in 208 s (libexpat 40511e0d…); upload 10 files OK; dry run 22 objects, check ok, DONE in `batch99/i1/dryrun/<iid>/` |
| fed host choice | a | /data6 (3434G free), 1200G |
| fake spot notice (census-fed-watch) | a, b | INTERRUPTED.test in `feed/<x>/live/`, no STOP, no interrupted flag |
| census-other-done T1-T6, all finalizes `--decide-only`, guard real run | big | as expected (T2: 5L blocked by the missing batch6L DONE; T3/T4 rc 0) |
| waiter W1-W9 `--decide-only` | big | starts only when all 5 conditions hold |
| census-batch6L-finalize --dry-run on the check output | big | 19 objects, check ok, DONE in `batch6L/dryrun/` |
| restart_spot.sh stubs (fake aws, stub launch and ssm) R1-R8 | local | counts and plans include fed; full path calls `s6-files-0/1/2` and `s6-relaunch-<x>` with the commit; nothing to relaunch when all done; 0 refused aws calls |
| watchdog real run (timer 20:30) | local | spot a/b fed "waiting", batch6L ok, no alert |

Test objects kept: `B/s6test/<iid>/…`, `B/batch99/i1/{done,dryrun}/`, `B/batch6L/dryrun/`, `B/feed/<x>/live/INTERRUPTED.test`. On spot b, `/w/batch99i1` (test image) and `/etc/cregit-census/fedtest-*` remain.

## When the commit arrives

1. `./stage-cregit.sh <commit>` writes `upload-cregit/cregit-<short>.bundle` (the range 95cdc88..commit, verified) and `SHA256SUMS.<short>`, and prints the user's `aws s3 cp` commands for `B/cregit/`. A test bundle of 9079a9c was staged at 20:34; it is not the confirmed commit.
2. After the upload: `./set-cregit.sh <full sha> <bundle sha256> <libexpat sha256> --go`. It does three things:
   - it updates `feed.tsv`;
   - it runs `census-fed-workload batch6 --commit …` and one feeder pass on each spot instance; the parts start as slots free, each with its own checkout and gate;
   - it runs `census-batch6L-cregit --commit …` on the big EC2.
3. The fallback, only if the user decides it: `./set-cregit.sh --base --go` runs batch 6 on 95cdc88.

## Stop

- All via SSM: `I=<id> scripts/ssm.sh <script>`.
- **Hold the feeder:** `touch /etc/cregit-census/fed/PAUSE`.
- **One fed part:** `touch /w/<id>/ctp/STOP`.
- **batch6L before its start:** `touch /b6L/ctp/STOP`. After its start, the same file stops new starts.
- **Keep a spot instance up:** `touch /home/ec2-user/NO_SHUTDOWN`.

## Files

- `upload/`: the batch 6 inputs.
- `upload-cregit/`: the cregit bundles.
- `feed.tsv`: the fed workloads.
- `stage-cregit.sh` and `set-cregit.sh`.
- `scripts/remote-spot/`: the census-fed-* scripts and units, plus census-spot-decide.
- `scripts/remote-L/`: the batch6L files, census-other-done, the guard and census-backup.
- `scripts/` (SSM steps):
  - spot: p1-probe, s6-files-0/1/2 (from gen-s6-files.sh), t1-feeder-stub, t2-init, t3-notice-live, s6-arm;
  - big EC2: e1-probe, L1-setup, L2a/L2b-install (from gen-L2.sh).
- `out/`: the outputs of each step.

## Fix 2026-10-09 23:01 UTC: batch6L gate file
`set-cregit.sh --base --go` at 22:56 UTC: the batch6L gate passed (libexpat 40511e0d…), but
`/etc/cregit-census/` did not exist on the big EC2, so `batch6L.gate` was not written and the waiter
saw no passed gate. `scripts/L4-gatefix.sh` made the folder and ran `census-batch6L-cregit --base`
again: CHECK OK 23:01:47 UTC (236 s). The waiter now waits only for batch 4 (3 projects not started).

## Update 2026-10-10 00:40 UTC: batches 7-20 queued, worker-aware feeder

Measured unless marked.

- **feed.tsv:** 14 lines (batch7..batch20) with commit 1f176633…, bundle `B/cregit/cregit-1f17663.bundle` (sha256 a827082e…) and WANT_PQ 14eb5d72…. The old file is kept as feed.tsv.bak.<epoch>.
- **On both spot instances,** `scripts/s7-enqueue.sh` ran `census-fed-workload batchN --commit …` and then `census-fed-enqueue batchN` for N = 7..20. Each input's sha256 is ok, and every derived part manifest is equal to its parts.<wl>.tsv.
  - Spot a (${RUNNER_EC2_SPOT_A2}): 74 queued parts (4 of batch6, then 70 of batches 7-20).
  - Spot b (${RUNNER_EC2_SPOT_B3}): 73 queued parts.
  - batch6 stays on 95cdc88.
- **Gate of 1f17663 on a spot instance,** tested before the first batch 7 part (`t4-gate-1f17663.sh`, test workload batch97 on spot b):
  - part-init fetched the bundle and checked out 1f17663, clean;
  - CHECK OK at 00:12:46 UTC: libexpat 14eb5d72…, 2,196,248 bytes, 257 s.
  - Each real part runs the gate again; if it fails, the feeder writes PAUSE and does not fall back.
- **Relaunches** re-queue all 15 workloads from feed.tsv. `restart_spot.sh` now lists S3 once per workload: `--remaining` takes 54 s instead of 3 min 22 s, with the same output. The previous version is kept as `restart_spot.sh.bak-20261010`.
- **Spot ids:** no other script of mine hard-codes spot ids. `set-cregit.sh` reads them from instances.txt (the coordinator's change). On the big EC2, only `census-batch6L-cregit` and `census-L7-20-cregit` write into `/etc/cregit-census/`, and both now create it first.
- **Feeder change, worker-aware (since ~00:28 UTC):**
  - A running part now counts only its busy workers: min(4, running + not started).
  - The next part starts while at most 16 of `worker_slots` (default 20) workers are busy, with at most `slots` (default 8) parts at once.
  - Why: at 00:20 four batch 5 parts on spot a ran 1-2 projects each and had 0 left to start, so about 14 of their 20 workers were idle.
  - Stub-tested (`t5-feeder-workers.sh`): full parts started 5; tails started up to the 8-part cap; unreadable counts count 4.
  - First real effect: spot b started batch6b3 at 00:28 (13 of 20 workers busy), and spot a started batch6a2 and a3.
- **Other script changes:**
  - Live: a finished part gets one line and no per-part upload, so the pass stays short with about 75 parts.
  - Trim: it skips finished parts.
  - Part-init sizes an image by the parts that still run on its host.
  - `s6-files-2.sh` runs daemon-reload only when a unit file changed. For these updates, unit files were unchanged, so there was no reload.

## Change 2026-10-10 01:18 UTC: batch6L started before batch 4 ended (user decision)
The waiter now skips condition (1) when `/etc/cregit-census/batch6L.no-b4-wait` exists
(`scripts/L5-no-b4-wait.sh`; old waiter kept as `census-batch6L-wait.orig-b4wait` on the instance and
here). The other floors stayed. Decision at 01:18:08: running 12 (max 16), batch 4 not started 1,
MemAvailable 204G, /data free 3576G: start. census-batch6L.service is active since 01:18:10.

## Update 2026-10-10 02:50 UTC: batch 21 (DP8L supplement) queued

Measured unless marked.

- **Batch 21** (81 projects: S 60, M 20, L 1; built in ${RUNNER_STUDY_REPO} e0c47cb). Its inputs are in `B/batch21/input/` (uploaded by the user).
- **feed.tsv** has the batch21 line from feed.next.tsv: commit 1f17663, the same bundle and WANT_PQ 14eb5d72. The old file is kept as feed.tsv.bak.<epoch>.
- **On both spot instances,** `scripts/s21-enqueue.sh` ran `census-fed-workload batch21 --commit …` and then `census-fed-enqueue batch21`.
  - The installed census-fed-derive gave 5 of 5 sha256 ok per half. Its `--derive` code is the same as the new split_batchN.py; only the split reads frame.batch21.csv.
  - The 10 parts are queued after batch 20. Spot a has 75 queued parts and spot b 75.
- **Relaunches** re-queue batch 21: `--remaining` counts batch21a1..a5, and the stub relaunch script contains its workload and enqueue lines.
- **Its L project, NetBSD__pkgsrc,** goes into the L7-20 queue as v2 (see `~/s3-work/ec2-L7-20/README.md`).
- **Shared scripts:** watchdog.sh and status_all.sh are now edited through a temp file and an atomic mv. The 00:06 UTC alert "restart_spot.sh: line 65: syntax error" came from an in-place edit of restart_spot.sh while the watchdog read it.

## Update 2026-10-10 15:45 UTC: batch 22 (GNU supplement) queued

Measured unless marked.

- **Batch 22** was built in ${RUNNER_STUDY_REPO} 9f74b6d, with 3 parts per half (a1-a3, b1-b3; 31 S/M projects). Its inputs are in `B/batch22/input/`.
- **feed.tsv** has the batch22 line (1f17663; same bundle and WANT_PQ). The old file is kept as feed.tsv.bak.<epoch>.
- **On both spots,** `scripts/s22-enqueue.sh` set the workload commit and enqueued it. The derive gave 3 of 3 sha256 ok per half.
  - Spot a (${RUNNER_EC2_SPOT_A4}): 71 parts queued, ending with batch22 a1-a3.
  - Spot b (${RUNNER_EC2_SPOT_B3}): 56 parts queued, ending with batch22 b1-b3.
- **Relaunches** re-queue it: `--remaining b` counts batch22b1..b3, and the stub relaunch script has its enqueue line.
- **batch22L** runs as census L22 on the big EC2 (see `~/s3-work/ec2-L22/README.md`).
- **Known deterministic failure, not fixed:** signalwire__freeswitch (batch7a3) fails in blobExec step 2: a NullPointerException, `getCommitter()` null at Walker.scala:866.
