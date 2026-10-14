#!/usr/bin/env python3
"""render.py: put the account values back into the runner copies, or check the copies.

Usage:
  python3 -I render.py --check [--env FILE]   check each copy against ORIGIN.tsv
  python3 -I render.py --out DIR [--env FILE] write the rendered files into DIR

The copies in this directory are the scripts that ran the dataset build on EC2.
A copy of kind "parametrized" has a token ${RUNNER_NAME} in place of an account value
(the bucket, the account id, the AWS profile, the region, the EC2 ids, the home paths).
The file runner.env gives the value of each token. This script reads runner.env as text.
It does not run it. Each line is NAME=VALUE or NAME='VALUE'.

--check does these steps for each row of ORIGIN.tsv:
  1. The sha256 of the copy is equal to copy_sha256.
  2. Kind "verbatim": the sha256 of the copy is equal to source_sha256.
  3. Kind "parametrized", when runner.env is present: the sha256 of the rendered copy is
     equal to source_sha256. So the copy is the file that ran, with the tokens only.
The exit status is 0 when all checks pass, else 1.
"""
import argparse
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = re.compile(rb"\$\{(RUNNER_[A-Z0-9_]+)\}")


def read_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name, _, value = line.partition("=")
            if len(value) >= 2 and value[0] == value[-1] == "'":
                value = value[1:-1]
            env[name.strip()] = value
    return env


def render(data, env):
    def value(m):
        name = m.group(1).decode()
        if name not in env:
            raise KeyError(f"{name} is not in runner.env")
        return env[name].encode()
    return TOKEN.sub(value, data)


def rows():
    with open(os.path.join(HERE, "ORIGIN.tsv"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            src, src_sha, copy, kind, copy_sha, names = (line.rstrip("\n").split("\t") + [""])[:6]
            # copy_path starts with "s7-run/runner/". Make it relative to this directory.
            yield src, src_sha, copy.split("runner/", 1)[1], kind, copy_sha


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--out")
    ap.add_argument("--env", default=os.path.join(HERE, "runner.env"))
    a = ap.parse_args()
    env = read_env(a.env) if os.path.exists(a.env) else None
    if a.out and env is None:
        sys.exit(f"error: {a.env} is missing (copy runner.env.example and fill it)")
    n = {"verbatim": 0, "parametrized": 0, "not checked": 0}
    bad = 0
    for src, src_sha, rel, kind, copy_sha in rows():
        data = open(os.path.join(HERE, rel), "rb").read()
        if a.out:
            out = os.path.join(a.out, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as f:
                f.write(render(data, env))
            os.chmod(out, os.stat(os.path.join(HERE, rel)).st_mode & 0o7777)
            continue
        if sha(data) != copy_sha:
            bad += 1
            print(f"BAD  {rel}: the copy changed (copy_sha256)")
            continue
        if kind == "verbatim":
            ok = sha(data) == src_sha
        elif env is None:
            n["not checked"] += 1
            continue
        else:
            ok = sha(render(data, env)) == src_sha
        if ok:
            n[kind] += 1
        else:
            bad += 1
            print(f"BAD  {rel}: not equal to {src}")
    if a.out:
        print(f"wrote the rendered files into {a.out}")
        return 0
    print(f"verbatim equal: {n['verbatim']}, parametrized equal after render: {n['parametrized']}, "
          f"parametrized not checked (no runner.env): {n['not checked']}, bad: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
