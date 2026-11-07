# Pass 3: the proof on every row and the drop of 8 columns

Pass 3 makes the final root of TOM 1.0.0 from the root of pass 2 (8,449 project files, 61
columns). It runs on one cloud machine (i4i.8xlarge). **It had not ended when these files were
copied (2026-11-07).** Its final `SHA256SUMS` and the files of `../../../data/` come in a later
commit.

## What it does

1. It reads the root of pass 2. It does not change it. Pass 2 must be DONE. Each fetched file must
   agree with its row of `SHA256SUMS`.
2. Before any drop, it proves on every row of every file the facts that permit each drop (step
   `prove`, DuckDB). Each count must be 0:

   | Column | Rule (all rows of the file) |
   |---|---|
   | `person_name` | `person_name IS NOT DISTINCT FROM replace(personid, 'author ', 'Author ')` |
   | `person_email` | `person_email IS NOT DISTINCT FROM CASE WHEN personid IS NOT NULL THEN author_email END` |
   | `footer_person_names` | `footer_person_names IS NOT DISTINCT FROM list_transform(footer_personids, x -> replace(x, 'author ', 'Author '))` |
   | `cregit_commit_sha` | one to one with `original_commit_sha` (NULL counts as a value) |
   | `repo_tag` | `repo_tag = ''` |
   | `archived`, `fork` | only `False` or `''`; the files per value: `False` 8,288 and `''` 161 |
   | `roster_lang` | one value in the file; the value goes to `project_facts` |

   A failed rule on any file stops the run. Then no other file is dropped and nothing is
   uploaded. The proof lines (`log/proof.jsonl`) hold counts only, no value of a person column.
3. It drops the 8 columns from all 8,449 files with `parquet_rename.py --drop`. The files get 53
   columns. The tool copies the other column chunks byte for byte. There is no rename and no new
   key-value: `ctp_schema_version` stays 3.
4. `roster_lang` moves to `organizations/project_facts.parquet` as the fact type
   `roster_language`: one row for each project with a non-empty value (135 projects, all of
   rosters of the Apache Software Foundation). The value is the cell as it is (for example
   `asf:Java, C`).
5. `release_info.parquet` keeps its 27 keys. Only `project_facts_rows` and
   `project_facts_sha256` change. `organizations/dataset.duckdb` does not change: no view names a
   dropped column.
6. `MANIFEST.tsv`: the rows of pass 2 with new `bytes` and `sha256`. All project files change, so
   the root and Hugging Face get all files again.

## Inputs

| Input | Value |
|---|---|
| Root of pass 2 | 8,449 project files, 61 columns, 127,360,411,332 bytes; the sha256 of its `SHA256SUMS` comes from the final status of pass 2 |
| Release documents | `docs/` of the stage (not here); its `tools/fill_release.py` checks 53 columns (`../fill-release/`) |
| ctp tools | `parquet_rename.py`, `parquet_rename_check.py` of ctp `e9c7656e59c1` (the files of `../pass-2/`) |
| Tools of the earlier passes | `tom_tools.py` and `hf_tools.py` (`../pass-1/`), `tom2_tools.py` (`../pass-2/`), `release_tools.py` (`../../release-root/`) |

## Checks (before the uploads)

- `fill_release.py check --root R --allow-todo`: 53 columns, schema 3, the footer keys, the
  organization tables, `MANIFEST.tsv`, the text rules.
- `tom3_tools.py check-root`: exactly 8,449 files; each footer has the 53 kept columns of its
  footer of pass 2 in order, with the same types, rows, row groups and key-values; no footer has
  a dropped column; every file has an OK ledger line and an OK proof line; 30,408,388,202 rows;
  `SHA256SUMS` lists every file and each project row differs from pass 2; the other files of the
  root are the bytes of pass 2; `MANIFEST.tsv` differs from pass 2 only in `bytes` and `sha256`;
  every view runs and no view names a dropped column; `project_facts` is the rows of pass 2 plus
  the roster facts of the proof; every `release_info` key agrees with its measured value.
- `sha256sum -c` of every file. `release_tools.py no-at`, `no-paths` and `guard`.
  `hf_tools.py precheck` and `validate-card`.
- Hugging Face: before the push, the Hub must hold the root of pass 2. After the push, every
  file of the Hub tree is verified against the new `SHA256SUMS`. A file on the Hub that is not in
  `SHA256SUMS` is a failure.

## Files

| File | What it does |
|---|---|
| `tom3.conf` | The values: the prefixes, the drop list, the expected counts and values, the pins. |
| `tom3_start.sh`, `tom3_run.sh` | The start and the driver (steps `preflight`, `fetch`, `keep`, `canary`, `prove`, `proof`, `pass`, `assemble`, `facts`, `release`, `manifest`, `markers`, `checksums`, `checks`, `upload`, `hf`, `end`). |
| `tom3_tools.py` | The Python steps: `keep`, `prove`, `proof-sum`, `pass`, `facts`, `release-info`, `values`, `keys`, `check-root`. |
| `SHA256SUMS`, `SOURCE` | The staged list and the stage note. |

## Local test (2026-11-07, before the stage)

- The local rehearsal ended DONE (15 steps) on 5 files (53,574,263 rows): 53 columns, the canary
  first, 27 `release_info` keys with only the 2 `project_facts` keys changed, 15 views run,
  `check-root` 0 problems. The output of libexpat is `SMOKE_OUT_SHA` of `tom3.conf`.
- Four negative runs stopped as planned: a wrong copy mode (the canary), files that break a rule
  (one file for each of `person_name`, `cregit_commit_sha`, `archived` and `repo_tag`: the run
  stops at `prove`, only the canary is dropped), a wrong roster count (the `proof` step), and a
  broken root (`check-root` finds a 61-column file, a stale `project_facts_sha256` and a view that
  names a dropped column).

## How to run

As for pass 1 (`../pass-1/README.md`), with the files of the table "Inputs" and of this folder
in the tools folder. `TOM_LOCAL=1` with `TOM2_DIR` (a local root of pass 2) runs the pass with
no upload.
