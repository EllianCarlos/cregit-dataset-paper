# Token on Me (TOM): the organization columns and tables

The organization database 1.0.0 is part of the TOM dataset on Hugging Face. It is in the folder
`organizations/`. It has ten Parquet tables and the file
`dataset.duckdb` with views over the tables and the project files. You need no other download. The
organization database is also published on its own on Zenodo (concept DOI 10.5281/zenodo.23744044). 4
tables there have the same bytes as here. Its table `project_organizations` has one row for each project
of the selection frame. The build tag of the database is `v4.9`.

The project files have four organization columns (columns 50 to 53 of COLUMNS.md). The two
`firm_*` columns hold only ids. The tables give the name, the kind, the sector and the parent of
each id. "Firm" here means any organization: a company, a university, a government body, a
foundation, a project, and others. The two `firm_*` columns are suggestions, not facts. ERROR.md
gives how often a value is wrong.

Row counts of the tables: `organizations` 9,343 (9,340 organizations and the 3 pseudo ids of
section 2.2), `organization_domains` [[tom: organization_domains rows]], `organization_namespaces` 7,061,
`project_organizations` [[tom: project_organizations rows]], `project_facts` [[tom: facts rows]],
`project_languages` [[tom: project_languages rows]], `project_labels` [[tom: project_labels rows]],
`project_licenses` [[tom: project_licenses rows]], `link_error` 108, `release_info`
[[tom: release_info rows]].

## 1. The columns in the project files

| No. | Column | Grain | Value |
|---|---|---|---|
| 50 | `firm_based_on_namespace` | project | The organization that controls the account of the namespace (relation `owns`). NULL when no organization of the tables controls it, for example the account of a person. |
| 51 | `firm_based_on_domain` | row | The organization of the e-mail domain of the author (`lower(trim(person_domain))`): an exact match, else the longest suffix match. Never NULL. |
| 52 | `project_enterprise_driven` | project | True when the enterprise rule finds that companies drive the project. |
| 53 | `project_enterprise_basis` | project | NULL, or a comma list of the tests of the rule that are true: `sdtc`, `mcpc`, `mcve`. An author is one e-mail address. The company of an author is the organization of the author domain, when its kind is `company` or `consultancy`. `sdtc`: at least 2 of the 3 authors with the most tokens have the same company. `mcpc`: one company with a strong `kind_basis` (`sec-filer`, `fortune-global-500`, `registry-id` or `wikidata-instance-of`) has 2 or more authors and 10% or more of the commits of the project. `mcve`: one company of any `kind_basis` has 2 or more authors and 10% or more of the commits. The names come from Spinellis et al. (2020). The tests and the thresholds are ours, not those of the 2020 paper. |

The two signals are different. The namespace column tells who controls the repository account.
The enterprise columns use the domain organizations of the authors, so they tell who writes the
code. The two can disagree: a company account can have mostly outside authors, and a personal
account can have company authors.

## 2. The rules

### 2.1 The address rule

`firm_based_on_domain` gives the organization of the address that the author chose for the
commit. It does not give the employer of the author. A free or a personal address is not an error
of the column. A personal or vanity domain of one person maps to `independent`, also when a list
names the employer of the person.

### 2.2 The pseudo ids

Three values of `firm_based_on_domain` are not organizations. Each has a row in
`organizations.parquet` with its own kind and `is_company = false`.

| Id | Meaning |
|---|---|
| `free-provider` | A free mail provider (a webmail, an ISP mailbox, a no-reply address of a forge, an alumni forward). Anybody can get an address there. The author acts as an independent person. |
| `independent` | A personal or vanity domain, or a real domain with no row in the tables. The author acts as an independent person. |
| `unknown` | No real domain: the value is blank, has no dot, or is a git-svn id. The address is not known. |

A real domain with no row in the tables maps to `independent`. ERROR.md gives the error of this
fallback. Alumni forwarding domains of universities (for example `alum.mit.edu`) map to
`free-provider`. Student domains stay with the university.

### 2.3 Personal domains are not in the public table

The public `organization_domains` table lists only organization domains and free-provider
domains. The domains that map to `independent` (personal and vanity domains) are not in it. The
project files and the view `tokens_with_current_organizations` still give `independent` for them,
so the results of an analysis do not change. Some rows are host names of work computers under an
organization domain. A host name can hold the user name of a person.

### 2.4 The namespace rule

`firm_based_on_namespace` names the organization that controls the account (relation `owns`). A
foundation that hosts a project is the relation `hosted_by`. It is not the value of the column.
The relations in `organization_namespaces`:

| Relation | Meaning | Gives `firm_based_on_namespace` |
|---|---|---|
| `owns` | The organization controls the account (the GitHub organization, the GitLab group, or the user account). The evidence is the account page, a page of the organization that names the account, or a forge that the organization runs. A roster line alone is not evidence of control. | yes |
| `hosted_by` | A foundation or a fiscal sponsor hosts a project of the namespace (its roster lists the project). It does not control the account. | no |
| `sponsored_by` | A fiscal sponsor sponsors a project of the namespace (its list of sponsored projects names the project). A fiscal sponsor never controls an account. 117 rows, all of the kind `fiscal-sponsor`. | no |
| `participates` | The staff of the organization take part, but another body controls the namespace. | no |
| `candidate` | A weak signal, for example a name match. | no |

The tests, in this order (the first true test applies):

| Class | Test | The `owns` row |
|---|---|---|
| foundation | The account of the foundation itself: its name, its web site, or a group on a forge that the foundation runs. A project account of an umbrella (Eclipse, Apache, GNU, KDE, GNOME, Mozilla, FreeBSD, NetBSD, PSF, The Document Foundation) is the umbrella. | the foundation |
| company or other organization | The web site of the account is a domain of an organization of the tables, or the account name is the name of a company. | that organization |
| project | The project controls the account. The umbrella rule does not apply to the Linux Foundation and its foundations (for example CNCF, OpenJS Foundation): their project accounts are project rows. | a project row, with the hosting foundation as its parent |
| person | The user account of one person. | none |
| unclear | The account does not exist now, or two rules disagree. | the earlier row stays, and a review item is open |

Example: the roster of the OpenJS Foundation lists Jest in the account `facebook`. Meta controls
that account. Thus `firm_based_on_namespace` is `meta`, and the OpenJS Foundation is `hosted_by`.

### 2.5 The kinds

| Kind | Test | `sna_sector` |
|---|---|---|
| `company` | A market producer whose owners can get a profit. | S.11 (S.12 for banks and insurers) |
| `consultancy` | A for-profit firm that mainly sells services to clients. It counts as a company (`is_company = true`). | S.11 |
| `project` | An open-source project or community with no legal entity of its own. | blank |
| `foundation` | A non-profit legal entity that hosts open-source projects or holds their assets. | S.15 |
| `fiscal-sponsor` | A foundation that sponsors many unrelated projects. | S.15 |
| `nonprofit` | Another non-profit legal entity: a charity, a society, a standards body. | S.15 |
| `academic` | A university, a college, or a research institute that does not sell on the market. | S.13 (public) or S.15 (private) |
| `government` | A body that a government or an intergovernmental body controls. | S.13 |
| `public-research` | A research institute that a government body owns or funds, and that a university is tied to (`university_id`). | S.13 |
| `free-provider`, `independent`, `unknown` | The pseudo ids of section 2.2. | S.14 for `independent` |

`is_company` is true for the kinds `company` and `consultancy`. The sectors follow the System of
National Accounts 2008 (SNA 2008, chapter 4).

## 3. The tables

| Table | Key | Columns |
|---|---|---|
| `organizations.parquet` | `organization_id` | `organization_id`, `name`, `kind`, `is_company`, `sna_sector`, `kind_basis`, `parent_company_id`, `university_id`, `country`, `wikidata_qid`, `status`, `review_status` |
| `organization_domains.parquet` | `domain` | `domain`, `organization_id`, `match`, `matched_domain`, `confidence`, `source`, `review_path`, `error_stratum`, `p_error` |
| `organization_namespaces.parquet` | `namespace` (one namespace can have more than one row, for example one `owns` row and one `hosted_by` row) | `host`, `namespace`, `namespace_type`, `organization_id`, `relation`, `evidence`, `verified` |
| `project_organizations.parquet` | `project` | `project`, `host`, `namespace`, `firm_based_on_namespace`, `project_enterprise_driven`, `project_enterprise_basis` |
| `project_facts.parquet` | `project`, `fact_type`, `fact_value` (one project can have more than one row) | `project`, `fact_type`, `fact_value` |
| `project_languages.parquet` | `project` | `project`, `language`, `language_tokei`, `language_tokei_linguist`, `largest_tied`, `target_share`, `code_lines_programming`, `code_lines_json`, `tokei_status` |
| `project_labels.parquet` | `project` | `project`, `stratum`, `stratum_all_kinds`, `added_fact_all_kinds`, `namespace_owner`, `namespace_owner_kind`, `basis` |
| `project_licenses.parquet` | `project` | `project`, `license`, `confidence`, `evidence_kind`, `version_choice`, `source` |
| `link_error.parquet` | `error_stratum` | `error_stratum`, `links`, `tokens`, `estimate`, `p_error_min`, `p_error_max`, `audited`, `errors`, `interval_low`, `interval_high`, `method` |
| `release_info.parquet` | `key` | `key`, `value` |

Notes:

- `project` of the project tables and of the views `project_hosts`, `project_sponsors` and
  `tokens_with_organizations` is the file name without `-dataset.parquet`.
- `organization_domains.match` is `exact` or `suffix`. For a suffix match, `matched_domain` is the
  longest parent domain that has a source row. `confidence` is the class of that source row:
  `curated`, `published`, `multi-developer`, `single-developer` or `proposed` (an AI proposal or
  an AI review answer). `review_path` tells how the link was made and checked. `error_stratum` and
  `p_error` give the error of the link (ERROR.md).
- `link_error` has one row for each error cell, and two rows for the fallback values.
- `project_facts` has one row for each project and fact. A project with no fact has no row.
  `fact_type` is one of `owner_kind`, `roster`, `company_org`, `company_roster_org`,
  `company_pool`, `roster_org`, `fiscal_sponsor`, `company_roster` and `roster_language`. The
  selection used all fact types except `roster_language` to set the label `stratum` (column 5 of
  the project files). `fact_value` is the key of the fact in its source list, for example `asf`
  for `roster`. It is not an `organization_id`.
- The fact type `roster_language` is the language that the roster gives, as the roster gives it,
  for example `asf:Java` or `asf:Java, C`. Only the rosters of the Apache Software Foundation give
  a language. [[tom: roster_language facts]] projects have this fact.
- `project_languages` has one row for each project: the tokei 14.0.0 measure of the code lines at
  the commit of the run. `language` is the host value (NULL for 161 projects).
  `language_tokei` is the largest programming language with the tokei names, and
  `language_tokei_linguist` with the GitHub Linguist names. `target_share` is the share of C,
  C++, Java and Rust in the programming code lines. `code_lines_json` gives the code lines of each
  language.
- `project_labels` has one row for each project. `stratum` is the label of the project files.
  `stratum_all_kinds` is the same rule with one more fact from the owner kind of the namespace
  owner (`added_fact_all_kinds`). The label changes in 1,684 projects. For 668 of these, the kind
  rests only on a manual review of the dataset authors (`kind_basis` `manual-review`), and for
  432 the kind has no `kind_basis`.
- `project_licenses` has one row for each project ([[tom: project_licenses projects]] projects).
  `license` is the value of the column `license` of the project files (column 16 of COLUMNS.md).
  `confidence` is the confidence class of the license pass: `high`, `medium`, `low` or `none`.
  `evidence_kind` gives the kind of evidence that the value rests on. `version_choice` gives
  the basis of the `-only` or `-or-later` choice of a GNU id. `source` is `pass` (the value of
  the license pass), `tom-1.0.0` (the earlier value stays) or `none` (no value: `NOASSERTION`).
  The view `project_licenses` of `dataset.duckdb` reads this table.
- `organizations.country` is a two-letter code (ISO 3166-1 alpha-2) or NULL.
  `organizations.wikidata_qid` is the Wikidata item or NULL.
- `release_info` holds the version of the database, the schema version, the mapping hash, the
  fallback rules, and the sha256 and the row count of each table.

## 4. Join with the organization tables

Run the queries from the release root, in `duckdb -readonly organizations/dataset.duckdb`.
`firm_based_on_namespace` is NULL for an account of a person: use a left join to keep these rows.

The tokens for each organization that controls the namespace:

```sql
SELECT o.name, o.kind, count(*) AS tokens
FROM tokens t
JOIN organizations o ON o.organization_id = t.firm_based_on_namespace
GROUP BY ALL
ORDER BY tokens DESC
LIMIT 20;
```

The tokens by the kind of the organization of the author address:

```sql
SELECT coalesce(o.kind, t.firm_based_on_domain) AS kind, count(*) AS tokens
FROM tokens t
LEFT JOIN organizations o ON o.organization_id = t.firm_based_on_domain
GROUP BY 1
ORDER BY 2 DESC;
```

The projects with a `roster` fact, with the organization that controls the account:

```sql
SELECT f.fact_value AS roster, p.project, p.firm_based_on_namespace
FROM project_facts f
JOIN project_organizations p USING (project)
WHERE f.fact_type = 'roster'
ORDER BY 1, 2;
```

The projects that a foundation hosts:

```sql
SELECT h.hosted_by, p.project, p.firm_based_on_namespace
FROM project_hosts h JOIN project_organizations p USING (project)
WHERE h.hosted_by = 'cloud-native-computing-foundation';
```

A query on `tokens` reads all project files. To test a query, first make a view over a few files,
for example `CREATE TEMP VIEW tokens AS SELECT * FROM read_parquet('parquet/apache__commons-*-dataset.parquet', filename = true);`.
The views of `dataset.duckdb` then read this temporary view.
