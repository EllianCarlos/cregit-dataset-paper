"""The token-against-line run on one machine (or locally with TVL_LOCAL=1).

For each drawn project (plan.tsv, draw_rank 1..N), the largest TOM pipeline time first:
  1. clone the project at its run_commit from its clone URL into the pinned-clone path
     (an empty bare repository, fetch of the run commit, else of all branches and tags;
     commit graph with changed-path filters); retries with backoff (longer for hosts
     other than GitHub); a failure goes into failures.tsv and stays in the denominator;
  2. copy its TOM file from the release root and check its sha256 against the root SHA256SUMS;
  3. the 3 line blames of each TOM file (blame_lines.one_file) on one shared pool of JOBS
     git jobs, each blame with its own limit;
  4. measure.py (a subprocess; the e-mail map stays in its memory);
  5. a leak scan (no at sign in any result file), then the upload of the project results.
A progress file goes to S3 every PROGRESS_S seconds. The run has a hard cap of CAP_H hours from
its first start: at CAP_H - RESERVE_MIN the blames stop (the files that did not end go into
limits.tsv as blame 'cap'), the started projects are measured with what they have, the
tables are uploaded, and the machine shuts down (stop). A second start continues.

    nice -n 10 python3 -I tvl_run.py --conf tvl.conf --plan plan.tsv --x /data/tvl
"""
import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import blame_lines  # noqa: E402

LOCAL = os.environ.get("TVL_LOCAL") == "1"
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
BLAME_LINE = re.compile(rb"^[^\t]*\t[0-9]+\t(?:[0-9a-f]{40})?\t(?:[0-9a-f]{40})?\t(?:[0-9a-f]{40})?\t[^\t]*\t[01]$")
STATES = ("queued", "cloning", "cloned", "blaming", "measuring", "uploading", "done",
          "clone_failed", "tom_failed", "measure_failed", "leak_held", "not_started_cap", "error")


def utc(t=None):
    return dt.datetime.fromtimestamp(t or time.time(), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_conf(path):
    c = {}
    for ln in Path(path).read_text().splitlines():
        ln = ln.split("#", 1)[0].strip()
        if "=" in ln:
            k, v = ln.split("=", 1)
            c[k.strip()] = v.strip().strip('"')
    for k in list(c) + ["TVL_RUN", "KIT_SUMS"]:
        if os.environ.get(k):
            c[k] = os.environ[k]
    c.setdefault("TVL_RUN", "local")
    return c


def parse_sums(text):
    """path -> sha256 of a SHA256SUMS text (comment and empty lines skipped)."""
    out = {}
    for ln in text.splitlines():
        parts = ln.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64 and not ln.startswith("#"):
            out[parts[1].strip().lstrip("*")] = parts[0]
    return out


def clean(x):
    return str(x).replace("\t", " ").replace("\n", " ").replace("\r", " ")[:300]


class Run:
    def __init__(self, conf, plan, x):
        self.c = conf
        self.x = Path(x)
        for d in ("pinned", "tom", "work", "state", "log", "tables", "duckdb-tmp", "status"):
            (self.x / d).mkdir(parents=True, exist_ok=True)
        self.log_f = open(self.x / "log" / "run.log", "a", buffering=1)
        n = int(conf["N"])
        rows = [r for r in plan if int(r["draw_rank"]) <= n]
        rows.sort(key=lambda r: (-float(r["pipeline_s"] or 0), int(r["draw_rank"])))
        self.plan = rows
        self.lock = threading.Lock()
        self.state = {r["project"]: "queued" for r in rows}
        self.info = {r["project"]: {"draw_rank": r["draw_rank"], "language": r["language"],
                                    "host": urlparse(r["clone_url"]).hostname or "", "run_commit": r["run_commit"]}
                     for r in rows}
        self.failures = []
        self.files_total, self.files_done = {}, collections.Counter()
        sf = self.x / "state" / "start_utc"
        if not sf.exists():
            sf.write_text(f"{time.time():.0f}\n")
        self.start = float(sf.read_text().split()[0])
        cap = float(conf["CAP_H"]) * 3600
        self.t_blame_end = self.start + cap - float(conf["RESERVE_MIN"]) * 60
        self.t_hard = self.start + cap - 10 * 60
        self.runner = blame_lines.Runner()
        self.cut = threading.Event()
        self.limits = {"plain": float(conf["LIMIT_PLAIN"]), "w": float(conf["LIMIT_W"]),
                       "wmc": float(conf["LIMIT_WMC"])}
        self.mem_cond = threading.Condition()
        self.mem_free = int(conf["MEASURE_BUDGET_GB"])
        self.alerts = []
        self.root_sums = {}
        self.domains = None

    # ---- small helpers
    def log(self, msg):
        line = f"{utc()} {msg}"
        with self.lock:
            self.log_f.write(line + "\n")
        print(line, flush=True)

    def set_state(self, p, s, **kw):
        with self.lock:
            self.state[p] = s
            self.info[p].update(kw)
        st = self.x / "state" / f"{p}.json"
        st.write_text(json.dumps({"state": s, **self.info[p]}))

    def fail(self, p, stage, attempts, secs, msg):
        with self.lock:
            self.failures.append((p, self.info[p]["draw_rank"], self.info[p]["host"], stage, attempts,
                                  round(secs, 1), clean(msg)))

    def sh(self, cmd, timeout=None, check=True, env=None):
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
        if check and r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "replace").strip().replace("\n", " ")[-300:])
        return r

    def s3(self, *args, timeout=3600):
        """aws s3 on the machine; locally a copy into the folder TVL_LOCAL_S3."""
        if LOCAL:
            base = Path(os.environ["TVL_LOCAL_S3"])
            op, src, dst = args[0], args[1], args[2]
            src = base / src[5:] if src.startswith("s3://") else Path(src)
            dst = base / dst[5:] if dst.startswith("s3://") else Path(dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if op == "cp":
                shutil.copyfile(src, dst)
            else:
                shutil.copytree(src, dst, dirs_exist_ok=True)
            return
        self.sh(["aws", "s3", *args, "--only-show-errors"], timeout=timeout)

    def run_prefix(self):
        return f"s3://{self.c['BUCKET']}/{self.c['RUN_PREFIX']}/{self.c['TVL_RUN']}"

    # ---- inputs of the release root
    def fetch_root(self):
        d = self.x / "root"
        d.mkdir(exist_ok=True)
        if LOCAL:
            self.domains = os.environ["TVL_DOMAINS"]
            sums = os.environ.get("TVL_ROOT_SUMS")
            if sums:
                self.c["ROOT_SUMS_SHA"] = hashlib.sha256(Path(sums).read_bytes()).hexdigest()
                self.root_sums = parse_sums(Path(sums).read_text())
            return
        root = f"s3://{self.c['BUCKET']}/{self.c['ROOT']}"
        self.s3("cp", f"{root}/SHA256SUMS", str(d / "SHA256SUMS"))
        got = hashlib.sha256((d / "SHA256SUMS").read_bytes()).hexdigest()
        size = (d / "SHA256SUMS").stat().st_size
        if str(size) != self.c["ROOT_SUMS_SIZE"]:
            raise SystemExit(f"ABORT: root SHA256SUMS has {size} bytes, not {self.c['ROOT_SUMS_SIZE']}")
        if self.c.get("ROOT_SUMS_SHA") and got != self.c["ROOT_SUMS_SHA"]:
            raise SystemExit(f"ABORT: root SHA256SUMS is {got[:12]}, not {self.c['ROOT_SUMS_SHA'][:12]}")
        self.c["ROOT_SUMS_SHA"] = got
        self.log(f"root SHA256SUMS: {size} bytes, sha256 {got}")
        self.root_sums = parse_sums((d / "SHA256SUMS").read_text())
        rel = "organizations/organization_domains.parquet"
        self.s3("cp", f"{root}/{rel}", str(d / "organization_domains.parquet"))
        if hashlib.sha256((d / "organization_domains.parquet").read_bytes()).hexdigest() != self.root_sums[rel]:
            raise SystemExit("ABORT: organization_domains.parquet does not match the root SHA256SUMS")
        self.domains = str(d / "organization_domains.parquet")

    # ---- 1. clone
    def clone(self, p, url, sha):
        dest = self.x / "pinned" / f"{p}.git"
        if LOCAL and os.environ.get("TVL_CLONE_MAP"):
            m = dict(ln.split("\t", 1) for ln in Path(os.environ["TVL_CLONE_MAP"]).read_text().splitlines() if "\t" in ln)
            if p in m:
                repo = Path(m[p].strip())
                self.sh(["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"])
                return repo, 0, 0.0
        if (dest / "tvl-pinned").exists():
            return dest, 0, 0.0
        if LOCAL and not url.startswith("file://"):
            raise RuntimeError("local run: only file:// clone URLs (no clone of project histories on this host)")
        gh = urlparse(url).hostname == "github.com"
        scale = float(os.environ.get("TVL_BACKOFF_SCALE", "1"))
        waits = [float(w) * scale for w in (self.c["BACKOFF_GITHUB"] if gh else self.c["BACKOFF_OTHER"]).split(",")]
        tmp = self.x / "pinned" / f"{p}.git.tmp"
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="/bin/true")
        to = float(self.c["CLONE_TIMEOUT_S"])
        t0, err = time.time(), ""
        for i in range(len(waits) + 1):
            if time.time() > self.t_blame_end or self.cut.is_set():
                raise RuntimeError(f"run cap before clone attempt {i + 1}; last error: {err}")
            shutil.rmtree(tmp, ignore_errors=True)
            self.info[p]["clone_attempts"] = i + 1
            left = max(60.0, min(to, self.t_blame_end - time.time()))
            try:
                self.sh(["git", "init", "-q", "--bare", str(tmp)], env=env)
                g = ["git", "-C", str(tmp), "-c", "protocol.version=2"]
                r = self.sh(g + ["fetch", "-q", "--no-tags", url, sha], timeout=left, check=False, env=env)
                if r.returncode != 0:
                    self.sh(g + ["fetch", "-q", url, "+refs/heads/*:refs/remotes/origin/*", "+refs/tags/*:refs/tags/*"],
                            timeout=left, env=env)
                self.sh(g + ["cat-file", "-e", f"{sha}^{{commit}}"], env=env)
                self.sh(g + ["update-ref", "refs/heads/tvl-pinned", sha], env=env)
                self.sh(g + ["symbolic-ref", "HEAD", "refs/heads/tvl-pinned"], env=env)
                if self.sh(g + ["rev-parse", "--is-shallow-repository"], env=env).stdout.strip() != b"false":
                    raise RuntimeError("shallow clone")
                self.sh(g + ["commit-graph", "write", "--reachable", "--changed-paths"], timeout=to, env=env)
                (tmp / "tvl-pinned").write_text(sha + "\n")
                tmp.rename(dest)
                return dest, i + 1, time.time() - t0
            except (RuntimeError, subprocess.TimeoutExpired) as e:
                err = str(e)[:300] if not isinstance(e, subprocess.TimeoutExpired) else f"timeout {to:.0f} s"
                self.log(f"clone {p} attempt {i + 1} failed: {clean(err)}")
                if i < len(waits):
                    if time.time() + waits[i] >= self.t_blame_end:
                        break
                    time.sleep(waits[i])
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(f"{self.info[p]['clone_attempts']} attempts: {err}")

    # ---- 2. TOM file
    def tom_copy(self, p):
        rel = f"parquet/{p}-dataset.parquet"
        dest = self.x / "tom" / f"{p}-dataset.parquet"
        want = self.root_sums.get(rel)
        if LOCAL:
            src = Path(os.environ["TVL_TOM_DIR"]) / f"{p}-dataset.parquet"
            if not src.exists():
                raise RuntimeError("no TOM file")
            shutil.copyfile(src, dest)
        else:
            if want is None:
                raise RuntimeError(f"{rel} is not in the root SHA256SUMS")
            for i in range(3):
                try:
                    self.s3("cp", f"s3://{self.c['BUCKET']}/{self.c['ROOT']}/{rel}", str(dest))
                    break
                except (RuntimeError, subprocess.TimeoutExpired):
                    if i == 2:
                        raise
                    time.sleep(30)
        if want is not None:
            got = hashlib.sha256(dest.read_bytes()).hexdigest()
            if got != want:
                raise RuntimeError(f"TOM file sha256 {got[:12]} is not the root value {want[:12]}")
        return dest

    def prepare(self, r):
        p = r["project"]
        if self.state[p] != "queued":
            return None
        if time.time() > self.t_blame_end or self.cut.is_set():
            self.set_state(p, "not_started_cap")
            return None
        self.set_state(p, "cloning")
        t0 = time.time()
        try:
            repo, attempts, secs = self.clone(p, r["clone_url"], r["run_commit"])
        except Exception as e:  # noqa: BLE001
            capped = self.cut.is_set() or time.time() > self.t_blame_end
            self.fail(p, "cap" if capped else "clone", self.info[p].get("clone_attempts", 0), time.time() - t0, e)
            self.set_state(p, "not_started_cap" if capped else "clone_failed")
            self.log(f"CLONE FAILED {p}: {clean(e)}")
            return None
        self.info[p].update(clone_s=round(time.time() - t0, 1), clone_attempts=attempts)
        try:
            tom = self.tom_copy(p)
        except Exception as e:  # noqa: BLE001
            self.fail(p, "tom", 3, time.time() - t0, e)
            self.set_state(p, "tom_failed")
            self.log(f"TOM COPY FAILED {p}: {clean(e)}")
            return None
        self.set_state(p, "cloned")
        return p, repo, tom, r["run_commit"]

    # ---- 3.-5. one project
    def project(self, pool, p, repo, tom, sha):
        try:
            work = self.x / "work" / p
            done_meta = work / "blame-meta.tsv"
            if not done_meta.exists():
                self.set_state(p, "blaming")
                files = blame_lines.tom_files(tom)
                self.files_total[p] = len(files)
                pb = blame_lines.ProjectBlame(p, repo, sha, work)

                def task(f):
                    res = blame_lines.one_file(self.runner, repo, sha, f, self.limits)
                    pb.add(res)
                    with self.lock:
                        self.files_done[p] += 1
                futs = [pool.submit(task, f) for f in files]
                for fu in futs:
                    fu.result()
                s = pb.finish(len(files))
                self.info[p].update(files=len(files), blame_wall_s=round(s["wall_s"], 1),
                                    blame_cpu_s=round(s["cpu_s"], 1), **{k: v for k, v in s.items() if k.startswith("limit_")})
                self.log(f"blamed {p}: {len(files)} files, {s['errors']} errors, limits plain {s['limit_plain']} "
                         f"w {s['limit_w']} wmc {s['limit_wmc']} cap {s['limit_cap']}, {s['wall_s'] / 60:.1f} min")
            if not self.measure(p, repo, tom, sha, work):
                return
            self.upload_project(p, work)
        except Exception as e:  # noqa: BLE001
            self.fail(p, "error", 1, 0, e)
            self.set_state(p, "error")
            self.alerts.append(f"{p}: {clean(e)}")
            self.log(f"ERROR {p}: {clean(traceback.format_exc())}")

    def measure(self, p, repo, tom, sha, work):
        self.set_state(p, "measuring")
        rows = int(self.info[p].get("tom_rows") or 0)
        need = int(self.c["MEASURE_BIG_GB"]) if rows > int(self.c["MEASURE_BIG_ROWS"]) else int(self.c["MEASURE_GB"])
        need = min(need, int(self.c["MEASURE_BUDGET_GB"]))
        with self.mem_cond:
            while self.mem_free < need:
                self.mem_cond.wait(30)
            self.mem_free -= need
        try:
            out = work / "out"
            out.mkdir(exist_ok=True)
            tmp = self.x / "duckdb-tmp" / p
            tmp.mkdir(exist_ok=True)
            cmd = [sys.executable, "-I", str(HERE / "measure.py"), "--only", p, "--repo", str(repo), "--commit", sha,
                   "--tom", str(tom), "--work-dir", str(work), "--domains", self.domains, "--out-dir", str(out),
                   "--tag=", "--threads", self.c["MEASURE_THREADS"], "--memory", f"{need}GB", "--temp-dir", str(tmp)]
            t0 = time.time()
            left = max(60.0, self.t_hard - time.time())
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=left)
                rc, err = r.returncode, r.stderr
            except subprocess.TimeoutExpired:
                rc, err = -9, b"timeout at the run cap"
            shutil.rmtree(tmp, ignore_errors=True)
            (work / "measure.log").write_bytes(err[-20000:])
            self.info[p]["measure_s"] = round(time.time() - t0, 1)
            if rc != 0:
                self.fail(p, "measure", 1, time.time() - t0, err.decode("utf-8", "replace")[-300:])
                self.set_state(p, "measure_failed")
                self.alerts.append(f"{p}: measure rc {rc}")
                self.log(f"MEASURE FAILED {p}: rc {rc}")
                return False
            self.log(f"measured {p} in {(time.time() - t0) / 60:.1f} min")
            return True
        finally:
            with self.mem_cond:
                self.mem_free += need
                self.mem_cond.notify_all()

    # ---- leak scan and upload
    @staticmethod
    def leak_scan(paths):
        """(path, number of lines) for each file with an e-mail address shape (text, at sign, domain with a
        dot and letters), or, for a blame.tsv.gz, a line that does not have the exact blame shape (a path, a
        line number, 3 columns of empty or 40 hexadecimal characters, an origin path, a blank flag). A bare
        at sign without an address shape (for example a version in a path) is not a hit: see at_sign_report.
        The scan reads gzip files decompressed."""
        hits = []
        for f in paths:
            f = Path(f)
            if not f.is_file():
                continue
            op = gzip.open if f.suffix == ".gz" else open
            blame = f.name == "blame.tsv.gz"
            n = 0
            with op(f, "rb") as fh:
                for i, ln in enumerate(fh):
                    ln = ln.rstrip(b"\n")
                    if EMAIL.search(ln) or (blame and i > 0 and not BLAME_LINE.match(ln)):
                        n += 1
            if n:
                hits.append((str(f), n))
        return hits

    @staticmethod
    def at_sign_report(project, work, paths):
        """Rows (project, file, column, lines, distinct values, shape) for the bare at signs of the files.
        The shape has letters as a and digits as 9. No value is written."""
        rows = []
        for f in paths:
            f = Path(f)
            if not f.is_file():
                continue
            op = gzip.open if f.suffix == ".gz" else open
            cols = collections.defaultdict(lambda: [0, set()])
            head = None
            with op(f, "rb") as fh:
                for i, ln in enumerate(fh):
                    ln = ln.rstrip(b"\n")
                    if i == 0:
                        head = ln.decode("utf-8", "replace").split("\t")
                    if b"@" not in ln:
                        continue
                    for j, v in enumerate(ln.split(b"\t")):
                        if b"@" in v:
                            c = cols[j]
                            c[0] += 1
                            c[1].add(v)
            for j, (n, vals) in sorted(cols.items()):
                col = head[j] if head and j < len(head) else str(j)
                shapes = collections.Counter(re.sub(r"[0-9]+", "9", re.sub(r"[A-Za-z]+", "a", v.decode("utf-8", "replace")))
                                             for v in vals)
                top = shapes.most_common(1)[0][0] if shapes else ""
                rows.append((project, str(f.relative_to(work)), col, n, len(vals), top))
        return rows

    def project_files(self, work):
        names = ["blame-meta.tsv", "files.tsv", "limits.tsv", "errors.tsv", "measure.log",
                 "out/per-project.tsv", "out/per-language.tsv", "out/examples.tsv"]
        if self.c.get("UPLOAD_BLAME", "1") == "1":
            names.append("blame.tsv.gz")
        return [work / n for n in names if (work / n).exists()]

    def upload_project(self, p, work):
        self.set_state(p, "uploading")
        files = self.project_files(work)
        rows = self.at_sign_report(p, work, files)
        with open(work / "at-signs.tsv", "w") as f:
            f.write("project\tfile\tcolumn\tlines\tdistinct_values\tshape\n")
            for r in rows:
                f.write("\t".join(clean(x) for x in r) + "\n")
        files = files + [work / "at-signs.tsv"]
        hits = self.leak_scan(files)
        if hits:
            self.set_state(p, "leak_held")
            self.alerts.append(f"{p}: at sign in {len(hits)} result files (held, not uploaded)")
            self.fail(p, "leak_scan", 1, 0, "; ".join(f"{Path(h).relative_to(work)} {n} lines" for h, n in hits))
            self.log(f"LEAK SCAN HOLD {p}: " + ", ".join(f"{Path(h).name}={n}" for h, n in hits))
            return
        dest = f"{self.run_prefix()}/results/{p}"
        for f in files:
            self.s3("cp", str(f), f"{dest}/{f.relative_to(work)}")
        self.set_state(p, "done")
        self.log(f"uploaded {p}")

    # ---- progress
    def progress(self, final=False):
        with self.lock:
            cnt = collections.Counter(self.state.values())
            running = [{"project": p, "files_done": self.files_done[p], "files": self.files_total.get(p, 0)}
                       for p, s in self.state.items() if s in ("blaming", "measuring", "uploading", "cloning")]
            fd, ft = sum(self.files_done.values()), sum(self.files_total.values())
        try:
            load = os.getloadavg()[0]
        except OSError:
            load = -1
        free = shutil.disk_usage(self.x).free / 1e9
        pr = {"utc": utc(), "run": self.c.get("TVL_RUN", "local"), "elapsed_h": round((time.time() - self.start) / 3600, 3),
              "cap_h": float(self.c["CAP_H"]), "blame_stop_utc": utc(self.t_blame_end), "projects": len(self.state),
              "counts": dict(cnt), "files_done": fd, "files_known": ft, "running": running[:30],
              "failures": len(self.failures), "alerts": self.alerts[-10:], "load1": round(load, 1),
              "disk_free_gb": round(free, 1), "cut": self.cut.is_set(), "final": final}
        f = self.x / "log" / "progress.json"
        f.write_text(json.dumps(pr, indent=1))
        return f

    def progress_loop(self, stop):
        last_up = 0.0
        while not stop.wait(60):
            try:
                f = self.progress()
                if time.time() - last_up >= float(self.c["PROGRESS_S"]):
                    if not self.leak_scan([f]):
                        self.s3("cp", str(f), f"{self.run_prefix()}/log/progress.json", timeout=300)
                    last_up = time.time()
            except Exception as e:  # noqa: BLE001
                self.log(f"progress upload failed: {clean(e)}")

    def cap_watch(self, stop):
        while not stop.wait(30):
            stop_file = (self.x / "STOP").exists()
            if (time.time() >= self.t_blame_end or stop_file) and not self.cut.is_set():
                self.cut.set()
                self.log(f"RUN CAP ({'STOP file' if stop_file else 'time'}): the blames stop now; "
                         "started projects are measured with what they have")
                self.runner.abort()

    # ---- tables at the end
    def merge_tables(self):
        t = self.x / "tables"

        def cat(name, srcs, header=None):
            keys, rows = [], []
            for s in srcs:
                if not s.exists():
                    continue
                lines = s.read_text().splitlines()
                if not lines:
                    continue
                hk = lines[0].split("\t")
                for k in hk:
                    if k not in keys:
                        keys.append(k)
                rows.extend(dict(zip(hk, ln.split("\t"))) for ln in lines[1:] if ln)
            keys = keys or (header or [])
            with open(t / name, "w") as f:
                f.write("\t".join(keys) + "\n")
                for r in rows:
                    f.write("\t".join(r.get(k, "") for k in keys) + "\n")
        done = [p for p, s in self.state.items() if s == "done"]
        w = self.x / "work"
        cat("per-project.tsv", [w / p / "out" / "per-project.tsv" for p in done])
        cat("per-language.tsv", [w / p / "out" / "per-language.tsv" for p in done])
        cat("examples.tsv", [w / p / "out" / "examples.tsv" for p in done])
        cat("limits.tsv", [w / p / "limits.tsv" for p in done], ["project", "file_path", "blame", "limit_s", "seconds"])
        cat("errors.tsv", [w / p / "errors.tsv" for p in done], ["project", "file_path", "blame", "message"])
        cat("blame-meta.tsv", [w / p / "blame-meta.tsv" for p in done])
        cat("at-signs.tsv", [w / p / "at-signs.tsv" for p in done], ["project", "file", "column", "lines", "distinct_values", "shape"])
        with open(t / "failures.tsv", "w") as f:
            f.write("project\tdraw_rank\thost\tstage\tattempts\tseconds\tmessage\n")
            for r in sorted(self.failures, key=lambda r: int(r[1])):
                f.write("\t".join(str(x) for x in r) + "\n")
        cols = ["project", "draw_rank", "language", "host", "state", "run_commit", "clone_attempts", "clone_s",
                "files", "limit_plain", "limit_w", "limit_wmc", "limit_cap", "blame_wall_s", "blame_cpu_s", "measure_s"]
        with open(t / "status.tsv", "w") as f:
            f.write("\t".join(cols) + "\n")
            for p in sorted(self.state, key=lambda p: int(self.info[p]["draw_rank"])):
                d = {"project": p, "state": self.state[p], **self.info[p]}
                f.write("\t".join(clean(d.get(k, "")) for k in cols) + "\n")
        info = {"run": self.c.get("TVL_RUN", "local"), "start_utc": utc(self.start), "end_utc": utc(),
                "elapsed_h": f"{(time.time() - self.start) / 3600:.3f}", "cap_h": self.c["CAP_H"],
                "cap_reached": str(int(self.cut.is_set())), "jobs": self.c["JOBS"],
                "limits_s": f"plain {self.c['LIMIT_PLAIN']}, w {self.c['LIMIT_W']}, wmc {self.c['LIMIT_WMC']}",
                "git": self.sh(["git", "--version"]).stdout.decode().strip(),
                "python": sys.version.split()[0], "duckdb": __import__("duckdb").__version__,
                "release_root": self.c["ROOT"], "root_sums_sha256": self.c.get("ROOT_SUMS_SHA", ""),
                "kit_sums_sha256": self.c.get("KIT_SUMS", ""), "nproc": str(os.cpu_count()),
                "instance_type": os.environ.get("TVL_ITYPE", "")}
        with open(t / "run-info.tsv", "w") as f:
            f.write("key\tvalue\n")
            for k, v in info.items():
                f.write(f"{k}\t{clean(v)}\n")
        return sorted(t.glob("*.tsv"))

    # ---- main
    def go(self):
        self.log(f"START run {self.c.get('TVL_RUN', 'local')}: {len(self.plan)} projects, {self.c['JOBS']} jobs, "
                 f"blames stop at {utc(self.t_blame_end)}, local={int(LOCAL)}")
        for p in self.state:
            sf = self.x / "state" / f"{p}.json"
            if sf.exists():
                s = json.loads(sf.read_text())
                if s["state"] in ("done", "clone_failed", "tom_failed"):
                    self.state[p] = s["state"]
                    self.info[p].update({k: v for k, v in s.items() if k != "state"})
        for r in self.plan:
            self.info[r["project"]]["tom_rows"] = r.get("rows", "")
        self.fetch_root()
        stop = threading.Event()
        threads = [threading.Thread(target=self.progress_loop, args=(stop,), daemon=True),
                   threading.Thread(target=self.cap_watch, args=(stop,), daemon=True)]
        for th in threads:
            th.start()
        managers = []
        with cf.ThreadPoolExecutor(int(self.c["JOBS"])) as pool, \
                cf.ThreadPoolExecutor(int(self.c["CLONE_JOBS"])) as prep:
            preps = [prep.submit(self.prepare, r) for r in self.plan]
            # the clones start in plan order (the largest first); a project goes to the blame pool as soon
            # as it is ready, so a slow clone with backoff does not hold the others
            for fu in cf.as_completed(preps):
                res = fu.result()
                if res is None:
                    continue
                th = threading.Thread(target=self.project, args=(pool, *res))
                th.start()
                managers.append(th)
            for th in managers:
                th.join()
        for p, s in self.state.items():
            if s == "queued":
                self.set_state(p, "not_started_cap")
        stop.set()
        tabs = self.merge_tables()
        hits = self.leak_scan(tabs)
        if hits:
            self.alerts.append(f"at sign in the tables: {hits}")
            self.log(f"LEAK SCAN HOLD tables: {hits}")
        else:
            for f in tabs:
                self.s3("cp", str(f), f"{self.run_prefix()}/tables/{f.name}")
        cnt = collections.Counter(self.state.values())
        bad = [s for s in cnt if s not in ("done", "clone_failed", "tom_failed", "not_started_cap")]
        status = "ALERT" if (self.alerts or bad) else "DONE"
        summary = (f"{status} {utc()}: " + ", ".join(f"{k} {v}" for k, v in sorted(cnt.items())) +
                   f"; cap reached {int(self.cut.is_set())}; alerts {len(self.alerts)}")
        self.log(summary)
        f = self.progress(final=True)
        (self.x / "status" / f"run.{status}").write_text(summary + "\n")
        logs = [f, self.x / "log" / "run.log", self.x / "status" / f"run.{status}"]
        lh = self.leak_scan(logs)
        for g in logs:
            if any(h[0] == str(g) for h in lh):
                continue
            sub = "status" if g.parent.name == "status" else "log"
            self.s3("cp", str(g), f"{self.run_prefix()}/{sub}/{g.name}")
        return status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--x", required=True)
    a = ap.parse_args()
    conf = read_conf(a.conf)
    lines = Path(a.plan).read_text().splitlines()
    hk = lines[0].split("\t")
    plan = [dict(zip(hk, ln.split("\t"))) for ln in lines[1:] if ln]
    status = Run(conf, plan, a.x).go()
    print(status)
    sys.exit(0 if status == "DONE" else 3)


if __name__ == "__main__":
    main()
