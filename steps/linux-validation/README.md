# The Linux kernel validation

A check of the organization column `firm_based_on_domain` against public employer statistics
of the Linux kernel (the LWN.net development statistics and a Linux Foundation report). It
changes no published file. Everything here is at organization level.

| File | What it is |
|---|---|
| `extract_linux_orgs.py` | Reads the Linux kernel file of the release root (`parquet/torvalds__linux-dataset.parquet`) and the organization table, and writes the token and commit counts per organization: `linux_org_total.csv` (whole file) and `linux_org_day.csv` (per committer day, author year, organization and two flags; here `linux_org_day.csv.xz`). |
| `source_tables.csv`, `source_windows.csv` | The published employer tables, typed from the sources, with our organization ids, and the period of each source. |
| `compare.py` | The comparison of each source table with our shares in the same period: `comparison_<source>__<table>.csv`, `comparison_summary.csv` (Spearman correlations, mean absolute differences). |
| `make_tables.py` | The tables `our_top20.md`, `main_table.md`, `main_table.csv` and `correlations.md`. |

## The run

The scripts ran on 2026-11-07 on the run host, on the published release root. The copies here
are the files that ran, byte for byte: `extract_linux_orgs.py` `59cd87516902`, `compare.py`
`24f76f0eaa86`, `make_tables.py` `7c3ec54cbc86`. The uncompressed `linux_org_day.csv` has
sha256 `94f2f8e08a246012ce394b163ed064bd7c7cd30b1569c8e09b163024ef5c49b9`.

The written results:

| File | What it is |
|---|---|
| `RESULTS.md` | The method and the results: the file, the pinned commit, the windows, the tables and the reasons for the differences of level. |
| `sources-raw.md` | The raw extract of the sources: each employer table as published, with its article, date and period. Developer tables were left out. |
| `paper-snippet.tex`, `paper-snippet.bib` | A draft table and the references for the paper. |

The sources are the LWN.net development statistics articles (7.3, 6.18, 6.12 and the method
article "Who wrote 2.6.20?") and the Linux Foundation kernel history report of 2020;
`RESULTS.md` and `paper-snippet.bib` give the full references.

## How to run

```sh
cd steps/linux-validation
xz -dk linux_org_day.csv.xz        # or make it again:
RELEASE_ROOT=ROOT python3 -I extract_linux_orgs.py
python3 -I compare.py
python3 -I make_tables.py           # needs numpy and pandas
```

`extract_linux_orgs.py` needs duckdb and reads the Linux kernel file of the release root.
