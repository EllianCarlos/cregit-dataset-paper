# The line-against-token run (random sample of 250 projects)

This step compares the author that `git blame` gives to a line with the author that TOM gives to
each token of the line. The report is `../../token-vs-line-report.md` (at the root of the repository).
The step does not change TOM 1.0.0 or any published file.

## What is here

| Path | What it has |
| --- | --- |
| `tables/frame.tsv` | The frame: the 8,598 projects of TOM 1.0.0 with language, commit band, TOM rows, TOM pipeline time, clone URL and pinned commit. |
| `tables/plan-sample-random.tsv` | The draw: the first 250 projects of the permutation (seed 20261109, column `draw_rank`). |
| `tables/run/` | The result tables of the run after the repair: `per-project.tsv` (167 columns), `per-language.tsv`, `examples.tsv`, `blame-meta.tsv`, `limits.tsv.gz` (each file over a limit or cut at the run cap), `errors.tsv`, `failures.tsv`, `status.tsv`, `run-info.tsv`, `at-signs.tsv`, the two status files, and the analysis (`analysis.md`, `estimates.tsv`). |
| `tables/pilot-19/` | The pilot (19 projects, not random): its tables and the analysis of the same code. |
| `kit/` | The scripts of the run and their tests (below). |
| `pilot/scripts/` | The scripts of the pilot (they use the pilot persons database and the token plain blame). |

The tables hold project names, file paths, commit ids and counts. They hold no author name, no e-mail
address and no person id. The only at signs in `kit/` and `pilot/` are code syntax (Python decorators,
the regular expression of the scan, a marker word of generated code). `tables/run/at-signs.tsv` has the
at sign of one path written as `(at)`.

## The kit

| File | Use |
| --- | --- |
| `kit/blame_lines.py` | The three line blames of the files of one project, with a limit for each blame (1,800 s, 1,800 s, 600 s). A file over a limit keeps its other blames and goes into `limits.tsv`. |
| `kit/measure.py` | All levels and the causes for one project. Identity without a persons database. Writes `per-project.tsv`, `per-language.tsv`, `examples.tsv`. |
| `kit/tvl_run.py` | The driver: clones (retry with backoff), TOM copies checked against the root `SHA256SUMS`, one pool of git jobs for all projects (largest first), the measure step, the leak scan, the upload, the progress file, the run cap. |
| `kit/tvl_unit.sh`, `kit/tvl_start.sh` | The systemd unit of the run and its start. The unit stops the machine at the end. |
| `kit/tvl.conf` | The values: release root, limits, jobs, cap (14 h), memory. `BUCKET_NAME` is the name of your S3 bucket. |
| `kit/tvl_repair.py` | The repair of finished projects from their kept blame files. |
| `kit/R1-tvl-setup.sh`, `kit/B1-tvl-run.sh`, `kit/M1-tvl-status.sh`, `kit/K1-tvl-hold.sh`, `kit/S1-tvl-stage.sh` | The scripts of the machine (setup, start, status, hold or stop) and the stage builder. The scripts that launch the machine and send commands (account, network and instance ids) are not here. |
| `kit/plan.tsv` | The draw table in the form that the driver reads (a copy of `tables/plan-sample-random.tsv`). |
| `kit/draw_sample.py` | The draw. |
| `kit/analyze.py` | The estimates and the report tables from `tables/run/`. |
| `kit/test_tvl.py` | 12 fixture tests (a small git repository and a TOM-like file with known values): token values, identity without a persons database, a limit that keeps the other blames, the run cap, a commit without `personid`, and the leak scan. |

## Reproduce

1. **Tests.** `cd kit && python3 -I test_tvl.py` (needs git and DuckDB 1.5.5). All 12 tests must pass.
2. **Draw.** `python3 -I kit/draw_sample.py --frame tables/frame.tsv --n 250 > plan.tsv` gives the table
   `tables/plan-sample-random.tsv` (same rows, in the same order, in the columns of the table). The frame
   comes from the ledgers of the TOM build; its columns are described in the script.
3. **Analysis from the result tables.**
   `python3 -I kit/analyze.py --tables tables/run --plan tables/plan-sample-random.tsv --frame 8598 --out-md analysis.md --out-tsv estimates.tsv`
   gives `tables/run/analysis.md` and `estimates.tsv` (for `limits.tsv` unzip `limits.tsv.gz` first).
4. **Run again** (one machine, about US$50 and 13 h at the run's own speed):
   - Take a machine with 64 vCPU, 256 GiB and 3.5 TB or more of local disk (the run used one m6id.16xlarge,
     on demand, Amazon Linux 2023, shutdown behavior stop). Put the TOM 1.0.0 root in an S3 bucket
     (`ROOT` in `tvl.conf`) and set `BUCKET_NAME`, `ROOT_SUMS_SIZE` (the byte size of the root `SHA256SUMS`) and
     the prefixes.
   - Stage `kit/` in `s3://BUCKET_NAME/token-vs-line/tools/` (`S1-tvl-stage.sh` builds the stage and the
     list of sha256 values; put that value in `WANT_SUMS` of the setup and run scripts).
   - On the machine, as root: `R1-tvl-setup.sh` (disks, git, Python 3.12 with DuckDB, tools, check of the root
     list, tests), then `B1-tvl-run.sh` (starts the unit `tvl-run`). `M1-tvl-status.sh` shows the progress.
     `K1-tvl-hold.sh` with `ACTION=hold` keeps the machine up at the end; `ACTION=stop` ends the blames now.
   - The unit clones each project at its `run_commit` into `/data/tvl/pinned`, copies its TOM file, runs the
     three blames with 60 git jobs, measures, scans, uploads `results/<project>/` and, at the end, `tables/`. A
     progress file goes to `log/progress.json` every 5 minutes. The run stops the blames 50 minutes before the cap
     of 14 h, measures what it has, uploads, and shuts the machine down.
   - A project that failed (status ALERT) can be measured again from its kept blame files with
     `tvl_repair.py` (copy the files of `kit/` to `/data/tvl/repair`, set `REPAIR_PROJECTS` and run it with the venv Python; see its header).
5. **Tool versions** of the run: git 2.50.1, Python 3.12.14, DuckDB 1.5.5, on the machine. The tests and the
   analysis ran with git 2.56.0 and Python 3.14.7 on the work host. The kit sha256 of the stage that the machine
   ran is `fcb5325676a472b076a2c825f09494ab003824db44448c4e5b9abfc6cd90afff` (the files of that stage differ from
   `kit/` in `measure.py`, `tvl_run.py` and `test_tvl.py`: the two fixes below). The root `SHA256SUMS` of the TOM
   1.0.0 root that the run read has the sha256 `ea2052f7ce8b764d4e54a940d71f3fd8d04b827b2db08a4d2dc0c38f7dcbf48d`.

## The two fixes after the first end of the run

The run ended with two projects not uploaded: a commit that TOM credits but gives no `personid` stopped the
measure step of one project; the leak scan held the blame file of another because an origin path has an at sign
(a version directory). `kit/` has the fixed code: a credited commit without `personid` takes the e-mail path, and the
scan holds an e-mail address shape in any file and any line of a blame file that is not the exact blame shape
(a bare at sign goes to `at-signs.tsv`). `tables/run/run.ALERT.txt` and `repair.DONE.txt` are the status
files of the run and of the repair.

## Limits of this record

The blame files (1.2 GB, commit ids only) and the logs stay in the bucket of the run. The kit files that
launch the machine are not here. The tables of the first end of the run (before the repair) are not here.
