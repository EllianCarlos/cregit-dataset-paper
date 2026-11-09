# Pass 5: the revision of TOM 1.0.0 (done on 2026-11-09)

Pass 5 makes a new root of TOM 1.0.0 and pushes it to the same Hugging Face repository
(`elliancarlos/token-on-me`) as a new revision. The release stays 1.0.0 and the DOI stays
`10.57967/hf/11505`: the pass makes no new DOI. The revision has 8,598 projects: the 8,449
projects of the root of pass 4 and the 149 new projects of `../../selection-funnel/`, built by
`../../new-projects/`. It gives the `license` column the values of `../../license-pass/` and adds
the side table `organizations/project_licenses.parquet`. TOM keeps its 53 columns.

## The result (2026-11-09)

The run ended DONE at 2026-11-09 17:00 UTC on one m6id.4xlarge machine (16 vCPU), after two
ALERTs, their fixes and a restart (section "What went wrong and how it was fixed").

| Item | Value |
| --- | --- |
| Root | `dataset-release/dataset-v1.0.0-tom-5/root/` of the bucket; 8,627 objects before the publish step of the integrity check, which added 2 files |
| Project files | 8,598 (8,449 of pass 4 and 149 new), 53 columns, 31,603,701,581 token rows, 116,839,509,483 bytes; the root has about 116.85 GB |
| `MANIFEST.tsv` | 8,598 rows |
| `license` | 3,607 files got another value; 703 files have `NOASSERTION` |
| Side tables | `organization_domains` 10,930 rows (10,899 and 31 new); `project_organizations`, `project_labels`, `project_languages` and `project_licenses` 8,598 rows each |
| `SHA256SUMS` after the run | sha256 `a453d5f10aa2806af0a97d68e574b5c5fa9bc99c6283d87fbfb6db7b2bd16b80`, 8,626 rows (the value of `log/final.status.json`) |
| `SHA256SUMS` after the integrity publish | sha256 `ea2052f7ce8b764d4e54a940d71f3fd8d04b827b2db08a4d2dc0c38f7dcbf48d`, 8,628 rows (the old rows and `docs/INTEGRITY.md`, `docs/integrity.tsv`; the value of the publish record of the integrity run). `../../../data/SHA256SUMS` has these rows. |
| The staged list | sha256 `da9125463a33d480755cdcb9ec91f6a6fab8292d4e73667785c1d3ed12fb43f6` (`SHA256SUMS` of this folder, `WANT_SUMS` of the run that ended DONE) |

The Hugging Face revisions of `elliancarlos/token-on-me` (public):

| Revision | What it has |
| --- | --- |
| `e81b554deb9b` | The root of pass 4 (the first revision of TOM 1.0.0). The DOI `10.57967/hf/11505` marks this revision. |
| `500bd0bb00e8` | 16:47 UTC: the data files of pass 5 without 7 changed files of the root (a mixed state, about 10 minutes; fix 4 below). |
| `46a123047ef2` | The run DONE: the full root of pass 5. The verify step of the Hub tree passed (8,627 files). |
| `5e20f9ff2a18fe155f14606da0d61d516baedd6a` | The publish step of the integrity check: `docs/INTEGRITY.md`, `docs/integrity.tsv` and the new `SHA256SUMS`. This is the final revision. |

DOI of the final revision: pending. The user can make a new DOI on Hugging Face for this
revision; `10.57967/hf/11505` stays the DOI of the first revision.

The integrity check (section "The integrity check") ran on the machine of the pass after the
run (run `20261109T170212Z`, checker sha256 `1c9ea571592f...`). The report is in
`integrity/run-20261109T170212Z/` of the pass prefix of the bucket (`INTEGRITY.md`,
`integrity.tsv`, `integrity.json`, `check.log`) and in the root as `docs/INTEGRITY.md` (2,784
bytes) and `docs/integrity.tsv` (1,049,926 bytes):
https://huggingface.co/datasets/elliancarlos/token-on-me/resolve/5e20f9ff2a18fe155f14606da0d61d516baedd6a/docs/INTEGRITY.md

The result line: 8,626 files (8,598 project files, 11 side tables, 1 database, 16 other files),
116,849,664,000 bytes read, 31,603,701,581 token rows (`MANIFEST.tsv`: 31,603,701,581), 16 views
counted, page CRC not written in 8,609 files, 0 problems, 6,763 s with 16 jobs. The check read
the root with `SHA256SUMS` `a453d5f10aa2...`. After the publish step `log/final.status.json`
keeps this value, and the publish record of the integrity run gives the value before
(`a453d5f10aa2...`) and after (`ea2052f7ce8b...`).

## What went wrong and how it was fixed

The run stopped twice with an ALERT. Each time the kit was fixed, staged again with a new
`WANT_SUMS`, uploaded by the user, and the run started again. A second start continues: the
steps that are DONE and the files with an OK ledger line are not done again. The staged lists in
order: `fc901a99a7cf...` (the first stage), `3a3921741224...` (fix 1), `6322c1a44dde...` (fix 2),
`0aaab61a41ab...` (fix 3), `da9125463a33...` (fix 4, the final stage). The files of the kit
before each fix are not here; the final files are.

1. **The base step: the new domain rows had the internal link schema.** The new-project machines
   wrote `organization_domains.new.parquet` with the columns of the internal link table
   (`domain`, `firm_based_on_domain`, `organisation_kind`, ...), not the 9 columns of the
   published table. The base step found that the schemas were not equal and stopped. Fix: the
   new step `domains` of `tom5_tools.py` writes the 31 new rows in the published schema
   (`organization_id` and the error columns `review_path`, `error_stratum`, `p_error`). The
   error values come from the error model of TOM 1.0.0 (`domainfix/em_newdomains.py`, on the
   local host, read only, output `inputs/new_domain_errors.tsv`). The script first runs the model
   on the published inputs and gets the published values again for all 10,899 earlier rows; then
   it adds the new links and their tokens: no earlier row changes. The documents
   `CHANGELOG.md` and `ORGANIZATIONS.md` got the new count (10,930 rows).
2. **The checks step: the footer key `organizations_mapping_sha256` of the 149 new files had
   values of each machine.** The release check wants the value of TOM in every file. Fix: the
   new step `footfix` writes the TOM value (`7b52a5...`, the value of `release_info`) into the
   footers of these files with `parquet_rename.py --set-kv` (footer only; no page is encoded
   again) and proves each file with `parquet_rename_check.py`. The data of all 1.2 billion rows
   of the 149 files matched the release tables.
3. **The upload step: the server-side copy of S3 was very slow.** The copy of the unchanged
   files of pass 4 used `aws s3 sync` with one `--exclude` pattern for each changed file. With
   thousands of patterns the AWS CLI used about 1.7 s of CPU for each key. Fix: a copy of each
   key from a key list, 32 at a time, then a listing of the destination: no key may be missing or
   have another size, and the step gives the count of other ETags. The
   download step of the changed files of pass 4 (`fetch2`) got the same fix.
4. **The hf step: the push list missed 7 changed files.** The list held the files that changed
   against the base root. The base already had the new `ledgers.parquet`,
   `pseudonymization.json` and 5 tables of `organizations/`, so these 7 files were not pushed,
   and for about 10 minutes the public repository had a mixed state (`500bd0bb00e8`). Fix: the
   push list also has each local file of the root whose `SHA256SUMS` row is not its row of pass 4.
   One more commit pushed the 7 files (`46a123047ef2`), and the verify step of the Hub tree
   passed.

Lessons for later kits:

- A step that copies rows from another kit must check their schema against the published table
  in the local rehearsal, with real files of the other kit, not only with test files.
- A footer key that holds a hash of shared data must come from one place (the release table),
  not from each machine. The release check of each footer value must also run on the machines
  that write the files.
- Do not give the AWS CLI more than a few `--include` or `--exclude` patterns. Copy from a key
  list in parallel and check each key in a listing after the copy.
- The push list to the Hub must come from a comparison of the root with the tree on the Hub (or
  with the `SHA256SUMS` of the last revision), not from a list of changes against a local step.
  Push the data files first and verify the whole tree before the run says DONE.

The kit of the new projects (`../../new-projects/`) has the same two root causes (fixes 1 and
2): its machines wrote the link schema and their own footer value. Its work folder has fixed
sources (`ta_tools.py`, `ta_run.sh`). They were not staged and did not run end to end, so they
are not here: `../../new-projects/patched/` has only the patches that ran.

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
| `tom5_start.sh`, `tom5_run.sh` | The start and the driver (steps `preflight`, `fetch`, `newlist`, `shape`, `footfix`, `footers`, `license`, `ledger`, `pseudo`, `fetch2`, `base` (first `tom5_tools.py domains`), `plan`, `canary`, `pass`, `assemble`, `tables`, `manifest`, `markers`, `checksums`, `view`, `checks`, `upload`, `hf`, `end`). |
| `tom5_tools.py` | The Python steps of the pass (with the steps `domains` and `footfix` of fixes 1 and 2). |
| `test-local.sh` | The local rehearsal (not staged). |
| `docs/` | The staged documents with their placeholders. |
| `inputs/license/30_compare.py`, `inputs/license/results.tom4.tsv`, `inputs/names.tsv`, `inputs/new_domain_errors.tsv` | Staged inputs: the comparison tool of the license pass, the stored decisions of the scan of the 8,449 projects, the map from the funnel names to the TOM names, the 31 new domain rows with their error values (fix 1). |
| `SHA256SUMS`, `SOURCE` | The final staged list (sha256 `da9125463a33d480755cdcb9ec91f6a6fab8292d4e73667785c1d3ed12fb43f6`, `WANT_SUMS` of the run that ended DONE) and the stage note. The first staged list was `fc901a99a7cf03ca72b4ef6af64d2a57a7844de96493116119d499c0d1ae6134` (section "What went wrong and how it was fixed"). `SOURCE` is the note of the first stage; the fixes did not write it again. |
| `machine/R1-tom5-setup.sh` | The setup of the machine (section "The machine setup"), with the fix of the scanner smoke test and the final `WANT_SUMS`. |
| `machine/B1-tom5-run.sh`, `machine/U1-tom5-upload.sh` | The start of the run on the machine (through the remote command script) and the upload of the stage by the user, with the final `WANT_SUMS`. |
| `domainfix/em_newdomains.py` | The error values of the 31 new domain rows (fix 1); it ran on the local host and wrote `inputs/new_domain_errors.tsv`. |
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

The files of `machine/` and `domainfix/` are not in the staged list either. `../KITS.tsv` gives
them (passes `pass-5-machine` and `pass-5-domainfix`) with the sha256 of the final file in the
work folder and of the copy. The copies of `R1-tom5-setup.sh` and `B1-tom5-run.sh` have
`REFUSED_INSTANCE_IDS` in the place of the list of EC2 instances that the scripts must refuse;
the copies of `R1-tom5-setup.sh` and `U1-tom5-upload.sh` have `BUCKET_NAME` in the place of the
bucket name; the copy of `U1-tom5-upload.sh` also has `AWS_PROFILE_NAME` and `KIT-FOLDER` in the
place of the AWS profile and of the kit folder. The copy of `em_newdomains.py` has
`STUDY-CHECKOUT`, `WORKSPACE-FOLDER` and `WORK-FOLDER` in the place of three default paths of the
work host. The other scripts of the kit that ran on the local host or sent commands to the
machine (the stage, the launch, the remote command script, the progress and the hold scripts)
are not here (`../README.md`).

The local rehearsal (`test-local.sh`) is the file of the first stage. It did not run again end
to end with the final stage: a run on 2026-11-09 15:48 UTC stopped at the step `domains`, because
the new-project file of the rehearsal already has the published schema of the domain rows. The
fixes were proved on the machine by the run that ended DONE and by the integrity check.
