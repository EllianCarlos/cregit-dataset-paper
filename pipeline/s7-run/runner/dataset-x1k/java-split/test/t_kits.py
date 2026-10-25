#!/usr/bin/env python3
"""t_kits.py: the java-split kit next to the rust-split kit on one machine A.

1. The names: units, timers, files, dirs, S3 prefixes and tags of the two kits do not collide.
   Only the row units of the runner, R8's timer, the finalize unit and rebalance.lock are shared.
2. Both pulls on one fake machine A with both rows in step 7 (rs-pull from ../rust-split/lib,
   read only): each pull stops and starts only its own row; while one pull restarts its row,
   the other finds rebalance.lock held and waits for its next run.
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

# No byte cache: the tests import rs_split.py of ../rust-split, and that kit must stay as it is.
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t_jv  # noqa: E402
from t_jv import A_ID, fake_bin, run, write  # noqa: E402

JV = t_jv.KIT
RS = os.path.join(os.path.dirname(JV), "rust-split")
SHARED = {"x1k-long@", "x1k-rebalance.timer", "x1k-long-finalize.service", "rebalance.lock"}

NAME_RX = [
    re.compile(r"/etc/systemd/system/([A-Za-z0-9_.@-]+)"),
    re.compile(r"systemctl (?:[a-z-]+ )+(?:--now )?([A-Za-z0-9_-]+\.(?:service|timer))"),
    re.compile(r"systemctl (?:-q )?is-active (?:-q )?([a-z][A-Za-z0-9_-]+)(?=[ )\"])"),
    re.compile(r"(/usr/local/(?:lib|bin|sbin)/[A-Za-z0-9_.-]+)"),
    re.compile(r"(/etc/[a-z]+-split)"),
    re.compile(r"(/data/x1k-long/[a-z]+-split)"),
    re.compile(r"(/tmp/[A-Za-z0-9_.-]+)"),
    re.compile(r"(dataset-x1k/[a-z]+-split)/"),
    re.compile(r"(NO_[A-Z]+_RESTART)"),
    re.compile(r"(dataset-[a-z]+-split)-"),
    re.compile(r"Values=([a-z]+-split)"),
    re.compile(r"\$T/([a-z]+-split-stage)"),
    re.compile(r"(rebalance\.lock)"),
]


def kit_names(kit):
    """The names a kit installs or uses, from its scripts without the comment lines."""
    files = []
    for sub in ("", "lib", "src"):
        d = os.path.join(kit, sub)
        files += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith((".sh", ".body", ".py", ".pl"))]
    names = set()
    for p in files:
        for line in open(p, encoding="utf-8"):
            if line.lstrip().startswith("#"):
                continue
            for rx in NAME_RX:
                names.update(rx.findall(line))
    return names


class TNames(unittest.TestCase):
    def test_names_differ(self):
        jv, rs = kit_names(JV), kit_names(RS)
        jv_units = {n for n in jv if n.endswith((".service", ".timer")) and n.split(".")[0] not in ("x1k-rebalance", "x1k-long-finalize")}
        rs_units = {n for n in rs if n.endswith((".service", ".timer")) and n.split(".")[0] not in ("x1k-rebalance", "x1k-long-finalize")}
        # The java units on A (jv-pull) and on the extras (jv-run, jv-upload).
        self.assertEqual(jv_units - {"rs-pull.timer"}, {"jv-pull.service", "jv-pull.timer", "jv-run.service", "jv-upload.service"})
        # The java kit only reads the state of rs-pull.timer (P1 and P2 print it).
        for sub in ("", "lib", "src"):
            for f in os.listdir(os.path.join(JV, sub)):
                if f.endswith((".sh", ".body")):
                    for line in open(os.path.join(JV, sub, f)):
                        if "rs-pull" in line and not line.lstrip().startswith("#"):
                            self.assertRegex(line, r"systemctl (is-active|list-timers) ", f)
                            self.assertNotRegex(line, r"systemctl (start|stop|enable|disable|restart)", f)
        self.assertEqual(rs_units, {"rs-pull.service", "rs-pull.timer", "rs-run.service", "rs-upload.service"})
        # jv-pull reads the state of rs-pull.timer (P1, P2), it never writes it.
        common = (jv & rs) - SHARED - {"rs-pull.timer"}
        self.assertEqual(common, set(), "names in both kits")
        for need in ("/usr/local/bin/jv-pull", "/usr/local/lib/java-split", "/etc/java-split", "/data/x1k-long/java-split",
                     "dataset-x1k/java-split", "NO_JV_RESTART", "dataset-java-split", "java-split", "java-split-stage"):
            self.assertIn(need, jv)
        for bad in ("/usr/local/bin/rs-pull", "/usr/local/lib/rust-split", "/etc/rust-split", "/data/x1k-long/rust-split",
                    "dataset-x1k/rust-split", "NO_RS_RESTART", "dataset-rust-split", "rust-split-stage"):
            self.assertNotIn(bad, jv)
        # The one shared lock of all restarts.
        self.assertIn("rebalance.lock", jv)
        self.assertIn("rebalance.lock", rs)

    def test_pull_locks_differ_restart_lock_same(self):
        jvp = open(os.path.join(JV, "lib", "jv-pull.sh")).read()
        rsp = open(os.path.join(RS, "lib", "rs-pull.sh")).read()
        for src, s in ((jvp, "java-split"), (rsp, "rust-split")):
            self.assertIn('S=$ROOT/%s' % s, src)
            self.assertIn('exec 9>>"$S/state/pull.lock"', src)
            self.assertIn('exec 8>>"$ROOT/rebalance.lock"', src)
            self.assertIn("flock -n 8", src)
        self.assertIn("P=aws__aws-sdk-java", jvp)
        self.assertIn("P=awslabs__aws-sdk-rust", rsp)


FAKE_SYSTEMCTL = r"""#!/usr/bin/env bash
# fake systemctl for two rows: state files in $FAKE_SD; "stop" sleeps FAKE_STOP_SLEEP s; "start" writes
# the start line of the row into its run.log.
D=$FAKE_SD; echo "$*" >> $D/calls.log
q=0; if [ "$1" = is-active ] && [ "${2:-}" = -q ]; then q=1; set -- is-active "${@:3}"; fi
case $1 in
  is-active) u=$2; s=$(cat "$D/$u" 2>/dev/null || echo inactive); [ $q = 1 ] || echo $s; [ "$s" = active ] ;;
  stop) sleep "${FAKE_STOP_SLEEP:-0}"; echo inactive > "$D/$2" ;;
  reset-failed) : ;;
  start) echo active > "$D/$2"; p=${2#x1k-long@}; j=$(sed -n 's/^JOBS=//p' "$FAKE_ROOT/$p/run.env")
         echo "=== $(date -u +%FT%TZ) x1k-long $p start on i-test (cregit 57551d7, ctp ca113e3, full pipeline): last completed step 6, from-step 7, removed 0; blame-jobs $j, memory-limit 96GB, retries 10" >> "$FAKE_ROOT/$p/logs/run.log" ;;
  *) : ;;
esac
"""

ROWS = {"java": ("aws__aws-sdk-java", "data3", 44), "rust": ("awslabs__aws-sdk-rust", "data2", 132)}


class TTwoPulls(unittest.TestCase):
    def setUp(self):
        self.d = d = tempfile.mkdtemp()
        self.s3 = d + "/s3"
        os.makedirs(self.s3)
        fb = fake_bin(d)
        write(fb + "/systemctl", FAKE_SYSTEMCTL)
        os.chmod(fb + "/systemctl", 0o755)
        self.root = d + "/x1k-long"
        os.makedirs(self.root)
        for x in ("home", "run", "sd"):
            os.makedirs(d + "/" + x)
        write(d + "/asset", A_ID + "\n")
        self.env = dict(os.environ, FAKE_S3=self.s3, PATH=fb + ":" + os.environ["PATH"], ROOT=self.root,
                        X1K_ASSET=d + "/asset", X1K_HOME=d + "/home", X1K_RUN=d + "/run", SYSTEMCTL="systemctl", RUNAS="",
                        N="2", RESTART_MIN="1", STALE_MIN="40", AUTO_RESTART="1", POLL="0", SETTLE="0",
                        FAKE_SD=d + "/sd", FAKE_ROOT=self.root,
                        JV_TEST="1", JV_LIB=JV + "/lib", JV_BUCKET="s3://b",
                        RS_TEST="1", RS_LIB=RS + "/lib", RS_BUCKET="s3://b")
        self.T = {}
        for kit, (p, vol, jobs) in ROWS.items():
            T = "%s/%s/x1k/%s" % (d, vol, p)
            os.makedirs(T + "/out/" + p + "/blame")
            os.makedirs(T + "/logs")
            os.symlink(T, self.root + "/" + p)
            self.T[kit] = T
            write(T + "/run.env", "JOBS=%d\n" % jobs)
            write(T + "/logs/run.log", "=== 2026-10-22T10:00:00Z x1k-long %s start on i-x (cregit 57551d7, ctp ca113e3, full pipeline): "
                                       "last completed step 6, from-step 7, removed 0; blame-jobs %d, memory-limit 96GB, retries 10\n" % (p, jobs))
            write(T + "/out/%s/pipeline.log" % p, "  Step 7 - blame\n1: h1.x\n2: h2.x\n3: h3.x\n")
            write(d + "/sd/x1k-long@" + p, "active\n")
            split, mod, pfx = ("java-split", "jv", "jv") if kit == "java" else ("rust-split", "rs", "rs")
            lib = JV + "/lib" if kit == "java" else RS + "/lib"
            sys.path.insert(0, lib)
            sp = __import__("%s_split" % mod)
            names = ["h%d.x" % i for i in range(1, 6)] + ["t%d.x" % i for i in range(1, 9)]
            left = [(i, 100 - i, n) for i, n in enumerate(names, 1)]
            e1 = "%s/%s/e1" % (self.root, split)
            os.makedirs(e1 + "/parts")
            sp.write_rows(e1 + "/left.tsv", left)
            head, parts = sp.split(left, 2, 3, 2)
            for k, rows in parts.items():
                sp.write_rows(e1 + "/parts/part-%d.tsv" % k, rows)
            # part 1 of each kit sends its files as one batch and ends with DONE; part 2 never started
            out = "%s/extra-%s/out" % (d, kit)
            for _, _, n in parts[1]:
                write(os.path.join(out, n + ".blame"), "blame %s %s\n" % (kit, n))
            os.makedirs("%s/extra-%s/st" % (d, kit))
            os.makedirs("%s/extra-%s/bd" % (d, kit))
            pre = "s3://b/dataset-x1k/%s/out/1" % split
            r = run(["bash", "-c", '. "%s/%s_batch.sh"; seq=$(%s_batch_build "%s" extra-%s/st extra-%s/bd); %s_batch_upload %s extra-%s/bd $seq && %s_batch_commit extra-%s/st extra-%s/bd $seq'
                     % (lib, pfx, pfx, out, kit, kit, pfx, pre, kit, pfx, kit, kit)], env=self.env, cwd=d)
            self.assertEqual(r.returncode, 0, r.stderr)
            write("%s/b/dataset-x1k/%s/out/1/status.txt" % (self.s3, split), "x")
            write("%s/b/dataset-x1k/%s/out/1/DONE" % (self.s3, split), "x")

    def calls(self):
        p = self.d + "/sd/calls.log"
        return open(p).read() if os.path.exists(p) else ""

    def pull(self, kit, **kw):
        cmd = JV + "/lib/jv-pull.sh" if kit == "java" else RS + "/lib/rs-pull.sh"
        return ["bash", cmd], dict(self.env, **kw)

    def test_each_pull_restarts_only_its_row(self):
        c, e = self.pull("java")
        r = run(c, env=e)
        self.assertIn("OK: unit active", r.stdout, r.stdout + r.stderr)
        self.assertIn("stop x1k-long@aws__aws-sdk-java", self.calls())
        self.assertNotIn("x1k-long@awslabs__aws-sdk-rust", re.sub(r"is-active.*", "", self.calls()))
        self.assertEqual(len(os.listdir(self.T["java"] + "/out/aws__aws-sdk-java/blame")), 4)
        self.assertEqual(os.listdir(self.T["rust"] + "/out/awslabs__aws-sdk-rust/blame"), [])
        open(self.d + "/sd/calls.log", "w").close()
        c, e = self.pull("rust")
        r = run(c, env=e)
        self.assertIn("OK: unit active", r.stdout, r.stdout + r.stderr)
        self.assertIn("stop x1k-long@awslabs__aws-sdk-rust", self.calls())
        self.assertNotIn("x1k-long@aws__aws-sdk-java", re.sub(r"is-active.*", "", self.calls()))
        # the jobs of each row stay as in its run.env
        self.assertIn("blame-jobs 44,", open(self.T["java"] + "/logs/run.log").read().splitlines()[-1])
        self.assertIn("blame-jobs 132,", open(self.T["rust"] + "/logs/run.log").read().splitlines()[-1])
        # the second runs: no new restart
        for kit in ("java", "rust"):
            c, e = self.pull(kit)
            self.assertIn("decide: WAIT only 0", run(c, env=e).stdout)

    def test_restarts_never_at_once(self):
        c, e = self.pull("java", FAKE_STOP_SLEEP="4")
        pj = subprocess.Popen(c, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(100):
            if "stop x1k-long@aws__aws-sdk-java" in self.calls():
                break
            time.sleep(0.1)
        self.assertIn("stop x1k-long@aws__aws-sdk-java", self.calls())
        c, e = self.pull("rust")
        r = run(c, env=e)
        self.assertIn("decide: RESTART", r.stdout)
        self.assertIn("R8 holds rebalance.lock: the restart waits for the next run", r.stdout)
        self.assertNotIn("stop x1k-long@awslabs__aws-sdk-rust", self.calls())
        out, _ = pj.communicate(timeout=60)
        self.assertIn("OK: unit active", out)
        r = run(c, env=e)
        self.assertIn("OK: unit active", r.stdout, "the rust pull restarts on its next run")
        self.assertFalse(os.path.exists(self.root + "/java-split/ALERT"))
        self.assertFalse(os.path.exists(self.root + "/rust-split/ALERT"))
        self.assertFalse(os.path.exists(self.d + "/home/NO_SHUTDOWN"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
