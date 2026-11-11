## Run state

| state | projects |
|---|---|
| done | 19 |

Projects in the per-project table: 19. Clone and copy failures (failures.tsv rows): 0.

## Token level: All projects with a value

| share of tokens with | projects | project mean % (95% interval) | token-weighted % (95% bootstrap interval) | project median % |
|---|---|---|---|---|
| another author, plain line blame | 19 | 21.92 (14.09 to 29.75) | 22.11 (10.66 to 35.47) | 19.78 |
| another author, line blame -w | 19 | 19.28 (13.19 to 25.37) | 19.72 (8.56 to 32.30) | 19.11 |
| another author, line blame -w -M -C | 19 | 17.27 (11.76 to 22.78) | 15.93 (7.63 to 26.73) | 17.96 |
| another commit, plain | 19 | 47.66 (41.71 to 53.62) | 34.96 (23.42 to 48.98) | 49.04 |
| another commit, -w -M -C | 19 | 41.96 (36.31 to 47.62) | 27.43 (17.94 to 41.15) | 43.31 |
| another organization, plain | 19 | 13.14 (6.99 to 19.30) | 9.35 (2.65 to 17.22) | 9.93 |
| another organization, -w -M -C | 19 | 10.31 (5.78 to 14.85) | 6.88 (1.95 to 13.46) | 8.33 |

## Token level: Without projects with more than 10% of the tokens cut

| share of tokens with | projects | project mean % (95% interval) | token-weighted % (95% bootstrap interval) | project median % |
|---|---|---|---|---|
| another author, plain line blame | 19 | 21.92 (14.09 to 29.75) | 22.11 (10.66 to 35.47) | 19.78 |
| another author, line blame -w | 19 | 19.28 (13.19 to 25.37) | 19.72 (8.56 to 32.30) | 19.11 |
| another author, line blame -w -M -C | 19 | 17.27 (11.76 to 22.78) | 15.93 (7.63 to 26.73) | 17.96 |
| another commit, plain | 19 | 47.66 (41.71 to 53.62) | 34.96 (23.42 to 48.98) | 49.04 |
| another commit, -w -M -C | 19 | 41.96 (36.31 to 47.62) | 27.43 (17.94 to 41.15) | 43.31 |
| another organization, plain | 19 | 13.14 (6.99 to 19.30) | 9.35 (2.65 to 17.22) | 9.93 |
| another organization, -w -M -C | 19 | 10.31 (5.78 to 14.85) | 6.88 (1.95 to 13.46) | 8.33 |

## Tokens cut or not blamed

| blame | tokens of the sample without this blame | share of all tokens % | projects with a cut above 10% |
|---|---|---|---|
| plain | 0 | 0.00 | none |
| w | 0 | 0.00 | none |
| wmc | 0 | 0.00 | none |

All tokens of the sample: 12,303,576 in 19 projects. Projects with a plain-blame value in the mean: see the token tables.

Projects with more than 10% of the tokens in files without a plain line blame: 0.

| project | language | draw band | tokens | files | files cut | tokens without plain blame % | tokens in files over any limit or cap % |
|---|---|---|---|---|---|---|---|

Projects with no token covered by the plain blame (no value): 0 (none).

| share of tokens without plain blame | projects |
|---|---|
| no cut | 19 |
| 0 to 1% | 0 |
| 1 to 10% | 0 |
| 10 to 50% | 0 |
| more than 50% | 0 |

Files over a limit (limits.tsv), by blame: . Projects with at least one file over a limit: 0.

| project | files over the plain limit | over the -w limit | over the -w -M -C limit | cut at the run cap |
|---|---|---|---|---|

## Other levels (project means)

| level | all projects with a value | without projects with a cut above 10% |
|---|---|---|
| code lines with tokens from 2 or more authors, % | 17.22 (12.31 to 22.12), n 19 | 17.22 (12.31 to 22.12), n 19 |
| files with the same top author (tokens against plain lines), % | 83.85 (75.71 to 91.99), n 19 | 83.85 (75.71 to 91.99), n 19 |
| files with the same top-3 author set, plain, % | 58.74 (46.23 to 71.24), n 19 | 58.74 (46.23 to 71.24), n 19 |
| files with the same top author, -w -M -C, % | 90.75 (86.49 to 95.01), n 19 | 90.75 (86.49 to 95.01), n 19 |
| project: author share TVD, plain, pp | 13.57 (8.10 to 19.04), n 19 | 13.57 (8.10 to 19.04), n 19 |
| project: author share TVD, -w -M -C, pp | 8.42 (5.76 to 11.07), n 19 | 8.42 (5.76 to 11.07), n 19 |
| project: author share Spearman, plain | 0.87 (0.83 to 0.91), n 19 | 0.87 (0.83 to 0.91), n 19 |
| project: same top author, plain, share of projects | 73.68 (51.91 to 95.46), n 19 | 73.68 (51.91 to 95.46), n 19 |
| project: organization share TVD, plain, pp | 6.91 (3.24 to 10.57), n 19 | 6.91 (3.24 to 10.57), n 19 |
| project: organization share Spearman, plain | 0.92 (0.85 to 0.98), n 19 | 0.92 (0.85 to 0.98), n 19 |
| project: same top organization, share of projects | 94.74 (83.69 to 100.00), n 19 | 94.74 (83.69 to 100.00), n 19 |

## Causes of tokens with another author (plain line blame)

| cause | tokens | % of tokens with another author | % of them in generated files |
|---|---|---|---|
| whitespace | 330,390 | 12.1 | 21.8 |
| move_copy_line | 677,094 | 24.9 | 81.2 |
| part_line | 1,119,489 | 41.2 | 49.1 |
| layout | 39,930 | 1.5 | 33.9 |
| other | 553,298 | 20.3 | 68.0 |

(The token plain blame was not run: a cause `move_copy_token` does not exist in this run; its tokens fall into the later rules.)

## Identity residual

| value | number |
|---|---|
| blamed lines (plain) | 2,552,464 |
| lines whose commit TOM does not credit | 11,518 |
| of them identified by the e-mail map | 11,476 |
| of them with no TOM identity (own id) | 42 (0.0016%) |
| largest project share of lines with no TOM identity % | 0.035 |
| TOM-credited commits with no personid | 0 |
| commits whose rows have more than one personid | 0 |
| e-mail addresses with more than one personid | 0 |

## Project mean of tokens with another author (plain), by language and draw band

| language | projects | mean % | median % | standard deviation |
|---|---|---|---|---|
| ? | 19 | 21.92 | 19.78 | 16.26 |

| commit band | projects | mean % | median % | standard deviation |
|---|---|---|---|---|
| ? | 19 | 21.92 | 19.78 | 16.26 |

## Checks on the main value

- Bootstrap 95% interval of the project mean (10,000 draws): 15.20 to 29.41; the t interval with the finite population correction: 14.09 to 29.75.
- Without the correction the half-width is 7.83 pp; with it 7.83 pp.
- The 5 projects with most blamed tokens hold 84.4% of the blamed tokens; the largest holds 37.7%.
| project | blamed tokens | share of blamed tokens % | tokens with another author % |
|---|---|---|---|
| DK22Pac__plugin-sdk | 4,635,679 | 37.7 | 8.35 |
| Adyen__adyen-java-api-library | 3,015,188 | 24.5 | 40.58 |
| github__copilot-sdk | 1,700,209 | 13.8 | 34.38 |
| influxdata__influxdb-client-java | 565,276 | 4.6 | 10.22 |
| swoole__phpx | 464,136 | 3.8 | 3.55 |

- Quartiles of the project values: 10.22, 19.78, 32.81; minimum 1.13, maximum 57.84; standard deviation 16.26 (the planning value was 16.26).
- Projects with a value above 50%: 2; below 5%: 2.

## Costs of the run (blame CPU)

| blame | CPU hours |
|---|---|
| plain | 0.1 |
| w | 0.1 |
| wmc | 1.1 |

