# Steps after the build

The dataset build (`pipeline/s7-run/`) wrote one Parquet file for each project. The steps
here made the published files from those files, or give the evidence behind numbers in the
documents of the release. Each step has one folder with a README: what the step does, which
run used it, how to run it, and what is not here.

| Folder | What it does | Changes the published files |
|---|---|---|
| `organizations/` | The organization database (v4.9), the domain and namespace links, the column write, the organization tables of the release, and the error model. | yes |
| `final-write/` | The one write of each project file: the organization columns and the pseudonyms. | yes |
| `release-root/` | The release root: the project files, the organization tables, the documents, `MANIFEST.tsv`, `SHA256SUMS` and `ledgers.parquet`. | yes |
| `reencode/` | The record of the re-encode of the project files with pyarrow (the bytes change, the data does not). | yes |
| `release-passes/` | The three release passes of TOM 1.0.0: the subset of the tokei rule, the column changes (71 -> 61 -> 53 columns), the value fills, the side tables, the uploads to Hugging Face. Also `tools/fill_release.py` of the TOM root, the value-fix scripts and the proof of the direct 53-column write. | yes |
| `error-model/` | The numbers of `docs/ERROR.md` of the release. | no |
| `language-selection/` | The evidence for the language rule of the selection. | no |
| `linux-validation/` | A comparison of the organization shares of the Linux kernel with published sources. | no |

The order of the steps: `organizations/` (database and links), `final-write/`,
`release-root/`, `reencode/`, then the root build again on the re-encoded files
(`release-root/`). That root (10,754 project files, 71 columns) is the source root of the
release passes. Then `release-passes/`: pass 1, pass 2 and pass 3 make the root of TOM 1.0.0
(8,449 project files, 53 columns). The other three folders hold evidence only. The keep list of
pass 1 comes from `language-selection/tokei/`.

## How the files got here

- Files of the study repository come through the sync (`sync/`, see the top README). The
  source id `study-s8` copies the files of the organization step at study commit
  `561edc9fdc32` into `organizations/study/`. That commit holds the files that ran: the
  study has later commits of them (a spelling rename). `sync/patches.tsv` replaces one line
  in two of these files: a default path that named the private study repository.
- Files that were never in git (the run kits and the work folders of the run host) are
  copied directly. `tools.lock` gives, for each script, the sha256 of the file that ran when
  the run recorded it, and the sha256 of the copy here when the two differ. A copy differs
  only where a default path of the run host became an option or an environment variable.
- The kits of the release passes were never in git either. Each pass has the staged list of its
  machine (`SHA256SUMS`, pinned in its start script). `release-passes/KITS.tsv` maps each row of
  each list to its copy here. The configuration files and the start scripts differ from the
  staged files only in the bucket name (a placeholder). `release-passes/check-kits.sh` checks
  the copies.
- Not here: the scripts that started, watched or stopped cloud machines, sent commands to
  them or uploaded files, the progress monitors, and the scripts of the archive record. The
  run values (the storage bucket, the account, the machines) stay out of this repository.

## Tests

`make test` runs the tests of these folders that need no data. Some tests need inputs from
outside the repository (a pseudonymizer checkout, the organization database, the release
tool `fill_release.py`); they skip when the input is missing. The README of each folder
names the environment variables that give these inputs.
