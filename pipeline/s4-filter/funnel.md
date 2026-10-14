# S4 funnel

Computed 2026-10-06T19:51+00:00. 0 rows are not measured yet; each one leaves at the step that needs its measurement.

| Step | Rows after the step | Removed by the step |
| --- | ---: | ---: |
| pool | 184,589 |  |
| a GitHub row has a default branch commit | 183,954 | 635 |
| not archived (DP6) | 147,246 | 36,708 |
| not a GitHub fork (DP6) | 141,475 | 5,771 |
| not a mirror (DP6) | 141,437 | 38 |
| pushed on or after 2025-04-03 (DP5) | 117,255 | 24,182 |
| Linguist lists C, C++, Java or Rust | 34,817 | 82,438 |
| measured at the pinned commit (S3) | 34,346 | 471 |
| non-vendored tokenizable ≥ 5% of code bytes (DP3) | 28,161 | 6,185 |
| has a license file (DP8L) | 25,263 | 2,898 |

Frame: **25,263 projects**, 269.7 GB of tokenizable code, about 4,777 serial pipeline hours (63 s for each tokenizable MB).

## Run layers (DP7), largest first

| Layer (commits) | Projects | Serial hours | Cumulative hours |
| --- | ---: | ---: | ---: |
| ≥ 5,000 | 3,265 | 2,694 | 2,694 |
| 1,000–4,999 | 6,740 | 973 | 3,667 |
| 500–999 | 3,801 | 308 | 3,974 |
| 100–499 | 6,997 | 416 | 4,390 |
| < 100 | 4,460 | 387 | 4,777 |

## Reasons for removal

| Reason | Rows |
| --- | ---: |
| no C, C++, Java or Rust in Linguist | 82,438 |
| archived | 36,708 |
| last push before 2025-04-03 | 24,182 |
| non-vendored tokenizable < 5% of code bytes | 6,185 |
| fork | 5,771 |
| no license file | 2,897 |
| no default branch commit | 635 |
| clone: not-git | 279 |
| clone: clone-failed | 191 |
| mirror | 38 |
| tree call failed (HTTP 404) | 1 |
| clone facts: fetch-failed | 1 |
