# kde (KDE e.V.) — fetched 2026-10-05 (raw/kde/fetched_at.txt)
- Groups: `https://invent.kde.org/api/v4/groups?top_level_only=true&per_page=100&all_available=true` (33 top-level groups, raw/kde/groups_toplevel.json).
- Projects: `https://invent.kde.org/api/v4/groups/<group>/projects?per_page=100&include_subgroups=true&page=N`, all pages, every group (raw/kde/proj_<group>_<N>.json).
- Excluded by judgment: `neon` (1367 distribution-packaging repos), `qt` (263; group says "Replica of the Qt Project repositories"), `mirrors` (12; "Mirrors of open source software, synced from their upstream repositories"). All other 30 groups kept, including teams, websites, sysadmin, documentation, packaging, unmaintained, historical (group recorded in note).
- roster_status: `archived` if GitLab archived is true, else `active` (`unmaintained`/`historical` groups are fully archived; group is in note). Projects deduplicated by GitLab id.
- Mirror rule: KDE's GitHub org description says "Official read-only mirror of the KDE project" and links https://community.kde.org/Infrastructure/Github_Mirror (raw/kde/community_github_mirror.html: "KDE is managing a read-only mirror of our repos on GitHub ... https://github.com/KDE"). GitHub KDE org listed via GraphQL (1218 repos, raw/kde/github_KDE.json). github_slug=KDE/<repo> if (a) the GitHub repo's homepageUrl equals the invent web_url (783 rows), or (b) the repo name equals the invent path, that path is unique across ALL fetched invent projects (incl. excluded groups), and the GitHub repo's homepage does not point to a different invent URL (341 rows). Otherwise no slug (37 rows have a same-named GitHub repo but are ambiguous).
- Counts: 1546 rows (1546 repos; 1525 distinct names), 1546 with repo_url, 1124 with github_slug; 956 active, 590 archived.
- Parser: raw/_bin/parse_kde.py. REST calls: 0.

## Decision 2026-10-05
The 341 slugs matched only by a unique repository name are dropped (the spec forbids a name match). The 783 slugs whose GitHub mirror homepage points to the invent URL stay, as information only. KDE repositories are measured from invent.kde.org (plan R3). The original file is kde.orig.csv.
