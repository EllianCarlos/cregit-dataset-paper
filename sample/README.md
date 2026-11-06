# Try the dataset: a sample of whole projects

This folder holds a small sample of the cregit token dataset, version 1.0.0, and the code to
read it. Use it to learn the format and to test your code before you download the full release.

The dataset gives, for each token of the source code of a project, the commit and the person
(a pseudonym) that last changed the token, and the organization of the address of that person.
The sample has 36 whole project files of the release: all rows and all 71 columns of each file.

| Path | Content |
|---|---|
| `data/parquet/` | 36 project files, `<project>-dataset.parquet` (45,553,409 token rows, 247,500,886 bytes) |
| `data/organizations/` | The six organization tables and `dataset.duckdb` of the release, byte-identical (all rows) |
| `data/SHA256SUMS` | The sha256 of each file of `data/` |
| `data/reencode-log.jsonl` | One line for each project file: the content check of the re-encode step (see below) |
| `DATA_DICTIONARY.md` | Each column of the project files and of the organization tables: type, NULLs, meaning, example |
| `SAMPLE.md` | The selection rule, the list of the projects and the bias of the sample against the release |
| `load.py` | Loads the files with pandas and pyarrow, prints a summary and runs example queries |
| `example.ipynb` | Worked examples over the sample, with the outputs saved |
| `select_sample.py` | Applies the selection rule to the full release |

## Quick start

You need Python 3.10 or later.

```sh
pip install pandas pyarrow
python load.py
```

`load.py` prints the number of projects, rows and columns, the projects by commit layer,
language and governance label, the row count of each organization table, and three examples:
the share of code tokens by kind of the organization of the author address, the top 5 author
pseudonyms and the top organizations of one project (`--project`, default `google__guava`), and
the code tokens by author year. It runs in about 10 seconds on the sample.

DuckDB is optional:

```sh
pip install duckdb
python load.py --duckdb
cd data && duckdb -readonly organizations/dataset.duckdb
```

```sql
-- the share of code tokens by kind of the organization of the author address
SELECT domain_organization_kind, count(*) * 100.0 / sum(count(*)) OVER () AS percent
FROM tokens_with_organizations
WHERE is_structural = 0
GROUP BY 1 ORDER BY 2 DESC;
```

Open `dataset.duckdb` from `data/`: its views read `parquet/` and `organizations/` by relative
paths. To run the notebook: `pip install jupyter matplotlib duckdb`, then `jupyter notebook
example.ipynb` in this folder.

## How the sample maps to the full release

- The same files. Each sample file is a whole project file of the release, with the same
  name, the same rows, the same row order and the same columns.
- The same writer. The release files are written again with pyarrow 26.0.1 and fixed settings
  (writer settings fingerprint `e98a53aed203`), with no data change. The sample files come from
  the same tool (`reencode.py`, sha256 `06f2f1c00dfb...`) on the release files. The writer is
  deterministic (two writes of one file give the same bytes), so each sample file has the bytes
  of the file of the same name in the release. To check it, compare `data/SHA256SUMS` with the
  `SHA256SUMS` of the release.
- The content check. Each line of `data/reencode-log.jsonl` gives, for one file, the sha256 of
  the release file before the re-encode (equal to the published sha256) and after it, and the
  checks: the row count, the hash sums of the rows and of each column, an order-dependent hash
  sum, the schema, the 5 footer entries, and a decode of every page. All checks passed for the
  36 files.
- The same organization tables. `data/organizations/` holds the full tables of the release, not
  a filtered copy. They are small (less than 1 MB) and cover all 10,763 projects of the
  selection frame.
- The same code. `load.py --data <release root>` runs on the full release: it reads one column
  at a time in batches of 1,000,000 rows. The full release has 10,754 project files and
  32,635,174,618 rows, so a full scan takes a long time. `--only <project> ...` limits the
  scan to some projects.
- Where the full release is: Zenodo, DOI [[dataset DOI]]. The release documents (`docs/` of the
  release: SCHEMA, COLUMNS, ORGANIZATIONS, ERROR, LIMITATIONS, PRIVACY, PROVENANCE) give the
  full facts. Read `docs/LIMITATIONS.md` and `docs/ERROR.md` before you use the data.
- The sample is not a random sample. `SAMPLE.md` gives its bias. Do not report results from
  the sample.

## License

CC BY 4.0 for the data that the dataset authors made: the project columns 1 to 30, the
organization columns 68 to 71, the pseudonyms and the organization tables (except the
third-party parts that `THIRD-PARTY.md` of the release lists). The text of the code
(`source_text`, `token_value`, `file_path`, `commit_summary` and the commit trailers) keeps the
license of its project. The column `license` gives the SPDX identifier that the host found;
`NOASSERTION` (9 of the 36 sample projects) means that the host found no identifier. Check the
license of a project before you use its text. `LICENSE.md` of the release gives the details.

## Privacy

The identity columns are pseudonymized, not anonymous. A keyed hash replaced the names, the
addresses and the person ids (`DATA_DICTIONARY.md` lists the columns). The same person has the
same pseudonym in all files. Pseudonymized data can still be personal data under data protection
law. These columns are not pseudonymized: `person_domain` and the domain part of the addresses,
`commit_summary`, the code text, the commit hashes and the project columns. A domain of one
person, a commit hash or a commit summary can lead to a person. Use the data only for research.
Do not try to identify a person. The examples print only aggregates, organization ids and
pseudonyms. `docs/PRIVACY.md` of the release gives the details.

## Citation

Cite the dataset: [[citation of the dataset, DOI [[dataset DOI]]]]. Cite the paper that
describes the dataset: [[citation of the paper]].
