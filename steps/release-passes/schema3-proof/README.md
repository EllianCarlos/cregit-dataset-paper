# The direct write of the 53-column schema

The passes changed the files after the build. ctp now writes the schema of TOM in a normal run,
with no later pass: ctp branch `feat/schema-3-run` (commit `a9f0bed`) and the cregit fork branch
`feat/schema-3` (commit `8d60a8f`). A run writes the 53 columns of ctp schema 3 and
`project_facts.parquet` (with the fact type `roster_language`). `ctp.py select` runs the tokei
language rule as the selection step.

This folder holds the proof of 2026-11-07: a rebuild of 2 projects at their pinned commits,
compared with the output of the passes for the same projects.

## Files

| File | What it does |
|---|---|
| `make-tom.sh` | Makes the output of pass 1 for given source files (the drop of 10 columns, the rename and the footer key) with `parquet_rename.py`, then checks it. |
| `compare_tom.py` | Compares a rebuilt file with the file of the passes: the column names and types, the footer key-values, the rows, and for each column the rows that differ. For a column that differs, it tests if the map between the two files is one to one (a bijection). Pseudonyms made with another salt differ in every value, but a bijection shows that both files group the rows the same way. It prints counts and hashes only. |
| `diff_by_file.py` | Counts the rows with another `original_commit_sha` for each source file. With a file name, it also compares all other rows. |
| `compare_facts.py` | Compares `project_facts.parquet` of a run with the facts of the rule of the passes (`../pass-1/tom_tools.py`; `TOM_TOOLS` overrides the path). |
| `results/manifest.tsv` | The run manifest: the 2 projects and their pinned commits. |
| `results/kept.tsv`, `results/dropped.tsv`, `results/languages.tsv` | The output of `ctp.py select` (tokei 14.0.0): both projects kept, largest language C. |
| `results/compare-libexpat.json` | libexpat against the output of pass 1 (61 columns). |
| `results/compare-libexpat-53.json`, `results/compare-emscripten-53.json` | Both projects against the 53 kept columns. |
| `results/diff-emscripten.txt` | The rows of emscripten that differ, by source file. |

`compare_facts.py` and `make-tom.sh` differ from the files that ran (`0bde3d36ea67` and
`01e4e6eefeca`) only in a path: the path of `tom_tools.py` became an option, and a comment
names `../pass-1/tom.conf`. `compare_tom.py` (`12a2039ba0e9`) and `diff_by_file.py`
(`defd87925351`) are the files that ran.

## Results

- `libexpat__libexpat` (195,672 rows): the same 53 columns and types, the same rows, the same
  footer key-values except `pseudonymization_registry_sha256` (another salt). Every column is
  equal, or a bijection (the 5 identity columns and the trailer lists: pseudonyms).
- `emscripten-core__emscripten` (11,299,416 rows): the same 53 columns and types, the same rows
  and the same footer key-values except the registry hash. One source file differs:
  `system/include/compat/arm_neon.h` (402,039 rows, 3.56%) has another last commit
  (`original_commit_sha`) on its rows. On all other rows, the 34 columns that are not identity
  columns are equal, and every identity column is a bijection. The cause of the difference in
  that one file is not known.
- `project_facts.parquet` of the run: 0 rows for the 2 projects.

The runs took place from 15:38 to 16:58 UTC. In that time, both branches got the 53-column
list (cregit `8d60a8f`, ctp `d6ddb9a`). After the runs, ctp `a9f0bed` changed the name of the
roster fact type. The libexpat run of 16:40 continued from the run of 15:38 (the runner resumed
at its step 10). A rebuild of both projects at the final commits is not done.

## How to run

```sh
python3 -I compare_tom.py REBUILT.parquet TOM.parquet --json out.json
python3 -I diff_by_file.py REBUILT.parquet TOM.parquet [SOURCE_FILE]
python3 -I compare_facts.py project_facts.parquet SOURCE.parquet [SOURCE.parquet ...]
bash make-tom.sh OUTDIR SOURCE.parquet [SOURCE.parquet ...]
```

The scripts need DuckDB (1.5.5); `make-tom.sh` also needs `uv` and pyarrow, and its library path
names Nix store paths.
