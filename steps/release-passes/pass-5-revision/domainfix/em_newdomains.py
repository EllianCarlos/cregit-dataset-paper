#!/usr/bin/env python3
"""error_stratum and p_error of the new link domains of TOM-5, by the error model of TOM 1.0.0 (local, read only).

    em_newdomains.py ROWS_TSV TOKENS_TSV OUT_TSV

The model is s8-companies/error_model.py (model v4.7) on the inputs of the published run
error-model-v4.9-final-20261027 (database companies.v4.9.duckdb, the links of the final write, the x1k
counts, the audit sample and the tail audit, no column audit). Two runs in one process:

  1. the published inputs: p_error_rows must equal organization_domains_p_error.parquet of that run row
     for row (key_hash, error_stratum, p_error), and the error_stratum, p_error and review_path of the
     published organization_domains table (TOM-4, 10,899 rows) must follow from them;
  2. the same inputs plus the new links (ROWS_TSV, the link schema) and their tokens in the new files
     (TOKENS_TSV, an x1k-style token table): the rows of the old links must not change; the rows of the
     new links are the answer.

OUT_TSV: domain, organization_id, match, matched_domain, confidence, source, review_path, error_stratum,
p_error (repr), plus the path fields origin, band, later, skey for the record.
"""
import csv
import sys
import tempfile
from pathlib import Path

S8 = Path("STUDY-CHECKOUT/dataset-selection/s8-companies")
sys.path.insert(0, str(S8))
import duckdb  # noqa: E402
import error_model as em  # noqa: E402
import build_organizations as bo  # noqa: E402

WS = em.WS_DEFAULT
EM = WS / "error-model-v4.9-final-20261027"
DB = WS / "companies.v4.9.duckdb"
LINKS = Path("WORKSPACE-FOLDER/final-work/dataset-final-2/m0/links-final")
X1K = WS / em.DEFAULTS["v4.7"]["x1k"]
AUDIT = WS / em.AUDIT_SAMPLE_DEFAULT
TAIL = WS / em.TAIL_AUDIT_DEFAULT
PUB = Path("WORK-FOLDER/zenodo-company/record/organization_domains.parquet")   # = TOM-4 (sha256 831e0163)
LINK_COLS = ["domain", "firm_based_on_domain", "organisation_kind", "match", "matched_domain", "confidence", "source"]


def model(links: Path, x1k: Path):
    d = em.Data(WS, db=DB, links=links, model="v4.7", x1k=x1k)
    ctx = em.compute(d, 2, 20261018, audit=AUDIT, tail_audit=TAIL, column_audit=None)
    n_links = d.q("SELECT count(DISTINCT domain) FROM lc")[0][0]
    rows = em.p_error_rows(ctx["chain"], ctx["P0"], ctx["d_se"])
    em.check_p_error_rows(len(rows), n_links)
    return ctx, rows


def main() -> int:
    rows_tsv, tok_tsv, out_tsv = map(Path, sys.argv[1:4])
    new = [dict(zip(LINK_COLS, r)) for r in csv.reader(rows_tsv.open(), delimiter="\t")]
    tok = {r[0]: int(r[1]) for r in csv.reader(tok_tsv.open(), delimiter="\t")}
    assert len(new) == 31 and set(tok) == {r["domain"] for r in new}, "rows and tokens"
    c = duckdb.connect()
    # ---- 1. the published run
    ctx0, rows0 = model(LINKS, X1K)
    pe = next(p for p in (EM / "organization_domains_p_error.parquet", EM / "organisation_domains_p_error.parquet") if p.exists())
    pub_pe = c.execute(f"SELECT key_hash, regexp_replace(error_stratum, 'organis', 'organiz', 'g'), p_error "
                       f"FROM read_parquet('{pe}') ORDER BY 1").fetchall()
    mine = sorted(rows0)
    diff = sum(1 for a, b in zip(mine, pub_pe) if a != b) + abs(len(mine) - len(pub_pe))
    print(f"proof 1a: p_error rows {len(mine)}, published {len(pub_pe)}, rows that differ {diff}")
    if diff:
        for a, b in [(a, b) for a, b in zip(mine, pub_pe) if a != b][:5]:
            print("   mine", a, "published", b)
        return 1
    c.execute("CREATE TABLE m (key_hash VARCHAR, error_stratum VARCHAR, p_error DOUBLE)")
    c.executemany("INSERT INTO m VALUES (?, ?, ?)", mine)
    q = f"""SELECT count(*), count(m.key_hash),
              count(*) FILTER (WHERE m.error_stratum IS DISTINCT FROM t.error_stratum),
              count(*) FILTER (WHERE m.p_error IS DISTINCT FROM t.p_error),
              count(*) FILTER (WHERE {bo.review_path_sql('m.error_stratum', 't.source')} IS DISTINCT FROM t.review_path)
            FROM read_parquet('{PUB}') t LEFT JOIN m ON m.key_hash = {bo.key_hash_sql('t.domain')}"""
    n, joined, d_st, d_pe, d_rp = c.execute(q).fetchone()
    print(f"proof 1b: TOM-4 organization_domains {n} rows, with a model row {joined}; differ: error_stratum {d_st}, "
          f"p_error {d_pe}, review_path (rule) {d_rp}")
    if n != joined or d_st or d_pe or d_rp:
        return 1
    # the earlier tokens of the new domains (version 1 cache + x1k counts) must be 0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        dd = em.Data(WS, db=DB, links=LINKS, model="v4.7", x1k=X1K)
        lst = ", ".join("'" + r["domain"].replace("'", "''") + "'" for r in new)
        n_ev = dd.q(f"SELECT count(*), coalesce(sum(tokens), 0) FROM tok_ev WHERE domain IN ({lst})")[0]
        n_lc = dd.q(f"SELECT count(*) FROM lc WHERE domain IN ({lst})")[0][0]
        print(f"earlier: the new domains in the model token table: {n_ev[0]} rows, {n_ev[1]} tokens; in the links: {n_lc}")
        if n_ev[1] or n_lc:
            return 1
        # ---- 2. the published inputs plus the new links and their tokens
        la = td / "links-aug"
        la.mkdir()
        lsrc = f"read_parquet('{LINKS / 'domain_links.parquet'}')"
        cols = [r[0] for r in c.execute(f"DESCRIBE SELECT * FROM {lsrc}").fetchall()]
        print("links-final domain_links columns:", cols)
        assert cols == LINK_COLS, cols
        c.execute("CREATE TABLE nl (domain VARCHAR, firm_based_on_domain VARCHAR, organisation_kind VARCHAR, match VARCHAR, "
                  "matched_domain VARCHAR, confidence VARCHAR, source VARCHAR)")
        c.executemany("INSERT INTO nl VALUES (?, ?, ?, ?, ?, ?, ?)", [[r[k] or None for k in LINK_COLS] for r in new])
        c.execute(f"COPY (SELECT * FROM {lsrc} UNION ALL SELECT * FROM nl ORDER BY domain) TO '{la / 'domain_links.parquet'}' (FORMAT PARQUET)")
        for f in ("project_links.parquet", "links.json", "enterprise_audit.parquet"):
            (la / f).symlink_to(LINKS / f)
        xa = td / "x1k-aug.parquet"
        c.execute("CREATE TABLE nt (project VARCHAR, domain VARCHAR, tokens BIGINT)")
        c.executemany("INSERT INTO nt VALUES ('tom5-new-projects', ?, ?)", sorted(tok.items()))
        xcols = [r[0] for r in c.execute(f"DESCRIBE SELECT * FROM read_parquet('{X1K}')").fetchall()]
        sel = ", ".join(f"nt.{x}" if x in ("project", "domain", "tokens") else f"NULL AS {x}" for x in xcols)
        c.execute(f"COPY (SELECT * FROM read_parquet('{X1K}') UNION ALL BY NAME SELECT {sel} FROM nt) TO '{xa}' (FORMAT PARQUET)")
        ctx1, rows1 = model(la, xa)
    by1 = {r[0]: r for r in rows1}
    old_changed = sum(1 for r in rows0 if by1.get(r[0]) != r)
    print(f"proof 2: rows {len(rows1)} = {len(rows0)} + {len(rows1) - len(rows0)}; old rows changed {old_changed}")
    if old_changed or len(rows1) - len(rows0) != 31:
        return 1
    ch = {r["domain"]: r for r in ctx1["chain"] if r["domain"] in tok}
    out = []
    for r in sorted(new, key=lambda x: x["domain"]):
        x = ch[r["domain"]]
        kh, st, p = by1[em.key_hash(r["domain"])]
        assert x["tokens"] == tok[r["domain"]] and x["o41"] == r["firm_based_on_domain"], r["domain"]
        rp = c.execute(f"SELECT {bo.review_path_sql('s', 'src')} FROM (SELECT ?::VARCHAR s, ?::VARCHAR src)",
                       [st, r["source"]]).fetchone()[0]
        out.append([r["domain"], r["firm_based_on_domain"], r["match"], r["matched_domain"], r["confidence"], r["source"],
                    rp, st, repr(p), x["origin"], x["band"], "+".join(x["later"]) or "-", "|".join(x["skey"])])
    with out_tsv.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["domain", "organization_id", "match", "matched_domain", "confidence", "source", "review_path",
                    "error_stratum", "p_error", "origin", "band", "later", "skey"])
        w.writerows(out)
    for r in out:
        print("NEW", *r, sep="\t")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
