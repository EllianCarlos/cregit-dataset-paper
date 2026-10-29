# s0-pilot: the pilot run of September 2026

This folder is a frozen record of the pilot run. The pilot run came before the
selection stages (s1 to s6) and the dataset build of version 1. It tested the ctp
tool on a sample of 200 projects. Do not change these files. The later stages use
one file of the pilot run: `s2-pool/resolve.py` read `candidates.csv` as the old
pool (`SOURCES.md` names it at ctp commit `6ac22e7`; the bytes are equal).

## What the pilot run did

1. `select_corpus.py` built a pool of candidate projects (`candidates.csv`, 24,405
   rows). It gave each project a control label (community, company-owned or
   foundation) by the rules of `docs/CODEBOOK.md`.
2. On 2026-09-14, `select_corpus.py sample` drew 200 projects from the 3,842
   eligible projects of the pool (`manifest.sample.tsv`, `docs/CORPUS-SAMPLE.md`).
   The seed is 20261110. Each cell (control label, language, size class) got at
   least 2 projects. The other projects went to the cells in proportion to their
   size. The size classes are: S, fewer than 30,000 commits; M, 30,000 to 150,000
   commits; L, more than 150,000 commits.
3. ctp ran the 187 projects of size class S and M. `manifest.phase1-sm.tsv` is this
   run set: it holds the S and M rows of `manifest.sample.tsv`, and no other rows.
   The ledger of the run shows 186 finished projects and 1 failed project.
   The 13 L projects of the sample ran apart: 12 in `manifest.l13.tsv` and
   `torvalds__linux` in `manifest.linux.tsv`.
4. On 2026-09-22, cregit got `git blame -C100` (copy detection). Plain `git blame`
   does not follow code that moves between files. `reblame_wave.sh` ran steps 7 to
   10 of ctp again for the projects that were done: first 3 projects, then 136
   projects from 2026-09-22 17:19. The share of tokens that changed author was
   0% to 25% for each project (`docs/REBLAME-C100.md`). The re-blame of
   `googleapis__google-cloud-java` ran on a second machine (`runner/gcj-reblame/`).
5. The projects that had Rust files needed step 2 again, because of a defect of the
   Rust tokenizer. They did not go through `reblame_wave.sh`.
   `backfill_rust_tokens.py` repairs the four columns that this defect made wrong
   on the `.rs` rows of a published Parquet file.

`resources.tsv` records the resource use of the run every 15 seconds, from
2026-09-13 04:29 UTC to 2026-10-05 17:15 UTC.

## Files

| File | Role |
|---|---|
| `README.md` | This file. |
| `select_corpus.py` | Builds the pool, gives the control labels, draws the sample, writes the manifests and `docs/CORPUS-REVIEW.md`. |
| `shared_history.py` | Finds projects that carry the history of another project. It flags them. It does not remove them. |
| `resume_enrich.sh` | Starts `select_corpus.py enrich` again after each GitHub rate limit, until the pass is complete. |
| `candidates.csv` | The pool: 24,405 rows with the control facts and the label of each project. |
| `manifest.generated.tsv` | 3,948 labeled projects of the pool, in the ctp manifest format. |
| `manifest.sample.tsv` | The sample of 200 projects. |
| `manifest.phase1-sm.tsv` | The run set: the 187 S and M projects of the sample. |
| `manifest.l13.tsv` | 13 projects that ran apart: the 12 L projects of the sample other than `torvalds__linux`, and the M project `tencent__tencentkona-21`. |
| `manifest.linux.tsv` | The run of `torvalds__linux` from a local clone. |
| `manifest.a15.tsv` | 47 S and M projects of the sample, in the run order of 2026-10-04 (largest expected cost first). |
| `manifest.mvp5.tsv` | 5 projects of an early test run. |
| `manifest.shardtest.tsv` | One test project. Its size class is L, so that ctp uses the sharded path. |
| `project_meta.py` | Builds `project_meta.json`, the sidecar of the 29 provenance fields of each project. |
| `project_meta.json` | The sidecar of the pilot run (210 projects). |
| `mask_impact.py` | Measures which files the old per-language file masks dropped. It writes `data/mask-impact.csv`. |
| `data/mask-impact.csv` | The result of `mask_impact.py` for the run set and Linux. |
| `validate_spinellis.py` | Compares the control labels with the labels of Spinellis et al. (MSR 2020). It writes `docs/SPINELLIS-VALIDATION.md`. |
| `backfill_rust_tokens.py` | Repairs the four columns that the Rust tokenizer defect made wrong on the `.rs` rows of a Parquet file. |
| `reblame_wave.sh` | Runs steps 7 to 10 again with `--reblame` for a list of projects. It backs up the `.validated` stamps first. |
| `corpus-progress.sh` | Shell functions that show the progress of a run (`cprog`, `cwatch`, `ctail`). |
| `resources.tsv` | The resource samples of the run (111,379 rows, one header line). |
| `docs/CODEBOOK.md` | The rules that give a project its control label. |
| `docs/CORPUS-REVIEW.md` | The sampling frame, the exclusions and the draw of each cell. |
| `docs/CORPUS-SAMPLE.md` | The allocation of the sample to the cells. |
| `docs/REBLAME-C100.md` | Why and how the projects were blamed again with `-C100`, and the measured effect. |
| `docs/SPINELLIS-VALIDATION.md` | The result of `validate_spinellis.py`. |
| `runner/gcj-reblame/fetch-gcj-result.sh` | Packs the re-blame result of `googleapis__google-cloud-java` on the second machine and serves it through an SSM port forward. |
| `runner/gcj-reblame/receive-gcj-result.sh` | Gets the parts through the port forward, checks their sha256 and unpacks them into a staging folder. |
| `runner/gcj-reblame/handoff.md` | The work note for the second machine. It stays in the study repository only, because it names a host. |
| `tests/test_*.py` | The tests of `select_corpus.py`, `shared_history.py`, `project_meta.py`, `validate_spinellis.py` and `backfill_rust_tokens.py`. |

The pilot parts of the other ctp documents (README, DESIGN, DATASET-SCHEMA,
LIMITATIONS, sources/README) come in a separate change.

## Source

All files come from the ctp repository (cregit-token-pipeline), commit `17f1766`
(branch `corpus-freeze-and-tests`), at the same relative paths. Two groups are
different:

- `resources.tsv` is the working copy of ctp, not the committed file. Its first
  51,102 lines are equal to `17f1766:resources.tsv`. The 60,278 rows after them
  (from 2026-09-20 16:52 UTC) were never committed to ctp. sha256:
  `8f08d51d06aa448f8a6df9c08bd22a7319e843a45758ae14b2a4fc2510d3fe4c`.
- `manifest.a15.tsv`, `manifest.l13.tsv` and the two scripts of
  `runner/gcj-reblame/` were untracked files of the ctp working tree. In ctp, the
  two scripts were at the root.

All other files are equal to the files of `17f1766`, except the changes in the
next section.

## Changes from the source

Each change removes a machine value or makes a relative path work from this folder.
All other bytes are equal to the source.

| File | Change |
|---|---|
| `reblame_wave.sh` | `CTP`, `CORPUS`, `BACKUPS` and `CREGIT` come from the environment. Their defaults are the old paths under `$RUNNER_HOME_LOCAL`. The script stops if neither is set. `STAMPS` is now next to `BACKUPS` (the same place as before). `CREGIT_PY3` and `CREGIT_PY3_SITE` keep the old Nix store paths as defaults, and the environment can set them. |
| `corpus-progress.sh` | The default of `CTP_DIR` is `$HOME/cregit-token-pipeline`. The comment tells you to set `CTP_DIR`. The example `source` line names this folder. |
| `mask_impact.py` | It reads `pipeline.cfg` from `$CTP_DIR` (default: this folder), because `pipeline.cfg` stays in ctp. |
| `manifest.linux.tsv` | The path of the local Linux clone starts with the token `${RUNNER_HOME_LOCAL}`. Replace the token before you use the manifest. |
| `docs/REBLAME-C100.md` | A decision names the user, not a person. |
| `runner/gcj-reblame/fetch-gcj-result.sh` | The AWS profile, the region and the EC2 id come from `RUNNER_AWS_PROFILE`, `RUNNER_AWS_REGION` and `GCJ_INSTANCE` (required). The role name comes from `GCJ_ROLE`. A comment no longer names the permissions boundary. |
| `runner/gcj-reblame/receive-gcj-result.sh` | The default of `DEST` is the old path under `$RUNNER_HOME_LOCAL`. |

`git -C <ctp> show 17f1766:<path>` gives the source of each tracked file.
The names `RUNNER_HOME_LOCAL`, `RUNNER_AWS_PROFILE` and `RUNNER_AWS_REGION` are
the tokens of `s7-run/runner/runner.env.example`.

## How to run the code

The code runs against ctp commit `17f1766`, not against a later ctp. Later ctp
commits moved `META_FIELDS` out of `project_meta.py` and removed some modules. The
modules import `file_mask` and `validate_schema` from ctp. `select_corpus.py`
needs the `file_mask.py` of `17f1766`.

1. Make a ctp checkout at `17f1766`:

       git -C <ctp> worktree add /tmp/ctp-17f1766 17f1766

2. Put this folder and the checkout on `PYTHONPATH`, and run the code from this
   folder:

       cd s0-pilot
       export PYTHONPATH="$PWD:/tmp/ctp-17f1766"

3. Run the tests. You need pytest. Without the duckdb module, 17 tests skip.

       python3 -m pytest -c /dev/null --rootdir="$PWD" -p no:cacheprovider \
           -m "not network" tests/

   On 2026-10-29 the result was 499 passed and 1 xpassed (with duckdb 1.5.5).
   The same tests in the ctp checkout give the same result.

4. Make the sample and the sidecar again. Run them in a copy of this folder,
   because they write into the folder of the script:

       python3 ./select_corpus.py sample
       python3 ./project_meta.py --candidates candidates.csv \
           --manifest manifest.sample.tsv \
           --fixture-manifest manifest.mvp5.tsv \
           --fixture-manifest /tmp/ctp-17f1766/manifest.tsv \
           --fixture-manifest manifest.shardtest.tsv \
           --out project_meta.json

   On 2026-10-29, `project_meta.json` was byte-identical. `manifest.sample.tsv`
   was identical except the date in its second line. `manifest.tsv` is a ctp file.

The shell scripts need the run data of the pilot run (the project folders, the
Parquet backups and the cregit checkout). That data is not in this folder.
`reblame_wave.sh` and `corpus-progress.sh` run ctp from `$CTP` or `$CTP_DIR`. They
use the manifests, `project_meta.json` and `pipeline.cfg` of that checkout, which
are equal to the files here at `17f1766`. `mask_impact.py` opens the blob maps in
the read-only mode of SQLite, which can still make side files next to them.
