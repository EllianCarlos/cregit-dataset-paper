#!/usr/bin/env bash
# R4-start-b.sh (machine B of the x1k relaunch, FULL pipeline, root, through ssm.sh; after R1, R2
# (all 4 CHECK OK) and R3-install-b.sh): start the rows of this machine's slot.
# User decision 2026-10-19: the x1k rows join the released dataset. So B runs the v1 code path:
# the UNPATCHED ctp ca113e3 (firm step, join and full validate; no --no-firm), cregit 57551d7,
# the flags of the v1 fed parts (in x1k-run of R3-install-b.sh).
#   1. inputs: s3://B/dataset-x1k/inputs/ -> /data/x1k-inputs, sha256 checked (the inputs of the
#      first run; no new upload);
#   2. code check: each part's ctp clone is ca113e3, clean, never patched (no .x1k-patched); the
#      ctp tests pass in p1's clone; each part's R2 gate Parquet (unpatched ca113e3, full steps with
#      the firm step, on the part's own cregit copy) is 14eb5d72 (WANT_PQ of the v1 batches 7-26)
#      and has 70 columns;
#   3. (the no-firm check of R4-start.sh is not used);
#   4. the deal. A FIXED deal of all rows of manifest.x1k-p1..p4.tsv minus the 11 machine-A rows
#      (7,204) to 8 parts. First the heavy rows, longest first, each to the part with the least
#      heavy hours so far (LPT). HEAVY below: the 273 non-A rows with >= 30 MB tokenizable
#      (x1k/predict.tsv of ${RUNNER_STUDY_REPO} 63591d3, sha256 ef45b59b) or >= 1 h measured in the first
#      run; columns name, hours (measured wall time of the first run if the row is in done/, else
#      the measured mean of its size class). Then the light rows in u order by rank
#      across the 4 source parts, row by row to the 8 parts. The deal does not depend on the done
#      set, so both machines and each
#      relaunch get the same parts. Slot 1 (/etc/dataset-x1k/slot) runs parts 1-4, slot 2 parts
#      5-8, on /data1-4. Then each part drops the rows with dataset-x1k/done-full/<p>/OK. The old
#      done/ (the --no-firm run; Parquets without the firm columns) is not used: those 1,377 rows run
#      again in full. ctp plan() also skips a project that its own ledger has as done;
#   5. WORKERS per part from nproc: 5 below 128 vCPU (96 vCPU: 20 workers), 6 from 128 vCPU (24
#      workers); WORKERS=<n> in the environment of this script overrides it. Starts x1k-watch, the
#      upload, live and finalize timers and x1k@1..4.
# Run id: /etc/dataset-x1k/run (from R3-install-b.sh). It refuses when live/<run>/START is in S3
# already (a used run id): a relaunch takes a new NAME (dataset-x1k-b<slot>-r<n>), and continues
# with the rows of the slot that have no done-full/OK. Writes /etc/dataset-x1k/started and
# dataset-x1k/live/<run>/START and deal.tsv. Never on the instances of the refuse list.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_A}) echo "ABORT: $IID is on the refuse list"; exit 1 ;; esac
B=s3://${RUNNER_BUCKET}
E=/etc/dataset-x1k; I=/data/x1k-inputs
NCPU=$(nproc)
if [ -z "${WORKERS:-}" ]; then
  if [ "$NCPU" -ge 128 ]; then WORKERS=6; elif [ "$NCPU" -ge 96 ]; then WORKERS=5; else echo "ABORT: $NCPU vCPU; the B list has 96 or 128"; exit 1; fi
fi
WANT_PQ=14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
NSLOTS=2
# The machine-A rows (README "Relaunch plan", machine A): never in a B part.
A_ROWS="RMerl__asuswrt-merlin.ng awslabs__aws-sdk-rust metashell__metashell microsoftgraph__msgraph-beta-sdk-java aws__aws-sdk-java TencentCloud__tencentcloud-sdk-cpp googleapis__google-cloud-rust Byron__google-apis-rs autc04__Retro68 notnotype__neuro-book pur1fying__blue_archive_auto_script"
RUN=$(cat $E/run 2>/dev/null) || { echo "ABORT: no $E/run (run R3-install-b.sh through scripts/w6/ssm-run.sh)"; exit 1; }
SLOT=$(cat $E/slot 2>/dev/null) || { echo "ABORT: no $E/slot (run R3-install-b.sh through scripts/w6/ssm-run.sh)"; exit 1; }
case $SLOT in 1|2) ;; *) echo "ABORT: slot '$SLOT' is not 1 or 2"; exit 1 ;; esac
echo "== $(date -u +%FT%TZ) $IID R4-b start, run $RUN, slot $SLOT of $NSLOTS, $NCPU vCPU, $WORKERS workers per part"
aws s3 ls $B/dataset-x1k/live/$RUN/START >/dev/null 2>&1 && { echo "ABORT: live/$RUN/START is in S3: run id $RUN is used; launch with a new NAME"; exit 1; }
[ -f $E/started ] && { echo "ABORT: $E/started exists (this instance started already)"; exit 1; }
for K in 1 2 3 4; do systemctl is-active -q x1k@$K && { echo "ABORT: x1k@$K runs already"; exit 1; }
  tail -1 $E/p$K.check 2>/dev/null | grep -q '^CHECK OK' || { echo "ABORT: p$K has no CHECK OK (run R2)"; exit 1; }; done
[ -x /usr/local/bin/x1k-run ] || { echo "ABORT: run R3-install-b.sh first"; exit 1; }
grep -q 'live/$RUN/progress.txt' /usr/local/bin/x1k-live || { echo "ABORT: x1k-live is not the R3-install-b.sh version"; exit 1; }
grep -q 'dataset-x1k/done-full"' /usr/local/bin/x1k-upload || { echo "ABORT: x1k-upload does not write to done-full/ (run the R3-install-b.sh of the full run)"; exit 1; }
grep -q -e '--no-firm' /usr/local/bin/x1k-run && { echo "ABORT: x1k-run has --no-firm (run the R3-install-b.sh of the full run)"; exit 1; }
# 1. inputs
mkdir -p $I
aws s3 cp $B/dataset-x1k/inputs/ $I/ --recursive --only-show-errors || { echo "ABORT: inputs download"; exit 1; }
(cd $I && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: inputs sha256"; exit 1; }
chown -R ec2-user:ec2-user $I; echo "inputs: $(head -1 $I/SOURCE); $(wc -l < $I/SHA256SUMS) files"
# 2. code check: the v1 code path (unpatched ca113e3, the R2 gate = 14eb5d72 with 70 columns)
for K in 1 2 3 4; do C=/data$K/x1k/ctp; G=/data$K/x1k/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet
  [ ! -e $C/.x1k-patched ] || { echo "ABORT: p$K ctp clone was patched ($C/.x1k-patched)"; exit 1; }
  h=$(sudo -u ec2-user git -C $C rev-parse --short HEAD); d=$(sudo -u ec2-user git -C $C status --porcelain --untracked-files=no)
  [ "$h" = ca113e3 ] && [ -z "$d" ] || { echo "ABORT: p$K ctp clone is $h, changes: $d"; exit 1; }
  [ "$(sha256sum $G 2>/dev/null | cut -d' ' -f1)" = $WANT_PQ ] || { echo "ABORT: p$K gate Parquet is not 14eb5d72"; exit 1; }
  n=$(cd $C && sudo -u ec2-user .venv/bin/python -c 'import duckdb, sys; print(len(duckdb.connect().execute("describe select * from read_parquet(?)", [sys.argv[1]]).fetchall()))' $G)
  [ "$n" = 70 ] || { echo "ABORT: p$K gate Parquet has $n columns, not 70"; exit 1; }
  echo "p$K: ctp $h clean, not patched; gate Parquet 14eb5d72, $n columns (firm step in)"
done
t=$(cd /data1/x1k/ctp && sudo -u ec2-user .venv/bin/python -m pytest -q -o addopts= -p no:cacheprovider 2>&1 | tail -1)
echo "ctp tests (p1 clone, ca113e3): $t"; echo "$t" | grep -q ' passed' && ! echo "$t" | grep -q -e failed -e error || { echo "ABORT: ctp tests"; exit 1; }
r="code: ctp ca113e3 unpatched (full pipeline), cregit 57551d7, gate 14eb5d72 on all 4 copies"
# 4. the fixed deal; this slot's 4 parts minus done-full/OK
aws s3 ls $B/dataset-x1k/done-full/ --recursive > /tmp/x1k-done.ls 2>/dev/null; rc=$?
# rc 1 with no output: the prefix is empty (first start)
[ $rc = 0 ] || { [ $rc = 1 ] && [ ! -s /tmp/x1k-done.ls ]; } || { echo "ABORT: listing of done-full/ (rc $rc)"; exit 1; }
awk '$4 ~ /^dataset-x1k\/done-full\/[^\/]+\/OK$/ {split($4, a, "/"); print a[3]}' /tmp/x1k-done.ls | sort -u > /tmp/x1k-oks
echo "projects with done-full/OK in S3: $(wc -l < /tmp/x1k-oks)"
mkdir -p /tmp/x1k-deal
cat > /tmp/x1k-heavy.tsv <<'HEAVY'
TencentCloud__tencentcloud-sdk-cpp-intl-en	20.50
TencentCloud__tencentcloud-sdk-java	17.68
qwq233__Nullgram	15.42
F-Stack__f-stack	13.91
NextAlone__Nnngram	12.08
NextAlone__Nagram	11.99
im030__Momogram	11.43
marchaesen__vcxsrv	11.30
multi-os-engine__multi-os-engine	10.46
Grasscutters__Grasscutter	7.62
TA-Lib__ta-lib	7.01
microsoft__win32metadata	6.09
stm32duino__Arduino_Core_STM32	5.39
glKarin__com.n0n3m4.diii4a	5.19
oneapi-src__oneAPI-samples	4.84
OctoGramApp__OctoGram	4.30
alibaba__MNN	4.30
linuxkerneltravel__lmp	4.30
copperspice__copperspice	4.30
makepad__makepad	4.30
Nekogram__Nekogram	4.30
YannickJadoul__Parselmouth	4.30
olikraus__u8g2	4.30
skylersaleh__SkyEmu	4.30
microsoftgraph__msgraph-sdk-java	4.30
mas-elkhanza__SIMRS-Khanza	4.30
huahua132__skynet_fly	4.30
bytedeco__javacpp-presets	4.30
microsoft__windows-rs	4.30
MrDrElliot__LuminaEngine	4.30
CloverHackyColor__CloverBootloader	4.30
IppClub__Dora-SSR	4.30
hyperledger-iroha__iroha	4.30
xMasterX__all-the-plugins	4.30
mirkosertic__Bytecoder	4.30
xarray__osgverse	4.30
LWJGL__lwjgl3	4.30
MarlinFirmware__Configurations	4.26
TencentCloud__tencentcloud-sdk-java-intl-en	4.25
weolar__miniblink49	4.23
Xilinx__Vitis-AI	4.21
linkingvision__rapidvms	3.16
liuliu__ccv	2.25
RedisGraph__RedisGraph	2.08
Pumpkin-MC__Pumpkin	2.07
open-goal__jak-project	1.81
ARM-software__Arm-2D	1.76
DrTimothyAldenDavis__SuiteSparse	1.59
Sidiora-Labs__Paxeer-X-Network	1.53
timi-liuliang__echo	1.52
analogdevicesinc__msdk	1.44
EpicGames__raddebugger	1.35
TrampolineRTOS__trampoline	1.34
Refinitiv__Real-Time-SDK	1.34
jart__cosmopolitan	1.26
MobiVM__robovm	1.24
rue-language__rue	1.19
TEN-framework__ten-framework	1.18
utelle__wxsqlite3	1.14
ax-llm__ax	1.14
esa__pagmo2	1.11
rust-lang__stdarch	1.10
canboat__canboat	1.07
simd-everywhere__simde	1.07
apple__coremltools	1.07
arlyon__async-stripe	1.06
gojue__ecapture	1.05
FreeRTOS__FreeRTOS	1.04
drawthingsai__draw-things-community	1.03
seemoo-lab__nexmon	0.97
aardappel__lobster	0.94
Firmament-Autopilot__FMT-Firmware	0.94
hggq__paozhu	0.88
thradams__cake	0.86
jakartaee__platform-tck	0.81
pulumi__pulumi-kubernetes	0.73
SethRobinson__Patchy	0.71
arduino__ArduinoCore-mbed	0.65
oceanbase__seekdb	0.65
yoshisuga__MAME4iOS	0.65
OpenNJet__OpenNJet	0.65
google__sagetv	0.65
pschatzmann__arduino-audio-tools	0.65
littlekernel__lk	0.65
soramimi__Guitar	0.65
sajjadium__ctf-archives	0.65
eclipse-egf__emf.egf	0.65
Paciente8159__uCNC	0.65
tmk__tmk_keyboard	0.65
KSwordDEV__KSword	0.65
avrdudes__avr-libc	0.65
tauri-apps__cef-rs	0.65
mhogrefe__malachite	0.65
jellyfin__jellyfin-ffmpeg	0.65
zeldaret__tp	0.65
warpdotdev__warp	0.65
gambit__gambit	0.65
mighty-gerbils__gerbil	0.65
risc0__risc0	0.65
ruvnet__RuVector	0.65
deeplearning4j__deeplearning4j	0.65
thunder-engine__thunder	0.65
antopilo__Nuake	0.65
mikekazakov__nimble-commander	0.65
synapticon__Etherlab_EtherCAT_Master	0.65
DiSlord__NanoVNA-D	0.65
ngageoint__six-library	0.65
open-simh__simh	0.65
yimengfan__BDFramework.Core	0.65
Xilinx__Vitis-Tutorials	0.65
LuisaGroup__LuisaRender	0.65
HackerN64__HackerSM64	0.65
ammaarreshi__Generals-Mac-iOS-iPad	0.65
colbymchenry__codegraph	0.65
Rheosoph__flow-like	0.65
nearai__ironclaw	0.65
818000__bus	0.65
danoon2__Boxedwine	0.65
eclipse-agileuml__agileuml	0.65
flomesh-io__pipy	0.65
espressif__esp-adf	0.65
mappu__miqt	0.65
duckdb__duckdb-spatial	0.65
DC-SWAT__DreamShell	0.65
ixray-team__ixray-1.6-stcop	0.65
LunarG__gfxreconstruct	0.65
ColdGrub1384__Pyto	0.65
Serial-Studio__Serial-Studio	0.65
gotempsh__temps	0.65
fabsig__GPBoost	0.65
kaluma-project__kaluma	0.65
radkesvat__WaterWall	0.65
Filoppi__Luma-Framework	0.65
plan9foundation__plan9	0.65
eduard-permyakov__permafrost-engine	0.65
Tracktion__tracktion_engine	0.65
aovestdipaperino__tokensave	0.65
icedland__iced	0.65
MrNeRF__LichtFeld-Studio	0.65
Auties00__Cobalt	0.65
pacifio__atlas	0.65
VincentWei__MiniGUI	0.65
kiegroup__kie-wb-common	0.65
quickfix__quickfix	0.65
skylicht-lab__skylicht-engine	0.65
Meulengracht__MollenOS	0.65
fawney19__Aether	0.65
elishacloud__dxwrapper	0.65
omnigres__omnigres	0.65
Kelsidavis__WoWee	0.65
oracle__graalvm-reachability-metadata	0.65
Eukaryot__sonic3air	0.65
tksuoran__erhe	0.65
eclipse-uml2__uml2	0.65
espressif__esp-iot-solution	0.65
geogebra__geogebra	0.65
EVerest__EVerest	0.65
microsoft__Windows-driver-samples	0.65
lablup__mlxcel	0.65
Bearer__bearer	0.65
NVIDIA__nvmesh-kernel	0.65
mholtkamp__octave	0.65
microsoft__msix-packaging	0.65
JACoders__OpenJK	0.65
open-quantum-safe__liboqs	0.65
ntop__PF_RING	0.65
HarbourMasters__PaperBoat	0.65
magnitudedev__magnitude	0.65
lightvector__KataGo	0.65
ZSeven-W__openpencil	0.65
digitalgust__miniJVM	0.65
crate-ci__typos	0.65
NVIDIA__cuda-rust	0.65
coredevices__PebbleOS	0.65
0xErwin1__dbflux	0.65
AnalyseDeCircuit__oxideterm	0.65
DK22Pac__plugin-sdk	0.65
artifact-keeper__artifact-keeper	0.65
sevenlabs-hq__carbon	0.65
AshenvaleZX__ZXEngine	0.65
skvadrik__re2c	0.65
apache__gravitino	0.65
mysql__mysql-workbench	0.65
onap__sdc	0.65
markaren__threepp	0.65
dsldevkit__dsl-devkit	0.65
ACreTeam__ac-decomp	0.65
dpjudas__SurrealEngine	0.65
ctxrs__ctx	0.65
schreibfaul1__ESP32-MiniWebRadio	0.65
deividAlfa__stm32_soldering_iron_controller	0.65
opencomputeproject__OpenNetworkLinux	0.65
AllenDang__cimgui-go	0.65
octos-org__octos	0.65
eclipse-kitalpha__kitalpha	0.65
turms-im__turms	0.65
jerryuhoo__Fire	0.65
2ship2harkinian__2ship2harkinian	0.65
SAT-R__sa2	0.65
HarbourMasters__Shipwright	0.65
infiniflow__infinity	0.65
TableProApp__TablePro	0.65
BabylonJS__BabylonNative	0.65
IBM__JTOpen	0.65
blawar__ooot	0.65
vczh-libraries__Release	0.65
sipwise__kamailio	0.65
acl-dev__acl	0.65
OpenGamma__Strata	0.65
LiangliangNan__Easy3D	0.65
cping__LGame	0.65
Squalr__Squally	0.65
Noelo-Lab__kuna	0.65
kirill-grouchnikov__radiance	0.65
microsoft__openvmm	0.65
stripe__stripe-java	0.65
Garux__netradiant-custom	0.65
ghaerr__microwindows	0.65
portapack-mayhem__mayhem-firmware	0.65
amov-lab__Prometheus	0.65
OGSR__OGSR-Engine	0.65
ZSWatch__ZSWatch	0.65
LiteLDev__LeviLamina	0.65
doriaxengine__doriax	0.63
GhostESP-Revival__GhostESP	0.59
Yuzhii0718__bl-mt798x-dhcpd	0.59
ValveSoftware__Proton	0.59
SpartanJ__eepp	0.58
opendaylight__vtn	0.58
BodbDearg__PsyDoom	0.50
apache__drill	0.47
momentum-mod__game	0.47
eclipse-jsdt__webtools.jsdt	0.47
BoundaryML__baml	0.42
chrishayuk__larql	0.42
floci-io__floci	0.42
ROCm__composable_kernel	0.41
eclipse-embed-cdt__eclipse-plugins	0.41
losnoco__Cog	0.40
alibaba__rtp-llm	0.40
Adyen__adyen-java-api-library	0.39
i42output__neoGFX	0.37
microsoft__microsoft-ui-xaml	0.35
google__nearby	0.34
oracle__coherence	0.34
fallow-rs__fallow	0.33
Tencent__ncnn	0.33
lyusupov__SoftRF	0.32
gideros__gideros	0.32
ArduPilot__apm_planner	0.31
plabayo__rama	0.30
yyjeqhc__webcodex	0.30
rive-app__rive-runtime	0.28
lexmount__moli	0.26
agentic-os-org__ANOLISA	0.25
dphnAI__sonar	0.25
ARM-software__ComputeLibrary	0.24
bryanthaboi__gen1recomp	0.19
lovyan03__LovyanGFX	0.19
Tencent__mars	0.18
TheWaveWarden__odin2	0.17
OSCC-Project__iEDA	0.15
facebookresearch__ocean	0.15
elishacloud__Silent-Hill-2-Enhancements	0.15
sophgo__sophon-demo	0.14
flipperdevices__flipperzero-firmware	0.14
garglk__garglk	0.14
Tiiny-AI__PowerInfer	0.13
MayaPosch__NymphCast	0.12
praydog__REFramework	0.12
Bodmer__TFT_eSPI	0.11
solosky__pixl.js	0.09
RfidResearchGroup__ChameleonUltra	0.08
HEAVY
python3 - $I /tmp/x1k-oks /tmp/x1k-heavy.tsv /tmp/x1k-deal "$RUN" "$SLOT" "$NSLOTS" $A_ROWS <<'PY_DEAL' || { echo "ABORT: the deal"; exit 1; }
import sys
from pathlib import Path

inp, oks_file, heavy_file = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
out, run, slot, nslots, a_rows = Path(sys.argv[4]), sys.argv[5], int(sys.argv[6]), int(sys.argv[7]), sys.argv[8:]
SRC, PER = 4, 4  # 4 source part manifests; 4 parts per machine
NP = PER * nslots
assert 1 <= slot <= nslots
hl = [x.split("\t") for x in open(heavy_file).read().splitlines() if x.strip()]
heavy = [c[0] for c in hl]
est = {c[0]: float(c[1]) for c in hl}  # estimated hours of the row (measured in the first run, else by size)
assert len(heavy) == len(set(heavy)) == 273, f"HEAVY list: {len(heavy)} rows, {len(set(heavy))} names"
rank = {n: i for i, n in enumerate(heavy)}
done = {x.strip() for x in open(oks_file) if x.strip()}
a_set = set(a_rows)
assert len(a_set) == 11, f"expected 11 machine-A rows, got {len(a_set)}"
comments, parts, seen = {}, {}, {}
for k in range(1, SRC + 1):
    rows = []
    comments[k] = []
    for line in open(inp / f"manifest.x1k-p{k}.tsv").read().splitlines():
        if line.startswith("#"):
            comments[k].append(line)
        elif line.strip():
            name = line.split("\t", 1)[0]
            assert name not in seen, f"{name} is in p{seen[name]} and p{k}"
            seen[name] = k
            rows.append((name, k, len(rows) + 1, name in rank, line))
    parts[k] = rows
assert not sorted(a_set - set(seen)), f"machine-A rows not in the manifests: {sorted(a_set - set(seen))}"
assert not sorted(set(heavy) - set(seen)), f"HEAVY rows not in the manifests: {sorted(set(heavy) - set(seen))[:5]}"
assert not set(heavy) & a_set, "a machine-A row is in HEAVY"
unknown_ok = sorted(done - set(seen))
assert not unknown_ok, f"done-full/OK names not in the manifests: {unknown_ok[:5]} ({len(unknown_ok)})"
assert not done & a_set, f"a machine-A row has done-full/OK: {sorted(done & a_set)}"
# the fixed deal: independent of the done set
keep = {k: [r for r in parts[k] if r[0] not in a_set] for k in parts}


def by_rank(lists):
    """Row 1 of p1, p2, p3, p4, then row 2 of each, and so on (a list that ends drops out)."""
    res, i = [], 0
    while any(i < len(x) for x in lists):
        res += [x[i] for x in lists if i < len(x)]
        i += 1
    return res


heavy_rows = sorted((r for k in parts for r in keep[k] if r[3]), key=lambda r: rank[r[0]])
light_rows = by_rank([[r for r in keep[k] if not r[3]] for k in parts])
order = heavy_rows + light_rows
deal = {g: [] for g in range(1, NP + 1)}
load = {g: 0.0 for g in deal}
for r in heavy_rows:  # longest first, each to the part with the least load (LPT); ties: lowest part
    g = min(deal, key=lambda x: (load[x], x))
    deal[g].append(r); load[g] += est[r[0]]
for i, r in enumerate(light_rows):  # then row by row
    deal[i % NP + 1].append(r)
total = sum(len(v) for v in parts.values())
assert len(order) + len(a_set) == total, (len(order), total)
cols = next(c for c in comments[1] if c.startswith("# Columns:"))
out.mkdir(parents=True, exist_ok=True)
mine = range((slot - 1) * PER + 1, slot * PER + 1)
n_run = n_skip = 0
with open(out / "deal.tsv", "w") as d:
    d.write("part\tseq\tproject\tfrom_part\tfrom_row\theavy\tdone_full\n")
    for g, rows in deal.items():
        for j, r in enumerate(rows, 1):
            d.write(f"p{g}\t{j}\t{r[0]}\tp{r[1]}\t{r[2]}\t{int(r[3])}\t{int(r[0] in done)}\n")
for k, g in enumerate(mine, 1):
    rows = [r for r in deal[g] if r[0] not in done]
    n_run += len(rows); n_skip += len(deal[g]) - len(rows)
    with open(out / f"manifest.run.p{k}.tsv", "w") as f:
        f.write(f"# x1k full run {run}, slot {slot}: local part p{k} = deal part {g} of {NP} (R4-start-b.sh deal of "
                f"manifest.x1k-p1..p{SRC}.tsv minus {len(a_set)} machine-A rows; minus done-full/OK): heavy rows first, then u order.\n{cols}\n")
        for r in rows:
            f.write(r[4] + "\n")
    print(f"local p{k} = deal part {g}: {len(deal[g])} rows, {len(deal[g]) - len(rows)} with done-full/OK, "
          f"{len(rows)} to run ({sum(1 for r in rows if r[3])} heavy), first {rows[0][0] if rows else '-'}")
print(f"manifest rows {total}; machine A {len(a_set)}; dealt {len(order)} to {NP} parts "
      f"({sum(1 for r in order if r[3])} heavy); slot {slot}: {n_run} to run, {n_skip} with done-full/OK")
print("estimated hours of the heavy rows per deal part: " + " ".join(f"p{g} {load[g]:.0f}" for g in deal))
PY_DEAL
for K in 1 2 3 4; do R=/data$K/x1k/manifest.run.tsv
  mv -f /tmp/x1k-deal/manifest.run.p$K.tsv $R; chown ec2-user: $R
  echo "p$K: $(grep -c -v -e '^#' -e '^[[:space:]]*$' $R) rows to run"
done
cp /tmp/x1k-deal/deal.tsv $E/deal.tsv; chmod 644 $E/deal.tsv
# 5. start
echo $WORKERS > $E/workers
echo "started $(date -u +%FT%TZ) on $IID, run $RUN, slot $SLOT, full pipeline, $NCPU vCPU, $WORKERS workers per part" > $E/started
systemctl daemon-reload
systemctl enable --now x1k-watch.service >/dev/null 2>&1; systemctl start x1k-upload.timer x1k-live.timer x1k-finalize.timer
for K in 1 2 3 4; do systemctl reset-failed x1k@$K 2>/dev/null; systemctl start x1k@$K; done
{ cat $E/started; for K in 1 2 3 4; do echo "p$K: $(grep -c -v -e '^#' -e '^[[:space:]]*$' /data$K/x1k/manifest.run.tsv) rows"; done; echo "$t"; echo "$r"; } > /tmp/x1k-START
aws s3 cp /tmp/x1k-START $B/dataset-x1k/live/$RUN/START --only-show-errors
aws s3 cp $E/deal.tsv $B/dataset-x1k/live/$RUN/deal.tsv --only-show-errors
sleep 60
for K in 1 2 3 4; do echo "p$K: $(systemctl is-active x1k@$K) $(tail -1 /data$K/x1k/logs/run.log | cut -c1-200)"; done
echo "R4-b done $(date -u +%FT%TZ)"
