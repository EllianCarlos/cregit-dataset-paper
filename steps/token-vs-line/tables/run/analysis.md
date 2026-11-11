## Run state

| state | projects |
|---|---|
| done | 250 |

Projects in the per-project table: 250. Clone and copy failures (failures.tsv rows): 0.

## Token level: All projects with a value

| share of tokens with | projects | project mean % (95% interval) | token-weighted % (95% bootstrap interval) | project median % |
|---|---|---|---|---|
| another author, plain line blame | 249 | 19.30 (17.32 to 21.27) | 22.19 (17.19 to 26.81) | 18.39 |
| another author, line blame -w | 249 | 16.05 (14.48 to 17.62) | 19.11 (14.26 to 23.76) | 15.40 |
| another author, line blame -w -M -C | 249 | 15.53 (13.99 to 17.06) | 17.89 (13.39 to 22.31) | 14.64 |
| another commit, plain | 249 | 42.27 (40.18 to 44.35) | 34.40 (28.42 to 40.48) | 43.58 |
| another commit, -w -M -C | 249 | 36.46 (34.58 to 38.34) | 28.78 (23.42 to 34.30) | 38.17 |
| another organization, plain | 249 | 10.54 (9.12 to 11.96) | 11.62 (7.46 to 15.93) | 7.10 |
| another organization, -w -M -C | 249 | 8.51 (7.43 to 9.59) | 9.42 (5.85 to 13.19) | 5.06 |

## Token level: Without projects with more than 10% of the tokens cut

| share of tokens with | projects | project mean % (95% interval) | token-weighted % (95% bootstrap interval) | project median % |
|---|---|---|---|---|
| another author, plain line blame | 248 | 19.22 (17.24 to 21.20) | 21.09 (16.45 to 25.59) | 18.02 |
| another author, line blame -w | 248 | 15.97 (14.40 to 17.55) | 18.07 (13.47 to 22.69) | 15.10 |
| another author, line blame -w -M -C | 244 | 15.42 (13.88 to 16.95) | 15.61 (11.97 to 19.42) | 14.54 |
| another commit, plain | 248 | 42.23 (40.14 to 44.33) | 33.31 (27.52 to 39.44) | 43.56 |
| another commit, -w -M -C | 244 | 36.23 (34.33 to 38.14) | 25.95 (21.36 to 31.06) | 38.00 |
| another organization, plain | 248 | 10.47 (9.05 to 11.89) | 10.40 (6.94 to 14.24) | 7.05 |
| another organization, -w -M -C | 244 | 8.44 (7.36 to 9.51) | 7.54 (4.88 to 10.47) | 5.18 |

## Tokens cut or not blamed

| blame | tokens of the sample without this blame | share of all tokens % | projects with a cut above 10% |
|---|---|---|---|
| plain | 34,734,492 | 4.14 | llvm__llvm-project, gitlab.inria.fr__cedar__connectionlens |
| w | 34,734,492 | 4.14 | llvm__llvm-project, gitlab.inria.fr__cedar__connectionlens |
| wmc | 48,850,633 | 5.83 | llvm__llvm-project, NextAlone__Nnngram, wireshark__wireshark, Squalr__Squally, eclipse-milo__milo, gitlab.inria.fr__cedar__connectionlens |

All tokens of the sample: 838,348,903 in 250 projects. Projects with a plain-blame value in the mean: see the token tables.

Projects with more than 10% of the tokens in files without a plain line blame: 2.

| project | language | draw band | tokens | files | files cut | tokens without plain blame % | tokens in files over any limit or cap % |
|---|---|---|---|---|---|---|---|
| gitlab.inria.fr__cedar__connectionlens | Java | b | 369,257 | 301 | 301 | 100.00 | 100.00 |
| llvm__llvm-project | C++ | d | 85,570,861 | 72966 | 69369 | 40.16 | 40.48 |
| NextAlone__Nnngram | Java | b | 17,006,436 | 6847 | 12 | 0.00 | 17.79 |
| wireshark__wireshark | C | d | 35,142,218 | 4336 | 11 | 0.00 | 20.42 |
| Squalr__Squally | C++ | b | 4,004,403 | 6203 | 1 | 0.00 | 26.53 |
| eclipse-milo__milo | Java | a | 4,997,991 | 3256 | 1 | 0.00 | 19.18 |

Projects with no token covered by the plain blame (no value): 1 (gitlab.inria.fr__cedar__connectionlens).

| share of tokens without plain blame | projects |
|---|---|
| no cut | 226 |
| 0 to 1% | 22 |
| 1 to 10% | 0 |
| 10 to 50% | 1 |
| more than 50% | 1 |

Files over a limit (limits.tsv), by blame: cap 69663, wmc 36. Projects with at least one file over a limit: 7.

| project | files over the plain limit | over the -w limit | over the -w -M -C limit | cut at the run cap |
|---|---|---|---|---|
| llvm__llvm-project | 0 | 0 | 7 | 69362 |
| gitlab.inria.fr__cedar__connectionlens | 0 | 0 | 0 | 301 |
| NextAlone__Nnngram | 0 | 0 | 12 | 0 |
| wireshark__wireshark | 0 | 0 | 11 | 0 |
| SakuraEngine__SakuraEngine | 0 | 0 | 4 | 0 |
| Squalr__Squally | 0 | 0 | 1 | 0 |
| eclipse-milo__milo | 0 | 0 | 1 | 0 |

## Other levels (project means)

| level | all projects with a value | without projects with a cut above 10% |
|---|---|---|
| code lines with tokens from 2 or more authors, % | 13.39 (12.06 to 14.72), n 249 | 13.32 (12.00 to 14.65), n 248 |
| files with the same top author (tokens against plain lines), % | 89.08 (87.58 to 90.58), n 249 | 89.19 (87.70 to 90.68), n 248 |
| files with the same top-3 author set, plain, % | 67.11 (64.28 to 69.95), n 249 | 67.23 (64.39 to 70.06), n 248 |
| files with the same top author, -w -M -C, % | 92.50 (91.61 to 93.39), n 249 | 92.60 (91.72 to 93.48), n 248 |
| project: author share TVD, plain, pp | 10.56 (9.19 to 11.92), n 249 | 10.47 (9.12 to 11.83), n 248 |
| project: author share TVD, -w -M -C, pp | 7.42 (6.48 to 8.35), n 249 | 7.34 (6.41 to 8.27), n 248 |
| project: author share Spearman, plain | 0.91 (0.90 to 0.92), n 232 | 0.91 (0.90 to 0.92), n 231 |
| project: same top author, plain, share of projects | 87.15 (83.02 to 91.27), n 249 | 87.50 (83.42 to 91.58), n 248 |
| project: organization share TVD, plain, pp | 5.27 (4.29 to 6.26), n 249 | 5.25 (4.26 to 6.23), n 248 |
| project: organization share Spearman, plain | 0.95 (0.94 to 0.96), n 191 | 0.95 (0.94 to 0.96), n 190 |
| project: same top organization, share of projects | 91.16 (87.67 to 94.66), n 249 | 91.13 (87.62 to 94.64), n 248 |

## Causes of tokens with another author (plain line blame)

| cause | tokens | % of tokens with another author | % of them in generated files |
|---|---|---|---|
| whitespace | 26,304,089 | 14.8 | 3.3 |
| move_copy_line | 17,873,342 | 10.0 | 7.6 |
| part_line | 94,109,768 | 52.8 | 6.3 |
| layout | 6,318,432 | 3.5 | 3.1 |
| other | 33,713,027 | 18.9 | 3.3 |

(The token plain blame was not run: a cause `move_copy_token` does not exist in this run; its tokens fall into the later rules.)

## Identity residual

| value | number |
|---|---|
| blamed lines (plain) | 165,921,412 |
| lines whose commit TOM does not credit | 1,477,293 |
| of them identified by the e-mail map | 1,459,921 |
| of them with no TOM identity (own id) | 17,372 (0.0105%) |
| largest project share of lines with no TOM identity % | 2.159 |
| TOM-credited commits with no personid | 1 |
| commits whose rows have more than one personid | 0 |
| e-mail addresses with more than one personid | 0 |

## Project mean of tokens with another author (plain), by language and draw band

| language | projects | mean % | median % | standard deviation |
|---|---|---|---|---|
| C | 68 | 19.36 | 19.18 | 16.87 |
| C++ | 66 | 18.62 | 15.07 | 15.97 |
| Java | 63 | 22.31 | 25.05 | 16.72 |
| Rust | 52 | 16.43 | 16.72 | 14.02 |

| commit band | projects | mean % | median % | standard deviation |
|---|---|---|---|---|
| a | 76 | 14.61 | 8.65 | 14.67 |
| a? | 3 | 11.69 | 8.00 | 13.91 |
| b | 129 | 18.75 | 16.17 | 15.47 |
| c | 31 | 30.19 | 26.48 | 17.06 |
| d | 10 | 30.49 | 32.81 | 12.07 |

## Checks on the main value

- Bootstrap 95% interval of the project mean (10,000 draws): 17.30 to 21.30; the t interval with the finite population correction: 17.32 to 21.27.
- Without the correction the half-width is 2.01 pp; with it 1.98 pp.
- The 5 projects with most blamed tokens hold 35.0% of the blamed tokens; the largest holds 8.3%.
| project | blamed tokens | share of blamed tokens % | tokens with another author % |
|---|---|---|---|
| OpenNuvoton__NUC970_Linux_Kernel | 66,553,565 | 8.3 | 23.88 |
| adoptium__jdk26u | 57,371,702 | 7.1 | 24.25 |
| TencentCloud__tencentcloud-sdk-cpp | 57,109,264 | 7.1 | 38.71 |
| llvm__llvm-project | 51,205,847 | 6.4 | 38.33 |
| Rust-GCC__gccrs | 49,296,280 | 6.1 | 17.57 |

- Quartiles of the project values: 4.39, 18.39, 29.97; minimum 0.00, maximum 79.22; standard deviation 16.07 (the planning value was 16.26).
- Projects with a value above 50%: 11; below 5%: 66.

## Costs of the run (blame CPU)

| blame | CPU hours |
|---|---|
| plain | 35.7 |
| w | 36.1 |
| wmc | 714.0 |

