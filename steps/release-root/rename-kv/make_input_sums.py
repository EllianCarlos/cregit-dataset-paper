#!/usr/bin/env python3
"""Write the SHA256SUMS of dataset release 2 input (parquet/ and organizations/).

The sha256 of each project file comes from the rename log (out_sha256, read
from the written file).  The tool checks the size of each file against the
log, and computes the sha256 of each file of organizations/.  Lines are
"<sha256>  <path relative to the root>", sorted (LC_ALL=C order).

Usage: python -I make_input_sums.py ROOT LOG_TSV OUT
"""
import csv
import hashlib
import os
import sys

root, log, out = sys.argv[1:4]
csv.field_size_limit(1 << 30)
rows = {}
with open(log) as fh:
    for r in csv.DictReader(fh, delimiter="\t"):
        if r["status"] == "OK":
            rows[r["file"]] = r  # the last OK row of a file wins
names = sorted(n for n in os.listdir(os.path.join(root, "parquet")) if n.endswith(".parquet"))
extra = sorted(os.listdir(os.path.join(root, "parquet")))
if len(names) != len(extra):
    sys.exit(f"parquet/ has files that are not .parquet: {sorted(set(extra) - set(names))[:5]}")
missing = [n for n in names if n not in rows]
if missing:
    sys.exit(f"{len(missing)} files have no OK row in the log, for example {missing[:3]}")
lines = []
total = 0
for n in names:
    size = os.path.getsize(os.path.join(root, "parquet", n))
    if size != int(rows[n]["out_size"]):
        sys.exit(f"{n}: size {size} is not the logged {rows[n]['out_size']}")
    total += size
    lines.append((f"parquet/{n}", rows[n]["out_sha256"]))
for n in sorted(os.listdir(os.path.join(root, "organizations"))):
    p = os.path.join(root, "organizations", n)
    if not os.path.isfile(p) or n.startswith("."):
        sys.exit(f"unexpected entry in organizations/: {n}")
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    total += os.path.getsize(p)
    lines.append((f"organizations/{n}", h.hexdigest()))
lines.sort(key=lambda x: x[0].encode())
with open(out, "w") as fh:
    for path, sha in lines:
        fh.write(f"{sha}  {path}\n")
print(f"{len(lines)} files, {total} bytes -> {out}")
