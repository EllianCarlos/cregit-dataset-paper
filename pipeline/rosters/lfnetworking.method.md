# lfnetworking: LF Networking

- Project list: https://lfnetworking.org/projects/, fetched with curl at 2026-10-05T01:34:10Z (raw/lfnetworking/projects.html). The "Our Projects" grid lists 12 entries. Stratoweave appears only in the page's Projects menu; I added it with a note. The page gives websites only, no repositories and no stages.
- Repositories: LFN's own landscape (landscape.lfnetworking.org; repo lfnetworking/member_landscape, linked from the projects page), https://raw.githubusercontent.com/lfnetworking/member_landscape/main/landscape.yml, fetched at 2026-10-05T01:34:52Z. I used items with `project: lfn` in category "LF Networking Projects" (8 items), taking repo_url plus every additional_repos entry. I ignored items with `project: lfn-5g`, `lfedge`, `cncf` and `foundation`, which are Super Blueprint and partner entries.
- Parse: `/usr/bin/python3 raw/lfnetworking/parse_lfn.py`. I mapped site names to landscape names by hand: CNTI→CNTi, OpenDaylight→Opendaylight, and the rest are identical. Duranta, Essedum, OpenAN, O-RAN-SC and Stratoweave have no lfn landscape item, so each gets one row with no repo_url and the page as source_url.
- roster_status is empty, because neither source gives a lifecycle stage. The page text calls Duranta an "incubation project" and Essedum a "candidate project"; both are in `note`.
- Counts: 13 projects, 451 rows (ONAP 288, OpenDaylight 101, Nephio 26, FD.io 21, Anuket 7, others 1 each). Rows with repo_url: 444. Rows with github_slug: 444.
- 21 repo names carry an "archived-" prefix (noted). CNTI and L3AF have landscape items without repo_url.
- I made no claim about whether a GitHub repo is a mirror; the landscape does not say.
