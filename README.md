# cregit token dataset, v1

This repository holds the scripts, the input lists and the tool pins of the
cregit token dataset, version 1. It supports a Data and Tool paper.
Its goal is reproducibility: a reader can check each published file, and can
build the dataset again for one project with the same tools.

## The dataset

Dataset v1 has one row for each token of the source code of 3,548 software
projects. For each token, a row gives the author of the commit that last
changed the token (the cregit token blame), and metadata of the commit and of
the project.

The projects are active, licensed C, C++, Java and Rust projects with 5,000 or
more commits at the snapshot commit. The sources are GitHub, GitLab hosts,
foundation rosters, company organisations and published project lists.
`pipeline/SELECTION-STAGES.md` gives the rules.

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

1. `make verify` checks the sha256 of each published file against
   `data/SHA256SUMS`.
2. `make rebuild-one PROJECT=<owner__repo>` builds the dataset again for one
   project with the pinned tools. Then it compares the sha256 of the new
   Parquet file with the published value.

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
| `data/SHA256SUMS` | The sha256 of each published file (filled at the v1 freeze). |
| `ANONYMIZATION-TODO.md` | Identifying text to remove before the anonymous mirror. |

## How `pipeline/` and `tools/` are made

`sync/sources.tsv` lists each copied file: the source, the source commit, the
git blob id, the source path and the destination path.
`sync/sync-from-sources.sh` copies the files again from the recorded commit
with `git archive`. It does not read a working tree. Then it checks the git
blob id of each file. `sync/untracked.tsv` lists 104 generated inputs that git does not
track in the source. The script copies each one only when its sha256 is equal to the value
of a committed checksum file. `sync/sync-from-sources.sh --check` runs the check only.
It needs no source repository.
