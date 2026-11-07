# The organization step

This step gives each token row its organization columns (`firm_based_on_namespace`,
`firm_based_on_domain`, `project_enterprise_driven`, `project_enterprise_basis`) and gives
the release its organization tables and its error numbers. The files are in
`study/s8-companies/` (the folder `s8-companies` of the study repository) and
`study/s7-run/final_merge.py` (a module that `run_v0.py` imports). They are copies at study
commit `561edc9fdc32` (`sync/sources.tsv`, source id `study-s8`). Do not edit them here.

Some file names and option names keep the British spelling "organisation" of the run. The
release uses "organization" (`../release-root/rename-kv/`).

## The parts

| Part | Files | What it does |
|---|---|---|
| Database | `build_companies.py`, `build_companies_v4.py`, `manual/`, `proposals/` | Builds the organization database. `build_companies.py --version v4` runs `build_companies_v4.py`: version 3 plus the review layers. `manual/v4*_*.csv` are the audit layers of the review (fields, merges, new organizations, domains, namespaces), one set of files for each database version up to v4.9. |
| Domains | `extract_domains_v1.py` | Counts the tokens and commits of each author e-mail domain in each project file. Output: one small Parquet file for each project (a cache). |
| Links | `build_links.py`, `link_format.py` | Joins the database with the domain cache and the project metadata. Output: `domain_links.parquet`, `project_links.parquet` and `links.json` (the mapping hash). |
| Column write | `build_v0.py`, `run_v0.py` | Writes the organization columns into each project file, in the same pass as the pseudonyms (`../final-write/`). |
| Release tables | `build_organisations.py` | Writes the organization tables of the release (`tables`) and the views of `dataset.duckdb` (`views`). |
| Error model | `error_model.py`, `ERROR_MODEL.md`, `review/audit_*.py`, `review/DEFINITIONS.md`, `review/AUDIT_SAMPLE.md` | The error of the organization columns and the column audit (`../error-model/`). |

`review/audit_columns_serve.py` and `review/audit_columns.html` are the local page of the
column audit. The tests import them.

## The runs

| Part | Run | Version that ran |
|---|---|---|
| Database v4.9 | One build on 2026-10-25, 12 minutes before study commit `c63013a`, which has the same files as `561edc9`. Database sha256 `000831924310`. | The run recorded no hash of the scripts. |
| Domains, links, column write | The final write (`../final-write/`). Its staged tool list (`SHA256SUMS` sha256 `ec7bf7277f0a`) gives `build_v0.py` `540c2d67fd2a`, `run_v0.py` `107219e5e288`, `build_links.py` `0ba2cb695dee`, `extract_domains_v1.py` `f5166a3a42fa`, `final_merge.py` `acede0d85493`. | These files, byte for byte, except the one replaced line of `build_links.py` (below). |
| Release tables | The first build of the release root, with the final error model. Its staged list gives `build_organisations.py` `fb964892318f`. The later root builds took these tables from their input and only renamed them (`../release-root/`). | This file, byte for byte. |
| Error model and column audit | The final model of 2026-10-28 (`../error-model/`). | The run recorded no hash. The model ran on the working copy 15 minutes before study commit `79543bc`; `561edc9` has the same files. |

Two earlier runs used older versions of some of these files: the organization columns with
an older database (kit `dataset-v0-org`, `build_v0.py` `24fd33839199`, `run_v0.py`
`ca0716895141`) and the links of the second set of projects (kit `x3`, `extract_domains_v1.py`
`a993501f1c90`, `build_links.py` `0ba2cb695dee`). The final write replaced their output, so no
published file comes from them. Their files are not here; `tools.lock` (rows `org-kit` and
`links-kit`) gives their hashes.

`sync/patches.tsv` replaces line 50 of `build_companies.py` and line 81 of `build_links.py`:
the default path of the study folder named the private study repository. The options `--ds`
(`build_companies.py`) and `--sidecar` (`build_links.py`) give the path. The other files are
the files that ran.

## How to run

The commands need Python 3.12 or later with duckdb 1.5.5 (the dev shell: `nix develop`, then
`$CREGIT_PYTHON`). Paths in capitals are placeholders. The scripts read their other defaults
from a work folder under the home directory; give every path as an option.

```sh
cd steps/organizations/study/s8-companies
# The database (needs the inputs below that are not here).
python3 -I build_companies.py --version v4 --out WORK --ds STUDY/dataset-selection --ctp CTP \
  --web WORK/fetch/normalized --review WORK/review --manual manual
# The domain cache and the links of all project files.
python3 -I extract_domains_v1.py --inputs EXTRACT.tsv --cache WORK/cache \
  --person-domain-at first-valid --psl PUBLIC_SUFFIX_LIST --anon-dir PSEUDONYMIZER
python3 -I build_links.py --organisations-version v4.9 --db companies.v4.9.duckdb \
  --cache WORK/cache --sidecar SIDECAR.json --out LINKS
# The column write: ../final-write/README.md.
# The release tables.
python3 -I build_organisations.py tables --links LINKS --out ROOT/organisations \
  --private-out PRIVATE --db companies.v4.9.duckdb --error-model ERROR_MODEL_OUT
python3 -I build_organisations.py views --root ROOT
```

`PSEUDONYMIZER` is a folder with `pseudonymize.py` of ctp at `a4b511b` (the pseudonymizer
row of `tools.lock`). The docstring of each script gives all its options.

## Not here

- The fetched web results (`fetch/normalized/`) and the review folder of the work folder (the
  decisions, the AI answers and the private review layers). They hold the e-mail domains and
  the accounts of the dataset, some of them personal, so they stay private. The database
  build needs them.
- The database itself. The release has the public part of it: the tables of
  `organizations/` in the release root.
- The domain caches and the link tables of the run. The link tables name personal domains.

## Tests

```sh
cd steps/organizations/study/s8-companies
CTP_ANON_DIR=PSEUDONYMIZER python3 -I -m pytest -q -p no:cacheprovider .
```

On 2026-11-07 in the dev shell (Python 3.14, duckdb 1.5.5): 256 passed, 1 failed. The failed
test builds the real database from the local inputs; it reads the study folder from the
replaced default path. The same test passes on the unchanged files with the study folder in
place (68 passed). Without `CTP_ANON_DIR` the tests of the pseudonym write skip.
`make test` runs these tests with an empty home folder, so the tests that read local inputs
skip.
