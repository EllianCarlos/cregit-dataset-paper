"""Tests of x3_report.py and x3_plainblame.py (kit x3) on small files. No AWS.
Run: <ctp venv python> -I -m pytest -q -p no:cacheprovider ~/s3-work/dataset-x1k/x3/test
The test addresses are made with chr(64), so this file holds no address."""
import csv
import json
import sys
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
S8 = Path.home() / "Projects/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection/s8-companies"
sys.path.insert(0, str(S8))
import x3_plainblame  # noqa: E402
import x3_report  # noqa: E402
import build_links  # noqa: E402

AT = chr(64)


def tsv(path: Path, header, rows) -> Path:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    return path


def read_tsv(path: Path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def cache_file(d: Path, project: str, rows) -> None:
    """rows: (domain, local part, tokens, commits); the e-mail is local part + at sign + domain."""
    d.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE t (project VARCHAR, domain VARCHAR, email VARCHAR, committer_domain VARCHAR, "
                "tokens BIGINT, commits BIGINT, first_date TIMESTAMP, last_date TIMESTAMP)")
    con.executemany("INSERT INTO t VALUES (?, ?, ?, '', ?, ?, NULL, NULL)",
                    [(project, dom, f"{u}{AT}{dom}" if u else "", t, c) for dom, u, t, c in rows])
    con.execute(f"COPY t TO '{d / (project + '.parquet')}' (FORMAT PARQUET)")


# ---------------------------------------------------------------- x3_report inputs + check-cache
def test_inputs_and_check_cache(tmp_path):
    root = tmp_path / "raw"
    (root / "parquet").mkdir(parents=True)
    for p in ("a", "b"):
        (root / "parquet" / f"{p}-dataset.parquet").write_bytes(b"x")
    res = tsv(tmp_path / "results.tsv", ("project", "source", "output", "output_sha256", "rows"),
              [("a", "x1k-b", "parquet/a-dataset.parquet", "aa", 3), ("b", "x1k-a", "parquet/b-dataset.parquet", "bb", 7)])
    out = tmp_path / "inputs.tsv"
    assert x3_report.main(["inputs", "--results", str(res), "--root", str(root), "--out", str(out)]) == 0
    rows = read_tsv(out)
    assert [r["project"] for r in rows] == ["b", "a"]  # the most rows first
    assert rows[0]["path"] == str(root / "parquet/b-dataset.parquet") and rows[0]["rows"] == "7"
    cache = tmp_path / "cache"
    cache_file(cache, "a", [("acme.com", "x", 3, 1)])
    cache_file(cache, "b", [("acme.com", "x", 5, 1), ("", "", 2, 1)])
    assert x3_report.main(["check-cache", "--inputs", str(out), "--cache", str(cache)]) == 0
    cache_file(cache, "b", [("acme.com", "x", 5, 1)])  # 5 tokens, 7 rows
    assert x3_report.main(["check-cache", "--inputs", str(out), "--cache", str(cache)]) == 1
    (cache / "b.parquet").unlink()
    assert x3_report.main(["check-cache", "--inputs", str(out), "--cache", str(cache)]) == 1


def test_inputs_missing_file_fails(tmp_path):
    res = tsv(tmp_path / "results.tsv", ("project", "output", "output_sha256", "rows"),
              [("a", "parquet/a-dataset.parquet", "aa", 3)])
    assert x3_report.main(["inputs", "--results", str(res), "--root", str(tmp_path),
                           "--out", str(tmp_path / "i.tsv")]) == 1


# ---------------------------------------------------------------- links: gate, merge, domains
@pytest.fixture
def links_inputs(tmp_path):
    db = tmp_path / "companies.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE company (company_id VARCHAR, name VARCHAR, kind VARCHAR, kind_basis VARCHAR, "
                "review_status VARCHAR)")
    con.executemany("INSERT INTO company VALUES (?, ?, ?, ?, ?)", [
        ("acme", "Acme", "company", "sec-filer", "accepted"),
        ("independent", "Independent", "independent", "", "accepted"),
        ("free-provider", "Free mail provider", "free-provider", "", "accepted"),
    ])
    con.execute("CREATE TABLE company_domain (domain VARCHAR, company_id VARCHAR, confidence VARCHAR, source VARCHAR)")
    con.executemany("INSERT INTO company_domain VALUES (?, ?, ?, 'test')", [
        ("acme.com", "acme", "curated"), ("me.name", "independent", "curated")])
    con.execute("CREATE TABLE company_namespace (host VARCHAR, namespace VARCHAR, company_id VARCHAR, "
                "relation VARCHAR, evidence VARCHAR, verified BOOLEAN)")
    con.execute("INSERT INTO company_namespace VALUES ('github.com', 'acme', 'acme', 'owns', 'page', true)")
    con.close()
    v1c, xc = tmp_path / "v1" / "cache", tmp_path / "x1k" / "cache"
    cache_file(v1c, "acme__v", [("acme.com", "a", 50, 5), ("acme.com", "b", 40, 4), ("me.name", "m", 10, 1)])
    cache_file(v1c, "solo__w", [("old.org", "o", 5, 1)])
    cache_file(xc, "acme__x", [("acme.com", "a", 30, 3), ("eu.acme.com", "e", 20, 2), ("new.io", "n", 9, 1),
                               ("new.io", "k", 1, 1), ("old.org", "o", 3, 1), (f"z{AT}host", "", 2, 1),
                               ("", "", 1, 1), ("users.noreply.github.com", "g", 4, 1)])
    cache_file(xc, "other__y", [("new.io", "n", 6, 2)])
    v1s, xs = tmp_path / "v1.json", tmp_path / "x1k.json"
    v1s.write_text(json.dumps({"acme__v": {"clone_url": "https://github.com/acme/v.git", "owner": "acme"},
                               "solo__w": {"clone_url": "https://github.com/solo/w.git", "owner": "solo"}}))
    xs.write_text(json.dumps({"acme__x": {"clone_url": "https://github.com/acme/x.git", "owner": "acme"},
                              "other__y": {"clone_url": "https://gitlab.com/other/y.git", "owner": "Other"},
                              "gone__z": {"clone_url": "https://github.com/gone/z.git", "owner": "gone"}}))
    return tmp_path, db, v1c, xc, v1s, xs


def test_gate_merge_and_domains(links_inputs):
    tmp, db, v1c, xc, v1s, xs = links_inputs
    ref, chk, mrg = tmp / "ref", tmp / "chk", tmp / "mrg"
    build_links.build(db, v1c, v1s, ref, "1GB", 1, "v-test")
    build_links.build(db, v1c, v1s, chk, "1GB", 1, "v-test")
    assert x3_report.main(["compare-links", "--got", str(chk), "--ref", str(ref)]) == 0
    m = build_links.build(db, [v1c, xc], [v1s, xs], mrg, "1GB", 1, "v-test")
    assert m["projects"] == 5
    assert x3_report.main(["compare-links", "--got", str(mrg), "--ref", str(ref), "--subset"]) == 0
    # the merged links are not the v1 links: the full gate fails, as it must
    assert x3_report.main(["compare-links", "--got", str(mrg), "--ref", str(ref)]) == 1
    out = tmp / "out"
    assert x3_report.main(["domains", "--v1-cache", str(v1c), "--x1k-cache", str(xc), "--links", str(mrg),
                           "--v1-sidecar", str(v1s), "--x1k-sidecar", str(xs), "--out", str(out),
                           "--memory-limit", "1GB", "--threads", "1"]) == 0
    new = read_tsv(out / "new_domains.x1k.tsv")
    assert [(r["domain"], r["projects"], r["tokens"], r["authors"], r["top_project"]) for r in new] == [
        ("new.io", "2", "16", "2", "acme__x")]
    assert float(new[0]["token_share_x1k"]) == pytest.approx(16 / 76)
    assert float(new[0]["token_share_all"]) == pytest.approx(16 / 181)
    linked = {r["domain"]: r["firm_based_on_domain"] for r in read_tsv(out / "new_domains_linked.x1k.tsv")}
    assert linked == {"eu.acme.com": "acme", "users.noreply.github.com": "free-provider"}
    ns = read_tsv(out / "new_namespaces.x1k.tsv")
    assert {(r["host"], r["namespace"], r["tokens"]) for r in ns} == {("gitlab.com", "other", "6"),
                                                                      ("github.com", "gone", "0")}
    s = json.loads((out / "domains.x1k.json").read_text())
    assert s["x1k_tokens"] == 76 and s["v1_tokens"] == 105 and s["new_domains_unlinked"] == 1
    assert s["x1k_token_share_by_value_class"]["organisation"] == pytest.approx(50 / 76)
    assert s["x1k_token_share_by_value_class"]["unknown"] == pytest.approx(3 / 76)
    assert s["x1k_projects_with_namespace_owner"] == 1
    con = duckdb.connect()
    dc = dict(con.execute("SELECT domain, tokens FROM read_parquet(?) WHERE project = 'acme__x'",
                          [str(out / "domain_counts.x1k.parquet")]).fetchall())
    assert dc[x3_report.NOT_A_DOMAIN] == 2 and dc["new.io"] == 10
    files = sorted(out.iterdir()) + [mrg / f"{t}.parquet" for t in x3_report.LINK_TABLES] + [mrg / "links.json"]
    assert x3_report.main(["no-at", *map(str, files)]) == 0


def test_no_at_finds_an_address(tmp_path):
    f = tmp_path / "a.tsv"
    f.write_text(f"domain\nx{AT}y.org\n")
    p = tmp_path / "a.parquet"
    duckdb.connect().execute(f"COPY (SELECT 'ok' AS a, 'x' || chr(64) || 'y' AS b) TO '{p}' (FORMAT PARQUET)")
    assert x3_report.main(["no-at", str(f)]) == 1
    assert x3_report.main(["no-at", str(p)]) == 1


# ---------------------------------------------------------------- x3_plainblame
def log(root: Path, d: str, p: str, name: str, files, form: str = "after 3600 s of -C100") -> None:
    """A pipeline log with one cregit PLAIN-BLAME line per file of FILES."""
    f = root / d / p / "state" / "logs" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(f"PLAIN-BLAME {x} {form}\n" for x in files) + "other line\n")


def extra_log(root: Path, d: str, k: str, files) -> None:
    f = root / d / "out" / k / "plainblame.log"
    f.parent.mkdir(parents=True)
    f.write_text("".join(f"PLAIN-BLAME {x} after 3600 s of -C100\n" for x in files))


def run_pb(tmp_path, results):
    res = tsv(tmp_path / "results.tsv", ("project", "source"), results)
    out, summ = tmp_path / "pb.tsv", tmp_path / "pb.json"
    assert x3_plainblame.main(["--results", str(res), "--logs", str(tmp_path / "logs"), "--out", str(out),
                               "--summary", str(summ)]) == 0
    return {r["project"]: r for r in read_tsv(out)}, json.loads(summ.read_text()), out, summ


def test_plainblame_rules(tmp_path):
    L = tmp_path / "logs"
    log(L, "done-full", "b1", "pipeline-20261019T010000.log", ["a.c", "b.c", "c.c", "d.c"])
    log(L, "done-full", "b1", "pipeline-20261020T010000.log", ["a.c"])          # B: newest only -> 1
    log(L, "done-full", "awslabs__aws-sdk-rust", "pipeline-20261020T010000.log", ["r1.rs", "r2.rs"])
    log(L, "done-full", "awslabs__aws-sdk-rust", "pipeline-20261021T010000.log", ["r3.rs"])
    log(L, "done-full", "pf", "pipeline-20261019T010000.log", ["p1", "p2", "p3"])  # the done-full run: not used
    log(L, "done-pathfix", "pf", "pipeline-20261020T224156.log", ["p1", "dir with space/p 2.c"])
    extra_log(L, "rust-split", "1", ["e1.rs", "e2.rs"])
    extra_log(L, "rust-split", "2", [])
    got, s, out, summ = run_pb(tmp_path, [("b1", "x1k-b"), ("awslabs__aws-sdk-rust", "x1k-a"),
                                          ("pf", "x1k-pathfix"), ("nolog", "x1k-b")])
    assert (got["b1"]["plain_blame"], got["b1"]["plain_blame_lines"]) == ("1", "1")
    assert (got["b1"]["plain_blame_all_logs"], got["b1"]["plain_blame_all_logs_lines"]) == ("4", "5")
    r = got["awslabs__aws-sdk-rust"]
    assert (r["plain_blame"], r["plain_blame_lines"], r["plain_blame_extra"]) == ("5", "5", "2")
    assert (got["pf"]["plain_blame"], got["pf"]["log_dir"]) == ("2", "done-pathfix")
    assert got["nolog"]["plain_blame"] == "NA"
    assert s["files"] == 8 and s["lines"] == 8 and s["no_log"] == ["nolog"] and s["projects_with_plain_blame"] == 3
    assert s["extra_machines"]["awslabs__aws-sdk-rust"] == {"parts": 2, "lines": 2, "files": 2}
    assert AT not in out.read_text() + summ.read_text()


def test_a_file_that_falls_back_in_two_attempts_counts_once(tmp_path):
    L = tmp_path / "logs"
    # machine A row: attempt 1 falls back on big.c and x.c; the resumed attempt 2 blames big.c again
    # (and it falls back again, here with the exit 128 form of 23e4ccb); an extra machine also has x.c
    log(L, "done-full", "aws__aws-sdk-java", "pipeline-20261020T010000.log", ["big.c", "x.c"])
    log(L, "done-full", "aws__aws-sdk-java", "pipeline-20261021T010000.log", ["big.c"], "after git exit 128 of -C100")
    extra_log(L, "java-split", "1", ["x.c", "y.c"])
    got, s, _, _ = run_pb(tmp_path, [("aws__aws-sdk-java", "x1k-a")])
    r = got["aws__aws-sdk-java"]
    assert (r["plain_blame_all_logs"], r["plain_blame_all_logs_lines"]) == ("2", "3")
    assert (r["plain_blame_extra"], r["plain_blame_extra_lines"]) == ("2", "2")
    assert (r["plain_blame"], r["plain_blame_lines"]) == ("3", "5")   # big.c, x.c, y.c once each
    assert s["files"] == 3 and s["lines"] == 5


def test_plainblame_unknown_source_is_usage(tmp_path):
    res = tsv(tmp_path / "results.tsv", ("project", "source"), [("a", "v1")])
    assert x3_plainblame.main(["--results", str(res), "--logs", str(tmp_path), "--out", str(tmp_path / "o"),
                               "--summary", str(tmp_path / "s")]) == 2
