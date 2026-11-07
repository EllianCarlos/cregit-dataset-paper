#!/usr/bin/env python3
"""The tools of kit dataset-release: they assemble and check the release root R of the dataset.

    release_tools.py s3-list-check  --listing LS --prefix KEY --expect N [--input]
    release_tools.py verify-source  --dir D --label L --expect N [--expect-rows N] [--jobs J] [--no-project-files]
                                    --out JSON
    release_tools.py verify-input   --dir IN --a DA --b DB --expect N [--jobs J] --out JSON
    release_tools.py links-check    --a DA --b DB --mapping SHA [--ov V]
    release_tools.py assemble       --a DA --b DB [--input IN] --docs DOCS --root R --expect N --names-out FILE
    release_tools.py layers         --results-a TSV --results-b TSV --b-layer v1 --prefixes "v1=v1 x1k=x1k"
                                    --expect-v1 N --expect-x1k N --out TSV
    release_tools.py pseudo-merge   --a JSON --b JSON --a-files N --b-projects P [P ...] --want-a SHA
                                    --want-b SHA --out JSON
    release_tools.py schema         --root R --fill-release PY --pseudonymization JSON --mapping SHA --ov V
                                    --expect N [--expect-rows N] [--jobs J] --out TSV
    release_tools.py ledger-pick    --ledgers DIR --schema TSV --out JSONL --report TSV
    release_tools.py ledger-merge   --proven JSONL --picked JSONL --schema TSV --out JSONL
    release_tools.py ledger-clean   --records JSONL --ledgers DIR [DIR ...] --out PARQUET --report TSV [--deny W ...]
    release_tools.py ledger-clean-check --file PARQUET --records JSONL [--schema TSV] [--targets TSV ...]
                                    [--deny W ...]
    release_tools.py check-classes  --check-out TXT
    release_tools.py sums-compare   --root R --a DA --b DB [--input IN]
    release_tools.py guard          --root R --names FILE
    release_tools.py no-at          (--root R | FILE ...)
    release_tools.py links-rewrite  --src JSON --out JSON --report TSV
    release_tools.py no-paths       (--root R | FILE ...)
    release_tools.py split-plan     --root R --limit BYTES --max-files N --archive-max BYTES --out-dir D
    release_tools.py reencode-chain --log JSONL --published SUMS --published-sha SHA --input IN --settings-sha SHA
                                    [--pyarrow V] [--duckdb V] [--recheck N] [--jobs J] [--kit-sha SHA ...] --out JSON
    release_tools.py reencode-root  --root R --published SUMS --published-sha SHA --published-manifest TSV
                                    --log JSONL --out TSV

s3-list-check  The listing (aws s3 ls --recursive) of a release folder holds only parquet/<p>-dataset.parquet
               and the six small files of a final write, and N project files. A key with the word registry or
               salt (not a project file) stops the run. --input: the listing of the input prefix of release 2
               (IN_PREFIX): parquet/<p>-dataset.parquet, the files of organizations/ and an optional SHA256SUMS.
verify-source  A downloaded release folder: each SHA256SUMS row is parquet/<p>-dataset.parquet, each file is
               there with its sha256, no other Parquet file; results.tsv names the same files and sha256
               values; links.json gives the sha256 of domain_links.parquet and project_links.parquet; the
               folder holds no other file. Writes a JSON report (counts and hashes). --no-project-files: the
               folder has only the small files (the project files come from the input of release 2), so the
               check of the files on disk and of their sha256 is not done.
verify-input   The input of release 2 (IN_PREFIX, downloaded to IN): parquet/ holds exactly N project files and
               no other file, and their names are the names of SHA256SUMS of A and B; organizations/ holds the
               tables of ORG_TABLES and dataset.duckdb and no file name with the old spelling; IN/SHA256SUMS,
               if there is one, gives the sha256 of each project file. The footers are the job of schema.
links-check    The link tables of folder B (the release takes them): the sha256 of links.json, the mapping
               hash, the version; the difference to folder A (counts and project names only).
assemble       R/parquet/ gets a hard link of each project file of A and B (a copy across file systems), and
               R gets the release documents as they are in DOCS. Stops on a project in both folders or
               another total. --input IN: the project files come from IN/parquet/ (the same names as A and B).
layers         layers.tsv (project, layer) from the input prefix of results.tsv of A and the rows of B.
pseudo-merge   pseudonymization.json of R: the keys that A and B share (they must be equal) and both
               registry hashes with their files.
schema         Each project file: the 71 columns of ctp schema 2 (SCHEMA_2 of fill_release.py), the footer
               (schema version, organizations version, mapping hash, pseudonymization version and the registry
               hash of its folder; no footer key with the old spelling "organis"). Writes one row per file
               (project, columns, rows, registry, problems).
ledger-pick    The ctp ledgers (records step=project, status=done): for each project of R, the record of the
               run that wrote its file (the same rows). Writes the picked records with commit fields only
               and a report (project, class, records, commit). A project with no clear record keeps empty
               commit cells (fill_release.py check reports it).
ledger-merge   The proven records (a sha256 chain from the run file to the input of the final write) before the
               records of ledger-pick. Two records with other commits (also in one file) or a proven record
               with no commit stop the build.
ledger-clean   ledgers.parquet of R (on the main host, where all ledgers are; S0 stages it): all rows of the
               picked run of each file. The run is the run_id and attempt of the done row with the end time and
               the commits of the record (--records); the rows come from each ledger file that holds that done row,
               with no duplicates, in the ledger order (column seq). The tool drops the keys of machine state
               (LEDGER_DROP) and keys of a person identity (IDENTITY_KEY), cuts each absolute path to its base
               name (not /nix/store), replaces machine values (MACHINE_IDS) by the word machine and the user names
               (the user of the tool, ec2-user, ssm-user, --deny) by the word user. One thread and a fixed order:
               the same input gives the same bytes. The report lists each changed key with a count (no value).
ledger-clean-check  ledgers.parquet: the columns; each project of --schema (else of --records) has the rows of
               one run, seq 1..n and one done row; the done row has the end time and commits of its record, the
               sha256 of --targets (the run file) and the rows of --schema (the release file); no value or key
               holds the at sign, a path, a machine value, a user name, a dropped key or an identity key.
check-classes  The lines of `fill_release.py check` in three classes: the to-do markers of the documents,
               the manifest rows with no commit, all other problems (hard). Exit 1 if a hard problem exists.
sums-compare   The project rows of R/SHA256SUMS are the rows of the SHA256SUMS of A and B. --input IN: the
               rows of IN/SHA256SUMS; with no IN/SHA256SUMS, only the names of A and B (the sha256 values of
               release 2 are new, because the footer changed).
guard          R holds no file named registry or salt (the project files of the name list can hold the word,
               for example confluentinc__schema-registry), no env file, no link, no dot name, no __pycache__,
               no Parquet file outside parquet/ and organizations/ (except ledgers.parquet at the top level), no
               project file that is not in the list.
no-at          Exit 1 if a text file (every file that is not Parquet, DuckDB or tar) holds the at sign, or a
               text column of a Parquet file outside R/parquet/. Prints file names and counts only.
links-rewrite  links.json for R: each string value that is an absolute machine path becomes its base name
               (for example /data/final/tools/companies.v4.9.duckdb -> companies.v4.9.duckdb); every other key
               and value stays, also mapping_sha256 and the output hashes (checked). A key with the British
               spelling "organis" gets the American spelling "organiz" (release 2; for example
               organisations_version -> organizations_version). The report lists each change.
no-paths       Exit 1 if a text file (as no-at) or a column of a Parquet file at the top level of R (ledgers.parquet)
               holds an absolute machine path: /data, /data1.., /home, /root, /tmp, /local, /mnt, /var at the
               start of a path. Prints file names, line numbers and row counts only.
split-plan     The Zenodo plan: records of at most --limit bytes and --max-files files under one concept DOI,
               by whole files, in name order, the same plan for the same root. Record 1 holds the top-level
               files and the archive release-meta.tar (docs/, organizations/, tools/). The project files go
               into tar archives of at most --archive-max bytes (one file larger than that gets its own).
               Writes zenodo-plan.tsv, zenodo-records.tsv and records/record-NN.tsv (the manifest of a record).
reencode-chain The input prefix is the re-encode of the published root (kit dataset-reencode): the sha256 of
               --published (the R/SHA256SUMS of the published root) is --published-sha; for each project file of
               it the last line of the re-encode log (--log, one JSON line per file) is OK with all checks true,
               the pinned writer settings (--settings-sha, the same for all lines) and versions (pyarrow, duckdb:
               one set), its reencode.py sha256 one of --kit-sha (repeatable: the kit versions of the stage, the
               retry of one file with a new reencode.py; no --kit-sha: one version for all lines; the report
               lists each version and the DuckDB read batch of each file), its input sha256 is the
               published sha256, its output sha256 and size are the row of IN/SHA256SUMS and the size of the file
               in IN/parquet/, and its rows are the rows of the footer of that file. The organizations/ rows of
               IN/SHA256SUMS are the published rows (byte-identical files). --recheck N: for N files (a fixed
               pick by the sha256 of the name) DuckDB computes the content hash of the input file again (row
               count, sum of the row hashes, the order-dependent sum, one sum for each column); it must be the
               hash of the log. The chain: published sha256 -> log input sha256 -> log content check -> log
               output sha256 -> IN/SHA256SUMS -> (sums-compare) R/SHA256SUMS.
reencode-root  After the checksums of R: the project rows of R/SHA256SUMS are the output sha256 values of the
               log; the other rows are the published rows, except the documents (listed in --out as changed) and
               MANIFEST.tsv; organizations/, ledgers.parquet, links.json, pseudonymization.json and tools/ must be
               byte-identical; no path is added or removed. MANIFEST.tsv (the published one, its sha256 is the
               published row): the same header and rows in the same order; only the columns bytes and sha256
               change, from the input values of the log to its output values.
Exit 0 ok, 1 a check failed, 2 usage. No output holds an address or a person value.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
AT = chr(64)
PROJECT_FILE = re.compile(r"^parquet/([^/]+)-dataset\.parquet$")
SMALL_FILES = ("SHA256SUMS", "results.tsv", "links.json", "domain_links.parquet", "project_links.parquet",
               "pseudonymization.json")
LINK_TABLES = ("domain_links.parquet", "project_links.parquet")
BINARY_SUFFIXES = {".parquet", ".duckdb", ".tar", ".gz", ".zst", ".db"}
FOOTER_SCHEMA = "ctp_schema_version"
FOOTER_OV = "organizations_version"
FOOTER_MAPPING = "organizations_mapping_sha256"
# Release 2 has the American spelling "organization". The final writes of release 1 (folders A and B, their
# links.json) have the British spelling; links-check and verify-source accept it when they read (OLD_OV).
OLD_OV = "organisations_version"
ORG_DIR = "organizations"
ORG_TABLES = ("organizations", "organization_domains", "organization_namespaces", "project_organizations",
              "link_error", "release_info")
OLD_SPELLING = re.compile(r"organis", re.IGNORECASE)
FOOTER_PSEUDO = "pseudonymization_version"
FOOTER_REGISTRY = "pseudonymization_registry_sha256"
TAR_BLOCK = 512
TAR_RECORD = 10240


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_many(paths: list, jobs: int) -> list[str]:
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        return list(ex.map(sha256_file, paths))


def read_sums(path: Path) -> list[tuple[str, str]]:
    rows = []
    for line in Path(path).read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        rows.append((digest, rel))
    return rows


def project_of(rel: str) -> str | None:
    m = PROJECT_FILE.match(rel)
    return m.group(1) if m else None


BACKUP = re.compile(r"\.before-[\w.-]+$")


def links_ov(j: dict):
    """The organizations version of a links.json: the new key, else the old key of release 1."""
    return j.get(FOOTER_OV, j.get(OLD_OV))


def spell(s: str) -> str:
    """The American spelling of a name: organis -> organiz (the case of each letter stays)."""
    return OLD_SPELLING.sub(lambda m: m.group(0)[:-1] + ("Z" if m.group(0)[-1] == "S" else "z"), s)


def pin_ok(value: str, pin: str) -> bool:
    return bool(value) and len(pin) >= 12 and value.startswith(pin)


def word_hit(name: str) -> str | None:
    low = name.lower()
    for w in ("registry", "salt"):
        if w in low:
            return w
    if low.endswith(".env") or low == "env":
        return "env"
    return None


def load_fill_release(path: Path):
    spec = importlib.util.spec_from_file_location("fill_release", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def connect():
    import duckdb
    return duckdb.connect()


def kv_of(con, path: Path) -> dict:
    return dict(con.execute("SELECT decode(key), decode(value) FROM parquet_kv_metadata(?)", [str(path)]).fetchall())


def report(problems: list[str], ok_line: str) -> int:
    for p in problems[:200]:
        print(f"PROBLEM: {p}")
    if len(problems) > 200:
        print(f"PROBLEM: ... {len(problems) - 200} more")
    print(ok_line if not problems else f"{len(problems)} problems")
    return 1 if problems else 0


# ---------------------------------------------------------------- s3-list-check
def cmd_s3_list_check(a) -> int:
    base = a.prefix.rstrip("/") + "/"
    problems, n = [], 0
    for line in Path(a.listing).read_text().splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        key = parts[3]
        if not key.startswith(base):
            problems.append(f"a key outside the prefix: {key}")
            continue
        rel = key[len(base):]
        if project_of(rel):
            n += 1
        elif a.input and (rel == "SHA256SUMS" or (rel.startswith(f"{ORG_DIR}/") and rel.count("/") == 1)):
            continue
        elif not a.input and rel in SMALL_FILES:
            continue
        else:
            w = word_hit(Path(rel).name)
            problems.append(f"an unexpected key{' with the word ' + w if w else ''}: {rel}")
    if n != a.expect:
        problems.append(f"{n} project files, not {a.expect}")
    what = f"the files of {ORG_DIR}/" if a.input else "the small files"
    return report(problems, f"s3-list-check {base}: {n} project files and {what} only")


# ---------------------------------------------------------------- verify-source
def cmd_verify_source(a) -> int:
    d = Path(a.dir)
    problems: list[str] = []
    rep: dict = {"label": a.label}
    sums = read_sums(d / "SHA256SUMS")
    rels = [r for _, r in sums]
    bad = [r for r in rels if not project_of(r)]
    if bad:
        problems.append(f"SHA256SUMS: {len(bad)} rows that are not parquet/<project>-dataset.parquet, first {bad[0]}")
    if len(set(rels)) != len(rels):
        problems.append("SHA256SUMS: a path is there twice")
    on_disk = sorted(f"parquet/{p.name}" for p in (d / "parquet").glob("*") if p.is_file())
    if a.no_project_files:              # release 2: the project files come from the input (verify-input)
        if on_disk:
            problems.append(f"{len(on_disk)} files in parquet/ (want none: --no-project-files), first {on_disk[0]}")
        on_disk = list(rels)
    extra = sorted(set(on_disk) - set(rels))
    missing = sorted(set(rels) - set(on_disk))
    if extra:
        problems.append(f"{len(extra)} files in parquet/ that SHA256SUMS does not name, first {extra[0]}")
    if missing:
        problems.append(f"{len(missing)} files of SHA256SUMS are missing, first {missing[0]}")
    if len(rels) != a.expect:
        problems.append(f"{len(rels)} project files, not {a.expect}")
    present = [] if a.no_project_files else [(dg, r) for dg, r in sums if r not in missing]
    got = hash_many([d / r for _, r in present], a.jobs)
    diff = [r for (dg, r), g in zip(present, got) if dg != g]
    if diff:
        problems.append(f"{len(diff)} files with another sha256, first {diff[0]}")
    want = dict((r, dg) for dg, r in sums)
    with open(d / "results.tsv", newline="") as fh:
        res = list(csv.DictReader(fh, delimiter="\t"))
    rout = {r["output"]: r for r in res}
    if set(rout) != set(rels) or len(res) != len(rels):
        problems.append(f"results.tsv: {len(res)} rows; it does not name the files of SHA256SUMS once each")
    wrong = [o for o, r in rout.items() if want.get(o) and r.get("output_sha256") != want[o]]
    if wrong:
        problems.append(f"results.tsv: {len(wrong)} rows with another sha256, first {wrong[0]}")
    names = [r for r in rout if project_of(r) != rout[r].get("project")]
    if names:
        problems.append(f"results.tsv: {len(names)} rows where the project is not the file name")
    rows = sum(int(r["rows"]) for r in res)
    if a.expect_rows is not None and rows != a.expect_rows:
        problems.append(f"results.tsv: {rows} rows of tokens, not {a.expect_rows}")
    lj = json.loads((d / "links.json").read_text())
    for t in LINK_TABLES:
        if sha256_file(d / t) != lj["outputs"].get(t):
            problems.append(f"{t}: the sha256 is not the one of links.json")
    pj = json.loads((d / "pseudonymization.json").read_text())
    others = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()
                    and str(p.relative_to(d)) not in SMALL_FILES and not project_of(str(p.relative_to(d))))
    if others:
        problems.append(f"{len(others)} other files in the folder, first {others[0]}")
    rep.update({"files": len(rels), "rows": rows, "sha256sums_sha256": sha256_file(d / "SHA256SUMS"),
                "results_sha256": sha256_file(d / "results.tsv"), "links_json_sha256": sha256_file(d / "links.json"),
                "mapping_sha256": lj.get("mapping_sha256"), FOOTER_OV: links_ov(lj),
                "link_projects": lj.get("projects"), "registry_sha256": pj.get("registry_sha256"),
                "pseudonymization_json_sha256": sha256_file(d / "pseudonymization.json"),
                "bytes": (None if a.no_project_files else
                          sum((d / r).stat().st_size for r in rels if r not in missing)),
                "project_files": "input" if a.no_project_files else "here", "problems": problems})
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    files = ("the project files are not here (the input of release 2)" if a.no_project_files
             else f"{rep['bytes']} bytes, each sha256 ok")
    return report(problems, f"verify-source {a.label}: {len(rels)} files, {rows} rows, {files}; links.json ok; "
                            f"registry {str(rep['registry_sha256'])[:12]}")


# ---------------------------------------------------------------- verify-input
def cmd_verify_input(a) -> int:
    d = Path(a.dir)
    problems: list[str] = []
    names = sorted(r for s in (a.a, a.b) for _, r in read_sums(Path(s) / "SHA256SUMS"))
    files = sorted(f"parquet/{p.name}" for p in (d / "parquet").glob("*") if p.is_file())
    proj = [r for r in files if project_of(r)]
    if len(proj) != a.expect:
        problems.append(f"{len(proj)} project files in the input, not {a.expect}")
    if len(proj) != len(files):
        problems.append(f"{len(files) - len(proj)} other files in parquet/, first {sorted(set(files) - set(proj))[0]}")
    if proj != names:
        problems.append(f"{len(set(proj) ^ set(names))} names of the input are not the names of A and B")
    org = d / ORG_DIR
    have = sorted(p.name for p in org.glob("*") if p.is_file()) if org.is_dir() else []
    want = sorted([f"{t}.parquet" for t in ORG_TABLES] + ["dataset.duckdb"])
    if not org.is_dir():
        problems.append(f"the input has no {ORG_DIR}/ folder")
    for f in sorted(set(want) - set(have)):
        problems.append(f"{ORG_DIR}/{f} is missing")
    for f in sorted(set(have) - set(want)):
        problems.append(f"{ORG_DIR}/{f}: not a file of the release")
    old = sorted(str(p.relative_to(d)) for p in d.rglob("*") if OLD_SPELLING.search(p.name))
    if old:
        problems.append(f"{len(old)} names with the old spelling organis, first {old[0]}")
    others = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file()
                    and p.parent not in (d / "parquet", org) and p.relative_to(d).as_posix() != "SHA256SUMS")
    if others:
        problems.append(f"{len(others)} other files in the input, first {others[0]}")
    sums = d / "SHA256SUMS"
    checked = 0
    if sums.is_file():
        rows = read_sums(sums)
        rels = sorted(r for _, r in rows)
        # The rows are the project files, or the project files and the files of the organization folder.
        with_org = sorted(proj + [f"{ORG_DIR}/{f}" for f in have])
        if rels not in (proj, with_org):
            problems.append(f"SHA256SUMS of the input: {len(rels)} rows; {len(set(rels) ^ set(with_org))} names are "
                            f"not the project files and the files of {ORG_DIR}/")
        present = [(dg, r) for dg, r in rows if (d / r).is_file()]
        got = hash_many([d / r for _, r in present], a.jobs)
        diff = [r for (dg, r), g in zip(present, got) if dg != g]
        if diff:
            problems.append(f"{len(diff)} files with another sha256 than in SHA256SUMS of the input, first {diff[0]}")
        checked = len(present)
    rep = {"files": len(proj), "bytes": sum((d / r).stat().st_size for r in proj),
           "sha256sums": sha256_file(sums) if sums.is_file() else None, "sha256_checked": checked,
           ORG_DIR: {f: sha256_file(org / f) for f in have}, "problems": problems}
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    sh = f"each sha256 of SHA256SUMS ok ({checked})" if sums.is_file() else "no SHA256SUMS (the schema step checks the footers)"
    return report(problems, f"verify-input: {len(proj)} project files, the names of A and B; {len(have)} files of "
                            f"{ORG_DIR}/; {sh}")


# ---------------------------------------------------------------- links-check
def cmd_links_check(a) -> int:
    import duckdb
    da, db = Path(a.a), Path(a.b)
    problems = []
    ja = json.loads((da / "links.json").read_text())
    jb = json.loads((db / "links.json").read_text())
    for j, d, label in ((ja, da, "A"), (jb, db, "B")):
        for t in LINK_TABLES:
            if sha256_file(d / t) != j["outputs"].get(t):
                problems.append(f"{label} {t}: the sha256 is not the one of links.json")
        if not pin_ok(j.get("mapping_sha256", ""), a.mapping):
            problems.append(f"{label}: mapping {str(j.get('mapping_sha256'))[:12]}, not {a.mapping[:12]}")
        if a.ov and links_ov(j) != a.ov:
            problems.append(f"{label}: organizations version {links_ov(j)}, not {a.ov}")
    if problems:
        return report(problems, "")
    con = duckdb.connect()
    lines = []
    for t in LINK_TABLES:
        same = sha256_file(da / t) == sha256_file(db / t)
        if same:
            lines.append(f"{t}: the same file in A and B")
            continue
        q = "SELECT count(*) FROM (SELECT * FROM read_parquet(?) EXCEPT SELECT * FROM read_parquet(?))"
        only_b = con.execute(q, [str(db / t), str(da / t)]).fetchone()[0]
        only_a = con.execute(q, [str(da / t), str(db / t)]).fetchone()[0]
        line = f"{t}: {only_b} rows only in B, {only_a} rows only in A"
        if t == "project_links.parquet":
            ps = [r[0] for r in con.execute(
                "SELECT DISTINCT project FROM (SELECT * FROM read_parquet(?) EXCEPT SELECT * FROM read_parquet(?)) "
                "ORDER BY 1 LIMIT 20", [str(db / t), str(da / t)]).fetchall()]
            line += f"; projects of the B rows: {', '.join(ps)}"
        lines.append(line)
    print("\n".join(lines))
    print(f"links: A {len(ja.get('outputs', {}))} outputs, {ja.get('projects')} projects, {ja.get('total_tokens')} tokens; "
          f"B {jb.get('projects')} projects, {jb.get('total_tokens')} tokens")
    return report(problems, f"links-check: B is the link set of the release; mapping {jb['mapping_sha256'][:12]} "
                            f"in A and B; version {links_ov(jb)}")


# ---------------------------------------------------------------- assemble
def place(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src.resolve(), dst)          # the file itself, also when src is a link (the fake aws makes links)
        return "link"
    except OSError:
        shutil.copyfile(src.resolve(), dst)
        return "copy"


def docs_files(docs: Path) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(docs):
        rel_dir = os.path.relpath(dirpath, docs)
        dirnames[:] = sorted(x for x in dirnames if not x.startswith(".") and x != "__pycache__"
                             and not (rel_dir == "." and x == "_staging"))
        for f in sorted(filenames):
            rel = os.path.normpath(os.path.join(rel_dir, f))
            if f.startswith(".") or rel in ("parquet/TODO.txt", f"{ORG_DIR}/TODO.txt") or f.endswith(".pyc"):
                continue
            if BACKUP.search(f):        # the backups of release-staging (<file>.before-<step>) are not documents
                continue
            out.append(rel)
    return out


def cmd_assemble(a) -> int:
    da, db, root = Path(a.a), Path(a.b), Path(a.root)
    pa = [project_of(r) for _, r in read_sums(da / "SHA256SUMS")]
    pb = [project_of(r) for _, r in read_sums(db / "SHA256SUMS")]
    problems = []
    both = sorted(set(pa) & set(pb))
    if both:
        problems.append(f"{len(both)} projects in both folders, first {both[0]}")
    if None in pa or None in pb:
        problems.append("a SHA256SUMS row is not a project file")
    names = sorted(set(p for p in pa + pb if p))
    if len(names) != a.expect:
        problems.append(f"{len(names)} project files in A and B, not {a.expect}")
    di = Path(a.input) if a.input else None      # release 2: the project files of the input, by the names of A and B
    if di is not None:
        got = sorted(p.name[: -len("-dataset.parquet")] for p in (di / "parquet").glob("*-dataset.parquet"))
        if got != names:
            problems.append(f"the input has {len(got)} project files; {len(set(got) ^ set(names))} names are not "
                            f"the names of A and B")
    if root.exists() and any(root.iterdir()):
        problems.append(f"{root} is not empty")
    if problems:
        return report(problems, "")
    (root / "parquet").mkdir(parents=True, exist_ok=True)
    kinds = {"link": 0, "copy": 0}
    for d, ps in ((da, pa), (db, pb)):
        for p in ps:
            kinds[place((di or d) / "parquet" / f"{p}-dataset.parquet", root / "parquet" / f"{p}-dataset.parquet")] += 1
    docs = docs_files(Path(a.docs))
    for rel in docs:
        dst = root / rel
        if dst.exists():
            return report([f"a document would replace {rel}"], "")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(a.docs) / rel, dst)
    Path(a.names_out).write_text("".join(n + "\n" for n in names))
    src = " (the files of the input)" if di is not None else ""
    print(f"assemble: {len(names)} project files ({len(pa)} of A, {len(pb)} of B{src}; {kinds['link']} hard links, "
          f"{kinds['copy']} copies); {len(docs)} documents")
    return 0


# ---------------------------------------------------------------- layers
def cmd_layers(a) -> int:
    pref = dict(x.split("=", 1) for x in a.prefixes.split())
    problems, layer = [], {}
    with open(a.results_a, newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            first = r["input"].split("/", 1)[0]
            if first not in pref:
                problems.append(f"{r['project']}: input prefix {first} has no layer")
                continue
            layer[r["project"]] = pref[first]
    with open(a.results_b, newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if r["project"] in layer:
                problems.append(f"{r['project']}: in both results files")
            layer[r["project"]] = a.b_layer
    bad = sorted(v for v in set(layer.values()) if v not in ("v1", "x1k"))
    if bad:
        problems.append(f"layer values {bad} (fill_release.py takes v1 and x1k)")
    n1 = sum(1 for v in layer.values() if v == "v1")
    n2 = sum(1 for v in layer.values() if v == "x1k")
    if n1 != a.expect_v1 or n2 != a.expect_x1k:
        problems.append(f"{n1} rows of the 5,000+ layer and {n2} of the 1,000-4,999 layer, not "
                        f"{a.expect_v1} and {a.expect_x1k}")
    if problems:
        return report(problems, "")
    with open(a.out, "w") as fh:
        fh.write("project\tlayer\n")
        for p in sorted(layer):
            fh.write(f"{p}\t{layer[p]}\n")
    print(f"layers: {len(layer)} projects: {n1} v1 (5,000 commits or more), {n2} x1k (1,000 to 4,999)")
    return 0


# ---------------------------------------------------------------- pseudo-merge
def cmd_pseudo_merge(a) -> int:
    ja = json.loads(Path(a.a).read_text())
    jb = json.loads(Path(a.b).read_text())
    problems = []
    ra, rb = ja.get("registry_sha256", ""), jb.get("registry_sha256", "")
    if not pin_ok(ra, a.want_a):
        problems.append(f"A names registry {ra[:12]}, not {a.want_a[:12]}")
    if not pin_ok(rb, a.want_b):
        problems.append(f"B names registry {rb[:12]}, not {a.want_b[:12]}")
    if ra == rb:
        problems.append("A and B name the same registry")
    keys = (set(ja) | set(jb)) - {"registry_sha256"}
    for k in sorted(keys):
        if ja.get(k) != jb.get(k):
            problems.append(f"the key {k} differs in A and B")
    if problems:
        return report(problems, "")
    b_projects = sorted(a.b_projects)
    out = {k: ja[k] for k in sorted(keys)}
    out["registries"] = [
        {"registry_sha256": ra, "files": a.a_files,
         "scope": "every file of parquet/ except the files of the next registry"},
        {"registry_sha256": rb, "files": len(b_projects), "projects": b_projects,
         "scope": "the files of these projects (a separate write after the first one, with the same salt)"}]
    out["registry_relation"] = ("The second registry is the first one plus the identities of the projects of the "
                                "second row. Each pseudonym of the first registry has the same value in the second "
                                "one. The footer key pseudonymization_registry_sha256 of each file names its registry.")
    text = json.dumps(out, indent=1, sort_keys=True) + "\n"
    if AT in text:
        return report(["the output holds the at sign"], "")
    Path(a.out).write_text(text)
    print(f"pseudo-merge: registries {ra[:12]} ({a.a_files} files) and {rb[:12]} ({', '.join(b_projects)}); "
          f"{len(keys)} shared keys equal")
    return 0


# ---------------------------------------------------------------- schema
def cmd_schema(a) -> int:
    import duckdb
    fr = load_fill_release(Path(a.fill_release))
    want = [tuple(x) for x in fr.SCHEMA_2]
    pj = json.loads(Path(a.pseudonymization).read_text())
    regs = pj["registries"]
    ra, rb = regs[0]["registry_sha256"], regs[1]["registry_sha256"]
    bset = set(regs[1]["projects"])
    files = sorted((Path(a.root) / "parquet").glob("*-dataset.parquet"))
    local = threading.local()

    def one(path: Path):
        con = getattr(local, "con", None)
        if con is None:
            con = local.con = duckdb.connect()
        name = path.name[: -len("-dataset.parquet")]
        probs = []
        got = [(r[0], r[1]) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]
        if got != want:
            probs.append(f"not the 71 columns of schema 2 ({len(got)} columns)")
        kv = kv_of(con, path)
        rows = con.execute("SELECT num_rows FROM parquet_file_metadata(?)", [str(path)]).fetchone()[0]
        if kv.get(FOOTER_SCHEMA) != "2":
            probs.append(f"{FOOTER_SCHEMA} {kv.get(FOOTER_SCHEMA)}")
        if kv.get(FOOTER_OV) != a.ov:
            probs.append(f"{FOOTER_OV} {kv.get(FOOTER_OV)}")
        if kv.get(FOOTER_MAPPING) != a.mapping:
            probs.append(f"mapping {str(kv.get(FOOTER_MAPPING))[:12]}")
        old = sorted(k for k in kv if OLD_SPELLING.search(k))
        if old:
            probs.append(f"footer key with the old spelling: {', '.join(old)}")
        if kv.get(FOOTER_PSEUDO) != str(pj.get("pseudonymization_version")):
            probs.append(f"{FOOTER_PSEUDO} {kv.get(FOOTER_PSEUDO)}")
        reg = kv.get(FOOTER_REGISTRY, "")
        if reg != (rb if name in bset else ra):
            probs.append(f"registry {reg[:12]} (want {(rb if name in bset else ra)[:12]})")
        return name, len(got), int(rows or 0), reg[:12], "; ".join(probs)

    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        res = list(ex.map(one, files))
    with open(a.out, "w") as fh:
        fh.write("project\tcolumns\trows\tregistry\tproblems\n")
        for r in res:
            fh.write("\t".join(str(x) for x in r) + "\n")
    problems = [f"{r[0]}: {r[4]}" for r in res if r[4]]
    rows = sum(r[2] for r in res)
    if len(res) != a.expect:
        problems.append(f"{len(res)} project files, not {a.expect}")
    if a.expect_rows is not None and rows != a.expect_rows:
        problems.append(f"{rows} rows, not {a.expect_rows}")
    missing_b = sorted(bset - {r[0] for r in res})
    if missing_b:
        problems.append(f"the projects of registry B are not in R: {missing_b}")
    nb = sum(1 for r in res if r[0] in bset)
    return report(problems, f"schema: {len(res)} files, 71 columns of ctp schema 2 each, footer ok "
                            f"(schema 2, {a.ov}, mapping {a.mapping[:12]}); {rows} rows; registry {ra[:12]} in "
                            f"{len(res) - nb} files, {rb[:12]} in {nb}")


# ---------------------------------------------------------------- ledger-pick
TEST_LEDGER = re.compile(r"(^|\.)test\.jsonl$")


def ledger_files(d: Path) -> list[Path]:
    return sorted(p for p in d.rglob("*.jsonl") if p.is_file() and not TEST_LEDGER.search(p.name))


def cmd_ledger_pick(a) -> int:
    rows = {}
    with open(a.schema, newline="") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            rows[r["project"]] = int(r["rows"])
    recs: dict[str, dict] = {p: {} for p in rows}
    nfiles = 0
    for f in ledger_files(Path(a.ledgers)):
        nfiles += 1
        with open(f, errors="replace") as fh:
            for line in fh:
                if '"project"' not in line or '"done"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("step") != "project" or r.get("status") != "done" or r.get("project") not in recs:
                    continue
                tools = r.get("tools") or {}
                pq = r.get("parquet") or {}
                key = (str(r.get("run_id", "")), str(r.get("end_utc", "")), str(r.get("checked_out_sha", "")))
                recs[r["project"]][key] = {
                    "end_utc": str(r.get("end_utc", "")), "checked_out_sha": r.get("checked_out_sha") or "",
                    "snapshot_sha": r.get("snapshot_sha") or "", "cregit_commit": tools.get("cregit_commit") or "",
                    "ctp_commit": tools.get("ctp_commit") or "", "rows": pq.get("rows")}
    counts: dict[str, int] = {}
    picked = []
    with open(a.report, "w") as rep:
        rep.write("project\tclass\trecords\tcommit\n")
        for p in sorted(rows):
            rs = sorted(recs[p].values(), key=lambda x: x["end_utc"])
            full = [x for x in rs if x["checked_out_sha"] and x["cregit_commit"] and x["ctp_commit"]]
            match = [x for x in full if x["rows"] is not None and int(x["rows"]) == rows[p]]
            pick, cls = None, ""
            if match:
                if len({(x["checked_out_sha"], x["cregit_commit"], x["ctp_commit"]) for x in match}) == 1:
                    pick, cls = match[-1], "rows"
                else:
                    cls = "gap-ambiguous"
            elif full:
                if any(x["rows"] is not None for x in full):
                    cls = "gap-other-rows"
                elif len({(x["checked_out_sha"], x["cregit_commit"], x["ctp_commit"]) for x in full}) == 1:
                    pick, cls = full[-1], "one-run-no-rows"
                else:
                    cls = "gap-ambiguous"
            else:
                cls = "gap-no-record" if not rs else "gap-fields"
            counts[cls] = counts.get(cls, 0) + 1
            rep.write(f"{p}\t{cls}\t{len(rs)}\t{(pick or {}).get('checked_out_sha', '')[:12]}\n")
            if pick:
                picked.append({"step": "project", "status": "done", "project": p, "end_utc": pick["end_utc"],
                               "checked_out_sha": pick["checked_out_sha"], "snapshot_sha": pick["snapshot_sha"],
                               "tools": {"cregit_commit": pick["cregit_commit"], "ctp_commit": pick["ctp_commit"]}})
    with open(a.out, "w") as fh:
        for r in picked:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    print(f"ledger-pick: {nfiles} ledger files; {len(rows)} projects; picked {len(picked)}; classes "
          + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 0


# ---------------------------------------------------------------- ledger-merge
def cmd_ledger_merge(a) -> int:
    """The proven records (sha256 chain from the run file to the final-write input, made on the main host with
    the local ledgers too) before the records of ledger-pick. A project with two records that name other commits
    stops the build; a proven record for a project that is not in the release stops it too."""
    with open(a.schema, newline="") as fh:
        rows = {r["project"] for r in csv.DictReader(fh, delimiter="\t")}

    def key(r):
        t = r.get("tools") or {}
        return (r.get("checked_out_sha") or "", t.get("cregit_commit") or "", t.get("ctp_commit") or "")

    bad = []

    def load(f):  # a project with two records of other commits in one file is a problem (not the last one wins)
        out = {}
        for line in Path(f).read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r["project"] in out and key(out[r["project"]]) != key(r):
                    bad.append(f"{r['project']}: two records with other commits in {Path(f).name}")
                out[r["project"]] = r
        return out

    proven, picked = load(a.proven), load(a.picked)
    bad += [f"proven record for {p}, which is not in the release" for p in sorted(set(proven) - rows)]
    bad += [f"{p}: the proven record has no checked_out_sha, cregit_commit or ctp_commit"
            for p in sorted(proven) if not all(key(proven[p]))]
    bad += [f"{p}: proven {key(proven[p])} but ledger-pick {key(picked[p])}"
            for p in sorted(set(proven) & set(picked)) if key(proven[p]) != key(picked[p])]
    n = {"proven": 0, "ledger": 0, "none": 0}
    with open(a.out, "w") as fh:
        for p in sorted(rows):
            r = proven.get(p) or picked.get(p)
            n["proven" if p in proven else "ledger" if r else "none"] += 1
            if r:
                fh.write(json.dumps(r, sort_keys=True) + "\n")
    for b in bad[:50]:
        print(f"HARD: {b}")
    print(f"ledger-merge: {len(rows)} projects; proven {n['proven']}; ledger-pick only {n['ledger']}; "
          f"no record {n['none']}; {len(bad)} problems; picked {n['proven'] + n['ledger']};")
    return 1 if bad else 0


# ---------------------------------------------------------------- ledger-clean, ledger-clean-check
LEDGERS_FILE = "ledgers.parquet"
LEDGER_RULES = "ledger-clean 1"
# An absolute path (or a path under ~) in a string. It must not start inside a word, a URL or another path. The
# Nix store paths stay: they name the build of a tool, not a folder of a machine.
PATH_TOKEN = re.compile(r"(?<![\w.:/~-])~?/(?!nix/store/)[^\s\"'`,;=()\[\]{}<>|]+")
# Values that name a machine: instance, volume and network ids, EC2 host names, IPv4 addresses, S3 URLs and ARNs,
# account ids (12 digits alone).
MACHINE_IDS = re.compile(r"\b(?:i|vol|snap|sg|subnet|vpc|ami|eni)-[0-9a-f]{8,17}\b|\bip-\d{1,3}(?:-\d{1,3}){3}\b"
                         r"|\b[\w-]+\.(?:compute|ec2)\.internal\b|\b(?:\d{1,3}\.){3}\d{1,3}\b|\bs3://[^\s\"']*"
                         r"|\barn:aws[\w:/.-]*|(?<!\w)\d{12}(?!\w)|AWS_PROFILE|--profile\b")
# Keys that hold only the state of the machine and serve no reproduction purpose.
LEDGER_DROP = ("queue_pos", "queue_total", "log", "cleanup", "pin.dest", "flags.cregit_dir", "flags.output_dir")
# Keys that can hold the identity of a person. The ledgers of ctp hold none; the tool drops such a key.
IDENTITY_KEY = re.compile(r"(?i)^(?:author\w*|committer\w*|e_?mail\w*|mail|identity|person\w*|user_?name|login)$")
# The public facts of a project (the name, the clone URL, the branch): the machine rule does not change them.
LEDGER_PUBLIC = ("project", "manifest_row", "pin.url", "resolve.url", "pin.branch", "pin.remote_default_branch",
                 "resolve.branch")
LEDGER_COLUMNS = (("project", "VARCHAR"), ("run_id", "VARCHAR"), ("attempt", "INTEGER"), ("seq", "INTEGER"),
                  ("step", "VARCHAR"), ("status", "VARCHAR"), ("start_utc", "VARCHAR"), ("end_utc", "VARCHAR"),
                  ("duration_s", "DOUBLE"), ("exit_code", "INTEGER"), ("v", "INTEGER"), ("pinned_sha", "VARCHAR"),
                  ("checked_out_sha", "VARCHAR"), ("snapshot_sha", "VARCHAR"), ("file_mask_sha256", "VARCHAR"),
                  ("parquet_file", "VARCHAR"), ("parquet_rows", "BIGINT"), ("parquet_bytes", "BIGINT"),
                  ("parquet_sha256", "VARCHAR"), ("argv", "VARCHAR[]"), ("manifest_row", "VARCHAR"),
                  ("tools", "VARCHAR"), ("flags", "VARCHAR"), ("extra", "VARCHAR"))
LEDGER_JSON = ("manifest_row", "tools", "flags", "extra")


def deny_words(extra=()) -> list[str]:
    import getpass
    words = {getpass.getuser(), "ec2-user", "ssm-user", *extra}
    return sorted(w for w in words if w and len(w) >= 3)


def canon(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def is_public(key: str) -> bool:
    return any(key == p or key.startswith(p + ".") for p in LEDGER_PUBLIC)


class LedgerCleaner:
    """Cleans one ledger row: drops the machine keys, cuts each path to its base name, replaces machine values by
    the word machine and the user names by the word user. Counts each change by key (no value)."""

    def __init__(self, deny: list[str]):
        self.counts: dict[tuple[str, str], int] = {}
        self.deny = re.compile(r"(?i)(?<![\w-])(?:" + "|".join(map(re.escape, deny)) + r")(?![\w-])") if deny else None

    def count(self, key: str, action: str, n: int = 1) -> None:
        self.counts[(key, action)] = self.counts.get((key, action), 0) + n

    def text(self, s: str, key: str) -> str:
        def cut(m):
            base = os.path.basename(m.group(0).rstrip("/"))
            return base or "machine"
        s2, n = PATH_TOKEN.subn(cut, s)
        if n:
            self.count(key, "path cut to the base name", n)
        if not is_public(key):
            # the user names first: a name can hold a machine value (the bucket name holds the account id)
            if self.deny:
                s2, n = self.deny.subn("user", s2)
                if n:
                    self.count(key, "user name replaced by user", n)
            s2, n = MACHINE_IDS.subn("machine", s2)
            if n:
                self.count(key, "machine value replaced by machine", n)
        return s2

    def value(self, v, key: str):
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                sub = f"{key}.{k}" if key else k
                if sub in LEDGER_DROP:
                    self.count(sub, "key dropped (machine state)")
                    continue
                if IDENTITY_KEY.match(k):
                    self.count(sub, "key dropped (identity)")
                    continue
                k2 = self.text(k, sub + "{key}") if isinstance(k, str) else k
                out[k2] = self.value(x, sub)
            return out
        if isinstance(v, list):
            return [self.value(x, key + "[]") for x in v]
        if isinstance(v, str):
            return self.text(v, key)
        return v

    def row(self, r: dict, seq: int) -> dict:
        c = self.value(r, "")
        out = {"seq": seq}
        for name, _ in LEDGER_COLUMNS:
            if name in ("seq", "extra", "argv") or name.startswith("parquet_") or name in LEDGER_JSON:
                continue
            out[name] = c.pop(name, None)
        pq = c.pop("parquet", None)
        if isinstance(pq, dict):
            out["parquet_file"] = pq.pop("path", None)
            out["parquet_rows"] = pq.pop("rows", None)
            out["parquet_bytes"] = pq.pop("bytes", None)
            out["parquet_sha256"] = pq.pop("sha256", None)
            if pq:
                c["parquet"] = pq
        elif pq is not None:
            c["parquet"] = pq
        argv = c.pop("argv", None)
        if isinstance(argv, list) and all(isinstance(x, str) for x in argv):
            out["argv"] = argv
        elif argv is not None:
            c["argv"] = argv
        for name in ("manifest_row", "tools", "flags"):
            x = c.pop(name, None)
            out[name] = None if x is None else canon(x)
        out["extra"] = canon(c) if c else None
        return out


def ledger_scan_files(dirs: list[str]) -> list[Path]:
    """The ledger files of the folders, in path order: no test ledger, nothing under gate/ or .venv/."""
    out = []
    for d in dirs:
        out += [p for p in ledger_files(Path(d)) if not ({"gate", ".venv"} & set(p.relative_to(d).parts[:-1]))]
    return sorted(set(out))


def record_key(r: dict) -> tuple:
    t = r.get("tools") or {}
    return (str(r.get("end_utc") or ""), r.get("checked_out_sha") or "", r.get("snapshot_sha") or "",
            t.get("cregit_commit") or "", t.get("ctp_commit") or "")


def cmd_ledger_clean(a) -> int:
    """The cleaned ledger rows of the picked run of each file, as one Parquet file (built on the main host, where
    all ledgers are; S0 stages it)."""
    import duckdb
    recs = {}
    raw = Path(a.records).read_bytes()  # one read: the sha256 of the footer is the sha256 of the records used
    for line in raw.decode().splitlines():
        if line.strip():
            r = json.loads(line)
            recs[r["project"]] = record_key(r)
    files = ledger_scan_files(a.ledgers)
    # 1. the done row of the picked run: project, end time, commits as the record
    hits: dict[str, dict[str, tuple]] = {p: {} for p in recs}
    for f in files:
        with open(f, errors="replace") as fh:
            for line in fh:
                if '"done"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                p = r.get("project")
                if (p in recs and r.get("step") == "project" and r.get("status") == "done"
                        and record_key(r) == recs[p]):
                    hits[p][str(f)] = (r.get("run_id"), r.get("attempt"))
    problems = [f"{p}: no done row with the commits of the record" for p in sorted(recs) if not hits[p]]
    problems += [f"{p}: the done rows name {len(set(h.values()))} runs" for p, h in sorted(hits.items())
                 if len(set(h.values())) > 1]
    if problems:
        return report(problems, "")
    # 2. all rows of that run (same run_id, project, attempt) in each file that holds the done row; no duplicates
    want: dict[str, set] = {}
    for p, h in hits.items():
        for f, (run_id, att) in h.items():
            want.setdefault(f, set()).add((p, run_id, att))
    rows: dict[str, dict[str, dict]] = {p: {} for p in recs}
    for f in sorted(want):
        ids = {k[1] for k in want[f] if k[1]}
        with open(f, errors="replace") as fh:
            for line in fh:
                if not any(i in line for i in ids):
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                k = (r.get("project"), r.get("run_id"), r.get("attempt"))
                if k in want[f]:
                    rows[k[0]].setdefault(canon(r), r)
    for p in sorted(recs):
        done = [r for r in rows[p].values() if r.get("step") == "project" and r.get("status") == "done"]
        if len(done) != 1:
            problems.append(f"{p}: {len(done)} done rows in the run")
    if problems:
        return report(problems, "")
    # 3. clean, then one Parquet file in a fixed order (one thread, the same bytes for the same input)
    cl = LedgerCleaner(deny_words(a.deny or ()))
    out = Path(a.out)
    tmp = out.with_name(out.name + ".rows.tmp.jsonl")
    n = 0
    with open(tmp, "w") as fh:
        for p in sorted(recs):
            for seq, r in enumerate(rows[p].values(), 1):
                fh.write(canon(cl.row(r, seq)) + "\n")
                n += 1
    cols = ", ".join(f"'{c}': '{t}'" for c, t in LEDGER_COLUMNS)
    names = ", ".join(c for c, _ in LEDGER_COLUMNS)
    meta = {"rules": LEDGER_RULES, "records_sha256": hashlib.sha256(raw).hexdigest(), "projects": str(len(recs)),
            "rows": str(n)}
    kv = ", ".join(f"{k}: '{v}'" for k, v in meta.items())
    part = out.with_name(out.name + ".part")
    con = duckdb.connect()
    con.execute("SET threads = 1")
    con.execute("SET preserve_insertion_order = true")
    con.execute(f"COPY (SELECT {names} FROM read_json('{tmp}', format = 'newline_delimited', columns = {{{cols}}}) "
                f"ORDER BY project, run_id, attempt NULLS FIRST, seq) TO '{part}' "
                f"(FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 19, ROW_GROUP_SIZE 200000, KV_METADATA {{{kv}}})")
    con.close()
    os.replace(part, out)
    tmp.unlink()
    with open(a.report, "w") as fh:
        fh.write("key\taction\tcount\n")
        for (k, act), c in sorted(cl.counts.items()):
            fh.write(f"{k}\t{act}\t{c}\n")
    by_act: dict[str, int] = {}
    for (_, act), c in cl.counts.items():
        by_act[act] = by_act.get(act, 0) + c
    acts = "; ".join(f"{act} {c}" for act, c in sorted(by_act.items())) or "no key changed"
    print(f"ledger-clean: {len(files)} ledger files; {len(recs)} projects; {n} rows; {acts}; "
          f"{out.name} {sha256_file(out)[:12]} ({out.stat().st_size} B)")
    return 0


def ledger_strings(v, key: str):
    """Each string of a cleaned value with its key; the keys of a JSON object count as strings too."""
    if isinstance(v, dict):
        for k, x in v.items():
            sub = f"{key}.{k}" if key else k
            yield sub + "{key}", k
            yield from ledger_strings(x, sub)
    elif isinstance(v, list):
        for x in v:
            yield from ledger_strings(x, key + "[]")
    elif isinstance(v, str):
        yield key, v


def cmd_ledger_clean_check(a) -> int:
    """The cleaned ledger file: every project has the rows of one run with one done row; the done row has the
    commits of its record (and the sha256 of the run file, the rows of the release file when given); no value holds
    the at sign, a path, a machine value, a user name or an identity key."""
    con = connect()
    f = str(a.file)
    desc = [(r[0], r[1]) for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [f]).fetchall()]
    problems = []
    if [c for c, _ in desc] != [c for c, _ in LEDGER_COLUMNS]:
        problems.append(f"the columns are not the {len(LEDGER_COLUMNS)} columns of ledger-clean")
        return report(problems, "")
    recs = {}
    for line in Path(a.records).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            recs[r["project"]] = record_key(r)
    projects = set(recs)
    rows_of = {}
    if a.schema:
        with open(a.schema, newline="") as fh:
            rows_of = {r["project"]: int(r["rows"]) for r in csv.DictReader(fh, delimiter="\t")}
        projects = set(rows_of)
    target = {}
    for t in a.targets or ():
        with open(t, newline="") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                target[r["project"]] = r["sha256"]
    deny = deny_words(a.deny or ())
    deny_re = re.compile(r"(?i)(?<![\w-])(?:" + "|".join(map(re.escape, deny)) + r")(?![\w-])")
    names = [c for c, _ in LEDGER_COLUMNS]
    runs: dict[str, set] = {}
    seqs: dict[str, list] = {}
    done: dict[str, list] = {}
    nrows = 0
    hits: dict[str, int] = {}
    cur = con.execute("SELECT * FROM read_parquet(?)", [f])
    while True:
        batch = cur.fetchmany(20000)
        if not batch:
            break
        for t in batch:
            nrows += 1
            r = dict(zip(names, t))
            p = r["project"]
            runs.setdefault(p, set()).add((r["run_id"], r["attempt"]))
            seqs.setdefault(p, []).append(r["seq"])
            if r["step"] == "project" and r["status"] == "done":
                done.setdefault(p, []).append(r)
            for c in names:
                v = r[c]
                if c in LEDGER_JSON and v is not None:
                    v = json.loads(v)
                    key = "" if c == "extra" else c
                else:
                    key = c
                for k, s in ledger_strings(v, key):
                    kinds = []
                    if AT in s:
                        kinds.append("the at sign")
                    if PATH_TOKEN.search(s) or MACHINE_PATH.search(s):
                        kinds.append("a path")
                    if not is_public(k.replace("{key}", "")):
                        if MACHINE_IDS.search(s):
                            kinds.append("a machine value")
                        if deny and deny_re.search(s):
                            kinds.append("a user name")
                    if k.endswith("{key}"):
                        last = k[:-5].rsplit(".", 1)[-1]
                        if IDENTITY_KEY.match(last) or k[:-5] in LEDGER_DROP:
                            kinds.append("a dropped key")
                    for kind in kinds:
                        hits[f"{k}: {kind}"] = hits.get(f"{k}: {kind}", 0) + 1
    problems += [f"{k} ({n} values)" for k, n in sorted(hits.items())]
    have = set(runs)
    problems += [f"{p}: no rows" for p in sorted(projects - have)]
    problems += [f"{p}: rows of a project that is not in the list" for p in sorted(have - projects)]
    n_rec = n_sha = n_rows = 0
    for p in sorted(have & projects):
        if len(runs[p]) != 1:
            problems.append(f"{p}: rows of {len(runs[p])} runs")
        if sorted(seqs[p]) != list(range(1, len(seqs[p]) + 1)):
            problems.append(f"{p}: the row numbers are not 1..{len(seqs[p])}")
        d = done.get(p, [])
        if len(d) != 1:
            problems.append(f"{p}: {len(d)} done rows")
            continue
        d = d[0]
        tools = json.loads(d["tools"] or "{}")
        got = (d["end_utc"] or "", d["checked_out_sha"] or "", d["snapshot_sha"] or "",
               tools.get("cregit_commit") or "", tools.get("ctp_commit") or "")
        if p in recs:
            n_rec += 1
            if got != recs[p]:
                problems.append(f"{p}: the done row does not have the commits of the record")
        if p in target:
            n_sha += 1
            if d["parquet_sha256"] != target[p]:
                problems.append(f"{p}: the done row does not have the sha256 of the run file")
        if p in rows_of:
            n_rows += 1
            if d["parquet_rows"] != rows_of[p]:
                problems.append(f"{p}: the done row has {d['parquet_rows']} rows, the release file {rows_of[p]}")
    return report(problems, f"ledger-clean-check: {Path(f).name}: {nrows} rows, {len(have)} projects of "
                            f"{len(projects)}; done row = record for {n_rec}, sha256 of the run file for {n_sha}, "
                            f"rows of the release file for {n_rows}; no at sign, path, machine value, user name "
                            f"or identity key")


# ---------------------------------------------------------------- check-classes
def cmd_check_classes(a) -> int:
    marker, ledger, hard = 0, 0, []
    mark = "TO" + "DO"
    for line in Path(a.check_out).read_text().splitlines():
        if line.startswith("check:") or not line.strip():
            continue
        if line.endswith(f" {mark} marker"):
            marker += 1
        elif re.search(r"^MANIFEST\.tsv: \S+ has no (run_commit|cregit_commit|ctp_commit)$", line):
            ledger += 1
        else:
            hard.append(line)
    for h in hard[:50]:
        print(f"HARD: {h}")
    print(f"check classes: {len(hard)} hard, {marker} marker lines, {ledger} manifest rows with no commit")
    return 1 if hard else 0


# ---------------------------------------------------------------- sums-compare
def cmd_sums_compare(a) -> int:
    root = Path(a.root)
    got = {r: d for d, r in read_sums(root / "SHA256SUMS") if r.startswith("parquet/")}
    want = {}
    for d in (Path(a.a), Path(a.b)):
        want.update({r: dg for dg, r in read_sums(d / "SHA256SUMS")})
    problems = []
    what = "the source rows"
    if a.input:          # release 2: the footer changed, so the sha256 values are the ones of the input
        sums = Path(a.input) / "SHA256SUMS"
        if sums.is_file():
            rows = read_sums(sums)
            inp = {r: dg for dg, r in rows if r.startswith("parquet/")}
            # The input SHA256SUMS can also list the files of the organization folder: R must have the same bytes.
            org_in = {r: dg for dg, r in rows if r.startswith(f"{ORG_DIR}/")}
            org_r = {r: d for d, r in read_sums(root / "SHA256SUMS") if r.startswith(f"{ORG_DIR}/")}
            bad = sorted(r for r in org_in if org_r.get(r) != org_in[r])
            if bad:
                problems.append(f"{len(bad)} files of {ORG_DIR}/ in R are not the files of the input, first {bad[0]}")
            if set(inp) != set(want):
                problems.append(f"the input SHA256SUMS has {len(inp)} rows; {len(set(inp) ^ set(want))} names are "
                                f"not the names of A and B")
            want, what = inp, "the rows of the input SHA256SUMS"
        else:
            want, what = {r: got.get(r) for r in want}, "the names of A and B (the input has no SHA256SUMS)"
    if set(got) != set(want):
        problems.append(f"R/SHA256SUMS has {len(got)} parquet/ rows, the sources {len(want)}; "
                        f"{len(set(got) ^ set(want))} differ")
    diff = [r for r in got if r in want and got[r] != want[r]]
    if diff:
        problems.append(f"{len(diff)} files with another sha256 than in the source SHA256SUMS, first {diff[0]}")
    return report(problems, f"sums-compare: the {len(got)} parquet/ rows of R/SHA256SUMS are {what}")


# ---------------------------------------------------------------- guard
def cmd_guard(a) -> int:
    root = Path(a.root)
    names = set(Path(a.names).read_text().split())
    problems = []
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for x in dirnames:
            rel = os.path.normpath(os.path.join(rel_dir, x))
            if x.startswith(".") or x == "__pycache__":
                problems.append(f"a folder {rel}")
            elif os.path.islink(os.path.join(dirpath, x)):
                problems.append(f"a link {rel}")
            elif word_hit(x):
                problems.append(f"a folder named {word_hit(x)}: {rel}")
        for x in filenames:
            rel = os.path.normpath(os.path.join(rel_dir, x))
            full = os.path.join(dirpath, x)
            if os.path.islink(full):
                problems.append(f"a link {rel}")
                continue
            if x.startswith("."):
                problems.append(f"a dot file {rel}")
                continue
            p = project_of(rel)
            if p is not None:
                seen += 1
                if p not in names:
                    problems.append(f"a project file that is not in the name list: {rel}")
                continue
            if rel.startswith("parquet/"):
                problems.append(f"a file in parquet/ that is not a project file: {rel}")
            elif rel.endswith(".parquet") and not rel.startswith(f"{ORG_DIR}/") and rel != LEDGERS_FILE:
                problems.append(f"a Parquet file outside parquet/ and {ORG_DIR}/: {rel}")
            w = word_hit(x)
            if w:
                problems.append(f"a file named {w}: {rel}")
    if seen != len(names):
        problems.append(f"{seen} project files in R, {len(names)} names in the list")
    return report(problems, f"guard: {seen} project files of the name list; no registry, salt or env file, "
                            f"no link, no dot name")


# ---------------------------------------------------------------- no-at
def cmd_no_at(a) -> int:
    if a.root:
        root = Path(a.root)
        files = [p for p in sorted(root.rglob("*")) if p.is_file() and not (
            p.suffix == ".parquet" and p.relative_to(root).parts[0] == "parquet")]
    else:
        files = [Path(f) for f in a.files]
    con = None
    bad, text_n, pq_n = 0, 0, 0
    for f in files:
        if f.suffix == ".parquet":
            con = con or connect()
            pq_n += 1
            cols = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(f)]).fetchall()]
            cond = " OR ".join(f'contains(coalesce(CAST("{c}" AS VARCHAR), \'\'), chr(64))' for c in cols) or "false"
            n = con.execute(f"SELECT count(*) FROM read_parquet(?) WHERE {cond}", [str(f)]).fetchone()[0]
            if n:
                bad += 1
                print(f"AT SIGN: {f.name}: {n} rows")
        elif f.suffix in BINARY_SUFFIXES:
            continue
        else:
            text_n += 1
            n = f.read_bytes().count(AT.encode())
            if n:
                bad += 1
                print(f"AT SIGN: {f.name}: {n} times")
    print(f"no-at: {text_n} text files and {pq_n} Parquet files checked; {bad} with the at sign")
    return 1 if bad else 0


# ---------------------------------------------------------------- links-rewrite, no-paths
MACHINE_PATH = re.compile(r"""(?:^|(?<=[\s"'`(\[=,:;<>]))/(?:data[0-9]*|home|root|tmp|local|mnt|var)(?=/|[\s"'`)\],;:]|$)""")


def is_machine_path(v: str) -> bool:
    return bool(MACHINE_PATH.match(v))


def key_names(v):
    if isinstance(v, dict):
        for k, x in v.items():
            yield k
            yield from key_names(x)
    elif isinstance(v, list):
        for x in v:
            yield from key_names(x)


def cmd_links_rewrite(a) -> int:
    src = json.loads(Path(a.src).read_text())
    changes = []

    def walk(v, ptr):
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                nk = spell(k)                     # release 2: the key names have the American spelling
                if nk != k:
                    changes.append((f"{ptr}/{k}", f"key {k}", f"key {nk}"))
                if nk in out or (nk != k and nk in v):
                    problems.append(f"the key {ptr}/{nk} is there twice after the spelling change")
                out[nk] = walk(x, f"{ptr}/{k}")
            return out
        if isinstance(v, list):
            return [walk(x, f"{ptr}/{i}") for i, x in enumerate(v)]
        if isinstance(v, str) and is_machine_path(v):
            new = os.path.basename(v.rstrip("/"))
            changes.append((ptr, v, new))
            return new
        return v

    problems = []
    out = walk(src, "")
    for k in ("mapping_sha256", "outputs", "total_tokens", "projects"):
        if out.get(k) != src.get(k):
            problems.append(f"the key {k} changed")
    if out.get(FOOTER_OV) != links_ov(src):
        problems.append(f"the key {FOOTER_OV} changed")
    if any(OLD_SPELLING.search(k) for k in key_names(out)):
        problems.append("a key of the output still has the old spelling organis")
    text = json.dumps(out, indent=1) + "\n"
    if AT in text:
        problems.append("the output holds the at sign")
    if any(MACHINE_PATH.search(line) for line in text.splitlines()):
        problems.append("the output still holds a machine path")
    if problems:
        return report(problems, "")
    Path(a.out).write_text(text)
    with open(a.report, "w") as fh:
        fh.write("key\tbefore\tafter\n")
        for c in changes:
            fh.write("\t".join(c) + "\n")
    keys = sum(1 for c in changes if c[1].startswith("key "))
    print(f"links-rewrite: {len(changes) - keys} machine paths cut to the base name; {keys} key names with the "
          f"spelling organiz; mapping {out['mapping_sha256'][:12]} and the {len(out.get('outputs', {}))} output "
          f"hashes unchanged")
    return 0


def text_files(a) -> list[Path]:
    if a.root:
        root = Path(a.root)
        return [p for p in sorted(root.rglob("*")) if p.is_file() and p.suffix not in BINARY_SUFFIXES]
    return [Path(f) for f in a.files if Path(f).suffix not in BINARY_SUFFIXES]


def parquet_path_hits(f: Path) -> int:
    """The rows of a Parquet file with an absolute machine path in a column (each column as text)."""
    con = connect()
    n = 0
    cur = con.execute("SELECT CAST(COLUMNS(*) AS VARCHAR) FROM read_parquet(?)", [str(f)])
    while True:
        batch = cur.fetchmany(20000)
        if not batch:
            break
        n += sum(1 for t in batch if any(v is not None and MACHINE_PATH.search(v) for v in t))
    return n


def cmd_no_paths(a) -> int:
    bad, n = 0, 0
    if a.root:
        pqs = sorted(p for p in Path(a.root).glob("*.parquet") if p.is_file())
    else:
        pqs = [Path(f) for f in a.files if Path(f).suffix == ".parquet"]
    for f in pqs:
        n += 1
        hits = parquet_path_hits(f)
        if hits:
            bad += 1
            print(f"MACHINE PATH: {f.name}: {hits} rows")
    for f in text_files(a):
        n += 1
        hits = [i for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1) if MACHINE_PATH.search(line)]
        if hits:
            bad += 1
            print(f"MACHINE PATH: {f.name}: lines {', '.join(map(str, hits[:10]))}{' ...' if len(hits) > 10 else ''}")
    print(f"no-paths: {n} files checked ({len(pqs)} Parquet); {bad} with an absolute machine path")
    return 1 if bad else 0


# ---------------------------------------------------------------- split-plan
def round_up(n: int, k: int) -> int:
    return -(-n // k) * k


def tar_bytes(members: list[tuple[str, int]]) -> int:
    """An upper bound of the size of an uncompressed tar of these members (pax or GNU format): one header
    block and the data in whole blocks for each member, two more blocks for a long name, the end blocks."""
    n = sum(TAR_BLOCK + round_up(size, TAR_BLOCK) + 2 * TAR_BLOCK for _, size in members) + 2 * TAR_BLOCK
    return round_up(n, TAR_RECORD)


def pack_archives(files: list[tuple[str, int, str]], limit: int) -> list[list[tuple[str, int, str]]]:
    out, cur, cur_b = [], [], 0
    for f in files:
        if cur and tar_bytes([(x[0], x[1]) for x in cur] + [(f[0], f[1])]) > limit:
            out.append(cur)
            cur, cur_b = [], 0
        cur.append(f)
        cur_b += f[1]
    if cur:
        out.append(cur)
    return out


def cmd_split_plan(a) -> int:
    root = Path(a.root)
    sums = {r: d for d, r in read_sums(root / "SHA256SUMS")}
    allf = [(r, (root / r).stat().st_size, d) for r, d in sorted(sums.items())]
    allf.append(("SHA256SUMS", (root / "SHA256SUMS").stat().st_size, sha256_file(root / "SHA256SUMS")))
    problems = []
    big = [f for f in allf if f[1] > a.limit]
    if big:
        problems.append(f"{len(big)} files larger than the limit, first {big[0][0]}")
    top = sorted(f for f in allf if "/" not in f[0])
    meta = sorted(f for f in allf if "/" in f[0] and not f[0].startswith("parquet/"))
    proj = sorted(f for f in allf if f[0].startswith("parquet/"))
    rest = sorted(set(allf) - set(top) - set(meta) - set(proj))
    if rest:
        problems.append(f"{len(rest)} files of no class")
    if problems:
        return report(problems, "")
    meta_tar = tar_bytes([(x[0], x[1]) for x in meta]) if meta else 0
    rec1_fixed = sum(f[1] for f in top) + meta_tar
    rec1_files = len(top) + (1 if meta else 0)
    total = rec1_fixed + sum(round_up(f[1], TAR_BLOCK) + 3 * TAR_BLOCK for f in proj)
    n = max(1, math.ceil(total / a.limit))
    while True:
        target = total / n
        groups: list[list] = [[] for _ in range(n)]
        cum = rec1_fixed
        for f in proj:
            w = round_up(f[1], TAR_BLOCK) + 3 * TAR_BLOCK
            k = min(n - 1, int((cum + w / 2) // target))
            groups[k].append(f)
            cum += w
        recs, fits = [], True
        for k, g in enumerate(groups):
            arch = pack_archives(g, a.archive_max)
            payload = sum(tar_bytes([(x[0], x[1]) for x in ar]) for ar in arch)
            zfiles = len(arch) + 1 + (rec1_files if k == 0 else 0)
            upload = payload + (rec1_fixed if k == 0 else 0)
            recs.append((g, arch, upload, zfiles))
            if upload > a.limit or zfiles > a.max_files:
                fits = False
        if fits:
            break
        n += 1
        if n > len(proj) + 1:
            return report(["no plan fits the limits"], "")
    out = Path(a.out_dir)
    (out / "records").mkdir(parents=True, exist_ok=True)
    width = max(2, len(str(n)))
    plan_rows, rec_rows = [], []
    for k, (g, arch, upload, zfiles) in enumerate(recs, 1):
        rid = f"{k:0{width}d}"
        rows = []
        if k == 1:
            rows += [(f[0], f[0], f[1], f[2]) for f in top]
            rows += [("release-meta.tar", f[0], f[1], f[2]) for f in meta]
        for j, ar in enumerate(arch, 1):
            name = f"parquet-r{rid}-a{j:02d}.tar"
            rows += [(name, f[0], f[1], f[2]) for f in ar]
        with open(out / "records" / f"record-{rid}.tsv", "w") as fh:
            fh.write("zenodo_file\tpath\tbytes\tsha256\n")
            for r in rows:
                fh.write("\t".join(str(x) for x in r) + "\n")
        plan_rows += [(rid,) + r for r in rows]
        names = [project_of(f[0]) for f in g]
        rec_rows.append((rid, zfiles, len(arch) + (1 if k == 1 and meta else 0), len(rows), len(g),
                         sum(r[2] for r in rows), upload, names[0] if names else "", names[-1] if names else ""))
    with open(out / "zenodo-plan.tsv", "w") as fh:
        fh.write("record\tzenodo_file\tpath\tbytes\tsha256\n")
        for r in plan_rows:
            fh.write("\t".join(str(x) for x in r) + "\n")
    with open(out / "zenodo-records.tsv", "w") as fh:
        fh.write("record\tzenodo_files\tarchives\trelease_files\tproject_files\tpayload_bytes\tupload_bytes_max"
                 "\tfirst_project\tlast_project\n")
        for r in rec_rows:
            fh.write("\t".join(str(x) for x in r) + "\n")
    placed = [r[2] for r in plan_rows]
    if sorted(placed) != sorted(f[0] for f in allf) or len(set(placed)) != len(placed):
        return report(["the plan does not hold each file of R once"], "")
    big_rec = max(r[6] for r in rec_rows)
    print(f"split-plan: {len(allf)} files, {sum(f[1] for f in allf)} bytes -> {n} records under one concept DOI; "
          f"the largest record {big_rec} bytes (limit {a.limit}); at most {max(r[1] for r in rec_rows)} Zenodo files "
          f"per record (limit {a.max_files}); record 1 holds {len(top)} top-level files and release-meta.tar "
          f"({len(meta)} files)")
    return 0


# ---------------------------------------------------------------- main
# ---------------------------------------------------------------- reencode-chain, reencode-root
REENCODE_SAME = ("organizations/", "ledgers.parquet", "links.json", "pseudonymization.json", "tools/")


def reencode_log(path: Path) -> dict:
    """The last line of each file of the re-encode log."""
    last = {}
    for line in Path(path).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            last[r["file"]] = r
    return last


def reencode_fingerprint(con, path: Path) -> dict:
    """The content hash of reencode.py (and of bench.py of the measurement): the same SQL."""
    p = "'" + str(path).replace("'", "''") + "'"
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({p})").fetchall()]
    q = ", ".join(f'"{c}"' for c in cols)
    per_col = ", ".join(f'sum(hash("{c}")::HUGEINT)::VARCHAR' for c in cols)
    r = con.execute(f"SELECT count(*), sum(h::HUGEINT)::VARCHAR, sum(hash(file_row_number, h)::HUGEINT)::VARCHAR, "
                    f"{per_col} FROM (SELECT file_row_number, hash({q}) AS h, * FROM read_parquet({p}, "
                    f"file_row_number=true))").fetchone()
    return {"rows": int(r[0]), "rowhash": r[1], "orderhash": r[2], "colhash": list(r[3:])}


def cmd_reencode_chain(a) -> int:
    import duckdb
    problems: list[str] = []
    pub = Path(a.published)
    if not pin_ok(sha256_file(pub), a.published_sha):
        problems.append(f"the published SHA256SUMS is not {a.published_sha[:12]}")
    pub_rows = dict((r, h) for h, r in read_sums(pub))
    pub_proj = {project_of(r): h for r, h in pub_rows.items() if project_of(r)}
    pub_org = {r: h for r, h in pub_rows.items() if r.startswith(f"{ORG_DIR}/")}
    d = Path(a.input)
    if not (d / "SHA256SUMS").is_file():
        problems.append("the input has no SHA256SUMS (the re-encode input needs it)")
        return report(problems, "")
    in_rows = dict((r, h) for h, r in read_sums(d / "SHA256SUMS"))
    in_proj = {project_of(r): h for r, h in in_rows.items() if project_of(r)}
    in_org = {r: h for r, h in in_rows.items() if r.startswith(f"{ORG_DIR}/")}
    if set(in_proj) != set(pub_proj):
        problems.append(f"{len(set(in_proj) ^ set(pub_proj))} project names of the input are not the published names")
    if in_org != pub_org:
        diff = sorted(set(in_org.items()) ^ set(pub_org.items()))
        problems.append(f"organizations/ of the input is not the published organizations/ ({len(diff)} rows differ, "
                        f"first {diff[0][0] if diff else '?'})")
    log = reencode_log(Path(a.log))
    extra = sorted(set(n[: -len("-dataset.parquet")] for n in log) - set(pub_proj))
    if extra:
        problems.append(f"{len(extra)} files of the log are not published project files, first {extra[0]}")
    con = duckdb.connect()
    versions, settings, n_ok, b_in, b_out = set(), set(), 0, 0, 0
    scripts: dict = {}           # reencode_sha256 -> file count (more than one: the retry of a file with a new kit)
    batches: dict = {}           # read_batch -> file count (a line of the first kit version has none: 262144)
    odd_batch: list = []
    kit = set(a.kit_sha or [])
    rows_total = 0
    for p in sorted(pub_proj):
        name = f"{p}-dataset.parquet"
        r = log.get(name)
        if r is None:
            problems.append(f"{p}: no line in the re-encode log")
            continue
        why = []
        if r.get("status") != "OK":
            why.append(f"status {r.get('status')}")
        bad = sorted(k for k, v in (r.get("checks") or {}).items() if v is not True)
        if bad or not r.get("checks"):
            why.append(f"checks not true: {', '.join(bad) or 'none logged'}")
        v = r.get("versions") or {}
        versions.add((v.get("pyarrow"), v.get("duckdb")))
        scripts[v.get("reencode_sha256")] = scripts.get(v.get("reencode_sha256"), 0) + 1
        rb = r.get("read_batch", 262_144)
        batches[str(rb)] = batches.get(str(rb), 0) + 1
        if rb != 262_144:
            odd_batch.append(f"{p}={rb}")
        if kit and v.get("reencode_sha256") not in kit:
            why.append(f"reencode.py {str(v.get('reencode_sha256'))[:12]} is not a kit version of the stage")
        if v.get("pyarrow") != a.pyarrow or v.get("duckdb") != a.duckdb:
            why.append(f"pyarrow {v.get('pyarrow')} duckdb {v.get('duckdb')}")
        settings.add(r.get("settings_sha256"))
        if r.get("settings_sha256") != a.settings_sha:
            why.append(f"settings {str(r.get('settings_sha256'))[:12]}")
        if r.get("in_sha256") != pub_proj[p] or r.get("want_sha256") not in ("", pub_proj[p]):
            why.append("the input sha256 of the log is not the published sha256")
        if r.get("out_sha256") != in_proj.get(p):
            why.append("the output sha256 of the log is not the row of the input SHA256SUMS")
        f = d / "parquet" / name
        if not f.is_file() or f.stat().st_size != r.get("out_bytes"):
            why.append("the size of the input file is not the output size of the log")
        else:
            nr = con.execute("SELECT num_rows FROM parquet_file_metadata(?)", [str(f)]).fetchone()[0]
            rows_total += int(nr or 0)
            if int(nr or 0) != r.get("rows"):
                why.append(f"{nr} rows in the footer, {r.get('rows')} in the log")
        if why:
            problems.append(f"{p}: {'; '.join(why)}")
        else:
            n_ok += 1
            b_in += r["in_bytes"]
            b_out += r["out_bytes"]
    if len(versions) != 1:
        problems.append(f"{len(versions)} sets of tool versions (pyarrow, duckdb) in the log (one is expected)")
    if not kit and len(scripts) > 1:
        problems.append(f"{len(scripts)} reencode.py versions in the log and no --kit-sha list (one is expected)")
    pick = sorted(pub_proj, key=lambda p: hashlib.sha256(p.encode()).hexdigest())[: max(0, a.recheck)]
    local = threading.local()

    def recheck(p):
        c = getattr(local, "con", None)
        if c is None:
            c = local.con = duckdb.connect()
            c.execute("SET threads=2")
        r = log.get(f"{p}-dataset.parquet") or {}
        fp = reencode_fingerprint(c, d / "parquet" / f"{p}-dataset.parquet")
        want = dict(r.get("fingerprint") or {}, rows=r.get("rows"))
        return p, fp == want

    rechecked = []
    if pick and not problems:
        with ThreadPoolExecutor(max_workers=max(1, a.jobs // 2)) as ex:
            rechecked = list(ex.map(recheck, pick))
        for p, ok in rechecked:
            if not ok:
                problems.append(f"{p}: the content hash of the input file is not the hash of the log")
    rep = {"published_sha256": sha256_file(pub), "projects": len(pub_proj), "chain_ok": n_ok, "in_bytes": b_in,
           "out_bytes": b_out, "rows": rows_total, "organizations_rows": len(in_org),
           "versions": sorted(list(x) for x in versions), "settings_sha256": sorted(str(x) for x in settings),
           "reencode_sha256": dict(sorted((str(k), n) for k, n in scripts.items())), "kit_sha256": sorted(kit),
           "read_batch": dict(sorted(batches.items())), "read_batch_not_default": sorted(odd_batch),
           "rechecked": [p for p, _ in rechecked], "problems": problems}
    Path(a.out).write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    v = next(iter(versions)) if len(versions) == 1 else ("?", "?")
    return report(problems, f"reencode-chain: {n_ok} project files: published SHA256SUMS {sha256_file(pub)[:12]} -> "
                            f"re-encode log (OK, all checks; pyarrow {v[0]}, duckdb {v[1]}, settings "
                            f"{a.settings_sha[:12]}; reencode.py "
                            f"{', '.join(f'{str(k)[:12]} {n} files' for k, n in sorted(scripts.items(), key=lambda x: -x[1]))}; "
                            f"read batch {', '.join(f'{k} {n} files' for k, n in sorted(batches.items()))}) -> input "
                            f"SHA256SUMS; {b_in} B -> {b_out} B; {rows_total} rows; "
                            f"{ORG_DIR}/ {len(in_org)} files byte-identical; content hash again for "
                            f"{len(rechecked)} files: the hash of the log")


def cmd_reencode_root(a) -> int:
    problems: list[str] = []
    root = Path(a.root)
    pub = Path(a.published)
    if not pin_ok(sha256_file(pub), a.published_sha):
        problems.append(f"the published SHA256SUMS is not {a.published_sha[:12]}")
    old = dict((r, h) for h, r in read_sums(pub))
    new = dict((r, h) for h, r in read_sums(root / "SHA256SUMS"))
    log = reencode_log(Path(a.log))
    rows = []
    for r in sorted(set(old) | set(new)):
        if r not in new:
            problems.append(f"{r}: published, not in R")
            continue
        if r not in old:
            problems.append(f"{r}: in R, not published")
            continue
        p = project_of(r)
        if p:
            lr = log.get(f"{p}-dataset.parquet") or {}
            if new[r] != lr.get("out_sha256") or old[r] != lr.get("in_sha256"):
                problems.append(f"{p}: the rows of SHA256SUMS are not the sha256 values of the log")
            continue
        state = "same" if old[r] == new[r] else "changed"
        if state == "changed" and r.startswith(REENCODE_SAME):
            problems.append(f"{r}: changed (it must be byte-identical)")
        rows.append((r, state))
    man = Path(a.published_manifest)
    if old.get("MANIFEST.tsv") != sha256_file(man):
        problems.append("the published MANIFEST.tsv given is not the published one (sha256)")
    o_lines = man.read_text().splitlines()
    n_lines = (root / "MANIFEST.tsv").read_text().splitlines()
    hdr = o_lines[0].split("\t")
    changed_cols = {"bytes", "sha256"}
    if n_lines[0] != o_lines[0] or len(n_lines) != len(o_lines):
        problems.append(f"MANIFEST.tsv: another header or another row count ({len(n_lines) - 1}, published "
                        f"{len(o_lines) - 1})")
    else:
        ib, isha = hdr.index("bytes"), hdr.index("sha256")
        for ol, nl in zip(o_lines[1:], n_lines[1:]):
            o, n = ol.split("\t"), nl.split("\t")
            other = [h for h, x, y in zip(hdr, o, n) if x != y and h not in changed_cols]
            lr = log.get(f"{o[0]}-dataset.parquet") or {}
            if other:
                problems.append(f"MANIFEST.tsv {o[0]}: the column {other[0]} changed")
            if (str(lr.get("in_bytes")), lr.get("in_sha256")) != (o[ib], o[isha]) or \
                    (str(lr.get("out_bytes")), lr.get("out_sha256")) != (n[ib], n[isha]):
                problems.append(f"MANIFEST.tsv {o[0]}: bytes and sha256 are not the values of the log")
    with open(a.out, "w") as fh:
        fh.write("path\tstate\n")
        for r, st in rows:
            fh.write(f"{r}\t{st}\n")
    ch = [r for r, st in rows if st == "changed"]
    return report(problems, f"reencode-root: {sum(1 for r in new if project_of(r))} project rows of R/SHA256SUMS = the "
                            f"output sha256 of the log; {len(rows) - len(ch)} other files byte-identical to the "
                            f"published root, {len(ch)} changed ({', '.join(ch)}); MANIFEST.tsv: only bytes and "
                            f"sha256 changed, to the values of the log")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("s3-list-check"); s.add_argument("--listing", required=True); s.add_argument("--prefix", required=True)
    s.add_argument("--expect", type=int, required=True); s.add_argument("--input", action="store_true")
    s = sub.add_parser("verify-source"); s.add_argument("--dir", required=True); s.add_argument("--label", required=True)
    s.add_argument("--expect", type=int, required=True); s.add_argument("--expect-rows", type=int)
    s.add_argument("--jobs", type=int, default=os.cpu_count() or 1); s.add_argument("--out", required=True)
    s.add_argument("--no-project-files", action="store_true")
    s = sub.add_parser("verify-input"); s.add_argument("--dir", required=True); s.add_argument("--a", required=True)
    s.add_argument("--b", required=True); s.add_argument("--expect", type=int, required=True)
    s.add_argument("--jobs", type=int, default=os.cpu_count() or 1); s.add_argument("--out", required=True)
    s = sub.add_parser("links-check"); s.add_argument("--a", required=True); s.add_argument("--b", required=True)
    s.add_argument("--mapping", required=True); s.add_argument("--ov")
    s = sub.add_parser("assemble"); s.add_argument("--a", required=True); s.add_argument("--b", required=True)
    s.add_argument("--docs", required=True); s.add_argument("--root", required=True)
    s.add_argument("--expect", type=int, required=True); s.add_argument("--names-out", required=True)
    s.add_argument("--input")
    s = sub.add_parser("layers"); s.add_argument("--results-a", required=True); s.add_argument("--results-b", required=True)
    s.add_argument("--b-layer", default="v1"); s.add_argument("--prefixes", default="v1=v1 pf17=v1 x1k=x1k")
    s.add_argument("--expect-v1", type=int, required=True); s.add_argument("--expect-x1k", type=int, required=True)
    s.add_argument("--out", required=True)
    s = sub.add_parser("pseudo-merge"); s.add_argument("--a", required=True); s.add_argument("--b", required=True)
    s.add_argument("--a-files", type=int, required=True); s.add_argument("--b-projects", nargs="+", required=True)
    s.add_argument("--want-a", required=True); s.add_argument("--want-b", required=True); s.add_argument("--out", required=True)
    s = sub.add_parser("schema"); s.add_argument("--root", required=True); s.add_argument("--fill-release", required=True)
    s.add_argument("--pseudonymization", required=True); s.add_argument("--mapping", required=True)
    s.add_argument("--ov", required=True); s.add_argument("--expect", type=int, required=True)
    s.add_argument("--expect-rows", type=int); s.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    s.add_argument("--out", required=True)
    s = sub.add_parser("ledger-pick"); s.add_argument("--ledgers", required=True); s.add_argument("--schema", required=True)
    s.add_argument("--out", required=True); s.add_argument("--report", required=True)
    s = sub.add_parser("ledger-merge"); s.add_argument("--proven", required=True); s.add_argument("--picked", required=True)
    s.add_argument("--schema", required=True); s.add_argument("--out", required=True)
    s = sub.add_parser("ledger-clean"); s.add_argument("--records", required=True)
    s.add_argument("--ledgers", nargs="+", required=True); s.add_argument("--out", required=True)
    s.add_argument("--report", required=True); s.add_argument("--deny", nargs="*")
    s = sub.add_parser("ledger-clean-check"); s.add_argument("--file", required=True); s.add_argument("--records", required=True)
    s.add_argument("--schema"); s.add_argument("--targets", nargs="*"); s.add_argument("--deny", nargs="*")
    s = sub.add_parser("check-classes"); s.add_argument("--check-out", required=True)
    s = sub.add_parser("sums-compare"); s.add_argument("--root", required=True); s.add_argument("--a", required=True)
    s.add_argument("--b", required=True); s.add_argument("--input")
    s = sub.add_parser("guard"); s.add_argument("--root", required=True); s.add_argument("--names", required=True)
    s = sub.add_parser("no-at"); s.add_argument("--root"); s.add_argument("files", nargs="*")
    s = sub.add_parser("links-rewrite"); s.add_argument("--src", required=True); s.add_argument("--out", required=True)
    s.add_argument("--report", required=True)
    s = sub.add_parser("no-paths"); s.add_argument("--root"); s.add_argument("files", nargs="*")
    s = sub.add_parser("split-plan"); s.add_argument("--root", required=True); s.add_argument("--limit", type=int, required=True)
    s.add_argument("--max-files", type=int, required=True); s.add_argument("--archive-max", type=int, required=True)
    s.add_argument("--out-dir", required=True)
    s = sub.add_parser("reencode-chain"); s.add_argument("--log", required=True); s.add_argument("--published", required=True)
    s.add_argument("--published-sha", required=True); s.add_argument("--input", required=True)
    s.add_argument("--settings-sha", required=True); s.add_argument("--pyarrow", default="26.0.1")
    s.add_argument("--duckdb", default="1.5.5"); s.add_argument("--recheck", type=int, default=0)
    s.add_argument("--jobs", type=int, default=4); s.add_argument("--out", required=True)
    s.add_argument("--kit-sha", action="append", default=[])
    s = sub.add_parser("reencode-root"); s.add_argument("--root", required=True); s.add_argument("--published", required=True)
    s.add_argument("--published-sha", required=True); s.add_argument("--published-manifest", required=True)
    s.add_argument("--log", required=True); s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd in ("no-at", "no-paths") and not a.root and not a.files:
        print(f"{a.cmd}: give --root or files", file=sys.stderr)
        return 2
    return {"s3-list-check": cmd_s3_list_check, "verify-source": cmd_verify_source, "verify-input": cmd_verify_input,
            "links-check": cmd_links_check,
            "assemble": cmd_assemble, "layers": cmd_layers, "pseudo-merge": cmd_pseudo_merge, "schema": cmd_schema,
            "ledger-pick": cmd_ledger_pick, "ledger-merge": cmd_ledger_merge,
            "ledger-clean": cmd_ledger_clean, "ledger-clean-check": cmd_ledger_clean_check, "check-classes": cmd_check_classes, "sums-compare": cmd_sums_compare,
            "guard": cmd_guard, "no-at": cmd_no_at, "links-rewrite": cmd_links_rewrite, "no-paths": cmd_no_paths,
            "split-plan": cmd_split_plan, "reencode-chain": cmd_reencode_chain, "reencode-root": cmd_reencode_root}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
