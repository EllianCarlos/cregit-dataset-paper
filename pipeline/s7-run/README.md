# S7: run manifests and the census

This directory turns the frame (`../s4-filter/frame.csv`, 25,263 projects) into
run manifests, and holds the commands and records of the cregit census.

The names below stand for local and account values:

- `$CREGIT_PROJECTS`: the directory that holds `cregit-workspace` and the clones of ctp and cregit.
  The scripts find it themselves: it is the nearest parent directory that holds `cregit-workspace`.
- `$RUNNER_BUCKET`, `$RUNNER_AWS_PROFILE` and `$RUNNER_EC2_*`: the bucket, the AWS profile and the
  EC2 ids of the dataset build. `runner/runner.env` gives them (local only, see
  `runner/runner.env.example`). `census_funnel.py` reads it.

## Files

| File | What it is |
|---|---|
| `build_run.sh` | Splits the frame into the five commit layers and builds one manifest for each layer with `build_manifest.py` (cregit-token-pipeline), plus `manifest.batch1.tsv` (the first 5% of layer 1, 164 projects). Writes `SHA256SUMS`. |
| `manifest.layer{1..5}.tsv`, `*.order.tsv` | One manifest for each layer, in u order. The sixth column is the S2 snapshot commit. |
| `manifest.batch1.tsv`, `manifest.batch1.order.tsv` | Batch 1: 164 projects of layer 1 (≥ 5,000 commits). |
| `frame.layer*.csv`, `project_meta.*.json` | Written by `build_run.sh`; not in git (hashes in `SHA256SUMS`). |
| `census.cfg` | `CTP_CONFIG` for the census: cregit 157cf8b, output in `cregit-workspace/census-2026-10`. |
| `run_batch1.sh` | The batch 1 command: `--latest --tokenizer-worker --skip-html`, 3 workers, `--retries 2`, disk floor 500 GB. Start it only with the user's agreement. |
| `status.sh` | `./status.sh` (progress), `full`, `log [N]`, `audit NAME`. |
| `step_monitor.py`, `step_times.tsv` | Records when each cregit step (1–10) starts, from the census logs, every 30 s. Read-only; runs beside the census. |
| `step_report.py` | Step durations for each project and the share of each step. |
| `speed-audit-20261008.md` | The read-only speed audit of batch 1: where the time goes (gc, walker thread, blame jobs) and the ranked changes, with when each can apply. |
| `speed-impact-20261008.md` | The estimated hours each speed fix saves, for batch 1 and the full census, from a time model fitted on the finished projects; the batch 1 ETA with no change. |
| `step2-profile-20261008.md` | The step 2 profile: where the time goes inside step 2 (timeout stalls, the two serial JVM threads, copies of unmasked blobs, SQLite, gc) and seven ranked speed-ups. |
| `step2-profile-check-20261008.md` | Check of the step 2 profile claims against the code, plus the memo language defect it found (proved on two Linux blobs). |
| `srcml-fix-20261009.md` | The srcML non-termination fix (adjacent C string literals; function-name loop): all 81 census timeouts finish, 8,454 of 8,492 blobs identical, provenance block. |
| `ec2-load-20261009.md` | CPU, memory and disk use on the batch 2 instance: S projects take about 10 min instead of 3-4 because step 2 waits on cross-directory `rename()` on the single `/data` filesystem; CPU, memory and I/O are not the limit. |
| `runs-20261009.md` | Resume point (see "State at 17:35 UTC" at its end). What runs where (batch 1 here, batch 2 on EC2 on-demand, batch 3 on spot + the batch 2 instance), how to watch and stop each run, the decisions with their rationale, and the open points. |
| `step2-speed-20261009.md` | The step 2 speed-ups (alternates, SQLite batching and cache, zlib 1, JDK SHA-1, no bitmap): Parquet identical on 4 projects, curl step 2 CPU -39%. |
| `enrich_meta.py` | Fills `license`, `owner_type`, `archived`, `fork` and (since 2026-10-09 20:15 UTC) `source` (the `pool.csv` column `origins`, as it is) in a `project_meta` sidecar from `../s2-pool/pool.csv` (join: manifest name → frame row → `pool_key`). `bash build_run.sh batch N` (N = 6..20) runs it in place, so batches 7–20 get `source`; batch 6 has `source` = ''. Batches 1–5 have new `project_meta.*.enriched.json` files. |
| `final_meta.py` | Writes `project_meta.layer1.final.json` (not in git; sha256 in `project_meta.layer1.final.json.sha256`): the sidecars of dataset version 1 plus `source`, the S6 label columns (`stratum`, `fact`, `contested`, `label_date`, from `../s6-labels/labels.csv`) and `roster_name`, `roster_lang` (from `../s5-evidence/evidence.csv`). Since 2026-10-11 it covers 3,379 projects: the layer 1 enriched sidecar (batches 1-20, 3,265) and `project_meta.batch21.json` (81) and `project_meta.batch22.json` (33), in this order. The sidecar of 2026-10-09 (3,265 projects) is kept as `project_meta.layer1.final.20261009.json` (not in git; sha256 in `project_meta.layer1.final.20261009.json.sha256`). Its 3,265 rows are the first rows of the new sidecar. Two host rules (user decisions of 2026-10-11) then apply: a project that is not on GitHub and has a blank `license` gets `NOASSERTION` (36 old rows), and a project on git.savannah.gnu.org gets the owner `gnu` (25 batch 22 rows). The sidecar before these rules (sha256 c988c37a) is kept as `project_meta.layer1.final.20261011a.json` (not in git; sha256 in its `.sha256` file). Since 2026-10-16 the default inputs cover all 3,548 projects of v1, and the output is a new file: `project_meta.v1.final.json` (not in git; sha256 4023295a in `project_meta.v1.final.json.sha256`). The inputs add `project_meta.batch23.json` (118), `project_meta.batch25.json` (50) and `project_meta.batch26.json` (1), their frames, `../s2-pool/v2/pool.batch25.csv` and `pool.batch26.csv`, and `../s4-filter/supplement23.licenses.csv`, `supplement25.licenses.csv` and `supplement26.licenses.csv`. `--labels` takes several files: `../s6-labels/labels.csv`, `labels.batch25.csv`, `labels.batch26.csv`. The label files of batches 25 and 26 have no `label_date` column, so these rows keep the `label_date` of their sidecar (2026-10-14). The 3,379 rows of `project_meta.layer1.final.json` are the first rows of the v1 sidecar, with all fields the same. `project_meta.layer1.final.json` and its `.sha256` file do not change: the inputs of 2026-10-11 still give it byte for byte (a test checks this). |
| `rewrite_meta_columns.py` | Fills the 11 sidecar columns that changed after the run (`--fields` to choose fewer) in one finished Parquet from a sidecar (DuckDB `SELECT * REPLACE`), then checks the other columns row by row. Use the final sidecar. `--report` appends a TSV row. Same CLI as `rewrite_footer_columns.py`, so the two run one after the other. Not applied to census files yet. |
| `rewrite_footer_columns.py`, `test_rewrite_footer_columns.py` | Recomputes the 15 `footer_*` columns of one finished Parquet from the original commits (the trailer fix of cregit 1f17663), then checks every row. See "Trailer post-fix of the 95cdc88 batches". |
| `footer_fix_batches.py` | Runs `rewrite_footer_columns.py` on each finished Parquet of the 95cdc88 runs, at most 2 at a time. Writes a parallel tree and a manifest; skips the done ones. See "Trailer post-fix of the 95cdc88 batches". |
| `split_run_ledgers.py`, `test_split_run_ledgers.py` | For each fetched project of the big EC2 runs (batch2, batch3L, batch4, batch5L, batch6L), writes its rows of the run ledger to `done/<project>/ledger.from-run.jsonl` and the pinned commit of the attempt that made the Parquet to `pin.from-run.json`. Reads local copies of the S3 run ledgers (`cregit-workspace/run-ledgers/`). Never writes `ledger.jsonl` (`fetch_done.sh` syncs S3 into that tree). |
| `footer_fix_again.sh` | Run by the timer `footer-fix-again`: fetches the run ledgers (read only), runs `split_run_ledgers.py`, then starts `footer-fix` again with `--retry-transient` when it is not active. Stops the timer when `footer_fix_batches.py --pending` finds no open project. |
| `fetch_done.sh` | Copies the finished files of the EC2 runs (`done/`, `final/`) from S3 to `cregit-workspace/census-cloud/` and checks each Parquet against its `OK` sha256 (`verified.tsv`, `failed.tsv`, `fetch.log`). Download only. Runs every 30 min from the transient user timer `census-fetch` (started 2026-10-09 22:41 UTC). Restart after a reboot: `systemd-run --user --unit=census-fetch --on-calendar='*:05,35' --timer-property=AccuracySec=60s --setenv=HOME=$HOME --setenv=PATH="$PATH" <path>/fetch_done.sh`. |
| `test_enrich_meta.py`, `test_final_meta.py` | Tests for the three, including cregit's `generate_dataset.py` run end to end with the enriched and the final sidecar. |
| `superseded-20261007.tsv` | The three outputs that ran at the snapshot commit and were run again at the newest commit (moved to `census-2026-10/.superseded/20261007/`). |
| `batch1.log`, `batch1-only.log`, `restart.log`, `step_monitor.log` | Run logs; not in git. |

## Rules of the run (decided 2026-10-06 and 2026-10-07)

- Layers run largest first (≥ 5,000 commits first); inside a layer the order is u.
- Each project runs at the head of its default branch when its first attempt
  starts (`--latest`). The ledger records the commit that ran (`pinned_sha`) and
  the snapshot commit (`snapshot_sha`). The selection facts stay measured at the
  snapshot commit.
- No HTML (`--skip-html`). Anonymization is a separate release step.
- Step 2 uses the tokenizer worker pool (`--tokenizer-worker`).

## Operation

- Stop after the running projects: `touch STOP` in the pipeline worktree. To
  end the running projects too, send SIGTERM to the census twice.
- Resume: run `run_batch1.sh` again. A project with a blob map resumes at step 2.
- A stopped attempt counts toward `--retries`. Linux has used both retries of
  batch 1: do not restart the census while Linux runs.
- 2026-10-08: the host rebooted at 21:07 UTC and ended the census (0 failed before
  that; foxhound lost about 6 h of its gc, which had not written a pack). Restarted at
  21:18 UTC with `RETRIES=3 run_batch1.sh`, because the reboot was foxhound's third
  interrupted attempt and `--retries 2` would have given it up. The stale
  `gc.pid` in foxhound's cregit.git (PID not running) was removed first.
- 2026-10-09 01:55 UTC: the Claude Code session that had started the census
  ended, and its exit sent SIGTERM to the whole process tree: foxhound, tracy and
  difftastic were killed (rc=-15). Cataclysm-DDA had already failed on every
  resume since the crash, with a truncated loose object in its cregit.git (JGit
  `EOFException: Short read of block`). Its workdir was moved to
  `census-2026-10/.superseded/20261009/` (record in `superseded.tsv` there), so it
  reruns from step 1 at its recorded commit. Restarted at 01:59 UTC with
  `RETRIES=4` (foxhound's fourth interrupted attempt), as systemd user units, so
  that no session exit can stop it again:
  `systemd-run --user --unit=census-batch1 --same-dir --setenv=RETRIES=4 ... ./run_batch1.sh`
  and `--unit=census-step-monitor ... python3 step_monitor.py`, output appended to
  `batch1.log` and `step_monitor.log`. Check with
  `systemctl --user status census-batch1`. Stop after the running projects with
  `touch STOP` as before; `systemctl --user stop` sends SIGTERM.
- 2026-10-09 06:02 UTC: the OOM killer hit one process of Wilfred__difftastic (peak 16.4 GB
  RSS in its step 2 resume). The systemd default `OOMPolicy=stop` then stopped the whole unit, so
  foxhound (in gc after step 2, about 4 h lost) and tracy (in blame) were killed too (rc=-15). The
  stop was found at 12:13 UTC. No lock files were left. Restarted at 12:16 UTC with the user's
  agreement: `WORKERS=2 RETRIES=6` and `-p OOMPolicy=continue`, so that an OOM fails only that
  project. foxhound and tracy resumed at step 2.
- 2026-10-09 14:37 UTC: with the user's agreement, `touch STOP` in the ctp worktree: batch 1 starts
  no new project here. foxhound and tracy finish locally. The not-started rest (difftastic included)
  moves to EC2 with the new code (95cdc88); the 49 finished projects get retokenized later. The
  watchdog treats this STOP as intended.
- 2026-10-11 00:38 UTC: SAP__project-foxhound finished (blame ended about 23:55; firm 1,760 s at
  19.7 GB peak RSS; validate, schema and join OK; cleanup freed 242 GiB; Parquet 1.1 GB). With STOP
  in place the census then ended with rc=3 ("done 2, skipped 49"), so the unit shows "failed". This
  is the planned end of the local run: no restart. The local run holds 51 finished projects; the
  other 113 of batch 1 run as batch1rest on the spots. The 51 get retokenized after the census.
- 2026-10-11 04:26 UTC (big EC2, batch 4 p2): OpenVSP, plain blame for FemaleGeomData.h and
  MaleGeomData.h after 38.5 h of `-C100` (user decision). The census was not restarted: the
  `blameRepoFiles.pl` parent was paused, the 2 git blame processes stopped, the 2 `.blame` files
  replaced with plain-blame copies, the parent resumed. Details and the formatBlame exit-code
  defect: runs-20261009.md, update 04:30 UTC.
- 2026-10-11 06:46 UTC: spot a reclaimed; watchdog restart 3 of 6 on $RUNNER_EC2_SPOT_A5. After the
  relaunch, `batch22 a3` and `batch21 a5` (local run census-local-a) were removed from the new fed
  queue again (`local-a/queue-edit2.ssm.json`). Do this after every spot a relaunch until the local
  run ends and its outputs are merged. Details: runs-20261009.md, update 07:30 UTC.
- After every spot relaunch, `~/s3-work/ec2-batch3/post_relaunch.sh <a|b> <instance-id>` does the
  three post-relaunch steps. `restart_spot.sh` runs it at its end (since 2026-10-12 01:30 UTC).
  The steps: (1) spot a: `/etc/cregit-census/fed/slots` = 12; (2) both halves: `formatBlame.pl`
  of 57551d7 in the cregit copy of each active b3/b5 part; (3) spot a: remove `batch22 a3` and
  `batch21 a5` from the fed queue, under the feeder lock. Each step checks first and prints SKIP
  when the state is not the expected one. A second run changes nothing. The b3 parts run in the
  template `/data/cregit-ec2`, and the script never changes the template. Thus the b3 parts keep
  the old file. If the script ends with "FAILED or incomplete", run it again by hand. Details:
  runs-20261009.md, update 01:35 UTC 2026-10-12.
- 2026-10-12 06:07 UTC: AWS reclaimed spot b ($RUNNER_EC2_SPOT_B4, "Spot instance termination").
  The watchdog launched $RUNNER_EC2_SPOT_B5 (us-west-2d) at 06:18 UTC, restart 3 of 10. 163 projects
  were left. The gate gave 40511e0d (b5 parts) and 14eb5d72 (fed parts). `post_relaunch.sh` swapped
  `formatBlame.pl` in the copy of census-b5@batch1restb2 (arangodb). The feeder started fed parts
  from 06:32 UTC. The projects that ran at the reclaim start again. batch15 b1 (BRL-CAD, gone) is in
  the queue again and fails at resolve. No action was needed. Details: runs-20261009.md, update
  06:40 UTC 2026-10-12.
- 2026-10-13 07:32 UTC (big EC2, L7-20): low disk. All 6 kernels of wave 2 were in step 10 at once;
  their DuckDB temp files grew /bL7 by about 17 GB/min (2,649 of 2,999 GB used, /data 650 GB free,
  under the 800 GB guard, which touched STOP in /bL7, /bL7b, /bL1r and /bL23). To prevent ENOSPC,
  the `generate_dataset.py` processes of 4 kernels (WSL2, ni, gsc, OHCL) got SIGSTOP; adi and Xilinx
  continue. No process was killed. Resume with SIGCONT after the space comes back; then remove the
  guard STOP files. Script `~/s3-work/ec2-L7-20/scripts/space-pause-20261013.sh`, log
  `/data/logs/space-pause-20261013.log`. Details: runs-20261009.md, update 07:40 UTC 2026-10-13.
- 2026-10-15 15:39 UTC (big EC2): the machine powered itself off after the L7-20b finalize, as built.
  liferay ended (join 15:37); all 10 queues of the big EC2 have `final/DONE` in S3. No restart: no
  work is left there. Lost with the instance store: `/data/logs` and the liferay helper log. The
  instance is stopped, not terminated (the user decides). Details: runs-20261009.md, update 15:50 UTC.
- 2026-10-15 20:02 UTC (spot b): the watchdog relaunched spot b (restart 4 of 10)
  after the old one ended its work: BRL-CAD (batch15b1, excluded) still counted as remaining. Fix: the
  skip list `census-watchdog/settled.tsv` in `restart_spot.sh --remaining`; spot b now counts 0. The new
  spot b is held (NO_SHUTDOWN) for plan B. Details: runs-20261009.md, update 21:15 UTC.
- Open check: stella-emu__stella was running at the crash and finished after the
  restart; its cleanup deleted the memo and repos, so zero-length memo entries
  (possible on xfs after a crash) can no longer be ruled out. A rerun is cheap.
- Do not move a finished output away without also deleting its row from the
  `joined` table of `ctp.duckdb`: the join of every later project fails.

## Batches 2 and 3 on EC2 (2026-10-09)

Runbook with every command: `~/s3-work/ec2-batch3/README.md`. In short:

- Batch 3 = rows 329-492 of `frame.layer1.csv`, built by `build_run.sh` and split by
  `split_batch3.py`. `manifest.batch3L.tsv` has the 5 L projects. `manifest.batch3a.tsv` (80) and
  `manifest.batch3b.tsv` (79) take alternate S+M rows in u order. `manifest.batch3a1..a4.tsv`
  are batch3a's 4 parts for the A/B test (rows k, k+4, ...). The spot instance writes the same
  files itself, and they were sha256-identical.
- batch3L runs on the batch 2 on-demand instance $RUNNER_EC2_BIG, with its own ctp clone and
  output and 5 workers. A waiter starts it when batch 2 has no unstarted project left and runs at
  most 15 projects. The instance powers off only after both batch 2 and batch3L have finalized,
  whichever finishes second.
- batch3a and batch3b run on one-time m6id.24xlarge spot instances. They use `--memory-limit
  16GB`, because lagadic__visp failed in firm at 8 GB on batch 2. Each finished project is copied
  to `batch3/<a|b>/done/<project>/` with an `OK` marker. A watcher acts on a spot notice.
  `restart_spot.sh a|b` reruns what has no `OK` yet.
  Restart 2026-10-09 23:31 UTC: AWS reclaimed spot b ($RUNNER_EC2_SPOT_B2, notice 23:21 UTC).
  The watchdog launched $RUNNER_EC2_SPOT_B3 and `restart_spot.sh` ended OK at 23:45 UTC; the
  feeder queued the batch 6 b parts again. Half b has used 1 of its 3 restarts.
  Restart 2026-10-10 07:16 UTC: AWS reclaimed spot a ($RUNNER_EC2_SPOT_A2). The watchdog launched
  $RUNNER_EC2_SPOT_A3 (m5d.24xlarge, 384 GiB, 4 x 838 GB); restart OK at 07:37 UTC. Two feeder fixes
  followed (tar race in part-init; slots 5 and worker_slots 16 on this smaller type), see
  runs-20261009.md. Half a has used 1 of its 3 restarts.
  Restart 2026-10-10 12:31 UTC: AWS reclaimed the m5d spot a; the watchdog launched
  $RUNNER_EC2_SPOT_A4 (i4i.24xlarge); restart OK at 12:53 UTC. Half a has used 2 of its 3 restarts.
  Restart 2026-10-10 16:32 UTC: AWS reclaimed spot b; the watchdog launched $RUNNER_EC2_SPOT_B4
  (i4i.24xlarge); it ran at 16:50 UTC. Half b has used 2 of its 3 restarts.
- A/B test: batch3a uses one XFS filesystem per instance-store disk, with one census part per
  filesystem and the 20 workers split evenly. Run 2 (from 12:27 UTC, EC2 Fleet, both on
  i4i.24xlarge) has 6 parts of 4,4,3,3,3,3 workers; `manifest.batch3a1..a4.tsv` describe run 1's
  4 parts only.
  batch3b keeps one RAID0 with 20 workers. The reason is that step 2 on batch 2 waited on
  cross-directory `rename()`, which Linux serializes per filesystem (`ec2-load-20261009.md`).
  `ab_compare.py` compares step-2 commits/s and projects/hour from `done/`.
- Watch: `aws s3 cp s3://$RUNNER_BUCKET/<batch2|batch3L|batch3/a|batch3/b>/live/progress.txt -`;
  for batch 2, `steps.txt` shows each running project's cregit step and lists LineageOS first.
- Stop: `touch STOP` in the census's ctp clone (via SSM). `NO_SHUTDOWN` in /home/ec2-user keeps
  an instance up after its finalize.
- Costs: on-demand about $5.70/h. Spot was $1.73-2.85/h by AZ, never more than on-demand.
  Spot capacity for m6id.24xlarge was very low: the first two spot instances were reclaimed after
  about 25 min, and at 04:04 UTC no AZ had capacity.
  Run 2 used an EC2 Fleet over 8 x86 NVMe types in all AZs and got i4i.24xlarge.
- Spot census units have `OOMPolicy=continue`. census-batch2 and census-batch3L were left at the
  default `stop`, because changing them would need a daemon-reload while batch 2 runs.

## Batch 4 on EC2 (2026-10-09)

The runbook with every command is `~/s3-work/ec2-batch4/README.md`. In short:

- **What it is.** Batch 4 = rows 493-656 of `frame.layer1.csv`, all size classes. `build_run.sh`
  builds `manifest.batch4.tsv`.
- **The split.** `split_batch4.py` splits it by alternate rows in u order:
  - `manifest.batch4p1.tsv`: 55 projects, S 47, M 7, L 1 (lvbs-linux);
  - `manifest.batch4p2.tsv`: 55 projects, S 43, M 10, L 2 (llvm-mos, ceph);
  - `manifest.batch4p3.tsv`: 54 projects, S 47, M 7.
- **Where it runs.** On the batch 2 on-demand instance, next to batch 2 and batch3L, since 13:19 UTC.
  There are 3 censuses, `census-batch4p1`, `census-batch4p2` and `census-batch4p3`, each with 4 workers,
  `--memory-limit 16GB`, `--disk-floor-gb 300` and `OOMPolicy=continue`.
- **Filesystems.** Each census has its own loop-mounted XFS (a sparse 1200 GiB image on /data, at
  /b4p1../b4p3). Each is its own superblock and so has its own rename lock (`ec2-load-20261009.md`).
  A root timer runs fstrim on them and writes STOP into batch 4 if /data has less than 800 GiB free.
- **Identity check.** The libexpat check on /b4p1 gave Parquet sha256 40511e0d...fc5d, identical to
  the reference.
- **Power-off rule.** The instance now powers off only when batch 2, batch3L and batch 4 have ALL
  finalized: every `final/DONE` is in S3 and no census unit is active (`census-other-done`). Tested
  with dry runs, and nothing powered off.
- **Watch:** `aws s3 cp s3://$RUNNER_BUCKET/batch4/live/progress.txt -`, and
  `steps.txt` for all 3 parts, with the L projects first.

## Batch 5 and batch 1 rest on EC2 (2026-10-09)

The runbook with every command is `~/s3-work/ec2-batch5/README.md`. In short:

- **What it is.**
  - batch5 = rows 657-820 of `frame.layer1.csv` (164 projects: S 143, M 19, L 2).
  - batch1rest = the batch 1 projects that did not finish locally (113 projects: S 94, M 16, L 3).
    It leaves out the 49 finished ones (`batch1-finished-20261009.txt`) and foxhound and tracy,
    which finish locally. It runs with the new code.
  - `build_run.sh` builds batch5, and `split_batch5.py` builds batch1rest and the split.
- **The split.**
  - The 5 L projects go to `manifest.batch5L.tsv`: census batch5L on the batch 2 on-demand instance,
    5 workers, own loop XFS /b5L and own cregit copy.
  - The S and M projects go to 10 parts of 4 workers, 5 on each batch 3 spot instance (`parts.tsv`,
    `parts.assign.tsv`, `manifest.<workload><part>.tsv`). They are balanced by predicted time, and
    every part is in u order.
  - The instances derive the part manifests from the workload manifests with
    `split_batch5.py --derive` and check each sha256.
- **Started.** The spot parts at 16:38:55 UTC (`census-b5@<id>`) and batch5L at 16:43:07 UTC.
  - Every part has its own loop XFS image, ctp clone and cregit copy, with its path fixed before
    the start, and `OOMPolicy=continue`.
  - The libexpat check gave Parquet sha256 40511e0d...fc5d on one new copy per instance.
- **Termination.** A spot instance terminates only when every census on it (the batch 3 parts and
  the batch 5 parts) has finalized (`census-spot-decide`).
  - The big EC2 powers off only when batch 2, 3L, 4 and 5L have all finalized (`census-other-done`).
  - Tested with dry runs; nothing terminated or powered off.
- **Restart.** `restart_spot.sh` relaunches every unfinished workload of a lost spot half, with
  remaining = share minus done/OK. The watchdog keeps its cap of 3 restarts per half. Tested with stubs.
- **Watch:** `status_all.sh` (it also shows `batch5L`, `batch5/a1` and `batch5/b1`: the combined
  view of each spot instance), or
  `aws s3 cp s3://$RUNNER_BUCKET/batch5/a1/live/progress.txt -`.

## Local supplement run (2026-10-11)

The user approved this on 2026-10-11: this machine runs S projects from the end of spot a's queue.
Spot b does not change. No part moves between the two spot instances.

- **Parts.** `batch22 a3` (7 S) and `batch21 a5` (12 S), 19 projects. These are the only parts at
  the end of spot a's queue with S rows only. Every other tail part has M rows. This run takes S
  rows only, so a part with M rows stays on spot a.
- **Queue edit.** 04:33:27 UTC, through SSM, under the feeder lock: spot a's queue went from 64 to
  62 lines (temp file, then `mv`). No unit was restarted, stopped or reloaded.
  Record: `local-a/queue-edit.out.txt`.
- **Code.** ctp ca113e3 and cregit 1f17663, the same code as the spot parts of batches 7-22.
  srcML is `/nix/store/g6xii595...-srcml-1.1.0-unstable-2026-10-04` and libsrcml is dea4467b.
  The blobExec jar is 3daa1201. git is 2.55.0.
- **Gate.** libexpat gave Parquet sha256 14eb5d72...b799 (2,196,248 bytes). This is the
  reference value. Result: `local-a/gate-result.txt`.
- **Unit.** systemd user unit `census-local-a` (`-p OOMPolicy=continue -p MemoryMax=14G`).
  The unit runs `local-a/run.sh`, with 2 workers, `--retries 3 --skip-html --latest
  --tokenizer-worker --blame-jobs 4 --memory-limit 6GB --min-free-mem-gb 8 --disk-floor-gb 300`.
  The memory limit is 6GB, not 16GB, because the budget of this machine is 14 GB.
- **Files.** Everything is in `$CREGIT_PROJECTS/cregit-workspace/census-local-a/`:
  - `ctp/` is the ctp clone and `cregit/` is the cregit copy.
  - `out/` holds the outputs.
  - `logs/census-local-a.log` and `logs/publish.log` are the logs.
  - `<workload>/<part>/done/<project>/` holds the finished projects. This is the S3 `done/` layout:
    the Parquet, `.validated`, `state/`, `ledger.jsonl` and `OK`. The first line of `OK` is
    `<sha256>  <name>-dataset.parquet`.
  - `publish_done.py` writes these folders every 60 s and once more at the end.
- **Check.** Use `systemctl --user status census-local-a` and
  `tail $CREGIT_PROJECTS/cregit-workspace/census-local-a/logs/census-local-a.log`.
  To count the finished projects, use
  `find $CREGIT_PROJECTS/cregit-workspace/census-local-a/batch2? -path '*/done/*' -name OK | wc -l`.
- **Stop.** To stop after the running projects, run
  `touch $CREGIT_PROJECTS/cregit-workspace/census-local-a/ctp/STOP`. `systemctl --user stop` sends
  SIGTERM to the running projects.
- **Spot a restart.** `restart_spot.sh a` computes the remaining work from S3 `done/OK`. These 19
  projects have no `OK` in S3, so after a reclaim of spot a, `census-fed-enqueue` adds
  `batch22 a3` and `batch21 a5` to the new queue again. Remove them again after such a restart.
  Do this before the feeder reaches them.
- **Merge.** The S3 `done/` folders do not hold these 19 projects. The merge must also read
  `census-local-a/<workload>/<part>/done/`.
- **Rerun census-local-b (2026-10-12).** The same setup reran objectteams (batch11 a4) with ctp
  ca113e3, cregit 57551d7 and 1 worker. The gate gave libexpat 14eb5d72...b799. The project is done.
  The output is in `$CREGIT_PROJECTS/cregit-workspace/census-local-b/batch11/a4/done/`, and the scripts
  and records are in `local-b/`. The merge must also read `census-local-b/<workload>/<part>/done/`.
- **Rerun census-local-c (2026-10-12).** The same setup reruns 49 of the 51 batch 1 projects that
  ran with the old cregit 157cf8b (not torvalds__linux and SAP__project-foxhound). It uses ctp
  ca113e3, cregit 57551d7, 2 workers and the LPT order. The gate gave libexpat 14eb5d72...b799. The
  unit started at 13:53:56 UTC. The output goes to `$CREGIT_PROJECTS/cregit-workspace/census-local-c/batch1/done/`,
  and the scripts and records are in `local-c/`. To stop after the running projects, run
  `touch $CREGIT_PROJECTS/cregit-workspace/census-local-c/ctp/STOP`.
- **Rerun census-local-d (2026-10-14).** The same setup reran gitlab.inria.fr__cedar__connectionlens
  (batch25 a4). All 4 spot attempts failed in blame: git -C100 exits 128 ("unable to generate diff")
  when a commit moves a blob over 1 GiB. The user chose a rerun with the fix: cregit 23e4ccb (57551d7 plus
  plain blame after a -C100 git exit 128, branch fix/blame-exit128-fallback). ctp ca113e3, 1 worker, the
  local-b memory flags. The gate gave libexpat 14eb5d72...b799. The project is done (15:01:47 UTC), with 2
  PLAIN-BLAME files. The output is in `$CREGIT_PROJECTS/cregit-workspace/census-local-d/batch25/a4/done/`, and the
  scripts and records are in `local-d/`. prelim_merge.py reads it.

## Second L queue L7-20b on the big EC2 (2026-10-11)

The user approved this on 2026-10-11 at 16:45 UTC. The runbook is `~/s3-work/ec2-L7-20b/README.md`.

- **Split.** Census L7-20 runs rows 1-6 (6 kernel trees) and keeps rows 7-16 (10 projects, 353.7 h predicted). Census L7-20b runs rows 17-56 (BrowserWorks__waterfox .. jlord__patchwork, 40 projects, 330.2 h predicted). The rows that had not started had 683.9 h predicted, so half is 341.9 h (inferred).
- **Inputs.** They are built on the instance from the L7-20 v2 inputs (no upload): `manifest.L7-20b.tsv` (sha256 ba254e0e…; the rows are unchanged and in the same order) and a byte copy of the L7-20 sidecar.
- **Code.** ctp ca113e3 and cregit 1f17663 (copies of the L7-20 ones). The gate gave libexpat 14eb5d72… at 19:15:55 UTC.
- **Census.** `census-L7-20b` uses 6 workers and the L7-20 flags. It runs on its own loop XFS `/bL7b`. It started at 19:16:01 UTC.
- **No double run.** `census-L7-20-split.timer` (every 5 s) writes `/bL7/ctp/STOP` and the marker `/bL7/ctp/STOP.split-L7-20b` when census L7-20 has started all 16 rows before row 17 and L7-20b has started. ctp census then starts no new project and no retry, and the running projects finish. A row of rows 1-16 that fails after that needs a rerun; the watcher lists it.
- **S3.** `L7-20b/live/` (with a "split:" line), `L7-20b/done/`, `L7-20b/final/`.
- **Power-off, guard, backup, watchdog.** `census-other-done`, the guard, `census-backup`, `watchdog.sh`, `status_all.sh` and `fetch_done.sh` include L7-20b.
- **Expected end (inferred).** L7-20b about 2026-10-14 03:00 UTC, L7-20 about 2026-10-15 04:00 UTC.

## Batch 24: the not-started L7-20b rows on spot b (2026-10-13, prepared, not queued)

User decision 2026-10-13 ~12:35 UTC. The runbook is `~/s3-work/ec2-batch24/README.md`.

- **Why.** Spot b used 3 of its 20 workers. The big EC2 ran at a load of about 208 on 96 CPUs, and the L7-20b rows took about 1.6 times their predictions there (2 of 40 done after 41 h).
- **Freeze.** `/bL7b/ctp/STOP` (and `STOP.move-to-spot-b`) since 12:40:50 UTC. Census L7-20b starts no new row and no retry. Its 6 running rows finish, then it ends and writes `L7-20b/final/DONE`. Do not remove this STOP: L7-20b would then start the moved rows again.
- **Rows.** The 32 rows that L7-20b had not started: rows 25-56 of `manifest.L7-20.tsv` v2 (freebsd__freebsd-src .. jlord__patchwork, all L, 169.6 h predicted, inferred). Fields and order are unchanged. The sidecar is a byte copy of the L7-20 one.
- **Parts.** Fed workload `batch24`, half b only: 5 parts (b1-b5) of 3 workers, LPT by predicted hours (makespan 12.0-13.1 h each, inferred). Each part has its own 1200G image with a 300G disk floor. Cregit 57551d7, libexpat gate 14eb5d72.
- **Steps.** The user runs `upload-batch24.sh` (ALL OK), then `S1-feed-line.sh` (feed.tsv, for a relaunch), then `s24-enqueue.sh` on spot b.
- **Risks.** A spot reclaim runs the rows in progress again from the start. A failure of one of the 6 running L7-20b rows needs a rerun.

## Batch 23: the DP8L v4 near-miss supplement (2026-10-11, prepared, not queued)

The user decided on 2026-10-11 at about 19:00 UTC: "Yes, add them". The runbooks are `~/s3-work/ec2-batch23/README.md` (spot parts, upload) and `~/s3-work/ec2-L23/README.md` (census L23).

- **Rule (DP8L v4).** `../s4-filter/funnel.py --near-miss` applies DP8L v3, and a GitHub row of the near-miss classes C, D and E of `../s4-filter/dp8l-audit/` also passes (`NEAR_MISS`: other root name, a package file declares a license, a license file in a subfolder). It writes `frame.v4.csv`, `funnel.v4.md`, `frame_status.v4.csv` and `supplement.v4.csv`. `frame.csv` (d99faef7…) and `frame.layer1.csv` do not change. The v3 files come out the same with the new code.
- **Funnel.** v3 26,012 projects, v4 26,837 (+825 = 593 E + 154 D + 78 C). Layer 1: 3,379 to 3,497 (+118). The audit predicted 118 (E 96, D 12, C 10).
- **Rows.** `../s4-filter/supplement_batch.py 23 v4` takes the layer 1 rows of `supplement.v4.csv` that are in no manifest of batches 1-22: 118 rows, S 93, M 17, L 8, all on GitHub. It writes `supplement23.v4.csv`, `supplement23.licenses.csv` (NOASSERTION for all 118; the evidence is "<class>: <file names>") and `../s2-pool/v2/pool.batch23.csv` (118 rows, equal to their `pool.csv` rows).
- **Build.** `POOL=../s2-pool/v2/pool.batch23.csv bash build_run.sh supplement 23 ../s4-filter/supplement23.v4.csv ../s4-filter/supplement23.licenses.csv`, then `split_batchN.py 23` (5 parts per half). The sidecar has 118 of 118 keys joined, a license value and a `source` value for each. `batch23.ubatch.tsv` gives the u batch of each row (the batch 21 rule). No name or URL repeats in batches 1-23 (3,497 projects). The parts derive with sha256 ok. `SHA256SUMS` gets 19 new lines.
- **Parts.** All 10 parts run on spot b (user decision 2026-10-11 ~21:05 UTC; spot a had 55 parts queued, spot b 21): batch23 b1-b10, 110 projects (S 93, M 17), 55.4 h of work (inferred). `one_half.py batch23 b` set the half column of `parts.batch23.tsv` to b for every part and renamed a1-a5 to b6-b10 (the rows of each part do not change). census-fed-enqueue and `restart_spot.sh` pick the parts of a half by that column, so a spot a relaunch queues no batch 23 part.
- **L rows.** `manifest.batch23L.tsv`: NetBSD/src, openbsd/src, checkedc/checkedc-clang, WebKit/WebKit, Xilinx/hls-llvm-project, openbsd/ports, alpinelinux/aports, archlinuxcn/repo. They run as census L23 on the big EC2, in LPT order (`manifest.L23.tsv`, built on the instance), 4 workers, own loop XFS `/bL23`.
- **Clone check.** `../clone-failures-20261009/probe_rows.py` (read-only: `git ls-remote` and `gh api repos/<slug>/commits/<oid>`, one call at a time): 118 of 118 resolve, and 118 of 118 pinned commits exist on GitHub. The head moved after the snapshot for 64 rows. Output: `../clone-failures-20261009/probes/20261011T2007Z-batch23/`.
- **Code.** ctp ca113e3, cregit 57551d7 (the blame time limit), bundle `cregit-57551d7.bundle` (sha256 18b1bf1c…, in S3 since 20:05 UTC), libexpat gate 14eb5d72….
- **S5/S6 (run on 2026-10-16).** `build_evidence.py` and `build_labels.py` have `frame.batch23.csv` in `FRAMES`. The pool rows are in `s2-pool/pool.csv` (`v2/pool.batch23.csv` holds the same 118 rows), so no pool file was added. S5: 3,497 projects, 4,656 fact rows (145 of batch 23); the old `evidence.csv` is kept as `../s5-evidence/evidence.20261011.csv`. S6: `build_labels.py --date 2026-10-16 --prior labels.20261011.csv` (the old `labels.csv`, kept). The 3,379 old rows do not change. The 118 new rows: unknown 86, personal 15, foundation 11, company 6 (`label_date` 2026-10-16). `final_meta.py` has `project_meta.batch23.json`, `frame.batch23.csv` and `../s4-filter/supplement23.licenses.csv` in its defaults (with batches 25 and 26; see `final_meta.py` above). Open for the user: 3 company labels from one rule-based source (`../s6-labels/method.md` case L7).
- **Order of the start.** The user runs `~/s3-work/upload-batch23.sh` (Claude's S3 uploads are denied). After `ALL OK`: the feed.tsv line (`S1-feed-line.sh`), `s23-enqueue.sh` on spot b only, then the L23 steps L1 to L3 and `W1-watch-entries.sh`.

## L1r: batch 1 L rerun on the big EC2 (2026-10-12, installed, started 20:04 UTC)

- 2026-10-12 20:04 UTC, user decision "Start L1r now": `IGNORE-L23` and `MAXRUN=14` (drop-in of
  census-L1r-wait). Script `~/s3-work/ec2-L1r/scripts/L4-start-now.sh`. Details: runs-20261009.md, update 20:10 UTC.

The user decided on 2026-10-12 at about 14:10 UTC: "Big EC2 L queue". The runbook is `~/s3-work/ec2-L1r/README.md`. The user uploaded the inputs at 18:07 UTC (ALL OK). The install ended at 18:17 UTC: the gate passed (libexpat 14eb5d72…), and the waiter waits for census L23.

- **Projects.** torvalds__linux and SAP__project-foxhound. Batch 1 ran them with the old cregit 157cf8b. The other 49 batch 1 projects run again on this machine (census-local-c).
- **Inputs.** `manifest.L1r.tsv` (sha256 3443e70a…): the 2 rows of `manifest.batch1.tsv`, unchanged, foxhound first (LPT). `project_meta.L1r.json` (sha256 c4c5b946…): the 2 entries of `project_meta.batch1.json`, unchanged. The user uploads them with `~/s3-work/upload-L1r.sh` to `L1r/input/`.
- **Code.** ctp ca113e3, cregit 57551d7 (bundle sha256 18b1bf1c…), own gate (libexpat 14eb5d72…). The L23 flags with 2 workers and `--latest`.
- **Disk.** Own loop XFS `/bL1r` (3000G sparse). The guard fstrims it and writes its STOP below 800 GiB on /data.
- **Priority.** The waiter starts L1r only after census L23 has started, and only when at most 12 other projects run (L23 counts as its 4 worker slots while it has queued rows), MemAvailable >= 120 GiB and /data >= 1600 GiB free. `census-L1r-wait --decide-only` shows the decision.
- **Firm step.** `census-L1r-firm.timer` sets oom_score_adj -500 on the L1r firm processes every 30 s.
- **S3.** `L1r/input/`, `L1r/live/`, `L1r/final/`, `L1r/done/<project>/`.
- **Power-off, guard, backup, watchdog.** `census-other-done`, the guard and `census-backup` have L1r since the install (L2a, backups `.orig-L23`). `watchdog.sh`, `status_all.sh`, `fetch_done.sh` and `prelim_merge.py` (`"L1r": "57551d7"`) have it now.

## Preliminary merge for queries (2026-10-12)

`prelim_merge.py` builds `$CREGIT_PROJECTS/cregit-workspace/merge-prelim/prelim.duckdb` from the Parquets on
this machine. It copies no token data: the view `tokens` reads the chosen Parquets in place. It is
not the final merge (task 6). Run it again to add new arrivals (about 30 s):

```
$CREGIT_PROJECTS/cregit-workspace/census-local-a/ctp/.venv/bin/python -I prelim_merge.py
```

- One Parquet per project. Order: local-b/local-a reruns, then the 1f17663/57551d7 cloud files and
  the trailer-fixed 95cdc88 files (`census-cloud-fixed`), then unfixed 95cdc88 files, then batch 1
  local (cregit 157cf8b, `needs_retokenize`).
- Tables: `projects`, `candidates`, `frame` (3,497 v1 projects); views `frame_status`, `tokens`.
- First build (13:50 UTC): 2,842 projects, 14,374,917,935 token rows; 652 pending, 3 excluded.
- Not applied yet: the 11-column metadata rewrite (`rewrite_meta_columns.py`). Take the project
  metadata from `project_meta.layer1.final.json` until then. (2026-10-16: `project_meta.v1.final.json`
  holds all 3,548 v1 projects, also those of batches 23, 25 and 26; it is a `--sidecar` for
  `rewrite_meta_columns.py`.)

## Trailer post-fix of the 95cdc88 batches (2026-10-11)

The user approved this on 2026-10-11.

- **Defect.** cregit 95cdc88 fills the 15 `footer_*` columns (commit trailers) wrongly.
  blobExec appends "\n" + "Former-commit-id" to each message. This makes a new paragraph, so
  JGit finds no other trailer. cregit 1f17663 reads the trailers from the step 3 original log
  DB and keeps one entry for each person in each typed list.
- **Scope.** Each row of `cregit-workspace/census-cloud/verified.tsv` of the runs batch1rest,
  batch2, batch3, batch3L, batch4, batch5, batch5L, batch6 and batch6L. The ledger rows of the
  project must name cregit 95cdc88: `done/<project>/ledger.jsonl` (spot runs, from S3), else
  `ledger.from-run.jsonl` (big EC2 runs, from `split_run_ledgers.py`; all 336 name 95cdc88). Out of scope: the 51 local batch 1 projects in
  `census-2026-10` (157cf8b; they get a new tokenization later) and batches 7-22, L7-20 and L22
  (1f17663).
- **Count at the start (04:32 UTC).** 919 Parquets: batch1rest 107, batch2 163, batch3 158,
  batch3L 4, batch4 162, batch5 162, batch5L 4, batch6 157, batch6L 2. 0 are in
  `census-2026-10`. `footer_fix_batches.py --list` prints the current counts.
- **The persons DB.** The spot runs (batch1rest, batch3, batch5, batch6: 584 projects) did not
  upload `<project>-persons.db`. `footer_fix_batches.py` builds it again as step 5 does (the
  persons one-jar), on a commit-only clone that holds only the branch of `state/pin.json` at the
  pinned commit, as `pin.py` does. Measured on Activiti__Activiti: the tables are equal to the
  census DB, except the `emails.dateadded` time. `rewrite_footer_columns.py` checks the DB
  against the person columns of every author and refuses the file if one differs. The manifest
  note is `persons_db=rebuilt`.
- **The pinned clone.** Since 2026-10-11 06:05 UTC, when the pinned commit is known
  (`state/pin.json`, else `pin.from-run.json`), the tool reads a commit-only clone with only that
  branch at that commit. When the branch no longer holds the commit (an upstream history
  rewrite), the script fetches it by its hash, as `pin.py` does. The manifest note is `pinned`.
  Measured on Activiti__Activiti and fledge-iot__fledge: the output has the same sha256 as with
  the clone of `clone_url`. ptt__pttbbs (batch2) was refused with the clone of `clone_url`
  (41 commits not in it); with its pinned commit e7d7627 it is ok (2 commits changed).
- **Output.** `cregit-workspace/census-cloud-fixed/<same relative path>/<project>-dataset.parquet`
  plus the persons DB that the tool used. The original files are only read.
  `census-cloud-fixed/manifest.tsv` has one row for each attempt (the last row of a path counts):
  project, run, input and output sha256, rows, commits, changed commits (commits whose 15 values
  changed), commits with a typed trailer before and after, status, seconds. The tool output is in
  `logs/<project>.log`, its report row in `reports/<project>.tsv`, the job log in
  `footer-fix.log`. The clones and the original log DBs are in `.work/<project>` and are deleted
  after each project.
- **Unit.** `footer-fix` (systemd user unit, `OOMPolicy=continue`, `MemoryMax=12G`). At most 2
  projects at a time; a project with more than 300,000 commits runs alone. `--java-opts=-Xmx3g`,
  DuckDB memory limit 3 GB, 2 threads.
  - Check: `systemctl --user status footer-fix`, `tail census-cloud-fixed/footer-fix.log`,
    `cut -f12 census-cloud-fixed/manifest.tsv | sort | uniq -c`.
  - Stop after the running projects: `touch census-cloud-fixed/STOP`. Stop at once:
    `systemctl --user stop footer-fix` (the next run deletes the partial output, the spill and the work directory).
  - New arrivals: remove `STOP`, then start the unit again with the same command (it skips
    the done ones; `--retry-failed` tries the failed ones again):
    `systemd-run --user --unit=footer-fix -p OOMPolicy=continue -p MemoryMax=12G
    -p StandardOutput=append:$CREGIT_PROJECTS/cregit-workspace/census-cloud-fixed/footer-fix.log
    -p StandardError=append:$CREGIT_PROJECTS/cregit-workspace/census-cloud-fixed/footer-fix.log
    --setenv=HOME=$HOME --setenv=PATH="$PATH" <python with duckdb> -I <this dir>/footer_fix_batches.py --jobs 2`.
    `--retry-transient` tries again only the statuses that can change (clone_failed, error,
    no_persons_db, input_mismatch), not `refused`.
- **Timer.** `footer-fix-again` (transient user timer, every 2 h at :20, from 2026-10-11 06:20
  UTC) runs `footer_fix_again.sh`. Its log: `census-cloud-fixed/footer-fix-again.log`; the open
  projects: `census-cloud-fixed/pending.txt`. It stops itself when every project of
  `manifest.batch1rest.tsv` and `manifest.batch2.tsv` … `manifest.batch6.tsv` is settled: ok or
  refused in the post-fix manifest, `failed` in `failed-projects.tsv`, or a local batch 1
  project. A census project that fails and is not in `failed-projects.tsv` keeps it on.
  - Stop: `systemctl --user stop footer-fix-again.timer`.
  - Start again (after a reboot, say): `systemd-run --user --unit=footer-fix-again
    --on-calendar='*-*-* 00/2:20:00' --timer-property=AccuracySec=60s --setenv=HOME=$HOME
    --setenv=PATH="$PATH" <this dir>/footer_fix_again.sh`.
- **Trials (measured).** Activiti__Activiti (batch2, census persons DB): 8 commits changed, 51 ->
  55 commits with a typed trailer, 11 s. GNOME__dia (batch6, rebuilt DB): 31 changed, 0 -> 31,
  11 s. Hamlib__Hamlib (batch6, rebuilt DB): 68 changed, 0 -> 65, 16 s. A second run wrote
  nothing (0 to do). The GNOME__dia output of a run by hand and of the job are the same bytes.

## Batch 25: the GitLab layer 1 rows (2026-10-14, prepared, not queued)

User decisions 2026-10-13 ~22:15 UTC and 2026-10-14 ~01:00 UTC (verbatim in `../s2-pool/gitlab/README.md`): GitLab instances and roster groups with no stars rule, a gitlab.com search with stars > 400, "Remove copies, keep upstreams", the 2026-10-10 group rule replaced for GitLab, and "into v1 as batch 25". Runbook: `~/s3-work/ec2-batch25/README.md`.

- **Rows.** `../s2-pool/gitlab/`: 31,148 listed + 75 from the search; 170 layer 1 candidates; copy rules R1-R5 (`decide.py`): 52 kept; DP3 and DP8L with the frame's code (`measure_dp.py`): 50 rows, S 45, M 4, L 1. Pinned commit = the head fetched on 2026-10-14 (a later snapshot than the other v1 rows).
- **Build.** `build_batch25_inputs.py` wrote `../s4-filter/supplement25.gitlab.csv`, `../s4-filter/supplement25.licenses.csv` (the `supplement_batch.py` license rule) and `../s2-pool/v2/pool.batch25.csv` (origins `gitlab:<host>` or `gitlab-search:stars>400`). Then `POOL=../s2-pool/v2/pool.batch25.csv bash build_run.sh supplement 25 ../s4-filter/supplement25.gitlab.csv ../s4-filter/supplement25.licenses.csv`: 50 of 50 keys joined, 50 with a license and a source value. No name or URL repeats in batches 1-24.
- **Labels.** `labels_batch25.py` (the instance owner as roster evidence): foundation 4 (`roster_org:kde`, `roster_org:gnome`), fiscal-sponsor 5 (`fiscal_sponsor:sfc` Wine, `fiscal_sponsor:spi` Arch Linux, Adelie, Manasource), unknown 41 (freedesktop.org: no roster names the instance owner; Inria: no fact type; gitlab.com search: no S5 fact). It fills `stratum`, `fact`, `label_date` 2026-10-14 in `project_meta.batch25.json` and writes `labels.batch25.csv` with a `basis_note` for each row.
- **Parts.** `split_batchN.py 25 --parts-per-half 2`, `one_half.py batch25 a`, then part a5 (1 worker) for mesa/mesa, the one L row: a1-a4 of 4 workers (8, 13, 16, 12 rows) and a5. 16.6 h of predicted work (inferred). The derive gives sha256 ok for a1-a5. `SHA256SUMS` gets 12 lines.
- **Tooling.** `feed.next.tsv` has the batch25 line (57551d7); `prelim_merge.py` FRAME has `project_meta.batch25.json` and RUN_CREGIT `batch25`; `fetch_done.sh` fetches batch 7-25.
- **Order of the start.** The user runs `~/s3-work/upload-batch25.sh` (ALL OK); then `S1-feed-line.sh`, then `s25-enqueue.sh` on spot a only.

## Batch 26: the GitLab DP8L v4 near miss (2026-10-14, prepared, not queued)

User decision 2026-10-14 ~16:40 UTC, verbatim: "yes to mutt" (the DP8L v4 near-miss classes C, D and E, until now for GitHub rows only, also pass GitLab rows). Runbook: `~/s3-work/ec2-batch26/README.md`.

- **Rows.** `../s2-pool/gitlab/near_miss_gitlab.py` (the classes of `../s4-filter/dp8l-audit/audit_dp8l.py`) on the 2 kept GitLab rows that pass DP3 and fail DP8L: muttmua/mutt class C (root `COPYRIGHT`, `GPL`), mesa/demos class H (stays out). 1 row, S, pinned 844fcfe7861631359ee789e4231d322144a1bd3b (the head that `measure_dp.py` fetched on 2026-10-14).
- **Build.** `../s2-pool/gitlab/build_batch26_inputs.py` wrote `../s4-filter/supplement26.gitlab.csv`, `../s4-filter/supplement26.licenses.csv` (NOASSERTION, evidence `C near miss: other root name: COPYRIGHT;GPL`) and `../s2-pool/v2/pool.batch26.csv`. Then `POOL=../s2-pool/v2/pool.batch26.csv bash build_run.sh supplement 26 ../s4-filter/supplement26.gitlab.csv ../s4-filter/supplement26.licenses.csv`: 1 of 1 keys joined, with a license and a source value. No name or URL repeats in batches 1-25.
- **Labels.** `labels_batch26.py`: unknown (a gitlab.com search row, no S5 fact; the batch 25 rule), `other_facts` owner_kind:user; `labels.batch26.csv`.
- **Part.** `parts_batch26.py`: part a1, 1 worker, spot a, 0.1 h predicted (inferred). The derive gives sha256 ok. `SHA256SUMS` gets 8 lines (the `project_meta.batch26.json` line holds the sha256 after the label fill).
- **Tooling.** `feed.next.tsv` has the batch26 line (57551d7); `prelim_merge.py` FRAME has `project_meta.batch26.json` and RUN_CREGIT `batch26` (v1 = 3,548); `fetch_done.sh` fetches batch 7-26; `../report/build_status_html.py` reads `pool.batch26.csv`.
- **Order of the start.** The user runs `~/s3-work/upload-batch26.sh` (ALL OK); then `S1-feed-line.sh`, then `s26-enqueue.sh` on spot a only.

## Dataset v1-raw: the final merge, stage 1 (2026-10-16)

The dataset build ended for v1: 3,544 projects are in the preliminary merge (23,692,479,892 token
rows, 186.2 GB). Not in v1: kitao__pyxel (pending; the owner account is suspended) and the 3
excluded rows. The last project, asuswrt-merlin.ng, comes from a fast second firm step on spot a
(`~/s3-work/firm-fast-20261016/`, source `local-e`); the slow ctp run checks it later.

Decisions of the user (2026-10-16), also in `runs-20261009.md`:
- Two stages. Stage 1 is v1-raw: the 11 metadata columns from the v1 sidecar and the v1 encoding,
  with the real names and e-mail addresses. It stays private (S3 backup). Stage 2 is v1-public:
  the pseudonymized files, made from v1-raw after the anonymizer rework.
- Encoding v1: ZSTD level 19, `ROW_GROUP_SIZE 1000000`, `PARQUET_VERSION V2`
  (`rewrite_meta_columns.py --encoding v1`). Tests on two files: 70-77% of the run size, the same
  values in the same order.
- The Savannah owner is `gnu` (the host rule in `rewrite_meta_columns.py`).
- Batch 23 has S5/S6 labels (offline run; `s6-labels/method.md` case L7 for three
  single-source company labels, kept by the user).
- mongodb__mongo (cregit 9ccead6) has the footer post-fix (`footer_fix_batches.py` accepts 9ccead6;
  `footer-fix-again.timer` is stopped).

Files:
- `project_meta.v1.final.json` (git-ignored; pin `project_meta.v1.final.json.sha256`, 4023295a…):
  3,548 keys. `final_meta.py` writes it. The old `project_meta.layer1.final.json` (49e13f06…)
  stays.
- `final_merge.py` (tests `test_final_merge.py`): per project, largest first, copy the chosen run
  file, check its sha256, `rewrite_meta_columns.py --encoding v1`, `validate_schema.py` of ctp
  ca113e3 (the version on ctp `corpus-freeze-and-tests` refuses the column order of the runs),
  check the rows, copy to DEST, one row in `results.tsv`. A second start continues; `OUT/STOP`
  stops new projects. At the end: `SHA256SUMS`, `results.tsv` and the sidecar go to DEST.
- `~/s3-work/dataset-v1/` (outside git): `build_inputs.py` writes `inputs.tsv` (one row per
  project: the chosen file, its S3 key, its sha256) and `upload.tsv` (the 1,002 files that exist
  only on this machine). The user uploads with `U1-upload-inputs.sh` and `U2-upload-tools.sh`.
  On spot a: `M1-start-merge.sh` (unit `v1raw-merge`, output `/data1/v1raw/out` and
  `s3://…/dataset-v1/raw/`), `M2-check.sh` (progress). Run them with
  `cd ~/s3-work/ec2-batch23/scripts && I=<instance id> bash ssm.sh <script>`.
- Spot a has `NO_SHUTDOWN` since 2026-10-16 19:12 UTC. Remove it after the S3 backup of v1-raw.

Open for stage 2: the anonymizer rework (salted branch `feat/pseudonymise-identity-columns`, a
registry table in place of SQL `MAP` literals, one fused write, the false failures, private
reports), and the transfer of the salt (the user decides; Claude never sees the salt).

## Dataset v0 with the organization columns (runbook prepared 2026-10-19, not run)

The runbook with every command is `~/s3-work/dataset-v0-org/README.md`. In short:
- The v0 write runs again with the organization columns of `s8-companies/LINK_COLUMNS_DESIGN.md`
  (approved 2026-10-19): ctp schema 2 = the 67 columns of v1-raw without `firm_raw`, `firm` and
  `firm_source`, then `firm_based_on_namespace`, `firm_based_on_domain`,
  `project_enterprise_driven`, `project_enterprise_basis`, and three footer entries
  (`ctp_schema_version`, `organizations_version`, `organizations_mapping_sha256`; the files of
  release 1 have the old names `organisations_version` and `organisations_mapping_sha256`).
- Inputs: v1-raw from `s3://.../dataset-v1/raw/`, links of database v4.2 (`build_links.py`; the
  v4.1 links are a dry run). Output: `s3://.../dataset-v0-org/` (the old `dataset-v0/` stays).
- Machine: one i4i.24xlarge spot in us-west-2 (as spot a). Unit `v0-org`, two passes: the 10 files
  with 195 M rows or more with 10 jobs x 56 GB, then the other 3,534 files with 88 jobs x 5 GB
  (`run_v0.py --min-rows/--max-rows`). Estimate: about 5.5-6 h, about 15 USD at the spot price.
- Local test (2026-10-19, the workspace folder `companies/v0-local-test-v4.1/`): 5 small
  projects through `final_merge.py` and `run_v0.py`: the 71 columns, the footer, 0 rows that differ
  from the join prototype's method, 0 ids outside `organizations`.
