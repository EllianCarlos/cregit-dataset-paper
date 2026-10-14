"""Tests for split_batchN.frame_index (2026-10-10: batch 21 rows are not in frame.layer1.csv)."""
import csv
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import split_batchN  # noqa: E402

COLS = ["slug", "host", "repo_url", "commits", "tok_bytes"]


def write(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def row(slug, commits="6000"):
    return {"slug": slug, "host": "github.com", "repo_url": f"https://github.com/{slug}.git", "commits": commits,
            "tok_bytes": "1000"}


def test_a_batch_frame_adds_rows_that_layer1_does_not_have(tmp_path):
    write(tmp_path / "frame.layer1.csv", [row("a/a"), row("b/b")])
    write(tmp_path / "frame.batch21.csv", [row("c/c")])
    index = split_batchN.frame_index(tmp_path, "batch21")
    assert sorted(index) == ["https://github.com/a/a", "https://github.com/b/b", "https://github.com/c/c"]


def test_without_a_batch_frame_the_index_is_layer1(tmp_path):
    write(tmp_path / "frame.layer1.csv", [row("a/a")])
    assert list(split_batchN.frame_index(tmp_path, "batch7")) == ["https://github.com/a/a"]


def test_a_url_in_both_files_must_have_the_same_row(tmp_path):
    write(tmp_path / "frame.layer1.csv", [row("a/a")])
    write(tmp_path / "frame.batch9.csv", [row("a/a", commits="7000")])
    with pytest.raises(AssertionError, match="differs"):
        split_batchN.frame_index(tmp_path, "batch9")


@pytest.mark.parametrize("n", range(6, 21))
def test_for_the_built_batches_the_index_does_not_change(n):
    if not (HERE / f"frame.batch{n}.csv").exists():
        pytest.skip("no frame file")
    only_layer1 = {r["repo_url"].rstrip("/").removesuffix(".git"): r
                   for r in csv.DictReader(open(HERE / "frame.layer1.csv", encoding="utf-8"))}
    assert split_batchN.frame_index(HERE, f"batch{n}") == only_layer1
