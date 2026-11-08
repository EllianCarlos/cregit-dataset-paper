# The license pass of the revision

The revision of TOM 1.0.0 gives the `license` column SPDX license expressions from a scan of the
license files at the pinned commit of each project, and adds the side table
`organizations/project_licenses.parquet`. This folder gives the scan of the 8,449 projects of
TOM 1.0.0, the rules that make the column value, and the hand check of the new values.
`../release-passes/pass-5-revision/` writes the values into the files; it scans the 149 new
projects again on its machine with the same code and tools.

## The tools

| Part | Version |
| --- | --- |
| Scanner | ScanCode 32.5.0 |
| SPDX template diff | spdx tools-java 2.0.7, SPDX license list 3.29.0 |
| Second opinions | licensee 10.1.0, askalono 0.5.0 |
| The scan run | ctp branch `feat/license-scan` at `6b6efcf` (one cloud machine, c7i.16xlarge, 2026-11-08) |
| The rule layer that makes the values | ctp branch `feat/license-scan` at `0f9b8ad`: it decided all stored scans again, with no new scan |

No AI made the license values. The scanner and fixed rules made them.

## The scan

`run` status of the 8,449 projects: ok 8,434, error 10, fetch-error 3, no-key-files 2
(`REPORT.md`, section 1). The gate of the scan kit: 6 of 6 projects give their known value.
`REPORT.md` compares the pass with the values of TOM 1.0.0 and lists the cases for review
(`analysis/compare_tom.tsv`, one row for each project; `analysis/review.tsv`).

## The values (`70_values.py`)

The rule takes the value of the pass when the confidence is high or medium and the project is
not on the review list. Else it keeps the value of TOM 1.0.0 (a `;` list is written with AND),
or NOASSERTION. Result for the 8,449 projects (`work/values/summary.txt`):

- confidence: high 7,021, medium 1,056, low 303, none 69;
- NOASSERTION: 692 (TOM 1.0.0 has 2,147);
- 1,455 projects get a new value;
- 3,524 project files change their `license` value (the new values, and changes of style or of
  a dual license);
- 219 `;` lists are written with AND.

## The hand check

`80_audit_items.py` drew a seeded sample of 100 of the 1,455 new values (seed 20261108, stratified
by confidence and evidence kind; `work/values/sample100.tsv`). `audit_app.py` showed each item
on a local page: the value, the evidence files at the pinned commit and their links. The user
judged each value right or wrong (`work/audit/answers.tsv`).

Result: 0 wrong of 100 (95% Wilson interval 0.0% to 3.7%); high confidence 0 of 68, medium 0 of
32. There are no corrections (`work/audit/corrections.tsv` is empty). `work/audit/AUDIT_OK` is the
flag that the release kit needs before it writes the values.

Note: the page refused to save the 100th answer (`X11Libre__xserver`), because the tunnel to the
page closed. The user judged it right and reported it. That row of `answers.tsv` was added from
the report of the user, and its note says so.

## Files

| Path | Contents |
| --- | --- |
| `REPORT.md` | The report of the pass: coverage, the comparison with TOM 1.0.0, the review cases, the fixed rules, the hand check. |
| `60_report.py` | Makes the tables of `REPORT.md` and `analysis/`. |
| `70_values.py` | The rule of the column value, the fills of the value pass, the side table and the sample. |
| `80_audit_items.py`, `audit_app.py` | The items of the hand check and the local page. |
| `analysis/`, `work/values/`, `work/audit/` | The outputs above. |

The files are copies of the work folder of the pass (never in git). They have the bytes of the
files that ran, except `work/audit/items.json`: the copy has no field `excerpt`. That field held
excerpts of the license files of the projects. `80_audit_items.py` replaced the copyright lines
with `[line omitted]`, but other lines of a license text can name persons, so the copy drops
the field. The links `view` and `raw` of each file give the same text at the pinned commit. The
sha256 of the file that ran is `aa2f480e361d9e900dbb90478b54f816f7a2492a65bba22ca555db9878ced34a`.

| File | sha256 |
| --- | --- |
| `REPORT.md` | `8de52a84a9b3b2868dbbce6e084f79349ac0bb2a02847cf9dc46a3dc46bc54bf` |
| `60_report.py` | `8dce62a11f01bb489c10a81636db55713d34b02a5cb94a603820c393000453d5` |
| `70_values.py` | `e8f0cff21eb72994a2b3d42e95aa09d860457c03f847702aafb26b8d27551d43` (the file of the stage of the release kit) |
| `80_audit_items.py` | `206095d583ba50ec26901f5f34ec15a39818456f67822cfd629076d571f21233` |
| `audit_app.py` | `1981dc93493074c6c309b8acbd1b9a85579cfc646ad85ef0b0264960bbaa40fe` |
| `analysis/compare_tom.tsv` | `a1a7e9de229a965c5755a7ebf3fb14add908593837eadc631c52b80318f61810` |
| `analysis/review.tsv` | `2de6f5b63d2125b2ca17d9b8f61ca022fa54e9be00bc1136c83e66a9b259d32a` |
| `work/values/summary.txt` | `d7e0ed14e775633eb56e34137b7bee68704eb45156348d87f3c64a3d27e53e04` |
| `work/values/sample100.tsv` | `7c9473595aa009910662f3607cd6622ee64b72fe5f134c1b8cf77fbc50e42245` |
| `work/audit/answers.tsv` | `1216b21c6b9fbb64e09594235f1a694b4740207ce85ac0b70bd62b55cf6487ba` |
| `work/audit/AUDIT_OK` | `dfe794ae1e38f982ab30270a84c4efa2391ab3bf6c6b5d84781b3619d33c9913` |
| `work/audit/corrections.tsv` | `3860f54df07e6ea732cc8cbbd30572e5b73762524945864b57db635e1dae60c5` |

Not here (large files, in the storage bucket of the run):

| File | Bytes | sha256 |
| --- | ---: | --- |
| `license-scancode/run/license-scancode-1/out-projects.tar` (the stored scans of each project) | 481,341,440 | `f2ace4f1b4ecb3299489767bd4d33050e4682eafc883b7d1c18387aca5827b72` |
| `license-scancode/run/license-scancode-1/results/results.tsv`, `results.jsonl`, `scan.log`, `retry.log` (the raw results of the scan) | 1,840,977; 12,638,097; 616,092; 36,907 | not recorded |
| `license-scancode/tools/SHA256SUMS` (the staged list of the scan kit, 392 rows; the Nix closure of the scanner, the ruby gems and the jar of the template diff) | 50,177 | `285b432a6d75ee409ac9dd4c59e6984dd193f00b7b24050f26af5ea5588b4899` (the local stage of the kit; the object in the bucket has the same size, its sha256 was not read again) |

Also not here: the full value tables of `work/values/` (`decisions.tsv`, `license_column.tsv`,
`license_fills.tsv`, `project_licenses.tsv`). The release has the values in the project files and
in `organizations/project_licenses.parquet`. The scan kit scripts that started and watched the
machine stay out (they hold the run values).
