"""build-L23-input.py SRC DST: build DST/manifest.L23.tsv and DST/project_meta.L23.json from the batch 23
inputs in SRC (s3://BUCKET/batch23/input/, ${RUNNER_STUDY_REPO} s7-run). The manifest holds the 8 rows of
manifest.batch23L.tsv, unchanged, longest predicted first (LPT, the rule of census L7-20; ctp census starts
the rows in manifest order). The sidecar is a byte copy of project_meta.batch23L.json. Refuses if an input
or the output differs from the expected sha256. Predicted hours: split_batchN.py 23 (the fit of
split_batch5.py; inferred, weak for L projects)."""
import hashlib
import os
import sys

WANT_M = "c8c986af2a7667bb22010c2f71f90df1321e16795eb4ec5b52893eada7553ade"  # manifest.batch23L.tsv
WANT_J = "e823a93bc254428b945fa5b004bda4f341a78992107f7187fd1776b47ca1cb97"  # project_meta.batch23L.json
LPT = [("NetBSD__src", 17.5), ("openbsd__src", 12.3), ("checkedc__checkedc-clang", 10.6), ("WebKit__WebKit", 10.4),
       ("Xilinx__hls-llvm-project", 6.5), ("openbsd__ports", 0.5), ("alpinelinux__aports", 0.3),
       ("archlinuxcn__repo", 0.2)]
WANT_OUT = sys.argv[3] if len(sys.argv) > 3 else None


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main(src, dst):
    m = open(os.path.join(src, "manifest.batch23L.tsv"), "rb").read()
    j = open(os.path.join(src, "project_meta.batch23L.json"), "rb").read()
    assert sha(m) == WANT_M, "manifest.batch23L.tsv sha256 differs"
    assert sha(j) == WANT_J, "project_meta.batch23L.json sha256 differs"
    rows = {l.split("\t")[0]: l for l in m.decode("utf-8").splitlines(keepends=True)
            if l.strip() and not l.startswith("#")}
    assert sorted(rows) == sorted(n for n, _ in LPT), "the L rows differ from the LPT list"
    head = [f"# Census L23 (2026-10-11): the {len(LPT)} rows of manifest.batch23L.tsv (sha256 {WANT_M}),\n",
            "# unchanged, longest predicted first (LPT). Predicted hours (inferred):"
            + "".join(f" {n} {h}" for n, h in LPT) + "\n",
            "# Columns: name  url  category  file_filter  size_class  commit\n"]
    out = ("".join(head) + "".join(rows[n] for n, _ in LPT)).encode("utf-8")
    if WANT_OUT:
        assert sha(out) == WANT_OUT, f"manifest.L23.tsv sha256 {sha(out)} differs from {WANT_OUT}"
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, "manifest.L23.tsv"), "wb").write(out)
    open(os.path.join(dst, "project_meta.L23.json"), "wb").write(j)
    print(f"L23: {len(LPT)} rows, {sum(h for _, h in LPT):.1f} h predicted; manifest.L23.tsv sha256 {sha(out)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
