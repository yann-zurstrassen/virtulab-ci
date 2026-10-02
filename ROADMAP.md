# 🗺️ VirtuLab CI Roadmap

**Goal:** a firmware team adds VirtuLab to the CI they already have and keeps their editor, build system and toolchain habits. They describe their firmware once (chip, build, devices, budgets) and every push is built, tested on emulated hardware and reported, with no bench and no CI scripting.

Today VirtuLab works well for projects shaped like [`examples/`](examples): VirtuLab compiles source globs itself, links its own startup code, and runs on one of 9 boards. Real projects use CMake, Make, PlatformIO, STM32Cube or Zephyr, bring their own HAL, startup file and linker script, and target a specific part number. This roadmap closes that gap.

Phases are ordered by what blocks adoption. Items within a phase can be worked on in parallel.

---

## Phase 1: Fit existing projects

Without this phase, most real firmware repositories cannot adopt VirtuLab at all.

### 1.1 Bring your own build

Run the project's build command and take the ELF it produces, instead of compiling globs.

```yaml
build:
  command: cmake --preset test && cmake --build build/test
  elf: build/test/firmware_tests.elf
```

- Footprint, symbol diff, emulation, `addr2line` and the report all work from the ELF unchanged.
- The baseline runs the same command in the exported baseline tree (`baseline.py`).
- Compiler diagnostics are still parsed from the command's output, so annotations keep working.
- The glob build stays as the zero-config option.

**Touches:** `build.py` (new `build_command()` path next to `build()`), `baseline.py`, `cli.py`, `action.yml`.
**Done when:** `examples/thermostat` builds and passes through a CMake project, including the baseline delta.

### 1.2 Runtime as a library

In "bring your own build" mode the project keeps its own vector table and startup code, so the runtime needs to split in two:

- **`virtulab_io`:** console, `vl_exit`, `vl_sim`, `vl_fault_report`, and the test framework. No vector table, no `Reset_Handler`.
- **`startup.c`:** optional, kept for zero-config projects.

Ship `virtulab_io` as a CMake package (`virtulab::io`), a PlatformIO library and plain sources. Document the one-line `HardFault_Handler` hook-up for projects that keep their own handlers.

**Touches:** `virtulab/runtime/`, new `virtulab/runtime/CMakeLists.txt` and `library.json`.
**Done when:** an STM32Cube-generated project with its own `startup_stm32*.s` reports faults and exit codes through VirtuLab.

### 1.3 Project config file: `virtulab.yml`

One file at the repository root describes the firmware. The CLI, the GitHub Action and the Docker image all read it, so no CI system duplicates settings.

```yaml
chip: STM32F407VG          # or board: lm3s6965evb
build:
  command: ...             # or sources / include_dirs / cflags
  elf: ...
peripherals: board.repl
timeout: 30s
budgets:
  flash_increase: 2K
  ram_increase: 512
```

- Precedence, lowest to highest: file, then action inputs or CLI flags.
- Unknown keys are an error, so typos don't fail silently.
- Several targets in one file (`targets:` list) map to a board matrix and separate `report_id`s.

**Touches:** `cli.py` (new `options_from_file`), README, `action.yml`.
**Done when:** the CI setup for both examples is `uses: yann-zurstrassen/virtulab-ci@v1` with no inputs.

---

## Phase 2: Target the firmware's actual chip

### 2.1 VirtuLab console device

Replace the per-family UART code in `startup.c` (`VL_CONSOLE_STM32_USART`) with a `VirtuLab.Console` peripheral in the device library. It sits at a fixed reserved address and has a TX register and an exit register.

- The same runtime code then works on every Renode chip: no USART register variants for F4, L4/H7 and nRF.
- Exit becomes a real signal from the peripheral, replacing the `VIRTULAB_EXIT:` sentinel and the 50 ms log polling in `emulator.py`.
- Firmware UARTs stay free for the code under test.

**Touches:** new `virtulab/devices/Console.cs`, `startup.c`, `emulator.py`, `boards.py`.

### 2.2 Chip catalog instead of a board list

Users name a part number, not a dev board. Replace the hand-written entries in `boards.py` with data:

```yaml
# virtulab/chips/stm32l476rg.yml
cpu: cortex-m4f
flash: { origin: 0x08000000, size: 1M }
ram:   { origin: 0x20000000, size: 128K }
renode: platforms/cpus/stm32l4.repl
qemu: null
```

- Real Flash and RAM limits, so "does it fit?" matches the part being bought.
- Initial families: STM32 F0/F1/F4/F7/L0/L4/H7, nRF52832/nRF52840, SAMD21, then RISC-V (ESP32-C3).
- Dev boards (`board:`) stay as aliases for a chip plus its on-board devices.
- Every catalog entry runs in the e2e suite, as boards do today.

**Touches:** `boards.py`, new `virtulab/chips/`, `Dockerfile` (SVD cache for each family).

### 2.3 Grow the device library

More datasheet-accurate models, following the approach in [`TMP108.cs`](virtulab/devices/TMP108.cs): SPI NOR flash, IMUs, power monitors, EEPROMs. Then generate models from datasheets.

Each model ships with a firmware test in `tests/` that checks it against the datasheet register map.

---

## Phase 3: Install anywhere, set up in minutes

### 3.1 `pipx install virtulab` with a Docker backend

- Publish the engine to PyPI. It is stdlib-only, so it has no dependencies.
- When the Arm toolchain, QEMU or Renode are missing from `PATH`, `virtulab run` runs itself inside `ghcr.io/yann-zurstrassen/virtulab-ci` with the project mounted. Developers keep their OS and editor and need only Docker.
- Local runs and CI use the same image, so a local pass means a CI pass.

**Touches:** new `pyproject.toml`, `cli.py` (container re-exec), `release.yml` (PyPI publish job).

### 3.2 `virtulab init`

1. Detect the build system: `CMakeLists.txt`, `platformio.ini`, `*.ioc`, Zephyr `prj.conf`, `Makefile`.
2. Read the MCU from it: PlatformIO `board`, the Cube `.ioc` part number, Zephyr board, or `-mcpu` and device defines.
3. Write `virtulab.yml` and the CI file for the detected host: `.github/workflows/virtulab.yml` or `.gitlab-ci.yml`.
4. Run once and print the report.

**Done when:** a fresh PlatformIO STM32 project goes from `virtulab init` to a passing CI run with no manual edits.

---

## Phase 4: Every CI, not just GitHub

- **JUnit XML** report next to `report.md`, so GitLab, Jenkins and Azure DevOps show test results natively. Add per-test timing.
- **GitLab CI/CD component:** `include: component: …/virtulab@1`, with MR comments through the GitLab API alongside `github.py`.
- **Footprint history** across `main`, with trend charts in the report.
- **Scenario files:** change sensor values on a timeline without writing C, by driving `vl_sim` commands from YAML.

---

## Validation track (runs alongside all phases)

Onboard 3–5 real open-source firmware repositories, at least one each:

| Build system | Stack |
| :--- | :--- |
| CMake | STM32 HAL (Cube-generated) |
| PlatformIO | Arduino or bare STM32 |
| Zephyr | west, nRF52 |
| Make | CMSIS, no vendor HAL |

Record every point where setup needs a manual step or a workaround, and feed it back into the phases above. A phase is complete only when the relevant reference projects run without workarounds.
