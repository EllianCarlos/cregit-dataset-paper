"""Tests for final_meta.py (2026-10-09; batches 21-22 added 2026-10-11; batches 23, 25 and 26 added
2026-10-16). Run: python3 -m pytest -q test_final_meta.py"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import final_meta  # noqa: E402

FRAME = {"o__r": {"pool_key": "gh:1"}}


def lab(**kw):
    r = {"project": "o__r", "pool_key": "gh:1", "label": "foundation", "label_basis": "roster:asf",
         "contested": "", "label_date": "2026-10-09"}
    r.update(kw)
    return r


def rec(**kw):
    r = {f: "" for f in ("clone_url", "source", "stratum", "fact", "contested", "label_date",
                         "owner", "roster_name", "roster_lang", "license")}
    r.update(kw)
    return r


def test_finalize_fills_the_label_and_roster_columns():
    out, problems = final_meta.finalize({"o__r": rec(license="MIT")}, {"o__r": lab()},
                                        {"o__r": {"roster_name": "asf:X", "roster_lang": "asf:C"}},
                                        FRAME)
    assert problems == []
    assert out["o__r"] == rec(license="MIT", stratum="foundation", fact="roster:asf",
                              label_date="2026-10-09", roster_name="asf:X", roster_lang="asf:C")


@pytest.mark.parametrize("labels, meta, needle", [
    ({}, {"o__r": rec()}, "no label"),
    ({"o__r": lab(), "x__y": lab(project="x__y")}, {"o__r": rec()}, "keys that the sidecar has not"),
    ({"o__r": lab(pool_key="gh:2")}, {"o__r": rec()}, "pool_key"),
    ({"o__r": lab()}, {"o__r": rec(stratum="company")}, "already 'company'"),
])
def test_finalize_problems(labels, meta, needle):
    _, problems = final_meta.finalize(meta, labels, {}, FRAME)
    assert any(needle in p for p in problems)


def test_a_label_row_with_no_label_date_keeps_the_sidecar_date():
    row = {k: v for k, v in lab().items() if k != "label_date"}
    out, problems = final_meta.finalize({"o__r": rec(label_date="2026-10-14")}, {"o__r": row}, {},
                                        FRAME)
    assert problems == [] and out["o__r"]["label_date"] == "2026-10-14"
    _, problems = final_meta.finalize({"o__r": rec()}, {"o__r": row}, {}, FRAME)
    assert any("no label_date" in p for p in problems)


def test_roster_columns(tmp_path):
    ev = tmp_path / "e.csv"
    cols = ["project", "fact_type", "subject", "name", "language"]
    with ev.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerow(["p", "roster", "asf", "Apache Kafka", "Scala"])
        w.writerow(["p", "roster", "asf-incubator", "Kafka", ""])
        w.writerow(["p", "roster_org", "lf", "LF Org", ""])         # an org fact: no roster_name
        w.writerow(["p", "owner_kind", "apache", "", ""])
        w.writerow(["q", "fiscal_sponsor", "sfc", "Git", ""])
    assert final_meta.roster_columns(ev) == {
        "p": {"roster_name": "asf-incubator:Kafka; asf:Apache Kafka", "roster_lang": "asf:Scala"},
        "q": {"roster_name": "sfc:Git", "roster_lang": ""}}


def test_the_committed_final_sidecar_is_what_the_script_writes(tmp_path):
    pin = HERE / "project_meta.v1.final.json.sha256"
    if not (HERE.parent / "s2-pool" / "pool.csv").exists():
        pytest.skip("no s2-pool/pool.csv")
    out = tmp_path / "final.json"
    assert final_meta.main(["--out", str(out)]) == 0
    assert hashlib.sha256(out.read_bytes()).hexdigest() == pin.read_text().split()[0]
    m = json.loads(out.read_text())
    labels = {r["project"]: r for p in final_meta.LABELS for r in csv.DictReader(p.open())}
    assert set(m) == set(labels)
    for k, r in m.items():
        assert r["stratum"] == labels[k]["label"] and r["fact"] == labels[k]["label_basis"]
        assert r["source"]
    assert len(m) == 3548


def test_the_inputs_of_2026_10_11_give_the_old_final_sidecar(tmp_path):
    """Batches 1-22 with the labels of 2026-10-11 give project_meta.layer1.final.json."""
    pin = HERE / "project_meta.layer1.final.json.sha256"
    if not (HERE.parent / "s2-pool" / "pool.csv").exists():
        pytest.skip("no s2-pool/pool.csv")
    out = tmp_path / "final.json"
    args = [a for p in final_meta.SIDECARS[:3] for a in ("--sidecar", str(p))]
    assert final_meta.main(["--out", str(out), "--labels",
                            str(HERE.parent / "s6-labels" / "labels.20261011.csv")] + args) == 0
    assert hashlib.sha256(out.read_bytes()).hexdigest() == pin.read_text().split()[0]


def test_merge():
    assert final_meta.merge([{"a": 1}, {"b": 2, "a": 1}], "x") == {"a": 1, "b": 2}
    with pytest.raises(ValueError, match="repeats"):
        final_meta.merge([{"a": 1}, {"a": 2}], "x")


def test_a_key_in_two_sidecars_is_an_error(tmp_path):
    side = HERE / "project_meta.batch22.json"
    if not side.exists():
        pytest.skip(f"no {side.name}")
    assert final_meta.main(["--out", str(tmp_path / "x.json"), "--sidecar", str(side),
                            "--sidecar", str(side)]) == 1
    assert not (tmp_path / "x.json").exists()


def test_the_layer_1_run_of_2026_10_09_differs_only_by_the_host_rules(tmp_path):
    """The 3,265 projects of batches 1-20 with the labels of 2026-10-09 give the old sidecar,
    except the license of the 36 projects that are not on GitHub (host rule, 2026-10-11)."""
    old = HERE / "project_meta.layer1.final.20261009.json"
    if not (HERE.parent / "s2-pool" / "pool.csv").exists() or not old.exists():
        pytest.skip("no s2-pool/pool.csv or no sidecar of 2026-10-09")
    out = tmp_path / "final.json"
    assert final_meta.main(["--out", str(out), "--sidecar", str(final_meta.SIDECARS[0]),
                            "--labels", str(HERE.parent / "s6-labels" / "labels.20261009.csv")]) == 0
    o, n = json.loads(old.read_text()), json.loads(out.read_text())
    assert list(o) == list(n)
    diff = [(k, f, o[k][f], n[k][f]) for k in o for f in o[k] if o[k][f] != n[k][f]]
    assert len(diff) == 36
    assert all(f == "license" and a == "" and b == "NOASSERTION" and "github.com/" not in o[k]["clone_url"]
               for k, f, a, b in diff)


@pytest.mark.parametrize("host, rec_in, changed, want", [
    ("github.com", {"license": "", "owner": "o"}, set(), {"license": "", "owner": "o"}),
    ("", {"license": "", "owner": "o"}, set(), {"license": "", "owner": "o"}),
    ("gitlab.com", {"license": "", "owner": "o"}, {"license"}, {"license": "NOASSERTION", "owner": "o"}),
    ("gitlab.com", {"license": "MIT", "owner": "o"}, set(), {"license": "MIT", "owner": "o"}),
    ("git.savannah.gnu.org", {"license": "NOASSERTION", "owner": "git"}, {"owner"},
     {"license": "NOASSERTION", "owner": "gnu"}),
    ("Git.Savannah.gnu.org", {"license": "", "owner": "git.savannah.gnu.org"}, {"license", "owner"},
     {"license": "NOASSERTION", "owner": "gnu"}),
    ("gcc.gnu.org", {"license": "NOASSERTION", "owner": "git"}, set(),
     {"license": "NOASSERTION", "owner": "git"}),
])
def test_host_rules(host, rec_in, changed, want):
    new, got = final_meta.host_rules(rec_in, {"host": host})
    assert (new, got) == (want, changed)


def test_the_new_sidecar_keeps_the_old_rows():
    old, new = HERE / "project_meta.layer1.final.20261009.json", HERE / "project_meta.layer1.final.json"
    if not (old.exists() and new.exists()):
        pytest.skip("no final sidecars")
    o, n = json.loads(old.read_text()), json.loads(new.read_text())
    assert list(n)[:len(o)] == list(o)
    for k in o:   # only the license host rule changes an old row
        gh = "github.com/" in o[k]["clone_url"]
        assert n[k] == (o[k] if gh else {**o[k], "license": o[k]["license"] or "NOASSERTION"}), k
    added = [n[k] for k in list(n)[len(o):]]
    assert len(added) == 114
    assert all(r["stratum"] and r["label_date"] == "2026-10-11" and r["source"] for r in added)


def test_the_v1_sidecar_keeps_the_rows_of_2026_10_11():
    old, new = HERE / "project_meta.layer1.final.json", HERE / "project_meta.v1.final.json"
    if not (old.exists() and new.exists()):
        pytest.skip("no final sidecars")
    o, n = json.loads(old.read_text()), json.loads(new.read_text())
    assert list(n)[:len(o)] == list(o)
    assert all(n[k] == o[k] for k in o)
    dates = {"23": "2026-10-16", "25": "2026-10-14", "26": "2026-10-14"}   # 25, 26: the sidecar's date
    added = list(n)[len(o):]
    assert len(added) == 169
    for b, date in dates.items():
        keys = json.loads((HERE / f"project_meta.batch{b}.json").read_text())
        assert all(n[k]["stratum"] and n[k]["label_date"] == date and n[k]["source"] for k in keys)
    assert sum(len(json.loads((HERE / f"project_meta.batch{b}.json").read_text())) for b in dates) \
        == len(added)


@pytest.mark.parametrize("name, n_detected", [("project_meta.layer1.final.json", 0),
                                              ("project_meta.v1.final.json", 11)])
def test_the_new_sidecar_follows_the_host_rules(name, n_detected):
    """A row that is not on GitHub has NOASSERTION, or the license that the supplement found.
    Batch 25 (2026-10-14): s4-filter/supplement25.licenses.csv found a license in 11 GitLab rows."""
    new = HERE / name
    if not new.exists():
        pytest.skip("no final sidecar")
    n = json.loads(new.read_text())
    with (HERE.parent / "s4-filter" / "supplement25.licenses.csv").open(newline="") as fh:
        found = {r["pool_key"]: r["license"] for r in csv.DictReader(fh) if r["license"] != "NOASSERTION"}
    other = {k: r for k, r in n.items() if "github.com/" not in r["clone_url"]}
    detected = {k: r for k, r in other.items() if r["license"] != "NOASSERTION"}
    assert len(detected) == n_detected
    for k, r in detected.items():
        assert r["license"] and found.get("url:" + r["clone_url"].removesuffix(".git")) == r["license"], k
    sav = [r for k, r in n.items() if k.startswith("git.savannah.gnu.org__")]
    assert len(sav) == 25 and all(r["owner"] == "gnu" for r in sav)


def test_out_refuses_an_existing_file(tmp_path):
    out = tmp_path / "x.json"
    out.write_text("keep")
    assert final_meta.main(["--out", str(out)]) == 1
    assert out.read_text() == "keep"
