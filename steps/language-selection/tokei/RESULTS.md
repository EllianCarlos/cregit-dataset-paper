# Language mix by tokei at the pinned run commit

Date: 2026-11-07. Everything here was done locally. Nothing was committed or pushed.

Rule: keep a project when its largest single programming language is C, C++, Java or Rust.

## Inputs

- The 10,763 input rows of `../pinned/projects.tsv`, each with its pinned commit. 10,754 rows have a release file, and 9 do not.
- The clone URLs come from `../pinned/inputs.tsv`, or from `../pinned/measure.jsonl` when a row was fetched by clone there.
- Token rows, bytes, commits and file names come from the `MANIFEST.tsv` of the source root of the release passes (10,754 project files).

## Method

For each project:

1. Fetch the pinned commit only, with depth 1, into a new bare repository in the work folder (`TOKEI_WORK`): `git init --bare`, then `git fetch --depth 1 --no-tags <url> <sha>`. Git runs with no user or system configuration, no credentials and no prompts. Hosts other than GitHub get one fetch at a time.
2. Write the files of the commit to a work folder. The first 71 rows (the 30 test rows and the first 41 rows of the full run) used `git checkout` and then deleted `.git`. The rest wrote each blob with `git cat-file --batch`, as explained in "Disk writes" below. Both ways leave out:
   - Vendored paths. This is the selection's vendor rule from `s3-measure/measure_trees.py` (`VENDOR`): a path is left out when one of its directories is named `vendor`, `vendored`, `third_party`, `third-party`, `thirdparty`, `3rdparty`, `external` or `deps`, in any case.
   - Qt translation files. These are `.ts` files (in any case) whose content starts with `<?xml`, `<!DOCTYPE TS` or `<TS`, after an optional UTF-8 BOM and whitespace.
3. Run tokei 14.0.0 as `tokei --hidden --no-ignore -o json`. The store path is in `measure.py` and `shell.nix`. `--hidden` counts dot files. `--no-ignore` keeps `.gitignore`, `.ignore` and `.tokeignore` files from hiding committed files. tokei does not follow symbolic links (tested).
4. Use the `code` count of each language: lines of code, with no comments and no blanks.
5. Embedded child languages are added to their parent language, the way tokei's own Total does (`Language::summarise`). For example, the Rust code in a Markdown fence counts as Markdown, and the Python in a Jupyter notebook counts as Jupyter Notebooks. Check: for every project, the sum over languages equals tokei's `Total.code`, with 0 mismatches.
6. Merge the header languages: C = `C` + `C Header`, and C++ = `C++` + `C++ Header`. tokei maps `.h` to `C Header`. All other tokei languages stay as they are; for example JSX, TSX, `C++ Module` and `Arduino C++` stay separate.
7. Keep only programming languages, using `languages.tsv`:
   - 199 tokei names match a Linguist name in `s3-measure/languages.yml` (case-insensitive). They take the Linguist `type`: 161 are programming and 38 are not.
   - 130 tokei names do not match. They are mapped by hand in `HAND` in `measure.py` (84 programming, 46 not). Each one names the Linguist language it was mapped to, or "none" with a reason.
   - Following Linguist, SQL, GraphQL, TeX, HTML, CSS, Vue and Svelte are not programming. Dockerfile, Makefile, CMake and Shell are programming. tokei names `.in` files `Autoconf`, which is mapped to Linguist M4Sugar (programming).
8. Record, for each project:
   - The code lines of each programming language.
   - The total code lines of the languages left out.
   - The largest language. There were no ties.
   - The target share: C + C++ + Java + Rust code lines over all programming code lines.
   - The number of Qt `.ts` files removed.
   - The rule result.
   - The fetch method.
   `measure.jsonl` holds no paths, no file names and no person data.

Workarounds:

- `git.busybox.net__busybox`: the host refuses a fetch by SHA, so the default branch was fetched with growing depth until the pinned commit was there. The depth was 32.
- `git.libreoffice.org__libvisio` and `git.libreoffice.org__libetonyek`: git.libreoffice.org answers 403, so the same SHA was fetched from the GitHub mirror (LibreOffice/libvisio, LibreOffice/libetonyek). The libetonyek mirror is a new workaround, used in the retry pass. For both, the fetched commit equals the pinned commit.
- `git.savannah.gnu.org__emacs` needed no retry this time. 8 GitHub rows needed a second fetch attempt.

### Disk writes

The first 41 rows of the full run were slow because the disk was the limit, at about 1.6 GB of tree per minute. That run was stopped softly (no new rows started, running rows finished) and restarted with a different way to write the files.

The new way writes the blobs with `git cat-file --batch` and leaves out three kinds of files:
- symbolic links and submodules, which tokei does not count;
- files with one of 105 binary extensions (images, audio, video, fonts, archives, object code and the like; `NEVER` in `measure.py`).

This does not change any count:
- tokei picks a language by file name, by extension, or by a shebang only when the file has no extension. A file of each of the 105 extensions, in lower and upper case, with C code or a shebang inside, gave 0 lines.
- The 30 test projects were measured both ways (`measure.jsonl` lines from the checkout, `compare.jsonl` from the new way). All 30 are identical in every language count, the left-out total, the largest language, the share, the rule and the Qt count.

Over the 10,682 rows measured the new way:
- 40.9 million tree entries;
- 795 GB of blobs;
- 37.1 million files and 505 GB were written;
- 2.45 million files (253 GB) had a binary extension;
- 1.25 million files (33 GB) were vendored.

## Test (30 projects) and estimate

The test set (`sample30.tsv`) has three groups:
- the 10 largest projects by `rows`;
- 10 random projects (seed 20261107);
- 10 random projects of the 400 rows where `lang_linguist` and `lang_with_ts` differ.

The test ran with 8 workers under `nice`. The machine has 16 cores, 30 GB of memory (about 13 GB free) and 1.5 TB free disk. Other users' jobs were running too.

| | |
|---|---|
| Wall time | 491 s |
| Downloaded (pack bytes) | 5.55 GB |
| Tree size (from `../pinned`) | 34.1 GB |
| Peak disk in the work folder (sampled every 10 s) | 19.1 GB |

Estimate:
- A fit of worker-seconds = 1.1 s + 65.5 s per GB of tree, over the 1,062 GB of tree of all rows, gave 2.8 h with 8 workers.
- With 1.5 times the per-GB cost, it gave 4.0 h.
- Both are under 10 hours, so the full run was started in the tmux session `cregit-tokei`.

## Full run

| | |
|---|---|
| Wall time | 00:59 to 03:10 UTC, about 2 h 11 min, with a 4-minute pause for the restart |
| Retry pass | 03:11 UTC |
| Downloaded (sum of pack bytes in `measure.jsonl`) | 409.3 GB |
| Peak disk | 68.9 GB at 01:40 UTC, during the checkout part (`sajjadium__ctf-archives`, a 55 GB tree, was in flight) |
| Peak disk after the restart | 4.5 GB, counted as the sum of pack and written bytes of the rows in flight |
| Workers | 8, with 2 threads each for git and tokei, under `nice -n 10` and `ionice -c2 -n7` |

## Not measured (10 rows, all dropped)

- 3 rows were dropped by the user's decision ("dropped: repository gone"): `dust-tt__dust`, `abgox__PSCompletions`, `milisp__codexia`.
- 7 rows failed the fetch. They failed again on two more depth-1 retries and were dropped, by the user's decision ("dropped: fetch failed"). The list is in `fetch-failed.tsv`.
  - 5 GitHub repositories answer 404 to the GitHub API: `overtake__TelegramSwift`, `IBM__JTOpen`, `AgentsMesh__AgentsMesh`, `metlo-labs__metlo`, `veritone__labs-docker-model-runner`. Their byte results in `../pinned` came from S3 tree records made earlier, not from a new fetch.
  - 2 Savannah repositories refuse a fetch by SHA, and the pinned commit is no longer a branch tip: `git.savannah.gnu.org__denemo`, `git.savannah.gnu.org__gnubg`. History was not fetched for these.

Together, the 10 rows have 9,566,471 token rows. All 10 have a release file.

## Results

### Kept and dropped

| Rows | kept / rows |
|---|---|
| All input rows | 8,449 / 10,763 |
| Rows with a release file | 8,447 / 10,754 |

Dropped:
- All input rows: 2,314. That is 2,304 measured rows whose largest language is another one, plus the 10 rows that were not measured.
- Rows with a release file: 2,307. That is 2,297 measured plus 10 not measured.

Two kept rows have no release file: `kitao__pyxel` (Rust) and `signalwire__freeswitch` (C). (TOM 1.1.0 has a file for `signalwire__freeswitch`: `../../release-passes/pass-6-freeswitch/`.) `Librelancer__Librelancer` has no programming code at the pinned commit, so it is dropped.

Kept token rows and bytes (MANIFEST `rows` and `bytes`):

| | all |
|---|---|
| Kept token rows | 30,406,900,014 |
| All manifest token rows | 32,635,174,618 |
| Kept bytes | 127,424,637,166 |
| All manifest bytes | 137,087,040,565 |

Kept projects by largest language: C++ 2,467, Java 2,197, C 2,171, Rust 1,614.

Dropped measured projects by largest language (top 10): Python 481, TypeScript 357, JavaScript 202, Kotlin 176, Go 111, C# 85, Objective-C 66, TSX 66, Dart 58, Swift 53. Scala also has 53. The full list is in `summary.json`.

### Share thresholds

Share is C + C++ + Java + Rust code lines over all programming code lines.

| Rule | Projects kept | With a release file | Token rows | Bytes |
|---|---|---|---|---|
| Largest language is C, C++, Java or Rust | 8,449 | 8,447 | 30,406,900,014 | 127,424,637,166 |
| Share >= 30% | 9,069 | 9,067 | 31,890,137,534 | 133,939,798,917 |
| Share >= 50% | 8,241 | 8,239 | 30,128,352,767 | 126,401,474,185 |

### Kept set by commits (MANIFEST `commits`), rows with a release file

| SS < 1,500 | S 1,500-2,499 | M 2,500-4,999 | L 5,000-14,999 | XL 15,000-49,999 | XXL >= 50,000 | Total |
|---|---|---|---|---|---|---|
| 1,687 | 1,939 | 2,017 | 1,811 | 715 | 278 | 8,447 |

The kept set has 8,447 parquet files, which is fewer than 10,000.

### The 400 rows where the two byte-based results differ

tokei keeps 183 of the 400. All 400 were measured.

### tokei against the byte-based results

Only the 10,753 measured rows are compared.

Linguist variant (`lang_linguist`): 620 rows get a different result.
- tokei keeps and bytes drop: 258.
- tokei drops and bytes keep: 362.

| project | largest by bytes | largest by tokei | tokei share |
|---|---|---|---|
| Grashjs__cmms | Java | TypeScript | 0.258 |
| JohnnyMorganz__luau-lsp | C++ | Lua | 0.494 |
| MapleTechLabs__maple | Rust | TypeScript | 0.026 |
| Nozbe__WatermelonDB | C | JavaScript | 0.442 |
| Zeal-Operating-System__ZealOS | C++ | HolyC | 0.054 |
| hAcKlyc__MyAgents | Rust | TypeScript | 0.302 |
| jtenniswood__espcontrol | JavaScript | C | 0.511 |
| magcius__noclip.website | Rust | TypeScript | 0.029 |
| sqlpage__SQLPage | JavaScript | Rust | 0.669 |
| winglang__wing | Rust | TypeScript | 0.293 |

WITH_TS variant (`lang_with_ts`): 586 rows get a different result.
- tokei keeps and bytes drop: 441.
- tokei drops and bytes keep: 145.

| project | largest by bytes | largest by tokei | tokei share |
|---|---|---|---|
| JetBrains__MPS | JetBrains MPS/Mathematical Programming System | Java | 0.973 |
| KDE__plasma-browser-integration | JavaScript | C++ | 0.526 |
| MmgTools__mmg | C | GLSL | 0.090 |
| OpenBCI__OpenBCI_GUI | Processing | Java | 0.417 |
| alibaba__SREWorks | JavaScript | Java | 0.568 |
| jenkinsci__blueocean-plugin | JavaScript | Java | 0.462 |
| lumina-desktop__lumina | TypeScript | C++ | 0.921 |
| mmontag__chip-player-js | Logos | C | 0.925 |
| spockframework__spock | Java | Groovy | 0.384 |
| tntim96__JSCover | Java | JavaScript | 0.193 |

The examples are a random sample (seed 7) of each list. The full lists can be rebuilt from `projects.tsv`.

### Qt .ts files

- 15,745 Qt translation `.ts` files were removed, in 335 projects.
- Not removed: 398 `.ts` files in 91 projects have a NUL byte in their first 8 KB. They are binary, for example MPEG transport streams. tokei counts such files as TypeScript (tested: a random binary `.ts` file gave 35 TypeScript code lines).

## Keep list

`projects.keep.txt` has 8,447 lines, one per kept row with a release file. Each line is the stem of the release parquet file name: the file is `<stem>-dataset.parquet`, and the stem equals the project name.
- It is the keep list of the first release pass (`steps/release-passes/pass-1/`).
- All 8,447 names are project names of the source root.

## Files

- `measure.py`: the script, with the steps `langs`, `sample`, `run`, `report` and `final`.
- `shell.nix`: where tokei 14.0.0 comes from.
- `run-all.sh`: the full-run command used in tmux.
- `progress.py`: progress by tree bytes.
- `languages.tsv`: each tokei language, whether it counts as programming, and how that was decided.
- `sample30.tsv`: the test set.
- `measure.jsonl`: one line per project as it ended. The last line of a project counts.
- `compare.jsonl`: the 30 test projects measured the new way.
- `projects.tsv`: one row per input row. It has the pinned commit, the tokei status, the largest language, the target share, the rule result, the Qt `.ts` count and the fetch method, plus the byte-based `lang_linguist`, `lang_with_ts`, `largest_linguist` and `largest_with_ts`.
- `summary.json`: the counts in this file, and the full lists.
- `final.json`: the share thresholds, size classes and parquet count.
- `fetch-failed.tsv`: the 7 dropped fetch failures.
- `projects.keep.txt`: the keep list.
- `test.log`, `run.log`, `compare.log`, `retry.log`: the logs.
- `run-stats.*.jsonl`: wall time and peak disk of each run.
