# dataset-pathfix runbook (prepared 2026-10-20; scripts made 22:15 UTC; nothing launched)

User decision 2026-10-20: fix the two cregit path defects and run the affected projects again.
The fix: cregit branch `fix/path-quoting` on `57551d7` (worktree `${RUNNER_PROJECTS_TILDE}/cregit-pathfix`).
The scan of the affected projects: `${RUNNER_PROJECTS_TILDE}/cregit-workspace/path-defect/` (`affected.tsv`,
`affected-files.tsv`, `scan-status.tsv`, `README-scan.txt`).

## Files

| file | what | who runs it |
|---|---|---|
| `S1-stage-cregit.sh` | after the commit: checks the 3 proven blobs, makes `stage/cregit-<sha7>.bundle` (needs 95cdc88, as `cregit-57551d7.bundle`), verifies it in a clone that has only 95cdc88 | main session |
| `S2-stage-inputs.sh` | `stage/inputs/`: `manifest.pathfix.tsv`, `seeds.tsv`, `parts.tsv`, `sidecars.tsv`, `SOURCE`, `SHA256SUMS` | main session |
| `U1-upload-pathfix.sh` | uploads the bundle to `B/cregit/` and the inputs plus the v1 sidecar to `B/dataset-x1k/inputs-pathfix/`, then reads them back | the user |

`B` = `s3://${RUNNER_BUCKET}`.

## The rows

36 projects with `lost_bytes > 0` in `affected.tsv` (scan of 2026-10-20: 10,758 of 10,759 trees
listed; the second pass over 64 rows of other hosts found 0 affected files; `denemo` (v1,
Savannah) is not listed, see `README-scan.txt`):

- v1: 18 rows (cregit of the run: 95cdc88 3, 1f17663 9, 57551d7 6). Not run again: `github__codeql`
  (its 2 lost files are empty, so no tokens), `JetBrains__intellij-plugins` and `KDE__labplot`
  (57551d7 runs: the single-quote files are in the Parquet).
- x1k: 18 rows (all 57551d7). 16 have a Parquet in `done-full/`; `huaweicloud__ModelArts-Lab` and
  `saleha-muzammil__Academic-Time-Machine` have none (the B run failed on the defects).

## The code path (the v1 code path, as machine B of x1k)

- ctp `ca113e3` unpatched; cregit `14b8db4` (14b8db468e4f6565fab5692a1ab1c3066d12f371) = 57551d7 +
  the fix, from `B/cregit/cregit-14b8db4.bundle` (sha256 b3d2c139...; it needs 95cdc88, which the
  AMI copy `/opt/cregit-ec2.checked` has); srcML `dea4467b`; flags of the v1 fed parts:
  `--retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB
  --min-free-mem-gb 24 --disk-floor-gb 300`.
- The libexpat gate stays `14eb5d72` (2,196,248 B): proven locally on 2026-10-20 with the final
  files (`${RUNNER_PROJECTS_TILDE}/cregit-workspace/gate-pathfix/lpf2.gate.log`). R2 keeps `WANT_PQ`.
- The same commit as the first run: `pf-seed` writes `state/<name>/latest.json` from `seeds.tsv`
  before the start, so `--latest` REUSES the commit of the first run (ctp `resolve_latest`), and
  the ledger keeps `snapshot_sha` = the manifest commit. For `resolved_sha = S3` (16 x1k rows),
  `pf-seed` reads `dataset-x1k/done-full/<name>/state/latest.json` and `ledger.rows.jsonl` on the
  machine (with the role of the machine; do not read them locally): the seed must have the
  `snapshot_sha` of `seeds.tsv`, and the final `project` row of the first run must have
  `checked_out_sha` = its `resolved_sha`. A missing or wrong seed stops the start (R4) or the
  part (`pf-run` exit 3). An existing `latest.json` with another commit is never overwritten.
- Sidecars as they are (`sidecars.tsv`): v1 rows `project_meta.v1.final.json`
  (`inputs-pathfix/sidecar/`), x1k rows `project_meta.x1k.json` (the B sidecar, from
  `dataset-x1k/inputs/`). R4 checks the sha256 of both.

## User decision 2026-10-20: 35 rows, no AliSQL

`alibaba__AliSQL` (v1) loses only 1 file of 458 bytes (a Boost.Wave test file with a non-ASCII
directory name), and its first run took 66 h. So it does not run again; it keeps its first-run
Parquet (cregit 57551d7) and gets a LIMITATIONS line
(`${RUNNER_PROJECTS_TILDE}/cregit-workspace/path-defect/LIMITATIONS-draft.txt`). Part 3 goes away. The uploaded
inputs (36 rows) do not change: R4 has `DROP="alibaba__AliSQL"`, and its deal stops if part 3 holds
another row or if the parts after the drop are not p1 = 17 and p2 = 18 rows.

## Scripts (made 2026-10-20; copies of `~/s3-work/dataset-x1k/`)

| file | from | what |
|---|---|---|
| `L1-launch-pf.sh` | `L1-launch-b.sh` | `NAME=dataset-pathfix-b1` (after a reclaim `-r1`, `-r2`, ...), own `instances.txt` and `fleet/`; types i4i.24xlarge, r6id.24xlarge, i4i.32xlarge, r6id.32xlarge (>= 768 GiB, instance store) in the 4 subnets 2a-2d; weight 1, target 1; `MAX_TOTAL_PRICE` 3.50 $/h by default; `DRY_RUN=1` = EC2 DryRun only |
| `scripts/ssm-run-pf.sh` | `w6/ssm-run.sh` | sends a script with `PF_RUN=<run id>` through `scripts/ssm.sh` (a copy); refuses the instances of the refuse list |
| `scripts/R1-setup-pf.sh` | `R1-setup.sh` | cregit 14b8db4 from the bundle; 2 parts `/data1/pf`, `/data2/pf`; config `/etc/dataset-pathfix/pK.cfg` |
| `scripts/R2-gate-pf.sh` | `R2-gate.sh` | `CREGIT_COMMIT` 14b8db4; 2 gates; `WANT_PQ` 14eb5d72 and `WANT_SRCML` dea4467b unchanged |
| `scripts/R3-install-pf.sh` | `w6/R3-install-b.sh` | run id `^dataset-pathfix-b1(-r[0-9]+)?$`; inputs `/data/pathfix-inputs`; `pf-run` (sidecar per part from `sidecars.tsv`, `pf-seed` first), `pf-seed`, `pf-upload` (DEST `dataset-x1k/done-pathfix`, never over an OK), `pf-live`, `pf-watch`, `pf-finalize` (power-off only after `final/<run>/DONE` with the size check); units `pf@1`, `pf@2` |
| `scripts/R4-start-pf.sh` | `w6/R4-start-b.sh` | inputs from `inputs-pathfix/` (SHA256SUMS pinned to c2c9ac76..., the staged one) + the x1k sidecar; code check; deal = `parts.tsv` minus AliSQL minus `done-pathfix/<name>/OK`, longest rows first; `pf-seed` for both parts; workers p1 4, p2 4 |
| `scripts/C1-check-pf.sh` | `C1-check.sh` | progress (read only) |
| `scripts/test/T1-dry-run.sh` | new | local dry run, no AWS: the deal and `pf-seed` as they are in R4/R3, on `stage/inputs/` and a synthetic `done-full/` |

Refuse list (all scripts): the big EC2 `${RUNNER_EC2_BIG}` (stopped, batch 2), machine A of x1k
`${RUNNER_EC2_X1K_LONG_A4}` (on-demand, it runs: never touch it), spot a `${RUNNER_EC2_SPOT_A6}`, the first
x1k machine `${RUNNER_EC2_X1K_A}`. S3 keys of the run: `dataset-x1k/done-pathfix/<name>/`,
`dataset-x1k/live/<run>/`, `dataset-x1k/final/<run>/` (new keys; done-full/ and done/ are only
read).

Checks of 2026-10-20 (22:15 UTC): `bash -n` of every script and of the embedded scripts of R3;
`bash scripts/test/T1-dry-run.sh` = T1 ALL PASS (p1 17 rows from SpecialK, 5.09 serial h; p2 18
rows from linuxkerneltravel__lmp, 9.16 serial h; no AliSQL; a relaunch with 2 OK gives 16 + 17;
the deal refuses an OK of AliSQL, an unknown OK and a missing DROP; `pf-seed` writes 17 + 18 seeds,
is idempotent and refuses a changed commit, a wrong snapshot, a wrong first-run checkout and a
missing seed); `NAME=dataset-pathfix-b1 DRY_RUN=1 bash L1-launch-pf.sh` = "Request would have
succeeded" (16 overrides, MaxTotalPrice 3.50, target 1).

## Steps (main session, after the user's go)

Done: 1. the commit of `fix/path-quoting` (14b8db4) and S1; 2. S2 (`stage/inputs/`, 36 rows);
3. the user ran U1 (ALL OK: `cregit-14b8db4.bundle` b3d2c139..., `SHA256SUMS.14b8db4`, the 5 input
files in `dataset-x1k/inputs-pathfix/` and the v1 sidecar); 4. the scripts above and their checks.

5. Launch and set up (about 30-45 min until R4):

```bash
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
cd ~/s3-work/dataset-pathfix
bash scripts/test/T1-dry-run.sh | tail -1                      # T1 ALL PASS
NAME=dataset-pathfix-b1 bash L1-launch-pf.sh                   # prints INSTANCE_ID TYPE SUBNET
export RUN=dataset-pathfix-b1 I=<INSTANCE_ID>
aws ssm describe-instance-information --filters Key=InstanceIds,Values=$I \
  --query 'InstanceInformationList[0].PingStatus' --output text   # wait for Online (2-5 min)
bash scripts/ssm-run-pf.sh scripts/R1-setup-pf.sh 3600         # "R1 done", p1/p2 cregit 14b8db4
TAILN=20 bash scripts/ssm-run-pf.sh scripts/R2-gate-pf.sh 7200 # p1, p2 "CHECK OK", rc=0
bash scripts/ssm-run-pf.sh scripts/R3-install-pf.sh 600        # "R3-pf installed (run dataset-pathfix-b1)"
TAILN=100 bash scripts/ssm-run-pf.sh scripts/R4-start-pf.sh 1800  # p1 17, p2 18 to run; 2 x "seeds OK"; "R4-pf done"
```

6. Watch: `TAILN=80 bash scripts/ssm-run-pf.sh scripts/C1-check-pf.sh 300`;
   `aws s3 ls s3://${RUNNER_BUCKET}/dataset-x1k/done-pathfix/ --recursive | grep -c '/OK$'`
   (35 at the end); the end: `aws s3 ls s3://${RUNNER_BUCKET}/dataset-x1k/final/$RUN/DONE`.
   The machine powers off (and terminates) 2 min after `final/<run>/DONE` is in S3 with the correct
   size. `live/<run>/ALERT` = a part ended without "census finished": no power-off; look with C1.
7. After a spot reclaim (`live/<run>/INTERRUPTED`): the same steps with
   `NAME=dataset-pathfix-b1-r1` and `RUN=dataset-pathfix-b1-r1` (then `-r2`, ...). R4 drops the rows
   that have `done-pathfix/<name>/OK`; `pf-seed` writes the same seeds again (same commits).
8. After `final/<run>/DONE`: the check below, then the merge changes.

## Time and cost (estimate)

- Part 1: 17 v1 rows, 5.1 serial h measured in the first runs, longest 1.7 h (SpecialK): ~2 h at
  4 workers.
- Part 2: 18 x1k rows, 9.2 serial h (prediction x2), longest `linuxkerneltravel__lmp` 4.8 h:
  ~5 h at 4 workers (lmp starts first).
- Setup (launch, R1, R2 gate, R3, R4) ~0.5-1 h, so about 6 h in total.
- Spot price on 2026-10-20 22:16 UTC: i4i.32xlarge 2d $1.98/h, i4i.24xlarge 2a $2.35/h and 2c
  $2.36/h, r6id.24xlarge 2b $2.47/h; cap `MAX_TOTAL_PRICE` $3.50/h. About 6 h x $2.0-2.4 = about
  15 USD (at most ~$21 at the cap); with one spot reclaim about $25-30.
- AliSQL (part 3, ~8-15 h at 32 blame jobs) does not run (user decision 2026-10-20).

## Check after the run (local, read only)

For each project with an old Parquet: the rows of every file that is not in `affected-files.tsv`
must be equal in all columns (duckdb `EXCEPT` in both directions); the new rows must be exactly
the files of `affected-files.tsv` (by `file_path`); the commit (`checked_out_sha`) must be the
seed. For the 2 new x1k rows: the Parquet exists and is validated. Then:
- v1: `~/s3-work/dataset-v1/inputs.tsv`: the 17 rows that ran again take the `done-pathfix/` key,
  sha256 and `cregit` = 14b8db4 (rebuild with `build_inputs.py`). `alibaba__AliSQL` keeps its
  first-run key and cregit 57551d7 (LIMITATIONS line).
- x1k: the merge plan (X0-X7 of `~/s3-work/dataset-x1k/README.md`) takes `done-pathfix/` before
  `done-full/` for the 18 rows (the x2 kit does it: `x2/build_inputs_x1k.py`, see the x1k README
  "Merge plan"); a path-fix row without `done-pathfix/<name>/OK` is held back, never merged in its
  defective version.
- Release: pass the rerun ledgers to `fill_release.py manifest --ledgers`; the newest finished
  `project` record wins, so `cregit_commit` = the new commit for these rows.
