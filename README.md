# cregit token dataset, v1

This repository holds the scripts, the input lists and the tool pins of the
cregit token dataset, version 1. It supports a Data and Tool paper.
Its goal is reproducibility: a reader can check each published file, and can
build the dataset again for one project with the same tools.

## The dataset

Dataset v1 has one row for each token of the source code of software projects.
The selection (S1-S6) gave 3,548 projects (the keys of the final v1 sidecar). The
build and the merge (S7) gave 3,544 files, and BRL-CAD came in a later separate
write: the 5,000+ layer of the release has 3,545 files. 3 selected projects have
no file. For each token, a row gives the author of the commit that last changed
the token (the cregit token blame), and metadata of the commit and of the project.

The projects are active, licensed C, C++, Java and Rust projects with 5,000 or
more commits at the snapshot commit. The sources are GitHub, GitLab hosts,
foundation rosters, company organizations and published project lists.
`pipeline/SELECTION-STAGES.md` gives the rules.

The release adds a second commit layer (user decision, 2026-10-23). It is one dataset of
10,754 project files: 3,545 files with 5,000 or more commits (the v1 build and BRL-CAD, a
later separate write) and 7,209 files with 1,000 to 4,999 commits. It has 32,635,174,618
token rows and 162,472,453,753 B (162.5 GB) of release files (ZSTD 19), in the release root
`dataset-release-1` (10,780 files). `REPRODUCE.md` (sections 4.6 to 5) gives the runs, the merge and the links of
the second layer.

## Release decisions (user, 2026-10-25)

- Host: Zenodo. About 4 records of 50 GB under one concept DOI, unless Zenodo gives a
  larger quota (the answer is open). The record ids come here when they exist.
- Reproducibility: the release has everything that a reproduction needs, also the web
  captures (the fetched third-party pages), each with its URL, its fetch date and its
  sha256. The pages are third-party content: `THIRD-PARTY.md` of the release gives a
  license note for each source (not written yet).
- The commit SHAs (`tools.lock`, `sync/sources.tsv`) and the tool bundles are published.
- Anonymous release: for the blind review, the user's own repositories go out as an
  anonymous release (one anonymous export commit; the user pushes it). The Data and Tool
  track itself is single-anonymous, but the user still wants the anonymous release.

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
| Validate | Check each file against its recorded sha256 and the column contract. | `make verify`, `pipeline/s7-run/fetch_done.sh` |

`REPRODUCE.md` gives, for each stage, the inputs, the command, the expected
output hash, the cost and the time.

## Two short paths for reviewers

1. `make verify DATA_DIR=<release root>` checks the sha256 of each published
   project file against `data/SHA256SUMS`. `make validate DATA_DIR=<release root>`
   checks the 71 columns of ctp schema 2 and the footer of each file.
2. `make rebuild-one PROJECT=<owner__repo>` builds the dataset again for one
   project with the pinned tools. The published files have pseudonyms made with
   a salt that is deleted by design, so no rebuild gives their bytes. The target
   checks the run output and the file before the pseudonyms against the recorded
   sha256 values (`data/REBUILD-TARGETS.tsv`). Then it checks that the published
   file is equal to that file in every column that the pseudonyms do not change
   (`REPRODUCE.md`, section 6.1).

Both targets need the Nix dev shell: `nix develop`. Then run `make help`.
`make flake-check` proves that the shell has the tool store paths of the dataset build.

## Status of this version

This is the first version of the repository. Some parts are not ready. Each
target that is not ready prints `not ready: <reason>` and exits with a
non-zero status. `REPRODUCE.md` lists what is left.

## Layout

| Path | Contents |
|---|---|
| `pipeline/` | Copies of the paper scripts and their inputs. Do not edit them here. |
| `tools/ctp/`, `tools/cregit/` | Copies of some files of the pinned ctp and cregit commits (the column contract, the validation, the Nix files of srcML). |
| `tools/ctp-venv/` | The package lists of the ctp Python environment on each machine type. |
| `tools/jars/` | The jar content check (`jar_content_sha256.py`). The flake pins the jars by sha256. |
| `sync/` | The source list and the scripts that copy and check `pipeline/`. |
| `tools.lock` | The tool versions and bundle hashes. |
| `flake.nix`, `flake.lock` | The pinned environment (Nix). |
| `Makefile` | The reviewer and stage targets. |
| `scripts/` | The helper scripts of the Makefile. |
| `data/SHA256SUMS` | The sha256 of each published project file (10,754 rows of the release root). |
| `data/REBUILD-TARGETS.tsv` | For each project file: the run record and the three target sha256 values of `rebuild-one`. |
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
