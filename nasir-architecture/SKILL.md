---
name: nasir-architecture
description: Use when writing/modifying C++ for the Nasir architecture.
version: 1.0.0
author: hermes-agent
license: MIT
metadata:
  hermes:
    tags: [cpp, nasir, nsrOpenSIL, flight-simulator, shared-memory, coding-style]
    related_skills: [gimbal-controller-dev, drone-flight-analysis]
---

# Nasir Architecture — Coding Style

The architecture is called **Nasir (نصیر)** — the `nsr` prefix in all Platform
identifiers derives from it. Pattern classification: **Blackboard / Shared Repository**
(POSA) with DDS-like data-centric traits — shared memory tables = blackboard, modules =
knowledge sources, notifiers + ID_CLOSE_ALL/ID_PAUSE_ALL = control component. Related
classes: Linda tuple space, Space-Based Architecture, data-centric pub/sub (DDS),
multi-process modular monolith. NOT microservices (single host, shared data plane,
coordinated build/deploy/lifecycle).

## When to Use

Load this skill whenever writing, extending, or modifying any C++ module in the
nsrOpenSIL repo (cloned at /home/oem/nsrOpenSIL, or the Platform submodule at
src/InCommon/Platform). Use it to match the existing architecture (shared-memory
Platform API), naming, formatting, logging, and build conventions so new code
integrates without friction.

Flight/simulator project (Iranian team). All modules are standalone C++ executables
linked against the shared-memory Platform library (`src/InCommon/Platform`, submodule,
prefix `nsr`). Modules talk to each other ONLY through Platform shared-memory buffers
+ notifiers — never direct calls across modules.

IMPORTANT: the Platform submodule is the reusable core. The sibling modules under
`src/` (SimParameters, AircraftDynamic-*, Controller-*, MapPlot, RealTimePlot,
SimpleCamSim, SimpleEarthRenderer, CamDistortion, UserInput) are OPTIONAL and
project-specific — they exist only in this repo, not in other consumers of Platform.
Never reference them as part of the Platform contract; in this skill they appear only
as concrete examples from this project.

## Shared-memory mechanisms (5 kinds)

All data lives in shared memory, declared via x-macro tables (see next section).
Every kind follows the same pattern: table file → `extern` pointers/IDs → runtime
API on those handles.

1. **NumBuffer (numeric channels)** — scalar/vector doubles per channel, time-stamped.
   Access: `getValue(ID_X)`, `setValue(ID_X, v)`, `getDataTime(ID)`,
   `getDataOnce(ID, default, last, has_new)`, `getDataValidity(ID)`.
   Channels of a vector are consecutive IDs (`ID_GT_GPS_LLA`, `+1`, `+2`).
   Read with timeout+newness: `getValue(ID_X, 0.5, is_new)`.
   ALWAYS access via symbolic `ID_*` constants — never hardcode raw numbers
   (`setValue(ID_GT_GPS_LLA+2, alt)`, not `setValue(23672, alt)`).

2. **RawBuffer (serial/raw byte stream)** — ring buffer for arbitrary byte data
   (serial ports, blobs). Declared as `extern RawBuffer3* name;` (e.g. `mLOGB`,
   `mVignetPathB`). API: `rbPush`, `rbPull`, `rbRePush`, `rbRePull`, `rbRollBack`,
   `rbGetRemainLength`, `rbGetRemainLengthBeforeChar`, `rbReset`, `rbErase`.
   Pull is per-reader (`int reader` arg); lookup by name: `getRawBufferByName()`.

3. **ImageBuffer (frames)** — ring of fixed-size frames + metadata + timestamps.
   Declared as `extern ImageBuffer* name;` (e.g. `DAY_CAMERA_IDEAL`).
   Write: `ibGetNextFrameForWrite()` → fill → `ibFinalizeWrite(time_s)`.
   Read: `ibGetLastFrameForRead()`, `ibGetFrameForReadAtTime()`, or per-reader
   `ibGetNextFrameForRead()` + `ibFinalizeNextFrameRead()`; `ibReaderResetToLast()`.
   Lookup by name: `getImageBufferByName()`.

4. **StructBuffer (typed structs)** — ring of fixed-size structs + timestamps.
   API: `sbPush(data, time_s)`, `sbRePush`, `sbGetLastBufferForRead`,
   `sbGetBufferForReadAtTime`, `sbGetBufferForPull`/`sbPull` (per-reader),
   `sbLast`, `sbGetSpecificStruct(index)`, `sbGetWrittenCount`,
   `sbGetNextBufferForWrite` + `sbFinalizeWrite`.

5. **Notif (notify/wait between processes)** — shared-memory condition variables.
   Class `InterProccNotifier`, declared as `extern InterProccNotifier* NT_X_NOTIF;`
   (e.g. `NT_SENSORS_NOTIF`, `NT_CAM_IDEAL_NOTIF`, `NT_AIRCRAFT_DYNAMIC_NOTIF`).
   API: `notify()` (returns trigger counter), `wait(timeout_sec)`,
   `waitIfNoNewNotif(last_trigger_number, timeout_sec)`. Producer calls
   `NT_X_NOTIF->notify()` after writing; consumers block in the while-loop condition.
   `notifyAll()` prevents lock on shutdown; `initNotifsByTable()`/`deinitNotifs()`
   run inside NativeOpen/NativeClose. Implemented with pthread_cond/mutex on Linux,
   HANDLE/mutex on Windows, both inside a SharedMemory segment.

## Architecture (notifier-driven modules)

The loop below is the notifier-driven pattern used by most modules. Display modules
(e.g. MapPlot in this project) may instead poll with no notifier:
`while (getValue(ID_CLOSE_ALL) < 0.5) { ... sleep 100ms }` — both are valid.

```
#include "nsrPlatform.h"   // everything: buffers, time, log, notif, matlib
#undef TAG
#define TAG "ModuleName:" // log tag convention

double DESIRED_DT = 1.0 / 200.0;  // or local loop rate

int main(int argc, char* argv[]) {
    NativeOpen();            // required FIRST (allocates shared memory)
    NativeSetSignalHandlers();
    ...
    static uint64_t last_trigger_number = 0;
    while (NT_X_NOTIF->waitIfNoNewNotif(last_trigger_number)
        && getValue(ID_CLOSE_ALL) < 0.5) {
        double time_s = myTime();
        double dt = calc_dt(time_s);
        if (getValue(ID_PAUSE_ALL) > 0.5) continue;
        if (dt <= 0.) continue;

        bool is_new;
        double v = getValue(ID_INPUT, 0.5, is_new);  // timeout+newness
        if (!is_new) continue;
        ...
        setValue(ID_GT_OUT, val);       // write outputs
        NT_X_NOTIF->notify();           // wake dependent modules
        synchronize_us(0, (int)(DESIRED_DT*1e6));
    }
    return 0;
}
```

Key API: `NativeOpen`, `NativeStep`, `NativeClose`, `NativeSetSignalHandlers`,
`myTime()`, `calc_dt()`, `synchronize_us()`, `getValue(ID[, timeout, is_new])`,
`setValue(ID, val)`, `getDataTime(ID)`, `getDataOnce(ID, default, last, has_new)`,
`getDataValidity(ID)`, `rescale(x, in_lo, in_hi, out_lo, out_hi)`, `normalize_angle()`.

Template notes:
- `ID_INPUT`/`ID_GT_OUT` in the template are example placeholders — use real IDs from
  the tables.
- Time source varies: `myTime()` (sim time) or `getDataTime(ID_X)` (timestamp of the
  triggering data — the Controller module uses the latter).
- `synchronize_us` paces time-driven modules (AircraftDynamic); notifier-driven
  modules pace via the wait itself and may omit it.

## Data tables (x-macro) — what is editable

**NEVER edit the minimal baseline tables inside the Platform submodule**:
- `src/InCommon/Platform/NumBuffer/nsrMinimalIndexTable.h` — system NumBuffers only
  (ID_LOG_TIME, ID_CLOSE_ALL, ID_PAUSE_ALL, ID_PRESSED_KEY)
- `src/InCommon/Platform/RawBuffer/nsrMinimalRawBufferTable.h` — system RawBuffers only
  (mLOGB, mInputDataPathB, mOutputLogPathB, LOG_BUFFER_LEN 10*1024)

New buffers/notifiers go into the EXTERNAL x-macro table files in the MAIN repo at
`src/InCommon/` (outside the Platform folder). Platform's CMake auto-detects their
existence and sets `HAVE_EXTERNAL_*_TABLE 1` + adds `../` to include dirs:

| File (src/InCommon/) | Macro | Line form |
|---|---|---|
| nsrIndexTables.h | ADD_BUFF | `ADD_BUFF(ID_GT_GPS_LLA, 23670, 3, 0, true, 0, "GT AC GPS Lat (deg)\tLon\tAlt(m ASL)\t")` — real line; `_id` is random in 0..32767 |
| nsrRawBufferTable.h | ADD_BUFF | `ADD_BUFF(mVignetPathB, 300)` — key offset BUFFER_SHARED_MEM_KEY_OFFSET |
| nsrImageTable.h | ADD_BUFF | `ADD_BUFF(DAY_CAMERA, 1920*1080*4, sizeof(RecommendedImageMetaData), 20)` — key offset IMAGE_SHARED_MEM_KEY_OFFSET |
| nsrNotifTable.h | ADD_NOTIF | `ADD_NOTIF(NT_SENSORS_NOTIF)` — key offset NOTIF_SHARED_MEM_KEY_OFFSET |
| nsrStructTable.h | ADD_BUFF | (expected by CMake HAVE_EXTERNAL_STRUCT_TABLE; file not in repo yet — the StructBuffer API is fully implemented in Platform, only the external table is missing; create it here when needed) |

ADD_BUFF signature: `(_elem, _id, _width, _savable, _log, _encrypted, _NAME)`.
- ID name = `ID_` + group (GT=ground truth, Eu, Gyro, Acc, RC, Controller…) + `_` + channel.
- The numeric `_id` values are RANDOM numbers, not sequential: when adding a buffer,
  pick a random ID within 0..32767 (65535/2) so two people adding buffers concurrently
  don't collide. The build-time Python checker (check_num_buffer_index_overlaps.py,
  run by x_build_all.sh) validates every table for duplicate/overlapping ID ranges.
- Channels of one logical vector are consecutive: `ID_GT_GPS_LLA`, `+1`, `+2`.
- Notifier names: `NT_<MODULE>_NOTIF` (NT_AIRCRAFT_DYNAMIC_NOTIF, NT_SENSORS_NOTIF, NT_CAM_IDEAL_NOTIF).
- Each external table defines its own shared-memory key offset — keep offsets unique and monotonic.
- Governance: every buffer is defined exactly once (single source of truth). The
  submodule's memory system is only ever changed via review (double-checked); project
  buffers/notifiers are added ONLY through the external tables in src/InCommon/ —
  never by editing the submodule's minimal tables.

## Naming conventions

| Item | Rule | Examples |
|---|---|---|
| Platform files/classes/functions | `nsr` prefix | nsrPlatform.h, nsrNumBuffer, nsrMathLib, nsrQuat |
| Module files | lowercase_with_underscores | cam_distortion.cpp, aircraft_dynamic.cpp, controller_multi_rotor.cpp (mapPlot.cpp is a MixedCase exception) |
| Classes | PascalCase | MBTilesReader, PController, ColoredNoiseGenerator |
| Functions | camelCase (mixed with lowercase ok) | NativeOpen, getValue, tile2lla, X2LAT |
| Macros/constants | SCREAMING_SNAKE | MAP_WIDTH, DESIRED_DT, JUMP_VALUE, TOTAL_BUFFER_LENGTH |
| Locals | snake_case, short | centerLat, time_s, last_trigger_number, is_new |
| Statics/globals | snake_case, `static` at file scope | static int mapHeight; static double lat_offset |

## Formatting

- 4-space indent, no tabs. Space after keywords: `if (`, `while (`, `for (`, `switch (`.
- Function braces on NEW line (Allman); class/control braces inline allowed.
- C++11 (CMAKE_CXX_STANDARD 11). `using namespace std;` + `using namespace cv;` in modules (no std:: prefixes).
- `static_cast<>` for conversions; `char *argv[]` / `double &lat` pointer-ref spacing varies — don't fight it.
- Comments: `//` line comments; Doxygen `/** @param @brief */` for Platform API; Persian comments common in Platform lib (with `@nsrStartFarsi` markers). Keep English in module code.
- File header convention: `//ALLAH` or `/** Besm ALLAH ... */` at top.

## Logging

```
#undef TAG
#define TAG "CamDist:"
LOGI(TAG, "format %f\n", val);  // also LOGV/LOGW/LOGE(LOG,TAG,...)
```
On desktop LOG* writes to logfile (LOGE forces LOGDUMP); on Android maps to __android_log_print.
printf/std::cerr for usage/help output is normal too.

## Adding a new module (step by step)

1. **Create the folder** `src/<ModuleName>/` with:
   - `<module_name>.cpp` — the main file (lowercase_with_underscores)
   - `CMakeLists.txt`
   - `README.md` (convention — several existing modules lack it; add one anyway)
   - `.gitignore` with `build` and `.vscode` (convention — CamDistortion has it; add it anyway)

2. **CMakeLists.txt template** (minimal; `Controller-MultiRotor` in this project is a
   concrete example of the same shape):

   ```cmake
   cmake_minimum_required(VERSION 3.10)
   project(<ExecName>)          # e.g. AircraftController
   set(CMAKE_CXX_STANDARD 11)
   set(CMAKE_CXX_STANDARD_REQUIRED ON)

   ##Add Platform library######################
   include_directories(../InCommon)
   include_directories(../InCommon/Platform)
   ############################################

   set(SOURCES <module_file>.cpp)
   add_executable(${PROJECT_NAME} ${SOURCES})
   target_link_libraries(${PROJECT_NAME} ${CMAKE_CURRENT_LIST_DIR}/../InCommon/Platform/build/libPlatform.a)
   target_include_directories(${PROJECT_NAME} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
   ```

   Platform is always referenced as `../InCommon` + `../InCommon/Platform` include dirs
   and the static lib at `../InCommon/Platform/build/libPlatform.a`. Add
   `find_package(OpenCV REQUIRED)` + link OpenCV if the module needs it (see the
   `CamDistortion` example in this project).

3. **main() template** — follow the Architecture section above: `NativeOpen()` first,
   `NativeSetSignalHandlers()`, the notifier while-loop, `synchronize_us` at the end.

4. **Register in the root scripts** (all four):
   - `x_build_all.sh` — append the 5-line block (it also runs the overlap checker first):
     ```
     folder="./src/<ModuleName>"
     mkdir -p "$folder/build"
     cd "$folder/build"
     cmake ..
     make -j${NPROC}
     cd -
     ```
   - `x_run_all.sh` — launch the executable as a background job (`./... &` then `cd -`)
     at the right point in the startup order: SimParameters first, then simulators
     (AircraftDynamic, Sensors), controllers, plotters/renderers, and **UserInput
     always LAST** (it owns key strokes). setAddresses must run before anything else.
   - `x_stop_all.sh` — no change needed: shutdown is `buffwrite ID_CLOSE_ALL 1` and
     every module must honor ID_CLOSE_ALL in its loop.
   - `x_clean_all.sh` — append `rm -rf ./src/<ModuleName>/build/*`.

Startup order in THIS project's x_run_all.sh (module names are optional/project-specific;
preserve the relative order of whatever modules exist): removeSharedMemory →
setAddresses → sleep 1 → SimParameters → sleep 1 → AircraftDynamic → AircraftSensors →
Controller → plots (MapPlot/RealTimePlot) → renderers (SimpleEarthRenderer,
CamDistortion) → imageBufferShow/video writers → UserInput last.

## CMake / build / CI style

- Build environment — Platform ONLY (minimal):

  ```bash
  sudo apt-get install -y build-essential cmake
  ```

  That's all: pugixml and Yaml are vendored inside Platform (Settings/), python3
  (for the overlap checker) is preinstalled, and no OpenCV/EGL/JSBSim/python3-dev is
  needed for Platform — those are only for the optional modules. Compile via
  `x_build_all.sh` (no manual cmake). The full-module build additionally needs:
  pkg-config libopencv-dev libegl-dev libgles-dev libx11-dev libsdl2-dev
  libsqlite3-dev python3-dev + jsbsim-devel .deb (see GitHub releases), and
  RealTimePlot additionally hardcodes python3.10.

- Per-module CMakeLists.txt, `cmake_minimum_required(VERSION 3.10)`,
  `project(X CXX)`, links `../InCommon/Platform/build/libPlatform.a` + OpenCV.
- Platform CI (gitlab-ci.yml): gcc docker, cmake+make, then cppcheck (approx. command —
  the repo's `x_cpp_check.sh` also passes an addon flag and redirects to build/cppcheck.xml):
  `cppcheck --project=build/compile_commands.json --enable=warning --inconclusive --suppressions-list=CppCheckSuppressions.txt --xml`
  (run via `x_cpp_check.sh`).
- Build-time ID validation — `x_build_all.sh` runs before compiling:
  `python3 src/InCommon/Platform/NumBuffer/check_num_buffer_index_overlaps.py src/InCommon/nsrIndexTables.h`
  The checker exits non-zero on: (a) overlapping ID ranges between buffers, (b)
  headline column-count mismatch (number of `\t` in NAME must equal buffer width).
  Note: x_build_all.sh has no `set -e`, so a non-zero exit is printed but does NOT
  halt the build — and the checker only validates entries with `_log=true`
  (system `_id=0` buffers like ID_CLOSE_ALL are skipped). Always run it before
  pushing table changes.
- Build census: x_build_all.sh has 13 blocks (Platform + 12 modules); all build
  cleanly except RealTimePlot — its CMakeLists hardcodes python3.10 (needs
  python3.10-dev; on Ubuntu 24.04 / python3.12, python3-dev alone is not enough).
- Linux scripts `x_build_all.sh`, `x_run_all.sh`, `x_stop_all.sh`, `x_clean_all.sh`;
  Windows `y_*.bat`. New modules should get entries in these.

## Nasir architecture — strengths & weaknesses

Closest industry relative: **ARINC 653** (avionics IMA standard): isolated partitions on
one CPU, inter-partition communication via sampling/queuing ports, health monitoring.
Same spirit (isolated units + shared data plane on one machine) but ARINC 653 adds
guaranteed temporal partitioning (fixed cyclic scheduling windows) and safety
certification (DO-178C) — Nasir runs as plain processes on a general OS without those.

Strengths:
- Process-level fault isolation: each module is an OS process; a crash (e.g. an OpenGL
  driver bug in a renderer) doesn't take down siblings.
- Decoupled data plane: modules only touch shared-memory buffers + notifiers, so a
  module can be added/removed/replaced without editing others.
- Single source of truth: x-macro tables define every buffer once; IDs, log headlines
  and docs (data_diagram_generate.py) can't drift apart; build-time overlap check
  (check_num_buffer_index_overlaps.py) blocks duplicate ID ranges.
- Real-time-friendly data model: ring buffers, per-reader cursors, timestamps,
  DATALOST detection, wait/notify trigger counters.
- Efficient sync: pthread_cond/HANDLE in shared memory — consumers block, no polling.
- Zero-copy, low latency: no serialization/network on the main data path.
- Cross-platform: Linux/Windows/Android (log maps to logcat).

Weaknesses:
- No temporal guarantees: general OS scheduling; a CPU-hogging module can starve
  others; no fixed time windows or budget enforcement (unlike ARINC 653).
- Single-host only: shared memory doesn't span machines; scaling = bigger machine.
- No type safety / unit discipline: channels are double or void*; a wrong ID or unit
  (deg vs rad, m vs ft) is a silent runtime bug that propagates between processes.
- Manual key offsets (0x200/0x300/0x400/0x500): a cross-table collision corrupts
  shared memory silently — the overlap checker validates only nsrIndexTables.h, not
  the key offsets.
- No version handshake: all processes must run the same build; mixed builds corrupt
  data — removeSharedMemory is a workaround, not a protocol.
- Script-based orchestration with acknowledged race conditions (`sleep 1` between
  startups in x_run_all.sh); no supervision/auto-restart of crashed modules (the
  WatchDog module — NativeWatchDogReset — is reset-based, not a process supervisor).
- Global tables = coordination cost: any buffer change requires all modules to
  rebuild and restart together.

## Applicability — where Nasir fits

Good fit (data-centric, time matters):
- Simulation (SIL) and hardware-in-the-loop (HIL) on one machine — heterogeneous
  real-time modules exchanging data deterministically.
- Single-host avionics/mission systems: sensor fusion, INS/GPS navigation, autopilot.
- Test rigs: add/remove modules (sensor sims, loggers, replay) without touching others.
- Data recording/replay/analysis — everything is time-stamped and table-logged.
- GUI: ONLY light (viewer/dashboard) GUI fits — map, plots, camera views, telemetry:
  one-way bus→GUI reads, multiple independent displays over one data source (MapPlot,
  RealTimePlot, SimpleEarthRenderer, imageBufferShow in this project). A simple light
  UI is buildable with just a few commands (e.g. OpenCV namedWindow/imshow-style
  viewers, simple dashboards reading the bus). Anything beyond light display is a
  poor fit.

Poor fit:
- Any GUI heavier than light display (interactive editors, rich control panels, forms):
  frameworks are event-driven; Nasir is data-driven + time-sliced.
  NumBuffer is last-value-wins, so events (click/drag/focus/gesture) lose event
  semantics; widget state belongs to the UI, not a global bus; the notifier while-loop
  fights the GUI event loop in the same process.
- Distributed/multi-host systems: shared memory does not cross machines.
- Independent deploy/scale needs (cloud, web backends): use microservices/SOA.
- Multiple teams evolving the data contract in parallel: global schema churn.
- Data isolation/security between components: global bus = everyone reads everything.
- Business/CRUD applications: databases + services, not a blackboard.
- Certified safety-critical systems without temporal guarantees (unless evolving toward
  the ARINC 653 model).
- Simple single-process apps: the architecture overhead is unjustified.

Bottom line: Nasir is for systems where DATA is central and TIME matters. It displays
data well but does not do rich interaction.

## Pitfalls

- NEVER call Platform functions before NativeOpen() — segfault.
- NEVER touch nsrMinimalIndexTable.h (submodule baseline); add buffers/notifiers only in the external tables under src/InCommon/ (nsrIndexTables.h, nsrRawBufferTable.h, nsrImageTable.h, nsrNotifTable.h).
- Loop must not spin hot: use notifier wait + `synchronize_us`; honor ID_PAUSE_ALL/ID_CLOSE_ALL.
- Don't cross-module call; everything is shared-memory + notifier.
- Submodule Platform has its own repo (hamgit.ir:ansar/Platform.git) — keep its style (nsr prefix, Farsi docs) when touching it.
- CppCheckSuppressions.txt already ignores third-party files (pugixml, Yaml, catch_amalgamated) — don't add your own files there without reason.
- docs/data-diagram-*.md/html are GENERATED by data_diagram_generate.py — edit the generator, not the docs.