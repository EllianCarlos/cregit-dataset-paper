# asf-incubator — ASF Incubator podlings — method
- Source: https://whimsy.apache.org/public/public_podlings.json (ASF Whimsy), fetched 2026-10-05T01:31:01Z. 376 podlings: 24 current, 267 graduated, 85 retired (status_counts in the file). Raw: raw/asf-incubator/. https://incubator.apache.org/podlings.xml returned a 302 to svn; it was not used.
- The podling list gives no repositories. Repos come from https://projects.apache.org/json/foundation/repositories.json (raw/asf/), using these rules, in order:
  1. Keys that match a current PMC or a retired committee by name prefix are excluded, because they go to asf or asf-attic.
  2. Remaining keys are matched to a podling id by longest prefix (key == id or "<id>-*"). This gives one row per repo (323 rows, mostly current podlings).
  3. A graduated podling with no such repo gets one row for repositories.json[<podling id>] if that key exists. The note says the repo is now under the TLP or the Attic (188 rows).
  4. Every other podling gets one row with empty repo_url (169 rows). Most are retired podlings, whose repos are no longer in repositories.json.
- github_slug = apache/<key> for gitbox URLs only. roster_status = whimsy `status` (current / graduated / retired).
- Judgment: assigning a repo to a podling by name prefix is an inference; the note records it.
- Counts: 376 projects, 676 rows, 507 with repo_url, 505 with github_slug. GitHub REST calls: 0.
