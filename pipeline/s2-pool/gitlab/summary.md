# GitLab pool extension: measurement (counts only)

Computed by summarize.py. Each row gets the first step that removes it.

## Listing (server filters: public, not archived, last activity on or after 2025-04-03)

| Host | Listed | Personal namespace | Fork | Empty | No default branch | No C/C++/Java/Rust | Kept |
|---|---:|---:|---:|---:|---:|---:|---:|
| git.adelielinux.org | 57 | 36 | 0 | 0 | 0 | 9 | 12 |
| git.dynare.org | 42 | 32 | 0 | 0 | 0 | 6 | 4 |
| git.themanaworld.org | 81 | 45 | 0 | 0 | 1 | 20 | 15 |
| gitlab.archlinux.org | 4,000 | 72 | 0 | 0 | 0 | 3,896 | 32 |
| gitlab.com (roster groups) | 462 | 0 | 20 | 3 | 3 | 269 | 167 |
| gitlab.com-search | 75 | 18 | 0 | 0 | 0 | 24 | 28 |
| gitlab.com-search-personal | 18 | 0 | 0 | 0 | 0 | 8 | 10 |
| gitlab.eclipse.org | 1,681 | 647 | 0 | 0 | 16 | 715 | 303 |
| gitlab.freedesktop.org | 5,838 | 5,307 | 0 | 0 | 2 | 116 | 413 |
| gitlab.gnome.org | 6,126 | 5,393 | 0 | 0 | 14 | 369 | 350 |
| gitlab.inria.fr | 3,103 | 1,432 | 0 | 0 | 17 | 1,004 | 650 |
| gitlab.winehq.org | 600 | 576 | 0 | 0 | 0 | 8 | 16 |
| invent.kde.org | 9,158 | 7,272 | 0 | 0 | 19 | 1,100 | 767 |
| **total** | **31,241** | **20,830** | **20** | **3** | **72** | **7,544** | **2,767** |

## Screen of the kept rows

| Host | Already in the pool | < 5,000 commits | Shares history (same name) | Failed | Layer 1 candidate |
|---|---:|---:|---:|---:|---:|
| git.adelielinux.org | 0 | 8 | 1 | 0 | 3 |
| git.dynare.org | 1 | 3 | 0 | 0 | 0 |
| git.themanaworld.org | 1 | 11 | 0 | 0 | 3 |
| gitlab.archlinux.org | 0 | 29 | 0 | 0 | 3 |
| gitlab.com (roster groups) | 7 | 158 | 0 | 0 | 2 |
| gitlab.com-search | 0 | 18 | 9 | 0 | 11 |
| gitlab.eclipse.org | 101 | 178 | 4 | 0 | 20 |
| gitlab.freedesktop.org | 200 | 129 | 14 | 0 | 70 |
| gitlab.gnome.org | 3 | 276 | 61 | 0 | 10 |
| gitlab.inria.fr | 1 | 609 | 7 | 0 | 33 |
| gitlab.winehq.org | 1 | 11 | 1 | 0 | 3 |
| invent.kde.org | 12 | 673 | 69 | 0 | 13 |
| **total** | **327** | **2,103** | **166** | **0** | **171** |

## Layer 1 candidates by shared history (root commit)

- new: 76
- skip: shares history with a frame row: 88
- skip: shares history with a pool row (not in the frame): 7
- new rows in 58 distinct histories (root commits); the largest clusters: 7 x gfx-ci/android/mesa, 3 x neon/backports-resolute/libdrm-resolute, 3 x drm/igt-gpu-tools, 3 x wlroots/wlroots, 3 x cedar/abstra, 2 x mesa/piglit

New, one row per history: 58 (DP8L root check: {'yes': 56, 'no': 2}). Same name as a non-GitHub frame row: 0.
Expected after DP3 (80.3% pass rate of the GitHub layer 1 rows): about 47.
Estimated serial pipeline hours (median hours of the layer 1 frame per commit bucket, 100k-500k 1.6 h, 20k-100k 0.4 h, 5k-20k 0.1 h, >=500k 21.4 h): about 34 h before DP3.

Note (2026-10-14): the row gitlab.com-search-personal lists again the 18 personal-namespace rows that the row gitlab.com-search removes (user decision ~15:35 UTC: the search takes personal namespaces too); in the screen table both search files count under gitlab.com-search. Of the 10 kept personal rows, 8 have fewer than 5,000 commits, OpenRGB shares history with the frame row CalcProgrammer1/OpenRGB (same project), and muttmua/mutt (8,687 commits; upstream of the frame row neomutt/neomutt) fails DP8L (root files COPYRIGHT and GPL only). So no personal row entered v1 at first. Since ~16:40 UTC (user: "yes to mutt") the DP8L v4 near misses also pass GitLab rows: mutt (class C) enters v1 as batch 26 (near_miss.tsv, README.md fourth round).
