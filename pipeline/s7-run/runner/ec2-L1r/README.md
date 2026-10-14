# Census L1r: batch 1 rerun, L, on the big EC2 (installed 2026-10-12 18:17 UTC, waiting for L23)

**Status 18:17 UTC.** The user ran `upload-L1r.sh` at 18:07 UTC (ALL OK). P1, L1, L2a, L2a2 (twice: the firm script fix 5ea9d9a1), L2b, L3 and R1 ran (outputs in `out/`). Gate CHECK OK 18:15:57 UTC (libexpat 14eb5d72…). Active: census-L1r-wait, census-L1r-live.timer, census-L1r-firm.timer. census-L1r is inactive: the waiter waits for census L23. The text below is the plan as prepared.

Batch 1 ran on the local machine on 2026-10-07..09 with the old cregit 157cf8b. Its outputs must be tokenized again with the current code. 49 of its 51 projects run again on the local machine (census-local-c). The user decided on 2026-10-12 at about 14:10 UTC that the 2 others run as a small L queue on the big EC2 (answer: "Big EC2 L queue"). This is that queue. B = `s3://${RUNNER_BUCKET}`. Measured unless marked.

Nothing here is installed on the instance. Only the read-only probes `P1-probe.sh` (out/P1-probe.out, 13:53 UTC) and `P2-probe.sh` (out/P2-probe.out, 14:04 UTC: a waiter dry run on the real state) ran. Run the steps below only after `~/s3-work/upload-L1r.sh` prints `ALL OK`.

## Projects

`manifest.L1r.tsv` (sha256 3443e70ac9d78ff3c428bfddc3fa311873f38b161b761637d41b69560f1e6768) holds the 2 rows of `manifest.batch1.tsv` (sha256 53e3090b…) unchanged, longest first (LPT). `project_meta.L1r.json` (sha256 c4c5b946d8f8623d045ea6f0ac872b37ff9e2a5eb0fe12d0ece501329d52c081) holds the 2 entries of `project_meta.batch1.json` (sha256 fa6a956d…) unchanged, in the format of that file (json indent 1). `scripts/build-L1r-input.py` writes both files and `SHA256SUMS` into `upload/`. It refuses if a source sha256 differs.

| row | project | commits | batch 1 time (cregit 157cf8b) | batch 1 disk |
|---|---|---:|---:|---|
| 1 | SAP__project-foxhound | 992,058 | 36.4 h | the cleanup freed 242 GiB |
| 2 | torvalds__linux | 1,484,687 | 25.9 h | 435 GB |

Expected makespan on 2 workers: about 36 h after the start (inferred from batch 1; the big EC2 is loaded, and the new code adds blame -C100 with a 3600 s limit per file, so expect longer).

## State of the instance at 13:53-14:04 UTC (P1, P2)

- 13 projects run: L7-20 6, L7-20b 6, L22 1 (gcc). batch5L is done (0 running). census-batch2 and census-batch3L are inactive.
- census-L23 has not started. Its waiter waits: 13 others (max 12) and /data free 1395 G (min 2000).
- MemAvailable 136-156 GiB of 372 GiB. Load 107 on 96 CPUs.
- /data: 1395-1472 G free of 5307 G. Images (sparse, used): bL7 2000 G, bL7b 1597 G, bL22 124 G, bL23 2 G.
- Shared scripts are the L23 versions: census-other-done dfc79946…, census-batch4-guard 3aea045a…, census-backup ba1a206a…. L1-setup and L2a refuse if they differ.
- /data/cregit-ec2 is at 95cdc88 and clean (the bundle prerequisite). /bL7b/ctp is at ca113e3.
- fsids in use: 70000000000-70800000000 (/bL23 = 70800000000). /bL1r gets the next free loop device.
- The firm step is the process `python3 <ctp>/firm_attribution.py <out>/<project>/<project>-dataset.parquet --memory-limit …` in the cgroup of its census unit (`0::/system.slice/census-L7-20b.service`). At 13:53 UTC one kernel firm step (MotorolaMobilityLLC__kernel-msm, L7-20b) had 39 GB RSS. No process had oom_score_adj -500 (the 4 L7-20 kernel firm steps that got it at 00:40 UTC had ended).

## Layout (the L23 pattern)

- Loop XFS `/data/loop/bL1r.img` (3000G sparse, the L23 size) at `/bL1r`. The image is sparse: only the used blocks take /data space, and the guard fstrims it. Expected use: about 700 GiB at the peak (inferred: 435 GB for Linux and about 242 GiB for foxhound in batch 1).
- Inputs: `B/L1r/input/` (from `upload-L1r.sh`) to `~ec2-user/L1r-input/`: `manifest.L1r.tsv`, `project_meta.L1r.json`, `SHA256SUMS` (sha256 checked, also against the 2 values above).
- ctp clone `/bL1r/ctp`: a git clone of `/bL7b/ctp` at ca113e3, with a copy of its `.venv`.
- cregit copy `/bL1r/cregit-ec2`: a tar of `/data/cregit-ec2` (95cdc88) without its build dir. `census-L1r-cregit` fetches `cregit-57551d7.bundle` (sha256 18b1bf1c…) and checks out 57551d7.
- Output `/bL1r/census-2026-10-L1r`, log `/data/logs/L1r.log`, config `~ec2-user/census-L1r.cfg`.

## Gate

`census-L1r-cregit --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle B/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c… --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799` (L3-gate-start.sh):
- libsrcml dea4467b…;
- libexpat 14eb5d72… (2,196,248 bytes, the L23 value);
- the blobExec jar equal to /data/cregit-ec2;
- result in `/etc/cregit-census/L1r.gate`.

## Census

`census-L1r.service` runs `ctp.py census --workers 2 --retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300` and `OOMPolicy=continue`. These are the flags of census-L23, with 2 workers (2 projects). `--latest` pins the HEAD of the start day (the rule of the run), so the commits differ from the batch 1 pins.

## Waiter (priority: L23 first)

`census-L1r-wait` starts the census when ALL of these hold:
0. Census L23 has started: `census-L23.service` is active, or `/bL23/ctp` has a `ledger.jsonl` or a `state/<name>/` dir (ctp writes them when a project starts; they stay after L23 ends). The file `/bL1r/ctp/IGNORE-L23` removes this rule (only on a user decision, for example if L23 is cancelled).
1. At most 12 other projects run (the L23 limit). The others are batch2, 3L, 4p1-3, 5L, 6L, L7-20, L22, L7-20b and L23. While L23 has queued rows, it counts as min(4, running + queued): its 4 worker slots. So L1r never takes the slot of an L23 row that is about to start. At most 14 run after the start.
2. MemAvailable ≥ 120 GiB.
3. /data has ≥ 1600 GiB free: the guard floor 800 GiB, plus about 700 GiB for L1r, plus a margin.
4. The gate passed for the HEAD of the copy.
5. The local inputs check (`~ec2-user/L1r-input/SHA256SUMS`).

A STOP file in /bL1r/ctp holds the start. `census-L1r-wait --decide-only` prints the decision and exits (0 = start, 1 = wait). It starts nothing. P2 ran it on the real state at 14:04 UTC: "L23 inactive, not started; other projects running 13 (max 12) … /data free 1395G (min 1600) …; census L23 has not started (L1r starts after L23): waiting", rc 1. The local tests (all overrides) gave the expected result for each rule.

## Firm protection (oom_score_adj -500)

`census-L1r-firm.timer` runs `census-L1r-firm` every 30 s. It finds the processes whose argv holds `/bL1r/ctp/firm_attribution.py` and whose cgroup is `census-L1r.service`, and it sets oom_score_adj to -500 if it is higher. This is the protection that the L7-20 kernel firm steps got by hand at 00:40 UTC. It is automatic here because the firm step comes many hours after the start. It protects the firm step of both projects: an OOM kill in firm retries the project from step 2 (25.9 h or 36.4 h on batch 1). Linux's firm step needed 15.7 GB RSS on batch 1; the kernel firm steps of L7-20 used about 40 GB. Status: `/run/census-L1r-firm.status` (also the "firm protect:" line of `L1r/live/progress.txt`). Events: `/data/logs/L1r-firm.log`. L2b tests it on a fake /proc in a temp dir (no real process changes).

## Power-off

- `census-other-done` (backup `.orig-L23`) gets L1r (`census-L1r-wait.service`, `census-L1r.service`, `B/L1r/final/DONE`). Every older finalize then also waits for L1r.
- The guard (`.orig-L23`) fstrims `/bL1r`, and below 800 GiB it writes `/bL1r/ctp/STOP` and `L1r/live/GUARD`.
- `census-backup` (`.orig-L23`) gets the RUNS line `L1r|/bL1r/census-2026-10-L1r|/bL1r/ctp`.

**S3 paths:** `L1r/input/`, `L1r/live/`, `L1r/final/`, `L1r/done/<project>/` (census-backup), `L1r/dryrun/`.

## Local entries (done 2026-10-12 14:03 UTC)

`scripts/W1-watch-entries.sh` added L1r to `~/s3-work/census-watchdog/watchdog.sh` (backup `watchdog.sh.orig-L1r`, mode 755), `status_all.sh` and `fetch_done.sh` RUNS (temp file and atomic mv). `prelim_merge.py` has `"L1r": "57551d7"` in RUN_CREGIT. Before the install the watchdog only logs "L1r: no live status" (no alert). After L3 the live status says "waiting", which the watchdog accepts.

## Steps

0. The user runs `! bash ~/s3-work/upload-L1r.sh`. It must print `ALL OK`.

Then run from `~/s3-work/ec2-L1r/scripts/` (ssm.sh: the script lines go into the SSM `commands` list, file:// JSON, no base64). Save each output in `out/<step>.out`.

1. `./ssm.sh P1-probe.sh 300` (read-only): check that the shared script sha256 values are still the L23 ones (dfc79946, 3aea045a, ba1a206a) and that /data has room.
2. `./ssm.sh L1-setup.sh 3600`: image, inputs (from S3), ctp clone, cregit copy, configs, gate helpers.
3. `bash gen-L2.sh` (only if a `remote-L/` file changed; the 3 install scripts are already built), then `./ssm.sh L2a-install.sh`, `./ssm.sh L2a2-install.sh`, `./ssm.sh L2b-install.sh`. L2b checks NeedDaemonReload=no on every census unit, runs `daemon-reload`, and checks that the running census units are unchanged (MainPID and ActiveEnterTimestamp, before and after). Then it runs the tests: the power-off rule T1-T8, the waiter W1-W12 and the firm protection F1-F2. Nothing powers off, nothing starts.
4. `./ssm.sh L3-gate-start.sh 3600`: the gate (about 3-5 min), a dry-run finalize, then the live timer, the firm timer and the waiter. L3 can end with exit 1 on its last line if the waiter has not started the census (this is expected while L23 waits).
5. `./ssm.sh R1-check.sh 300` (read-only).

`W1-watch-entries.sh` already ran (see above); it is idempotent.

## Open points for the user

- The /data floor 1600 GiB and the 12-project limit. L23 itself waits for /data ≥ 2000 GiB, and /data fell from 1472 G to 1395 G between 13:53 and 14:04 UTC. L1r cannot start before L23 starts.
- The firm protection covers both projects (not only Linux).

## Files

- `scripts/`: `ssm.sh`, `P1-probe.sh` and `P2-probe.sh` (read-only), `build-L1r-input.py` (local), `L1-setup.sh`, `gen-L2.sh` (builds `L2a`, `L2a2` and `L2b-install.sh`), `L3-gate-start.sh`, `R1-check.sh` (read-only), `W1-watch-entries.sh` (local, done), `remote-L/` (the instance files).
- `upload/`: `manifest.L1r.tsv`, `project_meta.L1r.json`, `SHA256SUMS`.
- `out/`: the outputs of each step.
- `~/s3-work/upload-L1r.sh`: the user-run upload.
