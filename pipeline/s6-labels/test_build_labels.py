"""Tests for build_labels.py (S6, 2026-10-09; batches 21-22 added 2026-10-11; batch 23 added 2026-10-16). Run: python3 -m pytest -q test_build_labels.py"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_labels as bl  # noqa: E402

FIRST = HERE / "labels.20261009.csv"   # the 3,265 labels of 2026-10-09 (batches 1-20)
PRIOR = HERE / "labels.20261011.csv"   # the 3,379 labels of 2026-10-11 (batches 1-22)
NEW_DATE = "2026-10-16"                 # the run that added batch 23
ORG = ("owner_kind", "owner_kind:org")
USER = ("owner_kind", "owner_kind:user")
ROSTER = ("roster", "roster:asf")
RORG = ("roster_org", "roster_org:lf")
SP = ("company_pool", "company_pool:spinellis")
CORG = ("company_org", "company_org:Microsoft")
FISC = ("fiscal_sponsor", "fiscal_sponsor:sfc")
GOV = ("government", "government:x")


@pytest.mark.parametrize("facts, label, basis, contested", [
    ([ORG, ROSTER], "foundation", "roster:asf", ""),
    ([ORG, RORG], "foundation", "roster_org:lf", ""),
    ([ORG, ROSTER, SP], "contested", "company_pool:spinellis;roster:asf",
     "company_pool:spinellis;roster:asf"),
    ([ORG, CORG], "company", "company_org:Microsoft", ""),
    ([USER, SP], "company", "company_pool:spinellis", ""),
    ([ORG, FISC], "fiscal-sponsor", "fiscal_sponsor:sfc", ""),
    ([ORG, FISC, ROSTER], "foundation", "roster:asf", ""),
    ([ORG, FISC, CORG], "contested", "company_org:Microsoft;fiscal_sponsor:sfc",
     "company_org:Microsoft;fiscal_sponsor:sfc"),
    ([ORG, GOV, ROSTER], "government", "government:x", ""),
    ([USER], "personal", "owner_kind:user", ""),
    ([ORG], "unknown", "", ""),
    ([], "unknown", "", ""),
    # A fact that sets no label still blocks personal: personal needs owner_kind:user alone.
    ([USER, ("roster_affiliated", "roster_affiliated:numfocus")], "unknown", "", ""),
    ([ORG, ("company_org_candidate", "company_org_candidate:google")], "unknown", "", ""),
    # The Red Hat table is a company fact (user decision 2026-10-09).
    ([ORG, ("company_roster_org", "company_roster_org:redhat")], "company",
     "company_roster_org:redhat", ""),
    ([ORG, ("roster", "roster:kde"), ("company_roster_org", "company_roster_org:redhat")],
     "contested", "company_roster_org:redhat;roster:kde", "company_roster_org:redhat;roster:kde"),
    ([ORG, RORG, ("company_roster_org", "company_roster_org:redhat")], "contested",
     "company_roster_org:redhat;roster_org:lf", "company_roster_org:redhat;roster_org:lf"),
    ([ORG, ("company_roster", "company_roster:mozilla")], "company", "company_roster:mozilla", ""),
])
def test_rules(facts, label, basis, contested):
    lab, b, c, other = bl.label(facts)
    assert (lab, bl.join(b), bl.join(c)) == (label, basis, contested)
    assert set(other) == {f for _, f in facts} - set(b)


def test_an_unknown_fact_type_is_an_error():
    with pytest.raises(ValueError):
        bl.label([("roster_x", "roster_x:y")])


def test_no_label_is_a_residual_community_needs_its_own_fact():
    assert bl.label([ORG])[0] == "unknown"
    assert bl.label([ORG, ("governance_doc", "governance_doc:GOVERNANCE.md")])[0] == "community"


def test_the_committed_labels_are_what_the_script_writes(tmp_path):
    if not (HERE.parent / "s5-evidence" / "evidence.csv").exists():
        pytest.skip("no S5 evidence")
    out, counts = tmp_path / "labels.csv", tmp_path / "counts.txt"
    assert bl.main(["--out", str(out), "--counts", str(counts), "--date", NEW_DATE,
                    "--prior", str(PRIOR)]) == 0
    assert out.read_bytes() == (HERE / "labels.csv").read_bytes()
    assert counts.read_bytes() == (HERE / "counts.txt").read_bytes()
    rows = list(csv.DictReader(out.open()))
    assert len(rows) == 3497 and len({r["project"] for r in rows}) == 3497
    assert all(r["label"] in bl.LABELS for r in rows)
    assert all(bool(r["contested"]) == (r["label"] == "contested") for r in rows)
    assert all(bool(r["label_basis"]) == (r["label"] != "unknown") for r in rows)


def test_the_rows_of_2026_10_09_and_2026_10_11_do_not_change():
    first = list(csv.DictReader(FIRST.open()))
    old = list(csv.DictReader(PRIOR.open()))
    new = list(csv.DictReader((HERE / "labels.csv").open()))
    assert len(first) == 3265 and new[:3265] == first
    assert len(old) == 3379 and new[:3379] == old
    assert {r["label_date"] for r in new[3265:3379]} == {"2026-10-11"}
    assert {r["label_date"] for r in new[3379:]} == {NEW_DATE}


def test_the_new_rows():
    new = {r["project"]: r for r in csv.DictReader((HERE / "labels.csv").open())}
    assert new["gcc.gnu.org__git__gcc"]["label_basis"] == "roster:gnu"
    assert new["git.busybox.net__busybox"]["label"] == "fiscal-sponsor"
    assert new["NetBSD__pkgsrc"]["label"] == "foundation"
    assert new["KDE__kwin"]["label"] == "contested"
    # batch 23
    assert new["NetBSD__src"]["label"] == "foundation"
    assert new["apache__cayenne"]["label_basis"] == "roster:asf;roster:asf-incubator"
    assert new["NVIDIA__nvtexlive"]["label"] == "company"
    assert new["igraph__rigraph"]["label"] == "unknown"   # NumFOCUS "affiliated" sets no label


def write_inputs(d, label_date="2026-10-09"):
    frame, ev, prior = d / "frame.csv", d / "evidence.csv", d / "prior.csv"
    frame.write_text("slug,host,pool_key,size_class,language\n"
                     "o/a,github.com,gh:1,S,C\no/b,github.com,gh:2,S,C\no/c,github.com,gh:3,S,C\n")
    ev.write_text("project,fact_type,fact\no__a,owner_kind,owner_kind:org\n"
                  "o__b,owner_kind,owner_kind:org\no__b,roster,roster:asf\n")
    # o__a as before; o__b had another label before; o__c is new.
    prior.write_text("project,pool_key,label,label_basis,contested,other_facts,size_class,language,"
                     f"label_date\no__a,gh:1,unknown,,,owner_kind:org,S,C,{label_date}\n"
                     f"o__b,gh:2,unknown,,,owner_kind:org,S,C,{label_date}\n")
    return frame, ev, prior


def test_prior_keeps_the_date_of_a_row_that_does_not_change(tmp_path):
    frame, ev, prior = write_inputs(tmp_path)
    out, counts = tmp_path / "labels.csv", tmp_path / "counts.txt"
    assert bl.main(["--frame", str(frame), "--evidence", str(ev), "--prior", str(prior),
                    "--date", "2026-10-11", "--out", str(out), "--counts", str(counts)]) == 0
    got = {r["project"]: (r["label"], r["label_date"]) for r in csv.DictReader(out.open())}
    assert got == {"o__a": ("unknown", "2026-10-09"), "o__b": ("foundation", "2026-10-11"),
                   "o__c": ("unknown", "2026-10-11")}
    assert counts.read_text().splitlines()[0] == \
        "projects: 3; label_date: 2026-10-09 (1), 2026-10-11 (2)"


def test_a_project_in_two_frames_is_an_error(tmp_path):
    frame, ev, _ = write_inputs(tmp_path)
    assert bl.main(["--frame", str(frame), "--frame", str(frame), "--evidence", str(ev),
                    "--out", str(tmp_path / "l.csv"), "--counts", str(tmp_path / "c.txt")]) == 1
