# Line authorship against token authorship in TOM 1.0.0

Date: 2026-11-11. This report compares two ways to give an author to the code of a project:
the line method (`git blame` of the source files) and the token method (the author columns of TOM).
It changes no file of TOM 1.0.0. The steps, scripts and tables are in `steps/token-vs-line/`.

## Main result

We drew a simple random sample of 250 projects from the 8,598 projects of TOM 1.0.0 and ran
the line method on the commit that TOM pins for each project. The line method gives the line
to the author of the last commit that changed the line. The token method gives each token to the
author of the last commit that changed the token.

| value | sample (250 projects) |
|---|---|
| **Tokens with another author under plain `git blame`: project mean** | **19.3%** (95% interval 17.3% to 21.3%) |
| Same value, token-weighted ratio | 22.2% (95% bootstrap interval 17.2% to 26.8%) |
| Tokens with another author under `git blame -w` (project mean) | 16.1% (14.5% to 17.6%) |
| Tokens with another author under `git blame -w -M -C` (project mean) | 15.5% (14.0% to 17.1%) |
| Tokens with another commit under plain `git blame` (project mean) | 42.3% (40.2% to 44.3%) |
| Tokens with another organization under plain `git blame` (project mean) | 10.5% (9.1% to 12.0%) |
| Tokens with another organization under `git blame -w -M -C` (project mean) | 8.5% (7.4% to 9.6%) |

The main value is the mean over the projects of the share of tokens with another author. It has
249 values (one project has no value, see the section on the cut projects). The interval is
mean ± t(0.975, 248) × s / √n × √((N − n) / (N − 1)) with N = 8,598. The interval covers the
error of the random sample only. The bootstrap interval of the same mean (17.3% to 21.3%) is
the same. The planned half-width was 2 percentage points (pp); the result is 1.98 pp.

The difference is not an error rate of the line method, and the token method is not ground truth.
The token method uses `git blame -C100` on token files, which searches for moved and copied code.
Section "Causes" shows how much of the difference comes from each cause.

The sample covers 838,348,903 tokens, 726,246 source files and 165,921,412 blamed lines.

## Method

- **Frame and draw.** The frame is the 8,598 project files of TOM 1.0.0 (C, C++, Java and Rust
  projects with 1,000 or more commits), sorted by project name (`steps/token-vs-line/tables/frame.tsv`).
  `draw_sample.py` shuffles the frame with `random.Random(20261109)`. The sample is the first 250
  projects of the permutation (column `draw_rank`). None of the 19 pilot projects is in the sample.
  The sample size comes from the standard deviation of the pilot values (16.26 pp): it gives a
  half-width of 2 pp at n = 250.
- **Line method.** For each source file of a project, at the pinned commit, we ran three blames:
  plain `git blame`, `git blame -w` (ignores whitespace) and `git blame -w -M -C` (also follows moved
  and copied lines). The file set is the set of files in the TOM file of the project.
- **Token method.** The TOM rows with `is_structural = 0`. A token belongs to the source line
  where it starts.
- **Identity.** Both methods use the same person ids. A commit that TOM credits gets its TOM
  `personid`. For another commit, the author e-mail address of the pinned clone gives the id that TOM
  gives to that address in other commits; if TOM has no id for the address, the commit gets its own
  id. The map from address to id exists only in the memory of the measure process of one project.
  No file of this run holds a name or an address.
- **Organization.** The column `firm_based_on_domain` for the commits that TOM credits; for
  other commits, the main value of the same person, else the value of the release domain table.
- **Levels.** Token: each token against the blame of its line. Line: a code line is a line where
  at least one token starts; it is mixed when its tokens have two or more authors. File: the top author
  by tokens against the top author by lines (all lines, also blank lines). Project: the author shares
  by tokens against the author shares by lines (TVD is half the sum of the absolute differences, the part
  of the project that changes owner; Spearman is the rank correlation).
- **Estimates.** The project mean with the finite population correction is the main value. The
  token-weighted ratio is the sum of the tokens with another author over the sum of the tokens; its interval
  is the 95% percentile interval of a bootstrap over the projects (10,000 draws, seed 20261109).
- **Machine.** One m6id.16xlarge (64 vCPU, on demand), 60 parallel git jobs, git 2.50.1, Python
  3.12.14, DuckDB 1.5.5. It started on 2026-11-10 at 16:54 UTC and ended at 06:11 UTC on
  2026-11-11 (13.27 h), at the run cap. The cost was about US$50. The blames used 786 CPU hours:
  35.7 for plain, 36.1 for `-w` and 714.0 for `-w -M -C`. The planning model had expected 207 CPU hours.
- **Limits for each file.** Plain blame 1,800 s, `-w` 1,800 s, `-w -M -C` 600 s. A file over a limit
  keeps its other blames and goes into a table of limits.
- **Release root.** TOM 1.0.0, final revision. The sha256 of its `SHA256SUMS` is
  `ea2052f7ce8b764d4e54a940d71f3fd8d04b827b2db08a4d2dc0c38f7dcbf48d`; the run checked the sha256 of each TOM
  file against this list.

## The run: the cap, the limits and the clone failures

- **Clones.** All 250 projects cloned at the first attempt (241 on GitHub, 9 on other hosts). There are
  no clone failures.
- **Files over the plain and `-w` limits: none.**
- **Files over the `-w -M -C` limit: 36**, in 6 projects: llvm-project (7), Nnngram (12), wireshark (11),
  SakuraEngine (4), Squally (1) and milo (1). These files keep their plain and `-w` blames.
- **The run cap.** The run had a hard limit of 14 hours. The blames stopped at 06:04 UTC, 13.2 h after
  the start. At that time the run had not started the blames of most files of two projects. The cap cut
  69,362 of the 73,129 files of llvm-project and all 301 files of connectionlens. A file that the cap
  cut has no blame of any kind and is in the table of limits with the blame type `cap`.

## The cut projects

The run order was by project (largest TOM time first) and, inside a project, by file (most TOM rows
first). So the files that the cap cut in llvm-project are its smaller files.

| blame | tokens of the sample without this blame | share of all tokens |
|---|---|---|
| plain and `-w` | 34,734,492 | **4.14%** |
| `-w -M -C` | 48,850,633 | 5.83% |

- **connectionlens** (369,257 tokens): no file blamed. It has no value; it is not in the mean.
- **llvm-project** (85.6 M tokens): 40.2% of its tokens are in cut files. Its value (38.3% under plain
  blame) comes from the other 51.2 M tokens, which are the larger files. It is in the mean with that value.
- For the `-w -M -C` blame, four more projects have more than 10% of their tokens in files over the 600 s limit:
  Nnngram (17.8%), wireshark (20.4%), Squally (26.5%) and milo (19.2%).

Results with and without the projects whose cut share is above 10% (for each blame, its own cut share):

| value | all projects with a value | without the cut projects |
|---|---|---|
| plain: project mean (projects) | 19.30% (17.32 to 21.27) (249) | 19.22% (17.24 to 21.20) (248) |
| plain: token-weighted ratio | 22.19% (17.19 to 26.81) | 21.09% (16.45 to 25.59) |
| `-w`: project mean | 16.05% (14.48 to 17.62) | 15.97% (14.40 to 17.55) |
| `-w -M -C`: project mean (projects) | 15.53% (13.99 to 17.06) (249) | 15.42% (13.88 to 16.95) (244) |
| `-w -M -C`: token-weighted ratio | 17.89% (13.39 to 22.31) | 15.61% (11.97 to 19.42) |
| organization, plain: project mean | 10.54% (9.12 to 11.96) | 10.47% (9.05 to 11.89) |

The project mean moves by 0.1 pp or less. The token-weighted ratio moves by 1.1 pp (plain) and
2.3 pp (`-w -M -C`), because llvm-project holds 6.4% of the blamed tokens. The conclusion does not change.

## Other levels

Project means over the 249 projects with a value (95% intervals in `steps/token-vs-line/tables/run/analysis.md`):

| level | value |
|---|---|
| Code lines with tokens from 2 or more authors | 13.4% (12.1% to 14.7%) |
| Files with the same top author (tokens against plain lines) | 89.1% (87.6% to 90.6%) |
| Files with the same top-3 author set (plain) | 67.1% (64.3% to 70.0%) |
| Files with the same top author, `-w -M -C` | 92.5% (91.6% to 93.4%) |
| Projects with the same top author (plain) | 87.2% (83.0% to 91.3%) |
| Project author shares: TVD, plain | 10.6 pp (9.2 to 11.9) |
| Project author shares: TVD, `-w -M -C` | 7.4 pp (6.5 to 8.4) |
| Project author shares: Spearman, plain | 0.91 (0.90 to 0.92) |
| Projects with the same top organization (plain) | 91.2% (87.7% to 94.7%) |
| Project organization shares: TVD, plain | 5.3 pp (4.3 to 6.3) |

The project values have a wide spread: the quartiles are 4.4%, 18.4% and 30.0%; the minimum is 0.0% and the
maximum is 79.2%. 66 projects are below 5% and 11 are above 50%. The mean depends on the project size
by commits: 14.6% for 1,000 to 1,999 commits (76 projects), 18.8% for 2,000 to 9,999 (129), 30.2% for
10,000 to 49,999 (31) and 30.5% for 50,000 or more (10); 3 projects with only a probe commit count: 11.7%. By language: C 19.4%, C++ 18.6%, Java 22.3%, Rust 16.4%.

## Causes

The rules run in order; the first rule that holds gives the cause of a token with another author under
plain blame.

| cause | rule | share of the tokens with another author |
|---|---|---|
| Whitespace | `git blame -w` gives the TOM author | 14.8% |
| Move or copy of a line | `git blame -w -M -C` gives the TOM author | 10.0% |
| Part of a line | the line has tokens of several authors and the line author wrote some of them | 52.8% |
| Layout | the line commit has no token in the file | 3.5% |
| Other | none of the rules above | 18.9% |

Generated files are 3% to 8% of each cause. The token plain blame was not run in this sample, so the cause
"move or copy of a token" of the pilot does not exist here; its tokens fall into the later rules.

## Identity and the repair

- 1,477,293 of the 165,921,412 blamed lines (0.89%) have a commit that TOM does not credit. The e-mail map
  identifies 1,459,921 of them. 17,372 lines (0.0105%) have an author with no TOM id; the largest share in one
  project is 2.16%.
- **One TOM commit has no `personid`**: 1 commit with 20 token rows in OpenNuvoton__NUC970_Linux_Kernel. The first
  run of the measure step stopped on it. The fixed step gives such a commit the same path as a commit that TOM does
  not credit. No commit has more than one `personid`, and no address has more than one.
- **Leak scan.** Each result file passes a scan before the upload. The first scan held a file for every at sign.
  It held the blame file of unicode-org__icu4x: 22 lines of one file, in the column of the origin file path of the
  `-w -M -C` blame, where the path has a version directory. The file has no line text, no name and no address.
  The scan now holds an e-mail address shape in any file, and any line of a blame file that is not the exact
  blame shape; a bare at sign goes to a table of counts and shapes (`at-signs.tsv`, which has the row of this
  one file; the other 248 projects passed the strict scan and have no at sign).
- **Repair.** The run ended at 06:11 UTC with two projects not uploaded (status ALERT). Both were measured
  again with the fixed code from the blame files kept on the machine, and the repair ended at 06:20 UTC
  with 250 projects done. The blames were not run again. The tables of the run are in `tables-after-repair/`.

## Comparison with the 19-project pilot

The pilot (2026-11-09) used 16 local test projects and 3 wide projects, all with 1,000 to 2,229 commits. It
was not a random sample, and three projects held 76% of its 12.3 M tokens.

| value | pilot (19 projects) | random sample (250 projects) |
|---|---|---|
| Plain blame, project mean | 21.9% (bootstrap 15.2% to 29.4%) | 19.3% (17.3% to 21.3%) |
| Plain blame, token-weighted ratio | 22.1% (10.7% to 35.5%) | 22.2% (17.2% to 26.8%) |
| `-w -M -C`, project mean | 17.3% | 15.5% |
| `-w -M -C`, token-weighted ratio | 15.9% | 17.9% |
| Files with the same top author, project mean | 83.8% | 89.1% |
| Projects with the same top author | 73.7% (14 of 19) | 87.2% |
| Author shares TVD, plain | 13.6 pp | 10.6 pp |

The pilot values lie inside the intervals of the sample. The sample has a narrower interval for both
estimates, and the ratio is nearly the same. The pilot projects are all small (1,000 to 2,229 commits), and the
project mean rises with the number of commits, so the pilot was not made to match the whole frame. Rerunning the 19
pilot projects with the code of this run (no persons database, no token plain blame) gives the same token values;
only the file-level and project-share values move (0.2 pp or less in the pooled file values), because ties are broken
by the id hash.

## Limits

- **The cap.** Two projects are partly or fully cut (section "The cut projects"). The part of llvm-project
  that was blamed is its larger files, not a random part. The main value changes by 0.08 pp without the
  cut projects.
- **The `-w -M -C` limit.** 36 files in 6 projects went over 600 s; 5.8% of the sample tokens have no
  `-w -M -C` blame. The values of that blame are over the tokens that it covers.
- **The sample.** The intervals cover the sampling error of a simple random sample of 250 projects out of
  8,598 (C, C++, Java, Rust, 1,000 or more commits). They do not cover other languages, small projects,
  or a different pinned commit. The 3 projects with only a probe commit count are in the sample like all others.
- **Measurement.** The token method is not ground truth. The line method follows `git blame` of git 2.50.1;
  other versions or options can differ. The file top author counts blank lines on the line side.
- **The weighted ratio.** The five projects with most blamed tokens hold 35.0% of the blamed tokens, and the
  largest holds 8.3%. Its interval is 4.8 pp wide on each side, against 2.0 pp for the project mean. We
  give the project mean as the main value.
- **Identity.** TOM person ids are pseudonyms; the e-mail map links an address to the id that TOM gave in
  other commits, so two addresses of one person that TOM did not link stay two persons. The share of lines
  without an id is 0.0105%. One credited commit has no id.
- **The pilot against the sample.** The pilot is not a random sample; see the comparison above.
- **The run was repaired once.** The code that made the final tables is the fixed code in
  `steps/token-vs-line/kit/`; the first code, which the machine ran for the other 248 projects, is the same except
  for the two fixes. The 12 fixture tests pass for the fixed code.
