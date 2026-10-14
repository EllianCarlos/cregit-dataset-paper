# xorg — X.Org Foundation — method
- Source: the freedesktop GitLab API. https://gitlab.freedesktop.org/api/v4/groups/xorg gives the description "X.Org and X11 protocol, server, driver, library, and application development". Projects came from https://gitlab.freedesktop.org/api/v4/groups/xorg/projects?include_subgroups=true&per_page=100&page=1..4 (x-total 386), fetched 2026-10-05T01:40:42Z. Raw: raw/xorg/. The X.Org wiki home (https://www.x.org/wiki/, saved) links its issues to gitlab.freedesktop.org/groups/xorg.
- One row per GitLab project: project = path_with_namespace (subgroups app, driver, lib, proto, font, util, test, doc, data, plus 4 at the top level). repo_url = web_url. roster_status = archived (124) or active (262), from the GitLab `archived` flag.
- No forks or pull mirrors are in the group. X.Org names no GitHub mirror, so github_slug is empty.
- Judgement: the GitLab xorg group is taken as the set of repos X.Org governs. Freedesktop projects outside that group (Mesa, Wayland and others) are not included.
- Counts: 386 projects, 386 rows, 386 with repo_url, 0 with github_slug. GitHub REST calls: 0.
