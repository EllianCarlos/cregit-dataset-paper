#!/usr/bin/env python3
"""jv_pull.py: the pull of machine A (P1; run as ec2-user by /usr/local/bin/jv-pull).

Commands:
  pull    --listing F --prefix P --s3 S3URL --stage DIR --blame DIR --parts DIR --n N --state DIR
          F is "aws s3 ls --recursive" of S3URL/out/ (keys start with P). A batch k/seq is
          complete when out/<k>/batches/b-<seq>.tar.zst, .list and .sha256 are all listed (the
          extra sends the .sha256 last). For each complete batch that is not in state/applied.tsv:
          download the 3 files into DIR (stage, the file system of the blame dir), check the
          sha256, check that the tar members are exactly the names of the .list and that each
          name is a "<file>.blame" of a file of part k, unpack into a new temp dir, and put each
          file in place with link(2) + unlink: link never replaces a file, so an existing .blame
          (machine A's own, or an earlier pull) always stays. Then the batch goes to applied.tsv
          and each new file to linked.tsv as "<epoch><TAB><index of A's order>" (no names).
  apos    --left L --log PIPELINE_LOG --state DIR
          Machine A's newest started index (as jv_split.py apos), read on from the last offset.
  decide  --listing F --prefix P --n N --state DIR --apos A --a-start EPOCH --now EPOCH
          --stale-min M --restart-min R
          Prints "RESTART <why>" or "WAIT <why>". RESTART needs: every complete batch applied;
          each part finished (DONE, STOPPED or GATE-FAILED, or no status.txt, or a status.txt
          older than M minutes); and at least R files linked after A's last start whose index is
          above A's newest started index (files that A's current list would blame again).
Stdout is counts only (no file names).
"""
import argparse
import calendar
import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import time

BATCH_RX = re.compile(r"^(\d+)/batches/b-(\d{6})\.(tar\.zst|list|sha256)$")
START_RX = re.compile(r"^(\d+): (.*)$")


def parse_listing(path, prefix):
    """{relative key: (size, epoch)} of an "aws s3 ls --recursive" output (UTC times)."""
    out = {}
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        for line in f:
            line = line.rstrip("\n")
            parts = line.split(None, 3)
            if len(parts) != 4 or not parts[3].startswith(prefix):
                continue
            d, t, size, key = parts
            try:
                ep = calendar.timegm(time.strptime(d + " " + t, "%Y-%m-%d %H:%M:%S"))
                size = int(size)
            except ValueError:
                continue
            out[key[len(prefix):]] = (size, ep)
    return out


def complete_batches(listing):
    have = {}
    for key in listing:
        m = BATCH_RX.match(key)
        if m:
            have.setdefault((int(m.group(1)), m.group(2)), set()).add(m.group(3))
    return sorted(b for b, kinds in have.items() if kinds == {"tar.zst", "list", "sha256"})


def read_applied(state):
    done = set()
    p = os.path.join(state, "applied.tsv")
    if os.path.exists(p):
        for line in open(p):
            f = line.split("\t")
            if len(f) >= 2:
                done.add((int(f[0]), f[1]))
    return done


def part_index(parts_dir, k, cache):
    if k not in cache:
        m = {}
        p = os.path.join(parts_dir, "part-%d.tsv" % k)
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="surrogateescape") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if line:
                        i, _, name = line.split("\t", 2)
                        m[name] = int(i)
        cache[k] = m
    return cache[k]


def safe_name(n):
    if not n.endswith(".blame") or n.startswith("/") or "\0" in n:
        return False
    return all(c not in ("", ".", "..") for c in n.split("/"))


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def tar_names(tarzst):
    p1 = subprocess.Popen(["zstd", "-q", "-dc", tarzst], stdout=subprocess.PIPE)
    out = subprocess.run(["tar", "-tf", "-"], stdin=p1.stdout, capture_output=True)
    p1.stdout.close()
    rc1 = p1.wait()
    if rc1 != 0 or out.returncode != 0:
        return None
    return [n for n in out.stdout.decode("utf-8", "surrogateescape").split("\n") if n]


def unpack(tarzst, dest):
    p1 = subprocess.Popen(["zstd", "-q", "-dc", tarzst], stdout=subprocess.PIPE)
    out = subprocess.run(["tar", "-xf", "-", "-C", dest, "--no-same-owner"], stdin=p1.stdout)
    p1.stdout.close()
    return p1.wait() == 0 and out.returncode == 0


def put_file(src, dst):
    """link + unlink: a rename that never replaces dst. Returns 'linked' or 'exists'."""
    d = os.path.dirname(dst)
    if d:
        os.makedirs(d, exist_ok=True)
    try:
        os.link(src, dst)
        r = "linked"
    except FileExistsError:
        r = "exists"
    os.unlink(src)
    return r


def do_pull(a):
    listing = parse_listing(a.listing, a.prefix)
    applied = read_applied(a.state)
    cache = {}
    new = [b for b in complete_batches(listing) if b not in applied and 1 <= b[0] <= a.n]
    dl = os.path.join(a.stage, "dl")
    os.makedirs(dl, exist_ok=True)
    tot = {"batches": 0, "bad": 0, "linked": 0, "exists": 0, "refused": 0}
    for k, seq in new:
        base = "b-%s" % seq
        names = {}
        ok = True
        for ext in ("tar.zst", "list", "sha256"):
            loc = os.path.join(dl, "%d-%s.%s" % (k, base, ext))
            names[ext] = loc
            if os.path.exists(loc):
                os.unlink(loc)
            r = subprocess.run([a.aws, "s3", "cp", "%s/out/%d/batches/%s.%s" % (a.s3, k, base, ext), loc,
                                "--only-show-errors"], capture_output=True)
            if r.returncode != 0 or not os.path.exists(loc):
                ok = False
                break
        if not ok:
            print("pull: part %d batch %s: download failed, next run tries again" % (k, seq))
            continue
        want = open(names["sha256"]).read().split()
        status = "ok"
        if not want or want[0] != sha256_of(names["tar.zst"]):
            status = "bad-sha256"
        lst = [n for n in open(names["list"], encoding="utf-8", errors="surrogateescape").read().split("\n") if n]
        pidx = part_index(a.parts, k, cache)
        refused = [n for n in lst if not safe_name(n) or n[:-len(".blame")] not in pidx]
        if status == "ok":
            members = tar_names(names["tar.zst"])
            if members is None:
                status = "bad-tar"
            elif sorted(members) != sorted(lst) or len(set(lst)) != len(lst):
                status = "bad-members"
        x = os.path.join(a.stage, "x-%d-%s" % (k, seq))
        linked = exists = 0
        if status == "ok":
            if os.path.exists(x):
                shutil.rmtree(x)
            os.makedirs(x)
            if not unpack(names["tar.zst"], x):
                status = "bad-unpack"
        if status == "ok":
            now = int(time.time())
            with open(os.path.join(a.state, "linked.tsv"), "a") as lk:
                for n in lst:
                    if n in refused:
                        continue
                    src = os.path.join(x, n)
                    st = os.lstat(src)
                    if not stat.S_ISREG(st.st_mode):
                        refused.append(n)
                        continue
                    if put_file(src, os.path.join(a.blame, n)) == "linked":
                        linked += 1
                        lk.write("%d\t%d\n" % (now, pidx[n[:-len(".blame")]]))
                    else:
                        exists += 1
        if os.path.exists(x):
            shutil.rmtree(x)
        for loc in names.values():
            if os.path.exists(loc):
                os.unlink(loc)
        with open(os.path.join(a.state, "applied.tsv"), "a") as ap:
            ap.write("%d\t%s\t%d\t%s\t%d\t%d\t%d\n" % (k, seq, int(time.time()), status, linked, exists, len(refused)))
        tot["batches"] += 1
        tot["bad"] += status != "ok"
        tot["linked"] += linked
        tot["exists"] += exists
        tot["refused"] += len(refused)
        print("pull: part %d batch %s: %s, %d files, linked %d, exists %d, refused %d"
              % (k, seq, status, len(lst), linked, exists, len(refused)))
    print("pull total: new batches %d (bad %d), linked %d, exists %d, refused %d"
          % (tot["batches"], tot["bad"], tot["linked"], tot["exists"], tot["refused"]))
    return 1 if tot["bad"] or tot["refused"] else 0


def do_apos(a):
    idx = {}
    with open(a.left, encoding="utf-8", errors="surrogateescape") as f:
        for line in f:
            line = line.rstrip("\n")
            if line:
                i, _, name = line.split("\t", 2)
                idx[name] = int(i)
    sp = os.path.join(a.state, "apos.state")
    off, best = 0, 0
    if os.path.exists(sp):
        try:
            off, best = [int(x) for x in open(sp).read().split()[:2]]
        except ValueError:
            off, best = 0, 0
    size = os.path.getsize(a.log)
    if size < off:
        off, best = 0, 0
    with open(a.log, "rb") as f:
        f.seek(off)
        data = f.read()
    end = data.rfind(b"\n") + 1
    for raw in data[:end].split(b"\n"):
        m = START_RX.match(raw.decode("utf-8", "surrogateescape").rstrip("\r"))
        if m:
            i = idx.get(m.group(2))
            if i is not None and i > best:
                best = i
    with open(sp + ".tmp", "w") as o:
        o.write("%d %d\n" % (off + end, best))
    os.replace(sp + ".tmp", sp)
    print(best)
    return 0


def do_decide(a):
    listing = parse_listing(a.listing, a.prefix)
    applied = read_applied(a.state)
    pending = [b for b in complete_batches(listing) if b not in applied and 1 <= b[0] <= a.n]
    if pending:
        print("WAIT %d complete batches are not applied yet" % len(pending))
        return 0
    live = []
    for k in range(1, a.n + 1):
        if any(("%d/%s" % (k, m)) in listing for m in ("DONE", "STOPPED", "GATE-FAILED")):
            continue
        st = listing.get("%d/status.txt" % k)
        if st is None:
            continue
        if a.now - st[1] > a.stale_min * 60:
            continue
        live.append(k)
    if live:
        print("WAIT parts still running: %s" % " ".join(str(k) for k in live))
        return 0
    waste = 0
    p = os.path.join(a.state, "linked.tsv")
    if os.path.exists(p):
        for line in open(p):
            f = line.split()
            if len(f) == 2 and int(f[0]) > a.a_start and int(f[1]) > a.apos:
                waste += 1
    if waste >= a.restart_min:
        print("RESTART %d files linked after A's last start lie ahead of A (index > %d)" % (waste, a.apos))
    else:
        print("WAIT only %d linked files ahead of A (need %d)" % (waste, a.restart_min))
    return 0


def main(argv):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull")
    for x in ("--listing", "--prefix", "--s3", "--stage", "--blame", "--parts", "--state"):
        p.add_argument(x, required=True)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--aws", default=os.environ.get("JV_AWS", "aws"))
    p = sub.add_parser("apos")
    for x in ("--left", "--log", "--state"):
        p.add_argument(x, required=True)
    p = sub.add_parser("decide")
    for x in ("--listing", "--prefix", "--state"):
        p.add_argument(x, required=True)
    for x in ("--n", "--apos", "--a-start", "--now", "--stale-min", "--restart-min"):
        p.add_argument(x, type=int, required=True)
    a = ap.parse_args(argv)
    os.makedirs(a.state, exist_ok=True)
    return {"pull": do_pull, "apos": do_apos, "decide": do_decide}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
