# Pass 1: the subset, the first column change and the first upload

Pass 1 made the first root of TOM 1.0.0 from the source root (10,754 project files, ctp
schema 2, 71 columns). It ran on 2026-11-07 on one cloud machine (i4i.8xlarge). It ended DONE.
Its root went to Hugging Face (revision `4c592c54affb`: 8,476 files, 8,447 project files).

## What it does

1. It reads the source root. It does not change it.
2. It keeps the projects of the keep list (`../../language-selection/tokei/projects.keep.txt`,
   8,447 names: the projects whose largest language at the pinned commit is C, C++, Java or Rust).
   It removes the 3 projects of `DROP_PROJECTS` (repositories that are gone). It stops when the
   kept files are not 8,447 files, 30,406,900,014 token rows and 127,424,637,166 bytes.
3. It changes each kept file in one run of `parquet_rename.py`. It drops 10 columns (`size_kb`,
   `file_mask`, `manifest_category`, `fact` and the 6 `history_*` columns). It renames
   `provenance_status` to `audit_frame_file`. It sets the footer key `ctp_schema_version` to 3.
   The result has 61 columns.
4. Before the drop, it reads each dropped column with DuckDB. Each column must hold the value
   that the column review found: empty, `pending` (`manifest_category`) or the one file mask.
   Else the file fails. `fact` is not checked: its values move to a side table.
5. It runs `parquet_rename_check.py` on each file. The first file (`CANARY`, libexpat) runs
   alone first. When it fails, the pass stops.
6. It writes `organizations/project_facts.parquet` (`project`, `fact_type`, `fact_value`: one row
   for each project and fact, from the `fact` text) and its view in
   `organizations/dataset.duckdb`. It filters `project_organizations.parquet` and
   `ledgers.parquet` to the kept projects. It writes the new rows and sha256 values into
   `release_info.parquet`.
7. It copies the release documents and fills their placeholders with measured values (log
   `markers.txt`). `TODO-DOI` stays.
8. It writes `MANIFEST.tsv` (without the column of the run batch) and `SHA256SUMS` with
   `tools/fill_release.py` of the documents.
9. It runs the checks. Only when all pass, it uploads the root to a new, empty storage prefix,
   then to Hugging Face. It verifies each file on Hugging Face against `SHA256SUMS`.

## Inputs

| Input | Value |
|---|---|
| Source root | 10,754 project files, `SHA256SUMS` sha256 `d35e913a0121...` (`SRC_SUMS_SHA` of `tom.conf`) |
| Keep list | `keep/projects.keep.txt` of the stage, sha256 `d971a204c1a4...` |
| Release documents | `docs/` of the stage (not here, see `../README.md`) |
| ctp tools | `parquet_rename.py`, `parquet_rename_check.py` of ctp `467677c8dbc0` |
| Hugging Face token | read at run time from the parameter store into a memory file system; deleted after the upload |

## Checks (before the uploads)

- `tools/fill_release.py check --root R --allow-todo`: schema 3, the footer keys, the
  organization tables, `MANIFEST.tsv`, no at sign, no forbidden word.
- `tom_tools.py check-root`: exactly the kept files (fewer than 10,000 in one folder), 61
  columns in each file, the footer key-values of the source with `ctp_schema_version` 3, the rows
  of the source, `SHA256SUMS` equal to the ledger, `MANIFEST.tsv` equal to the source manifest
  without the column of the run batch, every view of `dataset.duckdb` runs, no marker but `TODO-DOI`.
- `tom_tools.py count`: 8,447 files and 30,406,900,014 rows in the output footers.
- `sha256sum -c` of every row. `release_tools.py no-at`, `no-paths` and `guard`.
- `hf_tools.py precheck` (the limits of the Hub) and `validate-card` (README.md is the card).

## Files

| File | What it does |
|---|---|
| `tom.conf` | The values: the storage prefixes, the expected counts, the column changes, the pins. |
| `tom_start.sh` | Starts `tom_run.sh` as a system unit (or in the foreground with `TOM_LOCAL=1`). |
| `tom_run.sh` | The driver: the steps in order; a step with a DONE mark is skipped on a new start. Its head lists the steps. |
| `tom_tools.py` | The Python steps: `keep`, `count`, `pass` (the audit of the dropped columns, the change and the check of one file), `facts`, `orgs`, `ledgers`, `sizes`, `values`, `keys`, `markers`, `check-root`. Passes 2 and 3 use it too. |
| `hf_tools.py` | The Hugging Face steps: `precheck`, `validate-card`, `upload`, `verify`. Passes 2 and 3 use it too. |
| `parquet_rename.py`, `parquet_rename_check.py` | The ctp tools of commit `467677c8dbc0`. |
| `SHA256SUMS`, `SOURCE` | The staged list and the stage note. |

## Local test (2026-11-07, before the stage)

- The column change and its check passed on 9 local files: 3 release files, 3 DuckDB copies of the
  same projects and 3 variants with Bloom filters.
- The local rehearsal (`TOM_LOCAL=1`) ran all 12 steps on 3 release files and ended DONE (61
  columns, 0 problems in both checks). A second run with a wrong expected value stopped at the
  canary. No other file started.
- The footer statistics of the 8,447 kept files: every dropped column holds the expected value in
  every row group. 3,747 projects have facts (8 types, 4,333 facts).

## How to run

The kit needs a machine with the tools of the setup (see `../README.md`), the source root and the
documents. The values of the run go into `tom.conf` (`BUCKET` and the prefixes). Then:

```sh
mkdir -p /data/tom/tools
cp tom.conf tom_run.sh tom_start.sh tom_tools.py hf_tools.py parquet_rename.py \
   parquet_rename_check.py ../../release-root/release_tools.py /data/tom/tools/
# add keep/projects.keep.txt and docs/ to /data/tom/tools/, then:
TOM_LOCAL=1 SRC_DIR=SOURCE_ROOT HF=0 bash /data/tom/tools/tom_start.sh   # local run: no upload
```

`TOM_LOCAL=1` reads a local source root (`SRC_DIR`) and makes no upload and no shutdown.
