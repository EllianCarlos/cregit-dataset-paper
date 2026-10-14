# psf-sponsored (PSF fiscal sponsorees) — fetched 2026-10-05 (raw/psf-sponsored/fetched_at.txt)
- Source: https://www.python.org/psf/fiscal-sponsorees/ (raw/psf-sponsored/psf_fiscal-sponsorees.html, fetched with --compressed). Each `<h2>` after the intro is one sponsoree; 20 found.
- repo_url only when the sponsoree's paragraph links a github.com/gitlab.com owner/repo URL (github.com/sponsors/* excluded). Only Bandit (https://github.com/PyCQA/bandit) qualifies. The others link only websites, meetup pages or GitHub Sponsors pages (recorded in note).
- The list mixes software projects with user groups and conferences; no classification added (the source gives none).
- roster_status = `fiscal sponsoree`. The page says the PSF is not accepting new sponsorees at this time.
- Counts: 20 rows/projects, 1 repo_url, 1 github_slug. Parser: raw/_bin/parse_psfs.py. REST calls: 0.

## Home page lookup (2026-10-05)
- Input: the rows of psf-sponsored.csv with an empty repo_url (19). Output: psf-sponsored.repos.csv (one row per such row; the original CSV is untouched).
- Method: open the page the roster links for the project, ONE step, and take the repository link that page itself gives (code host owner/repo, GitLab/Gitea/cgit/gitweb, SourceForge code, Subversion). Fetcher raw/lookup/fetch.py: one request at a time, >=2 s between any two requests, manual redirects (each hop counted as a request), 30 s timeout, at most 2 retries on network error/5xx; Firefox User-Agent. raw/lookup/pass2.py then followed <meta refresh> targets once and made one more attempt with a plain descriptive User-Agent for pages that returned 403/406. Pages: raw/psf-sponsored/homepages/ (+ _fetch_log.jsonl). Candidates: raw/lookup/extract.py; the choice for each row was made by hand (raw/lookup/decisions.tsv) and every repo_url was checked to occur in the saved page (raw/lookup/assemble.py). GitHub REST calls: 0.
- Rule for choosing: the project's own main code repo (link labelled GitHub/Source/Code/Repository, or the repo named for the project); website-source repos ("Edit this page", *.github.io, *-web, webwml), theme credits, third-party projects and personal profiles are ignored. A link to a GitHub org / GitLab group / forge root -> repo_url = that URL, note "org only". github_slug only when repo_url is one github.com repo.
- Counts: 19 looked up; found repo 1 (1 with github_slug); org only 3; none named 0; not software 15; fetch failed 0; no link to follow 0.
- Judgement calls: the 15 user groups, conferences and PyLadies are classed not software from the PSF page's own descriptions and were not fetched. Jazzband, Pallets and PyPA are collectives; their homepages link GitHub orgs -> org only (Pallets also links pallets-eco). Twisted: twisted/twisted ('View Github').
- Failed hosts: none.
