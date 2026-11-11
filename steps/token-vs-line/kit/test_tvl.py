"""Fixture tests of the kit: blame limits, identity without a persons database, leak scan.

    python3 -I test_tvl.py        (needs git and duckdb; writes only to a temp folder)

The fixture is a small git repository with 4 commits by 3 e-mail addresses and a TOM-like
Parquet file that credits 2 of the commits. The expected values are counted by hand.
"""
import gzip
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import duckdb  # noqa: E402

import blame_lines  # noqa: E402
import measure  # noqa: E402
import tvl_run  # noqa: E402

PA, PB = "author 0000000000000a", "author 0000000000000b"
# a fixture address only; it is built so this file has no at sign
DOMAIN = {"a": "x.org", "b": "y.org", "c": "z.org"}


def mail(user, k):
    return user + chr(64) + DOMAIN[k]


def git(repo, *args, name=None, email=None, date="2020-01-01T00:00:00Z"):
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME=name or "n", GIT_AUTHOR_EMAIL=email or mail("n", "a"), GIT_AUTHOR_DATE=date,
               GIT_COMMITTER_NAME="c", GIT_COMMITTER_EMAIL=mail("c", "a"), GIT_COMMITTER_DATE=date)
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env,
                          text=True).stdout.strip()


def build(tmp):
    repo = Path(tmp) / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    steps = [("Alice", mail("alice", "a"), "int a = 1;\nint b = 2;\n"),
             ("Bob", mail("bob", "b"), "int a = 1;\nint b = 3;\n"),
             ("Alice Two", mail("alice", "a"), "int a = 1;\nint b = 3;\nint c;\n"),
             ("Carol", mail("carol", "c"), "int a = 1;\nint b = 3;\nint c;\nint d;\n")]
    shas = []
    for i, (n, e, text) in enumerate(steps):
        (repo / "a.c").write_text(text)
        git(repo, "add", "a.c")
        git(repo, "commit", "-q", "-m", f"c{i + 1}", name=n, email=e, date=f"2020-01-0{i + 1}T00:00:00Z")
        shas.append(git(repo, "rev-parse", "HEAD"))
    c1, c2, c3, c4 = shas
    # TOM: line 1 by c1; line 2: 4 tokens c1, the token '3' c2; line 3 by c1 (TOM says c1); line 4 by c2
    toks = [(1, c1)] * 5 + [(2, c1)] * 3 + [(2, c2)] + [(2, c1)] + [(3, c1)] * 3 + [(4, c2)] * 3
    pid = {c1: PA, c2: PB}
    firm = {c1: "x-org", c2: "y-org"}
    con = duckdb.connect()
    con.execute("CREATE TABLE t (file_path VARCHAR, token_index BIGINT, source_line BIGINT, is_structural BIGINT, "
                "original_commit_sha VARCHAR, personid VARCHAR, firm_based_on_domain VARCHAR)")
    con.execute("INSERT INTO t VALUES ('a.c', 0, 1, 1, ?, ?, ?)", [c1, PA, "x-org"])
    for i, (ln, c) in enumerate(toks, start=1):
        con.execute("INSERT INTO t VALUES ('a.c', ?, ?, 0, ?, ?, ?)", [i, ln, c, pid[c], firm[c]])
    tom = Path(tmp) / "fix-dataset.parquet"
    con.execute(f"COPY t TO '{tom}' (FORMAT parquet)")
    dom = Path(tmp) / "organization_domains.parquet"
    con.execute(f"COPY (SELECT * FROM (VALUES ('z.org', 'z-org'), ('y.org', 'y-org')) v(domain, organization_id)) "
                f"TO '{dom}' (FORMAT parquet)")
    return repo, c4, tom, dom, shas


def run_project(tmp, repo, head, tom, dom, limits=None, name="w"):
    work = Path(tmp) / name
    runner = blame_lines.Runner()
    pb = blame_lines.ProjectBlame("fix", repo, head, work)
    files = blame_lines.tom_files(tom)
    for f in files:
        pb.add(blame_lines.one_file(runner, repo, head, f, limits))
    pb.finish(len(files))
    con = duckdb.connect()
    out, ex, langs = measure.measure(con, "fix", repo, head, tom, work, dom)
    measure.write_tables(work / "out", [out], ex, langs)
    return out, work


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="tvl-test-")
        cls.repo, cls.head, cls.tom, cls.dom, cls.shas = build(cls.tmp)
        cls.out, cls.work = run_project(cls.tmp, cls.repo, cls.head, cls.tom, cls.dom)

    def test_token_level(self):
        o = self.out
        self.assertEqual(o["tokens"], 16)
        self.assertEqual(o["tok_matched"], 16)
        self.assertEqual(o["tok_author_diff"], 7)    # line 2: 4 tokens of A on a line of B; line 4: 3 tokens of B, line of C
        self.assertEqual(o["tok_commit_diff"], 10)   # line 2: 4, line 3: 3, line 4: 3
        self.assertEqual(o["tok_firm_diff"], 7)      # line 2: x-org against y-org; line 4: y-org against z-org (domain table)
        self.assertEqual(o["tok_matched_wmc"], 16)
        self.assertEqual(o["mixed_author_lines"], 1)

    def test_identity_without_persons_db(self):
        o = self.out
        self.assertEqual(o["commits_log"], 4)
        self.assertEqual(o["commits_tom"], 2)
        self.assertEqual(o["lines_blamed"], 4)
        self.assertEqual(o["lines_commit_not_in_tom"], 2)
        self.assertEqual(o["lines_id_email"], 1)      # c3: same e-mail address as c1, so personid A
        self.assertEqual(o["lines_id_unmapped"], 1)   # c4: an address that TOM has not
        self.assertEqual(o["commits_id_unmapped"], 1)
        self.assertEqual(o["id_pairs"], 2)

    def test_no_limits(self):
        self.assertEqual(self.out["files_limit_any"], 0)
        self.assertEqual(self.out["pct_tok_in_limit_any"], 0.0)

    def test_outputs_have_no_person_data(self):
        files = [p for p in self.work.rglob("*") if p.is_file()]
        self.assertTrue(files)
        self.assertEqual(tvl_run.Run.leak_scan(files), [])
        for p in files:
            data = gzip.open(p).read() if p.suffix == ".gz" else p.read_bytes()
            for k in ("alice", "bob", "carol", "Alice", "Carol", "x.org", "z.org"):
                self.assertNotIn(k.encode(), data, (p, k))

    def test_limit_keeps_other_blames(self):
        lim = {"plain": 1800.0, "w": 1800.0, "wmc": 1e-6}
        o, work = run_project(self.tmp, self.repo, self.head, self.tom, self.dom, lim, "wlim")
        self.assertEqual(o["tok_author_diff"], 7)
        self.assertEqual(o["tok_matched"], 16)
        self.assertEqual(o["tok_matched_wmc"], 0)
        self.assertEqual(o["files_limit_wmc"], 1)
        self.assertEqual(o["tok_in_limit_wmc"], 16)
        self.assertEqual(o["pct_tok_in_limit_any"], 100.0)
        lt = (work / "limits.tsv").read_text().splitlines()
        self.assertEqual(lt[0], "project\tfile_path\tblame\tlimit_s\tseconds")
        self.assertEqual(lt[1].split("\t")[:3], ["fix", "a.c", "wmc"])

    def test_plain_over_limit_keeps_rows(self):
        lim = {"plain": 1e-6, "w": 1800.0, "wmc": 1800.0}
        o, work = run_project(self.tmp, self.repo, self.head, self.tom, self.dom, lim, "plim")
        self.assertEqual(o["tok_matched"], 0)
        self.assertEqual(o["tok_matched_wmc"], 16)
        self.assertEqual(o["lines"], 4)
        self.assertEqual(o["files_limit_plain"], 1)

    def test_cap_cuts_files(self):
        r = blame_lines.Runner()
        r.abort()
        res = blame_lines.one_file(r, self.repo, self.head, "a.c")
        self.assertIsNone(res["rows"])
        self.assertEqual(res["limits"][0][1], "cap")


class Small(unittest.TestCase):
    def test_split_lines(self):
        self.assertEqual(blame_lines.split_lines(b""), [])
        self.assertEqual(blame_lines.split_lines(b"a\nb"), [b"a", b"b"])
        self.assertEqual(blame_lines.split_lines(b"a\r\n\n"), [b"a\r", b""])

    def test_leak_scan(self):
        d = Path(tempfile.mkdtemp(prefix="tvl-leak-"))
        (d / "ok.tsv").write_text("a\tb\n")
        addr = "y" + chr(64) + "z.org"
        with gzip.open(d / "bad.tsv.gz", "wt") as f:
            f.write("x\n" + addr + "\n")
        hits = tvl_run.Run.leak_scan([d / "ok.tsv", d / "bad.tsv.gz"])
        self.assertEqual([(Path(h).name, n) for h, n in hits], [("bad.tsv.gz", 1)])

    def test_scan_at_sign_in_path_is_not_a_hit(self):
        at, sha = chr(64), "a" * 40
        d = Path(tempfile.mkdtemp(prefix="tvl-at-"))
        head = "file_path\tline\tsha_plain\tsha_w\tsha_wmc\torig_file_wmc\tblank\n"
        with gzip.open(d / "blame.tsv.gz", "wt") as f:
            f.write(head)
            f.write(f"a/b.c\t1\t{sha}\t{sha}\t{sha}\tv{at}1/x/y.c\t0\n")
            f.write(f"a/b.c\t2\t{sha}\t\t\t\t1\n")
        self.assertEqual(tvl_run.Run.leak_scan([d / "blame.tsv.gz"]), [])
        rows = tvl_run.Run.at_sign_report("p", d, [d / "blame.tsv.gz"])
        self.assertEqual([(r[1], r[2], r[3], r[4]) for r in rows], [("blame.tsv.gz", "orig_file_wmc", 1, 1)])
        self.assertNotIn("v", rows[0][5].replace("a", ""))   # a shape, not the value

    def test_scan_address_in_path_or_odd_blame_line_is_a_hit(self):
        at, sha = chr(64), "a" * 40
        d = Path(tempfile.mkdtemp(prefix="tvl-at2-"))
        head = "file_path\tline\tsha_plain\tsha_w\tsha_wmc\torig_file_wmc\tblank\n"
        with gzip.open(d / "blame.tsv.gz", "wt") as f:
            f.write(head + f"u{at}h.org/x.c\t1\t{sha}\t{sha}\t{sha}\tx.c\t0\n")
        self.assertEqual(len(tvl_run.Run.leak_scan([d / "blame.tsv.gz"])), 1)
        with gzip.open(d / "blame.tsv.gz", "wt") as f:
            f.write(head + "x.c\t1\tNot A Sha\t\t\tx.c\t0\n")
        self.assertEqual(len(tvl_run.Run.leak_scan([d / "blame.tsv.gz"])), 1)


class NullPersonid(unittest.TestCase):
    def test_credited_commit_without_personid(self):
        tmp = tempfile.mkdtemp(prefix="tvl-null-")
        repo, head, tom, dom, shas = build(tmp)
        tom2 = Path(tmp) / "null-dataset.parquet"
        duckdb.connect().execute(
            f"COPY (SELECT * REPLACE (CASE WHEN original_commit_sha = '{shas[1]}' THEN NULL ELSE personid END AS personid) "
            f"FROM read_parquet('{tom}')) TO '{tom2}' (FORMAT parquet)")
        out, work = run_project(tmp, repo, head, tom2, dom, name="wnull")
        self.assertEqual(out["commits_tom_null_personid"], 1)
        self.assertEqual(out["tokens"], 16)
        self.assertEqual(out["commits_tom"], 2)
        self.assertGreater(out["tok_author_diff"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
