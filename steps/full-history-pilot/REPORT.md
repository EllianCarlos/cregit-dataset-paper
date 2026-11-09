# Full-history pilot of the Token on Me (TOM) dataset: report

Date: 2026-11-09. Status: the pilot is done. The machine is stopped. This report is the base for a later TOM release with history. It uses ASD-STE100 style. Times are UTC, unless the text says BRT (UTC-3).

## 0. Summary

- The pilot built a "full history" file for 32 sample projects and 1 gate project. Each file has every token that ever existed in the masked files, with 3 new columns: `history_token_id`, `added_commit_sha` and `removed_commit_sha`.
- The alive rows are the TOM rows. 28 of the 32 projects are equal to TOM 1.0.0 on all compared columns. In the other 4 projects, 1,006,471 rows (0.45% of the 222.4 M alive rows) have another commit. No token value differs and no row is missing. All 4 causes come from the blame step, not from the history columns (section 4).
- A full-history file has 3.1 times the rows of the TOM file (median of the projects 3.08, middle half 2.19 to 4.31, range 1.02 to 21.6). With NULL identity columns, it uses 2.8 bytes per row, which is 2.2 times the bytes of the TOM file.
- The history step (step 10) took a median of 0.28 of the time of steps 1 to 9. A very deep history is the exception: for `rust-lang__rust`, the replay alone took 9.1 hours (3.9 times steps 1 to 9).
- 7 projects failed in step 10 on the first run (DuckDB memory, a long CSV line, a NUL byte). One more project failed its write check (NUL bytes and bare CRs). All 8 got a fix, and all 8 pass now.
- The blame tool `repoblame` gives the same output as `git blame -C100` (0 different lines on 4 projects). On the machine it is 1.7 to 5.8 times slower in wall time. With the auto rule, steps 1 to 9 of the repoblame projects took 2.0 times their TOM pipeline time. The git projects took 0.34 times. Use git for a release.
- About 6% of the removed rows have no removing commit. A side branch had these tokens, and a merge dropped them.
- Estimate for a release with history: about 90 billion rows (55 to 170 billion), 250 to 370 GB, and about 70,000 CPU hours (20,000 to 100,000). That is about US$5,000 on m6id.16xlarge on demand (US$1,500 to 7,500). The 80 projects that the sample did not cover give most of the uncertainty (section 9). A history add-on that keeps the TOM blame rows can cost much less.

## 1. Purpose and design

### 1.1 Purpose

TOM 1.0.0 has one row for each token that is alive at the pinned commit of each project. The blame step gives each row its commit (`git blame -C100`). The pilot measures the cost to add every token that ever existed. It also checks that the tools keep the TOM rows the same.

### 1.2 The 3 history columns

The generator writes them after the 53 TOM columns (cregit branch `feat/full-history-dataset`, `generate_dataset.py`):

| Column | Meaning |
| --- | --- |
| `history_token_id` | The number of the token in the history of its path. |
| `added_commit_sha` | The original commit that added the token at this path (`born_sha`, with no move link). |
| `removed_commit_sha` | The first original commit that removed the token. When only a merge removed it, this is the merge where it left the mainline. NULL for an alive token. Also NULL for a token that only a side branch had and that a merge dropped. |

An alive token keeps its blame row with all its values. A removed token is a new row. Its `token_index`, `source_line`, `source_col` and `source_text` are NULL. Its `original_commit_sha` is the commit of its first identity after the move links (`origin_born_sha`). So `token_index IS NOT NULL` selects the TOM rows. The footer has `history_move_mode=moves` and `identity_columns=null`.

The identity columns are NULL in the pilot (`--no-identity`): the author and committer names and e-mails, `commit_summary`, `personid`, `person_domain` and the 15 `footer_*` lists. The pilot machine had no pseudonymization salt.

### 1.3 Population, sample and bands

- Population: the 8,449 TOM 1.0.0 projects, minus 24 projects with 1,000,000 commits or more (the Linux kernel and its copies), minus 56 projects whose TOM pipeline took more than 12 hours. That leaves 8,369 projects.
- Groups: language (`language_tokei`: C, C++, Java, Rust) and commit band: a (< 2,000), b (2,000 to 9,999), c (10,000 to 49,999) and d (50,000 or more).
- From each of the 16 groups, the sample has 1 project from the half with the smaller TOM file and 1 project from the other half: 32 projects. Seed 20261108 (`sample.py`, `sample.tsv`).
- The gate project is `tio__tio`. The machine must give its TOM rows exactly before the run starts.
- Local tests on the development host: 16 band-a projects (4 for each language) and 3 projects with wide commits (`local-tests.tsv`, `local-wide.tsv`; results in `results-local.tsv`).

### 1.4 Code

| Part | Branch, head | Content |
| --- | --- | --- |
| cregit | `feat/full-history-dataset`, 36714b1 | runner `--history DIR`, the history in step 10, removed rows and the 3 columns, `--blame-tool git\|repoblame`, the LF-line join, the repoblame time limit |
| token history | `feat/token-history-languages`, 42a4b1e | replay of the universal mask (C, C++, Java, Rust), fixes for wide commits, NUL bytes, bare CRs and long CSV lines |
| ctp | `feat/full-history`, 389c553 | `--history`, `--history-jobs`, `--history-mode`, `--blame-tool auto\|git\|repoblame`, `--no-identity`, schema 3 checks of the 3 columns, no retry after a check rejection |
| libgit2 fork | `exp/repo-blame`, 2a4406b7a | the `repoblame` tool with a `-C100` time limit |

These branches are committed locally. They are not pushed.

### 1.5 The auto blame-tool rule

ctp b145d10, `--blame-tool auto`:

1. More than 200,000 commits: git.
2. Else, if one commit changes 1,000 masked files or more: repoblame.
3. Else, if the history has 10,000 commits or fewer: repoblame.
4. Else: git.

In the run, 24 of the 32 sample projects used repoblame and 8 used git. The gate project used repoblame.

### 1.6 What "check" and "proof" compare

The check (`check.py`, after the run) compares each pilot file with the TOM 1.0.0 file of the project:

1. File against TOM. It compares the alive rows of the pilot file with the TOM rows on (`file_path`, `token_index`, `token_value`, `original_commit_sha`), in both directions (EXCEPT ALL). Then it compares all other columns except the identity columns and the 3 history columns. It also compares the organizations mapping hash of the footer.
2. History against TOM. It compares the history tokens that are alive at the pinned commit with the TOM rows, on the place, the value and the commit. The history commit is the origin after the move links. Each difference gets one cause:
   - `only_tom` or `only_history`: no row at that place on the other side.
   - `value`: the same place, another token value.
   - `commit_plain_blame`: another commit, in a file that the pilot blamed without `-C100`.
   - `commit_born`: another commit, and `born_sha` gives the TOM commit, so the move link differs.
   - `commit_moves`: another commit, because blame `-C100` follows a copy or a move that the moves mode does not follow, or the reverse.
3. Counts: rows, alive rows, removed rows, removed rows with no removing commit, and rows per alive TOM row.

The proof (`blame_proof.py`, after the check) runs both blame tools on the same projects with the same number of jobs, in separate systemd units. It compares the `.blame` files line by line. It records the wall time, the CPU time and the memory peak.

## 2. Run

### 2.1 Machine and timeline

The run used one on-demand m6id.16xlarge (64 vCPU, 256 GiB, 2 x 1,900 GB local NVMe in RAID 0) in us-west-2b, with the AMI of the TOM runs. It ran 5 projects at a time, with the longest TOM pipeline first. It used 8 blame jobs, 12 replay jobs and 8 DuckDB threads.

| UTC, 2026-11-08 | Event |
| --- | --- |
| 02:03 | Launch. |
| 02:11 | The TOM files are fetched from Hugging Face (sha256 checked). The inputs are made. |
| 02:12 | The first gate check fails: DuckDB finds no home folder in the unit. The kit now sets `HOME`. |
| 02:59 | Gate done (tio__tio is equal to TOM). The run step starts. |
| 05:52 to 09:04 | eclipse-cdt, ni u-boot, rhwp, gpui-ce and Silent-Hill-2 fail in step 10. |
| 09:21 | All projects of bands a to c and 5 of band d are done or failed. 3 long projects continue. |
| 14:57 | rust-lang__rust writes its file. The write check rejects it (366 rows with no `history_token_id`). |
| 16:59 to 17:33 | Repair of rust-lang__rust from step 10 (24 paths replayed again). Validated: 119,158,363 rows. |
| 18:43 | graalvm__labs-openjdk fails in step 10 (DuckDB memory at 24 GB). |
| 18:58 | KiCad fails in step 10 (a CSV line of 50 MB). The drive ends: 25 ok, 8 failed. |
| 20:32 to 21:34 | Rerun of the 7 failed projects, 3 at a time, with a DuckDB limit of 64 GB. All 7 are validated. |
| 21:36 to 21:44 | The run step needs 4 starts because of file lock collisions on `project_facts.parquet`. Run step done. |
| 21:50 | Check done. The proof fails at once: git refuses the repositories of another user when it runs as root. |
| 21:55 | The proof starts again after a git `safe.directory` change for root. |
| 23:42 | Proof done. Upload done (33 Parquet files). Run done. |
| about 23:50 | Machine stopped. |

The machine ran for about 21.8 hours. At US$3.80 per hour on demand, the cost was about US$83. The same machine also ran 2 small side jobs: a scan of all TOM 1.0.0 files for `token_index` gaps, and a token word cloud for the paper. So a small part of this time is not pilot time.

The first attempts of the 32 sample projects used 363 CPU hours. The machine had 64 x 21.8 = 1,395 vCPU hours, so it was about 26% busy. After 09:21, only 3 long projects ran (KiCad, graalvm__labs-openjdk, rust-lang__rust). These 3 projects set the wall time.

### 2.2 Wall time, CPU and memory of the first attempts

From `metrics.tsv` (first attempt of each project; cgroup values of the systemd unit).

| Project | Wall h | CPU h | Memory peak GiB | Blame step h | Result of the first attempt |
| --- | ---: | ---: | ---: | ---: | --- |
| KiCad__kicad-source-mirror | 16.0 | 58.7 | 40.6 | 15.2 | failed in step 10 (CSV line) |
| graalvm__labs-openjdk | 15.7 | 94.3 | 110.7 | 13.6 | failed in step 10 (memory) |
| rust-lang__rust | 12.1 | 131.8 | 151.5 | 1.2 | write check rejected (NUL bytes, bare CRs) |
| graalvm__graalvm-community-jdk21u | 3.6 | 24.1 | 71.7 | 2.4 | ok |
| eclipse-cdt__cdt | 2.9 | 15.4 | 41.6 | 2.4 | failed in step 10 (memory) |
| analogdevicesinc__oran-u-boot | 2.1 | 10.8 | 87.8 | 0.8 | ok |
| ni__u-boot | 1.1 | 7.1 | 41.4 | 0.6 | failed in step 10 (memory) |
| MaterializeInc__materialize | 0.3 | 2.3 | 40.9 | 0.06 | ok |
| edwardkim__rhwp | 0.3 | 1.3 | 52.2 | 0.07 | failed in step 10 (memory) |
| redpanda-data__redpanda | 0.3 | 2.8 | 33.2 | 0.04 | ok |
| gpui-ce__gpui-ce | 0.2 | 2.6 | 16.6 | 0.05 | failed in step 10 (NUL byte) |
| elishacloud__Silent-Hill-2-Enhancements | 0.2 | 0.4 | 15.2 | 0.02 | failed in step 10 (CSV line of 129 MB) |
| the other 21 projects | 0.01 to 0.3 each | | 1.4 to 34.7 | | ok |

The memory peak of the cgroup includes the page cache. The largest process-tree RSS was 25 to 28 GB at the 24 GB DuckDB limit. In the reruns at the 64 GB limit, it was 63 to 69 GB. DuckDB uses its whole limit when the query is large.

### 2.3 The 8 failures and their fixes

| Project | Cause | Fix |
| --- | --- | --- |
| graalvm__labs-openjdk | DuckDB ran out of memory at 24 GB in the build of the history (179 M rows). | Kit: the DuckDB limit is now 0.8 x MemTotal / parallel projects (`MEMORY_LIMIT=auto`). Rerun at 64 GB. |
| eclipse-cdt__cdt, ni__u-boot, edwardkim__rhwp | DuckDB ran out of memory at 24 GB in the JOIN of the generator (28 to 36 M rows). | The same kit change. Rerun at 64 GB. |
| KiCad__kicad-source-mirror | The history build read only CSV lines of 16 MB or less. One line had 50 MB (`bitmap_font_img.c`). | token history 42a4b1e: the limit comes from the longest line. |
| elishacloud__Silent-Hill-2-Enhancements | The same limit. One line had 129 MB (`d3dx9_data.h`). | The same commit. Full rerun, because its work folder was gone. |
| gpui-ce__gpui-ce | A NUL byte in a token file stopped the replay (IndexError). | token history fc8cade (`--text`, byte decode). |
| rust-lang__rust | 366 rows had no `history_token_id`. Git sees a token file with a NUL byte as binary and gives no hunks: 8 paths had no history, and 1 path kept an old tip. A bare CR in a token moves the blame `token_index` by one line, but the history counts LF lines (8 files). | token history fc8cade and cregit e13bbae (the join uses the LF line of the blame row). The TOM columns do not change. |

Each automatic retry of a failed project stopped after 0 seconds on the memo guard of the runner, because the first attempt kept a large memo. So the reruns used `--from-step 10`. The replay continued from its list of done paths, and the blame and token files stayed.

### 2.4 The rust repair

The repair did 4 things. It removed the 24 paths with a binary diff from the list of done paths. It installed the fixed tools beside the running units. It ran `ctp run --from-step 10 --only rust-lang__rust`. It replayed the 24 paths (1,030 rows, 18 s), then ran the build (584 s) and the generator (550 s). Step 10 took 1,368 s, and the write passed. A read-only sweep of the 26 other readable projects found 0 rows with no id and 0 text differences between the history and the blame.

### 2.5 Rerun walls

| Project | Rerun wall | Step 10 of the rerun |
| --- | ---: | ---: |
| eclipse-cdt__cdt | 8 min | 286 s |
| ni__u-boot | 9 min | 323 s |
| edwardkim__rhwp | 6 min | 237 s |
| gpui-ce__gpui-ce | 6 min | 208 s |
| KiCad__kicad-source-mirror | 34 min | 1,631 s |
| elishacloud__Silent-Hill-2-Enhancements | 22 min (full run) | 1,062 s |
| graalvm__labs-openjdk | 62 min | 2,647 s |
| rust-lang__rust (repair) | 34 min | 1,368 s |

## 3. Results per project

Sources: `checks.jsonl` (rows and bytes; the trusted counts), `metrics.tsv` (blame tool) and the step times of the pipeline logs. "Steps 1-9 s" is the sum of the step times of the first full attempt. "Step 10 s" is the history step plus the normal write of the file.

- \* The project failed in step 10 on the first attempt. The value is the time of the first attempt after step 9, plus step 10 of the rerun.
- \*\* Full rerun: steps 1 to 9 and step 10 of the rerun.

| Project | Lang. | Band | Commits | Blame tool | Alive rows | Full rows | Full / alive | Removed rows | Removed, no remover | Parquet MB | Bytes / row | Steps 1-9 s | Step 10 s | Step 10 / steps 1-9 |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rust-lang__rust | Rust | d | 342,546 | git | 22,896,083 | 119,158,363 | 5.20 | 96,262,280 | 21,461,076 | 361.5 | 3.03 | 9,204 | 35,903 * | 3.90 |
| analogdevicesinc__oran-u-boot | C | d | 90,111 | repoblame | 14,914,587 | 44,388,711 | 2.98 | 29,474,124 | 726,907 | 129.8 | 2.92 | 5,883 | 1,289 | 0.22 |
| graalvm__labs-openjdk | Java | d | 85,186 | repoblame | 60,239,297 | 178,136,861 | 2.96 | 117,897,564 | 115,429 | 506.0 | 2.84 | 52,167 | 7,130 * | 0.14 |
| graalvm__graalvm-community-jdk21u | Java | d | 78,604 | repoblame | 12,578,634 | 49,110,694 | 3.90 | 36,532,060 | 1,033,586 | 139.3 | 2.84 | 9,936 | 2,711 | 0.27 |
| KiCad__kicad-source-mirror | C++ | d | 59,105 | repoblame | 35,242,933 | 87,707,073 | 2.49 | 52,464,140 | 14,191 | 196.3 | 2.24 | 57,061 | 2,097 * | 0.04 |
| ni__u-boot | C | d | 57,709 | repoblame | 10,717,763 | 35,718,427 | 3.33 | 25,000,664 | 171,639 | 99.3 | 2.78 | 3,278 | 996 * | 0.30 |
| redpanda-data__redpanda | C++ | d | 52,502 | git | 5,315,867 | 8,892,307 | 1.67 | 3,576,440 | 17,228 | 38.6 | 4.35 | 683 | 298 | 0.44 |
| MaterializeInc__materialize | Rust | d | 51,546 | git | 5,304,972 | 13,945,930 | 2.63 | 8,640,958 | 21,273 | 55.8 | 4.00 | 674 | 341 | 0.51 |
| eclipse-cdt__cdt | Java | c | 36,628 | repoblame | 8,503,839 | 27,748,994 | 3.26 | 19,245,155 | 776,674 | 79.0 | 2.85 | 9,868 | 777 * | 0.08 |
| gpui-ce__gpui-ce | Rust | c | 35,949 | repoblame | 1,249,630 | 27,010,956 | 21.61 | 25,761,326 | 1,458,966 | 68.9 | 2.55 | 582 | 415 * | 0.71 |
| cygwin__cygwin | C | c | 22,584 | git | 6,431,475 | 12,485,331 | 1.94 | 6,053,856 | 7,508 | 46.8 | 3.75 | 592 | 257 | 0.43 |
| KDE__plasma-workspace | C++ | c | 20,408 | git | 889,743 | 2,383,663 | 2.68 | 1,493,920 | 68,580 | 8.7 | 3.64 | 392 | 58 | 0.15 |
| bitcoin-sv__bitcoin-sv | C++ | c | 19,890 | git | 2,348,271 | 8,666,415 | 3.69 | 6,318,144 | 1,794,985 | 30.3 | 3.50 | 386 | 133 | 0.34 |
| jumpmindinc__symmetric-ds | Java | c | 14,878 | repoblame | 2,032,698 | 6,457,761 | 3.18 | 4,425,063 | 51,848 | 17.5 | 2.71 | 771 | 146 | 0.19 |
| atheme__atheme | C | c | 11,843 | git | 623,646 | 2,048,732 | 3.29 | 1,425,086 | 371 | 7.5 | 3.64 | 123 | 34 | 0.28 |
| edwardkim__rhwp | Rust | c | 11,722 | git | 7,075,732 | 30,495,724 | 4.31 | 23,419,992 | 35,070 | 53.7 | 1.76 | 740 | 592 * | 0.80 |
| Keyfactor__signserver-ce | Java | b | 9,526 | repoblame | 1,020,919 | 6,858,219 | 6.72 | 5,837,300 | 794 | 14.4 | 2.11 | 409 | 97 | 0.24 |
| mongodb__mongo-c-driver | C | b | 8,030 | repoblame | 1,975,789 | 4,328,981 | 2.19 | 2,353,192 | 4,767 | 12.7 | 2.93 | 532 | 74 | 0.14 |
| dylan-lang__opendylan | C | b | 6,896 | repoblame | 295,584 | 1,686,845 | 5.71 | 1,391,261 | 292 | 3.2 | 1.88 | 81 | 23 | 0.28 |
| mosra__corrade | C++ | b | 5,328 | repoblame | 907,540 | 1,291,325 | 1.42 | 383,785 | 13 | 6.6 | 5.08 | 106 | 27 | 0.25 |
| remkop__picocli | Java | b | 4,731 | repoblame | 606,844 | 1,169,969 | 1.93 | 563,125 | 15,916 | 4.9 | 4.18 | 448 | 78 | 0.17 |
| rust-lang__futures-rs | Rust | b | 3,519 | repoblame | 283,173 | 1,216,725 | 4.30 | 933,552 | 967 | 3.5 | 2.90 | 45 | 20 | 0.44 |
| rustledger__rustledger | Rust | b | 3,250 | repoblame | 1,812,891 | 2,722,521 | 1.50 | 909,630 | 170 | 13.3 | 4.87 | 107 | 48 | 0.45 |
| solvespace__solvespace | C++ | b | 2,241 | repoblame | 415,436 | 1,467,153 | 3.53 | 1,051,717 | 0 | 5.2 | 3.56 | 50 | 25 | 0.50 |
| KDE__kclock | C++ | a | 1,827 | repoblame | 37,938 | 99,259 | 2.62 | 61,321 | 1,177 | 0.5 | 4.87 | 24 | 3 | 0.12 |
| ballcat-projects__ballcat | Java | a | 1,768 | repoblame | 342,058 | 1,512,590 | 4.42 | 1,170,532 | 1 | 3.8 | 2.50 | 55 | 32 | 0.58 |
| holepunchto__bare | C | a | 1,696 | repoblame | 32,348 | 180,060 | 5.57 | 147,712 | 0 | 0.4 | 2.34 | 25 | 7 | 0.28 |
| gotham-rs__gotham | Rust | a | 1,531 | repoblame | 113,118 | 322,959 | 2.85 | 209,841 | 8,391 | 1.2 | 3.72 | 28 | 7 | 0.25 |
| elishacloud__Silent-Hill-2-Enhancements | C++ | a | 1,448 | repoblame | 16,273,881 | 16,546,709 | 1.02 | 272,828 | 15,216 | 15.6 | 0.94 | 211 | 1,062 ** | 5.03 |
| BigPizzaV3__CodexPlusPlus | Rust | a | 1,306 | repoblame | 1,271,219 | 1,906,660 | 1.50 | 635,441 | 146,265 | 10.1 | 5.29 | 119 | 33 | 0.28 |
| tio__tio (gate) | C | a | 1,258 | repoblame | 36,468 | 56,425 | 1.55 | 19,957 | 390 | 0.4 | 6.72 | 34 | 5 | 0.15 |
| pengrad__java-telegram-bot-api | Java | a | 1,138 | repoblame | 131,730 | 243,639 | 1.85 | 111,909 | 620 | 1.1 | 4.57 | 38 | 8 | 0.21 |
| espressif__esp-bsp | C | a | 1,125 | repoblame | 547,926 | 3,634,196 | 6.63 | 3,086,270 | 352 | 2.5 | 0.69 | 47 | 57 | 1.21 |

Totals of the 32 sample projects: 222,433,564 alive rows, 699,543,752 full rows (3.14 times), 477,110,188 removed rows and 1.94 GB of Parquet. The TOM files of the same projects use 0.89 GB.

Row ratio by group (pooled, then the median of the projects):

| Group | Pooled ratio | Median |
| --- | ---: | ---: |
| Band a | 1.30 | 2.74 |
| Band b | 2.83 | 2.86 |
| Band c | 4.02 | 3.27 |
| Band d | 3.21 | 2.97 |
| C | 2.94 | 3.31 |
| C++ | 2.07 | 2.55 |
| Java | 3.17 | 3.22 |
| Rust | 4.92 | 3.58 |

The commit count does not predict the ratio (R² = 0.04 for log ratio against log commits). Generated files decide much of it. `gpui-ce__gpui-ce` (21.6) and `ormsgpack__ormsgpack` of the local tests (22.5) have files that the project rewrote many times. `elishacloud__Silent-Hill-2-Enhancements` (1.02) has huge generated headers that never changed.

The step 10 time is a median of 0.28 of steps 1 to 9 (range 0.04 to 5.0). Two cases are large. `rust-lang__rust` replayed 119,694 paths in 32,581 s with 12 jobs. `elishacloud__Silent-Hill-2-Enhancements` built a history with lines of up to 129 MB. The local tests gave 4% to 111% for the history parts only (median about 16%).

Local tests (19 projects, development host): 1.24 to 6.16 full rows per TOM row, and 22.45 for `ormsgpack__ormsgpack`. The pooled ratio was 2.01 (27.0 M rows against 13.4 M), at 2.9 bytes per row. Each file had the TOM rows exactly.

## 4. Check against TOM

### 4.1 Result

28 of 32 projects are equal to TOM on (`file_path`, `token_index`, `token_value`, `original_commit_sha`) and on all other compared columns. Each of the 33 files has the organizations mapping hash of TOM. The gate project is equal.

| Project | Rows that differ | Files | Columns that differ |
| --- | ---: | --- | --- |
| KiCad__kicad-source-mirror | 723,595 | `tools/gal_bitmap_font/bitmap_font_img.c` (400,793), `tools/gal_bitmap_font/hiero_img.c` (322,802) | commit and its dates |
| rust-lang__rust | 282,513 | `library/stdarch/crates/core_arch/src/arm_shared/neon/generated.rs` | commit and its dates |
| bitcoin-sv__bitcoin-sv | 359 | `src/big_int.h` | commit and its dates |
| cygwin__cygwin | 4 + 6 | `winsup/cygwin/pseudo-reloc.cc` (4); `winsup/cygwin/include/cygwin/socket.h` (6) | commit and its dates (4); `firm_based_on_domain` (6) |

In all 4 projects, the rows are at the same places with the same token values. Only the commit, and the columns that come from it, differ. Method: I copied the 4 pilot files and their TOM files to the release machine and joined them in DuckDB on (`file_path`, `token_index`). I used the history of each file in the pilot file (`added_commit_sha`, `removed_commit_sha`). I also used the GitHub commit API for the commits in question (files, status and line counts; no names).

### 4.2 KiCad: TOM has plain blame for 2 files; the pilot has the -C100 result

Correction of STATUS.md: the 2 differing files are not the 2 files whose repoblame the pilot stopped. The pilot stopped repoblame on `tools/gal_bitmap_font/bitmap_font_2048_0_img.c` and `common/gal/opengl/bitmap_font_img.c`. These 2 files then got plain blame after 3,600 s of `git blame -C100`, and they are equal to TOM. The 2 differing files finished in repoblame with `-C100`.

Evidence:

- TOM gives one commit, `f78721b451` (2016-09-14), to all 2,097,197 tokens of the first file and all 1,048,621 tokens of the second.
- GitHub: `f78721b451` adds `helpers/gal_bitmap_font/bitmap_font_img.c` (+1,034 lines). It also changes `common/gal/opengl/bitmap_font_img.c` in the same commit.
- GitHub: `552f724cac` (2022-07-21) renames `helpers/gal_bitmap_font/*` to `tools/gal_bitmap_font/*` with no line change. The history gives this rename commit as the birth at the new path for all tokens.
- Plain blame follows the whole-file rename and stops at the creation of the file. That gives one commit, `f78721b451`, which is the TOM value.
- `-C100` also searches the other files that the same commit changes. `common/gal/opengl/bitmap_font_img.c` changes in `f78721b451`, and it has had the same lines since `bda3011519` (2016-05-02). The pilot gives `bda3011519`, `53ef29802f` and `0c4b6dabd3` (2016-05-02), and `ade1d1fe74` (2016-05-27). All of them are older, and all come from that copy path.

Conclusion: TOM 1.0.0 very probably has plain blame for these 2 files (the 3,600 s time limit). TOM documents at least 530 such files. The TOM run logs are not in the release, so this report cannot show the `PLAIN-BLAME` lines. By the TOM rule (`-C100`), the pilot is right here.

### 4.3 rust-lang__rust: TOM has plain blame for neon/generated.rs; the pilot has the -C100 result

The pilot used git (more than 200,000 commits) with the same 3,600 s limit, and it did not fall back to plain blame.

| Share of the 562,907 tokens of the file | TOM | Pilot |
| --- | ---: | ---: |
| commit = history birth at this path | 96.5% | 47.2% |

For the 282,513 differing rows:
- The TOM commit is a commit of the history of this file for 277,766 rows.
- The pilot commit is older for 282,351 rows. The main pilot commits are from 2020-04-07 and 2024-12-10, and many of them are not commits of this file. They are copies from other generated files.

Plain blame and the history birth agree on about 97.5% of the tokens (local measure on tio__tio). So the TOM blame of this file is very probably plain blame after the time limit. The pilot machine is faster, so `-C100` finished in time. By the TOM rule, the pilot is right. The second file, `aarch64/neon/generated.rs`, is equal in both.

### 4.4 bitcoin-sv: both commits are improbable; the true origin is not known

- TOM gives `9667ac33ec` (2019-11-19) to 359 tokens of `src/big_int.h`. GitHub: this commit has one parent and changes 2 lines of this file.
- The pilot (git `-C100`) gives `25d3301277` (2019-11-14). GitHub: this is a merge with 2 parents that renames `src/big_int.hpp` to `src/big_int.h` with no line change. The history birth is the same commit for 323 of the 359 rows.
- The tokens are structural tokens and keywords on many lines: `begin_unit`, `namespace`, `class`, `public`, `explicit` and their punctuation.

A change of 2 lines does not add these tokens. A rename with no line change does not add them either. The true origin is probably older, in the history of `src/big_int.hpp`. Both builds use the same blame mode. So the difference shows that the blame of the token files is not stable between 2 builds when a merge renames a file and the token lines repeat. The data does not show which build is closer to the truth.

### 4.5 cygwin: 4 synthetic tokens (TOM is probably right) and 6 rows with another firm value

- The 4 rows are `begin_unit` (token 0) and 3 `DECL|struct|__anon84011b69...` tokens of anonymous structs. The tokenizer makes these lines; they are not source text.
- TOM gives `b862c42198` (2002-12-09) and `dc4e4aabba` (2009-10-07). GitHub: both commits change this file (the first adds it, the second changes +340 -14 lines).
- The pilot gives `b079a89e25` (2009-10-31), and the pilot history also puts their birth there. GitHub: this commit does not change `winsup/cygwin/pseudo-reloc.cc`.

So the token file of the pilot changed in a commit where the source file did not change. TOM is probably right for these 4 rows. The cause is in the token files (step 2) or in the blame of synthetic lines. The data does not show which.

The 6 other rows are in `winsup/cygwin/include/cygwin/socket.h`. They have the same commit in both files. There are 2 commits, and these 6 rows are all the rows of these 2 commits. TOM gives a university as `firm_based_on_domain`. The pilot gives `unknown`. The organizations mapping hash is the same. The pilot computes this column with NULL identity columns, and the domain link of these 2 commits did not resolve. TOM is probably right, but the cause is not known. It does not touch the history columns.

### 4.6 What the check shows for a release

The history columns do not change any alive row. All 1,006,471 differing rows come from the blame of 2 different builds:
- 2 cases of the wall-time fallback to plain blame (KiCad, rust).
- 2 small cases of unstable blame on synthetic or repeated token lines (bitcoin-sv, cygwin).

A rebuild of TOM with history will have such differences again, unless the release records the blame mode of each file (section 10).

## 5. Commit agreement: history birth against TOM blame -C100

On the machine (`checks.jsonl`), the history commit (the origin after the move links) is the TOM commit for 39.3% (bitcoin-sv) to 99.5% (Silent-Hill-2) of the alive tokens. The median of the projects is 72.5%, and the pooled value is 81.1%. With `born_sha` only (no move link), the median is 55.4%. The local tests gave 54% to 89%.

Over the sample, 42.1 M alive tokens have a different commit in the history than in TOM:
- 93% (39.1 M) have the cause `commit_moves`: blame `-C100` follows a copy or a move that the moves mode does not follow, or the reverse.
- 7% (2.9 M) have the cause `commit_born`: the move link of the history gives another commit, and `born_sha` gives the TOM commit.
- Only KiCad has `commit_plain_blame` rows (16,795, in its 2 plain-blame files). No value differs.

The cause, measured locally on tio__tio: `git blame -C100` gives the TOM commit for 100% of the tokens, `git blame -M` for 97.7%, and plain `git blame` for 65.3%. Plain blame and the history birth agree on 97.5%. So most of the difference is the `-M` that `-C` implies: git detects lines that move inside a file (at 20 alphanumeric characters). The moves mode of the token history does not follow these moves in the same way. A threshold of 20 in the moves mode did not change the result.

Effect on the file: an alive row gets its `original_commit_sha` from blame `-C100`. A removed row gets it from the history (`origin_born_sha`). So this column mixes 2 methods, and the 2 methods agree for only about 3 of 4 alive tokens.

## 6. Blame-tool proof

### 6.1 Output

On the machine (4 projects, 8 jobs each) and on the development host (7 projects, 2 jobs each), git and repoblame gave the same `.blame` bytes: 0 files and 0 lines differ. On the machine, that is 29.6 M lines in 21,293 files.

### 6.2 Time

Machine, 8 jobs each:

| Project | Commits | Widest commit (files) | git wall s | repoblame wall s | Wall ratio | git CPU s | repoblame CPU s | git / repoblame memory peak GB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| analogdevicesinc__oran-u-boot | 84,555 | 6,517 | 642.6 | 2,154.6 | 3.35 | 5,148 | 9,828 | 2.65 / 2.42 |
| ni__u-boot | 54,223 | 6,517 | 639.0 | 1,832.1 | 2.87 | 5,118 | 8,513 | 2.06 / 1.79 |
| jumpmindinc__symmetric-ds | 13,752 | 1,448 | 89.1 | 516.7 | 5.80 | 710 | 2,638 | 1.18 / 1.69 |
| mongodb__mongo-c-driver | 7,797 | 692 | 189.2 | 324.4 | 1.71 | 482 | 713 | 1.00 / 1.32 |

The automatic choice of the proof projects found only 4 distinct projects; its rule asked for up to 6.

On the development host, with 2 jobs each, repoblame used 1.2 to 4.0 times less CPU. For example: Adyen 2,409 s against 607 s, and DK22Pac 672 s against 182 s. These projects have 864 to 1,758 commits.

In the run (auto rule), the blame step of the repoblame projects was long:
- KiCad: 15.2 h. Repoblame was stopped on 2 files after many hours, then git ran with the time limit.
- graalvm__labs-openjdk: 13.6 h.
- graalvm-community: 2.4 h.
- eclipse-cdt: 2.4 h.

Steps 1 to 9 of the 24 repoblame projects took 39.4 h, which is 2.04 times their TOM pipeline time (19.3 h, on other machines). Steps 1 to 9 of the 8 git projects took 3.6 h, which is 0.34 times their TOM pipeline time (10.4 h). The machines are not the same, so these ratios are approximate, but the difference is large.

### 6.3 Recommendation

Use `git blame -C100` for a release. It is the TOM reference, and it was faster on all 4 machine proof projects (7,797 to 84,555 commits). Keep repoblame as an option for projects with very wide commits and short histories, but only after a timed test on the release machine. (An earlier measure on googleapis__google-cloud-java gave 5 to 8 times less CPU.) Do not use the auto rule of the pilot. Since cregit 36714b1, repoblame has the same `-C100` time limit as git. The KiCad run did not have it yet.

## 7. Removed tokens that no commit removed

A removed row with a NULL `removed_commit_sha` is a token that only a side branch had. A merge dropped it, so no commit on the replay path removed it. The history does not name that merge.

- Sample: 27,950,272 of 477,110,188 removed rows (5.9%).
- Per project: 0 (holepunchto__bare, solvespace) to 28.4% (bitcoin-sv__bitcoin-sv), median 0.5%. Other high values: BigPizzaV3__CodexPlusPlus 23.0% and rust-lang__rust 22.3%. rust-lang__rust has 21.5 M such rows, 77% of the sample total.
- Local tests: 0 to 706,032 per project (Adyen__adyen-java-api-library: 16% of its removed tokens).

These rows are correct as data. But a user cannot tell them from a token that a commit removed without a second query. See section 10.

## 8. Known tool defects and their state

| Defect | State |
| --- | --- |
| The generator ran out of memory at 2 GB from about 1 M history rows. | Fixed: cregit 99fb10a (the history aggregation runs before the large query). |
| The move links built the anchor index again for each born run (quadratic on wide commits). | Fixed: token history b8199b7. |
| DuckDB ran out of memory at 24 GB (build and generator JOIN). | Fixed in the kit only (`MEMORY_LIMIT=auto`). The ctp default does not size the limit from the machine. Open in ctp. |
| The history build read only CSV lines of 16 MB or less. | Fixed: token history 42a4b1e. The DuckDB buffer is 16 times the line limit, so a 129 MB line asks for a large block. |
| A NUL byte in a token file: git gives no hunks, and the history ids are wrong or missing. | Fixed: token history fc8cade. |
| A bare CR in a token: the blame `token_index` and the history LF line differ. | Fixed for the history join: cregit e13bbae. TOM 1.0.0 itself has `token_index` gaps in 77 files of 8 projects (555 missing indices, from a scan of all 8,449 TOM files). The TOM-chain fix for new projects is cregit fbbf42f (branch `fix/schema-3-bare-cr`). |
| The write check for NULL history ids misses a NUL byte that appears in a later commit when the tip gets shorter. | Open. A text check (history token text against blame token text) is stronger. The repair sweep used it. |
| A schema 3 check rejection caused retries of the whole pipeline. | Fixed: ctp fcb09ad (rejected, no retry; a write-only retry when the pipeline ended well). |
| repoblame had no `-C100` time limit. | Fixed: cregit 36714b1 with libgit2 2a4406b7a. |
| A retry of a project that failed in step 10 runs from step 1 and stops after 0 s on the memo guard of the runner. | Open. Workaround: `--from-step 10`. ctp fcb09ad covers check rejections only. |
| The history file `errors.txt` is append-only, and the runner stops when it is not empty. | Open. Workaround: move the file aside before a rerun. |
| A ctp run that only skips validated projects still writes `project_facts.parquet`. 5 parallel ctp processes collide (DuckDB lock, rename of the temporary file) and report rc=1 for validated projects. | Open. |
| `drive.py` counts rows with the shared module-level DuckDB connection in its worker threads. Two parallel projects can get each other's counts: the `eclipse-cdt__cdt` row of 21:36 has the row counts of `graalvm__labs-openjdk`. | Open (found by this report). `checks.jsonl` has the correct counts; use it. |
| `blame_proof.py` runs as root and calls git on the repositories of another user, and git refuses them. | Open. Workaround on the machine: `safe.directory=*` for root. |
| The kit marks the run step with the same file that marks the end of the whole run, so a new start refuses to run after the run step. | Open (kit). Workaround: move the step marker aside. |
| The run start script passes values (for example the number of parallel projects), but the run script reads the configuration file after them, so the configuration file wins. | Open (kit). |
| The first gate check failed because DuckDB had no home folder in the unit. | Fixed in the kit (the unit sets `HOME`). |
| The auto blame-tool rule chose repoblame for wide and deep histories, where it is slower. | Open (decision). See section 6.3. |
| The pilot computes `firm_based_on_domain` as `unknown` for 2 cygwin commits that TOM resolves. | Open; the cause is not known. |

## 9. Cost model for a release with history

### 9.1 Method

`model.py` fits 3 lines in log space over the 32 sample projects. Then it sums the prediction over the 8,369 projects of the population:

- rows: log(full / alive) against log(commits): R² = 0.04. The fit is flat, so it gives about the median ratio.
- CPU: log(CPU seconds) against log(TOM pipeline seconds): slope 1.19, R² = 0.94.
- bytes: log(bytes) against log(full rows): slope 0.93, R² = 0.95.

The low and high values put every project at the 10th or the 90th percentile of the residuals, so the band is wide. For the 8 projects that ran twice, CPU is the first attempt plus 8 CPU seconds for each wall second of the rerun (an upper bound). The machine is m6id.16xlarge (64 vCPU, 80% busy) at US$3.80 per hour.

### 9.2 Population (8,369 projects; 21.85 billion alive rows; TOM files 78 GB)

| Value | Low | Mid | High |
| --- | ---: | ---: | ---: |
| Full rows | 36.3 billion | 69.2 billion | 139.0 billion |
| CPU hours | 14,100 | 25,800 | 52,700 |
| Machine hours | 276 | 504 | 1,029 |
| US$ | 1,050 | 1,910 | 3,910 |
| Size with NULL identity columns | 0.06 TB | 0.18 TB | 0.53 TB |

A simpler check: 21.85 billion alive rows times the median ratio 3.08 gives 67 billion rows. The middle half of the ratios gives 48 to 94 billion.

### 9.3 The 80 projects that the sample left out

| Group | Projects | Alive rows | TOM pipeline time | TOM files |
| --- | ---: | ---: | ---: | ---: |
| 1,000,000 commits or more (Linux and its copies) | 24 | 4.29 billion | 647 h | 22.4 GB |
| TOM pipeline longer than 12 h | 56 | 4.27 billion | 1,788 h | 14.7 GB |

These 80 projects have 28% of the TOM rows. The sample has no project like them: the longest sample project had a TOM pipeline of 8.3 h. Two measures help:

- Linux (local, September 2026, `.c` and `.h` only): 407.9 M history rows for 199.8 M alive rows (2.04 times), 50.4 h of replay with 8 jobs, 2.5 h of build and 134 GB of work files.
- `rust-lang__rust` (342,546 commits): ratio 5.2, 9.1 h of replay with 12 jobs, and a 152 GiB cgroup peak.

With ratios of 2 to 3.1, the 80 projects add 17 to 27 billion rows. The CPU fit, used far outside its range, gives about 44,000 CPU hours: 11,000 for the 1,000,000-commit group and 33,000 for the 12-hour group. This value has low confidence. The replay time grows with the number of commits on the replay path, so each of the largest projects needs its own machine for 1 to 4 days.

### 9.4 Total for TOM with 8,598 projects

TOM now has 8,598 projects, 149 more than the 8,449 of the population source. The new projects are not measured. At the mean size of the population (2.6 M alive rows), they add about 1.2 billion full rows and about 2% of the cost.

| Value | Estimate | Range |
| --- | --- | --- |
| Full rows | about 90 billion (87 to 97 billion) | 55 to 170 billion |
| Size | 250 to 370 GB with the identity columns | 0.15 to 0.7 TB |
| CPU hours | about 70,000 (25,800 + 44,000) with the pilot tools and the auto blame rule | 20,000 to 100,000 |
| Machine hours (m6id.16xlarge) | about 1,400 | 400 to 2,000 |
| US$ | about 5,000 | 1,500 to 7,500 |
| DuckDB memory per project | 64 GB for the largest sample projects | more for the 80 left-out projects |

Notes:

- Size: the pilot files use 2.8 bytes per row with NULL identity columns. TOM 1.0.0 uses 4.0 bytes per alive row with the identity columns. A release must also fill the identity columns of the removed rows (with the salt). So the low size uses 2.8 bytes per row and the high size uses 4.0 bytes per row. TOM 1.0.0 is 115 to 137 GB, so a release with history is about 2 to 3 times as large.
- CPU: git blame for all projects (section 6.3) lowers the cost. Steps 1 to 9 of the repoblame projects took 2 times their TOM pipeline time.
- A much lower cost is possible. The alive rows of the pilot are the TOM rows. The history needs the token repository (steps 1 to 4) and the replay. It does not need the blame step, which is the largest part of steps 1 to 9 for the large projects (KiCad: 54,648 of 57,061 s). A history add-on that joins the history to the TOM rows needs no new blame, and it keeps the TOM rows. This needs a test, because the join uses the LF line of each blame row (cregit e13bbae).
- Memory: at 24 GB, the generator failed from about 28 M full rows and the build failed at 179 M rows. At 64 GB, all sample projects passed. The 80 left-out projects (up to 400 M history rows or more) need one of two changes: split the generator and the build by `file_path` (for example a hash in 16 to 32 parts), or use machines with 512 GB or more.

## 10. Open questions and recommendations

### 10.1 Columns

- Keep `history_token_id`, `added_commit_sha` and `removed_commit_sha`.
- Add a survivor flag `is_alive` (BOOLEAN, `token_index IS NOT NULL`). It costs almost nothing in Parquet, and it makes queries clear, because a NULL `removed_commit_sha` has 2 meanings today.
- Name the merge for a token that a merge dropped, or add `removal_kind` (`commit`, `merge`, `side_branch`). 5.9% of the removed rows (22% in rust-lang__rust) have no removing commit.
- Add `history_origin_commit_sha` (the origin after the move links) for all rows, including alive rows. Today `original_commit_sha` comes from blame `-C100` for alive rows and from the history for removed rows. The 2 methods agree for only 39% to 99.5% of the alive tokens of a project. With the new column, a user can choose one method for all rows.
- Decide the identity columns of the removed rows. They double the person data of the release, and they need the same pseudonymization as TOM.

### 10.2 Blame mode

- Use `git blame -C100` for all projects (section 6.3).
- Record the blame mode of each file in the release, for example a side table `blame_mode` with `file_path` and `c100` or `plain`, made from the `PLAIN-BLAME` lines. Two of the 4 differences in this pilot are a time-limit fallback, and TOM documents at least 530 such files. Without this table, a user cannot find these files, and a rebuild cannot repeat the same choices.
- Consider a limit that does not depend on wall time (for example a limit on the work of git), so that 2 machines make the same choice.
- Study the unstable blame of synthetic and repeated token lines (bitcoin-sv, cygwin). These rows are few (363 of 222 M). Document them in LIMITATIONS.

### 10.3 Memory and run

- Size the DuckDB limit from the machine in ctp, not only in the kit.
- Run the largest projects alone, or split the build and the generator by path.
- Fix the open run defects of section 8 before a release run: the memo guard on a step-10 retry, the `project_facts.parquet` collision, the shared DuckDB connection of `drive.py`, the step marker and the order of the configuration values in the kit, and `errors.txt`.
- Keep the text check of the history against the blame as a write check.

### 10.4 Scope

- Decide how to treat the 80 left-out projects. Options: a separate, later part of the release, or a run on large machines with a split generator. Measure 2 or 3 of them first, for example 1 project of 12 to 24 h and 1 project with more than 1,000,000 commits.
- Decide between a separate full-history dataset (a history add-on to the TOM rows) and a TOM 2.0 with the 3 columns in each file. The add-on costs less and keeps TOM 1.0.0 stable. TOM 2.0 makes one file per project.

### 10.5 Sources that this report could not read

All the required sources were read. This report did not read the TOM run logs, because they are not in the release. So the plain-blame status of the KiCad and rust files in TOM is an inference from the data (sections 4.2 and 4.3).

## Appendix: data and scripts

- Pilot results: `s3://BUCKET_NAME/full-history-pilot/run/full-history-pilot-1/` (not public). This has `results/` (`metrics.tsv`, `checks.jsonl`, `proof.tsv`, the logs of each project), `parquet/` (33 files) and `status/`.
- Side jobs on the pilot machine: `full-history-pilot/extra/tomscan/` (scan of TOM 1.0.0 for `token_index` gaps) and `extra/wordcloud/` (token word cloud).
- The read scripts of this report: `report/fhpr-*.sh` of the kit of the pilot (not in this package). They ran as root on the release machine through its SSM wrapper, with the scratch folder `/data1/fhpr/` (now removed). Derived tables: `report/data/table.tsv`, `report/data/table.md` and `report/data/model.json`.
- Local files in the work folder of the pilot (not in this package): `PLAN.md`, `STATUS.md`, `sample.tsv`, `population.tsv`, `results-local.tsv` and `proof-local.tsv`, and the scripts `check.py`, `blame_proof.py`, `drive.py`, `model.py` and `agree.py`.
