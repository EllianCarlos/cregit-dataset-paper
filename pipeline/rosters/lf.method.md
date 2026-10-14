# lf: The Linux Foundation (LFX project-service public API)

- Page read: https://www.linuxfoundation.org/projects (raw/lf/projects.html). The page has no project list in the HTML. Its module script `module_All_Projects_API.min.js` (saved in raw/lf/) fetches the list in the browser from `https://api-gw.platform.linuxfoundation.org/project-service/v1/public/projects?pageSize=-1&orderBy=name&$filter=status%20eq%20Active`. That is the LFX project-service public API, so it covers "LFX if public" as well.
- Fetches: the Active URL above at 2026-10-05T01:31:48Z (raw/lf/projects_api.json, 1325 records). The same URL without `$filter` at 2026-10-05T01:32:18Z (raw/lf/projects_api_allstatus.json, 1605 records: 1325 Active, 280 Archived). curl only, no GitHub REST calls.
- Parse: `/usr/bin/python3 raw/lf/parse_lf.py`. One row per record, because the API has one RepositoryURL field per record. Active rows come from the filtered file. Archived rows come from the unfiltered file and carry that URL as source_url.
- roster_status is the API's `Status` (Active or Archived). The API's `Category` (Sandbox, Incubating, Graduated, SIG, ...) goes in `note` as lfx_category, along with type (Project or Project Group), parent (ParentSlug), legal_parent and lfx_slug.
- Judgement call: I dropped the 2 `TestRecord=true` records ("Test Project Group IT", "Test Project IT").
- Judgement call: the API contains every LFX entity, including sub-foundation children (CNCF, LF AI and others), working groups, SIGs, funds and Project Groups. I did not filter these out. Use `note` (type, lfx_category, parent) to subset.
- The website renders only records that have both a Website and a ProjectLogo. I did not apply that display filter. The 24 records with DisplayOnWebsite=false are flagged in `note`.
- LF Europe: rows whose legal_parent is "Linux Foundation Europe", or whose parent is `lfeurope`, have note "LF Europe" (60 rows). Example: Servo Project (lfx_slug=servo-llc, Active, no RepositoryURL).
- github_slug is set only when RepositoryURL has the form github.com/owner/repo. 520 rows point at a GitHub org (github.com/owner only); those keep repo_url, leave the slug empty, and carry a note.
- Counts: 1603 rows / 1603 projects (1323 Active + 280 Archived). Rows with repo_url: 1034 (Active 863). Rows with github_slug: 492 (Active 405). Five slugs occur twice (e.g. prestodb/presto, academysoftwarefoundation/openvdb).

## zephyr-dpdk-check
- Zephyr: **yes**. "Zephyr Project" (lfx_slug=zep, Status Active, type Project, legal_parent The Linux Foundation). Its RepositoryURL is the org https://github.com/zephyrproject-rtos, not a repo, so github_slug is empty. The source does not name zephyrproject-rtos/zephyr.
- DPDK: **yes**. "Data Plane Development Kit (DPDK)" (lfx_slug=dpdk, Active, type Project Group, legal_parent The Linux Foundation). Its RepositoryURL is the org https://github.com/dpdk, so github_slug is empty. Child records with parent=dpdk: DTS (no repo), NFF-Go (intel-go/nff-go), Pktgen (pktgen/Pktgen-DPDK), SPP (http://git.dpdk.org/apps/spp/).
