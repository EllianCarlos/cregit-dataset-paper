# The value fixes of pass 2

These scripts made the inputs of the language and license fills and of the two side tables of
pass 2 (`../pass-2/`). They ran on 2026-11-07 on the run host, on the source root and the tokei
measure. The tables hold project names, hosts, commits, language names, license ids, scanner
ids and license file names only. They hold no person data and no file text.

## Files

| File | What it does |
|---|---|
| `00_base.sql` | Makes `work.duckdb`: one row for each project of the source root (the project-level columns, the clone URL, the pinned commit) and the organization table. |
| `dw.sh` | Runs a SQL file against `work.duckdb` (DuckDB 1.5.1, 6 GB memory). |
| `shell.nix` | The tools of the license scan: licensee, askalono, ScanCode, git, Python with DuckDB. |
| `prepared/p4_languages.sql` | `prepared/project_languages.parquet` (one row for each project: the host language, the tokei language, the tokei language after the Linguist name map, the share) and `prepared/language_fill_gaps.tsv`. |
| `prepared/p1_scan_outside_github.py` | The license scan of the projects outside GitHub with `NOASSERTION`: a depth-1 fetch of the pinned commit, then licensee (confidence 98 and 80), askalono and ScanCode on the root license files. It writes file names and scanner ids only. |
| `prepared/p1_summarize.py` | Classifies the scan results and writes `prepared/license_fill_outside_github.tsv` and its summary. |
| `prepared/p3_stratum_side_table.sql` | `prepared/project_labels.parquet`: the label rule of the selection run again with one added fact from the kind of the namespace owner. |
| `prepared/language_fill_gaps.tsv` | 180 projects with an empty `language` that tokei measured, with the proposed value. |
| `prepared/license_fill_outside_github.tsv` | 222 projects outside GitHub with `NOASSERTION`: the scanner ids, the root license files, the class and the proposed value. |
| `prepared/license_fill_outside_github.summary.md` | The counts by class, by host and by proposed value. |
| `prepared/project_languages.md` | The columns and the checks of `project_languages.parquet`. |

The fills of pass 2 take these rows on the projects of TOM: 161 language fills (the 159
projects of the keep list in `language_fill_gaps.tsv` and the 2 added projects) and 149 license
fills (the classes `licensee-98` and `licensee-98-partial`: 147 projects of the keep list and the
2 added projects). `tom2_tools.py prepare` of `../pass-2/` joins them with the keep list into
`../pass-2/inputs/fills.tsv`. It also takes the two Parquet tables to the projects of TOM and
adds the 2 projects of the HTTPS retry.

## Changes in the copies

The copies differ from the files that ran only in the input paths. The inputs that are not in
this repository are now in a folder `input/`:

| File | sha256 of the file that ran | sha256 of the copy | Replaced |
|---|---|---|---|
| `00_base.sql` | `96bb8a077bd1` | `b7d9333ec344` | `input/project_values.parquet` (the project-level values of each file), `input/MANIFEST.tsv` (the `MANIFEST.tsv` of the source root), `input/organizations.parquet` (the organization table of the source root) |
| `prepared/p4_languages.sql` | `eb56049c80ad` | `0080831dd701` | `input/tokei-measure.jsonl` (`measure.jsonl` of the tokei run, 11 MB) |
| `prepared/project_languages.md` | `b683515c2b5c` | `e9e86869219d` | the same path in the text |

The other files are the files that ran: `dw.sh` `ec7239d97358`, `shell.nix` `242f88018d2d`,
`p1_scan_outside_github.py` `2d4309be4618`, `p1_summarize.py` `53a989d8743c`,
`p3_stratum_side_table.sql` `1f5476b54628`, `language_fill_gaps.tsv` `f868aa813dfa`,
`license_fill_outside_github.tsv` `1dcc5a119753`, the summary `ea93ea536c2e`.

Not here: the Parquet outputs (`prepared/project_languages.parquet` `55cc74430b44`,
`prepared/project_labels.parquet` `3c8da7825256`; the subsets of pass 2 are in the root), the
raw scan lines, the logs, the scan of the GitHub projects with more than one root license file
(not used: those projects keep `NOASSERTION`), and the report of the decision with its queries.

## How to run

```sh
cd steps/release-passes/value-fixes
mkdir -p input   # put the inputs of the table above here
./dw.sh 00_base.sql
./dw.sh prepared/p4_languages.sql
./dw.sh prepared/p3_stratum_side_table.sql
nix-shell shell.nix --run 'python3 -I prepared/p1_scan_outside_github.py INPUT.tsv scan.jsonl WORK 6'
python3 -I prepared/p1_summarize.py scan.jsonl INPUT.tsv prepared/license_fill_outside_github.tsv \
  prepared/license_fill_outside_github.summary.md
```

`INPUT.tsv` has the columns `project`, `display`, `host`, `clone_url`, `run_commit` (the 222
projects of `license_fill_outside_github.tsv`). The scan uses the network (git fetch of one
commit per project). `dw.sh` names the DuckDB binary by its Nix store path.
