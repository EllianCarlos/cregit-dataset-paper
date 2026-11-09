"""integrity_fixtures.py OUT: a tiny TOM-form root for the local test of integrity_check.py, and its bad copies.

OUT/good       4 project files (pyarrow, ZSTD, 3 row groups each; 2 with page CRCs), 2 side tables, dataset.duckdb,
               MANIFEST.tsv, SHA256SUMS, docs/README.md
OUT/flip       good, with bytes flipped in a data page of a file without CRCs (SHA256SUMS not changed)
OUT/flip-crc   good, with bytes flipped in a data page of a file with CRCs; SHA256SUMS and MANIFEST.tsv rewritten,
               so only the page CRC and the decode can find it
OUT/flip-nocrc the same for a file without CRCs (only the decode and the statistics can find it)
OUT/truncated  good, with the footer of one file cut off
OUT/schema     good, with one file of another column type (SHA256SUMS and MANIFEST.tsv rewritten)
OUT/extra      good, with one file not in SHA256SUMS and one SHA256SUMS file removed
"""

import hashlib
import json
import os
import random
import shutil
import sys
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import integrity_check as C  # noqa: E402

OUT = Path(sys.argv[1])
KV = {"ctp_schema_version": "3", "organizations_mapping_sha256": "7b52" + "0" * 60, "organizations_version": "v4.9",
      "pseudonymization_registry_sha256": "ab" * 32, "pseudonymization_version": "2"}
PROJECTS = [("tio__tio", 3000, True), ("acme__alpha", 2500, False), ("acme__beta", 2000, True),
            ("git.savannah.gnu.org__gamma", 1500, False)]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def arrow_type(t):
    return {"string": pa.string(), "int64": pa.int64(), "bool": pa.bool_(),
            "list<element: string>": pa.list_(pa.field("element", pa.string()))}[t]


def table(project, n, rnd, schema=C.TOM_SCHEMA):
    words = ["int", "return", "if", "(", ")", "{", "}", "foo", "bar_baz", "x", ";", "ñandú", "数据"]
    cols = {}
    for name, t in schema:
        if name == "repo_name":
            v = [project] * n
        elif name == "license":
            v = ["MIT"] * n
        elif t == "string":
            v = [None if rnd.random() < 0.05 else "".join(rnd.choice(words) for _ in range(rnd.randint(1, 6)))
                 for _ in range(n)]
        elif t == "int64":
            v = [rnd.randint(0, 10 ** 6) for _ in range(n)]
        elif t == "bool":
            v = [rnd.random() < 0.5 for _ in range(n)]
        else:
            v = [[] if rnd.random() < 0.8 else [f"p{rnd.randint(1, 9)}"] for _ in range(n)]
        cols[name] = pa.array(v, type=arrow_type(t))
    return pa.table(cols).replace_schema_metadata(KV)


def write(path, tbl, crc):
    w = pq.ParquetWriter(path, tbl.schema, compression="zstd", write_page_checksum=crc, write_statistics=True,
                         use_dictionary=True, store_schema=False)
    w.write_table(tbl, row_group_size=1000)
    w.add_key_value_metadata(KV)
    w.close()


def build_good(root):
    rnd = random.Random(20261109)
    (root / "parquet").mkdir(parents=True)
    (root / "organizations").mkdir()
    (root / "docs").mkdir()
    man = []
    for p, n, crc in PROJECTS:
        f = root / "parquet" / f"{p}-dataset.parquet"
        write(f, table(p, n, rnd), crc)
        man.append({"project": p, "rows": n, "bytes": f.stat().st_size, "sha256": sha(f), "path": f"parquet/{p}-dataset.parquet"})
    facts = pa.table({"project": [p for p, _, _ in PROJECTS], "fact_type": ["roster_language"] * 4,
                      "value": ["C", "C++", "Java", "C"]})
    pq.write_table(facts, root / "organizations" / "project_facts.parquet")
    orgs = pa.table({"organization_id": ["acme", "independent"], "kind": ["company", "none"]})
    pq.write_table(orgs, root / "organizations" / "organizations.parquet")
    info = {"ctp_schema_version": "3", "mapping_sha256": KV["organizations_mapping_sha256"]}
    for t in ("project_facts", "organizations"):
        fp = root / "organizations" / f"{t}.parquet"
        info[f"{t}_rows"] = str(pq.ParquetFile(fp).metadata.num_rows)
        info[f"{t}_sha256"] = sha(fp)
    db = root / "organizations" / "dataset.duckdb"
    pq.write_table(pa.table({"key": ["x"], "value": ["y"]}), root / "organizations" / "release_info.parquet")
    cwd = os.getcwd()
    os.chdir(root)
    con = duckdb.connect(str(db))
    for t in ("project_facts", "organizations", "release_info"):
        con.execute(f'CREATE VIEW {t} AS SELECT * FROM "organizations/{t}.parquet"')
    con.execute("CREATE VIEW tokens AS SELECT * FROM read_parquet('parquet/*.parquet', filename = true)")
    con.execute("CREATE VIEW tokens_with_organizations AS SELECT t.*, o.kind AS domain_organization_kind FROM tokens t "
                "LEFT JOIN organizations o ON o.organization_id = t.firm_based_on_domain")
    con.close()
    os.chdir(cwd)
    info["dataset_db_sha256"] = sha(db)
    pq.write_table(pa.table({"key": list(info), "value": list(info.values())}),
                   root / "organizations" / "release_info.parquet")
    (root / "docs" / "README.md").write_text("# test root\n")
    write_meta(root, man)


def write_meta(root, man):
    cols = ["project", "rows", "bytes", "sha256", "path"]
    with open(root / "MANIFEST.tsv", "w") as f:
        f.write("\t".join(cols) + "\n")
        for r in sorted(man, key=lambda r: r["project"]):
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    rels = sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (root / "SHA256SUMS").write_text("".join(f"{sha(root / r)}  {r}\n" for r in rels))


def rewrite_meta(root):
    man = []
    for r in C.read_tsv(root / "MANIFEST.tsv"):
        f = root / r["path"]
        man.append({"project": r["project"], "rows": pq.ParquetFile(f).metadata.num_rows if f.exists() else r["rows"],
                    "bytes": f.stat().st_size, "sha256": sha(f), "path": r["path"]})
    write_meta(root, man)


def flip(path, column="source_text", row_group=1):
    md = pq.ParquetFile(path).metadata
    j = [md.schema.column(i).name for i in range(md.num_columns)].index(column)
    cc = md.row_group(row_group).column(j)
    start = cc.data_page_offset
    end = (cc.dictionary_page_offset or cc.data_page_offset) + cc.total_compressed_size
    at = start + (end - start) * 2 // 3
    b = bytearray(Path(path).read_bytes())
    for k in range(8):
        b[at + k] ^= 0xFF
    Path(path).write_bytes(bytes(b))
    return {"file": Path(path).name, "column": column, "row_group": row_group, "offset": at, "bytes": 8}


def main():
    if OUT.exists():
        raise SystemExit(f"ABORT: {OUT} exists")
    good = OUT / "good"
    build_good(good)
    notes = {}

    def copy(name):
        d = OUT / name
        shutil.copytree(good, d)
        return d

    d = copy("flip")
    notes["flip"] = flip(d / "parquet" / "acme__alpha-dataset.parquet")
    d = copy("flip-crc")
    notes["flip-crc"] = flip(d / "parquet" / "acme__beta-dataset.parquet")
    rewrite_meta(d)
    d = copy("flip-nocrc")
    notes["flip-nocrc"] = flip(d / "parquet" / "git.savannah.gnu.org__gamma-dataset.parquet")
    rewrite_meta(d)
    d = copy("truncated")
    f = d / "parquet" / "acme__beta-dataset.parquet"
    f.write_bytes(f.read_bytes()[:-200])
    notes["truncated"] = {"file": f.name, "cut": 200}
    d = copy("schema")
    sch = [(n, "string") if n == "token_index" else (n, t) for n, t in C.TOM_SCHEMA]
    write(d / "parquet" / "acme__alpha-dataset.parquet", table("acme__alpha", 2500, random.Random(1), sch), False)
    rewrite_meta(d)
    notes["schema"] = {"file": "acme__alpha-dataset.parquet", "token_index": "string"}
    d = copy("extra")
    (d / "docs" / "EXTRA.md").write_text("not in SHA256SUMS\n")
    (d / "docs" / "README.md").unlink()
    notes["extra"] = {"added": "docs/EXTRA.md", "removed": "docs/README.md"}
    (OUT / "fixtures.json").write_text(json.dumps(notes, indent=1) + "\n")
    print(json.dumps(notes))


if __name__ == "__main__":
    main()
