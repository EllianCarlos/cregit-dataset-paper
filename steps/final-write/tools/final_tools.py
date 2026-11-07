#!/usr/bin/env python3
"""final_tools.py: the input lists and the checks of the final write machine (kit dataset-final, 2026-10-25).

    final_tools.py pathfix-inputs --meta DIR --list FILE --v1-results TSV --out TSV
    final_tools.py assemble --root IN --list FILE --expect N [--report JSON]
    final_tools.py compare-links --got DIR --ref DIR [--out TXT]
    final_tools.py check-out --inputs IN/results.tsv --release DIR --anon-dir DIR --ov V --mapping H
                             --registry-sha256 H [--jobs N] [--out TSV]

pathfix-inputs  The inputs.tsv of final_merge.py for the path-fix rows of the 5,000+ layer (cregit
                14b8db4; part 1 of dataset-pathfix/stage/inputs/parts.tsv). DIR is a copy of
                s3://B/dataset-x1k/done-pathfix/<p>/ with OK and <p>.validated for each project of
                FILE. OK: line 1 "uploaded <utc> from <instance> part <part>", line 2
                "parquet_sha256 <sha>", then "<bytes>\t<file>" lines; <p>.validated has rows= and
                bytes= (bytes must equal the OK size). Each project must be in the v1-raw results.tsv.
                s3_key is relative to the --src of final_merge.py.
assemble        IN holds v1/ (dataset-v1/raw/), x1k/ (dataset-x1k/raw/) and pf17/ (the final_merge.py
                output of the path-fix rows). It writes IN/results.tsv for run_v0.py --v1raw IN: the
                v1-raw rows without the projects of FILE, the pf17 rows, the x1k rows (project, layer,
                source, output relative to IN, output_sha256, rows, output_bytes). Checks: N rows,
                no project or file name repeats, each file exists with its size, FILE = the pf17 rows.
                Also IN/files.txt (one absolute path per line: the registry pass) and
                IN/extract.v1.tsv, IN/extract.x1k.tsv (project, path, rows: extract_domains_v1.py).
compare-links   Two build_links.py outputs: the counts of rows only in GOT, only in REF and with other
                values, per table, and both mapping hashes. Counts only (a domain can be personal).
check-out       After the write: every file of IN/results.tsv is DIR/parquet/<name> with the ctp schema 2
                columns and types of pseudonymize.SCHEMA_2, the row count of the input, ZSTD, row
                groups of at most 1,000,000 rows, and the footer values (ctp_schema_version 2,
                organisations_version V, organisations_mapping_sha256 H, pseudonymization_version,
                pseudonymization_registry_sha256). DIR/SHA256SUMS has one line per file and each
                sha256 checks. DIR holds only the release files (no registry), and its text files hold
                no at sign. Metadata reads only, and the sha256 (parallel).
No output holds a value of a data column. Exit 0 ok, 1 a check failed, 2 usage.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

AT = chr(64)
PATHFIX_CREGIT = "14b8db4"
COMBINED_COLS = ("project", "layer", "source", "output", "output_sha256", "rows", "output_bytes")
RELEASE_TEXT = ("SHA256SUMS", "results.tsv", "links.json", "pseudonymization.json")
RELEASE_FILES = RELEASE_TEXT + ("domain_links.parquet", "project_links.parquet")


def fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def names(f: Path) -> list[str]:
    return [l.split()[0] for l in f.read_text().splitlines() if l.strip() and not l.startswith("#")]


def read_tsv(f: Path) -> list[dict]:
    with open(f, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def write_tsv(f: Path, cols, rows) -> None:
    tmp = f.with_name(f.name + ".tmp")
    with open(tmp, "w", newline="") as fh:
        w = csv.DictWriter(fh, cols, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(f)


def parse_ok(ok: Path) -> tuple[str, int, int]:
    """-> (parquet sha256, token rows, bytes) of one <p>/OK and its <p>.validated."""
    p = ok.parent.name
    lines = ok.read_text().splitlines()
    head = lines[0].split()
    if not (head and head[0] == "uploaded" and len(head) >= 2 and head[-2] == "part"):
        raise ValueError(f"{p}: OK line 1 is not 'uploaded ... part <part>'")
    if not lines[1].startswith("parquet_sha256 ") or len(lines[1].split()[1]) != 64:
        raise ValueError(f"{p}: OK line 2 is not 'parquet_sha256 <sha>'")
    sha = lines[1].split()[1]
    size = {l.split("\t")[1]: int(l.split("\t")[0]) for l in lines[2:] if "\t" in l}
    pq = f"{p}-dataset.parquet"
    if pq not in size:
        raise ValueError(f"{p}: no size line of {pq} in OK")
    st = dict(l.split("=", 1) for l in (ok.parent / f"{p}.validated").read_text().split() if "=" in l)
    n, b = int(st["rows"]), int(st["bytes"])
    if b != size[pq]:
        raise ValueError(f"{p}: the bytes of {p}.validated ({b}) are not the OK size ({size[pq]})")
    return sha, n, b


def cmd_pathfix_inputs(a) -> int:
    want = names(a.list)
    if len(set(want)) != len(want):
        return fail(f"{a.list}: a project repeats")
    v1 = {r["project"] for r in read_tsv(a.v1_results)}
    rows, bad = [], []
    for p in want:
        if p not in v1:
            bad.append(f"{p}: not a project of the v1-raw results.tsv")
            continue
        ok = a.meta / p / "OK"
        if not ok.is_file():
            bad.append(f"{p}: no done-pathfix OK")
            continue
        try:
            sha, n, b = parse_ok(ok)
        except (ValueError, KeyError, IndexError, OSError) as exc:
            bad.append(str(exc))
            continue
        rows.append({"project": p, "source": "v1-pathfix", "cregit": PATHFIX_CREGIT, "token_rows": n, "bytes": b,
                     "s3_key": f"dataset-x1k/done-pathfix/{p}/{p}-dataset.parquet", "sha256": sha})
    if bad:
        for m in bad:
            print(f"FAIL: {m}", file=sys.stderr)
        return 1
    write_tsv(a.out, ("project", "source", "cregit", "token_rows", "bytes", "s3_key", "sha256"), rows)
    print(f"pathfix-inputs: {len(rows)} rows, {sum(int(r['token_rows']) for r in rows)} token rows -> {a.out}")
    return 0


def cmd_assemble(a) -> int:
    root = a.root.resolve()
    pf_list = set(names(a.list))
    v1, pf, x1k = (read_tsv(root / d / "results.tsv") for d in ("v1", "pf17", "x1k"))
    bad = []
    if {r["project"] for r in pf} != pf_list:
        bad.append(f"the pf17 results.tsv has {len(pf)} rows, not the {len(pf_list)} projects of {a.list.name}")
    old = {r["project"]: r for r in v1 if r["project"] in pf_list}
    if set(old) != pf_list:
        bad.append(f"{len(pf_list - set(old))} path-fix projects are not in the v1-raw results.tsv")
    out = []
    for layer, sub, rows in (("v1", "v1", [r for r in v1 if r["project"] not in pf_list]), ("v1", "pf17", pf),
                             ("x1k", "x1k", x1k)):
        for r in rows:
            out.append({"project": r["project"], "layer": layer,
                        "source": "v1-pathfix" if sub == "pf17" else r.get("source", ""),
                        "output": f"{sub}/{r['output']}", "output_sha256": r["output_sha256"], "rows": r["rows"],
                        "output_bytes": r["output_bytes"]})
    projects = [r["project"] for r in out]
    files = [Path(r["output"]).name for r in out]
    if len(set(projects)) != len(projects):
        bad.append(f"{len(projects) - len(set(projects))} projects repeat")
    if len(set(files)) != len(files):
        bad.append(f"{len(files) - len(set(files))} file names repeat")
    if len(out) != a.expect:
        bad.append(f"{len(out)} rows, not {a.expect}")
    missing = sizes = 0
    for r in out:
        f = root / r["output"]
        if not f.is_file():
            missing += 1
        elif f.stat().st_size != int(r["output_bytes"]):
            sizes += 1
    if missing or sizes:
        bad.append(f"{missing} files missing, {sizes} files with another size")
    if bad:
        for m in bad:
            print(f"FAIL: {m}", file=sys.stderr)
        return 1
    write_tsv(root / "results.tsv", COMBINED_COLS, out)
    (root / "files.txt").write_text("".join(f"{root / r['output']}\n" for r in out))
    for layer in ("v1", "x1k"):
        rows = sorted((r for r in out if r["layer"] == layer), key=lambda r: -int(r["rows"]))
        write_tsv(root / f"extract.{layer}.tsv", ("project", "path", "rows"),
                  [{"project": r["project"], "path": str(root / r["output"]), "rows": r["rows"]} for r in rows])
    rep = {"files": len(out), "rows": sum(int(r["rows"]) for r in out),
           "by_layer": {k: {"files": sum(1 for r in out if r["layer"] == k),
                            "rows": sum(int(r["rows"]) for r in out if r["layer"] == k)} for k in ("v1", "x1k")},
           "pathfix": {"files": len(pf), "rows_new": sum(int(r["rows"]) for r in pf),
                       "rows_v1raw": sum(int(old[p]["rows"]) for p in old),
                       "projects_with_other_rows": sum(1 for r in pf if int(r["rows"]) != int(old[r["project"]]["rows"]))}}
    if a.report:
        a.report.write_text(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    print(f"assemble: {rep['files']} files, {rep['rows']} rows (v1 {rep['by_layer']['v1']['files']} incl. "
          f"{len(pf)} path-fix, x1k {rep['by_layer']['x1k']['files']}) -> {root / 'results.tsv'}")
    return 0


def cmd_compare_links(a) -> int:
    import duckdb
    con = duckdb.connect()
    lines = []
    for name, key in (("domain_links.parquet", "domain"), ("project_links.parquet", "project")):
        g, r = str(a.got / name), str(a.ref / name)
        cols = [c[0] for c in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [g]).fetchall()]
        rcols = [c[0] for c in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [r]).fetchall()]
        common = [c for c in cols if c in rcols and c != key]
        ng, nr = (con.execute("SELECT count(*) FROM read_parquet(?)", [f]).fetchone()[0] for f in (g, r))
        only_g, only_r, changed = con.execute(
            f"SELECT count(*) FILTER (WHERE r.{key} IS NULL), count(*) FILTER (WHERE g.{key} IS NULL), "
            f"count(*) FILTER (WHERE g.{key} IS NOT NULL AND r.{key} IS NOT NULL AND ("
            + " OR ".join(f"g.\"{c}\" IS DISTINCT FROM r.\"{c}\"" for c in common) + ")) "
            f"FROM read_parquet(?) g FULL JOIN read_parquet(?) r ON g.{key} = r.{key}", [g, r]).fetchone() \
            if common else (0, 0, 0)
        lines.append(f"{name}: got {ng} rows, ref {nr}; only in got {only_g}, only in ref {only_r}, "
                     f"other values {changed} (columns compared: {len(common)})")
    mg, mr = (json.loads((d / "links.json").read_text()).get("mapping_sha256", "") for d in (a.got, a.ref))
    lines.append(f"mapping_sha256: got {mg[:12]}, ref {mr[:12]}")
    text = "\n".join(lines) + "\n"
    if a.out:
        a.out.write_text(text)
    print(text, end="")
    return 0


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


# The largest row group that check-out accepts. build_v0.py writes with ROW_GROUP_SIZE 1000000, and DuckDB
# fills a row group with whole vectors of 2,048 rows, so a full row group holds 1,001,472 rows (489 vectors).
ROW_GROUP_TARGET = 1_000_000
DUCKDB_VECTOR = 2048
ROW_GROUP_MAX = -(-ROW_GROUP_TARGET // DUCKDB_VECTOR) * DUCKDB_VECTOR


def cmd_check_out(a) -> int:
    import duckdb
    sys.path.insert(0, str(a.anon_dir))
    import pseudonymize as P
    want_cols = [(c, t) for c, t in P.SCHEMA_2]
    want_kv = {"ctp_schema_version": "2", "organisations_version": a.ov, "organisations_mapping_sha256": a.mapping,
               P.FOOTER_VERSION_KEY: P.SCHEME_VERSION, P.FOOTER_REGISTRY_KEY: a.registry_sha256}
    inputs = read_tsv(a.inputs)
    rel = a.release
    sums = {}
    if (rel / "SHA256SUMS").is_file():
        for l in (rel / "SHA256SUMS").read_text().splitlines():
            sha, name = l.split(None, 1)
            sums[name.strip()] = sha

    def one(r: dict) -> dict:
        name = f"parquet/{Path(r['output']).name}"
        f = rel / name
        probs = []
        if not f.is_file():
            return {"file": name, "rows": "", "problems": "missing"}
        con = duckdb.connect()
        try:
            cols = [(c[0], c[1]) for c in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(f)]).fetchall()]
            if cols != want_cols:
                probs.append("columns or types are not ctp schema 2")
            n, maxg, codecs = con.execute(
                "SELECT (SELECT num_rows FROM parquet_file_metadata(?)), max(row_group_num_rows), "
                "string_agg(DISTINCT compression, ',') FROM parquet_metadata(?)", [str(f), str(f)]).fetchone()
            if int(n) != int(r["rows"]):
                probs.append(f"{n} rows, the input has {r['rows']}")
            if maxg and int(maxg) > ROW_GROUP_MAX:
                probs.append(f"a row group of {maxg} rows")
            if codecs and set(codecs.split(",")) - {"ZSTD"}:
                probs.append(f"compression {codecs}")
            kv = dict(con.execute("SELECT decode(key), decode(value) FROM parquet_kv_metadata(?)", [str(f)]).fetchall())
            bad = sorted(k for k, v in want_kv.items() if kv.get(k) != v)
            if bad:
                probs.append(f"footer values of {bad}")
        finally:
            con.close()
        if sums.get(name) != sha256(f):
            probs.append("sha256 is not the SHA256SUMS line")
        return {"file": name, "rows": n, "problems": "; ".join(probs)}

    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(one, inputs))
    general = []
    if len(sums) != len(inputs):
        general.append(f"SHA256SUMS has {len(sums)} lines, the inputs {len(inputs)}")
    extra = sorted(str(p.relative_to(rel)) for p in rel.rglob("*") if p.is_file()
                   and not (p.parent == rel / "parquet" and p.suffix == ".parquet") and p.name not in RELEASE_FILES)
    if extra:
        general.append(f"{len(extra)} files that are not release files (for example {extra[0]})")
    # The name rule skips the expected files: a project name can hold the word (confluentinc__schema-registry).
    expected = {f"parquet/{Path(r['output']).name}" for r in inputs}
    if any("registry" in p.name.lower() for p in rel.rglob("*") if str(p.relative_to(rel)) not in expected):
        general.append("a file named registry in the release folder")
    nparq = len(list((rel / "parquet").glob("*.parquet"))) if (rel / "parquet").is_dir() else 0
    if nparq != len(inputs):
        general.append(f"{nparq} Parquet files, the inputs {len(inputs)}")
    for t in RELEASE_TEXT:
        if (rel / t).is_file() and AT in (rel / t).read_text(errors="replace"):
            general.append(f"{t} holds the at sign")
        if not (rel / t).is_file():
            general.append(f"no {t}")
    nbad = sum(1 for r in res if r["problems"])
    if a.out:
        write_tsv(a.out, ("file", "rows", "problems"), res)
    print(f"check-out: {len(res)} files, {sum(int(r['rows'] or 0) for r in res)} rows, {nbad} files with "
          f"problems; release folder: {'; '.join(general) or 'ok'}")
    for r in [r for r in res if r["problems"]][:10]:
        print(f"  {r['file']}: {r['problems']}")
    return 1 if nbad or general else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pathfix-inputs")
    p.add_argument("--meta", type=Path, required=True)
    p.add_argument("--list", type=Path, required=True)
    p.add_argument("--v1-results", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("assemble")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--list", type=Path, required=True)
    p.add_argument("--expect", type=int, required=True)
    p.add_argument("--report", type=Path)
    p = sub.add_parser("compare-links")
    p.add_argument("--got", type=Path, required=True)
    p.add_argument("--ref", type=Path, required=True)
    p.add_argument("--out", type=Path)
    p = sub.add_parser("check-out")
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--release", type=Path, required=True)
    p.add_argument("--anon-dir", type=Path, required=True)
    p.add_argument("--ov", required=True)
    p.add_argument("--mapping", required=True)
    p.add_argument("--registry-sha256", required=True)
    p.add_argument("--jobs", type=int, default=16)
    p.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    for k in ("meta", "list", "v1_results", "root", "got", "ref", "inputs", "release", "anon_dir"):
        v = getattr(a, k, None)
        if v is not None and not v.exists():
            print(f"usage: {v} does not exist", file=sys.stderr)
            return 2
    return {"pathfix-inputs": cmd_pathfix_inputs, "assemble": cmd_assemble, "compare-links": cmd_compare_links,
            "check-out": cmd_check_out}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
