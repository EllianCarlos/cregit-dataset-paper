# The final write

The final write made each published project file in one pass: it added the 4 organization
columns (ctp schema 2) and replaced the identity values by pseudonyms. Inputs: the merged
project files of the build and the final organization database (v4.9). The pseudonymizer is
`pseudonymize.py` of ctp (pull request #10, the pseudonymizer rows of `tools.lock`; the run
ended with commit `a4b511b`). It stays in ctp and is not copied here.

## Files

| File | sha256 | What it does |
|---|---|---|
| `tools/final_tools.py` | `e0aa2797947b` | `pathfix-inputs` and `assemble` (the list of all input files), `compare-links` (the new links against the reference links, counts only), `check-out` (the end check of every written file: columns, types, rows, ZSTD, row groups, footer values, `SHA256SUMS`, no registry file, no at sign). |
| `fix_join.py` | `707ce1bec11b` | Joins the files of the second write machine with the files of the first one, then writes `results.tsv`, `SHA256SUMS`, the link files and `pseudonymization.json`. |
| `added-project/brlcad_tools.py` | `bd7f89ee2c8f` | The tools of the later write of one added project file (BRL-CAD): the selection check, the merge of its links into the links of the final write, and the merge of its registry rows. |
| `test/`, `added-project/test/` | | The tests (synthetic data). |

The column write itself is `run_v0.py` and `build_v0.py` of `../organizations/`.

## The runs

- The final write ran on 2026-10-26 and 2026-10-27 on one cloud machine, and a second machine
  wrote 27 of the files (25 files of the Linux family and 2 others) after a hotfix. The staged tools had
  the list `SHA256SUMS` with sha256 `ec7bf7277f0a`. Three tool files changed during the run
  (section 6 of `docs/RELEASE-NOTES.md` of the release): `pseudonymize.py` (`9a91a027f8c7` to
  `fbe9e9406d72`, ctp `4be3800` to `a4b511b`) and `final_tools.py` (`83ef5cf204bd` to
  `45f36393fc4a` to `e0aa2797947b`). The copy here is the last version, byte for byte.
  `fix_join.py` is the file that ran, byte for byte.
- The added project file came from a separate write with the staged tools of the final write
  (`ec7bf7277f0a`, so `final_tools.py` `83ef5cf204bd` and `pseudonymize.py` `9a91a027f8c7`)
  and `brlcad_tools.py` `bd7f89ee2c8f` (the copy here, byte for byte).

The order of the write on the machine (all paths are placeholders):

```sh
# 1. The input list (the merged files of the build and the rewritten path-fix files).
python3 -I tools/final_tools.py pathfix-inputs --meta PATHFIX_META --list PATHFIX_LIST \
  --v1-results MERGED_RESULTS.tsv --out PATHFIX_INPUTS.tsv
python3 -I tools/final_tools.py assemble --root IN --list PATHFIX_LIST --expect N --report assemble.json
# 2. The registry (one pass over all files) and the links with the final database.
python3 -I PSEUDONYMIZER/pseudonymize.py registry --salt-file SALT --registry PRIVATE/registry.parquet \
  --inputs-from IN/files.txt --psl PUBLIC_SUFFIX_LIST --organisations organisations.parquet --release-root REL
python3 -I ../organizations/study/s8-companies/extract_domains_v1.py --inputs IN/extract.TSV \
  --cache LINKS_WORK/cache --person-domain-at first-valid --psl PUBLIC_SUFFIX_LIST --anon-dir PSEUDONYMIZER
python3 -I ../organizations/study/s8-companies/build_links.py --organisations-version v4.9 \
  --db companies.v4.9.duckdb --cache CACHE_1 --cache CACHE_2 --sidecar SIDECAR_1 --sidecar SIDECAR_2 --out LINKS
python3 -I tools/final_tools.py compare-links --got LINKS --ref REF_LINKS --out compare-links.txt
# 3. The write: the organization columns and the pseudonyms, one file at a time.
python3 -I ../organizations/study/s8-companies/run_v0.py --v1raw IN --links LINKS --out OUT --dest REL \
  --threads 1 --pseudonymize --salt-file SALT --registry PRIVATE/registry.parquet --psl PUBLIC_SUFFIX_LIST \
  --anon-dir PSEUDONYMIZER --no-content-scan
# 4. The end check.
python3 -I tools/final_tools.py check-out --inputs IN/results.tsv --release REL --anon-dir PSEUDONYMIZER \
  --ov v4.9 --mapping MAPPING_SHA256 --registry-sha256 REGISTRY_SHA256 --out check-out.tsv
```

The run shell scripts that did this on the machines (download, upload, status files, the
stop of the machine) are not here: they hold the storage and machine values of the run.

## What no one can do again

The pseudonyms come from a salt. The salt was deleted after the write, by design, and the
registry (the map from real values to pseudonyms) is private. So no new run gives the bytes
of the published files. `make rebuild-one` (`REPRODUCE.md`, section 6.1) checks the columns
that the pseudonyms do not change.

## Tests

```sh
cd steps/final-write
CTP_ANON_DIR=PSEUDONYMIZER FINAL_STAGE_DIR=STAGE python3 -I -m pytest -q -p no:cacheprovider test
cd added-project
FINAL_STAGE_DIR=STAGE STUDY_DATASET_SELECTION=STUDY/dataset-selection CTP_DIR=CTP \
  python3 -I -m pytest -q -p no:cacheprovider test
```

`STAGE` is a folder with the staged tools of the final write (`run_v0.py`, `build_v0.py`,
`anon/pseudonymize.py`, `public_suffix_list.dat`). On 2026-11-07 in the dev shell: `test/`
15 passed with all inputs and 9 passed, 6 skipped without them; `added-project/test/` 9
passed with all inputs, skipped without them. The copies of the tests differ from the run
kit only in the paths: the kit read them from the home folder of the run host, these read
environment variables.
