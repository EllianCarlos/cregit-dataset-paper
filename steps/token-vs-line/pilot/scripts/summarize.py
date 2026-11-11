"""Make the Markdown result tables from ../tables/per-project.tsv.

    python3 -I summarize.py > ../tables/results.md
"""
import csv
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MEDIUM = {"DK22Pac__plugin-sdk", "Adyen__adyen-java-api-library", "github__copilot-sdk",
          "influxdata__influxdb-client-java"}


def load():
    rows = list(csv.DictReader(open(HERE / "tables" / "per-project.tsv"), delimiter="\t"))
    for r in rows:
        for k, v in list(r.items()):
            try:
                r[k] = float(v)
            except ValueError:
                pass
    return rows


def pct(a, b):
    return 100.0 * a / b if b else float("nan")


def f1(x):
    return "n/a" if x != x else f"{x:.1f}"


def f2(x):
    return "n/a" if x != x else f"{x:.2f}"


def main_lang(r):
    parts = [x for x in r["lang"].split(",") if not x.startswith("C/C++ header")] or r["lang"].split(",")
    best = max(parts, key=lambda s: int(s.rsplit(":", 1)[1]))
    return best.rsplit(":", 1)[0]


def table(head, body):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in b) + " |" for b in body]
    return "\n".join(out)


def pooled_and_median(rows, cols, fn):
    """cols: list of (num_key, den_key). Pooled = sums; median of the project values."""
    pooled = [pct(sum(r[n] for r in rows), sum(r[d] for r in rows)) for n, d in cols]
    med = [st.median(pct(r[n], r[d]) for r in rows) for n, d in cols]
    return [fn(x) for x in pooled], [fn(x) for x in med]


def main():
    rows = load()
    rows.sort(key=lambda r: (main_lang(r), r["tokens"]))
    small = [r for r in rows if r["project"] not in MEDIUM]
    man = {}
    for line in open("/path/to/pilot-scratch/hf-tom/MANIFEST.tsv"):
        f = line.rstrip("\n").split("\t")
        man[f[0]] = f
    print("## Sample\n")
    body = []
    for r in rows:
        parts = [x.rsplit(":", 1) for x in r["lang"].split(",")]
        tot = sum(int(n) for _, n in parts)
        mix = ", ".join(f"{k} {100 * int(n) / tot:.0f}%" for k, n in parts if 100 * int(n) / tot >= 1)
        m = man[r["project"]]
        body.append([r["project"], mix, f"{int(m[3]):,}", m[2], int(r["files"]), f"{int(r['tokens']):,}",
                     f"{int(r['lines']):,}", int(r["files_generated"]),
                     f1(pct(r["tok_generated"], r["tok_matched"]))])
    body.append(["**total**", "", "", "", int(sum(r["files"] for r in rows)), f"{int(sum(r['tokens'] for r in rows)):,}",
                 f"{int(sum(r['lines'] for r in rows)):,}", int(sum(r["files_generated"] for r in rows)),
                 f1(pct(sum(r["tok_generated"] for r in rows), sum(r["tok_matched"] for r in rows)))])
    print(table(["project", "file languages (share of tokens)", "commits", "size class", "files", "TOM tokens",
                 "source lines", "generated files", "tokens in generated files %"], body) + "\n")
    print("## Level 1: tokens\n")
    cols = [("tok_author_diff", "tok_matched"), ("tok_author_diff_wmc", "tok_matched"),
            ("tok_author_diff_tp", "tok_matched"), ("tok_commit_diff", "tok_matched"),
            ("tok_commit_diff_wmc", "tok_matched"), ("tok_firm_diff", "tok_matched"),
            ("tok_firm_diff_wmc", "tok_matched")]
    head = ["project", "main language", "files", "tokens", "author: line plain", "author: line -w -M -C",
            "author: token plain", "commit: line plain", "commit: line -w -M -C",
            "organization: line plain", "organization: line -w -M -C"]
    body = [[r["project"], main_lang(r), int(r["files"]), f"{int(r['tokens']):,}"]
            + [f1(pct(r[n], r[d])) for n, d in cols] for r in rows]
    p, m = pooled_and_median(rows, cols, f1)
    body.append(["**pooled (all tokens)**", "", int(sum(r["files"] for r in rows)),
                 f"{int(sum(r['tokens'] for r in rows)):,}"] + p)
    body.append(["**median of projects**", "", "", ""] + m)
    p, m = pooled_and_median(small, cols, f1)
    body.append(["pooled, small projects only", "", "", ""] + p)
    ng_d = sum(r["tok_author_diff"] - r["tok_author_diff_generated"] for r in rows)
    ng_n = sum(r["tok_matched"] - r["tok_generated"] for r in rows)
    g_d = sum(r["tok_author_diff_generated"] for r in rows)
    g_n = sum(r["tok_generated"] for r in rows)
    print("Percent of tokens whose line-method value is not the TOM value. "
          f"Author, line plain, pooled: {f1(pct(ng_d, ng_n))}% in files that are not generated "
          f"({ng_n:,.0f} tokens), {f1(pct(g_d, g_n))}% in generated files ({g_n:,.0f} tokens).\n")
    print(table(head, body) + "\n")

    print("## Level 2: lines with tokens from more than one author\n")
    head = ["project", "code lines", "mixed-author lines %", "tokens in mixed lines %",
            "line author wrote part %", "line author wrote none %", "line author token share %",
            "mixed-commit lines %", "line commit wrote part %"]
    body = []
    for r in rows:
        body.append([r["project"], f"{int(r['code_lines']):,}",
                     f1(pct(r["mixed_author_lines"], r["code_lines"])),
                     f1(pct(r["mixed_author_line_tokens"], r["tok_matched"])),
                     f1(pct(r["mixed_lp_wrote_part"], r["mixed_author_lines"])),
                     f1(pct(r["mixed_lp_wrote_none"], r["mixed_author_lines"])),
                     f1(100 * r["mixed_lp_token_share"]) if r["mixed_lp_token_share"] == r["mixed_lp_token_share"] else "n/a",
                     f1(pct(r["mixed_commit_lines"], r["code_lines"])),
                     f1(pct(r["mixedc_ls_part"], r["mixed_commit_lines"]))])
    s = lambda k: sum(r[k] for r in rows)  # noqa: E731
    wshare = sum(r["mixed_lp_token_share"] * r["mixed_author_lines"] for r in rows
                 if r["mixed_author_lines"]) / s("mixed_author_lines")
    body.append(["**pooled**", f"{int(s('code_lines')):,}", f1(pct(s("mixed_author_lines"), s("code_lines"))),
                 f1(pct(s("mixed_author_line_tokens"), s("tok_matched"))),
                 f1(pct(s("mixed_lp_wrote_part"), s("mixed_author_lines"))),
                 f1(pct(s("mixed_lp_wrote_none"), s("mixed_author_lines"))), f1(100 * wshare),
                 f1(pct(s("mixed_commit_lines"), s("code_lines"))),
                 f1(pct(s("mixedc_ls_part"), s("mixed_commit_lines")))])
    print("A code line is a source line on which at least one TOM token starts. "
          "\"Line author\" is the author that plain line blame gives to the line. "
          "\"Token share\" is the mean share of the tokens of a mixed line that the line author wrote in TOM. "
          f"With -w -M -C: line author wrote part of {f1(pct(s('mixed_lp_wrote_part_wmc'), s('mixed_author_lines_wmc')))}% of the mixed lines.\n")
    print(table(head, body) + "\n")

    print("## Level 3: top author of each file\n")
    head = ["project", "files", "top 1 same %", "top 3 set same %", "files with 2+ authors",
            "top 1 same % (2+ authors)", "top 3 same % (2+ authors)", "top 1 same % (-w -M -C)",
            "top 3 same % (-w -M -C)", "files with a tie"]
    body = []
    for r in rows:
        body.append([r["project"], int(r["files_cmp"]), f1(pct(r["file_top1_same"], r["files_cmp"])),
                     f1(pct(r["file_top3_same"], r["files_cmp"])), int(r["files_multi"]),
                     f1(pct(r["file_top1_same_multi"], r["files_multi"])),
                     f1(pct(r["file_top3_same_multi"], r["files_multi"])),
                     f1(pct(r["file_top1_same_wmc"], r["files_cmp_wmc"])),
                     f1(pct(r["file_top3_same_wmc"], r["files_cmp_wmc"])), int(r["file_ties"])])
    body.append(["**pooled**", int(s("files_cmp")), f1(pct(s("file_top1_same"), s("files_cmp"))),
                 f1(pct(s("file_top3_same"), s("files_cmp"))), int(s("files_multi")),
                 f1(pct(s("file_top1_same_multi"), s("files_multi"))),
                 f1(pct(s("file_top3_same_multi"), s("files_multi"))),
                 f1(pct(s("file_top1_same_wmc"), s("files_cmp_wmc"))),
                 f1(pct(s("file_top3_same_wmc"), s("files_cmp_wmc"))), int(s("file_ties"))])
    md = lambda k, d: f1(st.median(pct(r[k], r[d]) for r in rows))  # noqa: E731
    body.append(["**median of projects**", "", md("file_top1_same", "files_cmp"), md("file_top3_same", "files_cmp"),
                 "", md("file_top1_same_multi", "files_multi"), md("file_top3_same_multi", "files_multi"),
                 md("file_top1_same_wmc", "files_cmp_wmc"), md("file_top3_same_wmc", "files_cmp_wmc"), ""])
    print("Token method: the author with the most TOM tokens in the file. Line method: the author with the "
          "most blamed lines (all lines, blank lines too). Ties go to the lower hashed id on both sides.\n")
    print(table(head, body) + "\n")

    print("## Level 4: project shares\n")
    for name in ("author", "firm"):
        label = "authors" if name == "author" else "organizations (firm_based_on_domain)"
        head = ["project", "n", "MAD pp", "MAD pp (share >= 1%)", "max pp", "TVD pp", "Spearman",
                "top same", "top share tokens %", "top share lines %", "Spearman -w -M -C", "TVD pp -w -M -C",
                "TVD pp non-blank"]
        body = []
        for r in rows:
            g = lambda k, v="": r[f"{name}_{k}{v}"]  # noqa: E731
            body.append([r["project"], int(g("n")), f2(g("mad_pp")), f2(g("mad_pp_ge1")), f1(g("max_pp")),
                         f1(g("tvd_pp")), f2(g("spearman")), "yes" if g("top_same") else "**no**",
                         f1(g("top_tok_pct")), f1(g("top_line_pct")), f2(g("spearman", "_wmc")),
                         f1(g("tvd_pp", "_wmc")), f1(g("tvd_pp", "_nonblank"))])
        vals = lambda k: [r[f"{name}_{k}"] for r in rows if r[f"{name}_{k}"] == r[f"{name}_{k}"]]  # noqa: E731
        body.append(["**mean of projects**", f1(st.mean(vals("n"))), f2(st.mean(vals("mad_pp"))),
                     f2(st.mean(vals("mad_pp_ge1"))), f1(st.mean(vals("max_pp"))), f1(st.mean(vals("tvd_pp"))),
                     f2(st.mean(vals("spearman"))), f"{int(sum(vals('top_same')))} of {len(rows)}",
                     "", "", f2(st.mean(vals("spearman_wmc"))), f1(st.mean(vals("tvd_pp_wmc"))),
                     f1(st.mean(vals("tvd_pp_nonblank")))])
        body.append(["**median of projects**", f1(st.median(vals("n"))), f2(st.median(vals("mad_pp"))),
                     f2(st.median(vals("mad_pp_ge1"))), f1(st.median(vals("max_pp"))),
                     f1(st.median(vals("tvd_pp"))), f2(st.median(vals("spearman"))), "", "", "",
                     f2(st.median(vals("spearman_wmc"))), f1(st.median(vals("tvd_pp_wmc"))),
                     f1(st.median(vals("tvd_pp_nonblank")))])
        print(f"### {label}\n")
        print("Shares in percent of the project: TOM tokens against blamed lines (line plain). "
              "MAD = mean absolute difference over all keys of either side; TVD = half the sum of the "
              "absolute differences (the part of the project that changes owner).\n")
        print(table(head, body) + "\n")

    print("## Level 5: causes\n")
    causes = ["whitespace", "move_copy_line", "move_copy_token", "part_line", "layout", "other"]
    head = ["project", "tokens with another author"] + [f"{c} %" for c in causes] + ["in generated files %"]
    body = []
    for r in rows:
        tot = sum(r[f"cause_{c}"] for c in causes)
        gen = sum(r[f"cause_{c}_gen"] for c in causes)
        body.append([r["project"], f"{int(tot):,}"] + [f1(pct(r[f"cause_{c}"], tot)) for c in causes]
                    + [f1(pct(gen, tot))])
    tot = sum(s(f"cause_{c}") for c in causes)
    gen = sum(s(f"cause_{c}_gen") for c in causes)
    body.append(["**pooled**", f"{int(tot):,}"] + [f1(pct(s(f"cause_{c}"), tot)) for c in causes]
                + [f1(pct(gen, tot))])
    tot_s = sum(sum(r[f"cause_{c}"] for c in causes) for r in small)
    body.append(["pooled, small projects only", f"{int(tot_s):,}"]
                + [f1(pct(sum(r[f"cause_{c}"] for r in small), tot_s)) for c in causes]
                + [f1(pct(sum(sum(r[f"cause_{c}_gen"] for c in causes) for r in small), tot_s))])
    print(table(head, body) + "\n")
    print("Generated files: " + ", ".join(
        f"{r['project']} {int(r['files_generated'])} files, {f1(pct(r['tok_generated'], r['tok_matched']))}% of tokens, "
        f"author diff {f1(pct(r['tok_author_diff_generated'], r['tok_generated']))}%"
        for r in rows if r["files_generated"]) + "\n")

    print("## Checks\n")
    print(table(["project", "tokens without a line", "TOM ids = person-db ids", "persons-db misses",
                 "-C100 check (equal / checked)", "line firm not from TOM %", "line firm unknown %"],
                [[r["project"], int(r["tokens_unmatched"]),
                  "yes" if r["id_pairs"] == r["id_tom"] == r["id_canon"] else "**no**", int(r["persons_db_miss"]),
                  f"{int(r['c100_equal'])} / {int(r['c100_checked'])}" if r["c100_checked"] else "not run",
                  f2(pct(r["lines_firm_fallback"], r["lines"])), f2(pct(r["lines_firm_unknown"], r["lines"]))]
                 for r in rows]) + "\n")

    lang = list(csv.DictReader(open(HERE / "tables" / "per-language.tsv"), delimiter="\t"))
    agg = {}
    for x in lang:
        a = agg.setdefault(x["lang"], [0, 0, 0, 0, set()])
        a[0] += int(x["tokens"])
        a[1] += int(x["author_diff"])
        a[2] += int(x["author_diff_wmc"])
        a[3] += int(x["commit_diff"])
        if int(x["tokens"]) >= 1000:
            a[4].add(x["project"])
    print("## Level 1 by file language (file extension, pooled)\n")
    print(table(["language", "projects (1,000+ tokens)", "tokens", "author: line plain %", "author: line -w -M -C %",
                 "commit: line plain %"],
                [[k, len(v[4]), f"{v[0]:,}", f1(pct(v[1], v[0])), f1(pct(v[2], v[0])), f1(pct(v[3], v[0]))]
                 for k, v in sorted(agg.items(), key=lambda kv: -kv[1][0])]) + "\n")


if __name__ == "__main__":
    main()
