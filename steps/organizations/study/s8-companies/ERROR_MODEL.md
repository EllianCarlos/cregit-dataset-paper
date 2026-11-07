# S8 error model of the organisation columns (draft 2026-10-18; the user's decisions of 2026-10-19 applied)

Status: a proposal. When the user approves it, it replaces section 4 of `LINK_COLUMNS_DESIGN.md`.
`error_model.py` computes every number in this file. The tables go to
`~/Projects/cregit-workspace/companies/error-model/` (`tables.md` holds all of them) for model v4.6, and to `error-model-<database version>/` for model v4.7 (section 10a).

## 0. Summary

1. The two columns are measurements. Each link is the output of an instrument chain: a first source, then checks.
2. Model v4.6 (the published values) uses only the acquisition process. It does not use the audit. Model v4.7 (2026-10-25, section 10a) also uses the audit answers as measured values (type A).
3. `firm_based_on_domain` measures the organisation of the address that the author chose for the commit: the capacity in which the author committed (DECIDED 2026-10-19). A personal or free address means that the author acted as an independent person. A token whose real domain has no row in the database also gets `independent` (DECIDED 2026-10-19). A token with no real domain (blank, no dot, a git-svn id) gets `unknown` (DECIDED 2026-10-19, later the same day): the address is not known. The employer of the author is a side study, not part of the dataset (section 7).
4. A source's raw error is the share of its v3 links that a later check changed.
5. A check's detection rate comes from two pairs of checks on the same items. One pair is a two-pass removal design (round 4d or 4f, then round 7). The other is a two-sample capture-recapture design (rounds 3 and 4).
6. The user's decisions are the reference. Their own error is the user's reversal rate: of 196 items that the user decided, 3 got a second, different answer later (r = 1.53%, u = 0.88 points; section 4.4). The 10 of 186 user decisions that differ from the AI suggestion limit the error correlation of two AI reviews.
7. Bayes' rule gives each link an error probability from its path. A Monte Carlo propagation (JCGM 101) gives the column error and the corrected share of tokens by kind.
8. Result of model v4.6 for the layer v4.6 (v4.5 has the same values; section 2.1): `firm_based_on_domain` is wrong on 0.37% of all tokens (0.373%; U = 0.24 points, k = 2; 95% interval 0.15% to 0.62%). Wrong links give 0.11 points (0.116% of the linked tokens, U = 0.12). Organisations among the unmatched real domains, which show `independent`, give 0.26 points (U = 0.22). On v4.1 the column error was 0.372% and the link error 0.115%.
9. The company-kind share is 37.51% observed. With the link and kind errors removed and the companies among the unmatched domains added, it is 37.51% (U = 0.31 points; 95% interval 37.18% to 37.79%). With hard bounds for the unmatched domains (0 to 1), it is 38.65% (U = 1.60). On v4.1 the corrected share was 37.50% (U = 0.32). The pseudo ids `independent`, `free-provider` and `unknown` have no kind error (DECIDED 2026-10-19); this fix lowered the dataset value by 0.02 points.
10. In `firm_based_on_namespace`, the bound of the wrong-owner share is 10.8% of the owner rows (U = 9.3 points, project-weighted) and 8.3% of their tokens (U = 6.0). On v4.1 it was 2.6% (U = 1.5). The increase comes from the namespace rework of v4.3: the bound counts each owner row that changed from v3 as suspect, and v4.3 and v4.4 changed 171 owner rows on purpose. If a change by a later layer is no sign of an error, the share is 3.0% (U = 1.5). The user must choose (section 8). 423 projects (11.9%) probably have an owner that the "owns only" rule misses. `namespace_review_candidates.csv` lists the 608 rows to review (section 8).
11. `organisation_domains_p_error.parquet` gives the error probability of each domain link. The `organisation_domains` reference table ships it as the column `p_error` (section 4.5).
12. The parameters come from the history v3 -> v4.0 -> v4.1. Model v4.6 applies them to the layer v4.6 (`companies.v4.6.duckdb`, `links-v4.6/`; version 1 of the dataset only). The later layers have their own origins. A change of v4.2 is a user decision: the user audited every change. A value that AI round 9 (v4.4) set has the round 9 error q_r9 = 0.79%, from the user's check sample (section 2.1).
13. Model v4.7 (section 10a; interim values of 2026-10-25) applies the model to both layers of the dataset (32,626,028,860 tokens) and to database v4.7. It uses the audit answers as measured values in each complete stratum, and the check sample of each later AI round. On database v4.7, `firm_based_on_domain` is wrong on 0.83% of all tokens (U 0.65; 95% interval 0.26% to 1.40%); the organisations among the unmatched real domains give 0.69 points of it. The corrected company-kind share is 33.81% (U 0.55). The wrong-owner share of `firm_based_on_namespace` is 4.4% of the owns projects (U 3.1), or 2.0% (U 1.3) if a change by a later layer does not count. No audit stratum is complete yet (40 of 920 items have an answer), and round 10 has no check answer yet, so these values are interim.

## 1. Measurands

- **M1** (row grain): the organisation of the address that the author chose for the commit (DECIDED 2026-10-19). `firm_based_on_domain` estimates M1. The value is the organisation that controls the mail domain, by the rules of DEFINITIONS.md. A free-provider address, a personal domain and a domain with no row in the database give `independent` or `free-provider`: the author acted as an independent person. M1 is not "the employer". The employer is a side study (section 7).
- **M1k**: the kind of the M1 organisation (company, academic, and so on).
- **M2** (project grain): the organisation that controls the project's namespace (relation `owns`). `firm_based_on_namespace` estimates M2.
- **M3**: dataset statistics of M1k and M2. The example in this file is the share of all tokens whose mail domain a company or a consultancy controls.

The column error is the expected share of tokens whose column value is not the measurand value. All shares in this file are token shares, unless a table says "links", "rows" or "projects".

## 2. The acquisition chain

The chain is like the calibration chain of an instrument. Each step either makes a value (a source) or compares a value with a second instrument (a check). The chain ends at the user. The user is the reference: DEFINITIONS.md and the user's decisions define the right answer.

```
FIRST SOURCES (v1-v3 build, offline)                         raw error measured in section 5.1
  G1 gitdm curated map (gitdm, patch, rich, builtin, correction)
  G2 CNCF gitdm multi-developer      G3 CNCF gitdm single-developer
  G4 Spinellis 2020                  G5-G7 AI proposals (firm-domains, v1, v2; high or medium only)
  namespace: rosters, GitHub verified domain (W1), company pages, Spinellis, name match
        |
        v   v3 database (companies.duckdb) and v3 links  <-- the baseline of this model
        |
ORGANISATION ITEMS (kind, name, merge, reject; also domain conflicts)
  rounds 1-2 (top band) --> user decisions (186 items; 10 differ from the AI)   <-- reference
  round 3 = review A (old hint)  |  round 4 = review B (blind)    two samples (section 5.2)
        \______ 2,510 differ _____/
                 round 5 adjudicates (A, B, A=B or a new answer)
                 round 6 (349 institutes)
LINK CHECKS (keep, drop, move)
  round 4d (959 doubtful gitdm rows) --+
  round 4f (3,454 look-alike rows)  --+--> v4.0 build --> round 7 sweep (all 10,876 rows, blind)
                                                           --> rule corrections (121 rows)
                                                           --> round 8 (801 conflicts)
                                                           --> user chat decisions (6 domains)
        |
        v   v4.1 database (companies.v4.duckdb) and links-v4      <-- the parameters end here
        |
LATER LAYERS (section 2.1)
  v4.2  68 fixes with web sources            --> the user audited every change
  v4.3  namespace rework (owns = the organisation that controls the account; hosted_by)
  v4.4  AI round 9, one web check per fact   --> the user checked a seeded sample (0 of 62 wrong)
  v4.5  the user's rules (sponsored_by; the OSGeo rule)
        |
        v   v4.5 database (companies.v4.5.duckdb) --> links-v4.5 --> the two columns (evaluated)
```

`chain_coverage.csv` gives the paths of the 12,236 links with tokens of v4.5. 59.4% of the linked tokens kept their first-source value and saw rounds 4f and 7. 32.6% kept it and saw round 7 only (mostly free-provider rows). 2.1% kept it and saw rounds 4d and 7, and 0.5% also had a user decision. A check or a decision set the value of the other 5.3%.

### 2.1 The later layers (v4.2 to v4.6)

The parameters come from the history v3 -> v4.0 -> v4.1 (sections 4 and 5). The later layers add no new pairs of checks, so the model learns no new parameter from them, except q_r9 (below). The model applies the parameters to the evaluated layer. `error_model.py` reads it with `--db` and `--links`. With `--model v4.6` the defaults are `companies.v4.6.duckdb` and `links-v4.6/`, and the outputs are the published ones (checked on 2026-10-25: every file is byte-identical). Model v4.7 has other defaults (section 10a). The tables of this section were made on v4.5; v4.6 gives the same values (below). `link_format.py` reads the link folders of the old and the new column names. `summary.json` gives the version (`organisations_version`) and the sha256 of the database and of `links.json`. With `--db companies.v4.duckdb --links links-v4`, the script gives the v4.1 values again (checked on 2026-10-20: all values and both Parquet files are the same; only new tables and rows are added).

Each link of v4.5 gets its origin by one of these rules (`later_layers.csv`, central values):

| Rule | Links | Share of the linked tokens | Origin | Error |
|---|---:|---:|---|---:|
| the same domain row as in v4.1 | 12,149 | 98.26% | the v4.1 origin | 0.116% |
| the same row; a v4.4 merge renamed the organisation | 49 | 0.103% | the v4.1 origin, and the round 9 term | 0.88% |
| the same row; a v4.2 merge renamed the organisation | 10 | 0.062% | the v4.1 origin | 0.89% |
| the same row with a new id (the pseudo row of kind `project` has an id now) | 1 | 1.57% | the v4.1 origin | 0.04% |
| a row of v4.2 (pointer `manual/v42_`) | 16 | 0.007% | `user` | 1.98% |
| a row of v4.4 (pointer `manual/v44_`) | 11 | 0.005% | `r9` (AI round 9, web checks) | 0.79% |

The rules:

1. A row of v4.2 is a user decision. The user audited all 68 changes of v4.2 and found them right. The error of the row is the user's reversal rate (section 4.4). 14 of the 16 rows are the suffix matches of one new academic row; they also get the suffix term.
2. A row of v4.4 gets the new origin `r9` (AI round 9, one web check for each fact). Its error is q_r9. No check came after it.
3. A link that keeps its domain row (the same matched domain and the same pointer) keeps its v4.1 origin and its checks. A later merge changes only the id of the organisation. A v4.4 merge on the merge path adds the round 9 term: p = 1 - (1 - p)(1 - q_r9). A v4.2 merge adds nothing, because the user audited it.
4. The kind error follows the review of the organisation row. A row that v4.2 changed (reviewer `claude-main` and review date 2026-10-19 in `companies.v4.2.duckdb`) is a user decision. A row that round 9 set (reviewer `claude-main`, review date 2026-10-20) has the path "AI web check (round 9)" with the kind error q_r9 x phi (section 4.6). Each other AI row keeps its path.
5. Any other new or changed row gets its origin from its source pointer (`origin_of`): the pointer of a check gives that check; a pointer `review:ai/part-` gives the agreed answer of rounds 3 and 4 (or round 5, 6 or 8 for parts 9, 10 and 11); a pointer `manual/` or `review:decisions` gives `user`. A link that a check moved and whose row has no review pointer gets the origin of the agreed answer (an organisation-level answer of rounds 1 to 5 changed it). Else the origin is the first source.

**The round 9 error q_r9.** The user checked a seeded 10% sample of the round 9 decisions (`ai_round_check`, the parameters table). As answered, 1 of 62 answers is wrong. That answer used the old name of a relation. After the rename of the relation, 0 of 62 answers are wrong. The model uses Jeffreys on 0 of 62: the central value is (0 + 0.5) / (62 + 1) = 0.79%, and each draw is Beta(0.5, 62.5). All other counts of the model use the same rule, and the central value is the mean of the draws. The value 0 / 62 = 0 would say "no error"; a sample of 62 cannot show that. The rule of three gives an upper bound of 4.8%. The draws of q_r9 use their own random stream (seed + 9), so the draws of the other parameters do not change. The user saw the AI verdict, so the rate is a lower bound by anchoring (as for the user calibration).

Sensitivity (`sensitivity_r9.csv`, central values). With 1 of 62 as answered, q_r9 is 2.38%. The column error is then 0.3745% of all tokens (main: 0.3729%), and the corrected company share (line 3) is 37.279% (main: 37.285%). The effect is small, because round 9 set or renamed only 0.11% of the linked tokens.

v4.3 and v4.5 changed no domain link. v4.3 changed the namespace column (section 8). v4.5 changed no value of the two columns.

Old and new (central values; U with k = 2):

| Quantity | v4.1 | v4.5 |
|---|---|---|
| links with tokens | 12,222 | 12,236 |
| error of `firm_based_on_domain`, share of all tokens | 0.372% (U 0.24) | 0.373% (U 0.24) |
| wrong links, share of the linked tokens | 0.115% (U 0.12) | 0.116% (U 0.12) |
| company share corrected for E1 + E4 (line 3) | 37.27% (U 0.26) | 37.28% (U 0.24) |
| company share, dataset value (line 5) | 37.50% (U 0.32) | 37.51% (U 0.31) |
| error of `independent` for a real domain with no row (section 6.3) | 9.62% | 9.62% |
| namespace: wrong owner, project-weighted (section 8) | 2.56% (U 1.5) | 10.8% (U 9.3) |
| namespace: wrong owner, token-weighted | 2.93% (U 1.9) | 8.3% (U 6.0) |
| namespace review list | 442 rows | 608 rows |

**v4.6 (2026-10-21).** The model now applies to v4.6 (`--db` default `companies.v4.6.duckdb`,
`--links` default `links-v4.6/`). v4.6 adds back 48 `hosted_by` rows of OSGeo (the user's new rule
N2). `hosted_by` gives no value, so no link and no owns row changes. All error numbers are the same
as on v4.5:
- The column error of `firm_based_on_domain` is 0.373% of all tokens (U 0.244).
- The link errors are 0.116% of the linked tokens (U 0.121).
- The corrected company-kind share is 37.51% (U 0.31).
- The wrong-owner share of `firm_based_on_namespace` is 10.8% of the owns projects (U 9.3) and 8.3% of
  their tokens (U 6.0). If a change by a later layer does not count, it is 3.0% (U 1.5) and 3.5% (U 1.8).

Only the table of namespace rows changes. The `hosted_by` rows with evidence `roster` go from 969 to
1,015 with no verified value, and from 86 to 88 with verified false. The v4.5 tables are in
`error-model-v4.5-20261021/`.

## 3. Error sources

| # | Source | Column | Type (GUM) | Measured from |
|---|---|---|---|---|
| E1 | A link names the wrong organisation | domain | A from process counts, B for the transfer | sections 5.1 to 5.4 |
| E1s | A subdomain inherits its parent's organisation, but it is another organisation | domain | A (round 7 on subdomain rows) | 31 of 875 subdomain rows changed |
| E2 | The domain has no row; the column says `independent` (DECIDED 2026-10-19), but the domain belongs to an organisation | domain, M3 | B (from the AI proposal rate) | section 6.3 |
| E3 | Staff of an organisation commit with a free or personal address | not an error of M1 (DECIDED 2026-10-19); the employer side study only | - | section 7 |
| E4 | The kind of the organisation is wrong | M1k, M3 | A from process counts, B for rho | section 5.3 |
| E5 | Time: the database states the organisation as of 2026-10 | not an error of M1 by the user's rules; the employer side study only | - (one case is an assumption, A14) | section 7 |
| E6 | The namespace owner is wrong | namespace | B (bounds from a second instrument) | section 8 |
| E7 | The namespace owner is missing | namespace | indicator | section 8 |
| E8 | The AI checks share blind spots (common mode) | all | B | rho and the se range; section 9 |

## 4. Estimators

### 4.1 Raw error of a source (type A count, B transfer)

For the v3 links of source g, a link is "changed" when its v4.1 organisation differs from the merge-resolved v3 organisation, or when it lost its link. A merge is not a change. The detected share is d = changed / links. The Wilson (1927) interval gives its 95% interval.

A check finds only a part of the errors, so d is a lower bound. With a chain sensitivity S, the raw error is pi = d / S. A false change (a check moves a right link) makes d larger, so pi = d / S is conservative.

The strata are source group x token band x kind class. The bands are B1 (1M tokens or more), B2 (10k to 1M) and B3 (less than 10k). The classes are free-provider, independent and organisation. A stratum with fewer than 10 v3 links falls back to a coarser stratum.

### 4.2 Detection of a check: two designs

**Two-pass removal (rounds 4d or 4f, then round 7).** Round 7 saw the state after round 4d or 4f. It did not see the links that those rounds dropped, so a Lincoln-Petersen estimate is not valid here: the two samples do not come from the same population. The valid design is the removal method (Zippin 1956; Seber and Le Cren 1967). Pass 1 finds n1 errors. Pass 2 finds n2 errors among the links that pass 1 kept. With one detection probability p for both passes, p = 1 - n2/n1 and N0 = n1^2 / (n1 - n2).

**Two-sample capture-recapture (rounds 3 and 4).** Both reviews judged the same 4,176 organisation items in their v3 state. Review A is the answer of rounds 1 to 3 (round 3 for most items). Review B is round 4. An item has an error when the final answer (round 5 for the items that differ, else the shared answer) is an edit or a reject. Review A "captures" the error when it also proposes an edit or a reject. Lincoln-Petersen (Petersen 1896; Lincoln 1930) and Chapman (1951) give the total number of errors. The difference from the errors that A or B found is the number that both missed. The capture probabilities are p_A = m / n_B and p_B = m / n_A (Seber 1982). Eick et al. (1992) and Briand et al. (2000) use the same estimators for software inspections.

The model uses the sensitivity se of one AI check as a rectangular distribution between the two estimates (0.865 to 0.971).

### 4.3 Error of the AI answers: the two-rater model

Round 5 tells which of the two reviews was right when they disagreed in effect. Let x be the share of items where only A was wrong, y the share where only B was wrong, and w the share where both were wrong and disagreed. With a = x + z, b = y + z and z = a b + rho sqrt(a(1-a) b(1-b)), the share of agreed items that are both wrong is (z - w) / (1 - x - y - w). rho is the correlation of the two error indicators. With rho = 0, this is the classic independence result (Dawid and Skene 1979; Hui and Walter 1980 show why two raters alone cannot identify rho).

**Calibration of rho against the reference.** The user decided 186 items that had an AI suggestion (rounds 1-2). 10 decisions differ: 5.4% (Wilson 3.0% to 9.6%). The user saw the suggestion, so this is a lower bound of the AI error. rho_cal is the rho at which the mean single-review error (a + b)/2 equals 9.6%. The model uses rho uniform from 0 to rho_cal = 0.167. The same 10 of 186 give the error of one AI answer that no second review confirmed (rounds 5, 6 and 8): Jeffreys Beta(10.5, 176.5).

### 4.4 Wrong corrections

- q4: round 7 kept all 145 moves of rounds 4d and 4f that it saw. q4 = Jeffreys(0 of 145) / se.
- q7: the main session reversed 118 of 1,272 raw round 7 changes (9.3%). Those reversals fixed one error kind (bought firms). The residual is uniform from 0 to 9.3%.
- User or manual decisions (DECIDED 2026-10-19): the user's reversal rate, a measured metric of the process. An item counts once in N when the user decided it; it counts in k when a later decision (a later `decided_utc`) gave a different answer. The files are `review/decisions.csv`, its 7 saved snapshots in `review/history/`, `review/decisions.chat.csv` and `review/decisions.domains.chat.csv`. k = 3 of N = 196 (190 organisation items and 6 domain decisions): r = k/N = 1.53%, u = sqrt(r(1-r)/N) = 0.88 points. The three items: one accept that became a merge into another organisation (the same session), and two accepts or edits that got a parent later in the chat of the final audit. None changed the kind. Two more decisions were taken back with no new answer; they are not in k (a sensitivity row in section 5.4 adds them). The final audit (`review/audit-final/verdicts.csv` and its 9 snapshots) changed no definite answer: 10 sheets went from "unsure" or blank to "ok", and its 11 comments correct database rows, not earlier decisions of the user. If k were 0, the term would use the rule of three (95% upper bound 3/N, rectangular from 0 to 3/N). The Monte Carlo draw is a Beta distribution with mean r and standard deviation u: Beta(r(N-1), (1-r)(N-1)). This term replaces the old type B term (uniform 0 to 2%).
- Agreed answers of rounds 3 and 4 (origin "AB"): the two-rater result above.

### 4.5 Error probability of one link (type B from its path)

Let the step that set the link's value give the prior error (pi for a source, q for a check). Each later check with sensitivity se that kept the value gives, by Bayes' rule,

    p = prior (1 - se) / (prior (1 - se) + 1 - prior).

A suffix match adds the subdomain error (E1s): p = 1 - (1 - p)(1 - p_suffix), with p_suffix = Jeffreys(31 of 875). `link_error.parquet` holds p for every link (a hashed key, no domain).

**The `p_error` column (DECIDED 2026-10-19).** `organisation_domains_p_error.parquet` holds one row for each dataset domain with a link in the evaluated layer (v4.5: 12,236 rows; v4.1: 12,222 rows): `key_hash` (the same hashed domain key as `link_error.parquet`), `error_stratum` and `p_error` (the central p above). `error_stratum` is the cell of the link: origin group / token band / kind class / match, for example `source/B1 >=1M/organisation/exact`. These are the cells of the audit sample (`review/AUDIT_SAMPLE.md`); its `strata.csv` lists the cells of each audit stratum, so an audit result joins to the domains by this text. The release adds `p_error` and `error_stratum` to `organisation_domains` by the domain (the release build hashes the domain with the same rule). A domain with no row has no `p_error`; its value `independent` has the error of the unmatched domains (section 6.3), and `unknown` (no real domain) has no error. `link_error.parquet` of the release (`build_organisations.py`) gives both as two fallback rows. The public `organisation_domains` leaves out the `independent` rows (personal domains; the user, 2026-10-19). **One row for each link (2026-10-27).** The file holds one row for each link of the link folder. A link can name a domain that has no tokens in the token tables of the model: the final write counts its own tokens (3 of the 16,119 links of dataset-final-2). Such a link gets a chain row with 0 tokens (band B3) and its `p_error` by the rule of the other rows (origin from `current_origin`, then section 4.5). Its 0 tokens change no token share. `summary.json` gives `links_with_no_tokens`. `error_model.py` stops and does not write the file when the rows are not one for each link.

The column error is E = sum(t_l p_l) / sum(t_l), with t_l the tokens of link l.

### 4.6 Propagation and the kind shares

The Monte Carlo method of JCGM 101:2008 draws all parameters 2,000 times (seed 20261018). The counts use Jeffreys posteriors (Brown, Cai and DasGupta 2001), a parametric bootstrap in the sense of Efron and Tibshirani (1993). The type B parameters use rectangular distributions (GUM 4.3.7). The standard uncertainty u is the standard deviation of the draws. U = 2u (k = 2, about 95%).

For M3, a wrong link moves its tokens from the shown class to the true class. The probabilities come from the detected changes (`kind_transitions.csv`):

- A detected link error of a shown company went to a non-company in 145 links, to another company in 29, and lost its link in 466.
- The kind of a lost link is unknown: uniform from 0 to 1.
- A detected kind edit of a shown company went to a non-company in 263 links and stayed a company kind in 272.
- The kind error of an organisation is its item error times phi. phi = 171 / 580 is the share of real disagreements that involve the kind.

The corrected share is the observed share minus the expected false positives plus the expected false negatives. For two classes, this is the Rogan and Gladen (1978) estimator with the Se and Sp of the same matrix. The script checks that both give the same value. For more classes, `matrix_correct` inverts the confusion matrix.

## 5. Numbers

### 5.1 Raw error by source (v3 links with tokens; `source_raw_error.csv`)

| Source group | Links | Changed | Share of links (Wilson 95%) | Share of tokens |
|---|---:|---:|---|---:|
| G1 gitdm curated | 1,887 | 100 | 5.30% (4.38 to 6.40) | 2.26% |
| - free-provider rows | 101 | 0 | 0% (0 to 3.66) | 0% |
| - independent rows | 71 | 66 | 93.0% (84.6 to 97.0) | 98.2% |
| - organisation rows | 1,715 | 34 | 1.98% (1.42 to 2.76) | 2.17% |
| G2 CNCF gitdm multi-developer | 183 | 9 | 4.92% (2.61 to 9.08) | 1.71% |
| G3 CNCF gitdm single-developer | 1,018 | 594 | 58.4% (55.3 to 61.3) | 52.3% |
| G4 Spinellis 2020 | 128 | 0 | 0% (0 to 2.91) | 0% |
| G5 AI firm-domains | 1,703 | 29 | 1.70% (1.19 to 2.44) | 0.35% |
| G6 AI proposals v1 | 595 | 4 | 0.67% (0.26 to 1.72) | 0.17% |
| G7 AI proposals v2 | 4,547 | 30 | 0.66% (0.46 to 0.94) | 0.41% |

All v3 domain rows, also rows with no tokens (`source_raw_error_rows.csv`): G1 4.09% of 930, G2 11.2% of 206, G3 65.2% of 2,603 (985 rows went to independent), G4 0% of 113, G5 1.87% of 1,016, G6 0.44% of 458, G7 0.52% of 3,820.

Findings:

- The CNCF single-developer file is the weak source. It gives a developer's affiliation, not the domain owner.
- The gitdm "(Independent)" rows were mostly wrong in v3. They were university or project domains.
- The AI proposals are low because the build used only the high and medium answers. Also, the checks that measure them are AI checks of the same model family (E8).

### 5.2 Detection by check (`checks.csv`, `check_pairs.csv`, `capture_recapture.csv`)

| Check | Rows seen | Changed | Share changed | Tokens changed | Reversed later |
|---|---:|---:|---:|---:|---|
| round 4d (doubtful gitdm rows) | 959 | 563 | 58.7% | 46.5% | 0 |
| round 4f (look-alike rows, 10k tokens or more) | 3,454 | 68 | 1.97% | 0.16% | 3 (4.2% of raw changes) |
| round 7 (all v4.0 rows, blind) | 10,876 | 1,154 | 10.6% | 0.069% | 118 (9.3% of raw changes) |
| round 8 (801 conflicts) | 172 domain answers | 172 | - | - | 0 |
| user chat | 6 | 2 | - | - | - |

A change share is not a detection rate. It mixes the error prevalence of the rows with the sensitivity. The pairs separate them:

| Design | n1 | n2 | Result |
|---|---:|---:|---|
| removal: round 4d, then round 7 on the 269 kept rows | 563 | 3 | p = 0.995; N0 = 566.0; 0.02 errors left |
| removal: round 4f, then round 7 on the 3,126 kept rows | 68 | 2 | p = 0.971; N0 = 70.1; 0.06 errors left |
| moves of rounds 4d and 4f, judged again by round 7 | 145 | 0 changed | q4 = 0 of 145 |
| capture-recapture, organisation items: A found 1,342, B found 1,370, both 1,185 | | | Chapman N = 1,551.5 (sd 5.7); 24.5 missed by both (1.58%); p_A = 0.865, p_B = 0.883 |

### 5.3 Two-rater model of rounds 3, 4 and 5 (`rater_model.csv`)

8,681 items: 6,171 agreed and 1,206 differed only in form. Of the 1,304 real disagreements, round 5 took A in 511, B in 752, and a new answer in 41.

| Items | a (A wrong) | b (B wrong) | Agreed and wrong, rho = 0 | rho = 0.167 (rho_cal) | rho = 0.25 | rho = 0.5 |
|---|---:|---:|---:|---:|---:|---:|
| all 8,681 | 9.26% | 6.49% | 0.15% | - | 3.61% | 11.5% |
| organisations, 4,176 | 9.27% | 5.17% | 0% | 1.67% | 2.90% | 9.68% |
| domain conflicts, 4,505 | 9.34% | 7.79% | 0.39% | 2.69% | 4.29% | 13.3% |

For organisation items, the both-wrong share w is larger than the independence model predicts (rho_min = 0.011). The data show positive error correlation. A correlation above about 0.7 does not fit the observed disagreements.

### 5.4 Error of firm_based_on_domain (`column_error.csv`, `link_strata*.csv`, `sensitivity*.csv`)

The column has a value for every token since 2026-10-19: a token whose real domain has no row is `independent`, and a token with no real domain is `unknown`. So the main measure is the share of all tokens.

| Measure | Value | u | U (k = 2) | Monte Carlo 95% |
|---|---:|---:|---:|---|
| wrong share of all tokens (central) | 0.373% | 0.122 | 0.24 | 0.152% to 0.615% |
| of this: wrong links (rows of the database) | 0.109% | 0.057 | 0.11 | 0.044% to 0.263% |
| of this: organisations among the unmatched real domains (section 6.3) | 0.264% | 0.109 | 0.22 | 0.059% to 0.469% |
| wrong links, as a share of the linked tokens | 0.116% | 0.060 | 0.12 | 0.046% to 0.279% |

The values above are those of v4.5. Section 2.1 compares them with v4.1.

Old and new, side by side (the decisions of 2026-10-19, both on v4.1):

| Quantity | Before the decisions of 2026-10-19 | Now |
|---|---|---|
| wrong links, share of the linked tokens | 0.106% (U 0.13) | 0.115% (U 0.12) |
| column error, share of all tokens | 0.100% (U 0.12); 5.79% of the tokens had no value | 0.372% (U 0.24); every token has a value |
| company-kind share (section 5.5) | 37.35% (U 0.15), unmatched tokens not known | 37.50% (U 0.32), unmatched tokens counted |
| error of one user decision | uniform 0 to 2% (type B) | 1.53% (u 0.88), the user's reversal rate |
| employer terms | inside U: 17.9% of the linked tokens (U 19.9) | side study, not in the dataset budget (section 7) |

By the step that set the value (central values):

| Origin | Share of all tokens | Error |
|---|---:|---:|
| first source, kept by the checks | 89.2% | 0.080% |
| round 5 adjudication | 1.36% | 0.50% |
| rounds 3 and 4 agreed (AB) | 0.98% | 0.12% |
| user or manual (also v4.2) | 1.59% | 1.53% (the user's reversal rate) |
| round 4d or 4f move | 0.98% | 0.03% |
| round 7 move | 0.04% | 4.7% |
| round 8 | 0.06% | 5.6% |
| round 9 (v4.4, section 2.1) | 0.005% | 0.79% |
| suffix matches (all origins) | 0.23% | 3.7% |
| no row, now `independent`: real domains | 2.74% | 9.6% (section 6.3) |
| no real domain, now `unknown` | 3.05% | 0 (assumption A11) |

Sensitivity to the two type B choices of the AI checks (central values; the user DECIDED on 2026-10-19 to keep the measured range of se and rho until the audit):

| se of one AI check | rho = 0 | rho = 0.167 | rho = 0.5 | all tokens, rho = 0.167 |
|---:|---:|---:|---:|---:|
| 0.5 | 1.91% | 1.92% | 1.98% | 2.07% |
| 0.7 | 0.65% | 0.66% | 0.69% | 0.88% |
| 0.865 | 0.20% | 0.20% | 0.22% | 0.45% |
| 0.971 | 0.06% | 0.06% | 0.07% | 0.32% |

The first three value columns are shares of the linked tokens. The result depends mostly on se. The process measures se only with AI checks of one model family. If the AI checks share blind spots, se is lower than 0.865, and the column error is larger.

Sensitivity to the error of the user's decisions (`sensitivity_user.csv`, central values):

| Error of one user decision | Value | Wrong links (linked tokens) | Column error (all tokens) | Company share, line 3 |
|---|---:|---:|---:|---:|
| 0 (the user is the reference by definition) | 0 | 0.090% | 0.349% | 37.48% |
| reversal rate, 3 of 196 (main) | 1.53% | 0.116% | 0.373% | 37.29% |
| reversals and the 2 withdrawn decisions, 5 of 196 | 2.55% | 0.133% | 0.389% | 37.15% |
| the old type B term (uniform 0 to 2%, mean) | 1.0% | 0.107% | 0.365% | 37.35% |

The same term also sets the kind error of the organisations with the path "user or curated" (assumption A13). That is why the company share moves more than the column error.

### 5.5 Company-kind share (`budget_company_share.csv`)

| Line | Component | Value | u | U (k = 2) |
|---|---|---:|---:|---:|
| 1 | observed share (v4.5; a token with no row counts as `independent` or `unknown`) | 37.51% | - | - |
| 2 | link and kind residual errors (E1 + E4) | -0.24 | 0.120 | - |
| 3 | corrected for the link and kind errors only | 37.28% | 0.120 | 0.24 |
| 4 | companies among the unmatched real domains (now `independent`): company share uniform 0 to 2 x 8.6% | +0.234 | 0.098 | - |
| 5 | **dataset value: line 3 + line 4** (Monte Carlo) | **37.51%** | 0.155 | 0.31 |
| 6 | sensitivity: the company share of the unmatched real domains uniform 0 to 1 | +1.37 | 0.79 | - |
| 7 | line 3 + line 6 | 38.65% | 0.80 | 1.60 |
| 8 | check: Rogan-Gladen (Se 0.99319, Sp 0.99602) | 37.520% | - | equals the direct central value |

The Monte Carlo 95% intervals are 36.98% to 37.45% (line 3), 0.05 to 0.42 points (line 4) and 37.18% to 37.79% (line 5). Line 7 has hard bounds of 36.98% to 40.18%. On v4.1, line 2 was -0.25 (u 0.127) and line 5 was 37.50% (U 0.32). Line 2 is smaller on v4.5. The organisation rows of v4.2 and of round 9 now have the user error or q_r9 x phi as their kind error, not the error of one AI review. Line 2 is larger than in the first draft (-0.16): the user error is now 1.53% on average, not 1%. Since 2026-10-19 the pseudo ids `independent`, `free-provider` and `unknown` have no kind error (section 11a). Before that fix, line 2 was -0.23 (u 0.118) and line 5 was 37.52% (U 0.31): the old kind term moved a small share of the pseudo-id tokens to the company kind.

## 6. Other error sources (`other_sources.csv`)

### 6.1 Suffix matches (E1s)

0.226% of tokens match a parent domain (v4.5). Round 7 changed 31 of 875 subdomain rows (3.5%). The model uses this rate for every suffix match.

### 6.2 Partner addresses

Partner addresses under a company domain have 0.007% of tokens. They stay with the domain owner (a known limit). This term is too small to model.

### 6.3 No row in the database (E2): now `independent` or `unknown` (`other_sources.csv`, `unmatched_kinds.csv`, `sensitivity_unmatched.csv`)

DECIDED 2026-10-19: a token whose real domain has no row gets `firm_based_on_domain = independent`. A token with no real domain (blank, no dot, a git-svn id) gets `unknown` (DECIDED later the same day). The column is never NULL. `build_links.py` and `build_v0.py` apply both rules (2026-10-19).

| Part | Tokens | Share | Is the value wrong? |
|---|---:|---:|---|
| no real domain (blank, no dot, a git-svn id): `unknown` | 722,310,384 | 3.05% | No: the value says that the address is not known (assumption A11). |
| a real domain with a low-certainty AI proposal (1,966 domains) | 277,212,856 | 1.17% | Yes, for the organisations among them. |
| a real domain with no proposal (55,167 domains) | 371,803,882 | 1.57% | Yes, for the organisations among them; the same rate as the proposals (assumption A10). |

The kinds of the proposals (share of the proposed tokens; counts only):

| Proposed kind | Domains | Share of the proposed tokens |
|---|---:|---:|
| no answer (blank kind) | 1,126 | 53.0% |
| independent | 455 | 34.7% |
| company | 332 | 8.17% |
| free-provider | 14 | 2.68% |
| project | 19 | 0.93% |
| consultancy | 11 | 0.42% |
| nonprofit | 3 | 0.05% |
| academic | 5 | 0.05% |
| government | 1 | 0.00% |

So 8.59% of the proposed tokens are companies (company and consultancy), and 9.62% are organisations of any kind. A free-provider proposal is not an error of `independent`: a free address also means an independent person.

The term. The organisation share of the unmatched real domains is rectangular from 0 to 2 x 9.62% (mean 9.62%). The answers are low-certainty, so the rate can be anywhere from 0 to twice the measured value. The company share is rectangular from 0 to 2 x 8.59%, as before. One draw sets both: the organisation share is the company draw times 9.62 / 8.59 = 1.12, so that the organisation share is never below the company share.

Effect: the column error grows by 0.264 points of all tokens (u 0.109, U 0.22). The company-kind share grows by 0.234 points (u 0.098; section 5.5, line 4).

Model v4.7 replaces this type B rate by a measured rate (type A) when the page of the tail audit is complete: a PPS sample of 60 of the unmatched real domains, checked by the user (section 10a, "The tail audit").

Sensitivity (central values):

| Variant | Organisation rate | Company rate | Column error, all tokens | Company share |
|---|---:|---:|---:|---:|
| main: a blank kind is no organisation | 9.62% | 8.59% | 0.373% | 37.52% |
| the blank kinds have the mix of the answered proposals | 20.5% | 18.3% | 0.670% | 37.79% |
| hard bounds: 0 to 1 (mean 0.5) | 50% | 50% | 1.48% | 38.65% |

## 7. Outside the dataset measurand: the employer (a side study)

DECIDED 2026-10-19: the employer model is side work, not part of the dataset. The user: an employee who commits with a gmail address may commit as an outside participant, and with the company address on work time; that is not an error but a design decision. So the column measures the capacity that the chosen address shows, and two old error sources are not errors of the dataset:

- Staff of an organisation who commit with a free or personal address (E3).
- Time (E5): a domain of a bought firm maps to the buyer, so a token written before the purchase names the buyer. By the user's rules this is the defined value: "a former name is the current organisation" (DEFINITIONS.md section 1), and a bought firm whose brand is gone merges into the buyer (the user's Wolfson decision, 2026-10-17). The buyer is right by these rules. The term is about the employer on the commit date, so it stays in the side study.

`side/EMPLOYER_MODEL.md` and `side/employer_model.py` give the side study; its outputs are in `error-model/side-employer/`. For the employer, the same column is wrong on 18.7% of all tokens (U 20.5; 95% interval 1.8% to 35.7%), and the company-kind share would be 46.7% (U 15.5; v4.5; 46.6% on v4.1).

One time case stays open for the dataset: a domain of a defunct organisation can get a new holder, whose tokens then show the old organisation. The exposure is 0.45% of the tokens (organisations with status defunct). The process has no data on new holders, and a stale address of the old staff is the usual case. This is assumption A14, not a term of U.

### 7.1 Common mode of the AI checks (E8)

All link checks are AI checks of one model family. Section 5.4 shows the effect of a lower se.

## 8. The namespace column (`namespace_owner_check.csv`, `namespace_error.csv`)

The rows come from rosters (1,931 owns rows), the GitHub verified domain (217), company pages, Spinellis and name matches (candidates). The process checked the rows only indirectly:

- 34 `namespace-two-owners` conflicts were decided.
- The AI reviews saw the namespaces of every owner organisation.
- Merges and rejections changed the owner rows.

12 owns rows changed from v3 to v4.1. The later layers changed the namespace rows on purpose. The namespace rework of v4.3 gives the owns relation only to the organisation that controls the account, and AI round 9 (v4.4) checked these rows. On v4.5, 221 of the 1,010 owns rows differ from v3. A later layer set 171 of them: 152 by v4.3 and 19 by v4.4 (`namespace_owns_by_layer.csv`). The evidence `account-profile` is new in v4.3: the profile of the forge account names the organisation.

The second instrument is the domain column. For each project with an owner, the script computes the share of the project's tokens from the owner's own domains (the owner, its parent and its children). A company that owns a project but wrote no token of it is suspect. A foundation often writes no token with its own domain, so this test applies only to company owners.

| Owner rows (owns) | Projects | Bound basis | k | Bound B (Wilson upper) |
|---|---:|---|---:|---:|
| account profile, company | 11 | zero own tokens | 0 | 25.9% |
| account profile, foundation or other | 160 | changed by the process | 160 | 100% |
| company page, company | 38 | zero own tokens | 1 | 13.5% |
| roster, company | 7 | zero own tokens | 1 | 51.3% |
| roster, foundation or other | 408 | changed by the process | 6 | 3.17% |
| Spinellis, company | 4 | zero own tokens | 0 | 49.0% |
| verified domain, company | 341 | zero own tokens | 10 | 5.31% |
| verified domain, foundation or other | 38 | changed by the process | 5 | 27.3% |
| website domain, company | 1 | zero own tokens | 0 | 79.3% |
| website domain, foundation or other | 2 | changed by the process | 2 | 100% |

Each class is rectangular from 0 to B. The table gives the classes of v4.5 (v4.6 has the same values; section 2.1). Model v4.7 changes this section for both layers and for the audit values (section 10a).

- **Wrong owner (E6), owns rows:** 10.8% of the projects (u 4.6, U 9.3) and 8.3% of their tokens (U 6.0). On v4.1: 2.56% (u 0.75, U 1.5) and 2.93% (U 1.9).
- **Why the value went up.** The bound of a foundation or other owner counts each row that changed from v3 as suspect. All 160 rows of the class "account profile, foundation or other" changed in v4.3, so their bound is 100% (mean 50%). These changes are the rework itself, not errors that a check found. **Sensitivity:** if a change by a later layer (v4.3 to v4.6; the table text of model v4.6 says "v4.3 to v4.5", but the code counts the layers v4.3 to v4.6) is no sign of an error, the wrong-owner share is 3.0% of the projects (U 1.5) and 3.5% of the tokens (U 1.8). OPEN: the user must choose between the two values. A better estimate needs an audit of the v4.3 rows: round 9 judged 173 namespace items and found 57 wrong; v4.4 applied its answers.
- **Missed owner (E7):** the design takes `owns` only. 423 projects (11.9%; 13.2% of tokens) have a candidate row whose organisation wrote 10% or more of the tokens. They are probably owned. Most candidate rows pass this test (66% to 79% by evidence).
- 1,932 projects (54.5%) have no namespace row. With the owns rule, 2,538 projects (71.5%; 65.3% of tokens) have an empty column: the 1,932, and 606 projects with only a participates or candidate row.

All numbers of this section use `owns` rows only. The wrong-owner bound uses only owns rows. The candidate rows give only the missed-owner count.

**Review list** (`namespace_review_candidates.csv`; columns project, organisation_id, relation, evidence, token_share, reason). It holds project names and organisation ids, and no domain or person data. It is not in `tables.md`. It has 608 rows (v4.5):

| Reason | Rows |
|---|---:|
| owns row, company owner with no token from its own domains (the k of the company classes) | 12 |
| owns row, foundation or other owner that the process changed from v3 to v4.5 (the k of those classes) | 173 |
| candidate row, the organisation wrote 10% or more of the tokens (probable missed owner) | 423 |

When the user reviews these rows, the bound of each class must be computed again from the reviewed rows.

**Note on the rule.** The user chose `owns` only (section 11a). `LINK_COLUMNS_DESIGN.md` agrees. D6 and `build_links.py` still take the best row (owns, then participates, then candidate). `project_links.parquet` now fills an organisation for 1,616 projects: 1,010 owns, 38 participates and 568 candidate rows. Before the release, `build_links.py` must keep only the owns rows (open work; this change did not touch it).

## 9. Assumptions and their risks

| # | Assumption | Why it can fail | Effect |
|---|---|---|---|
| A1 | The final v4.1 answer is the truth for the changed links. | A check can be wrong. The q terms (section 4.4) cover this only in part. | The raw error can be too high or too low. |
| A2 | One se for all AI link checks, from the removal pass and from capture-recapture. | The checks use the same model family. Errors that all of them miss are not seen (heterogeneous catchability makes removal and capture-recapture estimates too low; Seber 1982). | The column error is too low. Section 5.4 shows the size. |
| A3 | rho from 0 to 0.167, calibrated on 186 user decisions. | The user saw the AI suggestion (anchoring). Those items are the top band, and rounds 1-2 used older prompts. | If rho is larger, the agreed answers have more errors. |
| A4 | Round 5 adjudicates correctly. | It is the same model, and it saw both answers. | The rates a and b can be wrong. |
| A5 | The links are independent given their stratum. | Errors of one organisation are correlated, for example all domains of one firm. | Small. The parameter uncertainty dominates u. |
| A6 | The kind of a lost link is uniform from 0 to 1. | Most lost links were personal domains (non-company). | Conservative for the company share. |
| A7 | A zero-count stratum uses the Jeffreys mean. | It is larger than the most probable value. | Conservative. |
| A8 | Changes before v3 are not counted. | The v1 to v3 builds also fixed errors. | The raw error of a source is too low. It is not a residual error. |
| A9 | The own-domain test is an upper-bound indicator for company namespace owners. | A small firm can commit with free addresses. | The bound is too high (conservative). |
| A10 | The organisation share of the unmatched real domains is rectangular from 0 to 2 x 9.62% (the proposal rate), also for the 55,181 domains with no proposal. | 53% of the proposed tokens have no answer. The domains with no proposal are smaller, and a small domain is more often personal. | The term can be too high or too low. If the blank answers have the mix of the answered proposals, the column error is 0.67% (section 6.3). |
| A11 | A token with no real domain (blank, no dot, a git-svn id) gets `unknown`. The value says that the address is not known, so it has no mapping error. | A git-svn id or a host name can come from the server of an organisation; `unknown` then hides an organisation. | No effect on the column error. The organisation shares of M3 can be too low, by at most 3.05 points. |
| A12 | The error of a user decision is the user's reversal rate (3 of 196). | The saved history starts on 2026-10-17 at 00:49 UTC; changes before it and changes before a save are not seen. Two decisions taken back with no new answer are not in k. | r can be too low. With the two withdrawn decisions, r = 2.55% (section 5.4). |
| A13 | The user-decision term also sets the kind error of the curated organisations (path "user or curated"). The pseudo ids `independent`, `free-provider` and `unknown` have no kind error (DECIDED 2026-10-19). | A curated source is not a user decision. | Conservative for the company share: with a zero user error, line 3 is 37.48% (not 37.27%). |
| A14 | The domain of a defunct organisation has no new holder in the dataset period. | A domain can expire and get a new holder. | Not in U. The exposure is 0.45% of the tokens; the share with a new holder is not known. |

## 10. What an audit adds later

The model does not need an audit. An audit can validate it and replace type B terms with type A terms.

1. The audit must be a stratified random sample with a fixed seed. Use the strata of `link_error.parquet`: origin x band x class x match.
2. Allocate the sample by the predicted error. Neyman allocation (Cochran 1977) puts more items where p_l t_l is large: round 5, round 7, round 8, suffix matches, G3, and the user-decided links.
3. A stratum with p = 0.1% needs about 3,000 items to find 3 errors. So the audit cannot measure the large clean strata directly. It can test them: 0 errors in 300 items gives an upper bound of 1% (95%).
4. The audit measures se without the common mode (E8), because the user is not an AI check. This is the main gain. The model's largest risk is se.
5. The audit tests the model per stratum. The test compares predicted and observed errors with a binomial test.
6. The same sample gives rho, with the user as the third rater.

The audit started on 2026-10-19 (sample of v4.1) and continues on the sample of v4.6 (`review/AUDIT_SAMPLE.md`). Model v4.7 reads its answers (section 10a). Model v4.6 does not.

## 10a. Model v4.7: both layers and the audit values (2026-10-25)

`error_model.py --model v4.7` (the default) is the model for database v4.7 and later. `--model v4.6` gives the published values of sections 0 to 9 again, byte for byte. Use the two models next to each other to show the effect of each change.

### What model v4.7 changes

1. **Both layers.** The propagation uses the tokens of version 1 and of the extension: the version 1 cache plus `x1k-links/dataset-x1k-links-1/domain_counts.x1k.parquet` (option `--x1k-counts`). The total is 32,626,028,860 tokens (`summary.json`, `total_tokens_ok`). The parameters still come from the history of version 1 (sections 4 and 5). The extension adds no history, so it adds no parameter.
2. **The merged links.** The default link folder is `x1k-links/dataset-x1k-links-1/links-merged/` (both layers). These links were made with database v4.6. When the link folder is older than the database, a domain with an exact row in the database and no link gets the exact link of `build_links.py` (same rules: no rejected organisation, no company for an academic or government domain, no dropped domain, the free-provider rule, the pseudo ids). A new row that gives only a suffix match stays unmatched. Check: with database v4.6 the rule adds 0 links, so it is the rule of `build_links.py`. With database v4.7 it adds 2,857 links (703,423,716 tokens, 2.16% of all tokens). `summary.json` gives `links_built_with_this_db` and `links_added_from_db_rows`. The final run must use links made with the final database; then the rule adds 0 links.
3. **The later AI layers.** A row with the source pointer `manual/v4N_` or `review/v4N_` (N of 7 or more) is a row of AI round N + 3 (v4.7 = round 10, v4.8 = round 11). Its origin is `rN+3`. Its error q is the error of one AI answer of that round, from the check sample of its audit page (`review/audit-v4N/`): k wrong of n decided answers of class `check`. The central value is the Jeffreys mean (k + 0.5) / (n + 1), as for q_r9. The interval is the 95% Clopper-Pearson interval. Each draw is Beta(k + 0.5, n - k + 0.5). When the page has no answer yet, q is q_r9 (a type B transfer from round 9, the last round with a check). A row whose domain or namespace is an item of class `decide` of the page is a user decision: the AI could not decide, so the user decides (origin `user`, error q_user). The same rules apply to the owns rows of the namespace column. No code change is necessary for v4.8.
4. **The kind of an organisation of a later round.** A later round stamps the organisation row (reviewer `claude-main`, a review date after 2026-10-20). When the organisation was in database v4.6 with the same kind, it keeps its path of v4.6: the round added a domain or a namespace, not the kind. Else its kind error is q of the later rounds x phi.
5. **The kind error of the user or curated path is q_user x phi.** Sections 4.4 and 4.6 say so, but the code of model v4.6 used q_user. This path holds 46.5% of the version 1 tokens. On version 1 alone this change moves the corrected company share (line 3) from 37.279% (U 0.241) to 37.421% (U 0.080), and the dataset value (line 5) from 37.513% (U 0.31) to 37.655% (U 0.21). The column error does not change.
6. **The namespace column.** A project of the extension has no v3 row, so it cannot have a change from v3. The share that the process changed (the bound of a foundation or other owner) therefore has the version 1 projects of the class as its denominator. The class bound applies only to the owns projects that no measured value and no later layer covers.
7. **The audit values** (next part).
8. **Text.** The model v4.7 tables say "a later layer (v4.3 or later)". The model v4.6 tables keep their published text.

### The audit values (type A)

`review/audit_analysis.py` reads the answers of the audit sample (`--audit-sample`, default `review/audit-sample-v4.6/`) each time it runs. `error_model.py` imports it. A link is in an audit stratum when its domain is a unit of the frame (`frame.csv`) and the link has the organisation of that unit. 12,450 links (29,541,228,193 tokens, 90.5% of all tokens) are in the frame. The other links (the new links of the extension and of round 10) keep the model value until the second phase of the audit gives them strata (`review/AUDIT_SAMPLE.md`).

The rule: when a stratum is complete (each sampled item has an answer), its measured value replaces the model value. `--audit-min-n N` lowers the rule to N decided answers. The measured value is the Jeffreys posterior of k wrong of n decided answers (an unsure answer does not count; the tables give it apart). The link error in the stratum becomes p x theta / m, where theta is the measured value and m is the mean model error of the links of the stratum. Thus the mean error of a unit of the stratum is the measured value, and the model keeps the relative error of the links in the stratum (a ratio estimator with the model as the auxiliary value). This is necessary because the audit measures an error per unit, the column error is per token, and a large link has a lower model error than a small one in the same stratum. The same replacement applies to an owns row of the namespace column: in a complete namespace stratum, the measured value replaces the class bound.

Each stratum measures one model parameter, with the later checks after it. `audit_replacements.csv` states each replacement: the parameter, the model value, the audit value, n, the binomial test against the model value, and whether the model uses the measured value. Interim state (2026-10-25, 14:47 UTC; 40 of the 920 items have an answer):

| Stratum | Parameter that the stratum measures | Model value (model v4.6 prediction) | Audit now: wrong of decided (unsure) | Measured value used |
|---|---|---|---|---|
| D01, D02 | no tokens in version 1: the band B3 value of the same origin | 7.83%, 5.41% (2.10%, 4.71%) | 0 of 2 (1); 0 of 2 (0) | no |
| D03, D04 | q_agreed, agreed answer of two AI reviews | 0.524%, 0.131% | 0 of 1 (1); 0 of 0 (1) | no |
| D05 | q4, a move of link check 4d or 4f | 0.219% | 0 of 0 | no |
| D06, D07 | q_single, one adjudication answer | 1.486%, 0.563% | 0 of 0; 0 of 1 | no |
| D08 | q7, a change of the sweep | 4.821% | 0 of 1 | no |
| D09 | q_single, the conflict round | 5.974% | 0 of 0 | no |
| D10 | q_r9, round 9 | 0.794% | 0 of 0 (1) | no |
| D11 to D18 | raw error of the first source, after the later checks | 0.062% (D11) to 3.648% (D13) | D11: 0 of 3; D12: 0 of 2 (1); others 0 of 0 | no |
| D19 | q_user, the user's decisions | 3.573% | 0 of 0 | no |
| N01 to N04 | bound B of the namespace class | 3.39%, 30.94%, 1.585%, 3.159% | 0 of 2 (1); 0 of 8; 1 of 6; 0 of 6 | no |

No stratum is complete yet, so the interim model values are those of the model. The binomial test finds no stratum different from the model value at the 5% level. The only wrong answer (a namespace row with a foundation roster as evidence) gives p = 0.091 against 1.585% (one tail).

`audit_update.csv` gives a sensitivity with all answers so far. Each stratum with an answer takes its value from the audit: (a) the Beta posterior with the model value as prior (the mean and variance of the model value in the Monte Carlo), and (b) the Jeffreys posterior alone. (a) gives 0.825% (U 0.648) for the column error, against 0.826% for the model alone. (b) gives 8.4%: the Jeffreys mean of 0 wrong of 2 or 3 is 12.5% to 16.7%, so a partial stratum must not replace the model value. This is why the rule waits for a complete stratum.

`review/audit_analysis.py` also gives the audit alone (AUDIT_SAMPLE.md, "Analysis after the audit"; outputs `audit_strata.csv`, `audit_population.csv`, `round_checks.csv`, `audit.md`, counts only). Interim: domains 12 decided answers, 0 wrong, 5 unsure (the strata with answers hold 92.4% of the tokens; token-weighted estimate 0%, Monte Carlo 95% interval 0.92% to 42.6%); namespaces 22 decided, 1 wrong, 1 unsure (project-weighted 6.7%, 95% interval 2.3% to 28.2%). These values are not informative yet.

**Round 10.** The check page of round 10 (`review/audit-v47/`) has 677 check items (a seeded 10% sample of 6,762 decided rows) and 97 items that the AI could not decide. At the run, 0 check items and 27 of the 97 had an answer. Thus q_r10 = q_r9 = 0.794% for now. 2,857 links (2.16% of all tokens) and 2,394 owns projects use it. When the check items have answers, q_r10 = (k + 0.5) / (n + 1), with the 95% Clopper-Pearson interval in `later_ai_layers.csv`.

### Interim values (2026-10-25; 2,000 draws, seed 20261018)

| Quantity | Model v4.6, published (v4.6, version 1) | Model v4.7, database v4.6 (both layers) | Model v4.7, database v4.7 (both layers) |
|---|---|---|---|
| tokens | 23,692,479,892 | 32,626,028,860 | 32,626,028,860 |
| links with tokens | 12,236 | 13,157 | 16,014 |
| error of `firm_based_on_domain`, all tokens | 0.373% (U 0.244; 95% 0.15 to 0.62) | 1.152% (U 1.03; 95% 0.28 to 2.02) | 0.826% (U 0.65; 95% 0.26 to 1.40) |
| of this: wrong links | 0.109% (U 0.114) | 0.123% (U 0.129) | 0.140% (U 0.139) |
| of this: organisations among the unmatched real domains | 0.264% (U 0.218) | 1.029% (U 1.03) | 0.685% (U 0.64) |
| wrong links, share of the linked tokens | 0.116% (U 0.121) | 0.136% (U 0.142) | 0.151% (U 0.150) |
| company share, observed | 37.513% | 32.275% | 33.318% |
| company share corrected for the link and kind errors (line 3) | 37.279% (U 0.241) | 32.195% (U 0.070) | 33.233% (U 0.075) |
| company share, dataset value (line 5) | 37.513% (U 0.31) | 33.065% (U 0.88) | 33.813% (U 0.55) |
| company share, hard bounds for the unmatched domains (line 7) | 38.648% (U 1.60) | 35.424% (U 3.73) | 35.384% (U 2.49) |
| namespace: wrong owner, owns projects (project-weighted) | 10.78% (U 9.26) of 1,010 | 7.58% (U 5.74) of 2,475 | 4.38% (U 3.09) of 4,923 |
| namespace: wrong owner, token-weighted | 8.30% (U 6.01) | 7.65% (U 5.54) | 6.20% (U 4.18) |
| namespace: a change by a later layer does not count (project-weighted) | 3.05% (U 1.48) | 2.90% (U 1.56) | 2.03% (U 1.35) |

The values are interim: no audit stratum is complete, round 10 has no check answer, and the links of v4.7 are not built. The largest term is now the organisations among the unmatched real domains: 0.69 of the 0.83 points. The extension adds many real domains with no row. The model gives them the type B rate of the unmatched domains of version 1 (uniform 0 to 2 x the rate of the AI proposals). Round 10 judged 3,175 new domains of the extension: by tokens, it found 53% organisations, 33% personal domains and 11% undecided. These domains have rows in v4.7, so they leave the unmatched pool. But the judged domains are the large ones, so the rate does not transfer to the tail without a check. The rate of the tail is the main open question of the domain column.

### The tail audit: a measured rate of the unmatched real domains (2026-10-26)

The user agreed (2026-10-26): add a random sample of about 60 domains of the unreviewed tail (the real mail domains with no organisation row in the database) to phase 2 of the audit. AI judges check the sampled domains with fetched web evidence (the round 10 method). The user checks all of them on an audit page. The measured, token-weighted organisation rate then replaces the assumed rate of the E2 term (section 6.3), one for one.

**The frame.** The frame is the E2 pool of the model, not a new list: `review/audit_tail_sample.py` takes it from `error_model.unmatched_rows` (model v4.7, database v4.8, the default links and extension counts). It is each domain of the evaluated tokens of both layers (the version 1 cache, domain and tokens columns only, and `domain_counts.x1k.parquet`) that has no link in `links-merged` after the exact links of the database (`add_db_links`), minus the tokens with no real domain (blank, no dot, an at sign). The two parts of the E2 term are both in it: the domains with a low-certainty AI proposal and the tail. The match is exact string equality of the domain: the token table joins the link table on the domain, and the database rows join on `company_domain.domain`; the proposal part matches in lower case. Thus the 3,175 domains of round 10 (with rows in v4.7) are not in the frame, and also the new-layer domains that `new_domains.x1k.tsv` lists and v4.8 maps. Size: 76,552 domains (1,966 with a proposal, 74,586 in the tail), 1,403,472,662 tokens (4.30% of all tokens). These are the same counts as the two E2 parts of the interim run on database v4.7: v4.8 changed no domain row. 515 frame domains have a removed link in `company_domain_dropped` (an earlier review found that the domain is not that organisation's). No frame domain matches a free-provider suffix of `build_links.py`, because those domains get the pseudo id `free-provider` and leave the pool. The frame checksum (sha256 of the sorted lines "domain TAB tokens") is a2ddb28d956313778d7bc9daae998ac355a4f29a0aea2c3a3caed7036c071ca4.

**The design.** Systematic sampling with probability proportional to tokens (PPS; Cochran 1977, chapter 9A), n = 60. The frame is sorted by tokens (descending, then by domain). Each domain with tokens at or above the step is a certainty unit; the step is computed again on the rest until no domain is larger. Result: 4 certainty units (147,818,924 tokens, 10.5% of the frame) and 56 points with the step K = 1,255,653,738 / 56 = 22,422,388 tokens. The start is u x K, with u the first 64 bits of sha256("20261026:tail") divided by 2^64. The inclusion probability of a point is 56 x t / 1,255,653,738 (from 0.008% to 91.6%). The workspace folder `review/audit-tail/` holds `frame.csv`, `design.json` (all units with their probabilities) and `sample.csv`; it is not in git, because it names personal domains. Of the 60 domains, 43 are in the tail part and 17 have a proposal.

**The AI verdicts.** Two judges, 30 domains each (`review/AI_ROUNDS.md`, "The tail audit"): 23 organisation (16 companies or consultancies, 7 other kinds), 25 independent (personal domains), 4 free-provider, 0 none, 8 unsure. The web archive blocked most snapshot pages, so the large dead domains are often unsure.

**The estimator** (`review/audit_tail.py`). The user's answer gives each unit a class: a right answer keeps the class of the AI verdict; a wrong answer gives the correct class of the answer (company, other organisation, independent, free-provider or none); an unsure answer, or a right answer to an AI verdict of unsure, gives unsure. y = 1 for an organisation of any kind. Each point has the weight t / pi = K, so the Horvitz-Thompson estimator (here also the Hansen-Hurwitz estimator) of the token-weighted rate is

    R = (sum over the certainty units of t y + K x (sum over the points of y)) / (sum over the certainty units of t + K x m)

with only the decided units in both sums (an unsure answer is apart) and m the number of decided points. With no unsure answer the denominator is the frame tokens. The certainty units have no sampling error, so R is a monotone function of the point share p = k / m. The 95% interval maps the Clopper-Pearson interval of p. The Monte Carlo draws map p ~ Beta(k + 0.5, m - k + 0.5) (Jeffreys) and the company share among the organisations s ~ Beta(kc + 0.5, k - kc + 0.5), so the company rate is never above the organisation rate. The central value is the Jeffreys mean, as for the audit strata. `tail_audit.csv` also gives the bounds for the unsure answers (all of them organisations, or none).

**Use in the model.** `error_model.py --model v4.7` reads the folder of `--tail-audit` (default `<ws>/review/audit-tail`; `--no-tail-audit` keeps the type B rate). When the page is complete (each item has an answer, and each wrong answer has its class), the measured organisation rate replaces o_unmatched and o_tail, and the measured company rate replaces f_unmatched and f_tail (the column error and line 4 of the company share). The draws use their own stream (seed + 11); the uniform draws of the type B rates still run, so all other draws stay the same. A sampled unit that is not in the evaluated pool leaves the estimate (for example a domain that a later link build matches by suffix), and the pool tokens outside the frame take the same rate; `summary.json` gives `tail_audit_frame_match` and `tail_audit_pool_tokens_in_frame_pct`. Until the page is complete, the type B rate stays: the outputs are those of `--no-tail-audit`, plus `tail_audit.csv`, one line in `parameters.csv` and the `tail_audit_*` keys of `summary.json` (checked on 2026-10-26 with `diff -r`). `--model v4.6` stays byte-identical to the published outputs.

**State at the run (2026-10-26; 2,000 draws, seed 20261018, database v4.8, the merged links).** 0 of the 60 items have an answer, so the model uses the type B rate: column error 0.813% (U 0.65; 95% 0.25 to 1.38), of which 0.685 points (U 0.64) are the organisations among the unmatched real domains; the company share, dataset value, is 33.817% (U 0.55). A sensitivity run (`agent-runs-20261023/tail-audit/`) takes the AI verdicts as the user's answers (right for each decided item, unsure for the 8 unsure items):

| Quantity | Type B (now) | Measured, if the user agrees with each decided AI verdict |
|---|---|---|
| organisation rate of the unmatched real domains | uniform 0 to 31.9% (mean 15.9%) | 44.4% (Horvitz-Thompson 44.3%; 95% Clopper-Pearson 31.4 to 57.7; unsure bounds 38.3 to 51.8) |
| company rate of the unmatched real domains | uniform 0 to 27.3% (mean 13.6%) | 29.2% (95% 18.0 to 43.0) |
| error of `firm_based_on_domain`, all tokens | 0.813% (U 0.65) | 2.035% (U 0.56; 95% 1.51 to 2.59) |
| of this: organisations among the unmatched real domains | 0.685% (U 0.64) | 1.908% (U 0.54) |
| company share, dataset value (line 5) | 33.817% (U 0.55) | 34.489% (U 0.50) |

The measured rate of the AI verdicts is far above the type B range. The type B rate counts a blank proposal kind (53% of the proposed tokens) as no organisation; the variant that gives the blank kinds the mix of the answered proposals has 30.4% (`sensitivity_unmatched.csv`). In the sample, small and large domains have about the same share of organisations (13 of the 29 decided domains under 1,000,000 tokens, 10 of the 23 at or above). If the user confirms the rate, the E2 term is the largest error of the domain column, and a review of the large unmatched domains is the cheapest way to make it smaller (each certainty unit alone holds 2.3% to 3.1% of the frame tokens).

### The column audit: a measured error of each column (2026-10-26)

The user decided (2026-10-26): the error numbers of the paper come from a measured audit sample of each organisation column, with at least 440 decided units per column and 800 at best. A measured rate then replaces the type B bounds. Before this audit, 334 of the 366 expected wrong owners of the namespace column came from type B bounds, and 497 projects in three classes had the bound 100%.

**The frames** (`review/audit_columns_sample.py`; database v4.9, the final links of the run dataset-final-2, the evaluated tokens of model v4.7). Namespace part: one unit for each owner namespace (host/namespace and its owner, an owns row of `firm_based_on_namespace`): 4,635 units, 7,627 projects, 26,767,918,616 tokens. Domain part: one unit for each real mail domain with tokens: 16,116 linked domains and 76,450 unmatched real domains, 92,566 units, 31,699,220,960 tokens. The 926,807,900 tokens with no real domain have the value unknown, which is right by definition; they are out of the frame.

**The design.** Each part has 800 units and a certainty stratum of the 60 largest units by tokens. Namespace part: one stratum for each term of section 8 (each class with a type B bound, round 10, round 11, and round 12 with the user decisions), a simple random sample in each, Neyman allocation on projects with the prior p of the model (B/2, or the q of the round), at least min(N_h, 15) units. Domain part: five strata (linked exact curated, linked exact other confidence, linked suffix, unmatched with an AI proposal, unmatched tail), systematic PPS on tokens in each (the method of the tail audit), Neyman allocation on tokens with the prior p (the token mean of `p_error`, or the organisation rate of the tail audit and of the proposals), at least min(N_h, 40) units. PPS has the lower variance for a token-weighted rate: the design effect of a simple random draw, N x sum(t^2) / (sum t)^2, is 13.6 to 566 in these strata. `design.json` in the workspace folder `review/audit-columns-v4.9/` (not in git) gives all strata, the seed text 20261026:columns and the frame checksums.

**The answers.** Namespace: right, or wrong with the correct class (another organisation, a person, the project itself, unknown), or unsure. Domain: right, or wrong with the correct class and the wrong part (the organisation, or only its kind), or unsure. An earlier answer of the user to the same question (the same namespace or domain and the same organisation and kind now; audits sample46, v47, v48 and tail) is carried: the page shows it with the tag carried, and the user can change it.

**The estimator** (`review/audit_columns.py`, changed 2026-10-28). The estimate is design-based. It uses no prior.

- A certainty stratum has no sampling error. Its rate is the weighted share of its answered units.
- A namespace stratum (simple random sample, Neyman allocation) uses the ratio estimator: r_h = sum w y / sum w over the answered units, with w the projects or the tokens of each unit. Its effective size is the Kish size n_h = (sum w)^2 / sum w^2, and its effective wrong count is k_h = r_h n_h.
- A domain stratum (systematic PPS on tokens) uses the PPS form of the tail audit: R_h = (sum_C t y + K M p_h) / (sum_C t + K M). C is the set of certainty units of the stratum, K = rest_tokens / rest_n is the token weight of one point, M is the number of answered points, and p_h = k_h / M is the wrong share of the points. The effective size is n_h = M.
- The rate of the column is sum W_h R_h / sum W_h over the strata with answers. W_h is the projects or the tokens of the stratum.

The central value is this design-weighted observed rate. With 0 wrong answers, the central value is 0.

The 95% interval is a stratified Clopper-Pearson interval with the effective size of each stratum (the effective-size form of Korn and Graubard 1998; Clopper and Pearson 1934; Kish 1965). The Monte Carlo method of JCGM 101:2008 combines the strata. Each draw of the lower limit takes p_h from Beta(k_h, n_h - k_h + 1), and p_h = 0 when k_h = 0. Each draw of the upper limit takes p_h from Beta(k_h + 1, n_h - k_h), and p_h = 1 when k_h = n_h. The finite-population correction fpc_h = 1 - n_h / N_h scales the distance of each draw from the observed share: p = r + sqrt(fpc_h) (x - r). The lower limit is the 2.5 percentile of the lower draws. The upper limit is the 97.5 percentile of the upper draws. With one stratum and fpc = 1, the interval is the exact Clopper-Pearson interval. With 0 wrong answers in all strata, the lower limit is 0 and the upper limit is more than 0. The standard uncertainty u is the standard deviation of all draws of both limits, and U = 2u.

The earlier estimator (until 2026-10-28) used the Jeffreys mean (k + 0.5) / (n + 1) of each stratum as its central value. That value is not 0 when k = 0. The Kish size of a namespace stratum is small when one unit has most of the projects of the sample. For example, in the stratum "class roster, foundation-or-other", one namespace has 135 of the 262 sampled projects, the Kish size is 3.16, and the Jeffreys mean of 0 wrong is 0.5 / 4.16 = 12.0%. Thus the earlier central values were prior values, not measured values.

An unsure answer is unknown, not right. The estimate gives the range from all unsure right (f = 0) to all unsure wrong (f = 1), with f the wrong share of the unsure units. The central value takes f = 0.5. The Monte Carlo draws take f from Uniform(0, 1), one f for all unsure units (a rectangular term). A domain is wrong when the column names the wrong organisation. For a domain with no link (value independent), only a correct class of an organisation is wrong, as in the E2 term. A kind-only error and the company share are reported apart.

**Use in the model.** `error_model.py --model v4.7 --column-audit <folder>` adds the tables `column_audit_state`, `column_audit_estimate`, `column_audit_strata` and `column_audit_sample_size`. When a part has at least 440 decided answers, its measured values replace the model values in `summary.json` (namespace: `namespace_wrong_owner_projects_pct` and `_tokens_pct`; domain: `E_dataset_pct`, `E_dataset_U_pct`, `E_dataset_mc95`, `E_all_pct`, `E_unmatched_pct`, `E_linked_pct`), and the model values stay under the keys `*_model_pct`. `namespace_error_basis` and `domain_error_basis` say which values the summary gives. Without the option the outputs are those of the plain run (checked on 2026-10-26 with `diff -r`: `summary.json` and all tables are the same; `summary.csv` and `tables.md` differ only in the order of the keys of `later_layers`, which comes from the set order of the round checks in the plain code too).

### What the final run needs

1. All answers: the 920 items of the audit sample and the 677 check items of round 10 (and the check items of round 11 for v4.8).
2. The final database (v4.8) and links of both layers made with it. Then run `error_model.py --db companies.v4.8.duckdb --links <that folder>`. Check in `summary.json`: `links_built_with_this_db` is true, `links_added_from_db_rows` is 0, `total_tokens_ok` is true, and `audit_strata_used` lists the complete strata.
3. The second phase of the audit (`review/AUDIT_SAMPLE.md`) for the units that only the extension adds. Until then they keep the model value (`audit_tokens_in_frame` gives the share that the audit covers).
4. Copy the final values of `audit_replacements.csv`, `later_ai_layers.csv`, `column_error.csv`, `budget_company_share.csv` and `namespace_error.csv` into this section, next to the model v4.6 values (`--model v4.6`).
5. The tail audit page complete: 60 answers, and each wrong answer with its class. Check in `summary.json`: `tail_audit_used` is true and `tail_audit_frame_match` is true. With links built again from v4.8, the pool can lose the domains that a new row matches by suffix; then the frame does not match, and `tail_audit_pool_tokens_in_frame_pct` gives the share of the pool that the frame covers (it must stay near 100). Copy `tail_audit.csv` and the measured line of `sensitivity_unmatched.csv` into this section.

## 11. Choices of the user

All seven choices are DECIDED. The words of each decision are in section 11a.

1. **se of the AI checks.** DECIDED 2026-10-19: the measured range (0.865 to 0.971) until the audit. The audit then measures se without the common mode (section 10). (The other choice was a wider type B range down to 0.5 for shared blind spots; section 5.4 shows its effect.)
2. **rho.** DECIDED 2026-10-19: uniform 0 to 0.167, calibrated on the user's decisions (section 4.3).
3. **Error of the user's own decisions.** DECIDED 2026-10-19: the user's reversal rate, r = 3/196 = 1.53% with u = 0.88 points (section 4.4). It replaces the uniform 0 to 2% term. (The other choices were 0, the user as the reference by definition, and the old uniform term; section 5.4 gives both.)
4. **The measurand M3 and the unmatched domains (E2).** DECIDED 2026-10-19: a token whose real domain has no row is `independent`; a token with no real domain is `unknown`. The dataset value of the company-kind share is line 5 of section 5.5, with the companies among the unmatched domains from the AI proposal rate. Line 7 (hard bounds) stays as a sensitivity. `build_links.py` and `build_v0.py` apply the rules.
5. **The namespace rule.** DECIDED 2026-10-19: `owns` only. Section 8 uses this rule, and `namespace_review_candidates.csv` lists the rows to review. (The other choice was the best row of D6: more owners, more candidates of unknown quality.)
6. **The measurand of the domain column (M1).** DECIDED 2026-10-19: the organisation of the address that the author chose for the commit. A personal or free address means an independent person. The employer is a side study (section 7). This decision replaces the first decision of the same day (the employer, with the staff and time terms inside U).
7. **Release.** DECIDED 2026-10-19: ship `p_error` per domain in the `organisation_domains` reference table (`organisation_domains_p_error.parquet`; section 4.5).

## 11a. User decisions (2026-10-19)

First decisions of the day:

- Choice 5, the namespace rule: `owns` rows only. The user expects the wrong owners and the missed owners to be fixable by review. The model then measures what is left after that review.
- The user agreed to audit a stratified random sample (section 10). The sample is in preparation (`review/AUDIT_SAMPLE.md`).
- Choice 6, first answer: the employer. This answer is now replaced (below).

Later decisions of the day:

- Choice 6: **the employer model is side work, not part of the dataset.** The user: an employee who commits with a gmail address may commit as an outside participant, and with the company address on work time; that is not an error, it is a design decision. So `firm_based_on_domain` measures the organisation of the address that the author chose (the capacity in which the author committed). A personal or free address means that the author acted as an independent person. The staff and time terms moved to `side/EMPLOYER_MODEL.md` and `side/employer_model.py`. No person id and no other new data comes from the dataset files; the user has not agreed to that extraction.
- Choice 4: **unmatched domains map to `independent`.** The 5.79% of tokens whose domain has no row get `independent`. Section 6.3 gives the error term of the organisations among them.
- Choice 4, changed later the same day: **a token with no real domain gets `unknown`** (blank, no dot, a git-svn id; 3.05% of the tokens). A real domain with no row stays `independent` (2.74%). `unknown` is a pseudo id like `independent` and `free-provider`. It has no mapping error: the value says that the address is not known (assumption A11).
- Approved fix: **the pseudo ids have no kind error.** `independent`, `free-provider` and `unknown` name no organisation, so their kind cannot be wrong. `error_model.py` (function `kind_error`) gives them a kind error of 0. The column error does not change (0.372%). The company-kind share goes from 37.52% (U 0.31) to 37.50% (U 0.32); line 2 of section 5.5 goes from -0.23 to -0.25. Two runs give the same tables (checked on 2026-10-19 with `diff -r`).
- Choice 3: **the error of the user's own decisions** uses the metrology convention that the user named: the standard deviation of a measured metric of the process. The metric is the user's reversal rate (section 4.4). The change of choice 6 itself is a change of method, not an answer to a review item, so it is not in the count.
- Choice 7: **ship `p_error` per domain** in `organisation_domains` (section 4.5).
- Choices 1 and 2 (kept): the share of errors that the AI checks find is the measured range until the audit; the shared-mistake level (rho) is calibrated on the user's decisions.
- Done 2026-10-19: `error_model.py` computes the dataset budget only. `side/employer_model.py` imports it and computes the employer study.

Note for the audit sample. The sample (`review/audit-sample/`, made at 00:22 UTC) records the sha256 of the old `link_error.parquet`. The new file differs only in `p_error` of the 10 links that the user set (1.0% before, 1.53% now). The cells of all links are the same. `audit_sample.py` makes a new sample when the file changes; the main session decides whether to draw it again.

## 12. Reproduce

    cd 2026.2-estudos-pesquisa-sistemas/dataset-selection/s8-companies
    PY=~/Projects/cregit-workspace/census-local-a/ctp/.venv/bin/python
    W=~/Projects/cregit-workspace/companies
    $PY -I error_model.py --model v4.6             # the published model: v4.6, version 1 (out: $W/error-model)
    $PY -I error_model.py                          # model v4.7 (the default): database v4.7, both layers,
                                                   # the audit values (out: $W/error-model-v4.7)
    $PY -I error_model.py --db $W/companies.v4.8.duckdb --links <the links of v4.8, both layers>
                                                   # the final run (out: $W/error-model-v4.8)
    $PY -I review/audit_analysis.py                # the audit alone (out: $W/review/audit-analysis)
    $PY -I side/employer_model.py                  # the side study
    $PY -I review/audit_tail_sample.py             # the frame and the sample of the tail audit (out: $W/review/audit-tail)
    $PY -I review/audit_tail.py estimate           # the tail audit alone (counts and rates only)
    $PY -I -m pytest -q -p no:cacheprovider test_error_model.py review/test_audit_analysis.py \
        review/test_audit_tail.py side/test_employer_model.py test_link_format.py test_build_organisations.py

Model v4.7 has these options: `--x1k-counts` (the domain counts of the extension), `--audit-sample` (the audit sample folder), `--audit-min-n N` (a stratum gives its measured value with N decided answers; default: only a complete stratum), `--no-audit`, `--tail-audit` (the tail audit folder; its measured rates replace the type B rates of the unmatched real domains when its page is complete) and `--no-tail-audit`.

One run of `error_model.py` takes about 80 seconds (model v4.7: about 150 seconds); the side study takes about 50 seconds. Two runs give the same tables and Parquet files (checked on 2026-10-19 with `diff -r`, for both scripts; checked again on 2026-10-20 for v4.5: each CSV, `summary.json` and `tables.md` byte by byte, and the two Parquet files by content and by bytes). The v4.1 outputs are in `error-model-v4.1-20261019/`. The scripts read the cache only through its domain and tokens columns and the file name (the project). No output holds a domain, an address or a person name. Only `namespace_review_candidates.csv` holds project names and organisation ids; it is not in `tables.md`.

## References

- Briand, L. C., El Emam, K., Freimut, B. G., and Laitenberger, O. (2000). A comprehensive evaluation of capture-recapture models for estimating software defect content. IEEE Transactions on Software Engineering 26(6), 518-540.
- Brown, L. D., Cai, T. T., and DasGupta, A. (2001). Interval estimation for a binomial proportion. Statistical Science 16(2), 101-133.
- Chapman, D. G. (1951). Some properties of the hypergeometric distribution with applications to zoological sample censuses. University of California Publications in Statistics 1, 131-160.
- Clopper, C. J., and Pearson, E. S. (1934). The use of confidence or fiducial limits illustrated in the case of the binomial. Biometrika 26(4), 404-413.
- Cochran, W. G. (1977). Sampling Techniques, 3rd ed. Wiley.
- Dawid, A. P., and Skene, A. M. (1979). Maximum likelihood estimation of observer error-rates using the EM algorithm. Applied Statistics 28(1), 20-28.
- Efron, B., and Tibshirani, R. J. (1993). An Introduction to the Bootstrap. Chapman and Hall.
- Eick, S. G., Loader, C. R., Long, M. D., Votta, L. G., and Vander Wiel, S. (1992). Estimating software fault content before coding. Proceedings of the 14th International Conference on Software Engineering, 59-65.
- Hui, S. L., and Walter, S. D. (1980). Estimating the error rates of diagnostic tests. Biometrics 36(1), 167-171.
- JCGM 100:2008. Evaluation of measurement data - Guide to the expression of uncertainty in measurement (GUM).
- JCGM 101:2008. Evaluation of measurement data - Supplement 1 to the GUM - Propagation of distributions using a Monte Carlo method.
- JCGM 200:2012. International vocabulary of metrology - Basic and general concepts and associated terms (VIM), 3rd ed.
- Kish, L. (1965). Survey Sampling. Wiley.
- Korn, E. L., and Graubard, B. I. (1998). Confidence intervals for proportions with small expected number of positive counts estimated from survey data. Survey Methodology 24(2), 193-201.
- Lincoln, F. C. (1930). Calculating waterfowl abundance on the basis of banding returns. U.S. Department of Agriculture Circular 118.
- Petersen, C. G. J. (1896). The yearly immigration of young plaice into the Limfjord from the German Sea. Report of the Danish Biological Station 6, 1-48.
- Rogan, W. J., and Gladen, B. (1978). Estimating prevalence from the results of a screening test. American Journal of Epidemiology 107(1), 71-76.
- Seber, G. A. F. (1982). The Estimation of Animal Abundance and Related Parameters, 2nd ed. Griffin.
- Seber, G. A. F., and Le Cren, E. D. (1967). Estimating population parameters from catches large relative to the population. Journal of Animal Ecology 36(3), 631-643.
- Wilson, E. B. (1927). Probable inference, the law of succession, and statistical inference. Journal of the American Statistical Association 22(158), 209-212.
- Zippin, C. (1956). An evaluation of the removal method of estimating animal populations. Biometrics 12(2), 163-189.
