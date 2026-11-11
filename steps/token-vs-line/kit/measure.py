"""Compare line authorship (git blame by lines) with token authorship (TOM).

Reads, per project: the TOM file, the line blames of blame_lines.py (and, if it
exists, the token plain blame of blame_tokens.py), the pinned clone (for the
author e-mail of each commit) and the domain table of the release. Writes one row
per project and the language and example tables.

Identity (the same function on both sides): a commit that TOM credits gets its
TOM personid. Another commit gets the personid that TOM gives to its author
e-mail address: the map from e-mail address to personid comes from the commits
that TOM credits (git author e-mail of the commit -> TOM personid). An e-mail
address that no TOM commit has gets its own id. The map and the e-mail addresses
stay in the memory of this process; no table, file or log gets them. The tables
keep a hash of the id only, and the outputs keep counts and commit ids only.

Organization: firm_based_on_domain. A commit that TOM credits gets its TOM value.
Another commit gets the main TOM value of the same person, else the value of the
release domain table for its e-mail domain, else "unknown".

Files over a blame limit (limits.tsv of blame_lines.py): each blame uses the lines
that it has. The row gives the tokens in files over a limit for each blame.

    nice -n 19 python3 -I measure.py                       # the 19 projects of ../sample.tsv
    nice -n 19 python3 -I measure.py --only tio__tio
    nice -n 19 python3 -I measure.py --only P --repo P.git --commit SHA --tom P-dataset.parquet \
        --work-dir work/P --domains organization_domains.parquet --out-dir out/P
"""
import argparse
import collections
import hashlib
import math
import secrets
import subprocess
import sys
from pathlib import Path

import duckdb

SCRATCH = Path("/path/to/pilot-scratch")
DOMAINS = Path("/path/to/host"
               "links-final/domain_links.parquet")
HERE = Path(__file__).resolve().parent.parent
SALT = "line-vs-token-20261109:"
# ids of authors with no TOM personid: a random key of this process, so their hash cannot be
# recomputed from a guessed e-mail address
_KEY = secrets.token_hex(16)
EXT = {".c": "C", ".h": "C/C++ header", ".cc": "C++", ".cpp": "C++", ".cxx": "C++",
       ".hpp": "C++", ".hh": "C++", ".hxx": "C++", ".java": "Java", ".rs": "Rust"}


def h(x):
    return hashlib.sha256((SALT + x).encode()).hexdigest()[:12]


def h_unmapped(email):
    return "u" + hashlib.sha256((_KEY + email).encode()).hexdigest()[:11]


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman(a, b):
    if len(a) < 3:
        return float("nan")
    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else float("nan")


def share_stats(rows):
    """rows: (key, token_count, line_count). Shares over the union of keys."""
    if not rows:
        return {k: float("nan") for k in ("n", "mad_pp", "mad_pp_ge1", "max_pp", "tvd_pp", "spearman",
                                          "top_same", "top_tok_pct", "top_line_pct")}
    tt = sum(r[1] for r in rows) or 1
    tl = sum(r[2] for r in rows) or 1
    a = [100.0 * r[1] / tt for r in rows]
    b = [100.0 * r[2] / tl for r in rows]
    d = [abs(x - y) for x, y in zip(a, b)]
    top_t = max(rows, key=lambda r: (r[1], r[0]))[0]
    top_l = max(rows, key=lambda r: (r[2], r[0]))[0]
    big = [i for i in range(len(rows)) if max(a[i], b[i]) >= 1.0]
    return {
        "n": len(rows),
        "mad_pp": sum(d) / len(d),
        "mad_pp_ge1": sum(d[i] for i in big) / len(big) if big else float("nan"),
        "max_pp": max(d),
        "tvd_pp": sum(d) / 2,
        "spearman": spearman(a, b),
        "top_same": int(top_t == top_l),
        "top_tok_pct": max(a),
        "top_line_pct": max(b),
    }


def git_authors(repo, commit):
    """(sha, lower-case author e-mail) of each commit reachable from the pinned commit. Memory only."""
    r = subprocess.run(["git", "-C", str(repo), "log", "--format=%H%x1f%ae", commit],
                       capture_output=True, check=True)
    out = []
    for ln in r.stdout.split(b"\n"):
        if b"\x1f" in ln:
            sha, e = ln.split(b"\x1f", 1)
            out.append((sha.decode(), e.decode("utf-8", "replace").strip().lower()))
    return out


def commits_table(con, repo, commit, tom):
    """Rows (sha, id hash, e-mail domain, id source) for all commits. Returns rows and counts."""
    credited = {s: (pid, n) for s, pid, n in con.execute(
        "SELECT original_commit_sha, min(personid), count(DISTINCT personid) FROM read_parquet(?) "
        "WHERE original_commit_sha IS NOT NULL GROUP BY 1", [str(tom)]).fetchall()}
    # a credited commit with no personid (TOM leaves it empty) has no TOM identity: it takes the
    # e-mail path below, like a commit that TOM does not credit
    nopid = {s for s, v in credited.items() if v[0] is None}
    log = git_authors(repo, commit)
    by_email = collections.defaultdict(collections.Counter)
    for sha, e in log:
        if sha in credited and sha not in nopid:
            by_email[e][credited[sha][0]] += 1
    email_map = {e: min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0] for e, c in by_email.items()}
    counts = {"commits_log": len(log), "commits_tom": len(credited),
              "commits_tom_not_in_log": len(set(credited) - {s for s, _ in log}),
              "commits_tom_null_personid": len(nopid),
              "commits_multi_personid": sum(1 for v in credited.values() if v[1] > 1),
              "emails_multi_personid": sum(1 for c in by_email.values() if len(c) > 1)}
    rows = []
    for sha, e in log:
        dom = e.rsplit("@", 1)[-1] if "@" in e else ""
        if sha in credited and sha not in nopid:
            rows.append((sha, h(credited[sha][0]), dom, "tom"))
        elif e in email_map:
            rows.append((sha, h(email_map[e]), dom, "email"))
        else:
            rows.append((sha, h_unmapped(e), dom, "none"))
    del log, by_email, email_map
    return rows, counts


def read_tsv(path):
    return f"read_csv('{path}', delim='\t', header=true, quote='', escape='', all_varchar=true)"


def measure(con, p, repo, commit, tom, work, domains):
    work = Path(work)
    rows, idc = commits_table(con, repo, commit, tom)
    con.execute("CREATE OR REPLACE TABLE c (sha VARCHAR, pid VARCHAR, dom VARCHAR, src VARCHAR)")
    con.executemany("INSERT INTO c VALUES (?, ?, ?, ?)", rows)
    del rows
    con.execute(f"""CREATE OR REPLACE TABLE t AS
        SELECT file_path f, token_index ti, source_line l, original_commit_sha sha_t,
               coalesce(firm_based_on_domain, '(none)') firm_t, personid tom_pid
        FROM read_parquet('{tom}') WHERE is_structural = 0""")
    con.execute(f"""CREATE OR REPLACE TABLE b AS
        SELECT file_path f, line::BIGINT l, sha_plain, sha_w, sha_wmc, orig_file_wmc, blank::INT blank
        FROM {read_tsv(work / 'blame.tsv.gz')}""")
    tp_avail = (work / "tokblame.tsv.gz").exists()
    if tp_avail:
        con.execute(f"""CREATE OR REPLACE TABLE tb AS
            SELECT file_path f, token_index::BIGINT ti, sha_tp, nullif(sha_c100, '') sha_c100
            FROM {read_tsv(work / 'tokblame.tsv.gz')}""")
    else:
        con.execute("CREATE OR REPLACE TABLE tb (f VARCHAR, ti BIGINT, sha_tp VARCHAR, sha_c100 VARCHAR)")
    con.execute(f"""CREATE OR REPLACE TABLE gen AS
        SELECT file_path f, generated FROM {read_tsv(work / 'files.tsv')}""")
    if (work / "limits.tsv").exists():
        con.execute(f"CREATE OR REPLACE TABLE lim AS SELECT DISTINCT file_path f, blame FROM {read_tsv(work / 'limits.tsv')}")
    else:
        con.execute("CREATE OR REPLACE TABLE lim (f VARCHAR, blame VARCHAR)")
    dcols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{domains}')").fetchall()]
    dval = "firm_based_on_domain" if "firm_based_on_domain" in dcols else "organization_id"
    # firm per commit: TOM value; else the person's main TOM value; else domain table
    con.execute(f"""CREATE OR REPLACE TABLE cc AS
        WITH cf AS (SELECT sha_t sha, min(firm_t) firm, count(DISTINCT firm_t) nf
                    FROM t GROUP BY 1),
             pf AS (SELECT c.pid, arg_max(firm_t, n) firm FROM
                    (SELECT sha_t, firm_t, count(*) n FROM t GROUP BY 1, 2) x
                    JOIN c ON c.sha = x.sha_t GROUP BY 1),
             dl AS (SELECT domain, min({dval}) firm FROM read_parquet('{domains}') GROUP BY 1)
        SELECT c.sha, c.pid, c.src, coalesce(cf.firm, pf.firm, dl.firm, 'unknown') firm,
               CASE WHEN cf.firm IS NOT NULL THEN 'tom' WHEN pf.firm IS NOT NULL THEN 'person'
                    WHEN dl.firm IS NOT NULL THEN 'domain' ELSE 'unknown' END firm_src,
               coalesce(cf.nf, 0) nf
        FROM c LEFT JOIN cf ON cf.sha = c.sha LEFT JOIN pf ON pf.pid = c.pid
               LEFT JOIN dl ON dl.domain = c.dom""")
    con.execute("""CREATE OR REPLACE TABLE j AS
        SELECT t.f, t.ti, t.l, t.sha_t, ct.pid pid_t, t.firm_t, t.tom_pid,
               b.sha_plain, b.sha_w, b.sha_wmc, b.orig_file_wmc,
               cp.pid p_plain, cw.pid p_w, cm.pid p_wmc, cp.firm firm_plain, cm.firm firm_wmc,
               cp.src src_plain, tb.sha_tp, tb.sha_c100, ctp.pid p_tp, ctp.firm firm_tp
        FROM t LEFT JOIN cc ct ON ct.sha = t.sha_t
               LEFT JOIN tb ON tb.f = t.f AND tb.ti = t.ti
               LEFT JOIN cc ctp ON ctp.sha = tb.sha_tp
               LEFT JOIN b ON b.f = t.f AND b.l = t.l
               LEFT JOIN cc cp ON cp.sha = b.sha_plain
               LEFT JOIN cc cw ON cw.sha = b.sha_w
               LEFT JOIN cc cm ON cm.sha = b.sha_wmc""")
    out = {"project": p}
    q = con.execute
    out["commits_id_unmapped"] = q("SELECT count(*) FROM c WHERE src = 'none'").fetchone()[0]
    out["firm_multi_per_commit"] = q("SELECT count(*) FROM cc WHERE nf > 1").fetchone()[0]
    out["id_pairs"], out["id_tom"], out["id_canon"] = q(
        "SELECT count(DISTINCT (tom_pid, pid_t)), count(DISTINCT tom_pid), count(DISTINCT pid_t) "
        "FROM j").fetchone()
    (out["files"], out["tokens"], out["tokens_unmatched"], out["lines"], out["lines_nonblank"]) = q(
        """SELECT (SELECT count(DISTINCT f) FROM t), count(*), count(*) FILTER (sha_plain IS NULL),
                  (SELECT count(*) FROM b), (SELECT count(*) FROM b WHERE blank = 0) FROM j""").fetchone()
    out["wmc_missing_lines"] = q("SELECT count(*) FROM b WHERE sha_wmc IS NULL").fetchone()[0]
    langs = {}
    for f, n in q("SELECT f, count(*) FROM t GROUP BY 1").fetchall():
        ext = "." + f.rsplit(".", 1)[-1].lower() if "." in f else ""
        langs[EXT.get(ext, "other")] = langs.get(EXT.get(ext, "other"), 0) + n
    out["lang"] = ",".join(f"{k}:{v}" for k, v in sorted(langs.items(), key=lambda x: -x[1]))

    # Level 1: tokens (each blame over the tokens whose line it blamed)
    r = q("""SELECT count(*) FILTER (p_plain <> pid_t), count(*) FILTER (sha_plain <> sha_t),
                    count(*) FILTER (firm_plain <> firm_t),
                    count(*) FILTER (p_wmc <> pid_t), count(*) FILTER (sha_wmc <> sha_t),
                    count(*) FILTER (firm_wmc <> firm_t),
                    count(*) FILTER (p_w <> pid_t), count(*) FILTER (sha_w <> sha_t)
             FROM j""").fetchone()
    (out["tok_author_diff"], out["tok_commit_diff"], out["tok_firm_diff"],
     out["tok_author_diff_wmc"], out["tok_commit_diff_wmc"], out["tok_firm_diff_wmc"],
     out["tok_author_diff_w"], out["tok_commit_diff_w"]) = r
    out["tok_matched"] = out["tokens"] - out["tokens_unmatched"]
    (out["tok_author_diff_tp"], out["tok_commit_diff_tp"], out["tok_firm_diff_tp"], out["tp_missing"],
     out["c100_checked"], out["c100_equal"]) = q(
        """SELECT count(*) FILTER (p_tp <> pid_t), count(*) FILTER (sha_tp <> sha_t),
                  count(*) FILTER (firm_tp <> firm_t), count(*) FILTER (sha_tp IS NULL),
                  count(*) FILTER (sha_c100 IS NOT NULL), count(*) FILTER (sha_c100 = sha_t) FROM j""").fetchone()
    gen_r = q("""SELECT count(*), count(*) FILTER (p_plain <> pid_t) FROM j JOIN gen USING (f)
                 WHERE generated IS NOT NULL AND sha_plain IS NOT NULL""").fetchone()
    out["tok_generated"], out["tok_author_diff_generated"] = gen_r
    out["files_generated"] = q("SELECT count(*) FROM gen WHERE generated IS NOT NULL").fetchone()[0]

    lang_sql = ("CASE lower(regexp_extract(f, '\\.([^./]+)$', 1)) WHEN 'c' THEN 'C' WHEN 'h' THEN 'C/C++ header' "
                "WHEN 'java' THEN 'Java' WHEN 'rs' THEN 'Rust' WHEN 'cc' THEN 'C++' WHEN 'cpp' THEN 'C++' "
                "WHEN 'cxx' THEN 'C++' WHEN 'hpp' THEN 'C++' WHEN 'hh' THEN 'C++' WHEN 'hxx' THEN 'C++' "
                "ELSE 'other' END")
    langrows = q(f"""SELECT {lang_sql} lang, count(*), count(*) FILTER (p_plain <> pid_t),
                            count(*) FILTER (p_wmc <> pid_t), count(*) FILTER (sha_plain <> sha_t)
                     FROM j WHERE sha_plain IS NOT NULL GROUP BY 1""").fetchall()

    # Level 2: lines with tokens from more than one author / commit
    for v, ps, ss in (("", "p_plain", "sha_plain"), ("_wmc", "p_wmc", "sha_wmc")):
        r = q(f"""WITH lt AS (
                    SELECT f, l, count(DISTINCT pid_t) na, count(DISTINCT sha_t) nc, count(*) n,
                           count(*) FILTER (pid_t = {ps}) n_lp, bool_or(pid_t = {ps}) lp_in,
                           bool_or(sha_t = {ss}) ls_in, count(*) FILTER (sha_t = {ss}) n_ls
                    FROM j WHERE {ss} IS NOT NULL GROUP BY 1, 2)
                  SELECT count(*), count(*) FILTER (na > 1), sum(n) FILTER (na > 1),
                         count(*) FILTER (na > 1 AND lp_in), count(*) FILTER (na > 1 AND NOT lp_in),
                         avg(n_lp / n) FILTER (na > 1),
                         count(*) FILTER (nc > 1), count(*) FILTER (nc > 1 AND ls_in),
                         count(*) FILTER (nc > 1 AND NOT ls_in), avg(n_ls / n) FILTER (nc > 1),
                         count(*) FILTER (na = 1 AND NOT lp_in)
                  FROM lt""").fetchone()
        (out["code_lines" + v], out["mixed_author_lines" + v], out["mixed_author_line_tokens" + v],
         out["mixed_lp_wrote_part" + v], out["mixed_lp_wrote_none" + v], out["mixed_lp_token_share" + v],
         out["mixed_commit_lines" + v], out["mixedc_ls_part" + v], out["mixedc_ls_none" + v],
         out["mixedc_ls_token_share" + v], out["single_author_lines_other" + v]) = r

    # Level 3: top author of each file (tokens against lines)
    for v, col in (("", "sha_plain"), ("_wmc", "sha_wmc")):
        q("""CREATE OR REPLACE TABLE ft AS
             SELECT f, a, n, row_number() OVER (PARTITION BY f ORDER BY n DESC, a) rk
             FROM (SELECT f, pid_t a, count(*) n FROM j GROUP BY 1, 2)""")
        q(f"""CREATE OR REPLACE TABLE fl AS
              SELECT f, a, n, row_number() OVER (PARTITION BY f ORDER BY n DESC, a) rk
              FROM (SELECT b.f, cc.pid a, count(*) n FROM b JOIN cc ON cc.sha = b.{col}
                    WHERE b.f IN (SELECT f FROM t) GROUP BY 1, 2)""")
        r = q("""WITH t1 AS (SELECT f, a FROM ft WHERE rk = 1), l1 AS (SELECT f, a FROM fl WHERE rk = 1),
                      t3 AS (SELECT f, string_agg(a, ',' ORDER BY a) s FROM ft WHERE rk <= 3 GROUP BY 1),
                      l3 AS (SELECT f, string_agg(a, ',' ORDER BY a) s FROM fl WHERE rk <= 3 GROUP BY 1),
                      tie AS (SELECT f FROM ft WHERE rk <= 2 GROUP BY 1 HAVING count(*) = 2 AND min(n) = max(n)
                              UNION SELECT f FROM fl WHERE rk <= 2 GROUP BY 1 HAVING count(*) = 2 AND min(n) = max(n)),
                      multi AS (SELECT f FROM ft GROUP BY 1 HAVING count(*) > 1)
                 SELECT count(*), count(*) FILTER (t1.a = l1.a),
                        count(*) FILTER (t3.s = l3.s),
                        count(*) FILTER (t1.f IN (SELECT f FROM tie)),
                        count(*) FILTER (t1.f IN (SELECT f FROM multi)),
                        count(*) FILTER (t1.f IN (SELECT f FROM multi) AND t1.a = l1.a),
                        count(*) FILTER (t1.f IN (SELECT f FROM multi) AND t3.s = l3.s)
                 FROM t1 JOIN l1 USING (f) JOIN t3 USING (f) JOIN l3 USING (f)""").fetchone()
        (out["files_cmp" + v], out["file_top1_same" + v], out["file_top3_same" + v],
         out["file_ties" + v], out["files_multi" + v], out["file_top1_same_multi" + v],
         out["file_top3_same_multi" + v]) = r

    # Level 4: project shares (tokens against lines)
    def shares(tkey, lkey, col, where=""):
        return q(f"""WITH a AS (SELECT {tkey} k, count(*) n FROM j GROUP BY 1),
                         bl AS (SELECT cc.{lkey} k, count(*) n FROM b JOIN cc ON cc.sha = b.{col}
                                WHERE b.f IN (SELECT f FROM t) {where} GROUP BY 1)
                    SELECT coalesce(a.k, bl.k), coalesce(a.n, 0), coalesce(bl.n, 0)
                    FROM a FULL JOIN bl ON a.k = bl.k""").fetchall()
    for name, tk, lk in (("author", "pid_t", "pid"), ("firm", "firm_t", "firm")):
        for v, col, wh in (("", "sha_plain", ""), ("_nonblank", "sha_plain", "AND b.blank = 0"),
                           ("_wmc", "sha_wmc", "")):
            s = share_stats(shares(tk, lk, col, wh))
            for k, val in s.items():
                out[f"{name}_{k}{v}"] = val
    out["lines_firm_fallback"] = q(
        """SELECT count(*) FROM b JOIN cc ON cc.sha = b.sha_plain WHERE cc.firm_src <> 'tom'""").fetchone()[0]
    out["lines_firm_unknown"] = q(
        """SELECT count(*) FROM b JOIN cc ON cc.sha = b.sha_plain WHERE cc.firm_src = 'unknown'""").fetchone()[0]

    # Level 5: causes for tokens with another author under plain line blame.
    # Ordered rules; the first rule that holds gives the cause. Without the token plain blame
    # (tp_available = 0) the rule move_copy_token does not apply.
    q("""CREATE OR REPLACE TABLE cause AS
         WITH lt AS (SELECT f, l, list(DISTINCT pid_t) pa FROM j GROUP BY 1, 2),
              fc AS (SELECT DISTINCT f, sha_t FROM j)
         SELECT j.*, CASE
             WHEN p_w = pid_t THEN 'whitespace'
             WHEN p_wmc = pid_t THEN 'move_copy_line'
             WHEN p_tp <> pid_t THEN 'move_copy_token'
             WHEN len(lt.pa) > 1 AND list_contains(lt.pa, p_plain) THEN 'part_line'
             WHEN NOT EXISTS (SELECT 1 FROM fc WHERE fc.f = j.f AND fc.sha_t = j.sha_plain) THEN 'layout'
             ELSE 'other' END cause,
             g.generated IS NOT NULL is_gen
         FROM j JOIN lt ON lt.f = j.f AND lt.l = j.l LEFT JOIN gen g ON g.f = j.f
         WHERE p_plain <> pid_t""")
    for c, n, ng in q("SELECT cause, count(*), count(*) FILTER (is_gen) FROM cause GROUP BY 1").fetchall():
        out[f"cause_{c}"] = n
        out[f"cause_{c}_gen"] = ng
    for c in ("whitespace", "move_copy_line", "move_copy_token", "part_line", "layout", "other"):
        out.setdefault(f"cause_{c}", 0)
        out.setdefault(f"cause_{c}_gen", 0)
    ex = q("""SELECT cause, f, sha_plain, sha_t, any_value(orig_file_wmc), count(*) n, any_value(is_gen),
                     min(l)
              FROM cause GROUP BY 1, 2, 3, 4
              QUALIFY row_number() OVER (PARTITION BY cause ORDER BY n DESC, f, sha_plain) <= 3""").fetchall()

    # Added for the larger run: the matched tokens of each blame, the files over a limit, the identity
    out["tp_available"] = int(tp_avail)
    out["tok_matched_w"], out["tok_matched_wmc"] = q(
        "SELECT count(*) FILTER (sha_w IS NOT NULL), count(*) FILTER (sha_wmc IS NOT NULL) FROM j").fetchone()
    for bl in ("plain", "w", "wmc", "cap"):
        out[f"files_limit_{bl}"], out[f"tok_in_limit_{bl}"] = q(
            f"""SELECT (SELECT count(*) FROM lim WHERE blame = '{bl}'),
                       count(*) FILTER (f IN (SELECT f FROM lim WHERE blame = '{bl}')) FROM t""").fetchone()
    out["files_limit_any"], out["tok_in_limit_any"] = q(
        "SELECT (SELECT count(DISTINCT f) FROM lim), count(*) FILTER (f IN (SELECT f FROM lim)) FROM t").fetchone()
    tk = out["tokens"] or 1
    for bl in ("plain", "w", "wmc", "cap", "any"):
        out[f"pct_tok_in_limit_{bl}"] = 100.0 * out[f"tok_in_limit_{bl}"] / tk
    out.update(idc)
    (out["lines_blamed"], out["lines_commit_not_in_tom"], out["lines_id_email"],
     out["lines_id_unmapped"]) = q(
        """SELECT count(*), count(*) FILTER (cc.src <> 'tom'), count(*) FILTER (cc.src = 'email'),
                  count(*) FILTER (cc.src = 'none')
           FROM b JOIN cc ON cc.sha = b.sha_plain""").fetchone()
    out["lines_sha_not_in_log"] = q(
        "SELECT count(*) FROM b WHERE sha_plain IS NOT NULL AND sha_plain NOT IN (SELECT sha FROM c)").fetchone()[0]
    out["pct_lines_id_unmapped"] = 100.0 * out["lines_id_unmapped"] / (out["lines_blamed"] or 1)
    out["tok_line_author_unmapped"] = q("SELECT count(*) FROM j WHERE src_plain = 'none'").fetchone()[0]
    out["commit"] = commit
    return out, [(p, *e) for e in ex], [(p, *lr) for lr in langrows]


def fmt(v):
    return f"{v:.6g}" if isinstance(v, float) else str(v)


def write_tables(out_dir, res, exs, langs, tag=""):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = []
    for o in res:
        for k in o:
            if k not in keys:
                keys.append(k)
    with open(out_dir / f"per-project{tag}.tsv", "w") as f:
        f.write("\t".join(keys) + "\n")
        for o in res:
            f.write("\t".join(fmt(o.get(k, "")) for k in keys) + "\n")
    with open(out_dir / f"per-language{tag}.tsv", "w") as f:
        f.write("project\tlang\ttokens\tauthor_diff\tauthor_diff_wmc\tcommit_diff\n")
        for r in langs:
            f.write("\t".join(str(x) for x in r) + "\n")
    with open(out_dir / f"examples{tag}.tsv", "w") as f:
        f.write("project\tcause\tfile\tline_commit\ttom_commit\torig_file_wmc\ttokens\tgenerated\tfirst_line\n")
        for e in exs:
            f.write("\t".join(str(x).replace("\t", " ") for x in e) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", action="append")
    ap.add_argument("--base-dir", default=str(HERE), help="the folder with sample.tsv, work/ and tables/")
    ap.add_argument("--work-root", help="the folder with one work folder per project (default BASE/work)")
    ap.add_argument("--repo")
    ap.add_argument("--commit")
    ap.add_argument("--tom")
    ap.add_argument("--work-dir")
    ap.add_argument("--domains", default=str(DOMAINS))
    ap.add_argument("--out-dir")
    ap.add_argument("--tag")
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--memory", default="4GB")
    ap.add_argument("--temp-dir")
    a = ap.parse_args()
    base = Path(a.base_dir)
    work_root = Path(a.work_root) if a.work_root else base / "work"
    projects = a.only or [l.split("\t")[0] for l in (base / "sample.tsv").read_text().splitlines()[1:]]
    if (a.repo or a.tom or a.work_dir or a.commit) and len(projects) != 1:
        sys.exit("--repo, --tom, --work-dir and --commit need exactly one --only")
    con = duckdb.connect()
    con.execute(f"SET threads = {a.threads}; SET memory_limit = '{a.memory}'")
    con.execute(f"SET temp_directory = '{a.temp_dir or work_root / 'duckdb-tmp'}'")
    res, exs, langs = [], [], []
    for p in projects:
        work = Path(a.work_dir) if a.work_dir else work_root / p
        if not (work / "blame-meta.tsv").exists():
            print("skip (no blame)", p, file=sys.stderr)
            continue
        repo = Path(a.repo) if a.repo else SCRATCH / "out-local" / p / f"{p}-original.git"
        tom = Path(a.tom) if a.tom else SCRATCH / "hf-tom" / "parquet" / f"{p}-dataset.parquet"
        commit = a.commit or subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True,
                                            text=True, check=True).stdout.strip()
        o, e, lr = measure(con, p, repo, commit, tom, work, a.domains)
        res.append(o)
        exs.extend(e)
        langs.extend(lr)
        m = o["tok_matched"] or 1
        print(f"{p}: author diff {100 * o['tok_author_diff'] / m:.2f}%, tokens in files over a limit "
              f"{o['pct_tok_in_limit_any']:.2f}%, unmapped lines {o['pct_lines_id_unmapped']:.4f}%", file=sys.stderr)
    if not res:
        sys.exit("no project measured")
    tag = a.tag if a.tag is not None else ("-" + a.only[0] if a.only and len(a.only) == 1 and not a.out_dir else "")
    write_tables(a.out_dir or base / "tables", res, exs, langs, tag)


if __name__ == "__main__":
    main()
