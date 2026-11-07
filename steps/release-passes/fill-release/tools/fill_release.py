#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Ellian Carlos Costa, Arthur Pilone Maia da Silva, David Tadokoro and Paulo Meirelles
"""Fill and check the release package of the dataset Token on Me (TOM).

Run each subcommand from any folder; give the release root with --root.

    fill_release.py manifest  --root R --ledgers 'runs/**/ledger.jsonl'
    fill_release.py checksums --root R [--jobs 8]
    fill_release.py verify    --root R [--jobs 8]
    fill_release.py check     --root R [--private-names FILE] [--allow-todo]

manifest   writes MANIFEST.tsv: one row for each parquet/<project>-dataset.parquet.
           The ledgers give the run commits; a project with no ledger row gets
           empty commit cells, and `check` reports it.
checksums  writes SHA256SUMS (sha256sum format) for every file under the root,
           except SHA256SUMS, the folder _staging/, __pycache__ folders and names that
           start with a dot.
verify     computes the sha256 values again and compares them with SHA256SUMS.
check      checks the schema 3 contract, the footer stamp, the organization
           tables, the manifest, and the text files (to-do markers, the at sign,
           private names). A footer key or a file or folder name with the old
           spelling "organis" is a problem. It exits 1 when a check fails.

Needs Python 3.10+ and the duckdb module (1.5 or later).
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AT_SIGN = chr(64)
PROJECT_RE = re.compile(r"([^/]+)-dataset\.parquet$")
SUMS = "SHA256SUMS"
MANIFEST = "MANIFEST.tsv"
SKIP_DIRS = {"_staging"}
TEXT_SUFFIXES = {".md", ".cff", ".tsv", ".txt", ".lock", ".py", ".json", ".sh"}
# Words that the documents must not use (built from parts, so this file passes its own check).
FORBIDDEN_WORDS = ("cen" + "sus", "cor" + "pus")
MARK_WORD = "TO" + "DO"

ORG_TABLES = ("organizations", "organization_domains", "organization_namespaces",
              "project_organizations", "project_facts", "project_languages", "project_labels",
              "link_error", "release_info")
FOOTER_KEYS = ("ctp_schema_version", "organizations_version", "organizations_mapping_sha256")
# The names of this release have the American spelling "organization". The British spelling "organisation" of the
# first build of the release root is a problem in a footer key and in a file or folder name.
OLD_SPELLING = re.compile(r"organis", re.IGNORECASE)
VARCHAR_LIST = "VARCHAR[]"

# ctp schema 3: schema 2 with provenance_status renamed to audit_frame_file and 18 columns dropped
# (size_kb, file_mask, manifest_category, fact, the 6 history columns, person_name, person_email,
# footer_person_names, cregit_commit_sha, repo_tag, archived, fork and roster_lang). The roster_lang
# value is the project_facts fact type roster_language.
SCHEMA_3 = (
    ("repo_name", "VARCHAR"), ("clone_url", "VARCHAR"), ("audit_frame_file", "VARCHAR"),
    ("source", "VARCHAR"), ("stratum", "VARCHAR"), ("contested", "VARCHAR"),
    ("label_date", "VARCHAR"), ("owner", "VARCHAR"), ("repo", "VARCHAR"),
    ("roster_name", "VARCHAR"), ("language", "VARCHAR"),
    ("commits", "VARCHAR"), ("size_class", "VARCHAR"),
    ("stars", "VARCHAR"), ("pushed_at", "VARCHAR"), ("license", "VARCHAR"),
    ("owner_type", "VARCHAR"),
    ("file_path", "VARCHAR"), ("token_index", "BIGINT"), ("source_line", "BIGINT"),
    ("source_col", "BIGINT"), ("source_text", "VARCHAR"), ("token_type", "VARCHAR"),
    ("token_value", "VARCHAR"), ("is_structural", "BIGINT"),
    ("original_commit_sha", "VARCHAR"),
    ("author_name", "VARCHAR"), ("author_email", "VARCHAR"), ("author_date", "VARCHAR"),
    ("committer_name", "VARCHAR"), ("committer_email", "VARCHAR"),
    ("committer_date", "VARCHAR"), ("commit_summary", "VARCHAR"),
    ("personid", "VARCHAR"), ("person_domain", "VARCHAR"),
    ("footer_signed_off_by", VARCHAR_LIST), ("footer_co_authored_by", VARCHAR_LIST),
    ("footer_co_developed_by", VARCHAR_LIST), ("footer_reviewed_by", VARCHAR_LIST),
    ("footer_acked_by", VARCHAR_LIST), ("footer_tested_by", VARCHAR_LIST),
    ("footer_reported_by", VARCHAR_LIST), ("footer_suggested_by", VARCHAR_LIST),
    ("footer_based_on_patch_by", VARCHAR_LIST), ("footer_helped_by", VARCHAR_LIST),
    ("footer_mentored_by", VARCHAR_LIST), ("footer_assisted_by", VARCHAR_LIST),
    ("footer_thanks_to", VARCHAR_LIST), ("footer_personids", VARCHAR_LIST),
    ("firm_based_on_namespace", "VARCHAR"), ("firm_based_on_domain", "VARCHAR"),
    ("project_enterprise_driven", "BOOLEAN"), ("project_enterprise_basis", "VARCHAR"),
)
assert len(SCHEMA_3) == 53

MANIFEST_COLUMNS = ("project", "clone_url", "size_class", "commits", "run_commit",
                    "frame_commit", "cregit_commit", "ctp_commit", "rows", "bytes", "sha256",
                    "path")


def sql_str(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def hash_many(paths: list[str], jobs: int) -> list[str]:
    if jobs <= 1 or len(paths) <= 1:
        return [sha256_file(p) for p in paths]
    # hashlib releases the GIL on large blocks, so threads read and hash in parallel.
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(sha256_file, paths))


def project_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / "parquet").glob("*-dataset.parquet") if p.is_file())


def project_name(path: Path) -> str:
    m = PROJECT_RE.search(path.name)
    if not m:
        raise ValueError(f"not a project file name: {path.name}")
    return m.group(1)


def release_files(root: Path) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        dirnames[:] = sorted(d for d in dirnames
                             if not d.startswith(".") and d != "__pycache__"
                             and not (rel_dir == "." and d in SKIP_DIRS))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            rel = os.path.normpath(os.path.join(rel_dir, name))
            if rel == SUMS:
                continue
            out.append(rel)
    return sorted(out)


def connect():
    import duckdb  # imported here so that --help works without duckdb
    return duckdb.connect()


# ---------- manifest ----------

def read_ledgers(patterns: list[str]) -> dict[str, dict]:
    """The last finished 'project' record of each project, by end time."""
    best: dict[str, dict] = {}
    for pattern in patterns:
        for path in sorted(glob.glob(pattern, recursive=True)):
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("step") != "project" or rec.get("status") != "done":
                        continue
                    name = rec.get("project")
                    if not name:
                        continue
                    old = best.get(name)
                    if old is None or str(rec.get("end_utc", "")) >= str(old.get("end_utc", "")):
                        best[name] = rec
    return best


def file_facts(con, path: Path) -> dict:
    p = sql_str(str(path))
    rows = con.execute(f"SELECT num_rows FROM parquet_file_metadata({p})").fetchone()[0]
    first = con.execute(f"SELECT clone_url, size_class, commits FROM read_parquet({p}) LIMIT 1"
                        ).fetchone() or ("", "", "")
    return {"rows": int(rows or 0), "clone_url": first[0] or "", "size_class": first[1] or "",
            "commits": first[2] or ""}


def cmd_manifest(args) -> int:
    root = Path(args.root)
    files = project_files(root)
    if not files:
        print(f"no project files in {root}/parquet", file=sys.stderr)
        return 2
    ledgers = read_ledgers(args.ledgers or [])
    hashes = hash_many([str(p) for p in files], args.jobs)
    con = connect()
    no_ledger = 0
    out = root / MANIFEST
    tmp = out.with_name("." + MANIFEST + ".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(MANIFEST_COLUMNS)
        for path, digest in zip(files, hashes):
            name = project_name(path)
            facts = file_facts(con, path)
            led = ledgers.get(name, {})
            tools = led.get("tools", {}) or {}
            if not led:
                no_ledger += 1
            w.writerow((name, facts["clone_url"], facts["size_class"],
                        facts["commits"], led.get("checked_out_sha", ""),
                        led.get("snapshot_sha", ""), tools.get("cregit_commit", ""),
                        tools.get("ctp_commit", ""), facts["rows"], path.stat().st_size,
                        digest, os.path.relpath(path, root)))
    os.replace(tmp, out)
    print(f"{out}: {len(files)} projects; {no_ledger} without a ledger row")
    return 0


# ---------- checksums ----------

def cmd_checksums(args) -> int:
    root = Path(args.root)
    rels = release_files(root)
    hashes = hash_many([str(root / r) for r in rels], args.jobs)
    out = root / SUMS
    tmp = out.with_name("." + SUMS + ".tmp")
    with open(tmp, "w") as f:
        for rel, digest in zip(rels, hashes):
            f.write(f"{digest}  {rel}\n")
    os.replace(tmp, out)
    print(f"{out}: {len(rels)} files")
    return 0


def read_sums(path: Path) -> dict[str, str]:
    sums = {}
    with open(path) as f:
        for line in f:
            digest, rel = line.rstrip("\n").split("  ", 1)
            sums[rel] = digest
    return sums


def cmd_verify(args) -> int:
    root = Path(args.root)
    sums = read_sums(root / SUMS)
    rels = release_files(root)
    problems = [f"not in {SUMS}: {r}" for r in rels if r not in sums]
    problems += [f"missing file: {r}" for r in sums if not (root / r).is_file()]
    present = [r for r in sums if (root / r).is_file()]
    for rel, digest in zip(present, hash_many([str(root / r) for r in present], args.jobs)):
        if digest != sums[rel]:
            problems.append(f"sha256 differs: {rel}")
    for p in problems:
        print(p)
    print(f"verify: {len(sums)} rows, {len(problems)} problems")
    return 1 if problems else 0


# ---------- check ----------

def check_parquet(con, root: Path, problems: list[str]) -> None:
    files = project_files(root)
    if not files:
        problems.append("parquet/: no project files")
        return
    info = root / "organizations" / "release_info.parquet"
    release_hash = None
    if info.is_file():
        row = con.execute(f"SELECT value FROM read_parquet({sql_str(str(info))}) "
                          f"WHERE key = 'mapping_sha256'").fetchone()
        release_hash = row[0] if row else None
        if release_hash is None:
            problems.append("release_info: no key mapping_sha256")
    want = list(SCHEMA_3)
    for path in files:
        p = sql_str(str(path))
        got = [(r[0], r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({p})").fetchall()]
        if got != want:
            names = [n for n, _ in got]
            extra = [n for n in names if n not in dict(want)]
            lost = [n for n, _ in want if n not in names]
            problems.append(f"{path.name}: not schema 3 ({len(got)} columns; missing {lost[:3]}, "
                            f"unexpected {extra[:3]})")
        kv = dict(con.execute(f"SELECT decode(key), decode(value) FROM parquet_kv_metadata({p})"
                              ).fetchall())
        for key in FOOTER_KEYS:
            if key not in kv:
                problems.append(f"{path.name}: footer has no {key}")
        old = sorted(k for k in kv if OLD_SPELLING.search(k))
        if old:
            problems.append(f"{path.name}: footer key with the old spelling: {', '.join(old)}")
        if kv.get("ctp_schema_version") not in (None, "3"):
            problems.append(f"{path.name}: ctp_schema_version is {kv.get('ctp_schema_version')}")
        if release_hash and kv.get("organizations_mapping_sha256") not in (None, release_hash):
            problems.append(f"{path.name}: stale file (mapping hash is not the release hash)")


def check_organizations(root: Path, problems: list[str]) -> None:
    for t in ORG_TABLES:
        if not (root / "organizations" / f"{t}.parquet").is_file():
            problems.append(f"organizations/{t}.parquet is missing")
    if not (root / "organizations" / "dataset.duckdb").is_file():
        problems.append("organizations/dataset.duckdb is missing")
    old = [rel for rel in release_files(root) if OLD_SPELLING.search(rel)]
    for rel in old[:20]:
        problems.append(f"{rel}: a name with the old spelling organis")
    if len(old) > 20:
        problems.append(f"{len(old) - 20} more names with the old spelling organis")


def check_manifest(root: Path, problems: list[str]) -> None:
    path = root / MANIFEST
    if not path.is_file():
        problems.append(f"{MANIFEST} is missing")
        return
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    if rows and tuple(rows[0].keys()) != MANIFEST_COLUMNS:
        problems.append(f"{MANIFEST}: the header is not {MANIFEST_COLUMNS}")
        return
    listed = {r["path"]: r for r in rows}
    files = {os.path.relpath(p, root) for p in project_files(root)}
    for rel in sorted(files - set(listed)):
        problems.append(f"{MANIFEST}: no row for {rel}")
    for rel in sorted(set(listed) - files):
        problems.append(f"{MANIFEST}: row for a missing file {rel}")
    sums_path = root / SUMS
    sums = read_sums(sums_path) if sums_path.is_file() else {}
    for rel, r in sorted(listed.items()):
        if rel in sums and sums[rel] != r["sha256"]:
            problems.append(f"{MANIFEST}: sha256 of {rel} is not the {SUMS} value")
        for col in ("run_commit", "cregit_commit", "ctp_commit"):
            if not r.get(col):
                problems.append(f"{MANIFEST}: {r['project']} has no {col}")
                break


def check_text(root: Path, private_names: list[str], allow_todo: bool,
               problems: list[str]) -> None:
    names = [n.lower() for n in private_names if n]
    for rel in release_files(root):
        if Path(rel).suffix.lower() not in TEXT_SUFFIXES and Path(rel).name != SUMS:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"{rel}: not UTF-8 text")
            continue
        low = text.lower()
        for i, line in enumerate(text.splitlines(), 1):
            if AT_SIGN in line:
                problems.append(f"{rel}:{i}: the at sign")
            if not allow_todo and MARK_WORD in line:
                problems.append(f"{rel}:{i}: {MARK_WORD} marker")
        for word in FORBIDDEN_WORDS:
            if re.search(r"\b" + word + r"\b", low):
                problems.append(f"{rel}: the word '{word}'")
        for n in names:
            if n in low:
                problems.append(f"{rel}: a name from the private list")
                break


def cmd_check(args) -> int:
    root = Path(args.root)
    private = []
    if args.private_names:
        if Path(args.private_names).resolve().is_relative_to(root.resolve()):
            print("the private list must be outside the release root", file=sys.stderr)
            return 2
        private = [line.strip() for line in open(args.private_names) if line.strip()]
    problems: list[str] = []
    con = connect()
    check_parquet(con, root, problems)
    check_organizations(root, problems)
    check_manifest(root, problems)
    check_text(root, private, args.allow_todo, problems)
    for p in problems:
        print(p)
    print(f"check: {len(problems)} problems")
    return 1 if problems else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--root", required=True)
    m.add_argument("--ledgers", nargs="*", help="glob patterns of ledger.jsonl files")
    m.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    for name in ("checksums", "verify"):
        s = sub.add_parser(name)
        s.add_argument("--root", required=True)
        s.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    c = sub.add_parser("check")
    c.add_argument("--root", required=True)
    c.add_argument("--private-names", help="a file outside the release, one name on each line")
    c.add_argument("--allow-todo", action="store_true")
    args = ap.parse_args(argv)
    return {"manifest": cmd_manifest, "checksums": cmd_checksums, "verify": cmd_verify,
            "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
