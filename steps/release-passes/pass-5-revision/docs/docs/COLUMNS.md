# The columns of a project file of Token on Me (TOM)

Each file in `parquet/` holds the tokens of one project. One row is one token. Each file has the
53 columns of ctp schema 3, in the order of this table. ctp is the cregit token pipeline.

| Block | Columns | The value changes by |
|---|---|---|
| A, project identity and selection | 1-17 | project |
| B, token | 18-25 | row |
| C, commit | 26-33 | commit |
| D, person | 34-35 | row |
| E, commit trailers (`VARCHAR[]`) | 36-49 | commit |
| F, organization | 50-53 | row (50 and 52-53: project) |

The pseudonymizer changes the identity columns (PRIVACY.md). The organization tables give the
name, the kind and the parent of each organization id (ORGANIZATIONS.md).

Some columns of the build are not in the files. Their values are in other columns:
`personid`, `author_email`, `footer_personids`, `original_commit_sha`, and the fact type
`roster_language` of `project_facts`.

| # | Column | Type | Block | Value |
|---:|---|---|---|---|
| 1 | `repo_name` | VARCHAR | A | The project name: the host path with `__` in place of `/`. It is a file system name. Do not use it as the key. |
| 2 | `clone_url` | VARCHAR | A | The clone URL of the repository. Use this column as the project key. |
| 3 | `audit_frame_file` | VARCHAR | A | The frame file of the selection that gave the project. The form: `frame:`, the name of the frame file, an at sign, `sha256:` and the first 12 hexadecimal characters of the sha256 of that file. Use it to find the selection input of a project, and to separate the selected projects from development fixtures. |
| 4 | `source` | VARCHAR | A | The source families that found the project (search, a roster file, a company organization, the Spinellis et al. set), for example `search`, `rosters/<file>:<roster>`, `company-org:<organization>`, `spinellis-2020:enterprise`. A semicolon separates more than one value. The values map to the 5 source families: `search` is the GitHub search; `company-org:<organization>` the company organizations; `rosters/<file>:<roster>`, `cncf-landscape:hosted` and `cncf-landscape:not-hosted` the 30 foundation and sponsor rosters (GNU is the roster `gnu`, and the CNCF landscape is the roster `cncf`); `spinellis-2020:enterprise` the Spinellis et al. set; `gitlab:<host>` and `gitlab-search:<rule>` GitLab. It is not the column `source` of `organization_domains.parquet` (the origin of a domain link, ORGANIZATIONS.md). |
| 5 | `stratum` | VARCHAR | A | The governance label of the project that the selection gave from its facts (`build_labels.py` of the replication package, first match wins): `foundation`, `fiscal-sponsor`, `company`, `contested`, `personal`, `unknown` (also `government` and `community`, with no project today). It is not the kind of an organization: for the kind, join `firm_based_on_namespace` to `organizations.kind`. The facts behind the label are in the table `project_facts` (ORGANIZATIONS.md). The table `project_labels` gives a second label that also uses the owner kind of the namespace owner. The files keep this column as it is (see the note "The label with the owner kind"). |
| 6 | `contested` | VARCHAR | A | The foundation and company facts of a project where the facts disagree: a foundation fact and a company fact, or a fiscal-sponsor fact and a company fact (`build_labels.py`). A semicolon separates the facts, for example `company_pool:spinellis;roster_org:lf`. Empty when no fact disagrees. |
| 7 | `label_date` | VARCHAR | A | The date of the label run that first gave this label. |
| 8 | `owner` | VARCHAR | A | The owner (namespace) of the repository on its host. |
| 9 | `repo` | VARCHAR | A | The repository name on its host. |
| 10 | `roster_name` | VARCHAR | A | The project name in the roster that lists the project. Empty when no roster lists it. The language that the roster gives is the fact `roster_language` of the table `project_facts` (ORGANIZATIONS.md). 1,179 projects have a `roster_name` and no `roster_language` fact. |
| 11 | `language` | VARCHAR | A | The primary language that the host gives (GitHub Linguist for GitHub). When the host gives no language (161 projects, all outside GitHub), the value comes from tokei: the largest programming language of the selection rule (tokei 14.0.0, code lines at the commit of the run), with the GitHub Linguist name. In these 161 projects the value is C (74), C++ (67) or Java (20). In the other projects, the value is the host value, and it is not always the language of the selection rule. The table `project_languages` keeps the host value (NULL for the 161 projects) and the tokei value of each project (ORGANIZATIONS.md). |
| 12 | `commits` | VARCHAR | A | The number of commits at the selection time. The type is VARCHAR: cast it to compare. |
| 13 | `size_class` | VARCHAR | A | The size class of the selection draw (`S`, `M` or `L`) from `commits`: `S` below 30,000 commits, `M` 30,000 to 150,000, `L` above 150,000. For a finer split, use the 6-class rule in the notes. |
| 14 | `stars` | VARCHAR | A | The number of stars at the selection time. Empty when the host gives no star count: 166 projects, all outside GitHub. |
| 15 | `pushed_at` | VARCHAR | A | The time of the last push at the selection time. |
| 16 | `license` | VARCHAR | A | The SPDX license expression of the project, with `AND`, `OR` and `WITH`. `AND` means that different files of the project have different licenses. The `;` lists of the earlier values are now written with `AND`. A license pass gives the value. The pass ran ScanCode Toolkit 32.5.0 on the key files of each project at its pinned commit: the root and depth-2 license files, the root READMEs, `LICENSES/`, the REUSE data, the package manifests and `debian/copyright`. A set of rules then gives one SPDX expression for each project, with a confidence class (`high`, `medium`, `low` or `none`). licensee 10.1.0 and askalono 0.5.0 give second opinions only. The column takes the pass value when the confidence is `high` or `medium` and the project is not on the review list. Examples of review cases: `LicenseRef` ids, `AND` lists of 4 or more ids, a second opinion that disagrees, a value that differs from the earlier value, `Apache-2.0 AND MIT` with no choice notice. Otherwise the column keeps its earlier value (the license detector of GitHub, or licensee 9.18.0 at confidence 98 for a project outside GitHub), or it is `NOASSERTION`. A bare GNU id (for example `GPL-2.0`, with no `-only` or `-or-later`) means that the version is known but the choice is not. The pass gives `-only` or `-or-later` only from a notice, a tag or the file headers. [[tom: license values]] projects have a value other than `NOASSERTION`. [[tom: license noassertion]] projects have `NOASSERTION`. `NOASSERTION` means that the method found no SPDX expression, not that the project has no license. The table `project_licenses` gives the confidence, the evidence and the source of each value (ORGANIZATIONS.md). A seeded hand check of 100 new values (projects that had `NOASSERTION` and now have a value) found 0 wrong of 100 (95% Wilson interval 0.0% to 3.7%). See LICENSE.md, section 2. |
| 17 | `owner_type` | VARCHAR | A | `User` or `Organization` (GitHub). Empty for hosts that do not give it. |
| 18 | `file_path` | VARCHAR | B | The path of the file in the repository. |
| 19 | `token_index` | BIGINT | B | The position of the token in the file, from 0. |
| 20 | `source_line` | BIGINT | B | The line of the token in the file, from 1. |
| 21 | `source_col` | BIGINT | B | The column of the token in the line, from 1. |
| 22 | `source_text` | VARCHAR | B | The raw characters of the token, with the white space after it. This is text of the project: the project license applies. |
| 23 | `token_type` | VARCHAR | B | The token type from the tokenizer (srcML for C, C++ and Java; a separate tokenizer for Rust). |
| 24 | `token_value` | VARCHAR | B | The token value without white space. This is text of the project: the project license applies. |
| 25 | `is_structural` | BIGINT | B | 1 for a boundary marker of the tokenizer, 0 for a token of the code. |
| 26 | `original_commit_sha` | VARCHAR | C | The same commit in the original repository. Use this value to find the commit on the host. |
| 27 | `author_name` | VARCHAR | C | PSEUDONYMIZED. The author name of the commit, replaced by `Author ` and 14 hexadecimal characters. |
| 28 | `author_email` | VARCHAR | C | PSEUDONYMIZED. The author address: `author_` and 14 hexadecimal characters, then the at sign and the domain. The domain is the first part after an at sign that is a valid domain (allowed characters, a dot and an ICANN public suffix). A second form has no at sign and no domain: only `author_` and the 14 hexadecimal characters. The pseudonymizer writes this form when the input has no at sign, or when no part after an at sign is a valid domain. An empty value stays empty. |
| 29 | `author_date` | VARCHAR | C | The author date: text in the form `yyyy-MM-dd HH:mm:ss`, in UTC, with no UTC offset. The type is VARCHAR, not a time stamp. Some commits have the zero time stamp `1970-01-01`. The tokens of imported history are dated before 1990 (2,401,621 rows in 21 projects). |
| 30 | `committer_name` | VARCHAR | C | PSEUDONYMIZED, as `author_name`. |
| 31 | `committer_email` | VARCHAR | C | PSEUDONYMIZED, as `author_email`. |
| 32 | `committer_date` | VARCHAR | C | The committer date, in the form of `author_date` (UTC, no UTC offset). The type is VARCHAR. The notes of `author_date` on zero and early dates also apply. |
| 33 | `commit_summary` | VARCHAR | C | The first line of the commit message, from the commit log of the cregit run. The pseudonymizer does not change it. A check of this column against the commit messages of the original repositories is in progress. It can hold names and addresses that the committers wrote (PRIVACY.md). |
| 34 | `personid` | VARCHAR | D | PSEUDONYMIZED. The person after the identity merge of cregit: `author ` and 14 hexadecimal characters. NULL when the author pair (name, address) of the commit matches no row of the `emails` table of cregit: `generate_dataset.py` of the cregit fork joins each commit to that table with a LEFT JOIN on the exact pair. Thus 97,950 rows in 42 projects are NULL. |
| 35 | `person_domain` | VARCHAR | D | The domain of the person address, in lower case with no leading or trailing spaces. It is NOT pseudonymized: it is the input of `firm_based_on_domain`. A value with an at sign keeps only the first part after an at sign that is a valid domain, else it is empty (the rule of `author_email`). NULL in the same rows as `personid`. |
| 36 | `footer_signed_off_by` | VARCHAR[] | E | The values of the `Signed-off-by` trailers of the commit. Each element is pseudonymized: name and address, with the domain kept. |
| 37 | `footer_co_authored_by` | VARCHAR[] | E | The values of the `Co-authored-by` trailers. Pseudonymized as `footer_signed_off_by`. |
| 38 | `footer_co_developed_by` | VARCHAR[] | E | The values of the `Co-developed-by` trailers. Pseudonymized. |
| 39 | `footer_reviewed_by` | VARCHAR[] | E | The values of the `Reviewed-by` trailers. Pseudonymized. |
| 40 | `footer_acked_by` | VARCHAR[] | E | The values of the `Acked-by` trailers. Pseudonymized. |
| 41 | `footer_tested_by` | VARCHAR[] | E | The values of the `Tested-by` trailers. Pseudonymized. |
| 42 | `footer_reported_by` | VARCHAR[] | E | The values of the `Reported-by` trailers. Pseudonymized. |
| 43 | `footer_suggested_by` | VARCHAR[] | E | The values of the `Suggested-by` trailers. Pseudonymized. |
| 44 | `footer_based_on_patch_by` | VARCHAR[] | E | The values of the `Based-on-patch-by` trailers. Pseudonymized. |
| 45 | `footer_helped_by` | VARCHAR[] | E | The values of the `Helped-by` trailers. Pseudonymized. |
| 46 | `footer_mentored_by` | VARCHAR[] | E | The values of the `Mentored-by` trailers. Pseudonymized. |
| 47 | `footer_assisted_by` | VARCHAR[] | E | The values of the `Assisted-by` trailers. Pseudonymized. |
| 48 | `footer_thanks_to` | VARCHAR[] | E | The values of the `Thanks-to` trailers. Pseudonymized. |
| 49 | `footer_personids` | VARCHAR[] | E | The set of persons of all trailers of the commit, after the identity merge, sorted. Pseudonymized element by element. |
| 50 | `firm_based_on_namespace` | VARCHAR | F | The id of the organization that controls the account of the project namespace (relation `owns`). NULL when no organization of the tables controls it (for example the account of a person). The same value on each row of a project. See ORGANIZATIONS.md. |
| 51 | `firm_based_on_domain` | VARCHAR | F | The id of the organization of the address that the author chose for the commit, from `person_domain`. Also one of the pseudo ids `free-provider`, `independent`, `unknown`. Never NULL. See ORGANIZATIONS.md. |
| 52 | `project_enterprise_driven` | BOOLEAN | F | True when the enterprise rule of Spinellis et al. (2020) finds that companies drive the project, from the domain organizations of the authors. The same value on each row of a project. |
| 53 | `project_enterprise_basis` | VARCHAR | F | The test of the enterprise rule that gave the value of `project_enterprise_driven`. The same value on each row of a project. |

## Join with the organization tables

The values of `firm_based_on_namespace` and `firm_based_on_domain` are `organization_id` values of
`organizations/organizations.parquet`. Join them to get the name, the kind and the parent of the
organization. Run the queries from the release root, in `duckdb -readonly
organizations/dataset.duckdb`. The README and ORGANIZATIONS.md give the examples.

## Notes

- Join the files on `clone_url`. `repo_name` is a file system name, and two hosts can give the
  same `repo_name`.
- The dates are strings in UTC with no UTC offset. Cast `author_date` and `committer_date`
  before you compare them.
- The 6-class size rule. `size_class` keeps the 3 classes of the selection draw. For a finer
  split by size, use 6 classes on `commits`: `SS` below 1,500 commits, `S` 1,500 to 2,499, `M`
  2,500 to 4,999, `L` 5,000 to 14,999, `XL` 15,000 to 49,999, `XXL` 50,000 or more. TOM has
  [[tom: size SS]] `SS` projects, [[tom: size S]] `S`, [[tom: size M]] `M`, [[tom: size L]] `L`, [[tom: size XL]] `XL` and [[tom: size XXL]] `XXL`. This query reads
  `MANIFEST.tsv` (one row for each project) from the release root:

```sql
SELECT CASE
         WHEN commits < 1500 THEN 'SS'
         WHEN commits < 2500 THEN 'S'
         WHEN commits < 5000 THEN 'M'
         WHEN commits < 15000 THEN 'L'
         WHEN commits < 50000 THEN 'XL'
         ELSE 'XXL'
       END AS size_class_6,
       count(*) AS projects
FROM (SELECT TRY_CAST(commits AS BIGINT) AS commits
      FROM read_csv('MANIFEST.tsv', delim = '\t', header = true, all_varchar = true))
GROUP BY 1 ORDER BY min(commits);
```

- The trailer arrays (36 to 48) follow the rules of JGit 4.6 (`getFooterLines`) on the original
  commit message, not the rules of `git interpret-trailers`: each `Key: value` line of the last
  paragraph is a trailer, with no 25% rule and no blank line necessary, and a continuation line
  is dropped. The key match is not case-sensitive.
- Each trailer array holds one entry for each person, not the raw trailer lines. Two values of
  one array are one person when their addresses give the same `personid` or the same address in
  lower case. The entry with the lowest trailer index stays.
- The trailer arrays (36 to 48) keep the order of the trailers in each commit. They do not align
  with each other. Column 49 is a set.
- The label with the owner kind. The table `project_labels` gives a second label,
  `stratum_all_kinds`, that also uses the owner kind of `firm_based_on_namespace`
  (ORGANIZATIONS.md). The column `stratum` of the files does not change.

