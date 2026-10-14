#!/usr/bin/env python3
"""S5/S6 labels of batch 25 (the GitLab rows; 2026-10-14) by the instance-owner rule, and the fill of
project_meta.batch25.json (stratum, fact, label_date).

User decision 2026-10-14 ~01:00 UTC (relayed): the instance owner is foundation evidence by the roster
rule (the 2026-10-10 rule "do not expand GitLab roster groups" is replaced for GitLab). So a roster that
names the instance, or a group or repository on it as the project's home, gives the same fact to every
kept row of that instance:
  invent.kde.org         roster_org:kde        (rosters/kde.csv: KDE's own list; the KDE rows have roster:kde)
  gitlab.gnome.org       roster_org:gnome      (rosters/gnome.csv)
  gitlab.winehq.org      fiscal_sponsor:sfc    (rosters/sfc.repos.csv: Wine, https://gitlab.winehq.org/wine/wine)
  gitlab.archlinux.org   fiscal_sponsor:spi    (rosters/spi.repos.csv: Arch Linux, group gitlab.archlinux.org/archlinux)
  git.adelielinux.org    fiscal_sponsor:spi    (rosters/spi.repos.csv: Adelie Linux, the instance root)
  git.themanaworld.org   fiscal_sponsor:spi    (rosters/spi.repos.csv: Manasource, git.themanaworld.org/mana/mana)
The S6 rules (s6-labels/method.md section 1) then give: roster_org -> foundation, fiscal_sponsor ->
fiscal-sponsor. No rule gives a label to (label unknown, the open question in the note column):
  gitlab.freedesktop.org (no roster names freedesktop.org itself; rosters/xorg.csv and the SFC entry
  "Xorg" name only the group xorg), gitlab.inria.fr (a public research institute; no government or
  academic fact type was collected), gitlab.com search rows (no S5 fact was collected for them).
Writes labels.batch25.csv (the labels.csv columns plus basis_note) and fills the sidecar in place
(refuses if a stratum is already set). label_date 2026-10-14.
"""
import csv, json
from pathlib import Path
H = Path(__file__).resolve().parent
OWNER = {"invent.kde.org": ("roster_org:kde", "foundation", "rosters/kde.csv: the instance of KDE"),
         "gitlab.gnome.org": ("roster_org:gnome", "foundation", "rosters/gnome.csv: the instance of GNOME"),
         "gitlab.winehq.org": ("fiscal_sponsor:sfc", "fiscal-sponsor", "rosters/sfc.repos.csv Wine: gitlab.winehq.org/wine/wine"),
         "gitlab.archlinux.org": ("fiscal_sponsor:spi", "fiscal-sponsor", "rosters/spi.repos.csv Arch Linux: gitlab.archlinux.org/archlinux"),
         "git.adelielinux.org": ("fiscal_sponsor:spi", "fiscal-sponsor", "rosters/spi.repos.csv Adelie Linux: the instance root"),
         "git.themanaworld.org": ("fiscal_sponsor:spi", "fiscal-sponsor", "rosters/spi.repos.csv Manasource: git.themanaworld.org/mana/mana")}
OPEN = {"gitlab.freedesktop.org": "OPEN: no roster names freedesktop.org (xorg.csv and SFC 'Xorg' name only the group xorg)",
        "gitlab.inria.fr": "OPEN: Inria is a public research institute; no government or academic fact was collected",
        "gitlab.com": "OPEN: gitlab.com search row; no S5 fact was collected"}
FLAG = {"World/": "NOTE: GNOME 'World' group = projects hosted by GNOME, not GNOME core projects",
        "ml/": "NOTE: Moubootaur Legends, hosted on The Mana World's instance"}
meta_p = H / "project_meta.batch25.json"; meta = json.loads(meta_p.read_text())
frame = {f"{r['host']}__" + "__".join(r["slug"].split("/")): r for r in csv.DictReader(open(H / "frame.batch25.csv"))}
assert all(not v["stratum"] for v in meta.values()), "a stratum is set already"
out = []
for name, v in meta.items():
    f = frame[name]; host = f["host"]
    fact, label, note = OWNER.get(host, ("", "unknown", OPEN.get(host, "")))
    if host in OWNER: note = "instance owner: " + note
    for pre, n in FLAG.items():
        if f["slug"].startswith(pre): note += "; " + n
    v["stratum"], v["fact"], v["label_date"] = label, fact, "2026-10-14"
    out.append(dict(project=name, pool_key=f["pool_key"], label=label, label_basis=fact, contested="",
                    other_facts="owner_kind:org", size_class=f["size_class"], language=f["language"], basis_note=note))
meta_p.write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
with open(H / "labels.batch25.csv", "w", newline="", encoding="utf-8") as fo:
    w = csv.DictWriter(fo, list(out[0]), lineterminator="\n"); w.writeheader(); w.writerows(out)
import collections; print(collections.Counter(r["label"] for r in out))
