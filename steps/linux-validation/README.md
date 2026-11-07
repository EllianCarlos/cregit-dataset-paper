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

Another session was still working on this folder when these files were copied. The copy has
the files that existed then. Not copied: the written results (`RESULTS.md`), the raw extract
of the sources (`sources-raw.md`) and a draft paper snippet, because they name the author of
the cited articles. `source_tables.csv` and `source_windows.csv` hold the numbers of the
sources; the sources are the LWN.net articles "Development statistics for the 7.3 kernel",
"Some 6.18 development statistics", "Development statistics for 6.12", the method article
"Who wrote 2.6.20?", and the Linux Foundation kernel history report of 2020.

## How to run

```sh
cd steps/linux-validation
xz -dk linux_org_day.csv.xz        # or make it again:
RELEASE_ROOT=ROOT python3 -I extract_linux_orgs.py
python3 -I compare.py
python3 -I make_tables.py           # needs numpy and pandas
```

`extract_linux_orgs.py` needs duckdb and reads the Linux kernel file of the release root.
