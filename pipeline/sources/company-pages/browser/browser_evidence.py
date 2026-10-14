#!/usr/bin/env python3
"""Company-page evidence from the browser reads (done_websites.tsv).

A row gives evidence only if its status is ok and found_logins names a kept
org of the row's company. Output: evidence_browser.csv with the same columns
as ../evidence.csv plus method=browser.
"""
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
todo = {r["url"]: r for r in csv.DictReader(open(HERE / "todo_websites.tsv"), delimiter="\t")}
rows = []
for r in csv.DictReader(open(HERE / "done_websites.tsv"), delimiter="\t"):
    if r["status"] != "ok" or not r["found_logins"]:
        continue
    for login in r["found_logins"].split(";"):
        rows.append([login, todo[r["url"]]["company"], r["url"], r["browser_url"], r["fetched_at_utc"], "browser"])
with open(HERE / "evidence_browser.csv", "w", newline="") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["org", "company", "page_url", "final_url", "fetched_at", "method"])
    w.writerows(sorted(rows))
print(len(rows), "rows")
