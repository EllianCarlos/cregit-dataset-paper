# bytecodealliance — fetched 2026-10-05 (raw/bytecodealliance/fetched_at.txt)
- Source: https://bytecodealliance.org/projects (raw/bytecodealliance/projects.html). Parsed the `<h3><a href=...>Name</a></h3>` entries under the "Core projects" (roster_status `core`) and "Hosted projects" (`hosted`) headings.
- repo_url = the entry's link; github_slug = owner/repo from it. Cranelift links to a subdirectory (bytecodealliance/wasmtime/tree/main/cranelift); repo_url is set to the containing repo bytecodealliance/wasmtime, noted.
- Counts: 36 projects (1 core: Wasmtime; 35 hosted), 36 rows, 36 repo_url, 36 github_slug. The GraphQL org listing (raw/bytecodealliance/github_bytecodealliance.json, 101 repos) was saved for reference but not used for rows.
- Parser: raw/_bin/parse_ba.py. REST calls: 0.
