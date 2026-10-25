# S5 evidence: method

Run: 2026-10-09, for the 3,265 projects of run layer 1 (`s7-run/frame.layer1.csv`, batches 1-20).
Run again on 2026-10-11 for the 3,379 projects of version 1 of the projects dataset: the 3,265
and the 114 projects of batches 21 and 22 (`s7-run/frame.batch21.csv`: 81 projects, the DP8L
supplement and BusyBox; `s7-run/frame.batch22.csv`: 33 GNU projects). The rows of the 3,265
projects did not change: a run with `--frame ../s7-run/frame.layer1.csv` writes the files of
2026-10-09 byte for byte. Run again on 2026-10-16 for the 3,497 projects of version 1: the 3,379
and the 118 projects of batch 23 (`s7-run/frame.batch23.csv`, the DP8L v4 near-miss rows). The
pool rows of batch 23 are in `s2-pool/pool.csv` with the same values as in
`s2-pool/v2/pool.batch23.csv`, so the pool files did not change. The rows of the 3,379 projects
did not change: a run with the three frames of 2026-10-11 writes `evidence.20261011.csv` (the
`evidence.csv` of 2026-10-11, kept) and the `counts.txt` and `checks.txt` of 2026-10-11 byte for
byte. The rules are in `../SELECTION-STAGES.md` section 7.

## 1. What this stage does

`build_evidence.py` writes one row for each fact about each project. Each row keeps the
source file, the URL that the source file records as read, the fetch time, and a pointer
(`file:line`) to the row that holds the fact.

The script reads only files that are already in this folder tree. **This run fetched
nothing.** All facts come from S1 and S2 files that were fetched on 2026-10-05 and
2026-10-06, each with its URL and fetch time.

```
python3 build_evidence.py            # writes evidence.csv, counts.txt, checks.txt
python3 -m pytest -q test_build_evidence.py
```

`s2-pool/pool.csv` must exist (`xz -d -k s2-pool/pool.csv.xz`).

The default inputs are the four frames (`frame.layer1.csv`, `frame.batch21.csv`,
`frame.batch22.csv`, `frame.batch23.csv` of `s7-run`) and two pool files: `s2-pool/pool.csv` and
`s2-pool/v2/pool.batch22.csv` (the 33 pool rows of batch 22, in the columns of `pool.csv`; 31
rows come from `s2-pool/v2/pool.supplement.csv`, the GNU roster v2, and 2 are copies of
`pool.csv` rows). `--frame` and `--pool` replace them; give each option once for each file. A
name or a pool key must not repeat across the frames. A pool key in two pool files must have
the same values in both.

## 2. Outputs

| File | Content |
| --- | --- |
| `evidence.csv` | one row for each fact: 4,656 rows for 3,497 projects (2026-10-11: 4,511 rows for 3,379 projects; 2026-10-09: 4,302 rows for 3,265 projects) |
| `evidence.20261011.csv` | the `evidence.csv` of 2026-10-11 (3,379 projects), kept |
| `counts.txt` | rows and projects for each fact type and for each fact |
| `checks.txt` | the join check against the pool `origins` (no difference), 2 info lines for the GNU roster v2 (case C7), and 3 roster URLs that name no GitHub account |

Columns of `evidence.csv`: `project` (the manifest and sidecar key), `pool_key`,
`fact_type`, `fact`, `subject` (the org key, the company or the login), `name` (the
project name as the source spells it), `status` (the status that the source gives, or the
strength of a company org fact), `language` (the language that the source names),
`source`, `source_url`, `fetched_at`, `pointer`, `note`.

## 3. The join

A project is a frame row. Its `pool_key` gives the `pool.csv` row.

- **Roster, repository level.** A GitHub row joins the roster rows whose `github_slug`
  (lower case) is one of the row's `input_slugs`. This is the same rule that
  `s2-pool/resolve.py` used to make the pool, so a renamed repository keeps its roster
  rows. A row on another host joins the roster rows with no slug whose normalized
  `repo_url` is the `pool_key` (the `norm_url` of `build_pool.py`). The `*.repos.csv`
  files (home page to repository lookups) take the kind of their main roster file and
  the status of the main file's row for the same project.
- **Roster, org level.** A roster row with no slug and a `github.com/<account>` URL names
  an org (`s2-pool/roster_orgs.csv`). It joins every project whose `owner_login` is that
  account (case is ignored). `github.com/orgs/<x>` gives `x`. A topics page and a broken
  repository URL give no account (`checks.txt`).
- **Spinellis.** The slug of each row of `enterprise_projects.txt` joins as above. Only
  a row with a `company_name` gives a fact.
- **Company org.** The project's owner is a kept org of `sources/spinellis-2020/org_links.csv`
  (rules L1 to L3) and an Organization in `pool.csv`.

**Check.** For each project, the roster files, the Spinellis set and the company org that
the join finds must be the ones that the pool `origins` names. All 3,497 projects agree. Two
batch 22 projects also join a later fetch of their roster file (case C7); the check writes an
info line for each.

## 4. Fact types and counts

Counts for the 3,497 projects. The column "Of them new" gives the rows and projects of
batches 21 and 22 (2026-10-11), then of batch 23 (2026-10-16).

| Fact type | Rule | Source | Rows | Projects | Of them new: 21-22 | Of them new: 23 |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `roster:<org>` | a foundation roster names the repository | `rosters/<org>.csv`, `rosters/obf.repos.csv` | 552 | 473 | 77, 75 | 14, 11 |
| `roster_org:<org>` | a foundation roster names the GitHub org of the repository | `rosters/lf.csv`, `lfai.csv`, `osgeo.csv` | 75 | 67 | 2, 2 | 0, 0 |
| `fiscal_sponsor:<org>` | a fiscal sponsor roster names the repository as sponsored | `rosters/sfc*.csv`, `spi.repos.csv`, `numfocus*.csv` | 40 | 40 | 2, 2 | 0, 0 |
| `roster_affiliated:<org>` | NumFOCUS names the repository as "affiliated" (case C2) | `rosters/numfocus.repos.csv` | 13 | 13 | 0, 0 | 1, 1 |
| `company_roster:<org>` | a company roster names the repository | `rosters/mozilla.csv` | 7 | 7 | 0, 0 | 0, 0 |
| `company_roster_org:<org>` | a company roster names the GitHub org (case C3) | `rosters/redhat.csv` | 105 | 105 | 40, 40 | 1, 1 |
| `company_pool:spinellis` | the Spinellis enterprise set has the repository, with a company | `sources/spinellis-2020/enterprise-oss.tar.gz` | 105 | 105 | 0, 0 | 3, 3 |
| `company_org:<org>`, strength `page` | a kept org whose own published website links to it | `sources/company-pages/evidence.csv`, `browser/evidence_browser.csv` | 97 | 78 | 2, 2 | 2, 2 |
| `company_org:<org>`, strength `verified-domain` | a kept org that GitHub verifies, with its website on a company domain | `sources/spinellis-2020/org_links.csv` | 94 | 94 | 2, 2 | 1, 1 |
| `company_org_candidate:<org>` | a kept org with neither (case C4) | `sources/spinellis-2020/org_links.csv` | 141 | 141 | 4, 4 | 5, 5 |
| `owner_kind:org` | GitHub owner type Organization | `s2-pool/pool.csv` | 3,029 | 3,029 | 75, 75 | 103, 103 |
| `owner_kind:user` | GitHub owner type User | `s2-pool/pool.csv` | 398 | 398 | 5, 5 | 15, 15 |

Note (2026-10-16): the table of 2026-10-11 gave 95 projects for `company_org` `page`. The
correct value for 2026-10-11 is 76 projects (95 rows): some projects have two page rows.

132 projects have a `company_org` fact: 38 with a page only, 54 with a verified domain only,
40 with both (2026-10-11: 130; 37, 54, 39). 877 projects have a fact other than `owner_kind`
(2026-10-11: 857; batch 23: 20). 70 projects are not on GitHub, so they have no `owner_kind`
fact: 36 of batches 1-20, BusyBox and the 33 GNU projects. All 118 projects of batch 23 are on
GitHub.

The new roster rows of batches 21 and 22: `roster:kde` 39, `roster:gnu` 35 (33 projects, case C7), `roster:netbsd`
1 (NetBSD/pkgsrc), `roster:eclipse` 1, `roster:rust-foundation` 1, `roster_org:lf` 2,
`fiscal_sponsor:numfocus` 1 (matplotlib) and `fiscal_sponsor:sfc` 1 (BusyBox).

The new rows of batch 23 (20 projects): `roster:asf` 7 and `roster:asf-incubator` 3
(`graduated`; these projects also have an `asf` row), `roster:eclipse` 2, `roster:netbsd` 1
(NetBSD/src), `roster:rust-foundation` 1, `roster_affiliated:numfocus` 1 (igraph/rigraph),
`company_roster_org:redhat` 1 (nfs-ganesha/nfs-ganesha), `company_pool:spinellis` 3
(digi-embedded/meta-digi, gwtproject/gwt, usdot-fhwa-stol/carma-platform), `company_org` 3
(NVIDIA/nvtexlive: page and verified domain; mongodb/docs: page) and `company_org_candidate` 5.

The roster `language` column is filled only from the ASF DOAP files
(`rosters/raw/asf/projects.json`, field `programming-language`): 72 rows (4 of batch 23). Only an `asf`
row that comes from a DOAP `repository` entry has a DOAP of its own. The other rosters
name no language.

## 5. Fact types that are not collected

**Decision of the user, 2026-10-09: these fact types are not collected for version 1 of
the dataset.** So the S6 counts of `government` and `community` are 0 because the evidence
was not collected, not because the dataset has no such projects. The paper must say this.

| Fact type | Why it is not collected | What it would take |
| --- | --- | --- |
| `government:<body>` | No S1 source lists government orgs. | A decision on a cited list (for example the list of government orgs on GitHub that GitHub publishes in its `government.github.com` repository), then one fetch of that file, kept with its URL and time, and the same org join as `roster_org`. |
| governance document (for `community`) | No S1 or S3 file holds file paths or file text: S3 kept only byte counts for each extension. | A rule for what a governance document must say to show community control (a file name alone does not show it). Then, for each project, a read of the named files at the snapshot commit (the pinned clones of the census, or one GitHub contents call for each project), kept with the commit, the path and the fetch time. |

## 6. Cases and choices

These are the cases where the rules of section 7 did not decide alone. The user decided
C2, C3 and C4 on 2026-10-09 (`../SELECTION-STAGES.md` section 10), and C7 and C8 on
2026-10-11. C1 and C5 are open.

- **C1. Roster status.** A roster fact keeps the status that the roster gives, but every
  status gives the fact, also `attic`, `archived`, `Archived`, `READ_ONLY` and `retired`.
  18 projects get `foundation` from inactive statuses only (none of batches 21, 22 and 23; 16 KDE `historical` or
  `unmaintained` repositories, `LibreOffice/online`, `xorg/xserver-xprint`, and others).
  `asf-incubator` `graduated` rows are kept; these projects also have an `asf` row.
- **C2. NumFOCUS "affiliated".** The NumFOCUS roster has two statuses. "Sponsored" projects
  are fiscally sponsored; "affiliated" projects are not. So "affiliated" gives the fact
  `roster_affiliated:numfocus`, which sets no label. NumFOCUS "sponsored" projects and PSF
  fiscal sponsorees give `fiscal_sponsor`, because their roster files have `org_kind`
  `fiscal-sponsor` (in layer 1: 17 NumFOCUS projects, no PSF project). Decided by the user
  on 2026-10-09; section 7 now names them.
- **C3. Red Hat.** The Red Hat roster is the "All projects" table of
  redhatofficial.github.io. Its method file says that the table lists projects that Red Hat
  takes part in, and that it does not state ownership. In layer 1 it names the orgs of 64
  projects, for example KDE (19), dotnet, openjdk, systemd, ceph and libreoffice. The fact
  is recorded as `company_roster_org:redhat`. With batches 21 and 22 it names the orgs of 104
  projects; KDE has 58 of them (39 in batch 21). With batch 23 it names the orgs of 105
  projects (the new one: nfs-ganesha/nfs-ganesha). The evidence shows that Red Hat takes part in
  the project, not that Red Hat controls it. The user chose on 2026-10-09 to count it as a
  company fact, so S6 uses it (see `../s6-labels/method.md`). The roster row for the org
  RedHatOfficial itself states ownership, but no layer 1 project is in that org.
- **C4. Kept company orgs with no page and no verified domain.** The Spinellis README says
  that a kept org link "is never a label by itself". So these projects (141 on 2026-10-16, 5 of
  them in batch 23) get
  `company_org_candidate:<org>` only, which sets no label (confirmed by the user on
  2026-10-09). 54 of them are in orgs that GitHub verifies but whose
  website is not on a domain of the company in `companies.csv`: google (27,
  `opensource.google`), xilinx (10, `www.amd.com`), dotnet (5, `dot.net`), grpc (3),
  flutter (2) and 7 more. The domain list comes from the committer domains in the Spinellis
  data, so it does not hold such domains.
- **C5. Company pages that were not read.** Two projects depend on a page that the browser
  step could not read: `HewlettPackard/gsc-linux` and, in batch 21, `HewlettPackard/gsc-uboot`
  (`www.hpe.com`: tool error). These runs could not read it, because the browser tool is not
  connected in these sessions. Both get `company_org_candidate:HewlettPackard` only.
- **C6. Spinellis rows with no company.** 441 projects are in the Spinellis enterprise set
  (416 of batches 1-20, 19 of batch 23), but only 105 rows give a company name (3 of batch 23).
  The other rows give no fact.
- **C7. The GNU roster v2 (2026-10-11).** `rosters/gnu.v2.csv` is `rosters/gnu.csv` fetched
  again on 2026-10-10, with the same 388 rows and more repository URLs. The 31 GNU projects of
  `pool.supplement.csv` name `rosters/gnu.v2.csv:gnu` in `origins`, and they join only that
  file. Two batch 22 projects (3dldf and bison) are `pool.csv` rows from `gnu.csv`, so their
  `origins` names only `rosters/gnu.csv:gnu`. Both roster files name them, so each gets two
  `roster:gnu` rows, one from each file. `LATER_FETCH` in `build_evidence.py` records that
  `gnu.v2.csv` is a later fetch of `gnu.csv`. For these two projects the join check accepts
  the later file and writes an info line. The label does not change: both rows give the same
  fact `roster:gnu`. **Decision of the user, 2026-10-11: keep both rows.**
- **C8. GNU is a foundation roster (2026-10-11).** Both GNU roster files give `org_kind`
  `foundation` (`rosters/gnu.method.md`: "FSF / GNU"). So each GNU project gets `roster:gnu`
  and S6 gives `foundation`. The code applies the `org_kind` of the roster file, as for the
  other rosters. **Decision of the user, 2026-10-11: GNU stays `foundation`.** The rule does
  not change.
