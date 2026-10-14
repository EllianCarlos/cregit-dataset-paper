# Census L7-20b: the second L queue on the big EC2 (2026-10-11)

The user approved this on 2026-10-11 at 16:45 UTC: a new census on the big EC2 with the smaller projects at the END of the L7-20 list, about 6 workers, no restart of L7-20, and a STOP on L7-20 when it reaches the L7-20b rows. B = `s3://${RUNNER_BUCKET}`. Measured unless marked.

## Split

At 19:11 UTC, census L7-20 had started rows 1-6 (the 6 kernel trees, in step 7 blame). Rows 7-56 had not started: 50 rows, 683.9 h predicted (inferred), half = 341.9 h.

| queue | rows | projects | predicted (inferred) |
|---|---|---|---|
| L7-20 (no change) | 1-6 running, 7-16 not started | 6 + 10 | 353.7 h for rows 7-16 |
| L7-20b (new) | 17-56: BrowserWorks__waterfox .. jlord__patchwork | 40 | 330.2 h |

A split at row 16 gives 360.7 h / 323.2 h. That is farther from half, so the split row is 17.

## Inputs (built on the instance, nothing from S3)

`L1-setup.sh` runs `~ec2-user/build-L7-20b-input.py` on the instance. It reads `~ec2-user/L7-20-input/` (v2: manifest 58af4ad6…, sidecar 28ddbccc…) and writes `~ec2-user/L7-20b-input/`:
- `manifest.L7-20b.tsv` (sha256 ba254e0e…): a new header and rows 17-56, unchanged and in the same order. The data rows are identical to the last 40 rows of L7-20.
- `project_meta.L7-20b.json`: a byte copy of the L7-20 sidecar (28ddbccc…).
- `SHA256SUMS`.

The script refuses if a source sha256 differs or if census L7-20 has started a split row.

## On ${RUNNER_EC2_BIG}

This follows the L22 pattern.

**Workers: 6.** At 19:11 UTC: MemAvailable 323 GiB of 371 GiB, 96 CPUs at load 32.6, /data free 2967 G, 8 other projects running (L7-20 6, L22 1, batch5L 1). The 6 L7-20 kernels use 298-315 G each on /bL7. The L7-20b rows are smaller (inferred).

**Layout.**
- Loop XFS `/data/loop/bL7b.img` (3000G sparse) at `/bL7b` (/dev/loop7), fsid 70700000000.
- ctp clone `/bL7b/ctp`: a git clone of `/bL7/ctp` at ca113e3 (feat/e2e-runner), with a copy of its `.venv` (Python 3.12.14, duckdb 1.5.5).
- cregit copy `/bL7b/cregit-ec2`: a tar of `/bL7/cregit-ec2` without its build dir, at 1f17663, not dirty. The blobExec jar is 3daa1201, equal to /data/cregit-ec2.
- Output `/bL7b/census-2026-10-L7-20b`, log `/data/logs/L7-20b.log`, config `~ec2-user/census-L7-20b.cfg`.

**Gate**, `census-L7-20b-cregit`, 19:13-19:15 UTC:
- libsrcml dea4467b…;
- libexpat **14eb5d72…** (2,196,248 bytes, 149 s);
- jar equal;
- result: `CHECK OK 2026-10-11T19:15:55Z cregit 1f176633…` in `/etc/cregit-census/L7-20b.gate`.

A dry-run finalize gave 18 objects, check ok, DONE in `L7-20b/dryrun/`.

**Census.** `census-L7-20b.service` runs with the flags of census-L7-20: `--workers 6 --retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300`, and `OOMPolicy=continue`. The waiter started it at **19:16:01 UTC**. At 19:17 the first 6 rows were in clone.

**Waiter.** `census-L7-20b-wait` starts the census when ALL of these hold:
1. At most 10 other projects run.
2. MemAvailable ≥ 120 GiB.
3. /data has ≥ 2500 GiB free (the L7-20 value).
4. The gate passed for the copy's HEAD.
5. The local inputs check (SHA256SUMS).
6. Census L7-20 has started no L7-20b row (no `/bL7/ctp/state/<name>/`).

**Split watcher.** `census-L7-20-split.timer` runs `/usr/local/bin/census-L7-20-split` every 5 s.
- ctp census starts rows in manifest order. It creates `state/<name>/` first when it starts a project.
- When all 16 rows before row 17 have a state dir in `/bL7/ctp/state/`, and census L7-20b has started, the watcher writes **`/bL7/ctp/STOP`** (owner ec2-user) and the marker `/bL7/ctp/STOP.split-L7-20b`.
- ctp census checks the STOP file before each start. It then starts no new project and no retry. The running projects finish, the census exits (rc 3, or 1 with a failure), and census-L7-20-finalize runs as usual.
- After census L7-20 ends, the watcher lists the rows before row 17 that have no done row in the L7-20 ledger ("NOT DONE IN L7-20"), then it stops its timer.
- Status: `/run/census-L7-20-split.status`, also on the "split:" line of `L7-20b/live/progress.txt`. Events: `/data/logs/L7-20-split.log`.
- **Known limits.**
  - If two L7-20 slots become free in the same scheduler pass, or row 16 fails in less than 5 s, L7-20 can start row 17 before the STOP. The watcher then reports "DOUBLE START", and the watchdog alerts.
  - The STOP drops the retries of census L7-20. A row before row 17 that fails needs a rerun.

**Power-off.**
- `census-other-done` (`.orig-L22`) has L7-20b (`census-L7-20b-wait.service`, `census-L7-20b.service`, `B/L7-20b/final/DONE`).
- The guard (`.orig-L22`) fstrims `/bL7b`, and below 800 GiB it writes `/bL7b/ctp/STOP` and `L7-20b/live/GUARD`.
- `census-backup` (`.orig-L22`) has the RUNS line `L7-20b|/bL7b/census-2026-10-L7-20b|/bL7b/ctp`.

**S3 paths:** `L7-20b/live/`, `L7-20b/final/`, `L7-20b/done/<project>/` (census-backup), `L7-20b/dryrun/`.

**Watchdog and status.** `watchdog.sh` (`.orig-L7-20b`) checks L7-20b. It alerts once for each of "DOUBLE START", "SPLIT CLASH", "NOT DONE IN L7-20" and "ERROR" on the split line. `status_all.sh` and `fetch_done.sh` include L7-20b.

## Expected end (inferred, from the predictions)

- L7-20b: LPT makespan 55.7 h, so about 2026-10-14 03:00 UTC.
- L7-20: the 6 kernels end about 2026-10-12 05:00 UTC, then rows 7-16 run in 2 waves. The end is about 2026-10-15 04:00 UTC.
- If the projects take 1.25 times the prediction: about 2026-10-14 17:00 and 2026-10-16 08:00 UTC.
- Without the split, L7-20 ends about 2026-10-17 00:00 UTC.

## Tests (19:11-19:13 UTC; nothing powered off; the 3 running census units were unchanged by the daemon-reload)

- **census-other-done:** T1 (8 censuses, real state) rc 1. T2: L7-20 is blocked by the missing L7-20b DONE (rc 1). T3 and T4 rc 0. T5 (an active unit) rc 1. T6 (bad argument) rc 2.
- **Finalizes:** all 8 run with `--decide-only` and none powers off. The guard was run for real.
- **Waiter:** 8 others running: starts; 11 others: waits. It waits on: no gate, memory 100 GiB, /data 2400 G, missing inputs, an L7-20b row started in L7-20. An inactive L7-20 is not counted.
- **Split watcher:** real state: "waiting: 10 of 16 rows". With a fake state dir and a temp STOP path: no STOP while L7-20b has not started; STOP and marker written (owner ec2-user) when it has; after the end of L7-20, it lists the rows that are not done.

## Files

- `scripts/`:
  - `ssm.sh`: it puts the script lines into the SSM `commands` list (file:// JSON, no base64);
  - `P1-probe.sh`, `P2-probe.sh` (read-only), `L1-setup.sh`, `gen-L2.sh` (which builds `L2a`, `L2a2` and `L2b-install.sh`), `L3-gate-start.sh`;
  - `remote-L/`: the instance files.
- `out/`: the outputs of each step.
