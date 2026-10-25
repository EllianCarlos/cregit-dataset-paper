# java-split: part of the aws-sdk-java blame on extra on-demand machines (built 2026-10-23, NOT launched)

User decision 2026-10-23: on-demand extra machines for the blame (step 7) of `aws__aws-sdk-java` on machine A
(${RUNNER_EC2_X1K_LONG_A4}, m6a.48xlarge on-demand, Run=x1k-long). The main session launches after review.
This kit is a copy of `../rust-split/` (read its README for the facts of cregit 57551d7 and the design);
only the differences are below. S3 prefix: `s3://${RUNNER_BUCKET}/dataset-x1k/java-split/`
(input/, out/<k>/, control/).

## The row at 2026-10-23 02:00 UTC
- aws-sdk-java: 78,064 files left, 44 jobs, about 1,265 files/h, 125 CPU s per file on A: about 2,714 CPU h,
  about 62 h at 44 jobs.
- awslabs__aws-sdk-rust: 65,370 left, 132 jobs, about 3,870 files/h, about 17 h. R8 never lowers a row's jobs,
  so java keeps 44 jobs until rust leaves step 7; then R8 gives java the free jobs (about 168 of TOTAL 176).
- Layout on A: `/data/x1k-long/aws__aws-sdk-java` is a link to `/data3/x1k/aws__aws-sdk-java` (volume 3,
  scripts/a/R1-setup.sh: `aws__aws-sdk-java 3 44 96GB`). The kit's own dir on A: `/data/x1k-long/java-split`
  (lists, state, logs; as rust-split, on /data1). The pull stage dir: `<row dir>/java-split-stage` on /data3,
  the file system of the blame dir.

## What differs from rust-split
1. The row: P=aws__aws-sdk-java everywhere; volume 3 (jv-pull.service has RequiresMountsFor=/data1 /data3;
   E0 shows /data1 and /data3).
2. The names, so both kits can be installed on A at once: on A `jv-pull.service`, `jv-pull.timer`,
   `/usr/local/bin/jv-pull`, `/usr/local/lib/java-split/`, `/etc/java-split/`, `/data/x1k-long/java-split/`,
   the guard file `~ec2-user/NO_JV_RESTART`; on the extras `jv-run.service`, `jv-upload.service`, `/jv`,
   `/etc/java-split/jv.env`; lib files `jv_*.py|pl|sh`; tags Run=java-split, Name=dataset-java-split-<k>
   (`-<k>-r<n>` for a replacement), Part=<k>. test/t_kits.py checks that no name is in both kits.
3. N=4 parts by default (E1 and jv-pull). On-demand quota L-1216C47A is 1,152 vCPU: A 192 + 4 x 192 = 960.
4. HEAD_FILES=3000 (rust 1500): A starts about 1,265 java files/h, so the head is about 2.4 h of A, as
   rust's head was. MARGIN=600 (rust 300): a-pos can be 20 min old, and A starts about 420 files in 20 min.
5. L1-launch-jv.sh: ON_DEMAND=1 by default (EC2 Fleet type instant, DefaultTargetCapacityType on-demand,
   OnDemandOptions lowest-price with MaxTotalPrice OD_MAX_PRICE=12.00, no SpotOptions); the on-demand vCPU
   check (pending and running on-demand vCPU of the standard families + 192 <= the quota, read with
   service-quotas); TYPES c7a.48xlarge/m7a.48xlarge, all 4 subnets (${RUNNER_AWS_REGION}a-d); price=on-demand in
   instances.txt. The refuse list (L1, ssm-jv.sh, S1) has the rust-split ids plus the 12 rust-split
   extras. ON_DEMAND=0 still gives the spot request.
6. jv-pull refuses a restart (ALERT) when JOBS in run.env is lower than the blame-jobs of the last start line,
   so the end restart can never lower the jobs R8 gave the row.
7. E0 prints the memory of the row's git blame processes (sum, mean, largest): S1 caps the jobs at
   (MemTotal - 16) / MEM_PER_JOB_GIB (1.5) GiB; c7a has 384 GiB (184 jobs need about 2 GiB each at most),
   use TYPES="m7a.48xlarge" if E0 shows a mean above 1.9 GiB.
8. E1 prints the 30 gate sizes (bytes, no names). The gate takes as long as its slowest file.
9. P1 and P2 also print the state of rs-pull.timer and x1k-rebalance.timer, and P2 the JOBS of run.env and
   of the last start line.

Everything else is as in rust-split: E1 export (the files left in blameRepoFiles.pl order, the head for A,
the tail split in N parts, the clone streamed to S3), the 30-file byte gate on each extra, the batches every
10 min, the pull timer on A (no overwrite, link + unlink, the restart under R8's lock), the one automatic
restart of the row at the end (the skip check of cregit 57551d7 runs only at the start of step 7), the stop
and hold controls (X1), S2/C1/P2 checks, P3 (restart by hand), P9 (timer off after the row passed step 7).

## Machine A with both kits and R8
- Timers on A: `rs-pull.timer` (rust-split), `jv-pull.timer` (this kit), `x1k-rebalance.timer` (R8), all
  every 10 min, and the finalize unit `x1k-long-finalize.service`.
- Each pull restarts only its own row (P is fixed in the script). Each pull has its own lock
  (`<kit dir>/state/pull.lock`). Every restart (R8, rs-pull, jv-pull) takes `/data/x1k-long/rebalance.lock`
  with `flock -n`, so two restarts never run at once; the one that finds the lock held waits for its next
  run. R8 holds the lock for its whole run, so its plan and its restarts never mix with a pull restart.
- Jobs: the runner reads JOBS from run.env; only R8 changes run.env (under the lock, while the unit is
  stopped, never lower). The pull restart keeps run.env's JOBS and checks the new start line has
  "blame-jobs <JOBS>,". With the check of item 6 the java restart cannot leave java with fewer jobs.
- R8 sees the pulled files (they keep the extras' mtimes) as output of the row: java's rate looks high and
  its weight low, but R8 never lowers jobs, and after rust leaves step 7 java is the only step-7 row,
  so it still gets the free jobs. An R8 restart of java (more jobs) also drops the pulled files from A's list.
- The finalize unit: both pulls and R8 skip a restart while it is active, and set NO_SHUTDOWN only during
  a restart (removed after, if it was not there before).

### The rust-split pull now (no rust extras, no DONE files)
Every 10 min rs-pull lists rust-split/out/, copies the status.txt files (all older than 40 min, so no part
counts as running), writes rust-split/control/a-pos.txt, and decides. It restarts the rust row only when at
least 100 pulled files lie ahead of A's position and were linked after the rust row's last start. No new
rust batches arrive, and any restart of the rust row (R8 raised it from 88 to 132 jobs, or rs-pull's own end
restart) sets a newer start time, so the decision stays "WAIT only 0 ...". It can never touch the java row,
and its restart would use the shared lock. So it does not have to be paused or turned off for this kit.
- P9-off-a.sh of rust-split cannot turn it off now: it refuses while the rust row is in step 7.
- Optional: hold it (rust-split X1 with MODE=hold: `rust-split/HOLD`, then rs-pull does nothing at all).
  That only makes it quiet; nothing is lost, since no rust extra runs. Send a temporary copy, so the kit
  file stays as it is (ssm passes no environment):
  `sed 's/^MODE=stop$/MODE=hold/' rust-split/X1-control-a.sh > /tmp/X1-rs-hold.sh && $A /tmp/X1-rs-hold.sh 300`.
- Check first with `$A rust-split/P2-check-a.sh 900`: the newest block should say "decide: WAIT", and
  no ALERT. After the rust row passed step 7: `$A rust-split/P9-off-a.sh`.

## Files
As in rust-split, with `rs` -> `jv`: E0-probe-a.sh, E1-export-a.sh, P1-install-a.sh, P2-check-a.sh,
P3-restart-a.sh, X1-control-a.sh, P9-off-a.sh, L1-launch-jv.sh, ssm-jv.sh, S1-setup-start.sh, S2-check.sh,
C1-status.sh, lib/ (jv_order.pl, jv_split.py, jv_blame.pl, jv_gate.sh, jv_batch.sh, jv-run.sh,
jv-upload.sh, jv_pull.py, jv-pull.sh), src/*.body + render.sh (E1, P1, S1 embed the lib files), test/.

## Launch sequence (main session)
Run from `~/s3-work/dataset-x1k`. A = `I=${RUNNER_EC2_X1K_LONG_A4} bash scripts/a/ssm-a.sh`.
1. `AWS_DRY=1 bash java-split/test/T1-all.sh` -> `T1 ALL PASS` (the last step is the real EC2 DryRun).
2. `$A java-split/E0-probe-a.sh 900` (read-only): git/perl paths, clone size, free disk on /data1 and
   /data3, the memory per git blame (above 1.9 GiB mean: TYPES="m7a.48xlarge" in step 5).
3. `$A java-split/E1-export-a.sh 7200`: needs `check: OK`, `read-back: ... sizes equal`, `E1 done`; note the
   `gate sizes` and the `root disk of an extra` lines (ROOT_GB if above 200). N, HEAD_FILES, GATE_N: edit
   the defaults in the script if needed (ssm passes no environment); N cannot change after an extra started.
4. `$A java-split/P1-install-a.sh 900`: jv-pull.timer active; first block `listing: 0 keys`,
   `a-pos: <n> (sent)`, `decide: WAIT only 0 ...`; the timers list shows jv-pull, rs-pull and x1k-rebalance.
5. `DRY_RUN=1 bash java-split/L1-launch-jv.sh` (add `ROOT_GB=<n>` if E1 asked for more than 200), then
   `bash java-split/L1-launch-jv.sh` (KS="1 2 3 4", on-demand). It stops at the first part it cannot
   launch (quota, capacity); launch the rest later with KS="...".
6. Per machine (about 2 min after launch, when SSM is online):
   `I=<id> bash java-split/ssm-jv.sh java-split/S1-setup-start.sh 3600`. Needs `sha256 ok`, `repo: HEAD as A`,
   `cregit: 57551d7`, `tools: ...`, `units: jv-upload active, jv-run active; phase gate`.
7. After 15-60 min: `I=<id> bash java-split/ssm-jv.sh java-split/S2-check.sh 600` ->
   `gate: 30 equal, 0 not equal of 30`, phase run. A failed gate writes `out/<k>/GATE-FAILED` and the
   machine powers off after 1 h: stop and look; do not go on.
8. Watch: `bash java-split/C1-status.sh`, `$A java-split/P2-check-a.sh 900`, `$A scripts/a/D9-rebalance-log.sh`.
9. End (automatic): the extras meet A (met-A) or finish their part, write DONE and power off (on-demand
   with shutdown terminate: they terminate); jv-pull pulls the last batches and restarts the java row once
   (`restart OK` in P2). If it waits for a part that is gone: `$A java-split/P3-restart-a.sh 900`.
   A lost machine: `REPLACE=1 KS=<k> bash java-split/L1-launch-jv.sh`, then S1 on the new one (it resumes
   from the batches in S3), or let A do the rest after the end restart.
10. After the java row passed step 7: `$A java-split/P9-off-a.sh`. Add the PLAIN-BLAME lines of
    `out/<k>/plainblame.log` to the PLAIN-BLAME records of the row. The batches in S3 hold blame data:
    delete `java-split/` when the row is in the dataset (user decision).

Stop at any time: `X1-control-a.sh` with MODE=stop (extras end cleanly, A continues alone; then P3 for the
restart), or MODE=hold (jv-pull inert). Terminating an extra loses only its unsent files (A redoes them).

## Expected time and cost (N = 4, 184 jobs each, A 44 jobs)
Work: about 76,000 files left at E1 (A goes on at 1,265 files/h until then), head 3,000 for A, tail about
73,000 = 4 parts of about 18,250. On a 7a vCPU (one core per vCPU) a java file takes about 85-125 CPU s
(A: 125 s with two threads per core; the tail holds the smaller files): 5,300-7,800 files/h per extra,
21,000-31,000 files/h for 4.

| phase | wall |
|---|---|
| E1 (clone tar + zstd + upload; size not known yet) | 15-40 min |
| P1, L1, S1 (clone download and unpack) | 20-40 min |
| gate (slowest of the 30 files) | 15-45 min |
| blame of the tail | 2.4-3.5 h |
| the last large files near the meeting, last batch, pull, end restart | 0.5-1 h |
| total, E1 start to the end restart | about 4.5-6.5 h |

Machine time: each extra runs from launch to power off, about 3.7-5.8 h: 15-23 machine-h.
Public on-demand price ${RUNNER_AWS_REGION} (aws pricing get-products, effective 2026-10-01): c7a.48xlarge 9.85 $/h,
m7a.48xlarge 11.13 $/h. Lowest-price takes c7a: about $150-230 (m7a: $165-260). Root disks and S3 requests:
below $3.
Without the extras: java at 44 jobs until rust ends (about 17 h, 21,500 files), then about 168 jobs
(about 4,000 files/h, less than linear) for the other 56,500: about 31 h in all. With the extras java's step 7
ends in about 6 h, so A's end is set by rust (about 17 h plus its steps 8-10): A runs about 14 h less
(about $135 at 9.61 $/h with EBS). N=2 would likely end java's step 7 in 7-9 h, also before rust, with less
setup and gate time per machine (about $120-170); the user chose N=4.

## Tests (2026-10-23, this machine; `bash test/T1-all.sh` -> T1 ALL PASS, also with PY=/usr/bin/python3 = 3.9)
render --check, bash -n, perl -c, compile, shellcheck -S warning (0 warnings), and 46 test cases:
- t_jv.py (27): the 25 cases of rust-split's t_rs.py with java names (.java files, 44 jobs, /data3), plus
  jv-pull never lowers the jobs (run.env below the last start line: ALERT, no stop; more jobs in run.env:
  the restart takes them) and jv-pull waits while another process holds rebalance.lock.
- t_extra.py (5) and t_e1s1.py (4): as in rust-split, with the java names.
- t_kits.py (4): the names of the two kits do not collide (units, files, dirs, S3 prefixes, tags, guard file;
  only the runner units, R8's timer, the finalize unit and rebalance.lock are shared; the java kit only reads
  rs-pull.timer); both pulls use their own pull.lock and the same rebalance.lock; both pulls on one fake
  machine A with both rows: each stops and starts only its own row with its own jobs, no second restart;
  while jv-pull restarts java, rs-pull finds the lock held and restarts rust on its next run.
- t_l1.py (6): L1 with a fake aws: the on-demand request (no SpotOptions, lowest-price, 2 types x 4 subnets,
  the tags), DRY_RUN calls create-fleet only with --dry-run, the on-demand quota check (and the read of the
  quota), a launch, a used name, a part with a machine, an id of the refuse list, a type mix, ON_DEMAND=0.
- With AWS_DRY=1: the real EC2 DryRun of L1 part 1 (on-demand): "Request would have succeeded". Done on
  2026-10-23 also for KS="1 2 3 4" and ROOT_GB=400; on-demand vCPU in use 192 of 1152.

## Risks
- The end restart is needed (skip-once). It is automatic (jv-pull, AUTO_RESTART=1) and has a manual way (P3).
  If it fails (ALERT), A re-blames files the extras did: lost time, never wrong data.
- On-demand capacity for 48xlarge may be short in a zone: the fleet tries both types in all 4 subnets;
  L1 stops at the first part with no instance.
- The cost runs until each extra powers off. An extra that hangs (no DONE, no power off) costs about
  10-11 $/h: watch C1 (status.txt age) and stop it by hand if needed.
- Memory: java blame memory per job is not known yet (E0 shows it). An out-of-memory git leaves no .blame
  (A does it after the restart).
- PLAIN-BLAME is wall time: a file can fall back to plain blame on one machine and not on another (7a is
  faster: fewer). A gate file that took close to 3600 s of -C100 on A could fall back on an extra and fail
  the gate (unlikely on the faster 7a). The extras' lines are in `out/<k>/plainblame.log`.
- At the meeting both sides can blame the same file (a-pos is up to about 20 min old): equal bytes, no gap.
- E1 reads the whole working clone once (tar + zstd -T12, nice) while A blames: some minutes of disk read on
  volume 3.
- The git/perl binaries of A must exist on the AMI of the extras (the nix store paths); S1 refuses otherwise.
- After an A relaunch P1 must be installed again (the units are on A's root disk).
- A file whose path starts with "-" fails in formatBlame.pl on every machine (known cregit defect).
