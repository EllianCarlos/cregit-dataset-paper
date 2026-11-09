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
These values of the integrity check (section "The integrity check") are also pending, because
the check did not run yet:

- the result line of `docs/INTEGRITY.md` (files, bytes, token rows, views, problems) and the
  time of the check;
- the sha256 of `SHA256SUMS` before the publish step (the value of `log/final.status.json`) and
  after it (the value of `publish.json` of the integrity run);
- the Hugging Face revision of the commit that adds `docs/INTEGRITY.md` and `docs/integrity.tsv`.

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

## The machine setup (`machine/R1-tom5-setup.sh`) and the run order

The setup script makes the disks, the Python environment and the scanner tools of the license
pass on the machine. Then it does two smoke tests: ScanCode on one small license file, and a
value pass of one small file of pass 4. It starts nothing.

A defect of the staged kit, found on the machine: the smoke test of ScanCode used a license file
with only the first line of the MIT text. ScanCode gave
`MIT AND LicenseRef-scancode-proprietary-license`, not `MIT`, so the setup stopped. The fix: the
smoke test now writes the full MIT text. The setup then gave `MIT` and passed. The setup script is
not in the staged list, so `WANT_SUMS` did not change. `machine/R1-tom5-setup.sh` is the fixed
script that ran. `../KITS.tsv` (pass `pass-5-machine`) gives its sha256 and the sha256 of the
copy; the copy has `BUCKET_NAME` in the place of the bucket name and `REFUSED_INSTANCE_IDS` in the
place of the list of EC2 instances that the setup must refuse. The sha256 of the script before
the fix is `5caf28822454222a869ab703f18f60957654fc30a39506e058e83365611784c2`.

The run order: put the Hugging Face token into the SSM parameter `/tom/hf-token` (`HF_SSM_PARAM`
of `tom5.conf`) before you start the run. The step `preflight` looks for the parameter and
stops the run with an ALERT when it is not there.

## The integrity check (`integrity/`)

DuckDB and Parquet have no command like `PRAGMA integrity_check` of SQLite.
`integrity/integrity_check.py` does this work for a local copy of a TOM root. It reads every
byte of the root. It does these checks:

1. Each row of `SHA256SUMS`: the file is in the root and its sha256 is the sha256 of the row. A
   project file must also agree with its row of `MANIFEST.tsv`. A file of the root that is not in
   `SHA256SUMS` is a problem.
2. The footer of each Parquet file parses. A project file has the 53 columns of TOM, in their
   order and with their types, and the footer keys of the reference file
   (`parquet/tio__tio-dataset.parquet`). Each footer value other than the `pseudonymization_*`
   keys is the value of the reference file.
3. A full decode of each Parquet file: every row group, every column chunk and every page, one row
   group at a time (pyarrow). The tool validates the decoded arrays. It compares the null count,
   the minimum and the maximum of each flat column chunk with the footer statistics. DuckDB cuts
   the string statistics at 256 bytes, so for a string column the tool accepts a statistic that is
   a prefix of the value that it read.
4. The page CRC, when the file has one. DuckDB writes no page CRC, so for most files the report
   says `not written`. For these files the sha256 of step 1 is the byte check.
5. The rows: the rows that the tool read are the footer rows. For a project file they are also its
   rows of `MANIFEST.tsv`; for a side table they are its rows in `release_info`. The side tables
   of `organizations/` are read in full, as the project files are.
6. `organizations/dataset.duckdb` opens read-only, and each view runs `SELECT count(*)`. The view
   `tokens` must have the total rows of `MANIFEST.tsv`. Each `tokens_*` view must have the rows of
   `tokens`.

The output (`--out`) is `integrity.tsv` (one row for each file), `integrity.json` and
`INTEGRITY.md`. The exit status is 0 only when there are 0 problems.

```sh
python3 -I integrity_check.py check --root ROOT --out OUT --jobs 16
```

The tool needs pyarrow 26.0.1 and DuckDB 1.5.5, the versions of `tom5.conf`.

### The local test

`integrity/integrity-test-local.sh` runs on a local host with no cloud access. Set `PY` to a
Python with pyarrow 26.0.1 and DuckDB 1.5.5. The test has 8 cases:

- 7 cases on small roots in the TOM form that `test/integrity_fixtures.py` makes. The good root
  must pass. These 6 bad roots must fail, with the expected column of `integrity.tsv` set to
  `no`: a flipped byte in a data page; a flipped byte with a new sha256 in `SHA256SUMS` and
  `MANIFEST.tsv`, in a file with page CRCs and in a file without them (the decode must find it);
  a file with its last 200 bytes cut; a file with another column type and a new sha256; a file
  that is not in `SHA256SUMS` together with a missing file.
- 1 case on the root of the last local rehearsal of the pass (`test-local.sh`: 3 project files,
  41,608,398 rows, the real `dataset.duckdb` with its 16 views): it must pass.

All 8 cases pass (2026-11-09). The rehearsal root took 53 s with 4 jobs.

### The run on the machine

The check runs on the machine of the pass, after the run is DONE, with a hold set, so the machine
does not stop. The order:

1. The user uploads `integrity_check.py` to the integrity folder of the bucket
   (`U2-tom5-integrity-upload.sh`). The script checks the sha256 before and the size after.
2. `I1-tom5-integrity.sh` with `ACTION=start`. It refuses to start when the run is not DONE, when
   no hold is set, when a shutdown is scheduled, when the venv has other versions, when the disk
   is too small, or when `integrity_check.py` is not the pinned file (`WANT_CHECK`). It downloads
   the published root from the bucket, compares the files with the bucket listing (path and size)
   and compares `SHA256SUMS` with the value of `log/final.status.json`. Then it runs the check
   with all vCPUs and uploads the report to `integrity/run-<utc>/` of the bucket (never into
   `root/`). `ACTION=status` gives the state.
3. `I2-tom5-integrity-publish.sh`, first with `ACTION=plan`, then with `ACTION=publish`. It
   publishes only a report with 0 problems. It adds the report to the root as
   `docs/INTEGRITY.md` and `docs/integrity.tsv`, with a new `SHA256SUMS` (the old rows and 2 new
   rows; no other row changes). In the bucket it keeps a copy of the old `SHA256SUMS` and uploads
   `SHA256SUMS` last. On Hugging Face it makes one commit with the 3 changed files and then
   verifies the whole tree. It does not change the visibility and makes no DOI. `MANIFEST.tsv`
   lists only `parquet/` files, so it does not change.

Expected time on one m6id.4xlarge (16 vCPU): about 2 to 2.5 hours for the download and the check
of the full root.

After the publish step, `log/final.status.json` of the run keeps the sha256 of the earlier
`SHA256SUMS` (the root that the check read). `publish.json` of the integrity run gives the sha256
before and after the publish step.

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
| `machine/R1-tom5-setup.sh` | The setup of the machine (section "The machine setup"), with the fix of the scanner smoke test. |
| `integrity/integrity_check.py` | The integrity check of a root (section "The integrity check"). `I1-tom5-integrity.sh` pins its sha256 (`WANT_CHECK` `1c9ea571592f...`). |
| `integrity/I1-tom5-integrity.sh`, `integrity/I2-tom5-integrity-publish.sh`, `integrity/U2-tom5-integrity-upload.sh` | The check on the machine, the publish step of the report, and the upload of the checker by the user. |
| `integrity/integrity-test-local.sh`, `integrity/test/integrity_fixtures.py` | The local test (8 cases) and the small test roots. |

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

The files of `integrity/` are not in the staged list: the integrity check came after the stage.
`../KITS.tsv` gives each one (pass `pass-5-integrity`) with the sha256 of the file in the work
folder and of the copy. The copies of `I1-tom5-integrity.sh` and `I2-tom5-integrity-publish.sh`
have the placeholder `INSTANCE_ID` in the place of the default EC2 instance id. The copy of
`U2-tom5-integrity-upload.sh` has `BUCKET_NAME` and `AWS_PROFILE_NAME` in the place of the bucket
name and the AWS profile. The other files have the bytes of the work folder. Part 2 of the local
test reads the output of `test-local.sh` (`test/work.*/x1/root/`) and one project file of the test
root of pass 4, with the default paths of the work host.
