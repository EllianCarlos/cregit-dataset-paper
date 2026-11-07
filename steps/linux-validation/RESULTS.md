# Linux kernel: organization shares of the TOM dataset against public employer statistics

Date: 2026-11-07. Everything here is at organization level. No person names, e-mail addresses or
pseudonyms appear in this folder.

## Summary

- The rank order of organizations in the TOM dataset agrees with the independent employer
  statistics of LWN.net and the Linux Foundation. The Spearman correlations are 0.65 to 0.84 when
  the periods are matched, and all permutation p-values are below 0.01 (n = 16 to 18 listed
  employers).
- The closest match is the count of surviving commits against LWN's changesets for the 7.3
  cycle: rho = 0.84 (n = 16), with a mean absolute difference of 1.15 points over LWN's top 10.
  For lines, our alive tokens in the 7.3 window against LWN's lines changed in 7.3 give
  rho = 0.73 (n = 17), with a mean absolute difference of 2.18 points.
- Against the long-period source (Linux Foundation, commits 2007-2019), our surviving commits of
  2007-2019 give rho = 0.65 (n = 17) and a mean absolute difference of 0.91 points over the top
  10. All alive tokens, with no period filter, give rho = 0.54.
- The levels differ for a few organizations, for reasons that we know. The largest is the
  address rule: the dataset maps the project address domain `kernel.org` to the Linux Foundation,
  while LWN assigns those developers to their employers by hand. The others are AMD's generated
  register headers, the deletions that LWN counts as lines changed, and companies whose
  developers commit with personal or `kernel.org` addresses (Google, Meta, Red Hat).

## 1. Our data

- **File.** The Linux kernel file of the release files, `parquet/torvalds__linux-dataset.parquet`.
- **Pinned commit.** The `run_commit` of `MANIFEST.tsv` is
  `24a19b953e2a3d0ea5a8c4951a0ab8f32720c907`. It is the "Linux 7.3-rc7" tag commit, with
  committer date 2026-10-12. The GitHub compare API shows it is identical to v7.3-rc7 and 289
  commits before v7.3 (released 2026-10-18).
  - The `frame_commit` (`67f0943b394d`, the commit at selection time) is an older commit of the
    same cycle. The run used the newer head.
- **Size.** 199,821,022 rows; 162,022,750 code tokens (`is_structural = 0`); 832,991 commits
  with at least one surviving code token. The newest committer date is 2026-10-11.
- **Organization column.** `firm_based_on_domain` (COLUMNS.md, column 69; ORGANIZATIONS.md,
  section 2). It gives the organization of the address domain that the author chose for the
  commit (`person_domain`), not the employer.
  - Pseudo ids: `independent` (a personal or vanity domain, or a real domain with no row in the
    tables), `free-provider` (webmail, ISP, forge no-reply), and `unknown` (no real domain).
  - `pre-git-import` covers the six commits of the 2005-04-16 import of the pre-git history,
    which hold 6.80% of the code tokens.
  - In this file, `person_domain` equals the domain of `author_email` for 99.97% of the code
    tokens. So the column is the author's address of each commit, as LWN uses.
  - `firm_based_on_namespace` is NULL for the whole file: no organization owns the account
    `torvalds`.
- **Known error** (ERROR.md, over the whole dataset).
  - Wrong or missed domain links: 2.735% of tokens (95% interval 1.12% to 4.93%). Of this,
    1.26 points are wrong links and 1.47 points are organizations behind real domains that have
    no row in the tables, which then count as `independent`.
  - The address rule is by design, not an error (ORGANIZATIONS.md 2.1): an employee who commits
    with a personal address counts as `independent`.
- **Tokens versus commits.** "Share of alive code tokens" counts the code tokens alive at the
  pinned commit, credited by blame to their commit. "Surviving commits" counts the commits that
  still own at least one alive code token. The second is the closer analog of a changeset count.
  - A commit with tokens both inside and outside the AMD register headers counts twice in the
    aggregate. The effect is negligible.

## 2. Public sources

The research notes, with every table as published, are in `sources-raw.md`. The tables used here
are typed in `source_tables.csv`. All URLs below were loaded on 2026-11-07. The rows used were
checked against the live pages: LWN 7.3, LWN 6.18 and LWN 6.12 against the articles, and the
LF 2020 table against page 13 and the cover of the PDF.

| Source | Date | Metric | Period | URL |
|---|---|---|---|---|
| LWN.net, J. Corbet, "Development statistics for the 7.3 kernel" | 2026-10-19 | Non-merge changesets and lines changed, by employer (top 20) | v7.2..v7.3 (18,765 changesets, 232 employers) | https://lwn.net/Articles/1100241/ |
| LWN.net, J. Corbet, "Some 6.18 development statistics" | 2025-12-01 | Changesets and lines changed, by employer (top 20) | 6.13 through 6.18, one LTS year (80,035 changesets, 372 employers) | https://lwn.net/Articles/1046966/ |
| LWN.net, J. Corbet, "Development statistics for 6.12" | 2024-11-18 | Changesets and lines changed, by employer (top 20) | 6.7 through 6.12, one LTS year (86,715 changesets) | https://lwn.net/Articles/997959/ |
| The Linux Foundation, K. Stewart, S. Khan, D. M. German, "2020 Linux Kernel History Report" | August 2020 | Commits by organization (top 20, Table 3) | Cumulative, 2007-2019 (780,048 commits, 1,730 organizations) | https://www.linuxfoundation.org/resources/publications/linux-kernel-history-report-2020 (PDF: https://www.linuxfoundation.org/hubfs/Reports/2020_kernel_history_report_082720.pdf) |
| LWN.net, J. Corbet, "Who wrote 2.6.20?" (method) | 2007-02-21 | Defines the employer mapping and the (Unknown) and (None) rows | 2.6.20 | https://lwn.net/Articles/222773/ |

- **Mapping.** All the sources use gitdm or its successor, LWN's Kernel Source Database. They
  credit each commit to the git author. A company address domain maps to the company, and the
  editor adds by hand the affiliations he knows of. These include developers who use personal or
  `kernel.org` addresses, with dates for job changes.
- **Pseudo rows.** "(Unknown)" means no employer could be found. "(None)" means a developer known
  to work on their own time. "(Consultant)" and "(Academia)" are not defined in the articles
  read. All four are in the denominator.
- **Truncation.** Each source lists only its top 20, so an employer outside the top 20 is "not
  listed" (n.l.) and is below about 0.8% (LWN) or 0.78% (LF).
- **No blame-based source.** No public source splits the code alive in the tree by employer. The
  LF 2020 report and LWN's 5.2 article use blame, but only by year or release, not by employer.
  So every comparison below is between a stock (our alive code) and a flow (their changes in a
  period).

## 3. Method

The scripts run in the nix shell of the DuckDB workbench, with `nice -n 15`, DuckDB
`memory_limit = 6GB` and 4 threads.

1. `extract_linux_orgs.py` (run with `RELEASE_ROOT` set to the folder of the release files)
   reads the Linux file once. It writes organization-level counts only:
   - `linux_org_day.csv`: code tokens and surviving commits per committer day, author year,
     organization, AMD register header flag (`drivers/gpu/drm/amd/include/asic_reg/`) and
     `kernel.org` address flag.
   - `linux_org_total.csv`: totals per organization.
2. `source_tables.csv` holds the published rows. Each named employer maps to our
   `organization_id` one to one. The only exception is "Emerson", which maps to
   `emerson-electric` and `national-instruments-corp-de` (NI is part of Emerson since 2023).
   - "HP Enterprise" maps to `hp`, because the tables put `hpe.com` there.
   - Subsidiaries are not rolled up, because LWN lists them apart (for example Linutronix, which
     is under Intel in our tables).
3. `source_windows.csv` matches each source period with a committer-day window, start
   inclusive and end exclusive.
   - LWN 7.3: 2026-06-28 (about v7.2-rc1, when subsystem trees start to collect 7.3 work) to
     2026-10-13 (the pinned commit).
   - LWN 6.13-6.18: 2024-09-29 (v6.12-rc1) to 2025-11-30 (v6.18).
   - LWN 6.7-6.12: 2023-09-10 (v6.6-rc1) to 2024-11-17 (v6.12).
   - LF 2020: 2007-01-01 to 2020-01-01.
   - These windows only approximate LWN's release ranges, which come from the commit graph
     (git log vA..vB), not from dates. Our 7.3 window holds 16,075 surviving commits, against
     LWN's 18,765 changesets.
4. `compare.py` computes our shares for several scopes: all alive tokens; without the pre-git
   import; without the AMD register headers; tokens in the window; surviving commits in the
   window; and `kernel.org` set apart. For each source table and scope it gives the Spearman rho
   over the listed named employers, rho over the source's top 10, and the mean absolute
   difference over the top 10. The outputs are `comparison_summary.csv` and
   `comparison_<source>__<table>.csv`.
5. `make_tables.py` builds `our_top20.md`, `main_table.md` and `main_table.csv`, and
   `correlations.md`, the latter with two-sided permutation p-values (20,000 permutations,
   seed 20261107).

## 4. Our shares (top 20)

Shares of the 162,022,750 alive code tokens. The 7.3 window has 2,471,064 alive tokens.

| Rank | Organization | Share of alive code tokens (%) | Without the pre-git import (%) | Alive tokens with committer date in the 7.3 window (%) |
|---:|---|---:|---:|---:|
| 1 | AMD | 16.33 | 17.52 | 29.40 |
| 2 | Intel | 6.97 | 7.48 | 3.34 |
| 3 | Red Hat | 3.76 | 4.04 | 1.37 |
| 4 | Linux Foundation | 3.62 | 3.88 | 8.12 |
| 5 | Qualcomm | 3.00 | 3.21 | 6.39 |
| 6 | Realtek Semiconductor | 2.49 | 2.68 | 2.25 |
| 7 | Linaro | 2.13 | 2.28 | 0.05 |
| 8 | NVIDIA | 1.57 | 1.68 | 1.30 |
| 9 | IBM | 1.50 | 1.61 | 0.91 |
| 10 | Broadcom | 1.43 | 1.53 | 0.17 |
| 11 | MediaTek | 1.32 | 1.41 | 0.58 |
| 12 | Google | 1.27 | 1.36 | 2.01 |
| 13 | SUSE | 1.18 | 1.26 | 0.32 |
| 14 | Texas Instruments | 1.02 | 1.10 | 0.04 |
| 15 | Mellanox | 1.00 | 1.07 | 0.00 |
| 16 | Oracle | 0.96 | 1.03 | 0.04 |
| 17 | Samsung | 0.94 | 1.00 | 0.05 |
| 18 | NXP | 0.88 | 0.95 | 7.06 |
| 19 | Cirrus Logic | 0.88 | 0.94 | 0.06 |
| 20 | Marvell | 0.82 | 0.88 | 0.68 |
| | (Independent) | 8.86 | 9.51 | 6.85 |
| | (Free e-mail provider) | 8.53 | 9.16 | 10.01 |
| | (Unknown: no real e-mail domain) | 0.00 | 0.00 | 0.00 |
| | (Pre-git import) | 6.80 | 0.00 | 0.00 |
| | No organization (independent + free-provider + unknown) | 17.40 | 18.67 | 16.86 |

- **AMD.** The AMD register headers (`drivers/gpu/drm/amd/include/asic_reg/`) hold 18,516,792
  code tokens, 11.43% of the file and 70% of AMD's tokens. Without them AMD has 7.9 million
  tokens and falls behind Intel (11.3 million) to second place (`linux_org_total.csv`).
- **`kernel.org`.** Addresses at `kernel.org`, which the tables map to the Linux Foundation, hold
  3.46% of all alive code tokens. They hold 8.1% of the alive tokens and 12.4% of the surviving
  commits of the 7.3 window.

## 5. The comparison

### 5.1 Main table

Each "LWN" or "LF" column is the published percent of all changesets, lines changed or commits
in the source period. Each "Ours" column is a share of our measure.

- "All alive tokens": tokens alive at v7.3-rc7, all history.
- "Alive tokens, window": alive tokens whose commit has a committer date in the source window.
- "Surviving commits, window": commits in the window that still own an alive token.

n.l. = not listed in the source's top 20.

| Employer | Ours: all alive tokens | LWN 7.3 lines changed | Ours: alive tokens, 7.3 window | LWN 7.3 changesets | Ours: surviving commits, 7.3 window | LWN 6.13-6.18 lines changed | Ours: alive tokens, 6.13-6.18 window | LF commits 2007-2019 | Ours: surviving commits, 2007-2019 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMD | 16.3 | 22.3 | 29.4 | 6.3 | 5.7 | 6.5 | 7.8 | 2.3 | 2.6 |
| Intel | 7.0 | 4.4 | 3.3 | 6.3 | 5.4 | 10.2 | 9.4 | 10.0 | 9.0 |
| Red Hat | 3.8 | 3.8 | 1.4 | 4.5 | 2.4 | 5.0 | 2.2 | 8.9 | 6.9 |
| Linux Foundation | 3.6 | n.l. | 8.1 | n.l. | 12.6 | 3.0 | 11.4 | 0.8 | 2.7 |
| Qualcomm | 3.0 | 6.1 | 6.4 | 5.9 | 3.6 | 5.5 | 7.6 | n.l. | 1.5 |
| Realtek | 2.5 | 1.6 | 2.2 | n.l. | 0.9 | n.l. | 0.8 | n.l. | 0.2 |
| Linaro | 2.1 | n.l. | 0.1 | n.l. | 0.3 | 3.0 | 2.0 | 3.2 | 2.3 |
| NVIDIA | 1.6 | 1.7 | 1.3 | 2.1 | 2.1 | 2.5 | 3.1 | n.l. | 0.8 |
| IBM | 1.5 | 2.0 | 0.9 | 2.5 | 2.2 | 2.3 | 0.8 | 3.8 | 2.8 |
| Broadcom | 1.4 | n.l. | 0.2 | n.l. | 0.3 | n.l. | 0.8 | 1.2 | 1.0 |
| Google | 1.3 | 5.6 | 2.0 | 6.1 | 3.8 | 7.2 | 3.2 | 2.8 | 1.6 |
| SUSE | 1.2 | n.l. | 0.3 | 1.9 | 1.8 | 3.1 | 1.9 | 3.5 | 3.0 |
| Texas Instruments | 1.0 | n.l. | 0.0 | n.l. | 0.1 | n.l. | 0.5 | 1.8 | 1.6 |
| Mellanox | 1.0 | n.l. | 0.0 | n.l. | 0.0 | n.l. | 0.0 | 1.2 | 1.7 |
| Oracle | 1.0 | n.l. | 0.0 | 1.4 | 0.3 | 1.4 | 0.6 | 1.7 | 1.7 |
| Samsung | 0.9 | 0.8 | 0.0 | n.l. | 0.1 | n.l. | 0.2 | 2.6 | 1.8 |
| NXP Semiconductors | 0.9 | 4.5 | 7.1 | 1.3 | 0.9 | 1.5 | 1.2 | 1.2 | 0.4 |
| Renesas Electronics | 0.7 | 1.2 | 0.3 | 1.3 | 0.8 | 1.2 | 1.0 | 2.0 | 0.7 |
| Huawei Technologies | 0.7 | n.l. | 0.2 | 0.9 | 0.8 | 1.9 | 1.5 | 1.2 | 1.1 |
| Meta | 0.7 | 2.7 | 0.1 | 2.8 | 0.4 | 2.9 | 0.7 | n.l. | 0.4 |
| Arm | 0.6 | n.l. | 0.2 | 1.2 | 0.7 | 1.8 | 1.0 | 1.0 | 1.1 |
| Collabora | 0.5 | 0.8 | 0.7 | n.l. | 0.4 | 1.5 | 1.9 | n.l. | 0.2 |
| HP Enterprise | 0.2 | 1.4 | 0.0 | n.l. | 0.0 | n.l. | 0.0 | n.l. | 0.5 |
| Cloudflare | 0.0 | 1.0 | 0.0 | n.l. | 0.0 | n.l. | 0.1 | n.l. | 0.0 |
| Morse Micro | 0.0 | 1.4 | 2.4 | n.l. | 0.0 | n.l. | 0.0 | n.l. | 0.0 |
| Kylinsoft | 0.0 | n.l. | 0.5 | 3.3 | 3.8 | n.l. | 0.1 | n.l. | 0.0 |
| Emerson | 0.0 | n.l. | 0.0 | n.l. | 0.0 | 1.8 | 0.0 | n.l. | 0.0 |
| Amutable | 0.0 | 1.5 | 0.0 | 1.2 | 0.0 | n.l. | 0.0 | n.l. | 0.0 |
| No organization (sources: Unknown + None + Consultant + Academia; ours: independent + free-provider + unknown) | 17.4 | 18.6 | 16.9 | 27.1 | 34.7 | 13.1 | 20.3 | 19.0 | 28.5 |

The LWN 6.7-6.12 tables give similar results; they are in `comparison_summary.csv`.

### 5.2 Rank correlation and absolute differences

Spearman rho is computed over the named employers that the source lists (its top 20, without the
pseudo rows). All of them are present in our tables. The p-value is from a two-sided permutation
test. The mean absolute difference is over the source's top 10 named employers, in percentage
points.

| Source table | Our measure | n | Spearman rho | permutation p | rho, top 10 of the source | mean abs. difference, top 10 (points) |
|---|---|---:|---:|---:|---:|---:|
| LWN 7.3 lines changed | Alive tokens, 7.3 window | 17 | 0.73 | 0.0014 | 0.68 | 2.18 |
| LWN 7.3 lines changed | All alive tokens (no period) | 17 | 0.67 | 0.0040 | | |
| LWN 7.3 changesets | Surviving commits, 7.3 window | 16 | 0.84 | 0.0001 | 0.89 | 1.15 |
| LWN 7.3 changesets | All alive tokens (no period) | 16 | 0.72 | 0.0024 | | |
| LWN 6.13-6.18 lines changed | Alive tokens, 6.13-6.18 window | 18 | 0.77 | 0.0004 | 0.50 | 2.43 |
| LWN 6.13-6.18 lines changed | All alive tokens (no period) | 18 | 0.74 | 0.0005 | | |
| LF commits 2007-2019 | Surviving commits, 2007-2019 | 17 | 0.65 | 0.0052 | 0.84 | 0.91 |
| LF commits 2007-2019 | All alive tokens (no period) | 17 | 0.54 | 0.0283 | | |

**Top 10 absolute differences** (ours minus source, points), for the closest pairs:

| LWN 7.3 lines: employer | LWN | Ours (alive tokens, 7.3 window) | Diff. |
|---|---:|---:|---:|
| AMD | 22.3 | 29.4 | +7.1 |
| Qualcomm | 6.1 | 6.4 | +0.3 |
| Google | 5.6 | 2.0 | -3.6 |
| NXP Semiconductors | 4.5 | 7.1 | +2.6 |
| Intel | 4.4 | 3.3 | -1.1 |
| Red Hat | 3.8 | 1.4 | -2.4 |
| Meta | 2.7 | 0.1 | -2.6 |
| IBM | 2.0 | 0.9 | -1.1 |
| NVIDIA | 1.7 | 1.3 | -0.4 |
| Realtek | 1.6 | 2.3 | +0.7 |

| LWN 7.3 changesets: employer | LWN | Ours (surviving commits, 7.3 window) | Diff. |
|---|---:|---:|---:|
| AMD | 6.3 | 5.7 | -0.6 |
| Intel | 6.3 | 5.4 | -0.9 |
| Google | 6.1 | 3.8 | -2.3 |
| Qualcomm | 5.9 | 3.6 | -2.3 |
| Red Hat | 4.5 | 2.4 | -2.1 |
| Kylinsoft | 3.3 | 3.8 | +0.5 |
| Meta | 2.8 | 0.4 | -2.4 |
| IBM | 2.5 | 2.3 | -0.3 |
| NVIDIA | 2.1 | 2.1 | -0.0 |
| SUSE | 1.9 | 1.8 | -0.2 |

| LF 2007-2019 commits: employer | LF | Ours (surviving commits, 2007-2019) | Diff. |
|---|---:|---:|---:|
| Intel | 10.0 | 9.0 | -1.0 |
| Red Hat | 8.9 | 6.9 | -2.1 |
| IBM | 3.8 | 2.8 | -1.0 |
| SUSE | 3.5 | 3.0 | -0.5 |
| Linaro | 3.2 | 2.3 | -0.9 |
| Google | 2.8 | 1.6 | -1.2 |
| Samsung | 2.6 | 1.8 | -0.8 |
| AMD | 2.3 | 2.6 | +0.3 |
| Renesas Electronics | 2.0 | 0.7 | -1.3 |
| Texas Instruments | 1.8 | 1.6 | -0.2 |

### 5.3 Sensitivity

The full grid is in `comparison_summary.csv`.

- **Without the pre-git import.** Every share rises by the factor 1/(1 - 0.068). Ranks, and so
  rho, do not change.
- **Without the AMD register headers** (and the pre-git import). Against LWN 6.13-6.18 lines
  changed, the mean absolute difference for all alive tokens falls from 2.93 to 1.62 points. Rho
  changes by less than 0.03 in every table.
- **`kernel.org` set apart** (out of the Linux Foundation, into no organization).
  - LF 2007-2019: rho rises from 0.65 to 0.84 for surviving commits, and from 0.54 to 0.78 for
    all alive tokens. LF lists the Linux Foundation at only 0.78%.
  - LWN 6.13-6.18 lines: rho falls from 0.77 to 0.70. LWN lists the Linux Foundation there at
    3.0%, between our 11.4% with `kernel.org` and about 0.1% without it. So setting `kernel.org`
    apart over-corrects: LWN probably credits part of that work to the Linux Foundation, and the rest to
    the employers of the maintainers.
  - The other tables do not list the Linux Foundation, so rho does not change.

## 6. Why the numbers differ

1. **Metric (stock against flow).** Our measure is the code alive at v7.3-rc7, credited by blame.
   The sources count changes in a period: changesets, or lines added or removed. Deletions,
   moves and code later rewritten count in "lines changed" but leave no alive tokens. Examples
   are Emerson at 1.8% of lines in 6.13-6.18 against 0.0% for us, and Amutable, HP Enterprise
   and Cloudflare in 7.3. Large generated files weigh more in tokens: AMD's register headers are
   11.4% of all alive code tokens. So AMD has 16.3% of the alive code, against 2.3% to 6.5% of
   changesets. Surviving commits are closer to changesets, which is why they correlate best.
2. **Period.** All alive tokens mix 21 years. Companies that were large earlier (Red Hat, IBM,
   SUSE, Texas Instruments, Mellanox, Linaro) keep a stock of old code, and newer contributors
   (Google, Meta, Kylinsoft) have little of it. The committer-day windows match the source
   periods only approximately: LWN uses the commit graph (vA..vB), and some code of a window has
   been rewritten since. Matching the period raises rho for the four main pairs, by 0.03 to
   0.12. The exception is LWN 6.7-6.12 lines, where rho goes from 0.70 to 0.69.
3. **Unknown, independent and none.** The pseudo rows do not measure the same thing.
   - LWN's "(Unknown)" is an author whose employer is unknown. Its "(None)" is an author known to
     be unpaid. Its "(Consultant)" and "(Academia)" are their own rows. So an author who commits
     from a webmail address but is known to work for a company counts for that company in LWN.
   - In the dataset the same commit counts as `free-provider` or `independent`, by design
     (ORGANIZATIONS.md 2.1). Universities and consultancies are organizations of their own.
   - The totals still come close: 16.9% for us against 18.6% for LWN 7.3 lines. For commits the
     gap is larger: 28.5% to 34.7% for us against 19.0% to 27.1% for the sources. The address
     rule moves to "no organization" the commits that LWN's hand mapping gives to employers.
4. **The project address `kernel.org`.** The tables map `kernel.org` to the Linux Foundation, an
   AI-proposed link that passed the checks. Many maintainers employed by Google, Meta, Red Hat,
   Intel and others commit from `kernel.org` addresses, and LWN credits them to their employers.
   With this domain the Linux Foundation has 3.6% of all alive tokens, 8.1% of the 7.3-window
   tokens and 12.6% of the 7.3-window commits; `kernel.org` alone gives 3.5, 8.1 and 12.4 of
   these points. LF lists the Linux Foundation at 0.78%, and LWN 7.3 does not list it.
   It is a likely reason for the low shares of Google and Meta in our data. The global error of
   ERROR.md (2.7% of tokens, with 1.26 points of wrong links) is averaged over all projects, so
   it does not bound a single project such as Linux, where one project domain carries 3.5% of the
   tokens.
5. **Other domain-mapping limits** (ERROR.md).
   - Real organization domains with no row in the tables count as `independent` (1.47 points of
     tokens over the dataset).
   - The dataset does not roll subsidiaries up, and neither do the source rows. Their dated
     mappings can still differ from ours: for example Mellanox after its purchase by NVIDIA, or
     Freescale under NXP.
   - The sources list only 20 employers each, so the correlation is over the source's top 20
     only, and an employer missing from a top 20 cannot be checked.

## 7. Files

| File | Content |
|---|---|
| `extract_linux_orgs.py` | Reads the Linux file and writes organization-level aggregates (needs `RELEASE_ROOT`) |
| `linux_org_day.csv`, `linux_org_total.csv` | The aggregates: organization level, no person data |
| `source_tables.csv`, `source_windows.csv` | Published employer rows with our id mapping; source windows |
| `compare.py`, `comparison_summary.csv`, `comparison_*.csv` | Shares and correlations for all scopes |
| `make_tables.py`, `our_top20.md`, `main_table.md`, `main_table.csv`, `correlations.md` | The tables of this file |
| `sources-raw.md` | Research notes: every source with metadata and full published tables |
| `paper-snippet.tex`, `paper-snippet.bib` | Paragraph, table and BibTeX entries for the paper |

To rerun, from the duckdb-workbench folder:

```
export PATH=/nix/var/nix/profiles/default/bin:$PATH TMPDIR=/tmp
RELEASE_ROOT=<release files> nice -n 15 nix-shell shell.nix --run "python3 -I ../linux-validation-20261107/extract_linux_orgs.py"
cd ../linux-validation-20261107
nice -n 15 nix-shell ../duckdb-workbench/shell.nix --run "python3 -I compare.py && python3 -I make_tables.py"
```
