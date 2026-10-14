# Stage S3: how each repository is measured

This document explains the S3 tree pass: which pool rows it measures, how it
pins each measurement to one commit, what it counts, and how the run can be
checked and repeated. The sources of each input are in `SOURCES.md`. The plan
is `../DATASET-RESOURCING-PLAN.md`.

Status on 2026-10-06 03:30 UTC: the pass runs; 9,457 of 33,699 rows are done.

## 1. From the sources to the measured rows

Each box gives the count on 2026-10-06. No step drops a row without a record.

```mermaid
flowchart TD
    S1["S1 GitHub search<br/>all languages, stars > 400,<br/>not archived, not a fork,<br/>pushed on or after 2025-04-03<br/><b>80,990 repositories</b>"]
    OLD["Old pool<br/>candidates.csv<br/>24,405 rows"]
    ROS["30 rosters<br/>and home page lookups"]
    SLUGS["S2 input slugs<br/><b>36,088</b>"]
    LOOK["S2 lookup<br/>GraphQL, then REST<br/>for renamed repositories"]
    UNRES["Not found: <b>528</b><br/>unresolved.csv<br/>511 HTTP 404, 15 HTTP 451,<br/>2 HTTP 403"]
    ORGS["GitHub organization,<br/>not a repository: <b>780</b><br/>roster_orgs.csv<br/>(evidence for S5)"]
    POOL["S2 pool<br/>pool.csv<br/><b>106,985 rows</b>"]
    OTHER["Other hosts: <b>2,377</b><br/>KDE, Eclipse GitLab,<br/>freedesktop, Apache SVN, ...<br/>(shallow clone, later)"]
    GH["GitHub rows: <b>104,608</b>"]
    NOHEAD["No HEAD commit: <b>134</b><br/>(S4 reason, later)"]
    NOLANG["No C, C++, Java or Rust<br/>in the Linguist list: <b>70,775</b><br/>(S4 reason, later)"]
    RECHECK["List cut at 20 languages<br/>and no target language: <b>14</b><br/>re-checked with the full list"]
    BACK["4 have target bytes<br/>languages_recheck.jsonl"]
    MEASURE["S3 tree pass<br/><b>33,699 + 4 rows</b>"]

    S1 --> POOL
    OLD --> SLUGS
    ROS --> SLUGS
    ROS --> ORGS
    ROS -- "repository on another host" --> POOL
    SLUGS --> LOOK
    LOOK -- "found: 35,560<br/>(3,470 under a new name)" --> POOL
    LOOK --> UNRES
    POOL --> OTHER
    POOL --> GH
    GH --> NOHEAD
    GH --> NOLANG
    GH -- "target language in the list" --> MEASURE
    NOLANG -.-> RECHECK
    RECHECK --> BACK
    BACK --> MEASURE
```

The search and the looked-up slugs overlap. `build_pool.py` merges them by the
GitHub `databaseId`, so a repository that comes from several sources is one
row. The column `origins` lists all its sources.

## 2. The choice of rows: a pre-filter, not the measurement

The column `languages` of `pool.csv` holds the Linguist byte counts that
GitHub computes for each repository. S1 and S2 read them with the GraphQL field
`languages(first: 20, orderBy: {field: SIZE, direction: DESC})`.

A GitHub row goes to the tree pass if all three conditions are true:

1. it has a HEAD commit (`head_oid`);
2. its language list contains C, C++, Java or Rust, or
   `languages_recheck.jsonl` finds target bytes for it;
3. its host is `github.com`.

Linguist does not count vendored, generated or documentation files. So this
step only removes the repositories that have no target code at all. The
exact share comes from the tree pass.

**The cut at 20 languages.** The list holds only the 20 largest languages.
1,059 rows list 20 languages. 14 of them list no target language, so a target
language can be below the cut. `recheck_languages.py` reads the full list
(`first: 100`) for these 14 rows. 4 of them have target bytes (103 to 4,052
bytes): `aiskillstore/marketplace`, `radian-software/apheleia`,
`oxsecurity/megalinter`, `openreplay/openreplay`. They are measured like all
other rows.

## 3. One repository, step by step

```mermaid
sequenceDiagram
    participant P as pool.csv row
    participant M as measure_trees.py
    participant G as GitHub REST API
    participant O as trees.jsonl

    P->>M: name_with_owner, head_oid (commit SHA read by S1 or S2)
    M->>G: GET /repos/{owner}/{repo}/git/trees/{head_oid}?recursive=1
    G-->>M: every file of that commit: path, type, size<br/>truncated = true or false
    Note over M: for each blob:<br/>add its size to the total,<br/>to its extension,<br/>to "vendored" if the path matches the vendor rule,<br/>to "tokenizable" if the path matches the universal mask
    M->>O: one JSON row, with fetched_at, then flush
```

**Why the commit is fixed.** S1 and S2 recorded `defaultBranchRef.target.oid`:
the SHA of the commit at the HEAD of the default branch when the row was
fetched. The tree call names that SHA, not `HEAD`. A commit cannot change, so
the same call gives the same tree on a later day. A push to the repository
after the fetch does not change the measurement.

Limits:

- The commits are not from one moment. They were read between 2026-10-05
  20:47 and 2026-10-06 02:03 UTC. Each pool row records its own `fetched_at`.
- If an owner force-pushes and GitHub deletes the old commit, the call fails.
  The row then records the HTTP status and has no counts.
- GitHub truncates a tree with more than 100,000 entries or more than 7 MB.
  The row then has `truncated: true`, and its counts cover only part of the
  tree. For such a row, the Linguist bytes are the fallback.

**What one row of `trees.jsonl` holds.**

| Field | Meaning |
| --- | --- |
| `name_with_owner`, `head_oid`, `tree_sha` | the repository, the measured commit and its root tree |
| `status` | the HTTP status of the tree call |
| `truncated` | true if GitHub cut the tree |
| `total_bytes`, `n_blobs` | all files of the commit |
| `by_ext` | bytes for each file extension |
| `vendor_by_ext` | bytes for each extension, only in vendored paths (`vendor/`, `third_party/`, `external/`, `deps/`, ...) |
| `tok_bytes`, `n_tok` | the files that the universal mask selects: the files that cregit can tokenize |
| `tok_vendor_bytes` | the part of `tok_bytes` in vendored paths |
| `fetched_at` | the time of the call (UTC) |

**From these counts to the share rule (stage S4).** The code bytes are the
bytes of the extensions that Linguist gives only to languages of type
`programming` (`prog_exts.py`, Linguist commit `538da05f`), plus the mask
extensions. S4 computes them from `by_ext`. The rule is: `tok_bytes` is at
least 5% of the code bytes.

## 4. The mask and its version

The script imports `UNIVERSAL_MASK` from
`$CREGIT_PROJECTS/cregit-token-pipeline/file_mask.py`, the same mask that the
pipeline uses. At start, `run.log` records:

- the SHA-256 of the mask string: `665c23c0…`;
- the last commit that changed `file_mask.py`: `91d6ccab`.

Before the start, the file had no uncommitted change and was the same as in
`91d6ccab`. The script reads the mask once, at start. An edit to the file
during the run does not change the run, and the log does not show the edit.

## 5. Quota, stops and the resume

- GitHub allows 5,000 REST calls per hour. When the quota is used up, the
  script sleeps until the reset, and `run.log` says so.
- After a server error (HTTP 500, 502, 503, 504) or a network error, the
  script waits 30 seconds and tries again, up to 10 times.
- An HTTP 403 with quota left and no `Retry-After` header is the status of the
  repository (for example, GitHub blocks it). The script records it and does
  not try again.
- The script writes each row and flushes it at once. At start, it skips the
  rows that are already in `trees.jsonl`. So after a stop, run it again:

```sh
cd dataset-selection/s3-measure
python3 measure_trees.py
```

The 4 rows of `languages_recheck.jsonl` were found after the start. The next
run of `measure_trees.py` measures them.

## 6. How to check the result

When the pass ends:

1. `wc -l trees.jsonl` gives 33,703 (33,699 + 4).
2. Count the rows by `status`. Each row that is not 200 needs its reason in S4.
3. Count the rows with `truncated: true`. Each one uses the Linguist fallback.
4. Compress the file to `trees.jsonl.xz`, write its SHA-256, and commit both.

To repeat one measurement, call the tree API with the `head_oid` of the row.
The result is the same, if GitHub still has the commit.

## 7. What S3 does not do yet

- The 2,377 rows on other hosts are measured later, by a shallow clone at the
  snapshot date.
- The commit counts are read later, only for the rows that pass the share
  rule.
- Stage S4 is not written yet. It gives each row that leaves a reason in
  `excluded_because`: "no HEAD commit", "no C, C++, Java or Rust bytes in
  Linguist", the HTTP status of a failed tree call, or the share rule.
