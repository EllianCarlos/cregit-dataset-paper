# runner: the scripts that ran the dataset build on EC2

These files are copies of the scripts that ran the dataset build (S7) on EC2 and on
this machine. The originals are in a local work directory (`~/s3-work`), which is not
a git repository. The copies keep the relative paths of the originals.

## Files

| Path | Contents |
|---|---|
| `INVENTORY.tsv` | Each file of the work directory: its role, if the build used it, the evidence, and the action (copy or skip, with the reason). |
| `ORIGIN.tsv` | Each copy: the source path, the source sha256, the copy path, the kind (`verbatim` or `parametrized`), the copy sha256 and the tokens. |
| `render.py` | Puts the account values back into the copies, or checks the copies against `ORIGIN.tsv`. |
| `runner.env.example` | The tokens, with placeholders. Copy it to `runner.env` (local only). |
| `ec2-batch*/`, `ec2-L*/` | The scripts of each run: machine setup, install, part feed, restart, probes. `scripts/remote*/` holds the files that the install scripts put on the machine (`/usr/local/bin` and the systemd units). |
| `census-watchdog/` | The local watchdog (a user timer). It restarts a lost spot machine. |
| `census-backup/` | The backup of the run state of the big machine. |
| `upload-*.sh` | The uploads of the run inputs to S3. The user ran them. |
| `dataset-v1/` | The merge of the 5,000+ layer (2026-10-16/17): the input list `inputs.tsv` (one row for each project: the run, the cregit commit, the S3 key and the sha256 of the run file), the upload scripts and the merge start and probe scripts (`M*.sh`). `tools/SOURCE` names the study commit of `final_merge.py` and `rewrite_meta_columns.py`. |
| `dataset-x1k/` | The runs of the 1,000-4,999 layer (2026-10-17 to 2026-10-23). `README.md` is the runbook. `L*.sh` launch the machines and the volumes; `scripts/` sets up, gates and starts the first machine; `scripts/w5/` and `scripts/w6/` are machine B (two machines); `scripts/a/` is machine A (the 11 long rows, on EBS volumes); `rust-split/` and `java-split/` are the extra machines of the blame of two long rows; `x2/` is the merge of the layer; `x3/` is the links of both layers. |
| `dataset-pathfix/` | The rerun of the projects of the two cregit path defects with cregit 14b8db4 (prepared 2026-10-20; 36 input rows, 35 run by the user's decision): the bundle stage, the inputs (`stage/inputs/`, with `seeds.tsv`, the commit of the first run of each project) and the machine scripts. |
| `dataset-v0-org/` | The organisation columns of version 1 (2026-10-21): the stage of the tools and the links, the upload, the machine setup and the start of `run_v0.py`. |

The four later kits (`dataset-*/`) were added on 2026-10-25. The copy skips the launch
records (`instances.txt`, `fleet/`), the outputs, the byte-code caches, the data inputs
(Parquet, DuckDB, the merge inputs), the tool bundles and the staged copies of files that the
study repository tracks (`INVENTORY.tsv` gives the reason of each skip). It also skips the
environment file of the volume ids of machine A (`dataset-x1k/scripts/a/vols.env`): the copy
step did not read it.

## The tokens

A copy of kind `parametrized` has a token `${RUNNER_NAME}` in place of an account
value: the bucket, the account id, the AWS profile, the region, the EC2 ids, the home
paths and the user name. All other bytes are equal to the original.
A copy of kind `verbatim` is equal to the original.

## Check the copies

    python3 -I render.py --check

Without `runner.env`, the check compares the verbatim copies with their source sha256.
With `runner.env`, it also renders each parametrized copy and compares the result
with its source sha256.

To get files that you can run, fill `runner.env` with your values, then:

    python3 -I render.py --out /path/to/work

The scripts expect the layout of the work directory. Some scripts give their paths as
`$HOME/s3-work/...`.
