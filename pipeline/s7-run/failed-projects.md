# Failed projects of the census

State at 2026-10-10 20:30 UTC. One row per project that failed at least once, in any run.

- `failed-projects.tsv`: the machine table (attempts, steps, times, commits). Made by
  `failed_projects.py` from all ledgers (the S3 `live/`, `final/` and `backup-ledger/` copies, plus
  the local batch 1 ledger).
- This file: the reason of each failure, read from the pipeline logs, and the action.

To make the table again:

```
export AWS_PROFILE=ellianco-personal AWS_REGION=us-west-2 AWS_PAGER=""
T=$(mktemp -d)
aws s3 sync s3://cregit-census-905418043997-usw2/ $T/ --exclude '*' \
  --include '*/live/ledger.jsonl' --include '*/final/*/ledger.jsonl' --include '*/backup-ledger/*' --only-show-errors
python3 failed_projects.py $T ~/Projects/cregit-token-pipeline/.claude/worktrees/agent-a0a3254f563a6a4b5/ledger.jsonl > failed-projects.tsv
```

## Summary

| Outcome | Projects |
|---|---|
| Failed, no attempt runs now | 2 (discovery-artifact-manager, freeswitch) |
| Failed locally, moved to spot a (runs there now) | 1 (difftastic) |
| In progress after earlier failures | 1 (foxhound) |
| Finished after a retry | 18 |
| **Total** | **22** |

## Excluded (user decision 2026-10-11 ~19:00 UTC)

Both projects below are excluded from dataset version 1, with the reason in LIMITATIONS. No code
changes during the census.

- googleapis__discovery-artifact-manager: no in-scope source at the census commit (`--latest`).
- signalwire__freeswitch: blobExec crash on a commit with no committer line.

## Failed: open (now excluded, see above)

| Project | Run | Attempts | Reason (from the log) | Class | Action |
|---|---|---|---|---|---|
| googleapis__discovery-artifact-manager | batch6/a4 (spot a, 95cdc88) | 4 | The census pins the newest HEAD (`--latest`). HEAD `bb221e1` (2026-10-10) has 1,284 files and 0 files that match the C/C++/Java/Rust mask; the project deleted its Java code on 2026-10-07. The frame snapshot `9b6a724` (2026-10-05) has 559 matching files. Blame finds 0 files; step 10: "ERROR: no tokens processed, nothing to output"; exit 1. | data (no in-scope source at HEAD) | Waits for the user: exclude, or run at the snapshot. |
| signalwire__freeswitch | batch7/a3 (spot a, 1f17663) | 4 | blobExec step 2: `NullPointerException ... CommitBuilder.getCommitter() is null` at Walker.scala:866. A commit has no committer line. Same error on each attempt. | tool defect (cregit blobExec) | Waits for the user: fix blobExec or exclude. |

## Failed: open (new 2026-10-11)

| Project | Run | Attempts | Reason (from the ledger and a check at 21:25 UTC) | Class | Action |
|---|---|---|---|---|---|
| BRL-CAD__brlcad | batch15/b1 (spot b, 1f17663) | resolve | 2026-10-11 05:16 UTC: "cannot reach https://github.com/BRL-CAD/brlcad.git: git ls-remote exit 128". At 21:25 UTC `git ls-remote` and `GET /repos/BRL-CAD/brlcad` give "not found" (404), but the org repo list shows BRL-CAD/brlcad as public, not archived, not disabled, pushed 2026-10-11 00:20 UTC, size 597,359 KB. | GitHub serves the repo inconsistently (probably a state on GitHub's side) | 2026-10-12: the user reports that the repository is gone and wrote to its owners. Waits for their answer, else exclude. Found by the "Dataset Paper" session. |

| Project | Run | Attempts | Reason | Class | Action |
|---|---|---|---|---|---|
| gitlab.eclipse.org__eclipse__objectteams__objectteams | batch11/a4 (spot a, 57551d7 per the part DONE file) | 4 (resolve, within 2 s) | 2026-10-12 00:53 UTC: "cannot reach https://gitlab.eclipse.org/eclipse/objectteams/objectteams: git ls-remote exit 128". It resolves again at 01:22 UTC (HEAD 0f8327b4). | network (transient; Eclipse GitLab) | Rerun done on this machine (census-local-b, ctp ca113e3, cregit 57551d7): done on attempt 1 at 2026-10-12 03:12 UTC, 50.7 min, Parquet sha256 7e00cd9f…4ae7 (69,551,004 bytes). Output: `~/Projects/cregit-workspace/census-local-b/batch11/a4/done/gitlab.eclipse.org__eclipse__objectteams__objectteams/`. Not in S3. |

## Failed: open (new 2026-10-13)

| Project | Run | Attempts | Reason | Class | Action |
|---|---|---|---|---|---|
| kitao__pyxel | batch13/a2 (spot a, 1f17663) | 4 (resolve) | Last attempt 2026-10-12 08:07 UTC: `git ls-remote exit 128`. At 2026-10-13 14:53 UTC `git ls-remote` gives "Repository not found", `GET /repos/kitao/pyxel` gives 404, and `GET /users/kitao/repos` lists 0 public repos. | account suspended (GitHub) | 2026-10-13 ~21:05 UTC, the user reports the cause: GitHub suspended the owner's account for a time, after an attacker used it in a supply chain attack (a malicious GitHub Actions workflow `security-audit.yml` pushed to 27 of the owner's repositories). Not verified here. User decision 2026-10-13 ~21:15 UTC: keep it pending, and record it in LIMITATIONS (cregit-token-pipeline docs/LIMITATIONS.md, commit 6dde0fe). Without the account before the v1 freeze, v1 excludes it. If it returns: rerun at the frame commit 50f9bd77 (not `--latest`), so that no commit after the snapshot enters the dataset. Found by the "Dataset Paper" session. |
| gitlab.inria.fr__cedar__connectionlens | batch25/a4 (spot a, 57551d7) | 4 (pipeline, step 7 blame) | 2026-10-14 03:45-03:58 UTC. For 2 of 301 files (`core/src/main/java/fr/inria/cedar/connectionlens/extraction/FlairNERExtractor.java`, `.../EntityExtractor.java`) `git blame` in the cregit repository gives `fatal: unable to generate diff (dd8a6e6fbc6973eeb8708f8422a9ff796be25944)`, exit 128 (status 32768). cregit 57551d7 exits 1 on a git failure, so the project fails. Same on each attempt. Logs: `s3://…/batch25/a4/final/i-0b2bab8df4a93865d/ctp/state/gitlab.inria.fr__cedar__connectionlens/logs/`. | git limit hit by repository data (diagnosed 2026-10-14) | Diagnosis (local rerun, `~/Projects/cregit-workspace/diag-connectionlens/`): the repository holds binary blobs over 1 GiB (largest: a 3.6 GB log, `fr-ner-wikiner-0.4.pt` 1.33 GB). Original commit 5b6c497 moves the .pt file and changes FlairNERExtractor.java; with `-C`, `git blame` reads the moved 1.33 GB blob as a copy candidate, xdiff refuses buffers over 1 GiB, and git dies with "unable to generate diff (<parent>)" (parent dd8a6e6 = cregit image of cca7d6f) instead of skipping the candidate. The original repo passes at -C100 only because its changed lines score under 100; it fails the same way at -C1/-C20. Plain blame and -M work. Reach: 0 other projects in 6,324 local pipeline logs (2,871 projects). Fix tested: `diag-connectionlens/formatBlame-exit128-fallback.patch` (cregit formatBlame.pl: on git exit 128 of -C100, run plain blame and print PLAIN-BLAME, like the time limit); effect: 2 of 301 files get plain blame. User decision 2026-10-14 ~14:35 UTC: rerun with the fix. **Done** 2026-10-14 15:01:47 UTC in census-local-d (ctp ca113e3, cregit 23e4ccb = 57551d7 + plain blame after a -C100 git exit 128, branch fix/blame-exit128-fallback; libexpat gate 14eb5d72 OK): 8.5 min, Parquet sha256 72b1c29a…fe34 (3,725,592 bytes), 387,925 rows; 2 PLAIN-BLAME files (FlairNERExtractor.java, EntityExtractor.java). Output: `~/Projects/cregit-workspace/census-local-d/batch25/a4/done/`. Not in S3. |

## Failed locally, moved; in progress

| Project | Run | Attempts | Reason | Class | Now |
|---|---|---|---|---|---|
| Wilfred__difftastic | batch1-local | 2 | Attempt 1 (2026-10-09 01:55): rc=-15, the Claude Code session exit sent SIGTERM to the census. Attempt 2 (06:02): the OOM killer hit one process (16.4 GB RSS in the step 2 resume), rc=-13. | stop (not the project) + memory | Moved to batch1rest/a2 on spot a (95cdc88) on 2026-10-09 14:37; it runs there since 2026-10-10 12:48. |
| SAP__project-foxhound | batch1-local | 3 | rc=-15 three times: the planned stop of 2026-10-07 16:43, the session exit of 2026-10-09 01:55, the OOM-policy stop of 06:02. (The host reboot of 2026-10-08 21:07 has no ledger row.) | stop (not the project) | Runs locally since 2026-10-09 12:16, in blame. |

## Finished after a retry

| Project | Run | Failed attempts | Reason of the failure | Class |
|---|---|---|---|---|
| git.savannah.gnu.org__git__emacs | L22 | 2 (clone) | `RPC failed; HTTP 500` from https.git.savannah.gnu.org, "expected 'packfile'". Attempt 3 cloned. | server error (transient) |
| CleverRaven__Cataclysm-DDA | batch1-local | 1 (pipeline) | JGit `EOFException: Short read of block`: a truncated loose object in its cregit.git after the host crash of 2026-10-08 21:07. The workdir moved to `.superseded/20261009/`; the rerun from step 1 finished. | crash damage |
| devflowinc__trieve | batch1-local | 1 (join) | `No files found ... libgit2__libgit2-dataset.parquet`: the join reads every `joined` row of `ctp.duckdb`, and the restart of 2026-10-07 01:59 had removed that output. | operator stop (stale `joined` row) |
| reyamira__models | batch1-local | 1 (join) | Same as trieve (missing `devflowinc__trieve-dataset.parquet`). | operator stop (stale `joined` row) |
| mongodb__libmongosql | batch1-local | 1 (pipeline) | rc=-15: the planned STOP of 2026-10-07 01:58. | operator stop |
| torvalds__linux | batch1-local | 2 (pipeline) | rc=-15: the planned stops of 2026-10-07 00:47 and 16:43. | operator stop |
| wolfpld__tracy | batch1-local | 2 (pipeline) | rc=-15: the session exit (2026-10-09 01:55) and the OOM-policy stop (06:02). Finished with -C100 in 876 min. | stop (not the project) |
| gitlab.eclipse.org__eclipse__escet__escet | batch1rest/a1 | 1 (resolve) | `git ls-remote exit 128` (cannot reach gitlab.eclipse.org). | network (transient) |
| KolibriOS__kolibrios | batch7/b2 | 1 (resolve) | `git ls-remote exit 128` (cannot reach github.com). | network (transient) |
| lagadic__visp | batch2 | 3 (firm) | DuckDB `OutOfMemoryException` at the 8 GB limit of `firm_attribution.py` (7.4/7.4 GiB used). Attempt 4 passed. | memory (step limit) |
| MystenLabs__sui | batch9/b2 | 1 (firm) | DuckDB `OutOfMemoryException` at the 16 GB limit (14.9/14.9 GiB used). Attempt 2 passed. | memory (step limit) |
| net-snmp__net-snmp, CrispStrobe__CrispASR | batch4/p1 | 2 (pipeline) | Attempt 1 (2026-10-09 13:39): rc=-15/-13, batch 4 was stopped to split it into p1–p3. Attempt 2: blobExec `meta mismatch on 'command': stored='/data/cregit-ec2/...', requested='/b4p1/cregit-ec2/...'`, exit 3 in 0.7 s: the blob map kept the old cregit path. Attempt 3 finished. | operator stop + resume defect |
| apache__camel-spring-boot, projectacrn__acrn-libvirt, rism-digital__verovio | batch4/p2 | 2 (pipeline) | Same as p1 (logs of camel-spring-boot and acrn-libvirt read; verovio has the same times and exit code). | operator stop + resume defect |
| kovidgoyal__kitty, peercoin__peercoin | batch4/p3 | 2 (pipeline) | Same as p1 (peercoin log read; kitty has the same times and exit code). | operator stop + resume defect |

## Classes

- **Data or tool defect, open (2):** discovery-artifact-manager (no source at HEAD), freeswitch (blobExec NPE).
- **Stops that were not caused by the project (most rows):** planned stops, the session exit, the
  OOM-policy stop of batch 1, and the batch 4 split. Each stop counts as an attempt.
- **Transient (3):** two `ls-remote` failures and the Savannah HTTP 500.
- **Memory (3):** two DuckDB limits in the firm step, one OOM kill (difftastic).
- **Crash damage (1):** Cataclysm-DDA.
- **Resume defect (7):** the blob map stores the cregit command path; a move of the cregit copy makes
  the resume fail once (exit 3). The next attempt finished in all 7 cases.
