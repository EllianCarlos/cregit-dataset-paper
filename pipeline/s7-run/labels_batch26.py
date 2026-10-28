#!/usr/bin/env python3
"""S5/S6 labels of batch 26 (gitlab.com/muttmua/mutt; 2026-10-14) by the rules of labels_batch25.py, and the fill
of project_meta.batch26.json (stratum, fact, label_date). The row is a gitlab.com search row, so no S5 fact was
collected for it: label unknown, with the OPEN note of labels_batch25.py. Its namespace is personal (ns_kind user,
the round of personal_rows.py), so other_facts is owner_kind:user. Writes labels.batch26.csv (the labels.csv columns
plus basis_note) and fills the sidecar in place (refuses if a stratum is already set). label_date 2026-10-14.
"""
import csv, json
from pathlib import Path
H = Path(__file__).resolve().parent
OPEN = {"gitlab.com": "OPEN: gitlab.com search row; no S5 fact was collected"}
meta_p = H / "project_meta.batch26.json"; meta = json.loads(meta_p.read_text())
frame = {f"{r['host']}__" + "__".join(r["slug"].split("/")): r for r in csv.DictReader(open(H / "frame.batch26.csv"))}
assert all(not v["stratum"] for v in meta.values()), "a stratum is set already"
out = []
for name, v in meta.items():
    f = frame[name]
    v["stratum"], v["fact"], v["label_date"] = "unknown", "", "2026-10-14"
    out.append(dict(project=name, pool_key=f["pool_key"], label="unknown", label_basis="", contested="",
                    other_facts="owner_kind:user", size_class=f["size_class"], language=f["language"],
                    basis_note=OPEN[f["host"]] + "; personal namespace (personal_rows.py)"))
meta_p.write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
with open(H / "labels.batch26.csv", "w", newline="", encoding="utf-8") as fo:
    w = csv.DictWriter(fo, list(out[0]), lineterminator="\n"); w.writeheader(); w.writerows(out)
print(len(out), "rows labeled unknown")
