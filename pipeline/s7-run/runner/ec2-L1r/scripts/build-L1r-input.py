"""build-L1r-input.py SRC DST: build DST/manifest.L1r.tsv, DST/project_meta.L1r.json and DST/SHA256SUMS for
census L1r (batch 1 rerun, L; 2026-10-12) from the batch 1 inputs in SRC (${RUNNER_STUDY_REPO} s7-run).

The manifest holds the 2 rows of manifest.batch1.tsv for torvalds__linux and SAP__project-foxhound,
unchanged, longest first (LPT; ctp census starts the rows in manifest order). The sidecar holds the 2
entries of project_meta.batch1.json, unchanged, in the format of that file (json indent 1). The script
refuses if an input differs from the expected sha256, or if a row or entry is missing. Hours are the
batch 1 durations on the old code (cregit 157cf8b, measured on this machine 2026-10-07..09)."""
import hashlib
import json
import os
import sys

WANT_M = "53e3090b8ec1a8e4a4b7a38a0eb691a0aba633d4841c7d652a479db0bd569765"  # manifest.batch1.tsv
WANT_J = "fa6a956d3cdcfa486489c02b5c1400a1b28506b66b449605db763d211cbfaf91"  # project_meta.batch1.json
LPT = [("SAP__project-foxhound", 36.4), ("torvalds__linux", 25.9)]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main(src, dst):
    m = open(os.path.join(src, "manifest.batch1.tsv"), "rb").read()
    j = open(os.path.join(src, "project_meta.batch1.json"), "rb").read()
    assert sha(m) == WANT_M, "manifest.batch1.tsv sha256 differs"
    assert sha(j) == WANT_J, "project_meta.batch1.json sha256 differs"
    rows = {l.split("\t")[0]: l for l in m.decode("utf-8").splitlines(keepends=True)
            if l.strip() and not l.startswith("#")}
    names = [n for n, _ in LPT]
    assert all(n in rows for n in names), "a row is missing in manifest.batch1.tsv"
    meta = json.loads(j)
    assert all(n in meta for n in names), "an entry is missing in project_meta.batch1.json"
    # the sidecar format: json.dumps(indent=1) + newline reproduces project_meta.batch1.json byte for byte
    assert (json.dumps(meta, indent=1) + "\n").encode("utf-8") == j, "project_meta.batch1.json format differs"
    head = [f"# Census L1r (2026-10-12): batch 1 rerun, L. The {len(LPT)} rows of manifest.batch1.tsv\n",
            f"# (sha256 {WANT_M}), unchanged, longest first (LPT).\n",
            "# Batch 1 hours on the old code (cregit 157cf8b):" + "".join(f" {n} {h}" for n, h in LPT) + "\n",
            "# Columns: name  url  category  file_filter  size_class  commit\n"]
    out_m = ("".join(head) + "".join(rows[n] for n in names)).encode("utf-8")
    out_j = (json.dumps({n: meta[n] for n in names}, indent=1) + "\n").encode("utf-8")
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, "manifest.L1r.tsv"), "wb").write(out_m)
    open(os.path.join(dst, "project_meta.L1r.json"), "wb").write(out_j)
    sums = "".join(f"{sha(b)}  {n}\n" for n, b in (("manifest.L1r.tsv", out_m), ("project_meta.L1r.json", out_j)))
    open(os.path.join(dst, "SHA256SUMS"), "w").write(sums)
    print(f"L1r: {len(LPT)} rows; manifest.L1r.tsv sha256 {sha(out_m)}; project_meta.L1r.json sha256 {sha(out_j)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
