#!/usr/bin/env python3
"""The fed spot part of batch 26 (2026-10-14): its one S row (gitlab.com/muttmua/mutt) as part a1 of 1 worker
on spot half a. split_batchN.py makes 2K bins of 4 workers on both halves, so it would give an empty part for
one row; this script writes the same files with split_batchN.part_text (so census-fed-derive rebuilds the part
manifest byte for byte) and the same predicted-time fit. Writes parts.batch26.tsv, parts.batch26.assign.tsv and
manifest.batch26a1.tsv, and appends their sha256 to SHA256SUMS. Refuses to overwrite.
"""
import hashlib, math, sys
from pathlib import Path
H = Path(__file__).resolve().parent
sys.path.insert(0, str(H))
from split_batchN import FIT, CLASS_COL, frame_index, name, part_text, read_manifest  # noqa: E402
wl, part, workers = "batch26", "a1", 1
outs = [f"parts.{wl}.tsv", f"parts.{wl}.assign.tsv", f"manifest.{wl}{part}.tsv"]
for f in outs: assert not (H / f).exists(), f"{f} exists"
src = H / f"manifest.{wl}.tsv"; _, rows = read_manifest(src)
assert rows and all(r.split("\t")[CLASS_COL] != "L" for r in rows)
frame = frame_index(H, wl)
pred = sum(math.exp(FIT[0] + FIT[1] * math.log(int(f["commits"])) + FIT[2] * math.log(max(int(f["tok_bytes"] or 1), 1)))
           for f in (frame[r.split("\t")[1].rstrip("/").removesuffix(".git")] for r in rows))
ph = f"{pred / 3600:.1f}"
text = part_text(src, part, workers, ph, {name(r) for r in rows})
(H / outs[2]).write_text(text, encoding="utf-8")
sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
(H / outs[0]).write_text(
    f"# Fed spot parts of {wl} (parts_batch26.py): the S and M projects of manifest.{wl}.tsv. sha256 is\n"
    f"# that of the part manifest manifest.<workload><part>.tsv, which split_batchN.py --derive rebuilds.\n"
    f"# {wl} (2026-10-14): one part, a1, 1 worker, on spot half a (gitlab.com/muttmua/mutt, DP8L v4 near miss C).\n"
    "half\tworkload\tpart\tworkers\tprojects\tpredicted_h\tsha256\n"
    f"a\t{wl}\t{part}\t{workers}\t{len(rows)}\t{ph}\t{sha}\n", encoding="utf-8")
(H / outs[1]).write_text("workload\tpart\tproject\n" + "".join(f"{wl}\t{part}\t{name(r)}\n" for r in rows), encoding="utf-8")
with open(H / "SHA256SUMS", "a") as f:
    for o in outs + ["labels.batch26.csv"]: f.write(f"{hashlib.sha256((H / o).read_bytes()).hexdigest()}  {o}\n")
print(f"{wl}{part}: {len(rows)} projects, {workers} worker, predicted {ph} h (inferred)")
