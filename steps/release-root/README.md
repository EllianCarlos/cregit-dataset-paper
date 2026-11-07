# The release root

This step assembles the release root of the dataset (version 1.0.0) and checks it: the
10,754 project files, the organization tables in `organizations/`, the documents,
`MANIFEST.tsv`, `SHA256SUMS`, `ledgers.parquet` (the cleaned run ledger rows of each file),
`links.json`, `pseudonymization.json` and `tools/fill_release.py`. The root has no registry,
no salt and no personal domain table.

## Files

| File | sha256 | What it does |
|---|---|---|
| `release_tools.py` | `68791baf80cf` | The steps of the root build: the checks of the downloaded write folders (sha256, results, links), `assemble`, `pseudo-merge` (both registry hashes in `pseudonymization.json`), `schema` (the 71 columns and the footer of each file), `ledger-pick`, `ledger-merge`, `ledger-clean` and `ledger-clean-check` (`ledgers.parquet`), `links-rewrite` and `no-paths` (no machine path in the root), `guard` and `no-at`, `sums-compare`, `reencode-chain` and `reencode-root` (the proof chain of the re-encoded files), `split-plan` (the split of the root into archive records). |
| `rename-kv/rename_kv_keys.py` | `9fbaeea52f86` | Renames 2 footer keys of each project file to the spelling "organization". Only the footer changes; the data part stays byte-identical. The same file is `scripts/rename_kv_keys.py`. |
| `rename-kv/rename_company_tables.py` | `7fc3db99d925` | Writes the organization tables and `dataset.duckdb` with the spelling "organization" (names, columns, label values) from the tables of `build_organisations.py`. |
| `rename-kv/check_release_views.py` | `3d37b4f713c6` | Compares each view of the renamed `dataset.duckdb` with the view before the rename. |
| `rename-kv/make_input_sums.py` | `08244b8842ed` | Writes the `SHA256SUMS` of the renamed files from the rename log. |
| `analysis/resolve_run_records.py`, `analysis/ledger_sha_match.py`, `analysis/diff_fields.py` | `cbad3d786683`, `0729387ee833`, `03142f8a8ac3` | Find the run record of the project files that had no clear record in the ledgers, by the sha256 of the run file (the run commits of `MANIFEST.tsv`). |
| `measure/measure.py` | `b52306afa9d9` | Counts four findings of the tool review on the release files (counts only, no network). |
| `test/`, `measure/test/` | | The tests (fake data). |

`tools/fill_release.py` of the release root (sha256 `faf4daac5640`) writes `MANIFEST.tsv` and
`SHA256SUMS` and runs the checks of the root. It is not copied here: its header holds the
names of the authors. Take it from the release root.

## The runs

| File | Run | Version that ran |
|---|---|---|
| `release_tools.py` | The root build of the published root on 2026-11-06, on one cloud machine, with the re-encoded files as input (the staged tool list `SHA256SUMS` of the kit has sha256 `32eb3e1c04ad`). | `68791baf80cf`, byte for byte. Earlier root builds used earlier versions. |
| `rename-kv/*.py` | The rename of 2026-10-28, on the run host. | The run recorded no hash. `rename_kv_keys.py` changed on 2026-10-29, after the rename. |
| `analysis/*.py` | The ledger review of 2026-10-28, on the run host. | The run recorded no hash. |
| `measure/measure.py` | The measure of the tool review findings, 2026-10-28. | `cf6b45ade3ba`. The copy differs in one line: the default output folder is `MEASURE_OUT_BASE` (default `measure-out`) instead of a folder under the home directory. |
| `build_organisations.py` | The organization tables (`../organizations/`). | |

The kit of the published root build staged `release_tools.py`, the release documents, the
proven run records, `ledgers.parquet` and the re-encode log; its `SOURCE` line names the input
of the build (the re-encoded files and their organization tables). The kit scripts that
started the machine, sent the steps to it, uploaded the root and fetched the reports are not
here.

## How to run

The steps of the build, on a folder `R` with all inputs (paths are placeholders):

```sh
python3 -I release_tools.py verify-input --dir IN --a WRITE_A --b WRITE_B --expect 10754 --out verify-input.json
python3 -I release_tools.py assemble --a WRITE_A --b WRITE_B --input IN --docs DOCS --root R --expect 10754 --names-out names.txt
python3 -I release_tools.py pseudo-merge --a WRITE_A/pseudonymization.json --b WRITE_B/pseudonymization.json \
  --a-files 10753 --b-projects PROJECT --want-a SHA_A --want-b SHA_B --out R/pseudonymization.json
python3 -I release_tools.py schema --root R --fill-release R/tools/fill_release.py \
  --pseudonymization R/pseudonymization.json --mapping MAPPING_SHA256 --ov v4.9 --expect 10754 --out schema.tsv
python3 -I R/tools/fill_release.py manifest --root R --layers layers.tsv --ledgers LEDGERS
python3 -I R/tools/fill_release.py checksums --root R
python3 -I R/tools/fill_release.py check --root R
python3 -I release_tools.py sums-compare --root R --a WRITE_A --b WRITE_B --input IN
python3 -I release_tools.py guard --root R --names names.txt
python3 -I release_tools.py no-at --root R
python3 -I release_tools.py no-paths --root R
```

The docstring of `release_tools.py` gives every step and option.

## Tests

```sh
cd steps/release-root
FILL_RELEASE=R/tools/fill_release.py COMPANIES_DB=companies.v4.9.duckdb \
  python3 -I -m pytest -q -p no:cacheprovider test measure/test
```

`test/fake.py` reads `fill_release.py` and the organization database from these variables,
and `build_v0.py` from `../organizations/study/s8-companies/` (`BUILD_V0_DIR` overrides it).
On 2026-11-07 in the dev shell: 74 passed with both inputs; without them the tests of
`release_tools.py` skip and the 16 tests of `measure.py` pass.
