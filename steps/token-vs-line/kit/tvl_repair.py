"""Repair of projects of a finished token-vs-line run, from the blame files kept on the machine.

Runs in X/repair with the patched measure.py and tvl_run.py (a copy of the files of the kit). For each
project in REPAIR_PROJECTS: measure again from X/work/<p>/blame.tsv.gz (no new blame, no clone), leak scan,
upload of the project results to results/<p>/. Then the merged tables of the whole run are rebuilt from
the work folders and uploaded to tables-after-repair/ (the tables/ of the run stay as they are); failures.tsv
keeps the rows of the run except those of the repaired projects, and run-info.tsv is the one of the run
plus the rows repair_utc and repaired_projects.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

X = Path(os.environ.get("X", "/data/tvl"))
R = X / "repair"
sys.path.insert(0, str(R))
import tvl_run  # noqa: E402


def main():
    conf = tvl_run.read_conf(R / "tvl.conf")
    lines = (R / "plan.tsv").read_text().splitlines()
    hk = lines[0].split("\t")
    plan = [dict(zip(hk, ln.split("\t"))) for ln in lines[1:] if ln]
    projects = os.environ["REPAIR_PROJECTS"].split()
    run = tvl_run.Run(conf, plan, X)
    run.t_hard = time.time() + 6 * 3600
    run.fetch_root()
    for p in run.state:
        sf = X / "state" / f"{p}.json"
        if sf.exists():
            d = json.loads(sf.read_text())
            run.state[p] = d.pop("state")
            run.info[p].update(d)
    tmp = R / "orig-tables"
    tmp.mkdir(exist_ok=True)
    pre = run.run_prefix()
    for n in ("failures.tsv", "run-info.tsv"):
        run.s3("cp", f"{pre}/tables/{n}", str(tmp / n))
    for ln in (tmp / "failures.tsv").read_text().splitlines()[1:]:
        f = ln.split("\t")
        if len(f) >= 7 and f[0] not in projects:
            run.failures.append(tuple(f[:6]) + ("\t".join(f[6:]),))
    shutil.copytree(X / "tables", X / "tables.before-repair", dirs_exist_ok=True)
    bad = []
    for p in projects:
        run.log(f"REPAIR {p}: was {run.state[p]}")
        repo = X / "pinned" / f"{p}.git"
        tom = X / "tom" / f"{p}-dataset.parquet"
        work = X / "work" / p
        if not (work / "blame-meta.tsv").exists():
            bad.append(p)
            run.log(f"REPAIR {p}: no blame files, skipped")
            continue
        if run.measure(p, repo, tom, run.info[p]["run_commit"], work):
            run.upload_project(p, work)
        if run.state[p] != "done":
            bad.append(p)
    tabs = run.merge_tables()
    info = (tmp / "run-info.tsv").read_text().rstrip("\n") + (
        f"\nrepair_utc\t{tvl_run.utc()}\nrepaired_projects\t{' '.join(p for p in projects if p not in bad)}\n")
    (X / "tables" / "run-info.tsv").write_text(info)
    hits = run.leak_scan(tabs)
    if hits:
        run.log(f"LEAK SCAN HOLD tables: {hits}")
        bad.append("tables")
    else:
        for f in tabs:
            run.s3("cp", str(f), f"{pre}/tables-after-repair/{f.name}")
    cnt = {}
    for s in run.state.values():
        cnt[s] = cnt.get(s, 0) + 1
    ok = [p for p in projects if p not in bad]
    msg = f"{'ALERT' if bad else 'DONE'} {tvl_run.utc()}: repaired {ok}, not repaired {bad}; states {cnt}"
    run.log(msg)
    st = X / "status" / ("repair.ALERT" if bad else "repair.DONE")
    st.write_text(msg + "\n")
    for g, sub in ((st, "status"), (X / "log" / "run.log", "log")):
        if not run.leak_scan([g]):
            run.s3("cp", str(g), f"{pre}/{sub}/{g.name}")
    print(msg)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
