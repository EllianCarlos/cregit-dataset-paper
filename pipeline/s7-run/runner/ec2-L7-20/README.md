# Census L7-20: the 55 L projects of batches 7-20 on the big EC2 (2026-10-10)

User decision 2026-10-09 ~23:50 UTC: one combined L queue, 6 workers, longest predicted first (LPT).
The deadline is 2026-10-20 20:00 UTC. Expected end (inferred): Oct 14-19. Account ${RUNNER_AWS_ACCOUNT}, ${RUNNER_AWS_REGION},
profile `${RUNNER_AWS_PROFILE}`; B = `s3://${RUNNER_BUCKET}`. Measured unless marked.

## Queue

- **Manifest:** `manifest.L7-20.tsv`, built by ${RUNNER_STUDY_REPO} `s7-run/build_L7_20.py` (commit b1e8ee1).
  - It holds the rows of manifest.batch7L.tsv .. batch20L.tsv, longest predicted first. ctp census runs rows in manifest order.
  - The sidecar is `project_meta.L7-20.json`: the 14 enriched batchNL sidecars, copied unchanged.
- **Predictions (inferred):** 917 h in total; the first are mptcp_net-next, gregkh__linux and wireguard-linux at 40.1 h each. The LPT makespan on 6 workers is 154 h, about 6.4 days from the start.
  - The predictions agree with /tmp/L7_20.json to 0.05 h.
- **Inputs:** staged in `upload/` (manifest, sidecar, SHA256SUMS). They are NOT uploaded yet. The command for the user is:

      export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
      aws s3 cp ~/s3-work/ec2-L7-20/upload/ s3://${RUNNER_BUCKET}/L7-20/input/ --recursive --only-show-errors

  The waiter copies them to `~ec2-user/L7-20-input/` and checks their sha256 itself, so nothing else is needed after the upload.

## On the big EC2 ${RUNNER_EC2_BIG}

These follow the batch6L pattern.

**Layout.**
- Loop XFS `/data/loop/bL7.img` (3000G sparse) at `/bL7`, fsid 70500000000.
- ctp clone `/bL7/ctp`, ca113e3.
- cregit copy `/bL7/cregit-ec2`, checked out at **1f17663** from `B/cregit/cregit-1f17663.bundle` (sha256 a827082e…).
- Output `/bL7/census-2026-10-L7-20`; log `/data/logs/L7-20.log`; config `~ec2-user/census-L7-20.cfg`.

**Gate**, `census-L7-20-cregit`, 00:21-00:25 UTC:
- libsrcml dea4467b…55f3;
- libexpat Parquet **14eb5d72…** (2,196,248 bytes, 218 s);
- blobExec jar equal to /data/cregit-ec2;
- result: `CHECK OK 2026-10-10T00:25:29Z cregit 1f176633…` in `/etc/cregit-census/L7-20.gate`.

**Census.** `census-L7-20.service` runs with `--workers 6 --retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300` and `OOMPolicy=continue`.

**Waiter.** `census-L7-20-wait` (active since 00:25:34 UTC) starts the census when ALL of these hold:
1. census-batch6L has started: its waiter is gone and its census is active or has a ledger.
2. At most 10 other projects run on the instance (batch2, 3L, 4p1-3, 5L, 6L), so 16 at most after the start.
3. MemAvailable ≥ 120 GiB.
4. /data has ≥ 2500 GiB free.
5. The gate passed for the copy's HEAD.
6. The inputs check (sha256).

At 00:25 the measured state was: batch6L not started, 12 other projects running, 215 GiB available, 3725 G free.

**Power-off.**
- `census-other-done` (the old version is kept as `.orig-b6L`) has L7-20 (`census-L7-20-wait.service`, `census-L7-20.service`, `B/L7-20/final/DONE`). Its test variables are `DONE_URL_L7_20` and `UNITS_L7_20`.
- The guard (`.orig-b6L`) fstrims `/bL7`, and below 800 GiB it writes `/bL7/ctp/STOP` and `L7-20/live/GUARD`.
- `census-backup` (`.orig-b6L`) has the RUNS line `L7-20|/bL7/census-2026-10-L7-20|/bL7/ctp`.
- `census-batch6L-cregit` now creates `/etc/cregit-census` (old version kept as `.orig-nomkdir`).

**S3 paths:** `L7-20/live/`, `L7-20/final/`, and `L7-20/done/<project>/` (written by census-backup). The test objects of the dry-run finalize are in `L7-20/dryrun/`.

## Tests (00:20-00:25 UTC; nothing powered off; the running units were the same before and after the daemon-reload)

- **census-other-done:**
  - T1: each of the 6 censuses on the real state, rc 1.
  - T2: batch6L with batch 2, 3L, 4 and 5L faked done is blocked by the missing L7-20 DONE (rc 1).
  - T3, T4, T5b: rc 0.
  - T6: a bad argument gives rc 2.
- **Finalizes:** all 6 run with `--decide-only` and none powers off. The guard was run for real.
- **Waiter (`--decide-only`):** it starts only when all conditions hold. It waits on each of: no gate, batch6L not started, 11 others running, memory 100 GiB, /data 2000 G, inputs missing.
- **Dry-run finalize** on the gate output: 17 objects, check ok, DONE written to `L7-20/dryrun/`.

## Files

- `upload/`: the staged inputs.
- `scripts/`:
  - `L1-setup.sh`, `gen-L2.sh` (which builds `L2a`, `L2a2` and `L2b-install.sh`), `L2c-tests.sh`, `L3-gate-start.sh`;
  - `remote-L/`: the instance files.
- `out/`: the outputs of each step.

## Update 2026-10-10 02:50 UTC: v2 inputs with NetBSD/pkgsrc (batch 21)

Measured unless marked.

- **v2 queue.** census-L7-20 had not started, so batch 21's one L project NetBSD__pkgsrc (457,576 commits, predicted 3.8 h) joins the queue.
  - `build_L7_20.py --v2` builds it (${RUNNER_STUDY_REPO} 3ff5298) over batches 7-21, reading frame.batch21.csv for the batch 21 rows.
  - The output is `manifest.L7-20.v2.tsv` / `project_meta.L7-20.v2.json`. pkgsrc is at row 44 of 56; the other 55 rows keep their order, and the sidecar records are unchanged.
  - Predicted (inferred): 920 h in total, LPT makespan 155 h on 6 workers.
  - v1 stays as it was; a rebuild of v1 is byte-identical.
- **Staged:** `upload-v2/` holds `manifest.L7-20.tsv` (58af4ad6…), `project_meta.L7-20.json` (28ddbccc…) and `SHA256SUMS` (whose own sha256 is bfa9fae7…). These are the names the census reads.
- **Upload (user):** `bash ~/s3-work/upload-L7-20-v2.sh`. It does three things:
  - keeps v1 in S3 as `L7-20/input-v1/`;
  - uploads v2 to `L7-20/input/`;
  - reads everything back and checks it against the staged SHA256SUMS.
- **Hold.** Since 02:43 UTC the waiter is held by `/bL7/ctp/STOP`, with the marker `/bL7/ctp/STOP.v2-hold`, so it cannot start on v1. Its status reads "STOP exists in /bL7/ctp: holding".
- **Swap.** `cregit-L7-20-v2swap.timer` (every 2 min, active since 02:46) does the rest:
  - once the S3 SHA256SUMS has sha256 bfa9fae7…, it copies and checks the v2 inputs into `~ec2-user/L7-20-input/` (older inputs go to `v1.<time>/`);
  - it removes the marker and the STOP (the STOP stays if the disk guard has tripped);
  - it stops its own timer.

  The first pass, at 02:46:59, logged "waiting for the v2 upload".
- **No waiter restart was needed.** The running waiter checks the local SHA256SUMS of the inputs, which will then be v2.
- **Watchdog:** it logs "held until its v2 inputs are uploaded". It alerts if the hold lasts more than 1 h after the v2 SHA256SUMS is in S3.
