# Batch 24: the not-started L7-20b rows on spot b (2026-10-13)

User decision 2026-10-13 ~12:35 UTC: move the L7-20b rows that had not started to spot b. At 12:16 UTC spot b used 3 of its 20 workers. The big EC2 had a load of about 208 on 96 CPUs, and the L7-20b rows took about 1.6 times their predictions there (measured: 2 of 40 done after 41 h). B = `s3://${RUNNER_BUCKET}`.

## What is done (prepared, not started)

1. `M1-freeze.sh` (`~/s3-work/ec2-L7-20b/move-to-spot-b/`) wrote `/bL7b/ctp/STOP` and `STOP.move-to-spot-b` on the big EC2 at 12:40:50 UTC. Census L7-20b starts no new row and no retry. Its 6 running rows finish. Then the census ends and census-L7-20b-finalize writes `L7-20b/final/DONE` (OnSuccess/OnFailure). At that time 8 rows had a state dir: waterfox, kernel-msm (done), classic-flang (done), intel llvm, liferay, enterprise-firefox, llvm-msvc, ODOS.
2. `build_batch24.py` wrote `upload/` (5 files) and `record/` (the 5 part manifests). The 32 rows are rows 25-56 of `manifest.L7-20.tsv` v2 (58af4ad6…), with fields and order unchanged. The sidecar is a byte copy of `project_meta.L7-20.json` (28ddbccc…), the same copy that L7-20b uses. The script checks that the 8 started rows are a prefix of L7-20b, and that a derive of `upload/` gives the recorded sha256 of each part.
3. `feed.next.tsv` (`~/s3-work/ec2-batch6/`) has the batch24 line: cregit 57551d7, bundle `cregit-57551d7.bundle` (18b1bf1c…), libexpat gate 14eb5d72…b799.

## Parts (spot half b only; 3 workers each; predicted hours are inferred)

| part | rows | makespan h | rows (predicted h) |
|---|---|---|---|
| b1 | 8 | 13.1 | freebsd-src 13.1, mysql-server 6.5, WineGDK 5.4, NetBSD pkgsrc 3.8, MariaDB server 3.6, vscode 0.5, audit-plugin-for-mysql 0.2, patchwork 0.0 |
| b2 | 6 | 12.0 | NUC970_Linux_Kernel 10.6, pfsense FreeBSD-ports 7.0, ferrocene 6.4, polardbx-engine 4.9, eloqsql 3.4, tauthon 1.6 |
| b3 | 6 | 12.2 | LibreOffice core 10.4, gccrs 7.2, android_platform_frameworks_base 6.3, freebsd-ports 5.1, TenDBCluster-TSpider 3.2, emacs-ng 1.8 |
| b4 | 6 | 12.6 | intellij-community 10.1, rondb 8.7, rust 6.1, androidx 4.0, swift 3.3, JetBrains android 2.5 |
| b5 | 6 | 12.6 | percona-xtrabackup 9.4, percona-server 8.9, cmssw 6.1, upbge 4.1, zephyr 3.7, commercial-emacs 1.7 |

Total 169.6 h predicted. If the rows take 1.6 times the prediction, each part takes about 20 h.

**Why 3 workers.** Each fed part gets its own 1200G loop XFS image on spot b's RAID0 `/data` (20,460 G free at 12:43 UTC), with a ctp disk floor of 300 G. So 3 L projects share about 900 G. The feeder starts a part only while it has a free part slot (8) and while the workers in use plus 4 are at most 20. At 3 in use, it starts b1-b5 in one pass: 3+3+3+3+3 = 18 workers, 8 parts. MemAvailable was 723 GiB. Each part keeps the fed flags: `--retries 3 --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300`.

## Steps (in this order)

1. The user runs `! bash ~/s3-work/upload-batch24.sh`. It must print `ALL OK`. It refuses if `B/batch24/input/` exists.
2. Run `bash ~/s3-work/ec2-batch24/scripts/S1-feed-line.sh`. It adds the batch24 line to `feed.tsv`, so a relaunch of spot b queues the parts again. It prints `restart_spot.sh --remaining` for a and b.
3. Check on the big EC2 that `/bL7b/ctp/STOP` still exists.
4. Run `cd ~/s3-work/ec2-batch23/scripts && I=${RUNNER_EC2_SPOT_B5} bash ssm.sh ~/s3-work/ec2-batch6/scripts/s24-enqueue.sh 900`. It refuses on half a. It sets the batch24 commit, then queues b1-b5. The feeder timer starts them in its next pass.
5. Check `/data/logs/fed-feeder.log` on spot b and `feed/b/live/progress.txt`.

## Tooling

- `restart_spot.sh` and the watchdog read `feed.tsv`, so batch24 is covered after step 2.
- `status_all.sh` shows the parts under `feed/b`. `fetch_done.sh` fetches `batch24` (7-24). `prelim_merge.py` reads the ledger in each done folder, and `RUN_CREGIT` has `batch24` as a fallback.

## Risks

- A spot reclaim loses the rows in progress. On a relaunch, `census-fed-enqueue` queues again only the rows without `done/OK`. These rows run from the start again.
- Under the STOP, the 6 running L7-20b rows get no retry. If one fails, it needs a rerun (for example as a batch 24 extra part).
- Do not remove `/bL7b/ctp/STOP`. Removing it lets L7-20b start the 32 rows again, so they run two times.
