# Report: ScanCode license pass over the 8,449 projects of TOM 1.0.0

Date: 2026-11-08. This report changes no release file. Nothing was pushed.

- Run: `run-license-scancode-1/results/` (results.tsv, results.jsonl, scan.log, retry.log, gate.txt).
- Tables: `60_report.py` makes all the numbers below. It writes `analysis/compare_tom.tsv` (one row per
  project, with the TOM value and the class) and `analysis/review.tsv` (the review cases).
  Command: `python3 -I 60_report.py`.
- Tools: ScanCode 32.5.0, SPDX template diff (spdx tools-java 2.0.7, SPDX list 3.29.0), licensee 10.1.0
  and askalono 0.5.0 as second opinions, rule layer of ctp `feat/license-scan` at 6b6efcf.
- TOM 1.0.0 value: `lists/tom_license_values.tsv` (the values before the release pass) plus the 149
  license fills of the release pass for projects outside GitHub (`dataset-tom-2` `inputs/fills.tsv`).
  This gives 2,099 GitHub and 48 other-host NOASSERTION values, the same counts as `docs/COLUMNS.md`.
  4 GitHub projects have no value in the local copies (KDE kmymoney, konqueror, kphotoalbum; qt qtbase).
  The rescan of 2026-11-07 counted them with the NOASSERTION set; this report does the same.

## 1. Coverage

| status | projects |
|---|---:|
| ok | 8,434 |
| error | 10 |
| fetch-error | 3 |
| no-key-files | 2 |
| total | 8,449 |

| projects | cause | TOM 1.0.0 value |
|---|---|---|
| OpenCPN, Redot-Engine, Warzone2100, GraphScope, endless-sky, godot, organicmaps, Prusa-Firmware-Buddy (8) | The SPDX template diff did not end in 900 s (many near matches). | 6 have a value, 2 NOASSERTION |
| apache cloudberry | ScanCode was killed (rc -9, memory). | Apache-2.0 |
| apache eventmesh | ScanCode did not end in 3,600 s. | Apache-2.0 |
| busybox (git.busybox.net) | The server refuses a fetch of the pinned commit ("unadvertised object") and has no filter support. | NOASSERTION |
| kaltura nginx-vod-module, kaltura playkit-android | The GitHub repositories are gone or private ("Repository not found"). | AGPL-3.0 |
| jasonrohrer OneLife, powerfolder PF-CORE | The commit has no key file (no license file, README, manifest or REUSE data). | NOASSERTION |

- A second try can fix 11 of the 15: the template diff with a longer time limit (or without the diff, at a
  lower confidence), ScanCode with more memory or time, and busybox from a mirror that serves the commit.
- Time (UTC). Instance: c7i.16xlarge (on demand). Launch 15:53. Main run 15:58 to 17:13, 56 jobs.
  Between 16:23 and 16:33, 549 projects failed in a burst (489 fetch errors and 60 errors). The retry
  (8 jobs, 17:13 to 18:13) fixed 535 of them. The upload ended at 18:14. Instance time is approximately
  2 h 20 min (approximately US$7).
- Per project (last try): median 11.4 s, 95th percentile 63.4 s, maximum 3,626 s. The sum is 45.6 hours.
- Gate: 6 of 6 projects give the expected value (`gate.txt`).

## 2. Against TOM 1.0.0

Classes compare the base ids (`-only`, `-or-later` and exceptions removed). "same" also accepts a
different id style (TOM `GPL-3.0`, pass `GPL-3.0-or-later`).

| pass against TOM 1.0.0 | high | medium | low | none | total |
|---|---:|---:|---:|---:|---:|
| same | 5,183 | 227 | 4 | 0 | 5,414 |
| same ids, other operator or exception | 155 | 8 | 0 | 0 | 163 |
| superset (pass names more ids) | 462 | 42 | 8 | 0 | 512 |
| subset (pass names fewer ids) | 48 | 3 | 0 | 0 | 51 |
| overlap | 1 | 99 | 4 | 0 | 104 |
| different (no common id) | 34 | 7 | 3 | 0 | 44 |
| no value (pass failed, TOM has a value) | 0 | 0 | 0 | 10 | 10 |
| new value (TOM NOASSERTION or missing) | 1,114 | 685 | 285 | 0 | 2,084 |
| both NOASSERTION | 0 | 0 | 0 | 67 | 67 |
| total | 6,997 | 1,071 | 304 | 77 | 8,449 |

- Projects with a TOM value: 6,298. The pass gives the same ids for 5,577 (88.6%). With high confidence:
  5,338 of 5,883 (90.7%); only 83 (1.4%) are subset, overlap or different.
- Superset is mostly a dual license that GitHub gives as one id: Apache-2.0 to "MIT OR Apache-2.0" (187)
  or "Apache-2.0 OR MIT" (61). 49 are "Apache-2.0 AND MIT" (see question 3).
- Same ids, other operator: mostly an exception that TOM does not show (GPL-2.0 to
  `GPL-2.0-only WITH LicenseRef-scancode-oracle-openjdk-exception-2.0`, 32), and ';' lists that become AND.
- Different (44): 13 are TOM GPL and pass LGPL (an LGPL-3.0 text next to the GPL-3.0 text; the pass is
  probably right). Two groups are probably rule-layer errors:
  - 10 Rust projects: TOM Apache-2.0, pass MIT (high, from a notice). Most are probably
    "MIT OR Apache-2.0".
  - 3 libvirt projects: TOM LGPL-2.1, pass GPL-2.0-or-later (high). libvirt is LGPL-2.1-or-later; the rule
    keeps the GPL text of `COPYING`.

### The key number: NOASSERTION projects that now get a value

| TOM NOASSERTION or missing | high | medium | low | none | total |
|---|---:|---:|---:|---:|---:|
| GitHub (the rescan set) | 1,091 | 665 | 282 | 65 | 2,103 |
| other hosts | 23 | 20 | 3 | 2 | 48 |
| total | 1,114 | 685 | 285 | 67 | 2,151 |

| estimate for the 2,103 GitHub projects | values |
|---|---:|
| before: safe strict rule (licensee and askalono) | 446 |
| before: any scanner | 1,102 |
| before: projection with ScanCode | 1,300 to 1,450 |
| now: high | 1,091 |
| now: high and medium | 1,756 |
| now: any value | 2,038 |
| proposal of section 5 (high and medium, not on the review list) | 1,384 |

The pass is above the ScanCode projection. The high and medium values on the review list (372 GitHub
projects) need a hand check before they count.

Evidence of the 2,084 new values: text 1,354, text with notice 233, notice in a license file 209,
sub-folder license file 106 (all low), README 95 (all low), manifest 54, REUSE 28, notice file 5.

## 3. Quality

### Agreement with the second opinions (8,434 ok projects)

| confidence | licensee agree | partial | disagree | no answer | askalono agree | partial | disagree | no answer |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| high | 5,672 | 594 | 37 | 694 | 6,309 | 161 | 34 | 493 |
| medium | 338 | 220 | 37 | 476 | 374 | 79 | 91 | 527 |
| low | 15 | 23 | 30 | 236 | 8 | 11 | 10 | 275 |
| none | 0 | 0 | 1 | 61 | 0 | 0 | 2 | 60 |

- Both second opinions disagree: 9 projects. Neither one gives an answer: 681 projects.
- Low values have almost no support: licensee agrees on 15 of 304, askalono on 8 of 304.

### Review cases (`analysis/review.tsv`)

A project can be in more than one kind. 1,092 distinct projects; 670 of them are TOM NOASSERTION.

| kind | projects | note |
|---|---:|---|
| `LicenseRef-scancode-*` id | 396 | kde-accepted-gpl 77, kde-accepted-lgpl 68, public-domain 51, proprietary-license 51, other-permissive 14, commercial-license 13 |
| low confidence | 304 | |
| AND list with 4 or more ids | 270 | 4 ids: 79, 5: 60, 6: 31, 7 to 11: 97, and 3 projects with 18, 20 and 28 ids |
| a second opinion disagrees | 230 | |
| AND from a declaration (README, manifest, notice, sub-folder) | 185 | 114 low, 71 medium; 179 TOM NOASSERTION |
| overlap with TOM | 104 | mostly KDE projects with REUSE data |
| "Apache-2.0 AND MIT" | 77 | 63 from two root texts at high confidence; TOM Apache-2.0 for 49 |
| subset of TOM | 51 | mostly KDE REUSE lists (the pass drops ids of sub-folders) |
| different from TOM | 44 | see section 2 |
| `WITH Linux-syscall-note` in a project that is not a kernel | 33 | 26 KDE projects whose COPYING is the kernel GPL-2.0 text with the syscall note; also clamav, ROCm amdgpu, libgpiod, fluxengine, fritzing |
| failed | 15 | see section 1 |

### The 30 hand-check projects (rescan `hand_check_sample.tsv`)

The `your_value` column of `hand_check_sample.tsv` is empty. Thus no hand truth exists, and this report
cannot count right values. What the data shows:

- Confidence: high 15, medium 10, low 4, none 1 (one project: no license found).
- 7 projects have a rescan strict value. The pass gives the same ids for 6: dathere qsv MIT, r-dbi odbc MIT,
  rspamd Apache-2.0, lxcfs LGPL-2.1-or-later, SSVOpenHexagon AFL-3.0, bottlerocket "Apache-2.0 AND MIT".
  u-boot-xlnx changes from OFL-1.1 (a bundled font) to GPL-2.0-or-later; the pass is probably right.
- Probable errors to check: bottlerocket (the project says "Apache-2.0 or MIT, at your option"; the pass
  gives AND), bitcoin-sv MIT (medium; the project uses its own Open BSV License), KDE kdevelop and
  assaultcube (10 and 8 ids, LicenseRef ids).
- Fill `your_value` for the 30 projects to get a measured error rate.

### The 58 disagreement projects of the rescan

- All 58 get a value: high 47, medium 9, low 2. None of them is ECL-2.0, AGPL-1.0 or BSD-4-Clause.
  The ECL-2.0 versus Apache-2.0 projects get Apache-2.0 (ScanCode exact match).
  BSD-3-Clause-Clear stays only for the 2 zama-ai projects (the title line of the text says "Clear").
- askalono agrees on 43, licensee agrees on 16 (licensee gives no answer on 31).
- 15 have a rescan strict value. The pass keeps the same ids for 5 (tporadowski redis, mendhak gpslogger,
  idempiere, locationtech jts, facebook zstd as "BSD-3-Clause OR GPL-2.0-only"). The others change, mostly
  to fewer and better ids (kdialog GFDL-1.3 to GPL-2.0-or-later, restinio BSL-1.0 to BSD-3-Clause as
  hand-checked in TOOLS.md).
- Probable errors to check: alphaville optimization-engine "Apache-2.0 AND MIT" (dual license),
  locationtech jts EPL-2.0 (the project is EPL-2.0 or EDL-1.0), sleuthkit BSD-3-Clause (low).
- No hand truth exists for these 58 either (the failure list in `license-scanners/README.md` does not say
  which scanner is right). The 3 projects hand-checked in TOOLS.md (odata, restinio, kid3) are right.

## 4. Open questions

### Question 1: a bare GPL id when no version notice exists

Data:
- 822 values have a bare GNU id (no `-only` or `-or-later`): GPL-2.0 295, GPL-3.0 258, LGPL-2.1 120,
  AGPL-3.0 81, LGPL-2.0 73, LGPL-3.0 62, GFDL-1.2 46. 228 of them are TOM NOASSERTION.
- `version_choice` (8,434 ok): not a GNU license 5,499; or-later 1,097; only 967; mixed 331; several 273;
  unknown 267.
- TOM 1.0.0 uses the bare ids for all GitHub values (GPL-3.0 848, GPL-2.0 545). SPDX lists the bare ids as
  deprecated.

Recommendation: keep the bare id. It says "version known, choice not known", and TOM 1.0.0 already uses it.
Do not write `-only` or `-or-later` without a notice. Say this in `docs/COLUMNS.md`.

### Question 2: REUSE, AND or ';' between files

Data:
- 251 projects have REUSE evidence. 240 values use AND, 0 use OR, 11 have one id. The values have 1 to 28
  ids (median 5).
- Against TOM: same ids 96 (TOM ';' list, pass AND), overlap 99, subset 18, superset 10, new value 28.
- 260 TOM 1.0.0 values use ';'. The pass gives SPDX expressions: 958 with AND, 359 with OR, 244 with WITH.

Recommendation: use AND, and change the 260 TOM ';' lists to AND in the new revision. AND is the SPDX
form for a package whose files have different licenses, and a parser can read it. One syntax in the
column is better than two. Say in `docs/COLUMNS.md` that AND means "different files have different
licenses".

### Question 3: prose "X or Y" read as AND, sent to a review list

Data:
- The rule joins the separate license names of one README notice with AND. 185 AND values come from a
  declaration (README 38, sub-folder 70, notice in a license file 64, manifest 9, notice file 4);
  114 low, 71 medium; 179 are TOM NOASSERTION.
- The same failure occurs without prose: 77 values are "Apache-2.0 AND MIT", 63 of them at high confidence
  from two root texts (`LICENSE-APACHE`, `LICENSE-MIT`). TOM has Apache-2.0 for 49. This is the common
  Rust dual license.
- When a manifest or notice gives the OR expression, the pass gets it: 305 values are "Apache-2.0 OR MIT".
- 10 Rust projects get only MIT (section 2). This is the same problem, in the other direction.

Recommendation: yes. Send these projects to the review list, and do not publish their AND value before the
check. For the next rule-layer version: (1) look for " or " / "either" between the two license names in
the notice line; (2) treat two root texts MIT plus Apache-2.0 without a notice as a review case, not as a
high AND.

### Question 4: low-confidence values with a confidence column, or NOASSERTION

Data:
- 304 low values; 285 of them are TOM NOASSERTION. Evidence: sub-folder license file 109, README 95,
  text 69, notice in a license file 16, other 15.
- Support is weak: licensee agrees on 15, askalono on 8.
- For comparison, medium values agree with a TOM value in 61% of cases (235 of 386); high values in 91%.

Recommendation: leave the 285 low values NOASSERTION in the `license` column (keep the TOM value for the
19 that have one). Publish the low candidates, with evidence, in a project-level side table of the license
pass. Add a confidence column (`high`, `medium`, `none`) for the published values. Users can then filter.

### Question 5: licensee gems installed with `gem install`

Data:
- licensee 10.1.0 and its 17 gems (among them nokogiri 1.19.7, a prebuilt x86_64 gem) are installed with
  `gem install` against the Ruby 3.4.8 of the Nix environment. They are not in the Nix closure. The kit
  stages them as one tarball and checks the version at setup.
- licensee is a second opinion only. It does not set a value. It changes the confidence of 60 projects
  (licensee disagrees and askalono disagrees or gives no answer). It gives an answer for 6,967 projects.

Recommendation: keep the result; do not run again. Record the gem names, the versions and the sha256 of
the tarball in the method document, and archive the tarball with the tools of the release. For the next
run, build licensee in Nix (a bundler environment with a lock file).

## 5. Proposal for the license column of the new TOM revision

Rule: publish the pass value when the confidence is high or medium and the project is not on the review
list. Hold the review list until a hand check. For low, none and held projects, keep the TOM 1.0.0 value
(NOASSERTION when TOM has none). Use SPDX expressions (AND, OR, WITH) and bare GNU ids when the choice is
not known.

| group | column value | projects |
|---|---|---:|
| high, not on the review list | pass value, same ids as TOM | 5,232 |
| high, not on the review list | pass value, TOM had fewer ids (dual licenses) | 394 |
| high, not on the review list | pass value, TOM NOASSERTION | 986 |
| medium, not on the review list | pass value, same ids as TOM | 219 |
| medium, not on the review list | pass value, TOM had fewer ids | 31 |
| medium, not on the review list | pass value, TOM NOASSERTION | 433 |
| high or medium, on the review list | keep the TOM value | 393 |
| high or medium, on the review list | NOASSERTION until the hand check | 380 |
| low | keep the TOM value | 19 |
| low | NOASSERTION | 285 |
| no pass value | keep the TOM value | 10 |
| no pass value | NOASSERTION | 67 |
| total | | 8,449 |

- NOASSERTION goes from 2,151 to 732 (1,419 new values). A hand check of the 380 held projects can add up
  to 380 more.
- Before publication: (1) hand-check a seeded sample of the 1,419 new values (for example 100 projects) to
  measure the error rate; (2) fix the two rule-layer errors of section 2 (MIT for Rust dual licenses,
  GPL for libvirt) and the AND/OR rule of question 3, then decide the rules again on the stored scans (no
  new scan is necessary); (3) remove `WITH Linux-syscall-note` outside kernel projects (33).
- The value of a project that TOM already has changes mostly in style (`-or-later`, exceptions, AND). Say
  this in the change log of the revision.

## 6. The fixed rules and the hand check (2026-11-08)

The rule layer is ctp `feat/license-scan` 0f9b8ad (not pushed); the ctp tests pass. The rules now read the
root key-file texts (the stored `stage.tar.gz`). The pass decided all stored scans again: no new scan,
7.6 min (`work/out/results.tsv`).

| rule | effect |
|---|---|
| Several license names in one notice are OR only when the notice lines say a choice ("X or Y", "either", "at your option", "dual licensed"; GNU "or later" phrases do not count). Else AND with the flag `review-and-from-notice`. A weaker notice match (score 50 or more) counts when a root license text confirms its id. | git-cliff, bottlerocket and alphaville optimization-engine give OR. 37 AND values are flagged. |
| MIT and Apache-2.0 root texts give "MIT OR Apache-2.0" when a README or manifest says the choice. Else `review-two-texts-mit-apache` (34), and `review-notice-drops-root-text` (22) for a notice that drops one of the two texts. | 6 of the 10 Rust projects that got only MIT now give "MIT OR Apache-2.0". 4 are held for review. |
| An LGPL text next to a GPL COPYING gives the LGPL when a notice names the LGPL. | The 3 libvirt projects give LGPL-2.1-or-later. |
| `WITH Linux-syscall-note` stays only in kernel projects (the project name has linux, kernel, lustre or amdgpu). | The KDE projects and clamav lose the note. |

After the fixes, with the publish rule of section 5 (`70_values.py`, `work/values/`):
- confidence: high 7,021, medium 1,056, low 303, none 69;
- NOASSERTION goes from 2,147 to 692; 1,455 projects get a new value; 344 TOM NOASSERTION projects are held for
  review;
- 3,524 files change their license value (1,455 new values, 2,069 changes of style or of a dual license).

Hand check: a seeded sample of 100 of the 1,455 new values (seed 20261108, stratified by confidence and
evidence kind; audit page on 127.0.0.1:2731). The user judged all 100 (the page refused the 100th save; the user reported it as right, and it was added to answers.tsv): 0 wrong (95% Wilson interval
0.0% to 3.7%). By confidence: high 0 of 68, medium 0 of 32. There are no
corrections (`work/audit/AUDIT_OK`, empty `work/audit/corrections.tsv`).
