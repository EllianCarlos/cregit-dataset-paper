# Kit x3: the extension domain cache, the merged links and the PLAIN-BLAME count

Prepared 2026-10-23. Nothing in this kit ran on AWS. No instance, no upload. The main session
launches; the user uploads (U1).

## What the machine does

One spot machine (`Run=x1k-links`, `Name=dataset-x1k-links-N`) does three things:

1. It makes the per-project domain cache of the extension (7,209 files of `dataset-x1k/raw/`) and,
   again, of v1 (3,544 files of `dataset-v1/raw/`). The caches hold e-mail addresses. They stay on
   the machine and end with it.
2. It builds the merged links: one `build_links.py` run over both caches and both sidecars, with
   company database v4.6. This gives one mapping hash for all 10,753 files. Before that, a v1-only
   run must give the links of `links-v4.6` of this host (the gate).
3. It counts the PLAIN-BLAME files of the extension from the pipeline logs in S3.

Only files with no address come back (`s3://B/dataset-x1k/links-work/<run>/`). Each file is checked
for the at sign on the machine before the upload (`x3_report.py no-at`) and again here (F1).

## Design decisions (and why)

- **The links run on the machine.** `build_links.py` needs the e-mail column. The table `au`
  groups by (project, email) for the three enterprise heuristics: sdtc takes the 3 authors with the
  most tokens (tie-break by email); mcpc and mcve count authors. A domain-only cache can give
  `domain_links` and `firm_based_on_namespace`, but not `project_enterprise_driven` or
  `project_enterprise_basis`. So the cache with the addresses must be where the links are built.
- **v1 is extracted again on the machine.** The user decided one mapping hash for all files: the
  links of v1 and the extension in one set. A merge of two link sets on this host would need new
  code for the statistics of links.json. The local v1 cache holds addresses, so it must not go to
  S3 from this host. The machine reads the v1 files that are in S3 already (127 GB, about 5 more
  minutes). The v1-only run is then a strong check: its mapping hash must be `2fb053cd1ee7`
  (links-v4.6) and its three tables must have the same rows.
- **Merged = one run.** A domain link depends only on the domain and the database. A project link
  depends only on the rows of its project. So the v1 rows of the merged links are the v1 links
  (checked: `compare-links --subset`), and the mapping hash changes only because the extension
  rows join it.
- **New domains.** A real extension domain with no row in the database gets `independent` (the
  fallback of `build_v0.py`) until a review. `new_domains.x1k.tsv` lists the ones that v1 does not
  have, with token shares, for the S8 review (audit pages, DNS study).
- **PLAIN-BLAME rules** (the user, `../M0-plainblame-count.sh`). The column `source` of
  `dataset-x1k/raw/results.tsv` selects the rule: `x1k-b` the newest log of `done-full/<p>/`;
  `x1k-a` all logs of `done-full/<p>/`; `x1k-pathfix` the newest log of `done-pathfix/<p>/` (that
  rerun made the Parquet of these rows). The extra machines add `rust-split/out/<k>/plainblame.log`
  to awslabs__aws-sdk-rust and `java-split/out/<k>/plainblame.log` to aws__aws-sdk-java (all 7 of
  these files are 0 bytes in S3 on 2026-10-23).
- **PLAIN-BLAME counts distinct files** (the main session, 2026-10-23). cregit prints
  `PLAIN-BLAME <file> after <N> s of -C100` (or `after git exit 128 of -C100`, 23e4ccb). The count
  of a row is the number of distinct file paths of these lines: for `x1k-a` the union over all logs
  of the row and the extra-machine logs, so a file that falls back in two attempts counts once.
  The line count stays in a second column (`plain_blame_lines`), so both are visible.

## Files

| File | Where it runs | What it does |
|---|---|---|
| `S0-x3-stage.sh` | this host, no AWS | builds `stage/` (the 6 tools, `companies.v4.6.duckdb`, `ref-links/` = W/links-v4.6) and prints `WANT_SUMS`, the sha256 of `stage/SHA256SUMS` |
| `U1-upload-x3.sh` | the user | uploads `stage/` to `s3://B/dataset-x1k/links-tools/` (checks the sha256 before, the sizes after) |
| `L1-launch-x3.sh` | main session | the spot fleet (copy of `../x2/L1-launch-x2.sh`; Run=x1k-links; refuse list; `DRY_RUN=1` for the EC2 DryRun) |
| `ssm-x3.sh` | main session | `../scripts/ssm.sh` for the x3 machine only; adds `export X3_RUN=<Name>` |
| `R1-x3-setup.sh` | machine, root | instance store at /data1.., tools with sha256 check, venv Python 3.12 + duckdb 1.5.5, S3 concurrency 32 |
| `M1-x3-start.sh` | machine, root | checks, then the unit `x1k-links` (systemd-run) that runs `tools/x3_run.sh` |
| `x3_run.sh` | machine (unit) | the run: downloads + sha256, extraction, cache check, v1 gate, merged links, reports, PLAIN-BLAME, at-sign check, upload, DONE/ALERT, shutdown |
| `M2-x3-check.sh` | machine, read-only | progress: downloads, cache files, log count, gate lines, DONE/ALERT, memory, disk |
| `F1-x3-fetch.sh` | this host (user or main session) | after DONE: downloads `links-work/<run>/` (no cache, no dataset file) to `W/x1k-links/<run>/` and checks the at sign again |
| `x3_report.py` | machine (and tests) | `inputs`, `check-cache`, `compare-links`, `domains`, `no-at` |
| `x3_plainblame.py` | machine (and tests) | the PLAIN-BLAME table and summary |
| `test/test_x3.py` | this host | 7 tests of the two Python tools (with `build_links.py`) |

Tools of `s8-companies` (${RUNNER_STUDY_REPO}, changed in this work, committed as 8372d93 by the main session):
`extract_domains_v1.py` (new `--inputs TSV`, `--cache DIR`) and `build_links.py` (`--cache` and
`--sidecar` can repeat). New test file `test_extract_domains_v1.py`; 3 new tests in
`test_build_links.py`. With one cache and one sidecar, `build_links.py` gives byte-identical
outputs and the same links.json as before (checked on the v1 cache and v4.6: mapping
`2fb053cd1ee7`, the 3 output sha256 equal, all links.json keys equal).

## Steps

Set `K=~/s3-work/dataset-x1k/x3`.

0. The s8-companies changes are in ${RUNNER_STUDY_REPO} 8372d93 (`stage/SOURCE` records it; `SOURCE` is
   not in SHA256SUMS). If a tool changes: `bash $K/S0-x3-stage.sh`, put the new `WANT_SUMS` in
   R1, M1 and U1.
1. User: `! bash ~/s3-work/dataset-x1k/x3/U1-upload-x3.sh`
   Expect: `uploaded 13 files (... B) to s3://.../dataset-x1k/links-tools/` and `U1-x3 done`
   (11 files of SHA256SUMS + SHA256SUMS + SOURCE; about 5 MB).
2. Main session (needs the user's OK to launch):
   `NAME=dataset-x1k-links-1 MAX_TOTAL_PRICE=2.50 bash $K/L1-launch-x3.sh`
   Expect: `refuse list before: ...`, then `i-... <type> subnet-...`, `refuse list after:` the same,
   one new line in `../instances.txt`.
3. Wait about 3 minutes for SSM. Then `I=<id> TAILN=30 bash $K/ssm-x3.sh $K/R1-x3-setup.sh 1800`
   Expect: the disk lines, `tools ok: 11 files, SHA256SUMS 7dba806bb9e3`, `python 3.12.x duckdb 1.5.5`,
   `R1-x3 done`.
4. `I=<id> TAILN=20 bash $K/ssm-x3.sh $K/M1-x3-start.sh 600`
   Expect: `== ... jobs <nproc-2> x <n>GB ...`, `START ... unit x1k-links`, the unit `active (running)`,
   `M1-x3 done`.
5. Progress: `I=<id> TAILN=30 bash $K/ssm-x3.sh $K/M2-x3-check.sh 300`
   Expect in order: `v1: downloaded ...; cache 3544 of 3544`, `x1k: ... cache 7209 of 7209`,
   gate lines `... -> OK` and `mapping_sha256: got 2fb053cd1ee7, ref 2fb053cd1ee7 -> OK`, then
   `x1k-links DONE run dataset-x1k-links-1 ...: all steps ok`. Or poll S3 (read-only):
   `aws s3 ls s3://${RUNNER_BUCKET}/dataset-x1k/links-work/dataset-x1k-links-1/`
   for `DONE` or `ALERT`. After DONE the instance terminates in 5 minutes.
6. User or main session: `bash $K/F1-x3-fetch.sh dataset-x1k-links-1`
   Expect: `no-at OK (about 24 files)`, the DONE line, the gate line, `merged: 10763 projects, ...
   domain links, mapping <new hash>`, `fetched to ${RUNNER_PROJECTS_TILDE}/cregit-workspace/companies/x1k-links/dataset-x1k-links-1`.

On ALERT: the machine stays up (cost about $0.8/h). Run M2 and read `ALERT`: it names the failed
steps. The outputs are in S3 if no file held the at sign. Fix, then either start M1 again (the
downloads and the cached projects are skipped) or end the machine (the main session, with the
user's OK). A spot interruption ends the machine: launch `dataset-x1k-links-2` and start again.

## Outputs (`links-work/<run>/`; no address in any of them)

- `links-merged/`: `domain_links.parquet`, `project_links.parquet` (10,763 rows = 3,548 v1 sidecar
  rows + 7,215 x1k sidecar rows), `enterprise_audit.parquet`, `links.json` (the merged
  mapping_sha256; inputs lists both sidecars and both caches). These are the links for the X4
  rewrite of all files (v1 again, and the extension) and for `build_organisations.py tables`.
- `gate-v1.txt`, `links-v1check.links.json`, `links-v1check.stdout.json`: the v1 gate.
- `check-merged.txt`, `links-merged.stdout.json`: the merged links and their statistics.
- `check-cache.v1.txt`, `check-cache.x1k.txt`, `extract.v1.log`, `extract.x1k.log`.
- `domain_counts.x1k.parquet`: per project and domain: tokens, commits, authors (counts).
- `new_domains.x1k.tsv`: real extension domains that v1 does not have and with no link row
  (value `independent` until a review): projects, tokens, commits, authors, token_share_x1k,
  token_share_all, top_project.
- `new_domains_linked.x1k.tsv`: extension domains new to v1 that have a link row (suffix, rule,
  exact): the id, kind, match, tokens, token share.
- `new_namespaces.x1k.tsv`: (host, namespace) of the extension sidecar that v1 does not have and
  with no `owns` value: projects, tokens.
- `domains.x1k.json`: counts and token shares (value classes organisation / free-provider /
  independent / unknown of the extension tokens, new-domain shares, namespace owners, enterprise
  projects).
- `plainblame.x1k.tsv` (7,209 rows: project, source, rule, log_dir, logs, newest_log,
  plain_blame_newest, plain_blame_newest_lines, plain_blame_all_logs, plain_blame_all_logs_lines,
  plain_blame_extra, plain_blame_extra_lines, plain_blame, plain_blame_lines; each `plain_blame*`
  without `_lines` is a count of distinct files), `plainblame.x1k.json` (distinct files and lines
  by source, the rows with no log), `plainblame.x1k.txt`.
- `no-at.txt`, `run.log`, `DONE` or `ALERT`.

## Time and cost (estimate)

Measured inputs: v1 local extraction 3,544 files in 3,274 job-seconds (3 jobs x 2 threads); the
x1k raw files are 36.81 GB (v1 raw 127.13 GB); the x2 spot i4i.24xlarge cost $2.33/h on 2026-10-23.

| Part | Estimate |
|---|---|
| launch + SSM ready | 3-5 min |
| R1 (dnf, pip, tools) | 3-5 min |
| downloads 164 GB (concurrency 32) + parallel sha256 | 5-10 min |
| extraction v1 + x1k (30 jobs on 32 vCPU, largest files first) | 5-15 min |
| v1 gate + merged links + reports | 2-5 min |
| PLAIN-BLAME log sync (in parallel with the above) + count | 5-15 min, hidden |
| upload + shutdown delay | 6 min |
| **total instance time** | **about 30-60 min** |

Cost: i4i.8xlarge spot about $0.75-0.85/h (a third of the i4i.24xlarge price; the fleet picks the
cheapest of the 4 types) -> **about $1**; with a 2.50 $/h cap the worst case is under $3. EBS (200
GiB gp3, 1 h) about $0.02; S3 requests (about 120,000 LIST/GET) about $0.05; S3 to EC2 in ${RUNNER_AWS_REGION}
has no transfer cost. An ALERT that waits costs about $0.8/h until someone ends the machine.

## Local tests (done 2026-10-23, no AWS)

- `extract_domains_v1.py --inputs --cache` on the five checked v1 files of
  `W/v0-check-v4.5/parquet/`: each project has the same group rows as the v1 cache (0 rows only
  in one side), the same tokens and commits per domain, and per domain sum(commits) = the
  distinct commits of the source file.
- `build_links.py` on the v1 cache with v4.6: byte-identical outputs, the same links.json.
- pytest: s8-companies 391 passed; `test/test_x3.py` 7 passed (one test: a machine A file that falls
  back in two attempts, and a file on an extra machine too, counts once).
- Rehearsal of `x3_run.sh` with a fake `aws` (a local folder as the bucket): 2 checked files as v1,
  3 as the extension (one per source), fake logs. Run 1 found a defect (empty sha256 chunks when
  there are fewer files than jobs; fixed) and showed the ALERT path (the rest ran, outputs went up,
  no shutdown). Run 2 and 3: DONE, gate OK, merged links OK, PLAIN-BLAME rules OK, no at sign in 21
  outputs; runs 2 and 3 give the same files. Run 4 (distinct-file count): DONE, the same merged
  links, the x1k-a row 2 distinct files from 4 lines. Folder:
  `${RUNNER_PROJECTS_TILDE}/cregit-workspace/agent-runs-20261023/x1k-links/test/rehearsal/` (its `machine*/work/*/cache`
  and `test/x1k/cache` hold addresses of the 5 check projects: local only; delete them when the
  review of this kit is done).

## After DONE (not in this kit)

1. `build_organisations.py tables --links W/x1k-links/<run>/links-merged ...` (local; no address).
2. The review of `new_domains.x1k.tsv` and `new_namespaces.x1k.tsv` (S8 method); a database v4.7
   if rows change; then this kit again with `OV=v4.7` and a new `DB=` (S0, U1, M1 defaults).
3. `error_model.py` with the extension; the two-phase audit (extension strata).
4. X4: `run_v0.py` over v1 (again) and the extension with the merged links (the v0-org kit with new
   inputs), so that every file has the merged mapping hash.
5. LIMITATIONS: the PLAIN-BLAME counts of `plainblame.x1k.json` (time limit / exit 128 table).
