# eclipse — Eclipse Foundation projects — method
- Source: https://projects.eclipse.org/api/projects?page=N&pagesize=100, fetched for N=1.. until a page came back empty (pages 1-7 hold 687 projects; page 8 = []). No page cap. Fetched 2026-10-05T01:32:10Z. Raw: raw/eclipse/p*.json.
- roster_status = API `state` (Regular 203, Incubating 255, Archived 229 projects). The note gives project_id and top_level_project.
- Rows per project:
  - (a) each `github_repos[].url`: 431 rows. github_slug comes from the URL.
  - (b) when `github.org` is set (311 orgs, 313 projects), every public repo of that org minus `ignored_repos`. The org repos were listed through GitHub GraphQL (23 queries, no REST), saved as raw/eclipse/github-orgs/<org>.json: 3026 rows. Archived and fork flags are in the note.
  - (c) when `gitlab.project_group` is set (81 groups), the projects of that group from https://gitlab.eclipse.org/api/v4/groups/<group>/projects?include_subgroups=true, minus `ignored_sub_groups`. Saved as raw/eclipse/gitlab-groups/: 666 rows. 3 groups that list no projects get one row with the group URL.
  - (d) projects with none of these: one row with empty repo_url (172 rows). `gerrit_repos` was null for every project.
- Judgement: Eclipse defines a declared github.org / gitlab group as "all repos in it belong to the project", so the org listings were enumerated. eclipse-gemini is declared by 3 projects, so its repos appear under each of them.
- Counts: 687 projects, 4298 rows, 4126 with repo_url, 3455 with github_slug. GitHub REST calls: 0. GraphQL: 23.
