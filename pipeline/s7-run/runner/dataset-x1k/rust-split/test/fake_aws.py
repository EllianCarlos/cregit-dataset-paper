#!/usr/bin/env python3
"""A fake "aws" for the tests: s3 ls / cp / rm on a local folder FAKE_S3 (s3://b/k -> FAKE_S3/b/k).
ls prints as the real CLI: "YYYY-MM-DD HH:MM:SS <size> <key>" (local time, so TZ applies).
FAKE_AWS_FAIL=<substring>: a cp whose source or target has it fails (exit 1)."""
import os
import shutil
import sys
import time

root = os.environ["FAKE_S3"]


def path(u):
    assert u.startswith("s3://"), u
    return os.path.join(root, u[5:])


def main(a):
    a = [x for x in a if x not in ("--only-show-errors", "--no-progress")]
    if "--expected-size" in a:
        i = a.index("--expected-size")
        del a[i:i + 2]
    if len(a) < 2 or a[0] != "s3":
        print("fake aws: only s3", file=sys.stderr)
        return 2
    cmd = a[1]
    fail = os.environ.get("FAKE_AWS_FAIL")
    if cmd == "ls":
        rec = "--recursive" in a
        u = [x for x in a[2:] if x.startswith("s3://")][0]
        p = path(u)
        bucket = u[5:].split("/", 1)[0]
        broot = os.path.join(root, bucket)
        out = []
        if rec:
            base = p if os.path.isdir(p) else os.path.dirname(p)
            for d, _, fs in os.walk(base):
                for f in fs:
                    full = os.path.join(d, f)
                    key = os.path.relpath(full, broot)
                    if key.startswith(u[5:].split("/", 1)[1] if "/" in u[5:] else ""):
                        out.append((full, key))
        else:
            if u.endswith("/") and os.path.isdir(p):
                for f in sorted(os.listdir(p)):
                    full = os.path.join(p, f)
                    if os.path.isdir(full):
                        out.append((None, "PRE %s/" % f))
                    else:
                        out.append((full, f))
            elif os.path.isfile(p):
                out.append((p, os.path.basename(p)))
            else:
                d, pre = os.path.dirname(p), os.path.basename(p)
                if os.path.isdir(d):
                    for f in sorted(os.listdir(d)):
                        if f.startswith(pre) and os.path.isfile(os.path.join(d, f)):
                            out.append((os.path.join(d, f), f))
        if not out:
            return 1
        for full, key in sorted(out, key=lambda x: x[1]):
            if full is None:
                print("                           " + key)
            else:
                st = os.stat(full)
                print("%s %10d %s" % (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)), st.st_size, key))
        return 0
    if cmd == "cp":
        rec = "--recursive" in a
        excl = []
        rest = []
        i = 2
        while i < len(a):
            if a[i] == "--exclude":
                excl.append(a[i + 1]); i += 2; continue
            if a[i] == "--recursive":
                i += 1; continue
            rest.append(a[i]); i += 1
        src, dst = rest[0], rest[1]
        if fail and (fail in src or fail in dst):
            print("fake aws: injected failure", file=sys.stderr)
            return 1
        if rec:
            sp = path(src)
            for d, _, fs in os.walk(sp):
                for f in fs:
                    rel = os.path.relpath(os.path.join(d, f), sp)
                    if rel in excl:
                        continue
                    t = os.path.join(dst, rel)
                    os.makedirs(os.path.dirname(t), exist_ok=True)
                    shutil.copyfile(os.path.join(d, f), t)
            return 0
        if src == "-":
            data = sys.stdin.buffer.read()
        elif src.startswith("s3://"):
            if not os.path.isfile(path(src)):
                print("fake aws: no such key", file=sys.stderr)
                return 1
            data = open(path(src), "rb").read()
        else:
            data = open(src, "rb").read()
        if dst == "-":
            sys.stdout.buffer.write(data)
        elif dst.startswith("s3://"):
            t = path(dst)
            os.makedirs(os.path.dirname(t), exist_ok=True)
            with open(t + ".fake-tmp", "wb") as f:
                f.write(data)
            os.replace(t + ".fake-tmp", t)
        else:
            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(data)
        return 0
    if cmd == "rm":
        p = path(a[2])
        if os.path.isfile(p):
            os.unlink(p)
            return 0
        return 1
    print("fake aws: no %s" % cmd, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
