# The error model and the column audit

`docs/ERROR.md` of the release gives the error of the organization columns. Its numbers come
from the final error model with the column audit (2026-10-28, database v4.9, the final links
of all project files). This folder holds the result tables of that run. The scripts are in
`../organizations/study/s8-companies/` (study commit `561edc9fdc32`).

## Scripts

| Script | What it does |
|---|---|
| `error_model.py` | The model: the raw error of each source, the detection of each check, the error probability of each link, Monte Carlo propagation (2,000 draws, seed 20261018), the column error and the corrected share of company tokens. `ERROR_MODEL.md` explains it. |
| `review/audit_columns_sample.py` | The frames and the stratified samples of the column audit (seed text `20261026:columns`, 800 units for each column). |
| `review/audit_columns.py` | `build`: the items of the audit page. `estimate`: the design-weighted rates and the stratified Clopper-Pearson intervals. For a part with 440 or more decided answers, `error_model.py` uses these rates in place of the model terms. |
| `review/audit_tail.py`, `review/audit_tail_sample.py` | The tail audit: a sample of 60 unmatched real domains with probability proportional to tokens, and the organization rate of the `independent` fallback. |
| `review/audit_analysis.py` | The earlier audit sample: the reversal rate of the reference decisions (3 of 196). |

## Results (`results/`)

The tables that `error_model.py` wrote on 2026-10-28 (output folder of the final model).
They hold counts, rates and labels only.

| File | Numbers of `docs/ERROR.md` |
|---|---|
| `summary.json`, `summary.csv` | All headline values: the error of `firm_based_on_domain` (2.735%, U = 2.0 points), its two parts, the corrected share of company tokens (34.471%), the model values without the audit. |
| `column_audit_state.csv`, `column_audit_strata.csv`, `column_audit_estimate.csv`, `column_audit_sample_size.csv` | Section 4, the column audit: decided, unsure and carried answers, and the rates of each stratum and part. |
| `tail_audit.csv` | The tail audit (41.7% organizations, 25.8% companies). |
| `column_error.csv`, `namespace_error.csv` | The model terms of both columns. |
| `parameters.csv`, `source_raw_error*.csv`, `capture_recapture.csv`, `check_pairs.csv`, `checks.csv`, `rater_model.csv`, `sensitivity*.csv` and the other CSV files | The parameters and the intermediate tables. |
| `tables.md` | All tables in one Markdown file. |

Not here: `namespace_review_candidates.csv` of the same folder (it lists account names),
`organisation_domains_p_error.parquet` (one row for each of the 16,119 links, keyed by a hash
of the domain, also the links of personal domains that the public table leaves out; the public
part is the `p_error` column of `organizations/organization_domains.parquet` of the release) and
`link_error.parquet` (it is in the release, `organizations/link_error.parquet`).

## The run

The model ran on the working copy at 01:18 UTC; study commit `79543bc` (01:33 UTC) has the
same scripts, and so has `561edc9`. The run recorded no hash of the scripts. The inputs are
in the private work folder: the database versions v3 to v4.9, the link history, the final
links of the write, the review rounds and the audit answers. They hold domains and account
names, some of them personal, so they are not here.

## How to run

```sh
cd steps/organizations/study/s8-companies
python3 -I review/audit_columns_sample.py --ws WORK --db companies.v4.9.duckdb --links LINKS --out AUDIT
python3 -I review/audit_columns.py build --folder AUDIT --db companies.v4.9.duckdb --links LINKS
# (the answers of the audit page go to AUDIT/ns/answers.csv and AUDIT/dom/answers.csv)
python3 -I review/audit_columns.py estimate --folder AUDIT
python3 -I error_model.py --ws WORK --db companies.v4.9.duckdb --links LINKS --out OUT --draws 2000 --seed 20261018
```

The tests are in `../organizations/` (`test_error_model.py`, `review/test_audit_*.py`).
