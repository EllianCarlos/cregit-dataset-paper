# Batch 26: gitlab.com/muttmua/mutt on spot a (prepared 2026-10-14, NOT queued)

User decision 2026-10-14 ~16:40 UTC, verbatim: "yes to mutt" (to: "Should mutt get the same license exception as GitHub rows and enter v1?"). The DP8L v4 near-miss classes C, D and E now pass GitLab rows too. mutt is class C (root `COPYRIGHT`, `GPL`); mesa/demos is class H and stays out (${RUNNER_STUDY_REPO} `dataset-selection/s2-pool/gitlab/near_miss.tsv`, README.md fourth round). B = `s3://${RUNNER_BUCKET}`.

Census code: ctp as batch 25, cregit 57551d7 (bundle `B/cregit/cregit-57551d7.bundle`, sha256 18b1bf1c…), libexpat gate 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 (unchanged).

## Inputs (`upload/`, 5 files with `SHA256SUMS`)

| file | sha256 |
|---|---|
| `manifest.batch26.tsv` | 52310bb9c195798851302c67ecb6ead376f714659e54b570261363ac4b5aebf0 |
| `project_meta.batch26.json` | 2642d1873361e74a1911df38210072ecd2ce0fbf916fa7bf87e1d87c564fac18 |
| `parts.batch26.tsv` | 2c86b5f7ec3a8b71e6e0af145c2d65fbb01b838102483eae00e3a8c65db6cd96 |
| `parts.batch26.assign.tsv` | 48782e5d3d65ea8a7483c07a9a5dfff5efcc1cce1bedcde8aa561a152aebbc11 |

Byte copies of the files in ${RUNNER_STUDY_REPO} `s7-run/`. `record/` keeps `manifest.batch26a1.tsv` (af0fae03…), `manifest.batch26.order.tsv`, `frame.batch26.csv`, `labels.batch26.csv` and `near_miss.tsv`.

## Part

| part | workers | rows | predicted work |
|---|---:|---:|---:|
| a1 | 1 | 1 (S: gitlab.com__muttmua__mutt, 8,687 commits, pinned 844fcfe7861631359ee789e4231d322144a1bd3b) | 0.1 h (inferred, split_batchN.py fit) |

`parts_batch26.py` writes the part (split_batchN.py would give an empty part for one row). `split_batchN.py --derive` rebuilds `manifest.batch26a1.tsv` byte for byte (checked 2026-10-14).

## Steps (in this order)

1. The user runs `! bash ~/s3-work/upload-batch26.sh`. It must print `ALL OK`. It refuses if `B/batch26/input/` exists.
2. Run `bash ~/s3-work/ec2-batch26/scripts/S1-feed-line.sh`. It adds the batch26 line of `feed.next.tsv` to `feed.tsv`, so a relaunch of spot a queues the part again.
3. Take the id of spot a from the last `a=` line of `~/s3-work/ec2-batch3/instances.txt` (${RUNNER_EC2_SPOT_A6} at 2026-10-14 16:40 UTC).
4. Run `cd ~/s3-work/ec2-batch23/scripts && I=${RUNNER_EC2_SPOT_A6} bash ssm.sh ~/s3-work/ec2-batch6/scripts/s26-enqueue.sh 900 > ~/s3-work/ec2-batch26/out/s26-enqueue-a.out`. It refuses on half b. It sets the batch26 commit under the feeder lock, then queues a1 at the end of the queue.
5. Check `/data/logs/fed-feeder.log` on spot a and `feed/a/live/progress.txt`.

## Risks

- A spot reclaim loses the row in progress; a relaunch queues it again if it has no `done/OK`.
- Spot a stops itself when its fed queue is empty. Queue the part before its 4 long rows end.
