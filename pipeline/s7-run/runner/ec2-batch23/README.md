# Batch 23: the DP8L v4 near-miss supplement (prepared 2026-10-11, NOT queued)

The user decided on 2026-10-11 at about 19:00 UTC: "Yes, add them". DP8L v4 also passes the GitHub rows of 3 near-miss classes of the DP8L audit: C (other root name), D (a package file declares a license), E (a license file in a subfolder). Batch 23 holds their 118 layer 1 rows: S 93, M 17, L 8. Built in ${RUNNER_STUDY_REPO} 76aeef8 (s7-run). B = `s3://${RUNNER_BUCKET}`.

Census code: ctp ca113e3, cregit 57551d7 (1f17663 plus the `git blame -C100` time limit of 3600 s per file, then plain blame). Bundle `B/cregit/cregit-57551d7.bundle`, sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e (already in S3 since 20:05 UTC). libexpat gate 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 (unchanged).

## Inputs (`upload/`, 8 files, `SHA256SUMS`)

`manifest.batch23.tsv`, `manifest.batch23.order.tsv`, `project_meta.batch23.json`, `parts.batch23.tsv`, `parts.batch23.assign.tsv`, `manifest.batch23L.tsv`, `project_meta.batch23L.json`, `SHA256SUMS`. They are byte copies of the files in ${RUNNER_STUDY_REPO} s7-run.

## Parts (all on spot b; 4 workers each; predicted, inferred)

User decision 2026-10-11 ~21:05 UTC: all 10 parts go to spot b (${RUNNER_EC2_SPOT_B4}), none to spot a. At 20:16 UTC spot a had 55 parts queued and spot b 21.

`one_half.py batch23 b` (${RUNNER_STUDY_REPO} s7-run) made this change. census-fed-enqueue and restart_spot.sh pick the parts of a half by the first column of `parts.batch23.tsv`, so every row now has half `b`. The former a1-a5 became b6-b10. Their rows do not change; only the "# Part" header line of their part manifests changes. b1-b5 do not change.

| part | projects | predicted work | former part |
|---|---:|---:|---|
| b1 | 4 | 6.8 h | b1 |
| b2 | 7 | 4.4 h | b2 |
| b3 | 16 | 4.2 h | b3 |
| b4 | 12 | 4.2 h | b4 |
| b5 | 18 | 4.2 h | b5 |
| b6 | 4 | 13.4 h (longest project 5.4 h) | a1 |
| b7 | 4 | 5.7 h | a2 |
| b8 | 16 | 4.2 h | a3 |
| b9 | 14 | 4.2 h | a4 |
| b10 | 15 | 4.1 h | a5 |

Total: 110 projects (S 93, M 17), 55.4 h of work. The queue order is b1..b10.

Check (21:05 UTC, a temp feed with only the batch23 line): `restart_spot.sh --remaining a` counts no batch23 work; `--remaining b` counts batch23b1..b10 = 110. So a spot a relaunch does not queue batch 23.

The L rows run as census L23 on the big EC2: `~/s3-work/ec2-L23/README.md`.

## Steps

1. The user runs `bash ~/s3-work/upload-batch23.sh`. It must print `ALL OK`. (Claude's S3 uploads are denied.)
2. `bash ~/s3-work/ec2-batch23/scripts/S1-feed-line.sh`: append the batch23 line of `~/s3-work/ec2-batch6/feed.next.tsv` to `feed.tsv` (commit 57551d7, bundle, sha256, gate 14eb5d72), so that a relaunch queues batch 23 too. It prints the remaining counts of both halves.
3. On spot b ONLY, from `~/s3-work/ec2-batch23/`:
   - `I=${RUNNER_EC2_SPOT_B4} scripts/ssm.sh ~/s3-work/ec2-batch6/scripts/s23-enqueue.sh 900 > out/s23-enqueue-b.out`

   `s23-enqueue.sh` refuses on half a. It sets the workload commit under the feeder lock, then runs `census-fed-enqueue batch23` (it copies `B/batch23/input/`, checks the sha256, derives the 10 part manifests and checks each sha256, and queues the parts at the end of the FIFO queue).
   Check: 10 of 10 "sha256 ok", and the queue ends with `batch23 b10`.
4. If spot b was relaunched, take its new ID from `~/s3-work/census-watchdog/restarts.b`.

## Queue at 20:16 UTC (read-only probe, out/p1-spot-probe-*.out)

- Spot a: 55 parts queued (next batch11 a2; the last is batch22 a2), 9 parts running, 19 of 20 workers in use.
- Spot b: 21 parts queued (next batch18 b3; the last is batch22 b3), 8 parts running.
- On both, the workloads batch19-22 (spot a: batch12-22) are already at 57551d7.

## Files

- `upload/`: the 8 input files.
- `scripts/ssm.sh` (I=<id>; file:// JSON, no base64), `p1-spot-probe.sh` and `p2-spot-probe.sh` (read-only), `S1-feed-line.sh` (local).
- `~/s3-work/ec2-batch6/scripts/s23-enqueue.sh` (next to s21 and s22).
- `out/`: the outputs.
