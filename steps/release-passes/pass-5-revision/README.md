# Pass 5: the revision of TOM 1.0.0 (staged, not run yet)

Pass 5 makes a new root of TOM 1.0.0 and pushes it to the same Hugging Face repository
(`elliancarlos/token-on-me`) as a new revision. The release stays 1.0.0 and the DOI stays
`10.57967/hf/11505`: the pass makes no new DOI. The revision has 8,598 projects: the 8,449
projects of the root of pass 4 and the 149 new projects of `../../selection-funnel/`, built by
`../../new-projects/`. It gives the `license` column the values of `../../license-pass/` and adds
the side table `organizations/project_licenses.parquet`. TOM keeps its 53 columns.

**TODO (revision root):** the pass has not run yet. The `SHA256SUMS` of the new root, its
Hugging Face revision, the row count and the sizes come after the run. Until then
`../../../data/SHA256SUMS` and `../../../data/REBUILD-TARGETS.tsv` describe the root of pass 4.

## What it does

1. It reads the root of pass 4 (8,449 project files, 53 columns, `SHA256SUMS` sha256
   `b7141d088461...`, `inputs/tom4.SHA256SUMS`). It does not change it.
2. It takes the project files of the new-project machines and keeps the 149 projects of
   `inputs/new_projects.tsv` (mapped to the TOM names by `inputs/names.tsv`). A file of a project
   in `inputs/removed.tsv` is dropped. The check is: 149 in, 0 missing, 0 extra, and each file has
   the sha256 of its row of `MANIFEST.new.tsv`.
3. The form gate: each new file must have the Parquet form of a file of TOM (the 53 columns,
   their order and types, the footer keys and their order, the writer, the codecs and encodings,
   the Bloom filter columns, the row groups). The pseudonymization keys can differ (the new batch
   has its own registry); every other footer value must be the value of TOM.
4. License values. The value in each file comes from its footer statistics. The 8,449 projects of
   pass 4 use the stored scans of the license pass, decided by ctp `feat/license-scan` `0f9b8ad`.
   The 149 new projects are scanned again on the machine with the same code and tools. The rule
   (`70_values.py`) gives the column value, then the corrections of the hand check apply (there
   are none). The pass refuses this step without `inputs/AUDIT_OK`.
5. The value pass: only the `license` chunks of the changed files are encoded again
   (`parquet_rename.py --values` of ctp `e9c7656`, then `parquet_rename_check.py` on each file).
   A canary file goes first.
6. The base root: the root of pass 4 plus the new projects: `MANIFEST.tsv`, `SHA256SUMS`,
   `ledgers.parquet`, the rows of the new projects in the tables of `organizations/` (a domain row
   that is in both must be equal), and `pseudonymization.json` with the registry entry and the
   rule of the new batch.
7. The side table `organizations/project_licenses.parquet` (`project`, `license`, `confidence`,
   `evidence_kind`, `version_choice`, `source`) and its view. `release_info` gets the rows and the
   sha256 of each table and the keys `organization_database_version` = 1.0.0 and
   `organization_database_doi` = `10.5281/zenodo.23744044`. The footer key
   `organizations_version` stays `v4.9`, the build tag of the organization database.
8. The documents (`docs/`, staged with the DOI and the release date 2026-11-07): the license text
   of `COLUMNS.md`, `LICENSE.md` section 2, the revision entry of `CHANGELOG.md`, a new
   `docs/LIMITATIONS.md` (the bare CR defect and the batch salt rule), and changes of
   `PRIVACY.md`, `ORGANIZATIONS.md`, `SCHEMA.md` and `README.md`. The pass fills the placeholders
   `[[tom: KEY]]` with measured values.
9. Upload: a new root prefix that must be empty. The unchanged project files of pass 4 get a
   server-side copy. Hugging Face gets the changed and new files in two commits (the data files,
   then `README.md` and `SHA256SUMS`), and the whole tree of the Hub is verified.

## Checks

- `tom5_tools.py check-root`, `fill_release.py check`, `sha256sum -c` of every local file;
  `release_tools.py` `no-at`, `no-paths` and `guard`; `hf_tools.py` `precheck` (10,000 entries for
  each folder) and `validate-card`.
- The run refuses to start until each new-project machine has `status/run.DONE` and the stage has
  `inputs/AUDIT_OK`.

## The local rehearsal (`test-local.sh`)

It uses 3 project files of the test root of pass 4 (libexpat and gnubg as old files, WineGDK as
the new file with a test registry key) and one file of a removed project. Run 1 goes through the
root build and the checks (DONE). Run 2 has no `AUDIT_OK` and stops before the value pass. Run 3
has a project of the list without a file and stops at the new-list step. Run 4 has a new file of
another form and stops at the form gate.

## Files

| File | What it does |
| --- | --- |
| `tom5.conf` | The values: the prefixes, the expected counts, the DOI and the date, the job counts, the limits of Hugging Face. |
| `tom5_start.sh`, `tom5_run.sh` | The start and the driver (steps `preflight`, `fetch`, `newlist`, `shape`, `footers`, `license`, `ledger`, `pseudo`, `fetch2`, `base`, `plan`, `canary`, `pass`, `assemble`, `tables`, `manifest`, `markers`, `checksums`, `view`, `checks`, `upload`, `hf`, `end`). |
| `tom5_tools.py` | The Python steps of the pass. |
| `test-local.sh` | The local rehearsal (not staged). |
| `docs/` | The staged documents with their placeholders. |
| `inputs/license/30_compare.py`, `inputs/license/results.tom4.tsv`, `inputs/names.tsv` | Staged inputs: the comparison tool of the license pass, the stored decisions of the scan of the 8,449 projects, the map from the funnel names to the TOM names. |
| `SHA256SUMS`, `SOURCE` | The staged list (sha256 `fc901a99a7cf03ca72b4ef6af64d2a57a7844de96493116119d499c0d1ae6134`, `WANT_SUMS` of the run) and the stage note. |

`../KITS.tsv` maps each staged file to its copy. The other staged inputs have copies in other
folders: `70_values.py`, `AUDIT_OK` and `corrections.tsv` in `../../license-pass/`;
`new_projects.tsv` and `removed.tsv` in `../../selection-funnel/data/`; the tools of passes 1 and
2, `release_tools.py` and `fill_release.py` as for pass 4. `license_rules.py` and
`license_scan.py` are the files of ctp `0f9b8ad`. `docs/docs/tools.lock` of the stage has the
bytes of the staged copy of pass 4, so it is not here again. The copies of `tom5.conf` and
`tom5_start.sh` differ from the staged files only in the bucket name (`BUCKET_NAME`). The copies of
`inputs/license/30_compare.py` and `70_values.py` have the placeholders `CTP-CHECKOUT` and
`WORK-FOLDER` in the place of two default paths of the work host, and `test-local.sh` has
`LICENSE-PASS-FOLDER` in the place of one.
