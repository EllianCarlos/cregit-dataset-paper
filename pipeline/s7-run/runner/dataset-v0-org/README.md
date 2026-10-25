# Runbook: dataset v0 with the organisation columns (ctp schema 2)

Prepared on 2026-10-19; inputs rebuilt from the final company database v4.5 on 2026-10-20. Not run.
No machine is started. The main session launches the machine after the user agrees to it.

## What the run does

`run_v0.py` runs `build_v0.py` on each of the 3,544 v1-raw files (`s3://.../dataset-v1/raw/`).
Each output file has the 67 columns of v1-raw without `firm_raw`, `firm` and `firm_source`, then
`firm_based_on_namespace`, `firm_based_on_domain`, `project_enterprise_driven` and
`project_enterprise_basis` (71 columns, ctp schema 2). The footer of each file holds
`ctp_schema_version`, `organisations_version` (v4.5) and `organisations_mapping_sha256`
(2fb053cd1ee7... for links-v4.5). The output goes to the new prefix
`s3://${RUNNER_BUCKET}/dataset-v0-org/`. The old v0 (`dataset-v0/`, database v3)
does not change. The x1k files get their columns in a second pass (section "x1k" below).

## Steps

1. Done on this machine (2026-10-20), with database v4.5 (`companies.v4.5.duckdb`):

       PY=${RUNNER_PROJECTS_TILDE}/cregit-workspace/census-local-a/ctp/.venv/bin/python
       W=${RUNNER_PROJECTS_TILDE}/cregit-workspace/companies
       cd ${RUNNER_PROJECTS_TILDE}/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection/s8-companies
       $PY -I build_links.py --organisations-version v4.5 --db $W/companies.v4.5.duckdb --out $W/links-v4.5
       $PY -I error_model.py            # reads the v4.5 links; writes $W/error-model (p_error)
       $PY -I build_organisations.py tables --db $W/companies.v4.5.duckdb --links $W/links-v4.5 \
           --error-model $W/error-model --out $W/organisations-v4.5 --private-out $W/organisations-v4.5-private

   A local test of 5 v1-raw files with the v4.5 links passed (`$W/v0-local-test-v4.5/`; the checks
   of step 7).
2. The tools that `build_stage.sh` stages (`s8-companies/build_v0.py`, `s8-companies/run_v0.py`,
   `s7-run/final_merge.py`) are committed in ${RUNNER_STUDY_REPO} and did not change, so the stage step
   accepts them. Commit the other changed files of 2026-10-20 before the release (list in the
   report of 2026-10-20), so that the release records the code that made the links and the tables.
3. Stage the tools and the v4.5 links (this machine, no AWS):

       L=${RUNNER_PROJECTS_TILDE}/cregit-workspace/companies/links-v4.5 bash ~/s3-work/dataset-v0-org/build_stage.sh

4. The user: `! bash ~/s3-work/dataset-v0-org/U-upload.sh` (expect `ALL OK`).
5. The main session launches the machine (see "Machine"), with `/data1`, `/data2` on the instance
   store and `/data/ctp/.venv` with duckdb, as on spot a. Then, through `ssm.sh`:

       I=<instance id>; H=~/s3-work/dataset-v0-org
       sed "s/^A=\${A:?.*}\$/A=$I/" $H/V1-start.sh > $H/V1-start.$I.sh    # ssm.sh passes no environment
       cd ~/s3-work/ec2-batch23/scripts && I=$I bash ssm.sh $H/V1-start.$I.sh 7200

   It downloads v1-raw (127 GB) and checks its `SHA256SUMS` (3,544 rows), downloads the inputs and
   checks them, and starts the unit `v0-org`: pass A (the 10 files with 195 M rows or more; 10 jobs
   x 56 GB), then pass B (the other 3,534 files; 88 jobs x 5 GB). A second start continues (done
   projects are skipped).
6. Progress: `V2-check.sh` through `ssm.sh`. At the end, `SHA256SUMS` with 3,544 rows is in
   `s3://.../dataset-v0-org/`. If a pass A file fails with "Out of Memory", run it again alone:
   `run_v0.py ... --only <project> --jobs 1 --memory-limit 200GB`.
7. Checks after the run (this machine, no AWS by the agent): the user or the main session copies
   5 small files of `dataset-v0-org/parquet/` to a local folder `R/parquet/`, links
   `R/organisations` to `organisations-v4.5`, runs
   `build_organisations.py views --root R` and
   `${RUNNER_PROJECTS_TILDE}/cregit-workspace/companies/v0-local-test-v4.5/check_v0_local.py` in `R`.
8. Release the machine (the user's yes).

## Machine and time

Recommended: one i4i.24xlarge (96 vCPU, 768 GiB, 4 x 3.75 TB NVMe), spot, ${RUNNER_AWS_REGION} (the bucket
region): the machine of the first v0 run. The two passes need 560 GB (pass A) and 440 GB
(pass B) of memory, and about 260 GB of disk (v1-raw and v0).

Estimate (from the first v0 run on spot a, 2026-10-16/17, and a local timing on 2026-10-19):

| Part | Basis | Time |
|---|---|---|
| Download v1-raw (127 GB) and the checks | S3 in the same region | 15-30 min |
| Pass A: 10 files, 2.47 B rows | 6 linux-size files took 57 min with 64 GB each (58,000 rows/s per job); gnuton__asuswrt-merlin.ng has 563 M rows | about 2.7 h (asuswrt), the others 1-1.3 h |
| Pass B: 3,534 files, 21.2 B rows | the first run wrote 75.5 GB of input in 97 min with 88 jobs (about 2.4 M rows/s); the new writer uses 8% less CPU (qt__qtbase, 26 M rows, 1 thread: 268 s against 292 s, peak 3.7 GB) | about 2.2-2.4 h |
| Total | | about 5.5-6 h |

Cost: about 6 h x the spot price (2.556 USD/h in ${RUNNER_AWS_REGION}a on 2026-10-09: about 15 USD). The
other option, the stopped big EC2 (${RUNNER_EC2_BIG}, m6id.24xlarge, 96 vCPU, 384 GiB,
on-demand 5.70 USD/h), needs pass A with at most 6 jobs x 56 GB: about 6.5-7 h, about 40 USD.

## x1k: the second pass (plan, not built)

The x1k files (projects with 1,000 to 4,999 commits) get the organisation columns after the
x1k-raw merge (step X2 of `~/s3-work/dataset-x1k/README.md`; output `s3://.../dataset-x1k/raw/`).
The author domains of x1k are not in `links-v4.5`: they are only in the x1k Parquet files in S3.
The per-author domain cache of v1 (`companies/cache/`) came from the local v1 files, and it holds
e-mail addresses. Thus the x1k links are built on the machine, from the x1k-raw files, and the
addresses never leave the machine.

1. On the v0-org machine (a third pass after pass B, or a new machine with the same setup):
   download `dataset-x1k/raw/` (parquet/, results.tsv, SHA256SUMS) to `/data1/x1kraw` and check
   `SHA256SUMS`.
2. Domain cache: `extract_domains_v1.py` reads only `merge-prelim/prelim.duckdb` today. It needs
   two options: `--inputs` (the results.tsv of final_merge.py, with the project and the file name)
   and `--cache` (the output folder). Then, on the machine:
   `extract_domains_v1.py --inputs /data1/x1kraw/results.tsv --cache /data2/x1k-cache --jobs 88`.
   The cache holds addresses: it stays on the instance store and goes when the machine goes.
3. Links: `build_links.py --organisations-version v4.5 --db companies.v4.5.duckdb --cache
   /data2/x1k-cache --sidecar project_meta.x1k.final.json --out /data2/links-x1k-v4.5`. The script
   stops if an output value holds the at sign. The rule of a domain (exact, then the longest suffix)
   and the rule of a namespace (owns rows only) depend only on the domain or the namespace and on
   the database, so a domain or a project that is in v1 and in x1k gets the same id in both.
   A new real domain with no row gets `independent`; a value with no real domain gets `unknown`.
4. Domain tokens without addresses: one Parquet with project, domain and tokens (from the cache)
   goes to a private S3 prefix (for example `dataset-x1k/org-work/`), for the error model and for
   the review of the new domains (the S8 method: a list of the new domains with the most tokens).
5. The x1k files: `run_v0.py --v1raw /data1/x1kraw --links /data2/links-x1k-v4.5 --out
   /data2/v0x1k/out --dest s3://.../dataset-x1k-org` (pass A and pass B by row count, as for v1;
   about 1.5-2 h for about 7,200 files).
6. This machine: download the x1k links and the domain tokens, merge them with links-v4.5 (a new
   step: the union of the domain links and of the project links; a domain in both must have the
   same id), run `error_model.py` on the union, and run `build_organisations.py tables` on the union
   (organisations-v4.5 gets the x1k domains and projects).

Open (decide before step 5): the files of v1 carry the mapping hash of links-v4.5, and the files of
x1k carry the hash of links-x1k-v4.5. The view `stale_files` compares each file with the one hash of
`release_info`. Choose one: (a) `release_info` holds the hash of each part and `stale_files` accepts
both (a change in `build_organisations.py`); or (b) write the v1 files again with the union of the
links (another v0 pass, about 5.5-6 h). The ids in the v1 files are the same in both cases (see
step 3); only the hash differs. Recommended: (a).

## Files here

| File | Who runs it | What |
|---|---|---|
| `build_stage.sh` | main session | tools (committed) and links of one version to `stage/` |
| `U-upload.sh` | the user | `stage/` to `s3://.../dataset-v0-org/inputs/` and a check |
| `V1-start.sh` | main session, on the machine | v1-raw download, the unit `v0-org` (two passes) |
| `V2-check.sh` | main session, on the machine | progress |
