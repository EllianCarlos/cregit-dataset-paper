# Census L23: the 8 L projects of batch 23 on the big EC2 (prepared 2026-10-11, NOT started)

The user decided on 2026-10-11 at about 19:00 UTC: "Yes, add them" (the near-miss rows of the license filter, DP8L v4). Batch 23 is built in ${RUNNER_STUDY_REPO} 76aeef8 (s7-run). B = `s3://${RUNNER_BUCKET}`. Measured unless marked.

Nothing here has run on the instance except the read-only probe `P1-probe.sh` (out/P1-probe.out, 20:19 UTC). Run the steps below only after `~/s3-work/upload-batch23.sh` prints `ALL OK`.

## Projects

`manifest.batch23L.tsv` (sha256 c8c986af…), in LPT order as `manifest.L23.tsv` (sha256 98152b6b…, built by `build-L23-input.py`; a local copy is `out/manifest.L23.local.tsv`). The predictions are inferred and weak for L projects: the model under-predicts large L.

| row | project | commits | tokenizable MB | predicted |
|---|---|---:|---:|---:|
| 1 | NetBSD__src | 317,009 | 1,790 | 17.5 h |
| 2 | openbsd__src | 247,628 | 1,121 | 12.3 h |
| 3 | checkedc__checkedc-clang | 456,547 | 347 | 10.6 h |
| 4 | WebKit__WebKit | 322,785 | 535 | 10.4 h |
| 5 | Xilinx__hls-llvm-project | 281,035 | 218 | 6.5 h |
| 6 | openbsd__ports | 213,424 | < 1 | 0.5 h |
| 7 | alpinelinux__aports | 264,054 | < 1 | 0.3 h |
| 8 | archlinuxcn__repo | 418,678 | < 1 | 0.2 h |

LPT makespan on 4 workers: 17.5 h (inferred). Expect much longer.

## State of the instance at 20:19 UTC (P1-probe)

- 14 projects run: L7-20 6, L7-20b 6, L22 1 (gcc), batch5L 1.
- MemAvailable 284 GiB of 372 GiB. Load 160 on 96 CPUs.
- /data: 2779 G free of 5307 G. Images: bL7 1871 G, b5L 239 G, bL7b 188 G, bL22 124 G.
- Shared scripts are the L7-20b versions: census-other-done db590d92…, census-batch4-guard dfa4f579…, census-backup 4787a2dd…. L1 and L2a refuse if they differ.
- /data/cregit-ec2 is at 95cdc88 and clean (the bundle prerequisite). The copies /bL7, /bL22 and /bL7b are at 1f17663 with 1 changed file (the formatBlame.pl swap of the blame time-limit plan).
- fsids in use: 70000000000-70700000000. /bL23 gets the next free loop device.

## Layout (same pattern as L22 and L7-20b)

- Loop XFS `/data/loop/bL23.img` (3000G sparse) at `/bL23`.
- Inputs: `B/batch23/input/` to `~ec2-user/batch23-input/` (sha256 checked), then `~ec2-user/L23-input/`: `manifest.L23.tsv`, `project_meta.L23.json` (a byte copy of `project_meta.batch23L.json`, e823a93b…), `SHA256SUMS`.
- ctp clone `/bL23/ctp`: a git clone of `/bL7b/ctp` at ca113e3, with a copy of its `.venv`.
- cregit copy `/bL23/cregit-ec2`: a tar of `/data/cregit-ec2` (95cdc88) without its build dir. `census-L23-cregit` fetches `cregit-57551d7.bundle` (sha256 18b1bf1c…) and checks out 57551d7.
- Output `/bL23/census-2026-10-L23`, log `/data/logs/L23.log`, config `~ec2-user/census-L23.cfg`.

## Gate

`census-L23-cregit --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle B/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c… --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799` (L3-gate-start.sh):
- libsrcml dea4467b…;
- libexpat 14eb5d72… (2,196,248 bytes, unchanged by 57551d7);
- the blobExec jar equal to /data/cregit-ec2;
- result in `/etc/cregit-census/L23.gate`.

## Census

`census-L23.service` runs `--workers 4 --retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300` and `OOMPolicy=continue` (the flags of L7-20b, 4 workers).

## Waiter

`census-L23-wait` starts the census when ALL of these hold:
1. At most 12 other projects run (batch2, 3L, 4p1-3, 5L, 6L, L7-20, L22, L7-20b), so at most 16 after the start.
2. MemAvailable ≥ 120 GiB.
3. /data has ≥ 2000 GiB free.
4. The gate passed for the copy's HEAD.
5. The local inputs check (`~ec2-user/L23-input/SHA256SUMS`).

A STOP file in /bL23/ctp holds the start. There is no split watcher: no other queue holds these rows.

With the state of 20:19 UTC (14 others), the waiter waits. It starts when 2 projects of the other queues end, if the disk and memory floors hold.

## Power-off

- `census-other-done` (backup `.orig-L7-20b`) gets L23 (`census-L23-wait.service`, `census-L23.service`, `B/L23/final/DONE`). Every older finalize then also waits for L23.
- The guard (`.orig-L7-20b`) fstrims `/bL23`, and below 800 GiB it writes `/bL23/ctp/STOP` and `L23/live/GUARD`.
- `census-backup` (`.orig-L7-20b`) gets the RUNS line `L23|/bL23/census-2026-10-L23|/bL23/ctp`.

**S3 paths:** `L23/live/`, `L23/final/`, `L23/done/<project>/` (census-backup), `L23/dryrun/`.

## Steps (after ALL OK)

Run from `~/s3-work/ec2-L23/scripts/` (ssm.sh: the script lines go into the SSM `commands` list, file:// JSON, no base64):

1. `./ssm.sh P1-probe.sh 300` (read-only): check that the shared script sha256 values are still the L7-20b ones.
2. `./ssm.sh L1-setup.sh 3600`: image, inputs (from S3), ctp clone, cregit copy, configs, gate helpers.
3. `bash gen-L2.sh` (only if a `remote-L/` file changed; the 3 install scripts are already built), then `./ssm.sh L2a-install.sh`, `./ssm.sh L2a2-install.sh`, `./ssm.sh L2b-install.sh`. L2b runs the tests: the power-off rule T1-T8 and the waiter W1-W8. Nothing powers off, nothing starts.
4. `./ssm.sh L3-gate-start.sh 3600`: the gate (about 3-5 min), a dry-run finalize, then the live timer and the waiter.
5. `./ssm.sh R1-check.sh 300` (read-only).
6. On this machine: `bash W1-watch-entries.sh` (watchdog.sh, status_all.sh and fetch_done.sh get L23 and batch 23; temp file and atomic mv).

Save each output in `out/<step>.out`.

## Open decisions for the user

- Workers 4 and the floors (12 others, 120 GiB, 2000 GiB). The load is already 160 on 96 CPUs. With 4 workers and LPT order, the 2 BSD source trees and 2 LLVM-size trees run first.
- checkedc-clang and Xilinx/hls-llvm-project are LLVM forks (not GitHub forks). llvm/llvm-project (batch3L), intel/llvm and other LLVM forks are already in the dataset, so this follows the rule. They share most of their history.

## Files

- `scripts/`: `ssm.sh`, `P1-probe.sh` (read-only), `build-L23-input.py`, `L1-setup.sh`, `gen-L2.sh` (builds `L2a`, `L2a2` and `L2b-install.sh`), `L3-gate-start.sh`, `R1-check.sh` (read-only), `W1-watch-entries.sh` (local), `remote-L/` (the instance files).
- `out/`: the outputs of each step.
