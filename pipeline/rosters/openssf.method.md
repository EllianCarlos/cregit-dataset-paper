# openssf: OpenSSF TAC project list

- Source: https://raw.githubusercontent.com/ossf/tac/main/README.md. This is the TAC's canonical list of Working Groups, Projects and SIGs; the default branch is main. Fetched with curl at 2026-10-05T01:33:33Z into raw/openssf/tac-README.md. I also saved organizational-structure-overview.md and EMERITUS.md; EMERITUS.md lists emeritus TAC members, not projects.
- Parse: `/usr/bin/python3 raw/openssf/parse_openssf.py`. It reads the markdown tables under `### Projects` (31 rows) and `### OpenSSF affiliated projects` (2 rows, noted as affiliated). roster_status is the link text of the Status cell (Sandbox, Incubating, Graduated or TBD). The Repository cell gives repo_url, and the Sponsoring Org goes in note.
- Judgment call: Working Groups and SIGs are excluded, because they are not projects under the TAC structure document. That includes the "OpenVEX" SIG row; the OpenVEX project row is kept.
- Counts: 33 projects, 33 rows. Rows per status: Sandbox 20, Incubating 4, Graduated 3, TBD 6. Rows with repo_url: 32 (AMPEL has none). Rows with github_slug: 25.
- Six entries link only a GitHub org and so have no slug: Gemara, OpenBao, OpenVEX, SBOMit, Secure Agentic Framework, Sigstore. Core Toolchain Infrastructure is at git.coretoolchain.dev.
- "Model signing" links to a file inside sigstore/model-transparency. I took the slug from that link and noted it.
