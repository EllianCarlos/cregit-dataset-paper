# DP8L audit: method

Date: 2026-10-09. Script: `audit_dp8l.py`. Results: `results.md`, `results.csv`,
`returned_frame.csv`. Raw responses: `raw/`.

## 1. Question

S4 removed 2,898 rows at DP8L ("has a license file"): 28,161 rows before the
step, 25,263 rows after it (the frame). Some of these projects have a license
file. This audit finds how many, and why S4 removed them.

## 2. The rule that S4 applied

`../funnel.py` applies two different tests:

- **GitHub rows** (2,692 of the 2,898): `has_license = r["license"] != ""`. The
  column `license` in `../../s2-pool/pool.csv` is the GraphQL field
  `licenseInfo.spdxId` (`../../s2-pool/build_pool.py`, line 48). This field is
  null when GitHub's license detector does not find a license that it knows. So
  for GitHub rows the test is "GitHub detects a license", not "a license file
  exists".
- **Other-host rows** (206): `has_license = bool(license_files)`, where
  `license_files` are the top-level names from `git ls-tree --name-only` at the
  snapshot commit that match `^(licen[cs]e|copying|unlicense)`, case-insensitive
  (`../../s3-measure/clone_facts.py`). This test reads the file names. It also
  matches folder names, because `git ls-tree` lists folders too.

The text in `SELECTION-STAGES.md` describes both tests, but only the second one
tests for a license file.

## 3. Rows

The rows of `../frame_status.csv` with `excluded_because` equal to `no license
file` (2,897) or `clone facts: fetch-failed` (1, busybox, an other-host row that
S3 could not fetch). The script reads them with the pool rows in pool order.

## 4. Data collection (GitHub rows only)

All calls are read-only GET calls to the GitHub REST API, with the token of
`gh auth token`. The script makes one call at a time, waits 0.5 s after each
call, and stops until the quota reset when fewer than 1,000 calls are left in
the hour. Every URL comes from the pool row (`name_with_owner`, `head_oid`) or
from an earlier response (the `sha` of a tree entry). The script does not
construct other URLs.

| Step | Call | Rows |
| --- | --- | --- |
| 1 | `GET /repos/{nwo}/git/trees/{head_oid}` (root tree, not recursive) | all GitHub rows |
| 2 | `GET /repos/{nwo}/readme?ref={head_oid}` | rows with no root entry that matches the S3 name rule |
| 3 | `GET /repos/{nwo}/git/trees/{head_oid}?recursive=1` | the same rows |
| 4 | `GET /repos/{nwo}/git/blobs/{sha}` for the root files `Cargo.toml`, `pom.xml`, `meson.build`, `vcpkg.json`, `library.json` | the same rows |
| 5 | `GET /repos/{nwo}/git/trees/{sha}` for each root folder named `LICENSES`, `LICENSE`, `LICENCES` or `LICENCE` (any case) | rows with such a folder |

`head_oid` is the snapshot commit of the pool. The S3 measures and the census
manifests use the same commit.

Each response is one line in `raw/{step}.jsonl`: `pool_key`, `name_with_owner`,
`head_oid`, `kind`, `item`, `url`, `final_url`, `fetched_at` (UTC),
`http_status`, `x_github_request_id`, and `body` (the exact response text). The
repository keeps `raw/{step}.jsonl.xz` and `raw/SHA256SUMS` (sha256 of the plain
files). `raw/.gitattributes` has `* -text`. `fetch.log` records the progress and
each response that is not HTTP 200.

Step 3 is the exception. Its 2,084 responses are 1.3 GB, too large for the
repository. The full file `raw/tree_recursive.jsonl` stays on the work machine
(not tracked); its sha256 is in `raw/SHA256SUMS`. `audit_dp8l.py extract` writes
`raw/tree_recursive.extract.jsonl` (tracked as `.xz`): for each response, the same
metadata, the sha256 and size of the body, the `truncated` flag, the number of
entries, and the paths of the files below the root whose name matches the S3
name rule. A tree at a fixed commit does not change, so the same URL gives the
same body again, and the sha256 checks it. `report` reads only the extract.

Calls made on 2026-10-09 and 2026-10-10 (22:37 to 00:29 UTC): 2,692 root trees
(2,691 HTTP 200, 1 HTTP 404), 2,084 READMEs (1,939 HTTP 200, 145 HTTP 404: no
README), 2,084 recursive trees (all HTTP 200, 21 truncated), 527 package files,
546 license folders. The token quota went below 1,000 once; the script waited
11 minutes for the reset.

## 5. Classification (`audit_dp8l.py report`, no network)

The script gives each row the first category that applies:

| Category | Test |
| --- | --- |
| A1 root license file | a root file (blob) that matches the S3 name rule, and whose name is `LICENSE`, `LICENCE`, `LICENSES`, `UNLICENSE`, `COPYING` alone or followed by `.`, `-`, `_`, a space or a digit (for example `LICENSE-2.0.txt`, `COPYING3`), and that is not a source or build file (`.cpp`, `.java`, `.json` and others) |
| A2 root license folder | no A1 file, but a root folder named `LICENSES`, `LICENCES`, `LICENSE` or `LICENCE` that holds at least one file (the REUSE layout) |
| P name rule matches, but no license file | a root entry matches the S3 prefix rule, but it is not A1 or A2 (for example `licenseregistry.cpp`, `license-api/`) |
| C near miss: other root name | a root name with `licen`, `copying`, `copyright`, `notice`, `legal`, `patents` or `eula` in it, or a license text name such as `epl-v10.html`, `gpl-3.0.txt` |
| D near miss: package file | `Cargo.toml` has `license =` or `license-file =`; `pom.xml` has `<licenses>`; `meson.build` has `license:`; `vcpkg.json` or `library.json` has `"license":` |
| E near miss: subfolder | a file that matches the name rule below the root, not in a third-party folder (`third_party`, `vendor`, `external`, `deps`, `contrib` and others) |
| F near miss: README | a line of the README has `licen` or `SPDX-License-Identifier` |
| G third-party only | license files only in third-party folders |
| H no license evidence found | none of the above |

"Comes back" means A1 or A2. A1 is the S3 name rule for files. A2 is the S3 name
rule for folders: S3 accepted such folders for other-host rows. P rows match the
literal S3 rule, but they are false matches, so they do not come back.

For each row the script takes the commit count from `../../s3-measure/commits.jsonl`
(GitHub) or `clone_facts.jsonl` (other hosts), the run layer (DP7), the size
class and u = sha256("20261110:" + slug), as `../funnel.py` does. It does not
measure again. All rows that come back passed every other S4 filter, because
DP8L is the last step and each row has the first step that removes it.

`other_host_copy` lists the other-host rows of `../../s3-measure/clones.jsonl`
with the same snapshot commit, so that a mirror of a project that is already in
the frame is visible.

`returned_frame.csv` has the rows that come back, with the columns and values
that `../funnel.py` gives to frame rows (S3 measures, pool facts), in run order
(layer, then u). It does not change `../frame.csv`.

## 6. Limits

- Other-host rows: S3 already applied the name rule to their root tree. S3 kept
  no tree listing, so this audit has no near-miss data for them.
- busybox (`url:https://git.busybox.net/busybox`): S3 could not fetch it, so this
  audit has no license test and no commit count for it. The v2 funnel
  (`../funnel.v2.md`, `../supplement.v2.csv`, commit e812c86) measured it again:
  it has a license file and comes back (layer 1, S, 18,355 commits).
- The README test and the package-file test find text, not a license grant. They
  are near misses for a manual check, not a decision.
- A recursive tree that GitHub truncates (`recursive_tree_status` = `200
  truncated`) can hide subfolder files.
- `portbuster1337/lpe-toolkit` gave HTTP 404 for its root tree (the repository
  is not available now).

## 7. Reproduce

```
python3 audit_dp8l.py fetch    # network; resumable; skips the calls that have a final answer
python3 audit_dp8l.py report   # no network; reads raw/*.jsonl or raw/*.jsonl.xz
```

`report` needs `../frame_status.csv` (from `../funnel.py`), `../../s2-pool/pool.csv`
(or `.xz`), the S3 files in `../../s3-measure/` (or `.xz`), and
`../../s7-run/frame.layer1.csv` (from `../../s7-run/build_run.sh`).

## 8. The decided rule and its application (2026-10-10)

The user decided the rule of `SELECTION-STAGES.md` section 6 (DP8L), in two
steps on 2026-10-10. First: one rule for all hosts, read from the root tree
(`../dp8l_rule.py`). Then (about 01:40 UTC) the final rule: a row passes if it has
a root license file or folder (the root rule), **or** if GitHub detects a license
(pool column `license` not empty). The user chose the union so that no row of
the frame leaves. `../funnel.py --dp8l` applies the union: for a GitHub row with
an empty `license`, `roots.csv` decides; other-host rows use the root rule on the
S3 names. The near misses (C, D, E, F, G, H, and P) fail both tests and stay out
of the frame. Their reason in `excluded_because` names the near miss, for
example "no license file (near miss: license file only in a subfolder)".

Result (`../funnel.v3.md`): DP8L keeps 25,866 rows = 25,263 (the frame) + 603
(the 602 GitHub rows that come back and BusyBox); no row of `../frame.csv` leaves.
Layer 1 has 3,346 rows = 3,265 + 81 (batch 21).

**The GitHub rows of the frame.** The rule applies to all rows, so the script
also read the root names of the 24,498 GitHub rows of `../frame.csv` at the
snapshot commit (`fetch-frame`): GraphQL, 50 rows in one query, one query at a
time (490 queries, 2026-10-10 00:42 to 01:18 UTC, `raw/frame_roots.jsonl`). The
script checks that `databaseId` is the pool `database_id`. The 13 rows that
GraphQL did not answer got the REST root tree call (`raw/frame_roots_rest.jsonl`,
all 13 HTTP 404: deleted or private now). For the 30 rows whose root has a
license folder but no license file, the script listed the folder
(`GET /repos/{nwo}/contents/{folder}?ref={head_oid}`, `raw/frame_license_folders.jsonl`).

`roots` writes `roots.csv`: for each GitHub row that reaches DP8L (2,692 DP8L
rows and 24,498 frame rows), `has_license`, the evidence and the reason.
Other-host rows use the S3 names (`clone_facts.jsonl`, `license_files`) with
the same rule; all 766 other-host rows of the v2 frame pass. Under the root rule
alone, 154 GitHub rows of the frame fail (40 in layer 1); the union keeps them
(table below).

**The 154 rows that pass only by GitHub's detection.** These GitHub rows of
`../frame.csv` have no root license file or folder by the root rule at the
snapshot commit; GitHub detects a license, so they stay in the frame. "Root names" are the root
entries with a license-like name (empty: none; "root tree not read": the repository gives HTTP 404 now).

| Project | Layer | GitHub license | Root names |
| --- | --- | --- | --- |
| aboutcode-org/scancode-toolkit | ≥ 5,000 | NOASSERTION | NOTICE, apache-2.0.LICENSE, cc-by-4.0.LICENSE, pyproject-licensedcode-data.toml, pyproject-licensedcode-index.toml |
| amanzi/amanzi | ≥ 5,000 | NOASSERTION | COPYRIGHT.md |
| ant-media/Ant-Media-Server | ≥ 5,000 | NOASSERTION | COMMUNITY_EDITION_LICENSE, ENTERPRISE_EDITION_LICENSE |
| antlr/grammars-v4 | ≥ 5,000 | MIT |  |
| berkeley-abc/abc | ≥ 5,000 | NOASSERTION | copyright.txt |
| BRL-CAD/brlcad | ≥ 5,000 | NOASSERTION | root tree not read |
| CESNET/UltraGrid | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| dankamongmen/notcurses | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| davidgiven/ack | ≥ 5,000 | NOASSERTION | Copyright |
| DCMTK/dcmtk | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| digi-embedded/android_platform_frameworks_base | ≥ 5,000 | NOASSERTION | MODULE_LICENSE_APACHE2, NOTICE |
| DragonFlyBSD/DragonFlyBSD | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| embox/embox | ≥ 5,000 | BSD-2-Clause | COPYRIGHT |
| freebsd/freebsd-ports | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| freebsd/freebsd-src | ≥ 5,000 | NOASSERTION | COPYRIGHT, cddl |
| GNOME/libxml2 | ≥ 5,000 | NOASSERTION | Copyright |
| graalvm/musl | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| IBAMR/IBAMR | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| jasonrohrer/OneLife | ≥ 5,000 | NOASSERTION | no_copyright.txt |
| jenkinsci/git-plugin | ≥ 5,000 | MIT | MIT-LICENSE.txt |
| kitao/pyxel | ≥ 5,000 | NOASSERTION | root tree not read |
| Kitware/ParaView | ≥ 5,000 | BSD-3-Clause | Copyright.txt |
| Kitware/VTK | ≥ 5,000 | NOASSERTION | Copyright.txt |
| liferay/liferay-docs | ≥ 5,000 | NOASSERTION | copyright.txt |
| LineageOS/android_frameworks_base | ≥ 5,000 | NOASSERTION | MODULE_LICENSE_APACHE2, NOTICE |
| mupen64plus-ae/mupen64plus-ae | ≥ 5,000 | GPL-3.0 | gpl-license |
| neuronsimulator/nrn | ≥ 5,000 | NOASSERTION | Copyright |
| OpenModelica/OpenModelica | ≥ 5,000 | NOASSERTION | OSMC-License.txt, OSMC-Runtime-License.txt |
| OpenSees/OpenSees | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| opnsense/src | ≥ 5,000 | NOASSERTION | COPYRIGHT, cddl |
| pfsense/FreeBSD-ports | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| pmodels/mpich | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| postgres/postgres | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| rethinkdb/rethinkdb | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| skaiworldwide-oss/agensgraph | ≥ 5,000 | NOASSERTION | COPYRIGHT |
| sushi-labs/sushiswap | ≥ 5,000 | MIT |  |
| Unidata/netcdf-c | ≥ 5,000 | BSD-3-Clause | COPYRIGHT |
| Uniswap/interface | ≥ 5,000 | GPL-3.0 |  |
| weihuayi/fealpy | ≥ 5,000 | NOASSERTION | COPYRIGHT.txt |
| yamcs/yamcs | ≥ 5,000 | AGPL-3.0 | AGPL-LICENSE.txt |
| 1lck/Lithe-IDEA | 1,000–4,999 | Apache-2.0 | root tree not read |
| aardappel/treesheets | 1,000–4,999 | Zlib | ZLIB_LICENSE.txt |
| aklivity/zilla | 1,000–4,999 | NOASSERTION | root tree not read |
| asterics/AsTeRICS | 1,000–4,999 | NOASSERTION | ARE-LICENSE_MITOrGPLv3WithException.txt |
| cargo-bins/cargo-binstall | 1,000–4,999 | GPL-3.0 |  |
| chris2511/xca | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| cjlin1/libsvm | 1,000–4,999 | BSD-3-Clause | COPYRIGHT |
| dalek-cryptography/curve25519-dalek | 1,000–4,999 | NOASSERTION |  |
| DanBloomberg/leptonica | 1,000–4,999 | NOASSERTION | leptonica-license.txt |
| devkitPro/libnds | 1,000–4,999 | NOASSERTION | libnds_license.txt |
| dinhvh/libetpan | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| dreamhead/moco | 1,000–4,999 | MIT | MIT-LICENSE.txt |
| espressif/esp-bsp | 1,000–4,999 | NOASSERTION | check_copyright_config.yaml |
| fluffos/fluffos | 1,000–4,999 | NOASSERTION | Copyright |
| GerHobbelt/pthread-win32 | 1,000–4,999 | NOASSERTION |  |
| GNOME/libxslt | 1,000–4,999 | NOASSERTION | Copyright |
| GNOME/msitools | 1,000–4,999 | NOASSERTION | copyright |
| gpgpu-sim/gpgpu-sim_distribution | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| herumi/mcl | 1,000–4,999 | BSD-3-Clause | COPYRIGHT |
| herumi/xbyak | 1,000–4,999 | BSD-3-Clause | COPYRIGHT |
| hpc/ior | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| ImageOptim/libimagequant | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| intel/yask | 1,000–4,999 | NOASSERTION | YASK-LICENSE.md |
| kornelski/pngquant | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| LuaJIT/LuaJIT | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| magiblot/tvision | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| mstorsjo/fdk-aac | 1,000–4,999 | NOASSERTION | MODULE_LICENSE_FRAUNHOFER, NOTICE |
| openresty/luajit2 | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| OpenVPN/openvpn3-linux | 1,000–4,999 | AGPL-3.0 | COPYRIGHT.md |
| Orc/discount | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| pgbouncer/pgbouncer | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| postgresml/postgresml | 1,000–4,999 | MIT | MIT-LICENSE.txt |
| rails-sqlserver/tiny_tds | 1,000–4,999 | NOASSERTION | MIT-LICENSE |
| rhboot/shim | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| rigaya/NVEnc | 1,000–4,999 | NOASSERTION | NVEnc_license.txt |
| rustsec/rustsec | 1,000–4,999 | NOASSERTION |  |
| sm0svx/svxlink | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| Tarsnap/scrypt | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| Tarsnap/spiped | 1,000–4,999 | NOASSERTION | COPYRIGHT |
| treefrogframework/treefrog-framework | 1,000–4,999 | BSD-3-Clause | copyright |
| zhanglun/lettura | 1,000–4,999 | MIT |  |
| zhiburt/tabled | 1,000–4,999 | MIT |  |
| 2ndQuadrant/pglogical | 500–999 | NOASSERTION | COPYRIGHT |
| alipay/alipay-sdk-java-all | 500–999 | Apache-2.0 |  |
| chxdeng/mabain | 500–999 | GPL-2.0 | GPLv2-LICENSE.md |
| clitic/vsd | 500–999 | Apache-2.0 |  |
| danielpclark/faster_path | 500–999 | MIT | MIT-LICENSE.txt |
| ethz-asl/ethzasl_msf | 500–999 | NOASSERTION | COPYRIGHT_Template.h, NOTICE |
| experientiallabs/experiential | 500–999 | Apache-2.0 | root tree not read |
| h4570/tyra | 500–999 | Apache-2.0 |  |
| intel/FSP | 500–999 | NOASSERTION | FSP_License.pdf, Other_Licenses |
| jordansissel/xdotool | 500–999 | BSD-3-Clause | COPYRIGHT |
| LiveContainer/LiveContainer | 500–999 | AGPL-3.0 | root tree not read |
| llnl/GOTCHA | 500–999 | NOASSERTION | COPYRIGHT, LGPL |
| lob/lob-java | 500–999 | MIT |  |
| LuaLanes/lanes | 500–999 | NOASSERTION | COPYRIGHT |
| MicrosoftDocs/winapps-winrt-api | 500–999 | CC-BY-4.0 |  |
| NXPNFCProject/NFC_NCIHAL_libnfc-nci | 500–999 | NOASSERTION | MODULE_LICENSE_APACHE2, NOTICE |
| ossc-db/pg_hint_plan | 500–999 | NOASSERTION | COPYRIGHT, COPYRIGHT.postgresql |
| PasteBar/PasteBarApp | 500–999 | NOASSERTION | CC-LICENSE |
| pgpointcloud/pointcloud | 500–999 | NOASSERTION | COPYRIGHT |
| plv8/plv8 | 500–999 | NOASSERTION | COPYRIGHT |
| pmix/pmix-standard | 500–999 | NOASSERTION | pmix_copyright.txt |
| polpo/picogus | 500–999 | GPL-2.0 |  |
| PureDarwin/PureDarwin | 500–999 | NOASSERTION | APPLE_DRIVER_LICENSE.txt, APPLE_LICENSE.txt, PUREDARWIN_LICENSE.txt |
| reorg/pg_repack | 500–999 | BSD-3-Clause | COPYRIGHT |
| rust-console/gba | 500–999 | Apache-2.0 |  |
| sqlcipher/android-database-sqlcipher | 500–999 | NOASSERTION | SQLCIPHER_LICENSE |
| statewright/statewright | 500–999 | NOASSERTION | PATENTS.md |
| stevepryde/thirtyfour | 500–999 | NOASSERTION |  |
| wanghuan9/skilldock | 500–999 | MIT | root tree not read |
| albertodemichelis/squirrel | 100–499 | MIT | COPYRIGHT |
| amutu/zhparser | 100–499 | NOASSERTION | COPYRIGHT |
| aws/aws-iot-device-sdk-cpp-v2 | 100–499 | Apache-2.0 |  |
| aws/aws-iot-device-sdk-java-v2 | 100–499 | Apache-2.0 |  |
| bgp/bgpq4 | 100–499 | BSD-2-Clause | COPYRIGHT |
| caamer20/Telegram-Drive | 100–499 | NOASSERTION | SUPPORTER_LICENSE_INVARIANTS.md |
| cjlin1/liblinear | 100–499 | BSD-3-Clause | COPYRIGHT |
| cnr-isti-vclab/nexus | 100–499 | GPL-3.0 |  |
| ComicSparks/jasmine | 100–499 | MIT |  |
| googlefonts/Inconsolata | 100–499 | OFL-1.1 |  |
| googlefonts/sawarabi-mincho | 100–499 | OFL-1.1 |  |
| IBM/diesel-json-form | 100–499 | Apache-2.0 |  |
| immunogenomics/harmony | 100–499 | NOASSERTION |  |
| liquidos-ai/AutoAgents | 100–499 | Apache-2.0 | APACHE_LICENSE, MIT_LICENSE |
| magiblot/turbo | 100–499 | NOASSERTION | COPYRIGHT |
| mTvare6/hello-world.rs | 100–499 | NOASSERTION | LICENSE.rs |
| netease-kit/NIM_PC_Demo | 100–499 | NOASSERTION | directui_license.txt, duilib_license.txt, openssl_license.txt |
| ossc-db/pg_bulkload | 100–499 | BSD-3-Clause | COPYRIGHT |
| ossc-db/pg_rman | 100–499 | NOASSERTION | COPYRIGHT |
| pufferfish-gg/Pufferfish | 100–499 | GPL-3.0 | PATCH-LICENSE |
| rafat/wavelib | 100–499 | NOASSERTION | COPYRIGHT |
| Shopify/better-html | 100–499 | MIT | MIT-LICENSE |
| szechyjs/dsd | 100–499 | NOASSERTION | COPYRIGHT |
| wellle/context.vim | 100–499 | MIT | MIT-LICENSE |
| ZacharyZhang-NY/Ely-GPUI-Components | 100–499 | MIT | root tree not read |
| zendesk/ultragrep | 100–499 | Apache-2.0 | APACHE20-LICENCE |
| aimeoa/hanshuang-codex | < 100 | MIT | root tree not read |
| alandipert/ncsa-mosaic | < 100 | NOASSERTION | COPYRIGHT |
| analogdevicesinc/ADSP-UCSDK | < 100 | NOASSERTION |  |
| analogdevicesinc/Magpie | < 100 | Apache-2.0 | Apache_License.txt |
| apple-oss-distributions/dyld | < 100 | NOASSERTION | APPLE_LICENSE |
| apple-oss-distributions/objc4 | < 100 | NOASSERTION | APPLE_LICENSE |
| apple-oss-distributions/xnu | < 100 | NOASSERTION | APPLE_LICENSE, bsd |
| archie0732/healthy-diet-ai-agent | < 100 | MIT | root tree not read |
| CMU-Graphics/Scotty3D | < 100 | MIT |  |
| EspressifApp/EsptouchForIOS | < 100 | NOASSERTION | ESPRESSIF_MIT_LICENSE_V1.LICENSE |
| eulerto/pg_similarity | < 100 | BSD-3-Clause | COPYRIGHT |
| infinet/lunar-calendar | < 100 | BSD-2-Clause | COPYRIGHT |
| khanhduytran0/SparseBox | < 100 | AGPL-3.0 | root tree not read |
| LanceZPF/agent-as-a-router | < 100 | MIT | root tree not read |
| livecontext-ai/livecontext-ce | < 100 | NOASSERTION | root tree not read |
| mesibo/messenger-app-android | < 100 | NOASSERTION | COPYRIGHT.md |
| NODIX-TECH/DLSS-5-MANAGER | < 100 | NOASSERTION | Copyright.txt, THIRD-PARTY-NOTICES.txt |

**License values.** `licenses` writes `licenses.csv` for the 602 rows that come
back and the row of `../supplement.v2.csv` (BusyBox): the SPDX ids that name the
files of the root folder `LICENSES` (REUSE; the file name without its extension
must be an id of the SPDX license list or exception list, or `LicenseRef-...`),
sorted and joined with `;`, else `NOASSERTION`. Only the folder `LICENSES` gives
ids: other folders (`licenses/`, `license/`, `Licenses/`) can hold the licenses
of software that the project packages (NetBSD/pkgsrc, libretro/Lakka-LibreELEC).
`license_evidence` keeps the files used. SPDX list: `raw/spdx/` (license-list-data
v3.29.0, read with `gh api` on 2026-10-10, `raw/spdx/SOURCE.tsv`).

**Manual check of three A2 folders** (`raw/manual_checks.jsonl`):

| Project | Folder | Finding | Decision |
| --- | --- | --- | --- |
| cocos2d/cocos2d-x | `licenses/` | 29 files; most are third-party licenses, but `licenses/LICENSE_cocos2d-x.txt` is the MIT license of cocos2d-x itself | project license; in |
| BroadleafCommerce/BroadleafCommerce | `licenses/` | `licenses.properties` points to `licenses/blc_dual/fair_use_license-1.0.txt`; the folder also has `commercial_license-1.1.txt`: the project's own dual license (source-available, not an OSI license) | project license file; in |
| SmileiPIC/Smilei | `License/` | `License/License` is the CeCILL-B text; `License/header` says that Smilei is under CeCILL-B | project license; in |
