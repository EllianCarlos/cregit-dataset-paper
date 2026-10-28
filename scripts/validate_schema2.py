#!/usr/bin/env python3
"""Check the column contract and the footer of each published project file (ctp schema 2).

Usage: validate_schema2.py DATA_DIR [--jobs N]

DATA_DIR is the release root: parquet/<project>-dataset.parquet, and (if present)
pseudonymization.json and MANIFEST.tsv.

The published files are ctp schema 2: the 67 cregit columns of the contract of ctp ca113e3
(tools/ctp/validate_schema.py, CREGIT_COLUMNS, unchanged), then the 4 organization columns.
The 3 firm columns of ca113e3 (firm_raw, firm, firm_source) are not in the published files.
The release write (organization columns and pseudonyms, one write) made this contract.

For each file the script checks:
  1. the 71 columns: the names, the types and the order (compare_schema of ca113e3);
  2. the footer keys: ctp_schema_version = 2, organizations_version = v4.9,
     organizations_mapping_sha256 = the mapping of the release, pseudonymization_version = 2,
     (release 1, dataset-release-1, has the old spelling of the two keys: organisations_version and
     organisations_mapping_sha256; the script accepts either spelling, OLD_FOOTER_KEYS),
     pseudonymization_registry_sha256 = the registry of the file in pseudonymization.json
     (when pseudonymization.json is present: each file must have a registry there);
  3. the number of rows = the rows column of MANIFEST.tsv (when MANIFEST.tsv is present: each
     file must have a row, and each row must have a file).
A file that the script cannot read is a problem, not a stop.
It reads only the Parquet metadata. It needs duckdb (the dev shell: CREGIT_PYTHON).
Exit 0: all files pass. Exit 1: one or more problems (each problem is printed). Exit 2: usage.
Exit 3: not ready (no project file under DATA_DIR).
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CA113E3_VALIDATOR = ROOT / "tools" / "ctp" / "validate_schema.py"

ORGANIZATION_COLUMNS = (
    ("firm_based_on_namespace", "VARCHAR"),
    ("firm_based_on_domain", "VARCHAR"),
    ("project_enterprise_driven", "BOOLEAN"),
    ("project_enterprise_basis", "VARCHAR"),
)
# The values of the release (dataset-release-1; the same in dataset-release-2).
WANT_FOOTER = {
    "ctp_schema_version": "2",
    "organizations_version": "v4.9",
    "organizations_mapping_sha256":
        "7b52a5155e6f9af60541d5cdfaf6ef6566679a1281497ab274decadb50debe62",
    "pseudonymization_version": "2",
}
# The names of the two keys in release 1 (before the spelling decision of 2026-10-28).
OLD_FOOTER_KEYS = {"organizations_version": "organisations_version",
                   "organizations_mapping_sha256": "organisations_mapping_sha256"}
REGISTRY_KEY = "pseudonymization_registry_sha256"
SUFFIX = "-dataset.parquet"


def load_ca113e3():
    sys.dont_write_bytecode = True  # no __pycache__ in tools/ctp/
    spec = importlib.util.spec_from_file_location("validate_schema_ca113e3", CA113E3_VALIDATOR)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # the dataclass of the module looks itself up here
    spec.loader.exec_module(mod)
    return mod


def registries(root: Path) -> tuple[bool, str | None, dict[str, str]]:
    """(the file is present, the registry of every file that no row names, {project: registry})
    of pseudonymization.json."""
    path = root / "pseudonymization.json"
    if not path.is_file():
        return False, None, {}
    default, named = None, {}
    for row in json.loads(path.read_text(encoding="utf-8")).get("registries", []):
        projects = row.get("projects")
        if projects:
            named.update({p: row["registry_sha256"] for p in projects})
        else:
            default = row["registry_sha256"]
    return True, default, named


def manifest_rows(root: Path) -> dict[str, int]:
    path = root / "MANIFEST.tsv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["project"]: int(r["rows"]) for r in csv.DictReader(fh, delimiter="\t")}


def check_file(vs, contract, path: Path, want_registry: str | None, want_rows: int | None):
    import duckdb

    problems = []
    name = path.name[: -len(SUFFIX)]
    rows = 0
    con = duckdb.connect()
    try:
        actual = [(r[0], r[1]) for r in con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]).fetchall()]
        problems += [f"{name}: {d}" for d in vs.compare_schema(actual, contract)]
        kv = dict(con.execute("SELECT decode(key), decode(value) FROM parquet_kv_metadata(?)",
                              [str(path)]).fetchall())
        for key, want in WANT_FOOTER.items():
            old = OLD_FOOTER_KEYS.get(key)
            got = kv[key] if key in kv else kv.get(old) if old else None
            if got != want:
                problems.append(f"{name}: footer {key} is {got!r}, want {want!r}")
        if want_registry is not None and kv.get(REGISTRY_KEY) != want_registry:
            problems.append(f"{name}: footer {REGISTRY_KEY} is {kv.get(REGISTRY_KEY)!r}, "
                            f"want {want_registry!r}")
        rows = con.execute("SELECT num_rows FROM parquet_file_metadata(?)",
                           [str(path)]).fetchone()[0]
        if want_rows is not None and rows != want_rows:
            problems.append(f"{name}: {rows} rows, MANIFEST.tsv has {want_rows}")
    except duckdb.Error as exc:
        problems.append(f"{name}: cannot read the file ({type(exc).__name__})")
    finally:
        con.close()
    return problems, int(rows or 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data_dir", type=Path)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args(argv)
    root = args.data_dir
    files = sorted((root / "parquet").glob("*" + SUFFIX))
    if not files:
        print(f"not ready: no parquet/*{SUFFIX} file under {root}", file=sys.stderr)
        return 3
    vs = load_ca113e3()
    contract = tuple(vs.CREGIT_COLUMNS) + ORGANIZATION_COLUMNS
    assert len(contract) == 71, len(contract)
    has_registry, default_registry, named_registry = registries(root)
    rows_of = manifest_rows(root)
    problems: list[str] = []
    total = 0

    def one(path: Path):
        name = path.name[: -len(SUFFIX)]
        reg = named_registry.get(name, default_registry)
        found, rows = check_file(vs, contract, path, reg, rows_of.get(name) if rows_of else None)
        if has_registry and reg is None:
            found.append(f"{name}: pseudonymization.json gives no registry for this file")
        if rows_of and name not in rows_of:
            found.append(f"{name}: a file with no row in MANIFEST.tsv")
        return found, rows

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for found, rows in pool.map(one, files):
            problems += found
            total += rows
    if rows_of:
        missing = sorted(set(rows_of) - {p.name[: -len(SUFFIX)] for p in files})
        problems += [f"{p}: in MANIFEST.tsv, no file" for p in missing]
    for p in problems:
        print(p)
    checks = "columns, footer" + (", registry" if has_registry else "") + (
        ", rows of MANIFEST.tsv" if rows_of else "")
    if problems:
        print(f"FAIL: {len(problems)} problems in {len(files)} files ({checks})")
        return 1
    print(f"OK: {len(files)} files have the 71 columns of ctp schema 2 ({checks}); {total} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
