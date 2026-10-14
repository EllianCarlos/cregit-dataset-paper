# mozilla (Mozilla Corporation, a subsidiary of the Mozilla Foundation) — listing fetched 2026-10-05T01:31:04Z
- Source: the GitHub org `mozilla` (https://github.com/mozilla; org websiteUrl https://www.mozilla.org/), listed via GitHub GraphQL `organization(login:"mozilla").repositories` (first:100, paginated, ordered by name). Script raw/_bin/gh_org_repos.py; raw: raw/mozilla/github_mozilla.json.
- One row per public repo: repo_url=url, github_slug=nameWithOwner, roster_status=`archived`/`active` from GitHub isArchived; forks (288) and mirrors noted.
- Limits: this is an org listing, not a curated Mozilla list of projects. It includes experiments, forks, archived repos (1954 of 2574) and docs. It does not cover other Mozilla-run GitHub orgs or code hosted at hg.mozilla.org / other hosts; no mozilla.org page listing projects was used.
- Counts: 2574 rows/projects, 2574 with repo_url, 2574 with github_slug. REST calls: 0 (GraphQL only).

## Decision 2026-10-05
All rows are org_kind company: Mozilla Corporation, a for-profit subsidiary of the Mozilla Foundation, runs these projects. The repositories are org-level evidence (plan R2): the source is the org listing, not a curated list. The original file is mozilla.orig.csv.
