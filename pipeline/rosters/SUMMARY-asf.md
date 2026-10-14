# Roster summary — foundations batch (asf agent), fetched 2026-10-05 UTC

| org_key | projects | rows | rows with github_slug | source URL | fetch issues |
|---|---|---|---|---|---|
| asf | 349 (216 PMCs, 310 DOAP projects) | 2677 | 2419 | https://projects.apache.org/json/foundation/projects.json + repositories.json + committees.json | none; 85 infra repos match no PMC and were left out |
| asf-incubator | 376 | 676 | 505 | https://whimsy.apache.org/public/public_podlings.json | podlings.xml redirects to svn, not used; repos matched to podlings by name prefix |
| asf-attic | 104 (96 committees + 8 sub-projects) | 284 | 170 | https://whimsy.apache.org/public/committee-retired.json | none |
| eclipse | 687 | 4298 | 3455 | https://projects.eclipse.org/api/projects (7 pages, all fetched) | none; org-level GitHub/GitLab repos listed via GraphQL and the gitlab.eclipse.org API |
| openinfra | 59 | 769 | 664 | https://opendev.org/openstack/governance/raw/branch/master/reference/projects.yaml + https://openinfra.org/projects/ | user-committee-repos.yaml returns 404; Airship is not on openinfra.org, so not added |
| documentfoundation | 76 | 76 | 2 | https://gerrit.libreoffice.org/projects/?d&t | only core and online have a GitHub mirror named by TDF |
| netbsd | 3 | 3 | 3 | https://wiki.netbsd.org/github/ | none |
| freebsd | 3 | 3 | 3 | https://docs.freebsd.org/en/books/handbook/mirrors/ | none |
| osgeo | 100 | 100 | 64 | https://www.osgeo.org/wp-admin/admin-ajax.php?action=getItems&postType=project | none; incubating status from the wiki Incubation_Committee page |
| obf | 27 | 27 | 3 | https://www.open-bio.org/projects/ | the page gives homepages, not repos; OBF is an SPI associated project |
| xorg | 386 | 386 | 0 | https://gitlab.freedesktop.org/api/v4/groups/xorg/projects | none; no GitHub mirror named |

GitHub REST calls used: 0 (GraphQL: 25 queries). Each org has a CSV (`<org>.csv`) and a method file (`<org>.method.md`). Raw downloads are under raw/<org>/. The parser is scripts/build_foundations.py, and it re-runs offline.
