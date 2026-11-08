# Data dictionary

This file describes each column of the project files and of the organization tables. The
sample and the full release have the same columns, the same types and the same order.

Sources of the facts: the release documents (`docs/COLUMNS.md`, `docs/SCHEMA.md`,
`docs/ORGANIZATIONS.md`, `docs/ERROR.md`, `docs/PRIVACY.md` of the release), the Parquet schema of
the files (pyarrow) and DuckDB `DESCRIBE`. A meaning that the release documents do not give is
marked "not described in the release documents"; then the row gives only the values in the
files.

The examples come from the sample. They hold no person data. A pseudonym shows as a pattern:
`<14 hex>` is 14 hexadecimal characters. The text "(at sign)" stands for the character that
separates the local part and the domain of an address. This file does not print that character.

## Types

| Short name | Parquet physical type | Parquet logical type | DuckDB type | pandas dtype (pyarrow `to_pandas`) |
|---|---|---|---|---|
| string | BYTE_ARRAY | String (UTF8) | VARCHAR | object (str) |
| int64 | INT64 | Int(bitWidth=64, isSigned=true) | BIGINT | int64 |
| boolean | BOOLEAN | none | BOOLEAN | bool (object when a NULL is present) |
| double | DOUBLE | none | DOUBLE | float64 |
| string list | LIST of BYTE_ARRAY String (three-level list) | List | VARCHAR[] | object (an array of str) |

**Nullability.** Every column of every file is OPTIONAL in the Parquet schema (DuckDB `DESCRIBE`
gives `null = YES`). The list columns are optional at the list level and at the element level.
The column "NULL in the sample" gives the rows with NULL in the 36 sample files (45,553,409 rows).
Many string columns use the empty string, not NULL, for "no value".

## 1. The project files: 71 columns (ctp schema 2)

One file for each project: `parquet/<project>-dataset.parquet`. One row is one token. `<project>`
is the host path of the repository with `__` in place of `/`.

The blocks: A, project identity and selection (1-30; one value for each project); B, token
(31-38); C, commit (39-47); D, person (48-52); E, commit trailers (53-67; one value for each
commit); F, organization (68-71).

**Pseudonymized columns.** 41, 42, 44, 45 and 48-50 (the names, the addresses and the person
id), and the trailer arrays 53-67 (each element). The pseudonym is a keyed hash (scheme 2). The
same person has the same pseudonym in all files of the release. The data is pseudonymized, not
anonymous (see the README, section "Privacy").

### Block A: project identity and selection

| # | Column | Type | NULL in the sample | Meaning | Example |
|---:|---|---|---:|---|---|
| 1 | `repo_name` | string | 0 | The project name: the host path with `__` in place of `/`. A file system name; do not use it as the key. | `google__guava` |
| 2 | `clone_url` | string | 0 | The clone URL of the repository. Use this column as the project key. | `https://github.com/google/guava.git` |
| 3 | `provenance_status` | string | 0 | The frame file of the selection that gave the project, and the first 12 characters of the sha256 of that file. | `frame:frame.batch20.csv`, then the at sign, then `sha256:2059a0abf367` |
| 4 | `source` | string | 0 | The source families that found the project (search, a roster file, a company organization, the Spinellis et al. set). A semicolon separates values. | `company-org:google;search;spinellis-2020:enterprise` |
| 5 | `stratum` | string | 0 | The governance label of the project: `foundation`, `fiscal-sponsor`, `company`, `contested`, `personal`, `unknown` (also `government` and `community`, with no project). | `company` |
| 6 | `fact` | string | 0 | The facts that set the label, in the form `type:value`. A semicolon separates values. Can be empty. | `company_pool:spinellis` |
| 7 | `contested` | string | 0 | The facts that disagree with the label. Empty when no fact disagrees. | empty |
| 8 | `label_date` | string | 0 | The date of the label run that first gave this label. | `2026-10-09` |
| 9 | `owner` | string | 0 | The owner (namespace) of the repository on its host. | `google` |
| 10 | `repo` | string | 0 | The repository name on its host. | `guava` |
| 11 | `roster_name` | string | 0 | The project name in the roster that lists the project. Empty when no roster lists it. | empty |
| 12 | `roster_lang` | string | 0 | The language that the roster gives. Empty when no roster lists the project. | empty |
| 13 | `language` | string | 0 | The primary language that the host gives (GitHub Linguist for GitHub). It is not the language of the tokens: the file mask (column 30) selects the files. | `Java` |
| 14 | `commits` | string | 0 | The number of commits at the selection time, as text. It gives the commit layer: 5,000 or more, or 1,000 to 4,999. | `7539` |
| 15 | `size_class` | string | 0 | The size class (`S`, `M` or `L`) from `commits`. | `S` |
| 16 | `size_kb` | string | 0 | The repository size in KB at the selection time. Empty in all sample files. | empty |
| 17 | `stars` | string | 0 | The number of stars at the selection time, as text. | `51919` |
| 18 | `pushed_at` | string | 0 | The time of the last push at the selection time. | `2026-10-06T00:34:35Z` |
| 19 | `license` | string | 0 | The SPDX identifier of the project license. `NOASSERTION` means that the host found no identifier. The token text (35, 37) keeps this license. | `Apache-2.0` |
| 20 | `owner_type` | string | 0 | `User` or `Organization` (GitHub). Empty for hosts that do not give it. | `Organization` |
| 21 | `archived` | string | 0 | The archived flag of the host, as text. | `False` |
| 22 | `fork` | string | 0 | The fork flag of GitHub, as text. It does not find copies of a history. | `False` |
| 23 | `history_cluster` | string | 0 | The cluster of projects that share one commit history. Empty when the project shares no history. | empty |
| 24 | `history_shared_with` | string | 0 | The other projects of the cluster, separated by spaces. | empty |
| 25 | `history_relation` | string | 0 | `includes`, `included_in`, `mirror` or `diverged`. It gives inclusion, not origin. | empty |
| 26 | `history_includes` | string | 0 | The projects whose full history is inside this project. | empty |
| 27 | `history_first` | string | 0 | The oldest repository of the cluster. | empty |
| 28 | `history_created` | string | 0 | The creation date of the cluster. | empty |
| 29 | `manifest_category` | string | 0 | The category of the run manifest. It is not the governance label: use `stratum`. | `pending` |
| 30 | `file_mask` | string | 0 | The regular expression that selected the files for the tokenizer. | `(?i)\.(c\|c\+\+\|cc\|cp\|cpp\|cxx\|h\|h\+\+\|hh\|hpp\|hxx\|java\|rs\|tcc)$` |

### Block B: token

| # | Column | Type | NULL in the sample | Meaning | Example |
|---:|---|---|---:|---|---|
| 31 | `file_path` | string | 0 | The path of the file in the repository. | `guava/src/com/google/common/base/Preconditions.java` |
| 32 | `token_index` | int64 | 0 | The position of the token in the file, from 0. | `92` |
| 33 | `source_line` | int64 | 0 | The line of the token in the file, from 1. | `117` |
| 34 | `source_col` | int64 | 0 | The column of the token in the line, from 1. | `1` |
| 35 | `source_text` | string | 0 | The raw characters of the token, with the white space after it. Text of the project: the project license applies. Empty for a boundary marker. | `public ` (with one space) |
| 36 | `token_type` | string | 0 | The token type from the tokenizer (srcML for C, C++ and Java; a separate tokenizer for Rust). | `specifier` |
| 37 | `token_value` | string | 0 | The token value without white space. Text of the project: the project license applies. For a boundary marker, the marker name (the `begin_unit` marker also holds the tokenizer facts). | `public`; marker: `begin_unit\|revision:1.0.0;language:Java;cregit-version:0.0.1` |
| 38 | `is_structural` | int64 | 0 | 1 for a boundary marker of the tokenizer, 0 for a token of the code. A comment is a token of the code. Filter `is_structural = 0` to count code tokens. | `0` |

### Block C: commit (the commit that last changed the token)

| # | Column | Type | NULL in the sample | Meaning | Example |
|---:|---|---|---:|---|---|
| 39 | `cregit_commit_sha` | string | 0 | The commit that blame gives for the token, in the cregit view of the repository. | `<40 hex>` |
| 40 | `original_commit_sha` | string | 0 | The same commit in the original repository. Use it to find the commit on the host. | `<40 hex>` |
| 41 | `author_name` | string | 0 | PSEUDONYMIZED. The author name of the commit. | `Author <14 hex>` |
| 42 | `author_email` | string | 0 | PSEUDONYMIZED. The author address. Three forms in the files: `author_<14 hex>`, then the at sign, then the domain (the first part after an at sign that is a valid domain); `author_<14 hex>` with no domain; or empty. | `author_<14 hex>` (at sign) `google.com` |
| 43 | `author_date` | string | 0 | The author date, `yyyy-MM-dd HH:mm:ss` in UTC, with no UTC offset. Text, not a time stamp: cast it before a comparison. | `2017-04-20 21:33:38` |
| 44 | `committer_name` | string | 0 | PSEUDONYMIZED, as `author_name`. | `Author <14 hex>` |
| 45 | `committer_email` | string | 0 | PSEUDONYMIZED, as `author_email`. | as column 42 |
| 46 | `committer_date` | string | 0 | The committer date, in the form of `author_date`. | `2017-04-21 02:27:51` |
| 47 | `commit_summary` | string | 0 | The first line of the commit message. NOT pseudonymized. It can hold names and addresses that the committers wrote. Can be empty. | (free text; no example here) |

### Block D: person (after the identity merge of cregit)

| # | Column | Type | NULL in the sample | Meaning | Example |
|---:|---|---|---:|---|---|
| 48 | `personid` | string | 0 | PSEUDONYMIZED. The person after the identity merge of cregit. NULL when cregit has no person. Use this column to count authors. | `author <14 hex>` |
| 49 | `person_name` | string | 0 | PSEUDONYMIZED. The value of `personid` with `Author` in place of `author`. It is not a display name. | `Author <14 hex>` |
| 50 | `person_email` | string | 0 | PSEUDONYMIZED, as `author_email`. | as column 42 |
| 51 | `person_domain` | string | 0 | The domain of the person address, in lower case with no leading or trailing spaces. NOT pseudonymized: it is the input of `firm_based_on_domain`. Can be empty. Many domains have one person only, so a domain can identify a person. | `google.com` |
| 52 | `repo_tag` | string | 0 | The repository of a multi-repository cregit run. Empty for all projects of the release. | empty |

### Block E: commit trailers (string lists)

Each list holds one entry for each person of the trailers of that key in the commit, in the
order of the trailers. The lists of columns 53-65 do not align with each other. Columns 66 and
67 are sorted sets. Each element is PSEUDONYMIZED: the name and the address as in columns 41 and
42, and the domain stays. An element has the form `Author <14 hex> <author_<14 hex>` (at sign)
`<domain>>`, or only `Author <14 hex>` (11,752 of the 6,337,020 elements of `footer_signed_off_by` in the sample). A commit with no trailer of
that key has an empty list (no NULL in the sample).

| # | Column | Type | NULL in the sample | Trailer key or meaning | Rows with a non-empty list in the sample |
|---:|---|---|---:|---|---:|
| 53 | `footer_signed_off_by` | string list | 0 | `Signed-off-by` | 5,168,663 |
| 54 | `footer_co_authored_by` | string list | 0 | `Co-authored-by` | 2,517,867 |
| 55 | `footer_co_developed_by` | string list | 0 | `Co-developed-by` | 333 |
| 56 | `footer_reviewed_by` | string list | 0 | `Reviewed-by` | 2,629,747 |
| 57 | `footer_acked_by` | string list | 0 | `Acked-by` | 216 |
| 58 | `footer_tested_by` | string list | 0 | `Tested-by` | 2,604,181 |
| 59 | `footer_reported_by` | string list | 0 | `Reported-by` | 2,215 |
| 60 | `footer_suggested_by` | string list | 0 | `Suggested-by` | 1,051 |
| 61 | `footer_based_on_patch_by` | string list | 0 | `Based-on-patch-by` | 0 |
| 62 | `footer_helped_by` | string list | 0 | `Helped-by` | 0 |
| 63 | `footer_mentored_by` | string list | 0 | `Mentored-by` | 0 |
| 64 | `footer_assisted_by` | string list | 0 | `Assisted-by` | 8,201 |
| 65 | `footer_thanks_to` | string list | 0 | `Thanks-to` | 0 |
| 66 | `footer_personids` | string list | 0 | The set of persons of all trailers of the commit, after the identity merge, sorted. Elements: `author <14 hex>`. | 6,418,983 |
| 67 | `footer_person_names` | string list | 0 | The set of person names of all trailers, sorted. Elements: `Author <14 hex>`. | 6,418,983 |

The trailers follow the rules of JGit 4.6 (`getFooterLines`) on the original commit message:
each `Key: value` line of the last paragraph is a trailer. The key match is not case-sensitive.

### Block F: organization

| # | Column | Type | NULL in the sample | Meaning | Example |
|---:|---|---|---:|---|---|
| 68 | `firm_based_on_namespace` | string | 11,503,853 (9 projects) | The id of the organization that controls the account of the project namespace (relation `owns`). NULL when no organization of the tables controls it, for example the account of a person. One value for each project. | `google` |
| 69 | `firm_based_on_domain` | string | 0 | The id of the organization of the address that the author chose for the commit, from `person_domain`. Also one of the pseudo ids `free-provider`, `independent`, `unknown`. Never NULL. It is not the employer. | `google`, `free-provider` |
| 70 | `project_enterprise_driven` | boolean | 0 | True when the enterprise rule of Spinellis et al. (2020) finds that companies drive the project, from the domain organizations of the authors. One value for each project. | `true` |
| 71 | `project_enterprise_basis` | string | 17,845,124 (19 projects) | The tests of the enterprise rule that gave the value of column 70, as a comma list of the codes `sdtc`, `mcpc` and `mcve` (the release documents do not expand the codes). NULL when no test holds. One value for each project. | `sdtc,mcpc,mcve` |

The two organization signals are different. Column 68 tells who controls the repository
account. Columns 69-71 tell who writes the code. The organization columns are suggestions with a
measured error (the release document `docs/ERROR.md`).

### The footer key-value entries of each project file

Each project file has five key-value entries in its Parquet footer, in this order:

| Key | Value in the sample |
|---|---|
| `ctp_schema_version` | `2` |
| `organizations_version` | `v4.9` (the build tag of the organization database 1.0.0 that gave the ids) |
| `organizations_mapping_sha256` | `7b52a5155e6f9af60541d5cdfaf6ef6566679a1281497ab274decadb50debe62` (the sha256 of the mapping from domains and namespaces to ids; equal to `mapping_sha256` in `release_info`) |
| `pseudonymization_version` | `2` (the pseudonym scheme) |
| `pseudonymization_registry_sha256` | `ca284a4e1b9f...` (the sha256 of the private registry that the write checked the pseudonyms against; the file of `BRL-CAD__brlcad`, not in the sample, has another value) |

The files have no `ARROW:schema` entry. The footer value `created_by` is
`parquet-cpp-arrow version 26.0.1`.

Read the entries with DuckDB:

```sql
SELECT file_name, decode(key) AS key, decode(value) AS value
FROM parquet_kv_metadata('parquet/*.parquet');
```

Or with pyarrow: `pyarrow.parquet.ParquetFile(path).metadata.metadata`.

## 2. The organization tables

The folder `organizations/` holds six Parquet tables and `dataset.duckdb` (views only). The
sample has the full tables of the release, byte-identical; they cover all 10,763 projects of the
selection frame, not only the sample. No column of these tables is pseudonymized. The tables have
no personal domains.

The column "NULL" gives the NULL rows in the full table.

### `organizations.parquet` (9,343 rows; key `organization_id`)

| Column | Type | NULL | Meaning | Example |
|---|---|---:|---|---|
| `organization_id` | string | 0 | The id of the organization. The values of columns 68 and 69 of the project files. Also the 3 pseudo ids `free-provider`, `independent`, `unknown`. | `netflix` |
| `name` | string | 0 | The name of the organization. | `Netflix` |
| `kind` | string | 0 | `company`, `project`, `consultancy`, `academic`, `foundation`, `government`, `nonprofit`, `public-research`, `fiscal-sponsor`, or a pseudo kind `free-provider`, `independent`, `unknown`. | `company` |
| `is_company` | boolean | 0 | True for the kinds `company` and `consultancy`. | `true` |
| `sna_sector` | string | 3,058 | The institutional sector of the System of National Accounts 2008 (`S.11` to `S.15`). NULL for kinds with no sector (for example `project`). | `S.11` |
| `kind_basis` | string | 3,126 | NULL, or a comma list of the reasons for the kind: `manual-review`, `wikidata-instance-of`, `gov-or-edu-domain`, `sec-filer`, `registry-id`, `legal-form-in-name`, `roster`, `fortune-global-500`, `rule-no-real-domain`. | `sec-filer,wikidata-instance-of,legal-form-in-name` |
| `parent_company_id` | string | 8,345 | The id of the main interested entity (rule R4: OpenJDK has the parent Oracle). | `oracle` (for `openjdk`) |
| `university_id` | string | 9,318 | For a `public-research` row: the id of the university that the institute is tied to. | NULL |
| `country` | string | 6,826 | Not described in the release documents. Two-letter values (69 distinct). | `US` |
| `wikidata_qid` | string | 8,016 | Not described in the release documents. Values of the form `Q` and digits (a Wikidata item id). | `Q907311` |
| `status` | string | 9,309 | NULL (active) or `defunct` (34 rows). | NULL |
| `review_status` | string | 0 | `ai-reviewed`, `accepted-ai`, `proposed` or `accepted`. | `accepted` |

### `organization_domains.parquet` (10,899 rows; key `domain`)

| Column | Type | NULL | Meaning | Example |
|---|---|---:|---|---|
| `domain` | string | 0 | The e-mail domain, in lower case. The join key with `lower(trim(person_domain))`. | `netflix.com` |
| `organization_id` | string | 0 | The organization of the domain. | `netflix` |
| `match` | string | 0 | `exact` (7,065 rows) or `suffix` (3,834): the link is an exact match or the longest suffix match. | `exact` |
| `matched_domain` | string | 0 | Not described in the release documents. In all `exact` rows it is equal to `domain`; in `suffix` rows it is a parent domain. | `netflix.com` |
| `confidence` | string | 0 | Not described in the release documents. Values: `proposed`, `curated`, `single-developer`, `multi-developer`, `published`. | `published` |
| `source` | string | 0 | The source of the link (24 values in this table, for example `gitdm`, `spinellis-2020`, `claude-proposal-v2`). | `spinellis-2020` |
| `review_path` | string | 0 | How the link was made and checked (9 values). The value `user decision` means a decision of the dataset authors. | `published or curated list, kept by the checks` |
| `error_stratum` | string | 0 | The error cell of the link: origin group / token band / kind class / match. The key of `link_error`. | `source/B1 >=1M/organization/exact` |
| `p_error` | double | 0 | The probability that the link names the wrong organization, from the path of the link. | `0.000324` |

### `organization_namespaces.parquet` (7,061 rows)

One namespace can have more than one row, for example one `owns` row and one `hosted_by` row.

| Column | Type | NULL | Meaning | Example |
|---|---|---:|---|---|
| `host` | string | 0 | The host of the namespace. | `github.com` |
| `namespace` | string | 0 | The account or group on the host. | `apache` |
| `namespace_type` | string | 1,351 | Not described in the release documents. Values: `org`, `group`, `user`. | `org` |
| `organization_id` | string | 0 | The organization of the relation. | `apache-software-foundation` |
| `relation` | string | 0 | `owns` (controls the account; gives column 68), `hosted_by`, `participates`, `candidate`, `sponsored_by`. | `owns` |
| `evidence` | string | 0 | The evidence of the relation, a semicolon list (for example `account-profile`, `roster`, `spinellis`, `website-domain`, `verified-domain`, `name-match`, `company-page`). | `roster` |
| `verified` | boolean | 5,577 | Not described in the release documents. | `true` |

### `project_organizations.parquet` (10,763 rows; key `project`)

| Column | Type | NULL | Meaning | Example |
|---|---|---:|---|---|
| `project` | string | 0 | The project name, as in the file name. 10,763 frame rows: 9 rows have no project file. | `google__guava` |
| `host` | string | 0 | The host of the repository. | `github.com` |
| `namespace` | string | 0 | The owner of the repository. | `google` |
| `firm_based_on_namespace` | string | 3,136 | As column 68 of the project files. | `google` |
| `project_enterprise_driven` | boolean | 0 | As column 70. | `true` |
| `project_enterprise_basis` | string | 7,839 | As column 71. | `sdtc,mcpc,mcve` |

### `link_error.parquet` (108 rows; key `error_stratum`)

One row for each error cell, and two fallback rows (`independent` for a real domain with no row,
and `unknown`).

| Column | Type | NULL | Meaning | Example (the row `fallback/independent/real domain with no row`) |
|---|---|---:|---|---|
| `error_stratum` | string | 0 | The error cell (see `organization_domains.error_stratum`). | `fallback/independent/real domain with no row` |
| `links` | int64 | 2 | The number of domain links in the cell. | NULL |
| `tokens` | int64 | 0 | The number of tokens of the links of the cell. | `1399041156` |
| `estimate` | double | 0 | The token-weighted estimate of the error probability of the cell. | `0.15934` |
| `p_error_min` | double | 2 | The minimum `p_error` of the links of the cell. | NULL |
| `p_error_max` | double | 2 | The maximum `p_error` of the links of the cell. | NULL |
| `audited` | int64 | 108 | The audit count. NULL until an audit. | NULL |
| `errors` | int64 | 108 | The errors found by the audit. NULL until an audit. | NULL |
| `interval_low` | double | 106 | The low end of the interval of the estimate. | `0.0` |
| `interval_high` | double | 106 | The high end of the interval of the estimate. | `0.31868` |
| `method` | string | 0 | The method of the estimate (3 values). | `type B: rectangular from 0 to 2 x the organization share of the AI proposals (...)` |

### `release_info.parquet` (20 rows; key `key`)

| Column | Type | NULL | Meaning | Example |
|---|---|---:|---|---|
| `key` | string | 0 | The name of a fact: the version of the organization database, the ctp schema version, the mapping hash, the two fallback rules, the domain key, and the sha256 and the row count of each table. | `organizations_version` |
| `value` | string | 0 | The value, as text. | `v4.9` |

### `dataset.duckdb` (views only)

Open it from the folder that holds `parquet/` and `organizations/` (the views use relative
paths): `cd data && duckdb -readonly organizations/dataset.duckdb`.

| View | Content |
|---|---|
| `organizations`, `organization_domains`, `organization_namespaces`, `project_organizations`, `link_error`, `release_info` | One view for each table. |
| `tokens` | All project files of `parquet/`, with the column `filename`. |
| `tokens_with_organizations` | `tokens` with `project` (from the file name), `domain_organization_kind`, `domain_organization_is_company` and `namespace_organization_kind`. |
| `tokens_with_current_organizations` | `tokens` with the ids from a new join of `person_domain` to `organization_domains`, with `project`, `error_stratum` and `p_error`. |
| `stale_files` | The files whose footer mapping hash is not the hash in `release_info`. No rows in a correct copy. |
| `project_hosts` | For each project: the foundations that host it (relation `hosted_by`). |
| `project_sponsors` | For each project: the organizations of the relation `sponsored_by`. |
