# lfedge: LF Edge landscape

- Source: https://raw.githubusercontent.com/lf-edge/lfedge-landscape/main/landscape.yml. The repo is at github.com/lf-edge/lfedge-landscape, default branch main, not archived, last commit 2026-09-30 (GraphQL). Fetched with curl at 2026-10-05T01:30:35Z into raw/lfedge/landscape.yml.
- Parse: `/usr/bin/python3 raw/landscape_parse.py lfedge raw/lfedge/landscape.yml <url> 2026-10-05T01:30:35Z lfedge.csv`. "Hosted projects only" means items with an item-level `project:` key. Its values are impact, growth and at_large, kept as given.
- Counts: 13 projects, 13 rows (no additional_repos). Rows per status: impact 5, growth 2, at_large 6. Rows with repo_url: 11. Rows with github_slug: 10.
- InfiniEdge AI and InstantX have no repo_url. FIDO Device Onboard's repo_url is the org github.com/fido-device-onboard, so it has no slug.
- The landscape gives one repo per project. For example, Akraino's repo is akraino-edge-stack/eliot, which is the repo the landscape lists, not necessarily the main one.
- I found no items whose homepage or repo is on lfedge.org but which lack a `project:` key, so no hosted project was left out by the rule.
