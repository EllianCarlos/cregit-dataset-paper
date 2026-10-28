# Projects dataset: where each input comes from

This folder holds every input of the project selection, with its source and
fetch date. The plan is `../DATASET-RESOURCING-PLAN.md`. Each stage writes its
output here, so the selection can be re-run from these files.

Snapshot date: **2026-10-05**. All age tests use this date. The push cutoff is
550 days before it: 2025-04-03.

## Rule

Each input file records, for each row, the URL that was read and the fetch time
(UTC). Raw downloads are kept, so each parse can be run again without network
access. A page that only the author's browser could read (bot checks) has the
source "page read in the author's browser", with the URL and the time.

## Organization list

| Input | Source | Fetched | Copy |
| --- | --- | --- | --- |
| Base list of organizations | https://opensource.com/resources/organizations | 2026-10-05 | `rosters/raw/opensource-com/` |

## Rosters (stage S1)

One file `rosters/<org>.csv` for each organization. Columns: `org_key,
org_kind, project, repo_url, github_slug, roster_status, source_url,
fetched_at, note`. The file `rosters/<org>.method.md` gives the exact URLs, the
parse rules, the counts and each judgment call. Raw downloads are in
`rosters/raw/<org>/`. Scripts are in `rosters/scripts/` and `rosters/raw/`.
The common rules are in `rosters/SPEC.md`.

| Roster | Rows | Main source |
| --- | ---: | --- |
| asf | 2,677 | https://projects.apache.org/json/foundation/projects.json |
| asf-incubator | 676 | https://whimsy.apache.org/public/public_podlings.json |
| asf-attic | 284 | https://whimsy.apache.org/public/committee-retired.json |
| bytecodealliance | 36 | https://bytecodealliance.org/projects |
| cncf | 294 | https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml |
| documentfoundation | 76 | https://gerrit.libreoffice.org/projects/ |
| eclipse | 4,298 | https://projects.eclipse.org/api/projects |
| freebsd | 3 | https://docs.freebsd.org/en/books/handbook/mirrors/ |
| gnome | 318 | https://gitlab.gnome.org/api/v4/groups/GNOME/projects |
| gnu | 388 | https://www.gnu.org/software/allgnupkgs.html (package pages: see below) |
| kde | 1,546 | https://invent.kde.org/api/v4/groups |
| lf | 1,603 | https://www.linuxfoundation.org/projects |
| lfai | 92 | https://raw.githubusercontent.com/lfai/landscape/main/landscape.yml |
| lfedge | 13 | https://raw.githubusercontent.com/lf-edge/lfedge-landscape/main/landscape.yml |
| lfnetworking | 451 | https://lfnetworking.org/projects/ |
| mozilla | 2,574 | https://github.com/mozilla (company label, see the method file) |
| netbsd | 3 | https://wiki.netbsd.org/github/ |
| numfocus | 166 | https://numfocus.org/sponsored-projects |
| obf | 27 | https://www.open-bio.org/projects/ |
| openinfra | 769 | https://opendev.org/openstack/governance (reference/ files) |
| openjs | 43 | https://raw.githubusercontent.com/openjs-foundation/cross-project-council/main/README.md |
| openssf | 33 | https://raw.githubusercontent.com/ossf/tac/main/README.md |
| osgeo | 100 | https://www.osgeo.org/projects/ |
| psf | 96 | https://www.python.org/psf/mission/ |
| psf-sponsored | 20 | https://www.python.org/psf/fiscal-sponsorees/ |
| redhat | 202 | https://redhatofficial.github.io/ (pool source, company evidence) |
| rust-foundation | 246 | https://foundation.rust-lang.org/ |
| sfc | 44 | https://sfconservancy.org/projects/current/ |
| spi | 48 | https://www.spi-inc.org/projects/ |
| xorg | 386 | https://gitlab.freedesktop.org/api/v4/groups/xorg |

All rosters were fetched on 2026-10-05. The files `<org>.repos.csv` (obf, sfc,
spi, numfocus, psf-sponsored) map a project home page to its repository. Each
row gives the page that was read.

**GNU package pages.** The cgit index of Savannah is in
`rosters/raw/gnu/cgit_index_page1_links.txt` and `..._page2_links.txt`. The
package pages that gnu.org served only to the author's browser are in
`rosters/raw/gnu/pages_browser/` and `gnu_browser_repos.tsv`. Status on
2026-10-05: 8 of 53 pages read; the next one is `gnubiff`.

## Old pool and the first share measurement (2026-10-04)

`share-2026-10-04/` keeps the measurement that led to the rule "tokenizable
bytes are at least 5% of the code bytes".

| File | What it is |
| --- | --- |
| `candidates.csv` | the old pool, 24,405 rows; cregit-token-pipeline commit `6ac22e7`, sha256 `c18461fe…7d6a` |
| `measure_share.py` | the measurement: GitHub recursive tree of HEAD, one call per repository |
| `shares.jsonl` | 10,526 rows (3,948 included and 6,578 excluded only by language), fetched 2026-10-04 23:20 to 2026-10-05 01:43 UTC |
| `prog_exts.py`, `languages.yml` | code extensions: Linguist languages of type `programming` |
| `what_if.py` | the old draw with a share rule |

This measurement did not record the HEAD commit or a fetch time for each row.
Stage S3 measures again, with both.

## Pinned versions

| Item | Version |
| --- | --- |
| Linguist `languages.yml` | github-linguist/linguist commit `538da05f034fa5c83bd81df128d144e208898da3` (2026-09-21), blob `1f72a41c`, sha256 `183243e3…e043` |
| Universal mask (`file_mask.py`) | cregit-token-pipeline commit `91d6ccab70c630dfef5679a483832b053d23e86b` |

## GitHub search (stage S1)

`s1-search/search.py` reads the query
`stars:>400 archived:false fork:false pushed:>=2025-04-03`, all languages, with
the GitHub GraphQL search API. The query had 80,993 results on 2026-10-05.
The script splits it into star bands and creation-date windows of at most
1,000 results. Outputs: `segments.jsonl` (each query, its result count and the
rows read), `repos.jsonl` (each repository, with `fetched_at` and the default
branch HEAD commit) and `run.log`.

Result (2026-10-05 20:47 to 2026-10-06 00:41 UTC): 121 segments, none over
1,000 results; 81,000 rows, 80,990 distinct repositories (`databaseId`). Six
segments differ from their result count by 2 repositories in total, because
star counts changed during the read. `repos.jsonl` is stored as
`repos.jsonl.xz` (`xz -d -k` restores it; `repos.jsonl.sha256` checks it). `run-attempt1.log` is a first start that
stopped on HTTP 502 errors before it read any segment; the script then got an
adaptive page size.

## Pool (stage S2)

`s2-pool/resolve.py` looks up each slug of the old pool (`candidates.csv`) and
of the rosters (including the `*.repos.csv` home page lookups) with GitHub
GraphQL, 2026-10-06 00:10 to 01:51 UTC. GraphQL does not follow a rename, so
`s2-pool/resolve_rest.py` checks each slug that it did not find with the REST
API, which follows the redirect (2026-10-06 01:51 to 02:03 UTC). A 403 with
quota left is the repository's own status (blocked), not a rate limit.

`s2-pool/build_pool.py` merges the search rows and the looked-up slugs by
`databaseId`, and adds the roster repositories on other hosts by their
normalized URL. It drops no row. Counts are in `s2-pool/pool_counts.txt`:

- 106,985 pool rows: 104,608 on GitHub (80,990 from the search), 2,377 on
  other hosts.
- 36,088 input slugs: 35,560 found, 3,470 of them under another name;
  528 not found, each with its reason in `s2-pool/unresolved.csv`
  (511 HTTP 404, 15 HTTP 451, 2 HTTP 403).
- 780 roster rows give a GitHub organization, not a repository:
  `s2-pool/roster_orgs.csv`, evidence for stage S5.

`pool.csv` and `resolve.jsonl` are stored as `.xz`, with `checksums.sha256`.

## Measurement (stage S3)

The method, with flow diagrams, is in `S3-MEASUREMENT.md`.

`s3-measure/measure_trees.py` reads the recursive tree of each GitHub pool row
at the HEAD commit that S1 or S2 recorded (`head_oid`), not at a later HEAD.
It measures the 33,699 rows whose Linguist bytes include C, C++, Java or Rust.
70,775 rows have none of these languages, and 134 have no HEAD commit; stage
S4 records them with their reason. Started 2026-10-06 02:04 UTC. The log
records the mask hash (sha256 `665c23c0…`) and the commit of `file_mask.py`.

## Company org repositories and company pages (2026-10-06)

| Folder | What it is |
| --- | --- |
| `sources/company-orgs/` | `list_org_repos.py`: every public repository of the 506 kept company orgs, GitHub GraphQL, 2026-10-06 04:13 to 06:45 UTC. 81,425 rows; for each org the rows read equal GitHub's `totalCount` (`orgs.jsonl`). `repos.jsonl.xz` with `repos.jsonl.sha256`. |
| `sources/company-pages/` | `company_pages.py`: 941 URLs for 150 companies, fetched with curl, one at a time, 2026-10-06 04:14 to 04:50 UTC. `raw/` keeps each body and its headers unchanged; `fetch.tsv` has one row for each fetch. `evidence.csv`: 35 orgs have their own published website (GitHub profile), on a company domain, that links to them. |
| `sources/company-pages/browser/` | `todo.tsv`: the 157 pages that blocked curl (HTTP 403, a bot check, or no answer). `done.tsv` and `<sha1>.txt`: 29 of them read in the author's Firefox on 2026-10-06. These copies are agent transcriptions of the browser tool output, not exact bytes; none of them links to a kept org. |

**No guessed URLs (decided 2026-10-06).** The first run also fetched guessed
patterns (`opensource.<domain>`, `<domain>/opensource`, ...). Their rows stay in
`fetch.tsv`, `raw/`, `browser/todo.tsv` and `browser/done.tsv` as a record, but
they give no evidence. Only the website that each org publishes in its GitHub
profile counts. Of these, 30 blocked curl; `browser/todo_websites.tsv` lists
them, and `browser/done_websites.tsv` records the browser reads, with only the
title and the github.com link lines of each page (`w_<sha1>.txt`). All 30 are read: 25 ok, 2 bot checks, 1 maintenance page, 1 add-on permission refusal (company.nokia.com), 1 tool error (www.hpe.com). `browser_evidence.py` writes `evidence_browser.csv`: 5 more orgs (MarvellEmbeddedProcessors, Oracle, mysql, Orange-OpenSource, orange-cloudfoundry), so 40 orgs in total have a company page. A headless
Chromium (nixpkgs `chromium --headless --dump-dom`) does not pass the bot checks
(Cloudflare "Just a moment", Akamai "Access Denied").
