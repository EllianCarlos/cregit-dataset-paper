"""Tests of measure.py on small synthetic Parquet files. Run:
  python3 -m pytest -q test/
Each finding has a positive case (the defect is in the file) and a negative
case (the file is correct)."""
import os
import stat
import subprocess
import sys

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "measure.py")
sys.path.insert(0, os.path.dirname(HERE))
import measure  # noqa: E402

AT = chr(64)
TAB = chr(9)
SHA1 = "1" * 40
SHA2 = "2" * 40
SHA3 = "3" * 40
COLS = ("file_path", "token_index", "token_type", "token_value", "is_structural",
        "cregit_commit_sha", "original_commit_sha", "commit_summary", "person_domain")
PSL_TEXT = """// a test list
// ===BEGIN ICANN DOMAINS===
com
uk
co.uk
*.ck
!www.ck
// ===END ICANN DOMAINS===
// ===BEGIN PRIVATE DOMAINS===
blogspot.com
// ===END PRIVATE DOMAINS===
"""


def unit(path, commit=SHA1, summary="fix: a thing", domain="example.com"):
    """Token rows of one correct file: begin_unit, content, end_unit, blank."""
    toks = [("begin_unit", "begin_unit|revision:1.0.0;language:C;", 1),
            ("name", "x", 0), ("operator", ";", 0),
            ("end_unit", "end_unit", 1), ("blank", "", 1)]
    return [(path, i, t, v, s, commit, "o" + commit[1:], summary, domain)
            for i, (t, v, s) in enumerate(toks)]


def write_parquet(target, rows):
    con = duckdb.connect()
    con.execute("CREATE TABLE t (file_path VARCHAR, token_index BIGINT, token_type VARCHAR, "
                "token_value VARCHAR, is_structural BIGINT, cregit_commit_sha VARCHAR, "
                "original_commit_sha VARCHAR, commit_summary VARCHAR, person_domain VARCHAR)")
    con.executemany("INSERT INTO t VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    con.execute(f"COPY t TO '{target}' (FORMAT parquet)")
    con.close()


def run(tmp_path, files, *extra):
    psl = tmp_path / "psl.dat"
    psl.write_text(PSL_TEXT)
    out = tmp_path / "out"
    cmd = [sys.executable, "-I", SCRIPT, "run", "--files", *map(str, files), "--out", str(out),
           "--psl", str(psl), "--psl-sha256", "any", "--jobs", "2", "--threads", "1",
           "--mem-per-job", "0.5", "--mem-reserve", "0", "--private",
           str(tmp_path / "private"), *extra]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r, out


def one(out, finding, project):
    rows = measure.read_tsv(os.path.join(out, finding, f"{project}.tsv"))
    assert len(rows) == 1
    return {k: (int(v) if v.lstrip("-").isdigit() else v) for k, v in rows[0].items()}


def files_rows(out, finding, project):
    return measure.read_tsv(os.path.join(out, finding, f"{project}.files.tsv"))


def summary(out):
    return {(r["finding"], r["measure"]): r["value"]
            for r in measure.read_tsv(os.path.join(out, "summary.tsv"))}


def all_output_bytes(out):
    data = b""
    for d, _, fs in os.walk(out):
        for f in fs:
            data += open(os.path.join(d, f), "rb").read()
    return data


# ------------------------------------------------------------------ M4

def test_m4_negative_balanced_units(tmp_path):
    f = tmp_path / "good-dataset.parquet"
    write_parquet(f, unit("src/a.c") + unit("src/b.java"))
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    m4 = one(out, "m4", "good")
    assert m4["files"] == 2
    assert m4["files_not_1_1_raw"] == 0
    assert m4["files_cut_off"] == 0
    assert files_rows(out, "m4", "good") == []


def test_m4_positive_cut_off_and_other_flags(tmp_path):
    cut = [r for r in unit("src/cut.c") if r[2] not in ("end_unit", "blank")]
    two = unit("src/two.c")
    two = two + [("src/two.c", 5, "begin_unit", "begin_unit|x", 1, SHA1, "o", "s", "d.com"),
                 ("src/two.c", 6, "end_unit", "end_unit", 1, SHA1, "o", "s", "d.com")]
    late = unit("src/late.c")[:4] + [("src/late.c", 4, "name", "y", 0, SHA1, "o", "s", "d.com")]
    gap = [r for r in unit("src/gap.c") if r[1] != 2]
    f = tmp_path / "bad-dataset.parquet"
    write_parquet(f, unit("src/ok.c") + cut + two + late + gap)
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    m4 = one(out, "m4", "bad")
    assert m4["files"] == 5
    assert m4["files_cut_off"] == 1
    assert m4["files_multi_unit"] == 1
    assert m4["files_end_not_last"] == 1
    assert m4["files_index_gap"] == 1
    assert m4["files_not_1_1_raw"] == 2           # cut.c and two.c
    assert m4["token_rows_in_cut_off_files"] == 3
    got = {x["file_path"]: x for x in files_rows(out, "m4", "bad")}
    assert set(got) == {"src/cut.c", "src/two.c", "src/late.c", "src/gap.c"}
    assert got["src/cut.c"]["cut_off"] == "1" and got["src/cut.c"]["n_end_unit"] == "0"
    assert summary(out)[("M4", "projects_with_cut_off_file")] == "1"


def test_m4_rust_prefix_markers_are_not_cut_off(tmp_path):
    rows = unit("src/a.rs")
    rows[0] = ("src/a.rs", 0, "-:-" + TAB + "begin_unit", "revision:0.0.1;language:Rust;",
               0, SHA1, "o", "s", "example.com")
    rows[3] = ("src/a.rs", 3, "unknown", "-:-" + TAB + "end_unit", 1, SHA1, "o", "s",
               "example.com")
    f = tmp_path / "rs-dataset.parquet"
    write_parquet(f, rows)
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    m4 = one(out, "m4", "rs")
    assert m4["files_not_1_1_raw"] == 1 and m4["files_not_1_1_after_repair"] == 0
    assert m4["files_rust_prefix"] == 1 and m4["files_not_1_1_raw_by_rust_prefix"] == 1
    assert m4["files_cut_off"] == 0 and m4["files_m10_shift"] == 0


# ------------------------------------------------------------------ M10

def shifted(path):
    """Rows of a file whose earlier name 'old;name.c' shifted the split."""
    rows = unit(path)
    rows[0] = (path, 0, "name.c;" + TAB + "begin_unit", "revision:1.0.0;language:C;",
               0, SHA1, "o", "s", "example.com")
    rows[1] = (path, 1, "name.c;" + TAB + "name", "x", 0, SHA1, "o", "s", "example.com")
    rows[3] = (path, 3, "unknown", "name.c;" + TAB + "end_unit", 1, SHA1, "o", "s",
               "example.com")
    rows[4] = (path, 4, "unknown", "name.c;" + TAB, 1, SHA1, "o", "s", "example.com")
    return rows


def test_m10_negative(tmp_path):
    f = tmp_path / "good-dataset.parquet"
    rows = unit("src/a.c")
    # A tab in token_type without ';' is the known Rust prefix defect, not M10.
    rows[1] = ("src/a.c", 1, "3:4" + TAB + "name", "x", 0, SHA1, "o", "s", "example.com")
    write_parquet(f, rows)
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    m10 = one(out, "m10", "good")
    assert m10["rows_shift"] == 0 and m10["files_shift"] == 0
    assert m10["rows_path_semicolon"] == 0
    assert one(out, "m4", "good")["rows_tab_in_token_type_not_m10"] == 1
    assert files_rows(out, "m10", "good") == []


def test_m10_positive_shift_and_path_semicolon(tmp_path):
    f = tmp_path / "semi-dataset.parquet"
    write_parquet(f, unit("src/ok.c") + shifted("src/new.c") + unit("src/x;y.c"))
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    m10 = one(out, "m10", "semi")
    assert m10["rows_shift"] == 4
    assert m10["files_shift"] == 1
    assert m10["rows_shift_in_token_type"] == 2
    assert m10["rows_shift_in_token_value_unknown"] == 2
    assert m10["rows_path_semicolon"] == 5 and m10["files_path_semicolon"] == 1
    m4 = one(out, "m4", "semi")
    # The shift removes the literal markers; the repaired count is 1/1.
    assert m4["files_not_1_1_raw"] == 1
    assert m4["files_not_1_1_after_repair"] == 0
    assert m4["files_m10_shift"] == 1 and m4["files_not_1_1_raw_by_m10"] == 1
    assert m4["files_cut_off"] == 0
    assert m4["files_end_not_last"] == 0          # the shifted blank is a blank
    paths = {x["file_path"] for x in files_rows(out, "m10", "semi")}
    assert paths == {"src/new.c", "src/x;y.c"}


# ------------------------------------------------------------------ M7

def test_m7_negative(tmp_path):
    f = tmp_path / "good-dataset.parquet"
    write_parquet(f, unit("a.c", SHA1, "feat: add x")
                  + unit("b.c", SHA2, "Mention Former-commit-id: zz in text")
                  + unit("c.c", SHA3, "feat: x Former-commit-id: " + "a" * 39))
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    m7 = one(out, "m7", "good")
    assert m7["commits"] == 3
    assert m7["commits_footer_end"] == 0
    assert m7["commits_footer_anywhere"] == 2


def test_m7_positive_counts_commits_not_rows(tmp_path):
    foot = " Former-commit-id: " + "ab12" * 10
    f = tmp_path / "foot-dataset.parquet"
    write_parquet(f, unit("a.c", SHA1, "feat: add x" + foot) + unit("b.c", SHA1, "feat: add x" + foot)
                  + unit("c.c", SHA2, "Former-commit-id: " + "cd34" * 10)
                  + unit("d.c", SHA3, "plain"))
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    m7 = one(out, "m7", "foot")
    assert m7["commits"] == 3
    assert m7["commits_footer_end"] == 1           # one commit, 10 token rows
    assert m7["token_rows_footer_end"] == 10
    assert m7["commits_footer_only"] == 1
    commits = measure.read_tsv(os.path.join(out, "m7", "foot.commits.tsv"))
    assert [c["cregit_commit_sha"] for c in commits] == [SHA1]
    assert commits[0]["token_rows"] == "10"
    assert summary(out)[("M7", "projects_with_footer_end")] == "1"


# ------------------------------------------------------------------ M9

M9_VALUES = {
    "example.com": "registrable/registrable",
    "foo.co.uk": "registrable/registrable",
    "www.ck": "registrable/registrable",
    "10.0.0.1": "ip/ipv4",
    "fe80::1": "ip/ipv6",
    "my-laptop": "local_host/single_label",
    "box.local": "local_host/local_suffix",
    "box.(none)": "local_host/none_suffix",
    "host.nosuchtld": "local_host/no_public_suffix",
    "co.uk": "other/public_suffix_only",
    "x.ck": "other/public_suffix_only",
    "bad name.com": "other/bad_chars",
}


def test_m9_negative_all_registrable(tmp_path):
    f = tmp_path / "good-dataset.parquet"
    write_parquet(f, unit("a.c", domain="example.com") + unit("b.c", domain="Foo.Co.UK "))
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    rows = measure.read_tsv(os.path.join(out, "m9", "good.tsv"))
    cls = {(x["class"], x["subclass"]): x for x in rows if x["class"] != "meta"}
    assert set(cls) == {("registrable", "registrable")}
    assert cls[("registrable", "registrable")]["distinct_values"] == "2"
    assert summary(out)[("M9", "projects_with_value_not_registrable")] == "0"


def test_m9_positive_classes_counts_only(tmp_path):
    rows = []
    for i, v in enumerate(M9_VALUES):
        rows += unit(f"f{i}.c", domain=v)
    rows += unit("n.c", domain=None) + unit("w.c", domain="user" + AT + "example.com")
    f = tmp_path / "mix-dataset.parquet"
    write_parquet(f, rows)
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    got = {}
    for x in measure.read_tsv(os.path.join(out, "m9", "mix.tsv")):
        got[(x["class"], x["subclass"])] = (x["distinct_values"], x["token_rows"])
    want = {}
    for v, c in M9_VALUES.items():
        k = tuple(c.split("/"))
        want[k] = want.get(k, 0) + 1
    for k, n in want.items():
        assert got[k] == (str(n), str(5 * n)), (k, got.get(k))
    assert got[("meta", "rows_null")][1] == "5"
    assert got[("meta", "rows_with_at_sign")][1] == "5"
    # Counts only: no value is in any output file.
    data = all_output_bytes(out)
    for v in ("my-laptop", "box.local", "host.nosuchtld", "10.0.0.1", "example.com"):
        assert v.encode() not in data, v
    assert AT.encode() not in data


def test_m9_sample_is_private_and_small(tmp_path):
    rows = []
    for i in range(30):
        rows += unit(f"f{i}.c", domain=f"host{i:02d}")
    f = tmp_path / "many-dataset.parquet"
    write_parquet(f, rows)
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    priv = tmp_path / "private"
    cmd = [sys.executable, "-I", SCRIPT, "m9-sample", "--files", str(f), "--out", str(out),
           "--psl", str(tmp_path / "psl.dat"), "--psl-sha256", "any", "--private", str(priv),
           "--max", "20", "--per-class", "30", "--mem", "512MB", "--threads", "1"]
    s = subprocess.run(cmd, capture_output=True, text=True)
    assert s.returncode == 0, s.stderr
    assert stat.S_IMODE(os.stat(priv).st_mode) == 0o700
    lines = (priv / "m9-sample.tsv").read_text().splitlines()
    assert len(lines) == 21                        # a header and 20 values
    assert b"host00" not in all_output_bytes(out)


def test_m9_global_distinct_over_projects(tmp_path):
    a = tmp_path / "a-dataset.parquet"
    b = tmp_path / "b-dataset.parquet"
    write_parquet(a, unit("x.c", domain="box.local") + unit("y.c", domain="example.com"))
    write_parquet(b, unit("x.c", domain="box.local"))
    r, out = run(tmp_path, [a, b])
    assert r.returncode == 0, r.stderr + r.stdout
    cmd = [sys.executable, "-I", SCRIPT, "m9-global", "--files", str(a), str(b), "--out",
           str(out), "--psl", str(tmp_path / "psl.dat"), "--psl-sha256", "any",
           "--private", str(tmp_path / "private"), "--mem", "512MB", "--threads", "1"]
    s = subprocess.run(cmd, capture_output=True, text=True)
    assert s.returncode == 0, s.stderr
    g = {(x["class"], x["subclass"]): x for x in measure.read_tsv(out / "m9.global.tsv")}
    assert g[("local_host", "local_suffix")]["distinct_values_all_files"] == "1"
    assert g[("local_host", "local_suffix")]["token_rows"] == "10"
    c = {(x["class"], x["subclass"]): x for x in measure.read_tsv(out / "m9.classes.tsv")}
    assert c[("local_host", "local_suffix")]["sum_of_per_project_distinct_values"] == "2"


# ------------------------------------------------------------------ run mechanics

def test_resume_skips_done_projects(tmp_path):
    f = tmp_path / "p-dataset.parquet"
    write_parquet(f, unit("a.c"))
    r1, out = run(tmp_path, [f])
    assert r1.returncode == 0, r1.stderr + r1.stdout
    assert "1 to do" in r1.stdout
    r2, _ = run(tmp_path, [f])
    assert r2.returncode == 0
    assert "1 done before, 0 to do" in r2.stdout
    os.unlink(out / "done" / "p.m7")
    r3, _ = run(tmp_path, [f])
    assert "1 to do" in r3.stdout
    assert "groups m7" in r3.stdout or "m4m10,m7,m9" in r3.stdout


def test_manifest_root_and_size_check(tmp_path):
    root = tmp_path / "root"
    (root / "parquet").mkdir(parents=True)
    write_parquet(root / "parquet" / "p-dataset.parquet", unit("a.c"))
    write_parquet(root / "parquet" / "q-dataset.parquet", unit("a.c"))
    size = os.path.getsize(root / "parquet" / "p-dataset.parquet")
    (root / "MANIFEST.tsv").write_text(
        "project\tbytes\tpath\n"
        f"p\t{size}\tparquet/p-dataset.parquet\n"
        f"q\t1\tparquet/q-dataset.parquet\n")
    psl = tmp_path / "psl.dat"
    psl.write_text(PSL_TEXT)
    out = tmp_path / "out"
    cmd = [sys.executable, "-I", SCRIPT, "run", str(root), "--out", str(out), "--psl", str(psl),
           "--psl-sha256", "any", "--jobs", "1", "--threads", "1", "--mem-per-job", "0.5",
           "--mem-reserve", "0", "--private", str(tmp_path / "private")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    assert r.returncode == 1                       # q has the wrong size
    assert (out / "done" / "p.m9").exists()
    assert not (out / "done" / "q.m9").exists()
    assert "differs from MANIFEST bytes" in (out / "errors.tsv").read_text()


def test_at_sign_in_path_is_encoded_and_check(tmp_path):
    f = tmp_path / "p-dataset.parquet"
    rows = [r for r in unit("lib/" + AT + "scope/a.c") if r[2] != "end_unit"]
    write_parquet(f, rows)
    r, out = run(tmp_path, [f])
    assert r.returncode == 0, r.stderr + r.stdout
    got = files_rows(out, "m4", "p")
    assert got[0]["file_path"] == "lib/%40scope/a.c"
    assert measure.check_no_at(str(out), str(tmp_path / "private")) == 0
    (out / "planted.txt").write_text("x" + AT + "y")
    assert measure.check_no_at(str(out), str(tmp_path / "private")) == 1


def test_psl_reader_reads_the_icann_section_only(tmp_path):
    p = tmp_path / "psl.dat"
    p.write_text(PSL_TEXT)
    psl = measure.load_psl(str(p))
    assert psl["rules"] == ["co.uk", "com", "uk"]
    assert psl["wild"] == ["ck"] and psl["exc"] == ["www.ck"]
    assert "blogspot.com" not in psl["rules"]
    assert psl["tlds"] == ["ck", "com", "uk"]


def test_enc_escapes_tsv_breakers_and_the_at_sign():
    assert measure.enc("a" + TAB + "b" + chr(10) + AT + "%") == "a%09b%0A%40%25"
