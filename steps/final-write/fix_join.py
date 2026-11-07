#!/usr/bin/env python3
"""fix_join.py (fix 2026-10-27): join the part write of a second machine with the write of the first machine,
then write the release text files as run_v0.py finish() would.

    fix_join.py --tools T --inputs IN/results.tsv --out O --release REL --part PART --links W/links-final
                --registry PRIV/registry.parquet --report R.json

PART is the downloaded s3://B/dataset-final/part/<run>/ (parquet/ and meta/results.tsv). For each part row:
the file sha256 and the row count must match the row, and the project must be an input. A project that both
machines wrote must have the same output sha256 (the write is deterministic); it is kept once. The new files
go to O/parquet/ and REL/parquet/ (sizes checked) and their rows to O/results.tsv. When every input project is
in O/results.tsv: O/SHA256SUMS (sorted by output), the link files and pseudonymization.json (the options of
the final write: registry and salt check from the registry footer, the PSL hash, the defaults of build_v0.py,
the content scan off) go to O and REL. Without a full set: the missing projects go to the report, exit 1.
Counts and project names only. Exit 0 ok, 1 not complete or a check failed, 2 usage.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import shutil
import sys
from pathlib import Path


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def read(p: Path) -> list[dict]:
    if not p.is_file():
        return []
    with open(p, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for k in ("tools", "inputs", "out", "release", "part", "links", "registry", "report"):
        ap.add_argument(f"--{k}", type=Path, required=True)
    a = ap.parse_args(argv)
    sys.path[:0] = [str(a.tools), str(a.tools / "anon")]
    import run_v0 as rv
    import build_v0 as bv
    from final_merge import rows_of
    import pseudonymize as P
    cols = list(rv.RESULT_COLS)
    inputs = {r["project"]: r for r in read(a.inputs)}
    have = read(a.out / "results.tsv")
    by = {r["project"]: r for r in have}
    part = read(a.part / "meta" / "results.tsv")
    rep = {"inputs": len(inputs), "first_machine": len(have), "part_rows": len(part), "added": 0, "both": 0,
           "problems": [], "missing": []}
    new_rows = []
    for r in part:
        p = r["project"]
        if p not in inputs:
            rep["problems"].append(f"{p}: not an input")
            continue
        f = a.part / "parquet" / Path(r["output"]).name
        if not f.is_file():
            rep["problems"].append(f"{p}: no part file")
            continue
        if p in by:
            if by[p]["output_sha256"] != r["output_sha256"]:
                rep["problems"].append(f"{p}: written by both machines with another sha256")
            else:
                rep["both"] += 1
            continue
        if sha256(f) != r["output_sha256"]:
            rep["problems"].append(f"{p}: the part file sha256 is not its row")
            continue
        if int(rows_of(f)) != int(inputs[p]["rows"]) or int(r["rows"]) != int(inputs[p]["rows"]):
            rep["problems"].append(f"{p}: rows are not the input rows")
            continue
        for d in (a.out / "parquet", a.release / "parquet"):
            d.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, d / f.name)
            if (d / f.name).stat().st_size != f.stat().st_size:
                rep["problems"].append(f"{p}: copy size in {d}")
        new_rows.append({c: r.get(c, "") for c in cols})
        by[p] = r
    if rep["problems"]:
        a.report.write_text(json.dumps(rep, indent=1) + "\n")
        print(f"fix_join: {len(rep['problems'])} problems (first: {rep['problems'][0]}); nothing appended")
        return 1
    if new_rows:
        with open(a.out / "results.tsv", "a", newline="") as fh:
            w = csv.DictWriter(fh, cols, delimiter="\t", lineterminator="\n")
            if not have:
                w.writeheader()
            w.writerows(new_rows)
    rep["added"] = len(new_rows)
    rep["missing"] = sorted(set(inputs) - set(by))
    if rep["missing"]:
        a.report.write_text(json.dumps(rep, indent=1) + "\n")
        print(f"fix_join: {rep['added']} added, {rep['both']} on both machines; {len(rep['missing'])} projects "
              f"missing (a gap pass writes them): {', '.join(rep['missing'][:5])}")
        return 1
    res = sorted(read(a.out / "results.tsv"), key=lambda r: r["output"])
    if len(res) != len(inputs) or {r["project"] for r in res} != set(inputs):
        rep["problems"].append("results.tsv does not hold each input once")
        a.report.write_text(json.dumps(rep, indent=1) + "\n")
        print("fix_join: results.tsv does not hold each input once")
        return 1
    with open(a.out / "SHA256SUMS", "w") as fh:
        for r in res:
            fh.write(f"{r['output_sha256']}  {r['output']}\n")
    for name in rv.LINK_FILES:
        shutil.copyfile(a.links / name, a.out / name)
    import duckdb
    con = duckdb.connect()
    meta = P.registry_meta(con, str(a.registry))
    con.close()
    dflt = {k: v.default for k, v in inspect.signature(bv.prepare_anon).parameters.items()}
    psl = P.load_psl(str(a.tools / "public_suffix_list.dat"))
    info = {"pseudonymization_version": P.SCHEME_VERSION, "registry_sha256": meta["registry_sha256"],
            "salt_check": meta.get("salt_check"), "psl_sha256": psl["sha256"],
            "email_domain": P.DEFAULT_EMAIL_DOMAIN, "person_domain_at": dflt["domain_at"],
            "commit_summary": dflt["summary_mode"], "leak_scan": True, "leak_scan_content_columns": False}
    (a.out / "pseudonymization.json").write_text(json.dumps(info, indent=1, sort_keys=True) + "\n")
    for name in ("SHA256SUMS", "results.tsv") + tuple(rv.LINK_FILES) + ("pseudonymization.json",):
        shutil.copyfile(a.out / name, a.release / name)
    rep["files"] = len(res)
    rep["rows"] = sum(int(r["rows"]) for r in res)
    a.report.write_text(json.dumps(rep, indent=1) + "\n")
    print(f"fix_join: {rep['added']} added, {rep['both']} on both machines; {len(res)} files, {rep['rows']} rows; "
          f"SHA256SUMS, results.tsv, link files and pseudonymization.json in O and REL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
