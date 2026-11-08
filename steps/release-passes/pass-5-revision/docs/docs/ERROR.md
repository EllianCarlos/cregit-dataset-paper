# The error of the organization columns of Token on Me (TOM)

The organization columns `firm_based_on_domain` and `firm_based_on_namespace` are measurements. They
can be wrong. This file gives the error columns, the audited error figures and the method. The paper
and the replication package (https://github.com/EllianCarlos/cregit-dataset-paper) give the full
error model.

## 1. The error columns

- `organizations/organization_domains.parquet` has two error columns for each domain row:
  - `error_stratum`: the error cell of the link (origin group / token band / kind class / match),
    for example `source/B1 >=1M/organization/exact`.
  - `p_error`: the probability that the link names the wrong organization.
- `organizations/link_error.parquet` has one row for each error cell: the links, the tokens, the
  token-weighted estimate, the minimum and the maximum `p_error`, the interval and the method. Two
  more rows give the fallback values `independent` and `unknown`.
- The view `tokens_with_current_organizations` of `organizations/dataset.duckdb` gives `p_error` on
  each token row that has a domain row.

## 2. Audited figures

Each figure is for the tokens or the projects of TOM.

| Quantity | Value |
|---|---|
| Error of `firm_based_on_domain` (share of the tokens of TOM) | 2.921%; 95% interval 1.465% to 4.904% (domain audit, 514 decided answers) |
| Share of tokens of company kinds, corrected | 34.993%; 95% interval 32.67% to 37.27% |
| Error of `firm_based_on_namespace` (`owns` rows with a wrong organization) | 0.0% of the projects; 95% interval 0.0% to 6.00% (namespace audit, 650 decided answers, 0 wrong) |
| Error of the fallback `independent` (a real domain with no row) | 15.643% (error model on TOM); the published `link_error` table gives 15.934% |

The audit found 14 domain rows that are wrong (0.037% of the tokens of TOM). The organization
database of 1.0.0 keeps these rows, and the error figure includes them.

## 3. Method

- The measure is a share of the tokens of TOM, not a share of domains.
- The samples are drawn with a probability proportional to the run tokens of each unit, within
  strata. The largest units are in the sample in full (certainty units).
- The estimator is the Hajek ratio estimator: the weighted wrong tokens divided by the weighted
  tokens of the decided answers.
- The open items of the tail were answered in a random order. A two-phase weight makes the answered
  items stand for all open items of their group.
- An open certainty unit is left out of the ratio. This assumes that it has the error rate of the
  answered units.

## 4. Use the error in an analysis

This query gives the expected share of wrong `firm_based_on_domain` values in a subset of the
tokens (here: one project). Run it in `duckdb -readonly organizations/dataset.duckdb`.

```sql
SELECT avg(coalesce(p_error,
                    CASE WHEN firm_based_on_domain = 'independent'
                         THEN (SELECT estimate FROM link_error
                               WHERE error_stratum LIKE 'fallback/independent%')
                         ELSE 0 END)) AS expected_error
FROM tokens_with_current_organizations
WHERE project = 'apache__syncope';
```

Limit: the public `organization_domains` table has no personal domains (ORGANIZATIONS.md,
section 2.3). Thus the query gives the fallback rate (15.934%) to all `independent` tokens. For the
tokens of personal domains this rate is too high: their token-weighted error is 0.376%.
