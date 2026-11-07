# The release passes of Token on Me (TOM) 1.0.0

The dataset "Token on Me" (TOM), version 1.0.0, is on Hugging Face
(`elliancarlos/token-on-me`, public). Three release passes made its root from the source root.
The source root has 10,754 project files (ctp schema 2, 71 columns). It is the output of the
steps `../final-write/`, `../release-root/` and `../reencode/`. Each pass reads the root of the
step before it, writes a new root and does not change its input. Each pass ran unattended on one
cloud machine, from one kit of scripts. The kit stops at the first failed check, before the
uploads.

| Pass | Input | What it does | Output |
|---|---|---|---|
| `pass-1/` | the source root | Keeps the 8,447 projects of the tokei language rule. Drops 10 columns and renames `provenance_status` to `audit_frame_file` (71 -> 61 columns). Sets `ctp_schema_version` to 3. Writes `organizations/project_facts.parquet`. Uploads the root to Hugging Face. | 8,447 project files, 61 columns |
| `pass-2/` | the root of pass 1 | Adds `git.savannah.gnu.org__denemo` and `git.savannah.gnu.org__gnubg`. Fills 161 empty `language` cells (tokei) and 149 `license` cells (licensee 9.18.0 at confidence 98, projects outside GitHub). Adds the side tables `project_languages` and `project_labels`. | 8,449 project files, 61 columns, 9 organization tables |
| `pass-3/` | the root of pass 2 | Proves a rule on every row of every file, then drops 8 more columns (61 -> 53). Moves `roster_lang` to `project_facts` (fact type `roster_language`). | 8,449 project files, 53 columns |

The folders of this step:

| Folder | Contents |
|---|---|
| `pass-1/`, `pass-2/`, `pass-3/` | The staged kit of each pass: its configuration, its driver, its Python tools, the staged list `SHA256SUMS` and the stage note `SOURCE`. A README for each pass. |
| `fill-release/` | `tools/fill_release.py` of the TOM root (53 columns, 9 organization tables) and its test. |
| `value-fixes/` | The scripts and the tables of the value fixes of pass 2 (language and license fills, side tables). |
| `schema3-proof/` | The proof that ctp now writes the 53-column schema in a normal run: a rebuild of 2 projects, compared with the output of the passes. |
| `KITS.tsv`, `check-kits.sh` | For each file of each staged list: the sha256 that ran, the copy in this repository and its sha256. The check script compares them. |

## The staged files

Each kit had a stage folder. The stage held the tools of the machine and a list `SHA256SUMS`.
The run started only when the sha256 of that list was the value pinned in its start script
(`WANT_SUMS`). So the staged list names the exact bytes that ran:

| Pass | sha256 of the staged list | Staged |
|---|---|---|
| 1 | `7b1187384ebb669e64b67ced1b773bcb6def4ac91e3242c99b52113c8c13b684` | 2026-11-07 03:48 UTC |
| 2 | `d4e286a5ca6c0799e24dd0d915e8058baf8bf62e89204418eda74469daf17cf4` | 2026-11-07 16:48 UTC |
| 3 | `e142c5a982ad0fc1ef5431d2aa7daf9670765491ae6a2d6689986ea39a599201` | 2026-11-07 18:07 UTC |

`KITS.tsv` maps each row of each list to its copy. A file that two passes staged with the same
bytes has one copy: the copy of the first pass that staged it. `release_tools.py` is
`../release-root/release_tools.py` (the same sha256). The keep list is
`../language-selection/tokei/projects.keep.txt`. `fill_release.py` of pass 3 is
`fill-release/tools/fill_release.py`.

Replaced values: the copies of `tom.conf`, `tom2.conf`, `tom3.conf`, `tom_start.sh`,
`tom2_start.sh` and `tom3_start.sh` differ from the staged files in one line each. The name of
the storage bucket became the placeholder `BUCKET_NAME`. No other byte changed. `KITS.tsv` gives
the sha256 of the staged file and of the copy.

Not here:

- The release documents of each stage (`docs/`). They hold placeholders (`[[tom: KEY]]`). Each
  pass fills them with measured values and writes the filled copies into its root. The final
  documents are in the root of pass 3.
- `source.SHA256SUMS` of passes 1 and 2: the list of the source root.
- The two side-table inputs of pass 2 (`inputs/project_languages.parquet`,
  `inputs/project_labels.parquet`). Pass 2 copies them byte for byte to `organizations/` of its
  root, and pass 3 keeps them.
- The kit scripts that ran on the local host or sent commands to the machine: the stage script,
  the upload of the stage, the launch, the remote command script, the setup, the start, the
  progress and the hold scripts, the local rehearsals and the list of machines that a kit must
  refuse. These scripts hold the run values (the account, the bucket, the machines). The setup
  script made the disks and the Python environment (pyarrow 26.0.1, DuckDB 1.5.5,
  huggingface_hub 2.4.0, hf-xet 1.8.0, the values of each configuration file), copied the stage
  and ran the smoke test of the configuration (`SMOKE`, `SMOKE_OUT_SHA`).

## The column tools

The passes change the files with two tools of ctp (`tools.lock`, rows `release-pass-tool`):

- `parquet_rename.py` drops and renames columns and sets footer key-values. It copies the column
  chunks that it keeps byte for byte; no page is encoded again. With `--values` it encodes again
  only the chunks of the columns whose values change (pass 2).
- `parquet_rename_check.py` proves each output file against its input: the kept chunks have the
  same bytes, the footer is the old footer minus the dropped columns, and pyarrow, DuckDB and the
  Bloom filters read the file.

Pass 1 used ctp commit `467677c8dbc0f8a794c6ef7517daca8941582b58`. Passes 2 and 3 used ctp
commit `e9c7656e59c18316cda1b83acf81cb1d8fc9bca6`. The outputs of the two commits are
byte-identical for the change of pass 1 (the local test of pass 2).

## Check

```sh
steps/release-passes/check-kits.sh
```

`make stage-hashes` runs it too.

## Tests

`make test` runs `fill-release/test/`. The kit tools have no unit tests here: each kit ran a
local rehearsal on a few release files before the stage (see the README of each pass). The
rehearsals read local release files, so they are not here.
