#!/usr/bin/env python3
"""End-to-end tests of the extra-machine units (lib/jv-run.sh + lib/jv-upload.sh) on this machine:
the real formatBlame.pl of 57551d7 on a small git repo, a fake S3 (test/fake_aws.py), the test hooks
JV_BASE, JV_ETC, JV_LIB, JV_UPLOAD, JV_SHUTDOWN, JV_RUNAS, JV_IMDS. Then machine A's pull
(jv_pull.py) takes the batches, and the pulled files must equal blameRepoFiles.pl output."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t_jv  # noqa: E402

KIT, LIB = t_jv.KIT, t_jv.LIB
S3B = "s3://b/dataset-x1k/java-split"


class TExtra(unittest.TestCase):
    def setUp(self):
        self.d = d = tempfile.mkdtemp()
        self.s3 = d + "/s3"
        os.makedirs(self.s3)
        self.fb = t_jv.fake_bin(d)
        self.repo = d + "/data3/x1k/p/out/p/p-cregit"
        t_jv.make_history_repo(self.repo)
        self.cregit = os.path.dirname(t_jv.cregit_tree(d))
        mask = r"(?i)\.(java)$"
        # machine A: the reference .blame of every mask file (blameRepoFiles.pl, as step 7 does it)
        self.ref = d + "/ref"
        os.makedirs(self.ref)
        r = t_jv.run(["perl", self.cregit + "/blameRepo/blameRepoFiles.pl", "--jobs=2", "--formatBlame=" + self.cregit + "/blameRepo/formatBlame.pl",
                      self.repo, self.ref, mask], env=t_jv.ENV_GIT)
        assert r.returncode == 0, r.stderr
        o = t_jv.run(["perl", LIB + "/jv_order.pl", self.repo, d + "/empty", mask, d + "/done.tsv"], env=t_jv.ENV_GIT)
        left = [l.split("\t", 2) for l in o.stdout.splitlines()]
        self.assertEqual(len(left), 4)
        # A finished the 2 largest (the gate), part 1 is the other 2
        self.RS = RS = d + "/jv"
        for p in ("in/parts", "in/gate/a", "out/blame", "state", "logs", "batches", "control"):
            os.makedirs(RS + "/" + p)
        with open(RS + "/in/gate/gate.tsv", "w") as f:
            for i, s, n in left[:2]:
                f.write("%s\t%s\n" % (s, n))
                t_jv.write(RS + "/in/gate/a/" + n + ".blame", open(self.ref + "/" + n + ".blame", "rb").read())
        with open(RS + "/in/parts/part-1.tsv", "w") as f:
            for i, s, n in left[2:]:
                f.write("%s\t%s\t%s\n" % (i, s, n))
        os.makedirs(d + "/parts")
        shutil.copy(RS + "/in/parts/part-1.tsv", d + "/parts/part-1.tsv")
        self.left = left
        self.ETC = d + "/etc"
        os.makedirs(self.ETC)
        t_jv.write(self.ETC + "/jv.env", "K=1\nNAME=dataset-java-split-1\nJOBS=2\nMARGIN=0\nUPLOAD_EVERY=600\nGATE_FAIL_HOLD=0\n"
                   "S3=%s\nREPO=%s\nCREGIT=%s\n" % (S3B, self.repo, self.cregit))
        t_jv.write(self.ETC + "/blame.env", "PATH=%s\nHOME=%s\nGIT_CONFIG_GLOBAL=/dev/null\nGIT_CONFIG_NOSYSTEM=1\n" % (os.environ["PATH"], d))
        self.env = dict(os.environ, FAKE_S3=self.s3, PATH=self.fb + ":" + os.environ["PATH"], JV_BASE=RS, JV_ETC=self.ETC,
                        JV_LIB=d + "/lib", JV_RUNAS="", JV_SHUTDOWN="touch %s/SHUTDOWN-CALLED" % RS, JV_IMDS="http://127.0.0.1:9",
                        JV_UPLOAD="bash %s/jv-upload.sh" % LIB)
        shutil.copytree(LIB, d + "/lib")

    def rsrun(self):
        return t_jv.run(["bash", LIB + "/jv-run.sh"], env=self.env, timeout=300)

    def s3keys(self):
        base = self.s3 + "/b/dataset-x1k/java-split/out/1"
        return sorted(os.path.relpath(os.path.join(x, f), base) for x, _, fs in os.walk(base) for f in fs) if os.path.isdir(base) else []

    def pull(self):
        L = self.d + "/listing.txt"
        r = t_jv.run(["aws", "s3", "ls", "--recursive", S3B + "/out/"], env=dict(self.env, TZ="UTC"))
        t_jv.write(L, r.stdout)
        for p in ("A/blame", "A/stage", "A/state"):
            os.makedirs(self.d + "/" + p, exist_ok=True)
        return t_jv.run([sys.executable, "-I", LIB + "/jv_pull.py", "pull", "--listing", L, "--prefix", "dataset-x1k/java-split/out/",
                         "--s3", S3B, "--stage", self.d + "/A/stage", "--blame", self.d + "/A/blame", "--parts", self.d + "/parts",
                         "--n", "1", "--state", self.d + "/A/state"], env=dict(self.env, JV_AWS="aws"))

    def test_gate_blame_done_pull(self):
        r = self.rsrun()
        log = open(self.RS + "/logs/run.log").read() if os.path.exists(self.RS + "/logs/run.log") else r.stdout
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("gate: 2 equal, 0 not equal of 2", r.stdout)
        self.assertTrue(os.path.exists(self.RS + "/state/GATE-OK"))
        keys = self.s3keys()
        self.assertIn("DONE", keys)
        self.assertIn("batches/b-000001.sha256", keys)
        self.assertIn("status.txt", keys)
        self.assertIn("plainblame.log", keys)
        self.assertTrue(os.path.exists(self.RS + "/SHUTDOWN-CALLED"))
        self.assertEqual(open(self.RS + "/state/phase").read().strip(), "done")
        status = open(self.s3 + "/b/dataset-x1k/java-split/out/1/status.txt").read()
        self.assertNotIn("@", status)
        for i, s, n in self.left[:2]:
            self.assertNotIn(n, status, "a name in status.txt")
        # machine A pulls; the pulled files equal blameRepoFiles.pl output byte for byte
        p = self.pull()
        self.assertIn("linked 2, exists 0, refused 0", p.stdout)
        for i, s, n in self.left[2:]:
            self.assertEqual(open(self.d + "/A/blame/" + n + ".blame", "rb").read(), open(self.ref + "/" + n + ".blame", "rb").read())
        self.assertEqual(os.listdir(self.cregit + "/blameRepo/build"), [], "a temp file was left")
        del log

    def test_gate_fails(self):
        n = self.left[0][2]
        with open(self.RS + "/in/gate/a/" + n + ".blame", "ab") as f:
            f.write(b"0" * 40 + b";;x\n")
        r = self.rsrun()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("gate: 1 equal, 1 not equal of 2", r.stdout)
        keys = self.s3keys()
        self.assertIn("GATE-FAILED", keys)
        self.assertIn("gate.txt", keys)
        self.assertFalse([k for k in keys if k.startswith("batches/")], "a batch after a failed gate")
        self.assertEqual(os.listdir(self.RS + "/out/blame"), [])
        self.assertTrue(os.path.exists(self.RS + "/SHUTDOWN-CALLED"))

    def test_resume_skips_sent_and_numbers_go_on(self):
        # an earlier machine of part 1 sent the file of index 4 as batch 7 and died
        i, s, n = self.left[3]
        prev = self.d + "/prev"
        t_jv.write(prev + "/out/" + n + ".blame", open(self.ref + "/" + n + ".blame", "rb").read())
        os.makedirs(prev + "/st")
        t_jv.write(prev + "/st/seq", "000006\n")
        r = t_jv.run(["bash", "-c", '. "%s/jv_batch.sh"; seq=$(jv_batch_build prev/out prev/st prev/bd); jv_batch_upload %s/out/1 prev/bd $seq'
                      % (LIB, S3B)], env=self.env, cwd=self.d)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.rsrun()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("resume: 1 names sent before, batch number 000007", r.stdout)
        started = [l for l in open(self.RS + "/logs/blame.log").read().splitlines() if l.split(":", 1)[0].isdigit()]
        self.assertEqual([l.split(": ", 1)[1] for l in started], [self.left[2][2]])
        self.assertIn("batches/b-000008.sha256", self.s3keys())
        self.assertIn("linked 2", self.pull().stdout)

    def test_stop(self):
        t_jv.write(self.RS + "/control/STOP", "")
        r = self.rsrun()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("STOPPED", self.s3keys())
        self.assertNotIn("DONE", self.s3keys())
        self.assertEqual(open(self.RS + "/state/phase").read().strip(), "stopped")

    def test_meets_A_and_no_shutdown_file(self):
        t_jv.write(self.RS + "/control/apos", "%s 1\n" % self.left[2][0])   # A started index 3
        t_jv.write(self.RS + "/NO_SHUTDOWN", "")
        r = self.rsrun()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("end met-A", r.stdout)
        self.assertIn("DONE", self.s3keys())
        self.assertFalse(os.path.exists(self.RS + "/SHUTDOWN-CALLED"))
        started = [l for l in open(self.RS + "/logs/blame.log").read().splitlines() if l.split(":", 1)[0].isdigit()]
        self.assertEqual([l.split(": ", 1)[1] for l in started], [self.left[3][2]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
