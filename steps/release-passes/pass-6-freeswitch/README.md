# Pass 6: TOM 1.1.0, the 8,598-project revision plus `signalwire__freeswitch` (done on 2026-11-11)

Pass 6 makes the root of TOM 1.1.0 and pushes it to the same Hugging Face repository
(`elliancarlos/token-on-me`) as a new revision. The input is the final root of TOM 1.0.0 (pass 5,
8,598 project files, `SHA256SUMS` `ea2052f7ce8b...`). The pass copies the 8,598 project files
without a change and adds one project file: `signalwire__freeswitch`. The build of TOM 1.0.0 had no
file for this project, because blobExec stopped on 2 commits with two `author` headers
(`../../../LIMITATIONS.md`, section "Token on Me (TOM) 1.1.0"). A fixed tool chain made the file
first (`project-run/`). Then this pass made the root, the tables, the documents and the checksums.
TOM keeps its 53 columns. Version 1.1.0 has its own DOIs.

## The result

| Item | Value |
| --- | --- |
| Root | `dataset-release/dataset-v1.1.0/root/` of the bucket; 8,630 objects after the publish step of the integrity check |
| Project files | 8,599 (8,598 of TOM 1.0.0 with the same sha256, and `parquet/signalwire__freeswitch-dataset.parquet`), 53 columns, 31,610,939,708 token rows, 116,868,017,571 bytes |
| The new file | 7,238,127 rows, 28,508,088 bytes, language C, 36,204 commits, run commit `3dee68e8109`, license `MPL-1.1` (hand check), its own batch salt (deleted after the run) |
| `MANIFEST.tsv` | 8,599 rows: the 8,598 rows of TOM 1.0.0 without a change, and 1 new row |
| Side tables | `organization_domains` 10,931 rows (10,930 and 1 new: `benbria.ca`, kind company, 5,802 tokens, no audit answer); `project_organizations`, `project_labels`, `project_languages` and `project_licenses` 8,599 rows each (1 new row each, 0 changed rows); `organizations` (9,343), `organization_namespaces` (7,061), `project_facts` and `link_error` do not change; `ledgers.parquet` 13 new rows, 0 changed |
| `license` | the 8,598 earlier values do not change; the new project has `MPL-1.1` from a hand check (source `audit`, confidence `checked` in `project_licenses`) |
| `SHA256SUMS` before the integrity publish | sha256 `1ed022bdf37ca1aa378452840472332514b7a427d790a7cb89f75c1054216671` (the value that `docs/INTEGRITY.md` names) |
| `SHA256SUMS` after the integrity publish | sha256 `352111c7ffe83760f3b238bb1daa36b6899a5708d5bd8e31904e4f7fa2f892db`, 8,629 rows, 962,156 bytes. `../../../data/SHA256SUMS` has these rows. |
| Integrity check | 2026-11-11T23:45:14Z: 0 problems; 8,627 files, 116,878,175,989 bytes read, 31,610,939,708 token rows, 16 views, 6,712 s with 16 jobs (`docs/INTEGRITY.md` of the root) |
| The staged list | sha256 `086d54a1cedb8a6d6287e17a1f5408cf3c0a3481375c057a0b98be39f297123d` (`SHA256SUMS` of this folder, `WANT_SUMS` of the run) |

The hosts and the identifiers of TOM 1.1.0:

| Host | Identifier |
| --- | --- |
| Hugging Face, `elliancarlos/token-on-me` | revision `d094988ba30d90b574c8d3b233258f519a9fa86a` (the integrity report commit; the check through the public API passed: 8,630 files); DOI 10.57967/hf/11596 |
| Internet Archive | item `token-on-me-1.1.0` (https://archive.org/details/token-on-me-1.1.0), 97 files |
| Zenodo | the landing record of 1.1.0 (documents, checksums and the download kit; not the data files): version DOI 10.5281/zenodo.24173700, concept DOI 10.5281/zenodo.24118526 |

The documents of the root hold no Hugging Face DOI of 1.1.0: a revision cannot hold the DOI that
names it. They cite the Zenodo concept DOI and name the earlier revision with its DOI
(10.57967/hf/11537). The new DOI is in the Zenodo record, the Internet Archive item and the paper.

## The erratum

`CHANGELOG.md` of the root says that the license of the new project "comes from the same license
pass and rules as the earlier values". That is wrong: the value comes from a hand check (the rules
gave `NOASSERTION`). Three other document texts are wrong too. The release files keep their bytes.
The erratum is in the descriptions of the Zenodo record and of the Internet Archive item.
`../../../LIMITATIONS.md` (section "Token on Me (TOM) 1.1.0") gives the full list. The Hugging Face
commit `d094988ba30d` has the message "TOM 1.0.0: batch 1 of 1 (3 files)": the upload tool of the
integrity publish (`hf_tools.py upload`) had a fixed text. The kit got a message option after the
release; `integrity/I2-tom6-integrity-publish.sh` here is the file that ran.

## How the run went

1. The project run (`project-run/`, one m6id.4xlarge machine, 2026-11-10). The first start used the
   old jars and stopped as in TOM 1.0.0. `project-run/machine/J1-fs-jar-install.sh` installed the
   blobExec jar of cregit `e1e7d94` (sha256 `7573dc66...`). Then step 3 (the git log database of the
   original repository) stopped with the same `NullPointerException`: slickGitLog and persons also
   read the committer with JGit. `project-run/machine/J2-fs-fix2-install.sh` installed the slickGitLog and persons jars of
   cregit `c879bd3` (sha256 `7fde5a03...` and `7939aa17...`), took the new stage
   (`project-run/SHA256SUMS`, sha256 `1f88e9dc2b7c...`) and set the cregit tree to `c879bd3`. Pass 1
   of the project then ran again from step 3 (the tokenize output was kept). Attempt 5 ended OK at
   2026-11-10T23:49:01Z (`ledgers.parquet` of the root). The output had the published form of a TOM
   file: 53 columns, the pseudonyms of its own batch salt.
2. The error row of the new domain (`domainfix/em_newdomain1.py`, the local host, read only). It
   proves the 10,899 published rows and the 31 rows of the 8,598-project revision again (0 rows
   differ), then gives the row of `benbria.ca` (p_error 0.1131). `inputs-put/new_domain_errors.tsv`
   is the row that went to the machine.
3. The release run (`tom6_run.sh`, one m6id.4xlarge machine, 2026-11-11). The run stopped at the
   license step for the hand check. The user checked the root LICENSE file at `3dee68e8109` (the
   text of MPL-1.1) and agreed to `MPL-1.1` (`inputs-put/AUDIT_OK`, `inputs-put/corrections.tsv`).
   `machine/B2-tom6-run-corrected.sh` then continued the run: it is `B1` with one change, it accepts
   the new `inputs/corrections.tsv`. The run ended DONE and pushed the root to the Hub.
4. The integrity check (`integrity/`): it read every byte of the root (0 problems), then
   `integrity/I2-tom6-integrity-publish.sh` put `docs/INTEGRITY.md`, `docs/integrity.tsv` and the
   new `SHA256SUMS` into S3 and into one Hub commit (`d094988ba30d`).
5. The Internet Archive item and the Zenodo record were made after this, from the same root (their
   kits are not here: see `../../README.md`, "Not here").

## What the run checks

- The base: the staged `inputs/tom4.SHA256SUMS` is the root list of TOM 1.0.0 (`ea2052f7ce8b...`);
  the S3 root has one object for each row; the copy check gives 0 missing files, 0 other sizes.
- The new file: the rows and the bytes of the project run, the Parquet form against `tio__tio` (53
  columns, order, types, footer keys, writer, codecs, Bloom filters, row groups).
- The mapping hash: `footfix` sets `organizations_mapping_sha256` of the new file to the value of
  the base `release_info` (footer only, proved by `parquet_rename_check.py`); `mapcheck` reads the
  footers of the 8,599 files and refuses any other value.
- All 8,599 footers against `MANIFEST.tsv`; the sum of the rows is 31,610,939,708.
- The license: ScanCode 32.5.0 and the rules of ctp `0f9b8ad` run for the new project only; the
  8,598 base rows of `project_licenses` stay; a value that the rules do not give stops the run until
  the hand check.
- No at sign and no machine path in a new document or table (`release_tools.py`).
- Hugging Face: the push list is the difference of the new `SHA256SUMS` against the base list; the
  stale integrity files of the base are deleted; the whole tree is checked after the push.

## Files

| Path | Contents |
| --- | --- |
| `SHA256SUMS`, `SOURCE` | the staged list of the release run and its stage note |
| `tom6.conf`, `tom6_start.sh`, `tom6_run.sh`, `tom6_tools.py`, `docs/`, `inputs/` | the staged files of the release run that no earlier pass staged with the same bytes (`../KITS.tsv` maps the other rows to their copies) |
| `inputs-put/` | the three inputs that went to the machine during the run (`AUDIT_OK`, `corrections.tsv`, `new_domain_errors.tsv`) |
| `machine/` | the setup, the start (`B1`, and `B2` after the hand check) and the stage upload |
| `integrity/` | the integrity check (`integrity_check.py`, sha256 `b3a0e4ca6af3...`, pinned in `I1`), its start, its publish step, its upload and its local test |
| `domainfix/` | the error model script of the new domain row |
| `project-run/` | the project run of `signalwire__freeswitch`: the staged list (`SHA256SUMS`), `SOURCE`, the files that differ from the kit of the 149 new projects (`../../new-projects/kit/`), and the two jar install scripts |

The copies differ from the files that ran only in the run values: the bucket name (`BUCKET_NAME`),
the AWS profile (`AWS_PROFILE_NAME`), the kit folder (`KIT-FOLDER`), the refuse list of machine ids
(`REFUSED_INSTANCE_IDS`) and three default paths of the work host in `domainfix/em_newdomain1.py`.
`../KITS.tsv` gives the sha256 of each file that ran and of each copy; `../check-kits.sh` checks them.
`project-run/SHA256SUMS` lists the cregit bundle (`code/cregit-ta.bundle`, head `c879bd3`), the ctp
tar of `a9f0bed` and the Nix closure of licensee: `../../../tools.lock` gives them.

Not here: the launch, remote command, progress and hold scripts, the local rehearsals of the release
run (`test-local.sh`, `test/` with real release files), the kit README of the project run, and the
kits of the Internet Archive item and of the Zenodo record.
