# Pass 4: the DOI pass (documents only)

Pass 4 made the final root of TOM 1.0.0 from the root of pass 3. It changes documents only. It
puts the DOI (`10.57967/hf/11505`) and the release date (2026-11-07) into the documents, and it
removes 3 documents. The 8,449 project files do not change: they are byte-identical to pass 3.
It ran on 2026-11-07 on one small cloud machine (m7i.large) and ended DONE. Hugging Face
revision `e81b554deb9b` has its root. The DataCite version of the DOI names revision
`bc7543affd2e` (the root of pass 3, with the same project files).

## What it does

1. It reads the root of pass 3 (8,449 project files, 53 columns; `SHA256SUMS` sha256
   `820f6e8233d8...`, `TOM3_SUMS_PREFIX` of `tom4.conf`). It does not change it. It fetches only
   the files outside `parquet/` and reads the footer of each project file.
2. It takes the documents of the stage (12 files). The documents of pass 3 that the stage does not
   have must be exactly `REMOVED_DOCS`: `docs/LIMITATIONS.md`, `docs/PROVENANCE.md` and
   `docs/RELEASE-NOTES.md`. The paper now gives the limitations and the provenance.
3. It fills the markers: `TODO-DOI` (5 lines), `TODO-DATE` (3 lines) and the placeholders
   `[[tom: KEY]]` with the values that pass 3 measured. No marker may stay.
4. `SHA256SUMS`: the rows of pass 3 for the project files and the sha256 of every other file.
   `MANIFEST.tsv`, `organizations/`, `ledgers.parquet`, `links.json` and `pseudonymization.json`
   keep the bytes of pass 3 (`KEEP_SAME`).
5. The new root gets the project files by a server-side copy of the root of pass 3. Hugging Face
   gets only the changed documents and `SHA256SUMS`, and the 3 removed documents are deleted.

## Checks

- `fill_release.py check` without `--allow-todo` (no marker may stay).
- `tom4_tools.py check-root`: each project row of `SHA256SUMS` is its row of pass 3; the
  `KEEP_SAME` files have the bytes of pass 3; only documents changed; the files that are gone are
  exactly `REMOVED_DOCS`; 53 columns and `ctp_schema_version` 3 in each footer; 30,408,388,202
  rows; the DOI and the date in `CITATION.cff`.
- `sha256sum -c` of every local file; `release_tools.py no-at`, `no-paths`, `guard`;
  `hf_tools.py precheck`, `validate-card`.
- After the copy: one object for each file; each project object has the ETag of pass 3, and a
  seeded sample of 32 project objects is downloaded and hashed.
- Hugging Face: before the push the Hub holds the root of pass 3; after the push, every file of
  the Hub tree is verified against the new `SHA256SUMS`.

## The final root

| Value | |
|---|---|
| `SHA256SUMS` | 8,475 rows, sha256 `b7141d088461944872033563ac6609cb6fe846ec179e6aae6eeed62078186899` (`../../../data/SHA256SUMS` has all rows) |
| `MANIFEST.tsv` | 8,450 lines (8,449 projects), sha256 `3d59a94b402d1949e7db71cdaeacba1561e45e284eb4f840a2e39f75a063fde8` |
| Project files | 8,449 files, 115,391,496,638 bytes, 30,408,388,202 token rows (the sums of `MANIFEST.tsv`) |

## Files

| File | What it does |
|---|---|
| `tom4.conf` | The values: the prefixes, the DOI and the date, the marker counts, `KEEP_SAME`, `REMOVED_DOCS`, the hash sample. |
| `tom4_start.sh`, `tom4_run.sh` | The start and the driver (steps `preflight`, `fetch`, `keep`, `footers`, `assemble`, `fill`, `checksums`, `view`, `checks`, `upload`, `hf`, `end`). |
| `tom4_tools.py` | The Python steps of the pass. |
| `SHA256SUMS`, `SOURCE` | The staged list (sha256 `ddbe7134d9e4...`, `WANT_SUMS` of the run) and the stage note. |

`tom_tools.py` and `hf_tools.py` are the files of `../pass-1/`, `tom2_tools.py` of `../pass-2/`,
`release_tools.py` of `../../release-root/`, and `docs/tools/fill_release.py` of
`../fill-release/tools/`. The copies of `tom4.conf` and `tom4_start.sh` differ from the staged
files only in the bucket name (`BUCKET_NAME`); `../KITS.tsv` gives both sha256 values. The
documents of the stage are not here: the root has the filled copies.
