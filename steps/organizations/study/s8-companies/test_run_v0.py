"""Tests for run_v0.py on two small v1-raw files and a local DEST directory."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

duckdb = pytest.importorskip("duckdb")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_v0  # noqa: E402
from final_merge import sha256  # noqa: E402
from build_v0 import mapping_sha256  # noqa: E402
from test_build_v0 import DOMAINS, PROJECT, make_links, make_src  # noqa: E402


@pytest.fixture
def setup(tmp_path):
    v1 = tmp_path / "v1raw"
    (v1 / "parquet").mkdir(parents=True)
    res = []
    for p, doms in (("o__r", ["acme.example.org", "x.example.org", "acme.example.org"]),
                    ("q__s", ["apache.example.org"])):
        f = make_src(v1 / "parquet" / f"{p}-dataset.parquet", doms)
        res.append({"project": p, "output": f"parquet/{f.name}", "output_sha256": sha256(f),
                    "rows": len(doms), "output_bytes": f.stat().st_size})
    with open(v1 / "results.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(res[0]), delimiter="\t")
        w.writeheader()
        w.writerows(res)
    links = tmp_path / "links"
    links.mkdir()
    pl, dl = make_links(links, [PROJECT, {"project": "q__s"}], DOMAINS)
    m = mapping_sha256([(d["domain"], d["firm_based_on_domain"]) for d in DOMAINS], [("o__r", "acme"), ("q__s", None)])
    (links / "links.json").write_text(json.dumps({"outputs": {pl.name: sha256(pl), dl.name: sha256(dl)},
                                                  "organisations_version": "v-test", "mapping_sha256": m}))
    out, dest = tmp_path / "out", tmp_path / "dest"
    args = ["--v1raw", str(v1), "--links", str(links), "--out", str(out), "--dest", str(dest),
            "--jobs", "2", "--memory-limit", "1GB"]
    return args, v1, links, out, dest


def test_all_projects_and_finish(setup):
    args, v1, links, out, dest = setup
    assert run_v0.main(args) == 0
    with open(out / "results.tsv", newline="") as fh:
        got = {r["project"]: r for r in csv.DictReader(fh, delimiter="\t")}
    assert set(got) == {"o__r", "q__s"}
    sums = (dest / "SHA256SUMS").read_text().split("\n")
    assert len([s for s in sums if s]) == 2
    for name in ("results.tsv", "domain_links.parquet", "project_links.parquet", "links.json"):
        assert (dest / name).is_file()
    con = duckdb.connect()
    r = con.execute("SELECT firm_based_on_namespace, firm_based_on_domain FROM read_parquet(?)",
                    [str(dest / "parquet/o__r-dataset.parquet")]).fetchall()
    assert r == [("acme", "acme"), ("acme", "independent"), ("acme", "acme")]
    # A second start does nothing new.
    assert run_v0.main(args) == 0
    with open(out / "results.tsv") as fh:
        assert len(fh.read().strip().split("\n")) == 3


def test_bad_v1raw_sha_fails_one_project(setup):
    args, v1, links, out, dest = setup
    with open(v1 / "results.tsv") as fh:
        text = fh.read()
    lines = text.strip().split("\n")
    cols = lines[1].split("\t")
    cols[2] = "0" * 64
    lines[1] = "\t".join(cols)
    (v1 / "results.tsv").write_text("\n".join(lines) + "\n")
    assert run_v0.main(args) == 1
    assert "sha256" in (out / "failed.tsv").read_text()
    assert not (dest / "SHA256SUMS").exists()


def test_link_sha_mismatch_is_a_bad_input(setup):
    args, v1, links, out, dest = setup
    good = json.loads((links / "links.json").read_text())
    (links / "links.json").write_text(json.dumps(dict(good, outputs={"domain_links.parquet": "0",
                                                                     "project_links.parquet": "0"})))
    assert run_v0.main(args) == 2


def test_links_without_the_mapping_hash_are_a_bad_input(setup):
    args, v1, links, out, dest = setup
    good = json.loads((links / "links.json").read_text())
    (links / "links.json").write_text(json.dumps({"outputs": good["outputs"]}))
    assert run_v0.main(args) == 2


def test_a_wrong_mapping_hash_fails_each_project(setup):
    args, v1, links, out, dest = setup
    good = json.loads((links / "links.json").read_text())
    (links / "links.json").write_text(json.dumps(dict(good, mapping_sha256="f" * 64)))
    assert run_v0.main(args) == 1
    assert "mapping hash" in (out / "failed.tsv").read_text()
    assert not (dest / "SHA256SUMS").exists()


def test_two_passes_by_rows_finish_once(setup):
    """The large files run in their own pass (--min-rows); the pass that ends last writes SHA256SUMS."""
    args, v1, links, out, dest = setup
    assert run_v0.main(args + ["--min-rows", "2"]) == 0          # o__r has 3 rows, q__s has 1
    assert not (dest / "SHA256SUMS").exists()
    with open(out / "results.tsv", newline="") as fh:
        assert [r["project"] for r in csv.DictReader(fh, delimiter="\t")] == ["o__r"]
    assert run_v0.main(args + ["--max-rows", "1"]) == 0
    assert len([s for s in (dest / "SHA256SUMS").read_text().split("\n") if s]) == 2


# --- --pseudonymize (synthetic v1-raw files of pseudonymize.make_synthetic; a throw-away salt)

from test_build_v0 import ANON_DIR, anon_module, make_registry, make_salt, make_v1raw  # noqa: E402


@pytest.fixture
def fused_setup(tmp_path):
    P = anon_module()
    v1 = tmp_path / "v1raw"
    (v1 / "parquet").mkdir(parents=True)
    res, srcs = [], []
    for i, n in enumerate((1500, 900)):
        f, project = make_v1raw(P, v1 / "parquet" / f"p{i}.parquet", rows=n, at_every=5 + i)
        f = f.rename(v1 / "parquet" / f"{project}-{i}-dataset.parquet")
        srcs.append(f)
        res.append({"project": f"{project}-{i}", "output": f"parquet/{f.name}", "output_sha256": sha256(f),
                    "rows": n, "output_bytes": f.stat().st_size})
    with open(v1 / "results.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(res[0]), delimiter="\t")
        w.writeheader()
        w.writerows(res)
    links = tmp_path / "links"
    links.mkdir()
    pl, dl = make_links(links, [dict(PROJECT, project=res[0]["project"])], DOMAINS)
    m = mapping_sha256([(d["domain"], d["firm_based_on_domain"]) for d in DOMAINS], [(res[0]["project"], "acme")])
    (links / "links.json").write_text(json.dumps({"outputs": {pl.name: sha256(pl), dl.name: sha256(dl)},
                                                  "organisations_version": "v-test", "mapping_sha256": m}))
    salt = make_salt(tmp_path / "salt")
    reg, rsha = make_registry(P, tmp_path, srcs, salt)
    out, dest = tmp_path / "out", tmp_path / "dest"
    args = ["--v1raw", str(v1), "--links", str(links), "--out", str(out), "--dest", str(dest), "--jobs", "2",
            "--memory-limit", "1GB", "--pseudonymize", "--salt-file", str(salt), "--registry", str(reg),
            "--psl", P.find_psl(), "--anon-dir", str(ANON_DIR)]
    return dict(P=P, args=args, out=out, dest=dest, reg=reg, rsha=rsha, res=res, tmp=tmp_path)


def test_fused_run_writes_all_projects_and_no_registry(fused_setup):
    f = fused_setup
    assert run_v0.main(f["args"]) == 0
    with open(f["out"] / "results.tsv", newline="") as fh:
        done = list(csv.DictReader(fh, delimiter="\t"))
    assert sorted(r["project"] for r in done) == sorted(r["project"] for r in f["res"])
    assert all(f"registry {f['rsha'][:12]}" in r["detail"] and "scan ok" in r["detail"] for r in done)
    info = json.loads((f["dest"] / "pseudonymization.json").read_text())
    assert info["registry_sha256"] == f["rsha"] and info["pseudonymization_version"] == f["P"].SCHEME_VERSION
    names = {p.name for p in f["dest"].rglob("*") if p.is_file()}
    assert "registry.parquet" not in names and len(list((f["dest"] / "parquet").glob("*.parquet"))) == 2
    assert chr(64) not in (f["dest"] / "pseudonymization.json").read_text()
    con = duckdb.connect()
    for p in (f["dest"] / "parquet").glob("*.parquet"):
        kv = dict(con.execute("SELECT decode(key), decode(value) FROM parquet_kv_metadata(?)", [str(p)]).fetchall())
        assert kv[f["P"].FOOTER_REGISTRY_KEY] == f["rsha"]
    con.close()


def test_fused_run_passes_no_content_scan(fused_setup):
    f = fused_setup
    assert run_v0.main(f["args"] + ["--no-content-scan"]) == 0
    with open(f["out"] / "results.tsv", newline="") as fh:
        assert all("information columns skipped" in r["detail"] for r in csv.DictReader(fh, delimiter="\t"))
    info = json.loads((f["dest"] / "pseudonymization.json").read_text())
    assert info["leak_scan"] is True and info["leak_scan_content_columns"] is False


def test_fused_run_refuses_a_registry_under_out(fused_setup):
    f = fused_setup
    inside = f["out"] / "private" / "registry.parquet"
    inside.parent.mkdir(parents=True)
    inside.write_bytes(f["reg"].read_bytes())
    args = list(f["args"])
    args[args.index("--registry") + 1] = str(inside)
    assert run_v0.main(args) == 2


def test_fused_run_needs_the_fused_options(fused_setup):
    f = fused_setup
    args = [a for a in f["args"] if a != "--pseudonymize"]
    assert run_v0.main(args) == 2
    args = list(f["args"])
    del args[args.index("--salt-file"):args.index("--salt-file") + 2]
    assert run_v0.main(args) == 2


def test_max_failures_writes_stop(setup):
    args, v1, links, out, dest = setup
    with open(v1 / "results.tsv", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    for r in rows:
        r["output_sha256"] = "0" * 64
    with open(v1 / "results.tsv", "w", newline="") as fh:
        w = csv.DictWriter(fh, list(rows[0]), delimiter="\t")
        w.writeheader()
        w.writerows(rows)
    assert run_v0.main(args + ["--max-failures", "1", "--jobs", "1"]) == 1
    assert (out / "STOP").is_file()
    assert len((out / "failed.tsv").read_text().splitlines()) == 1     # the second project did not start
