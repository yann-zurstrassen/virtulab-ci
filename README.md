# 🛡️ VirtuLab CI

> **Continuous firmware security and safety verification on every PR, powered by emulation.**

VirtuLab CI builds your C firmware on every pull request, runs its tests on an emulated Cortex-M, and adds the checks a bench run is too slow to repeat: fuzzing, fault injection and coverage. Results land in one sticky PR comment. Footprint tracking and unit tests are the free hook; the security evidence is the point.

Emulation is the **fast layer** of the test pyramid. Hardware-in-the-loop (HIL) stays the final gate. This page says what ran, on what machine, and where emulation stops.

---

---

## 🚀 Quick start: pick board, sensors and tests, get CI

Nothing to install except Docker (or the Arm toolchain, QEMU and a C compiler). `virtulab` runs in its image when your machine lacks a tool.

```sh
virtulab ui            # opens a page: pick a board, protocols, sensors and tests
# or, from the terminal:
virtulab init          # the same questions, answered in the shell
virtulab check         # validate board, wiring and test selection before running
virtulab run           # run the selected tests (--only unit,fuzz / --skip fault)
virtulab ci --write    # (re)write the CI file
virtulab demo          # watch the whole flow, with three broken changes that get caught
```

One file, `virtulab.yml`, drives all of it (board, sensors, tests, CI):

```yaml
version: 1
board: stm32f4_discovery
modules:
  temp: { model: tmp108, bus: i2c1, address: 0x48 }
  baro: { model: bmp180, bus: i2c1 }
tests:
  unit: {}
  footprint: { flash_increase: 4K, ram_increase: 2K }
  coverage: { min_lines: 80 }
  fuzz: { harness: fuzz/fuzz.c, sources: [src/parser.c], seconds: 20 }
```

CI is then one step (`virtulab ci --write` creates the whole workflow), or one command for any other CI:

```yaml
- uses: yann-zurstrassen/virtulab-ci@v1
```
```sh
docker run --rm -v "$PWD:/workspace" ghcr.io/yann-zurstrassen/virtulab-ci:1 run
```

| You pick | Options today |
| :--- | :--- |
| Board | 9 (`virtulab catalog`). Only `stm32f4_discovery` (Renode) can carry sensors; the 8 QEMU boards run the CPU only |
| Protocol | I²C, SPI, UART (SPI and UART buses exist on the board; no SPI or UART sensor model ships yet) |
| Sensor | TMP108 (datasheet model), BMP180 (Renode's model, lightly tested). Both I²C |
| Tests | unit, footprint, coverage, fuzz, fault injection. Fault injection needs a QEMU board |

The sample firmware `init` can create (`--template starter`) is built to pass on its first run. Its sensor drivers are written for `i2c1`. A full recorded run is in [`docs/demo-run.txt`](docs/demo-run.txt). The setup page is local only (127.0.0.1, random token).

> **Honest limits.** The GitHub and GitLab files are generated and structurally validated, and the same steps run in the Docker image locally, but the workflows have not been executed on GitHub. Fuzzing is host-side, fault injection is single instruction skip, coverage is line and branch. See [docs/FIDELITY.md](docs/FIDELITY.md).


## 🎯 Who it's for

Firmware teams in **medical, automotive and industrial** products, and any team of **20+ engineers** where the bench is shared and slow.

| Problem | What VirtuLab CI does about it |
| :--- | :--- |
| **Bugs the bench misses.** A bench run rarely sends a 33-byte payload or skips one instruction | Fuzzes the parser and sweeps single-instruction skips through the PIN check on every PR |
| **Security evidence arrives after the bench.** Findings show up late, when changes are expensive | Coverage, fuzz and fault-injection results are in the PR before anyone books bench time |
| **Regressions nobody sees.** Flash and RAM creep up, tests silently break | Footprint delta against the base branch, with budgets that fail the build |

It does not replace HIL or bench qualification. Chips and dev boards are cheap; waiting for them, and finding bugs late, is the cost.

## 📸 Live PR showcase

Five demo branches, each off `feat/security-positioning`. **The PRs are not opened on GitHub** (`gh` is not installed on the authoring machine), so each row links to the PR text and its real sticky comment in this repo. Every number below comes from a run on the machine listed under [How it works](#️-how-it-works).

| PR | Change | Real result | Details |
| :--- | :--- | :--- | :--- |
| 1 · `demo/pr1-passing` | Add a Celsius→Fahrenheit helper | ✅ 30/30 tests · Flash **+236 B** · RAM ±0 B · fuzz 0 crashes · no bypass found | [pr1.md](docs/demo-prs/pr1.md) |
| 2 · `demo/pr2-memory-regression` | Add an 8 KiB history buffer | ⚠️ 29/29 tests pass, but RAM **+8,200 B** exceeds the 2 KiB budget, so the build fails | [pr2.md](docs/demo-prs/pr2.md) |
| 3 · `demo/pr3-failing-test` | "Simplify" the CRC-16 start value | ❌ 3 tests fail, reported with file and line, e.g. `test/test_crc.c:29` | [pr3.md](docs/demo-prs/pr3.md) |
| 4 · `demo/pr4-fuzz-overflow` | Relax the parser length check (off-by-one) | ✅ 28/28 unit tests, but ❌ **fuzzing finds a crash** after 135 executions; 37-byte input committed in `fuzz/crashes/` | [pr4.md](docs/demo-prs/pr4.md) |
| 5 · `demo/pr5-fault-injection` | Drop the redundant PIN compare "to save flash" | ✅ 28/28 tests · Flash **−56 B**, but ❌ **2 of 36** single-instruction skips grant a wrong PIN | [pr5.md](docs/demo-prs/pr5.md) |

PRs 4 and 5 are the point: every unit test and the footprint check are green, and the security checks still fail.

## 🤖 Real example sticky comment

This is the comment for PR 5, produced by `make -k footprint coverage fuzz fault report` and assembled by `tools/ci_report.py`, the script the CI `report` job runs. The collapsed emulator-log and symbol-table sections are left out here; the full text is in [pr5.md](docs/demo-prs/pr5.md). **The GitHub Actions workflow itself has not been run**, so this comment was produced locally, not posted by CI.

> ### 🤖 VirtuLab CI Report — `lm3s6965evb` (Cortex-M3, QEMU)
>
> **Status:** ✅ PASSED · Emulation `0.05s`
>
> | Metric | Current | Δ vs `a39c1bb` | Usage |
> | :--- | ---: | ---: | :--- |
> | **Flash** | `5,856 B` | -56 B 📉 | 2.2% of 256 KiB |
> | **RAM** | `236 B` | ±0 B | 0.4% of 64 KiB (static) |
> | **Unit tests** | `28 / 28` | — | ✅ 0 failed |
>
> ### 🛡️ Security & safety checks
>
> | Check | Result | Details |
> | :--- | :--- | :--- |
> | Coverage (unit tests) | `93.9%` lines · `81.3%` branches | 138/147 lines, 65/80 branches taken at least once (gcov, native build) |
> | Fuzzing (`parser`) | ✅ 0 crashes | 53,908,480 execs in 10.0s, seed 1; 0 known crash input(s) reproduced. Host-side parser fuzzing. |
> | Fault injection (`auth`) | ❌ auth bypass reachable by single instruction skip | 2 of 36 skipped instructions grant a wrong PIN |
>
> Fidelity: see [docs/FIDELITY.md](docs/FIDELITY.md). Emulation is the fast layer; hardware-in-the-loop stays the final gate.

## 🔥 Features

| Feature | What it does | Status |
| :--- | :--- | :--- |
| 🧪 **Fuzzing** | Deterministic mutation loop over `parser_parse()` with ASan/UBSan, a guard canary and a parse→encode round-trip property. Known crash inputs in `fuzz/crashes/` are replayed first | ✅ ran. **Host-side fuzzing of the parser logic, not full-system fuzzing.** AFL++/libFuzzer: 🚧 PLANNED |
| 💥 **Fault injection** | QEMU + GDB: skip one instruction at a time inside `src/auth.c`, rerun the probe, report any wrong-PIN grant | ✅ ran. Single skip, first execution only. Not a model of physical glitches |
| 📈 **Coverage** | `make coverage`: native gcov build of the unit tests, line and branch summary | ✅ ran. **Line and branch only, no MC/DC** |
| 📊 **Footprint** | Flash/RAM from the real ELF, delta against the base ref, budgets that fail the build | ✅ ran |
| 🧩 **Modular peripheral models** | Swap the sensor model with one make variable (below) | 🧪 MOCKED at the HAL layer, link-time |
| 🛡️ **Deterministic exit** | `main()`'s return value becomes the exit code via QEMU semihosting; no hung emulators | ✅ ran |
| 🖊️ **Inline annotations, HardFault reports** | Engine features from the earlier versions ([engine reference](docs/ENGINE.md)) | Existing, not re-verified in this work |

### 🧩 Same tests, different sensor model (60 seconds)

The sensor reaches the firmware through a small HAL. One config line per model picks which one is linked:

```text
$ cat targets/sensor_nominal.cfg
# Healthy sensor: slow drift around 21.5 degC.
SENSOR_MODEL := src/hal/sensor_hal_nominal.c
$ cat targets/sensor_faulty.cfg
# Failing sensor: three good samples, then the reading freezes.
SENSOR_MODEL := src/hal/sensor_hal_faulty.c
```

```text
$ make test SENSOR=nominal   (filtered to model, size and sensor test lines)
  src/hal/sensor_hal_nominal.c
📊 Flash 5,912 B / 256 KiB · RAM 236 B / 64 KiB (text 5,908, data 4, bss 232)
test/test_sensor.c:49:test_sensor_first_sample_is_about_room_temperature:PASS
test/test_sensor.c:50:test_sensor_stays_healthy_over_repeated_samples:PASS
test/test_sensor.c:51:test_sensor_rejects_null_arguments:PASS
✅ PASSED in 0.04s — 28/28 tests passed
make exit code: 0

$ make test SENSOR=faulty   (filtered to model, size and sensor test lines)
  src/hal/sensor_hal_faulty.c
📊 Flash 5,912 B / 256 KiB · RAM 236 B / 64 KiB (text 5,908, data 4, bss 232)
test/test_sensor.c:49:test_sensor_first_sample_is_about_room_temperature:PASS
test/test_sensor.c:32:test_sensor_stays_healthy_over_repeated_samples:FAIL: Expected 0 Was 4 sensor reported a fault while sampling
test/test_sensor.c:51:test_sensor_rejects_null_arguments:PASS
❌ FAILED in 0.03s (exit code 1) — 27/28 tests passed
make exit code: 2
```

The lines above are filtered from the full runs in [`docs/modularity-run.txt`](docs/modularity-run.txt). The nominal model drifts around 21.5 °C; the faulty one freezes after three samples, and the firmware's stuck-value check turns that into `SENSOR_ERR_STUCK` (4), which the test catches.

> 🧪 **MOCKED, and not the same binary.** These are software stand-ins behind a HAL, selected **at link time**, so the two runs use two ELFs that differ only in the model. They are not QEMU devices, and they do not exercise an I2C driver or bus timing. A bus-level device model needs an emulator that can attach devices (the Renode path in [`docs/ENGINE.md`](docs/ENGINE.md); 🚧 not run in this work).

## ⏱️ Team time-gain

Team-level time savings depend on your numbers, not ours. This repo ships a calculator for the arithmetic and **claims no result**:

```
hours saved / week = devs × PRs per dev per day × days per week × avg bench wait (h) × rerun rate × caught share
```

`rerun rate` is the share of PRs that need an extra bench run. `caught share` is how many of those reruns emulation would have caught earlier. The example below uses **illustrative inputs, not measurements**:

```text
$ python3 tools/roi.py --devs 20 --prs-per-day 1 --bench-wait-hours 2 --rerun-rate 0.2 --caught-share 0.5
ASSUMPTIONS (yours, not measured):
  developers            20
  PRs / dev / day       1
  working days / week   5
  avg bench wait (h)    2
  rerun rate            0.2
  caught-share          0.5
hours saved per week: 20.0
```

**Measured, for scale.** Wall-clock time of each step from a clean clone on one machine (Apple M4 Pro, 14 cores, macOS, one run each; see [`docs/runs/`](docs/runs/)):

| Step | Wall time |
| :--- | ---: |
| `make test` (compile, link, emulate 28 tests) | 0.6 s |
| `make coverage` | 0.8 s |
| `make fuzz` | 10 s (the time budget; CI is set to 60 s) |
| `make fault` (56 skipped instructions, each a QEMU + GDB run) | 40 s |

These say how long the checks take on a laptop. They say nothing about your bench queue.

## 🧭 Where emulation stops and HIL starts

Emulation is the fast layer: logic, memory-safety, boot, footprint and software fault handling on every PR. It cannot see timing, interrupt latency, flash wear, clock tree, DMA contention, analog behaviour or silicon errata. HIL covers those and stays the final gate.

Test pyramid and a table of which bug classes each layer catches: **[docs/WHERE_EMULATION_STOPS.md](docs/WHERE_EMULATION_STOPS.md)**.

## 🔬 Fidelity & trust

Emulators can be wrong, so this repo says where. For `lm3s6965evb`, the device list comes from QEMU's own `info qtree`/`info mtree` dump ([raw](docs/qemu-lm3s6965evb-devices.txt)), not from memory:

| Status | What it covers |
| :--- | :--- |
| **modeled** | core, NVIC, SysTick, flash (as ROM), SRAM, system control, 7 GPIO ports, 3 UARTs, SSI, 2 I2C, 4 timers, ADC, watchdog, Ethernet |
| **stubbed** | PWM, QEI0/1, analogue comparator, hibernation, flash controller |
| **not modeled** | DMA controller, external sensors |
| **exercised by this repo's tests** | core, flash/SRAM, semihosting. **No peripheral** |

Known divergences from real hardware and what to validate on the bench: **[docs/FIDELITY.md](docs/FIDELITY.md)**. When emulator and bench disagree, the bench is right.

## ⚙️ How it works

```
      pull request / push
              │
              ▼
┌──────────────────────────── GitHub Actions: jobs run in parallel ───────────────────────────┐
│                                                                                             │
│  build-test      footprint        coverage      fuzz              fault-injection           │
│  arm-none-eabi   build base ref   host gcov     host parser       QEMU + GDB: skip one      │
│  -gcc, link,     + this PR,       line and      mutation loop,    instruction at a time     │
│  run unit tests  Flash/RAM Δ,     branch %      ASan + UBSan,     in src/auth.c, rerun a    │
│  in QEMU         budgets                        replay known      probe, flag any           │
│  (semihosting                                   crash inputs      wrong-PIN grant           │
│   exit code)                                                                                │
└───────┬────────────────┬──────────────┬──────────────┬───────────────────┬──────────────────┘
        └────────────────┴──────────────┴──────┬───────┴───────────────────┘
                                               ▼   one result line per job in .ci/
                         tools/ci_report.py ──▶ one sticky PR comment
                                               ▲
                    HIL / bench: final gate, not part of this repo
```

The unit tests, footprint and fault injection run on the emulated target through the repository's engine (`virtulab/`); coverage and fuzzing run natively on the host. Everything in this README was run locally on **Apple M4 Pro, macOS, QEMU 11.1.1, arm-none-eabi-gcc 15.3.1, Apple clang 21**. The GitHub Actions workflow is written and syntax-checked (Ruby's YAML parser; `actionlint` was not available), but **has not been run on GitHub**.

## 🛠️ Quick start

From a clean checkout, one command:

```sh
make test          # build with -Wall -Wextra -Werror -Wconversion and run 28 tests in QEMU
make help          # coverage, fuzz, fault, footprint, report
```

Needs `python3`, `arm-none-eabi-gcc`, `qemu-system-arm`, a host C compiler, and for `make fault` an Arm-capable GDB (`arm-none-eabi-gdb` or `gdb-multiarch`).

The CI jobs call exactly those targets. Excerpt of [`.github/workflows/firmware-ci.yml`](.github/workflows/firmware-ci.yml):

```yaml
  build-test:
    name: Build & unit tests (QEMU)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install toolchain and emulator
        run: sudo apt-get update && sudo apt-get install -y --no-install-recommends $TOOLS
      - name: make test
        run: make test

  fault-injection:
    name: Fault injection (single instruction skip)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install toolchain, emulator and GDB
        run: sudo apt-get update && sudo apt-get install -y --no-install-recommends $TOOLS
      - name: make fault
        run: make fault
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: fragment-fault
          path: .ci/fault.txt
          if-no-files-found: ignore
```

The packaged GitHub Action (`uses: yann-zurstrassen/virtulab-ci@v1`: tests and footprint only, no fuzz or fault injection) is documented in [docs/ENGINE.md](docs/ENGINE.md). 🚧 It was not re-run in this work.

## 🎯 Supported targets

| Target | Emulator | Status |
| :--- | :--- | :--- |
| `lm3s6965evb` (Cortex-M3) | QEMU | ✅ Runs the full demo here: unit tests, footprint, fault injection (coverage and fuzz run on the host) |
| `lm3s811evb`, `stm32vldiscovery`, `netduinoplus2`, `microbit`, `mps2-an385`, `mps2-an386`, `mps2-an500` | QEMU | ✅ The engine's CRC example passes on each ([`docs/runs/engine-tests.txt`](docs/runs/engine-tests.txt)). 🚧 PLANNED for the security demo: not run |
| `stm32f4_discovery` + I2C sensor | Renode | 🚧 PLANNED here: Renode is not installed on the authoring machine ([`docs/ENGINE.md`](docs/ENGINE.md)) |
| Any chip by part number, Zephyr/CMake/PlatformIO projects | n/a | 🚧 PLANNED, see [ROADMAP.md](ROADMAP.md) |

Everything not marked ✅ above has no run behind it in this repo. Every assumption, skipped item and mocked piece is in [docs/DECISIONS.md](docs/DECISIONS.md).

## 🤝 Bring VirtuLab CI to your firmware team

Want to cut physical bench-testing bottlenecks, stop firmware bloat and speed up PR reviews for your embedded team?

* 🌐 **Website:** [virtulab.io](https://virtulab.io) *(demo)*
* ✉️ **Contact:** [sales@virtulab.io](mailto:sales@virtulab.io)
