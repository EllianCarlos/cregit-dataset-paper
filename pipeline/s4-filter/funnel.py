#!/usr/bin/env python3
"""S4 funnel: apply the filters in order and count the rows after each one.

Inputs: ../s2-pool/pool.csv and the S3 files in ../s3-measure/ (trees.jsonl,
clones.jsonl, commits.jsonl, clone_facts.jsonl, languages_recheck.jsonl).
Each pool row gets the FIRST filter that removes it (excluded_because); a row
that passes every filter is in the frame. The frame is then split into the run
layers by commit count (DP7), largest first.

The filters, in order (decided 2026-10-05 and 2026-10-06):
  GitHub rows: a default branch commit; not archived, not a fork, not a mirror
  (DP6); last push on or after 2025-04-03 (DP5); Linguist lists C, C++, Java or
  Rust. All rows: measured at the pinned commit (S3); tokenizable bytes that
  are not vendored >= 5% of code bytes (DP3); a license file (DP8L).
Other-host rows have no GitHub flags; they pass the GitHub-only steps.

While S3 runs, rows that are not measured yet leave at their step with the
reason "not measured yet", and the funnel is provisional.

Output (with --suffix S: funnelS.md, frame_statusS.csv, frameS.csv, so that
the published files do not change): funnel.md (the tables), frame_status.csv (pool_key, name_with_owner,
host, excluded_because, layer), and frame.csv: one row for each project of the
frame, in the input contract of build_manifest.py (cregit-token-pipeline,
docs/E2E.md), in run order: layer largest first, then u. size_class follows
select_corpus.py: S < 30,000 commits, M up to 150,000, L above. labels is
"pending" until S6. Snapshot date 2026-10-05.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
S3 = HERE.parent / "s3-measure"
sys.path.insert(0, str(S3))
from prog_exts import programming_extensions  # noqa: E402
import dp8l_rule  # noqa: E402  the DP8L rule of 2026-10-10 (dp8l_rule.py, next to this file)

TARGET = {"C", "C++", "Java", "Rust"}
PUSHED_MIN = "2025-04-03"  # 550 days before the snapshot date 2026-10-05
SHARE_MIN = 0.05
PROG = programming_extensions()
LAYERS = [(5000, "≥ 5,000"), (1000, "1,000–4,999"), (500, "500–999"), (100, "100–499"), (0, "< 100")]
PENDING = "not measured yet"
V2_POOL = HERE.parent / "s2-pool/v2"
V2_DOC = """--v2 inputs (decided 2026-10-09 23:50 UTC, ../clone-failures-20261009):
  ../s3-measure/v2/clones.jsonl, clone_facts.jsonl, trees.jsonl, commits.jsonl
                              rows measured again or new, with the S3 code (the last row wins)
  ../s2-pool/v2/url_map.tsv   pool_key -> the clone URL that the host publishes (Savannah)
  ../s2-pool/v2/reasons.tsv   pool_key -> the classified exclusion reason
  ../s2-pool/v2/pool.supplement.csv  new pool rows (the GNU roster v2), columns of pool.csv"""
NEAR_MISS = {  # DP8L v4 (user, 2026-10-11 ~19:00 UTC): these audit classes (dp8l-audit, C, D, E) pass too
    "no license file (near miss: license file only in a subfolder)",  # E
    "no license file (near miss: a package file declares a license)",  # D
    "no license file (near miss: other root name)",  # C
}
SALT = "20261110:"  # the permanent random numbers (D21); u_of() in build_manifest.py


def u_of(slug):
    return (int.from_bytes(hashlib.sha256((SALT + slug).encode()).digest()[:8], "big") >> 11) / 2**53


def size_class(commits):
    return "S" if commits < 30000 else ("M" if commits <= 150000 else "L")


def slug_url(r, m):
    """(slug, clone URL). GitHub: the resolved name. Other hosts: the URL path."""
    if r["host"] == "github.com":
        return r["name_with_owner"], f"https://github.com/{r['name_with_owner']}.git"
    path = r["repo_url"].split("://", 1)[1].split("/", 1)[1].strip("/")
    return path.removesuffix(".git"), r["repo_url"]


def hours(tok):
    """cregit wall time model from resources.tsv: 63 s for each tokenizable MB, 30 s minimum."""
    return max(30, 63 * tok / 1e6) / 3600


def load_jsonl(path, key):
    out = {}
    if path.exists():
        for l in path.open():
            d = json.loads(l)
            out[d[key]] = d  # the last row wins: a re-measure replaces an earlier failure
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suffix", default="", help='write funnel<S>.md, frame_status<S>.csv, frame<S>.csv '
                    '(for example ".v2"); the default writes the published files')
    ap.add_argument("--v2", action="store_true", help="also read the v2 inputs (see V2_DOC); implies --suffix .v2 "
                    "and writes supplement.v2.csv")
    ap.add_argument("--dp8l", action="store_true", help="DP8L of 2026-10-10: the root rule for all hosts "
                    "(dp8l_rule.py; GitHub rows from dp8l-audit/roots.csv), or, for GitHub rows, a license that "
                    "GitHub detects (pool license not empty); implies --v2 and --suffix .v3, "
                    "and writes supplement.v3.csv")
    ap.add_argument("--near-miss", action="store_true", help="DP8L v4 of 2026-10-11: --dp8l, and a GitHub row of "
                    "the near-miss classes of dp8l-audit (C other root name, D package file, E license file in a "
                    "subfolder; NEAR_MISS) also passes; implies --dp8l and --suffix .v4, and writes supplement.v4.csv")
    args = ap.parse_args()
    args.dp8l = args.dp8l or args.near_miss
    args.v2 = args.v2 or args.dp8l
    sfx = args.suffix or (".v4" if args.near_miss else ".v3" if args.dp8l else ".v2" if args.v2 else "")
    roots = ({r["pool_key"]: r for r in csv.DictReader(open(HERE / "dp8l-audit/roots.csv", encoding="utf-8"))}
             if args.dp8l else None)
    if roots is not None and (S3 / "v2/roots.csv").exists():  # the root trees of the new GitHub rows (v2)
        roots.update({r["pool_key"]: r for r in csv.DictReader(open(S3 / "v2/roots.csv", encoding="utf-8"))})
    trees = load_jsonl(S3 / "trees.jsonl", "name_with_owner")
    clones = load_jsonl(S3 / "clones.jsonl", "pool_key")
    commits = load_jsonl(S3 / "commits.jsonl", "name_with_owner")
    cfacts = load_jsonl(S3 / "clone_facts.jsonl", "pool_key")
    url_map, why_v2 = {}, {}
    if args.v2:
        clones.update(load_jsonl(S3 / "v2/clones.jsonl", "pool_key"))
        cfacts.update(load_jsonl(S3 / "v2/clone_facts.jsonl", "pool_key"))
        trees.update(load_jsonl(S3 / "v2/trees.jsonl", "name_with_owner"))
        commits.update(load_jsonl(S3 / "v2/commits.jsonl", "name_with_owner"))
        url_map = {r["pool_key"]: r["clone_url"] for r in csv.DictReader(open(V2_POOL / "url_map.tsv"), delimiter="\t")}
        why_v2 = {r["pool_key"]: r["reason"] for r in csv.DictReader(open(V2_POOL / "reasons.tsv"), delimiter="\t")}
    recheck = S3 / "languages_recheck.jsonl"
    extra = {d["name_with_owner"] for d in map(json.loads, recheck.open()) if d["target_bytes"]} if recheck.exists() else set()

    steps = ["pool", "a GitHub row has a default branch commit", "not archived (DP6)", "not a GitHub fork (DP6)",
             "not a mirror (DP6)", "pushed on or after 2025-04-03 (DP5)", "Linguist lists C, C++, Java or Rust",
             "measured at the pinned commit (S3)", "non-vendored tokenizable ≥ 5% of code bytes (DP3)",
             "has a license file (DP8L)" if not args.near_miss
             else "has a license file, or a near miss C, D or E (DP8L v4)"]
    after = Counter()
    reasons = Counter()
    frame, status = [], []
    pool_rows = list(csv.DictReader(open(HERE.parent / "s2-pool/pool.csv", encoding="utf-8")))
    sup_pool = V2_POOL / "pool.supplement.csv"
    if args.v2 and sup_pool.exists():  # new pool rows (v2), with the same columns
        pool_rows += list(csv.DictReader(open(sup_pool, encoding="utf-8")))
    for r in pool_rows:
        gh, nwo, key = r["host"] == "github.com", r["name_with_owner"], r["pool_key"]
        if key in url_map:
            r["repo_url"] = url_map[key]  # the clone URL that the host publishes (v2)
            r["host"] = r["repo_url"].split("://", 1)[1].split("/", 1)[0]  # and its host (a page row had savannah.gnu.org)
        m = n_commits = has_license = None
        lic_reason = ""  # with --dp8l: why a row has no license file (the near-miss reason of the audit)
        fail = None  # (step index that removes the row, reason)
        if gh:
            langs = set(json.loads(r["languages"] or "{}"))
            checks = [(not r["head_oid"], "no default branch commit"), (r["archived"] == "True", "archived"),
                      (r["fork"] == "True", "fork"), (r["mirror"] == "True", "mirror"),
                      ((r["pushed_at"] or "") < PUSHED_MIN, "last push before 2025-04-03"),
                      (not (TARGET & langs or nwo in extra), "no C, C++, Java or Rust in Linguist")]
            for i, (bad, why) in enumerate(checks, 1):
                if bad:
                    fail = (i, why)
                    break
            if not fail:
                t, c = trees.get(nwo), clones.get(key)
                if t and t.get("truncated"):
                    m = c if c and c["status"] == "ok" else None
                    if not m:
                        fail = (7, PENDING if not c else f"truncated tree, clone: {c['status']}")
                elif t and t.get("status") == 200:
                    m = t
                else:
                    fail = (7, PENDING if not t else f"tree call failed (HTTP {t.get('status')})")
                n_commits = (commits.get(nwo) or {}).get("commits")
                has_license = r["license"] != ""
                if roots is not None and not has_license:  # --dp8l: GitHub detects none; the root tree decides
                    root = roots.get(key)
                    has_license = None if root is None else root["has_license"] == "True"
                    lic_reason = root["reason"] if root else ""
                    if args.near_miss and lic_reason in NEAR_MISS:
                        has_license = True
        else:
            c = clones.get(key)
            if not c:
                fail = (7, PENDING)
            elif c["status"] != "ok":
                fail = (7, f"clone: {c['status']}")
            else:
                m = c
                f = cfacts.get(key)
                if f and f["status"] == "ok":
                    n_commits, has_license = f["commits"], bool(f["license_files"])
                    if roots is not None:  # --dp8l: the same names as for GitHub rows
                        has_license = any(dp8l_rule.is_license_name(x) for x in f["license_files"])
                elif f:
                    fail = (9, f"clone facts: {f['status']}")
        if not fail:
            code = sum(v for k, v in m["by_ext"].items() if k in PROG)
            own = m["tok_bytes"] - m.get("tok_vendor_bytes", 0)
            if not code or own < SHARE_MIN * code:
                fail = (8, "non-vendored tokenizable < 5% of code bytes")
            elif has_license is None:
                fail = (9, PENDING + " (license file)")
            elif not has_license:
                fail = (9, lic_reason or "no license file")
        if fail and key in why_v2:
            fail = (fail[0], why_v2[key])  # the classified reason (v2); the step does not change
        stop = fail[0] if fail else len(steps)
        for s in steps[:stop]:
            after[s] += 1
        layer = ""
        if not fail:
            layer = next(name for lo, name in LAYERS if (n_commits or 0) >= lo) if n_commits is not None else "unknown"
            slug, url = slug_url(r, m)
            frame.append({"tok": m["tok_bytes"], "layer": layer, "slug": slug, "host": r["host"], "repo_url": url,
                          "head_oid": r["head_oid"] if gh else m["head_oid"], "u": u_of(slug),
                          "size_class": size_class(n_commits), "labels": "pending", "commits": n_commits,
                          "language": r["primary_language"], "tok_bytes": m["tok_bytes"],
                          "tok_vendor_bytes": m.get("tok_vendor_bytes", 0), "pushed_at": r["pushed_at"],
                          "stars": r["stars"], "pool_key": key})
        else:
            # One line for all "duplicate of X" rows in funnel.md; frame_status keeps the name.
            reasons["duplicate of a GitHub row of the same project" if fail[1].startswith("duplicate of ")
                    else fail[1]] += 1
        status.append([key, nwo, r["host"], fail[1] if fail else "", layer]
                      + ([fail[0] if fail else ""] if sfx else []))

    pending = sum(v for k, v in reasons.items() if k.startswith(PENDING))
    lines = ["# S4 funnel" + (" (provisional while S3 runs)" if pending else ""), "",
             f"Computed {dt.datetime.now(dt.timezone.utc).isoformat(timespec='minutes')}. "
             f"{pending:,} rows are not measured yet; each one leaves at the step that needs its measurement.", "",
             "| Step | Rows after the step | Removed by the step |", "| --- | ---: | ---: |"]
    prev = None
    for s in steps:
        lines.append(f"| {s} | {after[s]:,} | {'' if prev is None else f'{prev - after[s]:,}'} |")
        prev = after[s]
    lines += ["", f"Frame: **{len(frame):,} projects**, {sum(f['tok'] for f in frame)/1e9:,.1f} GB of tokenizable code, "
              f"about {sum(hours(f['tok']) for f in frame):,.0f} serial pipeline hours (63 s for each tokenizable MB).", "",
              "## Run layers (DP7), largest first", "", "| Layer (commits) | Projects | Serial hours | Cumulative hours |",
              "| --- | ---: | ---: | ---: |"]
    cum = 0
    for _, name in LAYERS + [(None, "unknown")]:
        fs = [f for f in frame if f["layer"] == name]
        if not fs:
            continue
        h = sum(hours(f["tok"]) for f in fs)
        cum += h
        lines.append(f"| {name} | {len(fs):,} | {h:,.0f} | {cum:,.0f} |")
    lines += ["", "## Reasons for removal", "", "| Reason | Rows |", "| --- | ---: |"]
    lines += [f"| {k} | {v:,} |" for k, v in reasons.most_common()]
    (HERE / f"funnel{sfx}.md").write_text("\n".join(lines) + "\n")
    with (HERE / f"frame_status{sfx}.csv").open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        # With a suffix (v2, v3): also "step", the index in `steps` of the step that
        # removed the row (1 = default branch commit ... 9 = license file); empty in the frame.
        w.writerow(["pool_key", "name_with_owner", "host", "excluded_because", "layer"] + (["step"] if sfx else []))
        w.writerows(status)
    rank = {name: i for i, (_, name) in enumerate(LAYERS)}
    frame.sort(key=lambda f: (rank[f["layer"]], f["u"], f["slug"]))
    cols = ["slug", "host", "repo_url", "head_oid", "u", "size_class", "labels", "layer", "commits", "language",
            "tok_bytes", "tok_vendor_bytes", "pushed_at", "stars", "pool_key"]
    with (HERE / f"frame{sfx}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows({**r, "u": repr(r["u"])} for r in frame)
    if args.v2:
        write_supplement(frame, cols, sfx if args.dp8l else ".v2")  # .v3, or .v4 with --near-miss
    print("\n".join(lines))


def write_supplement(frame, cols, sfx=".v2"):
    """supplement<sfx>.csv (.v2, .v3 with --dp8l, .v4 with --near-miss): the frame rows that are not in the published frame.csv,
    in run order (layer largest first, then u). It becomes its own batch."""
    old = {r["pool_key"] for r in csv.DictReader(open(HERE / "frame.csv", encoding="utf-8"))}
    new = {r["pool_key"] for r in frame}
    gone = old - new
    if gone:
        print(f"WARNING: {len(gone)} rows of frame.csv are not in the v2 frame: {sorted(gone)[:10]}")
    sup = [r for r in frame if r["pool_key"] not in old]
    with (HERE / f"supplement{sfx}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows({**r, "u": repr(r["u"])} for r in sup)
    print(f"supplement{sfx}.csv: {len(sup)} rows; {len(gone)} rows of frame.csv left")


if __name__ == "__main__":
    main()
