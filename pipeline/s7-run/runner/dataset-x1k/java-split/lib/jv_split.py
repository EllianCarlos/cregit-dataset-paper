#!/usr/bin/env python3
"""jv_split.py: the split of the files left (machine A, E1; also used by the tests).

Commands:
  apos  --left L --log PIPELINE_LOG
        The index (in L) of the newest file that step 7 of machine A started: the largest
        index among the names of the "<count>: <name>" lines of blameRepoFiles.pl. 0 if none.
  split --left L --apos A --head H --n N --out DIR
        head = the files with index <= A + H (machine A keeps them). tail = the rest.
        Part k (1..N) = every N-th file of the tail, starting at the k-th. Writes DIR/head.tsv,
        DIR/part-<k>.tsv ("index<TAB>size<TAB>name", index order) and DIR/split.txt.
  check --left L --out DIR --n N
        Proves the split: no file in two parts, no head file in a part, head + parts = left.
  gate  --done D --blame-dir B --log PIPELINE_LOG --since EPOCH --count C --out FILE
        C files that machine A finished (a .blame exists, mtime >= EPOCH), not PLAIN-BLAME,
        spread evenly over the candidates sorted by size and name. Writes "size<TAB>name".
Output on stdout is counts only (no file names).
"""
import argparse
import os
import re
import sys

START_RX = re.compile(r"^(\d+): (.*)$")
PLAIN_RX = re.compile(r"^PLAIN-BLAME (.*) after \d+ s of -C100$")


def read_left(path):
    rows = []
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            i, s, name = line.split("\t", 2)
            rows.append((int(i), int(s), name))
    for n, r in enumerate(rows, 1):
        if r[0] != n:
            raise ValueError("left list: line %d has index %d" % (n, r[0]))
    return rows


def write_rows(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", errors="surrogateescape") as f:
        for i, s, name in rows:
            f.write("%d\t%d\t%s\n" % (i, s, name))
    os.replace(tmp, path)


def log_lines(path):
    with open(path, "rb") as f:
        for raw in f:
            yield raw.decode("utf-8", "surrogateescape").rstrip("\n").rstrip("\r")


def apos(left, lines):
    idx = {name: i for i, _, name in left}
    best = 0
    for line in lines:
        m = START_RX.match(line)
        if m:
            i = idx.get(m.group(2))
            if i is not None and i > best:
                best = i
    return best


def split(left, a, head_files, n):
    if n < 1:
        raise ValueError("n must be >= 1")
    if a < 0 or head_files < 0:
        raise ValueError("apos and head must be >= 0")
    bound = a + head_files
    head = [r for r in left if r[0] <= bound]
    tail = [r for r in left if r[0] > bound]
    parts = {k: [] for k in range(1, n + 1)}
    for j, r in enumerate(tail):
        parts[j % n + 1].append(r)
    return head, parts


def check(left, head, parts):
    """Returns a list of problems (empty = the split is right)."""
    probs = []
    seen = {}
    for k, rows in parts.items():
        for r in rows:
            if r[2] in seen:
                probs.append("a file is in part %d and part %d" % (seen[r[2]], k))
            seen[r[2]] = k
        idx = [r[0] for r in rows]
        if idx != sorted(idx):
            probs.append("part %d is not in index order" % k)
    hn = {r[2] for r in head}
    both = hn & set(seen)
    if both:
        probs.append("%d head files are in a part" % len(both))
    if head and seen:
        hmax = max(r[0] for r in head)
        pmin = min(r[0] for rows in parts.values() for r in rows)
        if pmin <= hmax:
            probs.append("a part file has an index (%d) inside the head (max %d)" % (pmin, hmax))
    union = hn | set(seen)
    ln = {r[2] for r in left}
    if union != ln:
        probs.append("head + parts != left: %d missing, %d extra" % (len(ln - union), len(union - ln)))
    total = len(head) + sum(len(v) for v in parts.values())
    if total != len(left):
        probs.append("row count %d != left %d" % (total, len(left)))
    sizes = [len(v) for v in parts.values()]
    if sizes and max(sizes) - min(sizes) > 1:
        probs.append("parts differ by more than one file: %s" % sizes)
    return probs


def gate(done_rows, plain, mtime_of, since, count):
    cand = []
    for s, name in done_rows:
        if name in plain:
            continue
        mt = mtime_of(name)
        if mt is None or mt < since:
            continue
        cand.append((s, name))
    cand.sort()
    if len(cand) < count:
        raise ValueError("only %d gate candidates, need %d" % (len(cand), count))
    if count == 1:
        return [cand[len(cand) // 2]]
    step = (len(cand) - 1) / (count - 1)
    pick = []
    used = set()
    for j in range(count):
        k = int(round(j * step))
        while k in used:
            k += 1
        used.add(k)
        pick.append(cand[k])
    return pick


def main(argv):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apos"); p.add_argument("--left", required=True); p.add_argument("--log", required=True)
    p = sub.add_parser("split")
    for a in ("--left", "--out"):
        p.add_argument(a, required=True)
    for a in ("--apos", "--head", "--n"):
        p.add_argument(a, required=True, type=int)
    p = sub.add_parser("check"); p.add_argument("--left", required=True); p.add_argument("--out", required=True)
    p.add_argument("--n", required=True, type=int)
    p = sub.add_parser("gate")
    for a in ("--done", "--blame-dir", "--log", "--out"):
        p.add_argument(a, required=True)
    p.add_argument("--since", required=True, type=float); p.add_argument("--count", required=True, type=int)
    a = ap.parse_args(argv)

    if a.cmd == "apos":
        print(apos(read_left(a.left), log_lines(a.log)))
        return 0
    if a.cmd == "split":
        left = read_left(a.left)
        head, parts = split(left, a.apos, a.head, a.n)
        os.makedirs(a.out, exist_ok=True)
        write_rows(os.path.join(a.out, "head.tsv"), head)
        for k, rows in parts.items():
            write_rows(os.path.join(a.out, "part-%d.tsv" % k), rows)
        probs = check(left, head, parts)
        with open(os.path.join(a.out, "split.txt"), "w") as f:
            f.write("left %d apos %d head_files %d n %d\n" % (len(left), a.apos, a.head, a.n))
            f.write("head %d (index 1-%d)\n" % (len(head), head[-1][0] if head else 0))
            for k, rows in parts.items():
                f.write("part %d: %d files, index %s-%s\n" % (k, len(rows), rows[0][0] if rows else "-", rows[-1][0] if rows else "-"))
            f.write("check: %s\n" % ("OK" if not probs else "; ".join(probs)))
        sys.stdout.write(open(os.path.join(a.out, "split.txt")).read())
        return 0 if not probs else 1
    if a.cmd == "check":
        left = read_left(a.left)
        head = read_left_any(os.path.join(a.out, "head.tsv"))
        parts = {k: read_left_any(os.path.join(a.out, "part-%d.tsv" % k)) for k in range(1, a.n + 1)}
        probs = check(left, head, parts)
        print("check: " + ("OK" if not probs else "; ".join(probs)))
        return 0 if not probs else 1
    if a.cmd == "gate":
        done_rows = []
        with open(a.done, encoding="utf-8", errors="surrogateescape") as f:
            for line in f:
                line = line.rstrip("\n")
                if line:
                    s, name = line.split("\t", 1)
                    done_rows.append((int(s), name))
        plain = set()
        for line in log_lines(a.log):
            m = PLAIN_RX.match(line)
            if m:
                plain.add(m.group(1))

        def mtime_of(name):
            try:
                return os.stat(os.path.join(a.blame_dir, name + ".blame")).st_mtime
            except OSError:
                return None
        pick = gate(done_rows, plain, mtime_of, a.since, a.count)
        with open(a.out, "w", encoding="utf-8", errors="surrogateescape") as f:
            for s, name in pick:
                f.write("%d\t%s\n" % (s, name))
        print("gate: %d files of %d done (%d PLAIN-BLAME names excluded), sizes %d-%d B"
              % (len(pick), len(done_rows), len(plain), pick[0][0], pick[-1][0]))
        return 0
    return 2


def read_left_any(path):
    rows = []
    with open(path, encoding="utf-8", errors="surrogateescape") as f:
        for line in f:
            line = line.rstrip("\n")
            if line:
                i, s, name = line.split("\t", 2)
                rows.append((int(i), int(s), name))
    return rows


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
