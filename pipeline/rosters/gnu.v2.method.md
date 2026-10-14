# gnu v2 (FSF / GNU): fetched 2026-10-10 00:32 to 03:20 UTC

`gnu.v2.csv` is a new version of `gnu.csv`. `gnu.csv` does not change. The
first fetch (`gnu.method.md`) got repositories for only 22 of the 388 packages,
because gnu.org and Savannah stopped answering this machine. This version
fetches the published pages again (user decision, 2026-10-10).

## Sources, in the order of the links

All pages are kept with their URL, HTTP status, final URL, sha256 and fetch
time in `raw/gnu-v2/fetch.tsv` and `raw/gnu-v2/pages/` (exact bytes, `* -text`).
`raw/gnu-v2/fetch_gnu_v2.py` fetches them, one request at a time, 8 s apart.
No URL is built from a name: each URL is a link on a page fetched before.

1. https://www.gnu.org/software/allgnupkgs.html: the GNU package list, 388
   packages (the same 388 as in `gnu.csv`). Fetched at 02:44 UTC. gnu.org did
   not answer one test at about 00:20 UTC.
2. The Savannah list of GNU groups (type 1), the URL that the first fetch
   kept: 391 group page links.
3. Each group page `https://savannah.gnu.org/projects/<group>`: its
   "Homepage" tab, its "Browse Git repository" link and its git page link.
4. Each git page `/git/?group=<group>`: the anonymous clone URL.
5. The package page `https://www.gnu.org/software/<pkg>/` of each package
   that no group with a git page names as its home page.
6. A `git.html` page that a package page links on its own gnu.org site
   (gcc and mpfr; the mpfr one redirects to www.mpfr.org).
7. The project website that the GNU page gives (user decision, 2026-10-10
   03:35 UTC: follow GNU's link): the redirect target, or a link on the page
   whose host or first path part has the package name
   (`raw/gnu-v2/site_links.tsv`, from `raw/_bin/site_links_gnu_v2.py`; 68
   links for 49 packages).
8. At most 3 pages of that site, on the same host, whose path names git,
   source, development, repository, download or code. A failed answer from a
   project website is only recorded; it is not a block of this machine.

Blocks: Savannah web pages did not answer once (01:39 UTC, the git page of
libmatheval). The script waited 30 minutes, as the block rule says, and then
went on (02:10 UTC). No other proxy or address was used.

## Rule: the repository of a package

`raw/_bin/parse_gnu_v2.py`, in this order:

1. The package has a `repo_url` in `gnu.csv`: kept (22 rows, in the pool;
   `s2-pool/v2/url_map.tsv` gives their clone URLs).
2. A group whose "Homepage" is `https://www.gnu.org/software/<pkg>/` and that
   has a git page: the clone URL on the git page whose repository has the name
   of the "Browse Git repository" link, else the name of the group.
3. Else the package page (step 5, or the 2026-10-05/06 copy in `raw/gnu/`
   when there is no new copy): a Savannah group link, or a repository that the
   page publishes. A repository counts only if its name is the package name,
   or `apps-<name>` (GNUstep), or, for a clone URL on the project's own host,
   has the package name as one "-" part (`binutils-gdb` for binutils). A
   page can also link other projects (curl/curl on the libidn2 page).
4. A group with no git page (CVS, SVN, Hg or Bzr only): the package page and
   its git.html page can still name a git repository on another host (gcc:
   `https://gcc.gnu.org/git/gcc.git`).
5. A package that still has no git repository: the clone URL that its project
   website publishes (steps 7-8). It counts if its repository name is the
   package name, or, for a clone URL (a `git clone` line, git://, `.git`), has
   the package name inside (glibc for libc); a forge project link must have the
   exact name. The chain GNU page -> site page -> clone URL is in `v2_source`.
6. Else the true reason (column `v2_status`).

## Clone protocol

Since 2026-10-09 22:58 UTC, `git.savannah.gnu.org` does not accept connections
from this machine on ports 443 and 80. Port 9418 (git://) works. The Savannah
guide https://savannah.gnu.org/maintenance/UsingGit/ (kept in
`s2-pool/v2/pages/`, fetched 2026-10-10 02:55 UTC) publishes the anonymous form
`git clone git://git.savannah.gnu.org/<group>.git`. So `clone_url_git` is the
git:// form of the same path as `clone_url`, and S3 v2 clones over git://. The
repository content is the same over both protocols. `clone_url` (https) stays
the recorded URL.

## Counts (388 packages)

| v2_status | Packages |
| --- | ---: |
| git (a Savannah clone URL) | 176 |
| git (another host, named on a GNU or Savannah page; 5 on GitHub) | 24 |
| git (the project website names the clone URL: glibc, mailman, mpfr, poke, texmacs) | 5 |
| in the pool (`gnu.csv`) | 22 |
| no git repository on Savannah (CVS, SVN, Hg or Bzr), and no page names one (17 of them: the project website names no git clone URL) | 94 |
| the package page redirects off gnu.org, and no page names a git repository (25 of them: the website was read) | 29 |
| the package page names no repository (2 of them: the website was read) | 30 |
| the package page links only repositories of other projects | 4 |
| no source (no group names the home page; no package page) | 3 |
| the hurd git page gives 11 URLs, none only named hurd | 1 |

`s2-pool/v2/build_pool_supplement.py` turns these rows into new pool rows
(`s2-pool/v2/pool.supplement.csv`, 199 rows). It leaves out 6 that are
already in the pool (less, mc, texmacs, xaos, and libidn2 and icecat, which
share a repository with another row).

## Open

- Packages whose website names no git clone URL on the pages read (gmp and
  octave use Mercurial; gnupg, ncurses, R and others publish no clone URL on
  the pages that the rule reads).
- hurd: the main repository is ambiguous (`hurd.git` and `hurd/hurd.git`).
