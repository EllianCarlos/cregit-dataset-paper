# The run of the new projects of the revision

The revision of TOM 1.0.0 adds the 149 new projects of `../selection-funnel/`. This step builds
their project files with the tool chain of TOM. The output files have the published form of TOM
1.0.0 (53 columns, ctp schema 3, the TOM Parquet form). `../release-passes/pass-5-revision/`
then adds them to the root.

The run used three cloud machines (on demand, one kit): machine A (`tom-add-159-1`, the bulk of
the list), machine B (`tom-add-159-2`, the 3 long projects) and machine C (`tom-add-159-3`, the 7
GitLab projects that decision 2 of the funnel brought back). Each machine ran
`ta_run.sh` as one systemd unit. The kit name counts the 159 candidates of the funnel before the
copy check; the release keeps the 149 projects of `new_projects.tsv` and drops the files of the
removed candidates.

Status of this record: machine C ended DONE (7 project files). Machines A and B were in pass 2
when this record was written. The release kit waits for `status/run.DONE` of each machine.

## The tool chain

| Part | Version |
| --- | --- |
| cregit | fork, branch `fix/schema-3-bare-cr`, commit `c65f1e7`: `feat/schema-3` `8d60a8f` (the 49 cregit columns of ctp schema 3; `git blame -C100` with a limit of 3,600 s for each file, then plain blame) + `fbbf42f` (the `.blame` lines split on LF only: a bare CR stays in its token, `token_index` has no gap) + `c65f1e7` (`23e4ccb` cherry-picked: plain blame after a git exit 128 of `-C100`, as for 1 project of TOM) |
| srcML | the build with the non-termination patch (`tools.lock`, rows `srcml`) |
| ctp | branch `feat/schema-3-run`, commit `a9f0bed`: the run, the schema 3 write with the organization columns and the pseudonyms |
| writer of the published files | `reencode_parquet.py` of ctp `c2a8432` with pyarrow 26.0.1: Parquet 2.6, data page V1, ZSTD 19, row groups of 1,000,000 rows, no page index, Bloom filters on `file_path`, `token_value`, `source_text` and `personid` |
| links | the link step of TOM: `extract_domains_v1.py`, `build_links.py` and the organization database 1.0.0 (build tag `v4.9`) |
| license | licensee 9.18.0 at confidence 98 (the version of the license fills of TOM 1.0.0), on the root license files and package files at the pin |
| pseudonyms | `pseudonymize.py` of ctp `a9f0bed`, with a new random salt for this batch |

`tools.lock` has the rows of these commits.

## What a machine does (`ta_run.sh`)

The steps: `precheck` (machine B only), `fetch`, `inputs`, `license`, `fill`, `gate`, `pass1`,
`links`, `pseudo`, `pass2`, `reencode`, `check`, `tables`, `upload`, then the end.

1. Pass 1: `ctp.py run --schema 3` at the funnel pin, with the link tables of TOM and with no
   salt. These files hold the real identities. They stay in the private folder of the machine.
2. Links: the link step of TOM on these files. A domain or project row that is also in the
   tables of TOM must be equal, else the run stops.
3. Pseudo and pass 2: the batch gets a new random salt on the machine. The private registry of
   TOM is read for its token columns only: a new token equal to a token of TOM stops the run.
   Then `schema3.py write` of ctp writes the file again from the private file (without its 4
   organization columns) with the salt. The generator does not run again.
4. Reencode: the writer of the published files, with its content check.
5. Check: the copied columns are equal to pass 1, row for row; each identity column is a
   function of the private value; `schema3.py check`; `validate.py`; the Parquet form gate
   (`ta_tools.py shape`) against the TOM file of the gate project.

At the end the machine deletes the salt file and stops.

## The gate

Each machine first builds `tio__tio`, a project of TOM 1.0.0. A plain write of pass 1 must be
equal to its TOM file in every column except the pseudonym columns. After pass 2 and the
re-encode, each pseudonym column must be a bijection of the TOM column, every other of the 53
columns must be equal, the footer must be equal except the two pseudonymization keys, and the
Parquet form must be the TOM form. The gate passed on all three machines (status `gate.DONE`).

## Defects of the kit found in the run

These are defects of the run scripts, not of the data. Each one stopped a step; the fix is
given. The fixes on the machines changed the staged files, so the files that ran are the
staged files plus these patches.

- `results/` and `/data/ta` were owned by root. The precheck of machine B and the gate of machine A
  write there as `ec2-user`, so they stopped. Fix on the machines: `chown ec2-user` of the two
  folders. The stage of machine C has the fix in `ta_run.sh` (`kit/ta_run.c.sh`), and a rerun
  takes a pass-1 file that is already in the private folder.
- `compare_tom.py`: the bijection check used `coalesce(l, chr(0))`, which fails on a BOOLEAN
  column. Fix on all machines: `coalesce(CAST(l AS VARCHAR), chr(0))` (and the same for `r`).
  `patched/compare_tom.py` is the patched file.
- DuckDB writes its temporary folder `.tmp` into the working directory. The working directory of
  the systemd unit is `/`, which `ec2-user` cannot write, so the links step of machine B
  stopped. Fix on machines A and B: the folders `/.tmp` and `/data/ta/.tmp`, owned by
  `ec2-user`.
- The write of pass 2 (`ta_tools.py write`) ran several files at a time in a ThreadPoolExecutor,
  with DuckDB in the same process. DuckDB stopped with a segmentation fault. Fix on machines A
  and B: the COPY of each file runs in a subprocess (`patched/ta_tools.py`). Later the parallel
  schema 3 writes stopped with crashes in libc. Fix: `WRITE_JOBS=1`.
- An ALERT stops the run and removes the salt of the batch. This is by design. So after an ALERT
  in pass 2, pass 2 runs again from the start with a new salt (the old outputs of pass 2 are
  moved aside first).

## Files

| Path | Contents |
| --- | --- |
| `kit/ta.conf`, `kit/ta_start.sh`, `kit/ta_run.sh`, `kit/ta_tools.py`, `kit/compare_tom.py`, `kit/drive.py` | The files of the stage of machines A and B (staged list `kit/SHA256SUMS.ab`, sha256 `bb610035fcb7a6c4db47816a8185f009ab7f6aaaca3c570ad58ec4f1809806b8`, note `kit/SOURCE.ab`). |
| `kit/ta.c.conf`, `kit/ta_run.c.sh` | `ta.conf` and `ta_run.sh` of the stage of machine C (staged list `kit/SHA256SUMS.c`, sha256 `ca22ffbc734bf41ca3a49cd766c287b06f347b53fefedfef83bdcb2a2415d390`, note `kit/SOURCE.c`). The other files of this stage have the bytes of the stage of A and B, except the project lists and the metadata of the projects (`lists/`, `meta/`). |
| `patched/compare_tom.py`, `patched/ta_tools.py` | The staged files with the patches of the run (above). |

The copies of `ta.conf`, `ta.c.conf`, `ta_start.sh`, `ta_run.sh` and `ta_run.c.sh` differ from
the staged files only in the bucket name (`BUCKET_NAME`). The sha256 values:

| File | staged sha256 | sha256 of the copy |
| --- | --- | --- |
| `ta.conf` | `e9a4b58cd55dbc780982b7f73906998784afc01bd6787d175a0d486afcfd142d` (`SHA256SUMS.ab`) | `fc301505228d24602859801df600e4e89e893fd124c2d0c1db84a040cb718ec6` |
| `ta.c.conf` | `805f8dee5eed786300152c03ca4f68a07c148b5980ddb96eec85fe67f39e3b92` (`SHA256SUMS.c`) | `e1f2fc6b06f37a3b2aded9c9c65acf68a9210e0e9e5fac1b84db84fcc89a1cf1` |
| `ta_start.sh` | `b1343c0e047c4ca7670d161040f86ba9825f94cc311e63e39bde9d26d11f56e3` | `f0dea6f1dad059958ff131519652f117dfab5f5350c74ab42c95da820bfe3085` |
| `ta_run.sh` | `3cf20f99250a9bc868b7b6c231eeb807516fafbd31e1e3b7ac4d04f906ea58ca` (`SHA256SUMS.ab`) | `13101cf1f37c5608401b3859b015399fd1a57dadb4b85d05d6dff340290bc682` |
| `ta_run.c.sh` | `86773692dc9aed19bbb3db28b324088b536bd3a9f649b62659894485d8808787` (`SHA256SUMS.c`) | `053b8abe04559fa0b9830cb05f723ba939257d73af5302d7b5e10f8d0f5371be` |
| `patched/compare_tom.py` | - | `a80f256ab34ddf850800e5a4efaec17ec3a9b53c8b79a5df0f1cc9321e8ed860` |
| `patched/ta_tools.py` | - | `d8b283f44a8ba56956abd62fc1de6ecbabc51128571d6fd73cc78bdd7021d938` |

`ta_tools.py`, `compare_tom.py` and `drive.py` are the staged files (the same sha256 as the
staged lists).

Not here:

- The other files of the stages: the code bundles of cregit and ctp, the metadata and the link
  tables of the new projects, the organization database, the Nix closure of licensee 9.18.0, the
  pseudonymizer and the re-encode tool. The staged lists name each file with its sha256.
- The scripts that staged, uploaded, launched, set up, watched, held or patched the machines.
  They hold the run values (the account, the bucket, the machines).
- The output: the project files and `results/` of each machine are in the storage bucket, under
  `tom-add-159/run/<machine>/`. The private folders (the registries and the full link tables, with
  real identities) never leave the bucket.
