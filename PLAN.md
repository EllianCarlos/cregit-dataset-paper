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
| A6 | LIMITATIONS items | Add the in-place `formatBlame.pl` swap of 2026-10-11 (about 26 running copies), the plain-blame files, the exclusions, pyxel, the later GitLab snapshot, the GitLab rule differences and the cregit versions. | The list is in the ctp `docs/LIMITATIONS.md`, and it is copied here. |

## Phase B: when the dataset build ends

| # | Item | Action | Done when |
|---|---|---|---|
| B1 | Final merge | Write the merge script (task 6) and the metadata rewrite (the Savannah owner, NOASSERTION licenses) in the study repository. Sync. Make `make merge` work. | The merged files exist, and their sha256 values are recorded. |
| B2 | Validate and freeze | Run `make validate` on all projects. Fill `data/SHA256SUMS`. | `make verify` passes from a fresh clone. |
| B3 | Two equalities are not measured | Rerun a sample (libexpat and about 5 projects) with other worker, blame-job and memory flags. Compare "95cdc88 plus the post-fix" with "57551d7" on the same sample. The big EC2 has free CPUs for this. **Needs the user's yes before any run.** | The result is in REPRODUCE.md and LIMITATIONS: equal, or the list of differences. |
| B4 | `rebuild-one` | After the bundles, ledgers and sidecar are published, write steps 4-6. | `make rebuild-one PROJECT=libexpat__libexpat` gives the published sha256. |
| B5 | Stop the machines | The user gives the direction to stop or terminate each instance. Then read the final cost in the Billing console. | All instances are stopped. The cost is in REPRODUCE.md section 4.4. |
| B6 | Rename pass | Rename the identifiers of kind census-name in the source repositories, in one pass. Rerun the tests and the libexpat gate. Sync. | The scan shows 0 census-name hits. The gate sha256 is unchanged. |

## Phase C: the release, by about 2026-11-01

| # | Item | Action | Done when |
|---|---|---|---|
| C1 | Dataset hosting | The data is about 173 GB. One Zenodo record allows about 50 GB. **The user decides** between more than one record (for example by batch), a larger quota, or another host. | The host and the record ids are in README.md. |
| C2 | Web captures that are not copied (about 250 MB) | Recommendation: do not publish third-party pages. Publish the fetch lists with URL, date and sha256. **The user decides.** | REPRODUCE.md section 3 states the rule. |
| C3 | Public commit SHAs can identify the authors | Recommendation: during the review, ship the tool bundles in the anonymous package and keep the SHAs. Name the public repositories only after acceptance. **The user decides.** | `tools.lock` and README.md follow the decision. |
| C4 | Anonymous export | Make one new commit with an anonymous author from a clean tree. The user pushes it to the anonymous mirror. | The mirror shows the files, and no history. |
| C5 | Independent check | Fresh-context agents clone the export and run `make verify`, `make test` and `make rebuild-one` without help. Skeptic agents try to refute each finding. | All findings are fixed or listed in LIMITATIONS. |

## Decisions that the user owns

- B3: the yes to run the sample on the big EC2.
- B5: the stop or termination of each instance.
- C1: the dataset host.
- C2: the web captures.
- C3: the commit SHAs during the review.
