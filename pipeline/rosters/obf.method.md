# obf — Open Bioinformatics Foundation — method
- Source: https://www.open-bio.org/projects/ (raw/obf/projects.html, a Hugo page with unquoted attributes), fetched 2026-10-05T01:39:11Z. The sections "Member Projects", "Affiliated Projects", "Other Related Projects" and "Retired Projects" give roster_status member / affiliated / other related / retired.
- One row per project named in those sections: 5 member, 2 affiliated, 7 other related, 13 retired. The page links each project's homepage, not its repository, so repo_url is left empty unless the page itself links a GitHub repo:
  - BioPython: its license link points into github.com/biopython/biopython.
  - BlipKit and Biolib (retired): linked directly to GitHub.
  Homepages are in the note. Repos were not looked up anywhere else.
- SPI status: OBF is itself an SPI associated project. https://www.spi-inc.org/projects/ lists "Open Bioinformatics Foundation", and https://www.spi-inc.org/projects/obf/ describes it, naming the services "Accepting donations, Holding assets, Underwriting events" and a project liaison. Both pages are saved in raw/obf/. So org_kind = foundation here, but OBF's legal and fiscal home is SPI.
- Counts: 27 projects, 27 rows, 3 with repo_url, 3 with github_slug. GitHub REST calls: 0.

## Home page lookup (2026-10-05)
- Input: the rows of obf.csv with an empty repo_url (24). Output: obf.repos.csv (one row per such row; the original CSV is untouched).
- Method: open the page the roster links for the project, ONE step, and take the repository link that page itself gives (code host owner/repo, GitLab/Gitea/cgit/gitweb, SourceForge code, Subversion). Fetcher raw/lookup/fetch.py: one request at a time, >=2 s between any two requests, manual redirects (each hop counted as a request), 30 s timeout, at most 2 retries on network error/5xx; Firefox User-Agent. raw/lookup/pass2.py then followed <meta refresh> targets once and made one more attempt with a plain descriptive User-Agent for pages that returned 403/406. Pages: raw/obf/homepages/ (+ _fetch_log.jsonl). Candidates: raw/lookup/extract.py; the choice for each row was made by hand (raw/lookup/decisions.tsv) and every repo_url was checked to occur in the saved page (raw/lookup/assemble.py). GitHub REST calls: 0.
- Rule for choosing: the project's own main code repo (link labeled GitHub/Source/Code/Repository, or the repo named for the project); website-source repos ("Edit this page", *.github.io, *-web, webwml), theme credits, third-party projects and personal profiles are ignored. A link to a GitHub org / GitLab group / forge root -> repo_url = that URL, note "org only". github_slug only when repo_url is one github.com repo.
- Counts: 24 looked up; found repo 10 (6 with github_slug); org only 0; none named 5; not software 0; fetch failed 3; no link to follow 6.
- Judgment calls: 6 retired projects (BioSOAP, BioCORBA, Wikiomics, OpenBQS, BioClipse, DAS/BioDAS) have no link on the roster, so nothing to follow (counted 'no link'). Chado: the GMOD wiki gives a Subversion URL, taken. BioPHP: the page links a Google Code project ('Lee Katz's biophp', one of two code bases it lists); taken, the service is closed. Skam: the SourceForge project the page labels 'Sourceforge CVS' is taken. BioWeka: the roster links a SourceForge project page; its 'Code' tab is taken. GBrowse and BioHaskell link only their website repos -> none. Pise links a PubMed abstract (HTTP 203 interstitial) -> failed.
- Failed hosts: biojs.net (HTTP 521), yandell-lab.org (404), pubmed.ncbi.nlm.nih.gov (203 interstitial). sourceforge.net / *.sourceforge.net answered 403 to the browser UA and 200 on the second attempt.

## Browser lookup, 2026-10-05
BioJS also failed in the author's Firefox ("Invalid URL").
