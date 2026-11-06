# The sample: rule, list and bias

The sample has 36 whole project files of the release: all rows and all 71 columns of each file.
It has 45,553,409 token rows (0.14% of the 32,635,174,618 rows of the release) and 247,500,886
bytes of Parquet files. The largest file has 36,508,533 bytes.

## The rule

The rule uses the release only: `MANIFEST.tsv` (the columns `layer` and `rows`) and two project
columns of each file, `language` and `stratum` (the footer statistics of the first row group).
`select_sample.py` applies it:

```sh
python select_sample.py --root <release root>
```

1. The candidates are the project files whose `language` is C, C++, Java or Rust. `language` is
   the primary language that the host gives. The tokens of every project come from C, C++, Java
   and Rust files, but 2,456 projects have another primary language (for example Python) or none.
2. The groups. The governance label `stratum` has six values. For the four labels `company`,
   `foundation`, `personal` and `unknown`, the rule makes one group for each commit layer, each
   language and each label: 2 x 4 x 4 = 32 groups. The labels `contested` and `fiscal-sponsor`
   have few projects, so the rule makes one group for each layer and each of these labels, with
   the four languages together: 2 x 2 = 4 groups.
3. In each group, the rule sorts the files by the number of token rows, then by the project
   name. It takes the file at the position (n - 1) // 2, from 0: the lower median of the group.

The rule uses rows, not bytes. The rows do not change when a file is written again with other
Parquet settings, but the bytes change. Thus the rule gives the same projects before and after
the re-encode of the release. The script checks that each chosen file is under 100,000,000
bytes. The median gives a typical project of each group. The smallest file of a group is often a
project with almost no code tokens.

The label `personal` means that the project is in the account of a person. The release has no
label "independent project": `personal` is the nearest label.

## The list

"Group size" is the number of release files in the group of the project. "Bytes" is the size of
the sample file (the size of the release file after the re-encode).

| Project | Commit layer | Language | Label (`stratum`) | Group size | Rows | Bytes |
|---|---|---|---|---:|---:|---:|
| `NetApp__netapp-lustre` | 5,000 or more | C | company | 58 | 3,880,954 | 36,508,533 |
| `drowe67__freedv-gui` | 5,000 or more | C | fiscal-sponsor | 23 | 1,920,291 | 5,497,621 |
| `apache__axis-axis2-c-core` | 5,000 or more | C | foundation | 73 | 905,036 | 5,446,064 |
| `ghaerr__elks` | 5,000 or more | C | personal | 88 | 2,186,262 | 9,979,704 |
| `cesanta__mongoose` | 5,000 or more | C | unknown | 433 | 2,587,710 | 10,201,494 |
| `mysql__mysql-shell` | 5,000 or more | C++ | company | 45 | 2,933,605 | 15,564,969 |
| `KDE__ktexteditor` | 5,000 or more | C++ | contested | 72 | 714,638 | 4,087,122 |
| `mavlink__qgroundcontrol` | 5,000 or more | C++ | foundation | 43 | 2,107,884 | 11,907,423 |
| `dchapyshev__aspia` | 5,000 or more | C++ | personal | 135 | 1,558,590 | 7,458,900 |
| `vcmi__vcmi` | 5,000 or more | C++ | unknown | 719 | 2,347,939 | 17,125,441 |
| `google__guava` | 5,000 or more | Java | company | 68 | 4,101,399 | 19,275,838 |
| `apache__sis` | 5,000 or more | Java | foundation | 185 | 3,390,286 | 21,886,481 |
| `xipki__xipki` | 5,000 or more | Java | personal | 51 | 1,155,772 | 4,952,251 |
| `SmartBear__soapui` | 5,000 or more | Java | unknown | 443 | 1,681,008 | 7,078,706 |
| `firecracker-microvm__firecracker` | 5,000 or more | Rust | company | 5 | 723,071 | 4,641,305 |
| `Dstack-TEE__dstack` | 5,000 or more | Rust | foundation | 36 | 800,970 | 4,160,585 |
| `glommer__pgmicro` | 5,000 or more | Rust | personal | 39 | 3,141,735 | 15,864,663 |
| `fabro-sh__fabro` | 5,000 or more | Rust | unknown | 237 | 1,735,824 | 8,280,657 |
| `mozilla__nspr` | 1,000 to 4,999 | C | company | 59 | 573,744 | 2,586,551 |
| `GNOME__recipes` | 1,000 to 4,999 | C | foundation | 85 | 156,153 | 861,747 |
| `mbroz__cryptsetup` | 1,000 to 4,999 | C | personal | 384 | 497,978 | 2,981,696 |
| `emqx__neuron` | 1,000 to 4,999 | C | unknown | 585 | 450,922 | 2,413,605 |
| `awslabs__palace` | 1,000 to 4,999 | C++ | company | 92 | 747,099 | 4,034,731 |
| `KDE__plasma-integration` | 1,000 to 4,999 | C++ | contested | 265 | 61,291 | 340,227 |
| `eclipse-upm__upm` | 1,000 to 4,999 | C++ | foundation | 50 | 831,990 | 3,832,976 |
| `czyt1988__SARibbon` | 1,000 to 4,999 | C++ | personal | 497 | 471,732 | 1,816,750 |
| `xtensor-stack__xsimd` | 1,000 to 4,999 | C++ | unknown | 807 | 479,779 | 1,987,166 |
| `oracle-samples__oracle-db-examples` | 1,000 to 4,999 | Java | company | 133 | 251,121 | 942,780 |
| `opendaylight__ovsdb` | 1,000 to 4,999 | Java | foundation | 294 | 419,793 | 2,455,480 |
| `matteobaccan__owner` | 1,000 to 4,999 | Java | personal | 295 | 312,699 | 1,768,071 |
| `gitlab4j__gitlab4j-api` | 1,000 to 4,999 | Java | unknown | 713 | 356,148 | 1,902,173 |
| `Azure__kars` | 1,000 to 4,999 | Rust | company | 34 | 626,355 | 2,858,166 |
| `rwf2__Rocket` | 1,000 to 4,999 | Rust | fiscal-sponsor | 7 | 409,844 | 2,303,693 |
| `nmstate__nmstate` | 1,000 to 4,999 | Rust | foundation | 73 | 354,871 | 1,592,838 |
| `casey__just` | 1,000 to 4,999 | Rust | personal | 405 | 258,794 | 1,366,945 |
| `yeslogic__allsorts` | 1,000 to 4,999 | Rust | unknown | 767 | 420,122 | 1,537,534 |
| **Total (36 projects)** | | | | | **45,553,409** | **247,500,886** |

## The bias against the full release

The sample is not a random sample. It has the same number of projects in each group, so it
over-represents the small groups and under-represents the large ones. The tables compare the
counts and the shares of the projects and of the token rows.

### Commit layer

| Layer | Release projects | Release share | Sample projects | Sample share | Release rows share | Sample rows share |
|---|---:|---:|---:|---:|---:|---:|
| 1,000 to 4,999 commits | 7,209 | 67.0% | 18 | 50.0% | 27.4% | 16.9% |
| 5,000 or more commits | 3,545 | 33.0% | 18 | 50.0% | 72.6% | 83.1% |

### Language (the primary language of the host)

| Language | Release projects | Release share | Sample projects | Sample share | Release rows share | Sample rows share |
|---|---:|---:|---:|---:|---:|---:|
| C++ | 2,712 | 25.2% | 10 | 27.8% | 24.1% | 26.9% |
| Java | 2,199 | 20.4% | 8 | 22.2% | 19.9% | 25.6% |
| C | 1,787 | 16.6% | 9 | 25.0% | 37.6% | 28.9% |
| Rust | 1,600 | 14.9% | 9 | 25.0% | 8.0% | 18.6% |
| another language or none | 2,456 | 22.8% | 0 | 0.0% | 10.4% | 0.0% |

### Governance label (`stratum`)

| Label | Release projects | Release share | Sample projects | Sample share | Release rows share | Sample rows share |
|---|---:|---:|---:|---:|---:|---:|
| unknown | 6,076 | 56.5% | 8 | 22.2% | 56.0% | 22.1% |
| personal | 2,436 | 22.7% | 8 | 22.2% | 17.7% | 21.0% |
| foundation | 1,136 | 10.6% | 8 | 22.2% | 10.1% | 19.7% |
| company | 689 | 6.4% | 8 | 22.2% | 14.9% | 30.4% |
| contested | 365 | 3.4% | 2 | 5.6% | 0.7% | 1.7% |
| fiscal-sponsor | 52 | 0.5% | 2 | 5.6% | 0.6% | 5.1% |

### The kind of the organization that controls the account (`firm_based_on_namespace`)

The rule does not use this column. The table shows its effect.

| Kind | Release projects | Release share | Sample projects | Sample share | Release rows share | Sample rows share |
|---|---:|---:|---:|---:|---:|---:|
| project | 3,320 | 30.9% | 8 | 22.2% | 27.7% | 16.6% |
| none (NULL: no organization controls the account) | 3,130 | 29.1% | 9 | 25.0% | 18.0% | 25.3% |
| company | 2,411 | 22.4% | 12 | 33.3% | 40.1% | 43.9% |
| foundation | 1,486 | 13.8% | 7 | 19.4% | 11.5% | 14.2% |
| academic | 153 | 1.4% | 0 | 0.0% | 0.9% | 0.0% |
| consultancy | 91 | 0.8% | 0 | 0.0% | 0.4% | 0.0% |
| nonprofit | 73 | 0.7% | 0 | 0.0% | 0.4% | 0.0% |
| government | 62 | 0.6% | 0 | 0.0% | 0.8% | 0.0% |
| public-research | 28 | 0.3% | 0 | 0.0% | 0.2% | 0.0% |

### Size (token rows of a project)

| Rows | Release projects | Release share | Sample projects | Sample share | Release rows share | Sample rows share |
|---|---:|---:|---:|---:|---:|---:|
| under 100,000 | 2,008 | 18.7% | 1 | 2.8% | 0.3% | 0.1% |
| 100,000 to 999,999 | 4,982 | 46.3% | 21 | 58.3% | 6.3% | 23.6% |
| 1,000,000 to 9,999,999 | 3,252 | 30.2% | 14 | 38.9% | 29.3% | 76.2% |
| 10,000,000 to 99,999,999 | 467 | 4.3% | 0 | 0.0% | 37.7% | 0.0% |
| 100,000,000 or more | 45 | 0.4% | 0 | 0.0% | 26.4% | 0.0% |

The median project of the release has 503,239 rows; the median project of the sample has 735,085
rows. The sample has no project with 10,000,000 rows or more. In the release, these 512 projects
hold 64.1% of all rows. Thus the shares of the sample (for example the shares by organization
kind in `load.py`) do not estimate the shares of the release. Use the sample to learn the format
and to test code, not to report results.
