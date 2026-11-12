# The selection funnel of the revision (8,598 projects)

The revision of TOM 1.0.0 has 8,598 projects: the 8,449 projects of TOM 1.0.0 and 149 new
projects (41 from the GitHub and other-host pool, 108 from GitLab hosts). This folder gives the
funnel that selects them. It replaces the Linguist steps of the selection funnel
(`../../pipeline/s4-filter/funnel.v4.md`) with the tokei rule of `../language-selection/tokei/`,
and it puts the GitLab rows into the pool. No project of TOM 1.0.0 leaves
(`data/missing.tsv` is empty; `tools/fold_copy_rules.py` asserts it).

## The funnel

| Step | After the step | Removed | GitLab after | GitLab removed |
| --- | ---: | ---: | ---: | ---: |
| Pool of all sources | 194,572 |  | 9,784 |  |
| Commit on the default branch | 193,882 | 690 | 9,730 | 54 |
| Not archived | 157,173 | 36,709 | 9,730 | 0 |
| Not a fork (GitLab: also a fork of a pool project by shared root commit) | 151,291 | 5,882 | 9,619 | 111 |
| Not a mirror (GitLab: also a copy of another pool project) | 150,209 | 1,082 | 8,575 | 1,044 |
| Push on or after 2025-04-03 (GitLab: last activity) | 126,021 | 24,188 | 8,570 | 5 |
| tokei rule: the largest programming language is C, C++, Java or Rust | 23,744 | 102,277 | 1,213 | 7,357 |
| License file, or a near miss C, D or E (DP8L) | 22,341 | 1,403 | 1,019 | 194 |
| 1,000 or more commits | 8,599 | 13,742 | 153 | 866 |
| Selected (TOM 1.0.0 projects with a project file, and the new projects) | 8,598 | 1 | 153 | 0 |

The values are in `data/funnel_counts_folded.json` (key `new`). The 8,598 projects are 8,449 of
TOM 1.0.0 (45 on GitLab hosts) and 149 new projects (108 on GitLab hosts).

A user decision of 2026-11-09 moved kitao/pyxel to the commit step: its repository is not found,
so it has no commit on the default branch. Before, it left at the last step (no project file).
Each count from the commit step to the 1,000-commit step became 1 smaller (193,883 to 193,882;
8,600 to 8,599). The pool, the count of each source and the final set did not change. Only
signalwire/freeswitch leaves at the last step now (TOM 1.1.0 adds it: the TOM box becomes 8,599, equal
to the 1,000-commit box, and 0 projects fail; `../release-passes/pass-6-freeswitch/`). `tools/set_pyxel_exit.py` changed the row of
kitao/pyxel in the step file of the work folder and the step counts of
`data/funnel_counts.json`; `tools/fold_copy_rules.py` then wrote `data/funnel_counts_folded.json`.

The tokei rule is in the place of the three Linguist and byte-share steps of the earlier funnel.
Each rule looks at one project only, so the place changes the counts between the steps, but not
the final set. A project that the tokei measure cannot fetch leaves at the tokei step.

## The copy rules

A copy of a pool project must not count twice. The fork step and the mirror step have these
rules:

- All hosts: the fork flag and the mirror flag of the host.
- GitLab hosts only: a fork of a pool project by a shared root commit (R3), a copy namespace
  (R1), the same project by a reading by hand (R2), and a shared history with a pool row of the
  same name.
- The copy check of the new projects (`tools/copycheck/`): for each candidate, the host APIs give
  the root and the head commits of the candidate and of its partners (the pool rows and the
  selected rows of the same name, and the rows that a GitHub search finds by the root commit).
  `data/copy_check_evidence.tsv` has one row for each pair.

The user took two decisions on these rules (2026-11-08):

1. The root-commit fork rule and the other copy rules are GitLab rules. On GitHub and the other
   hosts, only the fork flag and the mirror flag remove a row, as for the 8,449 projects of TOM
   1.0.0.
2. An upstream never leaves because of its own copy. A partner that left the funnel at a step
   counts only if it holds the head of the row (then the row is behind it, so the row is the
   copy). A partner that is recorded as a copy never counts. A selected partner always counts.

With decision 2, the shared-history rule on record no longer removes 24 GitLab rows (`data/copy_check_rule2.tsv`,
`tools/copycheck/rule2_check.py`). 7 of them went back to the tokei step. 17 of them passed the
tokei, license and commit steps; they got the copy check of the new projects. 10 of them left
at the fork step and 7 joined the new projects (`tools/copycheck/extra7.py`).

The result: 159 candidates before the copy check, 17 removed by it (`data/removed.tsv`: the
step, the rule and the evidence), 7 back by decision 2, 149 new projects
(`data/new_projects.tsv`, `data/added.tsv`).

## Files

| Path | Contents |
| --- | --- |
| `data/new_projects.tsv` | The 149 new projects: name, host, pinned commit and its source, commits, tokei largest language and share, the step where the earlier funnel dropped the project, license evidence, size and estimated pipeline hours. The input list of `../new-projects/`. |
| `data/added.tsv` | The same 149 projects with the TOM project name. |
| `data/removed.tsv` | The 17 candidates that the copy check removed. |
| `data/copy_check_evidence.tsv` | The pairs of the copy check (root and head commits of both rows). |
| `data/copy_check_rule2.tsv` | The rows of the shared-history rule on record that decision 2 checked again. |
| `data/fetch-failed.tsv` | The rows that the tokei measure could not fetch. |
| `data/missing.tsv` | The projects of TOM 1.0.0 that the funnel does not select (none). |
| `data/funnel_counts.json`, `data/funnel_counts_folded.json` | The counts before and after the folded copy rules. |
| `tools/fold_copy_rules.py` | Folds the copy rules into the fork and mirror steps and writes the counts. |
| `tools/set_pyxel_exit.py` | Moves kitao/pyxel to the commit step (2026-11-09) and recomputes the step counts of `data/funnel_counts.json`. |
| `tools/gitlab_checks.py` | The GitLab commit and shared-history checks of the rows on record. |
| `tools/copycheck/` | The copy check: `partners.py` (the pairs), `check.py` (the host APIs), `classify.py` (the rules), `rule2_check.py` (decision 2), `extra7.py` (the 7 rows back). |

`data/` comes through the sync (`../../sync/`, source id `study-funnel`, study commit
`f4d87914582c`). `tools/` was never in git: these are copies of the work folder of the funnel.
The copies of `fold_copy_rules.py`, `gitlab_checks.py` and `copycheck/partners.py` differ from
the files that ran in one line: the default path of the study repository became
`STUDY-REPOSITORY`. The sha256 of the files that ran:

| File | sha256 of the file that ran | sha256 of the copy |
| --- | --- | --- |
| `fold_copy_rules.py` | `023a074581205b4564e3fea8bd609e753e68bd0a59913254c5e043889611ea8c` | `026a01f6e6da23071c77a9091d076be52f3cdd03b3c8ad0d05adbd44e39882d9` |
| `gitlab_checks.py` | `978c620ef8731b70a9e827493aea0e970d72b444ca35737e849ea953c8619804` | `c4bba6a0db16cc50051bf2e55882eae22355c89cac55e4313b2235dda9d8e1f0` |
| `set_pyxel_exit.py` | `4b66efb663d954c494ff5ee91177ed55194649c51d0ff3e27cac7efe7f21eb1d` | the same |
| `copycheck/check.py` | `aef807e1c11b777bd29de71850e7d9837c205e7e86a5d03a5bb44ab1f134277a` | the same |
| `copycheck/classify.py` | `e166c9100725cf8664734528feda6dc3376f1e4e2e15364b363b324b1f0c3c6f` | the same |
| `copycheck/extra7.py` | `100d9a26259fe55e4c86a333351d79c85e09dfe07aa0ba2e92008d894cf9d340` | the same |
| `copycheck/partners.py` | `0c0e22bbb9a6d1442008b4d1591b5dc60862b954acf1df0c12f3c142714c5d64` | `602f171b923f5b85de4618bf979fa1b1a149f86ebdfd9488426f7106a9d4d3b9` |
| `copycheck/rule2_check.py` | `05913958ed7a81a9d989ab2a7a53531c947901f11e13fa8cfda7683b327368a8` | the same |

Not here: the API caches and logs of the copy check (they are large and hold answers of the host
APIs), and the scripts that built the earlier funnel tables of the work folder.
