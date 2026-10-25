# rust-split: part of the aws-sdk-rust blame on extra spot machines (built 2026-10-21, NOT launched)

User decision 2026-10-21: extra machines for the blame (step 7) of `awslabs__aws-sdk-rust`, the slowest row of
machine A (${RUNNER_EC2_X1K_LONG_A4}, m6a.48xlarge on-demand, Run=x1k-long). The main session launches after review.
S3 prefix: `s3://${RUNNER_BUCKET}/dataset-x1k/rust-split/` (input/, out/<k>/, control/).

## Facts from the code (cregit 57551d7, the copy of the runs: bundle `~/s3-work/upload-cregit-blamelimit/cregit-57551d7.bundle`, thin on 95cdc88; read from `${RUNNER_PROJECTS_TILDE}/cregit-workspace/cregit` at 57551d7)
- File list (`blameRepoFiles.pl` 65-102): plain `git -C <repo> ls-files` (no `-z`: a name git quotes never matches the mask and is never blamed), the mask as a Perl regex on that name, `-f <repo>/<name>`, then the skip check `-f <out>/<name>.blame`.
- Order (104-118): size of the worktree file, largest first; ties keep the ls-files order.
- The skip check runs **once**, when the list is built at the start of step 7. A `.blame` that appears later does not remove the file from the running list: machine A would blame it again (and `move()` replaces the file with equal bytes). So the extras save time only if the row restarts after their files arrived. That restart is part of the kit (rs-pull, below).
- Call (127): `formatBlame.pl --blameExtension=.blame <repo> <name> <outdir>`, fork + exec, at most `--jobs`; the output dirs are made before the first fork.
- `formatBlame.pl`: `git -C <repo> blame -C100 --porcelain <name>`; after `CREGIT_C100_LIMIT` s (unset = 3600, wall time) it kills git, prints `PLAIN-BLAME <file> after <N> s of -C100` on stderr and runs `git blame --porcelain` with no limit. A non-zero git status writes no `.blame` (exit 1). Temp file: `mkstemp("<cregit>/blameRepo/build/tmpfile-XXXXX")`, then `File::Copy::move` to `<out>/<name>.blame` (a rename when both are on one file system). The .blame lines hold commit, original path and the line text; no repo path.
- Runner: `run_pipeline_process.sh` step 7, `perl blameRepoFiles.pl --jobs=$JOBS --formatBlame=... <repo>-cregit <work>/blame "$MASK"`. Machine A's x1k-long-run removes `tmpfile-*` at each start.
- git and perl: the runs use the binaries in the PATH of the runner (on the batch machines: `/nix/store/8wxs6573...-git-2.55.0`, `perl-5.42.0`, PERL5LIB). A's exact binaries are not known here: E0 (read-only) and E1 read them from the running processes; S1 refuses an extra without the same git path and version and perl version.

## Changes to the design, and why
1. The extras take their part **from the largest index down** (A's order), and A goes up from index 1: they meet in the middle. A walking up never meets a file an extra did before the meeting.
2. **The end restart.** Because of the skip-once rule, rs-pull restarts the row once (R8 procedure) when every part is finished and all batches are in: the new list skips every pulled file. Without this the split saves nothing. A manual way: P3.
3. **A moving stop.** rs-pull sends A's newest started index to `control/a-pos.txt` every 10 min; an extra starts no file with index <= a-pos + MARGIN (300) and ends there ("met-A"). So when the extras are faster than planned they stop near A instead of doing files A has started.
4. **Batches**, not one S3 object per file: each 10 min a `b-<seq>.tar.zst` + `.list` + `.sha256` (sent last). The "temp name, then rename" of the brief is formatBlame.pl's own (S1 checks that its build dir and the out dir are on one file system); a batch takes only `*.blame` names. On A the files go in with link(2) + unlink from a temp dir on the blame dir's file system: link never replaces a file.
5. Pulled files keep the extra's mtime (the time it finished them). R8 then sees the row's real output rate; its restarts of the row (more jobs) also drop pulled files from A's list. rs-pull takes R8's `rebalance.lock` for its restart.
6. One type pair per launch (`c7a/m7a` default, or `c6a/m6a`): the parts are equal, so a mix lets the slow machines set the end. L1 refuses a mix.
7. Gate files: 30 files that A finished **on this machine** (mtime after boot), not PLAIN-BLAME, spread over the sizes; compared byte for byte (`cmp`).

## Files
| file | where | what |
|---|---|---|
| E0-probe-a.sh | A, read-only | step-7 process (jobs, env names, CREGIT_C100_LIMIT), git/perl binaries + versions, cregit HEAD/blobs, clone size, free disk |
| E1-export-a.sh | A, root | order + split + gate, pack (clone streamed to S3, no copy on A's disks) and upload `input/`, SHA256SUMS last, size read-back |
| P1-install-a.sh | A, root | rs-pull.py/rs-pull + rs-pull.timer (10 min); runs it once |
| P2-check-a.sh | A, read-only | pull log, batches per part, files pulled per hour, part status, left files, ETA |
| P3-restart-a.sh | A, root | one rs-pull run with FORCE_RESTART=1 (the end restart by hand) |
| X1-control-a.sh | A, root | MODE=stop/unstop (S3 control/STOP: extras end), hold/unhold (rs-pull does nothing) |
| P9-off-a.sh | A, root | disable rs-pull.timer after the row passed step 7 |
| L1-launch-rs.sh | this machine | one spot fleet per part (KS), Run=rust-split, Part=k, refuse list, quota check, MAX_TOTAL_PRICE, ROOT_GB; DRY_RUN=1 |
| ssm-rs.sh | this machine | ssm.sh for an extra (tags checked), adds RS_PART/RS_NAME (+ RS_JOBS, RS_MARGIN, ...) |
| S1-setup-start.sh | extra, root | packages, input (sha256), clone stream (sha256), checks, rs.env, units rs-upload + rs-run, start |
| S2-check.sh | extra, read-only | phase, gate, progress, files per hour, batches, PLAIN-BLAME, ETA of the part |
| C1-status.sh | this machine, read-only | instances, per part: batches in S3, status age, markers (s3 ls only) |
| lib/ | | rs_order.pl (copy of blameRepoFiles.pl 65-118), rs_split.py, rs_blame.pl (driver), rs_gate.sh, rs_batch.sh, rs-run.sh, rs-upload.sh, rs_pull.py, rs-pull.sh |
| src/*.body, render.sh | | E1/P1/S1 are rendered with the lib files embedded (gzip + base64 + sha256 check) |
| test/T1-all.sh | this machine | all checks (below) |

## Launch sequence (main session)
Run from `~/s3-work/dataset-x1k`. A = `I=${RUNNER_EC2_X1K_LONG_A4} bash scripts/a/ssm-a.sh`.
1. `bash rust-split/test/T1-all.sh` -> `T1 ALL PASS`.
2. `$A rust-split/E0-probe-a.sh 900` (read-only): note git/perl paths, clone size, free disk.
3. `$A rust-split/E1-export-a.sh 7200`: needs `check: OK`, `read-back: ... sizes equal`, `E1 done`; note the ROOT_GB line. (N, HEAD_FILES, GATE_N: edit the defaults in the script if needed; ssm passes no environment.)
4. `$A rust-split/P1-install-a.sh 900`: timer active; first block shows `listing: 0 keys`, `a-pos: <n> (sent)`, `decide: WAIT only 0 ...`.
5. `DRY_RUN=1 bash rust-split/L1-launch-rs.sh` (add `ROOT_GB=<n>` if E1 asked for more than 200), then `bash rust-split/L1-launch-rs.sh` (KS="1 2 3 4 5", TYPES, MAX_TOTAL_PRICE=5.00). It stops at the first part it cannot launch; launch the rest later with KS="...".
6. Per machine (about 2 min after launch, when SSM is online): `I=<id> bash rust-split/ssm-rs.sh rust-split/S1-setup-start.sh 3600`. Needs `sha256 ok`, `repo: HEAD as A`, `cregit: 57551d7`, `tools: ...`, `units: rs-upload active, rs-run active; phase gate`.
7. After 15-60 min: `I=<id> bash rust-split/ssm-rs.sh rust-split/S2-check.sh 600` -> `gate: 30 equal, 0 not equal of 30`, phase run. A failed gate writes `out/<k>/GATE-FAILED` and the machine powers off after 1 h: stop and look; do not go on.
8. Watch: `bash rust-split/C1-status.sh`, `$A rust-split/P2-check-a.sh 900`, `$A scripts/a/D9-rebalance-log.sh`.
9. End (automatic): extras write DONE and power off; rs-pull pulls the last batches and restarts the row once (`restart OK` in P2). If it waits for a part that is gone: `$A rust-split/P3-restart-a.sh 900`. A spot reclaim: `REPLACE=1 KS=<k> bash rust-split/L1-launch-rs.sh`, then S1 on the new machine (it resumes from the batches in S3), or let A do the rest after the end restart.
10. After the row passed step 7: `$A rust-split/P9-off-a.sh`. Add the PLAIN-BLAME lines of `out/<k>/plainblame.log` to the PLAIN-BLAME records of the row (they are not in A's pipeline.log). The batches in S3 hold blame data: delete `rust-split/` when the row is in the dataset (user decision).

Stop at any time: `X1-control-a.sh` with MODE=stop (extras end cleanly, A continues alone; then P3 for the restart), or MODE=hold (rs-pull inert). Terminating an extra loses only its unsent files (A redoes them).

## Expected time and cost (N = 5, 184 jobs each, A 88 jobs; 229,700 files left x 480 CPU s = 30,600 CPU h)
| types | files/h (A + extras) | blame | wall incl. setup and end | machine-h | cost at the spot price of 2026-10-21 20:00 UTC | at 2.2-4.5 $/h |
|---|---|---|---|---|---|---|
| c6a/m6a (480 s/file as A) | 660 + 6,900 | 30 h | about 33 h | 162 | $363-528 (2.24-3.26 $/h) | $356-729 |
| c7a/m7a (1.3-1.5x per vCPU, an estimate: one core per vCPU, Zen 4) | 660 + 9,000-10,400 | 21-24 h | about 23-26 h | 114-129 | $385-577 (3.37-4.46 $/h) | $251-582 |
Plus root disks (below $15) and S3 requests (below $2). A alone: 348 h (14.5 days) for this row; A costs $230/day (on-demand $8.29/h + EBS $1.32/h). Quota: spot vCPU 1,152; in use 96 (v0 machine) + 5 x 192 = 1,056.

## Tests (2026-10-21, this machine; `bash test/T1-all.sh` -> T1 ALL PASS, also with PY=/usr/bin/python3 = 3.9 as on A)
render --check, bash -n, perl -c, compile, shellcheck -S warning (0 warnings), and 34 test cases:
- t_rs.py (25): rs_order.pl gives exactly the start order of the real blameRepoFiles.pl 57551d7 (ties, a quoted non-ASCII name skipped, a done file); split invariants on 6 shapes up to 229,700 rows (no file in two parts, no head file in a part, head + parts = left, every N-th of the tail) and the check finds 3 kinds of errors; A's index from pipeline.log (incremental, truncation); gate pick; the driver (largest index down, skip of done and sent files, the exact argv of blameRepoFiles.pl, at most --jobs at once, STOP, the meeting with A, failures counted); the real formatBlame.pl started by blameRepoFiles.pl and by rs_blame.pl gives equal bytes (-C100 credit of moved lines checked); the gate compare (equal, DIFF, NO-HERE, empty list); batches (only .blame, pending batch resent, upload failure); the pull (no overwrite of A's file, link = same inode, incomplete batch ignored, bad sha256, wrong members, a name outside the part, `..`), the end rule; rs-pull with a fake systemctl (pull, a-pos, one restart, no second one, HOLD, guards, a bad start line -> ALERT and NO_SHUTDOWN kept, AUTO_RESTART=0, not machine A).
- t_extra.py (5): rs-run + rs-upload end to end with the real formatBlame.pl: gate -> blame -> batches -> DONE -> power off; failed gate; resume after a relaunch (sent files skipped, batch numbers go on); STOP; meeting A with NO_SHUTDOWN. The pulled files equal blameRepoFiles.pl output byte for byte.
- t_e1s1.py (4): the rendered E1 on a fake /proc of the running step 7 (no file name and no at sign in its output; SHA256SUMS right; the env has only the blame variables; a second E1 refuses; not in step 7 -> refuses), then the rendered S1 (clone stream + sha256, A's path string, checks; a corrupt clone refused; a part not in the split refused; machine A refused), then rs-run as S1 installed it and the pull.
- L1 DRY_RUN for c7a/m7a, c6a/m6a and ROOT_GB=400: "Request would have succeeded".

## Risks
- The end restart is needed (skip-once). It is automatic (rs-pull, AUTO_RESTART=1) and has a manual way (P3). If it fails (ALERT), A re-blames files the extras did: lost time, never wrong data.
- PLAIN-BLAME is wall time: a file can fall back to plain blame on one machine and not on another (faster 7a: fewer). The extras' lines are in `out/<k>/plainblame.log`, not in A's pipeline.log.
- At the meeting both sides can blame the same file (a-pos is up to about 20 min old): equal bytes, no gap.
- Memory: 184 jobs on 384 GiB (c7a/c6a); A shows about 1.4 GiB per job. S1 caps jobs at (MemTotal - 16) / 1.5 GiB. An out-of-memory git leaves no .blame (A does it after the restart). TYPES="m7a.48xlarge" (768 GiB) if needed.
- A spot reclaim loses the unsent files (at most 10 min) and the running ones; a replacement resumes from S3.
- E1 reads the whole working clone once (tar + zstd -T12, nice) while A blames: some minutes of disk read on volume 2.
- The git/perl binaries of A must exist on the AMI of the extras (the nix store paths); S1 refuses otherwise.
- After an A relaunch (it is on-demand, so unlikely) P1 must be installed again (the units are on A's root disk; the E1 lists stay on /data1).
- A file whose path starts with "-" fails in formatBlame.pl on every machine (known cregit defect); it shows in errors.log.
