# Text cut from the ctp docs

This file keeps the text that the generic-pipeline cleanup removed from four
documents of `cregit-token-pipeline` (ctp). The base is ctp commit `17f1766`
(branch `corpus-freeze-and-tests`). Each section names the source file. Each
block holds the removed lines of one change, with their line numbers at
`17f1766`. The ctp working tree keeps a rewritten, generic version of each
file, so a block can be shorter than the text it replaced.

`docs/LIMITATIONS.md` is not in this file. It moved whole, unchanged, to
`cregit-dataset-paper/LIMITATIONS.md`.

## `README.md`

Removed lines 3-4:

````text
Builds a **token-level code authorship dataset** over a stratified corpus of
FLOSS repositories, by orchestrating the
````

Removed line 6:

````text
corpus-level selection, provenance, validation and anonymization around it.
````

Removed lines 10-11:

````text
that token, the person's employer where it can be resolved, and 29 columns
recording how the project entered the corpus and how it was labeled.
````

Removed lines 21-23:

````text
| know what is wrong with the data before you analyze it | **[`docs/LIMITATIONS.md`](docs/LIMITATIONS.md)** |
| know why attribution changed in September 2026, and by how much | **[`docs/REBLAME-C100.md`](docs/REBLAME-C100.md)** |
| know how a project got its `stratum`, or label one yourself | [`docs/CODEBOOK.md`](docs/CODEBOOK.md) |
````

Removed lines 25-29:

````text
| see the sampling frame, exclusions and the per-cell draw | [`docs/CORPUS-REVIEW.md`](docs/CORPUS-REVIEW.md), [`docs/CORPUS-SAMPLE.md`](docs/CORPUS-SAMPLE.md) |
| see the strata checked against an independent published labeling | [`docs/SPINELLIS-VALIDATION.md`](docs/SPINELLIS-VALIDATION.md) |

The three corpus reports are **generated** — by `select_corpus.py review`,
`select_corpus.py sample` and `validate_spinellis.py`. Do not edit them by hand.
````

Removed lines 37-40:

````text
# 2. pick a manifest (TSV: name, url, category, file_mask, size_class).
#    --manifest defaults to manifest.tsv, which is only 4 legacy pilots.
M=manifest.phase1-sm.tsv
./ctp.py run --manifest $M --jobs 3 --skip-html --drop-memo
````

Removed lines 42-43:

````text
./validate_schema.py <out>/*/*-dataset.parquet   # schema gate over the corpus
./ctp.py db                                      # rebuild ctp.duckdb + tokens view
````

Removed lines 46-47:

````text
Full regeneration, from rosters to an anonymized release, is the step table in
[`docs/DATASET-SCHEMA.md` §2](docs/DATASET-SCHEMA.md#2-regenerating-it).
````

Removed line 58:

````text
candidates.csv ──► select_corpus.py sample ──► manifest.*.tsv
````

Removed line 60:

````text
project_meta.json (29 provenance fields) ──────────┤
````

## `docs/DESIGN.md`

Removed lines 4-5:

````text
[`DATASET-SCHEMA.md`](DATASET-SCHEMA.md); for how a project is labeled, read
[`CODEBOOK.md`](CODEBOOK.md).
````

Removed lines 7-9:

````text
**Goal.** Run cregit end-to-end over a stratified corpus of FLOSS projects and
produce per-project token-authorship datasets that share one schema, on a single
workstation (16 cores, 30 GB RAM, one NVMe).
````

Removed line 19:

````text
2. **Corpus layer** — selection, provenance, validation, retention and
````

Removed lines 51-52:

````text
  They live in `project_meta.json`, a **sidecar keyed by manifest name and joined
  on `clone_url`**, passed to the generator with `--project-meta`.
````

Removed lines 62-65:

````text
a polyglot project's other languages; `data/mask-impact.csv` measures what that
cost. The column stays because it records which mask a Parquet was built with.
Projects whose primary language has no tokenizer are still excluded at selection
time.
````

Removed lines 67-68:

````text
Selection heuristics are a separate concern: `select_corpus.py` emits candidate
rows for curation, and the runner only consumes a curated manifest.
````

Removed lines 118-120:

````text
`memo/` plus `html/` is 68–96% of a work directory. Measured on four pilots,
`memo/` alone was 45–88%. Keeping both across a large corpus does not fit on the
disk; dropping both is what makes the corpus feasible.
````

Removed line 147:

````text
  first. A corpus is unusable if one project has 38 columns and another 70, or if
````

Removed line 151:

````text
The run invokes only the first, so the schema gate has to be run over the corpus
````

Removed line 159:

````text
## 7. Corpus-level stages
````

Removed lines 163-168:

````text
1. **`select_corpus.py`** — rosters and searches → control facts → `candidates.csv`
   → a stratified `manifest.sample.tsv`. See `CODEBOOK.md`.
2. **`shared_history.py`** — finds projects that carry another project's history,
   which GitHub's fork flag does not. They are flagged, not excluded.
3. **`project_meta.py`** — the 29-field provenance sidecar.
4. **`build_domain_map.py`** — the domain→firm map, from public affiliation data
````

Removed line 170:

````text
5. **`consolidate.py`** — `ctp.duckdb`: a `projects` state table, `phase_metrics`,
````

Removed line 172:

````text
   manifests indexed are selectable and default to the corpus run set; a
````

Removed line 176:

````text
6. **`anonymize_parquet.py`** / **`verify_anon.py`** — the release path. The
````

Removed line 190:

````text
- **A corpus-level firm or organization rollup.** Attribution is per token only.
````

Removed line 194:

````text
- **A packaging step** emitting per-stratum trees with checksums and a schema
````

Removed lines 206-207:

````text
| One project poisons the run | that project fails and is retried; the corpus continues |
| Tokenizer fix lands mid-corpus | the tokenized repo and blob map are retained, so only affected blobs are re-tokenized and the Parquet is regenerated |
````

## `docs/DATASET-SCHEMA.md`

Removed lines 3-6:

````text
Reference for the published artifact. Four questions, in order: what the dataset
is (§1), how to regenerate it (§2), what every column means (§3), and what is
known to be wrong with it — [`LIMITATIONS.md`](LIMITATIONS.md), which you should
read before analyzing the data.
````

Removed line 27:

````text
row, so a consumer can filter a corpus without a second join. A column is cheap
````

Removed line 30:

````text
### 1.1 The corpus
````

Removed lines 36-66:

````text
| Candidate rows considered | 24,405 (28 fields) | `candidates.csv` |
| Eligible rows | 3,948 | `candidates.csv`, `included == True` |
| Sampling frame (distinct repositories) | 3,842 | eligible rows collapsed by `clone_url` |
| Projects drawn | 200 — 156 S, 31 M, 13 L | `manifest.sample.tsv` |
| Strata drawn | 103 community, 69 company-owned, 28 foundation | `manifest.sample.tsv` field 3 |
| Sampling seed | `20261110` | `select_corpus.SAMPLE_SEED` |
| Cell floor | 2 per `(stratum, language, size_class)` cell | `select_corpus.SAMPLE_FLOOR` |
| Size classes | S < 30,000 commits; M 30,000–150,000; L > 150,000 | `select_corpus.SIZE_S`, `SIZE_M` |

The draw is stratified by `(stratum, language, size_class)`: a floor of 2 from
every cell first, then the remainder by largest remainder, and a cell is never
asked for more than it holds. `docs/CORPUS-SAMPLE.md` is the per-cell allocation.
One `random.Random` is seeded per cell from `f"{seed}:{cell_key}"`, so adding a
cell does not re-draw the others.

**The run set is smaller than the draw.** `manifest.phase1-sm.tsv` holds the 187
S- and M-class projects and `manifest.linux.tsv` holds one L-class project: 188
of the 200. The other 12 L-class projects are held back on disk grounds (one
L-class working directory measured 435 GB). Run them from
`manifest.sample.tsv` once retention has a Parquet-only level.

**The published set is smaller than the run set: 185 of the 188.** Two projects are
excluded on purpose and one is still running. `tencent__tencentkona-21` cannot be
parsed completely and `tencent__tendbcluster-tendb` is a near-duplicate of
`tencent__tendbcluster-tdbctl`; both keep their manifest row and their `projects`
row, and `consolidate.py` records the reason in `excluded_because`. Read published
membership from that column, never from the presence of a Parquet file.
`docs/LIMITATIONS.md` holds the measurements.

How a project gets its `stratum` is `docs/CODEBOOK.md`. It is a claim about who
*controls* a project and never about who contributes to it.
````

Removed line 70:

````text
All 186 Parquets that conform to the contract today carry one `file_mask` value.
````

Removed lines 72-77:

````text
polyglot project's other languages; `data/mask-impact.csv` is the record of what
that cost, re-derivable with `./mask_impact.py`, and the widening is provably a
superset — no project loses a file. Note that `./ctp.py run --mask REGEX`
overrides the manifest for a run without updating `project_meta.json`, so a run
using it publishes a `file_mask` that does not describe what happened. The runner
warns; nothing enforces it.
````

Removed line 79:

````text
### 1.2 Selecting the corpus out of the output directory
````

Removed lines 81-82:

````text
The output directory also holds development fixtures. One predicate separates
them:
````

Removed line 87:

````text
WHERE provenance_status = 'candidates.csv';   -- drops the fixtures
````

Removed lines 90-100:

````text
`provenance_status` is `candidates.csv` for a corpus project and
`fixture-needs-rework` for a fixture. `project_meta.json` holds 210 entries of 29
fields: 200 corpus projects and 10 fixtures. A fixture has only four real fields
— `provenance_status`, `clone_url`, `manifest_category`, `file_mask` — and the
other **25 are empty strings**. It was never selected, so it has no stratum, no
draw and no history cluster, and empty strings read as findings rather than as
absences. `provenance_status` is deliberately the second column, because it
qualifies everything after it.

A corpus project that is *not* found in `candidates.csv` is a hard error rather
than a silent blank row.
````

Removed lines 102-104:

````text
`./ctp.py db` builds the same view (plus a `projects` tracking table and a
`phase_metrics` table) into `ctp.duckdb`, over the run set rather than over the
glob. It is a derived index; the files are the authority.
````

Removed lines 107-109:

````text
`read_parquet` over a list binds **one** schema for the whole list: the 10 fixtures
in the output directory are at older 23- and 38-column schemas and will abort the
view outright. `consolidate.py` handles this by including only files whose schema
````

Removed lines 125-139:

````text
| 1. Fetch rosters | `./select_corpus.py rosters` | `.corpus-cache/` |
| 2. Resolve repositories | `./select_corpus.py enrich` | `.corpus-cache/repo-meta.json` |
| 3. Find shared histories | `./shared_history.py scan` then `ancestry` | history cluster cache |
| 4. Emit candidates | `./select_corpus.py emit` | `candidates.csv`, `manifest.tsv` |
| 5. Draw the sample | `./select_corpus.py sample` | `manifest.sample.tsv`, `docs/CORPUS-SAMPLE.md` |
| 6. Build the provenance sidecar | `./project_meta.py --candidates candidates.csv --manifest manifest.sample.tsv --fixture-manifest manifest.tsv --fixture-manifest manifest.mvp5.tsv --fixture-manifest manifest.shardtest.tsv --out project_meta.json` | `project_meta.json` (200 + 10) |
| 7. Build the domain→firm map | `./build_domain_map.py fetch` then `build` | `data/affiliation.merged.csv` |
| 8. Run the corpus | `./ctp.py run --manifest manifest.phase1-sm.tsv --jobs N --skip-html --drop-memo --project-meta project_meta.json --firm-map data/affiliation.merged.csv --firm-canonical data/firm_canonical.csv` | one Parquet per project, plus a `.validated` stamp |
| 9. Gate the schema | `./validate_schema.py <out>/*/*-dataset.parquet` | exit 1 on any drift |
| 10. Build the index | `./ctp.py db` | `ctp.duckdb` |
| 11. Prune | `./retain.py --apply` | deletes `memo/` and `html/` only |
| 12. Pseudonymize for release | `./anonymize_parquet.py OUTDIR <in>.parquet ...` | anonymized Parquets + JSON report |
| 13. Verify the release | `./verify_anon.py OUTDIR` | exit 1 on any residue |

**`--manifest` defaults to `manifest.tsv`, which is four legacy pilot projects.**
````

Removed line 191:

````text
| 3 | `provenance_status` | VARCHAR | sidecar | `candidates.csv` \| `fixture-needs-rework` |
````

Removed lines 193-196:

````text
| 5 | `stratum` | VARCHAR | sidecar | `community` \| `company-owned` \| `foundation` |
| 6 | `fact` | VARCHAR | sidecar | the control fact that assigned the stratum |
| 7 | `contested` | VARCHAR | sidecar | non-empty when two facts disagreed |
| 8 | `label_date` | VARCHAR | sidecar | when the stratum was assigned |
````

Removed line 213:

````text
| 25 | `history_relation` | VARCHAR | sidecar | `includes` \| `included_in` \| `mirror` \| `diverged` — about **inclusion**, not origin |
````

Removed line 231:

````text
| 43 | `author_date` | VARCHAR | `commits.autdate` | **string, not a timestamp**: `yyyy-MM-dd HH:mm:ss` in the JVM time zone (UTC on the run machines), no UTC offset |
````

Removed lines 271-273:

````text
no blank line necessary, continuation lines dropped). In dataset v1 (cregit `1f17663` and
later, and the rewrite of the `95cdc88` files) each typed list keeps one entry for each
person ([`LIMITATIONS.md`](LIMITATIONS.md)).
````

Removed line 298:

````text
The 29 provenance columns are injected as SQL literals from `project_meta.json`,
````

Removed lines 305-306:

````text
`data/affiliation.merged.csv` (**4,041 domains, 2,995 distinct company strings**),
canonicalizing the name through the reviewed `data/firm_canonical.csv`. The join is
````

Removed lines 315-329:

````text
tier. Counted from `data/affiliation.merged.csv` at this revision:

| `source` | domains | Confidence |
| --- | ---: | --- |
| `cncf-gitdm-single` (+ `-self-reference`) | 2,761 + 28 = **2,789 of 4,041 (69%)** | **one person only** |
| `gitdm` | 768 | curated, hand-checked |
| `cncf-gitdm` (+ `-self-reference`) | 204 + 5 = 209 | several people agree |
| `spinellis-sec` (+ `-self-reference`) | 111 + 2 = 113 | published source |
| `patch` | 72 | curated |
| `rich` | 55 | curated |
| `builtin` | 33 | definitional |
| `correction` | 2 | reviewed overlay, `data/affiliation.corrections.csv` |

`firm` is **not always a firm.** 58 domains carry the label `(Independent)` and 15
more carry `Independent` — the same category under two spellings, so any
````

Removed line 336:

````text
Use `kind` from the map (`free_provider`, 52 domains) to separate them, and treat
````

Removed lines 346-348:

````text
`data/firm_canonical.csv` is a **reviewed table, not a rule**: 62 rows, of which
51 merge a raw spelling into a canonical name and 11 record a candidate merge
that was examined and **rejected** (parent rollups such as `AWS`→`Amazon`;
````

Removed lines 365-370:

````text
Measured over the 200 drawn projects: 125 names equal `owner__repo` verbatim, 60
need slugging to match the URL, and **15 do not derive from the clone URL at
all** because the repository was renamed or transferred upstream. Any analysis
that joins back to a roster on `repo_name` silently loses at least those 15.
Reproduce the split with `select_corpus.project_name(owner, repo)` over
`manifest.sample.tsv`.
````

Removed lines 372-377:

````text
`clone_url` is the identity. `candidates.csv` keeps **one row per provenance
fact**, not one per project, so a repository that two rosters name appears twice:
24,405 rows cover 23,707 distinct non-empty `clone_url`s, 196 of which carry more
than one row. `select_corpus.dedupe_by_clone_url` is the resolution rule — group
by `clone_url`, and the row whose owner matches the URL wins — and anything
reading `candidates.csv` must apply it. `project_meta.py` does.
````

Removed line 434:

````text
| the Rust tokenizer shifts four columns | every `.rs` row |
````

Removed lines 440-441:

````text
| 2 of the 188 run-set projects have no Parquet | corpus totals |
| 185 of the 188 are published; read `excluded_because`, not file presence | corpus totals, per-org aggregates |
````

Removed line 451:

````text
| the 29 provenance names agree across three files in two repositories | `tests/test_meta_field_drift.py` — `project_meta.META_FIELDS`, `validate_schema.EXPECTED_COLUMNS[1:30]`, and the generator's own list |
````

Removed line 455:

````text
| duplicate `clone_url`s resolve the same way everywhere | `select_corpus.dedupe_by_clone_url`, called by `project_meta.build_meta` |
````

## `sources/README.md`

Removed lines 3-6:

````text
The two large files in this directory are **not produced by this pipeline.** They
are the published enterprise/cohort dataset of Spinellis et al., MSR 2020
(Zenodo `10.5281/zenodo.3742962`, CC-BY-4.0), vendored here so that corpus
selection is reproducible without a network fetch:
````

Removed lines 10-16:

````text
| `enterprise_projects.txt` | 17,264 | `select_corpus.parse_spinellis` → `F1_pool:spinellis-*` |
| `cohort_project_details.txt` | 311,223 | `select_corpus.parse_spinellis_cohort` → `F1_pool:spinellis-cohort` |

Both are used as **candidate pools only, never as stratum labels**: they label
contribution composition, and this pipeline labels control. `docs/CODEBOOK.md`
§5 states the rule and why; `docs/SPINELLIS-VALIDATION.md` is the generated
comparison between the two labellings.
````
