# project_languages.parquet and language_fill_gaps.tsv

Built by `p4_languages.sql` (log: `p4_languages.out`) from the finished tokei measure (`input/tokei-measure.jsonl`, run ended 03:10:37 UTC, retries 03:11 UTC; the last final line per project). One row per release project (10,754).

Columns: `project` (file stem), `language` (host value of the release, null when empty), `language_tokei` (largest programming language by tokei code lines, tokei names, C Header merged into C and C++ Header into C++ as in measure.py), `language_tokei_linguist`, `largest_tied` (empty unless there is a tie; there are none), `target_share` (C + C++ + Java + Rust code lines over all programming code lines), `code_lines_programming`, `code_lines_json` (code lines per tokei language, as JSON), `tokei_status`.

`language_tokei_linguist`: the code lines after the name map TSX -> TypeScript, JSX -> JavaScript, GNU Style Assembly -> Assembly, FORTRAN Modern -> Fortran, summed per mapped name, then the largest. Because the lines are summed, TSX + TypeScript can overtake another language: 50 projects get TypeScript although their tokei largest is another language (Rust 31, Java 7, Python 4, 8 others), and 3 more change to JavaScript or Assembly. Mapping only the name of the largest language, without summing, would keep those 53 at their tokei value. FORTRAN Legacy is not in the map (6 projects keep "FORTRAN Legacy").

Checks:
- tokei status: ok 10,744; dropped, fetch failed 7 (5 GitHub repositories now private or gone, 2 Savannah commits no longer a branch tip); dropped, repository gone 3.
- All 10,744 measured at the MANIFEST `run_commit`; `target_share` recomputed from the lines matches the measure for all.
- Agreement with the host value where both exist (10,564): 89.2% raw, 90.2% with the name map; 1,036 differ.
- Keep rule (largest tokei language C, C++, Java or Rust): 8,447 kept, 2,297 not; the same 8,447 as `projects.keep.txt`.

## language_fill_gaps.tsv

182 release projects have an empty `language` (all outside GitHub). tokei measured 180; the 2 left are the Savannah projects whose pinned commit the host no longer serves. The proposed value is `language_tokei_linguist`:

| proposed | projects |
|---|---:|
| C | 72 |
| C++ | 67 |
| Java | 20 |
| QML | 3 |
| JavaScript, Objective-C, Objective-C++, Ruby | 2 each |
| Autoconf, Bitbake, Emacs Lisp, F#, Happy, Kotlin, Lex, Perl, Scheme, TTCN-3 | 1 each |

By host: git.savannah.gnu.org 56 of 58, invent.kde.org 56, gitlab.eclipse.org 26, gitlab.freedesktop.org 15, gitlab.com 8, 13 other hosts 19.
