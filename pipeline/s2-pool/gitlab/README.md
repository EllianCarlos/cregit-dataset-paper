# GitLab pool extension: measurement (2026-10-13/14)

This folder holds a read-only measurement. It adds nothing to `pool.csv`, to the frame or to any manifest, and nothing goes to the census.

## User decisions (2026-10-13 ~22:15 UTC, verbatim answers)

1. Scope: **"Also gitlab.com search"**. That is: (a) all public, non-fork projects in group namespaces of the GitLab instances that are already in our rosters, pool or v1 frame, and the gitlab.com groups that roster rows name; plus (b) a gitlab.com-wide search with stated criteria.
2. Duplicates: **"Skip the GitLab copy (Recommended)"**. A GitLab project that shares history with a row already in the pool is not added. Its URL is recorded as a fact (cluster table).
3. Release: **"Measure first, then decide (Recommended)"**. Counts only.

## Fetch record

| Step | Endpoint (GitLab API v4 unless stated) | Parameters | Time (UTC) |
|---|---|---|---|
| Host probe | `GET /api/v4/projects?per_page=1` on each of the 68 non-GitHub hosts of the pool files | none | 2026-10-13 22:20–22:22 |
| Listing | `GET /api/v4/projects` (instances, keyset by id) or `GET /api/v4/groups/:id/projects?include_subgroups=true` (gitlab.com groups) | `visibility=public archived=false last_activity_after=2025-04-03T00:00:00Z per_page=100 simple=false` | 2026-10-13 22:34 – 10-14 00:05 |
| Languages | `GET /api/v4/projects/:id/languages` | none | same |
| Commit screen | `GET /api/v4/projects/:id/repository/commits` | `ref_name=<default> per_page=1 page=5000` | 22:47 – 00:32 |
| Commit count, same-name check | `git clone --bare --filter=tree:0`, `git rev-list --count HEAD`, `git cat-file -e <pool head_oid>` | lazy fetch off (see below) | same |
| DP8L | `GET /api/v4/projects/:id/repository/tree` (root) | `ref=<default> per_page=100` | same |
| Oldest commit | `GET /api/v4/projects/:id/repository/commits` | `per_page=1 page=<commit count>` | 23:54 – 00:35 |
| GitHub copy | GitHub REST `search/commits` `q=hash:<root>` (3 pages max); GitHub GraphQL `repository{object(oid)}` in the 3,427 GitHub layer 1 frame repositories for the 8 roots with more than 300 results | `gh` token of this machine | 00:35 – 00:50 |
| gitlab.com search probe | `GET https://gitlab.com/api/v4/projects` | as listing, plus `with_programming_language`, `order_by=id` or `star_count` | 22:2x – 23:3x |

- All GitLab requests were unauthenticated, one at a time per host, 0.5 s apart. No HTTP 429 came back.
- The DP5 cut is `PUSHED_MIN = "2025-04-03"` of `s4-filter/funnel.py`. GitLab's `last_activity_at` also moves on issue and merge-request activity, so this bound is wider than a push date.
- GitLab gives no `mirror` flag without authentication, so DP6 "not a mirror" is not applied. Mirror namespaces show in the candidate list instead.

## Hosts

11 hosts answer the GitLab API: `git.adelielinux.org`, `git.dynare.org`, `git.themanaworld.org`, `gitlab.archlinux.org`, `gitlab.com`, `gitlab.eclipse.org`, `gitlab.freedesktop.org`, `gitlab.gnome.org`, `gitlab.inria.fr`, `gitlab.winehq.org`, `invent.kde.org` (`hosts.probe.tsv`).

`gitlab.archlinux.org` was stopped at project id 36,714 of 103,247: 3,871 of the first 4,000 rows are `archlinux/packaging/packages/*` build-recipe repositories, not software projects (`logs/gitlab.archlinux.org.stopped`).

## Results

The full tables are in `summary.md`. The short form:

- **Listed:** 31,148 projects. **Kept after the cheap steps:** 2,729. The cheap steps remove personal namespaces (20,812), forks (20), empty repositories (3), rows with no default branch (72) and rows with no C, C++, Java or Rust (7,512).
- **Screen of the 2,729 kept rows:**
  - already in the pool: 327 (roster rows);
  - fewer than 5,000 commits: 2,085;
  - same name and shared history with a pool row: 157;
  - **layer 1 candidates (at least 5,000 commits): 160**.
- **Shared history by root commit (the oldest commit of the history):**
  - 85 share it with a frame row (mostly Linux, LLVM, GCC and binutils trees);
  - 6 share it with a pool row outside the frame;
  - **69 are new**, in 51 distinct histories.
- **Of the 51 histories:**
  - 6 are in copy namespaces (`mirrors`, `lorry-mirrors`, `neon/backports-*`, `gfx-ci/android`);
  - 4 are Qt mirrors on invent.kde.org;
  - 2 are forks of a GitHub project whose oldest commit is not a root: `wine/wine-gecko` (Firefox), `mono/corefx`.
  - **About 39 look like original projects** that are missing now, for example `mesa/mesa` (231,435 commits; the GitHub row `mesa/mesa` is another project), `cairo/cairo`, `poppler/poppler`, `wlroots/wlroots`, `libinput/libinput`, `monado/monado`, `pacman/pacman`, `world/gedit/gedit`, `world/abiword`, `simgrid/simgrid`, `starpu/starpu` and `why3/why3`.
- **DP8L:** 49 of the 51 have a root license file. DP3 is not measured. The GitHub layer 1 rows pass DP3 and DP8L at 79.6%, so about 31 of the 39 rows can reach the frame.
- **Compute (inferred):** about 32 serial pipeline hours for the 51 histories. This uses the median hours of the layer 1 frame for each commit bucket (63 s per tokenizable MB). For an L-class project, the real time can be several times this value. One spot can run the rows in about one day.

### gitlab.com search (part b): stopped after the probe

- `with_programming_language` gives HTTP 500 after about 15 s (a server time limit) for any `id_after` past the start of the id range. So the language bound does not work on gitlab.com (`estimate_gitlabcom.py`, `gitlabcom.estimate.tsv`).
- Without the language bound, id sampling (`estimate_gitlabcom_nolang.py`, 24 points) gives **about 3.3 million** public projects that are not archived and active since 2025-04-03. 43% of them are in group namespaces and are not forks. That is far above the 50,000 limit of this measurement, so no sweep ran.
- Ranked by stars (`order_by=star_count`, offset pagination), rank 1,000 has about 36 stars and rank 10,000 about 3 stars.

## Method limits

- The root commit is the last row of the API history listing. For a history with several roots, it is one of them. So two copies of one project can show two different roots (`mesa/mesa` and `gfx-ci/android/mesa`).
- The GitHub commit search covers the default branches of public repositories and only some forks. We read at most 300 results for each root; for the 8 larger families, the GraphQL check covered only the layer 1 GitHub frame rows.
- A shared root is not always the same project. `vkd3d` shares its root with the frame row `vkd3d-proton`, and `binutils-gdb` copies share it with `lowRISC/opentitan`. The rule "skip the GitLab copy" then removes an upstream project.
- The first part of the same-name check ran with lazy fetch on (until 2026-10-13 ~23:45 UTC: the small hosts, GNOME, KDE, inria, and part of Eclipse and freedesktop). A positive result then can come from an object of the host's fork network. A negative result is not affected.

## Files

`probe_hosts.sh`, `list_gitlab.py`, `screen_layer1.py`, `roots_check.py`, `frame_object_check.py`, `summarize.py`, `estimate_gitlabcom.py`, `estimate_gitlabcom_nolang.py`; outputs `hosts.probe.tsv`, `rows/*.jsonl`, `screen*.tsv`, `clusters*.tsv`, `roots.tsv`, `frame_object_hits.tsv`, `candidates.tsv`, `summary.md`, `gitlabcom.estimate*.tsv`, `logs/`.

## Second round (2026-10-14): decisions, search, copy rules, batch 25

User decisions 2026-10-14 ~01:00 UTC (verbatim answers, relayed by the coordinator):

- gitlab.com search: **"Retry with my token"**, and "are we really making sure we have more than the minimal stars (as github)". So the GitLab instances and roster groups have no stars rule (like the rosters), and the gitlab.com-wide search uses **stars > 400**, the rule of the GitHub search (SELECTION-STAGES.md section 3).
- Copies: **"Remove copies, keep upstreams"**: remove copy namespaces (mirrors, lorry-mirrors, backports, Qt mirrors on invent.kde.org, gfx-ci/android) and forks; skip a GitLab row only if the shared-history pool row is the SAME project; keep an upstream (vkd3d) whose root is shared only with a fork. Recheck every row that was checked before the GIT_NO_LAZY_FETCH fix.
- Roster groups: **"Today's choice replaces it"**: the 2026-10-10 rule "do not expand GitLab roster groups" is replaced for GitLab.
- Release: **"adding another batch is the way to go" + "1"**: into v1 as batch 25.

**gitlab.com search, stars > 400** (`search_gitlabcom_stars.py`, 2026-10-14 ~01:3x UTC, unauthenticated; gitlab.com did not block, so no token was needed): `order_by=star_count`, offset pages, stop at stars <= 400. 75 projects; removed: 5 last activity before 2025-04-03, 18 personal namespace, 24 no C/C++/Java/Rust; **28 kept**. Screen: 10 have fewer than 5,000 commits, 8 share history with a pool row of the same name (GitHub mirrors: wireshark, qemu, openmw, remmina, fdroid x2, tortoisegit, aurorastore), **10 layer 1 candidates**. 10 of the 18 personal-namespace rows list a target language (for example CalcProgrammer1/OpenRGB, muttmua/mutt); the GitHub search has no owner rule, so this is an open question.

**Recheck** (`recheck_same_name.py`, lazy fetch off, a new clone for each row): 157 same-name rows; 155 confirmed. Not confirmed: `gitlab.gnome.org/community/ubuntu/gnome-software` (Ubuntu's downstream of GNOME Software: R3 fork, removed) and `invent.kde.org/rolisteam/rolisteam` (the pool row KDE/rolisteam has the same root commit ccd65c09: R2 same project, skipped; note: that GitHub mirror is in frame layer 100-499, the GitLab original has 6,783 commits).

**Copy rules** (`decide.py` -> `decisions.tsv`, 170 candidates = 160 + 10 from the search): R1 copy namespace 43, R2 same project 2 (gnu-grub/grub = GNU GRUB on Savannah in the frame; kicad = kicad-source-mirror in the frame), R3 fork 73 (with the 21 Linux trees), R4 upstream kept 6 (mesa, vkd3d, libcamera, dbus, weston, eigen), R5 split kept 2 (mesa/demos, pipewire/media-session), new history kept 44. **Kept: 52.**

**DP3 and DP8L** (`measure_dp.py`, the frame's code: `measure_clones.count`, the funnel DP3 test, `dp8l_rule`): 52 measured; why3/why3 fails DP3 (OCaml), mesa/demos fails DP8L (no root license file; the near-miss classes apply to GitHub rows only). **Batch 25: 50 rows** (S 45, M 4, L 1).

**Build** (`build_batch25_inputs.py`, then `s7-run/build_run.sh supplement 25`, `split_batchN.py 25 --parts-per-half 2`, `one_half.py batch25 a`, part a5 for mesa): see `s7-run/README.md`, section Batch 25.

## Third round (2026-10-14 ~15:35 UTC): personal namespaces in the gitlab.com search

User decision (verbatim): **"Yes then"** to: the gitlab.com search (stars > 400) also takes projects in PERSONAL namespaces, the same rule as the GitHub search (no owner rule). Other decisions since the second round (relayed): the 73 shared-history rows (R3 forks) stay out of v1, and LIMITATIONS must note the rule difference against GitHub; the GitLab labels get a manual review later; cedar/connectionlens was rerun locally with cregit 23e4ccb (fix/blame-exit128-fallback) and is in the merge (study repository commit 5efb869).

Funnel of the 18 personal-namespace rows (`personal_rows.py`, then `screen_layer1.py`, `roots_check.py`, `decide.py`, `measure_dp.py`, the same steps as batch 25):

| Step | Rows |
|---|---:|
| personal-namespace rows of the stars > 400 search (all active since 2025-04-03) | 18 |
| fork, empty or no default branch | 0 |
| no C, C++, Java or Rust in the languages API | 8 |
| fewer than 5,000 commits | 8 |
| shares history with a pool row of the same project (CalcProgrammer1/OpenRGB, frame layer 1; same name, head commit in the GitLab history with lazy fetch off) | 1 |
| layer 1 candidate | 1 (muttmua/mutt, 8,687 commits) |
| copy rules | mutt: R4 upstream (its root commit is shared only with the frame row neomutt/neomutt, a fork) |
| DP3 | pass |
| DP8L (root rule) | **fail**: the root has `COPYRIGHT` and `GPL`, no LICENSE, LICENCE, COPYING, UNLICENSE or LICENSES |
| **enter v1** | **0** (on 2026-10-14 ~15:50 UTC; changed at ~16:40 UTC, see the next section) |

At that time there was no batch 26. The DP8L near-miss classes (other root name) passed only GitHub rows (DP8L v4), so mutt stayed out.

## Fourth round (2026-10-14 ~16:40 UTC): the DP8L v4 near misses also pass GitLab rows (batch 26)

User decision (verbatim): **"yes to mutt"**, to the question "Should mutt get the same license exception as GitHub rows and enter v1?". So the DP8L v4 near-miss classes C, D and E (`s4-filter/funnel.py` NEAR_MISS, the batch 23 rule of 2026-10-11) now pass GitLab rows too. This removes the license-rule difference against GitHub. The fork-rule difference (the 73 R3 rows stay out) does not change.

`near_miss_gitlab.py` applies the classes of `s4-filter/dp8l-audit/audit_dp8l.py` (the same patterns and the same order; git trees of a depth-1 fetch of the pinned head replace the GitHub REST responses) to every kept row that passes DP3 and fails DP8L in `measure.jsonl`. Output `near_miss.tsv`:

| Row | Pinned head | Class | Evidence | Enters v1 |
|---|---|---|---|---|
| https://gitlab.com/muttmua/mutt | 844fcfe7861631359ee789e4231d322144a1bd3b | C (other root name) | `COPYRIGHT`, `GPL` | yes |
| https://gitlab.freedesktop.org/mesa/demos | 649baedafcb90313ade69909fdef1ee156ab5f8d | H (no license evidence) | none: no root near name, no package file, no license file below the root, no README line | no |

`build_batch26_inputs.py` writes `../../s4-filter/supplement26.gitlab.csv`, `../../s4-filter/supplement26.licenses.csv` (NOASSERTION, evidence `C near miss: other root name: COPYRIGHT;GPL`, the form of `supplement_batch.py`) and `../v2/pool.batch26.csv` (origin `gitlab-search:stars>400 (personal namespace)`). Then `s7-run/`: `build_run.sh supplement 26`, `labels_batch26.py` (unknown, the gitlab.com search rule of batch 25) and `parts_batch26.py` (part a1, 1 worker, spot a). **Batch 26: 1 row (S).** v1 = 3,548 projects. Runbook: `~/s3-work/ec2-batch26/README.md`.

## Why the GitLab extension adds few projects (2026-10-14)

The user asked why the gitlab.com search found so few projects. The reasons, with the measured counts:

1. **Few gitlab.com projects have many stars.** Only 75 public, active gitlab.com projects have more than 400 stars. The same rule on GitHub gave 80,990 repositories (SELECTION-STAGES.md §3). Ranked by stars, gitlab.com project number 1,000 has about 36 stars, and number 10,000 has about 3. Most popular open source projects keep their main copy on GitHub, or they have a GitHub mirror that the pool already has.
2. **v1 takes only layer 1 (>= 5,000 commits).** This is the strongest filter. 8 of the 18 personal-namespace rows have fewer commits. On GitHub too, only about 13% of the frame reaches layer 1 (3,379 of 25,263).
3. **The language rule.** 8 of the 18 personal-namespace rows have no C, C++, Java or Rust code.
4. **Copies of rows that we have.** OpenRGB is already in v1 through its GitHub copy (CalcProgrammer1/OpenRGB). The same holds for many large GitLab projects: GNOME and KDE are in v1 through their GitHub mirrors (53 `GNOME__*` and 58 `KDE__*` rows). GitHub does not mark these copies as mirrors, so they pass DP6.
5. **The license rule.** muttmua/mutt failed only the license file check (DP8L): its root has `COPYRIGHT` and `GPL`. Since 2026-10-14 ~16:40 UTC ("yes to mutt") the DP8L v4 near misses pass GitLab rows too, so mutt is in v1 as batch 26 (fourth round above).

So the low count does not come from a defect of the search. It comes from the stars rule, which is equal to the GitHub search rule on purpose. A lower stars bound for gitlab.com only would give more rows, but the two searches would then use different rules.
