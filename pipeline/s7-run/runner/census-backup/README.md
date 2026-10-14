# Census Parquet backup (2026-10-09)

User request: back up the finished Parquets to S3, regularly.

| where | how | S3 prefix |
|---|---|---|
| spot a / spot b | already built in: each project is copied when it finishes | `batch3/<a|b>/done/`, `batch5/<part>/done/`, `batch1rest/<part>/done/` |
| big EC2 ${RUNNER_EC2_BIG} | `census-backup.timer` (every 30 min, as root, instance role), script `/usr/local/bin/census-backup` (source `remote/census-backup`, installer `deploy-big.sh`) | `batch2/done/`, `batch3L/done/`, `batch4/p1..p3/done/`, `batch5L/done/` |
| this machine (batch 1, old code) | `backup_local.sh`, started by the user (Claude's `aws s3 cp` is denied) | `batch1/done/` |

Each project gets its `*-dataset.parquet`, `*.validated`, `*-persons.db`, `*-persons.xls`; then `OK` holds the
Parquet sha256 and the time. A project with `OK` is skipped. Sizes are checked against S3 before `OK`.
Each pass also copies `ledger.jsonl`, `metrics.tsv`, `resources.tsv` to `<run>/backup-ledger/`.

Local timer (run it yourself, with `!` in Claude Code):

    systemd-run --user --unit=census-backup-local --on-calendar='*:07/30' --setenv=HOME=$HOME --setenv=PATH="$PATH" ~/s3-work/census-backup/backup_local.sh

Logs: big EC2 `/data/logs/census-backup.log`; local `backup-local.log` here.
Check: `aws --profile ${RUNNER_AWS_PROFILE} --region ${RUNNER_AWS_REGION} s3 ls s3://${RUNNER_BUCKET}/ --recursive | grep -c '/done/.*/OK$'`
