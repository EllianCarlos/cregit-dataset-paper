# Pass 2: two added projects, the value fills and the side tables

Pass 2 made the second root of TOM 1.0.0 from the root of pass 1 (8,447 project files, 61
columns). It ran on 2026-11-07 on one cloud machine (m6id.2xlarge). It ended DONE at
17:04 UTC. Its root went to Hugging Face (revision `e3cda53fb51f`: 8,480 files, 8,449 project
files).

## What it does

1. It reads the root of pass 1. It does not change it. Pass 1 must be DONE.
2. It adds 2 projects: `git.savannah.gnu.org__denemo` and `git.savannah.gnu.org__gnubg`
   (`ADD_PROJECTS`). The tokei run could not fetch their pinned commits by SHA. A second fetch
   over HTTPS got them (`../../language-selection/tokei/savannah-https-retry.jsonl`): the largest
   language of both is C. Their files come from the source root and get the change of pass 1
   (10 dropped columns, the rename, `ctp_schema_version` 3). The audit of the dropped columns of
   pass 1 runs first. The new root has 8,449 project files and 30,408,388,202 token rows.
3. `language`: it fills each empty cell with the tokei language after the Linguist name map
   (`language_tokei_linguist` of `project_languages`). All 161 fills are C, C++ or Java (159 files
   of pass 1 and the 2 new files).
4. `license`: it fills the projects outside GitHub that have a licensee value at confidence 98
   (classes `licensee-98` and `licensee-98-partial`; several values are joined with `;`). That is
   149 files (147 files of pass 1 and the 2 new files). The GitHub projects keep `NOASSERTION`.
5. It writes two side tables, each with a view in `organizations/dataset.duckdb`:
   `project_languages.parquet` (9 columns, 8,449 rows) and `project_labels.parquet` (7 columns,
   8,449 rows). `release_info.parquet` gets 5 new keys (the rows and sha256 of the two tables and
   `dataset_db_sha256`). Its `ctp_schema_version` changes from 2 to 3: pass 1 kept the build value.
6. It changes 183 files of pass 1 (36 language only, 24 license only, 123 both) with
   `parquet_rename.py --values`. The tool encodes again only the chunks of `language` and
   `license`, and copies all other bytes. It refuses a file when the column does not hold the old
   value. `parquet_rename_check.py` proves each file.
7. The other 8,264 project files do not change. The machine reads only their footers. The new
   root gets them by a server-side copy from the root of pass 1. They are not uploaded to Hugging
   Face again.

`inputs/fills.tsv` lists every fill (`project`, `column`, `old`, `new`, `basis`: 310 rows).
`inputs/prepare.json` gives the counts of the inputs. `tom2_tools.py prepare` made both from the
value-fix tables (`../value-fixes/`), the keep list and the HTTPS retry.

## Inputs

| Input | Value |
|---|---|
| Root of pass 1 | 8,447 project files; the sha256 of its `SHA256SUMS` comes from the final status of pass 1 |
| Source root | for the 2 added files, `SHA256SUMS` sha256 `d35e913a0121...` |
| Fills and side tables | `inputs/` of the stage (`inputs/fills.tsv` `2878e5437457`; the two Parquet inputs are not here, see `../README.md`) |
| Release documents | `docs/` of the stage (not here) |
| ctp tools | `parquet_rename.py`, `parquet_rename_check.py` of ctp `e9c7656e59c1` |

## Checks (before the uploads)

- `fill_release.py check` of the check view (all 8,449 files: schema 3, the footer keys, 9
  organization tables, `MANIFEST.tsv`, the text rules).
- `tom2_tools.py check-root`: exactly 8,449 files with 61 columns and the footer key-values of
  pass 1; 30,408,388,202 rows; no empty or null `language` (footer statistics); every fill is in
  the footer statistics; the unchanged footers are the footers of pass 1; `SHA256SUMS` and
  `MANIFEST.tsv` agree with the ledger and the footers; every view runs; the side tables,
  `project_organizations` and `ledgers.parquet` have exactly the 8,449 projects; every
  `release_info` key agrees with its measured value.
- `sha256sum -c` of every local file. `release_tools.py no-at`, `no-paths` and `guard`.
  `hf_tools.py precheck` and `validate-card`.
- After the storage upload: one object for each file, with its size.
- Hugging Face: before the push, the Hub must hold the root of pass 1. After the push, every file
  of the Hub tree is verified against the new `SHA256SUMS`.

## The run

A start stopped at the storage upload: the server-side copy of the large unchanged files needed
a permission that the machine did not have. The driver was fixed
(`--copy-props metadata-directive`) and staged again (the staged list here, `d4e286a5ca6c`). A
new start continued after the DONE steps and ended DONE. The earlier starts used earlier staged
lists. Their files are not here: the copies here are the files of the last start. The earlier
lists record `tom2_run.sh` `0772559ae7bd` (before the fix) and `tom2_tools.py` `d6a649173c82`
(before a fix of a footer key check).

## Files

| File | What it does |
|---|---|
| `tom2.conf` | The values: the prefixes, the added projects, the expected counts, the side tables, the pins. |
| `tom2_start.sh`, `tom2_run.sh` | The start and the driver (steps `preflight` to `end`; the head of `tom2_run.sh` lists them). |
| `tom2_tools.py` | The Python steps: `prepare`, `keep`, `footers`, `plan`, `pass`, `facts`, `tables`, `manifest`, `sums`, `view`, `values`, `keys`, `check-root`, `hf-push`. Pass 3 uses it too. |
| `parquet_rename.py`, `parquet_rename_check.py` | The ctp tools of commit `e9c7656e59c1`. Pass 3 uses them too. |
| `inputs/fills.tsv`, `inputs/prepare.json` | The fills and the input counts. |
| `SHA256SUMS`, `SOURCE` | The staged list and the stage note. |

`tom_tools.py` and `hf_tools.py` of the stage are the files of `../pass-1/`.

## Local test (2026-11-07, before the stage)

- The ctp tool of `e9c7656e59c1` on 7 files: the change of pass 1 is byte-identical to the
  output of `467677c8dbc0`; the value pass and its check pass.
- The local rehearsal ended DONE (16 steps) on 5 files (3 files of pass 1 and the 2 new files).
  Three negative runs stopped as planned: a wrong `manifest_category` (the canary of the new
  files), a wrong old value (the plan step), and a root with a stale `release_info` key
  (`check-root`).

## How to run

As for pass 1 (`../pass-1/README.md`), with these files in the tools folder: `tom2.conf`,
`tom2_run.sh`, `tom2_start.sh`, `tom2_tools.py`, `parquet_rename.py`,
`parquet_rename_check.py` of this folder, `tom_tools.py` and `hf_tools.py` of `../pass-1/`,
`../../release-root/release_tools.py`, `keep/projects.keep.txt`, `inputs/` and `docs/`.
`TOM_LOCAL=1` with `TOM1_DIR` and `SRC_DIR` (local roots) runs the pass with no upload.
