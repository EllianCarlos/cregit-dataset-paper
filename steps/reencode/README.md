# The re-encode of the project files

The re-encode wrote each of the 10,754 project files again with pyarrow, with no data change:
the same rows in the same order, the same columns, types and footer key-values. Only the
encoding changed, and the files became 84.4% of their size (162,466,431,130 B to
137,087,040,565 B). The release root build then ran again on the new files
(`../release-root/`, `reencode-chain` and `reencode-root`).

## The tool

The tool is now a generic step of ctp: `reencode_parquet.py`, with its documentation
`docs/REENCODE.md` and its tests, in ctp commit `c2a8432a1911` (branch
`feat/parquet-reencode`). Its defaults are the settings of this run, and they give the same
settings sha256 `e98a53aed203` when the 5 footer keys of the dataset are given
(`docs/REENCODE.md` of ctp). The ctp copy is changed for general use: every setting is an
option, the cloud storage parts are gone, and two check names changed (`zstd` is
`compression`, `pages_v1` is `page_version`; the log here has the old names, log version 1).

Two versions of the run script made the files (field `versions.reencode_sha256` of each log
line):

| Script sha256 | Files | Note |
|---|---|---|
| `06f2f1c00dfb` | 10,753 | The first pass, read batch 262,144 rows. |
| `99b7596b2806` | 1 (`LibreOffice__core`) | The first pass failed on this file (a DuckDB string buffer limit), so the script got `--read-batch` and `--read-batch-for`, and the file ran again with read batch 32,768 rows. |

## The run record

| File | What it holds |
|---|---|
| `reencode-log.jsonl.xz` | One JSON line for each file and attempt (10,755 lines: 10,754 OK and the failed first attempt above). sha256 of the uncompressed log: `ae64dfb92f7a18b2b233c2a0122ab6448a4791831ef6ff32a4f30e16b638cda0`, the log that the root build staged. Each OK line gives the input and output sha256, the rows, the content fingerprint (a hash of each row summed, a hash of each column, an order hash), the result of each check, the footer key-values and the versions. |
| `summary.json` | The counts of the run: 10,754 files OK, 0 failures, rows 32,635,174,618, the settings sha256, the script versions. |
| `env.txt` | Python 3.12.14, duckdb 1.5.5, pyarrow 26.0.1, the settings sha256, the machine type. |

The settings sha256 of all lines is
`e98a53aed2038837fae2cf20d9de407729517f9290faaa44ab33c3762c9fcfbb`: pyarrow 26.0.1, data page
V1, ZSTD level 19, row groups of 1,000,000 rows, pages of 8 MB, PLAIN for `token_value`,
`source_text` and `source_col`, DELTA_BINARY_PACKED for `token_index` and `source_line`,
dictionaries for the other columns, Bloom filters on `file_path`, `token_value`,
`source_text`, `cregit_commit_sha` and `personid`, and the row order kept.

The run ran on one cloud machine on 2026-11-05 and 2026-11-06. The scripts that set up the
machine, started the run, watched it and moved the files are not here.

## How to check a file

```sh
xz -dc reencode-log.jsonl.xz | sha256sum   # ae64dfb92f7a...
xz -dc reencode-log.jsonl.xz | grep '"file":"libexpat__libexpat-dataset.parquet"'
sha256sum ROOT/parquet/libexpat__libexpat-dataset.parquet   # the out_sha256 of the OK line
```

With ctp at `c2a8432`, `reencode_parquet.py settings` prints the writer settings and their
sha256, and `reencode_parquet.py one` re-encodes one file and runs the same content check
(`docs/REENCODE.md` of ctp).
