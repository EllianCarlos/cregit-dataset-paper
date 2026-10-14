#!/usr/bin/env python3
"""Move every fed part of a workload to one spot half (batch 23, user decision 2026-10-11 ~21:05 UTC:
all 10 batch 23 parts on spot b, none on spot a).

  one_half.py WL TO      for example: one_half.py batch23 b

census-fed-enqueue and restart_spot.sh pick the parts of a half by the first column ("half") of
parts.<WL>.tsv; they do not read the part name. The parts of TO keep their names and their manifests
(byte-identical). The parts of the other half get the next numbers of TO, in their order (batch 23:
a1..a5 become b6..b10). Their rows do not change; only the "# Part <name>" header line of the part
manifest changes, so their sha256 changes. Rewrites parts.<WL>.tsv and parts.<WL>.assign.tsv, writes
the new part manifests manifest.<WL><part>.tsv, and prints the part manifests that no longer belong
to the workload (remove them from the record). The queue order is the file order: TO first, then the
moved parts.
"""
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from split_batchN import part_text, read_parts  # noqa: E402


def main(wl: str, to: str) -> None:
    assert to in ("a", "b"), to
    parts, assign = read_parts(HERE, wl)
    head = [l for l in (HERE / f"parts.{wl}.tsv").read_text(encoding="utf-8").splitlines() if l.startswith("#")]
    keep = [p for p in parts if p[0] == to]
    move = [p for p in parts if p[0] != to]
    n = max(int(p[2][1:]) for p in keep) if keep else 0
    rows, rename, stale = [], {}, []
    for half, w, p, k, cnt, h, sha in keep:
        rows.append([half, w, p, k, cnt, h, sha])
        rename[p] = p
    for half, w, p, k, cnt, h, sha in move:
        n += 1
        q = f"{to}{n}"
        text = part_text(HERE / f"manifest.{w}.tsv", q, int(k), h, assign[(w, p)])
        (HERE / f"manifest.{w}{q}.tsv").write_text(text, encoding="utf-8")
        rows.append([to, w, q, k, cnt, h, hashlib.sha256(text.encode("utf-8")).hexdigest()])
        rename[p] = q
        stale.append(f"manifest.{w}{p}.tsv")
    head.append(f"# {wl} (2026-10-11): every part on spot half {to} (one_half.py); the former parts "
                + ", ".join(f"{p} -> {q}" for p, q in rename.items() if p != q) + ".")
    out = "\n".join(head) + "\nhalf\tworkload\tpart\tworkers\tprojects\tpredicted_h\tsha256\n"
    out += "".join("\t".join(r) + "\n" for r in rows)
    (HERE / f"parts.{wl}.tsv").write_text(out, encoding="utf-8")
    lines = (HERE / f"parts.{wl}.assign.tsv").read_text(encoding="utf-8").splitlines()
    new = [lines[0]] + ["\t".join([w, rename[p], x]) for w, p, x in (l.split("\t") for l in lines[1:])]
    (HERE / f"parts.{wl}.assign.tsv").write_text("\n".join(new) + "\n", encoding="utf-8")
    for r in rows:
        print("\t".join(r[:6]))
    print("stale:", " ".join(stale))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
