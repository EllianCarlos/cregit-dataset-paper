#!/usr/bin/env python3
"""error_stratum and p_error of the new link domains of release 1.1.0 (the domain of the one added project), by the error
model of TOM 1.0.0 (local, read only).

    em_newdomain1.py ROWS_TSV TOKENS_TSV OUT_TSV [PRIOR_ROWS_TSV PRIOR_TOKENS_TSV]

ROWS_TSV: the link-schema rows of the new domain(s) (no header; the columns LINK_COLS); TOKENS_TSV: domain, tokens in the new
file. PRIOR_*: the 31 domains of the 8,598-project revision (default new_links.tsv and tokens.tsv next to this script).
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
PUB = Path("KIT-FOLDER/base-docs/organizations/organization_domains.parquet")   # the base table, 10,930 rows (HF revision 5e20f9ff2a18)
LINK_COLS = ["domain", "firm_based_on_domain", "organisation_kind", "match", "matched_domain", "confidence", "source"]


def model(links: Path, x1k: Path):
    d = em.Data(WS, db=DB, links=links, model="v4.7", x1k=x1k)
    ctx = em.compute(d, 2, 20261018, audit=AUDIT, tail_audit=TAIL, column_audit=None)
    n_links = d.q("SELECT count(DISTINCT domain) FROM lc")[0][0]
    rows = em.p_error_rows(ctx["chain"], ctx["P0"], ctx["d_se"])
    em.check_p_error_rows(len(rows), n_links)
    return ctx, rows


def augmented(c, td: Path, name: str, rows: list, toks: dict, label: dict):
    la = td / f"links-{name}"
    la.mkdir()
    lsrc = f"read_parquet('{LINKS / 'domain_links.parquet'}')"
    cols = [r[0] for r in c.execute(f"DESCRIBE SELECT * FROM {lsrc}").fetchall()]
    assert cols == LINK_COLS, cols
    c.execute(f"CREATE OR REPLACE TABLE nl (domain VARCHAR, firm_based_on_domain VARCHAR, organisation_kind VARCHAR, match VARCHAR, "
              "matched_domain VARCHAR, confidence VARCHAR, source VARCHAR)")
    c.executemany("INSERT INTO nl VALUES (?, ?, ?, ?, ?, ?, ?)", [[r[k] or None for k in LINK_COLS] for r in rows])
    c.execute(f"COPY (SELECT * FROM {lsrc} UNION ALL SELECT * FROM nl ORDER BY domain) TO '{la / 'domain_links.parquet'}' (FORMAT PARQUET)")
    for f in ("project_links.parquet", "links.json", "enterprise_audit.parquet"):
        (la / f).symlink_to(LINKS / f)
    xa = td / f"x1k-{name}.parquet"
    c.execute("CREATE OR REPLACE TABLE nt (project VARCHAR, domain VARCHAR, tokens BIGINT)")
    c.executemany("INSERT INTO nt VALUES (?, ?, ?)", [[label[d], d, t] for d, t in sorted(toks.items())])
    xcols = [r[0] for r in c.execute(f"DESCRIBE SELECT * FROM read_parquet('{X1K}')").fetchall()]
    sel = ", ".join(f"nt.{x}" if x in ("project", "domain", "tokens") else f"NULL AS {x}" for x in xcols)
    c.execute(f"COPY (SELECT * FROM read_parquet('{X1K}') UNION ALL BY NAME SELECT {sel} FROM nt) TO '{xa}' (FORMAT PARQUET)")
    return la, xa


def main() -> int:
    here = Path(__file__).resolve().parent
    args = sys.argv[1:]
    rows_tsv, tok_tsv, out_tsv = map(Path, args[0:3])
    prior_rows_tsv = Path(args[3]) if len(args) > 3 else here / "new_links.tsv"
    prior_tok_tsv = Path(args[4]) if len(args) > 4 else here / "tokens.tsv"
    new = [dict(zip(LINK_COLS, r)) for r in csv.reader(rows_tsv.open(), delimiter="\t")]
    tok = {r[0]: int(r[1]) for r in csv.reader(tok_tsv.open(), delimiter="\t")}
    prior = [dict(zip(LINK_COLS, r)) for r in csv.reader(prior_rows_tsv.open(), delimiter="\t")]
    ptok = {r[0]: int(r[1]) for r in csv.reader(prior_tok_tsv.open(), delimiter="\t")}
    assert len(prior) == 31 and set(ptok) == {r["domain"] for r in prior}, "prior rows and tokens"
    assert new and set(tok) == {r["domain"] for r in new} and not ({r["domain"] for r in new} & set(ptok)), "rows and tokens"
    c = duckdb.connect()
    pl = ", ".join("'" + d.replace("'", "''") + "'" for d in ptok)
    c.execute(f"CREATE VIEW basetab AS SELECT * FROM read_parquet('{PUB}')")
    c.execute(f"CREATE VIEW tom4tab AS SELECT * FROM basetab WHERE domain NOT IN ({pl})")
    nb, n4 = c.execute("SELECT (SELECT count(*) FROM basetab), (SELECT count(*) FROM tom4tab)").fetchone()
    print(f"base table {nb} rows; without the {len(ptok)} domains of the 8,598-project revision: {n4}")
    if nb - n4 != len(ptok) or c.execute(f"SELECT count(*) FROM basetab WHERE domain IN ({', '.join(repr(x) for x in [r['domain'] for r in new])})").fetchone()[0]:
        return 1
    # ---- 1. the published run (the first 10,899 rows)
    ctx0, rows0 = model(LINKS, X1K)
    pe = next(p for p in (EM / "organization_domains_p_error.parquet", EM / "organisation_domains_p_error.parquet") if p.exists())
    pub_pe = c.execute(f"SELECT key_hash, regexp_replace(error_stratum, 'organis', 'organiz', 'g'), p_error "
                       f"FROM read_parquet('{pe}') ORDER BY 1").fetchall()
    mine = sorted(rows0)
    diff = sum(1 for a, b in zip(mine, pub_pe) if a != b) + abs(len(mine) - len(pub_pe))
    print(f"proof 1a: p_error rows {len(mine)}, published {len(pub_pe)}, rows that differ {diff}")
    if diff:
        return 1
    c.execute("CREATE TABLE m (key_hash VARCHAR, error_stratum VARCHAR, p_error DOUBLE)")
    c.executemany("INSERT INTO m VALUES (?, ?, ?)", mine)
    q = f"""SELECT count(*), count(m.key_hash),
              count(*) FILTER (WHERE m.error_stratum IS DISTINCT FROM t.error_stratum),
              count(*) FILTER (WHERE m.p_error IS DISTINCT FROM t.p_error),
              count(*) FILTER (WHERE {bo.review_path_sql('m.error_stratum', 't.source')} IS DISTINCT FROM t.review_path)
            FROM tom4tab t LEFT JOIN m ON m.key_hash = {bo.key_hash_sql('t.domain')}"""
    n, joined, d_st, d_pe, d_rp = c.execute(q).fetchone()
    print(f"proof 1b: first {n} organization_domains rows, with a model row {joined}; differ: error_stratum {d_st}, p_error {d_pe}, review_path (rule) {d_rp}")
    if n != joined or d_st or d_pe or d_rp:
        return 1
    dd = em.Data(WS, db=DB, links=LINKS, model="v4.7", x1k=X1K)
    lst = ", ".join("'" + r["domain"].replace("'", "''") + "'" for r in new + prior)
    n_ev = dd.q(f"SELECT count(*), coalesce(sum(tokens), 0) FROM tok_ev WHERE domain IN ({lst})")[0]
    n_lc = dd.q(f"SELECT count(*) FROM lc WHERE domain IN ({lst})")[0][0]
    print(f"earlier: the new domains in the model token table: {n_ev[0]} rows, {n_ev[1]} tokens; in the links: {n_lc}")
    if n_ev[1] or n_lc:
        return 1
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # ---- 2. plus the 31 domains of the 8,598-project revision: their rows must be the rows of the base table
        la, xa = augmented(c, td, "prior", prior, ptok, {d: "tom5-new-projects" for d in ptok})
        ctx1, rows1 = model(la, xa)
        by1 = {r[0]: r for r in rows1}
        old_changed1 = sum(1 for r in rows0 if by1.get(r[0]) != r)
        pub31 = {r[0]: r for r in c.execute(f"SELECT {bo.key_hash_sql('domain')}, error_stratum, p_error FROM basetab WHERE domain IN ({pl})").fetchall()}
        diff31 = sum(1 for k, r in pub31.items() if by1.get(k) is None or by1[k][1:] != (r[1], r[2]))
        print(f"proof 2: rows {len(rows1)} = {len(rows0)} + {len(rows1) - len(rows0)}; first rows changed {old_changed1}; "
              f"the {len(pub31)} rows of the 8,598-project revision that differ from the base table {diff31}")
        if old_changed1 or diff31 or len(rows1) - len(rows0) != len(ptok):
            return 1
        # ---- 3. plus the new domain(s)
        la2, xa2 = augmented(c, td, "all", prior + new, {**ptok, **tok}, {**{d: "tom5-new-projects" for d in ptok}, **{d: "tom6-new-project" for d in tok}})
        ctx2, rows2 = model(la2, xa2)
    by2 = {r[0]: r for r in rows2}
    old_changed2 = sum(1 for r in rows1 if by2.get(r[0]) != r)
    print(f"proof 3: rows {len(rows2)} = {len(rows1)} + {len(rows2) - len(rows1)}; earlier rows changed {old_changed2}")
    if old_changed2 or len(rows2) - len(rows1) != len(new):
        return 1
    ch = {r["domain"]: r for r in ctx2["chain"] if r["domain"] in tok}
    out = []
    for r in sorted(new, key=lambda x: x["domain"]):
        x = ch[r["domain"]]
        kh, st, p = by2[em.key_hash(r["domain"])]
        assert x["tokens"] == tok[r["domain"]] and x["o41"] == r["firm_based_on_domain"], r["domain"]
        rp = c.execute(f"SELECT {bo.review_path_sql('s', 'src')} FROM (SELECT ?::VARCHAR s, ?::VARCHAR src)", [st, r["source"]]).fetchone()[0]
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
