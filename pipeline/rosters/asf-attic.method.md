# asf-attic — retired ASF projects (the Attic) — method
- Source: https://whimsy.apache.org/public/committee-retired.json, fetched 2026-10-05T01:31:01Z: 96 retired committees, with retired and established dates. Raw: raw/asf-attic/. roster_status = attic on every row.
- Repos, by rule:
  - repositories.json keys (raw/asf/) that match a retired committee id by longest prefix and match no current PMC: 243 rows.
  - DOAP `repository` entries of the projects.json entries with pmc=attic (key attic-<id>) that are not already covered. The same URL normalisation as asf applies.
- 8 projects.json attic entries (ecs, jakarta_cactus, oltu_-_parent, open_climate_workbench, oro, regexp, traffic_control, xindice) are not retired committees. They are retired sub-projects. They were added with source_url = projects.json and a note saying so.
- Retired committees with no repo found: one row with empty repo_url.
- github_slug apache/<key> for gitbox URLs. svn keys and svn DOAP URLs get no slug.
- Counts: 104 projects (96 committees plus 8 sub-projects), 284 rows, 281 with repo_url, 170 with github_slug. GitHub REST calls: 0.
