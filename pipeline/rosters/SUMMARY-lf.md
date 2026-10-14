# LF-family rosters, fetched 2026-10-05

| org_key | projects | rows | rows with github_slug | source URL | caveat |
|---|---|---|---|---|---|
| lf | 1603 (1323 Active + 280 Archived) | 1603 | 492 | https://api-gw.platform.linuxfoundation.org/project-service/v1/public/projects?pageSize=-1&orderBy=name (filtered Active, and unfiltered for Archived) | 520 rows give only a GitHub org; 2 test records dropped; the API returns every LFX entity (sub-foundations, working groups, SIGs, funds), type in `note`; 60 rows "LF Europe" |
| cncf | 258 | 294 | 292 | https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml | Monocle left out (`project:` only under `extra:`, an LF AI & Data project) |
| lfai | 62 | 92 | 90 | https://raw.githubusercontent.com/lfai/landscape/main/landscape.yml | none |
| lfedge | 13 | 13 | 10 | https://raw.githubusercontent.com/lf-edge/lfedge-landscape/main/landscape.yml | none |
| openssf | 33 | 33 | 25 | https://raw.githubusercontent.com/ossf/tac/main/README.md | none |
| lfnetworking | 13 | 451 | 444 | https://lfnetworking.org/projects/ and https://raw.githubusercontent.com/lfnetworking/member_landscape/main/landscape.yml | no stages published; 5 projects have no repo; ONAP alone has 288 rows |
| openjs | 43 | 43 | 40 | https://raw.githubusercontent.com/openjs-foundation/cross-project-council/main/README.md | stages as written (Impact, At-Large, Feature-Complete, Archived, Incubating); repos from Contributing Guide links |

Zephyr and DPDK are in `lf`, each as a GitHub org (zephyrproject-rtos, dpdk), so `github_slug` is empty. 0 GitHub REST calls. Written by the parent session from the agent's report, because the harness blocked the agent from writing this file.
