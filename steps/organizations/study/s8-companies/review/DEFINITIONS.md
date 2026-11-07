# S8 review: definitions and decision rules (2026-10-17)

These rules apply to every review of the company database: the AI review agents and the user's
review in `review.html`. They make the rules of PROPOSAL.md section 4.1 and DECISIONS.md D2
exact. If a case is not covered here, the decision is `defer` with a note.

## 1. The kind of an organisation

Apply the tests in this order. The first test that is true gives the kind. Test K4b before K4 and
K5 (the user, 2026-10-18): trace the relations of a research institute; with both a government
owner and a university tie it is public-research.

| # | Test | kind | sna_sector |
|---|---|---|---|
| K1 | The value is not an organisation: a placeholder, a machine name, a typo with no clear owner. | (reject the item) | |
| K2 | Anybody can get an address there without an employment or a membership: a webmail, an ISP mailbox, GitHub/GitLab noreply, an alumni forwarding address. | free-provider | |
| K3 | One natural person uses the domain for themselves: a vanity or personal domain, a one-person "studio" or "consulting" brand with no staff and no registered company that you know of. | independent | S.14 |
| K4b | A research institute with BOTH links: a government body owns or funds it, AND a university is tied to it (the university runs it, or the institute is tied to it by statute or by joint staff and teaching). Examples: Instituto Butantan (Sao Paulo state health secretariat + Universidade de Sao Paulo), LBNL (US DOE + University of California). `parent_company_id` = the government body (if it is in the database), `university_id` = the university. Institutes with only one of the two links are K4 or K5. | public-research | S.13 |
| K4 | A government or an intergovernmental body controls it: a ministry, an agency, a national laboratory run by a government (even if a contractor operates it), a public research centre, CERN, ESA, the UN. | government | S.13 |
| K5 | A university, a college, or a research institute that does not sell on the market. A state controls it (a public university, Inria, CNRS): S.13. It is private and non-profit (MIT, Stanford, a private institute): S.15. A for-profit university is K10. | academic | S.13 or S.15 |
| K6 | A non-profit legal entity that hosts open-source projects or holds their assets: a foundation, a trade association that hosts projects (Linux Foundation, a 501(c)(6)), a fiscal sponsor (SFC, SPI). | foundation; fiscal-sponsor for a sponsor of many unrelated projects | S.15 |
| K7 | Another non-profit legal entity: a charity, a society, an association, a standards body that is not a company (W3C is hosted by members; IETF; a user group e.V.). | nonprofit | S.15 |
| K8 | An open-source project or community with no legal entity of its own, or a project domain whose legal owner is not clear (a project mail domain such as `winehq.org`). If a foundation or a company owns the project, use K6/K10 for the owner and record the project as the domain's role. | project | (blank) |
| K9 | A for-profit firm that mainly sells services to clients: consulting, contracting, outsourcing, training. | consultancy | S.11 |
| K10 | Any other market producer whose owners can get a profit: a company of any size, a state-owned enterprise that sells at market prices (Australia Post, a public bank), a start-up, a subsidiary. Banks and insurers: S.12. | company | S.11 or S.12 |

Notes:
- K9 consultancy is a kind of company: it gets `is_company` = true, S.11, and counts as a company
  in the link columns and the enterprise heuristics (`COMPANY_KINDS` = company, consultancy). The
  separate kind lets an analysis count work that a firm does for its clients apart.
- A product or a brand of a company is the company (`ydb.tech` -> Yandex). Put the product
  name in the note, not in `name`. An OPEN project of a company is a project with the company as
  parent (R4).
- A former name is the current organisation (`10gen.com` -> MongoDB); an acquired company with
  its own domain stays a separate company with `parent_company_id` = the buyer, and `status`
  acquired when the brand is gone.
- A university spin-off company is a company (K10), not academic.
- An "Inc", "GmbH", "Ltd", "S.A.", "LLC", "s.r.o." in the legal name supports K10, but a
  foundation can also be a company by law (a "Stiftung" or a "Foundation Inc" is K6).
- A kind from gitdm (CNCF affiliations) is weak: gitdm gives "company" to every employer, also to
  universities and labs. Check it against K4-K7.

## 1b. Umbrella projects and legal entities (the user's review, 2026-10-17)

**R1. A project of an umbrella organisation is not a separate organisation.** An umbrella is an
organisation that hosts many projects: GNU, the Apache Software Foundation, KDE, GNOME, Eclipse,
Mozilla, the Linux Foundation and its sub-foundations, FreeBSD, the Python Software Foundation, and
others of the same kind. When a project belongs to an umbrella (it is a GNU package, an Apache
project, a KDE application), its item is merged into the umbrella: `action` edit, `merge_into` =
the umbrella id. The project name becomes an alias, and the project's mail domains go to the
umbrella. Examples from the user: GCC (gcc.gnu.org) -> GNU; OpenOffice.org -> the Apache Software
Foundation (Apache OpenOffice). A former owner (Sun, Oracle for OpenOffice.org) goes in the note.
A project that only uses an umbrella service (a mailing list, a fiscal sponsor such as SPI or SFC
for many unrelated projects) is not merged: a fiscal sponsor is not an umbrella under R1.
For the namespace column, R1 does not apply to the Linux Foundation and its foundations: their
project accounts are project rows (rule N1 in section 4; the user, 2026-10-19).

**R2. A community and its legal entity are one organisation.** When a legal entity exists to serve
one community (KDE e.V. for KDE, the GNOME Foundation for GNOME), the organisation has the name of
the community (`name` = KDE) and the legal name of the entity (`legal_name` = KDE e.V.; write it in
`note` because the decision has no legal_name column). The kind follows the entity: a registered
non-profit that holds the community's assets is a foundation (K6). The user's words: "KDE e.V. is
just a branch of KDE focused on legal".

**R4. A project of a company stays a project, tied to the company by its parent (the user,
2026-10-17).** When a company owns or leads an open project (OpenJDK -> Oracle, TensorFlow and Go
-> Google, WebKit -> Apple, Fedora -> Red Hat), the project is NOT merged into the company:
`kind` = project, `parent_company_id` = the company id. Reason: people of many employers use the
project's mail domain (openjdk.org, fedoraproject.org), so a merge would make all of them
authors of the owner company. For a project, `parent_company_id` means "the main interested entity of
the project" (see the principle below). No employer column is added (the user's decision). R1 (a project of an
umbrella foundation merges into the foundation) does not change. A domain that a company gives
only to its own staff (quicinc.com) is the company, not a project.
R4 also applies when a university, a research institute or a government body owns or leads the
project (the user, 2026-10-17): ViennaRNA -> University of Vienna, JASP -> University of
Amsterdam. The project is not merged into the academic organisation; `parent_company_id` = the
academic organisation id. The column name stays; its meaning is "the main interested entity".

**Principle: open projects have no owners (the user, 2026-10-18).** All projects of the dataset
are open source and licensed, so no organisation owns them. A project has authors, maintainers
and interested entities. For a project, `parent_company_id` = its MAIN interested entity: the
organisation that maintains, sponsors or mainly develops it (Chromium -> Google, OpenJDK ->
Oracle, ViennaRNA -> University of Vienna). One parent at most; name other interested entities in
the note. Do not write "owns" or "owner" for a project in notes or docs; write "maintains",
"sponsors", "mainly develops" or "main interested entity".
User decision (2026-10-18): Chromium (chromium.org) is a project with Google as parent.

Decisions that the user gives in a chat, not in `review.html`, are in
`decisions.chat.csv` (the same columns, `decided_by` = user). The build reads both files. When both
files have a row for the same item, the row with the later `decided_utc` wins (the user, 2026-10-18:
a chat answer of the final audit can change an earlier decision of `review.html`). The chat rows stay
in their own file because the tool overwrites `decisions.csv` on each save.

**R3. An obvious case needs no card.** An organisation that is already `accepted`, where the AI
also says accept, is not shown as a card at any confidence (for example Qualcomm).

## 2. When an organisation is `accepted`

Accept when all of these hold:
1. The organisation exists (or existed) and the name is its usual name.
2. The kind follows section 1.
3. At least one domain or namespace link is right: the organisation owns that domain (the
   e-mail addresses there are its staff or members), or owns the namespace.
4. No person name is the organisation name, except an organisation named after a person
   (Max Planck Society, Hasso Plattner Institute, Rohde & Schwarz).

Reject when the item is not an organisation (K1), or is a duplicate (then give the kept id in
`merge_into`).

Edit (accept with changes) when the organisation is real but the kind, the name, the parent or
the sector is wrong.

Defer when you are not sure. A defer is better than a guess.

## 3. Domain links

- A domain belongs to an organisation when the organisation controls the mail domain. A
  developer affiliation (one person at `berkeley.edu` who worked for Microsoft) is not a domain
  link: reject that domain row, keep the organisation.
- A personal or vanity domain of one person belongs to `independent` (K3), also when gitdm or
  another list names the person's employer (the user, final audit, 2026-10-18). A person's work
  counts for an employer only when the person commits with an address of the employer's domain.
  This holds for every organisation, also for a domain with no dataset tokens.
- This is a design decision, not an error (the user, 2026-10-19). The author chooses the address
  for each commit. An employee who commits with a free or personal address acts as an outside
  participant; the same person on work time commits with the employer's address. So
  `firm_based_on_domain` gives the organisation of the address that the author chose, not the
  employer. The error budget (`ERROR_MODEL.md`) measures only the errors of that mapping. The
  employer is a side study (`side/EMPLOYER_MODEL.md`), not part of the dataset.
- A domain with no row in the database maps to `independent` (the user, 2026-10-19). The error
  budget gives a term for the organisations among these domains.
- A token with no real domain (blank, no dot, a git-svn id) gets `unknown` (the user, 2026-10-19).
- A domain of another firm or of a mail provider is not the employer's domain: move it to its own
  organisation, to `free-provider`, or drop it (kiwi.com is the travel firm Kiwi.com, not Google).
- Partner addresses under a company domain (`cirrus.corp-partner.google.com`) stay with the owner
  of the domain. This is a known limit: the address belongs to the staff of a partner firm.
- An academic or government domain never belongs to a company.
- Alumni domains are `free-provider` (K2; the user, v4.9 audit page, 2026-10-25): a forwarding
  domain of a university for its former students (first label `alum`, `alumni`, `alumnus`,
  `alumnae`, `anciens`; also `cantab.net`, `m4x.org`, `normalesup.org`) maps to `free-provider`,
  also when it is a subdomain of a university domain (the suffix rule must not give it to the
  university). Student domains stay with the university. The release documents say this in
  ORGANISATIONS.md, section 2.2.
- A subdomain of a company domain is the company (`linux.intel.com` -> Intel), unless the
  subdomain is a separate organisation (`research.example.edu` of a lab is still the university).

## 4. Namespace links

**Rule N1.** `firm_based_on_namespace` names the organisation that controls the account; a
hosting foundation is the `hosted_by` relation (the user, 2026-10-19). A fiscal sponsor is the
`sponsored_by` relation (the user, 2026-10-20).

- `owns`: the organisation controls the account (the GitHub organisation, the GitLab group or the
  user account of the namespace). Evidence: the account page (name, website, the verified mark of
  GitHub, description), a company page that names the account, the forge that the organisation
  runs. A roster line alone is not evidence of control: a foundation roster lists the projects
  that the foundation hosts, also in accounts of companies (the roster of the OpenJS Foundation
  lists Jest in the account `facebook`, which Meta controls).
- `hosted_by` (since v4.3): a foundation hosts a project of the namespace (its roster lists the
  project), but it does not control the account. Examples: the Linux Foundation and its
  foundations (CNCF, OpenJS Foundation and the others), Apache, Eclipse, OSGeo for its OSGeo
  projects (rule N2). The relation never gives `firm_based_on_namespace`. It keeps the foundation
  reachable from the reference tables (table `organisation_namespaces`, view `project_hosts`).
- `sponsored_by` (since v4.5, the user, 2026-10-20): a fiscal sponsor sponsors a project of the
  namespace. A fiscal sponsor is an organisation of kind `fiscal-sponsor` (K6): NumFOCUS, Software
  Freedom Conservancy, Software in the Public Interest. The sponsor's own list must name the
  project as sponsored (for NumFOCUS, https://numfocus.org/sponsored-projects; a NumFOCUS
  "affiliated project" has no relation). A fiscal sponsor is never `owns` and never `hosted_by`.
  The relation never gives `firm_based_on_namespace`; the view `project_sponsors` shows it. From
  v4.4 to v4.5, all 100 `hosted_by` rows of the three fiscal sponsors became `sponsored_by`.
- `participates`: the organisation's staff take part, but another body owns the namespace.
- `candidate`: a weak signal (a name match, a website on a company domain). A reviewer can
  upgrade it to `owns` when the org page or the repository says so.

Who controls an account (the classes of `manual/v43_namespaces.csv`; apply the first test that is
true):

| Class | Test | `owns` row | Roster foundation |
|---|---|---|---|
| foundation | The foundation's own account: its name is the foundation's name, its website is a domain of the foundation, or it is a group on a forge that the foundation runs (gitlab.eclipse.org, invent.kde.org, gitlab.gnome.org, git.savannah.gnu.org, git.osgeo.org). A project account of an R1 umbrella (Eclipse, Apache, GNU, KDE, GNOME, Mozilla, FreeBSD, NetBSD, PSF, The Document Foundation) is the umbrella (R1). For Eclipse, the Eclipse Foundation Project Handbook says: "Official project repositories must be hosted under an Eclipse Foundation-managed organisation at GitHub". | the foundation | `hosted_by`, if it is another foundation |
| company, organisation | The website of the account is a domain of a company (or of a university, a government body or another organisation) of the database, or the account name is the name of a company (a name match only; the audit page shows it). | that organisation | `hosted_by` |
| project | A project account: the project controls it. For namespaces, R1 does not apply to the Linux Foundation and its foundations (CNCF, LF AI & Data, LF Edge, LF Networking, OpenSSF, OpenJS Foundation): the user, 2026-10-19, `dexidp` is the account of the Dex project. | a project row (kind project; an existing row, else a new row) with the hosting foundation as parent (R4) | `hosted_by` |
| person | A user account of one person. | none (no value) | `hosted_by` |
| unclear | Not clear (the account does not exist now, two rules disagree, an earlier merge stops a project row). | the v4.2 row stays; a conflict row `v43-namespace-review` asks the user | unchanged |

**Rule N2 (OSGeo, the user, 2026-10-21).** OSGeo hosts every project in its directory
(https://www.osgeo.org/projects/). That means the OSGeo projects (projectType osgeo), the projects
in incubation, the OSGeo Community projects (projectType community), the heritage projects and the
projects that the directory only lists (projectType none). Each namespace of such a project has a
`hosted_by` row of OSGeo. `hosted_by` never gives `firm_based_on_namespace` (rule N1): the project
or the firm that controls the account keeps its `owns` row. The parent of a project row stays its
main interested entity (R4), not OSGeo: MobilityDB has the Universite libre de Bruxelles, and
mapfish has Camptocamp. This rule replaces the rule of 2026-10-20, which hosted only the OSGeo
projects and the incubating projects. v4.5 removed 48 `hosted_by` rows of OSGeo (21 community
projects, 27 listed projects). v4.6 adds all 48 back with their v4.4 fields
(`manual/v46_namespaces.csv` and the private file of the workspace). The LocationTech row
(`participates`) does not change.

**Rule N3 (an organisation that we know only from its account, the user, 2026-10-25).** Some
organisation accounts (a GitHub organisation, a group on another forge) show no legal entity: no
fetched page names a company, a foundation, a university or another body behind the account. Such
an account keeps an organisation row of kind `project` (K8: no legal entity of its own) that `owns`
the account, so `firm_based_on_namespace` names it. But a mail domain of such a row maps to
`independent` in `firm_based_on_domain`: an address of the domain does not show an employer. The
manual layer gives each such domain to `independent` (a domain row, as for a personal domain); the
row itself has no domain row. If the evidence names a legal entity that can control the account, do
not use this rule: the item goes to the user. The rule started with the accounts of the 5,000+ layer
that the user left unsure on purpose on the v4.8 audit page (layer v4.9). The user then applied it to
the project rows of round 10 that we know only from the account and that had domain links (43 rows;
9 rows whose evidence names a legal entity keep their domains). Firm rows are not in the rule.

A project account with no dataset project gets no new row in v4.3: its roster rows become
`hosted_by`, and the namespace has no `owns` row. A namespace that is a person's account is not
named in git: its rows are in the private file `review/v43_namespaces.private.csv` of the workspace.

## 5. Conflicts

| Conflict type | Decision |
|---|---|
| kind-differs | Choose the kind by section 1. |
| proposal-low-certainty | Accept the proposal (with edits) only when you can name the organisation with certainty; else reject (the domain stays unmatched). |
| withheld-person-like-name | Allow the name when it is an organisation name (a brand such as Thomson Reuters); else reject. |
| proposal-differs-from-map | Choose the right organisation for the domain. |
| wikidata-several-items | Choose the QID of the organisation (not a subsidiary, not a dissolved item, unless the organisation is dissolved). |
| namespace-two-owners | Choose the owner; the other gets `participates`, or no row. |
| possible-duplicate | Merge (give the kept id) or keep both. |
| others | Choose by the rules above, or defer. |

## 6. Decision values (the columns of decisions.csv)

`item_id, type, key, action, kind, name, parent_company_id, merge_into, sna_sector, qid, note,
decided_by, decided_utc`

- `action`: accept, edit, reject, defer.
- An empty cell means "no change". To set a value to blank, write `(blank)` (for example the
  sector of a project).
- `parent_company_id` and `merge_into` take ids of the database. In `review.html` you can type a
  name or an alias: the form changes it to the id when exactly one organisation has that name.
  Else the typed text stays, and the progress line counts it ("typed names wait for an id").
  Claude resolves these names before the build. The build checks every id and turns an unknown
  id into a conflict row; it never adds an organisation from a decision.
- `decided_by`: `user`, or `claude-review-v1` for an AI suggestion; an AI suggestion that the user
  accepts in the tool gets `user (ai)`.
- An AI suggestion is never a decision until the user accepts it. The build reads only rows with
  `decided_by` = `user` or `user (ai)`.
