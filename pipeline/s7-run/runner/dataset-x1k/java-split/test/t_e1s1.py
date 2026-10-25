#!/usr/bin/env python3
"""End-to-end test of E1-export-a.sh (machine A) and S1-setup-start.sh (an extra), as rendered, on this
machine with their test hooks: a fake /proc (the step-7 processes of the row), a fake systemctl, a fake
S3, no sudo, no chown, no units. Then jv-run on the S1 result and the pull on the A side.
Checks: E1 writes a correct input (sha256, the clone, the split, the gate, the env without other
variables) and prints no file name and no at sign; a second E1 refuses; S1 checks and unpacks it;
a corrupt clone is refused; the blame of the part equals blameRepoFiles.pl output after the pull."""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t_jv  # noqa: E402

KIT, LIB, P, A_ID = t_jv.KIT, t_jv.LIB, t_jv.P, t_jv.A_ID
MASK = r"(?i)\.(c|c\+\+|cc|cp|cpp|cxx|h|h\+\+|hh|hpp|hxx|java|rs|tcc)$"

FAKE_SYSTEMCTL = """#!/bin/sh
# fake systemctl: x1k-long units are active, jv-run is not
case "$*" in *x1k-long@*) exit 0 ;; *) exit 3 ;; esac
"""


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


class TE1S1(unittest.TestCase):
    def setUp(self):
        self.d = d = tempfile.mkdtemp()
        self.s3 = d + "/s3"
        os.makedirs(self.s3)
        fb = t_jv.fake_bin(d)
        t_jv.write(fb + "/systemctl", FAKE_SYSTEMCTL)
        os.chmod(fb + "/systemctl", 0o755)
        self.root = d + "/x1k-long"
        self.T = T = d + "/data3/x1k/" + P
        os.makedirs(self.root)
        os.makedirs(T + "/out/" + P)
        os.symlink(T, self.root + "/" + P)
        self.W = W = T + "/out/%s/%s-cregit" % (P, P)
        t_jv.make_history_repo(W)
        for i in range(10):
            t_jv.write(W + "/gen/m%02d.java" % i, "".join("let v%d = %d;\n" % (j, j * i) for j in range(5 + 7 * i)))
        t_jv.write(W + "/gen/README.md", "not in the mask\n")
        t_jv.git(W, "add", "-A")
        t_jv.git(W, "commit", "-q", "-m", "gen")
        # cregit tree of the row: a checkout of 57551d7
        self.C = C = T + "/cregit-ec2"
        r = t_jv.run(["git", "clone", "-q", "--shared", "--no-checkout", t_jv.CREGIT_SRC, C], env=t_jv.ENV_GIT)
        assert r.returncode == 0, r.stderr
        r = t_jv.run(["git", "-C", C, "checkout", "-q", "--detach", "57551d7"], env=t_jv.ENV_GIT)
        assert r.returncode == 0, r.stderr
        # machine A: every file blamed into ref/, the blame dir keeps the 4 largest (A goes largest first)
        self.ref = d + "/ref"
        os.makedirs(self.ref)
        r = t_jv.run(["perl", C + "/blameRepo/blameRepoFiles.pl", "--jobs=4", "--formatBlame=" + C + "/blameRepo/formatBlame.pl", W, self.ref, MASK], env=t_jv.ENV_GIT)
        assert r.returncode == 0, r.stderr
        o = t_jv.run(["perl", LIB + "/jv_order.pl", W, d + "/none", MASK, d + "/x.tsv"], env=t_jv.ENV_GIT)
        order = [l.split("\t", 2)[2] for l in o.stdout.splitlines()]
        self.assertEqual(len(order), 14)
        self.BL = BL = T + "/out/%s/blame" % P
        for n in order[:4]:
            t_jv.write(BL + "/" + n + ".blame", open(self.ref + "/" + n + ".blame", "rb").read())
        self.order = order
        self.names = order
        # pipeline.log: step 7 started the first 2 files left (index 1 and 2)
        t_jv.write(T + "/out/%s/pipeline.log" % P, "═══\n  Step 7 — blame\nPLAIN-BLAME %s after 3600 s of -C100\n1: %s\n2: %s\n" % (order[0], order[4], order[5]))
        for k in (".x", "cregit-ec2/blameRepo/build", "cregit-ec2/tokenizeByBlobId/build"):
            os.makedirs(T + "/" + k, exist_ok=True)
        t_jv.write(C + "/blameRepo/build/tmpfile-AbCdE", "partial")   # a temp file of a running blame: not packed
        # fake /proc: blameRepoFiles.pl, formatBlame.pl, git blame of the row
        pr = d + "/proc"
        env = "PATH=%s\0HOME=%s\0LANG=C.UTF-8\0GIT_CONFIG_GLOBAL=/dev/null\0GIT_CONFIG_NOSYSTEM=1\0SECRET_TOKEN=zzz\0AWS_X=y\0" % (os.environ["PATH"], d)
        procs = {
            "101": (["perl", C + "/blameRepo/blameRepoFiles.pl", "--jobs=44", "--formatBlame=" + C + "/blameRepo/formatBlame.pl", W, BL, MASK], shutil.which("perl")),
            "102": (["perl", C + "/blameRepo/formatBlame.pl", "--blameExtension=.blame", W, order[4], BL], shutil.which("perl")),
            "103": (["git", "-C", W, "blame", "-C100", "--porcelain", order[4]], os.path.realpath(shutil.which("git"))),
            "104": (["bash", "-c", "unrelated"], shutil.which("bash")),
        }
        for pid, (argv, exe) in procs.items():
            os.makedirs(pr + "/" + pid)
            t_jv.write(pr + "/" + pid + "/cmdline", "\0".join(argv) + "\0")
            t_jv.write(pr + "/" + pid + "/environ", env)
            os.symlink(exe, pr + "/" + pid + "/exe")
        t_jv.write(pr + "/stat", "cpu 1 2 3\nbtime 0\n")
        t_jv.write(d + "/asset-a", A_ID + "\n")
        t_jv.write(d + "/asset-x", "i-0aaaabbbbccccdddd\n")
        self.base = dict(os.environ, FAKE_S3=self.s3, PATH=fb + ":" + os.environ["PATH"], JV_BUCKET="s3://b", JV_SUDO="",
                         SYSTEMCTL="systemctl", JV_TEST="1", JV_RESERVE_GB="1")
        self.envA = dict(self.base, X1K_ASSET=d + "/asset-a", ROOT=self.root, JV_PROC=pr, JV_DATA1=d, N="3", HEAD_FILES="2", GATE_N="3")
        self.IN = self.s3 + "/b/dataset-x1k/java-split/input"

    def e1(self, **kw):
        return t_jv.run(["bash", KIT + "/E1-export-a.sh"], env=dict(self.envA, **kw), timeout=300)

    def s1(self, part="2", **kw):
        RS = self.d + "/jv"
        env = dict(self.base, X1K_ASSET=self.d + "/asset-x", JV_BASE=RS, JV_ETC=self.d + "/etc", JV_LIB=self.d + "/lib",
                   JV_BIN=self.d + "/bin", JV_PART=part, JV_NAME="dataset-java-split-" + part, JOBS="2", MARGIN="0", **kw)
        return t_jv.run(["bash", KIT + "/S1-setup-start.sh"], env=env, timeout=300), RS

    def test_e1_s1_run_pull(self):
        r = self.e1()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = r.stdout
        self.assertIn("E1 done", out)
        self.assertNotIn("@", out)
        for n in self.names:
            self.assertNotIn(n, out, "a file name in the E1 output")
        self.assertIn("order: tracked 16 mask 14 done 4 left 10", out)
        self.assertIn("machine A newest started index: 2 of 10 left", out)
        self.assertIn("check: OK", out)
        # the input in S3
        sums = dict(reversed(l.split("  ", 1)) for l in open(self.IN + "/SHA256SUMS").read().splitlines())
        for f, h in sums.items():
            self.assertEqual(sha(self.IN + "/" + f), h, f)
        self.assertIn("clone.tar.zst", sums)
        self.assertEqual(len([f for f in sums if f.startswith("gate/a/")]), 3)
        gate = [l.split("\t", 1)[1] for l in open(self.IN + "/gate/gate.tsv").read().splitlines()]
        self.assertNotIn(self.order[0], gate, "a PLAIN-BLAME file in the gate")
        self.assertTrue(set(gate) <= set(self.order[:4]), "a gate file that A did not finish")
        benv = open(self.IN + "/blame.env").read()
        self.assertIn("GIT_CONFIG_GLOBAL=/dev/null", benv)
        self.assertNotIn("SECRET", benv)
        self.assertNotIn("AWS_X", benv)
        st = dict(l.split("=", 1) for l in open(self.IN + "/settings.env").read().splitlines())
        self.assertEqual(st["REPO"], self.W)
        self.assertEqual(st["APOS0"], "2")
        self.assertEqual(st["A_JOBS"], "44")
        self.assertEqual(st["CREGIT_COMMIT"], "57551d7ad82a784615c1490623d72cb9dc994ba1")
        self.assertEqual(open(self.IN + "/mask.txt").read().strip(), MASK)
        parts = {k: open(self.IN + "/parts/part-%d.tsv" % k).read().splitlines() for k in (1, 2, 3)}
        self.assertEqual(sorted(int(l.split("\t")[0]) for v in parts.values() for l in v), list(range(5, 11)))
        # the clone in S3 is the working clone
        x = self.d + "/xclone"
        os.makedirs(x)
        subprocess.run("zstd -q -dc %s/clone.tar.zst | tar -C %s -xf -" % (self.IN, x), shell=True, check=True)
        self.assertEqual(t_jv.git(x + "/%s-cregit" % P, "rev-parse", "HEAD"), t_jv.git(self.W, "rev-parse", "HEAD"))
        self.assertEqual(t_jv.git(x + "/%s-cregit" % P, "status", "--porcelain"), "")
        # the cregit tree: no build content
        subprocess.run("mkdir -p %s/xc && zstd -q -dc %s/cregit.tar.zst | tar -C %s/xc -xf -" % (self.d, self.IN, self.d), shell=True, check=True)
        self.assertTrue(os.path.exists(self.d + "/xc/cregit-ec2/blameRepo/formatBlame.pl"))
        self.assertFalse(os.path.exists(self.d + "/xc/cregit-ec2/blameRepo/build"), "the build dir (temp files) was packed")
        # a second E1 refuses
        r2 = self.e1()
        self.assertNotEqual(r2.returncode, 0)
        self.assertIn("SHA256SUMS exists", r2.stdout)

        # the extra: A's tree is not on this machine (the clone gets A's path string as a symlink)
        shutil.move(self.d + "/data3", self.d + "/data3.A")
        r, RS = self.s1()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for want in ("sha256 ok", "repo: HEAD as A, clean worktree, path string of A", "cregit: 57551d7, clean",
                     "tools: git version", "JV_TEST: units not written"):
            self.assertIn(want, r.stdout)
        self.assertNotIn("@", r.stdout)
        self.assertEqual(os.path.realpath(self.W), RS + "/repo/%s-cregit" % P)
        jv_env = dict(l.split("=", 1) for l in open(self.d + "/etc/jv.env").read().splitlines())
        self.assertEqual((jv_env["K"], jv_env["JOBS"], jv_env["MARGIN"]), ("2", "2", "0"))
        self.assertEqual(open(RS + "/control/apos").read().split()[0], "2", "the A index of E1")
        for f in ("lib/jv_blame.pl", "lib/jv_gate.sh", "lib/jv_batch.sh", "bin/jv-run", "bin/jv-upload"):
            self.assertTrue(os.path.exists(self.d + "/" + f), f)
        # S1 again: no new download (CLONE-OK), the same checks
        r, RS = self.s1()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("sha256 ok", r.stdout)
        # jv-run as installed (gate on 3 files, then part 2), then A pulls
        env = dict(self.base, JV_BASE=RS, JV_ETC=self.d + "/etc", JV_LIB=self.d + "/lib", JV_RUNAS="", JV_IMDS="http://127.0.0.1:9",
                   JV_SHUTDOWN="touch %s/SHUTDOWN-CALLED" % RS, JV_UPLOAD="bash %s/bin/jv-upload" % self.d)
        rr = t_jv.run(["bash", self.d + "/bin/jv-run"], env=env, timeout=300)
        self.assertEqual(rr.returncode, 0, rr.stdout + rr.stderr)
        self.assertIn("gate: 3 equal, 0 not equal of 3", rr.stdout)
        self.assertTrue(os.path.exists(self.s3 + "/b/dataset-x1k/java-split/out/2/DONE"))
        shutil.rmtree(self.d + "/data3")      # the symlink of the extra
        shutil.move(self.d + "/data3.A", self.d + "/data3")
        L = self.d + "/listing.txt"
        t_jv.write(L, t_jv.run(["aws", "s3", "ls", "--recursive", "s3://b/dataset-x1k/java-split/out/"], env=dict(self.base, TZ="UTC")).stdout)
        os.makedirs(self.d + "/stage")
        p = t_jv.run([sys.executable, "-I", LIB + "/jv_pull.py", "pull", "--listing", L, "--prefix", "dataset-x1k/java-split/out/",
                      "--s3", "s3://b/dataset-x1k/java-split", "--stage", self.d + "/stage", "--blame", self.BL,
                      "--parts", self.IN + "/parts", "--n", "3", "--state", self.d + "/pst"], env=dict(self.base, JV_AWS="aws"))
        self.assertIn("linked 2, exists 0, refused 0", p.stdout)
        for line in parts[2]:
            n = line.split("\t", 2)[2]
            self.assertEqual(open(self.BL + "/" + n + ".blame", "rb").read(), open(self.ref + "/" + n + ".blame", "rb").read(), n)

    def test_s1_refuses_bad_clone(self):
        r = self.e1()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(self.IN + "/clone.tar.zst", "r+b") as f:
            f.seek(100)
            f.write(b"\0\0\0\0")
        shutil.move(self.d + "/data3", self.d + "/data3.A")
        r, RS = self.s1()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ABORT: clone download", r.stdout)
        self.assertFalse(os.path.exists(RS + "/repo/.x"))
        self.assertFalse(os.path.exists(RS + "/state/CLONE-OK"))

    def test_s1_refuses_bad_part_and_machine(self):
        r = self.e1()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r, _ = self.s1(part="4")
        self.assertIn("ABORT: no part-4.tsv", r.stdout)
        r = t_jv.run(["bash", KIT + "/S1-setup-start.sh"], env=dict(self.base, X1K_ASSET=self.d + "/asset-a", JV_PART="1"))
        self.assertIn("refuse list", r.stdout)

    def test_e1_refuses_when_not_step7(self):
        with open(self.T + "/out/%s/pipeline.log" % P, "a") as f:
            f.write("  Step 8 — remap commits\n")
        r = self.e1()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not 7", r.stdout)
        self.assertFalse(os.path.exists(self.IN))


if __name__ == "__main__":
    unittest.main(verbosity=2)
