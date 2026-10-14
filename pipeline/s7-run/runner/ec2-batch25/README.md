# Batch 25: the GitLab layer 1 rows on spot a (prepared 2026-10-14, NOT queued)

User decision 2026-10-14 ~01:00 UTC: "adding another batch is the way to go" + "1" = into dataset v1 as batch 25. The rows come from the GitLab pool extension (${RUNNER_STUDY_REPO} `dataset-selection/s2-pool/gitlab/`, README.md there). B = `s3://${RUNNER_BUCKET}`.

Census code: ctp ca113e3, cregit 57551d7 (bundle `B/cregit/cregit-57551d7.bundle`, sha256 18b1bf1c…, in S3 since 2026-10-11), libexpat gate 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 (unchanged).

## Inputs (`upload/`, 5 files with `SHA256SUMS`)

`manifest.batch25.tsv` (ec96e8f8…), `project_meta.batch25.json` (ef49e69e…, with the batch 25 labels), `parts.batch25.tsv` (7a03fe77…), `parts.batch25.assign.tsv` (6ceeb418…). Byte copies of the files in ${RUNNER_STUDY_REPO} `s7-run/`. `record/` keeps the part manifests, `manifest.batch25.order.tsv`, `labels.batch25.csv` and `predicted_hours.txt`.

## Parts (spot half a only; predicted hours are inferred, split_batchN.py fit)

| part | workers | rows | predicted work |
|---|---:|---:|---:|
| a1 | 4 | 8 (S 5, M 3) | 3.4 h |
| a2 | 4 | 13 (S 12, M 1) | 2.6 h |
| a3 | 4 | 16 (S 16) | 2.8 h |
| a4 | 4 | 12 (S 12) | 2.7 h |
| a5 | 1 | 1 (L: mesa/mesa, 231,435 commits) | 5.1 h |

Total 50 rows, 16.6 h of predicted work. The fit is off by up to 3 times for L rows, so mesa can take 15 h or more.

**Why mesa is a spot part, not an L census.** The big EC2 is full until about 2026-10-15/16 (L7-20 kernels, L23, L1r). Mesa is one L row with a small tree (tokenizable 165 MB at the pinned commit). A part of 1 worker on spot a has its own 1200 G image. A spot reclaim restarts it from the beginning.

**Half a.** `split_batchN.py 25 --parts-per-half 2`, then `one_half.py batch25 a` (b1, b2 became a3, a4), then part a5 (1 worker). `restart_spot.sh --remaining a` with a temp feed of only the batch25 line counts batch25a1-a5 = 50; `--remaining b` counts 0.

## Steps (in this order)

1. The user runs `! bash ~/s3-work/upload-batch25.sh`. It must print `ALL OK`. It refuses if `B/batch25/input/` exists.
2. Run `bash ~/s3-work/ec2-batch25/scripts/S1-feed-line.sh`. It adds the batch25 line of `feed.next.tsv` to `feed.tsv`, so a relaunch of spot a queues the parts again.
3. Take the id of spot a from the last `a=` line of `~/s3-work/ec2-batch3/instances.txt` (${RUNNER_EC2_SPOT_A6} at 2026-10-14 02:00 UTC).
4. Run `cd ~/s3-work/ec2-batch23/scripts && I=${RUNNER_EC2_SPOT_A6} bash ssm.sh ~/s3-work/ec2-batch6/scripts/s25-enqueue.sh 900 > ~/s3-work/ec2-batch25/out/s25-enqueue-a.out`. It refuses on half b. It sets the batch25 commit under the feeder lock, then queues a1-a5 at the end of the queue.
5. Check `/data/logs/fed-feeder.log` on spot a and `feed/a/live/progress.txt`.

## Risks

- A spot reclaim loses the rows in progress; a relaunch queues again only the rows without `done/OK`.
- The rows are on hosts that are new to the census (gitlab.inria.fr, gitlab.com, gitlab.archlinux.org, git.adelielinux.org): a host can refuse many clones (Eclipse gave HTTP 429 before).
