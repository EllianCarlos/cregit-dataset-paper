# Census L22: the 2 L projects of batch 22 on the big EC2 (2026-10-10)

The user approved this at about 15:05 UTC. B = `s3://${RUNNER_BUCKET}`. Measured unless marked.

## Projects

batch22L of the GNU supplement (${RUNNER_STUDY_REPO} 9f74b6d):

| project | commits | predicted |
|---|---|---|
| gcc.gnu.org__git__gcc | 233,470 | 7.0 h (inferred; the model under-predicts large L, so expect much longer) |
| git.savannah.gnu.org__git__emacs | 183,705 | 1.8 h (inferred) |

**Inputs.** `B/batch22/input/` (already uploaded), copied to `~ec2-user/L22-input/`: sha256 ok, 7 files. The census reads `manifest.batch22L.tsv` and `project_meta.batch22L.json`.

## On ${RUNNER_EC2_BIG}

This follows the L7-20 pattern.

**Layout.**
- Loop XFS `/data/loop/bL22.img` (2000G sparse) at `/bL22`, fsid 70600000000.
- ctp clone `/bL22/ctp`, ca113e3.
- cregit copy `/bL22/cregit-ec2`: a tar into a temp dir without the build dir (the race fix of the spot part-init), then an mv. It is checked out at 1f17663.
- Output `/bL22/census-2026-10-L22`, log `/data/logs/L22.log`.

**Gate**, `census-L22-cregit`, 15:36-15:40 UTC:
- libsrcml dea4467b…;
- libexpat **14eb5d72…** (2,196,248 bytes, 249 s);
- jar equal;
- result: `CHECK OK 2026-10-10T15:40:46Z` in `/etc/cregit-census/L22.gate`. The script creates `/etc/cregit-census` first.

A dry-run finalize gave 18 objects, check ok, DONE in `L22/dryrun/`.

**Census.** `census-L22.service` runs with `--workers 2 --retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300` and `OOMPolicy=continue`.

**Waiter.** `census-L22-wait` (active since 15:40:53 UTC) starts the census when ALL of these hold:
1. At most 14 other projects run (batch2, 3L, 4p1-3, 5L, 6L, L7-20).
2. MemAvailable ≥ 120 GiB.
3. /data has ≥ 1500 GiB free.
4. The gate passed for the copy's HEAD.
5. The inputs check.

At 15:40 it was waiting: 16 other projects running, 182 GiB available, 2290 G free.

**Disk floor.** I kept 1500 GiB, with 700 GiB above the 800 GiB guard. The measured image use at 15:36 was: b6L 827G for 3 L projects, b5L 646G for 5, bL7 356G after 2 h. So gcc and emacs may need about 300-600 G together (inferred).

**Power-off.**
- `census-other-done` (`.orig-L7-20`) has `L22` (`census-L22-wait.service`, `census-L22.service`, `B/L22/final/DONE`).
- The guard (`.orig-L7-20`) fstrims `/bL22`, and below 800 GiB it writes `/bL22/ctp/STOP` and `L22/live/GUARD`.
- `census-backup` (`.orig-L7-20`) has the RUNS line `L22|/bL22/census-2026-10-L22|/bL22/ctp`.

**Watchdog and status.** `watchdog.sh` (`.orig-L22`) and `status_all.sh` (62e7e2e) check L22; "waiting" is ok.

## Tests (15:35-15:41 UTC; nothing powered off; the 7 running units were unchanged by the daemon-reload)

- **census-other-done:** T1 (7 censuses, real state) rc 1. T2: L7-20 is blocked by the missing L22 DONE (rc 1). T3 and T4 rc 0. T5 (an active unit) rc 1. T6 (bad argument) rc 2.
- **Finalizes:** all 7 run with `--decide-only` and none powers off. The guard was run for real.
- **Waiter:**
  - 16 others running: waits; 14 others: starts;
  - waits on: no gate, memory 100 GiB, /data 1400 G, missing inputs;
  - an inactive L7-20 is not counted.

## Files

- `scripts/`:
  - `L1-setup.sh`, `gen-L2.sh` (which builds `L2a`, `L2a2` and `L2b-install.sh`), `L3-gate-start.sh`;
  - `remote-L/`: the instance files.
- `out/`: the outputs of each step.
