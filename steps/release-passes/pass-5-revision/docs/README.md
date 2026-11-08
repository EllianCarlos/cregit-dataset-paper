---
pretty_name: Token on Me (TOM)
license: cc-by-4.0
language:
- en
tags:
- code
- software-engineering
- mining-software-repositories
- authorship
- git-blame
- cregit
- open-source
- organizations
size_categories:
- 10B<n<100B
configs:
- config_name: tokens
  default: true
  data_files:
  - split: train
    path: parquet/*.parquet
- config_name: organizations
  data_files:
  - split: train
    path: organizations/organizations.parquet
- config_name: organization_domains
  data_files:
  - split: train
    path: organizations/organization_domains.parquet
- config_name: organization_namespaces
  data_files:
  - split: train
    path: organizations/organization_namespaces.parquet
- config_name: project_organizations
  data_files:
  - split: train
    path: organizations/project_organizations.parquet
- config_name: project_facts
  data_files:
  - split: train
    path: organizations/project_facts.parquet
- config_name: project_languages
  data_files:
  - split: train
    path: organizations/project_languages.parquet
- config_name: project_labels
  data_files:
  - split: train
    path: organizations/project_labels.parquet
- config_name: project_licenses
  data_files:
  - split: train
    path: organizations/project_licenses.parquet
- config_name: link_error
  data_files:
  - split: train
    path: organizations/link_error.parquet
- config_name: release_info
  data_files:
  - split: train
    path: organizations/release_info.parquet
---

# Token on Me (TOM)

Version 1.0.0, released on 2026-11-07. DOI: 10.57967/hf/11505. TOM is the public Hugging Face dataset
repository `elliancarlos/token-on-me` (https://huggingface.co/datasets/elliancarlos/token-on-me).

Token on Me (TOM) gives, for each token of the source code of free and open-source projects with
1,000 commits or more, the commit and the person (pseudonymized) that last changed it. cregit makes
this attribution with `git blame` at the token level. TOM also gives, for each token, the
organization of the address of the author, and for each project, the organization that controls
its account.

The organization database is part of this dataset. It is in the folder `organizations/` of the
same Hugging Face repository and has the same DOI. You need no other download.

## Content

| Part | Value |
|---|---|
| Projects | [[tom: parquet files]] project files, [[tom: rows]] token rows |
| Languages | The largest programming language of each project: C, C++, Java or Rust. The table `project_languages` gives the language of each project |
| Snapshot | The selection frame of 2026-10-05; the runs use the newest head at the run time (GitLab rows: 2026-10-14) |
| Organization database | organization database 1.0.0 (Zenodo DOI 10.5281/zenodo.23744044), in `organizations/`: [[tom: organizations rows]] organization rows (with the 3 pseudo ids `free-provider`, `independent`, `unknown`), one row for each project, the facts, the language measure, the governance labels and the license values of each project |
| Size | [[tom: parquet bytes]] bytes in the Parquet files of `parquet/` |

A project is in TOM when it has 1,000 commits or more in the selection frame and its largest
programming language is C, C++, Java or Rust. The measure is tokei 14.0.0, in code lines, at the
commit of the run. Header files count as their language. Vendored folders and Qt `.ts`
translation files do not count.

## Folders

| Path | Content |
|---|---|
| `parquet/` | One Parquet file for each project, 53 columns (docs/COLUMNS.md) |
| `organizations/` | The organization database: ten tables and `dataset.duckdb` (docs/ORGANIZATIONS.md) |
| `docs/` | SCHEMA, COLUMNS, ORGANIZATIONS, ERROR, PRIVACY, LIMITATIONS, `tools.lock` |
| `MANIFEST.tsv` | One row for each project file |
| `ledgers.parquet` | The run ledger rows of each project file |
| `SHA256SUMS` | The sha256 of each file |
| `tools/fill_release.py` | The script that makes the manifest and the checksums, and checks the release |

## Start

The Hub viewer and `datasets.load_dataset` read the project files as the configuration `tokens`
(split `train`), and each organization table as its own configuration. The full dataset is large,
so stream it or read one file first:

```python
from datasets import load_dataset

tokens = load_dataset("elliancarlos/token-on-me", "tokens", split="train", streaming=True)
organizations = load_dataset("elliancarlos/token-on-me", "organizations", split="train")
```

```sql
-- DuckDB 1.5 or later, one project file over the network
SELECT * FROM 'hf://datasets/elliancarlos/token-on-me/parquet/apache__syncope-dataset.parquet' LIMIT 10;
```

To work with all files, download the repository, check the files, then open the views from the
download folder:

```sh
hf download elliancarlos/token-on-me --repo-type dataset --local-dir tom
cd tom
sha256sum -c SHA256SUMS
duckdb -readonly organizations/dataset.duckdb
```

```sql
-- the share of tokens by kind of the organization of the author address
SELECT domain_organization_kind, count(*) * 100.0 / sum(count(*)) OVER () AS percent
FROM tokens_with_organizations
GROUP BY 1 ORDER BY 2 DESC;

-- the share of the tokens of each project whose author address belongs to the organization
-- that controls the project account
SELECT repo_name,
       round(100.0 * avg(CASE WHEN firm_based_on_domain = firm_based_on_namespace THEN 1 ELSE 0 END), 2)
         AS insider_percent
FROM tokens
WHERE firm_based_on_namespace IS NOT NULL
GROUP BY ALL ORDER BY insider_percent DESC LIMIT 10;
```

docs/ORGANIZATIONS.md gives the join keys and more examples.

## Read before you use the data

- The organization columns are suggestions with a measured error (docs/ERROR.md).
- `firm_based_on_domain` gives the organization of the address that the author chose, not the
  employer (docs/ORGANIZATIONS.md, section 2.1).
- The identity columns are pseudonymized. Do not try to identify a person (docs/PRIVACY.md).
- The column `license` gives an SPDX expression from a license pass, or `NOASSERTION`. It is not a
  legal finding. Check the license in the repository of a project (LICENSE.md, section 2).
- docs/LIMITATIONS.md gives the known defects of the data.
- The paper and the replication package (https://github.com/EllianCarlos/cregit-dataset-paper)
  give the build, the provenance and the limitations.

## License

See LICENSE.md and THIRD-PARTY.md.

## Citation

See CITATION.cff (DOI: 10.57967/hf/11505). A later version adds the citation of the paper that describes
the dataset.
