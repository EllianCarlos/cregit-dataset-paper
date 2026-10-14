# S4 funnel

Computed 2026-10-10T05:26+00:00. 0 rows are not measured yet; each one leaves at the step that needs its measurement.

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
| has a license file (DP8L) | 25,410 | 2,913 |

Frame: **25,410 projects**, 270.7 GB of tokenizable code, about 4,796 serial pipeline hours (63 s for each tokenizable MB).

## Run layers (DP7), largest first

| Layer (commits) | Projects | Serial hours | Cumulative hours |
| --- | ---: | ---: | ---: |
| ≥ 5,000 | 3,299 | 2,709 | 2,709 |
| 1,000–4,999 | 6,776 | 974 | 3,683 |
| 500–999 | 3,819 | 308 | 3,991 |
| 100–499 | 7,039 | 417 | 4,408 |
| < 100 | 4,477 | 388 | 4,796 |

## Reasons for removal

| Reason | Rows |
| --- | ---: |
| no C, C++, Java or Rust in Linguist | 82,438 |
| archived | 36,709 |
| last push before 2025-04-03 | 24,183 |
| non-vendored tokenizable < 5% of code bytes | 6,229 |
| fork | 5,771 |
| no license file | 2,913 |
| empty repository (no commit) | 630 |
| duplicate of a GitHub row of the same project | 167 |
| SVN, not git | 121 |
| empty repository (no refs) | 83 |
| mirror | 38 |
| private or removed (the host asks for a login) | 38 |
| roster names a site or a group, not a repository | 20 |
| no repository created (the host says it does not exist yet) | 5 |
| roster names a GitHub organization, not a repository | 3 |
| moved or removed (the host says not found) | 3 |
| no default branch commit at the snapshot | 2 |
| host retired (git.apache.org refuses connections) | 2 |
| web site; the page names no repository | 2 |
| web page removed (HTTP 404 on 2026-10-10) | 2 |
| the host blocks our IP address (Codeberg, HTTP 429) | 2 |
| host retired (redirects to the GitHub organization linuxfoundation) | 2 |
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
| the host serves only dumb HTTP (no shallow fetch, the S3 method) | 1 |
