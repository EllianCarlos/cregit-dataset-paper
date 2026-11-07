# Linux kernel: independent employer-share sources (raw extract)

Collected 2026-11-07 for the validation of the token-level organization shares of torvalds/linux.
Each table is copied as published (same rows, same order, same numbers). Developer tables were left out on purpose; only employer and other non-person tables are copied.

## The pinned commit

- Correction (2026-11-07): the release file of the Linux kernel was built at the `run_commit` of `MANIFEST.tsv`, `24a19b953e2a3d0ea5a8c4951a0ab8f32720c907`, not at the `frame_commit` (`67f0943b394d`, the commit at the selection time, a merge of 2026-10-05 three commits after v7.3-rc6) that this note first used.
- `24a19b953e2a` is the "Linux 7.3-rc7" tag commit, committer date 2026-10-12T03:04:55Z (GitHub API, `https://api.github.com/repos/torvalds/linux/commits/24a19b953e2a3d0ea5a8c4951a0ab8f32720c907`). The GitHub compare API shows it is identical to v7.3-rc7, 447 commits after v7.3-rc6 and 289 commits before v7.3. So the release file holds the whole 7.3 merge window and all fixes up to rc7, but not the last week before v7.3.

Recent release dates (the committer date of the "Linux X.Y" tag commit, in UTC, from the GitHub API):

| Tag | Date (UTC) |
|---|---|
| v6.18 | 2025-11-30 |
| v6.19 | 2026-02-08 |
| v7.0 | 2026-04-12 |
| v7.1 | 2026-06-14 |
| v7.2 | 2026-08-16 |
| v7.3-rc1 | 2026-08-30 |
| v7.3-rc6 | 2026-10-04 |
| (pinned commit) | 2026-10-05 |
| v7.3-rc7 | 2026-10-12 |
| v7.3 | 2026-10-18 |
| v7.4-rc1 | 2026-11-01 |

Note: LWN says 7.2 came out on August 17 because of time zones; the tag commit is 2026-08-16T21:32Z.

## How LWN counts (applies to every LWN section below)

- Tool and mapping: the series began with "Who wrote 2.6.20?" (Jonathan Corbet, LWN.net, 2007-02-21, https://lwn.net/Articles/222773/). It credits each patch to the git "author". Corporate email domains map to their company, and the editor fills in a known affiliation by hand, "in some cases, the developer was asked for this information." The scripts became gitdm (the "git data miner", git://git.lwn.net/gitdm.git; README read from the mirror https://github.com/npalix/gitdm, file README). Its EmailMap lines have the form `[user at] domain, employer, optional end date`; the README says "If a date is provided, the entry is only valid up to that date ... This feature can be useful for properly tracking developers' work when they change employers but do not change email addresses." gitdm also has EmailAliases, to join one developer's several addresses.
- The recent articles (6.18 onward) point to the subscriber-only LWN Kernel Source Database (KSDB) as the data source. The 6.18 article says "LWN subscribers can find much of the information below — and more — at any time in the LWN Kernel Source Database"; the 7.2 article says a plot "like much of the information here, comes from the subscriber-only LWN Kernel Source Database". The articles read here do not describe how the KSDB maps affiliations.
- Categories, as defined in "Who wrote 2.6.20?" and used since then:
  - "(Unknown)": "patches for which existence of a supporting employer could not be determined".
  - "(None)": "the patches from developers known to be working on their own time".
  - "(Consultant)" and "(Academia)": these labels are not defined in the articles read here. "(Academia)" first appears in the 7.3 table; older tables list universities by name.
  Every one of these rows is counted in the denominator.
- Metric: "changesets" means non-merge commits in the release range (`vX.(Y-1)..vX.Y`). In the 2.6.20 article, "lines changed" counts "the greater of the number of lines added or removed by each individual changeset". These are flow metrics: what was committed in the period, not who owns the code at the end.
- Percent: the share of all changesets (or lines changed) in the period. Each table shows only the top 20 employers.

---

## LWN: "Development statistics for the 7.3 kernel"

- Author: Jonathan Corbet. Publisher: LWN.net (Eklektix, Inc.), licensed CC BY-SA 4.0.
- Date: 2026-10-19. URL: https://lwn.net/Articles/1100241/ (the full text loaded on 2026-11-07).
- Period: the 7.3 development cycle (v7.2..v7.3; v7.3 was released 2026-10-18). It covers 18,765 non-merge commits (over 20,000 commits with merges) from 3,021 developers, 807 of them new. It counts 232 employers that LWN could identify.
- Metric: changesets and lines changed (flow).
- Note in the article: "The continuing flood of new developers is behind the inexorable growth in the 'unknown' category; the bulk of them probably are working on their own time, but there is no easy way to know for sure." 92 Kylinsoft developers contributed to 7.3.
- Closest to the pinned commit: it is the same cycle, though LWN counts up to the final v7.3 tag. The pinned commit is 733 commits before v7.3.

Table "Most active 7.3 employers":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| (Unknown) | 3851 | 20.5% |
| AMD | 1186 | 6.3% |
| Intel | 1179 | 6.3% |
| Google | 1138 | 6.1% |
| Qualcomm | 1115 | 5.9% |
| Red Hat | 837 | 4.5% |
| (None) | 679 | 3.6% |
| Kylinsoft | 624 | 3.3% |
| Meta | 524 | 2.8% |
| IBM | 472 | 2.5% |
| NVIDIA | 400 | 2.1% |
| SUSE | 363 | 1.9% |
| (Consultant) | 303 | 1.6% |
| Oracle | 271 | 1.4% |
| (Academia) | 268 | 1.4% |
| Renesas Electronics | 240 | 1.3% |
| NXP Semiconductors | 237 | 1.3% |
| Arm | 234 | 1.2% |
| Amutable | 216 | 1.2% |
| Huawei Technologies | 174 | 0.9% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| AMD | 225173 | 22.3% |
| (Unknown) | 144387 | 14.3% |
| Qualcomm | 61771 | 6.1% |
| Google | 56977 | 5.6% |
| NXP Semiconductors | 45506 | 4.5% |
| Intel | 44774 | 4.4% |
| Red Hat | 38420 | 3.8% |
| (None) | 32075 | 3.2% |
| Meta | 27768 | 2.7% |
| IBM | 20441 | 2.0% |
| NVIDIA | 16737 | 1.7% |
| Realtek | 15731 | 1.6% |
| Amutable | 14873 | 1.5% |
| Morse Micro | 13949 | 1.4% |
| HP Enterprise | 13698 | 1.4% |
| Renesas Electronics | 11756 | 1.2% |
| (Consultant) | 11405 | 1.1% |
| Cloudflare | 10070 | 1.0% |
| Collabora | 8405 | 0.8% |
| Samsung | 8399 | 0.8% |


## LWN: "Development statistics for the 7.2 kernel"

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2026-08-17. URL: https://lwn.net/Articles/1088776/ (loaded).
- Period: the 7.2 cycle (v7.1..v7.2). It covers 16,418 non-merge commits from 2,652 developers (613 new) and 249 identified employers.
- Note in the article: "The most significant change this time around, arguably, is the significant increase in developers with unknown affiliation."

Table "Most active 7.2 employers":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| (Unknown) | 2743 | 16.7% |
| Intel | 1512 | 9.2% |
| Google | 1191 | 7.3% |
| Red Hat | 873 | 5.3% |
| AMD | 813 | 5.0% |
| Qualcomm | 767 | 4.7% |
| (None) | 743 | 4.5% |
| NVIDIA | 535 | 3.3% |
| Meta | 441 | 2.7% |
| (Consultant) | 429 | 2.6% |
| SUSE | 358 | 2.2% |
| Renesas Electronics | 328 | 2.0% |
| IBM | 307 | 1.9% |
| Kylin | 278 | 1.7% |
| NXP Semiconductors | 264 | 1.6% |
| Oracle | 245 | 1.5% |
| Arm | 222 | 1.4% |
| BayLibre | 203 | 1.2% |
| Microsoft | 201 | 1.2% |
| Bootlin | 194 | 1.2% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| AMD | 224121 | 22.4% |
| (Unknown) | 103861 | 10.4% |
| Google | 102565 | 10.3% |
| Qualcomm | 59021 | 5.9% |
| Intel | 53661 | 5.4% |
| Red Hat | 51559 | 5.2% |
| Meta | 38635 | 3.9% |
| (None) | 28218 | 2.8% |
| NVIDIA | 27417 | 2.7% |
| MediaTek | 22025 | 2.2% |
| NXP Semiconductors | 17692 | 1.8% |
| BayLibre | 15972 | 1.6% |
| Oracle | 12233 | 1.2% |
| Microsoft | 11786 | 1.2% |
| Renesas Electronics | 11103 | 1.1% |
| Linaro | 10209 | 1.0% |
| (Consultant) | 9362 | 0.9% |
| IBM | 9205 | 0.9% |
| Texas Instruments | 8398 | 0.8% |
| SUSE | 8350 | 0.8% |


## LWN: "Development statistics for the 7.1 kernel"

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2026-06-15. URL: https://lwn.net/Articles/1077425/ (loaded).
- Period: the 7.1 cycle (v7.0..v7.1). It covers 15,849 non-merge changesets from 2,479 developers (530 new) and 230 identified employers.

Table "Most active 7.1 employers":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| (Unknown) | 2160 | 13.6% |
| Intel | 1435 | 9.1% |
| Google | 1227 | 7.7% |
| AMD | 828 | 5.2% |
| Qualcomm | 787 | 5.0% |
| Red Hat | 745 | 4.7% |
| (None) | 694 | 4.4% |
| NVIDIA | 595 | 3.8% |
| Meta | 535 | 3.4% |
| (Consultant) | 500 | 3.2% |
| SUSE | 459 | 2.9% |
| Oracle | 390 | 2.5% |
| Arm | 334 | 2.1% |
| Renesas Electronics | 289 | 1.8% |
| NXP Semiconductors | 254 | 1.6% |
| IBM | 215 | 1.4% |
| Huawei Technologies | 210 | 1.3% |
| Kylin | 181 | 1.1% |
| Linutronix | 171 | 1.1% |
| SerNet | 155 | 1.0% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| Meta | 156583 | 15.8% |
| AMD | 136736 | 13.8% |
| (Unknown) | 76738 | 7.7% |
| Qualcomm | 75847 | 7.6% |
| Samsung | 55391 | 5.6% |
| Google | 54537 | 5.5% |
| Intel | 48917 | 4.9% |
| NVIDIA | 37374 | 3.8% |
| Red Hat | 35706 | 3.6% |
| (None) | 35178 | 3.5% |
| Oracle | 15837 | 1.6% |
| SerNet | 14403 | 1.5% |
| Arm | 13030 | 1.3% |
| SUSE | 12208 | 1.2% |
| NXP Semiconductors | 11777 | 1.2% |
| Huawei Technologies | 11580 | 1.2% |
| Realtek | 10314 | 1.0% |
| (Consultant) | 9984 | 1.0% |
| Marvell | 8282 | 0.8% |
| Amutable | 7483 | 0.8% |


## LWN: "Development statistics for the 7.0 kernel"

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2026-04-13. URL: https://lwn.net/Articles/1066723/ (loaded).
- Period: the 7.0 cycle (v6.19..v7.0). It covers 14,251 non-merge commits from 2,362 developers (489 new) and 225 identified employers.
- Note in the article: "the number of developers with unknown affiliation has been slowly growing despite our efforts to track them down."

Table "Most active 7.0 employers":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| (Unknown) | 1666 | 11.7% |
| Intel | 1540 | 10.8% |
| Google | 1075 | 7.5% |
| AMD | 943 | 6.6% |
| Red Hat | 922 | 6.5% |
| Qualcomm | 795 | 5.6% |
| (None) | 598 | 4.2% |
| Meta | 424 | 3.0% |
| SUSE | 362 | 2.5% |
| Oracle | 296 | 2.1% |
| Huawei Technologies | 291 | 2.0% |
| (Consultant) | 276 | 1.9% |
| NVIDIA | 268 | 1.9% |
| Renesas Electronics | 258 | 1.8% |
| IBM | 256 | 1.8% |
| Linaro | 245 | 1.7% |
| NXP Semiconductors | 238 | 1.7% |
| Collabora | 226 | 1.6% |
| Arm | 223 | 1.6% |
| Bootlin | 144 | 1.0% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| AMD | 139764 | 17.2% |
| Qualcomm | 73226 | 9.0% |
| (Unknown) | 70208 | 8.6% |
| Google | 68169 | 8.4% |
| Intel | 50468 | 6.2% |
| Red Hat | 40147 | 4.9% |
| Broadcom | 24765 | 3.0% |
| (None) | 23184 | 2.8% |
| Meta | 20655 | 2.5% |
| IBM | 18792 | 2.3% |
| Oracle | 17101 | 2.1% |
| Linux Foundation | 17084 | 2.1% |
| NXP Semiconductors | 15380 | 1.9% |
| Collabora | 14691 | 1.8% |
| SUSE | 13113 | 1.6% |
| Linaro | 12100 | 1.5% |
| Huawei Technologies | 10526 | 1.3% |
| NVIDIA | 9954 | 1.2% |
| Renesas Electronics | 8636 | 1.1% |
| Realtek | 8415 | 1.0% |


## LWN: "Development statistics for 6.19"

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2026-02-09. URL: https://lwn.net/Articles/1057302/ (loaded).
- Period: the 6.19 cycle (v6.18..v6.19). It covers 14,344 non-merge changesets from 2,141 developers (333 new) and 227 identified employers.

Table "Most active 6.19 employers":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| Intel | 1591 | 11.1% |
| (Unknown) | 1410 | 9.8% |
| Google | 1099 | 7.7% |
| Red Hat | 829 | 5.8% |
| Renesas Electronics | 741 | 5.2% |
| AMD | 612 | 4.3% |
| (None) | 554 | 3.9% |
| Qualcomm | 485 | 3.4% |
| SUSE | 462 | 3.2% |
| Microsoft | 434 | 3.0% |
| NVIDIA | 407 | 2.8% |
| (Consultant) | 392 | 2.7% |
| Meta | 379 | 2.6% |
| Oracle | 371 | 2.6% |
| NXP Semiconductors | 325 | 2.3% |
| Linaro | 319 | 2.2% |
| Huawei Technologies | 260 | 1.8% |
| IBM | 236 | 1.6% |
| Arm | 200 | 1.4% |
| Bootlin | 160 | 1.1% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| Google | 101728 | 13.6% |
| (Unknown) | 70125 | 9.4% |
| Intel | 59934 | 8.0% |
| AMD | 45025 | 6.0% |
| Qualcomm | 36322 | 4.9% |
| NVIDIA | 32585 | 4.4% |
| Red Hat | 31429 | 4.2% |
| Microsoft | 30621 | 4.1% |
| (None) | 27285 | 3.7% |
| MediaTek | 23223 | 3.1% |
| Ideas on Board | 14880 | 2.0% |
| Renesas Electronics | 14350 | 1.9% |
| Meta | 14232 | 1.9% |
| Collabora | 14088 | 1.9% |
| Huawei Technologies | 13257 | 1.8% |
| SUSE | 13209 | 1.8% |
| Oracle | 12943 | 1.7% |
| Arm | 12761 | 1.7% |
| IBM | 12230 | 1.6% |
| Linaro | 9015 | 1.2% |


Note: the 6.19, 7.0, 7.1, 7.2 and 7.3 articles cover the full LTS cycle from 6.18 to 7.3 (7.3 is expected to be the next LTS). LWN did not publish a combined "6.19-7.3 employers" table in the 7.3 article. Adding up the five top-20 tables gives only a partial total, because employers below 20th place in a release are missing.

---

## LWN: "Some 6.18 development statistics" (with the year-long 6.13-6.18 LTS cycle)

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2025-12-01. URL: https://lwn.net/Articles/1046966/ (loaded).
- Periods:
  - The 6.18 cycle: 13,710 commits from 2,134 developers and 217 known employers.
  - The longer cycle from 6.12 to 6.18 (six releases, 6.13 through 6.18, roughly 2024-11-17 to 2025-11-30): 80,035 non-merge changesets from 5,275 developers and 372 employers in total.

Table "Most active 6.18 employers":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| Intel | 1420 | 10.4% |
| (Unknown) | 1307 | 9.5% |
| Google | 1080 | 7.9% |
| Red Hat | 866 | 6.3% |
| AMD | 682 | 5.0% |
| (None) | 633 | 4.6% |
| Linaro | 539 | 3.9% |
| SUSE | 534 | 3.9% |
| Qualcomm | 529 | 3.9% |
| Meta | 445 | 3.2% |
| Renesas Electronics | 358 | 2.6% |
| Huawei Technologies | 356 | 2.6% |
| (Consultant) | 309 | 2.3% |
| NVIDIA | 300 | 2.2% |
| Oracle | 257 | 1.9% |
| vivo Mobile Communication Co | 257 | 1.9% |
| NXP Semiconductors | 223 | 1.6% |
| Arm | 210 | 1.5% |
| Collabora | 189 | 1.4% |
| SerNet | 183 | 1.3% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| Linux Foundation | 118142 | 15.0% |
| Intel | 74255 | 9.4% |
| Google | 67881 | 8.6% |
| Qualcomm | 56423 | 7.2% |
| (Unknown) | 55307 | 7.0% |
| AMD | 35901 | 4.6% |
| (None) | 33870 | 4.3% |
| Red Hat | 29083 | 3.7% |
| SUSE | 26027 | 3.3% |
| Meta | 24669 | 3.1% |
| Huawei Technologies | 23250 | 3.0% |
| Linaro | 19481 | 2.5% |
| (Consultant) | 15261 | 1.9% |
| NVIDIA | 14395 | 1.8% |
| Collabora | 13782 | 1.8% |
| Texas Instruments | 12434 | 1.6% |
| Renesas Electronics | 10756 | 1.4% |
| NXP Semiconductors | 9893 | 1.3% |
| BayLibre | 9025 | 1.1% |
| Microsoft | 8065 | 1.0% |


Table "Most active 6.13-18 employers" (out of 372 employers in total):

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| Intel | 8813 | 11.0% |
| (Unknown) | 6796 | 8.5% |
| Google | 6037 | 7.5% |
| Red Hat | 5181 | 6.5% |
| (None) | 4257 | 5.3% |
| AMD | 4098 | 5.1% |
| Linaro | 3701 | 4.6% |
| SUSE | 2750 | 3.4% |
| Meta | 2744 | 3.4% |
| Qualcomm | 2532 | 3.2% |
| Huawei Technologies | 1917 | 2.4% |
| Oracle | 1886 | 2.4% |
| NVIDIA | 1882 | 2.4% |
| Renesas Electronics | 1858 | 2.3% |
| Arm | 1547 | 1.9% |
| IBM | 1345 | 1.7% |
| (Consultant) | 1252 | 1.6% |
| NXP Semiconductors | 1218 | 1.5% |
| Linutronix | 1149 | 1.4% |
| Microsoft | 887 | 1.1% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| Intel | 434943 | 10.2% |
| (Unknown) | 383181 | 9.0% |
| Google | 309767 | 7.2% |
| AMD | 277384 | 6.5% |
| Qualcomm | 235450 | 5.5% |
| Red Hat | 215725 | 5.0% |
| (None) | 176686 | 4.1% |
| SUSE | 133567 | 3.1% |
| Linaro | 129946 | 3.0% |
| Linux Foundation | 129058 | 3.0% |
| Meta | 124927 | 2.9% |
| NVIDIA | 107931 | 2.5% |
| IBM | 96906 | 2.3% |
| Huawei Technologies | 82132 | 1.9% |
| Arm | 77217 | 1.8% |
| Emerson | 76919 | 1.8% |
| Collabora | 64629 | 1.5% |
| NXP Semiconductors | 62549 | 1.5% |
| Oracle | 60553 | 1.4% |
| Renesas Electronics | 52732 | 1.2% |


## LWN: "Development statistics for 6.12" (with the year-long 6.7-6.12 LTS cycle)

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2024-11-18. URL: https://lwn.net/Articles/997959/ (loaded).
- Period: the longer cycle from 6.6 to 6.12 (six releases, 6.7 through 6.12, roughly 2023-10-29 to 2024-11-17). It covers 86,715 non-merge changesets from 5,111 developers and 361 employers in total. The article also has a 6.12-only table, which is not copied here.

Table "Most active 6.7-12 employers" (out of 361 employers in total):

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| Intel | 11356 | 13.1% |
| (None) | 6881 | 7.9% |
| Google | 5920 | 6.8% |
| (Unknown) | 5668 | 6.5% |
| AMD | 5233 | 6.0% |
| Linaro | 5112 | 5.9% |
| Red Hat | 4863 | 5.6% |
| Huawei Technologies | 2459 | 2.8% |
| SUSE | 2319 | 2.7% |
| Meta | 2207 | 2.5% |
| Oracle | 1986 | 2.3% |
| Pengutronix | 1871 | 2.2% |
| Qualcomm | 1792 | 2.1% |
| NVIDIA | 1713 | 2.0% |
| IBM | 1612 | 1.9% |
| Renesas Electronics | 1574 | 1.8% |
| (Consultant) | 1227 | 1.4% |
| Arm | 1178 | 1.4% |
| NXP Semiconductors | 916 | 1.1% |
| Texas Instruments | 781 | 0.9% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| AMD | 918483 | 18.1% |
| Intel | 540531 | 10.6% |
| Google | 378278 | 7.4% |
| (None) | 352401 | 6.9% |
| Linaro | 314793 | 6.2% |
| Red Hat | 308732 | 6.1% |
| (Unknown) | 292949 | 5.8% |
| Meta | 150897 | 3.0% |
| Oracle | 136086 | 2.7% |
| Qualcomm | 108629 | 2.1% |
| NVIDIA | 94799 | 1.9% |
| SUSE | 86590 | 1.7% |
| Realtek | 78260 | 1.5% |
| Emerson | 63036 | 1.2% |
| IBM | 61320 | 1.2% |
| Collabora | 58147 | 1.1% |
| Renesas Electronics | 56839 | 1.1% |
| Huawei Technologies | 50113 | 1.0% |
| NXP Semiconductors | 41451 | 0.8% |
| Microsoft | 38985 | 0.8% |


## LWN: "Some 6.6 development statistics" (with the 6.2-6.6 LTS "supercycle")

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2023-10-30. URL: https://lwn.net/Articles/948970/ (loaded).
- Period: 6.2 through 6.6 (from the 6.1 release on 2022-12-11 to 6.6 on 2023-10-29). It covers 72,425 non-merge changesets from 4,598 developers (1,359 new). The article also has a 6.6-only table, which is not copied here.

Table "Most active employers, 6.2 through 6.6":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| Intel | 7488 | 10.3% |
| Linaro | 6882 | 9.5% |
| Google | 4990 | 6.9% |
| Red Hat | 4642 | 6.4% |
| (Unknown) | 4546 | 6.3% |
| AMD | 3709 | 5.1% |
| (None) | 3037 | 4.2% |
| Huawei Technologies | 2801 | 3.9% |
| Pengutronix | 2234 | 3.1% |
| SUSE | 2088 | 2.9% |
| NVIDIA | 2088 | 2.9% |
| Meta | 1865 | 2.6% |
| Oracle | 1718 | 2.4% |
| IBM | 1608 | 2.2% |
| (Consultant) | 1207 | 1.7% |
| Qualcomm | 1140 | 1.6% |
| Renesas Electronics | 1066 | 1.5% |
| NXP Semiconductors | 962 | 1.3% |
| Collabora | 746 | 1.0% |
| Arm | 680 | 0.9% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| Google | 482473 | 12.0% |
| Linaro | 435631 | 10.8% |
| AMD | 315689 | 7.8% |
| Intel | 309591 | 7.7% |
| Red Hat | 235604 | 5.8% |
| (Unknown) | 200825 | 5.0% |
| Qualcomm | 147468 | 3.7% |
| NVIDIA | 139600 | 3.5% |
| Meta | 111214 | 2.8% |
| Realtek | 106662 | 2.6% |
| (None) | 100191 | 2.5% |
| SUSE | 83300 | 2.1% |
| IBM | 72711 | 1.8% |
| Linux Foundation | 68750 | 1.7% |
| Microchip Technology Inc. | 66363 | 1.6% |
| MediaTek | 65067 | 1.6% |
| Oracle | 60791 | 1.5% |
| Collabora | 55622 | 1.4% |
| (Consultant) | 52382 | 1.3% |
| Renesas Electronics | 43984 | 1.1% |


## LWN: "Development statistics for the 6.1 kernel (and beyond)" (with the 5.16-6.1 LTS cycle)

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2022-12-12. URL: https://lwn.net/Articles/915435/ (loaded).
- Period: 5.16 through 6.1 (from 5.15 on 2021-10-31 to 6.1 on 2022-12-11). It covers 86,660 patches from 5,034 developers (1,741 new) and a net growth of over 3.7 million lines. The article also has a 6.1-only table, which is not copied here.
- Note in the article: the lines column is dominated by machine-generated amdgpu register definitions ("AMD's showing in the 'lines changed' column demonstrates what the results of regularly dumping machine-generated register definitions into the kernel can be").

Table "Most active employers, 5.16 through 6.1":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| Intel | 9295 | 10.7% |
| (Unknown) | 6134 | 7.1% |
| Google | 5597 | 6.5% |
| Red Hat | 4916 | 5.7% |
| AMD | 4474 | 5.2% |
| Linaro | 4373 | 5.0% |
| (None) | 4029 | 4.6% |
| Huawei Technologies | 3649 | 4.2% |
| Meta | 2904 | 3.4% |
| NVIDIA | 2563 | 3.0% |
| SUSE | 2269 | 2.6% |
| (Consultant) | 2018 | 2.3% |
| Oracle | 1944 | 2.2% |
| IBM | 1703 | 2.0% |
| Renesas Electronics | 1487 | 1.7% |
| Arm | 1391 | 1.6% |
| NXP Semiconductors | 1292 | 1.5% |
| MediaTek | 1212 | 1.4% |
| Alibaba | 944 | 1.1% |
| Microchip Technology Inc. | 943 | 1.1% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| AMD | 1653237 | 26.8% |
| Intel | 744059 | 12.1% |
| Google | 345341 | 5.6% |
| Linaro | 302581 | 4.9% |
| (Unknown) | 212408 | 3.4% |
| Meta | 209040 | 3.4% |
| Red Hat | 202698 | 3.3% |
| Realtek | 185932 | 3.0% |
| NVIDIA | 179426 | 2.9% |
| (None) | 165999 | 2.7% |
| Oracle | 132210 | 2.1% |
| MediaTek | 112561 | 1.8% |
| Huawei Technologies | 101436 | 1.6% |
| (Consultant) | 86227 | 1.4% |
| SUSE | 81624 | 1.3% |
| NXP Semiconductors | 71782 | 1.2% |
| Xilinx | 66447 | 1.1% |
| IBM | 65059 | 1.1% |
| Renesas Electronics | 58418 | 0.9% |
| Microchip Technology Inc. | 50529 | 0.8% |


---

## Linux Foundation: "2020 Linux Kernel History Report"

- Authors (signed off on the cover): Kate Stewart, Shuah Khan, Daniel M German. Reviewers listed on the cover include Greg Kroah-Hartman and Jonathan Corbet.
- Publisher: The Linux Foundation. Date: August 2020 (cover: "v5.8 A Publication of The Linux Foundation | August 2020").
- Landing page: https://www.linuxfoundation.org/resources/publications/linux-kernel-history-report-2020 (loaded).
- PDF: https://www.linuxfoundation.org/hubfs/Reports/2020_kernel_history_report_082720.pdf?hsLang=en (downloaded; 25 pages; the tables are images, read from pages 6 and 13).
- Commit metric: commits by organization, cumulative over 2007-2019. There were 780,048 commits from 1,730 organizations, and "The top 20 organizations listed below accounted for 68% of the commits".
- Mapping: gitdm. The report says: "the label of '(Unknown)' are those patches for which a supporting employer's existence could not be determined. When 'None' is used, it indicates the patches from developers known to be working on their own time. This convention is used in the gitdm tool that was used to generate these tables and was initially documented in the statistics about the 2.6.20 release."
- Page 14 also has two charts: the yearly percentage of commits by company for 2007-2019, and cumulative commits by company. For the last ten years, "long tail accounts for about one-third of all the commits."

Table 3, "Top 20 Committers" (commits 2007-2019):

| Organization | # of Commits 2007-2019 | % |
|---|---:|---:|
| None | 93,225 | 11.95% |
| Intel | 78,068 | 10.01% |
| Red Hat | 69,443 | 8.90% |
| (Unknown) | 31,919 | 4.09% |
| IBM | 29,538 | 3.79% |
| SUSE | 27,239 | 3.49% |
| Linaro | 24,740 | 3.17% |
| (Consultant) | 23,081 | 2.96% |
| Google | 21,779 | 2.79% |
| Samsung | 20,160 | 2.58% |
| AMD | 17,781 | 2.28% |
| Renesas Electronics | 15,542 | 1.99% |
| Texas Instruments | 13,855 | 1.78% |
| Oracle | 13,295 | 1.70% |
| Broadcom | 9,572 | 1.23% |
| Huawei Technologies | 9,379 | 1.20% |
| Mellanox | 9,267 | 1.19% |
| NXP Semiconductors | 9,223 | 1.18% |
| Arm | 7,646 | 0.98% |
| Linux Foundation | 6,109 | 0.78% |

The report also has a blame-based table, but it is by year, not by employer. Its "Kernel Archeology" section (pages 5-6) uses cregit token-level blame on Linux 5.8 (source: https://cregit.linuxsources.org/code/5.8/lib/vsprintf.c.html). "2,964 tokens can be traced back to 1991 that can still be found in the 5.8 kernel," and "over half of the code in the 5.8 kernel was written in the last seven years."

Table 1, "Year of Origin of Tokens in Linux v5.8" (2020 is "as of 8/2/2020"):

| Year | # of Tokens | Proportion | Accumulated |
|---|---:|---:|---:|
| 1991 | 2,964 | 0.00% | 0.00% |
| 1992 | 30,740 | 0.03% | 0.03% |
| 1993 | 46,910 | 0.04% | 0.07% |
| 1994 | 38,443 | 0.03% | 0.11% |
| 1995 | 95,498 | 0.09% | 0.19% |
| 1996 | 204,573 | 0.19% | 0.38% |
| 1997 | 370,193 | 0.34% | 0.72% |
| 1998 | 436,941 | 0.40% | 1.11% |
| 1999 | 775,706 | 0.70% | 1.81% |
| 2000 | 1,469,450 | 1.33% | 3.15% |
| 2001 | 828,530 | 0.75% | 3.90% |
| 2002 | 2,475,002 | 2.24% | 6.14% |
| 2003 | 1,310,598 | 1.19% | 7.33% |
| 2004 | 2,023,705 | 1.83% | 9.16% |
| 2005 | 2,575,195 | 2.33% | 11.49% |
| 2006 | 2,449,966 | 2.22% | 13.71% |
| 2007 | 3,118,829 | 2.83% | 16.54% |
| 2008 | 4,410,921 | 4.00% | 20.54% |
| 2009 | 5,461,240 | 4.95% | 25.49% |
| 2010 | 4,805,525 | 4.35% | 29.84% |
| 2011 | 5,859,906 | 5.31% | 35.15% |
| 2012 | 6,072,494 | 5.50% | 40.65% |
| 2013 | 6,440,436 | 5.84% | 46.49% |
| 2014 | 6,091,508 | 5.52% | 52.01% |
| 2015 | 8,968,298 | 8.13% | 60.14% |
| 2016 | 7,622,786 | 6.91% | 67.04% |
| 2017 | 11,028,463 | 9.99% | 77.04% |
| 2018 | 9,248,269 | 8.38% | 85.42% |
| 2019 | 10,843,056 | 9.83% | 95.24% |
| 2020* | 5,248,662 | 4.76% | 100.00% |

## Linux Foundation: "2017 Linux Kernel Development Report"

- Authors: Jonathan Corbet (LWN.net) and Greg Kroah-Hartman (The Linux Foundation). Publisher: The Linux Foundation.
- Date: October 2017 (the PDF creation date is 2017-10-24). The report covers development through 4.13 (released 2017-09-03), with an emphasis on 4.8 to 4.13. It calls itself the eighth in a series published roughly every year since 2008.
- Landing page: https://www.linuxfoundation.org/resources/publications/linux-kernel-report-2017 (loaded; page title "Linux Kernel Development Report 2017").
- PDF: https://www.linuxfoundation.org/hubfs/Reports/LinuxKernelReport_2017.pdf?hsLang=en (downloaded; 31 pages; the table is on page 14 of the report).
- Period of the employer table: releases 4.8 through 4.13 (about 14 months, ending 2017-09-03). It covers "just under 83,000 changesets" from 4,319 developers and 519 corporations.
- Metric: changes (non-merge changesets).
- Mapping: "For each developer, corporate affiliation was obtained through one or more of: the use of company email addresses, sponsorship information included in the code they submit, or simply asking the developers directly. The numbers presented are necessarily approximate; developers occasionally change employers, and they may do personal work out of the office." The categories are defined this way:
  - "unknown": developers "for whom we were unable to determine a corporate affiliation". With few exceptions, all of them contributed 10 or fewer changes over the past three years.
  - "none": developers "known to be doing this work on their own, with no financial contribution happening from any company".
  The report adds: "even if one assumes that all of the 'unknown' contributors are working on their own time, well over 85 percent of all kernel development is demonstrably done by developers who are being paid for their work". It also says unpaid work was "14.6 percent in the 2012 version of this report, but is 8.2 percent this time around".
- Long-period context in the same report: since 2.6.11 (2005), 15,637 developers from at least 1,513 companies have contributed. The report gives no cumulative-since-2005 employer table.

Table "Top companies contributing to the Linux kernel, 4.8–4.13":

| Company | Changes | % |
|---|---:|---:|
| Intel | 10,833 | 13.1% |
| none | 6,819 | 8.2% |
| Red Hat | 5,965 | 7.2% |
| Linaro | 4,636 | 5.6% |
| unknown | 3,408 | 4.1% |
| IBM | 3,359 | 4.1% |
| consultants | 2,743 | 3.3% |
| Samsung | 2,633 | 3.2% |
| SUSE | 2,481 | 3.0% |
| Google | 2,477 | 3.0% |
| AMD | 2,215 | 2.7% |
| Renesas Electronics | 1,680 | 2.0% |
| Mellanox | 1,649 | 2.0% |
| Oracle | 1,402 | 1.7% |
| Huawei Technologies | 1,275 | 1.5% |
| Broadcom | 1,267 | 1.5% |
| ARM | 1,256 | 1.5% |
| Texas Instruments | 1,136 | 1.4% |
| Free Electrons | 969 | 1.2% |
| NXP Semiconductors | 839 | 1.0% |
| Canonical | 805 | 1.0% |
| Facebook | 771 | 0.9% |
| Imagination Technologies | 669 | 0.8% |
| Cavium | 664 | 0.8% |
| Code Aurora Forum | 648 | 0.8% |
| Outreachy | 633 | 0.8% |
| BayLibre | 615 | 0.7% |
| NVidia | 579 | 0.7% |
| linutronix | 565 | 0.7% |
| Rockchip | 507 | 0.6% |

---

## Older LWN articles that look at longer periods or at code age

### LWN: "Statistics from the 5.2 kernel — and before"

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2019-06-21. URL: https://lwn.net/Articles/791606/ (loaded).
- Period of the employer table: the 5.2 cycle, as of about 13,600 non-merge changesets before release. It covers 1,716 developers and 215 employers.
- Blame-based part ("Code longevity"): "for each file in the kernel tree, git blame is run and the commit that added each line is noted. After associating each commit with the development cycle that brought it into the mainline, it is possible to see how many lines of code were introduced by each cycle." The result is shown only as a chart by release; there is no employer breakdown. The text adds: "over 2.5 million lines of code in the kernel — nearly 10% of the total — date back to the initial Git commit in 2005", and 215 files in 5.1 had not changed since the initial commit.

Table "Most active 5.2 employers":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| Intel | 1684 | 12.4% |
| (Unknown) | 1063 | 7.8% |
| Red Hat | 859 | 6.3% |
| Google | 730 | 5.4% |
| (None) | 633 | 4.7% |
| AMD | 544 | 4.0% |
| Linutronix | 480 | 3.5% |
| SUSE | 423 | 3.1% |
| IBM | 411 | 3.0% |
| Linaro | 370 | 2.7% |
| Huawei Technologies | 367 | 2.7% |
| Bootlin | 360 | 2.6% |
| Mellanox | 354 | 2.6% |
| ARM | 305 | 2.2% |
| (Consultant) | 295 | 2.2% |
| Renesas Electronics | 276 | 2.0% |
| Oracle | 217 | 1.6% |
| NXP Semiconductors | 182 | 1.3% |
| Linux Foundation | 160 | 1.2% |
| BayLibre | 159 | 1.2% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| Linux Foundation | 132863 | 14.5% |
| Linutronix | 127352 | 13.9% |
| Intel | 99721 | 10.9% |
| Realtek | 47705 | 5.2% |
| (Unknown) | 35515 | 3.9% |
| Red Hat | 34869 | 3.8% |
| AMD | 23993 | 2.6% |
| Collabora Multimedia | 22794 | 2.5% |
| Linaro | 22696 | 2.5% |
| Google | 22450 | 2.5% |
| (None) | 22200 | 2.4% |
| IBM | 19651 | 2.1% |
| MediaTek | 14937 | 1.6% |
| Mellanox | 14657 | 1.6% |
| Cisco | 14656 | 1.6% |
| Samsung | 14260 | 1.6% |
| SUSE | 13559 | 1.5% |
| SGI | 13441 | 1.5% |
| ARM | 12407 | 1.4% |
| BayLibre | 11753 | 1.3% |


### LWN: "Who wrote 3.0 - from two points of view"

- Author: Jonathan Corbet. Publisher: LWN.net. Date: 2011-07-13. URL: https://lwn.net/Articles/451243/ (loaded).
- Period: the 3.0 cycle, as of 3.0-rc7: 9,007 changesets from 1,110 developers and 184 employers. A "longer-term look" covers 2.5.0 to 3.0 (about 9.5 years, 291,664 changesets, 8,078 developers) for developers only. About employers over that period the article says: "The per-employer numbers are necessarily even fuzzier - to the point that they are most likely not worth showing here. Suffice to say that, in general form, they resemble the numbers we have been showing for the last few years." So it has no long-period employer table.

Table "Most active 3.0 employers":

By changesets:

| Employer | Count | Percent |
|---|---:|---:|
| (None) | 1085 | 12.0% |
| Red Hat | 1000 | 11.1% |
| Intel | 839 | 9.3% |
| (Unknown) | 569 | 6.3% |
| Novell | 441 | 4.9% |
| IBM | 374 | 4.2% |
| Microsoft | 361 | 4.0% |
| Atheros Communications | 241 | 2.7% |
| Texas Instruments | 234 | 2.6% |
| Broadcom | 222 | 2.5% |
| Oracle | 187 | 2.1% |
| AMD | 162 | 1.8% |
| Nokia | 158 | 1.8% |
| Fujitsu | 154 | 1.7% |
| Google | 129 | 1.4% |
| University of Cambridge | 119 | 1.3% |
| Analog Devices | 118 | 1.3% |
| (Consultant) | 113 | 1.3% |
| Samsung | 103 | 1.1% |
| Wolfson Microelectronics | 103 | 1.1% |

By lines changed:

| Employer | Count | Percent |
|---|---:|---:|
| Intel | 163232 | 18.1% |
| (None) | 152840 | 16.9% |
| Broadcom | 61948 | 6.9% |
| Red Hat | 59079 | 6.5% |
| Atheros Communications | 53268 | 5.9% |
| Marvell | 31118 | 3.4% |
| (Unknown) | 29261 | 3.2% |
| IBM | 20587 | 2.3% |
| Metzler Brothers Systementwicklung GbR | 19933 | 2.2% |
| Novell | 19578 | 2.2% |
| University of Cambridge | 16969 | 1.9% |
| Pengutronix | 16207 | 1.8% |
| Realsil Microelectronics | 14876 | 1.6% |
| Analog Devices | 12998 | 1.4% |
| Tilera | 12257 | 1.4% |
| Freescale | 11637 | 1.3% |
| Microsoft | 11564 | 1.3% |
| Texas Instruments | 10802 | 1.2% |
| Wolfson Microelectronics | 10051 | 1.1% |
| Samsung | 9784 | 1.1% |


---

## Search notes

- I found no public source that splits the code alive in a kernel tree by employer, using blame on lines or tokens. Two blame-based sources exist, and both split by time, not by company:
  - The LF 2020 report: cregit tokens in 5.8, by year of origin.
  - LWN on 5.2: git blame lines, by release.
- LWN's KSDB (https://lwn.net/ksdb/...) would have per-release employer pages, but it is for subscribers only and was not read.
- Search limits: no WebSearch tool was available in this session, and DuckDuckGo and Bing gave no useful results from the command line. LWN articles were found through the LWN kernel index (https://lwn.net/Kernel/Index/), and the LF reports through their known landing pages. The LF 2015 and 2016 report pages were not found at the URLs tried, so they are not included.
- All the LWN articles above loaded as full text on 2026-11-07. None was behind the subscriber-only window any more; the 7.3 article came out on 2026-10-19.
