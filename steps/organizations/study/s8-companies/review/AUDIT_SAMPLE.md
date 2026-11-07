# Audit sample of the S8 organisation database v4.1 (second audit pass, 2026-10-19)

## Purpose

The user agreed to audit a stratified random sample of the database (ERROR_MODEL.md, sections 10 and 11a). The audit gives type A values for the error of the two organisation columns. It also tests the error model in each stratum. The user is not an AI check, so the audit measures the detection rate of the AI checks without their shared blind spots.

## Populations

1. Domain units. Each dataset domain with a link in v4.1 is one unit (12,222 units). Each row of company_domain that no link uses is also one unit (1,743 units). These rows have no tokens. They are in their own band, "B0 no tokens".
2. Namespace units. Each `owns` row of company_namespace is one unit (2,188 units).

Not in the sample: the 492 links with no organisation in v4.1, and all unmatched domains. They belong to a separate audit of the domains with no match.

## Strata

The cells are those of link_error.parquet: origin x token band x class x match. The audit strata are unions of these cells. Many cells have fewer than 30 units, so the script joins them by a fixed rule (domain_rule in audit_sample.py):

- Rows with no tokens: one stratum for organisations, one for personal or free domains. All origins are together. A row with no tokens is never in a stratum with token rows.
- First source, kept by the later checks: one stratum for each token band and class (organisation, or personal or free) for the exact matches. The suffix matches are in two strata: bands B1 and B2 together, and band B3.
- Agreed answer of rounds 3 and 4, and the adjudication of rounds 5 and 6: one stratum for each class.
- Set by link check rounds 4d or 4f, set by round 7, set by round 8, and set by the user: one stratum each.

The namespace strata use the classes of the error model (section 8): evidence class x owner kind x "has dataset projects". Rows with no dataset project are one stratum. The two large classes with projects are alone. The other classes with projects are one stratum.

The result is 18 domain strata and 4 namespace strata. frame.csv gives the stratum of each unit.

The error model gives no predicted error for rows with no tokens. For these rows the script uses the mean error of the band-B3 exact links of the same origin group and class.

## Allocation

1. The budget of a population is 40 items for each stratum. Thus the mean is 40 items for each stratum.
2. Each stratum gets at least 30 items, or all its units if it has fewer. 0 errors in 30 items give a 95% upper bound of 9.5%. This bound is below 9.6%, the upper bound of the error of one unconfirmed AI answer (10 of 186 user decisions). Thus a clean stratum shows that it is better than one unchecked AI answer.
3. The script gives the rest of the budget by a compromise Neyman allocation (Cochran 1977, chapter 5A). It takes the mean of two Neyman shares. The first share is N_h S_h, for the error rate of the rows. The second share is T_h S_h, for the token-weighted error of the column (for namespaces, the project-weighted error). S_h = sqrt(p_h (1 - p_h)), and p_h is the predicted error of the error model.
4. No stratum gets more items than it has units.

The extra items go to the first-source links with 1M tokens or more (90.5% of the linked tokens), to the band-B3 suffix matches, and to the namespace rows.

## Total

The total is 880 items: 720 domains and 160 namespaces. At about 30 seconds for each item, the audit takes about 7 to 8 hours. One person can do it in two or three sessions. A smaller total would give fewer than 30 items to some strata, so a clean stratum would not give a useful bound. A larger total would take more than one working day.

## Draw

The script takes a simple random sample without replacement in each stratum. The seed of a stratum is sha256("20261019:<stratum id>"). Thus the sample of one stratum does not change when another stratum changes. The page shows the items in one seeded random order. Thus the strata are mixed.

## The audit page

The page shows the domain or the namespace, the mapped organisation (kind, parent, other fields), and the evidence that the database has. The page does not show the stratum or the predicted error, so the audit is blind. Links to the website of the domain and to a web search open only on a click.

Give one answer for each item: right, wrong or unsure. For "wrong", type the correct organisation. You can add a note. The server writes answers.csv. A value that holds an at sign is not saved.

## Analysis after the audit

1. In each stratum, the error rate is k_h / n_h, without the "unsure" answers. Give a Clopper-Pearson interval.
2. Compare each stratum with its predicted error by a binomial test.
3. For the column error, weight each stratum by its token share (strata.csv, weight_share_pct). Use the design weight N_h / n_h.
4. Report the "unsure" answers apart from the errors.

`audit_analysis.py` (2026-10-25) does these steps. It reads answers.csv each time it runs, so the run after the last answer gives the final values with no change of code:

    ~/Projects/cregit-workspace/census-local-a/ctp/.venv/bin/python -I audit_analysis.py
    ~/Projects/cregit-workspace/census-local-a/ctp/.venv/bin/python -I -m pytest -q test_audit_analysis.py

- Per stratum (audit_strata.csv): right, wrong and unsure answers; k_h / n_h without the unsure answers; the 95% Clopper-Pearson interval; the Jeffreys mean; the worst case (all unsure answers wrong); the exact binomial test against p_pred_links_pct (both tails and the two-sided p value). A wrong answer with a correct organisation id equal to the shown id counts apart (the organisation is right, another field is wrong).
- Per population (audit_population.csv): the column error with the token share (domains) or the project share (namespaces) of each stratum, and with the row share N_h / N; the design-based value sum_h (N_h / n_h) sum_i w_i e_i over the items with a decided answer; the coverage (the weight of the strata with an answer); the stratified standard error with the finite population correction; a Monte Carlo interval of the Jeffreys posteriors (20,000 draws, seed 20261025).
- The check pages of the AI rounds (round_checks.csv; default review/audit-v47): the error of one AI answer of the round from its check items (Jeffreys mean, Clopper-Pearson interval), and the count of the items that the AI could not decide (user decisions).
- An answer with another data_sha256 (another database) or another items_sha256 (another page) does not count. The outputs (default ~/Projects/cregit-workspace/companies/review/audit-analysis/) hold counts only. The script never writes to an answers file.

error_model.py (model v4.7) imports the script and uses the measured value of each complete stratum (ERROR_MODEL.md, section 10a).

## Reproduce

    cd 2026.2-estudos-pesquisa-sistemas/dataset-selection/s8-companies/review
    ~/Projects/cregit-workspace/census-local-a/ctp/.venv/bin/python -I audit_sample.py
    ~/Projects/cregit-workspace/census-local-a/ctp/.venv/bin/python -I -m pytest -q test_audit_sample.py

The script reads companies.v4.duckdb, links-v4/domain_links.parquet, links-v4/project_links.parquet, error-model/link_error.parquet and error-model/namespace_error.csv. It does not read the extraction cache. The outputs go to ~/Projects/cregit-workspace/companies/review/audit-sample/. They hold domains, so they stay off the record. meta.json holds the sha256 of the database and of link_error.parquet. If either changes, a new run makes a new sample.

## The v4.6 draw (2026-10-23)

The user answered 79 of the 880 items of the v4.1 sample. The published values come from database v4.6, so the error model needs a sample of v4.6. The user asked on 2026-10-23 to finish the sample. The script drew the sample again from v4.6, with the same design and the same seed:

    W=~/Projects/cregit-workspace/companies
    ~/Projects/cregit-workspace/census-local-a/ctp/.venv/bin/python -I audit_sample.py \
      --out $W/review/audit-sample-v4.6 --db $W/companies.v4.6.duckdb --links $W/links-v4.6 --error-model $W/error-model
    ~/Projects/cregit-workspace/census-local-a/ctp/.venv/bin/python -I carry_sample_answers.py \
      --old $W/review/audit-sample --new $W/review/audit-sample-v4.6

Result: 920 items (meta.json data_sha256 cefa55cc...; sample.csv sha256 775bd33f...).

- Domains: 13,980 units, 19 strata, 760 items. The new stratum D19 holds the links that a user decision set after v4.1 (26 units, all in the sample).
- Namespaces: 1,005 units (the `owns` rows of v4.6; rule N1 cut them from 2,188), 4 strata, 160 items.

carry_sample_answers.py keeps an old answer only when the new sample has the same unit (population and key) with the same organisation. 26 of the 79 answers carry over (7 domains, 19 namespaces; 24 right, 2 unsure). The other 53 items changed their value or are not in the new draw. carried.csv lists the pairs of old and new item ids. Thus 894 items are open.

The page is the mount `sample46` of the audit hub (http://127.0.0.1:8767/sample46/). It keeps its browser backup under its own key (`s8sample46.answers`), so the backup of the v4.1 page does not mix in. The v4.1 sample stays read-only in `review/audit-sample/`.

## Two phases for the extension (user decision, 2026-10-23)

The v4.6 sample covers the units of version 1 only: the extension (projects with 1,000 to 4,999 commits) has no organisation links yet. The user agreed to two phases:

1. Phase 1, now: the user answers the 894 open items of the v4.6 sample. These answers stay valid after the extension links exist, because the database rows that they check do not change.
2. Phase 2, after the extension links exist: new strata for the units that only the extension adds (new domain links, new `owns` rows with extension projects) and for the version 1 links whose token band changes with the extension tokens. The same design rules (floor 30, compromise Neyman allocation, seed sha256("20261019:<stratum id>")) draw the extra items. The analysis then weights each stratum by its token share in the full dataset (version 1 + extension).
3. Phase 2 also has the tail audit (user decision, 2026-10-26): a random sample of 60 of the real mail domains with no organisation row in the database (both layers; 76,552 domains, 1,403,472,662 tokens in v4.8). The sample is proportional to tokens (systematic PPS, seed sha256("20261026:tail"); 4 domains larger than the step are certainty units). The user checks the AI verdict of each sampled domain on the audit page `tail` of the hub. The answers give a token-weighted organisation rate of these domains (`audit_tail.py`, Horvitz-Thompson), which replaces the assumed rate of the error model when the page is complete (`../ERROR_MODEL.md` section 10a). Method and results of the AI judges: `AI_ROUNDS.md`, "The tail audit".
