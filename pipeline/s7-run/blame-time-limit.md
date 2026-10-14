# Deploy plan: the blame time limit (not deployed)

`$RUNNER_BUCKET` and `$RUNNER_EC2_*` stand for the bucket and the EC2 ids of the dataset build
(`runner/runner.env`, local only; `runner/runner.env.example` gives the names).

Written 2026-10-11 19:10 UTC. User decision 2026-10-11 16:45 UTC: "Swap now + time limit".
Nothing in this plan ran on an instance. The inventory below comes from read-only SSM
commands at 18:59-19:05 UTC.

## The change

| Code line | Old commit | New commit | Bundle (prerequisite 95cdc88) | Bundle sha256 | libexpat gate |
|---|---|---|---|---|---|
| batches 7-22, L7-20, L22 | 1f17663 | `57551d7ad82a784615c1490623d72cb9dc994ba1` (branch fix/trailers-original-db) | `cregit-57551d7.bundle` | `18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e` | `14eb5d72…b799`, 2,196,248 B (unchanged) |
| batches 1-6, batch5L, batch1rest, batch3 | 95cdc88 | `9ccead6716a619a7e3ddc7bad9234f14deae865c` (branch fix/blame-time-limit-95cdc88) | `cregit-9ccead6.bundle` | `64a4f3f081a91694b1976d531883c6ad547c54116a625d384c0d03785d935e06` | `40511e0d…fc5d`, 2,184,432 B (unchanged) |

- Only one run-time file changes: `blameRepo/formatBlame.pl`. It is the same file on both
  lines: sha256 `788acb9abac05782058c6b0b599b349caf63b85fa49b8375af9240be7bc0b435`. The old
  file on every copy has sha256 prefix `bcb806793422aac1`.
- New behavior: `git blame -C100` gets 3600 s (`CREGIT_C100_LIMIT` or `--c100-limit` changes
  it; 0 = no limit). After the limit, the script kills git and runs `git blame --porcelain`
  with no limit. It prints `PLAIN-BLAME <file> after <N> s of -C100` to STDERR.
- New behavior: if git fails or is killed for another reason, the script writes no `.blame`
  file and exits 1. `blameRepoFiles.pl` prints `Error code [...]`, ends with `Error [N]` and
  exit 1, and step 7 fails. Before, the script wrote an empty `.blame` and exited 0.
- The STDERR line reaches `$WORK/pipeline.log` (`run_pipeline_process.sh` line 855:
  `exec > >(tee -a "$LOG_FILE") 2>&1`) and ctp's copy
  `state/<project>/logs/pipeline-<stamp>.log`. `census-fed-finalize` uploads the `state/*/logs`
  files with each part.
- Upload first (the user runs it): `bash ~/s3-work/upload-cregit-blamelimit.sh`. It must
  print `ALL OK`. The objects go to `s3://$RUNNER_BUCKET/cregit/`.

## What a swap changes and what it does not change

- `blameRepoFiles.pl` starts one `formatBlame.pl` process per file. Perl reads the script file
  when the process starts. Thus a swap changes only the files that start after it.
- A `formatBlame.pl` process that runs at the swap time keeps the old code: no limit and no
  status check. Do NOT kill the `git blame -C100` child of such a process. The old code then
  writes an empty `.blame` and exits 0, and the tokens of that file are lost with no error.
  For such a file, use the OpenVSP procedure (runs log, update 2026-10-11 04:30 UTC).
- Use a temp file and `mv` in the same directory. `rename(2)` is atomic, so a process that
  starts during the swap reads the old file or the new file, never a partial file. Do not use
  `git checkout` in a running copy: git removes and writes the file, and a process that starts
  in that gap fails.
- The swap makes the copy dirty (`git status`: 1 modified file). For a running part, nothing
  checks this again: `census-fed-part-init` runs once per part, before its start.
- The ctp ledger records the cregit commit of a run at its start (HEAD of the copy). After a
  swap in place, the ledger still shows 1f17663 or 95cdc88. The runs log must record the swap
  time of each copy (see "Record").

## Long -C100 blames that run now (19:00 UTC, old code; a swap does not change them)

- spot a: Wilfred__difftastic `tree-sitter-kotlin/src/parser.c` (7 h 22 min);
  alibaba__AliSQL `tpch_constants.hpp`, `tpcds_constants.hpp` (10 h 38 min),
  `tpcds_idx.hpp` (10 h 27 min), `strings/ctype-gb18030.cc` (1 h 25 min);
  phalcon__cphalcon `build/phalcon/phalcon.zep.c` (10 h 30 min; a plain blame of it runs in
  `/w/batch9a5/plain-swap/`, started 18:52 UTC by another session); avrdudes__avrdude
  `src/urbootlist.c` (11 h 28 min); hortonworks__cloudbreak (generated Java, 10 h 57 min);
  apache__hive (thrift `gen-javabean`, 10 h 43 min).
- spot b: MoarVM__MoarVM `src/strings/unicode_db.c` (11 h 02 min); Expensify__Bedrock
  `libstuff/sqlite3.c` (3 h 49 min); KratosMultiphysics__Kratos (4 h 10 min); OpenMPT__openmpt
  `nolace_data.c`, `fargan_data.c` (3 h 00 min); vsg-dev__VulkanSceneGraph
  `pbr_ShaderSet.cpp` (2 h 48 min); u3d-community__U3D `sqlite3.c` (53 min).
- big EC2: none longer than 1 min at 19:00 UTC.

## Step 1: running copies (swap formatBlame.pl in place)

Inventory at 18:59 UTC (active units and their copies):

| Machine | Unit | Copy | HEAD |
|---|---|---|---|
| spot a $RUNNER_EC2_SPOT_A5 | census-fed@batch6a1, batch6a4 | /w/batch6a1/cregit-ec2, /w/batch6a4/cregit-ec2 | 95cdc88 |
| spot a | census-fed@batch8a2, batch9a1, batch9a3, batch9a5 | /w/batch8a2/…, /w/batch9a1/…, /w/batch9a3/…, /w/batch9a5/cregit-ec2 | 1f17663 |
| spot a | census-fed@batch10a1, batch10a2, batch10a3 | /w/batch10a1/…, /w/batch10a2/…, /w/batch10a3/cregit-ec2 | 1f17663 |
| spot a | census-b5@batch1resta2 | /w/batch1resta2/cregit-ec2 | 95cdc88 |
| spot a | census-b3@a2 (brave-core) | /data1/cregit-ec2 | 95cdc88 |
| spot b $RUNNER_EC2_SPOT_B4 | census-fed@batch11b1, batch15b4, batch16b3, batch17b1, batch17b2, batch17b4, batch17b5 | /w/<id>/cregit-ec2 | 1f17663 |
| spot b | census-b5@batch1restb2 | /w/batch1restb2/cregit-ec2 | 95cdc88 |
| big EC2 $RUNNER_EC2_BIG | census-batch5L (firefox) | /b5L/cregit-ec2 | 95cdc88 |
| big EC2 | census-L7-20 | /bL7/cregit-ec2 | 1f17663 |
| big EC2 | census-L22 (gcc, emacs) | /bL22/cregit-ec2 | 1f17663 |

Do not change `/data/cregit-ec2` (the template of new part copies; step 2 gives new parts the
new commit) or the copies of finished parts.

Before the swap, run the inventory again (the set of active units changes). SSM
AWS-RunShellScript, as root, on each machine, with `DIRS` set to the copies of that machine:

```bash
set -uo pipefail
B=s3://$RUNNER_BUCKET/cregit
bf=/data/input/cregit-57551d7.bundle; BSHA=18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e
NEW=788acb9abac05782058c6b0b599b349caf63b85fa49b8375af9240be7bc0b435
DIRS="/w/batch6a1/cregit-ec2 ..."   # the copies of this machine, from the table
[ -f $bf ] && [ "$(sha256sum $bf | cut -d' ' -f1)" = $BSHA ] || { aws s3 cp $B/cregit-57551d7.bundle $bf.tmp --only-show-errors && mv -f $bf.tmp $bf; }
[ "$(sha256sum $bf | cut -d' ' -f1)" = $BSHA ] || { echo "ABORT: bundle sha256"; exit 1; }
chmod 644 $bf
T=$(sudo -u ec2-user mktemp -d)
sudo -u ec2-user bash -c "set -e; git clone -q --no-checkout /data/cregit-ec2 $T/r; git -C $T/r fetch -q $bf '+refs/heads/*:refs/remotes/fed-bundle/*'; git -C $T/r show 57551d7:blameRepo/formatBlame.pl > $T/formatBlame.pl"
[ "$(sha256sum $T/formatBlame.pl | cut -d' ' -f1)" = $NEW ] || { echo "ABORT: new file sha256"; exit 1; }
for D in $DIRS; do
  [ -f $D/blameRepo/formatBlame.pl ] || { echo "SKIP $D: no formatBlame.pl"; continue; }
  install -o ec2-user -g ec2-user -m 755 $T/formatBlame.pl $D/blameRepo/.formatBlame.pl.new \
    && mv -f $D/blameRepo/.formatBlame.pl.new $D/blameRepo/formatBlame.pl \
    && echo "SWAPPED $D $(date -u +%FT%TZ) head=$(sudo -u ec2-user git -C $D rev-parse --short HEAD) sha=$(sha256sum $D/blameRepo/formatBlame.pl | cut -c1-16)"
done
rm -rf $T
```

The `formatBlame.pl` of 57551d7 is the same file as that of 9ccead6, so one bundle serves the
copies of both lines. `/data/cregit-ec2` on spot b and on the big EC2 is at 95cdc88 (the
inventory shows this), so the bundle prerequisite is there. This plan did not check that
`/data/input` exists on the big EC2. If it does not exist, set `bf` to a temp path there.

Check after the swap: every listed copy prints `SWAPPED … sha=788acb9abac05782`. Then the
next files of each running project use the new code. A file with a `-C100` blame longer than
3600 s gives one `PLAIN-BLAME` line in the pipeline log.

## Step 2: parts that start later on the running spots (workload commit)

A new fed part gets its own copy of `/data/cregit-ec2`, and `census-fed-part-init` checks it
out at `CREGIT_COMMIT` of `/etc/cregit-census/fed/wl/<workload>.env` (fetched from the bundle,
sha256-checked). Then `census-fed-check` runs the libexpat gate on the copy. The gate values do
not change, so the check passes with the new commit.

Queue at 19:05 UTC:

- spot a: batch10 (2 parts: a4, a5), batch11-20 (5 each), batch21 (4), batch22 (2). Started
  parts on spot a: batch6a1, 6a4, 7a3, 8a2, 9a1, 9a3, 9a4, 9a5, 10a1, 10a2, 10a3.
- spot b: batch18-21 (5 each), batch22 (3). Started parts on spot b: batch10-17 only.

`census-fed-workload` refuses to change the commit of a workload with started parts. Thus:

- spot a, batch11-22, and spot b, batch18-22: no started part, so the normal command works.
  Run it for each of these workloads, under the feeder lock (`exec 9>$F/lock; flock -w 3000 9`,
  as in `local-a/queue-edit2.ssm.json`):

  ```bash
  /usr/local/bin/census-fed-workload batchN --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 \
    --bundle s3://$RUNNER_BUCKET/cregit/cregit-57551d7.bundle \
    --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e \
    --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
  ```

- spot a, batch10 (a4, a5 queued; a1-a3 started): the command refuses. Decision for the user:
  - A (recommended): under the feeder lock, write `/etc/cregit-census/fed/wl/batch10.env` with
    the same five lines that the command writes (`CREGIT_COMMIT=57551d7…`, `CREGIT_BUNDLE=…`,
    `CREGIT_BUNDLE_SHA256=18b1…`, `WANT_PQ=14eb5d72…`, `WANT_SRCML=dea4467b…`; temp file, then
    `mv`). This bypasses the guard. The started parts a1-a3 keep their own `$id.env` with
    1f17663, and nothing reads the workload file for them again.
  - B: keep batch10 on 1f17663 and swap `formatBlame.pl` in `/w/batch10a4/cregit-ec2` and
    `/w/batch10a5/cregit-ec2` (step 1 commands) after their part-init. This needs a watch for
    the feeder.

## Step 3: a relaunched spot (restart_spot.sh)

A relaunched spot is a new instance from the batch 3 AMI (`/data/cregit-ec2` at 95cdc88, empty
`/etc/cregit-census/fed`). `restart_spot.sh` reads `~/s3-work/ec2-batch6/feed.tsv` and runs
`census-fed-workload` for each line (lines 125-130), so on a new instance there are no started
parts and no refusal. Edit `feed.tsv` on this machine after the upload prints `ALL OK`:

- `batch6`: `base - - -` becomes
  `9ccead6716a619a7e3ddc7bad9234f14deae865c  s3://$RUNNER_BUCKET/cregit/cregit-9ccead6.bundle  64a4f3f081a91694b1976d531883c6ad547c54116a625d384c0d03785d935e06  40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d`
  (tab-separated; the gate value of `--base`).
- `batch7` to `batch22`: `1f176633675eb836e322bf66bcf87343e98c98e1  …/cregit-1f17663.bundle  a827082e…`
  becomes `57551d7ad82a784615c1490623d72cb9dc994ba1  s3://$RUNNER_BUCKET/cregit/cregit-57551d7.bundle  18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e`;
  the gate column `14eb5d72…b799` does not change.

The b3 part (batch3) and the b5 parts (batch5, batch1rest) of a relaunched spot use the AMI
copy at 95cdc88 with no bundle (`census-b5-parts-init`). They get the old `formatBlame.pl`.
To give them the new file, run the step 1 commands on their copies after `restart_spot.sh`
ends (or add the swap to `s5-relaunch-<x>.sh`). This is open.

## Record

- After step 1: append to `runs-20261009.md` one line per copy with the `SWAPPED` time, and
  the files that ran at the swap time (they keep the old code). The ledger rows of these runs
  show the old commit. The swap time tells which files had the new code: files that started
  after it.
- After step 2 and step 3: the ledger rows of new runs show 57551d7 or 9ccead6 (ctp reads the
  copy HEAD), so they need no extra record.
- For the dataset notes (LIMITATIONS): the files with a `PLAIN-BLAME` line have blame without
  copy detection. Find them with `grep -h '^PLAIN-BLAME' state/*/logs/pipeline-*.log` in the
  uploaded ctp state of each part.
- 2026-10-14: cregit 23e4ccb (branch fix/blame-exit128-fallback, on 57551d7) also uses plain blame
  after a `-C100` git exit 128, and prints `PLAIN-BLAME <file> after git exit 128 of -C100`. Cause:
  git dies with "unable to generate diff" when a commit moves a blob over 1 GiB (xdiff limit). Only
  census-local-d runs 23e4ccb (libexpat gate 14eb5d72 unchanged; formatBlame.t 46 tests).
- Plain-blame files for LIMITATIONS, reason "git exit 128 of -C100 (moved blob > 1 GiB)":
  gitlab.inria.fr__cedar__connectionlens `core/src/main/java/fr/inria/cedar/connectionlens/extraction/FlairNERExtractor.java`
  and `core/src/main/java/fr/inria/cedar/connectionlens/extraction/EntityExtractor.java`.

## Risks

- A git that the kernel kills for memory now fails step 7 of the project (before: silent
  loss). The project then fails in the census and needs a rerun. A rerun of step 7 blames only
  the files with no `.blame`, because the new code writes none for a failed file.
- Plain blame of a huge file needs memory too (4.5 M lines took 164 s on the big EC2). It has
  no limit.
- The limit counts from the start of each `-C100` process. With `--jobs=4`, four huge files
  can each use 3600 s before plain blame starts.
