# openjs: OpenJS Foundation

- Source: https://raw.githubusercontent.com/openjs-foundation/cross-project-council/main/README.md, section "### OpenJS Foundation Projects" (the repo has no separate projects data file; root listed via GraphQL). Fetched with curl at 2026-10-05T01:35:23Z into raw/openjs/README.md. PROJECT_PROGRESSION.md was saved for the stage definitions.
- Parse: `/usr/bin/python3 raw/openjs/parse_openjs.py`. roster_status is the `####` heading, with "Projects" stripped: Impact, At-Large, Feature-Complete, Archived, Incubating. The current README has no "growth" or "emeritus" stage.
- The tables have no repository column. Judgement call: repo_url is the project-name link when that is a github.com/owner/repo URL (Globalize, Chassis, PEP). Otherwise it is the owner/repo prefix of the "Contributing Guide" link. The note records which rule applied. I did not check that a Contributing-Guide repo is the main code repo; Interledger.js points to interledger/rfcs, and vis.gl, an umbrella, points to visgl/deck.gl.
- Disagreements are noted. Globalize's project link is jquery/globalize while its contributing link is globalizejs/globalize. Jest's contributing link is facebook/jest while its charter link is jestjs/jest.
- No GitHub repo link: Express (contributing link is expressjs.com), Node-RED (nodered.org) and RequireJS (requirejs.org).
- Counts: 43 projects, 43 rows. Rows per stage: Impact 6, At-Large 20, Feature-Complete 5, Archived 7, Incubating 5. Rows with repo_url: 40. Rows with github_slug: 40.
- Working Groups are excluded.
