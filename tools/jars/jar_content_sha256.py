#!/usr/bin/env python3
"""Print a content sha256 for each jar file: the sha256 of its sorted entry list.

Usage: python3 -I tools/jars/jar_content_sha256.py JAR [JAR ...]

Each line of the entry list is "name CRC-32 size". A nested jar counts by its own entry
list, not by its CRC, because the zip time stamps of a nested jar change with each build.
Two jars with the same value have the same entries. Only zip time stamps can differ.

The values for the cregit jars of the dataset build (the same on the local machine and on
the three EC2 machines that were checked on 2026-10-14):
  a80c9c01a8cc1acd0576e267a3dfabc5855ab14bc4f855e5405627aa91a0d896  blobExec-0.1.0-assembly.jar
  9f088b84a5849c1247997e07125b7579ee9eb56faef796b01be61eb87e5d6204  slickgitlog_2.10-0.1-SNAPSHOT-one-jar.jar
  6d7e92f8615873628b5acf9490d184cc3ac4e87d8386562414845e4040bdac3d  persons_2.10-0.1-SNAPSHOT-one-jar.jar
  cff2537eeb6c17404d19d2a705a80f1ca40b11a334b2451f5357d7e6bc0be381  remapcommits_2.10-0.1-SNAPSHOT-one-jar.jar
"""
import hashlib
import os
import sys
import zipfile


def entry_lines(z, prefix=""):
    for info in sorted(z.infolist(), key=lambda i: i.filename):
        if info.filename.endswith(".jar"):
            with z.open(info) as f, zipfile.ZipFile(f) as inner:
                yield from entry_lines(inner, prefix + info.filename + "!")
        else:
            yield f"{prefix}{info.filename} {info.CRC:08x} {info.file_size}\n"


def content_sha256(path):
    h = hashlib.sha256()
    with zipfile.ZipFile(path) as z:
        for line in entry_lines(z):
            h.update(line.encode())
    return h.hexdigest()


def main(argv):
    if not argv:
        sys.exit(__doc__)
    for path in argv:
        print(f"{content_sha256(path)}  {os.path.basename(path)}")


if __name__ == "__main__":
    main(sys.argv[1:])
