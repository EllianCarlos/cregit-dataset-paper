# Spinellis et al., MSR 2020: the enterprise dataset

Source: D. Spinellis, Z. Kotti, K. Kravvaritis, G. Theodorou, P. Louridas,
"A Dataset of Enterprise-Driven Open Source Software", MSR 2020.
Zenodo record 3742962, DOI 10.5281/zenodo.3742962, version 1.1.0.0
(2020-04-21), license CC-BY-4.0.

| File | What it is |
| --- | --- |
| `enterprise-oss.tar.gz` | the record's only file, downloaded unchanged |
| `FETCH.tsv` | URL, fetch time, MD5 (matches the record) and SHA-256 |
| `zenodo-record-3742962.json` | the record metadata as the Zenodo API gave it |
| `company_links.py` | the rules that define companies, domains and org links |
| `companies.csv`, `org_links.csv` | the output of `company_links.py` |

## How the projects dataset uses it (decided 2026-10-06)

1. **Pool source.** All 17,264 rows of `enterprise_projects.txt`, with no stars
   rule. Only the S4 filters apply. The cohort file is not used.
2. **Company list.** The companies with a Fortune Global 500 or SEC 10-K/20-F
   flag. The rules of `company_links.py` decide which GitHub orgs are linked
   to a company. A kept link is a candidate. Its evidence comes in stage S5:
   a page from the company itself (strong), or a GitHub verified org with a
   website on the company domain (supporting).

The Spinellis link from a project to a company comes from the e-mail domain of
the committers, not from the ownership of the org. Their own evaluation reports
89% precision and a Cohen's kappa of 0.29. So a link is never a label by itself.

## Result of the rules (2026-10-06)

166 companies, 651 owners. 506 org links kept (150 companies), 145 not kept:

- 10 fail L1: shared projects linked to several companies (apache, kubernetes,
  kubernetes-sigs, openstack, jenkinsci, KhronosGroup, tensorflow,
  cloudfoundry-community, cloudfoundry-incubator, crosswalk-project).
- 11 fail L2: the company is on half or fewer of the owner's rows (eclipse,
  onnx, node-red, spring-cloud, stackforge, ...).
- 124 fail L3: 107 owners are User accounts, 18 owners no longer exist (one of
  them also fails L2).

Of the 506 kept orgs, 85 are verified by GitHub, 197 have a website on a
company domain, 51 have both, and 275 have neither.

**Known limit.** The list holds only companies with a Fortune Global 500 or SEC
flag, and links only orgs whose rows carry the company. So it misses company
orgs such as `JetBrains` (a private company, no SEC filings) and `linkedin`
(Microsoft is on 1 of its 21 rows, because linkedin.com is not mapped to
Microsoft). The paper must state this limit.
