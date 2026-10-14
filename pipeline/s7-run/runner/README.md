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
