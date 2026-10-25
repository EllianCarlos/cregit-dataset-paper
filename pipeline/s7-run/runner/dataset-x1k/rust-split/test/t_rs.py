#!/usr/bin/env python3
"""Tests of the rust-split kit on this machine, with fakes (no AWS, no machine).
Needs: perl, git, zstd, GNU tar, bash, and the cregit clone with 57551d7 (CREGIT_SRC, default
${RUNNER_PROJECTS_TILDE}/cregit-workspace/cregit). Run: python3 -I test/t_rs.py (or test/T1-all.sh)."""
import os
import random
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(KIT, "lib")
sys.path.insert(0, LIB)
import rs_split  # noqa: E402
import rs_pull  # noqa: E402

CREGIT_SRC = os.environ.get("CREGIT_SRC", os.path.expanduser("${RUNNER_PROJECTS_TILDE}/cregit-workspace/cregit"))
A_ID = "${RUNNER_EC2_X1K_LONG_A4}"
P = "awslabs__aws-sdk-rust"


def run(cmd, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(cmd, **kw)


def git(repo, *a, env=None):
    e = dict(os.environ, GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t.example", GIT_COMMITTER_NAME="T",
             GIT_COMMITTER_EMAIL="t.example", GIT_AUTHOR_DATE="2020-01-01T00:00:00Z",
             GIT_COMMITTER_DATE="2020-01-01T00:00:00Z", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    if env:
        e.update(env)
    r = run(["git", "-C", repo] + list(a), env=e)
    assert r.returncode == 0, r.stderr
    return r.stdout


def cregit_tree(d):
    """blameRepoFiles.pl and formatBlame.pl of 57551d7 (checked by blob id) in d/cregit/blameRepo."""
    b = os.path.join(d, "cregit", "blameRepo")
    os.makedirs(b, exist_ok=True)
    for f, blob in (("blameRepoFiles.pl", "7036ef5ab963a4a5a7fc78572615e415ab8114ef"),
                    ("formatBlame.pl", "76d8a379d47ad87ac13b2ca28cf6985d4ff94824")):
        data = subprocess.run(["git", "-C", CREGIT_SRC, "show", "57551d7:blameRepo/" + f], capture_output=True).stdout
        p = os.path.join(b, f)
        open(p, "wb").write(data)
        os.chmod(p, 0o755)
        got = run(["git", "hash-object", p]).stdout.strip()
        assert got == blob, (f, got)
    return b


def write(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    with open(p, mode) as f:
        f.write(data)


ENV_GIT = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")


class TOrder(unittest.TestCase):
    """rs_order.pl gives the order in which the real blameRepoFiles.pl starts the files."""

    def test_order_equals_blameRepoFiles(self):
        d = tempfile.mkdtemp()
        repo = os.path.join(d, "r")
        os.makedirs(repo)
        git(repo, "init", "-q")
        files = {"a.rs": 100, "b.rs": 300, "dir x/c.rs": 300, "d.txt": 500, "eé.rs": 400, "f.rs": 50,
                 "g.rs": 0, "z/y/h.RS": 300, "-dash.rs": 200, "k.rs": 300}
        for n, s in files.items():
            write(os.path.join(repo, n), "x" * s)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "c")
        out = os.path.join(d, "out")
        write(os.path.join(out, "f.rs.blame"), "done")
        mask = r"(?i)\.(rs)$"
        b = cregit_tree(d)
        rec = os.path.join(d, "rec.sh")
        write(rec, "#!/bin/sh\necho \"$*\" >> %s/rec.log\n" % d)
        os.chmod(rec, 0o755)
        r = run(["perl", os.path.join(b, "blameRepoFiles.pl"), "--jobs=1", "--formatBlame=" + rec, repo, out, mask], env=ENV_GIT)
        started = [l.split(": ", 1)[1] for l in r.stderr.splitlines() if l.split(":", 1)[0].isdigit()]
        o = run(["perl", os.path.join(LIB, "rs_order.pl"), repo, out, mask, os.path.join(d, "done.tsv")], env=ENV_GIT)
        self.assertEqual(o.returncode, 0, o.stderr)
        left = [l.split("\t", 2)[2] for l in o.stdout.splitlines()]
        idx = [int(l.split("\t", 2)[0]) for l in o.stdout.splitlines()]
        self.assertEqual(left, started)
        self.assertEqual(idx, list(range(1, len(left) + 1)))
        # largest first, ties in ls-files order; the quoted non-ASCII name is not in the list
        self.assertNotIn("eé.rs", " ".join(left))
        self.assertEqual(open(os.path.join(d, "done.tsv")).read(), "50\tf.rs\n")
        self.assertEqual(left[:3], ["b.rs", "dir x/c.rs", "k.rs"])
        self.assertEqual(left[-1], "g.rs")
        self.assertIn("mask 8 done 1 left 7", o.stderr)


class TSplit(unittest.TestCase):
    def left(self, n, seed):
        rnd = random.Random(seed)
        return [(i, rnd.randint(0, 9999), "f%06d.rs" % rnd.randint(0, 10 ** 6) + "-%d" % i) for i in range(1, n + 1)]

    def test_split_invariants(self):
        for n_left, apos, head, n in ((10007, 1, 1500, 5), (10007, 2000, 1500, 5), (5000, 4999, 10, 3),
                                      (100, 0, 0, 7), (3, 1, 1, 5), (229700, 13000, 1500, 5)):
            left = self.left(n_left, n_left + apos)
            h, parts = rs_split.split(left, apos, head, n)
            self.assertEqual(rs_split.check(left, h, parts), [], (n_left, apos, head, n))
            names = [r[2] for k in parts for r in parts[k]]
            self.assertEqual(len(names), len(set(names)), "a file in two parts")
            hn = {r[2] for r in h}
            self.assertFalse(hn & set(names), "a head file in a part")
            self.assertTrue(all(r[0] <= apos + head for r in h))
            self.assertTrue(all(r[0] > apos + head for k in parts for r in parts[k]))
            self.assertEqual(hn | set(names), {r[2] for r in left}, "the union is not the left list")
            for k in parts:
                self.assertEqual([r[0] for r in parts[k]], sorted(r[0] for r in parts[k]))
                # every N-th of the tail
                tail = [r for r in left if r[0] > apos + head]
                self.assertEqual(parts[k], tail[k - 1::n])

    def test_check_finds_errors(self):
        left = self.left(1000, 1)
        h, parts = rs_split.split(left, 10, 100, 4)
        bad = dict(parts)
        bad[2] = parts[2] + [parts[1][0]]
        self.assertTrue(rs_split.check(left, h, bad))
        bad = dict(parts)
        bad[3] = parts[3] + [h[0]]
        self.assertTrue(rs_split.check(left, h, bad))
        bad = dict(parts)
        bad[4] = parts[4][1:]
        self.assertTrue(rs_split.check(left, h, bad))

    def test_split_cli_and_files(self):
        d = tempfile.mkdtemp()
        left = self.left(3000, 7)
        rs_split.write_rows(os.path.join(d, "left.tsv"), left)
        r = run([sys.executable, "-I", os.path.join(LIB, "rs_split.py"), "split", "--left", d + "/left.tsv",
                 "--apos", "120", "--head", "500", "--n", "5", "--out", d + "/parts"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("check: OK", r.stdout)
        r = run([sys.executable, "-I", os.path.join(LIB, "rs_split.py"), "check", "--left", d + "/left.tsv", "--out", d + "/parts", "--n", "5"])
        self.assertEqual(r.stdout.strip(), "check: OK")
        with open(d + "/parts/part-2.tsv", "a") as f:
            f.write("%d\t%d\t%s\n" % left[0])
        r = run([sys.executable, "-I", os.path.join(LIB, "rs_split.py"), "check", "--left", d + "/left.tsv", "--out", d + "/parts", "--n", "5"])
        self.assertNotEqual(r.returncode, 0)

    def test_apos(self):
        left = [(1, 9, "big.rs"), (2, 8, "b.rs"), (3, 7, "c d.rs"), (4, 6, "x.rs"), (5, 5, "y.rs")]
        log = ["  Step 7 — blame", "1: big.rs", "2: done-before.rs", "3: c d.rs", "PLAIN-BLAME big.rs after 3600 s of -C100",
               "Error code [256][b.rs]", "1: b.rs", "12: unrelated: x", "4:x.rs"]
        self.assertEqual(rs_split.apos(left, log), 3)
        self.assertEqual(rs_split.apos(left, []), 0)
        # rs_pull apos reads on from its offset, and starts again when the log is shorter
        d = tempfile.mkdtemp()
        rs_split.write_rows(d + "/left.tsv", left)
        write(d + "/pl.log", "\n".join(log[:4]) + "\n")
        ap = lambda: run([sys.executable, "-I", os.path.join(LIB, "rs_pull.py"), "apos", "--left", d + "/left.tsv",
                          "--log", d + "/pl.log", "--state", d + "/st"]).stdout.strip()
        self.assertEqual(ap(), "3")
        with open(d + "/pl.log", "a") as f:
            f.write("9: x.rs\n10: y.rs")  # the last line has no newline yet: not read
        self.assertEqual(ap(), "4")
        with open(d + "/pl.log", "a") as f:
            f.write("\n")
        self.assertEqual(ap(), "5")
        write(d + "/pl.log", "1: b.rs\n")
        self.assertEqual(ap(), "2")

    def test_gate_pick(self):
        done = [(s, "f%03d.rs" % s) for s in range(1, 201)]
        plain = {"f010.rs", "f100.rs"}
        mt = {n: (50 if s < 20 else 100) for s, n in done}
        g = rs_split.gate(done, plain, lambda n: mt[n], 60, 30)
        self.assertEqual(len(g), 30)
        self.assertEqual(len(set(g)), 30)
        self.assertFalse({n for _, n in g} & plain)
        self.assertTrue(all(s >= 20 for s, _ in g))
        with self.assertRaises(ValueError):
            rs_split.gate(done, plain, lambda n: mt[n], 60, 500)


FAKE_FB = r"""#!/usr/bin/env bash
# fake formatBlame.pl: records its argv and the concurrency, sleeps, writes "<name>.blame".
D=__D__
echo "$$ $*" >> $D/calls.log
mkdir -p $D/active; touch $D/active/$$
n=$(ls $D/active | wc -l); echo $n >> $D/conc.log
sleep 0.2
out=${!#}; name=${@: -2:1}
mkdir -p "$(dirname "$out/$name.blame")"; echo "blame of $name" > "$out/$name.blame.tmp"; mv "$out/$name.blame.tmp" "$out/$name.blame"
rm -f $D/active/$$
"""


class TDriver(unittest.TestCase):
    def setup(self, n=40, seed=3):
        d = tempfile.mkdtemp()
        fb = os.path.join(d, "fb.sh")
        write(fb, FAKE_FB.replace("__D__", d))
        os.chmod(fb, 0o755)
        rnd = random.Random(seed)
        idx = sorted(rnd.sample(range(1, 100000), n))
        part = [(i, 10, "d%d/f %d.rs" % (i % 3, i)) for i in idx]
        rs_split.write_rows(os.path.join(d, "part.tsv"), part)
        os.makedirs(os.path.join(d, "out"))
        os.makedirs(os.path.join(d, "state"))
        return d, fb, part

    def drive(self, d, fb, *extra, jobs=4):
        return run(["perl", os.path.join(LIB, "rs_blame.pl"), "--formatblame=" + fb, "--jobs=%d" % jobs,
                    "--part=" + d + "/part.tsv", "--state=" + d + "/state"] + list(extra) + ["/the/repo", d + "/out"])

    def started(self, r):
        return [l.split(": ", 1)[1] for l in r.stderr.splitlines() if l.split(":", 1)[0].isdigit()]

    def test_order_skip_argv_jobs(self):
        d, fb, part = self.setup()
        write(os.path.join(d, "out", part[-1][2] + ".blame"), "A")          # done here before
        write(os.path.join(d, "skip.txt"), part[-2][2] + "\n")               # sent before
        r = self.drive(d, fb, "--skip=" + d + "/skip.txt")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.started(r)
        want = [p[2] for p in sorted(part, reverse=True)][2:]
        self.assertEqual(st, want, "not from the largest index down, or a skip failed")
        calls = [l.split(" ", 1)[1] for l in open(d + "/calls.log").read().splitlines()]
        self.assertEqual(sorted(calls), sorted("--blameExtension=.blame /the/repo %s %s/out" % (n, d) for n in want))
        self.assertLessEqual(max(int(x) for x in open(d + "/conc.log").read().split()), 4)
        self.assertEqual(open(os.path.join(d, "out", part[-1][2] + ".blame")).read(), "A")
        self.assertTrue(open(d + "/state/end").read().startswith("part-end "))
        self.assertIn("Newly processed [38] Already done [2]", r.stdout)

    def test_stop_file(self):
        d, fb, part = self.setup()
        write(d + "/STOP", "")
        r = self.drive(d, fb, "--stop-file=" + d + "/STOP")
        self.assertEqual(self.started(r), [])
        self.assertTrue(open(d + "/state/end").read().startswith("stop "))

    def test_meets_A(self):
        d, fb, part = self.setup()
        a = part[len(part) // 2][0]
        write(d + "/apos", "%d 123\n" % (a - 50))
        r = self.drive(d, fb, "--apos-file=" + d + "/apos", "--margin=50")
        st = self.started(r)
        idx = {p[2]: p[0] for p in part}
        self.assertTrue(st)
        self.assertTrue(all(idx[n] > a for n in st))
        self.assertEqual(len(st), len([p for p in part if p[0] > a]))
        self.assertTrue(open(d + "/state/end").read().startswith("met-A "))
        # margin -1: no A rule (the gate)
        d2, fb2, part2 = self.setup()
        write(d2 + "/apos", "999999\n")
        r = self.drive(d2, fb2, "--apos-file=" + d2 + "/apos", "--margin=-1")
        self.assertEqual(len(self.started(r)), len(part2))

    def test_failed_file_counts(self):
        d, fb, part = self.setup(n=5)
        bad = os.path.join(d, "bad.sh")
        write(bad, "#!/bin/sh\nexit 1\n")
        os.chmod(bad, 0o755)
        r = self.drive(d, bad)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Error [5]", r.stdout)
        self.assertEqual([f for _, _, fs in os.walk(d + "/out") for f in fs], [], "a failed file left a .blame")


def make_history_repo(repo):
    os.makedirs(repo)
    git(repo, "init", "-q")
    rnd = random.Random(5)
    words = ["fn", "let", "mut", "x", "y", "struct", "impl", "return", "match", "Some", "None", "{", "}", "(", ")", ";"]
    for c in range(6):
        for f in ("src/a.rs", "src/b.rs", "lib/c.rs", "lib/sub dir/d.rs", "e.txt"):
            p = os.path.join(repo, f)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            old = open(p).read().splitlines() if os.path.exists(p) else []
            new = old[:]
            for _ in range(15):
                new.insert(rnd.randint(0, len(new)), " ".join(rnd.choice(words) for _ in range(rnd.randint(1, 8))))
            write(p, "\n".join(new) + "\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "c%d" % c, env={"GIT_AUTHOR_NAME": "Author%d" % c})
    # one commit that only moves 30 lines of a.rs to the end of b.rs (what -C100 credits to the old commits)
    a = open(os.path.join(repo, "src/a.rs")).read().splitlines()
    b = open(os.path.join(repo, "src/b.rs")).read().splitlines()
    write(os.path.join(repo, "src/b.rs"), "\n".join(b + a[:30]) + "\n")
    write(os.path.join(repo, "src/a.rs"), "\n".join(a[30:]) + "\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "move", env={"GIT_AUTHOR_NAME": "Mover"})


class TRealBlame(unittest.TestCase):
    """The real formatBlame.pl of 57551d7: started by blameRepoFiles.pl and by rs_blame.pl, the
    .blame files are equal byte for byte. And the gate compare."""

    def test_same_bytes_and_gate(self):
        d = tempfile.mkdtemp()
        repo = os.path.join(d, "repo")
        make_history_repo(repo)
        b = cregit_tree(d)
        mask = r"(?i)\.(rs)$"
        out1, out2 = os.path.join(d, "out1"), os.path.join(d, "out2")
        os.makedirs(out1); os.makedirs(out2)
        r = run(["perl", b + "/blameRepoFiles.pl", "--jobs=2", "--formatBlame=" + b + "/formatBlame.pl", repo, out1, mask], env=ENV_GIT)
        self.assertEqual(r.returncode, 0, r.stderr)
        o = run(["perl", LIB + "/rs_order.pl", repo, out2, mask, d + "/done.tsv"], env=ENV_GIT)
        write(d + "/part.tsv", o.stdout)
        r2 = run(["perl", LIB + "/rs_blame.pl", "--formatblame=" + b + "/formatBlame.pl", "--jobs=2", "--part=" + d + "/part.tsv",
                  "--margin=-1", "--state=" + d, repo, out2], env=ENV_GIT)
        self.assertEqual(r2.returncode, 0, r2.stderr)
        f1 = sorted(os.path.relpath(os.path.join(x, f), out1) for x, _, fs in os.walk(out1) for f in fs)
        f2 = sorted(os.path.relpath(os.path.join(x, f), out2) for x, _, fs in os.walk(out2) for f in fs)
        self.assertEqual(f1, f2)
        self.assertEqual(len(f1), 4)
        for f in f1:
            a, c = open(os.path.join(out1, f), "rb").read(), open(os.path.join(out2, f), "rb").read()
            self.assertEqual(a, c, f)
            self.assertRegex(a.decode().splitlines()[0], r"^[0-9a-f]{40};")
        self.assertIn(b";src/a.rs;", open(os.path.join(out1, "src/b.rs.blame"), "rb").read(), "-C100 did not credit the moved lines")
        self.assertEqual(os.listdir(b + "/build"), [], "a temp file was left")
        # gate compare: equal, then one differs, then one is missing
        gl = d + "/gate.tsv"
        write(gl, "".join("1\t%s\n" % f[:-len(".blame")] for f in f1))
        sh = lambda: run(["bash", "-c", '. "$1"; rs_gate_compare "$2" "$3" "$4" "$5"', "x", LIB + "/rs_gate.sh", gl, out1, out2, d + "/gate.res"])
        g = sh()
        self.assertEqual(g.returncode, 0, g.stdout + g.stderr)
        self.assertEqual(g.stdout.strip(), "gate: 4 equal, 0 not equal of 4")
        with open(os.path.join(out2, f1[0]), "ab") as f:
            f.write(b"x")
        g = sh()
        self.assertNotEqual(g.returncode, 0)
        self.assertIn(" DIFF ", open(d + "/gate.res").read())
        os.unlink(os.path.join(out2, f1[1]))
        g = sh()
        self.assertNotEqual(g.returncode, 0)
        self.assertEqual(g.stdout.strip(), "gate: 2 equal, 2 not equal of 4")
        self.assertIn(" NO-HERE ", open(d + "/gate.res").read())
        write(gl, "")
        self.assertNotEqual(sh().returncode, 0, "an empty gate list must fail")


def fake_bin(d):
    fb = os.path.join(d, "fakebin")
    os.makedirs(fb, exist_ok=True)
    write(os.path.join(fb, "aws"), "#!/bin/sh\nexec %s -I %s/test/fake_aws.py \"$@\"\n" % (sys.executable, KIT))
    os.chmod(os.path.join(fb, "aws"), 0o755)
    return fb


def bash_lib(d, script, env):
    return run(["bash", "-c", script], env=env, cwd=d)


class TBatchPull(unittest.TestCase):
    """The batches of an extra (only complete .blame files) and the pull of machine A (no
    overwrite, temp dir + link, only complete batches with a good sha256 and the part's names)."""

    def setUp(self):
        self.d = d = tempfile.mkdtemp()
        self.s3 = os.path.join(d, "s3")
        os.makedirs(self.s3)
        self.env = dict(os.environ, FAKE_S3=self.s3, PATH=fake_bin(d) + ":" + os.environ["PATH"], RS_AWS="aws")
        self.names = ["a.rs", "src/b.rs", "src/sub dir/c.rs", "z/d.rs", "z/e.rs"]
        left = [(i, 10, n) for i, n in enumerate(["head.rs"] + self.names + ["other.rs"], 1)]
        os.makedirs(d + "/parts")
        rs_split.write_rows(d + "/parts/part-1.tsv", [r for r in left if r[2] in self.names])
        rs_split.write_rows(d + "/parts/part-2.tsv", [r for r in left if r[2] == "other.rs"])
        self.out = d + "/x/out/blame"
        for n in self.names:
            write(os.path.join(self.out, n + ".blame"), "blame %s\n" % n)
        write(os.path.join(self.out, "src/notblame.tmp"), "partial")      # not a .blame: never sent
        for p in ("st", "bd", "A/blame", "A/stage", "A/state"):
            os.makedirs(os.path.join(d, p), exist_ok=True)
        self.S3P = "s3://b/dataset-x1k/rust-split/out/1"

    def sh(self, script):
        return bash_lib(self.d, '. "%s/rs_batch.sh"; %s' % (LIB, script), self.env)

    def build_send(self):
        r = self.sh('seq=$(rs_batch_build "%s" st bd) || exit 9; [ -n "$seq" ] || exit 0; rs_batch_upload "%s" bd "$seq" || exit 8; '
                    'rs_batch_commit st bd "$seq"; echo $seq' % (self.out, self.S3P))
        return r

    def pull(self, n=2):
        L = self.d + "/listing.txt"
        r = run(["aws", "s3", "ls", "--recursive", "s3://b/dataset-x1k/rust-split/out/"], env=dict(self.env, TZ="UTC"))
        write(L, r.stdout)
        return run([sys.executable, "-I", LIB + "/rs_pull.py", "pull", "--listing", L, "--prefix", "dataset-x1k/rust-split/out/",
                    "--s3", "s3://b/dataset-x1k/rust-split", "--stage", self.d + "/A/stage", "--blame", self.d + "/A/blame",
                    "--parts", self.d + "/parts", "--n", str(n), "--state", self.d + "/A/state"], env=self.env)

    def test_batches_and_pull(self):
        r = self.build_send()
        self.assertEqual(r.stdout.strip(), "000001", r.stderr)
        self.assertEqual(sorted(open(self.d + "/st/sent.list").read().split("\n")[:-1]), sorted(n + ".blame" for n in self.names))
        self.assertEqual(self.build_send().stdout.strip(), "", "no new file: no batch")
        # machine A has its own z/d.rs.blame: the pull must not replace it
        write(self.d + "/A/blame/z/d.rs.blame", "A-OWN\n")
        p = self.pull()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("linked 4, exists 1, refused 0", p.stdout)
        self.assertEqual(open(self.d + "/A/blame/z/d.rs.blame").read(), "A-OWN\n")
        for n in self.names:
            if n != "z/d.rs":
                self.assertEqual(open(os.path.join(self.d, "A/blame", n + ".blame")).read(), "blame %s\n" % n)
        self.assertFalse(os.path.exists(self.d + "/A/blame/src/notblame.tmp"))
        self.assertEqual([x for x in os.listdir(self.d + "/A/stage") if x != "dl"], [], "a temp dir was left")
        self.assertEqual(os.listdir(self.d + "/A/stage/dl"), [])
        self.assertEqual(len(open(self.d + "/A/state/linked.tsv").read().splitlines()), 4)
        # the second pull applies nothing
        self.assertIn("new batches 0", self.pull().stdout)
        # an incomplete batch (no .sha256 yet) is not taken
        write(os.path.join(self.out, "a2.rs.blame"), "late\n")
        with open(self.d + "/parts/part-1.tsv", "a") as f:
            f.write("20\t1\ta2.rs\n")
        r = self.sh('seq=$(rs_batch_build "%s" st bd); aws s3 cp bd/b-$seq.tar.zst %s/batches/b-$seq.tar.zst; '
                    'aws s3 cp bd/b-$seq.list %s/batches/b-$seq.list; echo $seq' % (self.out, self.S3P, self.S3P))
        self.assertEqual(r.stdout.strip(), "000002")
        self.assertIn("new batches 0", self.pull().stdout)
        self.assertFalse(os.path.exists(self.d + "/A/blame/a2.rs.blame"))
        # the pending batch is sent again (same number) and then taken
        r = self.build_send()
        self.assertEqual(r.stdout.strip(), "000002")
        self.assertIn("linked 1", self.pull().stdout)
        self.assertEqual(open(self.d + "/A/blame/a2.rs.blame").read(), "late\n")

    def test_upload_failure_keeps_pending(self):
        env = dict(self.env, FAKE_AWS_FAIL=".sha256")
        r = bash_lib(self.d, '. "%s/rs_batch.sh"; seq=$(rs_batch_build "%s" st bd); rs_batch_upload "%s" bd "$seq" && echo sent || echo failed'
                     % (LIB, self.out, self.S3P), env)
        self.assertEqual(r.stdout.strip(), "failed")
        self.assertEqual(open(self.d + "/st/pending").read().strip(), "000001")
        self.assertIn("new batches 0", self.pull().stdout)
        self.assertEqual(self.build_send().stdout.strip(), "000001")
        self.assertIn("linked 5", self.pull().stdout)

    def corrupt(self, how):
        r = self.sh('seq=$(rs_batch_build "%s" st bd); echo $seq' % self.out)
        seq = r.stdout.strip()
        bd = self.d + "/bd"
        if how == "sha":
            write("%s/b-%s.sha256" % (bd, seq), "0" * 64 + "  b-%s.tar.zst\n" % seq)
        elif how == "name":
            with open("%s/b-%s.list" % (bd, seq), "a") as f:
                f.write("not/in/the/part.rs.blame\n")
            # the tar must have it too, else it is a member error
            write(os.path.join(self.out, "not/in/the/part.rs.blame"), "x\n")
            run(["bash", "-c", 'tar -C "$1" --verbatim-files-from -T "$2" -cf - | zstd -q -o "$3" -f && (cd "$4" && sha256sum "b-$5.tar.zst" > "b-$5.sha256")',
                 "x", self.out, "%s/b-%s.list" % (bd, seq), "%s/b-%s.tar.zst" % (bd, seq), bd, seq])
        elif how == "members":
            with open("%s/b-%s.list" % (bd, seq), "a") as f:
                f.write("z/ghost.rs.blame\n")
        elif how == "dotdot":
            with open("%s/b-%s.list" % (bd, seq), "a") as f:
                f.write("../../evil.rs.blame\n")
        self.sh('rs_batch_upload "%s" bd %s' % (self.S3P, seq))

    def test_bad_sha_takes_nothing(self):
        self.corrupt("sha")
        p = self.pull()
        self.assertIn("bad-sha256", p.stdout)
        self.assertEqual(os.listdir(self.d + "/A/blame"), [])
        self.assertNotEqual(p.returncode, 0)

    def test_name_outside_part_refused(self):
        self.corrupt("name")
        p = self.pull()
        self.assertIn("linked 5, exists 0, refused 1", p.stdout)
        self.assertFalse(os.path.exists(self.d + "/A/blame/not/in/the/part.rs.blame"))

    def test_member_mismatch(self):
        self.corrupt("members")
        p = self.pull()
        self.assertIn("bad-members", p.stdout)
        self.assertEqual(os.listdir(self.d + "/A/blame"), [])

    def test_dotdot_refused(self):
        self.assertFalse(rs_pull.safe_name("../../evil.rs.blame"))
        self.assertFalse(rs_pull.safe_name("/abs.rs.blame"))
        self.assertFalse(rs_pull.safe_name("a/./b.rs.blame"))
        self.assertFalse(rs_pull.safe_name("a.rs"))
        self.assertTrue(rs_pull.safe_name("a b/c.rs.blame"))

    def test_put_file_never_replaces(self):
        d = self.d
        write(d + "/A/stage/t1", "new")
        write(d + "/A/blame/q.blame", "old")
        self.assertEqual(rs_pull.put_file(d + "/A/stage/t1", d + "/A/blame/q.blame"), "exists")
        self.assertEqual(open(d + "/A/blame/q.blame").read(), "old")
        self.assertFalse(os.path.exists(d + "/A/stage/t1"))
        write(d + "/A/stage/t2", "new2")
        ino = os.stat(d + "/A/stage/t2").st_ino
        self.assertEqual(rs_pull.put_file(d + "/A/stage/t2", d + "/A/blame/n/r.blame"), "linked")
        self.assertEqual(os.stat(d + "/A/blame/n/r.blame").st_ino, ino, "not a rename of the temp file")

    def test_decide(self):
        st = self.d + "/A/state"
        L = self.d + "/l.txt"
        now = int(time.time())
        ts = lambda t: time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t))
        pre = "dataset-x1k/rust-split/out/"

        def dec(lines, apos=100, start=now - 1000, n=3, rmin=2):
            write(L, "".join("%s %d %s%s\n" % (ts(t), 10, pre, k) for t, k in lines))
            return run([sys.executable, "-I", LIB + "/rs_pull.py", "decide", "--listing", L, "--prefix", pre, "--n", str(n),
                        "--state", st, "--apos", str(apos), "--a-start", str(start), "--now", str(now),
                        "--stale-min", "40", "--restart-min", str(rmin)]).stdout.strip()
        write(st + "/linked.tsv", "%d\t150\n%d\t160\n%d\t90\n%d\t170\n" % (now - 500, now - 400, now - 300, now - 5000))
        fresh, old = now - 60, now - 3600
        self.assertTrue(dec([(fresh, "1/status.txt"), (fresh, "1/DONE")]).startswith("RESTART 2 "))
        self.assertTrue(dec([(fresh, "1/status.txt")]).startswith("WAIT parts still running: 1"))
        self.assertTrue(dec([(old, "1/status.txt")]).startswith("RESTART"), "a stale part counts as finished")
        self.assertTrue(dec([(fresh, "2/status.txt"), (fresh, "2/STOPPED"), (fresh, "3/status.txt"), (fresh, "3/GATE-FAILED")]).startswith("RESTART"))
        self.assertTrue(dec([(fresh, "1/batches/b-000003.tar.zst"), (fresh, "1/batches/b-000003.list"),
                             (fresh, "1/batches/b-000003.sha256")]).startswith("WAIT 1 complete batches"))
        self.assertTrue(dec([], apos=165).startswith("WAIT only 0"), "files at or below A do not count")
        self.assertTrue(dec([], start=now - 450).startswith("WAIT only 1"), "files linked before A's start do not count")


FAKE_SYSTEMCTL = r"""#!/usr/bin/env bash
# fake systemctl for the rs-pull test: state files in $FAKE_SD; "start" writes a start line.
D=$FAKE_SD; echo "$*" >> $D/calls.log
q=0; if [ "$1" = is-active ] && [ "${2:-}" = -q ]; then q=1; set -- is-active "${@:3}"; fi
case $1 in
  is-active) u=$2; s=$(cat "$D/$u" 2>/dev/null || echo inactive); [ $q = 1 ] || echo $s; [ "$s" = active ] ;;
  stop) echo inactive > "$D/$2" ;;
  reset-failed) : ;;
  start) echo active > "$D/$2"; sleep 1
         echo "=== $(date -u +%FT%TZ) x1k-long awslabs__aws-sdk-rust start on i-test (cregit 57551d7, ctp ca113e3, full pipeline): last completed step 6, from-step 7, removed 0 tmpfile-* and 0 step-10/firm scratch files; blame-jobs ${FAKE_JOBS:-88}, memory-limit 128GB, retries 10" >> "$FAKE_RUNLOG" ;;
  *) : ;;
esac
"""


class TRsPullWrapper(unittest.TestCase):
    """lib/rs-pull.sh end to end with a fake S3 and a fake systemctl."""

    def setUp(self):
        self.d = d = tempfile.mkdtemp()
        self.s3 = d + "/s3"
        os.makedirs(self.s3)
        fb = fake_bin(d)
        write(fb + "/systemctl", FAKE_SYSTEMCTL)
        os.chmod(fb + "/systemctl", 0o755)
        self.root = d + "/x1k-long"
        T = d + "/data2/x1k/" + P
        os.makedirs(T + "/out/" + P + "/blame")
        os.makedirs(T + "/logs")
        os.makedirs(self.root)
        os.symlink(T, self.root + "/" + P)
        self.T = T
        names = ["h%d.rs" % i for i in range(1, 6)] + ["t%d.rs" % i for i in range(1, 9)]
        left = [(i, 100 - i, n) for i, n in enumerate(names, 1)]
        e1 = self.root + "/rust-split/e1"
        os.makedirs(e1)
        rs_split.write_rows(e1 + "/left.tsv", left)
        head, parts = rs_split.split(left, 2, 3, 2)
        os.makedirs(e1 + "/parts")
        for k, rows in parts.items():
            rs_split.write_rows(e1 + "/parts/part-%d.tsv" % k, rows)
        write(T + "/out/%s/pipeline.log" % P, "════\n  Step 7 — blame\n1: h1.rs\n2: h2.rs\n3: h3.rs\n")
        write(T + "/run.env", "JOBS=88\nMEM=128GB\n")
        write(T + "/logs/run.log", "=== 2026-10-21T16:23:05Z x1k-long %s start on i-x (cregit 57551d7, ctp ca113e3, full pipeline): "
                                   "last completed step 6, from-step 7, removed 0; blame-jobs 88, memory-limit 128GB, retries 10\n" % P)
        write(d + "/asset", A_ID + "\n")
        os.makedirs(d + "/home")
        os.makedirs(d + "/run")
        os.makedirs(d + "/sd")
        write(d + "/sd/x1k-long@" + P, "active\n")
        self.env = dict(os.environ, FAKE_S3=self.s3, PATH=fb + ":" + os.environ["PATH"], RS_TEST="1", ROOT=self.root,
                        X1K_ASSET=d + "/asset", X1K_HOME=d + "/home", X1K_RUN=d + "/run", SYSTEMCTL="systemctl", RUNAS="",
                        RS_LIB=LIB, RS_BUCKET="s3://b", N="2", RESTART_MIN="1", STALE_MIN="40", AUTO_RESTART="1",
                        POLL="0", SETTLE="0", FAKE_SD=d + "/sd", FAKE_RUNLOG=T + "/logs/run.log")
        # part 1 sends its files t-files as one batch, then DONE
        self.out = d + "/extra/out"
        for i, s, n in parts[1]:
            write(os.path.join(self.out, n + ".blame"), "blame %s\n" % n)
        os.makedirs(d + "/extra/st")
        os.makedirs(d + "/extra/bd")
        r = run(["bash", "-c", '. "%s/rs_batch.sh"; seq=$(rs_batch_build "%s" extra/st extra/bd); rs_batch_upload s3://b/dataset-x1k/rust-split/out/1 extra/bd $seq && rs_batch_commit extra/st extra/bd $seq'
                 % (LIB, self.out)], env=self.env, cwd=d)
        assert r.returncode == 0, r.stderr
        self.parts = parts

    def put(self, key, text):
        write(self.s3 + "/b/dataset-x1k/rust-split/" + key, text)

    def rspull(self, **kw):
        return run(["bash", LIB + "/rs-pull.sh"], env=dict(self.env, **kw))

    def test_pull_apos_restart_once(self):
        self.put("out/1/status.txt", "x")
        self.put("out/1/DONE", "x")
        r = self.rspull()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        bl = self.T + "/out/%s/blame" % P
        self.assertEqual(sorted(os.listdir(bl)), sorted(n + ".blame" for _, _, n in self.parts[1]))
        self.assertEqual(open(self.s3 + "/b/dataset-x1k/rust-split/control/a-pos.txt").read().split()[0], "3")
        self.assertIn("decide: RESTART", r.stdout)
        self.assertIn("OK: unit active", r.stdout)
        self.assertFalse(os.path.exists(self.d + "/home/NO_SHUTDOWN"))
        calls = open(self.d + "/sd/calls.log").read()
        self.assertIn("stop x1k-long@" + P, calls)
        self.assertIn("start x1k-long@" + P, calls)
        self.assertEqual(len(open(self.root + "/rust-split/state/restarts.log").read().splitlines()), 1)
        self.assertNotIn("@", r.stdout)
        r = self.rspull()
        self.assertIn("decide: WAIT only 0", r.stdout, "a second restart")
        self.assertEqual(open(self.d + "/sd/calls.log").read().count("start x1k-long@"), 1)

    def test_waits_for_a_running_part(self):
        self.put("out/2/status.txt", "x")
        r = self.rspull()
        self.assertIn("decide: WAIT parts still running: 2", r.stdout)
        self.assertNotIn("stop x1k-long", open(self.d + "/sd/calls.log").read() if os.path.exists(self.d + "/sd/calls.log") else "")

    def test_hold_and_guards(self):
        write(self.root + "/rust-split/HOLD", "")
        r = self.rspull()
        self.assertIn("HOLD exists: nothing done", r.stdout)
        self.assertEqual(os.listdir(self.T + "/out/%s/blame" % P), [])
        os.unlink(self.root + "/rust-split/HOLD")
        write(self.d + "/home/NO_REBALANCE", "")
        r = self.rspull()
        self.assertIn("no restart; ", r.stdout)
        self.assertNotIn("stop x1k-long", open(self.d + "/sd/calls.log").read())

    def test_bad_start_line_alerts(self):
        r = self.rspull(FAKE_JOBS="64")
        self.assertIn("ALERT: no new start line", r.stdout)
        self.assertTrue(os.path.exists(self.root + "/rust-split/ALERT"))
        self.assertTrue(os.path.exists(self.d + "/home/NO_SHUTDOWN"), "NO_SHUTDOWN must stay after an error")
        r = self.rspull(FORCE_RESTART="1")
        self.assertIn("ALERT exists: no restart", r.stdout)
        self.assertEqual(open(self.d + "/sd/calls.log").read().count("start x1k-long@"), 1)

    def test_auto_restart_off(self):
        r = self.rspull(AUTO_RESTART="0")
        self.assertIn("AUTO_RESTART=0: no restart", r.stdout)

    def test_not_machine_a(self):
        write(self.d + "/asset", "i-0123\n")
        r = self.rspull()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is not machine A", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
