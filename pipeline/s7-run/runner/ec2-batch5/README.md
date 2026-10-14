# Census batch 5 and batch 1 rest on EC2 (2026-10-09)

The user approved this at about 14:36 UTC. The main session then changed the split at about 15:00 UTC:
about 20 new workers per spot instance. Account ${RUNNER_AWS_ACCOUNT}, ${RUNNER_AWS_REGION}, profile `${RUNNER_AWS_PROFILE}`.
Bucket `s3://${RUNNER_BUCKET}` (B below).

Run `export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""` before every command,
because the shell's default profile belongs to another account.

## Workloads

- **batch5.** Rows 657-820 of `frame.layer1.csv` (`rows[4*164:5*164]`): 164 projects, S 143, M 19, L 2.
- **batch1rest.** The batch 1 projects that did not finish locally: 113 projects, S 94, M 16, L 3.
  - Left out: the 49 finished ones (`batch1-finished-20261009.txt`) and SAP__project-foxhound and
    wolfpld__tracy, which finish locally.
  - "Finished" is measured: the last ledger row says done, validate and join are ok, and the name is
    in the `joined` table of ctp.duckdb.
  - Same rows and pins as batch 1, but with the new code: cregit 95cdc88, ctp ca113e3.

The manifests are in ${RUNNER_STUDY_REPO} `dataset-selection/s7-run`:
- `build_run.sh` builds batch5, and `split_batch5.py` builds the rest.
- Commit 3ceea81 has the workloads; commit 9d6d556 has the 10-part split, which supersedes the 8-part split of 3ceea81.
- The inputs uploaded to `B/batch5/input/` are the 11 objects of `upload/`, with SHA256SUMS. The user ran the upload at 16:21 UTC.
- The spot instances derive their part manifests themselves: `census-b5-derive` is a copy of
  `split_batch5.py --derive`. Each sha256 must equal `parts.tsv`; all 10 were equal on both instances.

## Where it runs (measured, started 16:38:55 and 16:43:07 UTC)

| machine | census | parts (projects) | workers | filesystem |
|---|---|---|---|---|
| spot a ${RUNNER_EC2_SPOT_A2} (i4i.24xlarge) | census-b5@&lt;id&gt; | batch5a1 (25), batch5a2 (26), batch5a3 (28), batch1resta1 (27), batch1resta2 (27) | 4 each = 20 | images on /data1, /data3, /data5, /data6, /data2 |
| spot b ${RUNNER_EC2_SPOT_B2} (i4i.24xlarge) | census-b5@&lt;id&gt; | batch5b1 (27), batch5b2 (28), batch5b3 (28), batch1restb1 (28), batch1restb2 (28) | 4 each = 20 | 5 images on the RAID0 /data |
| big EC2 ${RUNNER_EC2_BIG} (m6id.24xlarge) | census-batch5L | 5 L: oran-linux, linux-imx, firefox, Bforartists, void-packages | 5 | /data/loop/b5L.img (2500G) at /b5L |

- The S+M parts are balanced by predicted time; each part is in u order.
- The predictor is a log-linear fit of duration on commits and tok_bytes over 354 finished EC2 projects, R² 0.73. Its predictions are inferred:
  - S+M: 2.8-3.0 h of work per worker.
  - L: oran-linux 35.7 h, linux-imx 31.6 h, firefox 25.5 h, Bforartists 6.1 h, void-packages 0.3 h.

**Each spot part `<id>`** (for example batch5a1, batch1restb2) has:
- `/etc/cregit-census/s5/<id>.env` and `<id>.cfg`;
- its own sparse loop XFS image `<host>/loop/<id>.img` (1200G), mounted at `/w/<id>`. That is its own superblock and so its own rename lock (fsid 70000000000..70400000000);
- its own ctp clone `/w/<id>/ctp` (ca113e3);
- its own cregit copy `/w/<id>/cregit-ec2`, whose path was fixed before the start, with an empty `tokenizeByBlobId/build`;
- its output `/w/<id>/census-2026-10-<workload>` and its log `/data/logs/b5-<id>.log`.

The census flags are `--workers 4 --retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4
--memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300`, and every unit has `OOMPolicy=continue`.

**batch5L** has its ctp clone at /b5L/ctp, its cregit copy at /b5L/cregit-ec2, its output at
/b5L/census-2026-10-batch5L and its log at /data/logs/batch5L.log. It uses the same flags with
`--workers 5` and `OOMPolicy=continue`.

## Identity checks (measured)

| copy | libsrcml.so.1.1.0 | libexpat Parquet | time |
|---|---|---|---|
| spot a /w/batch5a1/cregit-ec2 | dea4467b…55f3 | 40511e0d…fc5d | 136 s, 16:37:40 |
| spot b /w/batch5b1/cregit-ec2 | dea4467b…55f3 | 40511e0d…fc5d | 135 s, 16:37:39 |
| big EC2 /b5L/cregit-ec2 | dea4467b…55f3 | 40511e0d…fc5d | 239 s, 16:42 |

- The blobExec jar sha256 is 3daa1201… in /data/cregit-ec2 and in every copy.
- The copies are clean at 95cdc88.
- On the big EC2, `diff -rq` against /data/cregit-ec2 (ignoring build/ and .devenv) gives 1 line, `.git/index`, as in batch 4.

## S3

- **Spot parts:**
  - `B/<workload>/<part>/done/<project>/` holds the Parquet, .validated, state, logs and a ledger snapshot, plus `OK`. census-b5-upload writes them every minute.
  - `B/<workload>/<part>/live/` holds `progress.txt`, the combined view of the instance (the same file in every part of that instance), plus `steps.txt`, `<id>.log.tail`, `ledger.jsonl` and `system.txt`. census-b5-live writes them every 10 min.
  - The first line of `progress.txt` is `as of <ts>  census-b5 on <iid> (spot <x>): active|finalized|stopped ( <id>=<state> ... )  finalize=..  batch3=..`.
  - `B/<workload>/<part>/final/<instance-id>/` gets `DONE`. `B/<workload>/<part>/final/DONE` is written once every project of the part has OK.
- **batch5L:** `B/batch5L/live/` and `B/batch5L/final/`, both written as in batch 4.
- **Test objects.** Kept so the tests can be traced:
  - the dry runs `B/<workload>/<part>/dryrun/<iid>/` and `B/batch5L/dryrun/`;
  - the fake DONEs `B/s5test/<iid>/...`;
  - the fake-notice files `INTERRUPTED.test` and `ledger.test.jsonl` in the parts' live/.

Watch:

    aws s3 cp s3://${RUNNER_BUCKET}/batch5/a1/live/progress.txt - | head -40   # spot a, all 5 parts
    aws s3 cp s3://${RUNNER_BUCKET}/batch5/b1/live/progress.txt - | head -40   # spot b
    aws s3 cp s3://${RUNNER_BUCKET}/batch5L/live/progress.txt -
    ${RUNNER_PROJECTS_TILDE}/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection/s7-run/status_all.sh short
    ~/s3-work/ec2-batch3/restart_spot.sh --remaining a    # projects without done/OK, per workload

## Termination rule on the spot instances

A spot instance terminates (shutdown, with shutdown behavior terminate) only when EVERY census on
it has finalized.

**Which censuses run there.** They are listed in `/etc/cregit-census/censuses`; both instances have `b3 b5`. `/usr/local/bin/census-spot-decide` checks them:
- **b3:** no `census-b3@<part>` is active, and `B/batch3/<x>/final/<iid>/DONE` exists.
- **b5:** no `census-b5@<id>` is active, and `B/<wl>/<part>/final/<iid>/DONE` exists for all 5 parts.

**Who decides.**
- `census-b5-finalize` waits for all 5 parts, copies and checks each part, writes the DONEs, then asks census-spot-decide.
- The patched `census-b3-finalize` asks the same after its DONE. Its only changes are the decide call before `shutdown` and `--decide-only`. The original is kept as `/usr/local/bin/census-b3-finalize.orig-b3only` and `~/s3-work/ec2-batch3/scripts/remote-spot/census-b3-finalize.orig-b3only`.
- Each finalize writes its own DONE before it asks, so only the last one terminates the instance.

**Guards kept.** There is no shutdown:
- after a failed copy;
- with `--dry-run`;
- if `/home/ec2-user/NO_SHUTDOWN` exists;
- for b3, if its longest part ran < 1 h;
- for b5, if its longest part ran < 1 h and no project of this instance reached done/OK.

**After a real spot notice,** both finalizes copy nothing.

**Spot a, old finalize.** The batch 3 finalize had been waiting since 13:17 UTC with the OLD script (pid 230769, script inode deleted). It would have terminated the instance as soon as NO_SHUTDOWN was gone. At 16:41 it was stopped while it was in its wait loop: its child was `sleep`, and a2 and a4 were still active. When a2 or a4 ends, the new script runs. Then NO_SHUTDOWN was removed: on a at 16:41:25 and on b at 16:40:11 (measured).

Tests, 16:38-16:41 UTC, on both instances. Nothing terminated.

| test | case | result (a and b) |
|---|---|---|
| T1 | real state, censuses=b3 | rc 1, census-b3@a2 / @b active |
| T2 | b3+b5, no units, no DONE (fake prefix) | rc 1, b3 DONE missing |
| T3 | only b3 DONE | rc 1, b5 DONE missing |
| T4 | every DONE, no units | rc 0 |
| T5 | every DONE, real units | rc 1 (b3 active) |
| T6 | unknown census word | rc 2 |
| T7, T10 | `census-b3-finalize --decide-only` | no termination |
| T8, T9, T11 | real state after the start; `census-b5-finalize --decide-only` | rc 1, no termination |
| dry run | `census-b5-finalize --dry-run` | 5 parts copied to dryrun/, check ok each, "no shutdown" |
| fake notice | `/run/census-b5-fake-spot-notice` | handled, 5 test STOP files in /run, none in the clones, INTERRUPTED.test in live/ |

## Spot interruption and restart (all workloads)

**On a notice.**
- `census-b5-watch` (IMDSv2 every 5 s) writes STOP into the 5 clones, INTERRUPTED and the ledger into each part's live/, and runs one upload pass.
- `census-b3-watch` does the same for batch 3.

**What a relaunch does.** `~/s3-work/ec2-batch3/restart_spot.sh [--remaining|--dry-run] a|b` (generalised; the old version is kept as `restart_spot.sh.orig-b3only`):
1. It counts each workload's share minus done/OK: b3 from `upload/manifest.batch3<x>.tsv`, b5 from this directory's `upload/parts.tsv` and `parts.assign.tsv`.
2. If nothing remains it exits 0, and it refuses while an instance with the tag is up.
3. Otherwise it launches with `launch_fleet.sh` and, in this order:
   - runs restore-<x>.sh (layout, inputs, the AMI cregit and the batch 3 scripts);
   - installs `scripts/s5-files-1.sh` and `-2.sh`;
   - only if b3 has work left: runs `gate-<x>.sh` (censuses += b3, then census-b3-parts-init, its check and its start);
   - only if b5 has work left: runs `scripts/s5-relaunch-<x>.sh`, which does census-b5-prep (run manifests minus done/OK), parts-init (new images, clones and copies), census-b5-check (libexpat on one new copy, as a gate) and census-b5-start.

**Watchdog.** The local watchdog relaunches a half when `--remaining` reports work left and no instance exists. The cap stays at 3 restarts per half (`restarts.a`, `restarts.b`).

Tests with stubs (a fake `aws` that only serves canned S3 listings, plus stub `launch_fleet.sh` and `ssm.sh`), 16:42-16:45 UTC. Nothing was launched or terminated.

| test | case | result |
|---|---|---|
| R1 | --remaining, 78/80 b3 done, 2 batch5a1 done | b3 2, b5 23+26+28+27+27, total 133 |
| R2 | an instance is up | refuses, rc 1 |
| R3 | dry run, both have work left | plan restore -> s5-files -> gate -> s5-relaunch |
| R5 | b3 complete | plan without the gate |
| R4 | every workload complete | "nothing to relaunch", rc 0, no launch |
| R6 | full path, b3 complete | launch, restore, s5-files-1/2, s5-relaunch-a; no gate; 0 refused aws calls |
| R7 | full path, both | as R6 plus gate-a (censuses += b3 first) |
| W1-W5 | watchdog: half done; lost half (restart 1 of 3, counter 1); counter 3 (cap alert, no restart); b5 "stopped" (alert); live view from an older instance (logged) | all as expected |

## batch5L on the big EC2: power-off rule and guard

- **census-other-done** now lists batch2, batch3L, batch4 and batch5L. The interface is unchanged, plus `batch5L`. The batch 4 version is kept as `/usr/local/bin/census-other-done.orig-3census`. `census-batch5L-finalize`, made from census-batch4-finalize, asks `census-other-done batch5L`.
- **The guard.** `census-batch4-guard` also runs fstrim on /b5L. Below 800 GiB free on /data it writes STOP into /b5L/ctp and `batch5L/live/GUARD`. The original is kept as `.orig-b4`. The guard only stops new starts: all 5 L projects started at once.
- **daemon-reload** was run only after NeedDaemonReload=no for all 14 existing census units. The MainPID and start time of census-batch2, census-batch3L and census-batch4p1-3 were the same before the reload, after it, and after the start (measured).

Tests at 16:42-16:43 UTC. Nothing powered off.

| test | case | result |
|---|---|---|
| T1 | each of batch2, batch3L, batch4 and batch5L, real state | rc 1 |
| T2 | batch4 with batch2 and 3L faked done | rc 1, batch5L/final/DONE missing (the new rule) |
| T3 | batch4 with 2, 3L and 5L faked done | rc 0 |
| T4 | batch5L with 2, 3L and 4 faked done | rc 0 |
| T5 | batch2 with 3L and 4 faked done | rc 1 (5L missing) |
| T6 | bad argument | rc 2 |
| T7 | `--decide-only` of the 4 finalizes | no power-off |
| T8 | guard real run | /data 4466G free; b5L image 2G |
| dry run | `census-batch5L-finalize --dry-run` on the check output | 20 objects in batch5L/dryrun/, check ok, DONE, no power-off |

## Stop

All via SSM: `I=<id> scripts/ssm.sh <script>`.
- **One spot part:** `touch /w/<id>/ctp/STOP`. **All spot parts:** `for d in /w/*/ctp; do touch $d/STOP; done`.
- **batch5L:** `touch /b5L/ctp/STOP`.
- **Keep an instance up after its finalizes:** `touch /home/ec2-user/NO_SHUTDOWN`.

## Costs (inferred)

- **Spot instances.** Each i4i.24xlarge spot instance costs about $2.56/h and was running for the batch 3 tails anyway. The new parts keep both up for about 3-5 h more; the longest predicted M project is 5 h. That is about $15-26 per instance, $30-50 for both.
- **Big EC2.** The m6id.24xlarge costs about $5.70/h on demand. batch5L extends its life only if it ends after batch 2, 3L and 4. If oran-linux (35.7 h predicted, a weak prediction for L) is last, that is up to about $100-200 more.
- **S3 and root volumes** are small.

## Open risks

- **Load.** It was about 250 on 96 vCPU on both spot instances right after the start (clones and tokenizers, measured 16:41) and 123 on the big EC2. Watch the step times.
- **Memory on the big EC2.** MemAvailable was 243 GiB before batch5L. Five L projects at once may need 100-200 GiB (inferred). OOMPolicy=continue fails only the project that is killed, and a retry follows.
- **Disk on the big EC2.** The disk floor only gates starts. The inferred peak of the 5 L projects is about 1.4 TB on /b5L, and /data had 4463G free.
- **Spot finalize failures.** If a spot finalize fails, the instance stays up. The watchdog then alerts on a "stopped" line and the session must look.
- **Projects that keep failing.** A project that fails in every attempt can cause up to 3 relaunches of a half; that is the cap.
- **Relaunches on other instance types.** A relaunch on m5d or m5dn (900 GB disks) sizes the images to 90% of the host disk shared among the images on it.

## Files

- `upload/`: the 11 staged inputs. `upload-superseded-8parts/`: the first staged set, never uploaded.
- `scripts/remote-spot/`: the spot files: `census-b5-*`, `census-spot-decide`, the patched `census-b3-finalize` and the units.
  - `scripts/gen-s5-files.sh` builds `s5-files-1.sh` and `s5-files-2.sh` from them.
- `scripts/remote-L/`: the batch5L files and the new census-other-done and guard.
- `scripts/` SSM steps:
  - spot: s1-probe, s2-pre-<x> (checks), s5-files-1/2, s2-post-<x> (reload, prep, parts, check), s3-start-<x> (tests and start), s4-a-stopfin (old finalize on a), s5-relaunch (for restart_spot.sh);
  - big EC2: e1-probe, L1-setup, L2-install.
- `out/`: the outputs of each step.
