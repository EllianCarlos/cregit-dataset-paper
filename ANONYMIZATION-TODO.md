# Anonymization to-do list

The review is double-blind. Before the repository goes to the anonymous mirror,
remove or replace each hit below. sync/anonymity-scan.sh writes this file.
Do not edit it by hand. Run the script again after each fix.

The list gives the kind, the file and the line. It does not show the matched text.
The patterns are in sync/anonymity-patterns.local, which stays local.

Files under pipeline/ are copies. sync/sync-from-sources.sh checks their bytes.
So fix them in the source repository, commit there, and sync again.

## Count by kind

| kind | files | lines |
|---|---:|---:|
| study-repo-name | 1 | 1 |
| aws-profile | 5 | 5 |
| home-path | 30 | 66 |
| bucket | 6 | 12 |
| aws-account | 0 | 0 |
| email | 0 | 0 |
| user-name | 0 | 0 |
| employer | 6 | 9 |
| ec2-id | 2 | 13 |
| census-name | 86 | 419 occurrences |

Kind census-name: identifiers and words that contain "census". The repository says
"dataset" (stages: selection, build, merge, validate). Rename them later in one pass,
in the source repositories. The section "census-name" below lists them.

## Items that the scan does not see

- Git commit metadata: the author name and e-mail of each commit. The anonymous mirror
  must serve files only, or the history must be rewritten in a fresh export.
- Hits in compressed files (*.xz, *.gz). The scan reads text files only.

## Hits

### study-repo-name

- `pipeline/s2-pool/gitlab/README.md`: lines 95

### aws-profile

- `pipeline/s7-run/build_run.sh`: lines 101
- `pipeline/s7-run/census_funnel.py`: lines 43
- `pipeline/s7-run/failed-projects.md`: lines 13
- `pipeline/s7-run/fetch_done.sh`: lines 13
- `pipeline/s7-run/footer_fix_again.sh`: lines 22

### home-path

- `pipeline/S3-MEASUREMENT.md`: lines 134
- `pipeline/s2-pool/gitlab/measure_dp.py`: lines 23
- `pipeline/s2-pool/gitlab/near_miss_gitlab.py`: lines 29
- `pipeline/s2-pool/gitlab/recheck_same_name.py`: lines 29
- `pipeline/s2-pool/gitlab/screen_layer1.py`: lines 62
- `pipeline/s7-run/README.md`: lines 250, 259, 261, 263, 273, 278, 280, 286, 346, 351, 411, 412
- `pipeline/s7-run/build_run.sh`: lines 8
- `pipeline/s7-run/census.cfg`: lines 4, 5
- `pipeline/s7-run/census_funnel.py`: lines 24
- `pipeline/s7-run/failed-projects.md`: lines 17, 53, 60
- `pipeline/s7-run/fetch_done.sh`: lines 15
- `pipeline/s7-run/footer_fix_again.sh`: lines 14
- `pipeline/s7-run/local-a/census.cfg`: lines 1, 3, 4
- `pipeline/s7-run/local-a/gate.sh`: lines 3, 5, 8
- `pipeline/s7-run/local-a/run.sh`: lines 7, 9
- `pipeline/s7-run/local-b/census.cfg`: lines 1, 3, 4
- `pipeline/s7-run/local-b/gate.sh`: lines 5, 9
- `pipeline/s7-run/local-b/run.sh`: lines 8, 10
- `pipeline/s7-run/local-c/census.cfg`: lines 1, 3, 4
- `pipeline/s7-run/local-c/gate.sh`: lines 5, 9
- `pipeline/s7-run/local-c/run.sh`: lines 11, 13
- `pipeline/s7-run/local-d/census.cfg`: lines 1, 3, 4
- `pipeline/s7-run/local-d/gate.sh`: lines 5, 9
- `pipeline/s7-run/local-d/run.sh`: lines 10, 12
- `pipeline/s7-run/prelim_merge.py`: lines 4, 5, 11
- `pipeline/s7-run/run_batch1.sh`: lines 14
- `pipeline/s7-run/srcml-fix-20261009.md`: lines 41, 45
- `pipeline/s7-run/superseded-20261007.tsv`: lines 2, 3, 4
- `pipeline/s7-run/test_rewrite_footer_columns.py`: lines 5
- `sync/anonymity-patterns.local.example`: lines 7

### bucket

- `pipeline/s7-run/README.md`: lines 163, 195, 228
- `pipeline/s7-run/blame-time-limit.md`: lines 28, 88, 137, 160, 163
- `pipeline/s7-run/census_funnel.py`: lines 25
- `pipeline/s7-run/failed-projects.md`: lines 15
- `pipeline/s7-run/fetch_done.sh`: lines 14
- `pipeline/s7-run/footer_fix_again.sh`: lines 23

### employer

- `pipeline/s2-pool/slugs.csv`: lines 18178
- `pipeline/s2-pool/v2/pages/8e2ae57bf304c35e7d027bc12b902b1d1906acf8.html`: lines 343
- `pipeline/s4-filter/frame_status.v2.csv`: lines 37821, 91101
- `pipeline/s4-filter/frame_status.v3.csv`: lines 37821, 91101
- `pipeline/s4-filter/frame_status.v4.csv`: lines 37821, 91101
- `pipeline/sources/cncf-landscape/landscape_repos.csv`: lines 702

### ec2-id

- `pipeline/s7-run/README.md`: lines 95, 108, 109, 137, 145, 146, 148, 149, 153, 154
- `pipeline/s7-run/blame-time-limit.md`: lines 69, 74, 76

### census-name

File paths that contain "census":

- `pipeline/s7-run/census.cfg`
- `pipeline/s7-run/census_funnel.py`
- `pipeline/s7-run/local-a/census.cfg`
- `pipeline/s7-run/local-b/census.cfg`
- `pipeline/s7-run/local-c/census.cfg`
- `pipeline/s7-run/local-d/census.cfg`

Identifiers and words in file contents (identifier: occurrences, files; more than 4 files gives the count only):

- `//cregit-census-905418043997-usw2`: 12, 6 files
- `//github.com/GoogleCloudPlatform/opencensus-jetty-demo.git`: 3, `pipeline/s7-run/frame.layer5.csv`, `pipeline/s7-run/manifest.layer5.tsv`, `pipeline/s7-run/project_meta.layer5.json`
- `/Projects/cregit-workspace/census-local-`: 1, `pipeline/s7-run/prelim_merge.py`
- `/Projects/cregit-workspace/census-local-a/logs/census-local-a.log`: 1, `pipeline/s7-run/README.md`
- `/Projects/cregit-workspace/census-local-a`: 5, `pipeline/s7-run/README.md`, `pipeline/s7-run/prelim_merge.py`
- `/Projects/cregit-workspace/census-local-b`: 2, `pipeline/s7-run/README.md`, `pipeline/s7-run/failed-projects.md`
- `/Projects/cregit-workspace/census-local-c`: 2, `pipeline/s7-run/README.md`
- `/Projects/cregit-workspace/census-local-d`: 2, `pipeline/s7-run/README.md`, `pipeline/s7-run/failed-projects.md`
- `/etc/cregit-census`: 4, `pipeline/s7-run/README.md`, `pipeline/s7-run/blame-time-limit.md`
- `/home/ellianco/Projects/cregit-workspace/census-2026-10`: 3, `pipeline/s7-run/superseded-20261007.tsv`
- `/home/ellianco/Projects/cregit-workspace/census-local-a`: 7, `pipeline/s7-run/local-a/census.cfg`, `pipeline/s7-run/local-a/gate.sh`, `pipeline/s7-run/local-a/run.sh`
- `/home/ellianco/Projects/cregit-workspace/census-local-b`: 6, `pipeline/s7-run/local-b/census.cfg`, `pipeline/s7-run/local-b/gate.sh`, `pipeline/s7-run/local-b/run.sh`
- `/home/ellianco/Projects/cregit-workspace/census-local-c`: 6, `pipeline/s7-run/local-c/census.cfg`, `pipeline/s7-run/local-c/gate.sh`, `pipeline/s7-run/local-c/run.sh`
- `/home/ellianco/Projects/cregit-workspace/census-local-d`: 5, `pipeline/s7-run/local-d/census.cfg`, `pipeline/s7-run/local-d/run.sh`
- `/local/home/ellianco/Projects/cregit-workspace/census-2026-10`: 1, `pipeline/s7-run/census.cfg`
- `/path/to/census.cfg`: 1, `tools/ctp/docs/E2E.md`
- `/usr/local/bin/census-fed-workload`: 1, `pipeline/s7-run/blame-time-limit.md`
- `CENSUS_CLOUD_DIR`: 2, `pipeline/s7-run/fetch_done.sh`
- `Census.`: 1, `pipeline/s7-run/README.md`
- `Census`: 6, `pipeline/s7-run/README.md`, `pipeline/s7-run/census_funnel.py`, `pipeline/s7-run/run_batch1.sh`, `pipeline/s7-run/split_batch5.py`
- `GoogleCloudPlatform/opencensus-jetty-demo`: 2, `pipeline/s7-run/frame.layer5.csv`, `pipeline/s7-run/manifest.layer5.order.tsv`
- `GoogleCloudPlatform__opencensus-jetty-demo`: 3, `pipeline/s7-run/manifest.layer5.order.tsv`, `pipeline/s7-run/manifest.layer5.tsv`, `pipeline/s7-run/project_meta.layer5.json`
- `HOME/Projects/cregit-workspace/census-cloud-fixed`: 2, `pipeline/s7-run/README.md`
- `HOME/Projects/cregit-workspace/census-cloud`: 1, `pipeline/s7-run/fetch_done.sh`
- `L/census.cfg`: 4, `pipeline/s7-run/local-a/run.sh`, `pipeline/s7-run/local-b/run.sh`, `pipeline/s7-run/local-c/run.sh`, `pipeline/s7-run/local-d/run.sh`
- `Projects/cregit-workspace/census-2026-10`: 1, `pipeline/s7-run/footer_fix_batches.py`
- `Projects/cregit-workspace/census-cloud-fixed`: 1, `pipeline/s7-run/footer_fix_batches.py`
- `Projects/cregit-workspace/census-cloud`: 2, `pipeline/s7-run/footer_fix_batches.py`, `pipeline/s7-run/split_run_ledgers.py`
- `WS/census-cloud-fixed`: 1, `pipeline/s7-run/footer_fix_again.sh`
- `census-2026-10`: 9, 5 files
- `census-L1r-firm.timer`: 1, `pipeline/s7-run/README.md`
- `census-L1r-wait`: 2, `pipeline/s7-run/README.md`
- `census-L22`: 1, `pipeline/s7-run/blame-time-limit.md`
- `census-L7-20-split.timer`: 1, `pipeline/s7-run/README.md`
- `census-L7-20`: 1, `pipeline/s7-run/blame-time-limit.md`
- `census-L7-20b`: 1, `pipeline/s7-run/README.md`
- `census-`: 1, `pipeline/s7-run/prelim_merge.py`
- `census-b3-prep`: 1, `pipeline/s7-run/split_batch3.py`
- `census-b3`: 1, `pipeline/s7-run/blame-time-limit.md`
- `census-b5-parts-init`: 1, `pipeline/s7-run/blame-time-limit.md`
- `census-b5`: 4, `pipeline/s7-run/README.md`, `pipeline/s7-run/blame-time-limit.md`
- `census-backup`: 2, `pipeline/s7-run/README.md`
- `census-batch1`: 2, `pipeline/s7-run/README.md`
- `census-batch2`: 1, `pipeline/s7-run/README.md`
- `census-batch3L`: 1, `pipeline/s7-run/README.md`
- `census-batch4p1`: 1, `pipeline/s7-run/README.md`
- `census-batch4p2`: 1, `pipeline/s7-run/README.md`
- `census-batch4p3`: 1, `pipeline/s7-run/README.md`
- `census-batch5L`: 1, `pipeline/s7-run/blame-time-limit.md`
- `census-batchNL-wait`: 1, `pipeline/s7-run/split_batchN.py`
- `census-cloud-fixed`: 10, `pipeline/s7-run/README.md`, `pipeline/s7-run/footer_fix_again.sh`, `pipeline/s7-run/prelim_merge.py`
- `census-cloud`: 3, `pipeline/s7-run/footer_fix_batches.py`, `pipeline/s7-run/prelim_merge.py`
- `census-fed-check.`: 3, `pipeline/s7-run/local-b/gate.sh`, `pipeline/s7-run/local-c/gate.sh`, `pipeline/s7-run/local-d/gate.sh`
- `census-fed-check`: 2, `pipeline/s7-run/blame-time-limit.md`, `pipeline/s7-run/local-a/gate.sh`
- `census-fed-derive.`: 1, `pipeline/s7-run/split_batchN.py`
- `census-fed-derive`: 1, `pipeline/s7-run/parts_batch26.py`
- `census-fed-enqueue`: 3, `pipeline/s7-run/README.md`, `pipeline/s7-run/one_half.py`
- `census-fed-feeder`: 2, `pipeline/s7-run/local-b/manifest.local-b.tsv`, `pipeline/s7-run/split_batchN.py`
- `census-fed-finalize`: 1, `pipeline/s7-run/blame-time-limit.md`
- `census-fed-part-init`: 2, `pipeline/s7-run/blame-time-limit.md`
- `census-fed-run`: 1, `pipeline/s7-run/local-a/run.sh`
- `census-fed-upload`: 4, `pipeline/s7-run/local-a/publish_done.py`, `pipeline/s7-run/local-b/publish_done.py`, `pipeline/s7-run/local-c/publish_done.py`, `pipeline/s7-run/local-d/publish_done.py`
- `census-fed-workload`: 2, `pipeline/s7-run/blame-time-limit.md`
- `census-fed`: 4, `pipeline/s7-run/blame-time-limit.md`
- `census-fetch`: 5, `pipeline/s7-run/README.md`, `pipeline/s7-run/fetch_done.sh`, `pipeline/s7-run/footer_fix_again.sh`, `pipeline/s7-run/prelim_merge.py`
- `census-funnel-`: 1, `pipeline/s7-run/census_funnel.py`
- `census-local-a.`: 1, `pipeline/s7-run/local-a/build_run_manifest.py`
- `census-local-a`: 15, 8 files
- `census-local-b.`: 1, `pipeline/s7-run/local-d/run.sh`
- `census-local-b`: 13, 7 files
- `census-local-c`: 14, 7 files
- `census-local-d`: 11, 7 files
- `census-name`: 6, `sync/anonymity-scan.sh`
- `census-other-done`: 4, `pipeline/s7-run/README.md`
- `census-spot-decide`: 1, `pipeline/s7-run/README.md`
- `census-step-monitor`: 1, `pipeline/s7-run/README.md`
- `census.`: 7, `pipeline/s2-pool/gitlab/README.md`, `pipeline/s7-run/README.md`, `pipeline/s7-run/build_run.sh`, `pipeline/s7-run/failed-projects.md`
- `census.cfg`: 1, `pipeline/s7-run/README.md`
- `census_funnel.py`: 1, `pipeline/s7-run/census_funnel.py`
- `census_funnel`: 1, `sync/rules.tsv`
- `census`: 147, 61 files
- `censuses`: 3, `pipeline/s7-run/README.md`, `pipeline/s7-run/split_batch4.py`, `tools/ctp/docs/E2E.md`
- `cregit-workspace/census-2026-10`: 1, `pipeline/s7-run/README.md`
- `cregit-workspace/census-cloud-fixed`: 1, `pipeline/s7-run/README.md`
- `cregit-workspace/census-cloud`: 2, `pipeline/s7-run/README.md`
- `generate_dataset_census`: 1, `pipeline/s7-run/test_rewrite_footer_columns.py`
- `here/census.cfg`: 1, `pipeline/s7-run/run_batch1.sh`
- `logs/census-local-a.log`: 1, `pipeline/s7-run/README.md`
- `manifest.census.tsv`: 3, `tools/ctp/docs/E2E.md`
- `pipeline/s7-run/census.cfg`: 1, `sync/sources.tsv`
- `pipeline/s7-run/census_funnel.py`: 1, `sync/sources.tsv`
- `pipeline/s7-run/local-a/census.cfg`: 1, `sync/sources.tsv`
- `pipeline/s7-run/local-b/census.cfg`: 1, `sync/sources.tsv`
- `pipeline/s7-run/local-c/census.cfg`: 1, `sync/sources.tsv`
- `pipeline/s7-run/local-d/census.cfg`: 1, `sync/sources.tsv`
- `project_meta.census.json`: 2, `tools/ctp/docs/E2E.md`
- `s7-run/census.cfg`: 1, `sync/sources.tsv`
- `s7-run/census_funnel.py`: 1, `sync/sources.tsv`
- `s7-run/local-a/census.cfg`: 1, `sync/sources.tsv`
- `s7-run/local-b/census.cfg`: 1, `sync/sources.tsv`
- `s7-run/local-c/census.cfg`: 1, `sync/sources.tsv`
- `s7-run/local-d/census.cfg`: 1, `sync/sources.tsv`
