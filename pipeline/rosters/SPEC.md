# Roster fetch spec (shared by all roster agents)

Goal: for each assigned organization, produce the list of projects it governs
(foundation), sponsors (fiscal sponsor) or owns (company), from the
organization's OWN published source, with the fetch date. This is evidence for
a research dataset; it must be truthful and reproducible.

Output: one file per organization, ~/tmp/rosters/<org-key>.csv, UTF-8, header:

  org_key,org_kind,project,repo_url,github_slug,roster_status,source_url,fetched_at,note

- org_key: short id, e.g. lf, lfai, asf, asf-incubator, openinfra, gnome, kde
- org_kind: foundation | fiscal-sponsor | company | government
- project: the project name as the source writes it
- repo_url: the canonical code repository URL the source gives (GitHub, GitLab, opendev, ...); empty if the source gives none
- github_slug: owner/repo on GitHub if the canonical repo is on GitHub OR an official GitHub mirror exists that the organization itself names (e.g. github.com/GNOME/<x>, github.com/KDE/<x>, github.com/openstack/<x>); else empty. Never guess a slug by name similarity.
- roster_status: the status the source gives (e.g. graduated, incubating, sandbox, active, retired, attic, podling); empty if none
- source_url: the exact URL read (API endpoint or file), one per row
- fetched_at: UTC ISO date-time of the fetch
- note: anything a reviewer needs (e.g. "mirror", "umbrella project, several repos")

Also write ~/tmp/rosters/<org-key>.method.md: 5-15 lines, the exact URLs,
commands, parsing rules, counts (projects, rows with repo_url, rows with
github_slug), and every judgment call you made. Save raw downloads under
~/tmp/rosters/raw/<org-key>/ so the parse can be re-run.

Rules:
- Read-only. Public sources only. Prefer machine-readable sources (JSON/YAML
  APIs, files in the organization's own git repos via raw URLs, GitLab APIs).
- GitHub REST quota is shared with a running measurement: at most 150
  `gh api` REST calls per agent in total. raw.githubusercontent.com and
  GitHub GraphQL do not count against it; use them for org repo listings.
- One row per repository. A project with several repositories gets several
  rows if the source lists them; otherwise one row with the main repository.
- Do not add projects from memory. If a source cannot be fetched or parsed,
  record that in the method file and stop for that org; do not substitute.
- Do not write anywhere except ~/tmp/rosters/.
