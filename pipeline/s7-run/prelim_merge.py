#!/usr/bin/env python3
"""Build a preliminary DuckDB file over the census Parquets that are on this machine now.

    PY=$CREGIT_PROJECTS/cregit-workspace/census-local-a/ctp/.venv/bin/python   # has duckdb 1.5.5
    $PY -I prelim_merge.py [--out $CREGIT_PROJECTS/cregit-workspace/merge-prelim/prelim.duckdb]

This is not the final merge (task 6). It copies no token data: the view `tokens` reads the Parquet
files in place. Run it again to add the projects that arrived since (census-fetch timer, footer-fix).

Sources, one candidate per project directory <owner>__<repo>:
  local-a/b/c/d      census-local-{a,b,c,d}/<wl>[/<part>]/done/<p>/ (reruns; OK needed)
  fixed              census-cloud-fixed/<rel>/  (95cdc88 runs after the trailer post-fix; status ok)
  cloud              census-cloud/<run>/.../done/<p>/  (only with .checked: sha256 equal to OK)
  batch1-local       census-2026-10/<p>/  (cregit 157cf8b, old srcML: must be retokenized)
One project, several candidates: the lowest rank wins, then the newest file.
  rank 0 local-a/b/c/d, rank 1 cloud with cregit 1f17663/57551d7 or fixed,
  rank 2 cloud 95cdc88 without the post-fix, rank 3 batch1-local.
Excluded (user decisions): discovery-artifact-manager, freeswitch, BRL-CAD.

Tables: projects (the chosen file per project, with flags), candidates (all files found),
frame (the v1 projects: 3,497, plus the 50 GitLab rows of batch 25 and the 1 row of batch 26 since 2026-10-14:
3,548), view frame_status (in prelim / pending / excluded), view tokens (all chosen Parquets, union_by_name). Not yet applied: the 11-column metadata rewrite
(rewrite_meta_columns.py; for example owner of the 25 Savannah rows, NOASSERTION licenses).
"""
import argparse
import json
import os
import sys
from pathlib import Path

import duckdb

W = Path.home() / "Projects/cregit-workspace"
EXCLUDED = {"googleapis__discovery-artifact-manager": "no in-scope source at HEAD",
            "signalwire__freeswitch": "blobExec NPE (commit without committer)",
            "BRL-CAD__brlcad": "repository gone (owners contacted)"}
OLD_RUNS = {"batch1rest", "batch2", "batch3", "batch3L", "batch4", "batch5", "batch5L", "batch6",
            "batch6L"}  # 95cdc88 (batch6 fed parts: 9ccead6, same output)
DS = Path(__file__).resolve().parent
FRAME = [DS / "project_meta.layer1.final.json",  # 3,379 layer 1 rows + 118 batch 23 rows = v1
         Path.home() / "s3-work/ec2-batch23/upload/project_meta.batch23.json",
         Path.home() / "s3-work/ec2-batch23/upload/project_meta.batch23L.json",
         DS / "project_meta.batch25.json",  # batch 25: the 50 GitLab rows (2026-10-14), v1 = 3,547
         DS / "project_meta.batch26.json"]  # batch 26: gitlab.com/muttmua/mutt (2026-10-14), v1 = 3,548
RUN_CREGIT = {"L7-20": "1f17663", "L22": "1f17663", "L7-20b": "1f17663", "L23": "57551d7",
              "L1r": "57551d7",
              "batch24": "57551d7", "batch25": "57551d7", "batch26": "57551d7"}  # runbooks; done/ has no ledger
# (batch24/25/26: fed, has one)


def cregit_of(d: Path) -> str:
    for name in ("ledger.jsonl", "ledger.from-run.jsonl"):
        f = d / name
        if not f.is_file():
            continue
        c = ""
        with open(f, errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                c = ((r.get("tools") or {}).get("cregit_commit") or c)
        if c:
            return c[:7]
    return ""


def parquet_in(d: Path):
    p = d / f"{d.name}-dataset.parquet"
    return p if p.is_file() else None


def scan():
    cands = []
    for lx in ("local-a", "local-b", "local-c", "local-d"):  # local-c: the batch 1 rerun (2026-10-12);
        # local-d: connectionlens with cregit 23e4ccb (2026-10-14)
        root = W / f"census-{lx}"
        for d in [*root.glob("*/done/*"), *root.glob("*/*/done/*")]:
            p = parquet_in(d)
            if p and (d / "OK").is_file():
                cands.append(dict(project=d.name, source=lx, run=str(d.relative_to(root).parent.parent),
                                  path=str(p), cregit=cregit_of(d), trailer_fixed=True, rank=0))
    fx = W / "census-cloud-fixed"
    ok = {}
    if (fx / "manifest.tsv").is_file():
        with open(fx / "manifest.tsv") as fh:
            hdr = fh.readline().rstrip("\n").split("\t")
            for line in fh:
                r = dict(zip(hdr, line.rstrip("\n").split("\t")))
                ok[r["rel_path"]] = r  # the last row per rel_path counts
    for rel, r in ok.items():
        if r.get("status") != "ok":
            continue
        d = fx / rel
        p = parquet_in(d)
        if p:
            cands.append(dict(project=d.name, source="fixed", run=rel.split("/done/")[0], path=str(p),
                              cregit=(r.get("cregit") or "95cdc88").replace("noledger", "95cdc88"),
                              trailer_fixed=True, rank=1))
    cc = W / "census-cloud"
    for chk in cc.glob("**/done/*/.checked"):
        d = chk.parent
        p = parquet_in(d)
        if not p:
            continue
        run = str(d.relative_to(cc)).split("/done/")[0]
        top = run.split("/")[0]
        c = cregit_of(d) or RUN_CREGIT.get(top) or ("95cdc88" if top in OLD_RUNS else "")
        new = c in ("1f17663", "57551d7")
        cands.append(dict(project=d.name, source="cloud", run=run, path=str(p), cregit=c,
                          trailer_fixed=new, rank=1 if new else 2))
    b1 = W / "census-2026-10"
    for d in b1.iterdir() if b1.is_dir() else []:
        p = parquet_in(d)
        if p:
            cands.append(dict(project=d.name, source="batch1-local", run="batch1-local", path=str(p),
                              cregit="157cf8b", trailer_fixed=False, rank=3))
    for c in cands:
        c["mtime"] = os.path.getmtime(c["path"])
        c["excluded"] = EXCLUDED.get(c["project"], "")
    return cands


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(W / "merge-prelim/prelim.duckdb"))
    a = ap.parse_args()
    cands = scan()
    best = {}
    for c in sorted(cands, key=lambda c: (c["rank"], -c["mtime"])):
        best.setdefault(c["project"], c)
    chosen = [c for c in best.values() if not c["excluded"]]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.duckdb")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    cols = ["project", "source", "run", "path", "cregit", "trailer_fixed", "rank", "mtime", "excluded"]
    con.execute("CREATE TABLE candidates (project VARCHAR, source VARCHAR, run VARCHAR, path VARCHAR, "
                "cregit VARCHAR, trailer_fixed BOOLEAN, rank INT, mtime DOUBLE, excluded VARCHAR)")
    con.executemany("INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?)", [[c[k] for k in cols] for c in cands])
    con.execute("ALTER TABLE candidates ADD COLUMN chosen BOOLEAN DEFAULT false")
    con.executemany("UPDATE candidates SET chosen = true WHERE path = ?", [[c["path"]] for c in chosen])
    paths = sorted(c["path"] for c in chosen)
    lit = "[" + ",".join("'" + x.replace("'", "''") + "'" for x in paths) + "]"
    con.execute(f"""CREATE TABLE projects AS
        SELECT c.project, c.source, c.run, c.path, c.cregit, c.trailer_fixed,
               c.source = 'batch1-local' AS needs_retokenize,
               (SELECT count(*) FROM candidates x WHERE x.project = c.project) AS n_candidates,
               m.num_rows AS token_rows, to_timestamp(c.mtime) AS file_time
        FROM candidates c
        JOIN (SELECT file_name, num_rows FROM parquet_file_metadata({lit})) m ON m.file_name = c.path
        WHERE c.chosen ORDER BY c.project""")
    con.execute(f"CREATE VIEW tokens AS SELECT * FROM read_parquet({lit}, union_by_name = true)")
    frame = set()
    for f in FRAME:
        frame |= set(json.load(open(f)))
    con.execute("CREATE TABLE frame (project VARCHAR PRIMARY KEY)")
    con.executemany("INSERT INTO frame VALUES (?)", [[x] for x in sorted(frame)])
    con.execute("""CREATE VIEW frame_status AS SELECT f.project,
        CASE WHEN p.project IS NOT NULL THEN 'in prelim' WHEN f.project IN ({ex}) THEN 'excluded'
             ELSE 'pending' END AS status, p.run, p.source
        FROM frame f LEFT JOIN projects p USING (project)""".format(
        ex=",".join("'" + x + "'" for x in EXCLUDED)))
    outside = con.execute("SELECT count(*) FROM projects WHERE project NOT IN (SELECT project FROM frame)").fetchone()[0]
    st = dict(con.execute("SELECT status, count(*) FROM frame_status GROUP BY 1").fetchall())
    n, rows = con.execute("SELECT count(*), sum(token_rows) FROM projects").fetchone()
    by = con.execute("SELECT source, cregit, count(*), sum(token_rows) FROM projects GROUP BY ALL ORDER BY ALL").fetchall()
    dup = con.execute("SELECT count(*) FROM projects WHERE n_candidates > 1").fetchone()[0]
    con.close()
    os.replace(tmp, out)
    print(f"{out}: {n} projects, {rows:,} token rows, {len(cands)} candidate files, {dup} projects with >1 file")
    for s, c, k, r in by:
        print(f"  {s:13} {c:8} {k:5} projects {r:>15,} rows")
    print(f"v1 frame {len(frame)}: {st}; chosen projects outside the frame: {outside}")
    print("excluded:", ", ".join(sorted({c['project'] for c in cands if c['excluded']})) or "none found")


if __name__ == "__main__":
    sys.exit(main())
