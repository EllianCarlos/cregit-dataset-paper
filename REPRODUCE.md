# How to reproduce the cregit token dataset v1

This file gives, for each stage, the inputs, the command, the expected output hash, the
cost and the time. A value with the word "estimate" is an estimate. "UNKNOWN" means that
no record was found. "copy" in a hash column means the sha256 of the copied file in this
repository, because the stage did not record a value when it ran.

The selection of dataset v1 (S1-S6) gave 3,548 projects: 3,497 from run layer 1 and its
supplements, 50 from GitLab hosts (batch 25) and 1 GitLab near miss (batch 26).
`pipeline/SELECTION-STAGES.md` gives the rules. The merge of the 5,000+ layer (section 5.1)
gave 3,544 files, and BRL-CAD__brlcad came in a later separate write: the 5,000+ layer of the
release has 3,545 files. 3 selected projects have no file.

The release (user decision, 2026-10-23) is one dataset of 10,754 project files in two
commit layers: the 5,000+ layer (5,000 or more commits: the v1 build, 3,544 files, and
BRL-CAD, 1 file of a later separate write) and the 1,000-4,999 layer (1,000 to 4,999 commits:
7,209 files). It has 32,635,174,618 token rows. The release files are 162,472,453,753 B
(162.5 GB, ZSTD 19) in the release root `dataset-release-1`. The run output was 241.3 GB. Sections 1-4.5 give
the build of the 5,000+ layer. Section 4.6 gives the runs of the 1,000-4,999 layer, section
4.7 the path-fix rerun, and section 5 the merge, the links and the open steps.

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
| `make sync-check` | Each file under `pipeline/` and `tools/` has the git blob id of `sync/sources.tsv`, or the sha256 of `sync/untracked.tsv`. | `OK: 879 files match sources.tsv, 104 files match untracked.tsv`; on 2026-10-25: `OK: 1319 files match sources.tsv, 104 files match untracked.tsv` (before the sync of the later kits, section 4.4); on 2026-10-28: `OK: 1517 files match sources.tsv, 105 files match untracked.tsv`. It needs a git repository (it runs `git ls-files`). In the anonymous export it reports the 3 files of `EXPORT-REDACTIONS.tsv` as CHANGED. |
| `make stage-hashes` | The stage outputs match the sha256 that each stage recorded (section 3 and 4). | `OK: the stage outputs match their recorded sha256` |
| `make test` | The tests of the copied scripts (in the dev shell). | S5: 10 passed, 10 skipped. S6: 25 passed. S7: 96 passed, 3 skipped. On 2026-10-28: S5: 10 passed, 12 skipped. S6: 25 passed. S7: 128 passed, 4 skipped. One S7 test reads `git show HEAD:`, so the tree must be a git repository. |

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

Web captures (user decision, 2026-10-25): the release publishes the fetched third-party pages
and files that the stages read (`rosters/raw/`, `sources/company-pages/raw/`, the Spinellis
tarball), each with its URL, its fetch date and its sha256. They are third-party content, so
`THIRD-PARTY.md` gives a license note for each source. This repository does not copy them.

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
On 2026-10-15 the blame script of 4 running copies (google-cloud-java, lean4,
asuswrt-merlin.ng, liferay-portal) changed to 365a47a; their ledgers name 57551d7
(liferay-portal: 1f17663). The 1,000-4,999 layer used 57551d7. The path-fix rerun
(35 projects) and BRL-CAD__brlcad used 14b8db4. Thus seven cregit commits wrote the files of
the release. Each commit is on a public branch (`tools.lock`, the notes of each row).
ctp was ca113e3 on every run. srcML was the same build on every run, except the batch 1
local run (157cf8b). The L1r run reruns the projects of that run.

Each cregit commit has a git bundle in `tools.lock`. The bundles of 9ccead6, 1f17663,
57551d7, 23e4ccb, 365a47a and 14b8db4 need 95cdc88 first (`cregit-ec2.bundle`, a complete bundle). 157cf8b
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

The scripts that ran the build on EC2 are in `pipeline/s7-run/runner/`: machine setup,
install, part feed, restart, watchdog and publish. `runner/INVENTORY.tsv` lists each file of
the original work directory, and the reason to copy or skip it. `runner/ORIGIN.tsv` gives
the source sha256 of each copy. 225 copies are verbatim. 210 copies have tokens
`${RUNNER_*}` in place of the account values (bucket, account id, profile, region, EC2 ids,
home paths). `python3 -I pipeline/s7-run/runner/render.py --check` checks the copies.
With your values in `runner/runner.env`, `render.py --out DIR` gives files that you can run.

The kits of the later runs (2026-10-16 to 2026-10-24) were copied into the study repository
on 2026-10-25 with the same rule: `runner/dataset-v1/` (the merge of the 5,000+ layer),
`runner/dataset-x1k/` (the runs, the merge and the links of the 1,000-4,999 layer),
`runner/dataset-pathfix/` (the path-fix rerun) and `runner/dataset-v0-org/` (the organization
columns of version 1). That adds 192 copies: 75 verbatim and 117 with tokens, so 300 verbatim
and 327 with tokens in total. The new tokens are the EC2 ids of the later machines and the four
subnets by availability zone (`runner.env.example`). The copy step checked each new copy: the
copy with the values put back is equal to the original, and no identifying pattern of the scan
is left (the only hits are fake EC2 ids of 4 test files; `sync/anonymity-allow.tsv` lists them).
The copy step did not read the environment file of machine A (`dataset-x1k/scripts/a/vols.env`,
the volume ids); it is not copied. These copies come into `pipeline/` at the next sync, after
the study commit (section 9).

`make build` prints "not ready": the full build needs an AWS account, a bucket and many
machine-days. Use `make rebuild-one` for one project.

### 4.5 One project again: `make rebuild-one PROJECT=<owner__repo>`

The target runs `scripts/rebuild-one.sh`. Section 6.1 gives the rule of the comparison. The
steps:

1. Find the project in the manifests and the sidecars of `pipeline/s7-run`.
2. Check the tool sources: the ctp bundle and the cregit bundle of the run in `TOOLS_DIR`
   (default `tools/bundles`) against `tools.lock`, or a ctp clone (`CTP_DIR`) and a built
   cregit tree (`CREGIT_DIR`). An incremental cregit bundle (`bundle_requires` is not "-")
   also needs the bundle of its base commit: the script clones the base bundle and fetches the
   bundle of the run, as the run machines did. Check the final sidecar of the layer before the
   ctp run. ctp runs each cregit step through devenv at the fixed path
   `~/.nix-profile/bin/devenv` (`nix profile add .#devenv`, section 1).
3. Find the published sha256 in `data/SHA256SUMS`.
4. Find the run record in `data/REBUILD-TARGETS.tsv`: the run commit (the commit that the run
   checked out; all runs used `--latest`, so this is not manifest column 6), the cregit and
   ctp commits, the run sidecar and the three target sha256 values.
5. Run ctp with the run commit (in the manifest row, without `--latest`), a sidecar with the
   entry of the run sidecar, and the flags of the dataset build. With a bundle, the script
   builds cregit as the run machines did (`run_pipeline_process.sh --build-only` and
   `make -C tokenize/srcMLtoken` in the devenv shell) and prints the sha256 of the blobExec
   jar against `tools.lock`.
6. Compare: (a) the run output with `merge_input_sha256`; (b) the output of
   `rewrite_meta_columns.py --encoding v1` with the final sidecar of the layer with
   `pre_pseudonym_sha256`; (c) if `DATA_DIR` has the published file, the column rule
   (`scripts/compare_published.py`).

Status on 2026-10-28: steps 1-6 are written. Without the bundles (not published yet), step 2
prints "not ready". With local tools (`CTP_DIR`, `CREGIT_DIR`, `CTP_PYTHON`) the target
passes (a) and (b) for libexpat__libexpat, and (c) passes on its published file (section 6.1).
The bundle path of step 5 was checked on 2026-10-28 with small test bundles only. The v1 final sidecar
`project_meta.v1.final.json` (sha256 `4023295a...`) is in `pipeline/s7-run`; the final
sidecar of the 1,000-4,999 layer is not synced yet (set `MERGE_SIDECAR`).

These facts limit the targets:

- The trailer post-fix rewrote the `footer_*` columns of the 95cdc88 Parquet files
  (`pipeline/s7-run/rewrite_footer_columns.py`). For these 815 files the merge input is the
  post-fix file (`merge_input = post-fix`), and the script stops with "not ready". cregit
  1f17663 and later make these columns in the run, but the equality of the two routes was not
  measured on all projects (UNKNOWN).
- The gate shows that a rerun is byte-identical when the commit, the flags and the tools are
  the same: the libexpat gate file has the same sha256 on each machine, and the rebuild of
  2026-10-28 gave the sha256 of the run of 2026-10-13. A rerun with other `--workers`,
  `--blame-jobs` or `--memory-limit` values was not compared (UNKNOWN).
- Set `TZ=UTC` for the run. slickgitlog writes `author_date` and `committer_date` in the time
  zone of the JVM, with no UTC offset. The run machines used UTC. Neither devenv nor ctp sets
  `TZ`, so a run on a machine in another time zone gives other bytes.
- The fallback to plain blame after 3600 s of `-C100` depends on the machine (its load, the
  parallel jobs, the restarts). No option makes plain blame for a given list of files, so a
  rebuild can make another choice for such a file and give other bytes. The blob exclusions of
  the tokenizer step (600 s of wall time for one blob) can also depend on the load.
- The tokenizer cache key does not include the language. With parallel workers, the same bytes
  at `x.h` and `x.cpp` can get the C or the C++ parse, so a rerun is not byte-identical for
  such files (about 0.0125% of the tokenized blobs in the pilot run; dataset v1 not measured).
- Some inputs are not pinned. Step 10 of cregit runs `INSTALL sqlite_scanner`, so DuckDB
  downloads the extension from the network (the build on the run machines is not recorded; the
  local machine has `f79b1db` for DuckDB 1.5.5). The tools do not set `GIT_CONFIG_NOSYSTEM` or
  `GIT_CONFIG_GLOBAL`, so the git configuration of the machine can change the blame. The
  pseudonymizer takes the newest Public Suffix List in `/nix/store` (the release used the list
  with sha256 prefix `65365c4c9a4a`); this does not touch the targets (a) and (b).

### 4.6 The runs of the 1,000-4,999 layer (2026-10-17 to 2026-10-23)

The kit is `pipeline/s7-run/runner/dataset-x1k/` (after the next sync). Its `README.md` is the
runbook: each step, each user decision and the log of each machine.

Inputs. The frame has 7,215 projects of frame v4 with 1,000 to 4,999 commits. The study
repository builds the inputs in `x1k/` (`build_x1k.py`, `run_build.sh`): the manifest
`manifest.x1k.tsv`, the 4 part manifests, the parts, the sidecar `project_meta.x1k.json` and the
final sidecar `project_meta.x1k.final.json` (sha256
`1520c5f4d8909b3625c73bdea3cc08f23fced0a77f3722ec0809acd80de96f35`). The stage of the kit
(`stage/SHA256SUMS`) has the same sha256 values. These inputs are not in the copy rules yet
(section 8).

The code path is the code path of the v1 batches 23-26: ctp ca113e3 (no patch), cregit
57551d7, the srcML build of section 1 (libsrcml `dea4467b...`) and the libexpat gate
`14eb5d72...`. The flags are the flags of the v1 parts, with `--disk-floor-gb 300` and 5 or 6
workers for each part:

```
--retries 3 --skip-html --latest --tokenizer-worker --blame-jobs 4 --memory-limit 16GB
--min-free-mem-gb 24 --disk-floor-gb 300
```

The runs, in order:

1. The first machine (dataset-x1k-a, from 2026-10-17 15:48 UTC) ran ctp with the patch
   `stage/ctp-no-firm.patch` (no firm step). The spot reclaim of 2026-10-18 22:02 UTC stopped
   it after 1,377 rows. The relaunch ran these rows again, so no file of the dataset comes from
   this run.
2. Machine B: two machines (dataset-x1k-b1 and dataset-x1k-b2, 2026-10-19/20) ran 7,204 rows
   in 8 parts. The deal is fixed: the heavy rows first, longest first. Steps: `L1-launch-b.sh`,
   then through `scripts/ssm.sh`: `scripts/R1-setup.sh`, `scripts/R2-gate.sh` (4 x "CHECK
   OK": the libexpat file of each part is `14eb5d72...`), `scripts/w6/R3-install-b.sh`,
   `scripts/w6/R4-start-b.sh`. Output: `done-full/<name>/` with `OK` last. At the end, 7,198
   rows had `OK`. 6 rows failed: 4 had no C, C++, Java or Rust file at the pinned commit, and 2
   failed on the cregit path defects (section 4.7).
3. Machine A: the 11 long rows, one worker each, on 4 EBS volumes (`L0-volumes.sh`,
   `L1-launch-a.sh`, `L2-attach.sh`, then `scripts/a/R1-setup.sh` to `scripts/a/R4-start.sh`).
   Each row has its own blame jobs and memory limit, and `--workers 1 --retries 10
   --disk-floor-gb 50` (`README.md`, "Rows, slots and flags"). After a spot reclaim, the run
   script starts ctp again with `--from-step` (the resume rule of the runbook). A local test of
   the resume rule gave the gate file `14eb5d72...` byte for byte. Machine A had four machines
   in turn (`dataset-x1k-long-a`). For aws-sdk-rust, `scripts/a/R10-retry-rust.sh` set
   `--retries 30`, because each restart counts as a failed attempt.
4. The extra machines. `rust-split/` (spot, 5 parts) and `java-split/` (2 on-demand machines)
   ran the blame step of aws-sdk-rust and aws-sdk-java with the blame code of 57551d7 and gave
   the `.blame` files back to machine A. For aws-sdk-java: 65,087 `.blame` files, and a byte
   gate of 30 of 30 files on both machines.
5. The path-fix rerun (section 4.7) gave the 2 rows with the path defects.

Result: 7,215 rows in the frame, 6 rows out of scope (no C, C++, Java or Rust file at the
pinned commit: greta, loaders.gl, semantic-router, Librelancer, neuro-book and
blue_archive_auto_script), 7,209 files. The last row (aws-sdk-rust, 293,153,594 rows) ended on
2026-10-23 at 16:53:50 UTC. 367 files in 98 projects fell back to the plain blame (machine A
229 files in 6 projects, machine B 138 in 92, the path-fix rows 0, the extra machines 0).

Cost: the runbook gives estimates (machine B about US$120). The final cost is not recorded.

### 4.7 The path-fix rerun (2026-10-20)

The kit is `pipeline/s7-run/runner/dataset-pathfix/` (after the next sync). cregit 14b8db4 is
57551d7 plus the fix of two defects of the blame step: a path that git quotes (a non-ASCII byte,
a quote, a backslash, a tab or a newline) and a path that starts with "-" (`tools.lock`, row
14b8db4). A scan of all trees found 36 projects with lost source bytes (18 in each layer).

- The rerun ran 35 rows on one machine (dataset-pathfix-b1): 17 rows of the 5,000+ layer and 18
  rows of the 1,000-4,999 layer. By the user's decision, `alibaba__AliSQL` did not run again
  (a LIMITATIONS line).
- Each row used the commit of its first run: `stage/inputs/seeds.tsv` writes the state of
  `--latest` before the start, so ctp reuses that commit.
- The gate stayed `14eb5d72...` (local gate of 2026-10-20 and the R2 gate of the machine).
- End: 2026-10-20 23:25 UTC, 35 of 35 rows with `OK` in `done-pathfix/`.

The merge of the 1,000-4,999 layer takes `done-pathfix/` before `done-full/` (section 5.2).
For the 17 rows of the 5,000+ layer, see section 5.6.

## 5. Merge, links and the open steps

`pipeline/s7-run/prelim_merge.py` builds a preliminary DuckDB view over the run
directories. It is not the final merge. It reads local paths of the run machines.
`make merge` prints "not ready". The merges ran on EC2 through the kits below, and one local
entry point is not written (section 8). The message of the target is older than these kits.

Both merges use the same two tools (`tools.lock`, rows merge-tool): `final_merge.py` (sha256
`acede0d8...`) and `rewrite_meta_columns.py` (sha256 `365867b0...`), from study commit
17bc439. For each project, `final_merge.py` copies the run file and checks its sha256. Then
`rewrite_meta_columns.py` writes the 11 metadata columns from the final sidecar (ZSTD 19, 1 M-row
groups, Parquet V2) and compares every other column row by row. Then `validate_schema.py` of
ctp ca113e3 (sha256 `2efe32c3...`) checks the column contract, and the file goes to the
destination. Each done project gets a row in `results.tsv`, so a second start continues. At
the end the destination gets `SHA256SUMS`, `results.tsv` and the sidecar.

### 5.1 The merge of the 5,000+ layer (v1-raw, 2026-10-16/17)

- Kit: `pipeline/s7-run/runner/dataset-v1/`. `build_inputs.py` writes `inputs.tsv`: one row for
  each project (the run, the cregit commit, the token rows, the bytes, the S3 key and the sha256
  of the run file).
- Sidecar: `project_meta.v1.final.json` (sha256
  `4023295abc589a5eb0f4124e0aa76000402bd2492755e62f50af03121f661946`, 3,548 keys).
- Command: `M1-start-merge.sh` (and the later variants `M1b`, `M1c`) through `ssm.sh` on spot a.
  The scripts check the sha256 of the tools, the sidecar and `inputs.tsv` before the start.
- Output: `dataset-v1/raw/`, 3,544 files, 23,692,479,892 token rows, about 127 GB.

### 5.2 The merge of the 1,000-4,999 layer (x1k-raw, 2026-10-23)

- Kit: `pipeline/s7-run/runner/dataset-x1k/x2/`. `build_inputs_x1k.py` writes the input list
  from `done-full/`, the rows of machine A and `done-pathfix/`. A row of the path-fix list
  without `done-pathfix/<name>/OK` is held back.
- Steps: `L1-launch-x2.sh`, then through `ssm-x2.sh`: `R1-x2-setup.sh` (checks the sha256 of the
  tools, of the sidecar `1520c5f4...` and of `validate_schema.py`), `R2-x2-inputs.sh`,
  `M1-x2-start.sh`; `M2-x2-check.sh` and `D1-x2-fail.sh` are read-only probes.
- Pass 1 on dataset-x1k-raw-1. Pass 2 (the 4 slow rows: Retro68, metashell, aws-sdk-java,
  aws-sdk-rust) on dataset-x1k-raw-2, done at 19:31 UTC.
- Output: `dataset-x1k/raw/`, 7,209 of 7,209 files, 0 failed, 8.93 B token rows, 36.81 GB
  (55.09 GB in), with `SHA256SUMS`, `results.tsv` and `rewrite.tsv`.

### 5.3 The links of both layers (2026-10-24)

- Kit: `pipeline/s7-run/runner/dataset-x1k/x3/`; the tools are in `x3/stage/` (`tools.lock`, row
  links-kit; SHA256SUMS sha256 `7dba806bb9e3...`). The links need the address column, so they
  were built on the machine: `extract_domains_v1.py` makes the per-author domain cache from the
  raw files, and `build_links.py` maps the domains and the namespaces to the organizations of
  `companies.v4.6.duckdb`. The addresses do not leave the machine.
- Steps: `S0-x3-stage.sh` (local), `U1-upload-x3.sh` (the user), `L1-launch-x3.sh`, then through
  `ssm-x3.sh`: `R1-x3-setup.sh`, `M1-x3-start.sh`; `M2-x3-check.sh`; `F1-x3-fetch.sh` fetches the
  outputs without addresses.
- Gate: a run with the v1 cache only gave links-v4.6 byte for byte (mapping `2fb053cd1ee7`).
  The caches match the inputs: 3,544 files and 23,692,479,892 tokens (5,000+ layer), 7,209 files
  and 8,933,548,968 tokens (1,000-4,999 layer), 32,626,028,860 tokens in total.
- Output: the merged links (label v4.6, mapping `98f23158debd`): 10,763 projects (the frame
  keys) and 13,157 domain links. Each row of v1 is unchanged. Machine dataset-x1k-links-1
  (i4i.8xlarge spot) took 18 minutes.

### 5.4 The organization columns of version 1 (first write, 2026-10-21)

- Kit: `pipeline/s7-run/runner/dataset-v0-org/` (`README.md` is the runbook); tools in `stage/`
  (`tools.lock`, row org-kit): `run_v0.py` runs `build_v0.py` on each v1-raw file with
  links-v4.5.
- Output: `dataset-v0-org/parquet/`, 3,544 files, 125.83 GB, ctp schema 2 (71 columns).
- This write is not the final one: the release needs one write with the final database and the
  merged links of both layers (section 5.5).

### 5.5 Open steps

1. Organization database v4.8: the version after v4.7, with the review of the new domains and
   namespaces of both layers and the user check. Then the links again, the error model and the
   organization tables (`build_organizations.py tables`).
2. One write of the organization columns and the pseudonyms over all 10,753 files (one fused
   write; estimate about 8.5-9.5 h on 96 vCPU). It needs the final database, the final commit of
   `pseudonymize.py` (`tools.lock`: ctp 4be3800, then the hotfix a4b511b), the salt transfer, and the user's
   yes for the machine. The registry (real identity to pseudonym) stays private.
3. The release package: copy the files to `parquet/` and the tables to `organizations/`, run
   `build_organizations.py views`, then `fill_release.py manifest`, `checksums` and `check`; fill
   `data/SHA256SUMS`; the license note for each source in `THIRD-PARTY.md`; the Zenodo records.
4. `make verify` and `make rebuild-one` after the release (sections 4.5 and 6).

Spelling (the user's decision of 2026-10-28): the tools and the documents use "organization". The
release root `dataset-release-1` was written before that decision. It has the folder
`organisations/` (tables `organisations`, `organisation_domains`, `organisation_namespaces`,
`project_organisations`, column `organisation_id`) and the footer keys `organisations_version` and
`organisations_mapping_sha256`. `scripts/validate_schema2.py` and `build_organizations.py views`
accept both spellings.

Status on 2026-10-28: steps 1-3 are done with database v4.9: the one write of 10,753 files,
BRL-CAD__brlcad in a separate write with the same salt, and the release root
`dataset-release-1` (10,780 files). `data/SHA256SUMS` has its 10,754 project rows. Still open:
the final commit of the row pseudonymizer in `tools.lock`, the license notes of
`THIRD-PARTY.md`, the Zenodo records and step 4.

### 5.6 Open question: the path-fix rows of the 5,000+ layer

The input list of the v1 merge (`dataset-v1/inputs.tsv`, 2026-10-16) has no row with cregit
14b8db4: it is older than the path-fix rerun. The path-fix runbook says that these 17 rows
take the `done-pathfix/` key in `inputs.tsv`. This repository has no record that v1-raw or
`dataset-v0-org/` has the path-fix files. The one write of step 5.5.2 must take them.

## 6. Validate

| Check | Where | Status |
|---|---|---|
| Each Parquet file is larger than 10,000 bytes, has rows, and has the 70-column contract. | `tools/ctp/validate.py` (writes `.validated`), `tools/ctp/validate_schema.py` | runs in the build |
| Each fetched Parquet file has the sha256 of its `OK` file. | `pipeline/s7-run/fetch_done.sh` | runs after the build |
| Each published file has the column contract of ctp schema 2 (71 columns: the 67 cregit columns of ca113e3, then the 4 organization columns), the footer keys of the release write, the registry of `pseudonymization.json` and the rows of `MANIFEST.tsv`. | `make validate DATA_DIR=<release root>` (`scripts/validate_schema2.py`) | works; proof on 2026-10-28 with small test files (`scripts/test_release_checks.py`, `make test`: one good root passes; a schema 1 file, a wrong row count, a wrong registry, a file with no registry, a file with no row in `MANIFEST.tsv` and a file that cannot be read fail) and on the published file of libexpat__libexpat (OK). The release build checked the same contract on all 10,754 files (`schema.txt` of the build reports: 71 columns, footer schema 2, v4.9, mapping `7b52a5155e6f`, 32,635,174,618 rows, 0 problems). |
| Each published file has the sha256 of `data/SHA256SUMS`. | `make verify DATA_DIR=<release root>` | ready: `data/SHA256SUMS` has the 10,754 project rows of the release root `dataset-release-1` (its SHA256SUMS: `1293050b0c75...`). The run needs the downloaded files (162.5 GB). |

The 70-column contract of ca113e3 alone refuses every published file: the release write
replaced the 3 firm columns (`firm_raw`, `firm`, `firm_source`) with the 4 organization
columns. `scripts/validate_schema2.py` takes the 67 cregit columns from the ca113e3 copy
`tools/ctp/validate_schema.py` without a change.

### 6.1 The rule of `rebuild-one`

The published files went through the release write: the organization columns and the
pseudonyms of the identity columns, in one write, with a salt. The salt is deleted by design.
So no one can make the published bytes of a file again. `make rebuild-one` uses this rule:

1. The ctp run with the recorded tools and the recorded run commit gives the sha256 of the run
   output (`merge_input_sha256` of `data/REBUILD-TARGETS.tsv`).
2. The layer merge of that file (`pipeline/s7-run/rewrite_meta_columns.py --encoding v1` with
   the final sidecar of the layer) gives the sha256 of the file before the pseudonyms
   (`pre_pseudonym_sha256`). This is the input of the release write.
3. The published file has the rows of that file in the same order, and it is equal to that file
   in every column that the release write does not change. `scripts/compare_published.py`
   checks this. The release write changes only: the 7 identity columns (`author_name`,
   `author_email`, `committer_name`, `committer_email`, `personid`, `person_name`,
   `person_email`) and the 15 `footer_*` lists (each value that is not empty becomes a
   pseudonym, and the lists keep their length); `person_domain` (a value with no at sign
   becomes `lower(trim(value))`, a value with an at sign follows rule E); it removes
   `firm_raw`, `firm` and `firm_source`, and it adds the 4 organization columns.
   The release write does not change `commit_summary`, so it must be equal.
   The pseudonym is a salted hash of the value in lower case (`pseudonymize.py`). So the script
   checks, for each identity column: one value gives one pseudonym; values that are equal in
   lower case give one pseudonym; values that are not equal in lower case give different
   pseudonyms (not for the 13 trailer text lists: the write parses each trailer line, so two
   lines that differ only in spaces can give one pseudonym); no value that is not empty stays
   the same. NULL and the empty value do not change.

The run commit is the commit that the run checked out (the ledger `pinned_sha`). All runs used
`--latest`, so it is not column 6 of the S7 manifests (the frame commit). The run reads only
the entry of the project in its `project_meta` sidecar: the script takes a sidecar under
`pipeline/s7-run` whose entry has the recorded sha256 (`run_meta_entry_sha256`).

Proof on 2026-10-28 (local machine, libexpat__libexpat, ctp ca113e3, cregit 57551d7, run commit
ac140c2d, duckdb 1.5.5): the ctp run gave `2dcc77fd...85df8dc` (2,198,503 B, equal to the run
of 2026-10-13), and the merge step gave `e67bf24e...6f8f8` (1,701,870 B, equal to the input of
the release write). The published file is `6e034dca...c32c3de` (1,685,462 B). Step 3 on
2026-10-28 (the merge step again from the run file of 2026-10-13, then
`scripts/compare_published.py` on the downloaded published file): OK, 195,672 rows in the same
order, 44 columns equal, 22 identity columns follow the pseudonym rule.
`scripts/test_release_checks.py` (`make test`) checks both scripts on small files.

Limits of the rule:

- 815 files have a merge input that is the trailer post-fix of the run output
  (`merge_input = post-fix`). The script does not run the post-fix step yet.
- 17 files of the path-fix rerun have a run record that matches by rows only
  (`run_record = rows-only`).
- 7,209 files of the 1,000-4,999 layer need the run sidecar `project_meta.x1k.json` and the
  final sidecar of the layer (`project_meta.x1k.final.json`) under `pipeline/`. They are not
  synced yet, and 475 of these projects are in no manifest under `pipeline/s7-run`. The v1
  final sidecar is in `pipeline/s7-run` since 2026-10-28.
- Count on 2026-10-28 (steps 1-4 and the sidecar entry, with the files of this repository):
  2,680 files, all of the 5,000+ layer, get to the ctp run of step 5.
- 33 files have no entry sha256 of the run sidecar (`run_meta_entry_sha256` is empty): 32 with no
  unique copy of the run sidecar, and BRL-CAD__brlcad (its run summary comes from its own kit).
- The effect of other worker, blame-job and memory flags on the bytes is not measured
  (section 7). The script uses the flags of the dataset build: 1 worker, `--blame-jobs 4`,
  `--memory-limit 6GB`, `--tokenizer-worker`, `--skip-html`.

## 7. UNKNOWN values

| Item | Why |
|---|---|
| libexpat gate of cregit 157cf8b | No gate file was found for this commit. |
| The cregit jars, the tokenizer programs and the ctp venv on the run machines that were terminated before 2026-10-14 | Only the local machine, spot a, spot b and the big EC2 were checked. All jars of these four machines have the same content. |
| Run time of each selection stage | Not recorded in this repository. |
| Byte identity of a rerun with other worker, blame-job or memory flags | Not measured. |
| Equality of "95cdc88 run plus the trailer post-fix" and "a run on 1f17663 or later" | Not measured on all projects. |
| The slickGitLog, persons and remapCommits jars on the machines of the 1,000-4,999 layer and of the path-fix rerun | The machines are terminated. Their gate and their ledgers record only the blobExec jar. |
| The final cost of the build, the runs of the 1,000-4,999 layer and the release steps | Not recorded (PLAN.md, item B5). Section 4.4 and the runbooks give estimates. |

Checked again on 2026-10-25, still UNKNOWN: the gate of 157cf8b (the only libexpat file of
that run has no ledger, and the gate procedure did not make it) and the three jar rows (the
ledgers record only `blobexec_jar_sha256`). No file fills them.

Found on 2026-10-14 (no longer UNKNOWN):

- The bundles of cregit 23e4ccb and of the srcML fork commits: `tools.lock` gives the
  file, the sha256, the size and the base. cregit 157cf8b is in `cregit-ec2.bundle`.
- The ctp bundle in object storage: the storage records no sha256. Its size, its ETag (the
  MD5 of a one-part upload) and its CRC64NVME checksum are equal to the values of the local
  file. So it is the same file, with the sha256 of `tools.lock`.
- The packages of the ctp venv on EC2: `tools/ctp-venv/`.

## 8. Left for later

- Add the rows of the other release files to `data/SHA256SUMS` from the SHA256SUMS of
  `dataset-release-2` (the project rows are there since 2026-10-28).
- Publish the tool bundles (`tools.lock`). Sync the final sidecars of both layers and the run
  sidecar of the 1,000-4,999 layer into `pipeline/`. Then `rebuild-one` needs no local paths
  (section 6.1).
- Write one entry point for `make build` over the runner scripts of `pipeline/s7-run/runner/`.
  Now each batch has its own scripts.
- Write one local entry point for `make merge` over the merge kits (section 5), and the
  offline replay of S4-S6 (`make select`).
- The steps of section 5.5: database v4.8, the one write of the organization columns and the
  pseudonyms, and the release package.
- Sync the later kits into `pipeline/` after the study commit (section 9).
- Add the inputs of the 1,000-4,999 layer (study `x1k/`) to `sync/rules.tsv`. First fix the
  identifying text of `x1k/README.md` and `x1k/run_build.sh` at the source (a home path, the
  bucket and EC2 ids).
- The web captures (user decision, 2026-10-25): publish them with the release, each with its
  URL, its fetch date and its sha256: `rosters/raw/` (except the ASF `projects.json` that S5
  reads), `sources/company-pages/raw/`, and the Spinellis dataset tarball (Zenodo record
  3742962, `sources/spinellis-2020/FETCH.tsv` gives its MD5). They are third-party pages and
  files, about 250 MB. `THIRD-PARTY.md` needs a license note for each source.
- Work through `ANONYMIZATION-TODO.md`: the deferred hits (after the build ends, and at the
  export) and the kind census-name.

## 9. How `pipeline/` and `tools/` are made again

```
sync/make-sources-list.sh study <commit>     # then review the diff of sync/sources.tsv
sync/make-untracked-list.sh study <commit> '^(frame|project_meta)\.' s7-run/SHA256SUMS ...
sync/sync-from-sources.sh                    # copy and check
sync/anonymity-scan.sh                       # write ANONYMIZATION-TODO.md again
```

`sync/rules.tsv` selects the files. `sync/sources.local.conf` (local only) gives the local
clone of each source.

The copies of the later kits (section 4.4) are in the working tree of the study repository on
2026-10-25, not in a commit. `sync/sync-from-sources.sh` reads a commit only. So after the user
commits them: run `sync/make-sources-list.sh study <that commit>`, review the diff of
`sync/sources.tsv` (about 192 new rows under `pipeline/s7-run/runner/dataset-*/`, plus the
other study files that changed since e748945), then `sync/sync-from-sources.sh` and
`sync/anonymity-scan.sh`. `rules.tsv` never copies an environment file (`*.env`).
`sync/anonymity-allow.tsv` lists the scan hits that are not identifying text (checked by hand).
`sync/anonymity-deferred.tsv` lists the hits that wait: files that active jobs run until the
dataset build ends, and pinned tool copies to redact at the export.
