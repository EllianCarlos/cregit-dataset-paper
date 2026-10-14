#!/usr/bin/env python3
"""Apply the copy rules of the user (2026-10-14 ~01:00 UTC, "Remove copies, keep upstreams") to the layer 1
candidates (candidates.tsv + the gitlab.com search rows) and write decisions.tsv: url, decision, rule, note.

Rules, in order:
  R1 copy namespace: mirrors, lorry-mirrors, backports, gfx-ci/android, CI copies (mesa_ci, gfx-ci), backup-*
     namespaces, and the Qt mirrors on invent.kde.org (qt/...) -> remove.
  R2 same project: the shared-history pool or frame row is the same project (a mirror or the same repository
     on another host) -> skip the GitLab copy.
  R3 fork: the GitLab row is a downstream copy of a project whose upstream is elsewhere (a fork, a vendor or
     research tree, a renamed copy) -> remove.
  R4 upstream: the GitLab row is the upstream; the rows that share its root are its forks or copies -> keep.
  R5 split: the project began as a split of another history (mesa/demos, pipewire/media-session); it is a
     separate project -> keep.
R2-R5 are a reading of each family (root commit, name, namespace, the project's own web home); NOTE says why.
"""
import csv, re
from pathlib import Path
H = Path(__file__).resolve().parent
COPY = re.compile(r"/(mirrors|infrastructure/mirrors|neon/backports-[^/]+|neon/forks|gfx-ci|mesa_ci|openhw-group/backup-\d+)/|invent\.kde\.org/qt/")
SAME = {  # R2: url -> the same project in the pool or frame
    "https://gitlab.freedesktop.org/gnu-grub/grub": "git.savannah.gnu.org git/grub (frame, layer 1): GNU GRUB, mirror on freedesktop",
    "https://gitlab.com/kicad/code/kicad": "kicad/kicad-source-mirror (frame, layer 1): the GitHub mirror of KiCad",
}
FORK = {  # R3: url -> upstream
    "https://gitlab.freedesktop.org/monado/electric-maple-monado": "fork of monado/monado",
    "https://gitlab.inria.fr/cedar/abstra": "fork of cedar/connectionlens (created 2026-05-18 from it)",
    "https://gitlab.inria.fr/cedar/connectionlens_archived2": "archived copy of cedar/connectionlens",
    "https://gitlab.inria.fr/poseidon/croco_poseidon": "fork of croco-ocean/croco",
    "https://gitlab.freedesktop.org/asahi/libdrm": "fork of mesa/libdrm",
    "https://gitlab.freedesktop.org/asahi/igt-gpu-tools": "fork of drm/igt-gpu-tools",
    "https://gitlab.freedesktop.org/camera/libcamera-softisp": "branch copy of camera/libcamera",
    "https://gitlab.freedesktop.org/camera/libcamera-vivid": "branch copy of camera/libcamera",
    "https://gitlab.winehq.org/wine/wine-gecko": "fork of Mozilla Firefox (gecko)",
    "https://gitlab.winehq.org/mono/corefx": "fork of dotnet/corefx",
    "https://gitlab.inria.fr/dynres/applications/charm": "research fork of Charm++ (GitHub UIUC-PPL/charm)",
    "https://git.adelielinux.org/spack/spack-packages": "copy of GitHub spack/spack-packages",
    "https://gitlab.freedesktop.org/panfrost/mesa": "fork of mesa/mesa", "https://gitlab.freedesktop.org/nouveau/mesa": "fork of mesa/mesa",
    "https://gitlab.freedesktop.org/imagination/mesa": "fork of mesa/mesa", "https://gitlab.freedesktop.org/mesa/mesa-archive": "archive copy of mesa/mesa history",
    "https://gitlab.com/recalbox/recalbox": "downstream of buildroot/buildroot (frame); OPEN: batocera.linux, also buildroot-based, is in the frame",
    "https://gitlab.freedesktop.org/gstreamer/meson-ports/libvpx": "port copy of webmproject/libvpx",
    "https://gitlab.inria.fr/benagil/volimem/cpython-pmem": "research fork of python/cpython", "https://gitlab.inria.fr/benagil/volimem/redis_pmdk": "research fork of pmem/pmdk",
    "https://git.themanaworld.org/ml/hercules": "fork of HerculesWS/Hercules (frame)", "https://gitlab.com/librehealth/toolkit/lh-toolkit": "fork of openmrs/openmrs-core (frame)",
    "https://gitlab.inria.fr/dynres/dyn-procs/prrte": "research fork of PRRTE (shares the Open MPI root)", "https://gitlab.inria.fr/dynres/applications/dynpetsc": "research fork of petsc/petsc",
    "https://gitlab.inria.fr/tansiv/ns-3-dev": "research fork of nsnam ns-3", "https://gitlab.gnome.org/world/gedit/libgedit-gtksourceview": "fork of GNOME/gtksourceview (frame)",
    "https://git.adelielinux.org/adelie/musl": "distribution fork of musl", "https://gitlab.inria.fr/arsene-pepr/llvm-fence-spec": "research fork of llvm/llvm-project",
    "https://gitlab.gnome.org/world/mobileshell/gnome-settings-daemon-mobile": "fork of GNOME/gnome-settings-daemon", "https://gitlab.gnome.org/world/mobileshell/gnome-shell-mobile": "fork of GNOME/gnome-shell",
    "https://gitlab.gnome.org/world/mobileshell/mutter-mobile": "fork of GNOME/mutter", "https://gitlab.inria.fr/sushi-public/fmh/zephyr": "research fork of zephyr",
    "https://gitlab.inria.fr/sed-rennes/overleaf/overleaf-cep": "fork of overleaf/overleaf",
    "https://gitlab.inria.fr/kdbench/multicore/px4-rt_and_px4-standard/px4-rt-xenomai": "benchmark copy of PX4/PX4-Autopilot (frame)",
    "https://gitlab.inria.fr/kdbench/multicore/px4-rt_and_px4-standard/px4-rt_linux_nprt_and_prt": "benchmark copy of PX4/PX4-Autopilot (frame)",
    "https://gitlab.inria.fr/kdbench/multicore/px4-rt_and_px4-standard/px4-standard-xenomai": "benchmark copy of PX4/PX4-Autopilot (frame)",
    "https://gitlab.inria.fr/kdbench/multicore/px4-rt_and_px4-standard/px4-standard_linux_nprt_and_prt": "benchmark copy of PX4/PX4-Autopilot (frame)",
}
KEEP_UP = {  # R4
    "https://gitlab.winehq.org/wine/vkd3d": "upstream; frame row HansKristian-Work/vkd3d-proton is its fork",
    "https://gitlab.freedesktop.org/camera/libcamera": "upstream; frame row raspberrypi/libcamera is its fork",
    "https://gitlab.freedesktop.org/dbus/dbus": "upstream; pool row ni/dbus is its fork",
    "https://gitlab.freedesktop.org/wayland/weston": "upstream; pool row microsoft/weston-mirror is Microsoft's fork (WSLg)",
    "https://gitlab.com/libeigen/eigen": "upstream; pool row nervanasystems/eigen is its fork",
    "https://gitlab.freedesktop.org/mesa/mesa": "upstream (the GitHub row mesa/mesa is another project)",
    "https://gitlab.com/muttmua/mutt": "upstream; frame row neomutt/neomutt is its fork",
}
SPLIT = {"https://gitlab.freedesktop.org/mesa/demos": "split from the Mesa history", "https://gitlab.freedesktop.org/pipewire/media-session": "split from the PipeWire history"}
LINUX = "1da177e4c3f41524e886b7f1b8a0c1fc7321cac2"
rows = list(csv.DictReader(open(H / "candidates.tsv"), delimiter="\t"))
roots = {r["url"]: r for r in csv.DictReader(open(H / "roots.tsv"), delimiter="\t")}
seen = {r["url"] for r in rows}
for f in ["screen.gitlab.com-search.tsv", "screen.gitlab.com-search-personal.tsv"]:  # personal: decision 2026-10-14 ~15:35 UTC
    for s in csv.DictReader(open(H / f), delimiter="\t"):
        if s["step_result"] == "layer 1 candidate" and s["url"] not in seen:
            rt = roots.get(s["url"], {})
            rows.append(dict(host="gitlab.com (search)", url=s["url"], commits=s["commits"], dp8l=s["dp8l"], cls="", root=rt.get("root", ""),
                             frame_hits=rt.get("frame_hits", ""), pool_hits=rt.get("pool_hits", "")))
out = open(H / "decisions.tsv", "w"); out.write("host\turl\tcommits\tdecision\trule\tnote\n"); undecided = []
for r in rows:
    u = r["url"]
    if COPY.search(u + "/"): d, rule, note = "remove", "R1 copy namespace", ""
    elif u in SAME: d, rule, note = "skip", "R2 same project", SAME[u]
    elif u in FORK: d, rule, note = "remove", "R3 fork", FORK[u]
    elif r.get("root") == LINUX: d, rule, note = "remove", "R3 fork", "a Linux tree; torvalds/linux is in the frame"
    elif u in KEEP_UP: d, rule, note = "keep", "R4 upstream", KEEP_UP[u]
    elif u in SPLIT: d, rule, note = "keep", "R5 split", SPLIT[u]
    elif r.get("frame_hits") or r.get("pool_hits"): d, rule, note = "UNDECIDED", "", f"frame {r.get('frame_hits')} pool {r.get('pool_hits')}"; undecided.append(u)
    else: d, rule, note = "keep", "new history", ""
    out.write(f"{r['host']}\t{u}\t{r['commits']}\t{d}\t{rule}\t{note}\n")
out.close()
import collections
c = collections.Counter(l.split("\t")[3] + " | " + l.split("\t")[4] for l in open(H / "decisions.tsv").read().splitlines()[1:])
for k, v in sorted(c.items()): print(v, k)
print("UNDECIDED:", undecided)
