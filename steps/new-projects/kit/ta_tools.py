#!/usr/bin/env python3
"""The helper of the kit tom-add-159-kit (the machine; the venv Python with DuckDB).

    ta_tools.py inputs   --meta-dir M --group G.txt --gate-tom F --gate-row ROW.tsv --out-dir IN
    ta_tools.py counts   --in-dir IN --work W --jobs N
    ta_tools.py fill     --in-dir IN --lsc-out DIR --rule tom|scancode
    ta_tools.py merge-links --tom-dir L --new-dir N --cache DIR --out-dir OUT
    ta_tools.py judge-gate  REPORT.json
    ta_tools.py judge-pass  REPORT.json
    ta_tools.py shape    --ref TOM.parquet FILE [FILE ...]
    ta_tools.py manifest --in-dir IN --files DIR --names N.txt --cregit C --ctp C --out MANIFEST.new.tsv
    ta_tools.py tables   --in-dir IN --meta-dir M --links OUT --names N.txt --out-dir DIR

inputs   the run inputs of one machine: manifest.tsv (the rows of the group, then the gate row), project_meta.json
         (the sidecar entries of meta/project_meta.json, and the 16 project columns of the gate TOM file), fill.tsv
         (the rows of the group), lsc.tsv (the list of license_scan.py: project, clone_url, run_commit, fetch_urls).
precheck a depth-1 fetch of each pin: the bytes of the universal mask, the share in vendor-like folders and with
         generated-like names, the largest files and folders (results/precheck.jsonl and .tsv). No blame, no tokenizer.
write    the published file of each project from its private pass 1 file: the 4 organization columns out, then
         schema3.py write of ctp with the merged link tables and the salt (the generator does not run again).
thin     the input of extract_domains_v1.py for a schema 3 file (person_email = author_email; see cmd_thin).
counts   for each fill row `commits=rev-list-count`: a blobless bare clone at the pin, then git rev-list --count.
         Writes IN/counts.tsv (project, commits, status).
fill     puts the machine values into manifest.tsv and project_meta.json (the old files stay as *.before):
         commits (counts.tsv), size_class (the TOM rule, see size_class()), license (LICENSE_RULE: tom = licensee at
         confidence 98 for the fill rows; scancode = the ScanCode decision of license_scan.py for every row).
         Writes IN/fill.done.tsv (project, key, value, source). A value that cannot be filled stops it.
merge-links  the link tables of the write of pass 2: the TOM tables plus the rows of build_links.py for the new
         projects. A domain or project that is in both must have the same values (else exit 1). Writes OUT/
         domain_links.parquet, OUT/project_links.parquet, OUT/report.json (new domain rows by kind, their tokens,
         the tokens of the real domains with no row: these get the fallback `independent`), and
         OUT/organization_domains.new.parquet (the new rows that are not `independent`: the published form).
judge-gate  the compare_tom.py report of the gate against its TOM file: every column equal, the footer equal except
         pseudonymization_registry_sha256. Exit 1 else.
judge-pass  the compare_tom.py report of pass 2 (the published file) against pass 1 (the private file of the same
         run): the columns that the write copies must be equal row for row; each identity column must be a
         function of the private value (one real value gives one pseudonym); the 4 organization columns may differ
         (other link tables) and are counted. Exit 1 else.
shape    each FILE must have the column names and types of the TOM file REF, in order, and its footer keys.
manifest the rows of MANIFEST.tsv (the TOM 1.0.0 layout) for the files of the names.
tables   the side-table rows of the new projects: project_organizations (host and namespace of meta, the 4 columns
         of the merged project links), project_facts (schema3.py facts of ctp, run before), project_labels and
         project_languages (meta, as they are).
Prints counts and hashes only, never an identity value.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

META16 = ("clone_url", "audit_frame_file", "source", "stratum", "contested", "label_date", "owner", "repo",
          "roster_name", "language", "commits", "size_class", "stars", "pushed_at", "license", "owner_type")
IDENTITY = {"author_name", "author_email", "committer_name", "committer_email", "personid", "person_domain",
            "footer_personids"}
ORG = {"firm_based_on_namespace", "firm_based_on_domain", "project_enterprise_driven", "project_enterprise_basis"}
REAL_BAD = {"NOASSERTION", "NONE", "other", "", None}


def sha256(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_tsv(p) -> list[dict]:
    with open(p, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_tsv(p, rows: list[dict], cols: list[str]) -> None:
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def manifest_rows(p) -> list[list[str]]:
    return [line.rstrip("\n").split("\t") for line in open(p) if line.strip() and not line.startswith("#")]


def write_manifest(p, rows) -> None:
    with open(p, "w") as f:
        for r in rows:
            f.write("\t".join(r) + "\n")


# --- size class: the TOM rule (the rule of meta/fill.tsv; S1 checks that meta names only these rules)
def size_class(rule: str, commits: int) -> str:
    if rule.split("=", 1)[-1] == "tom-commits-30k-150k":  # s4-filter/funnel.py:68-69, the rule of TOM
        return "S" if commits < 30000 else ("M" if commits <= 150000 else "L")
    raise SystemExit(f"size_class: unknown rule {rule!r}")


def cmd_inputs(a) -> int:
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    group = [n.strip() for n in open(a.group) if n.strip() and not n.startswith("#")]
    rows = {r[0]: r for r in manifest_rows(Path(a.meta_dir) / "manifest.tsv")}
    meta = json.loads((Path(a.meta_dir) / "project_meta.json").read_text())
    missing = [n for n in group if n not in rows or n not in meta]
    if missing:
        sys.exit(f"inputs: {len(missing)} names of the group have no manifest row or sidecar entry: {missing[:5]}")
    gate = manifest_rows(a.gate_row)
    if len(gate) != 1 or len(gate[0]) != 6:
        sys.exit("inputs: the gate row must be one manifest row of 6 fields")
    g = gate[0][0]
    con = duckdb.connect()
    vals = con.execute(f"SELECT {', '.join(META16)} FROM read_parquet(?) LIMIT 1", [a.gate_tom]).fetchone()
    side = {n: meta[n] for n in group}
    side[g] = {k: ("" if v is None else str(v)) for k, v in zip(META16, vals)}
    write_manifest(out / "manifest.tsv", [rows[n] for n in group] + gate)
    (out / "project_meta.json").write_text(json.dumps(side, indent=1, sort_keys=True) + "\n")
    fills = [r for r in read_tsv(Path(a.meta_dir) / "fill.tsv") if r["project"] in set(group)]
    write_tsv(out / "fill.tsv", fills, ["project", "key", "rule"])
    lsc = [{"project": n, "clone_url": rows[n][1], "run_commit": rows[n][5],
            "fetch_urls": meta[n].get("fetch_urls", "")} for n in group]
    write_tsv(out / "lsc.tsv", lsc, ["project", "clone_url", "run_commit", "fetch_urls"])
    print(f"inputs: {len(group)} projects + gate {g}; {len(fills)} fill rows; manifest "
          f"{sha256(out / 'manifest.tsv')[:12]}, sidecar {sha256(out / 'project_meta.json')[:12]}")
    return 0


def _count(job) -> dict:
    name, url, pin, work, git = job
    d = Path(work) / f"{name}.git"
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        if not d.exists():
            subprocess.run([git, "init", "-q", "--bare", str(d)], check=True, env=env)
            subprocess.run([git, "-C", str(d), "remote", "add", "origin", url], check=True, env=env)
        subprocess.run([git, "-C", str(d), "-c", "credential.helper=", "fetch", "-q", "--filter=blob:none",
                        "origin", pin], check=True, env=env, timeout=3600)
        n = subprocess.run([git, "-C", str(d), "rev-list", "--count", pin], check=True, env=env,
                           capture_output=True, text=True).stdout.strip()
        return {"project": name, "commits": n, "status": "ok"}
    except Exception as e:  # noqa: BLE001 - one row must not stop the others
        return {"project": name, "commits": "", "status": f"error {type(e).__name__}"}


def cmd_counts(a) -> int:
    inp = Path(a.in_dir)
    rows = {r[0]: r for r in manifest_rows(inp / "manifest.tsv")}
    want = [r["project"] for r in read_tsv(inp / "fill.tsv") if r["key"] == "commits"]
    Path(a.work).mkdir(parents=True, exist_ok=True)
    jobs = [(n, rows[n][1], rows[n][5], a.work, a.git) for n in want]
    with ThreadPoolExecutor(a.jobs) as pool:
        res = list(pool.map(_count, jobs))
    write_tsv(inp / "counts.tsv", res, ["project", "commits", "status"])
    bad = [r["project"] for r in res if r["status"] != "ok"]
    print(f"counts: {len(res) - len(bad)} of {len(res)} ok{'; failed: ' + ' '.join(bad) if bad else ''}")
    return 1 if bad else 0


def licensee98(proj_dir: Path) -> str | None:
    """The TOM rule of release pass 2: the real ids that licensee names at its default confidence 98
    (license_scan.py stores them in second.json), sorted and ';'-joined; None when there is none."""
    f = proj_dir / "second.json"
    if not f.is_file():
        return None
    lic = (json.loads(f.read_text()).get("licensee") or {}).get("licenses") or []
    ids = sorted({i for i in lic if i not in REAL_BAD and not str(i).startswith("LicenseRef")})
    return ";".join(ids) or None


LICENSE_RE = re.compile(r"(?i)^(licen[cs]e|copying|copyright|unlicense|notice|legal|mit-license|"
                        r"gpl|lgpl|apache|bsd|mpl|eula|patents)([-._ ].*)?$")
PACKAGE = {"Cargo.toml", "package.json", "pom.xml", "setup.cfg", "pyproject.toml", "DESCRIPTION", "meson.build"}


def licensee918(proj_dir: Path, licensee: str, work: Path) -> tuple[str | None, str]:
    """The TOM fill rule with the TOM tool (p1_scan_outside_github.py, p1_summarize.py of the release passes):
    licensee 9.18.0 `detect --json --confidence 98` on a folder with the root license files (LICENSE_RE) and the
    package files of the project, here taken from the folder that license_scan.py fetched at the pin
    (stage.tar.gz); the value is the sorted real ids, ';'-joined. Returns (value or None, status)."""
    import shutil
    import tarfile
    arc = proj_dir / "stage.tar.gz"
    if not arc.is_file():
        return None, "no stage.tar.gz"
    d = work / proj_dir.name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    with tarfile.open(arc) as t:
        for m in t.getmembers():
            name = m.name.lstrip("./")
            if m.isfile() and "/" not in name and (LICENSE_RE.match(name) or name in PACKAGE):
                m.name = name
                t.extract(m, d, filter="data")
    if not any(d.iterdir()):
        shutil.rmtree(d, ignore_errors=True)
        return None, "no root license file"
    p = subprocess.run([licensee, "detect", str(d), "--json", "--confidence", "98"], capture_output=True,
                       text=True, errors="replace", timeout=300)
    shutil.rmtree(d, ignore_errors=True)
    try:
        out = json.loads(p.stdout)
    except json.JSONDecodeError:
        return None, f"licensee rc={p.returncode}"
    ids = sorted({x.get("spdx_id") for x in out.get("licenses") or []
                  if x.get("spdx_id") not in REAL_BAD and not str(x.get("spdx_id")).startswith("LicenseRef")})
    return (";".join(ids) or None), "ok"


def cmd_fill(a) -> int:
    inp = Path(a.in_dir)
    man = manifest_rows(inp / "manifest.tsv")
    meta = json.loads((inp / "project_meta.json").read_text())
    counts = {r["project"]: r for r in read_tsv(inp / "counts.tsv")} if (inp / "counts.tsv").is_file() else {}
    lsc = {r["project"]: r for r in read_tsv(Path(a.lsc_out) / "results.tsv")}
    fills = read_tsv(inp / "fill.tsv")
    done, bad = [], []
    for r in fills:
        p, key, rule = r["project"], r["key"], r["rule"]
        if key == "commits":
            c = counts.get(p, {})
            if c.get("status") != "ok":
                bad.append(f"{p} commits"); continue
            meta[p]["commits"] = c["commits"]; done.append({"project": p, "key": key, "value": c["commits"],
                                                             "source": "git rev-list --count of the pin"})
    for r in fills:  # after the commits: the size class can need them
        p, key, rule = r["project"], r["key"], r["rule"]
        if key == "size_class":
            v = size_class(rule, int(meta[p]["commits"] or 0))
            meta[p]["size_class"] = v; done.append({"project": p, "key": key, "value": v, "source": rule})
        elif key == "license" and a.rule == "tom":
            if rule.split("=", 1)[-1] != "licensee98":
                bad.append(f"{p} license: no machine rule {rule!r}"); continue
            st = lsc.get(p, {}).get("status")
            if st != "ok":
                bad.append(f"{p} license (scan status {st})"); continue
            if a.licensee_bin:
                v, why = licensee918(Path(a.lsc_out) / "projects" / p, a.licensee_bin, Path(a.in_dir) / "licensee-work")
                if why not in ("ok", "no root license file"):
                    bad.append(f"{p} license ({why})"); continue
                src = "licensee 9.18.0 at confidence 98 on the root license files (the TOM fill)"
            else:
                v, src = licensee98(Path(a.lsc_out) / "projects" / p), "licensee 10.1.0 at confidence 98 (license_scan.py)"
            v = v or "NOASSERTION"
            meta[p]["license"] = v; done.append({"project": p, "key": key, "value": v, "source": src})
        elif key not in ("commits", "size_class", "license"):
            bad.append(f"{p} {key}: no machine rule {rule!r}")
    if a.rule == "scancode":
        for p in meta:
            if p in lsc and lsc[p].get("status") == "ok":
                meta[p]["license"] = lsc[p]["license"]
                done.append({"project": p, "key": "license", "value": lsc[p]["license"], "source": "scancode"})
    if bad:
        print(f"fill: {len(bad)} values cannot be filled: {bad[:8]}"); return 1
    for r in man:
        if r[0] in meta and meta[r[0]].get("size_class"):
            r[4] = meta[r[0]]["size_class"]
    for f in ("manifest.tsv", "project_meta.json"):
        if not (inp / f"{f}.before").exists():
            os.replace(inp / f, inp / f"{f}.before")
    write_manifest(inp / "manifest.tsv", man)
    (inp / "project_meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True) + "\n")
    write_tsv(inp / "fill.done.tsv", done, ["project", "key", "value", "source"])
    alias = {"audit_frame_file": ("audit_frame_file", "provenance_status")}  # the generator reads either name
    empty = [p for p, m in meta.items() if any(all(m.get(x) is None for x in alias.get(k, (k,))) for k in META16)]
    if empty:
        print(f"fill: sidecar entries without a key of the 16 columns: {empty[:5]}"); return 1
    print(f"fill: {len(done)} values; manifest {sha256(inp / 'manifest.tsv')[:12]}, sidecar "
          f"{sha256(inp / 'project_meta.json')[:12]}")
    return 0


VENDOR_DIRS = re.compile(r"(^|/)(third[_-]?party|3rd[_-]?party|thirdparty|vendor|vendored|external|externals|extern|"
                         r"deps|dependencies|contrib|submodules|libs?/[^/]+-[0-9][^/]*|node_modules|bundled)(/|$)",
                         re.I)
GENERATED = re.compile(r"(^|/)(parser|scanner|lexer|grammar)\.(c|h|cc|cpp)$|(\.pb\.|_pb2|\.g\.|_generated\.|\.gen\.|"
                       r"generated/|/gen/|autogen|amalgamation|sqlite3\.c$|\.min\.)", re.I)


def _precheck(job) -> dict:
    name, url, pin, work, git, mask = job
    d = Path(work) / f"{name}.git"
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    rec = {"project": name, "status": "ok"}
    try:
        if not d.exists():
            subprocess.run([git, "init", "-q", "--bare", str(d)], check=True, env=env)
            subprocess.run([git, "-C", str(d), "remote", "add", "origin", url], check=True, env=env)
        subprocess.run([git, "-C", str(d), "-c", "credential.helper=", "fetch", "-q", "--depth", "1", "origin", pin],
                       check=True, env=env, timeout=3600)
        out = subprocess.run([git, "-C", str(d), "ls-tree", "-r", "-l", "-z", pin], check=True, env=env,
                             capture_output=True).stdout.decode("utf-8", "replace")
        attrs = subprocess.run([git, "-C", str(d), "show", f"{pin}:.gitattributes"], env=env,
                               capture_output=True).stdout.decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return {"project": name, "status": f"error {type(e).__name__}"}
    rx = re.compile(mask)
    files = []
    for ent in out.split("\0"):
        if not ent.strip():
            continue
        meta, _, p = ent.partition("\t")
        parts = meta.split()
        if len(parts) < 4 or parts[1] != "blob" or parts[3] == "-":
            continue
        if rx.search(p):
            files.append((p, int(parts[3])))
    tot = sum(s for _, s in files) or 1
    vend = sum(s for p, s in files if VENDOR_DIRS.search(p))
    gen = sum(s for p, s in files if GENERATED.search(p))
    top: dict[str, int] = {}
    for p, s in files:
        k = "/".join(p.split("/")[:2]) if "/" in p else "(root)"
        top[k] = top.get(k, 0) + s
    big = sorted(files, key=lambda x: -x[1])[:25]
    rec.update({"masked_files": len(files), "masked_bytes": tot, "vendored_dir_bytes": vend,
                "vendored_dir_share": round(vend / tot, 4), "generated_name_bytes": gen,
                "generated_name_share": round(gen / tot, 4), "files_over_1mb": sum(1 for _, s in files if s > 1 << 20),
                "bytes_in_files_over_1mb": sum(s for _, s in files if s > 1 << 20),
                "gitattributes_vendored_or_generated": [l.strip() for l in attrs.splitlines()
                                                        if "linguist-vendored" in l or "linguist-generated" in l][:20],
                "top_dirs": sorted(top.items(), key=lambda x: -x[1])[:15], "largest_files": big})
    subprocess.run(["rm", "-rf", str(d)], check=False)
    return rec


def cmd_precheck(a) -> int:
    """A depth-1 fetch of each pin (no blame, no tokenizer): the size of the files of the universal mask, and how
    much of it is in vendor-like folders or has a generated-like name; the largest files and folders."""
    rows = manifest_rows(a.manifest)
    if a.only:
        keep = set(a.only.split(","))
        rows = [r for r in rows if r[0] in keep]
    Path(a.work).mkdir(parents=True, exist_ok=True)
    jobs = [(r[0], r[1], r[5], a.work, a.git, r[3]) for r in rows]
    with ThreadPoolExecutor(a.jobs) as pool:
        res = list(pool.map(_precheck, jobs))
    with open(a.out, "w") as f:
        for r in res:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    cols = ["project", "status", "masked_files", "masked_bytes", "vendored_dir_share", "generated_name_share",
            "files_over_1mb", "bytes_in_files_over_1mb"]
    write_tsv(a.out.replace(".jsonl", ".tsv"), res, cols)
    print(f"precheck: {sum(r['status'] == 'ok' for r in res)} of {len(res)} ok")
    return 0


def _write_one(job) -> dict:
    n, a = job
    src = Path(a.private) / f"{n}.parquet"
    base = Path(a.work) / f"{n}.base49.parquet"
    dst = Path(a.out_dir) / f"{n}-dataset.parquet"
    t0 = time.time()
    try:
        con = duckdb.connect()
        con.execute(f"SET memory_limit = '{a.memory_limit}'")
        con.execute(f"COPY (SELECT * EXCLUDE ({', '.join(sorted(ORG))}) FROM read_parquet(?)) TO '{base}' "
                    f"(FORMAT PARQUET, COMPRESSION ZSTD)", [str(src)])
        con.close()
        cmd = [sys.executable, "-I", str(Path(a.ctp) / "schema3.py"), "write", str(base), str(dst), "--project", n,
               "--domain-links", str(Path(a.links) / "domain_links.parquet"),
               "--project-links", str(Path(a.links) / "project_links.parquet"),
               "--organizations-version", a.organizations_version, "--memory-limit", a.memory_limit,
               "--threads", str(a.threads)]
        if a.salt_file:
            cmd += ["--pseudonymize", "--salt-file", a.salt_file, "--psl", a.psl, "--registry-dir", a.registry_dir]
        p = subprocess.run(cmd, capture_output=True, text=True)
        out = (p.stdout.strip().splitlines() or [""])[-1]
        rec = {"project": n, "rc": p.returncode, "seconds": round(time.time() - t0, 1), "result": out[:2000],
               "stderr_tail": p.stderr[-600:] if p.returncode else ""}
    except Exception as e:  # noqa: BLE001
        rec = {"project": n, "rc": "error", "seconds": round(time.time() - t0, 1), "result": f"{type(e).__name__}"}
    base.unlink(missing_ok=True)
    return rec


def cmd_write(a) -> int:
    """The write of the published file from the private file of pass 1: the 4 organization columns are left out
    (the rest is the 49 columns of the cregit generator, as the write copies them), then schema3.py write of ctp
    (the same call as the write phase of ctp run) with the merged link tables, the salt, one registry for each
    project. The generator does not run again."""
    names = [x.strip() for x in open(a.names) if x.strip()]
    Path(a.work).mkdir(parents=True, exist_ok=True)
    Path(a.out_dir).mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.jobs) as pool:
        res = list(pool.map(_write_one, [(n, a) for n in names]))
    with open(a.log, "a") as f:
        for r in res:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    bad = [r["project"] for r in res if r["rc"] != 0]
    print(f"write: {len(res) - len(bad)} of {len(res)} ok{'; failed: ' + ' '.join(bad) if bad else ''}")
    return 1 if bad else 0


def cmd_thin(a) -> int:
    """The input of extract_domains_v1.py (the TOM link step) for a schema 3 file: it reads person_email, a
    column that schema 3 leaves out. person_email repeats author_email (validate_schema.py, the note on
    SCHEMA_3_DROPPED_TOKEN_COLUMNS), so the thin file gives it the value of author_email. The rows keep their
    count, so the tokens of the cache are the rows of the file."""
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{a.memory_limit}'")
    rows = []
    for line in open(a.list):
        if not line.strip() or line.startswith("project\t"):
            continue
        p, src = line.rstrip("\n").split("\t")[:2]
        dst = out / f"{p}.thin.parquet"
        con.execute(f"COPY (SELECT person_domain, author_email AS person_email, committer_email, original_commit_sha, "
                    f"author_date FROM read_parquet(?)) TO '{dst}' (FORMAT PARQUET, COMPRESSION ZSTD)", [src])
        n = con.execute("SELECT count(*) FROM read_parquet(?)", [str(dst)]).fetchone()[0]
        rows.append({"project": p, "path": str(dst), "rows": n})
    write_tsv(out / "extract.tsv", rows, ["project", "path", "rows"])
    print(f"thin: {len(rows)} files, {sum(r['rows'] for r in rows):,} rows")
    return 0


def cmd_merge_links(a) -> int:
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    td, tp = str(Path(a.tom_dir) / "domain_links.parquet"), str(Path(a.tom_dir) / "project_links.parquet")
    nd, np_ = str(Path(a.new_dir) / "domain_links.parquet"), str(Path(a.new_dir) / "project_links.parquet")
    dcols = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [td]).fetchall()]
    pcols = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [tp]).fetchall()]
    for f, cols in ((nd, dcols), (np_, pcols)):
        got = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [f]).fetchall()]
        if got != cols:
            sys.exit(f"merge-links: {f} has columns {got}, the TOM table {cols}")
    eqd = " AND ".join(f't."{c}" IS NOT DISTINCT FROM n."{c}"' for c in dcols)
    conflict_d = con.execute(f"SELECT count(*) FROM read_parquet(?) t JOIN read_parquet(?) n USING (domain) "
                             f"WHERE NOT ({eqd})", [td, nd]).fetchone()[0]
    eqp = " AND ".join(f't."{c}" IS NOT DISTINCT FROM n."{c}"' for c in pcols)
    conflict_p = con.execute(f"SELECT count(*) FROM read_parquet(?) t JOIN read_parquet(?) n USING (project) "
                             f"WHERE NOT ({eqp})", [tp, np_]).fetchone()[0]
    con.execute(f"CREATE TABLE d AS SELECT * FROM read_parquet(?) UNION ALL "
                f"SELECT * FROM read_parquet(?) WHERE domain NOT IN (SELECT domain FROM read_parquet(?))",
                [td, nd, td])
    con.execute(f"CREATE TABLE p AS SELECT * FROM read_parquet(?) UNION ALL "
                f"SELECT * FROM read_parquet(?) WHERE project NOT IN (SELECT project FROM read_parquet(?))",
                [tp, np_, tp])
    con.execute(f"COPY (SELECT * FROM d ORDER BY domain) TO '{out / 'domain_links.parquet'}' (FORMAT PARQUET)")
    con.execute(f"COPY (SELECT * FROM p ORDER BY project) TO '{out / 'project_links.parquet'}' (FORMAT PARQUET)")
    new = con.execute("SELECT domain, firm_based_on_domain, organisation_kind FROM d WHERE domain NOT IN "
                      "(SELECT domain FROM read_parquet(?))", [td]).fetchall()
    con.execute(f"COPY (SELECT * FROM d WHERE domain NOT IN (SELECT domain FROM read_parquet(?)) "
                f"AND firm_based_on_domain <> 'independent' ORDER BY domain) TO "
                f"'{out / 'organization_domains.new.parquet'}' (FORMAT PARQUET)", [td])
    cache = f"{Path(a.cache)}/*.parquet"
    tok = con.execute(f"""
        WITH c AS (SELECT domain, sum(tokens) AS tokens FROM read_parquet('{cache}') GROUP BY 1)
        SELECT
          coalesce(sum(tokens), 0),
          coalesce(sum(tokens) FILTER (WHERE domain IN (SELECT domain FROM d)
                                         AND domain NOT IN (SELECT domain FROM read_parquet(?))), 0),
          count(*) FILTER (WHERE domain NOT IN (SELECT domain FROM d) AND domain <> '' AND domain LIKE '%.%'),
          coalesce(sum(tokens) FILTER (WHERE domain NOT IN (SELECT domain FROM d) AND domain <> ''
                                         AND domain LIKE '%.%'), 0),
          coalesce(sum(tokens) FILTER (WHERE domain = '' OR domain NOT LIKE '%.%'), 0)
        FROM c""", [td]).fetchone()
    kinds: dict[str, int] = {}
    for _, _, k in new:
        kinds[k or "?"] = kinds.get(k or "?", 0) + 1
    rep = {"tom_domain_rows": con.execute("SELECT count(*) FROM read_parquet(?)", [td]).fetchone()[0],
           "new_domain_rows": len(new), "new_domain_rows_by_kind": kinds,
           "new_project_rows": con.execute("SELECT count(*) FROM p").fetchone()[0]
           - con.execute("SELECT count(*) FROM read_parquet(?)", [tp]).fetchone()[0],
           "conflicts_domain": conflict_d, "conflicts_project": conflict_p,
           "tokens_all": tok[0], "tokens_new_domain_rows_no_audit": tok[1],
           "unmatched_real_domains": tok[2], "tokens_unmatched_real_domains_independent": tok[3],
           "tokens_no_real_domain_unknown": tok[4],
           "domain_links_sha256": sha256(out / "domain_links.parquet"),
           "project_links_sha256": sha256(out / "project_links.parquet")}
    (out / "report.json").write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    print("merge-links: " + json.dumps({k: v for k, v in rep.items() if not k.endswith("sha256")}, sort_keys=True))
    return 1 if conflict_d or conflict_p else 0


def _load(p) -> dict:
    return json.loads(Path(p).read_text())


PSEUDO_COLS = {"author_name", "author_email", "committer_name", "committer_email", "personid"}


def cmd_judge_gate(a) -> int:
    """--pseudonyms equal: every column equal. bijection (a new salt): each pseudonym column (the 5 identity
    columns and the footer_* lists) a bijection of TOM's, every other column equal. differ-ok (the private file
    of pass 1): the pseudonym columns, person_domain and the 4 organization columns are not compared."""
    r = _load(a.report)
    bad = []
    for e in r.get("per_column", []):
        c = e["column"]
        if not e["rows_differ"]:
            continue
        pseudo = c in PSEUDO_COLS or c.startswith("footer_")
        if a.pseudonyms == "bijection" and pseudo and e.get("bijection"):
            continue
        if a.pseudonyms == "differ-ok" and (pseudo or c == "person_domain" or c in ORG):
            continue
        bad.append(c)
    allow = {"pseudonymization_registry_sha256"} | ({"pseudonymization_version"} if a.pseudonyms == "differ-ok" else set())
    kv = [k for k in r.get("kv_differ", []) if k not in allow]
    ok = r.get("schema_equal") and r["rows"]["rebuilt"] == r["rows"]["tom"] and not bad and not kv
    print(f"gate: schema {r.get('schema_equal')}, rows {r['rows']}, columns that differ {bad}, footer keys that "
          f"differ {r.get('kv_differ')} -> {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


def cmd_judge_pass(a) -> int:
    r = _load(a.report)
    if not r.get("schema_equal") or r["rows"]["rebuilt"] != r["rows"]["tom"]:
        print(f"pass: schema {r.get('schema_equal')} rows {r.get('rows')} -> FAIL"); return 1
    bad, org = [], {}
    for e in r["per_column"]:
        c = e["column"]
        if not e["rows_differ"]:
            continue
        if c in ORG:
            org[c] = e["rows_differ"]
        elif c in IDENTITY or c.startswith("footer_"):
            # a function of the private value: as many pairs as distinct private values ("tom" side = pass 1)
            if e.get("pairs") != e.get("distinct_tom") or e.get("length_differ"):
                bad.append(c)
        else:
            bad.append(c)
    print(f"pass: rows {r['rows']['rebuilt']}, columns that must be equal and differ {bad}, organization columns "
          f"that differ {org} -> {'OK' if not bad else 'FAIL'}")
    return 1 if bad else 0


DICT_FALLBACK = {"PLAIN", "PLAIN_DICTIONARY", "RLE_DICTIONARY", "RLE"}


def parquet_form(con, f: str) -> dict:
    """The published form of a file: what the release writer decides, not what the data decides."""
    import pyarrow.parquet as pq
    md = pq.ParquetFile(f).metadata
    kv = [k.decode() for k in (md.metadata or {}).keys()]
    cols = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [f]).fetchall()
    sch = con.execute("SELECT name, type, type_length, repetition_type, converted_type, logical_type "
                      "FROM parquet_schema(?)", [f]).fetchall()
    per = con.execute("""SELECT path_in_schema, list(DISTINCT compression), list(DISTINCT encodings),
                                bool_or(bloom_filter_offset IS NOT NULL), bool_and(bloom_filter_offset IS NOT NULL),
                                bool_or(index_page_offset IS NOT NULL), bool_and(stats_null_count IS NOT NULL)
                         FROM parquet_metadata(?) GROUP BY path_in_schema ORDER BY min(column_id)""", [f]).fetchall()
    rg = [r[0] for r in con.execute("SELECT DISTINCT row_group_id, row_group_num_rows FROM parquet_metadata(?) "
                                    "ORDER BY 1", [f]).fetchall()]
    rgn = [r[1] for r in con.execute("SELECT DISTINCT row_group_id, row_group_num_rows FROM parquet_metadata(?) "
                                     "ORDER BY 1", [f]).fetchall()]
    return {"columns": [(c[0], c[1]) for c in cols], "parquet_schema": sch, "kv_keys": kv,
            "created_by": md.created_by, "format_version": md.format_version,
            "codec": {p: c for p, c, *_ in per},
            "encodings": {p: sorted({x.strip() for e in encs for x in e.split(",")}) for p, _, encs, *_ in per},
            "bloom_any": {p: b for p, _, _, b, *_ in per}, "bloom_all": {p: b for p, _, _, _, b, *_ in per},
            "index_page": any(r[5] for r in per), "statistics": all(r[6] for r in per),
            "row_groups_full": all(n == 1_000_000 for n in rgn[:-1]) and (rgn[-1] <= 1_000_000 if rgn else True),
            "row_groups": len(rg)}


def cmd_shape(a) -> int:
    """The Parquet form gate: each FILE must have the published form of the TOM file REF: the column names, types
    and order (DuckDB and the Parquet schema), the footer key order (no ARROW:schema), the writer and the format
    version, the codec of each column, the encodings of each column (a dictionary column may fall back to PLAIN in
    a large chunk), a Bloom filter on the same columns (in every row group), no page index, statistics, and full
    row groups of 1,000,000 rows (the last one smaller). Any difference stops it."""
    con = duckdb.connect()
    ref = parquet_form(con, a.ref)
    bad = 0
    for f in a.files:
        got = parquet_form(con, f)
        why = []
        for k in ("columns", "parquet_schema", "kv_keys", "created_by", "format_version", "codec", "bloom_any",
                  "bloom_all", "index_page", "statistics"):
            if got[k] != ref[k]:
                why.append(k)
        for c, encs in got["encodings"].items():
            allow = set(ref["encodings"].get(c, [])) | (DICT_FALLBACK if "RLE_DICTIONARY" in ref["encodings"].get(c, [])
                                                        else set())
            if not set(encs) <= allow:
                why.append(f"encodings of {c}")
        if not got["row_groups_full"]:
            why.append("row groups")
        bad += bool(why)
        print(f"{'ok ' if not why else 'BAD'} {Path(f).name}: {len(got['columns'])} columns, {got['row_groups']} row "
              f"groups, {got['created_by']}, format {got['format_version']}{'; differs: ' + ', '.join(why) if why else ''}")
    return 1 if bad else 0


def cmd_manifest(a) -> int:
    inp = Path(a.in_dir)
    man = {r[0]: r for r in manifest_rows(inp / "manifest.tsv")}
    meta = json.loads((inp / "project_meta.json").read_text())
    con = duckdb.connect()
    rows = []
    for n in [x.strip() for x in open(a.names) if x.strip()]:
        f = Path(a.files) / f"{n}-dataset.parquet"
        nrows = con.execute("SELECT count(*) FROM read_parquet(?)", [str(f)]).fetchone()[0]
        pin = man[n][5]
        rows.append({"project": n, "clone_url": meta[n]["clone_url"], "size_class": man[n][4],
                     "commits": meta[n]["commits"], "run_commit": pin, "frame_commit": pin,
                     "cregit_commit": a.cregit, "ctp_commit": a.ctp, "rows": nrows, "bytes": f.stat().st_size,
                     "sha256": sha256(f), "path": f"parquet/{n}-dataset.parquet"})
    cols = ["project", "clone_url", "size_class", "commits", "run_commit", "frame_commit", "cregit_commit",
            "ctp_commit", "rows", "bytes", "sha256", "path"]
    write_tsv(a.out, rows, cols)
    print(f"manifest: {len(rows)} rows, {sum(r['rows'] for r in rows):,} token rows, "
          f"{sum(r['bytes'] for r in rows):,} B")
    return 0


def cmd_tables(a) -> int:
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    names = [x.strip() for x in open(a.names) if x.strip()]
    con = duckdb.connect()
    con.execute("CREATE TABLE n(project VARCHAR)")
    con.executemany("INSERT INTO n VALUES (?)", [[x] for x in names])
    md = Path(a.meta_dir)
    pl = str(Path(a.links) / "project_links.parquet")
    po = str(md / "project_organizations.parquet")
    con.execute(f"""COPY (SELECT o.project, o.host, o.namespace, l.firm_based_on_namespace,
                                 l.project_enterprise_driven, l.project_enterprise_basis
                          FROM read_parquet('{po}') o JOIN n USING (project)
                          LEFT JOIN read_parquet('{pl}') l USING (project) ORDER BY o.project)
                    TO '{out / "project_organizations.new.parquet"}' (FORMAT PARQUET)""")
    for t in ("project_labels", "project_languages"):
        con.execute(f"""COPY (SELECT t.* FROM read_parquet('{md / (t + ".parquet")}') t JOIN n USING (project)
                              ORDER BY project) TO '{out / (t + ".new.parquet")}' (FORMAT PARQUET)""")
    got = {t: con.execute(f"SELECT count(*) FROM read_parquet('{out / (t + '.new.parquet')}')").fetchone()[0]
           for t in ("project_organizations", "project_labels", "project_languages")}
    ns = con.execute(f"SELECT count(*) FROM read_parquet('{po}') o JOIN n USING (project) "
                     f"JOIN read_parquet('{pl}') l USING (project) WHERE o.firm_based_on_namespace "
                     f"IS DISTINCT FROM l.firm_based_on_namespace").fetchone()[0]
    print(f"tables: {got}; namespace values of meta that differ from the links: {ns}")
    return 1 if ns or any(v != len(names) for v in got.values()) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("inputs"); s.add_argument("--meta-dir", required=True); s.add_argument("--group", required=True)
    s.add_argument("--gate-tom", required=True); s.add_argument("--gate-row", required=True)
    s.add_argument("--out-dir", required=True)
    s = sub.add_parser("counts"); s.add_argument("--in-dir", required=True); s.add_argument("--work", required=True)
    s.add_argument("--jobs", type=int, default=16); s.add_argument("--git", default="git")
    s = sub.add_parser("fill"); s.add_argument("--in-dir", required=True); s.add_argument("--lsc-out", required=True)
    s.add_argument("--rule", choices=("tom", "scancode"), default="tom")
    s.add_argument("--licensee-bin", default="", help="licensee 9.18.0 (the TOM fill); empty: licensee 10.1.0 of the scan")
    s = sub.add_parser("precheck"); s.add_argument("--manifest", required=True); s.add_argument("--work", required=True)
    s.add_argument("--out", required=True); s.add_argument("--only", default=""); s.add_argument("--jobs", type=int, default=8)
    s.add_argument("--git", default="git")
    s = sub.add_parser("write"); s.add_argument("--names", required=True); s.add_argument("--private", required=True)
    s.add_argument("--work", required=True); s.add_argument("--out-dir", required=True); s.add_argument("--ctp", required=True)
    s.add_argument("--links", required=True); s.add_argument("--organizations-version", required=True)
    s.add_argument("--salt-file", default=""); s.add_argument("--psl", default=""); s.add_argument("--registry-dir", default="")
    s.add_argument("--memory-limit", default="8GB"); s.add_argument("--threads", type=int, default=4)
    s.add_argument("--jobs", type=int, default=4); s.add_argument("--log", required=True)
    s = sub.add_parser("thin"); s.add_argument("--list", required=True); s.add_argument("--out-dir", required=True)
    s.add_argument("--memory-limit", default="8GB")
    s = sub.add_parser("merge-links"); s.add_argument("--tom-dir", required=True)
    s.add_argument("--new-dir", required=True); s.add_argument("--cache", required=True)
    s.add_argument("--out-dir", required=True)
    s = sub.add_parser("judge-gate"); s.add_argument("report")
    s.add_argument("--pseudonyms", choices=("equal", "bijection", "differ-ok"), default="equal")
    s = sub.add_parser("judge-pass"); s.add_argument("report")
    s = sub.add_parser("shape"); s.add_argument("--ref", required=True); s.add_argument("files", nargs="+")
    s = sub.add_parser("manifest"); s.add_argument("--in-dir", required=True); s.add_argument("--files", required=True)
    s.add_argument("--names", required=True); s.add_argument("--cregit", required=True)
    s.add_argument("--ctp", required=True); s.add_argument("--out", required=True)
    s = sub.add_parser("tables"); s.add_argument("--in-dir", required=True); s.add_argument("--meta-dir", required=True)
    s.add_argument("--links", required=True); s.add_argument("--names", required=True)
    s.add_argument("--out-dir", required=True)
    a = ap.parse_args(argv)
    return {"inputs": cmd_inputs, "counts": cmd_counts, "fill": cmd_fill, "thin": cmd_thin, "write": cmd_write, "precheck": cmd_precheck,
            "merge-links": cmd_merge_links,
            "judge-gate": cmd_judge_gate, "judge-pass": cmd_judge_pass, "shape": cmd_shape,
            "manifest": cmd_manifest, "tables": cmd_tables}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
