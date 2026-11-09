# Plan for the open items (2026-10-14)

Dates: the dataset build ends about 2026-10-15/16. The abstract is due 2026-11-05. The paper is due 2026-11-10.
The anonymous release is one new export commit with an anonymous author (user decision, 2026-10-14).

## Phase A: now, while the dataset build runs

These items do not need the end of the build. They do not touch a running job.

| # | Item | Action | Done when |
|---|---|---|---|
| A1 | EC2 runner scripts are outside git (`~/s3-work`) | Copy the scripts that the build used (machine setup, part feed, restart, publish, watchdog) into the study repository. Replace the account id, bucket, profile and instance ids with variables from one config file. Add them to `sync/rules.tsv` and sync. | `make sync-check` passes. The scan finds no account data in the copies. |
| A2 | No bundle for cregit 23e4ccb and the srcML fork commits | Run `git bundle create` for each commit. Record the sha256 and size in `tools.lock`. The user uploads them with a script. | No `UNKNOWN` bundle row for these commits. |
| A3 | EC2 ctp venv packages not recorded | Run a read-only `pip freeze` on one spot through SSM. Record it in `tools/ctp/`. | The venv row in `tools.lock` lists all packages. |
| A4 | The flake has no devenv command and no cregit jars | Pin the jars as fixed-output files by sha256 (from the bundles). Add the devenv command to the dev shell. Do not change ctp. | `nix flake check` passes. `nix develop` gives every tool that `rebuild-one` calls. |
| A5 | Anonymization hits in the source repositories | Fix them at the source: home paths, AWS profile, bucket, EC2 ids, the study repository name and the cachix cache name. Check the 9 employer hits by hand. Then sync and scan again. | The scan shows 0 hits, except kind census-name. |
| A6 | LIMITATIONS items | Add the in-place `formatBlame.pl` swap of 2026-10-11 (about 26 running copies), the plain-blame files, the exclusions, pyxel, the later GitLab snapshot, the GitLab rule differences and the cregit versions. | The list is in `LIMITATIONS.md` of this repository. It moved here whole from the ctp `docs/LIMITATIONS.md` on 2026-10-29 (ctp `17f1766`). |

## Phase B: when the dataset build ends

| # | Item | Action | Done when |
|---|---|---|---|
| B1 | Final merge | Write the merge script (task 6) and the metadata rewrite (the Savannah owner, NOASSERTION licenses) in the study repository. Sync. Make `make merge` work. | The merged files exist, and their sha256 values are recorded. |
| B2 | Validate and freeze | Run `make validate` on all projects. Fill `data/SHA256SUMS`. | `make verify` passes from a fresh clone. |
| B3 | Two equalities are not measured | Rerun a sample (libexpat and about 5 projects) with other worker, blame-job and memory flags. Compare "95cdc88 plus the post-fix" with "57551d7" on the same sample. The big EC2 has free CPUs for this. **Needs the user's yes before any run.** | The result is in REPRODUCE.md and LIMITATIONS: equal, or the list of differences. |
| B4 | `rebuild-one` | After the bundles, ledgers and sidecar are published, write steps 4-6. | `make rebuild-one PROJECT=libexpat__libexpat` gives the published sha256. |
| B5 | Stop the machines | The user gives the direction to stop or terminate each instance. Then read the final cost in the Billing console. | All instances are stopped. The cost is in REPRODUCE.md section 4.4. |
| B6 | Rename pass | Rename the identifiers of kind census-name in the source repositories, in one pass. Rerun the tests and the libexpat gate. Sync. | The scan shows 0 census-name hits. The gate sha256 is unchanged. |

### Status of phase B (2026-10-16 19:50 UTC)

The dataset build ended for v1: 3,544 projects, 23,692,479,892 token rows, 186.2 GB (kitao__pyxel pending, 3 excluded). The user said yes to B1+B2, B3, B4 and B6. Details: study repository `s7-run/README.md` (section "Dataset v1-raw") and `s7-run/runs-20261009.md`.

- B1: two stages (user decision). Stage 1, v1-raw (real identities, private): `final_merge.py` (study 6d441a7) with the v1 sidecar (3,548 keys, sha256 4023295a…, study 7e6a724) and the v1 encoding (ZSTD 19, 1 M-row groups, Parquet V2; about 70-77% of the size). It runs on spot a. Done before it: the Savannah owner rule (`gnu`), S5/S6 for batch 23 (offline), the mongodb__mongo footer post-fix. Stage 2, v1-public: the pseudonymizer (salted branch `feat/pseudonymise-identity-columns`) needs a rework before it can run on v1 (a registry table in place of SQL `MAP` literals, one fused write, false failures, reports with real identities). The salt transfer waits for the user.
- B2: after stage 2 (the published sha256 values are those of v1-public). `scripts/validate.sh` must use `tools/ctp/validate_schema.py` of ca113e3: the version on ctp `corpus-freeze-and-tests` refuses the column order of the runs.
- B3: plan ready (libexpat post-fix check locally, then a 6-project sample on spot a). Not started.
- B4: the "done when" value 14eb5d72… is the gate file, not the published libexpat file (2dcc77fd… now, a new value after B1). `rebuild-one.sh` step 5 must take the ledger `pinned_sha` (all runs used `--latest`), not manifest column 6. Fix the target before step 4-6.
- B6: about 10,900 of the 11,700 old-name hits are the runner copies, which `ORIGIN.tsv` checks byte for byte. The scan needs a record allowlist for this kind before "0 hits" is possible. The live paths and unit names wait for the end of all timers.

## Phase C: the release, by about 2026-11-01

| # | Item | Action | Done when |
|---|---|---|---|
| C1 | Dataset hosting | The data is about 173 GB. One Zenodo record allows about 50 GB. **The user decides** between more than one record (for example by batch), a larger quota, or another host. | The host and the record ids are in README.md. |
| C2 | Web captures that are not copied (about 250 MB) | Recommendation: do not publish third-party pages. Publish the fetch lists with URL, date and sha256. **The user decides.** | REPRODUCE.md section 3 states the rule. |
| C3 | Public commit SHAs can identify the authors | Recommendation: during the review, ship the tool bundles in the anonymous package and keep the SHAs. Name the public repositories only after acceptance. **The user decides.** | `tools.lock` and README.md follow the decision. |
| C4 | Anonymous export | Make one new commit with an anonymous author from a clean tree. The user pushes it to the anonymous mirror. | The mirror shows the files, and no history. |
| C5 | Independent check | Fresh-context agents clone the export and run `make verify`, `make test` and `make rebuild-one` without help. Skeptic agents try to refute each finding. | All findings are fixed or listed in LIMITATIONS. |

### Status of phase C (2026-10-25)

The release is one dataset of 10,753 projects in two commit layers: 5,000 or more commits (3,544 files) and 1,000 to 4,999 commits (7,209 files). It has 32,626,028,860 token rows, 162.6 GB of release files (ZSTD 19) and 241.3 GB of run output. The 173 GB of the C1 row is an older estimate.

User decisions of 2026-10-25:

- C1 (host): Zenodo. About 4 records of 50 GB under one concept DOI, unless Zenodo gives a larger quota. The answer of Zenodo on the quota is open.
- C2 (web captures): publish everything that a reproduction needs, also the web captures (the fetched third-party pages), each with its URL, its fetch date and its sha256. The pages are third-party content: `THIRD-PARTY.md` needs a licence note for each source. The licence text is not decided here.
- C3 (commit SHAs): publish the commit SHAs and the tool bundles.
- C4 (anonymous release): the user's own repositories go out as an anonymous release for the blind review: one anonymous export commit, which the user pushes. Two facts: the Data and Tool track is single-anonymous (MSR-DATA-AND-TOOL-TRACK.md, line 56), and the user still wants the anonymous release.

State of phase A:

- A1-A4: done. On 2026-10-25 the runner kits of the later runs (the merge of the 5,000+ layer, the runs, the merge and the links of the 1,000-4,999 layer, the path-fix rerun and the organisation columns of version 1) were copied into the study repository with the same token rule (192 copies). They come into `pipeline/` at the next sync, after the study commit (REPRODUCE.md section 9). `tools.lock` has the rows of the later tools (cregit 14b8db4, the merge tools, the links kit, the organisation kit, the pseudonymizer).
- A5: the scan of 2026-10-25 has 0 identifying hits. The old-name kind has 485 files (11,706 occurrences). The copy step checked the new copies against the same patterns: 0 identifying hits (fake test EC2 ids are on the allow list).
- A6: done for v1. The entries of the 1,000-4,999 layer are in work.

State of phase B:

- B1: stage 1 is done for both layers (v1-raw: 3,544 files; x1k-raw: 7,209 files). Stage 2 (the pseudonyms, with the organisation columns in one write) waits for the final database (v4.8), the final commit of the pseudonymizer and the salt.
- B2, B3, B4 and B6: open.
- B5: no machine runs. The stopped machine of batch 2 (the big EC2) and the 4 EBS volumes of machine A wait for the user's direction. The final cost is not recorded.

### Status of B2, B4, C4 and C5 (2026-10-28)

The release root `dataset-release-1` has 10,780 files (162,472,453,753 B; its SHA256SUMS has
the sha256 `1293050b0c75...`). The rebuild `dataset-release-2` changes only MANIFEST.tsv and
the documents, so the checks of the project files stay valid.

- B2: `data/SHA256SUMS` has the 10,754 project rows of the release root. The published files
  are ctp schema 2 (71 columns), so `make validate` now uses `scripts/validate_schema2.py`: the
  67 cregit columns of the ca113e3 contract, then the 4 organisation columns, the footer keys,
  the registry and the rows. The release build checked the same contract on all files
  (`schema.txt`). `make verify` and `make validate` on the real files need the download
  (162.5 GB): the user runs the check script of the release kit.
- B4: the target is not the published sha256 (the salt of the pseudonyms is deleted). The rule
  is in REPRODUCE.md, section 6.1, and the targets of each file are in
  `data/REBUILD-TARGETS.tsv`. Steps 4-6 of `rebuild-one` are written. Local proof for
  libexpat: run output `2dcc77fd...`, merge output `e67bf24e...` (the input of the release
  write), both equal to the records. The column check against the published file waits for the
  download of that file (1.7 MB).
- C4: the export is prepared in a local folder, not committed and not pushed. The user makes
  the one anonymous commit and pushes it.
- C5: fresh-context agents run on the local export.

## Decisions that the user owns

- B3: the yes to run the sample on the big EC2.
- B5: the stop or termination of each instance, and of the 4 volumes of machine A.
- C1: decided 2026-10-25 (Zenodo, split records); the quota answer is open.
- C2: decided 2026-10-25 (publish the web captures); the licence note of each source is open.
- C3: decided 2026-10-25 (publish the SHAs and the bundles).
- C4: decided 2026-10-25 (an anonymous export commit; the user pushes it).

## Status of the release: Token on Me (TOM) 1.0.0 (2026-11-07)

The release is now the dataset "Token on Me" (TOM), version 1.0.0: 8,449 project files, ctp
schema 3, 53 columns, 30,408,388,202 token rows. Three release passes made it from the root of
the re-encoded files (`steps/release-passes/`, REPRODUCE.md section 5.7).

User decisions of 2026-11-07:

- Selection: a project stays when its largest programming language at the pinned commit is C,
  C++, Java or Rust, by tokei code lines. The keep list has 8,447 projects; 2 Savannah projects
  came back after a fetch over HTTPS.
- Host: Hugging Face (`elliancarlos/token-on-me`), public from the start. This replaces the
  Zenodo records of the earlier hosting decision.
- Columns: 18 columns of the source root are dropped (10 in pass 1, 8 in pass 3), one is
  renamed, `fact` and `roster_lang` move to the side table `project_facts`. Pass 2 fills 161
  `language` values (tokei) and 149 `license` values (licensee at confidence 98, outside GitHub).
- The domain audit gives the published error (514 decided answers): 2.921% of the tokens of TOM
  (95% interval 1.465% to 4.904%); company share 34.993% (32.67% to 37.27%). The 14 wrong domain
  rows that the audit found stay in 1.0.0 and are documented.
- Version 1.1.0: a company pass after the paper deadline (2026-11-10).

State:

| Item | State |
|---|---|
| Pass 1 | Done. Hugging Face revision `4c592c54affb`. |
| Pass 2 | Done (17:04 UTC). Hugging Face revision `e3cda53fb51f`. |
| Pass 3 | Runs now. Its final root is not ready. |
| ctp direct write of schema 3 | ctp `feat/schema-3-run` `a9f0bed`, cregit fork `feat/schema-3` `8d60a8f`. Proof on 2 projects: libexpat agrees; emscripten differs in one source file (LIMITATIONS.md). Not pushed. |
| `data/SHA256SUMS`, `data/REBUILD-TARGETS.tsv` | Open: they need the final `SHA256SUMS` of pass 3. |
| `make validate` for schema 3 | Open: `tools/fill_release.py check` of the root checks schema 3 now. |
| DOI, the anonymous export, the independent check | Open. |

## Status of the release: TOM 1.0.0 is published (2026-11-07, evening)

| Item | State |
|---|---|
| Pass 3 | Done. Root `SHA256SUMS` `820f6e8233d8...`; Hugging Face revision `bc7543affd2e` (the DataCite version of the DOI). |
| Pass 4 (the DOI pass) | Done. Documents only: DOI 10.57967/hf/11505, the date, 3 documents removed (limitations, provenance, release notes: now in the paper). Final revision `e81b554deb9b`; final `SHA256SUMS` `b7141d088461...` (8,475 rows). |
| `data/SHA256SUMS`, `data/REBUILD-TARGETS.tsv` | Done: the final root (8,475 rows) and the 8,449 projects of TOM. |
| `make validate` for schema 3 | Done: it runs `fill_release.py check`; `SCHEMA=2` keeps the check of the source root. |
| A later company pass | Open: after 2026-11-10. |
| Open | The anonymous export, the independent check, a push of the commits of the passes and of the direct write. |

## Status of the revision of TOM 1.0.0 (2026-11-08)

| Item | State |
|---|---|
| Selection funnel (`steps/selection-funnel/`) | Done: 8,598 projects, 149 new (41 pool, 108 GitLab). |
| Run of the new projects (`steps/new-projects/`) | Machine C DONE (7 files); machines A and B in pass 2. |
| License pass (`steps/license-pass/`) | Done: values decided, hand check 0 wrong of 100. |
| Pass 5 (`steps/release-passes/pass-5-revision/`) | Staged (`fc901a99a7cf...`), not run. |
| `data/SHA256SUMS`, `data/REBUILD-TARGETS.tsv` | Open: they describe the root of pass 4 until the root of the revision exists. |
| Organization database 1.0.0 | Done: published on Zenodo (concept DOI 10.5281/zenodo.23744044). |

## Future work: the full-history pilot (2026-11-08)

TOM has the tokens that are alive at the pinned commit of each project. A pilot measured the cost
of a dataset of every token in the full history of a project. It is not part of TOM 1.0.0 and
this package has no copy of its kit. One machine built 33 history files (32 projects of a seeded
sample of TOM and the gate project), and all 33 passed the validation. At the pinned commit, 28 of
the 32 projects agree with TOM; the causes of the 4 differences are not studied yet.

The kit fixes after the run: the DuckDB memory limit comes from the machine size
(`MEMORY_LIMIT=auto`: 0.8 x the memory, divided by the projects that run at the same time); the
history builder sizes its line limit from the longest line of a token file (`token_history`
`42a4b1e`; the earlier fixed limit of 16 MB stopped 2 projects); a NUL byte in a token file
(`token_history` `fc8cade`). Open defects of the tools: parallel ctp starts collide on
`project_facts.parquet`; the start script cannot override the values of the kit configuration; a
retry of a project that failed late runs from step 1 and stops on its memo (use `--from-step`);
the blame proof needs a git `safe.directory` for the repositories of the run user; the end marker
of one step is the marker of the whole run.

**TODO (pilot report):** the report of the pilot (`REPORT.md` of the pilot) is not written yet.
Add its results and a link here when it exists.
