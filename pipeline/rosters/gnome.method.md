# gnome (GNOME Foundation) — fetched 2026-10-05 (raw/gnome/fetched_at.txt)
- Roster: GitLab API `https://gitlab.gnome.org/api/v4/groups/GNOME/projects?per_page=100&include_subgroups=false&page=N`, N=1..4 (x-total-pages 4). Raw: raw/gnome/page*.json, headers h*.txt.
- One row per project: project=`name`, repo_url=`web_url`, roster_status=`archived` if GitLab `archived` is true, else `active`.
- The endpoint's default with_shared=true returns 3 projects shared into the group from other namespaces (Infrastructure, Teams/Engagement, Teams/Releng); kept, flagged in note.
- Mirror rule: GNOME's GitHub org description says contributions are forwarded to gitlab.gnome.org and its website is https://handbook.gnome.org/infrastructure/github_mirror.html, which states "The GNOME GitHub Mirror is an automatically updated copy of the GNOME GitLab group" (raw/gnome/handbook_github_mirror.html). github_slug=GNOME/<repo> only when a repo with that exact path (case-insensitive) exists in the GitHub GNOME org listing (GitHub GraphQL organization(login:"GNOME").repositories, 320 repos, raw/gnome/github_GNOME.json).
- Counts: 318 projects, 318 rows, 318 with repo_url, 314 with github_slug (4 without: the 3 shared projects and GNOME/Initiatives), 1 archived.
- Parser: raw/_bin/parse_gnome.py. REST calls: 0.
