"""Tests of brlcad_tools.py (kit dataset-brlcad). Local only, synthetic data, a throw-away salt.

    python3 -m pytest -q test

The stage tools come from ~/s3-work/dataset-final/stage (the tools of the final write): build_links.py,
build_v0.py, the database v4.9, anon/pseudonymize.py (ctp-anon 4be3800) and the PSL.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

K = Path(__file__).resolve().parent.parent
FINAL = Path(os.environ.get("FINAL_STAGE_DIR", "FINAL_STAGE_DIR-is-not-set"))
DS = Path(os.environ.get("STUDY_DATASET_SELECTION", "STUDY_DATASET_SELECTION-is-not-set"))


def ctp_dir_ok() -> bool:
    return Path(os.environ.get("CTP_DIR", "CTP_DIR-is-not-set")).is_dir()

sys.path.insert(0, str(K))
import brlcad_tools as B  # noqa: E402

if not ((FINAL / "anon").is_dir() and DS.is_dir() and ctp_dir_ok()):
    pytest.skip("set FINAL_STAGE_DIR, STUDY_DATASET_SELECTION and CTP_DIR (see ../../README.md)", allow_module_level=True)

AT = chr(64)
DB = FINAL / "companies.v4.9.duckdb"
PSL = FINAL / "public_suffix_list.dat"


def anon():
    sys.path.insert(0, str(FINAL / "anon"))
    return B.load(FINAL / "anon/pseudonymize.py", "pseudonymize")


# ------------------------------------------------------------------ registry-merge

def salt(tmp: Path, name: str) -> Path:
    p = tmp / name
    p.write_bytes(os.urandom(32).hex().encode())
    p.chmod(0o600)
    return p


def raw_files(tmp: Path, P) -> list[str]:
    con = duckdb.connect()
    out = []
    # overlapping people: file 3 shares people 0-299 with the others and adds new ones
    for i, (rows, people, seed, sfx) in enumerate([(4000, 300, "one", "example"), (3000, 200, "two", "example"),
                                                   (5000, 700, "three", "example")]):
        f = tmp / f"raw{i}.parquet"
        P.make_synthetic(con, str(f), rows, schema2=False, people=people, seed_text=seed, domain_suffix=sfx)
        out.append(str(f))
    return out


def registry(P, paths, keys, out: Path) -> dict:
    return P.build_registry(paths, keys, str(out), memory_limit="2GB", threads=2, psl=str(PSL),
                            out=open(os.devnull, "w"))


def test_registry_merge_equals_one_run_over_all_files(tmp_path):
    P = anon()
    s = salt(tmp_path, "salt")
    keys = P.derive_keys(P.A.load_salt(path=str(s), env={}))
    files = raw_files(tmp_path, P)
    priv = tmp_path / "priv"
    priv.mkdir(mode=0o700)
    registry(P, files[:2], keys, priv / "a.parquet")
    registry(P, files[2:], keys, priv / "c.parquet")
    full = registry(P, files, keys, priv / "full.parquet")
    rc = B.main(["registry-merge", "--a", str(priv / "a.parquet"), "--c", str(priv / "c.parquet"),
                 "--out", str(priv / "b.parquet"), "--anon-dir", str(FINAL / "anon"), "--salt-file", str(s),
                 "--psl", str(PSL), "--report", str(tmp_path / "rep.json"), "--memory-limit", "2GB"])
    assert rc == 0
    con = duckdb.connect()
    kv = lambda f: dict(con.execute("SELECT decode(key), decode(value) FROM parquet_kv_metadata(?)", [f]).fetchall())
    kb, kf = kv(str(priv / "b.parquet")), kv(str(priv / "full.parquet"))
    assert kb == kf                                   # the same footer, files = 3
    assert kb["registry_sha256"] == full["registry_sha256"]
    diff = con.execute(f"SELECT count(*) FROM (SELECT * FROM '{priv}/b.parquet' EXCEPT SELECT * FROM '{priv}/full.parquet')"
                       f" UNION ALL SELECT count(*) FROM (SELECT * FROM '{priv}/full.parquet' EXCEPT SELECT * FROM "
                       f"'{priv}/b.parquet')").fetchall()
    assert diff == [(0,), (0,)]                       # every row, the anchors too
    assert oct((priv / "b.parquet").stat().st_mode & 0o777) == "0o600"
    rep = json.loads((tmp_path / "rep.json").read_text())
    assert rep["collisions"] == 0 and sum(rep["new_in_b"].values()) > 0


def test_registry_merge_refuses_another_salt(tmp_path):
    P = anon()
    s1, s2 = salt(tmp_path, "s1"), salt(tmp_path, "s2")
    files = raw_files(tmp_path, P)
    priv = tmp_path / "priv"
    priv.mkdir(mode=0o700)
    registry(P, files[:2], P.derive_keys(P.A.load_salt(path=str(s1), env={})), priv / "a.parquet")
    registry(P, files[2:], P.derive_keys(P.A.load_salt(path=str(s2), env={})), priv / "c.parquet")
    rc = B.main(["registry-merge", "--a", str(priv / "a.parquet"), "--c", str(priv / "c.parquet"),
                 "--out", str(priv / "b.parquet"), "--anon-dir", str(FINAL / "anon"), "--salt-file", str(s1),
                 "--psl", str(PSL)])
    assert rc == 1 and not (priv / "b.parquet").exists()


def test_registry_merge_refuses_a_wrong_pin(tmp_path):
    P = anon()
    s = salt(tmp_path, "salt")
    keys = P.derive_keys(P.A.load_salt(path=str(s), env={}))
    files = raw_files(tmp_path, P)
    priv = tmp_path / "priv"
    priv.mkdir(mode=0o700)
    registry(P, files[:2], keys, priv / "a.parquet")
    registry(P, files[2:], keys, priv / "c.parquet")
    rc = B.main(["registry-merge", "--a", str(priv / "a.parquet"), "--c", str(priv / "c.parquet"),
                 "--out", str(priv / "b.parquet"), "--anon-dir", str(FINAL / "anon"), "--salt-file", str(s),
                 "--psl", str(PSL), "--want-a", "0" * 64])
    assert rc == 1


# ------------------------------------------------------------------ links-merge

PROJECTS = {"p__one": ("github.com", "brl-cad", "brlcad"), "p__two": ("github.com", "someone", "two"),
            "p__new": ("github.com", "BRL-CAD", "brlcad-new")}


def sidecar(tmp: Path) -> Path:
    d = {p: {"clone_url": f"https://{h}/{o}/{r}.git", "owner": o, "repo": r} for p, (h, o, r) in PROJECTS.items()}
    f = tmp / "sidecar.json"
    f.write_text(json.dumps(d))
    return f


def cache(tmp: Path, name: str, rows: list[tuple]) -> Path:
    """rows: (project, domain, local part, tokens, commits)."""
    d = tmp / name
    d.mkdir()
    con = duckdb.connect()
    for p in sorted({r[0] for r in rows}):
        vals = [r for r in rows if r[0] == p]
        con.execute("CREATE OR REPLACE TABLE t (project VARCHAR, domain VARCHAR, email VARCHAR, committer_domain VARCHAR, "
                    "tokens BIGINT, commits BIGINT, first_date VARCHAR, last_date VARCHAR)")
        for pr, dom, loc, tok, com in vals:
            con.execute("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?, '2020-01-01', '2021-01-01')",
                        [pr, dom, f"{loc}{AT}{dom}" if dom else loc, dom, tok, com])
        con.execute(f"COPY t TO '{d}/{p}.parquet' (FORMAT PARQUET)")
    return d


OLD = [("p__one", "gmail.com", "a", 500, 10), ("p__one", "brlcad.org", "b", 300, 30), ("p__one", "", "c", 20, 1),
       ("p__two", "nrl.navy.mil", "d", 400, 20), ("p__two", "no-such-org-xyz.example", "e", 100, 5),
       ("p__two", "redhat.com", "l", 250, 12)]
NEW = [("p__new", "gmail.com", "f", 50, 3), ("p__new", "brlcad.org", "g", 900, 40),
       ("p__new", "cs.nps.navy.mil", "h", 70, 4),      # in the reference table of the final write? (suffix navy.mil)
       ("p__new", "itd.nrl.navy.mil", "i", 60, 2),     # a parent of nrl.navy.mil
       ("p__new", "zz-unmatched-org.example", "j", 30, 1), ("p__new", "", "k", 5, 1),
       ("p__new", "intel.com", "m", 400, 25)]


def build_links(tmp: Path, name: str, caches: list[Path], side: Path, ok: bool = True) -> Path:
    out = tmp / name
    args = [sys.executable, "-I", str(FINAL / "build_links.py"), "--organisations-version", "v4.9", "--db", str(DB),
            "--sidecar", str(side), "--out", str(out), "--memory-limit", "2GB", "--threads", "2"]
    for c in caches:
        args += ["--cache", str(c)]
    r = subprocess.run(args, capture_output=True, text=True)
    assert (r.returncode == 0) == ok, r.stderr[-800:]
    return out


def test_links_merge_gives_the_links_of_one_run_over_all_caches(tmp_path):
    side = sidecar(tmp_path)
    c_old, c_new = cache(tmp_path, "c-old", OLD), cache(tmp_path, "c-new", NEW)
    A = build_links(tmp_path, "A", [c_old], side)
    C = build_links(tmp_path, "C", [c_new], side)
    full = build_links(tmp_path, "full", [c_old, c_new], side)
    rc = B.main(["links-merge", "--tools", str(FINAL), "--a", str(A), "--c", str(C), "--cache", str(c_new),
                 "--project", "p__new", "--db", str(DB), "--out", str(tmp_path / "m"), "--report", str(tmp_path / "rep.txt"),
                 "--memory-limit", "2GB", "--threads", "2"])
    assert rc == 0
    con = duckdb.connect()
    for f in ("domain_links.parquet", "project_links.parquet", "enterprise_audit.parquet"):
        got, want = tmp_path / "m/links-B" / f, full / f
        n = con.execute(f"SELECT (SELECT count(*) FROM (FROM '{got}' EXCEPT FROM '{want}')) + "
                        f"(SELECT count(*) FROM (FROM '{want}' EXCEPT FROM '{got}'))").fetchone()[0]
        assert n == 0, f
    jb, jf = json.loads((tmp_path / "m/links-B/links.json").read_text()), json.loads((full / "links.json").read_text())
    assert jb["mapping_sha256"] == jf["mapping_sha256"]
    for k in ("domain_links", "domain_links_by_kind", "domain_links_by_match", "projects", "projects_by_basis",
              "projects_enterprise_driven", "projects_with_namespace_owner", "projects_by_namespace_owner_kind",
              "total_tokens"):
        assert jb[k] == jf[k], k
    for k in ("token_share_by_kind", "token_share_by_value_class", "token_share_by_reason", "token_share_company_kind"):
        assert B.close(jb[k], jf[k], 1e-12), k
    ja1 = json.loads((tmp_path / "m/links-A1/links.json").read_text())
    ja = json.loads((A / "links.json").read_text())
    assert ja1["mapping_sha256"] == ja["mapping_sha256"]          # A1 keeps the mapping of A
    s = json.loads((tmp_path / "m/links-merge.json").read_text())
    assert s["new_domain_rows"] > 0 and not s["same_mapping"]
    # the value error of links-A1: the tokens of the new rows whose value is not the fallback (here all but the
    # independent kind): intel.com (company) 400, cs.nps.navy.mil and itd.nrl.navy.mil (government) 70 + 60
    con2 = duckdb.connect()
    want = con2.execute(f"SELECT sum(tokens) FROM '{c_new}/*.parquet' WHERE domain IN ('intel.com', 'cs.nps.navy.mil', "
                        "'itd.nrl.navy.mil')").fetchone()[0]
    assert s["a1_value_error_tokens"] == want == 530
    # A1 = A with only the enterprise columns of the added project changed
    n = con.execute(f"SELECT count(*) FROM (FROM '{tmp_path}/m/links-A1/project_links.parquet' EXCEPT "
                    f"FROM '{A}/project_links.parquet')").fetchone()[0]
    assert n <= 1
    assert AT not in (tmp_path / "rep.txt").read_text()


def test_links_merge_with_no_new_domain_keeps_the_mapping(tmp_path):
    side = sidecar(tmp_path)
    only_old = [r for r in NEW if r[1] in ("gmail.com", "brlcad.org", "")]
    c_old, c_new = cache(tmp_path, "c-old", OLD), cache(tmp_path, "c-new", only_old)
    A = build_links(tmp_path, "A", [c_old], side)
    C = build_links(tmp_path, "C", [c_new], side, ok=False)     # no company-kind token: no links.json
    assert not (C / "links.json").exists() and (C / "domain_links.parquet").exists()
    rc = B.main(["links-merge", "--tools", str(FINAL), "--a", str(A), "--c", str(C), "--cache", str(c_new),
                 "--project", "p__new", "--db", str(DB), "--out", str(tmp_path / "m"), "--memory-limit", "2GB"])
    assert rc == 0
    s = json.loads((tmp_path / "m/links-merge.json").read_text())
    ja = json.loads((A / "links.json").read_text())
    assert s["new_domain_rows"] == 0 and s["same_mapping"] and s["links"]["B"]["mapping_sha256"] == ja["mapping_sha256"]
    assert B.sha256(tmp_path / "m/links-B/domain_links.parquet") == B.sha256(A / "domain_links.parquet")


def test_links_merge_refuses_a_changed_a(tmp_path):
    side = sidecar(tmp_path)
    c_old, c_new = cache(tmp_path, "c-old", OLD), cache(tmp_path, "c-new", NEW)
    A = build_links(tmp_path, "A", [c_old], side)
    C = build_links(tmp_path, "C", [c_new], side)
    rc = B.main(["links-merge", "--tools", str(FINAL), "--a", str(A), "--c", str(C), "--cache", str(c_new),
                 "--project", "p__new", "--db", str(DB), "--out", str(tmp_path / "m"), "--want-mapping", "1" * 64])
    assert rc == 1


# ------------------------------------------------------------------ select-check

def gitc(repo: Path, *a: str, env=None) -> str:
    e = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": f"t{AT}example.org", "GIT_COMMITTER_NAME": "T",
         "GIT_COMMITTER_EMAIL": f"t{AT}example.org", "HOME": str(repo.parent), "PATH": os.environ["PATH"]}
    e.update(env or {})
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True, env=e).stdout.strip()


def select_dir(tmp: Path) -> Path:
    d = tmp / "select"
    d.mkdir()
    ctp = Path(os.environ.get("CTP_DIR", "CTP_DIR-is-not-set"))
    (d / "file_mask.py").write_text(subprocess.run(["git", "-C", str(ctp), "show", "91d6ccab:file_mask.py"],
                                                   capture_output=True, text=True, check=True).stdout)
    for f in ("prog_exts.py", "languages.yml"):
        (d / f).write_bytes((DS / "s3-measure" / f).read_bytes())
    (d / "dp8l_rule.py").write_bytes((DS / "s4-filter/dp8l_rule.py").read_bytes())
    return d


def make_repo(tmp: Path) -> tuple[Path, str, str]:
    w = tmp / "work"
    w.mkdir()
    gitc(w, "init", "-q", "-b", "main")
    (w / "src").mkdir()
    (w / "vendor").mkdir()
    (w / "COPYING").write_text("license text\n")
    (w / "src/a.c").write_text("int a;\n" * 50)
    (w / "src/b.tcl").write_text("set x 1\n" * 40)
    (w / "vendor/v.c").write_text("int v;\n" * 10)
    gitc(w, "add", "-A")
    gitc(w, "commit", "-q", "-m", "one", env={"GIT_COMMITTER_DATE": "2026-10-01T00:00:00Z"})
    (w / "src/c.h").write_text("int c;\n" * 5)
    gitc(w, "add", "-A")
    gitc(w, "commit", "-q", "-m", "two", env={"GIT_COMMITTER_DATE": "2026-10-02T00:00:00Z"})
    frame = gitc(w, "rev-parse", "HEAD")
    (w / "src/d.c").write_text("int d;\n" * 5)
    gitc(w, "add", "-A")
    gitc(w, "commit", "-q", "-m", "three", env={"GIT_COMMITTER_DATE": "2026-10-20T00:00:00Z"})
    bare = tmp / "bare.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(w), str(bare)], check=True, capture_output=True)
    return bare, frame, gitc(w, "rev-parse", "HEAD")


def frame_json(tmp: Path, frame: str, sel: Path, bare: Path, commits: int, **over) -> Path:
    import re
    fm = B.load(sel / "file_mask.py", "file_mask")
    pe = B.load(sel / "prog_exts.py", "prog_exts")
    vendor = re.compile(r"(^|/)(vendor|vendored|third_party|third-party|thirdparty|3rdparty|external|deps)/", re.I)
    m = B.count_tree(B.git(bare, "ls-tree", "-r", "-l", frame).stdout, re.compile(fm.UNIVERSAL_MASK), vendor)
    code = sum(v for k, v in m["by_ext"].items() if k in pe.programming_extensions(sel / "languages.yml"))
    d = {"project": "x__y", "frame_commit": frame, "commits": commits, "frame_date": "2026-10-05T00:00:00Z",
         "pushed_min": "2025-04-03", "license": "NOASSERTION", "code_bytes": code,
         **{k: m[k] for k in ("total_bytes", "n_blobs", "tok_bytes", "n_tok", "tok_vendor_bytes")}}
    d.update(over)
    f = tmp / "frame.json"
    f.write_text(json.dumps(d))
    return f


def forge(tmp: Path, **over) -> Path:
    d = {"full_name": "x/y", "archived": False, "fork": False, "mirror": False, "updated_at": "2026-10-26T00:00:00Z",
         "owner": {"email": "never kept"}}
    d.update(over)
    f = tmp / "forge.json"
    f.write_text(json.dumps(d))
    return f


def run_select(tmp: Path, bare: Path, fj: Path, sel: Path, fg: Path) -> tuple[int, dict]:
    out = tmp / "select.json"
    rc = B.main(["select-check", "--repo", str(bare), "--frame", str(fj), "--select-dir", str(sel), "--url", "u",
                 "--forge-api", "unused", "--forge-file", str(fg), "--out", str(out)])
    return rc, json.loads(out.read_text())


def test_select_check_passes_a_good_repo(tmp_path):
    os.environ.setdefault("PATH", "/usr/bin:/bin")
    bare, frame, head = make_repo(tmp_path)
    sel = select_dir(tmp_path)
    # the frame count of the test repository is 2; the 5,000 rule is checked on the count of the frame
    fj = frame_json(tmp_path, frame, sel, bare, 2)
    rc, out = run_select(tmp_path, bare, fj, sel, forge(tmp_path))
    rules = {r["rule"]: r["ok"] for r in out["rules"]}
    assert rules["frame commit on the new host"] and rules["tree count at the frame commit = the frame measurement"]
    assert rules["frame commit is an ancestor of the run head (no rewritten history)"]
    assert out["commits_before_frame_date"] == 2 and out["commits_head"] == 3 and out["head"] == head
    assert out["measure_frame"]["license_root"] == ["COPYING"]
    assert "owner" not in out["forge"]
    # only the 5,000 rule fails here (a test repository is small)
    assert rc == 1 and out["result"] == "STOP: commit layer 5,000+ (count >= 5,000)"


def test_select_check_stops_on_another_count_and_tree_and_archive(tmp_path):
    bare, frame, _ = make_repo(tmp_path)
    sel = select_dir(tmp_path)
    fj = frame_json(tmp_path, frame, sel, bare, 7, tok_bytes=1)
    rc, out = run_select(tmp_path, bare, fj, sel, forge(tmp_path, archived=True))
    assert rc == 1
    for r in ("commit count at the frame commit = the frame count", "tree count at the frame commit = the frame measurement",
              "DP6: not archived, not a fork, not a mirror (forge API)"):
        assert r in out["result"], r


def test_select_check_stops_when_the_frame_commit_is_missing(tmp_path):
    bare, _, _ = make_repo(tmp_path)
    sel = select_dir(tmp_path)
    fj = tmp_path / "frame.json"
    fj.write_text(json.dumps({"project": "x__y", "frame_commit": "1" * 40, "commits": 2, "frame_date": "2026-10-05T00:00:00Z",
                              "pushed_min": "2025-04-03", "license": "", "code_bytes": 0, "total_bytes": 0, "n_blobs": 0,
                              "tok_bytes": 0, "n_tok": 0, "tok_vendor_bytes": 0}))
    rc, out = run_select(tmp_path, bare, fj, sel, forge(tmp_path))
    assert rc == 1 and "frame commit on the new host" in out["result"]
