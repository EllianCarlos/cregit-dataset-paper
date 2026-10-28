# cncf: CNCF landscape

- Source: https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml (master is the default branch, confirmed with GraphQL). Fetched with curl at 2026-10-05T01:29:35Z into raw/cncf/landscape.yml.
- Parse: `/usr/bin/python3 raw/landscape_parse.py cncf raw/cncf/landscape.yml <url> 2026-10-05T01:29:35Z cncf.csv`. The parser walks landscape > subcategories > items and keeps items that have an item-level `project:` key. roster_status is that value.
- One row for the item's repo_url, plus one row per `additional_repos[].repo_url` (note "additional_repos entry"). Rows are deduplicated on (name, repo_url), for items that are listed under several categories.
- github_slug is set only for github.com/owner/repo URLs.
- Counts: 258 projects, 294 rows. Rows per status: graduated 42, incubating 55, sandbox 169, archived 28. Rows with repo_url: 293. Rows with github_slug: 292.
- Edge cases: Curiefense (archived) has no repo_url. CoHDI's repo_url is the org github.com/CoHDI, so it has no slug.
- Judgment call: Monocle carries `project: sandbox` only under `extra:`, not at item level, and its description says it is an LF AI & Data Sandbox project. I excluded it under the item-level-key rule. This is why `grep project:` finds 259 lines against 258 projects.
