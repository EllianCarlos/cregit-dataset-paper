# The language selection evidence

The selection keeps a project when its tokenizable code of the target languages (C, C++,
Java, Rust) is at least 5% of its code bytes (rule DP3, `pipeline/SELECTION-STAGES.md`).
These scripts measure what stricter rules would keep, so that the paper can show how much of
the dataset each rule changes. They change no published file.

| Folder | Script | What it measures |
|---|---|---|
| `.` | `whatif.py` | The stricter rules on the 10,754 project files, with the bytes by extension of the selection measure (`pipeline/s3-measure/`, at the measured commit) and the token rows of the release. Output: `result.txt` and `rows.json` (`WITH_TS=1`: TypeScript counts as a programming language; `result.with-ts.txt`, `rows.ts.json`). |
| `pinned/` | `pinned.py` | The same rules at the pinned run commit of each of the 10,763 inputs (the 10,754 files and 9 inputs with no file), with the selection measure code unchanged. Output: `inputs.tsv`, `projects.tsv`, `results.txt`, `below5.*.tsv`; `RESULTS.md` explains the run and the results. |
| `tokei/` | `measure.py`, `run-all.sh`, `shell.nix` | The language mix of each input at the pinned run commit with tokei 14.0.0 (code lines by language), after the vendored folders and the Qt translation files are removed. `languages.tsv`: each tokei language and whether it counts as a programming language. `sample30.tsv`: the 30 test projects. |

The tables hold project names, commits, sizes, language counts and the rule results only.
They keep a column `layer` from the build (the run batch of each file); it is not a property
of the dataset.

## The runs

| Script | sha256 of the file that ran | sha256 of the copy | Run |
|---|---|---|---|
| `whatif.py` | `cecbe47eff13` | `23b3dad7a55f` | 2026-11-06, on the run host. |
| `pinned/pinned.py` | `e8f46086a568` | `b62cc7c97b29` | 2026-11-06, on the run host. |
| `tokei/measure.py` | `e47807643769` | `5024ca7f8c1c` | Started 2026-11-07 on the run host (`run --all --workers 8`). |
| `tokei/run-all.sh` | `88caabe3c599` | `614e711a5ba7` | The same run. |

The copies differ from the files that ran only in the default paths: the scripts read
`RELEASE_MANIFEST` (the `MANIFEST.tsv` of the release root), `PAPER_PIPELINE` (default: the
`pipeline/` folder of this repository) and `TOKEI_WORK` (the work folder of the tokei run,
default a folder under the temporary folder), and `tokei/measure.py` takes `PATH` from the
environment. On 2026-11-07 the copy of `whatif.py` gave `result.txt` and `rows.json` again
byte for byte.

**The tokei run had not ended when these files were copied** (15 of 10,733 projects done).
Its result tables (`measure.jsonl`, `projects.tsv`, `summary.json`) come here when the run
ends. `pinned/measure.jsonl` and `pinned/rows.json` (the raw measures and the per-project rows
before the tables, 14 MB and 8 MB) are not copied; `pinned.py measure` and `pinned.py whatif`
make them again.

## How to run

```sh
cd steps/language-selection
RELEASE_MANIFEST=ROOT/MANIFEST.tsv python3 -I whatif.py > result.txt
WITH_TS=1 RELEASE_MANIFEST=ROOT/MANIFEST.tsv python3 -I whatif.py > result.with-ts.txt
cd pinned
RELEASE_MANIFEST=ROOT/MANIFEST.tsv python3 -I pinned.py inputs
RELEASE_MANIFEST=ROOT/MANIFEST.tsv TMPDIR=WORK python3 -I pinned.py measure   # network: GitHub API and git
python3 -I pinned.py whatif
cd ../tokei
nix-shell shell.nix   # tokei 14.0.0, git, python3
RELEASE_MANIFEST=ROOT/MANIFEST.tsv TOKEI_WORK=WORK python3 -I measure.py langs
RELEASE_MANIFEST=ROOT/MANIFEST.tsv TOKEI_WORK=WORK python3 -I measure.py run --all --workers 8
python3 -I measure.py report
```

`pinned.py measure` uses the selection measure code (`pipeline/s3-measure/measure_trees.py`),
which takes a GitHub token from `gh auth token`. The docstring of each script gives its steps.
