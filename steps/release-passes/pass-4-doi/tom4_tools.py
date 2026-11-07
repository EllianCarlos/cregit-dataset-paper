#!/usr/bin/env python3
"""The tools of the DOI pass of TOM 1.0.0 (kit dataset-tom-4: documents only). Subcommands:
  validate    the DOI (DOI_PATTERN) and the release date (an ISO date from DATE_MIN to DATE_MAX).
  keep        the project files of the TOM-3 root: every parquet/ row of its SHA256SUMS, against its MANIFEST.tsv;
              writes keep.resolved.tsv (the kit-2 form, origin tom1 = the input root), keep.pf.tsv, keep.names and
              plan.tsv (kind "unchanged" for every file: tom2_tools.py footers, sums and view read them).
  fill        the documents: [[tom: KEY]] from the TOM-3 values (the date is DATE), TODO-DATE -> DATE, TODO-DOI -> DOI;
              the marker lines must be the expected counts; after the fill no marker word and no placeholder is left.
  view        the check view: the local root and a sparse file with the real footer for each project file.
  count       the TODO-DOI and TODO-DATE lines of a docs folder (S1 writes them into the staged tom4.conf).
  removed     the files of an old docs folder that a new one does not have (S1: the removed documents).
  sample      a seeded sample of project files (for the hash check of the S3 copies).
  check-root  the checks of the new root: SHA256SUMS against TOM-3 (the project rows and KEEP_SAME files unchanged,
              only documents changed, exactly REMOVED_DOCS gone), the footers of the view, the DOI and the date in the documents, no marker.
No output holds the at sign: each log and report line is masked before it is written.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tom_tools as T  # noqa: E402  (the tools of the first pass, staged with their sha256)
import tom2_tools as T2  # noqa: E402  (the tools of the second pass, staged with their sha256)
mask, utc, sha256, read_sums, project_of = T.mask, T.utc, T.sha256, T.read_sums, T.project_of
MARK, DATE_MARK, DOI_MARK, PH = T.MARK, T.DATE_MARK, T.DOI_MARK, T.PH
SCAN_SUFFIXES = {".md", ".cff", ".tsv", ".txt", ".lock", ".py", ".json", ".sh"}


def say(text: str) -> None:
    print(mask(text), flush=True)


def conf_list(text: str) -> list[str]:
    return [x for x in (text or "").split() if x]


def validate(doi: str, date: str, pattern: str, dmin: str, dmax: str) -> list[str]:
    probs = []
    if not re.fullmatch(pattern, doi or ""):
        probs.append(f"the DOI {doi!r} does not match {pattern}")
    try:
        d = datetime.date.fromisoformat(date or "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError
        if not (datetime.date.fromisoformat(dmin) <= d <= datetime.date.fromisoformat(dmax)):
            probs.append(f"the date {date} is not from {dmin} to {dmax}")
    except ValueError:
        probs.append(f"the date {date!r} is not an ISO date YYYY-MM-DD")
    return probs


def cmd_validate(a) -> int:
    probs = validate(a.doi, a.date, a.pattern, a.date_min, a.date_max)
    for x in probs:
        say("PROBLEM: " + x)
    if not probs:
        say(f"validate: DOI {a.doi} matches {a.pattern}; date {a.date}")
    return 1 if probs else 0


# ---------------------------------------------------------------------------------------------------- keep --
def cmd_keep(a) -> int:
    sums = read_sums(a.sums)
    head, rows = T2.tsv_lines(a.manifest)
    ix = {c: i for i, c in enumerate(head)}
    man = {r[ix["path"]]: r for r in rows}
    probs, keep = [], []
    pq_rows = sorted(r for r in sums if r.startswith("parquet/"))
    for rel in pq_rows:
        f = rel[len("parquet/"):]
        if "/" in f or not f.endswith(T.SUFFIX) or not re.fullmatch(r"[A-Za-z0-9._-]+", f):
            probs.append(f"{rel}: not a project file name")
            continue
        m = man.get(rel)
        if m is None or m[ix["sha256"]] != sums[rel] or m[ix["project"]] != project_of(f):
            probs.append(f"{rel}: no MANIFEST.tsv row with its sha256 and project")
            continue
        keep.append((project_of(f), f))
    if sorted(set(man) - set(pq_rows)):
        probs.append("MANIFEST.tsv rows without a SHA256SUMS row")
    if a.expect and len(keep) != a.expect:
        probs.append(f"{len(keep)} project files, expected {a.expect}")
    if len(keep) > a.max:
        probs.append(f"{len(keep)} project files, more than {a.max}")
    for x in probs[:30]:
        say("PROBLEM: " + x)
    if probs:
        return 1
    out = Path(a.out_dir)
    (out / "keep.resolved.tsv").write_text("".join(f"{p}\t{f}\ttom1\n" for p, f in keep))
    (out / "keep.pf.tsv").write_text("".join(f"{p}\t{f}\n" for p, f in keep))
    (out / "keep.names").write_text("".join(f"{p}\n" for p, _ in keep))
    (out / "plan.tsv").write_text("file\tproject\tkind\tvalues\n" + "".join(f"{f}\t{p}\tunchanged\t{{}}\n" for p, f in keep))
    say(f"keep: {len(keep):,} project files (SHA256SUMS = MANIFEST.tsv)")
    return 0


# ---------------------------------------------------------------------------------------------------- fill --
def scan_files(root: Path) -> list[Path]:
    """The files that marks_left of the first pass reads (the suffixes of fill_release.py check), outside parquet/."""
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and rel.parts[0] != "parquet" and (p.suffix in SCAN_SUFFIXES or p.name == "SHA256SUMS"):
            out.append(p)
    return out


def marks_anywhere(root: Path) -> list[str]:
    """Every line with a marker word (TODO-DOI too) or a placeholder."""
    left = list(T.marks_left(root))
    for p in scan_files(root):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if DOI_MARK in line:
                left.append(f"{p.relative_to(root)}:{i}")
    return sorted(set(left))


def cmd_fill(a) -> int:
    probs = validate(a.doi, a.date, a.pattern, a.date_min, a.date_max)
    vals = {k: str(v) for k, v in json.loads(Path(a.values).read_text()).items()}
    vals["date"] = a.date
    root = Path(a.root)
    files = T.text_files(root)
    n_doi = n_date = 0
    unknown, fills, new_text = set(), [], {}
    for p in files:
        rel = str(p.relative_to(root))
        lines = p.read_text(encoding="utf-8").split("\n")
        changed = False
        for i, line in enumerate(lines):
            for k in PH.findall(line):
                if k in vals:
                    fills.append(f"{rel}:{i + 1}: [[tom: {k}]] -> {vals[k]}")
                else:
                    unknown.add(k)
            n_doi += DOI_MARK in line
            n_date += DATE_MARK in line
            new = PH.sub(lambda m: vals.get(m.group(1), m.group(0)), line).replace(DATE_MARK, a.date).replace(DOI_MARK, a.doi)
            if new != line:
                lines[i] = new
                changed = True
        if changed:
            new_text[p] = "\n".join(lines)
    if unknown:
        probs.append(f"unknown placeholder keys: {sorted(unknown)}")
    if n_doi != a.expect_doi_lines or n_date != a.expect_date_lines:
        probs.append(f"{n_doi} lines with {DOI_MARK} and {n_date} lines with {DATE_MARK}; expected "
                     f"{a.expect_doi_lines} and {a.expect_date_lines}")
    if probs:
        for x in probs:
            say("PROBLEM: " + x)
        return 1
    if a.apply:
        for p, t in new_text.items():
            p.write_text(t, encoding="utf-8")
        left = marks_anywhere(root)
        if left:
            say(f"PROBLEM: marker words or placeholders left after the fill: {left[:20]}")
            return 1
    for f in fills:
        print("FILL", mask(f))
    say(f"fill: {n_doi} {DOI_MARK} lines -> {a.doi}; {n_date} {DATE_MARK} lines -> {a.date}; {len(fills)} placeholders; "
        f"{len(new_text)} files {'written' if a.apply else '(dry run)'}; markers left: 0")
    return 0


# -------------------------------------------------------------------------------------------------- sample --
def cmd_sample(a) -> int:
    rows = sorted(r for r in read_sums(a.sums) if r.startswith("parquet/"))
    rng = random.Random(a.seed)
    pick = sorted(rng.sample(rows, min(a.n, len(rows))))
    Path(a.out).write_text("".join(f"{r}\n" for r in pick))
    say(f"sample: {len(pick)} of {len(rows)} project files (seed {a.seed})")
    return 0


# --------------------------------------------------------------------------------------------- count, removed --
def marker_counts(root: Path) -> dict:
    """The lines with TODO-DOI and TODO-DATE in the documents (the files that fill reads), in total and per file."""
    per = {}
    for p in T.text_files(root):
        lines = p.read_text(encoding="utf-8").split("\n")
        per[str(p.relative_to(root))] = (sum(DOI_MARK in x for x in lines), sum(DATE_MARK in x for x in lines))
    return {"doi": sum(v[0] for v in per.values()), "date": sum(v[1] for v in per.values()), "per": per}


def cmd_count(a) -> int:
    c = marker_counts(Path(a.root))
    per = c["per"]
    probs = []
    for f, i, what in (("README.md", 0, DOI_MARK), ("CITATION.cff", 0, DOI_MARK), ("CITATION.cff", 1, DATE_MARK)):
        if per.get(f, (0, 0))[i] < 1:
            probs.append(f"{f} has no {what} line")
    for x in probs:
        say("PROBLEM: " + x)
    print(f"EXPECT_DOI_LINES={c['doi']} EXPECT_DATE_LINES={c['date']}")
    say("count: " + "; ".join(f"{f} {d}/{e}" for f, (d, e) in sorted(per.items()) if d or e) + " (TODO-DOI/TODO-DATE lines)")
    return 1 if probs else 0


def cmd_removed(a) -> int:
    """The files of --old (a docs folder) that --new does not have, one per line."""
    def files(d):
        return {str(p.relative_to(d)) for p in Path(d).rglob("*") if p.is_file()}
    for r in sorted(files(a.old) - files(a.new)):
        print(r)
    return 0


# ---------------------------------------------------------------------------------------------------- view --
def cmd_view(a) -> int:
    """The check view (the form of tom2_tools.py view): hard links of the local root and a sparse file with the real
    TOM-3 footer for each project file. The local root of this pass has no parquet/ folder."""
    import shutil
    root, view, tails = Path(a.root), Path(a.out), Path(a.tails)
    if view.exists():
        shutil.rmtree(view)
    feet = T2.read_footers(tails / "footers.jsonl")
    for rel in T2.local_files(root) + ["SHA256SUMS"]:
        (view / rel).parent.mkdir(parents=True, exist_ok=True)
        os.link(root / rel, view / rel)
    (view / "parquet").mkdir(exist_ok=True)
    n = 0
    for line in Path(a.keep).read_text().splitlines():
        if not line.strip():
            continue
        f = line.split("\t")[1]
        fr = feet[f]
        tail = (tails / (f + ".tail")).read_bytes()
        if hashlib.sha256(tail).hexdigest() != fr["tail_sha256"]:
            say(f"PROBLEM: {f}: the tail is not the fetched one")
            return 1
        with open(view / "parquet" / f, "wb") as o:
            o.truncate(fr["size"])
            o.write(b"PAR1")
            o.seek(fr["size"] - len(tail))
            o.write(tail)
        n += 1
    say(f"view: {len(T2.local_files(view)) + 1} files ({n} sparse files with the TOM-3 footers)")
    return 0


# ---------------------------------------------------------------------------------------------- check-root --
def cmd_check_root(a) -> int:
    root, view = Path(a.root), Path(a.view)
    probs, rep = [], {"utc": utc()}
    keep = [line.split("\t")[1] for line in Path(a.keep).read_text().splitlines() if line.strip()]
    sums, t3 = read_sums(root / "SHA256SUMS"), read_sums(a.tom3_sums)
    local = T2.local_files(root)
    if any(r.startswith("parquet/") for r in local):
        probs.append("the local root holds project files")
    if sorted(sums) != sorted(set(local) | {f"parquet/{f}" for f in keep}):
        probs.append(f"SHA256SUMS has {len(sums)} rows, not the local files and the {len(keep)} project files")
    for f in keep:
        if sums.get(f"parquet/{f}") != t3.get(f"parquet/{f}") or f"parquet/{f}" not in t3:
            probs.append(f"parquet/{f}: the SHA256SUMS row is not the TOM-3 row")
    for r in local:
        if sums.get(r) != sha256(root / r):
            probs.append(f"{r}: the SHA256SUMS row is not the file")
    same = conf_list(a.keep_same)
    protected = [r for r in t3 if any(r == s or (s.endswith("/") and r.startswith(s)) for s in same)]
    for r in protected:
        if sums.get(r) != t3[r] or not (root / r).is_file() or sha256(root / r) != t3[r]:
            probs.append(f"{r}: not the TOM-3 bytes")
    changed = sorted(r for r in sums if sums[r] != t3.get(r) and r != "SHA256SUMS")
    docs = {str(p.relative_to(root)) for p in T.text_files(root)} | {r for r in local if r.startswith("tools/")}
    not_doc = [r for r in changed if r not in docs]
    if not_doc:
        probs.append(f"changed files that are not documents: {not_doc[:5]}")
    gone = sorted(set(t3) - set(sums) - {"SHA256SUMS"})
    removed = sorted(conf_list(a.removed))
    if gone != removed:
        probs.append(f"the TOM-3 files that are gone {gone} are not REMOVED_DOCS {removed}")
    for r in removed:
        if (root / r).exists() or r in sums:
            probs.append(f"{r}: a removed document is in the root or in SHA256SUMS")
    for must in ("README.md", "CITATION.cff"):
        if must not in changed:
            probs.append(f"{must} did not change (it must get the DOI)")
    rep.update({"changed": changed, "gone": gone, "protected_same": len(protected)})
    # footers of the view (sparse files with the real TOM-3 footers)
    feet = T2.view_footers(view, a.jobs)
    if sorted(feet) != sorted(keep):
        probs.append(f"the view has {len(feet)} project files, not {len(keep)}")
    rows = 0
    for f, r in feet.items():
        rows += r["rows"]
        if r["columns"] != a.want_columns:
            probs.append(f"{f}: {r['columns']} columns, not {a.want_columns}")
        if r["kv"].get("ctp_schema_version") != a.schema_version:
            probs.append(f"{f}: ctp_schema_version is {r['kv'].get('ctp_schema_version')}")
    if a.expect_rows and rows != a.expect_rows:
        probs.append(f"rows {rows:,}, expected {a.expect_rows:,}")
    rep["rows"] = rows
    # the DOI and the date in the documents
    cff = (root / "CITATION.cff").read_text()
    if f'doi: "{a.doi}"' not in cff or f'date-released: "{a.date}"' not in cff:
        probs.append("CITATION.cff does not hold the DOI and the release date")
    n = sum(a.doi in line for p in T.text_files(root) for line in p.read_text().splitlines())
    if n < a.expect_doi_lines:
        probs.append(f"{n} document lines hold the DOI, expected at least {a.expect_doi_lines}")
    left = marks_anywhere(root)
    if left:
        probs.append(f"marker words or placeholders left: {left[:10]}")
    rep["doi_lines"] = n
    rep["problems"] = probs[:100]
    rep["n_problems"] = len(probs)
    Path(a.out).write_text(mask(json.dumps(rep, indent=1, sort_keys=True)))
    for x in probs[:40]:
        say("PROBLEM: " + x)
    say(f"check-root: {len(keep):,} project files = TOM-3 rows, {rows:,} rows, {a.want_columns} columns; "
        f"{len(protected)} KEEP_SAME files = TOM-3; changed documents {len(changed)}: {' '.join(changed)}; "
        f"gone {len(gone)}; DOI lines {n}; problems {len(probs)}")
    return 1 if probs else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def dd(s):
        for k in ("doi", "date", "pattern", "date-min", "date-max"):
            s.add_argument(f"--{k}", required=True)
    s = sub.add_parser("validate")
    dd(s)
    s = sub.add_parser("keep")
    for k in ("sums", "manifest", "out-dir"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--expect", type=int, default=0)
    s.add_argument("--max", type=int, default=9999)
    s = sub.add_parser("fill")
    dd(s)
    for k in ("root", "values"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--expect-doi-lines", type=int, required=True)
    s.add_argument("--expect-date-lines", type=int, required=True)
    s.add_argument("--apply", action="store_true")
    s = sub.add_parser("sample")
    for k in ("sums", "seed", "out"):
        s.add_argument(f"--{k}", required=True)
    s.add_argument("--n", type=int, required=True)
    s = sub.add_parser("count")
    s.add_argument("--root", required=True)
    s = sub.add_parser("removed")
    s.add_argument("--old", required=True)
    s.add_argument("--new", required=True)
    s = sub.add_parser("view")
    for k in ("root", "tails", "keep", "out"):
        s.add_argument(f"--{k}", required=True)
    s = sub.add_parser("check-root")
    for k in ("root", "view", "tom3-sums", "keep", "out", "doi", "date", "schema-version"):
        s.add_argument(f"--{k}", required=True)
    for k in ("keep-same", "removed"):
        s.add_argument(f"--{k}", default="")
    for k, d in (("want-columns", 53), ("expect-rows", 0), ("expect-doi-lines", 0), ("jobs", 8)):
        s.add_argument(f"--{k}", type=int, default=d)
    a = ap.parse_args(argv)
    for k, v in list(vars(a).items()):
        setattr(a, k.replace("-", "_"), v)
    return {"validate": cmd_validate, "keep": cmd_keep, "fill": cmd_fill, "sample": cmd_sample, "view": cmd_view, "count": cmd_count, "removed": cmd_removed,
            "check-root": cmd_check_root}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
