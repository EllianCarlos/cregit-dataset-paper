"""Tests for build_evidence.py (S5, 2026-10-09; batches 21-22 added 2026-10-11). Run: python3 -m pytest -q test_build_evidence.py
The real-data tests need s2-pool/pool.csv (xz -d -k s2-pool/pool.csv.xz) and skip without it."""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "s2-pool"))
import build_evidence as be  # noqa: E402

POOL = ROOT / "s2-pool" / "pool.csv"
need_pool = pytest.mark.skipif(not POOL.exists(), reason="no s2-pool/pool.csv")


@pytest.mark.parametrize("url, login", [
    ("https://github.com/3mfconsortium", "3mfconsortium"),
    ("https://github.com/KDE/", "kde"),
    ("https://github.com/orgs/C4SBF", "c4sbf"),
    ("https://github.com/eclipse?q=webtools", "eclipse"),
    ("https://github.com/topics/windows-pv-driver", ""),
    ("https://github.com/openhwfoundation /core-et", ""),
    ("https://gitlab.com/x", ""),
])
def test_org_login(url, login):
    assert be.org_login(url)[0] == login


def test_norm_url_is_the_one_of_build_pool():
    import build_pool
    for u in ("https://invent.kde.org/a/b.git", "http://Git.Savannah.gnu.org/x/", " https://x.org/y "):
        assert be.norm_url(u) == build_pool.norm_url(u)


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    if not POOL.exists():
        pytest.skip("no s2-pool/pool.csv")
    d = tmp_path_factory.mktemp("s5")
    out, counts, checks = d / "evidence.csv", d / "counts.txt", d / "checks.txt"
    assert be.main(["--out", str(out), "--counts", str(counts), "--checks", str(checks)]) == 0
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    by = defaultdict(list)
    for r in rows:
        by[r["project"]].append(r)
    return {"out": out, "counts": counts, "checks": checks, "rows": rows, "by": by}


def test_the_committed_outputs_are_what_the_script_writes(real):
    assert real["out"].read_bytes() == (HERE / "evidence.csv").read_bytes()
    assert real["counts"].read_bytes() == (HERE / "counts.txt").read_bytes()
    assert real["checks"].read_bytes() == (HERE / "checks.txt").read_bytes()


def test_every_join_agrees_with_the_pool_origins(real):
    lines = real["checks"].read_text().splitlines()
    assert lines and all(l.startswith("info:") for l in lines)


def test_every_fact_has_a_source_a_date_and_a_pointer(real):
    for r in real["rows"]:
        assert r["source"] and r["fetched_at"] and r["pointer"] and r["source_url"], r
        assert r["fact"].startswith(r["fact_type"] + ":")
        path = r["pointer"].split(":")[0]
        assert (ROOT / path).exists(), r["pointer"]


def test_every_github_project_has_one_owner_kind(real):
    frame = be.load_frame(*be.FRAMES)
    for x in frame:
        kinds = [r for r in real["by"][x["project"]] if r["fact_type"] == "owner_kind"]
        assert len(kinds) == (1 if x["pool_key"].startswith("gh:") else 0), x["project"]


def test_known_projects(real):
    by = real["by"]
    kafka = {(r["fact"], r["language"]) for r in by["apache__kafka"]}
    assert ("roster:asf", "Scala") in kafka and ("roster:asf-incubator", "") in kafka
    ms = {(r["fact"], r["status"]) for r in by["microsoft__terminal"] if r["fact_type"] == "company_org"}
    assert ms == {("company_org:Microsoft", "page"), ("company_org:Microsoft", "verified-domain")}
    hi = {r["fact"] for r in by["ERGO-Code__HiGHS"]}
    assert "roster_affiliated:numfocus" in hi and not any(f.startswith("fiscal_sponsor") for f in hi)
    git = {r["fact"] for r in by["git__git"]}
    assert "fiscal_sponsor:sfc" in git
    wine = {r["fact"] for r in by["gitlab.winehq.org__wine__wine"]}
    assert wine == {"fiscal_sponsor:sfc"}   # not on GitHub: no owner_kind
    assert {r["fact"] for r in by["torvalds__linux"]} == {"owner_kind:user"}


def test_a_kept_org_with_no_page_and_no_verified_domain_is_only_a_candidate(real):
    for r in real["rows"]:
        if r["fact_type"] == "company_org_candidate":
            assert not any(x["fact_type"] == "company_org" and x["name"] == r["name"]
                           for x in real["by"][r["project"]])


def test_the_frames_are_dataset_version_1(real):
    frame = be.load_frame(*be.FRAMES)
    assert len(frame) == 3379
    assert {r["project"] for r in real["rows"]} <= {x["project"] for x in frame}
    assert real["counts"].read_text().splitlines()[1] == "projects: 3379"


def test_load_frame_refuses_a_name_in_two_frames(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("slug,host,repo_url,pool_key\no/r,github.com,https://github.com/o/r.git,gh:1\n")
    with pytest.raises(ValueError, match="repeated"):
        be.load_frame(a, a)


def test_load_pool_takes_a_key_from_the_first_file_and_refuses_other_values(tmp_path):
    a, b, c = tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "c.csv"
    a.write_text("pool_key,origins\ngh:1,search\ngh:2,search\n")
    b.write_text("pool_key,origins\ngh:2,search\ngh:3,rosters/gnu.v2.csv:gnu\n")
    c.write_text("pool_key,origins\ngh:2,rosters/x.csv:x\n")
    got = be.load_pool([a, b], {"gh:2", "gh:3"})
    assert set(got) == {"gh:2", "gh:3"}
    assert (got["gh:2"]["_file"].name, got["gh:2"]["_line"]) == ("a.csv", 3)
    assert got["gh:3"]["_file"].name == "b.csv"
    with pytest.raises(ValueError, match="other values"):
        be.load_pool([a, c], {"gh:2"})


def test_batch_21_rows(real):
    by = real["by"]
    assert {r["fact"] for r in by["NetBSD__pkgsrc"]} == {"roster:netbsd", "owner_kind:org"}
    busybox = by["git.busybox.net__busybox"]   # not on GitHub: no owner_kind
    assert {r["fact"] for r in busybox} == {"fiscal_sponsor:sfc"}
    assert busybox[0]["source"] == "rosters/sfc.repos.csv"
    kwin = {r["fact"] for r in by["KDE__kwin"]}
    assert {"roster:kde", "company_roster_org:redhat"} <= kwin


def test_batch_22_rows_are_gnu_roster_rows(real):
    frame = be.load_frame(ROOT / "s7-run" / "frame.batch22.csv")
    assert len(frame) == 33
    for x in frame:
        facts = {r["fact"] for r in real["by"][x["project"]]}
        assert facts == {"roster:gnu"}, x["project"]   # not on GitHub: no owner_kind
    texinfo = real["by"]["git.savannah.gnu.org__git__texinfo"]
    assert [(r["source"], r["status"]) for r in texinfo] == [("rosters/gnu.v2.csv", "GNU package")]


def test_a_pool_row_from_before_gnu_v2_gives_an_info_line(real):
    # 3dldf and bison are in pool.csv from gnu.csv; gnu.v2.csv (a later fetch) names them too.
    lines = real["checks"].read_text().splitlines()
    for name in ("git.savannah.gnu.org__git__3dldf", "git.savannah.gnu.org__git__bison"):
        assert sorted(r["source"] for r in real["by"][name]) == ["rosters/gnu.csv", "rosters/gnu.v2.csv"]
        assert any(l.startswith(f"info: {name}: joined rosters/gnu.v2.csv:gnu too") for l in lines)
