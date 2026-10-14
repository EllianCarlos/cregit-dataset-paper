"""Tests for split_run_ledgers.py. Run: python3 -m pytest test_split_run_ledgers.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import split_run_ledgers as srl  # noqa: E402


def row(run_id, project, attempt, step, status, **kw):
    r = {"v": 1, "run_id": run_id, "project": project, "attempt": attempt, "step": step,
         "status": status, "pinned_sha": kw.pop("pinned_sha", "p" * 40),
         "tools": {"cregit_commit": kw.pop("cregit", "95cdc881e5c8f736c87487139849388575f20d91")}}
    r.update(kw)
    return r


def lines(*rows):
    return "".join(json.dumps(r) + "\n" for r in rows)


def setup(tmp_path, ledger_text, sha="a" * 64, rel="batch2/done/o__p"):
    cloud = tmp_path / "cloud"
    (cloud / rel).mkdir(parents=True)
    (cloud / rel / "o__p-dataset.parquet").write_bytes(b"x")
    (cloud / "verified.tsv").write_text(f"2026-10-11T00:00:00Z\t{rel}\t{sha}\n")
    led = tmp_path / "ledgers" / "batch2" / "live"
    led.mkdir(parents=True)
    (led / "ledger.jsonl").write_text(ledger_text)
    return cloud, tmp_path / "ledgers", cloud / rel


PIN = {"url": "https://github.com/o/p.git", "pinned_sha": "b" * 40, "branch": "main"}


def test_writes_the_rows_and_the_pin_of_the_attempt_that_made_the_parquet(tmp_path):
    text = lines(
        row("R1", "o__p", 1, "clone", "ok", pinned_sha="c" * 40, pin=dict(PIN, pinned_sha="c" * 40)),
        row("R1", "o__p", 1, "project", "failed", pinned_sha="c" * 40),
        row("R2", "o__p", 1, "clone", "ok", pinned_sha="b" * 40, pin=PIN),
        row("R2", "x__y", 1, "clone", "ok"),
        row("R2", "o__p", 1, "project", "done", pinned_sha="b" * 40,
            parquet={"sha256": "a" * 64}))
    cloud, ledgers, folder = setup(tmp_path, text)
    assert srl.main(["--ledgers", str(ledgers), "--cloud", str(cloud)]) == 0
    pin = json.loads((folder / srl.PIN_OUT).read_text())
    assert pin["pinned_sha"] == "b" * 40 and pin["branch"] == "main"
    assert pin["run_id"] == "R2" and pin["cregit_commit"].startswith("95cdc88")
    got = [json.loads(ln) for ln in (folder / srl.LEDGER_OUT).read_text().splitlines()]
    assert [(r["run_id"], r["project"], r["step"]) for r in got] == \
        [("R2", "o__p", "clone"), ("R2", "o__p", "project")]
    assert not (folder / "ledger.jsonl").exists()


def test_no_file_when_no_done_row_has_the_parquet_sha(tmp_path, capsys):
    text = lines(row("R1", "o__p", 1, "project", "done", parquet={"sha256": "f" * 64}))
    cloud, ledgers, folder = setup(tmp_path, text)
    srl.main(["--ledgers", str(ledgers), "--cloud", str(cloud)])
    assert not (folder / srl.PIN_OUT).exists() and not (folder / srl.LEDGER_OUT).exists()
    assert "no match: batch2/done/o__p" in capsys.readouterr().out


def test_two_copies_and_a_partial_last_line_give_each_row_once(tmp_path):
    text = lines(row("R1", "o__p", 1, "clone", "ok", pin=PIN),
                 row("R1", "o__p", 1, "project", "done", parquet={"sha256": "a" * 64}))
    cloud, ledgers, folder = setup(tmp_path, text)
    backup = ledgers / "batch2" / "backup-ledger"
    backup.mkdir()
    (backup / "ledger.jsonl").write_text(text + '{"v": 1, "proj')
    srl.main(["--ledgers", str(ledgers), "--cloud", str(cloud)])
    assert len((folder / srl.LEDGER_OUT).read_text().splitlines()) == 2


def test_a_second_run_writes_nothing_and_the_s3_ledger_stays(tmp_path, capsys):
    text = lines(row("R1", "o__p", 1, "clone", "ok", pin=PIN),
                 row("R1", "o__p", 1, "project", "done", parquet={"sha256": "a" * 64}))
    cloud, ledgers, folder = setup(tmp_path, text)
    (folder / "ledger.jsonl").write_text("from s3\n")
    srl.main(["--ledgers", str(ledgers), "--cloud", str(cloud)])
    first = capsys.readouterr().out
    mtime = (folder / srl.PIN_OUT).stat().st_mtime_ns
    srl.main(["--ledgers", str(ledgers), "--cloud", str(cloud)])
    assert "1 written" in first and "0 written, 1 unchanged" in capsys.readouterr().out
    assert (folder / srl.PIN_OUT).stat().st_mtime_ns == mtime
    assert (folder / "ledger.jsonl").read_text() == "from s3\n"


def test_refuses_to_write_a_file_named_ledger_jsonl(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        srl.write_if_changed(tmp_path / "ledger.jsonl", "x", False)
