# dataset-x1k runbook (2026-10-17)

The x1k test run: the 7,215 frame v4 projects with 1,000-4,999 commits, up to blame only (ctp `--no-firm`).
Plan, counts, decisions: `${RUNNER_PROJECTS_TILDE}/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection/x1k/README.md`.
Every shell: `export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""`.

## Files

- `stage/`: the upload content (11 files, SHA256SUMS). Built from the study repo `x1k/` and `${RUNNER_PROJECTS_TILDE}/ctp-x1k` (`git diff ca113e3`).
- `U1-upload-x1k-inputs.sh`: the user runs it: `! bash ~/s3-work/dataset-x1k/U1-upload-x1k-inputs.sh`. It must print ALL OK.
- `L1-launch.sh`: one spot instance through an EC2 Fleet (launch template cregit-census-batch3-spot, as `ec2-batch3/launch_fleet.sh`). Defaults: TYPE=c6id.32xlarge, SUBNETS=${RUNNER_SUBNET_AZ_D} (${RUNNER_AWS_REGION}d), NAME=dataset-x1k-a. Log: `instances.txt`, `fleet/`.
- `scripts/ssm.sh`: `I=<id> bash scripts/ssm.sh SCRIPT [TIMEOUT_S]` runs SCRIPT as root on the instance (copy of `ec2-batch6/scripts/ssm.sh`; output in s3://.../ssm-out/).
- `scripts/R1-setup.sh`: layout (4 XFS /data1-4), batch 2 inputs, cregit bundle 57551d7, the AMI cregit tree, 4 part trees /dataK/x1k (ctp clone ca113e3 + venv, own cregit copy at 57551d7, config /etc/dataset-x1k/pK.cfg).
- `scripts/R2-gate.sh`: the identity gate of each copy (libsrcml dea4467b, libexpat Parquet 14eb5d72 with the unpatched ca113e3, blobExec jar). Result /etc/dataset-x1k/pK.check.
- `scripts/R3-install.sh`: x1k-run, x1k-upload, x1k-live, x1k-watch, x1k-finalize and their units. Starts nothing.
- `scripts/R4-start.sh`: inputs from S3, patch + ctp tests + no-firm check, manifest.run.tsv per part (minus done/OK), start. WORKERS=6 default.
- `scripts/C1-check.sh`: read-only progress (counts, rate, ETA, memory).
- Machine B of the relaunch (2026-10-19, full pipeline, 2 machines b1 and b2; steps in "Machine B runbook" below): `L1-launch-b.sh`, `scripts/w6/ssm-run.sh`, `scripts/w6/R3-install-b.sh`, `scripts/w6/R4-start-b.sh`. R1, R2, C1 and `ssm.sh` do not change. The old scripts do not change.

## Steps

1. User: `! bash ~/s3-work/dataset-x1k/U1-upload-x1k-inputs.sh` -> ALL OK.
2. Launch: `bash ~/s3-work/dataset-x1k/L1-launch.sh` (other type or AZ only with the user's yes; for c6id.24xlarge use WORKERS=5 in step 6).
3. Wait for SSM: `aws ssm describe-instance-information --filters Key=InstanceIds,Values=<id> --query 'InstanceInformationList[].PingStatus'` -> Online.
4. `I=<id> TAILN=40 bash scripts/ssm.sh scripts/R1-setup.sh 3600` (ends "R1 done").
5. `I=<id> TAILN=20 bash scripts/ssm.sh scripts/R2-gate.sh 3600` (4 x "CHECK OK", rc=0), then `I=<id> bash scripts/ssm.sh scripts/R3-install.sh 600`.
6. After step 1 printed ALL OK: `I=<id> TAILN=40 bash scripts/ssm.sh scripts/R4-start.sh 3600` (NOFIRM OK, 4 units active).
7. Watch: `aws s3 cp s3://${RUNNER_BUCKET}/dataset-x1k/live/progress.txt -`; detail: `I=<id> TAILN=80 bash scripts/ssm.sh scripts/C1-check.sh 300`.

## Stop, interruption, end

- Stop after the running projects: touch `/dataK/x1k/ctp/STOP` (K = 1..4) through ssm. Touch `/home/ec2-user/NO_SHUTDOWN` first, or the finalize terminates the machine when all parts end.
- Spot notice: x1k-watch touches STOP, writes live/INTERRUPTED and uploads the finished projects. Relaunch: steps 2-6 with a new NAME (for example dataset-x1k-b). R4 runs only the rows without done/OK.
- End: x1k-finalize copies ledgers and logs to final/pK/, checks sizes, writes final/DONE, then `shutdown -h +2` (the instance terminates). A part that ended without "census finished" gives live/ALERT and no shutdown.
- Never touch spot a (${RUNNER_EC2_SPOT_A6}) or the big EC2 (${RUNNER_EC2_BIG}). The scripts refuse to run there.

## Log

- 2026-10-17 about 01:20-01:46 UTC: 4 x L1-launch.sh (c6id.32xlarge, ${RUNNER_AWS_REGION}d): UnfulfillableCapacity. No instance. Spot price then: 2d $1.25, 2b $2.23, 2c $2.34, 2a $2.66; c6id.24xlarge 2b $0.77. Placement score of c6id.32xlarge: 1 in all AZs.
- 2026-10-17 02:40 UTC: user decision: c6id.24xlarge in ${RUNNER_AWS_REGION}b, WORKERS=5; keep RMerl/asuswrt-merlin.ng running. L1-launch.sh (TYPE=c6id.24xlarge, ${RUNNER_SUBNET_AZ_B}) failed: UnfulfillableCapacity (fleet-a61e9c95...). Placement score of c6id.24xlarge: 1 in all AZs. Stopped as instructed (no other type or zone). No instance; R1-R4 not run.
- 2026-10-17 15:35 UTC: user decision: i4i.24xlarge spot in ${RUNNER_AWS_REGION}c (usw2-az3, score 3), 5 workers per part. Launched ${RUNNER_EC2_X1K_A} (NAME dataset-x1k-a, ${RUNNER_SUBNET_AZ_C}, spot price $2.3428/h, 96 vCPU, 743 GiB, 6 NVMe disks of 3.5 TB; parts on /data1-4). R1 ok 15:42 (R1 now accepts >= 4 disks); R2: 4 x CHECK OK 15:45 (libsrcml dea4467b, libexpat 14eb5d72); R3 installed. The user ran U1: ALL OK.
- 2026-10-17 15:48:29 UTC: RUN STARTED (R4, scripts/w5/R4-start.sh = R4 with WORKERS default 5): patch on all 4 clones, ctp tests 737 passed + 8 skipped, NOFIRM OK (67 vs 70 columns, 195,662 rows, 0 differing rows). Rows p1 1,756, p2 1,655, p3 1,962, p4 1,842 (7,215); 4 x 5 = 20 workers. RMerl/asuswrt-merlin.ng runs until the next morning; the user decides then. Watch: aws s3 cp s3://${RUNNER_BUCKET}/dataset-x1k/live/progress.txt - ; detail: I=${RUNNER_EC2_X1K_A} TAILN=80 bash scripts/ssm.sh scripts/C1-check.sh 300.
- 2026-10-18 22:02 UTC: spot reclaim of ${RUNNER_EC2_X1K_A} (see "Relaunch plan"). 1,377 rows have done/OK.
- 2026-10-19: the user approved the relaunch. Machine B scripts prepared and dry-run (see "Machine B runbook"). No launch yet.
- 2026-10-19: b1 launched by the main session: dataset-x1k-b1 = ${RUNNER_EC2_X1K_B1} (i4i.24xlarge, ${RUNNER_AWS_REGION}a, $2.37/h); R1 done. User decision: the x1k rows join the released dataset. The B scripts changed to the full pipeline (unpatched ca113e3, firm step), the new done set `done-full/`, and 2 machines (slot 1 = b1, slot 2 = b2).
- 2026-10-19 17:30 UTC: machine A scripts written for the full pipeline (L0, L1-launch-a, L2, scripts/a/; unpatched ca113e3, firm step, `done-full/`); local resume test passed (kill in step 7 -> `--from-step 7`, kill after step 10 -> `--from-step 11`: both Parquets = gate 14eb5d72 byte for byte); EC2 DryRun of the volumes and the fleet: would succeed. No volume or instance for A yet (see "Machine A runbook").

## Relaunch plan (proposal, not run)

Written 2026-10-18 after the spot reclaim of 22:02 UTC. Nothing here ran. No instance, volume, fleet or spot request exists for it. Every launch, volume and upload needs the user's yes.

### Facts used

- Done: 1,377 of 7,215 (`aws s3 ls --recursive dataset-x1k/done/`, 1,377 `OK` objects). Not done: 5,838.
- Long rows (machine A, 11 rows; manifest file and row):
  - p1 row 1 `RMerl__asuswrt-merlin.ng` (4,633 MB tokenizable, 4,877 commits).
  - p2 row 1 `awslabs__aws-sdk-rust` (1,845 MB); p2 row 2 `metashell__metashell` (555 MB); p2 row 7 `microsoftgraph__msgraph-beta-sdk-java` (214 MB).
  - p3 row 1 `aws__aws-sdk-java` (1,023 MB); p3 row 2 `TencentCloud__tencentcloud-sdk-cpp` (625 MB); p3 row 4 `googleapis__google-cloud-rust` (429 MB); p3 row 5 `Byron__google-apis-rs` (356 MB).
  - p4 row 4 `autc04__Retro68` (445 MB).
  - Two small rows that probably hung: p1 row 328 `notnotype__neuro-book` (0.06 MB, >= 15.2 h) and p1 row 500 `pur1fying__blue_archive_auto_script` (0.35 MB, >= 11.7 h). The cause is not known. The ledgers `live/ledger.p1.jsonl` can tell. This plan did not read them (no download).
  - (Row numbers count data rows; `manifest.x1k-pK.tsv` has 2 comment lines first.)
- Light rows (machine B): 5,827 = 5,838 - 11. 38 of them are "heavy" (35-153 MB). They are at the top of p2-p4. (2026-10-19: by size, 168 of the 5,827 have >= 30 MB tokenizable; R4-start-b.sh puts these first. See "Machine B runbook".)
- Measured wall time per done project (clone log name to `OK` time, from the S3 listing): < 1 MB 0.037 h, 1-3 MB 0.046 h, 3-10 MB 0.097 h, 10-30 MB 0.22 h, 30-100 MB 0.65 h, 100-200 MB 4.3 h (Telegram forks: Nullgram 15.4 h, Nagram 12.0 h). Applied to the 5,827 rows: about **600 worker-hours**.
- At 4 blame jobs, the SDK rows of this run took 17.7 h (tencentcloud-sdk-java, 289 MB) and 20.5 h (tencentcloud-sdk-cpp-intl-en, 366 MB). The 9 long rows ran 30.2 h and did not end.
- v1 asuswrt (gnuton, 234,044 files): blame at 4 jobs about 3,700 files/h; with a 32-job helper 73,000 files/h. Step 10 took 11-19 h with `--memory-limit 16GB` and spilled more than 502 GiB (memory note census-runs-20261009).

### Answers that the plan uses

1. Resume. ctp keeps no per-step markers. The record is the "Step N ... completed" lines in `out/<p>/pipeline.log`. A census restart skips done projects (`ctp.py` `plan()`, 1555-1563). For a not-done project, auto-resume (`ctp.py` 860-875) runs only when `--from-step` is 1. `resume_step` (776-785) returns 2 or 1, never 7. Then `drop_derived` (797-814) deletes `blame/`, the working clones, the DBs and the Parquet. So a plain restart redoes step 2 (per blob, with the memo), steps 3-6, and **all** of step 7. cregit itself skips a finished file: `blameRepoFiles.pl` 97-100 (`-f $outputFile`, existence only). At 57551d7, `formatBlame.pl` writes to a temp file and renames it only after git exits 0 (82-95). So a killed blame leaves no `.blame`. **Operator route, no code change:** start the project in its own census with `--from-step N` (N = last completed step + 1). With N > 1 there is no `drop_derived`, and step 7 skips the finished `.blame` files. The paths must stay the same (blobExec stores the cregit path). Every lost attempt counts as one retry (`ledger.py` 79-112), so use a high `--retries`. **Smallest code change** (not needed for this plan): `resume_step` returns 7 when the step-6 clones, the persons DB and `blame/` exist; `build_steps` calls `drop_derived` only for step 2 (the "Fix 5" of `s7-run/speed-impact-20261008.md`).
2. repoblame. No flag or path in ctp or cregit uses it (grep: 0 hits). v1 did not use it for google-cloud-java: v1 used `git blame -C100` with a 4-job runner, a helper of up to 88 jobs (cregit 365a47a) and plan B on spot b. Its output format is `<commit> <orig_line> <orig_path>` per line. cregit's `.blame` is `<sha>;<orig_path>;<text>`. There is no converter. Its result equals `git blame -C100` on the samples (474,664 gcj lines, 120,195 Linux lines). It is not equal to the ctp stage on the files that hit the 3600 s limit, because cregit then uses plain blame. Speed: 5.1-8.1x less CPU on google-cloud-java (commits that touch 10,000+ files). 5.3x **more** CPU on Linux `net/ipv4`. Generated SDK repositories can be like gcj, but nobody measured it. asuswrt-merlin.ng is a Linux-like tree: expect it to be slower. Decision of this plan: do not use repoblame.
3. CPU and memory. `--blame-jobs N` gives N parallel `git blame` per project (`blameRepoFiles.pl` 158-178, largest file first, no cap). ctp `--workers` runs more projects at once. It does not make one project faster. More blame jobs help while many files are open (asuswrt 4 to 32 jobs: about 20x more files per hour). `git blame -C100` uses 0.5-1.4 GB per process. With 64-92 jobs, the v1 spots kept about 740 GB free. CPU is the limit for blame. Disk and the DuckDB memory limit are the limits for step 10. The 3600 s limit is wall time per file. More load gives more PLAIN-BLAME files, so keep the blame jobs below the vCPU count.

### Machines (${RUNNER_AWS_REGION}, 2026-10-18 about 23:00 UTC)

Spot: price now per AZ 2a/2b/2c/2d (7-day range of the cheapest AZ). Score: `get-spot-placement-scores`, one type, target 1, single AZ, 2a/2b/2c/2d (usw2-az1..az4). On-demand: the Pricing API, Linux, shared tenancy.

| Type | vCPU | GiB | Disk | On-demand $/h | Spot $/h 2a / 2b / 2c / 2d | Score 2a/2b/2c/2d |
| --- | ---: | ---: | --- | ---: | --- | --- |
| m6a.48xlarge | 192 | 768 | EBS | 8.29 | 3.52 / 2.92 / 3.43 / **2.38** (2.36-2.43) | 3 / 1 / 3 / 2 |
| m8i.48xlarge | 192 | 768 | EBS | 10.16 | 3.98 / 4.44 / 3.49 / 2.50 | 3 / 3 / 2 / 2 |
| m7i.48xlarge | 192 | 768 | EBS | 9.68 | 3.79 / 3.98 / 3.82 / 3.75 | 1 / 3 / 3 / 3 |
| c6a.48xlarge | 192 | 384 | EBS | 7.34 | 2.85 / 3.19 / 2.98 / 2.46 | 3 / 3 / 3 / 3 |
| c7i.48xlarge | 192 | 384 | EBS | 8.57 | 4.54 / 4.62 / 4.52 / 3.45 | 3 / 3 / 3 / 3 |
| m6i.32xlarge | 128 | 512 | EBS | 6.14 | 1.76 / 1.78 / 2.36 / 1.83 | 1 / 1 / 3 / 3 |
| r6i.32xlarge | 128 | 1,024 | EBS | 8.06 | 2.94 / 3.03 / 2.87 / 1.88 | 1 / 3 / 3 / 1 |
| m6id.32xlarge | 128 | 512 | 4 x 1.9 TB | 7.59 | 3.23 / 2.84 / 3.60 / 2.68 | 1 / 1 / 1 / 3 |
| i4i.32xlarge | 128 | 1,024 | 8 x 3.75 TB | 10.98 | 3.55 / 3.39 / 2.98 / 2.12 | 3 / 3 / 3 / 1 |
| c6id.32xlarge | 128 | 256 | 4 x 1.9 TB | 6.45 | 2.60 / 2.23 / 2.28 / 1.17 | 1 / 1 / 1 / 1 |
| i4i.24xlarge | 96 | 768 | 6 x 3.75 TB | 8.24 | 2.38 / 3.19 / 2.36 / 3.06 | 3 / 3 / 3 / 3 |
| r6id.24xlarge | 96 | 768 | 4 x 1.4 TB | 7.26 (3/4 of r6id.32xlarge 9.68) | 3.52 / 2.57 / 3.51 / 3.67 | 3 / 3 / 3 / 2 |
| m6id.24xlarge | 96 | 384 | 4 x 1.4 TB | 5.70 | 2.30 / 1.32 / 2.90 / 2.95 | 2 / 1 / 1 / 3 |
| c6id.24xlarge | 96 | 192 | 4 x 1.4 TB | 4.84 | 1.47 / 0.78 / 1.46 / 1.49 | 1 / 1 / 1 / 1 |

Type lists (one fleet may choose): A list (m6i.32xlarge, r6i.32xlarge, m6a.48xlarge, c6a.48xlarge, m7i.48xlarge, m8i.48xlarge, c7i.48xlarge): score **9** in every AZ. B list (c6id.24xlarge, i4i.24xlarge, m6id.24xlarge, r6id.24xlarge, c6id.32xlarge, i4i.32xlarge, m6id.32xlarge): score **9** in every AZ. EBS gp3 in ${RUNNER_AWS_REGION}: $0.08 per GB-month, $0.005 per IOPS-month above 3,000, $0.04 per MiB/s-month above 125. Quotas: 1,152 vCPU on-demand, 1,152 vCPU spot.

### Machine A: the 11 long rows

- Market: spot, an EC2 Fleet with the A list in **one AZ, ${RUNNER_AWS_REGION}d** (${RUNNER_SUBNET_AZ_D}). EBS volumes stay in one AZ, so a relaunch must use the same AZ. Fallback: the same fleet as on-demand in ${RUNNER_AWS_REGION}d (m6a.48xlarge, $8.29/h).
- Work disk: 4 gp3 volumes, made before the launch, `DeleteOnTermination` false, encrypted, 12,000 IOPS, 500 MiB/s each. Sizes: v1 3 TB (asuswrt alone; v1 needed a 2.5 TB image for step 10), v2 2 TB (aws-sdk-rust, the 2 small rows), v3 2 TB (aws-sdk-java, tencentcloud-sdk-cpp, metashell), v4 2 TB (google-cloud-rust, google-apis-rs, msgraph-beta-sdk-java, Retro68). 9 TB: about $0.99/h storage + $0.33/h IOPS and throughput = **$1.32/h** while the volumes exist.
- One census per project (a one-row manifest), so each project has its own `--from-step`, `--blame-jobs` and `--memory-limit`. Each project has its own tree `/dataK/x1k/<project>/` (ctp clone, cregit copy 57551d7, out, logs). `--workers 1 --retries 10`, other flags as before.
- Blame jobs on 192 vCPU (sum 160): asuswrt 32, aws-sdk-rust 28, aws-sdk-java 20, tencentcloud-sdk-cpp 16, google-cloud-rust 16, google-apis-rs 16, metashell 12, Retro68 8, msgraph-beta-sdk-java 8, the 2 small rows 2 each. On 128 vCPU: two thirds of these.
- `--memory-limit` (step 10): asuswrt 300GB on 768 GiB (150GB on 384-512 GiB), all others 24GB. ctp warns when 1.4 x limit does not fit.
- Expected wall time: **20-40 h** (estimate, not measured). Basis: the SDK rows scale with size (366 MB took 20.5 h at 4 jobs, so aws-sdk-rust is about 100 h at 4 jobs and about 15-20 h at 28 jobs), plus step 2 and step 10. asuswrt: steps 2-7 took about 8 h at 32 jobs in v1, step 10 took 11-19 h at 16GB (expect less at 300GB; not measured).
- Cost: spot $1.83-2.50/h x 20-40 h = $37-100, plus EBS $26-53: **about $65-155**. On-demand for all of it: $166-332 + EBS.
- Spot reclaim: the volumes keep the work. Relaunch in ${RUNNER_AWS_REGION}d with L1 (spot; after 30 min without capacity: on-demand), attach the 4 volumes (L2), R1 (mount only, no mkfs), R2, R3, R4. R4 starts each project from the step after its last completed step. A reclaim loses the files in progress in step 7 (up to about 1 h each, because of the 3600 s limit), or the running step 10 (asuswrt: some hours), not the whole project.

### Machine B: the 5,827 light rows

- Market: spot, an EC2 Fleet with the B list in all 4 AZs (instance store; price-capacity-optimized). Most likely result: i4i.24xlarge in 2a/2c ($2.36-2.38/h), or a 128-vCPU type.
- WORKERS from `nproc`: 5 per part on 96 vCPU (20 workers), 6 per part on 128 vCPU (24 workers). Flags as before (`--blame-jobs 4 --memory-limit 16GB`, `--retries 3`).
- Manifest split: on the instance, R4 takes the 4 part manifests from `inputs/`, removes the rows with `done/OK` and the 11 A rows, and deals the rest row by row to 4 new parts. The 38 heavy rows stay at the top (as made on 2026-10-19: the 168 rows with >= 30 MB, largest first). Each part gets about 1,457 rows. No new upload is necessary.
- Done rows: skipped twice: R4 removes the `done/OK` rows, and ctp `plan()` skips a project with a done ledger row and a stamp.
- Expected wall time: 600 worker-hours / 20 = **about 30 h** (96 vCPU); / 24 = **about 25 h** (128 vCPU). The longest single rows (Telegram forks, 100-200 MB) take up to about 15 h and start first.
- Cost: $1.2-2.6/h x 25-30 h = **about $30-80** (expected about $60-70 on i4i.24xlarge).
- Spot reclaim: as before. The uploader sends each finished project to `done/`. Relaunch with a new NAME. R4 runs only the rows without `done/OK`. A reclaim loses only the running projects (most < 1 h; the heavy rows run in the first 15 h).
- Option: two B machines with 2 parts each (the same cost, about 15 h).

### Total

- A and B run at the same time. Wall time: **about 30-40 h** (A sets the end). Cost: **about $95-235** (both spot, A with EBS). With A on-demand: about $220-465.
- After the end: the A volumes stay and cost $1.32/h until the user deletes them (after the check of `done/`).

### Script changes (A: made on 2026-10-19, see "Machine A runbook"; B: made on 2026-10-19)

For A (new folder `long/`, so the B scripts stay as they are):
- `L0-volumes.sh` (new): create the 4 gp3 volumes in ${RUNNER_AWS_REGION}d with tags Run=x1k-long, Slot=1..4. It refuses if a volume with these tags exists.
- `L1-launch.sh`: `TYPES` (a list; one override per type and subnet) instead of `TYPE`; `MARKET=spot|on-demand` (DefaultTargetCapacityType); for A one subnet in ${RUNNER_AWS_REGION}d. Add the A and B instance ids to the refuse list.
- `L2-attach.sh` (new): attach the 4 volumes (by tag) as /dev/sdf-sdi. It refuses if a volume is attached to another instance or is in another AZ.
- `R1-setup.sh`: an EBS mode: find each volume by its NVMe serial (the volume id), mount Slot K at `/dataK` (the same path on each relaunch). Run mkfs only if `blkid` finds no file system. Never mkfs a volume with XFS. Make one tree per project, not per part; keep the trees that exist.
- `R2-gate.sh`: gate each project's cregit copy; skip a copy with `CHECK OK` and the same cregit commit.
- `R3-install.sh`: a unit `x1k-long@<project>`. Its run script reads the last "Step N ... completed" line of `out/<p>/pipeline.log`. If N >= 6, it runs the census with `--from-step N+1`; else a plain census (step-2 resume). Before the start it removes `blameRepo/build/tmpfile-*`. Flags per project from `/etc/dataset-x1k/long.tsv` (blame jobs, memory limit). `x1k-watch`: on a spot notice touch STOP in each tree and `sync`. `x1k-finalize`: as before (the volumes stay after the instance terminates).
- `R4-start.sh`: one-row manifests for the 11 rows minus `done/OK`; start the 11 units.
- `C1-check.sh`: per project: the step now, `.blame` count against the file count, PLAIN-BLAME count, free space per volume.
- Test before the launch: on the dev machine, stop a small project in step 7, then run it with `--from-step 7`. The Parquet must equal a full run (the libexpat gate 14eb5d72).

For B (made on 2026-10-19; see "Machine B runbook"):
- `L1-launch-b.sh` (new copy): `TYPES` with the B list and the 4 default subnets.
- `scripts/w6/R4-start-b.sh` (new copy): WORKERS from `nproc`; the exclude list of the 11 A rows; the re-deal of the remaining rows to 4 parts.
- `scripts/w6/R3-install-b.sh` (new copy) and `scripts/w6/ssm-run.sh` (new): a run id, so that the live and final files of each B run go to their own prefix.
- `R1`, `R2`, `C1`, `ssm.sh`: no change (R1 accepts >= 4 instance-store disks; all B types have 4-8).

### Decisions for the user

1. Relaunch, or stop at 1,377 rows. (p1 is in u order, so its 1,183 done rows are a random sample of the light rows.)
2. Machine A: spot + EBS + the resume scripts (cheaper, about half a day of script work and a local test), or on-demand (no reclaim; same scripts without the volume part, or instance store m6id.32xlarge).
3. A type list and AZ (proposal: the A list in ${RUNNER_AWS_REGION}d).
4. Blame jobs on A. More jobs end sooner but give more PLAIN-BLAME files. Record the count in LIMITATIONS.
5. The 2 small rows: run them on A, or drop them. Reading `live/ledger.p1.jsonl` first can show why they hung (a download; the user's yes).
6. Machine B: one machine (25-30 h) or two (about 15 h).
7. Delete the A volumes after the end (the user deletes them).

## Machine B runbook (full pipeline, 2 machines; prepared 2026-10-19)

State on 2026-10-19: the main session launched b1 = dataset-x1k-b1 = ${RUNNER_EC2_X1K_B1} (i4i.24xlarge, ${RUNNER_AWS_REGION}a, spot $2.37/h). R1 is done. R2 ran at the time of this text. R3-b and R4-b did not run. b2 does not exist.

User decision 2026-10-19: the x1k rows join the released dataset. So B runs the **full pipeline** with the v1 code. This replaces the `--no-firm` plan for B. No upload is necessary: ssm.sh sends the script text, and R4-start-b.sh uses the inputs of the first run (`inputs/`).

### The v1 code path

- v1 batches 23-26: ctp ca113e3, cregit 57551d7, libexpat gate 14eb5d72 (ec2-batch23/README.md, ec2-batch25/README.md). cregit 57551d7 is on 1f17663 (one trailer entry per person) plus the 3600 s blame limit. Thus the trailer post-fix (footer-fix) is not necessary for these Parquets.
- Flags of the v1 fed parts (`census-fed-run` in ec2-batch6/scripts/s6-files-0.sh): `--retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb <floor>`. B uses these with `--disk-floor-gb 300` and `--workers` 5 or 6 per part. The first x1k run added `--no-firm`. B does not.
- The no-firm patch (`stage/ctp-no-firm.patch`, ctp ab652d0) changes `ctp.py` and `validate.py`, and adds tests. It adds the flag `--no-firm`: no firm step, no join, and `validate --cregit-only`. B does not apply the patch. The ctp clones that R1 made are the clean ca113e3. x1k-run and R4-b refuse a clone that is patched or changed.
- R2 is the proof on each part's own cregit copy: unpatched ca113e3, full steps with the firm step, libexpat Parquet = 14eb5d72 (the gate of the v1 batches 7-26). R4-b checks again: 14eb5d72 and 70 columns.
- The v1 freeze steps after the run are not on the machine. As for v1, they run at the merge: the meta rewrite with the final sidecar, the pseudonymization, and the ZSTD 19 re-encode (memory note v1-freeze-decisions). B writes the raw per-project Parquets that v1 also had before these steps.

### Done set

- The new done set is `s3://.../dataset-x1k/done-full/<p>/OK`. x1k-upload writes there, and it does not write into a `done-full/<p>/` that has an OK.
- The old `done/` (1,377 rows of the `--no-firm` run, without the firm columns) stays as it is. No B script writes to it or reads it. Thus these 1,377 rows run again in full.

### The deal (2 machines, 8 parts)

- A fixed deal of all rows minus the 11 machine-A rows (7,204) to 8 parts. b1 (slot 1) runs parts 1-4, b2 (slot 2) runs parts 5-8, each on its /data1-4. The deal does not use the done set. Thus each machine and each relaunch gets the same parts. After the deal, each part drops the rows with `done-full/<p>/OK`.
- Heavy rows first: the 273 non-A rows with >= 30 MB tokenizable or >= 1 h measured in the first run, longest first. Each goes to the part with the least heavy hours so far (LPT). The hours are the measured wall time of the first run (for the rows in `done/`), else the measured mean of the size class. Then the light rows go row by row in u order.
- The slot comes from the NAME: dataset-x1k-b1 is slot 1 and dataset-x1k-b2 is slot 2. After a reclaim the NAME is dataset-x1k-b<slot>-r1, -r2 (the same slot, a new run id). R3-b writes `/etc/dataset-x1k/run` and `/etc/dataset-x1k/slot`.

### Dry run (2026-10-19, local, deal code of R4-start-b.sh unchanged)

- Input: `stage/` (equal to `inputs/`), with an empty done-full set (the prefix is empty now).
- Slot 1: 900 + 901 + 901 + 901 = 3,603 rows. Slot 2: 901 + 900 + 901 + 899 = 3,601 rows. Each part has 33-35 heavy rows and 54 estimated heavy hours.
- The two slots together are exactly the 7,215 rows minus the 11 A rows, with no overlap. The lines are the source lines without change. Both slots write the same `deal.tsv`.
- Relaunch test: 400 rows of part 2 marked as done-full. The slot 1 rerun drops only these 400, and slot 2's manifests stay byte-equal. An OK name that is not in the manifests stops R4-b.

### Time and memory

- Worker-hours: the 1,377 rows of the first run took 322 h (measured, clone to OK). The other 5,827 take about 601 h (measured per-size means). The firm step, the join and the full validate add 0.4-3.7% (local full runs census-local-a/b/c/d, 70 projects, metrics.tsv; mean about 2%). Total: **about 950 worker-hours** (range 920-1,030).
- One machine (20 workers): about 48 h. This is much more than 30 h, so the plan uses **two machines**.
- Per part (deal part, worker-hours / 5 workers): 23-24.4 h. The longest single row is 20.5 h (TencentCloud__tencentcloud-sdk-cpp-intl-en), and it starts first in part 1. Each machine: **about 24-25 h** on 96 vCPU, about 20 h on 128 vCPU.
- Memory for the firm step and step 10: `--memory-limit 16GB` per project (ctp warns when 1.4 x 16 = 22.4 GB does not fit). ctp checks `--min-free-mem-gb 24` only when it starts a project. On i4i.24xlarge (743 GiB, 20 workers): 37 GiB per worker; 20 x 22.4 GB = 448 GB also fits. Measured at 16GB: wine firm 412 s, tensorflow 308 s, google-cloud-java 85 min (248 M rows). The x1k rows are at most 790 MB tokenizable. For b2, L1-launch-b.sh now takes by default only the types with >= 768 GiB: i4i.24xlarge, r6id.24xlarge, i4i.32xlarge, r6id.32xlarge. c6id and m6id (192-512 GiB) only with an explicit `TYPES`.

### Prices and scores (2026-10-19 about 17:10 UTC, for b2)

- Placement score of the 4 default types: 9 / 9 / 9 / 6 (usw2-az1..az4).
- Spot $/h (2a / 2b / 2c / 2d):
  - i4i.24xlarge: 2.37 / 3.15 / 2.36 / 3.08.
  - r6id.24xlarge: 3.52 / 2.54 / 3.48 / 3.74.
  - i4i.32xlarge: 3.56 / 3.39 / 3.08 / 2.07.
  - r6id.32xlarge: 4.89 / 4.83 / 5.25 / 2.81.
- Most probable: i4i.24xlarge in 2c ($2.36/h). With `MAX_TOTAL_PRICE=3.50` the fleet does not take a pool above $3.50/h. The EC2 DryRun of the b2 fleet said "Request would have succeeded".

### Cost

- b1: about 25 h x $2.37 = about $59. b2: about 25 h x $2.36 = about $59. Total about **$120** (range $105-150), plus the setup (about 20 min each) and the hours of b1 before R4.
- One machine only: about 48 h, about $115, two times the wall time.

### Launch steps (main session, in this order)

Every shell: `export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""` and `cd ~/s3-work/dataset-x1k`.

b1 (${RUNNER_EC2_X1K_B1}; R1 is done):
1. R2 must end with 4 x "CHECK OK", rc=0.
2. R3-b: `RUN=dataset-x1k-b1 I=${RUNNER_EC2_X1K_B1} TAILN=20 bash scripts/w6/ssm-run.sh scripts/w6/R3-install-b.sh 600` -> "run id dataset-x1k-b1, slot 1 ..." and "R3-b installed (run dataset-x1k-b1)".
3. R4-b: `I=${RUNNER_EC2_X1K_B1} TAILN=40 bash scripts/ssm.sh scripts/w6/R4-start-b.sh 3600` -> 4 x "ctp ca113e3 clean, not patched; gate Parquet 14eb5d72, 70 columns", ctp tests passed, "slot 1: 3603 to run, 0 with done-full/OK", 4 units active, "R4-b done".

b2 (new machine):
4. L1: `NAME=dataset-x1k-b2 MAX_TOTAL_PRICE=3.50 bash L1-launch-b.sh` (default TYPES: the 4 types with >= 768 GiB, 4 AZs) -> "INSTANCE_ID TYPE SUBNET".
5. SSM: `aws ssm describe-instance-information --filters Key=InstanceIds,Values=<b2 id> --query 'InstanceInformationList[].PingStatus' --output text` -> Online.
6. R1: `I=<b2 id> TAILN=40 bash scripts/ssm.sh scripts/R1-setup.sh 3600` -> "R1 done".
7. R2: `I=<b2 id> TAILN=20 bash scripts/ssm.sh scripts/R2-gate.sh 3600` -> 4 x "CHECK OK", rc=0.
8. R3-b: `RUN=dataset-x1k-b2 I=<b2 id> TAILN=20 bash scripts/w6/ssm-run.sh scripts/w6/R3-install-b.sh 600`.
9. R4-b: `I=<b2 id> TAILN=40 bash scripts/ssm.sh scripts/w6/R4-start-b.sh 3600` -> "slot 2: 3601 to run".

Watch (each machine): `I=<id> TAILN=80 bash scripts/ssm.sh scripts/C1-check.sh 300`. Without SSM: `aws s3 ls s3://${RUNNER_BUCKET}/dataset-x1k/live/<run>/` and the count of `done-full/<p>/OK`.

### Spot reclaim and relaunch

- A reclaim loses only the running projects. x1k-upload sends each finished project to `done-full/<p>/` every 2 min. On the notice, x1k-watch touches STOP in each part, writes `live/<run>/INTERRUPTED` and the 4 ledgers, and does one more upload.
- The fleet is of type instant: it does not start a new instance. Relaunch the lost slot with a new NAME: `NAME=dataset-x1k-b<slot>-r1 MAX_TOTAL_PRICE=3.50 bash L1-launch-b.sh`, then steps 5-9 with `RUN=dataset-x1k-b<slot>-r1`. R4-b makes the same deal and runs the rows of the slot without `done-full/<p>/OK`. L1 refuses a slot that has an instance. The machine of the other slot does not stop L1.
- Stop after the running projects: as in "Stop, interruption, end" (first `touch /home/ec2-user/NO_SHUTDOWN`, then STOP in each part).
- End: x1k-finalize copies to `final/<run>/`, checks the sizes, and writes `final/<run>/DONE`. It checks that DONE is in S3 and then runs `shutdown -h +2` (the instance terminates). A part without the line `census finished` gives `live/<run>/ALERT` and no shutdown.
- Refuse list (L1, R3-b, R4-b): ${RUNNER_EC2_BIG} (the big EC2, stopped), ${RUNNER_EC2_SPOT_A6}, ${RUNNER_EC2_X1K_A}.

### Note for machine A

- Updated 2026-10-19 17:30 UTC: the machine A scripts now run the full pipeline (unpatched ca113e3, no `--no-firm`) and upload to `done-full/`. See "Machine A runbook".

## Machine A runbook (written 2026-10-19, not run)

The user approved the relaunch plan on 2026-10-19 (all recommendations). Later on 2026-10-19 the user decided that the x1k rows join the released dataset. Machine A thus runs the **full v1 pipeline**: ctp ca113e3 without a patch (the code of the R2 gate), the flags of the v1 fed parts, no `--no-firm`; the firm step, validate (full check), schema and join run. Results go to the full done set `done-full/<p>/` (as machines B). This section is for machine A: the 11 long rows on spot, with 4 EBS work volumes and resume by `--from-step`. Nothing in it ran: no volume, instance or fleet exists for it. The main session does L0, L1 and L2. No upload is necessary: R4 uses `manifest.x1k.tsv` and `project_meta.x1k.json` from `inputs/` of the first run, and the scripts go to the instance through SSM.

### Files (machine A)

- `L0-volumes.sh`: makes the 4 gp3 volumes in ${RUNNER_AWS_REGION}d (3,000 + 2,000 + 2,000 + 2,000 GiB, 12,000 IOPS, 500 MiB/s, encrypted; tags Project, Owner, Run=x1k-long, Slot=1..4, Name=x1k-long-K). Default: prints the commands. `DRY_RUN=1`: also the EC2 DryRun check. `RUN=1`: makes them and writes `a-volumes.txt` and `scripts/a/vols.env`. It refuses if a volume with Run=x1k-long exists. It never deletes.
- `L1-launch-a.sh`: an EC2 Fleet (instant) with one override per type in ${RUNNER_SUBNET_AZ_D} (${RUNNER_AWS_REGION}d; another AZ is refused). `MARKET=spot` (default; the A list m6i/r6i.32xlarge, m6a/c6a/m7i/m8i/c7i.48xlarge; price-capacity-optimized) or `MARKET=on-demand` (fallback only; default type m6a.48xlarge). `NAME` default dataset-x1k-long-a; tag Run=x1k-long. `DRY_RUN=1`: only the EC2 DryRun check. It refuses if an A instance exists. Refuse list (checked before and after, never the new id): the big EC2 ${RUNNER_EC2_BIG}, spot a ${RUNNER_EC2_SPOT_A6}, every instance with Run=x1k or Run=x1k-b or Name dataset-x1k-b*.
- `L2-attach.sh` (`I=<id>`): attaches the volumes by Slot tag as /dev/sdf..sdi, DeleteOnTermination false (checked). It refuses an instance without Run=x1k-long, a volume in another AZ, a volume on another instance. It writes `scripts/a/vols.env` (X1K_VOLS="1:vol-.. 2:vol-.. 3:vol-.. 4:vol-..").
- `scripts/a/ssm-a.sh` (`I=<id> [TAILN=N] bash scripts/a/ssm-a.sh SCRIPT [TIMEOUT_S]`): sends SCRIPT through `scripts/ssm.sh` as a small wrapper (X1K_VOLS + the script as gzip/base64; R3 is 21 KB, the wrapper about 10 KB, less than the 21 KB of the first R3 that SSM took). It refuses an instance without Run=x1k-long (tested: it refuses B ${RUNNER_EC2_X1K_B1}; nothing was sent).
- `scripts/a/R1-setup.sh`: finds each volume by its NVMe serial (the volume id without "-"). A volume without a signature (`blkid -p` rc 2) gets `mkfs.xfs -L x1k-long-K` (no -f). A volume with a file system is only mounted, and only if it is XFS with the label x1k-long-K; anything else aborts. Mounts at /data1..4 (the same paths on every relaunch), /data -> /data1. Inputs and the AMI cregit template as before. Writes `/data/x1k-long/long.tsv` and makes one tree per row: `/dataK/x1k/<p>` (link `/data/x1k-long/<p>`) with ctp/ (ca113e3 + venv), cregit-ec2/ (own copy at 57551d7), out/, logs/, uploaded/, ctp.cfg. It keeps a tree that exists.
- `scripts/a/R2-gate.sh`: the libsrcml, libexpat 14eb5d72 (full steps with the firm step) and blobExec jar gate of each tree's cregit copy, in parallel. Result `<tree>/gate.check` (on the volume). It skips a tree with CHECK OK for the same cregit commit and the same AMI.
- `scripts/a/R3-install.sh`: `x1k-long-run` and the unit `x1k-long@<p>` (KillMode=mixed, TimeoutStopSec=60, Restart=no), `x1k-long-upload` (to `done-full/<p>/` + OK, every 2 min; never into a prefix with an OK), `x1k-long-status`, `x1k-long-live` (`live-a/progress.txt`, every 10 min), `x1k-long-watch` (spot notice: STOP in each tree, ledgers and INTERRUPTED to `live-a/`, sync, one upload), `x1k-long-finalize` (all units inactive: `final-a/<p>/`, size check, `final-a/DONE`, then shutdown; the volumes stay). It starts nothing.
- `scripts/a/R4-start.sh`: inputs; each tree's ctp must be the clean ca113e3; ctp tests once (`/data/x1k-long/tests.ok`); per row without `done-full/<p>/OK`: `manifest.tsv` (one row of manifest.x1k.tsv) and `run.env`; `run.list`; starts the timers, the watch and one unit per row.
- `scripts/a/C1-check.sh`: read-only. Per project: unit, the last ctp ledger row (pipeline, firm, validate, join ...), step now, last completed step, `.blame` files and the files that step 7 of this attempt started (cregit prints no total), PLAIN-BLAME lines, orphan tmpfile-*, upload, out size; free space per volume; memory; last final ledger row.
- `scripts/a/test/resume-test.sh`: the local resume test (below). Logs: `scripts/a/test/resume-test.out` (full pipeline); `resume-test.nofirm.out` and `resume-test.nofirm.run1.out` (the earlier no-firm version, also passed).

### Rows, slots and flags

| Row | Slot (volume) | Blame jobs on 192 vCPU | `--memory-limit` on >= 700 GiB / on less |
| --- | --- | ---: | --- |
| RMerl__asuswrt-merlin.ng | 1 (3,000 GiB) | 32 | 300GB / 150GB |
| awslabs__aws-sdk-rust | 2 | 28 | 128GB / 64GB |
| notnotype__neuro-book | 2 | 2 | 24GB / 24GB |
| pur1fying__blue_archive_auto_script | 2 | 2 | 24GB / 24GB |
| aws__aws-sdk-java | 3 | 20 | 96GB / 48GB |
| TencentCloud__tencentcloud-sdk-cpp | 3 | 16 | 48GB / 32GB |
| metashell__metashell | 3 | 12 | 48GB / 32GB |
| googleapis__google-cloud-rust | 4 | 16 | 48GB / 32GB |
| Byron__google-apis-rs | 4 | 16 | 48GB / 32GB |
| microsoftgraph__msgraph-beta-sdk-java | 4 | 8 | 32GB / 24GB |
| autc04__Retro68 | 4 | 8 | 48GB / 32GB |

- R4 scales the blame jobs: round(jobs x nproc / 192), at least 1 (on 128 vCPU: two thirds; asuswrt 21). Other flags of each `ctp.py census` run (the v1 fed flags with these changes: one worker, more retries, a lower disk floor): `--workers 1 --retries 10 --skip-html --latest --tokenizer-worker --min-free-mem-gb 24 --disk-floor-gb 50`. The disk floor is 50 GB, not 300 GB: ctp checks it when a project starts, and a resumed project on a full volume must start.
- Memory limit (my choice): ctp gives `--memory-limit` to step 10 and to the firm step. The firm step sorts all token rows (`ORDER BY`). Measured: asuswrt (4,633 MB tokenizable, about 563 M rows) spilled 402 GB for hours at 16GB, and took 16 min at 400GB; google-cloud-java (248 M rows) took 85 min at 16GB. The rows scale with the tokenizable size (about 0.12 M rows per MB): aws-sdk-rust about 225 M rows -> 128GB; aws-sdk-java about 125 M -> 96GB; the 350-650 MB rows (43-76 M) -> 48GB; msgraph-beta (26 M) -> 32GB; the 2 small rows -> 24GB. A sort above the limit spills to the volume; it is slower, but it does not fail. On a type with less than 700 GiB (m6i.32xlarge 512 GiB, c6a/c7i.48xlarge 384 GiB) R4 uses the right column.

### The resume rule (x1k-long-run)

- At each start, the run script reads `out/<p>/pipeline.log` (the runner appends to it on each attempt). An attempt starts where a step heading is not above the heading before it. L = the last step of the newest attempt with a "✓ completed" line. If the newest attempt has no completed step, L = its first step - 1.
- L = 10 and the Parquet exists: `--from-step 11`. The runner does nothing (ctp: "The runner accepts --from-step 11+ and exits 0 having done nothing"). Then firm, validate, schema, join and cleanup run. A firm step that was killed thus does not run step 10 again and does not delete `blame/`.
- L = 10 without the Parquet: `--from-step 10`. L 6-9: `--from-step L+1`. L < 6 or no log: no `--from-step` (ctp auto-resume: step 2 after drop_derived when a clone and blob map exist, else step 1). If an input of the chosen step is missing (the cregit working clone for 7, `blame/` for 8, the 2 DBs for 9-10), it uses no `--from-step`.
- Before ctp starts, it removes `cregit-ec2/blameRepo/build/tmpfile-*` (orphans of a killed `formatBlame.pl`), `out/<p>/sync_*.db` and `out/<p>/duckdb_temp_*` (orphans of a killed step 10), `out/<p>/.<p>-dataset.parquet.firm-tmp` and the content of `out/<p>/.firm-spill/` (orphans of a killed firm step; firm_attribution.py replaces the Parquet with `os.replace` only at the end, so the Parquet stays intact), and `ctp/STOP` (x1k-long-watch writes it on a spot notice; `ctp.py census` exits at once if it exists). It refuses a ctp clone that is not the clean ca113e3. The start line in `logs/run.log` gives L, the from-step and the counts.
- With `--from-step` > 1, the runner keeps the workdir, and `blameRepoFiles.pl` skips each finished `.blame` (existence only). `formatBlame.pl` (57551d7) writes `blameRepo/build/tmpfile-*` and moves it to `blame/` only after git exits 0. The cregit copy and `out/` are on the same volume, so the move is a rename: a kill leaves no partial `.blame`.
- The join step (`consolidate.py --join`) writes the per-tree `ctp.duckdb`; it deletes and inserts the row of the project, so a rerun is safe.
- Parser test (combined state logs of the test): killed in 7 -> 6; then a full resumed attempt -> 10; resumed attempt cut after the step-8 heading -> 7; a new attempt killed in 7 again -> 6; killed in 3 -> 2 (no `--from-step`); an auto-resume attempt at step 2 killed -> 1. All as expected.

### Local resume test, full pipeline (2026-10-19 17:14-17:23 UTC, passed)

- Tools: ctp ca113e3 (clean clone of feat/e2e-runner of `${RUNNER_PROJECTS_TILDE}/cregit-token-pipeline`), cregit: copies of `gate-blamelimit/l1f/cregit` at 57551d7 (the copy that gave libexpat 14eb5d72 on 2026-10-11), Python 3.12 + duckdb 1.5.5. These are the tools of machine A. One difference: the dev machine, not the AMI, gives srcML and Java. The l1f gate Parquet is 14eb5d72, the same as on the EC2 copies, so the result is comparable. The run script is the text of R3 (sha256 prefix a99af0598a97edcd).
- Project: libexpat (R2 gate flags + `--retries 10 --disk-floor-gb 50`; no `--latest`, so the commit is the gate commit). Trees: `${RUNNER_PROJECTS_TILDE}/cregit-workspace/x1k-resume-test/{clean,resume,post}`; log `scripts/a/test/resume-test.out`.
- Clean run: Parquet **14eb5d72** (70 columns, 195,662 rows; = the gate); phases clone, pipeline, firm, validate, schema, join, cleanup.
- Kill in step 7: SIGKILL to every process of the unit at 15 of 90 `.blame` files. Left: 15 `.blame`, 1 tmpfile-*, no Parquet. Rerun: "last completed step 6, from-step 7, removed 1 tmpfile-*"; pipeline log of the rerun: steps 7-10 only; "Newly processed [75] Already done [15] files Error [0]"; then firm, validate, schema, join; rc=0, done; Parquet **14eb5d72**.
- Kill after step 10: SIGKILL just after the step-10 "✓ completed" line; the ledger shows the firm step started and not ended; the Parquet had 67 columns, no stamp. Rerun: "last completed step 10, from-step 11"; the pipeline log of the rerun has no step; firm, validate, schema, join ran; rc=0, done; Parquet **14eb5d72**.
- Result: **RESUME TEST OK**. The 3 Parquets are byte-equal to the gate Parquet 14eb5d72, with 0 differing rows (DuckDB EXCEPT ALL both ways). PLAIN-BLAME: 0. The ctp clones stay the clean ca113e3 after the runs. The uploader, run against the resume tree with a fake `aws` command, wrote the 13 files, the size check and the OK (no real S3 call).
- Not tested locally: a kill inside steps 8-10 (libexpat runs them in 2-3 s), and the EBS, SSM and systemd parts on the AMI.

### Launch steps (main session, in this order)

Every shell: `export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""` and `cd ~/s3-work/dataset-x1k`.

1. L0: `bash L0-volumes.sh` (read the commands), then `RUN=1 bash L0-volumes.sh` -> 4 lines "slot K vol-...", "L0 done ... X1K_VOLS=...". (DryRun of 2026-10-19: "Request would have succeeded".)
2. L1: `bash L1-launch-a.sh` -> "INSTANCE_ID TYPE SUBNET" and a line in `instances.txt`. On UnfulfillableCapacity: try again for up to 30 min, then `MARKET=on-demand bash L1-launch-a.sh` (m6a.48xlarge, $8.29/h). Optional (see "Risks that stay"): `TYPES="m6i.32xlarge r6i.32xlarge m6a.48xlarge m7i.48xlarge m8i.48xlarge" bash L1-launch-a.sh` leaves out the 384 GiB types. (DryRun of 2026-10-19: "Request would have succeeded".)
3. L2: `I=<id> bash L2-attach.sh` -> 4 attachments, DeleteOnTermination False, "L2 done".
4. SSM: `aws ssm describe-instance-information --filters Key=InstanceIds,Values=<id> --query 'InstanceInformationList[].PingStatus' --output text` -> Online.
5. R1: `I=<id> TAILN=40 bash scripts/a/ssm-a.sh scripts/a/R1-setup.sh 3600` -> 4 x "no signature, mkfs.xfs" (first launch), 11 tree lines "new", "R1 (machine A) done".
6. R2: `I=<id> TAILN=30 bash scripts/a/ssm-a.sh scripts/a/R2-gate.sh 3600` -> 11 x "CHECK OK", rc=0.
7. R3: `I=<id> TAILN=10 bash scripts/a/ssm-a.sh scripts/a/R3-install.sh 600` -> "R3 (machine A) installed: 6 scripts".
8. R4: `I=<id> TAILN=40 bash scripts/a/ssm-a.sh scripts/a/R4-start.sh 3600` -> "the clean ca113e3 in 11 trees", ctp tests passed, 11 rows with blame jobs and memory limit, 11 units active, start lines "from-step 1", "R4 (machine A) done".
9. Watch: `aws s3 cp s3://${RUNNER_BUCKET}/dataset-x1k/live-a/progress.txt -`; detail: `I=<id> TAILN=80 bash scripts/a/ssm-a.sh scripts/a/C1-check.sh 300`.

### Spot reclaim: recovery

1. Signs: `live-a/INTERRUPTED` in S3; the instance terminates about 2 min after the notice. The volumes detach and stay (`aws ec2 describe-volumes --filters Name=tag:Run,Values=x1k-long --query 'Volumes[].[VolumeId,State]' --output text` -> 4 x available).
2. L1 again in ${RUNNER_AWS_REGION}d (the same NAME is accepted after the old instance terminated): `bash L1-launch-a.sh`; after 30 min without capacity: `MARKET=on-demand bash L1-launch-a.sh`.
3. L2 (`I=<new id>`), SSM Online, then R1: it must print "XFS x1k-long-K exists, mount only" for each slot and "has pipeline.log" or "uploaded" for the trees. If it prints "no signature" for a slot that had data, stop and check (wrong volume).
4. R2: "CHECK OK already ..., skipped" for each tree (same AMI). R3. R4: it skips rows with `done-full/<p>/OK`; each start line in `<tree>/logs/run.log` shows "last completed step L, from-step F, removed N tmpfile-*".
5. Loss per reclaim: the `.blame` files in progress (at most about 1 h each, the 3600 s limit), or the running step 8-10 or firm step of a project (asuswrt step 10 or firm: some hours at most). Each reclaim adds one interrupted attempt; `--retries 10` allows 10.

### Stop and end

- `systemctl stop x1k-long@<p>`: SIGTERM to ctp only, SIGKILL to the rest after 60 s (as a reclaim; the resume rule then applies). Touch `/home/ec2-user/NO_SHUTDOWN` first, or the finalize terminates the machine when all units end.
- End: x1k-long-finalize uploads, copies ledgers, logs and pipeline.log to `final-a/<p>/`, checks the sizes, writes `final-a/DONE`, then `shutdown -h +2`. A unit without "census finished" or a row without upload gives `live-a/ALERT` and no shutdown.
- The volumes stay after the end. The user deletes them only after the check of the 11 `done-full/<p>/OK` and `final-a/DONE`.

### Risks that stay

- A runner or firm failure (not a kill) in the first ctp run of a row (no `--from-step`) makes ctp retry with auto-resume: step 2 and drop_derived, which deletes `blame/` and the Parquet. A git failure in blame (57551d7: exit 1), an OOM kill, or a firm error can cause it. After a reclaim or a stop, the ctp run has a `--from-step`, and its retries keep `blame/`. The smallest code change (`resume_step` returns 7, drop_derived only for step 2) is not in this plan. Thus never kill a single process (git, java, firm) by hand; stop the whole unit.
- Memory on the 384 GiB types (c6a.48xlarge, c7i.48xlarge): 160 blame jobs at 0.5-1.4 GB each, plus asuswrt step 10 or firm at 150GB (x 1.4), plus the SDK rows at 32-64GB, can come near 384 GiB. To prevent it, leave out these 2 types (L1 step 2, optional TYPES). Recommended now that the firm step runs.
- More blame jobs give more PLAIN-BLAME files (3600 s per file). C1 shows the count per row. Record it in LIMITATIONS.

### Cost (machine A)

- EBS: 9,000 GiB x $0.08/GB-month = $0.99/h; IOPS (4 x 9,000 above 3,000 x $0.005) + throughput (4 x 375 MiB/s x $0.04) = $0.33/h; total **$1.32/h ($31.6 per day)** from L0 until the user deletes the volumes.
- Spot in ${RUNNER_AWS_REGION}d (2026-10-18 about 23:00 UTC): m6i.32xlarge $1.83, r6i.32xlarge $1.88, m6a.48xlarge $2.38, c6a.48xlarge $2.46, m8i.48xlarge $2.50 per hour. Expected run 20-40 h (estimate; the firm step adds minutes to about 1 h per big row with these limits): **spot $37-100**, EBS for the run plus about 4-8 h before and after: **$32-63**. Total **about $70-165**.
- On-demand fallback (m6a.48xlarge $8.29/h): $166-332 + EBS.

## Run end and failures of machines B (2026-10-20)

- b2 wrote `final/dataset-x1k-b2/DONE` at 17:03:15 UTC. b1 wrote `final/dataset-x1k-b1/DONE` at 17:05:05 UTC. Each finalize did the size check and then `shutdown -h +2`. At 17:09 UTC both instances had the state terminated. Thus the finalize of B worked as designed. A part that ends with `census finished rc=1` (failed rows) is a clean end.
- `done-full/` has 7,199 OK: 7,198 B rows (b1 3,601 of 3,603, b2 3,597 of 3,601) and Byron__google-apis-rs of machine A. B Parquets: 7,199 files, 47.40 GB; the largest is glKarin__com.n0n3m4.diii4a (0.78 GB).
- 6 B rows have no OK. Each failed 4 times (`--retries 3`) at the same point. The causes come from the pipeline logs and the pinned clones on the machines (read before the termination, scripts `scripts/D1-failed-rows.sh` and `scripts/D2-noblame-detail.sh`). The pipeline logs of all attempts are also in `final/<run>/pK/state-not-uploaded.tar.gz`. The pinned-clone counts are not in S3 (the machines are gone).
- No row failed in the clone and no row failed by a time limit.

| Row (deal part) | Class | Evidence |
| --- | --- | --- |
| Librelancer__Librelancer (p1) | no tokens | Step 7 "Newly processed [0]", step 10 "no .blame files found". The pinned commit c113747d has 4 files (.gitmodules, .md, .gitignore, .editorconfig): the source is in git submodules. History has 122 mask paths. |
| vllm-project__semantic-router (p6) | no tokens | Pinned commit c9b65d59: 11,665 files (Go 4,130, Python 1,653, ...), 0 mask files. History has 253 mask paths. |
| visgl__loaders.gl (p7) | no tokens | Pinned commit 6773abca: 6,822 files (TypeScript 3,542, ...), 0 mask files. History has 670 mask paths. |
| greta-dev__greta (p8) | no tokens | Pinned commit c656bd59: 426 files (R 135, ...), 0 mask files. History has 477 mask paths. |
| huaweicloud__ModelArts-Lab (p7) | real defect (non-ASCII paths) | Pinned commit ce1a275f: 2,293 files, 996 with a non-ASCII name. 8 mask files, all with a non-ASCII name. `blameRepoFiles.pl` (cregit 57551d7, line 65) reads `git ls-files` without `-z`. git quotes such a name (`"dir/\346...cpp"`, core.quotePath is not set on the AMI or local), so the mask `\.(c|...)$` does not match the closing `"`. Step 7 blames 0 files. |
| saleha-muzammil__Academic-Time-Machine (p3) | real defect (path starts with "-") | Step 7: "Newly processed [960] ... Error [55]". The 55 files are in the folder `---- Books & Notes ----/`. `blameRepoFiles.pl` line 127 gives the path to `formatBlame.pl` without `--`; its GetOptions reads the path as an option ("Error in command line arguments", status 65280). `formatBlame.pl` also calls `git blame @options $file` without `--`. 57551d7 ends step 7 with exit 1 when a file fails. |

Machine A has 2 more no-token rows: notnotype__neuro-book (pinned 532ebb8a: 8,976 files, TypeScript 3,474, Vue 790; 0 mask files; history 4) and pur1fying__blue_archive_auto_script (pinned 0d57f472: 3,788 files, PNG 2,955, Python 516; 0 mask files; history 46). Each failed 11 times on 2026-10-19 (step 10 "no .blame files found"). On 2026-10-20 ctp did not try again ("failed 11 times ..., more than --retries 10").

Why "no tokens": the runs use `--latest` (the v1 rule). Thus the pinned commit is the newest commit on the run date, not the frame commit. At the pinned commit these repositories have no file in the mask (C, C++, Java, Rust). Their history has such files.

Recommendations (the user decides):
- The 6 no-token rows: exclude them. A rerun gives the same result. A rerun at the frame commit (without `--latest`) can give tokens, but it breaks the v1 rule. LIMITATIONS row: "`<p>` | `<frame commit>` | no tokens: the pinned commit `<sha>` (the newest commit on the run date) has no C, C++, Java or Rust file | excluded (decision `<date>`)". For Librelancer add: "the source is in git submodules, and the pipeline does not follow submodules".
- huaweicloud__ModelArts-Lab: exclude it from x1k now. LIMITATIONS row: "no tokens because of a defect: its 8 source files have non-ASCII path names, and cregit 57551d7 does not blame a file whose name git quotes". Also add a dataset-wide defect entry: "A source file with a non-ASCII byte (or a `"`, `\`, tab or newline) in its path is not in the token rows of any project (v1 and x1k)." The fix is `git ls-files -z` in `blameRepoFiles.pl`. The fix changes the cregit commit; thus do not rerun one row with it now. Measure the effect later (it needs the clones: count the mask files at the pinned commit with a quoted name).
- saleha-muzammil__Academic-Time-Machine: exclude it from x1k now. LIMITATIONS row: "excluded because of a defect: 55 of its 1,015 source files have a path that starts with `-`; the blame step of cregit 57551d7 reads such a path as an option and fails". The fix is `--` before the positional arguments (blameRepoFiles.pl line 127 and the `git blame` call of formatBlame.pl). v1 is not affected without a sign: cregit 95cdc88 (batches 1-22) and 57551d7 both end step 7 with exit 1 when a file fails (`exit($errorCount == 0 ? 0 : 1)`), so such a v1 project failed and is in the v1 failure or exclusion records.

## Machine A: finalize change (2026-10-20, R5)

Problem: `x1k-long-finalize` sets clean=0 for each row of run.list without `uploaded/<p>`. neuro-book and blue_archive_auto_script never upload. Thus the old text writes `live-a/ALERT` and does not power off.

Change (sent at 17:08 UTC with `I=${RUNNER_EC2_X1K_LONG_A2} TAILN=40 bash scripts/a/ssm-a.sh scripts/a/R5-finalize-exclude.sh 300`, rc 0):
- `/data/x1k-long/excluded.tsv` (volume 1, 310 B; also `live-a/excluded.tsv`, size checked): `<p><TAB><reason>` for the 2 rows. Reason: "no tokens: 0 C/C++/Java/Rust files at the pinned commit (step 10 of each attempt: no .blame files found, no tokens processed)".
- `/usr/local/bin/x1k-long-finalize`: sha256 4fbb5051... -> 076abd7e... (the old file is in `/root/x1k-long-finalize.before-R5`). The diff:
  - new: `X=$L/excluded.tsv` and `excluded() { [ -f $X ] && cut -f1 $X | grep -q -x -F "$1"; }`
  - `[ -e $R/uploaded/$p ] || clean=0` -> `[ -e $R/uploaded/$p ] || excluded $p || clean=0`
  - new: `[ -f $X ] && cp $X $T/excluded.tsv` (thus `final-a/excluded.tsv`, with the size check)
  - the DONE line says `excluded (<reason>)` for such a row, else `uploaded`; the ALERT text names excluded.tsv.
- A row in excluded.tsv must still have "census finished" in its run.log. Every other rule stays (all units inactive, size check, NO_SHUTDOWN, /run/x1k-hold, up >= 1 h, `shutdown -h +2`). The volumes keep DeleteOnTermination false (checked 17:08 UTC: sdf-sdi False; only the root volume is True).
- Before it writes, R5 checks: the installed text is the R3 text or the new text; the 2 units are not active; no upload; the newest pipeline log has "no .blame files found". It aborts on another state.
- `scripts/a/R3-install.sh` has the same new text (so a relaunch installs it). excluded.tsv is on volume 1, so it stays after a relaunch. R4 starts the 2 rows again after a relaunch; they end in seconds ("more than --retries 10").
- Test: `scripts/a/test/finalize-exclude-test.sh` (fake aws, systemctl, sudo, shutdown; 5 cases). Log `scripts/a/test/finalize-exclude-test.out`: new text "FINALIZE TEST OK"; the old text gives ALERT in case 1 (the problem). `bash -n` OK for R3, R5 and the installed file.

## Machine A: progress and estimate (2026-10-20 17:12 UTC)

Measured with `scripts/a/D5-progress.sh` and `scripts/a/D6-blame-rate.sh` (read-only). This attempt started 12:43:54 UTC (all rows from step 7). Mask files = `git ls-files` of the cregit working clone that match the mask; bytes = their size.

| Row | Jobs | State | .blame done / mask files | MB left | Rate now | Estimate |
| --- | ---: | --- | --- | ---: | --- | --- |
| RMerl__asuswrt-merlin.ng | 32 | step 10 since 13:45 (step 7 ended 13:45, 3,684 s); sync DB 196 GB done 17:10, Parquet write started 17:10 | 300,722 / 300,722 | 0 | - | Parquet, firm (300GB), validate, join, upload: about 18:30-20:00 UTC |
| googleapis__google-cloud-rust | 16 | step 10 since 17:11 (step 7: 16,049 s) | 3,995 / 3,995 | 0 | - | about 18:00-19:00 UTC |
| TencentCloud__tencentcloud-sdk-cpp | 16 | step 7 | 58,894 / 95,801 | 157 | 6,500-7,000 files/h, 50 MB/h | step 7 3-6 h; end about 21:00-24:00 UTC |
| microsoftgraph__msgraph-beta-sdk-java | 8 | step 7 | 7,040 / 28,899 | 243 | 850-900 files/h, 20 MB/h | 12-26 h: 2026-10-21 06:00-20:00 UTC |
| autc04__Retro68 | 8 | step 7 | 371 / 117,147 | 718 | 60 files/h, 25 MB/h | at least 29 h (by bytes); much more if a small file has a fixed cost |
| metashell__metashell | 12 | step 7 | 381 / 39,665 | 847 | 50 files/h, 20 MB/h | at least 42 h; probably 50-100 h |
| aws__aws-sdk-java | 20 | step 7 | 4,107 / 153,188 | 1,295 | 530-570 files/h, 29 MB/h | 45 h (by bytes) to 175 h (fit with a fixed cost of about 75 s per file) |
| awslabs__aws-sdk-rust | 28 | step 7 | 1,572 / 242,829 | 3,227 | 200-220 files/h, 23 MB/h | 140 h (by bytes) to about 600 h (fixed cost of about 230 s per file) |

- PLAIN-BLAME lines in the whole pipeline.log: asuswrt 6, aws-sdk-rust 16, metashell 40, google-cloud-rust 43, Retro68 26, aws-sdk-java 0, tencentcloud 0, msgraph-beta 0 (Byron__google-apis-rs: see its uploaded logs).
- Method: the MB per hour of each row is almost constant from hour to hour while the files get smaller (largest first), and the files per hour go up only a little. Thus each file has a fixed cost plus a cost per byte. The low value uses only the bytes; the high value fits both costs on hours 1 and 3. These are estimates, not measurements of the end.
- End of machine A with the current jobs: the row aws-sdk-rust controls it: **at least about 6 days (2026-10-26), probably 2-4 weeks**. Cost: spot $3.68/h + EBS $1.32/h = about $120 per day.
- The jobs of a ctp run do not change while it runs. When asuswrt and google-cloud-rust end (about 19:00 UTC), 48 of the 140 jobs are free, and only about 92 git processes run on 192 vCPU (memory 129 of 743 GiB used).
- Options for the user (no action taken):
  1. More blame jobs for the 4 slow rows. Touch `/home/ec2-user/NO_SHUTDOWN`, `systemctl stop x1k-long@<p>`, change `JOBS=` in `<tree>/run.env`, `systemctl start x1k-long@<p>`. The resume rule starts again at step 7 and keeps the `.blame` files (proved by the 12:43 relaunch). Example after 19:00 UTC: aws-sdk-rust 64, aws-sdk-java 48, metashell 24, Retro68 24 (about 180 jobs with tencentcloud and msgraph). aws-sdk-rust then needs about 60-270 h. More jobs can give more PLAIN-BLAME files.
  2. Plain blame (no -C100) for the generated SDK rows (aws-sdk-rust, aws-sdk-java). This is a method change; it needs a LIMITATIONS entry and a cregit or ctp flag that is not in ca113e3/57551d7.
  3. Exclude aws-sdk-rust (and perhaps aws-sdk-java) as generated code, with a LIMITATIONS row "excluded: blame did not end in the time budget".
  4. Merge x1k without the slow A rows first, and add them later (see "Merge plan"; final_merge.py continues a run, so a second pass is easy).

## Merge plan (written 2026-10-20; nothing in it ran)

Goal: the x1k Parquets join the released dataset like the v1 files. The v1 order (memory note v1-freeze-decisions): meta rewrite -> pseudonymization -> final encoding; do not freeze SHA256SUMS before all steps are done. v1 state today: v1-raw (meta rewrite + ZSTD 19) is done (`dataset-v1/raw/`, 3,544 files). The schema 2 organisation columns, the pseudonymization (v1-public) and the public SHA256SUMS are not done for v1 either. Thus x1k can join v1 at the v1-public write, and the v1-raw step is the only one that x1k must do alone.

Tools (${RUNNER_STUDY_REPO} `2026.2-estudos-pesquisa-sistemas/dataset-selection/`, here DS): `s7-run/final_merge.py` + `s7-run/rewrite_meta_columns.py` (the v1-raw tool; staged copies in `~/s3-work/dataset-v1/tools/`), `s5-evidence/build_evidence.py`, `s6-labels/build_labels.py`, `s7-run/final_meta.py`, `s8-companies/{build_links,build_organisations,build_v0,run_v0}.py`, ctp-anon `anonymize_parquet.py` (branch feat/pseudonymise-identity-columns, c0b83ac, not pushed), ctp `docs/LIMITATIONS.md` (branch corpus-freeze-and-tests).

The trailer post-fix is not necessary: all x1k Parquets are cregit 57551d7 (it has 1f17663, one trailer entry per person), or cregit 14b8db4 (57551d7 + the path fix) for the 18 path-fix rows.

Order of the X2 passes (2026-10-20): (1) the path-fix run `dataset-pathfix-b1` ends (`dataset-x1k/final/<run>/DONE`, see `~/s3-work/dataset-pathfix/README.md`); (2) x1k-raw merge, pass 1: all rows with an OK, the 18 path-fix rows from `done-pathfix/` (cregit 14b8db4); (3) pass 2 on a new machine: the machine A rows, and a path-fix row that was held in pass 1.

| Step | What | Inputs and outputs | Machine, time | Start |
| --- | --- | --- | --- | --- |
| X0 | Exclusions and counts | Decide the 8 exclusions (above). `! bash ~/s3-work/dataset-x1k/M0-plainblame-count.sh` -> `merge/plainblame.x1k.tsv` (PLAIN-BLAME per row; B: newest log, A: all logs). | local, about 10-20 min (download of the pipeline logs only) | **now** for B; again after A |
| X1 | S5/S6 sidecar for x1k | DS/x1k `frame.x1k.csv`, `pool.x1k.csv`, `licenses.x1k.csv`, `project_meta.x1k.json` (7,215 keys; stratum, fact, contested, label_date, roster_* blank; 112 keys without owner_type/archived/fork; 33 Savannah rows with owner `git`). Run build_evidence.py and build_labels.py with the x1k frame and pool (`--prior` of the v1 labels, so v1 label dates stay), the GitLab instance-owner rule of `labels_batch25.py`/`labels_batch26.py` for invent.kde.org 41, gitlab.eclipse.org 19, gitlab.freedesktop.org 12 and 7 others, then final_meta.py -> `project_meta.x1k.final.json` + .sha256 (host rules: Savannah owner `gnu`, non-GitHub blank license NOASSERTION). Check that the 112 keys get values. No web fetch is planned; tell the user the cost first if one is necessary. | local, about 1-2 h with the review | **now** (it covers all 7,215 rows, A rows too) |
| X2 | x1k-raw: meta rewrite + ZSTD 19 | A new `build_inputs` for x1k: read `done-pathfix/<p>/OK` before `done-full/<p>/OK` (sha256, sizes) and the `.validated` stamps (token_rows) -> `inputs.x1k.tsv` (`project source cregit token_rows bytes s3_key sha256`), minus the exclusions. The 18 path-fix rows come only from `done-pathfix/` (cregit 14b8db4); a path-fix row without `done-pathfix/<p>/OK` is held (not merged). Stage the same tools (sha256 as `dataset-v1/tools/SHA256SUMS`) and the X1 sidecar; upload by a user script. Run final_merge.py as v1 (`--jobs 88 --threads 1 --memory-limit 5GB`, validate_schema.py of ca113e3 = 2efe32c3) with `--dest s3://.../dataset-x1k/raw`. Output: `dataset-x1k/raw/parquet/`, SHA256SUMS, results.tsv, rewrite.tsv. | one i4i.24xlarge spot (as spot a; about $2.4/h). 47.4 GB in (v1: 186 GB at 23 MB/s in 1 h 52 min); about 1 h + 1 h setup, about $5 | after the path-fix run ends (pass 1: all rows with an OK); A rows and held rows: a second start with the same DEST (final_merge.py continues) |
| X3 | Domain cache and links for x1k | `extract_domains_v1.py` reads only `merge-prelim/prelim.duckdb` (local v1 files): make an x1k variant that reads x1k-raw. `build_links.py --sidecar` takes one file: give it a v1 + x1k sidecar or run it twice. New x1k e-mail domains and namespaces are not in the company database; without a row a real domain gets `independent`. Review the new domains with the S8 method (audit pages, DNS study) before the final database version. Rerun error_model.py with x1k. | local; the review of new domains is the long part (days, user time) | the domain cache: after X2 for B; the links: after the final database version (v4.4 is in work; no links-v4.2/v4.3 folder exists) |
| X4 | Organisation columns (schema 2) | build_v0.py through run_v0.py (`--v1raw` = the final_merge.py OUT dir; it reads results.tsv). Run v1 and x1k with the same links and database version. Output: 67 cregit columns + firm_based_on_namespace, firm_based_on_domain, project_enterprise_driven, project_enterprise_basis; footer ctp_schema_version 2, organisations_version, organisations_mapping_sha256; ZSTD 19. | the v0-org machine of `~/s3-work/dataset-v0-org/README.md` (i4i.24xlarge spot; v1 estimate 5.5-6 h, about $15); x1k adds about 1.5-2 h (33 GB after ZSTD 19, 7,200 files) | after X3 and the final database version |
| X5 | Pseudonymization (x1k-public with v1-public) | anonymize_parquet.py needs its rework first: a registry table (not SQL MAP literals), a leak scan that is not quadratic (about 62 days now by extrapolation), reports without real identities, memory and thread options, one fused write with X4 (decision D1). One salt and one registry over v1 + x1k (the cross-file collision and leak checks cover one invocation only). The salt stays with the user. | after the rework; the same machine as X4 (fused write) | waits for the rework (not for A) |
| X6 | Dataset DuckDB and views, SHA256SUMS | `build_organisations.py views --root DIR` over the v1 + x1k public files; a frame index as prelim.duckdb (frame 3,548 + 7,215; frame_status with done, excluded, pending); the public SHA256SUMS of all files (`cregit-dataset-paper/data/SHA256SUMS`). | local or the X4 machine, less than 1 h | after X5 and A |
| X7 | LIMITATIONS rows | New "Dataset x1k" entries in the format of the "Dataset v1" entries: (a) exclusions table (`project | frame commit | reason | status`), the 8 rows above and the A rows that the user excludes; (b) PLAIN-BLAME counts from X0 (B and A) as the v1 table (time limit / exit 128 / manual swap); (c) the 2 cregit defects (non-ASCII paths, paths that start with `-`) as dataset-wide entries with the v1 checks; (d) the x1k stratum (1,000-4,999 commits) and its run (ctp ca113e3, cregit 57551d7, gate 14eb5d72, `--latest`, the run dates). | local | **now** as a draft for B; final after A and X1 |

What can start now (A does not block it): X0 for B, X1 (all 7,215 rows), X2 for the 7,198 B rows (about 2 h on a new spot, about $5), the X3 domain cache of B, and the X7 draft. What waits for A: X0, X2 and X3 for the A rows, then X6 and the final X7. What waits for other work: X3 links and X4 (final company database), X5 (anonymizer rework). Thus the end of A is on the critical path only if the user keeps the slow SDK rows (see the options above); else X4-X6 wait for the database and the anonymizer, not for A.

## Merge plan: progress (2026-10-20, user decisions)

User decisions 2026-10-20: (1) machine A: more blame jobs for the slow rows, and the first x1k merge goes without them; (2) start X1 and X7, and prepare X2 up to the launch command. The 6 no-token rows are exclusions. ModelArts-Lab and Academic-Time-Machine are **not** exclusions: cregit gets a fix and they run again (another agent prepares that).

### X1 (done 2026-10-20, local, nothing fetched)

In ${RUNNER_STUDY_REPO} `dataset-selection/` (not committed):
- `python3 s5-evidence/build_evidence.py --frame x1k/frame.x1k.csv --pool x1k/pool.x1k.csv --out x1k/s5s6/evidence.x1k.csv --counts x1k/s5s6/evidence.counts.txt --checks x1k/s5s6/evidence.checks.txt` -> 9,441 facts for 7,215 projects; 0 join checks differ, 4 info lines.
- `python3 s6-labels/build_labels.py --evidence x1k/s5s6/evidence.x1k.csv --frame x1k/frame.x1k.csv --date 2026-10-20 --prior s6-labels/labels.csv --out x1k/s5s6/labels.x1k.csv --counts x1k/s5s6/labels.counts.txt` -> unknown 3,721, personal 2,043, foundation 697, company 455, contested 290, fiscal-sponsor 9.
- The 112 non-GitHub rows: the rosters give each of them a foundation label (invent.kde.org 41, git.savannah.gnu.org 33, gitlab.eclipse.org 19, gitlab.freedesktop.org 12, 7 others). Thus the instance-owner rule of `labels_batch25.py` is not necessary. Their owner_type, archived and fork stay blank, as for the 70 non-GitHub v1 rows (no fetch is necessary).
- `cd s7-run && python3 final_meta.py --sidecar ../x1k/project_meta.x1k.json --out ../x1k/project_meta.x1k.final.json --labels ../x1k/s5s6/labels.x1k.csv --evidence ../x1k/s5s6/evidence.x1k.csv --frame ../x1k/frame.x1k.csv --pool ../x1k/pool.x1k.csv --license-values ../x1k/licenses.x1k.csv` -> `x1k/project_meta.x1k.final.json`, 7,215 keys, **sha256 1520c5f4d8909b36...** (`.sha256` beside it). Host rules: owner `gnu` for the 33 Savannah rows; license 0 changes (the 112 non-GitHub rows have NOASSERTION already). The same fields as `project_meta.v1.final.json`; no key in common with v1; the key order of the input stays.
- The labels have no review by hand (as for the v1 GitLab rows).

### X7 (draft, 2026-10-20)

`${RUNNER_PROJECTS_TILDE}/cregit-token-pipeline/docs/LIMITATIONS.md` (branch corpus-freeze-and-tests, not committed): new "Dataset x1k" entries after the v1 Python/TypeScript entry, marked DRAFT in an HTML comment: the stratum and its run; the 6 no-token rows (excluded, user decision 2026-10-20); the 2 rows that wait for a cregit fix (pending); the dataset-wide defect "an in-scope file with a non-ASCII path name has no tokens" (v1 and x1k, not measured); PLAIN-BLAME (count open, `M0-plainblame-count.sh`); the slow rows that join later.

### X2 (prepared, not launched)

Kit: `~/s3-work/dataset-x1k/x2/`. All scripts pass `bash -n`; `build_inputs_x1k.py` passed a test on synthetic OK files (good rows, an excluded row with an OK, a bad OK). Path-fix change (2026-10-20 about 22:30 UTC, not launched): `bash x2/test/T1-x2-inputs.sh` -> "T1-x2 ALL PASS" (python 3.12 and 3.14; synthetic done-full and done-pathfix copies: done-pathfix wins, 14b8db4 in cregit.x1k.txt and inputs, 2 held rows, an excluded row, a v1 row of done-pathfix ignored, 6 error cases, the M1 guard). The EC2 DryRun of the fleet said "Request would have succeeded" (2026-10-20 19:06 UTC).

| File | What |
| --- | --- |
| `U1-upload-x2.sh` | the user uploads the X1 sidecar + sha256 to `dataset-x1k/raw-tools/` |
| `L1-launch-x2.sh` | one spot instance (i4i.24xlarge, r6id.24xlarge, i4i.32xlarge, r6id.32xlarge; 4 AZs; launch template cregit-census-batch3-spot), tags Run=x1k-raw, Name=dataset-x1k-raw-N; refuse list; `DRY_RUN=1` |
| `ssm-x2.sh` | scripts/ssm.sh for Run=x1k-raw only; adds `export X2_RUN=<Name>` |
| `R1-x2-setup.sh` | XFS on the instance store, tools of `dataset-v1/tools/` (final_merge.py acede0d8, rewrite_meta_columns.py 365867b0), the sidecar (1520c5f4), ctp ca113e3 from `batch2/input/ctp.bundle` (validate_schema.py 2efe32c3), venv duckdb 1.5.5 |
| `R2-x2-inputs.sh` | syncs only `<p>/OK` and `<p>.validated` of done-full and of done-pathfix; `pathfix.x1k.txt` (the 18 x1k path-fix rows; R2 stops if the list is not part 2 of `inputs-pathfix/parts.tsv`); writes `cregit.x1k.txt` (`<p> 14b8db4` for each path-fix row with `done-pathfix/<p>/OK`); `inputs.x1k.tsv` (the v1 columns; source x1k-a, x1k-b or x1k-pathfix; cregit 57551d7, or 14b8db4 for x1k-pathfix) minus the 6 exclusions; a path-fix row without `done-pathfix/<p>/OK` is held: `held.x1k.txt` and the "HELD:" lines of stdout; copies to `raw-work/<run>/` |
| `M1-x2-start.sh` | smoke test (3 rows: smallest GitHub, Savannah and KDE row; checks owner gnu, stratum, ZSTD) to `raw-smoke/<run>/`, a guard (it stops if a path-fix row of `inputs.x1k.tsv` has a done-full key or a cregit that is not 14b8db4; it prints the held rows), then the unit x1k-raw-merge: final_merge.py `--jobs 88 --threads 1 --memory-limit 5GB` to `s3://.../dataset-x1k/raw/`; at the end DONE or ALERT in `raw-work/<run>/`, then `shutdown -h +5` (unless NO_SHUTDOWN). A later pass on a new machine takes results.tsv and rewrite.tsv of DEST and continues. |
| `M2-x2-check.sh` | read-only progress |
| `test/T1-x2-inputs.sh` | local test, no AWS: the builder embedded in R2 (it must be the same as `build_inputs_x1k.py`), the cregit.x1k.txt code of R2 and the M1 guard on synthetic files |

Refuse lists (L1, ssm-x2, R1, R2, M1): also machine A `${RUNNER_EC2_X1K_LONG_A4}` and the path-fix machine `${RUNNER_EC2_PATHFIX_B1}` (added 2026-10-20 with the path-fix change).

Launch commands, pass 1 (start only after the path-fix run ends: `aws s3 ls s3://${RUNNER_BUCKET}/dataset-x1k/final/dataset-pathfix-b1/DONE` (or the `-rN` run of a relaunch) shows the file, and `aws s3 ls s3://${RUNNER_BUCKET}/dataset-x1k/done-pathfix/ --recursive | grep -c '/OK$'` = 35; main session; every shell `export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""` and `cd ~/s3-work/dataset-x1k`):
1. User: `! bash ~/s3-work/dataset-x1k/x2/U1-upload-x2.sh` -> 2 x "uploaded", "U1-x2 done". (Done: `raw-tools/` has the sidecar and its sha256 since 2026-10-20 22:07 UTC.)
2. `NAME=dataset-x1k-raw-1 MAX_TOTAL_PRICE=3.50 bash x2/L1-launch-x2.sh` -> "INSTANCE_ID TYPE SUBNET".
3. SSM Online: `aws ssm describe-instance-information --filters Key=InstanceIds,Values=<id> --query 'InstanceInformationList[].PingStatus' --output text`.
4. `I=<id> TAILN=30 bash x2/ssm-x2.sh x2/R1-x2-setup.sh 3600` -> "tools ok", "python 3.12... duckdb 1.5.5", "R1-x2 done".
5. `I=<id> TAILN=20 bash x2/ssm-x2.sh x2/R2-x2-inputs.sh 1800` -> "path-fix list: 18 x1k rows", "cregit.x1k.txt: 18 rows with cregit 14b8db4", "inputs.x1k.tsv: N rows (x1k-a .., x1k-b .., x1k-pathfix 18)", "path-fix: 18 of 18 x1k rows from done-pathfix", "HELD: 0 rows", "R2-x2 done". With the 7,200 done-full OK of 2026-10-20 22:30 UTC: N = 7,202 (7,200 - 16 path-fix rows + 18 x1k-pathfix). If HELD is not 0, the held rows wait for pass 2; decide before step 6.
6. `I=<id> TAILN=40 bash x2/ssm-x2.sh x2/M1-x2-start.sh 3600` -> "inputs: N projects (... x1k-pathfix cregit 14b8db4 18; ...)", "held (...): 0", "SMOKE TEST OK", "START ... unit x1k-raw-merge", "M1-x2 done".
7. Watch: `I=<id> TAILN=40 bash x2/ssm-x2.sh x2/M2-x2-check.sh 300`, or `aws s3 ls s3://${RUNNER_BUCKET}/dataset-x1k/raw-work/dataset-x1k-raw-1/`.

Estimate: 47.4 GB in (v1: 186 GB in 1 h 52 min with the same flags) -> about 40-60 min of merge, plus about 30 min setup; about $3-5. The machine terminates itself after DONE. Pass 2 (the machine A rows, and a held path-fix row when its `done-pathfix/<p>/OK` exists): steps 2-7 with `NAME=dataset-x1k-raw-2` (R2 builds the inputs again; M1 continues the results of DEST and writes SHA256SUMS over all rows). The 2 rows that had no Parquet (ModelArts-Lab, Academic-Time-Machine) are path-fix rows: they join in pass 1 when the path-fix run made their OK.

### Machine A: spot reclaim 2026-10-20 19:19 UTC, and the "more jobs" change

- AWS reclaimed ${RUNNER_EC2_X1K_LONG_A2}: notice 19:17:07 UTC, terminated 19:19:06 UTC (`Server.SpotInstanceTermination`). x1k-long-watch wrote `live-a/INTERRUPTED` and the ledgers at 19:17:35. The 4 volumes are `available` (slots 1-4). No relaunch was made (not my decision).
- State at the notice: done-full OK for Byron__google-apis-rs and googleapis__google-cloud-rust (17:42 UTC). RMerl__asuswrt-merlin.ng was in the firm step (2,837 s at 19:15; step 10 complete, Parquet on volume 1): the resume rule gives `--from-step 11` (firm, validate, schema, join only). The 6 step-7 rows keep their `.blame` files: aws-sdk-rust 2,188, aws-sdk-java 5,437, tencentcloud-sdk-cpp 76,429 (of 95,801), metashell 445, msgraph-beta 9,307, Retro68 593.
- Thus R6 (`scripts/a/R6-more-jobs.sh`, stop/JOBS/start on a live machine) did not run. For the relaunch, the change is in the table of `scripts/a/R1-setup.sh` instead (R1 writes `long.tsv`, and R4 writes `run.env` from it at each relaunch): aws-sdk-rust 28 -> 64, aws-sdk-java 20 -> 44, metashell 12 -> 20, Retro68 8 -> 20, msgraph-beta 8 -> 12; tencentcloud stays 16 (total 176 on 192 vCPU; R4 scales by nproc/192 on a smaller type). R6 stays for a machine that already runs with the old jobs (it skips a row whose JOBS is already the new value).
- Relaunch = "Spot reclaim: recovery" above (L1, L2, SSM, R1 "mount only", R2, R3, R4). R3 installs the finalize with excluded.tsv (the R5 text); `excluded.tsv` is on volume 1. R4 starts the 2 excluded rows again; they end in seconds. After R4, check in each start line: "from-step 11" for asuswrt, "from-step 7" and the new "blame-jobs" for the others.
