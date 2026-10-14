"""Tests for the supplement mode of build_run.sh (2026-10-10, batch 21): it checks its arguments and refuses
to overwrite a file before it calls any tool. The build itself is checked on the real batch 21 files."""
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def run(tmp_path, *args):
    shutil.copy(HERE / "build_run.sh", tmp_path / "build_run.sh")
    return subprocess.run(["bash", str(tmp_path / "build_run.sh"), *args], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "CTP": str(tmp_path / "no-ctp"), "HOME": str(tmp_path)})


@pytest.mark.parametrize("args", [["supplement"], ["supplement", "20", "a.csv", "b.csv"],
                                  ["supplement", "21", "missing.csv", "b.csv"], ["supplement", "x", "a.csv", "b.csv"]])
def test_bad_arguments_give_the_usage(tmp_path, args):
    (tmp_path / "a.csv").write_text("x\n")
    (tmp_path / "b.csv").write_text("x\n")
    r = run(tmp_path, *[str(tmp_path / a) if a.endswith(".csv") else a for a in args])
    assert r.returncode == 2 and "usage: build_run.sh supplement" in r.stderr


def test_an_existing_output_is_not_overwritten(tmp_path):
    (tmp_path / "a.csv").write_text("x\n")
    (tmp_path / "b.csv").write_text("x\n")
    (tmp_path / "manifest.batch21.tsv").write_text("keep\n")
    r = run(tmp_path, "supplement", "21", str(tmp_path / "a.csv"), str(tmp_path / "b.csv"))
    assert r.returncode == 1 and "FAIL manifest.batch21.tsv exists" in r.stderr
    assert (tmp_path / "manifest.batch21.tsv").read_text() == "keep\n"
    assert not (tmp_path / "frame.batch21.csv").exists()
