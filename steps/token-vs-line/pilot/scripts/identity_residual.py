"""Share of blamed lines whose commit author has no token in TOM (needs a person
database), and whose commit is not in TOM (needs more than a commit lookup).

    python3 -I identity_residual.py > ../tables/identity-residual.tsv
"""


import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))

import measure

HERE = Path(__file__).resolve().parent.parent
con = duckdb.connect()
con.execute("SET threads = 2; SET memory_limit = '4GB'")
print("project\tlines\tlines_commit_not_in_tom\tlines_person_not_in_tom")
for p in [l.split("\t")[0] for l in (HERE / "sample.tsv").read_text().splitlines()[1:]]:
    rows, _ = measure.commits_table(p)
    con.execute("CREATE OR REPLACE TABLE c (sha VARCHAR, pid VARCHAR, dom VARCHAR)")
    con.executemany("INSERT INTO c VALUES (?, ?, ?)", rows)
    tom = measure.SCRATCH / "hf-tom" / "parquet" / f"{p}-dataset.parquet"
    con.execute(f"CREATE OR REPLACE TABLE ts AS SELECT DISTINCT original_commit_sha sha FROM read_parquet('{tom}') WHERE is_structural = 0")
    con.execute("CREATE OR REPLACE TABLE tp AS SELECT DISTINCT c.pid FROM ts JOIN c USING (sha)")
    r = con.execute(f"""SELECT count(*), count(*) FILTER (b.sha_plain NOT IN (SELECT sha FROM ts)),
                               count(*) FILTER (c.pid NOT IN (SELECT pid FROM tp))
                        FROM read_csv('{HERE / 'work' / p / 'blame.tsv.gz'}', delim='\t', header=true, quote='',
                                      escape='', all_varchar=true) b JOIN c ON c.sha = b.sha_plain""").fetchone()
    print(p, *r, sep="\t")
