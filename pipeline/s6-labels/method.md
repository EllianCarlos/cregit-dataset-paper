# S6 labels: method

Run: 2026-10-09 (`label_date` 2026-10-09), for the 3,265 projects of run layer 1 (batches
1-20). Run again on 2026-10-11 (`label_date` 2026-10-11) for the 3,379 projects of version 1
of the projects dataset: the 3,265 and the 114 projects of batches 21 and 22. Input:
`../s5-evidence/evidence.csv` only, and the frames for `size_class` and `language`. The rules
are in `../SELECTION-STAGES.md` section 7. The rules did not change on 2026-10-11.

```
python3 build_labels.py --date 2026-10-11 --prior labels.20261009.csv   # writes labels.csv and counts.txt
python3 -m pytest -q test_build_labels.py
```

`labels.20261009.csv` is the `labels.csv` of 2026-10-09 (3,265 rows). `--prior` keeps its
`label_date` for each project whose row has the same values in all the other columns. The
other rows get `--date`. The user kept this rule on 2026-10-11. All 3,265 rows of 2026-10-09 are the same in the new `labels.csv`
(the first 3,265 rows, `label_date` 2026-10-09). The 114 new rows have `label_date`
2026-10-11. The default frames are those of `../s5-evidence/build_evidence.py`; `--frame`
replaces them.

## 1. Rules

The first rule that matches sets the label. `label_basis` names each fact that set it.

| Order | Label | Rule |
| ---: | --- | --- |
| 1 | `government` | a `government` fact |
| 2 | `contested` | a foundation fact (`roster`, `roster_org`) and a company fact |
| 3 | `foundation` | a foundation fact |
| 4 | `contested` | a `fiscal_sponsor` fact and a company fact (case L2) |
| 5 | `fiscal-sponsor` | a `fiscal_sponsor` fact (SFC, SPI, NumFOCUS "sponsored", PSF fiscal sponsorees) |
| 6 | `company` | a company fact: `company_pool:spinellis`, `company_org` (strength `page` or `verified-domain`), `company_roster` (mozilla), `company_roster_org` (the Red Hat table, see below) |
| 7 | `community` | a governance document fact |
| 8 | `personal` | `owner_kind:user`, and no other fact |
| 9 | `unknown` | all other projects |

**The Red Hat table (decision of the user, 2026-10-09).** `company_roster_org:redhat` comes
from the "All projects" table of redhatofficial.github.io. That table says that Red Hat
takes part in the project. It does not say that Red Hat owns or controls the project. The
user chose to count it as a company fact. So it sets `company` when there is no roster fact,
and it gives `contested` together with a `roster` or `roster_org` fact (rule 2) or a
`fiscal_sponsor` fact (rule 4). The paper must state what this evidence shows.

These S5 facts set no label: `owner_kind:org`, `roster_affiliated` (NumFOCUS "affiliated")
and `company_org_candidate` (a kept company org with no company page and no verified domain
on the company's domains; decision of the user, 2026-10-09). The column `other_facts` keeps
them, so a reader can see them.

No rule gives a label because other rules do not match. `unknown` means: no fact that sets
a label.

**Fact types that were not collected (decision of the user, 2026-10-09).** S5 did not
collect `government` facts or governance document facts for this version of the dataset.
So no project is `government` and no project is `community`. These two counts are 0 because
the evidence was not collected, not because the dataset has no such projects.

## 2. Outputs

`labels.csv`: `project`, `pool_key`, `label`, `label_basis`, `contested` (the facts in
conflict; non-empty only for `contested`), `other_facts`, `size_class`, `language`
(GitHub primary language, from the frame), `label_date`. Fact lists are sorted and joined
by `;`. `counts.txt`: the table below and the breakdowns. Its first line gives the number of
rows for each `label_date`.

## 3. Counts

The 3,379 projects of version 1 (2026-10-11):

| Label | L | M | S | Total |
| --- | ---: | ---: | ---: | ---: |
| foundation | 8 | 71 | 347 | 426 |
| company | 15 | 56 | 158 | 229 |
| contested | 2 | 9 | 64 | 75 |
| government | 0 | 0 | 0 | 0 |
| fiscal-sponsor | 1 | 18 | 19 | 38 |
| personal | 6 | 16 | 359 | 381 |
| community | 0 | 0 | 0 | 0 |
| unknown | 50 | 300 | 1,880 | 2,230 |
| **Total** | 82 | 470 | 2,827 | 3,379 |

The 114 projects of batches 21 and 22 (included above):

| Label | Batch 21 | Batch 22 | L | M | S | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| foundation | 5 | 33 | 3 | 6 | 29 | 38 |
| company | 5 | 0 | 0 | 4 | 1 | 5 |
| contested | 39 | 0 | 0 | 1 | 38 | 39 |
| fiscal-sponsor | 2 | 0 | 0 | 1 | 1 | 2 |
| personal | 5 | 0 | 0 | 0 | 5 | 5 |
| unknown | 25 | 0 | 0 | 12 | 13 | 25 |
| **Total** | 81 | 33 | 3 | 24 | 87 | 114 |

- Batch 22: all 33 GNU projects are `foundation` on `roster:gnu` (S5 cases C7 and C8).
- Batch 21: the 39 `contested` projects are KDE projects: `roster:kde` against the Red Hat
  table. `foundation`: NetBSD/pkgsrc (`roster:netbsd`), 2 on `roster_org:lf`, 1 on
  `roster:eclipse` and 1 on `roster:rust-foundation`. `company`: 2 on
  `company_org:analogdevicesinc`, 2 on `company_org:MarvellEmbeddedProcessors`, and
  cockpit-project/cockpit on the Red Hat table alone. `fiscal-sponsor`: matplotlib (NumFOCUS)
  and BusyBox (SFC). `unknown`: 21 have only `owner_kind:org`, 4 also have a
  `company_org_candidate` fact (avnet, ni, spdk, HewlettPackard).

The 3,265 projects of batches 1-20 (2026-10-09; no row changed on 2026-10-11):

| Label | L | M | S | Total |
| --- | ---: | ---: | ---: | ---: |
| foundation | 5 | 65 | 318 | 388 |
| company | 15 | 52 | 157 | 224 |
| contested | 2 | 8 | 26 | 36 |
| government | 0 | 0 | 0 | 0 |
| fiscal-sponsor | 1 | 17 | 18 | 36 |
| personal | 6 | 16 | 354 | 376 |
| community | 0 | 0 | 0 | 0 |
| unknown | 50 | 288 | 1,867 | 2,205 |
| **Total** | 79 | 446 | 2,740 | 3,265 |

The breakdowns below are for the 3,265 projects. `counts.txt` gives them for the 3,379.

- `company`: 90 rest on `company_org` alone, 35 on `company_org` and
  `company_pool:spinellis`, **55 on `company_pool:spinellis` alone** (the decision of
  2026-10-06 asks the report to count these), **34 on `company_roster_org:redhat` alone**,
  7 on `company_roster:mozilla`, and 3 on the Red Hat table with Spinellis or a company org.
- `contested`: 26 are a roster or roster_org fact against the Red Hat table (19 KDE,
  5 Linux Foundation or CNCF, for example ceph/ceph, and 2 The Document Foundation, for
  example LibreOffice/core), 9 are
  a roster or roster_org fact against `company_pool:spinellis` (for example
  grpc/grpc-java, apache/doris), and 1 is a fiscal sponsor against the Red Hat table
  (systemd/systemd: SPI).
- `unknown`: 2,120 have only `owner_kind:org`. 84 also have a fact that sets no label
  (74 `company_org_candidate`, 10 `roster_affiliated`). One project (not on GitHub) has
  only `roster_affiliated`.

**Change from the first run of the same day.** The first run did not count the Red Hat
table. The user decision changed 61 labels: 34 `unknown` to `company`, 26 `foundation` to
`contested`, and 1 `fiscal-sponsor` to `contested` (systemd/systemd).

## 4. Cases and choices

- **L1. A foundation fact or a company fact in a `contested` label.** Section 7 says "a
  `roster` fact and a company fact". This run takes `roster_org` as a roster fact here too,
  because the `foundation` rule takes both.
- **L2. A fiscal sponsor fact and a company fact.** Section 7 gives no rule for this case
  (both `fiscal-sponsor` and `company` require only "no roster fact"). This run gives
  `contested`. One project has this case: systemd/systemd (SPI and the Red Hat table). No
  project of batches 21 and 22 has it. This is an open decision for the user.
- **L3. `personal` is strict.** A user-owned project with any other fact is not `personal`.
  2 user-owned projects have another fact: one is `fiscal-sponsor`, and one is `unknown`
  (it has `roster_affiliated:numfocus`).
- **L4. A user-owned project with a Spinellis company** gets `company`, because rule 6 comes
  before rule 8. The Spinellis link comes from committer e-mail domains, not from control.
  No layer 1 project has this case now.
- **L5. Stale statuses.** `foundation` also comes from inactive roster statuses (S5 case C1).
  This is an open decision for the user.
- **L6. GNU (2026-10-11).** The 33 GNU projects get `foundation`, because the GNU roster files
  give `org_kind` `foundation` (S5 case C8). **Decision of the user, 2026-10-11: keep
  `foundation`.**
