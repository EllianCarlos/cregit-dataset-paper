# Language rules at the pinned run commit

Date: 2026-11-06. Everything here was done locally. Nothing was committed.

## Input set

There are 10,763 rows, the same number as the selection frame:

- 10,754 rows from the release manifest. The pinned commit is `run_commit`.
- 9 frame rows with no file (LIMITATIONS.md section 1). The pinned commit is the `pinned_sha` of the last run attempt in the run ledgers (`release-work/ledgers-20261028`). For `kitao__pyxel` the ledger's pinned commit is the frame commit, because the repository was gone and nothing was checked out. For `googleapis__discovery-artifact-manager` the last of its three runs pinned `bb221e1f`; an earlier run pinned `b5c9fd40`.

By layer:

- v1 (5,000+ commits): 3,548 rows. These are the 3,497 rows of `frame.v4.csv` plus 51 GitLab supplement rows (`supplement25.gitlab.csv`, `supplement26.gitlab.csv`). 3,545 have a file and 3 do not.
- x1k (1,000-4,999 commits): 7,215 rows. 7,209 have a file and 6 do not.

The pinned commit differs from the frame commit for 6,699 rows: the 6,691 manifest rows plus 8 of the 9 rows with no file.

## Method

The S3 code is used unchanged:

- `measure_trees.measure` makes one GitHub tree call at the pinned commit.
- For truncated trees and for other hosts, `measure_clones.measure` fetches the one commit with depth 1 and runs `git ls-tree`.

An S3 record was reused only when its commit is the pinned commit and the record is complete, which means a tree with HTTP 200 that is not truncated, or a clone with status ok. Reused records:

- 3,827 tree records.
- 191 clone records.

The 51 GitLab supplement rows have no S3 record with bytes by extension (`measure_dp.py` kept only totals), so they were fetched again.

New measures:

- 6,545 GitHub tree calls stored.
- 200 single-commit fetches: 108 truncated GitHub trees and 92 rows from other hosts.
- A retry pass for 3 rows:
  - `git.savannah.gnu.org__git__emacs`: the host returned HTTP 500 the first time. The retry worked.
  - `git.busybox.net__busybox`: the host refuses a fetch by SHA. The default branch was fetched with growing depth until the pinned commit was present. The depth used was not recorded; the cap was 4,096.
  - `git.libreoffice.org__libvisio`: the host answers 403 to any fetch. The same commit SHA was fetched from the LibreOffice GitHub mirror.

Rules (the code is in `pinned.py`; the rules and the extension-to-language map come from `../whatif.py`):

- share = non-vendored tokenizable bytes / code bytes. This is the DP3 measure.
- Two variants:
  - linguist: Linguist programming extensions only.
  - with_ts: also counts `.ts`, `.tsx`, `.mts`, `.cts` and `.mm`.
- Token rows are the manifest `rows` column. The share of token rows is taken over the measured projects.

## Not measured (3)

These GitHub repositories return 404, both for the repository and for the commit:

- `dust-tt__dust` (v1, 1,704,444 token rows)
- `abgox__PSCompletions` (x1k, 185,386 token rows)
- `milisp__codexia` (x1k, 176,180 token rows)

That leaves 10,760 measured: 3,547 v1 and 7,213 x1k.

## Results at the pinned commit

### Linguist only

| Rule | v1 kept / measured | x1k kept / measured | all kept / measured | share of token rows (v1 / x1k / all) |
|---|---|---|---|---|
| share >= 5% (DP3) | 3,545 / 3,547 | 7,195 / 7,213 | 10,740 / 10,760 | 100.0% / 100.0% / 100.0% |
| share >= 30% | 3,012 | 6,075 | 9,087 | 91.8% / 91.8% / 91.8% |
| share >= 50% | 2,677 | 5,471 | 8,148 | 85.4% / 86.4% / 85.6% |
| largest language is C, C++, Java or Rust | 2,812 | 5,744 | 8,556 | 89.8% / 93.3% / 90.7% |
| target group > any other single language | 2,887 | 5,823 | 8,710 | 94.7% / 95.1% / 94.8% |

### WITH_TS

| Rule | v1 kept / measured | x1k kept / measured | all kept / measured | share of token rows (v1 / x1k / all) |
|---|---|---|---|---|
| share >= 5% (DP3) | 3,478 / 3,547 | 7,064 / 7,213 | 10,542 / 10,760 | 100.0% / 99.9% / 100.0% |
| share >= 30% | 2,906 | 5,868 | 8,774 | 91.3% / 91.0% / 91.2% |
| share >= 50% | 2,546 | 5,210 | 7,756 | 84.1% / 84.8% / 84.3% |
| largest language is C, C++, Java or Rust | 2,673 | 5,483 | 8,156 | 88.7% / 92.2% / 89.7% |
| target group > any other single language | 2,762 | 5,578 | 8,340 | 93.8% / 94.1% / 93.9% |

Token rows of the measured projects:

- v1: 23,699,921,206
- x1k: 8,933,187,402
- all: 32,633,108,608

All manifest rows together have 32,635,174,618 token rows. The token-row counts kept by each rule are in `results.txt`.

## Share below 5% at the pinned commit

These are the projects DP3 would drop now. The lists are in `below5.linguist.tsv` and `below5.with_ts.tsv`.

Linguist only: 20 projects, 2 v1 and 18 x1k.

- 7 are rows with no file. All 7 have share 0 at the pinned commit:
  - `googleapis__discovery-artifact-manager`
  - `vllm-project__semantic-router`
  - `visgl__loaders.gl`
  - `notnotype__neuro-book`
  - `pur1fying__blue_archive_auto_script`
  - `greta-dev__greta`
  - `Librelancer__Librelancer` (only 4 files at the pinned commit, with no code bytes)
- 13 are released projects with 1,645,856 token rows in total:
  - `riclolsen__json-scada`
  - `ciribob__DCS-SimpleRadioStandalone`
  - `Nain57__Smart-AutoClicker`
  - `KDE__kdeconnect-android`
  - `aws-samples__appmod-blueprints`
  - `CherryHQ__cherry-studio-app`
  - `wyskoj__midis2jam2`
  - `edrlab__thorium-reader`
  - `home-assistant__addons`
  - `vlang__vinix`
  - `hyperledger-cacti__cacti`
  - `AutoDarkMode__Windows-Auto-Night-Mode`
  - `samuelclay__NewsBlur` (v1)

WITH_TS: 218 projects, 69 v1 and 149 x1k. 7 are rows with no file and 211 are released projects with 13,685,795 token rows.

## Frame commit vs pinned commit

Only projects measured at both commits are compared. The 51 GitLab supplement rows have no language split at the frame commit, so they are compared only for the share rules in the Linguist variant. The table gives the number of projects that change result at each rule, as "kept at frame, dropped at pinned" + "dropped at frame, kept at pinned".

| Variant | Rule | v1 | x1k | all |
|---|---|---|---|---|
| linguist | share >= 5% | 2 + 0 | 18 + 0 | 20 + 0 (of 10,760) |
| linguist | share >= 30% | 5 + 2 | 13 + 12 | 18 + 14 |
| linguist | share >= 50% | 4 + 1 | 12 + 15 | 16 + 16 |
| linguist | largest language is a target | 2 + 1 | 10 + 9 | 12 + 10 (of 10,709) |
| linguist | target group > any other | 2 + 0 | 14 + 11 | 16 + 11 |
| with_ts | share >= 5% | 2 + 1 | 15 + 3 | 17 + 4 (of 10,709) |
| with_ts | share >= 30% | 6 + 2 | 15 + 12 | 21 + 14 |
| with_ts | share >= 50% | 3 + 2 | 16 + 18 | 19 + 20 |
| with_ts | largest language is a target | 2 + 1 | 11 + 11 | 13 + 12 |
| with_ts | target group > any other | 2 + 0 | 15 + 14 | 17 + 14 |

Check: at the frame commit, the script gives the same numbers as `../result.txt` and `../result.with-ts.txt`. For example, "largest language is a target" keeps 8,511 of 10,703 in the Linguist variant, and DP3 under WITH_TS keeps 10,499 of 10,703.

## Files

- `pinned.py`: the script, with the steps `inputs`, `measure`, `retry` and `whatif`.
- `inputs.tsv`: the 10,763 input rows.
- `measure.jsonl`: one line for each project, plus 4 retry lines; the last line of a project counts. It holds sizes by extension only, with no paths and no person data.
- `projects.tsv`: one row for each project. Columns: the pinned commit, the share and the largest language in both variants, each rule result, and the share at the frame commit.
- `results.txt`: the full tables.
- `below5.*.tsv`: the projects with share below 5% at the pinned commit.
- `run.log`: the measure log.
