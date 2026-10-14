# lfai: LF AI & Data landscape

- Source: https://raw.githubusercontent.com/lfai/landscape/main/landscape.yml (main is the default branch; last commit 2026-09-28, both via GraphQL). Fetched with curl at 2026-10-05T01:30:35Z into raw/lfai/landscape.yml.
- Parse: `/usr/bin/python3 raw/landscape_parse.py lfai raw/lfai/landscape.yml <url> 2026-10-05T01:30:35Z lfai.csv`. Same rules as cncf: only items with an item-level `project:` key; one row per repo_url and per additional_repos entry; deduplicated on (name, repo_url).
- Counts: 62 projects, 92 rows. Rows per status: graduated 43, incubating 21, incubation 1, sandbox 22, archived 5. Rows with repo_url: 92. Rows with github_slug: 90.
- Judgement call: one item uses `project: incubation`, not `incubating`. I kept it as given and did not normalise it.
- OAAX and Vortex have GitHub org URLs (github.com/OAAX-standard, github.com/vortex-data), so their slugs are empty.
