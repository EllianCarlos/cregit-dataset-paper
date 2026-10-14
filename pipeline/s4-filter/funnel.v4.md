# S4 funnel

Computed 2026-10-11T20:05+00:00. 0 rows are not measured yet; each one leaves at the step that needs its measurement.

| Step | Rows after the step | Removed by the step |
| --- | ---: | ---: |
| pool | 184,788 |  |
| a GitHub row has a default branch commit | 184,153 | 635 |
| not archived (DP6) | 147,444 | 36,709 |
| not a GitHub fork (DP6) | 141,673 | 5,771 |
| not a mirror (DP6) | 141,635 | 38 |
| pushed on or after 2025-04-03 (DP5) | 117,452 | 24,183 |
| Linguist lists C, C++, Java or Rust | 35,014 | 82,438 |
| measured at the pinned commit (S3) | 34,552 | 462 |
| non-vendored tokenizable ≥ 5% of code bytes (DP3) | 28,323 | 6,229 |
| has a license file, or a near miss C, D or E (DP8L v4) | 26,837 | 1,486 |

Frame: **26,837 projects**, 299.2 GB of tokenizable code, about 5,298 serial pipeline hours (63 s for each tokenizable MB).

## Run layers (DP7), largest first

| Layer (commits) | Projects | Serial hours | Cumulative hours |
| --- | ---: | ---: | ---: |
| ≥ 5,000 | 3,497 | 2,891 | 2,891 |
| 1,000–4,999 | 7,215 | 1,015 | 3,906 |
| 500–999 | 4,031 | 361 | 4,267 |
| 100–499 | 7,382 | 565 | 4,831 |
| < 100 | 4,712 | 466 | 5,298 |

## Reasons for removal

| Reason | Rows |
| --- | ---: |
| no C, C++, Java or Rust in Linguist | 82,438 |
| archived | 36,709 |
| last push before 2025-04-03 | 24,183 |
| non-vendored tokenizable < 5% of code bytes | 6,229 |
| fork | 5,771 |
| no license file (no license evidence found) | 892 |
| empty repository (no commit) | 630 |
| no license file (near miss: only the README names a license) | 352 |
| no license file | 220 |
| duplicate of a GitHub row of the same project | 167 |
| SVN, not git | 121 |
| empty repository (no refs) | 83 |
| mirror | 38 |
| private or removed (the host asks for a login) | 38 |
| roster names a site or a group, not a repository | 20 |
| no license file (license files only in third-party folders) | 15 |
| no license file (the prefix rule matches only a name that is not a license file) | 5 |
| no repository created (the host says it does not exist yet) | 5 |
| roster names a GitHub organization, not a repository | 3 |
| moved or removed (the host says not found) | 3 |
| no default branch commit at the snapshot | 2 |
| host retired (git.apache.org refuses connections) | 2 |
| web site; the page names no repository | 2 |
| web page removed (HTTP 404 on 2026-10-10) | 2 |
| the host blocks our IP address (Codeberg, HTTP 429) | 2 |
| host retired (redirects to the GitHub organization linuxfoundation) | 2 |
| root tree not read (HTTP 404) | 1 |
| deleted after the snapshot (GitHub 404) | 1 |
| roster names a site or a group, not a repository (the page links the GitHub organization carvel-dev) | 1 |
| service closed (Google Code archive) | 1 |
| archive record, not a repository | 1 |
| the page names 2 repositories (fairpm/fair-plugin, fairpm/fair-protocol); neither has C, C++, Java or Rust in Linguist | 1 |
| host retired (git.orfeo-toolbox.org has no DNS name) | 1 |
| CVS or SVN, not git (the Savannah group page) | 1 |
| CVS, not git (the Savannah group page) | 1 |
| roster names a site or a group, not a repository (the page links the GitHub organization score-spec) | 1 |
| Monticello, not git (the roster note) | 1 |
| CVS, not git (the SourceForge code page) | 1 |
| Trac browser; the page publishes no git URL | 1 |
| CVS, not git (the roster note) | 1 |
| the host answers HTTP 500 | 1 |
| no license file at the root (GitHub licenseInfo ) | 1 |
| the host serves only dumb HTTP (no shallow fetch, the S3 method) | 1 |
