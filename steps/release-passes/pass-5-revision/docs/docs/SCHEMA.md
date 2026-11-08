# The structure of the release of Token on Me (TOM)

This file gives the folders, the file format, the views and the checks of Token on Me (TOM).
COLUMNS.md gives the meaning of each column. ORGANIZATIONS.md gives the organization tables.

## 1. Folders and files

| Path | Content |
|---|---|
| `README.md` | What the dataset is, how to start, how to cite. It is also the dataset card on Hugging Face. |
| `LICENSE.md`, `THIRD-PARTY.md` | The license, and the external sources of the organization tables with their attribution. |
| `CITATION.cff`, `CHANGELOG.md` | The citation and the changes between versions. |
| `parquet/` | One Parquet file for each project: `<project>-dataset.parquet`. |
| `organizations/` | The organization database: ten Parquet tables and `dataset.duckdb`. |
| `docs/` | COLUMNS, ERROR, LIMITATIONS, ORGANIZATIONS, PRIVACY, SCHEMA, and `tools.lock` (the pinned tools). |
| `MANIFEST.tsv` | One row for each project file (section 5). |
| `ledgers.parquet` | The run ledger rows of each project file. |
| `SHA256SUMS` | The sha256 of each file of the release. |
| `tools/fill_release.py` | The script that writes `MANIFEST.tsv` and `SHA256SUMS`, and checks the release. |

`<project>` is the host path of the repository with `__` in place of `/`. For a host other than
github.com, the name starts with the host, for example `git.savannah.gnu.org__git__3dldf`.

The release has [[tom: parquet files]] project files with [[tom: rows]] token rows. The Parquet files are
[[tom: parquet bytes]] bytes. All files have the same schema.

## 2. The project files

- Apache Parquet format 2.6, data page V1, ZSTD level 19, written by pyarrow 26.0.1.
- Row groups of 1,000,000 rows (the last row group of a file is smaller).
- Bloom filters (false positive rate 1%) in each row group for `file_path`, `token_value`,
  `source_text` and `personid`. Use them to skip row groups for an equality filter.
- The footer has the min and max statistics of each column chunk. The files have no page index.
- One row for each token of the files that the file mask selects (section 4), at the commit of the
  run.
- 53 columns (ctp schema 3). COLUMNS.md gives the names, the types and the order.
- Five key-value entries in the footer:

| Key | Value |
|---|---|
| `ctp_schema_version` | `3` |
| `organizations_version` | The build tag of the organization database: `v4.9` (organization database 1.0.0, Zenodo DOI 10.5281/zenodo.23744044). |
| `organizations_mapping_sha256` | The sha256 of the mapping (domain to organization id, project to `firm_based_on_namespace`, the two fallback rules): `7b52a5155e6f9af60541d5cdfaf6ef6566679a1281497ab274decadb50debe62` in all files. |
| `pseudonymization_version` | The pseudonym scheme: `2` (PRIVACY.md). |
| `pseudonymization_registry_sha256` | The sha256 of the private registry that the write checked the pseudonyms against. |

A change of WHICH organization a domain or a namespace maps to changes the mapping hash. A change
of the name, the kind or the parent of an organization does not change it.

```sql
SELECT file_name, decode(key) AS key, decode(value) AS value
FROM parquet_kv_metadata('parquet/*.parquet');
```

## 3. The views of `organizations/dataset.duckdb`

The DuckDB file holds only views, with paths relative to the release root. Open it from the
release root: `duckdb -readonly organizations/dataset.duckdb`.

| View | Content |
|---|---|
| `organizations`, `organization_domains`, `organization_namespaces`, `project_organizations`, `project_facts`, `project_languages`, `project_labels`, `project_licenses`, `link_error`, `release_info` | One view for each table (ORGANIZATIONS.md). |
| `tokens` | All project files, with the column `filename`. |
| `tokens_with_organizations` | `tokens` with the column `project` and the kinds of the organizations of the ids in the files. |
| `tokens_with_current_organizations` | `tokens` with the ids from a new join of `person_domain` to `organization_domains` (with the fallback values), with `project`, `error_stratum` and `p_error`. Use it to apply a newer table to older files. |
| `stale_files` | The files whose footer mapping hash is not the hash in `release_info`. In a correct release, this view has no rows. |
| `project_hosts` | For each project: the foundations that host it (relation `hosted_by`), with their names and kinds. |
| `project_sponsors` | For each project: the fiscal sponsors of its namespace (relation `sponsored_by`): `project`, `sponsored_by`, `sponsored_by_name`, `sponsored_by_kind`. [[tom: project_sponsors rows]] rows ([[tom: project_sponsors projects]] projects). |

## 4. The file mask

The run tokenized only the files whose path matches this regular expression:

```
(?i)\.(c|c\+\+|cc|cp|cpp|cxx|h|h\+\+|hh|hpp|hxx|java|rs|tcc)$
```

## 5. MANIFEST.tsv

One row for each project file. The columns:

| Column | Value |
|---|---|
| `project` | The project name (from the file name). |
| `clone_url`, `size_class`, `commits` | From the file. |
| `run_commit` | The commit that the run checked out. |
| `frame_commit` | The commit at the selection time. The run uses the newest head, so the two commits can differ. |
| `cregit_commit`, `ctp_commit` | The cregit and ctp commits of the run (`docs/tools.lock`). |
| `rows`, `bytes`, `sha256`, `path` | The number of rows, the size, the sha256 and the path of the file. |

## 6. SHA256SUMS and the checks

`SHA256SUMS` has the format of `sha256sum` and does not list itself. To check a copy, run
`sha256sum -c SHA256SUMS` in the release root.

`tools/fill_release.py check --root <release root>` checks that each project file has the 53
columns of COLUMNS.md and the footer entries, that its mapping hash is the hash of
`organizations/release_info.parquet`, that the organization tables exist, that `MANIFEST.tsv`
agrees with the files, and that no text file has a to-do marker or the at sign.
