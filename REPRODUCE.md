# How to reproduce the cregit token dataset v1

This file gives, for each stage, the inputs, the command, the expected output hash, the
cost and the time. A value with the word "estimate" is an estimate. "UNKNOWN" means that
no record was found. "copy" in a hash column means the sha256 of the copied file in this
repository, because the stage did not record a value when it ran.

Dataset v1 has 3,548 projects: 3,497 from run layer 1 and its supplements, 50 from GitLab
hosts (batch 25) and 1 GitLab near miss (batch 26). `pipeline/SELECTION-STAGES.md` gives
the rules.

## 1. The environment

The dataset build ran cregit in its devenv shell. `flake.nix` gives the same packages:
it uses the devenv-nixpkgs rev of `tools/cregit/devenv.lock`.

```
nix develop            # the dev shell for all Makefile targets
make flake-check       # nix flake check -L
```

Proof (2026-10-14, x86_64-linux): `nix flake check -L` prints

```
cregit-dataset-tools-check> devenv 2.4.0 (x86_64-linux)
devenv-identity-check> devenv matches the dataset build
all checks passed!
```

and `nix build --rebuild -L .#checks.x86_64-linux.srcml-identity` prints

```
srcml-identity-check> srcml, python3, cregit-python, cregit-perl, git and libsrcml match the dataset build
```

The checks compare these store paths with the paths of the dataset build:

| Package | Store path |
|---|---|
| srcML (patched) | `/nix/store/g6xii595faiacx4yaq4k0k2mrmp3hzhy-srcml-1.1.0-unstable-2026-10-04` |
| python3 | `/nix/store/3n4qphl9s728sz8frmpqqrv9b1m87g68-python3-3.14.7` |
| cregit python (duckdb 1.5.5, pytest) | `/nix/store/5gnikzfb2hkysq9d45mjl74h7vj4c5ad-python3-3.14.7-env` |
| cregit perl | `/nix/store/kq15zjik5prghj8xl3slaq1crxni4kfb-perl-5.42.0-env` |
| git 2.55.0 | `/nix/store/8wxs6573l730vxkqd6wp58kvxa19csll-git-2.55.0` |
| devenv 2.4.0 | `/nix/store/5sbcspxmvsj6g41dmv20flpvj9v8pzi8-devenv-2.4.0` |

They also check the sha256 of `libsrcml.so.1.1.0`:
`dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3`.

The devenv command comes from a second input, `nixpkgs-devenv`. The run machines installed
devenv with `nix profile add nixpkgs#devenv`. Their profile manifest records the locked
nixpkgs (NixOS/nixpkgs `39ad350a0602fa0a58a544344e3e9187526ea45c`, the channel tarball
`nixpkgs-26.11pre1087089.39ad350a0602`). The local machine and the three EC2 machines that
ran on 2026-10-14 have the same devenv store path. ctp runs devenv from the fixed path
`~/.nix-profile/bin/devenv`. The dev shell puts devenv on PATH. For ctp, also install it
into the profile:

```
nix profile add .#devenv
```

`nix develop -c <tool> --version` on x86_64-linux (2026-10-14) gives: devenv 2.4.0, git
2.55.0, srcml 1.1.0, perl 5.42.0, python3 3.14.7 (`CREGIT_PYTHON`: duckdb 1.5.5), ctp
python 3.12.14 (`CTP_PYTHON`: duckdb 1.5.5), java 21.0.12, `LEGACY_JAVA_HOME` java
1.8.0_492, sbt 2.0.6 (launcher), sqlite3 3.53.3, GNU Make 4.4.1, gcc 15.3.0, Universal
Ctags 6.2.1, git-filter-repo, xz 5.8.3, GNU tar 1.35, and GNU coreutils 9.11, awk, sed and
grep.

The cregit jars. `run_pipeline_process.sh` runs 4 jars: blobExec, slickGitLog, persons
and remapCommits. sbt downloads their dependencies at build time, so they are not pure
Nix builds. `packages.cregit-jars` pins the jar files of the dataset build by sha256
(`requireFile`) and puts them in the directory layout of a cregit checkout. The jar files
are in the tool bundle set (`jars/`, with `jars/SHA256SUMS`). Add them to the Nix store
first:

```
nix-store --add-fixed sha256 jars/*.jar
nix build .#cregit-jars
cp -rL --no-preserve=mode result/. <cregit checkout>/
```

Each run machine built its own jars. The blobExec jar has the same sha256 on all machines
that were checked. The other three jars have a different sha256 on each machine, but the
same entries (name, CRC-32 and size): only the zip time stamps of their nested jar differ.
`tools/jars/jar_content_sha256.py` computes this content sha256. `tools.lock` gives both
values for each machine.

The ctp venv. `tools/ctp-venv/` gives the package list of the ctp venv on spot a, on the
big EC2 and on the local machine (`pip freeze --all`). All venvs on one machine have the
same list. EC2 and local differ only in Python (3.12.14 and 3.12.13) and pip (23.2.1 and
25.0.1). `packages.ctp-python` of the flake is Python 3.12.14 with duckdb 1.5.5 and pytest
9.1.1. Its other packages have different versions (`tools.lock`, rows ctp-venv). ctp.py
itself uses the standard library only.

Platforms: the outputs are per system (x86_64-linux, aarch64-linux, x86_64-darwin,
aarch64-darwin). Only x86_64-linux is tested. devenv-nixpkgs patches nixpkgs in a
derivation at evaluation time, so a system evaluates only on a machine (or a builder) of
that system. The store paths above are for x86_64-linux. The jar files do not depend on
the system.

## 2. Repository checks

| Command | What it checks | Result on 2026-10-14 |
|---|---|---|
| `make sync-check` | Each file under `pipeline/` and `tools/` has the git blob id of `sync/sources.tsv`, or the sha256 of `sync/untracked.tsv`. | `OK: 879 files match sources.tsv, 104 files match untracked.tsv` |
| `make stage-hashes` | The stage outputs match the sha256 that each stage recorded (section 3 and 4). | `OK: the stage outputs match their recorded sha256` |
| `make test` | The tests of the copied scripts (in the dev shell). | S5: 10 passed, 10 skipped. S6: 25 passed. S7: 96 passed, 3 skipped. |

The S6 test `test_the_committed_labels_are_what_the_script_writes` runs `build_labels.py`
again and compares its output with `labels.csv`. So S6 replays offline from the copied inputs.

## 3. Selection (S1-S6)

The scripts are in `pipeline/`. They keep their paths of the source repository, so the
relative paths in them stay valid. S1-S3 read live APIs and web pages. A replay today gives
other values, because the repositories change. So the hashes below prove that the copied
files are the files of the selection. They do not prove that a new run gives the same files.

| Stage | Inputs | Command | Output | Expected sha256 | Cost | Time |
|---|---|---|---|---|---|---|
| S1 search | GitHub search API | `python3 s1-search/search.py [SNAPSHOT_DATE]` (default 2026-10-05) | `s1-search/repos.jsonl` (in git as `.xz`) | `140afa45882274d501b62b4871de358b4ebe1de50f3225bf2b56a7b88d250ef8` | API calls only | UNKNOWN |
| S1 company orgs | `sources/company-orgs/orgs.jsonl`, GitHub API | `sources/company-orgs/list_org_repos.py` | `sources/company-orgs/repos.jsonl` (`.xz`) | `617232ce154b3601f0ff4c403b0162de66d7bad176b2b150af4cccbaf096a028` | API calls only | UNKNOWN |
| S1 rosters | `rosters/raw/` (web captures, not copied, see section 8) | `rosters/scripts/build_foundations.py` | `rosters/*.csv` | copy | none | UNKNOWN |
| S2 resolve | S1 outputs, GitHub GraphQL and REST | `s2-pool/resolve.py`, `s2-pool/resolve_rest.py` | `s2-pool/resolve.jsonl` (`.xz`) | `30caba896379a46d13bcdc159c17740f38636df35be677dd7bfe1c6024583ce2` | API calls only | UNKNOWN |
| S2 pool | resolve output, rosters, sources | `s2-pool/build_pool.py` | `s2-pool/pool.csv` (`.xz`) | `1d058f2cd2e1b77018a3e512de9288d37681bba3d5835eee64a619ee72e2503d` | none | UNKNOWN |
| S2 supplements | pages, URL map, GitLab hosts | `s2-pool/v2/*.py`, `s2-pool/gitlab/*.py` | `s2-pool/v2/pool.batch{22,23,25,26}.csv` | copy | API calls only | UNKNOWN |
| S3 measure | `pool.csv`, GitHub REST trees, clones | `s3-measure/measure_trees.py`, `commit_counts.py`, `measure_clones.py`, `clone_facts.py` | `trees.jsonl`, `commits.jsonl`, `clones.jsonl`, `clone_facts.jsonl` (`.xz`) | trees `ba6d8e4d845b68bc48efe8fc878855fa8b456675651b3c541e461c7d7f24699f`, commits `57bb5349738d39de666ccf9466e983bdabf73d6229e0f7335f643a5c5791d5e2`, clones `d36ed77d5f83957742f07be79680cbd8ac3a417eb0ec985e2f563bcd3301f4d6`, clone_facts `6acfe223b7b11096198f3b3e687f764f0ea4678cfdb0f814237e7f911266408d` | API calls, clone disk | UNKNOWN |
| S4 filter | S3 outputs | `s4-filter/funnel.py` (`--near-miss` gives v4) | `s4-filter/frame.csv` (`.xz`, 25,263 projects) | `d99faef7d0a0344495037ff7a9f9d3364342b7afc92007e44edec5288668cf56` | none | UNKNOWN |
| S4 v4 frame | S4 outputs, the DP8L audit | `s4-filter/funnel.py --near-miss`, `s4-filter/supplement_batch.py N [V]` | `frame.v4.csv`, `frame_status.v4.csv`, `supplement.v4.csv` | copy: `30954b26b3117296c2b672859f4b119dc755dc97546a15280d86f897efb57f30`, `28a67d7046d2259d660a72057f0e5676f26ac3e1f80b5befe729850df555304b`, `311af7c5dc3282ca21a03a3a99452c1389713ab31ae90f5ba6aff2270dce16e9` | none | UNKNOWN |
| S5 evidence | frame, pool, rosters, company pages, org profiles | `s5-evidence/build_evidence.py [--frame F ...] [--pool P ...] [--out evidence.csv] [--counts counts.txt]` | `s5-evidence/evidence.csv` | copy: `53fa6cce5b94335f6de6e9db1d710b1d80f7074d8842e9c1d30597cb93805146` | none | UNKNOWN |
| S6 labels | `evidence.csv`, frame | `s6-labels/build_labels.py [--evidence ../s5-evidence/evidence.csv] [--frame F ...]`; GitLab rows: `s7-run/labels_batch25.py`, `s7-run/labels_batch26.py` | `s6-labels/labels.csv`, `s7-run/labels.batch25.csv`, `s7-run/labels.batch26.csv` | copy: `042a6f7eff21573fd62abef3aeab7b1cb3d897be4ad09d8248b073f31ac424f0`, `82fefe2b81d70f227a9f433a7c5b0a5d87092b896cd9e5b7ad52a6176b6075e8`, `6c8a1b98c2439df835c533e66e60de28cc92b85f9e3985cc63ce953cd1b38127` | none | under 1 s (test run) |

`make stage-hashes` checks every value in this table that is not marked "copy".
`make select` prints "not ready": the offline replay of S4-S6 is not wired into one command yet.

## 4. Build (S7)

### 4.1 Manifests

`pipeline/s7-run/build_run.sh` cuts the frame into run layers and batches. It calls
`build_manifest.py` of ctp (copy: `tools/ctp/build_manifest.py`) and `enrich_meta.py`.
The split scripts (`split_batchN.py` and others) make the parts of each batch.
`pipeline/s7-run/SHA256SUMS` records the sha256 of 431 files: the frames, the sidecars
(`project_meta.*.json`), the manifests and the parts. For example:

| File | sha256 |
|---|---|
| `manifest.layer1.tsv` | `19e869c9990154a176610c314986f1cc3162f9529fe82d62ef3fe609a5bf77ee` |
| `manifest.batch25.tsv` | `ec96e8f8712a384071394a6a5517e0420244887a433ebfcf8d0092e17f5a272d` |
| `manifest.batch26.tsv` | `52310bb9c195798851302c67ecb6ead376f714659e54b570261363ac4b5aebf0` |

A manifest row has the columns `name url category file_filter size_class [commit]`.
A sidecar is a JSON object: one record of 29 provenance fields for each manifest name.

### 4.2 The run of one batch

Each machine ran ctp on its part manifests. The command of the spot machines was:

```
CTP_CONFIG=$CFG .venv/bin/python ctp.py census --manifest "$M" --project-meta "$I/project_meta.$WL.json" \
  --workers "$WORKERS" --retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 \
  --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb "$FLOOR"
```

(`census` is the name of the ctp subcommand.) `pipeline/s7-run/local-d/run.sh` is a local
example of the same command. `CTP_CONFIG` names a file with `cregit_dir` (the cregit
checkout) and `output_dir`. The machines took ctp and cregit from the bundles of
`tools.lock`.

Before a machine started, it made the libexpat gate file (libexpat at commit
`a76b1174c1ea52abb639a4c69d52b630a8a106a2`) and compared its sha256 with the value of
`tools.lock` (column gate_sha256). `pipeline/s7-run/local-*/gate-result.txt` shows the
local results.

Output for each project: `<name>/<name>-dataset.parquet`, and `<name>/<name>.validated`
(`rows=N bytes=S`). A publish step copies them to `done/<name>/` and writes `OK` last. The
first line of `OK` is `<sha256>  <name>-dataset.parquet`.

### 4.3 Which tools each run used

`tools.lock` gives the cregit commit of each run. In short: batch1rest and batches 2-6 used
95cdc88 (one batch 6 project used 9ccead6). Batches 7-18 used 1f17663, and from 2026-10-11
also 57551d7. Batches 19-26, L23 and L1r used 57551d7. One project (local-d) used 23e4ccb.
ctp was ca113e3 on every run. srcML was the same build on every run, except the batch 1
local run (157cf8b). The L1r run reruns the projects of that run.

Each cregit commit has a git bundle in `tools.lock`. The bundles of 9ccead6, 1f17663,
57551d7 and 23e4ccb need 95cdc88 first (`cregit-ec2.bundle`, a complete bundle). 157cf8b
is an ancestor of 95cdc88, so `cregit-ec2.bundle` holds it. The bundle
`srcml-543fed6a.bundle` holds the two srcML fork commits (50a63193 and 543fed6a). It needs
srcML d382719 first (upstream, public). The patch `tools/cregit/nix/srcml-nontermination.patch`
is byte-identical to `git diff d382719 543fed6a`. Each bundle was checked on 2026-10-14 in
a new repository: fetch the base, fetch the bundle, check out the commit, and compare
`git rev-parse HEAD^{tree}` with the source.

The cregit jars, devenv and the ctp venv were the same on every run (section 1). The jar
files have a different sha256 by machine, but the same content. The tokenizer programs
`srcml2token` and `rust_tokenizer` were built on each machine too. Their sha256 differs
between the local machine and EC2 (`tools.lock`, row tokenizer-bin). The libexpat gate had
the same sha256 on each machine.

### 4.4 Cost and time

| Item | Value | Kind |
|---|---|---|
| Total cost of the build on EC2 | about US$1,600-1,800 | estimate |
| Total time | several days on EC2 (many machines in parallel) | estimate |
| On-demand machine | about US$5.70 per hour | recorded rate |
| Spot machines (i4i.24xlarge and similar) | US$1.73-2.85 per hour | recorded rates |
| libexpat gate, one machine | about 3 min (2026-10-11 04:27:51 to 04:30:36 UTC) | measured |
| connectionlens (387,925 rows), one worker | about 8 min (2026-10-14 14:53 to 15:01 UTC) | measured |

`make build` prints "not ready": the runner scripts of the EC2 machines are not in a
source repository yet.

### 4.5 One project again: `make rebuild-one PROJECT=<owner__repo>`

The target runs `scripts/rebuild-one.sh`. The steps:

1. Find the project in the manifests and the sidecars of `pipeline/s7-run`. (Works.)
2. Check the bundles in `TOOLS_DIR` (default `tools/bundles`) against `tools.lock`. (Works.)
3. Find the published sha256 in `data/SHA256SUMS`. (Not ready: the file has no rows yet.)
4. Find the tool versions of the published file in its ledger. (Not written.)
5. Run ctp with the pinned commit (manifest column 6, without `--latest`). (Not written.)
6. Compare the sha256. (Not written.)

Steps 4 and 5 are not written, for these reasons:

- The per-project ledger (the cregit commit and the pinned commit of each published file)
  is not in this repository. It goes into the dataset release.
- ctp runs each cregit step through devenv at the fixed path `~/.nix-profile/bin/devenv`,
  in a cregit checkout with the built jars. The flake now gives the two parts
  (`nix profile add .#devenv` and `packages.cregit-jars`, section 1). The script does not
  use them yet.

Step 2 checks only the git bundles. The flake checks the jar files (by their sha256, when
you build `packages.cregit-jars`).

Two facts limit a byte-for-byte comparison:

- The trailer post-fix rewrote the `footer_*` columns of the 95cdc88 Parquet files
  (`pipeline/s7-run/rewrite_footer_columns.py`). So for a 95cdc88 project, a rebuild is a
  new run on 95cdc88 and then the post-fix. cregit 1f17663 and later make these columns in
  the run, but the equality of the two routes was not measured on all projects (UNKNOWN).
- `pipeline/s7-run/rewrite_meta_columns.py` fills 11 metadata columns from the final sidecar
  (`project_meta.layer1.final.json`, sha256
  `49e13f0644bd26768d6587041e83f8af21a974172af9f37bdfd2620ea9acc513`). Use that sidecar
  for a rebuild.

The gate shows that a rerun is byte-identical when the commit, the flags and the tools are
the same: the libexpat gate file has the same sha256 on each machine. A rerun with other
`--workers`, `--blame-jobs` or `--memory-limit` values was not compared (UNKNOWN).

## 5. Merge

`pipeline/s7-run/prelim_merge.py` builds a preliminary DuckDB view over the run
directories. It is not the final merge. It reads local paths of the run machines.
`make merge` prints "not ready": the final merge script is not written yet.

## 6. Validate

| Check | Where | Status |
|---|---|---|
| Each Parquet file is larger than 10,000 bytes, has rows, and has the 70-column contract. | `tools/ctp/validate.py` (writes `.validated`), `tools/ctp/validate_schema.py` | runs in the build |
| Each fetched Parquet file has the sha256 of its `OK` file. | `pipeline/s7-run/fetch_done.sh` | runs after the build |
| Each published file has the column contract. | `make validate DATA_DIR=<dir>` | works; proof on 2026-10-14: the connectionlens file gives `OK ... (70 columns)` |
| Each published file has the sha256 of `data/SHA256SUMS`. | `make verify DATA_DIR=<dir>` | not ready: no rows yet |

## 7. UNKNOWN values

| Item | Why |
|---|---|
| libexpat gate of cregit 157cf8b | No gate file was found for this commit. |
| The cregit jars, the tokenizer programs and the ctp venv on the run machines that were terminated before 2026-10-14 | Only the local machine, spot a, spot b and the big EC2 were checked. All jars of these four machines have the same content. |
| Run time of each selection stage | Not recorded in this repository. |
| Byte identity of a rerun with other worker, blame-job or memory flags | Not measured. |
| Equality of "95cdc88 run plus the trailer post-fix" and "a run on 1f17663 or later" | Not measured on all projects. |

Found on 2026-10-14 (no longer UNKNOWN):

- The bundles of cregit 23e4ccb and of the srcML fork commits: `tools.lock` gives the
  file, the sha256, the size and the base. cregit 157cf8b is in `cregit-ec2.bundle`.
- The ctp bundle in object storage: the storage records no sha256. Its size, its ETag (the
  MD5 of a one-part upload) and its CRC64NVME checksum are equal to the values of the local
  file. So it is the same file, with the sha256 of `tools.lock`.
- The packages of the ctp venv on EC2: `tools/ctp-venv/`.

## 8. Left for later

- Fill `data/SHA256SUMS` at the v1 freeze. Then `make verify` works.
- Publish the tool bundles (`tools.lock`), the per-project ledgers and the final sidecar
  with the dataset. Then finish steps 4-6 of `rebuild-one`.
- Upload the new bundles and jars (`~/s3-work/upload-tool-bundles.sh`, run by the user).
- Commit the EC2 runner scripts (machine setup, part feed, restart, publish) to a source
  repository, remove the account data, and copy them here. Then `make build` can work.
- Write the final merge, and the offline replay of S4-S6 (`make select`).
- Decide on the web captures that are not copied: `rosters/raw/` (except the ASF
  `projects.json` that S5 reads) and `sources/company-pages/raw/`, and the Spinellis
  dataset tarball (Zenodo record 3742962, `sources/spinellis-2020/FETCH.tsv` gives its
  MD5). They are third-party pages and files, about 250 MB.
- Work through `ANONYMIZATION-TODO.md`, including the kind census-name.

## 9. How `pipeline/` and `tools/` are made again

```
sync/make-sources-list.sh study <commit>     # then review the diff of sync/sources.tsv
sync/make-untracked-list.sh study <commit> '^(frame|project_meta)\.' s7-run/SHA256SUMS ...
sync/sync-from-sources.sh                    # copy and check
sync/anonymity-scan.sh                       # write ANONYMIZATION-TODO.md again
```

`sync/rules.tsv` selects the files. `sync/sources.local.conf` (local only) gives the local
clone of each source.
