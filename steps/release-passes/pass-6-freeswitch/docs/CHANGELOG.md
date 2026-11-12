# Changes of Token on Me (TOM)

## 1.1.0, [[tom: date]]

Version 1.1.0 adds one project to the revision with 8,598 projects (Hugging Face DOI
10.57967/hf/11537).

- The project `signalwire/freeswitch` joins the dataset. The dataset now has [[tom: parquet files]]
  project files with [[tom: rows]] token rows (the new file has 7,238,127 rows). The new file has
  the same form as the others: 53 columns, ctp schema 3.
- Two commits of this project have two `author` headers, and the git library of the tool cannot
  read their committer. The tool now reads the committer from the `committer` header of the
  commit (docs/LIMITATIONS.md, section 3). No other project file changes.
- One new domain of this project gets a row in `organizations/organization_domains.parquet` (now
  [[tom: organization_domains rows]] rows). Its `review_path`, `error_stratum` and `p_error` come from the same
  error model as the earlier rows, which do not change. The error model has no audit sample for
  this domain.
- The tables `project_organizations`, `project_languages`, `project_labels` and `project_licenses`
  each get one row for the new project. `project_facts` gets no row. `release_info` has the new
  row counts and sha256 values.
- The license of the new project comes from the same license pass and rules as the earlier
  values (docs/COLUMNS.md, column 16).
- `pseudonymization.json` has one more batch, for the new project file.
- The Hugging Face revision with this version has its own DOI. It is on the Hugging Face page of
  the dataset and in the Zenodo record of this version.

## 1.0.0, revision of 2026-11-09

This revision keeps the release name 1.0.0.

- 149 projects join the dataset. The dataset now has 8,598
  project files with 31,603,701,581 token rows. The new files have the same form: 53 columns, ctp
  schema 3.
- 31 new domains of the new projects get rows in `organizations/organization_domains.parquet`
  (now 10,930 rows). Their `review_path`, `error_stratum` and `p_error` come from the same error
  model as the 10,899 earlier rows, which do not change; `link_error` keeps the cells of 1.0.0.
- The column `license` has new values from a license pass. ScanCode Toolkit 32.5.0 read the key
  license files of each project at its pinned commit. A set of rules gives one SPDX expression for
  each project, with a confidence class. The column takes the pass value when the confidence is
  high or medium and the project is not on the review list. Otherwise it keeps its earlier value,
  or it is `NOASSERTION` (docs/COLUMNS.md, column 16).
- 1,479 projects had `NOASSERTION` and now have a value.
  3,607 files changed their license value.
- The `;` lists of the column `license` are now SPDX expressions with `AND`.
- A seeded hand check of 100 new values (projects that had `NOASSERTION` and now have a value)
  found 0 wrong of 100 (95% Wilson interval 0.0% to 3.7%).
- A new table `organizations/project_licenses.parquet` gives the license value, the confidence,
  the evidence and the source of each project. `dataset.duckdb` has a new view
  `project_licenses` (docs/ORGANIZATIONS.md).
- The organization database is now named organization database 1.0.0, the name of its own Zenodo
  record (concept DOI 10.5281/zenodo.23744044). Its build tag `v4.9` stays in the footer key
  `organizations_version` of each project file. `release_info` has the new keys
  `organization_database_version` and `organization_database_doi`.
- A new document docs/LIMITATIONS.md gives the known defects: the tokens cut at a bare carriage
  return, and the pseudonymization across batches.

## 1.0.0 (2026-11-07)

The first public version of Token on Me (TOM), on Hugging Face (`elliancarlos/token-on-me`,
DOI: 10.57967/hf/11505).

- 8,449 project files with 30,408,388,202 token rows. A project is in TOM when it has 1,000
  commits or more and its largest programming language (tokei 14.0.0) is C, C++, Java or Rust.
- ctp schema 3: 53 columns (docs/COLUMNS.md), with four organization columns.
- The organization database v4.9 in `organizations/`: nine tables, with the error of each link
  (docs/ORGANIZATIONS.md, docs/ERROR.md).
- The identity columns are pseudonymized with a keyed hash (docs/PRIVACY.md).
- Parquet format 2.6, ZSTD level 19, row groups of 1,000,000 rows, Bloom filters on 4 columns
  (docs/SCHEMA.md).
