#!/usr/bin/env bash
# S2-stage-inputs.sh (this machine, main session; no S3 access): the inputs of the path-fix rerun,
# from the scan ${RUNNER_PROJECTS_TILDE}/cregit-workspace/path-defect/affected.tsv. Writes stage/inputs/:
#   manifest.pathfix.tsv   the rerun rows (lost_bytes > 0: a file with content and no tokens);
#                          commit = the FRAME commit of the original manifest (ctp writes it as
#                          snapshot_sha), file_filter empty (the default mask, as all v1/x1k runs)
#   seeds.tsv              name, resolved_sha, snapshot_sha, branch, source: R3 writes
#                          state/<name>/latest.json from it BEFORE the start, so ctp --latest
#                          REUSES the commit of the original run (no new remote head). resolved_sha
#                          "S3" = R3 reads dataset-x1k/done-full/<name>/state/latest.json on the
#                          machine (the x1k rows; Claude's S3 reads are denied here).
#   parts.tsv              name, part, hours: part 1 = the v1 rows, part 2 = the x1k rows, part 3 =
#                          alibaba__AliSQL alone (63 h of blame at 4 blame jobs in batch 9; it gets
#                          --blame-jobs 32)
#   sidecars.tsv           part, file, sha256, path: the sidecar of each part, used AS IS (no copy is
#                          made here): part 1 and 3 = s7-run/project_meta.v1.final.json, part 2 =
#                          x1k/project_meta.x1k.json (the sidecar of the x1k B run, already in
#                          s3://B/dataset-x1k/inputs/). U1 uploads the v1 file from its own path.
#   SOURCE, SHA256SUMS
# Refuses to overwrite: move stage/inputs aside first.
set -euo pipefail
H=${H:-$HOME/s3-work/dataset-pathfix}
PD=${RUNNER_PROJECTS}/cregit-workspace/path-defect
DS=${RUNNER_PROJECTS}/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection
CC=${RUNNER_PROJECTS}/cregit-workspace/census-cloud
O=$H/stage/inputs
[ -e "$O" ] && { echo "ABORT: $O exists; move it aside first"; exit 1; }
mkdir -p "$O"
python3 -I - "$PD" "$DS" "$CC" "$O" <<'EOF'
import csv, glob, json, os, sys
pd, ds, cc, out = sys.argv[1:5]
aff = [r for r in csv.DictReader(open(f"{pd}/affected.tsv"), delimiter="\t")
       if int(r["lost_bytes"] or 0) > 0]
proj = {r["project"]: r for r in csv.DictReader(open(f"{pd}/projects.tsv"), delimiter="\t")}
# size_class and the manifest row from the original manifests (v1 batch manifests, x1k manifest)
man = {}
for f in sorted(glob.glob(f"{ds}/s7-run/manifest.batch*.tsv")) + [f"{ds}/x1k/manifest.x1k.tsv"]:
    if ".order." in f:
        continue
    for line in open(f):
        if line.startswith("#") or not line.strip():
            continue
        c = line.rstrip("\n").split("\t")
        man.setdefault(c[0], c)
side = {"v1": f"{ds}/s7-run/project_meta.v1.final.json", "x1k": f"{ds}/x1k/project_meta.x1k.json"}
meta = {layer: json.load(open(f)) for layer, f in side.items()}
# measured hours (v1 ledgers) or predicted (x1k predict.tsv, the larger of the two models, x2)
pred = {r["name"]: max(int(r["fit_s"]), int(r["mb63_s"])) * 2 / 3600
        for r in csv.DictReader(open(f"{ds}/x1k/predict.tsv"), delimiter="\t")}
ledgers = {}
for li in csv.DictReader(open(f"{pd}/ledger-index.tsv"), delimiter="\t"):
    if li["final_status"] == "done":
        ledgers.setdefault((li["project"], li["checked_out_sha"]), []).append(li["ledger"])
rows, seeds, parts, problems = [], [], [], []
for r in sorted(aff, key=lambda r: r["project"]):
    n = r["project"]
    m = man.get(n)
    p = proj.get(n, {})
    if not m:
        problems.append(f"{n}: no manifest row"); continue
    if n not in meta[r["layer"]]:
        problems.append(f"{n}: no entry in the {r['layer']} sidecar"); continue
    frame = p.get("manifest_commit") or m[5]
    if frame != m[5]:
        problems.append(f"{n}: manifest_commit {frame} != manifest {m[5]}"); continue
    rows.append("\t".join([n, m[1], m[2], "", m[4], frame]))
    hours = None
    if r["layer"] == "v1":
        lj = os.path.join(cc, r["done_prefix"], "state", "latest.json")
        if not os.path.isfile(lj):
            # a post-fixed copy (dataset-v1/inputs/fixed/...): take the original run folder
            cands = [c for c in glob.glob(f"{cc}/**/done/{n}/state/latest.json", recursive=True)
                     + glob.glob(f"{cc}/**/state/{n}/latest.json", recursive=True)
                     if json.load(open(c)).get("resolved_sha") == r["commit"]]
            if not cands:
                problems.append(f"{n}: no local latest.json with {r['commit']}"); continue
            lj = sorted(cands)[0]
        rec = json.load(open(lj))
        if rec.get("resolved_sha") != r["commit"]:
            problems.append(f"{n}: latest.json {rec.get('resolved_sha')} != scan commit {r['commit']}"); continue
        seeds.append((n, rec["resolved_sha"], rec.get("snapshot_sha", frame), rec.get("branch", ""), lj))
        for led in ledgers.get((n, r["commit"]), []):
            for line in open(led):
                try:
                    j = json.loads(line)
                except ValueError:
                    continue
                if j.get("project") == n and j.get("step") == "project" and j.get("status") == "done":
                    hours = float(j["duration_s"]) / 3600
    else:
        if r["done_prefix"]:
            seeds.append((n, "S3", frame, "", f"{r['done_prefix']}state/latest.json"))
        else:
            # no done-full: the B run failed (the two defect rows). Their head did not move:
            # a --latest run on 2026-10-20 19:07 UTC resolved the manifest commit for both.
            seeds.append((n, frame, frame, "", "manifest commit (B run failed; head unchanged)"))
        hours = pred.get(n)
    part = "3" if n == "alibaba__AliSQL" else ("1" if r["layer"] == "v1" else "2")
    parts.append((n, part, f"{hours:.2f}" if hours is not None else ""))
if problems:
    print("ABORT:\n  " + "\n  ".join(problems)); sys.exit(1)
hdr = "# path-fix rerun: rows of path-defect/affected.tsv with lost_bytes > 0\n# Columns: name\turl\tcategory\tfile_filter\tsize_class\tcommit\n"
open(f"{out}/manifest.pathfix.tsv", "w").write(hdr + "\n".join(rows) + "\n")
with open(f"{out}/seeds.tsv", "w") as f:
    f.write("name\tresolved_sha\tsnapshot_sha\tbranch\tsource\n")
    for s in seeds:
        f.write("\t".join(s) + "\n")
with open(f"{out}/parts.tsv", "w") as f:
    f.write("name\tpart\thours\n")
    for s in parts:
        f.write("\t".join(s) + "\n")
import hashlib
with open(f"{out}/sidecars.tsv", "w") as f:
    f.write("part\tfile\tsha256\tpath\n")
    for part, layer in (("1", "v1"), ("2", "x1k"), ("3", "v1")):
        path = side[layer]
        f.write(f"{part}\t{os.path.basename(path)}\t{hashlib.sha256(open(path, 'rb').read()).hexdigest()}\t{path}\n")
for k in ("1", "2", "3"):
    hs = [float(h or 0) for _, p, h in parts if p == k]
    print(f"part {k}: {len(hs)} rows, {sum(hs):.1f} serial h (v1: measured; x1k: predicted x2), longest {max(hs or [0]):.1f} h")
EOF
for f in "$O"/*; do grep -l $'\x40' "$f" && { echo "ABORT: an at sign in $f"; exit 1; }; done
{ echo "path-fix rerun inputs, $(date -u +%FT%TZ)"; echo "affected.tsv sha256 $(sha256sum "$PD/affected.tsv" | cut -d' ' -f1)"; } > "$O/SOURCE"
(cd "$O" && sha256sum manifest.pathfix.tsv seeds.tsv parts.tsv sidecars.tsv SOURCE > SHA256SUMS)
echo "staged: $O"; cat "$O/SHA256SUMS"
