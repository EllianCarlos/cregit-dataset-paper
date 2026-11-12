# Token on Me (TOM) 1.1.0: the replication package

This repository holds the scripts, the input lists and the tool pins of the dataset
"Token on Me" (TOM), versions 1.0.0 and 1.1.0. It supports a Data and Tool paper.
Its goal is reproducibility: a reader can check each published file, and can
build the dataset again for one project with the same tools.

## Cite this package

This package has the DOI 10.5281/zenodo.24177100 (Zenodo record 24177100, version 1.1.0, the zip of a git tag of
this repository). `CITATION.cff` gives the citation. Cite the dataset with its own DOI: TOM 1.1.0 is
10.57967/hf/11596, TOM 1.0.0 is 10.57967/hf/11537 (section "The dataset").

## The dataset

TOM 1.1.0 has one row for each token of the source code of 8,599 software projects:
31,610,939,708 token rows in 8,599 project files (Parquet, ctp schema 3, 53 columns; section
"TOM 1.1.0"). TOM 1.0.0 has 8,598 project files and 31,603,701,581 token rows in its final
revision (section "The revision of TOM 1.0.0"); its first revision had 8,449 project files and
30,408,388,202 token rows. For each
token, a row gives the author of the commit that last changed the token (the cregit token
blame), metadata of the commit and of the project, and the organization columns. Identities
are pseudonyms.

The projects are active, licensed projects with 1,000 or more commits at the snapshot commit.
The sources are GitHub, GitLab hosts, foundation rosters, company organizations and published
project lists (`pipeline/SELECTION-STAGES.md`). A project stays in TOM when its largest
programming language at the pinned commit is C, C++, Java or Rust, by tokei code lines
(`steps/language-selection/tokei/`).

Hosts of TOM 1.1.0: Hugging Face, `elliancarlos/token-on-me` (public), revision
`d094988ba30d90b574c8d3b233258f519a9fa86a`, DOI 10.57967/hf/11596 (cite this DOI for 1.1.0); the
Internet Archive item `token-on-me-1.1.0` (https://archive.org/details/token-on-me-1.1.0); the
Zenodo landing record 10.5281/zenodo.24173700 (documents, checksums and the download kit, not the
data files). The Zenodo concept DOI 10.5281/zenodo.24118526 always names the newest version: cite it
to name TOM with no version. Section "TOM 1.1.0" gives the details.

TOM 1.0.0 on Hugging Face: the final revision is
`5e20f9ff2a18fe155f14606da0d61d516baedd6a` (pass 5 and its integrity report); its DOI is
10.57967/hf/11537 (cite this DOI for 1.0.0). Its Zenodo record is 10.5281/zenodo.24118527 and its
Internet Archive item is `token-on-me-1.0.0`. The DOI 10.57967/hf/11505 marks the first revision, `e81b554deb9b` (the documents with
the DOI). The DataCite version of that DOI names revision `bc7543affd2e`, which has the same
project files as `e81b554deb9b`. The first revision has 12 documents. The
limitations and the provenance are now in the paper and in this repository (`LIMITATIONS.md`,
`REPRODUCE.md`): the release no longer has `docs/LIMITATIONS.md`, `docs/PROVENANCE.md` and
`docs/RELEASE-NOTES.md`. The organization
database 1.0.0 ships in the same dataset, in the folder `organizations/`: https://huggingface.co/datasets/elliancarlos/token-on-me.
It is also published on Zenodo: cite the concept DOI 10.5281/zenodo.23744044 (version DOI
10.5281/zenodo.23744045). Its build tag is `v4.9`; the footer key `organizations_version` keeps
`v4.9`.

## How TOM was made

1. Selection (S1-S6) and build (S7): ctp ran cregit on each project and wrote one Parquet file
   for each project.
2. The steps after the build (`steps/`): the organization columns and the pseudonyms in one
   write, the root build, the re-encode. The result is the source root of the release passes:
   10,754 project files, ctp schema 2, 71 columns.
3. Five release passes (`steps/release-passes/`):
   - Pass 1 keeps the 8,447 projects of the tokei rule, drops 10 columns, renames
     `provenance_status` to `audit_frame_file` (61 columns) and writes the side table
     `project_facts`.
   - Pass 2 adds 2 Savannah projects (8,449), fills 161 empty `language` cells (tokei) and 149
     `license` cells (licensee at confidence 98, outside GitHub), and adds the side tables
     `project_languages` and `project_labels`.
   - Pass 3 proves a rule on every row, drops 8 more columns (53 columns) and moves
     `roster_lang` to `project_facts`.
   - Pass 4 (the DOI pass) changes documents only: the DOI, the date, 3 removed documents.
   - Pass 5 (done on 2026-11-09) made the revision of TOM 1.0.0: the 149 new projects, the
     license values and the side table `project_licenses` (section "The revision of TOM 1.0.0").
4. ctp now writes the 53-column schema in a normal run, with no later pass (ctp branch
   `feat/schema-3-run`, cregit fork branch `feat/schema-3`). A rebuild of 2 projects gives the
   output of the passes (`steps/release-passes/schema3-proof/`), except one file where the
   blame time limit of the busy rebuild host made cregit use plain blame.

## The error of the organization columns

The domain audit on TOM has 514 decided answers. The sample is systematic, with a probability
proportional to the run tokens of each domain. The estimator is the Hajek ratio. The answered
part of the random-order tail counts as a two-phase sample. Results (share of the tokens of TOM):

- The error of `firm_based_on_domain`: 2.921% (95% interval 1.465% to 4.904%).
- The share of tokens of company kinds, corrected: 34.993% (95% interval 32.67% to 37.27%).

`docs/ERROR.md` of the release gives the method and all figures. The audit answers name domains,
so they are not here.

## The revision of TOM 1.0.0 (2026-11-08)

A new revision of release 1.0.0 goes to the same Hugging Face repository, with the same DOI (no
new DOI). It has 8,598 projects: the 8,449 projects above and 149 new projects of the selection
funnel with the tokei rule (`steps/selection-funnel/`), built with the tool chain of TOM
(`steps/new-projects/`). It gives the `license` column SPDX license expressions from a license
scan (`steps/license-pass/`), adds the side table `organizations/project_licenses.parquet`, and
changes the documents. TOM keeps its 53 columns. The kit of the root is
`steps/release-passes/pass-5-revision/`; its run started on 2026-11-09. Until the run ends,
`data/` and the numbers above describe the root of pass 4. `HUMAN-CHECKS.md` gives the human checks of each step.

Note of 2026-11-09: the run ended DONE at 17:00 UTC. The root of the revision has 8,598 project
files, 31,603,701,581 token rows and 116,839,509,483 bytes of project files; its `SHA256SUMS` has
8,628 rows (sha256 `ea2052f7ce8b...`) after the integrity check added `docs/INTEGRITY.md` and
`docs/integrity.tsv`. The integrity check read every byte of the root and found 0 problems.
The final Hugging Face revision is `5e20f9ff2a18`. `data/` and the numbers above now describe
this root. The 4 fixes of the run and their lessons are in
`steps/release-passes/pass-5-revision/README.md`.
The DOI of the final revision is 10.57967/hf/11537 (made on 2026-11-09; the DataCite record
names version `5e20f9f` and links to 10.57967/hf/11505).

## TOM 1.1.0 (2026-11-11)

TOM 1.1.0 is the final revision of TOM 1.0.0 plus one project, `signalwire__freeswitch`. The build
of TOM 1.0.0 had no file for it: blobExec stopped on 2 commits with two `author` headers, because
JGit then gives no committer. The fixed tools read the committer from the `committer` header of the
commit (cregit fork, branch `fix/null-committer`: blobExec `e1e7d94`, slickGitLog and persons
`c879bd3`). The step is `steps/release-passes/pass-6-freeswitch/` (the project run and the release
run). `LIMITATIONS.md`, section "Token on Me (TOM) 1.1.0", gives the details.

- 8,599 project files, 31,610,939,708 token rows, 116,868,017,571 bytes of project files, 0 failed
  projects of the selection. The 8,598 project files of TOM 1.0.0 have the same bytes (sha256) and
  the same `MANIFEST.tsv` rows. The new file has 7,238,127 rows (28,508,088 bytes), language C,
  36,204 commits, license `MPL-1.1` (a hand check).
- The side tables get 1 row each (`project_organizations`, `project_labels`, `project_languages`,
  `project_licenses`) and 1 domain row (`organization_domains`: 10,931 rows). No earlier row
  changes.
- The root `SHA256SUMS` has 8,629 rows (sha256 `352111c7ffe8...`, after the integrity check: 0
  problems). `data/SHA256SUMS` has these rows; `data/SHA256SUMS-1.0.0` keeps the rows of TOM 1.0.0.
- Hosts: Hugging Face revision `d094988ba30d` (DOI 10.57967/hf/11596); Internet Archive item
  `token-on-me-1.1.0` (97 files); Zenodo version DOI 10.5281/zenodo.24173700 (concept DOI
  10.5281/zenodo.24118526). The organization database stays Zenodo concept DOI
  10.5281/zenodo.23744044.
- Erratum: `CHANGELOG.md` of 1.1.0 says that the license of the new project comes from the rules of
  the license pass. It comes from a hand check. The erratum is in the Zenodo and Internet Archive
  descriptions; the release files keep their bytes (`LIMITATIONS.md`).

## Archives of the code

Software Heritage archived the 3 code repositories. The first save was on 2026-11-09. The second save was on
2026-11-10, after we pushed the tool commits that the release and its new project depend on (the branches
`fix/schema-3-bare-cr`, `fix/null-committer`, `feat/license-scan` and `feat/parquet-reencode`, and the tags
`dataset-build/*`). Use the snapshots of 2026-11-10. They hold the commits that `tools.lock` pins, except
cregit `c879bd3` (slickGitLog and persons of TOM 1.1.0): on 2026-11-12 it is not on the public branch
`fix/null-committer` yet (its head is `e1e7d94`).

| repository | snapshot of 2026-11-10 | snapshot of 2026-11-09 (older) |
|---|---|---|
| cregit (the fork that TOM uses) | `swh:1:snp:db541fc6be6dd1ab6576343edfe398b9cae510cd` | `swh:1:snp:09cc8082ed0c5f3c137dac934125769e51773dde` |
| cregit-token-pipeline (ctp) | `swh:1:snp:93dde342b861e215d4bbc8c98b969d8fc2ecf816` | `swh:1:snp:f078b912faaf1cc5712d9705ba1dc3776a96e386` |
| cregit-dataset-paper (this repository; at `40f1314`) | `swh:1:snp:97137dd9c5422289b85cbf73c88785f404cf0d5e` | `swh:1:snp:ceb943a3eacfbdefe86ab1c1e9c12e42c78f74b5` (at `7d53970`) |

Open a snapshot at `https://archive.softwareheritage.org/<snapshot>`.

## Release decisions (user)

- Host: Hugging Face (2026-11-07), public from the start.
- Third-party sources: `THIRD-PARTY.md` of the release gives each source and its license or
  terms. This repository holds copies of some third-party files and web pages: `LICENSE-DATA`
  lists them with their terms. The Zenodo record of this package leaves out the raw third-party
  copies (the `export-ignore` lines of `.gitattributes`, 201 files); they stay in the GitHub
  repository.
- The commit SHAs (`tools.lock`, `sync/sources.tsv`) and the tool bundles are published.
- Anonymous release: for the blind review, the user's own repositories go out as an
  anonymous release (one anonymous export commit; the user pushes it).

The dataset build used three tools:

- ctp (cregit-token-pipeline): the runner. It clones a project, runs cregit and
  writes one Parquet file for each project.
- a cregit fork: the token blame. It uses srcML to split source files into tokens.
- srcML: the tokenizer, with patches.

`tools.lock` gives the exact version of each tool, and the sha256 of the git
bundle that the dataset build ran.

## The stages

| Stage | What it does | Where |
|---|---|---|
| Selection (S1-S6) | Find the candidate projects, measure them, filter them, label them. | `pipeline/s1-search` .. `pipeline/s6-labels` |
| Build (S7) | Run ctp for each project in batches. One Parquet file for each project. | `pipeline/s7-run` |
| Merge | Join the per-project files into the published files. | `pipeline/s7-run/prelim_merge.py` (preliminary) |
| Steps after the build | The organization columns and the pseudonyms, the root, the re-encode. | `steps/` |
| Release passes | The subset of the tokei rule, the column changes, the fills, the side tables, the uploads. | `steps/release-passes/` |
| Validate | Check each file against its recorded sha256 and the column contract. | `make verify`, `tools/fill_release.py check`, `pipeline/s7-run/fetch_done.sh` |

`REPRODUCE.md` gives, for each stage, the inputs, the command, the expected
output hash, the cost and the time.

## Two short paths for reviewers

1. `make verify DATA_DIR=<root>` checks the sha256 of each file of the root against
   `data/SHA256SUMS` (the 8,629 rows of the root of TOM 1.1.0). For a download of TOM 1.0.0, add
   `SUMS=data/SHA256SUMS-1.0.0` (the 8,628 rows of its final root). `make validate DATA_DIR=<root>` runs
   `fill_release.py check` (the same file as `tools/fill_release.py` of the root): the 53
   columns, the footer keys and the tables of each file. `SCHEMA=2` checks the source root of
   the passes (71 columns).
2. `make rebuild-one PROJECT=<owner__repo>` builds the dataset again for one
   project with the pinned tools. The published files have pseudonyms made with
   a salt that is deleted by design, so no rebuild gives their bytes. The target
   checks the run output and the file before the pseudonyms against the recorded
   sha256 values (`data/REBUILD-TARGETS.tsv`). Then it checks that the published
   file of TOM is equal to that file in every column that the pseudonyms and the release
   passes do not change (`REPRODUCE.md`, section 6.1).

Both targets need the Nix dev shell: `nix develop`. Then run `make help`.
`make flake-check` proves that the shell has the tool store paths of the dataset build.

## The line method against the token method

`token-vs-line-report.md` compares the line method (`git blame` of the source file) with the token method of
TOM on a simple random sample of 250 projects of TOM 1.0.0. With plain `git blame`, 19.3% of the tokens (project
mean; 95% interval 17.3% to 21.3%) have another author than in TOM. The scripts, the draw, the result tables and
the commands are in `steps/token-vs-line/`.

## Status of this version

Some parts are not ready. Each target that is not ready prints `not ready: <reason>` and exits
with a non-zero status. `REPRODUCE.md` lists what is left.

## Layout

| Path | Contents |
|---|---|
| `pipeline/` | Copies of the paper scripts and their inputs. Do not edit them here. |
| `steps/` | The steps after the build that made the published files (the organization columns, the final write, the root build, the re-encode, the five release passes of TOM 1.0.0, pass 6 of TOM 1.1.0, the selection funnel, the new projects, the license pass and the kit of the revision), and the evidence behind the error, language and Linux numbers. One folder for each step, each with a README (`steps/README.md`). |
| `tools/ctp/`, `tools/cregit/` | Copies of some files of the pinned ctp and cregit commits (the column contract, the validation, the Nix files of srcML). |
| `tools/ctp-venv/` | The package lists of the ctp Python environment on each machine type. |
| `tools/jars/` | The jar content check (`jar_content_sha256.py`). The flake pins the jars by sha256. |
| `queries/join-organizations.sql` | A DuckDB query that joins the project files with the organization database, with the join keys, the unique row key and the checks of the keys. It runs on the release root and on `sample/data`. |
| `sync/` | The source list and the scripts that copy and check `pipeline/`. |
| `tools.lock` | The tool versions and bundle hashes. |
| `flake.nix`, `flake.lock` | The pinned environment (Nix). |
| `Makefile` | The reviewer and stage targets. |
| `scripts/` | The helper scripts of the Makefile. |
| `data/SHA256SUMS` | The sha256 of each file of the root of TOM 1.1.0 (8,629 rows: 8,599 project files and the other files). |
| `data/SHA256SUMS-1.0.0` | The sha256 of each file of the final root of TOM 1.0.0 (8,628 rows: 8,598 project files and the other files). |
| `data/REBUILD-TARGETS.tsv` | For each of the 8,449 project files of the first revision: the run record, the target sha256 values of `rebuild-one`, the sha256 in the source root and the published sha256 in the final root (the same in TOM 1.1.0). |
| `token-vs-line-report.md` | The report of the run of the line method against the token method on 250 random projects (method, results with and without the cut projects, causes, limits). Its step is `steps/token-vs-line/`. |
| `HUMAN-CHECKS.md` | For each step: what is automatic or AI-proposed, what a human checked, and the measured result. |
| `ANONYMIZATION-TODO.md` | Identifying text to remove before the anonymous mirror. |

## How `pipeline/` and `tools/` are made

`sync/sources.tsv` lists each copied file: the source, the source commit, the
git blob id, the source path and the destination path.
`sync/sync-from-sources.sh` copies the files again from the recorded commit
with `git archive`. It does not read a working tree. Then it checks the git
blob id of each file. `sync/untracked.tsv` lists 105 generated inputs that git does not
track in the source. The script copies each one only when its sha256 is equal to the value
of a committed checksum file. `sync/sync-from-sources.sh --check` runs the check only.
It needs no source repository.
`sync/patches.tsv` lists the copied files with one replaced line (a default path that named the
private study repository). The copy step checks the git blob id of the file that ran before the
replacement; the check compares the sha256 after it. The source id `study-s8` copies the files of
the organization step at their own study commit into `steps/organizations/study/`.
