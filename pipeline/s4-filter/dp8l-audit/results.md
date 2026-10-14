# DP8L audit: results

Computed 2026-10-10T00:33:40+00:00 by `audit_dp8l.py report` from `raw/` (no network). Rows: the 2,898 rows that S4 removed at DP8L (`../frame_status.csv`). Method: `method.md`.

## Rows by category

| Category | Rows | of them in layer 1 (≥ 5,000 commits) |
| --- | ---: | ---: |
| A1 root license file | 58 | 3 |
| A2 root license folder (no root license file) | 544 | 77 |
| C near miss: other root name | 78 | 10 |
| D near miss: package file declares a license | 154 | 12 |
| E near miss: license file in a subfolder | 593 | 96 |
| F near miss: README names a license | 352 | 10 |
| G license files in third-party folders only | 15 | 1 |
| H no license evidence found | 892 | 18 |
| P name rule matches, but no license file | 5 | 0 |
| other host: checked in S3 | 205 | 10 |
| other host: not checked (fetch failed) | 1 | 0 |
| root tree not read (HTTP 404) | 1 | 0 |
| all | 2,898 | 237 |

## Rows that come back (A1 and A2) by run layer (DP7)

All of them passed every other S4 filter: DP8L is the last step, and each row has the first step that removes it.

| Layer (commits) | A1 root license file | A2 root license folder only | Total | of them: same head commit as an other-host row |
| --- | ---: | ---: | ---: | ---: |
| ≥ 5,000 | 3 | 77 | 80 | 0 |
| 1,000–4,999 | 26 | 232 | 258 | 0 |
| 500–999 | 8 | 103 | 111 | 0 |
| 100–499 | 12 | 98 | 110 | 0 |
| < 100 | 9 | 34 | 43 | 0 |
| all | 58 | 544 | 602 | 0 |

## Layer 1 projects that come back, in u order

`row` = the number of rows of `frame.layer1.csv` with a smaller u; `u batch` = the built or planned batch of 164 rows whose u range holds this u. These projects are in no batch now.

| # | Project | Commits | Size class | Evidence | Copy on another host | u | row | u batch |
| ---: | --- | ---: | :---: | --- | --- | ---: | ---: | ---: |
| 1 | alliedmodders/sourcemod | 7,475 | S | licenses/ (licenses/GPLv2.txt) |  | 0.000019 | 1 | 1 |
| 2 | cockpit-project/cockpit | 24,250 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.031227 | 134 | 1 |
| 3 | nymtech/nym | 11,275 | S | LICENSES/ (LICENSES/Apache-2.0.txt) |  | 0.044236 | 189 | 2 |
| 4 | KDE/k3b | 7,580 | S | LICENSES/ (LICENSES/GFDL-1.2-or-later.txt) |  | 0.048956 | 201 | 2 |
| 5 | ctt-gob-es/clienteafirma | 7,246 | S | license/ (license/EUPL v.1.1.pdf) |  | 0.059633 | 236 | 2 |
| 6 | analogdevicesinc/lnxdsp-u-boot | 85,074 | M | Licenses/ (Licenses/Exceptions) |  | 0.068658 | 262 | 2 |
| 7 | sleuthkit/autopsy | 35,955 | M | LICENSE-2.0.txt |  | 0.099071 | 369 | 3 |
| 8 | brucefan1983/GPUMD | 7,740 | S | LICENSES/ (LICENSES/GPL-3.0.txt) |  | 0.112892 | 418 | 3 |
| 9 | KDE/ktexteditor | 5,562 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.132415 | 480 | 3 |
| 10 | KDE/okular | 11,867 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.137468 | 494 | 4 |
| 11 | sleuthkit/sleuthkit | 10,795 | S | licenses/ (licenses/Apache-LICENSE-2.0.txt) |  | 0.140324 | 505 | 4 |
| 12 | matplotlib/matplotlib | 55,427 | M | LICENSE/ (LICENSE/LICENSE) |  | 0.157369 | 563 | 4 |
| 13 | Avnet/uboot-imx | 64,526 | M | Licenses/ (Licenses/Exceptions) |  | 0.167741 | 602 | 4 |
| 14 | MarvellEmbeddedProcessors/marvell-dpdk-sdk | 35,482 | M | license/ (license/README) |  | 0.168526 | 607 | 4 |
| 15 | ni/u-boot | 57,709 | M | Licenses/ (Licenses/Exceptions) |  | 0.186175 | 663 | 5 |
| 16 | KDE/labplot | 17,856 | S | LICENSES/ (LICENSES/Apache-2.0.txt) |  | 0.186638 | 665 | 5 |
| 17 | KDE/okteta | 6,773 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.190478 | 676 | 5 |
| 18 | KDE/kdepim-addons | 7,317 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.195999 | 695 | 5 |
| 19 | camunda/camunda | 117,051 | M | licenses/ (licenses/APACHE-2.0.txt) |  | 0.200840 | 716 | 5 |
| 20 | KDE/kate | 24,092 | S | LICENSES/ (LICENSES/CC0-1.0.txt) |  | 0.209836 | 745 | 5 |
| 21 | KDE/krusader | 7,551 | S | LICENSES/ (LICENSES/GFDL-1.1-or-later.txt) |  | 0.212035 | 753 | 5 |
| 22 | capstone-engine/capstone | 5,498 | S | LICENSES/ (LICENSES/LICENSE.TXT) |  | 0.256967 | 883 | 6 |
| 23 | KDE/kontact | 6,514 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.302112 | 1028 | 7 |
| 24 | KDE/kaddressbook | 7,422 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.325094 | 1099 | 7 |
| 25 | OpenRailAssociation/osrd | 16,029 | S | LICENSES/ (LICENSES/Apache-2.0.txt) |  | 0.328345 | 1111 | 7 |
| 26 | Mauler125/r5sdk | 5,471 | S | license/ (license/LICENSE) |  | 0.328709 | 1111 | 7 |
| 27 | ericpaulbishop/gargoyle | 6,359 | S | LICENSES/ (LICENSES/BSD(3-clause).txt) |  | 0.364336 | 1213 | 8 |
| 28 | cocos2d/cocos2d-x | 37,362 | M | licenses/ (licenses/LICENSE_AA-EDT.txt) |  | 0.370026 | 1231 | 8 |
| 29 | Jahia/jahia | 30,567 | M | license/ (license/apache2.txt) |  | 0.383685 | 1272 | 8 |
| 30 | NetBSD/pkgsrc | 457,576 | L | licenses/ (licenses/0-clause-bsd) |  | 0.395996 | 1316 | 9 |
| 31 | cloud-hypervisor/cloud-hypervisor | 11,734 | S | LICENSES/ (LICENSES/Apache-2.0.txt) |  | 0.397007 | 1318 | 9 |
| 32 | BroadleafCommerce/BroadleafCommerce | 18,777 | S | licenses/ (licenses/licenses.properties) |  | 0.408399 | 1351 | 9 |
| 33 | spdk/dpdk | 28,319 | S | license/ (license/README) |  | 0.421627 | 1392 | 9 |
| 34 | KDE/kalarm | 9,683 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.434669 | 1429 | 9 |
| 35 | redpanda-data/redpanda | 52,502 | M | licenses/ (licenses/README.md) |  | 0.455414 | 1496 | 10 |
| 36 | KDE/plasma-workspace | 20,408 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.464091 | 1529 | 10 |
| 37 | KDE/kwin | 31,643 | M | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.477797 | 1572 | 10 |
| 38 | KDE/kphotoalbum | 7,637 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.487823 | 1601 | 10 |
| 39 | Kode/Kore | 6,269 | S | licenses.txt |  | 0.519846 | 1707 | 11 |
| 40 | Moddable-OpenSource/moddable | 10,597 | S | licenses/ (licenses/Moddable CLA - corporate.pdf) |  | 0.527914 | 1734 | 11 |
| 41 | MarvellEmbeddedProcessors/marvell-dpdk | 43,991 | M | license/ (license/Linux-syscall-note) |  | 0.570984 | 1869 | 12 |
| 42 | KDE/latte-dock | 6,267 | S | LICENSES/ (LICENSES/CC0-1.0.txt) |  | 0.593428 | 1947 | 12 |
| 43 | libretro/Lakka-LibreELEC | 48,695 | M | licenses/ (licenses/0BSD.txt) |  | 0.599145 | 1964 | 12 |
| 44 | DPDK/dpdk | 45,593 | M | license/ (license/Linux-syscall-note) |  | 0.614302 | 2015 | 13 |
| 45 | rust-lang/rustc-perf | 6,055 | S | LICENSES/ (LICENSES/Apache-2.0.txt) |  | 0.648214 | 2140 | 14 |
| 46 | openhwfoundation/u-boot | 73,349 | M | Licenses/ (Licenses/Exceptions) |  | 0.657498 | 2169 | 14 |
| 47 | lessthanoptimal/BoofCV | 5,604 | S | LICENSE-2.0.txt |  | 0.667482 | 2202 | 14 |
| 48 | KDE/kdeplasma-addons | 11,286 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.670046 | 2212 | 14 |
| 49 | KDE/ksvg | 5,388 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.672031 | 2216 | 14 |
| 50 | KDE/ktextaddons | 7,365 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.682166 | 2241 | 14 |
| 51 | KDE/oxygen | 5,102 | S | LICENSES/ (LICENSES/CC0-1.0.txt) |  | 0.704117 | 2318 | 15 |
| 52 | KDE/kdeconnect-kde | 5,717 | S | LICENSES/ (LICENSES/Apache-2.0.txt) |  | 0.711303 | 2341 | 15 |
| 53 | clasp-developers/clasp | 15,116 | S | licenses/ (licenses/LGPL) |  | 0.723932 | 2378 | 15 |
| 54 | KDE/kio | 8,869 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.733913 | 2424 | 15 |
| 55 | analogdevicesinc/oran-u-boot | 90,111 | M | Licenses/ (Licenses/Exceptions) |  | 0.736106 | 2430 | 15 |
| 56 | HewlettPackard/gsc-uboot | 96,651 | M | Licenses/ (Licenses/Exceptions) |  | 0.736514 | 2431 | 15 |
| 57 | KDE/kleopatra | 10,140 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.772409 | 2542 | 16 |
| 58 | KDE/konversation | 9,908 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.789326 | 2588 | 16 |
| 59 | KDE/konqueror | 16,692 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.805624 | 2636 | 17 |
| 60 | qt/qtbase | 82,016 | M | LICENSES/ (LICENSES/AFL-2.1.txt) |  | 0.812447 | 2660 | 17 |
| 61 | JetBrains/kotlin | 144,645 | M | license/ (license/COPYRIGHT.txt) |  | 0.817667 | 2671 | 17 |
| 62 | UweTrottmann/SeriesGuide | 14,436 | S | LICENSES/ (LICENSES/Apache-2.0.txt) |  | 0.826549 | 2700 | 17 |
| 63 | SmileiPIC/Smilei | 11,776 | S | License/ (License/Contributors) |  | 0.849697 | 2778 | 17 |
| 64 | KDE/messagelib | 9,450 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.864352 | 2828 | 18 |
| 65 | qt-creator/qt-creator | 103,914 | M | LICENSES/ (LICENSES/LICENSE.GPL3-EXCEPT) |  | 0.864480 | 2828 | 18 |
| 66 | KDE/akonadi | 14,604 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.879783 | 2880 | 18 |
| 67 | KDE/kdepim-runtime | 17,802 | S | LICENSES/ (LICENSES/AGPL-3.0-or-later.txt) |  | 0.898179 | 2946 | 18 |
| 68 | KDE/plasma-nm | 5,090 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.912222 | 2994 | 19 |
| 69 | pioneerspacesim/pioneer | 22,340 | S | licenses/ (licenses/Apache-2.0.txt) |  | 0.916382 | 3014 | 19 |
| 70 | KDE/kio-extras | 8,724 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.921572 | 3034 | 19 |
| 71 | KDE/kmymoney | 10,773 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.928429 | 3054 | 19 |
| 72 | KDE/akregator | 7,992 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.929054 | 3054 | 19 |
| 73 | KDE/libplasma | 18,107 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.935493 | 3070 | 19 |
| 74 | KDE/kmail | 29,717 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.944181 | 3094 | 19 |
| 75 | KDE/kstars | 17,026 | S | LICENSES/ (LICENSES/Apache-2.0.txt) |  | 0.951144 | 3115 | 19 |
| 76 | KDE/korganizer | 13,899 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.954856 | 3132 | 20 |
| 77 | KDE/neochat | 7,214 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.982560 | 3221 | 20 |
| 78 | KDE/rkward | 8,237 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.991482 | 3249 | 20 |
| 79 | KDE/kirigami | 5,675 | S | LICENSES/ (LICENSES/BSD-2-Clause.txt) |  | 0.996488 | 3261 | 20 |
| 80 | KDE/discover | 11,682 | S | LICENSES/ (LICENSES/BSD-3-Clause.txt) |  | 0.999157 | 3263 | 20 |

Layer 1 by size class: S 59, M 20, L 1.
Layer 1 by u batch: 1: 2, 2: 4, 3: 3, 4: 5, 5: 7, 6: 1, 7: 4, 8: 3, 9: 5, 10: 4, 11: 2, 12: 3, 13: 1, 14: 6, 15: 6, 16: 2, 17: 5, 18: 4, 19: 8, 20: 5.

## P: the name rule matches, but the entry is not a license file

| Project | Layer | Root entries that match the prefix rule |
| --- | --- | --- |
| BBuf/Image-processing-algorithm | 100–499 | License Plate Recognition System |
| apache/incubator-kie-examples | 1,000–4,999 | licensesheader.txt |
| kobeyk/license | < 100 | license-api;license-app;license-core;license-creator;license-verify |
| demoiselle/framework | 1,000–4,999 | licence-lgpl |
| graspnet/anygrasp_sdk | < 100 | license_registration |
