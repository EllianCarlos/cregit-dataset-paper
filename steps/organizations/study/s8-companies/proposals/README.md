# S8 proposals: organisations of the top unmatched e-mail domains

Date: 2026-10-16.

## Source

The proposals come from model knowledge only. No step fetched data from the web. No step read
other files of `cregit-workspace/companies/`.

## Input

- File: `~/Projects/cregit-workspace/companies/links-trial/top_unmatched.csv`.
- Rows: 600 e-mail domains (columns domain, tokens, projects, authors; sorted by tokens).
- These are the largest e-mail domains of the dataset that the company database does not cover.

## Output

- File: `top_unmatched.v1.csv`.
- Rows: 600, one row for each input domain, in the input order.
- Columns: domain, name, kind, kind_basis, parent_name, certainty, reason.
- Three input domains hold an at sign (git-svn ids, rows 206, 311 and 439). The file writes
  the at sign as `%40`. Thus the file holds no at sign.
- The file holds no person name. A personal domain has the name `(Independent)`.
- A domain that we do not know has a blank name and a blank kind, and certainty `unknown`.
  Placeholder domains (for example `nowhere.fake`, `monsoon.(none)`) are also in this group.

## Counts per kind

| kind | rows |
|---|---:|
| company | 216 |
| independent | 178 |
| project | 64 |
| academic | 48 |
| free-provider | 20 |
| government | 12 |
| consultancy | 12 |
| nonprofit | 6 |
| foundation | 5 |
| fiscal-sponsor | 0 |
| (blank) | 39 |

## Counts per certainty

| certainty | rows |
|---|---:|
| high | 307 |
| medium | 181 |
| low | 73 |
| unknown | 39 |

## Counts per kind_basis

| kind_basis | rows |
|---|---:|
| manual-review | 524 |
| gov-or-edu-domain | 37 |
| (blank) | 39 |

## Status

Every row is a proposal for the user's review. When the database takes these rows, give them
`review_status` = `proposed` and the source `claude-proposal-v1`. Do not accept a row without
a review.

## Round 2 (2026-10-16): `top_unmatched.v2.csv`

Decision D7 of the user: the unmatched domains in token order until 95% of all tokens match,
plus the 3 unmatched domains with the most tokens of each project, with no minimum share. The
selection was measured on database version 2 (6f1c7fe), after round 1:
`~/Projects/cregit-workspace/companies/proposals-v2/selection.csv`, 7,874 domains, 4.0% of the
tokens.

- Source: model knowledge, no web. Eight agents worked on 8 batches of about 985 domains each,
  with the round 1 rules and format. The raw batch files stay in
  `~/Projects/cregit-workspace/companies/proposals-v2/round2-raw/`.
- The join removed 4 rows: they are version-control log lines, not domains, and one holds a
  first name. 7,870 rows stay, in selection order.
- Certainty: high 2,155, medium 1,857, low 2,726, unknown 1,132.
- High and medium per kind: company 1,486, independent 1,114, academic 665, project 236,
  free-provider 182, consultancy 169, government 79, nonprofit 52, foundation 29.
- Some values are dataset domains with a typo or a stray character (for example `intel.com_`).
  They stay as they are, because the dataset holds them so.
- Every row is a proposal for the user's review: review_status proposed, source
  claude-proposal-v2. The build uses only high and medium certainty.
- A Wikidata official-website (P856) check of the same domains gives separate evidence (W3).
