# netbsd — The NetBSD Foundation — method
- Sources:
  - https://wiki.netbsd.org/github/ (raw/netbsd/wiki.netbsd.org_github.html), fetched 2026-10-05T01:36:06Z. Under "Official repositories on GitHub" it says: "The src, xsrc and pkgsrc repositories, each as a read-only copy, have been available under github.com/NetBSD since 2017-06". It lists https://github.com/NetBSD/{src,xsrc,pkgsrc} and the Fossil copies.
  - https://www.netbsd.org/docs/guide/en/chap-fetch.html, which gives the canonical CVSROOT anoncvs@anoncvs.NetBSD.org:/cvsroot (modules src, xsrc).
  - anonhg.NetBSD.org (Mercurial conversions), saved for reference.
- Rows: one per official repository (src, xsrc, pkgsrc). repo_url = the CVSROOT string; the CVS module is in the note. github_slug = NetBSD/<module>, as the wiki names it.
- Judgment: pkgsrc is included because NetBSD's own wiki lists it among the official repositories.
- Counts: 3 projects, 3 rows, 3 with repo_url, 3 with github_slug. GitHub REST calls: 0.
