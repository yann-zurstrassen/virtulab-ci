# 🗺️ VirtuLab CI Roadmap

**Goal:** a firmware team describes its hardware once (the chip, the modules on the board and how they're wired) and gets a virtual board before any PCB exists. **No vendor IDE is needed at any point.** VirtuLab generates the project, builds it, runs it on the virtual board, debugs it from any editor and later flashes the real board. Every push is built, tested on the virtual board and reported, and the CI setup is a single line:

```yaml
- uses: yann-zurstrassen/virtulab-ci@v1
```
```sh
docker run --rm -v "$PWD:/src" ghcr.io/yann-zurstrassen/virtulab-ci:1
```

Today VirtuLab works well for projects shaped like [`examples/`](examples). It compiles source globs itself, links its own startup code, and runs on one of 9 hand-written boards in [`boards.py`](virtulab/boards.py). Extra devices are added as raw Renode `.repl` lines ([`examples/thermostat/board.repl`](examples/thermostat/board.repl)). Real teams today start from a vendor IDE (STM32CubeIDE, nRF Connect, MCUXpresso, MPLAB X). They configure pins and clocks in its graphical tool, generate code, build, and flash and debug on the physical chip. That means a different, heavyweight tool per vendor, and nothing works until the board exists. This roadmap replaces that whole workflow, while still accepting existing projects.

> **MVP status.** Built so far: `virtulab.yml` with typo suggestions (1.1, no JSON Schema yet), a catalog of boards, protocols, sensors and tests, `virtulab check` (a first cut of 3.3), `virtulab init` and a local setup page (a first cut of Phase 6 and 3.6), generated CI for GitHub and GitLab, Docker fallback and entry point (1.4, part of 4.3). Not built: bring-your-own-build (1.2), runtime library (1.3), chip IR and importers (Phase 2), pin and clock solver, debug and flash (Phase 4), JUnit XML (Phase 5). Sensor models: TMP108 and BMP180 only. See the README quick start.

### What a vendor IDE does, and what replaces it

| Vendor IDE job | Example | VirtuLab replacement | Roadmap item |
| :--- | :--- | :--- | :--- |
| Pick the chip | CubeMX MCU selector | chip catalog generated from SVD and devicetree | 2.1, 2.2 |
| Configure pins, clocks, peripherals | CubeMX pinout and clock tree views | `board:` spec + pin and clock solver | 3.1, 3.5 |
| Generate init code and project | CubeMX code generator | `virtulab new` / `virtulab generate` | 3.6 |
| Toolchain and build | bundled GCC + Eclipse managed build | Arm GNU toolchain + generated CMake, in the Docker image | 1.2, 3.6 |
| Run without hardware | (not possible) | virtual board on Renode | Phase 2, 3 |
| Debug | ST-Link / J-Link GDB server + Eclipse | `virtulab debug` + VS Code extension (or any GDB client) | 4.1 |
| Flash and debug the real board | CubeProgrammer, nRF Util, vendor GDB servers | `virtulab flash` / `virtulab debug --probe` via probe-rs or OpenOCD | 4.2 |
| Register views | SFR view | SVD-driven peripheral view in the VS Code extension | 4.1 |
| Graphical configuration | CubeMX GUI | visual board editor | Phase 6 |

Phases are ordered by what blocks adoption. Items within a phase can be worked on in parallel unless a dependency is stated.

---

## Principles

These decisions came out of the design discussion. Every phase should respect them.

1. **No vendor IDE, ever.** Every step, from choosing a chip to flashing the real board, works with `virtulab.yml`, the `virtulab` CLI and any editor. Vendor *libraries* (CMSIS, STM32Cube HAL/LL, nrfx, Zephyr) are used freely, because they're open source and that's what production firmware is built on. Vendor *tools* are never required.
2. **Generated projects use standard builds, and existing builds are accepted as they are.** New projects get a plain CMake build (or a Zephyr application) generated from the board spec, with no VirtuLab-specific build system. Existing projects keep their CMake, Make, PlatformIO or Zephyr build, and VirtuLab takes the ELF it produces. Emulation, footprint, symbol diffs, crash mapping and reports all work from the ELF. The glob build stays only as the zero-config path for small projects and demos.
3. **Chips are composed, not listed.** A chip is a CPU core plus a memory map plus instances of peripheral IP blocks plus interrupt wiring. Vendors reuse the same IP block across many parts, for example "STM32 I2C v2" in F0, F3, F7, L4, G0, G4 and H7. VirtuLab models each **IP block once** and builds any chip from data. No hand-maintained chip list.
4. **Reuse what exists for structure. Invest in behavior.** Register maps come from vendor SVD files and Zephyr devicetree, and Renode is the emulation engine. [dts2repl](https://github.com/antmicro/dts2repl) already turns devicetree into Renode platforms. Flashing and probe debugging come from probe-rs and OpenOCD. VirtuLab's value lies in five places: the spec format users edit, project generation, accurate behavior models, the fidelity report, and the CI and debug experience.
5. **Fidelity is always visible.** Every peripheral and module is reported as accurately modeled, approximated or stubbed. A test that passes on a stub must never look like a test that passes on an accurate model.
6. **The user never writes Renode syntax.** `.repl` and `.resc` are generated output. Users edit VirtuLab YAML only.
7. **One description drives everything.** The same `board:` spec generates the init code, the virtual board and the real-board flash and debug configuration. Because pins, clocks and modules are declared once, the code and the emulated hardware can't disagree.
8. **Virtual and real hardware are the same workflow.** `virtulab debug` and `virtulab test` work the same against the virtual board and against a probe-attached real board. Only a flag changes.
9. **One description, every entry point.** The CLI, the GitHub Action, the Docker image, the VS Code extension and the future editor all read the same `virtulab.yml`.

---

## Target architecture

```
                         ┌──────────────── virtulab.yml ────────────────┐
                         │  board: chip + modules + wiring              │
                         │  build: command + elf                        │
                         │  test:  timeout, budgets, scenarios          │
                         └──────────────────────────────────────────────┘
                                  │                         │
  Vendor data                     ▼                         ▼
  ───────────               ┌───────────┐             ┌───────────┐
  SVD / CMSIS-Pack ──┐      │  Chip IR  │             │  Board IR │◄── .ioc / devicetree /
  Zephyr .dtsi ──────┼─────►│  (YAML)   │             │  (YAML)   │    .mex importers
  user overrides ────┘      └─────┬─────┘             └─────┬─────┘
                                  │                         │
  IP model library ───────────────┤   matched by compatible │
   ├─ accurate (C#)               │   string or register    │
   ├─ declarative (YAML DSL)      │   fingerprint           │
   └─ auto stub (from SVD)        ▼                         ▼
                            ┌─────────────────────────────────────┐
  Module library ──────────►│  pin / clock solver + generators    │──► fidelity report
   (sensors, flash, …)      └───────┬─────────────────┬───────────┘    (board check)
                                    │                 │
  vendor libraries                  ▼                 ▼
  (CMSIS, Cube LL/HAL, ──► project: CMake + init   Renode .repl + .resc
   nrfx, Zephyr)            code + linker script         │
                                    │                    │
                                    ▼                    ▼
                                 build ──► ELF ──► emulate ──► report / PR comment
                                              │       │
                                              │       └──► GDB server ─┐
                                              │                        ├──► VS Code extension
                                              └──► probe-rs / OpenOCD ─┘    or any GDB client
                                                   (flash + debug the real board)
```

| Layer | What it is | Source | Effort |
| :--- | :--- | :--- | :--- |
| **Core** | Cortex-M0/M0+/M3/M4F/M7F/M33, RISC-V | Renode | none |
| **Structure** | memory map, peripheral instances, base addresses, IRQ numbers | generated from SVD and devicetree | automatic, thousands of parts |
| **Behavior** | what each IP block does: status bits, IRQs, DMA requests, bus transfers | VirtuLab IP model library | the main ongoing investment, reused across chips |
| **Board** | external modules on buses and pins | `board:` in `virtulab.yml` | per project |

---

## Phase 1: Fit existing projects

Without this phase, most real firmware repositories can't adopt VirtuLab at all. It doesn't depend on the virtual chip work, so it can ship first and still run on today's board list.

### 1.1 Project config file: `virtulab.yml`

One file at the repository root describes the firmware. The CLI, the GitHub Action and the Docker image all read it, so no CI system duplicates settings.

```yaml
board: stm32f4_discovery     # replaced by a full board: section in Phase 3
build:
  command: cmake --preset test && cmake --build build/test
  elf: build/test/firmware_tests.elf
peripherals: board.repl      # deprecated by Phase 3 modules
timeout: 30s
budgets:
  flash_increase: 2K
  ram_increase: 512
```

- Precedence, from lowest to highest: the file, then action inputs or CLI flags.
- Unknown keys are an error, with a "did you mean" suggestion, so typos don't fail silently.
- Several targets in one file (a `targets:` list) map to a board matrix with separate `report_id`s.
- The schema is versioned (`version: 1`) and published as JSON Schema, so editors get completion and validation.
- `virtulab config show` prints the merged, effective configuration and where each value came from.

**Touches:** `cli.py` (new `options_from_file`), new `virtulab/config.py`, `action.yml`, `entrypoint.sh`, README.
**Done when:** the CI setup for both examples is `uses: yann-zurstrassen/virtulab-ci@v1` with no inputs.

### 1.2 Bring your own build

Run the project's build command and take the ELF it produces, instead of compiling globs.

```yaml
build:
  command: cmake --preset test && cmake --build build/test
  elf: build/test/firmware_tests.elf
```

- Footprint, symbol diff, emulation, `addr2line` and the report all work from the ELF unchanged.
- The baseline runs the same command in the exported baseline tree (`baseline.py`).
- Compiler diagnostics are still parsed from the command's output, so annotations keep working. This holds for GCC and Clang. IAR and Keil formats come later.
- **Documented recipes for open build systems:** CMake (plain, and the CMake project CubeMX can export), Make, Zephyr / nRF Connect SDK (`west build -b <board>`), PlatformIO (`pio run -e <env>`).
- The Docker image ships the Arm GNU toolchain, CMake, Ninja and `west`. No vendor IDE goes in the image, and no recipe depends on one.
- Projects that today build only inside a vendor IDE (Eclipse managed build) are migrated rather than supported. `virtulab migrate` (3.7) converts them to CMake.
- The glob build stays as the zero-config option.

**Touches:** `build.py` (new `build_command()` path next to `build()`), `baseline.py`, `cli.py`, `action.yml`, `Dockerfile`, new `docs/builds/`.
**Done when:** `examples/thermostat` builds and passes through a CMake project, including the baseline delta.

### 1.3 Runtime as a library

In bring-your-own-build mode the project keeps its own vector table and startup code, so the runtime needs to split in two:

- **`virtulab_io`:** console, `vl_exit`, `vl_sim`, `vl_fault_report` and the test framework. No vector table, no `Reset_Handler`.
- **`startup.c`:** optional, kept for zero-config projects.

Ship `virtulab_io` as a CMake package (`virtulab::io`), a PlatformIO library, a Zephyr module and plain sources. Document the one-line `HardFault_Handler` hook-up for projects that keep their own handlers.

**Touches:** `virtulab/runtime/`, new `virtulab/runtime/CMakeLists.txt`, `library.json`, `zephyr/module.yml`.
**Done when:** an STM32Cube-generated project with its own `startup_stm32*.s` reports faults and exit codes through VirtuLab.

### 1.4 Honest Docker entry point

On its own, `FROM ghcr.io/yann-zurstrassen/virtulab-ci:1` doesn't run anything. Make the one-liner real for non-GitHub CI:

- The image's default command is `virtulab run`, reading `/src/virtulab.yml`.
- Document `docker run --rm -v "$PWD:/src" ghcr.io/yann-zurstrassen/virtulab-ci:1` as the universal one-liner. Keep `FROM …` + `RUN virtulab run` for teams that build images.
- Update the README header so it doesn't promise a single `FROM` line.

**Touches:** `Dockerfile`, `entrypoint.sh`, README.

---

## Phase 2: Virtual chip platform

This replaces the fixed board list with chips composed from IP blocks. It's the core of the product. 2.1 → 2.2 → 2.3 must land in order. 2.4 to 2.8 can then run in parallel.

### 2.1 Chip IR

VirtuLab's own description of a chip, and the single source of truth for everything downstream. It's generated by importers (2.2) and versioned in `virtulab/chips/`. Users can override it from their project.

```yaml
# virtulab/chips/stm32/stm32f407vg.yml  (generated, then reviewed)
part: STM32F407VG
vendor: ST
family: stm32f4
core: { cpu: cortex-m4f, fpu: fpv4-sp-d16, mpu: true, nvic_prio_bits: 4 }
memory:
  flash: { origin: 0x08000000, size: 1M }
  sram:  { origin: 0x20000000, size: 128K }
  ccm:   { origin: 0x10000000, size: 64K }
peripherals:
  rcc:    { ip: st.rcc.f4,      base: 0x40023800 }
  usart2: { ip: st.usart.v1,    base: 0x40004400, irq: 38 }
  i2c1:   { ip: st.i2c.v1,      base: 0x40005400, irq: [31, 32] }
  spi2:   { ip: st.spi.v1,      base: 0x40003800, irq: 36 }
  gpioa:  { ip: st.gpio.v2,     base: 0x40020000 }
  adc1:   { ip: st.adc.f4,      base: 0x40012000, irq: 18 }
  # …
pins: { package: LQFP100, map: stm32f407vg-pins.yml }   # alternate functions: board check and pin solver
clock_tree: st/stm32f4-clocks.yml                       # sources, PLLs, dividers, limits: clock solver
hal: { cmsis: cmsis-device-f4@<tag>, ll: stm32f4xx-hal-driver@<tag> }  # libraries for generated projects
sources:
  svd: STM32F407.svd@modm-io/cmsis-svd-stm32@<commit>
  dts: zephyr/dts/arm/st/f4/stm32f407.dtsi@<zephyr-tag>
```

- `ip:` names an IP block in the model library (2.4), never a specific chip.
- **Overrides:** a project can patch any field (`chip: { part: STM32F407VG, override: { memory.sram.size: 192K } }`) or point at its own chip file, for custom silicon or vendor errata.
- **Provenance:** every generated file records which SVD or devicetree version and which importer version produced it, so regenerating is reproducible and diffs are reviewable.
- A JSON Schema validates the IR, as for `virtulab.yml`.
- The current `Board` dataclass becomes a thin view over chip IR + board IR. Existing board names stay as aliases (`board: stm32f4_discovery`) so nothing breaks.

**Touches:** new `virtulab/chips/`, new `virtulab/chip.py`, `boards.py` (aliases on top of the IR).

### 2.2 Importers: SVD and devicetree → chip IR

Generate the structure for thousands of parts instead of writing it by hand.

- **SVD importer** (`tools/svd2chip.py`): memory-mapped peripherals, base addresses, register layouts, reset values and IRQ numbers. Use the patched SVD sets ([modm-io/cmsis-svd-stm32](https://github.com/modm-io/cmsis-svd-stm32), stm32-rs, [espressif/svd](https://github.com/espressif/svd)) in preference to raw vendor files, which contain known errors.
- **Devicetree importer** (`tools/dts2chip.py`): reuse Zephyr SoC `.dtsi` files and, where it fits, [dts2repl](https://github.com/antmicro/dts2repl)'s compatible-string mapping. The `compatible` string (`"st,stm32-i2c-v2"`) is the best signal for which IP block a peripheral is.
- **Merge rules:** devicetree provides IP identity and instance names, SVD provides registers and reset values, the CMSIS-Pack device description provides memory sizes per part. Conflicts are reported, never resolved silently.
- **Memory limits come from the exact part**, so "does it fit?" matches the chip being bought, not Renode's sometimes larger map. The current `stm32f4_discovery` entry already does this by hand.
- **Pin and alternate-function tables** come from the vendor's open data where available (STM32 Open Pin Data, nRF product specs). Board check (3.3) and the pin solver (3.5) need them.
- **Clock trees** (oscillators, PLL input and output ranges, multipliers and dividers, bus frequency limits, flash wait states per voltage range) are described once per family from the reference manual, and once per part where limits differ. The clock solver (3.5) needs them. This is the one structure that isn't in SVD and has to be written by hand per family, so budget for it.
- Importers run in CI on a schedule and open a PR when upstream data changes.

**Touches:** new `tools/`, new `virtulab/chips/`, `.github/workflows/` (scheduled import job).
**Done when:** every STM32F4 and STM32L4 part in the SVD set produces a valid chip IR file without manual edits.

### 2.3 Generator: chip IR + board IR → Renode platform

Turns the IR into what Renode runs, replacing the hard-coded `machine LoadPlatformDescription @platforms/…` in `emulator.py`.

- Emits one `.repl` per run into `.virtulab/`, with comments that trace each line back to the IR, plus the `.resc` script that `_renode_script()` builds today.
- Each IP block in the library declares its Renode peripheral type and constructor parameters. The generator only wires instances, addresses and IRQs.
- Unknown IP blocks fall back to the auto stub (2.4), never to a missing address that faults the firmware.
- `virtulab chip show STM32F407VG` prints the composed chip. `virtulab chip export --renode` writes the `.repl` for people who want to inspect it or use it directly in Renode.
- Keep a backend interface, so a QEMU backend can be added for CPU-only fast runs on parts QEMU supports.

**Touches:** new `virtulab/generate.py`, `emulator.py` (take a generated platform instead of `board.platform`).
**Done when:** the existing `stm32f4_discovery` e2e tests, thermostat included, pass on the *generated* STM32F407VG platform instead of Renode's hand-written one. This is the first proof that composed chips can replace hand-written ones, and it should be done as a spike before the rest of Phase 2.

### 2.4 IP model library and identification

The behavior layer, organized by IP block and reused across chips.

```
virtulab/ip/
  st/usart-v1/      model.yml | model.cs   tests/   README.md
  st/i2c-v2/        …
  st/rcc-f4/        …
  nordic/twim/      …
```

- **Three tiers per IP block**, reported as such everywhere:
  - **Accurate:** C# models written from the reference manual, like [`TMP108.cs`](virtulab/devices/TMP108.cs) is for a sensor. Used for complex blocks (DMA, USB, timers) or where timing matters.
  - **Declarative:** written in the YAML DSL (2.5). The default for most blocks.
  - **Auto stub:** generated from SVD. Registers hold reset values and read back what was written. Enough to keep firmware from faulting, not enough to trust its results.
- **Reuse Renode's built-in models** where they're correct. Wrap them as library entries with their tier and known gaps documented, so users get one catalog.
- **Identification:** match a chip's peripheral to an IP block by devicetree `compatible` string first, then by a register-layout fingerprint (register names, offsets, reset values hashed from the SVD). Unmatched peripherals are listed in the fidelity report.
- **Stubs need ready rules.** HAL code polls ready bits (`while (!(RCC->CR & RCC_CR_PLLRDY))`), and a plain register file hangs it forever. Stubs support simple rules such as "after writing `CR.PLLON=1`, `CR.PLLRDY` reads 1", written in the DSL, plus a heuristic default ("`*RDY` and `*RXNE`-style flags read as set after their enable bit is written") that's flagged as approximate.
- Each model ships with tests that check it against the reference-manual register map and documented behavior, and with a list of the chips it covers.

**Touches:** new `virtulab/ip/`, `virtulab/devices/` (merged into the library), `emulator.py` (load C# models on demand, as `VirtuLab.*` devices are today).

### 2.5 Declarative peripheral DSL

The big leverage point. Most peripheral behavior is "on a write to X, set Y and raise an IRQ". If that can be written in YAML instead of C#, new IP blocks take hours instead of days, and users, contributors and (later) datasheet-assisted generation can add them.

```yaml
# virtulab/ip/st/i2c-v1/model.yml
ip: st.i2c.v1
registers: from-svd            # layout and reset values from the chip's SVD
bus: i2c-controller            # connects to modules declared on this bus
behavior:
  - on: write CR1.START = 1
    do: [ set SR1.SB, irq ev ]
  - on: write DR when state = address
    do: [ bus.address(DR >> 1, rw = DR & 1), set SR1.ADDR, irq ev ]
  - on: read SR2
    do: [ clear SR1.ADDR ]
  - on: bus.nack
    do: [ set SR1.AF, irq er ]
state: [ idle, address, transmit, receive ]
```

- Primitives: register and field read/write triggers, set/clear/toggle, a state machine, IRQ raise and clear, DMA request lines, bus transactions (I2C, SPI, UART bytes), timers ("set `SR.TC` after N bytes at the configured baud rate").
- It compiles to a generated Renode C# peripheral, so runtime speed equals hand-written models and no interpreter runs in the emulation loop.
- An escape hatch lets one rule call a C# helper for the hard parts.
- `virtulab ip new st.i2c.v1 --from-svd STM32F407.svd` scaffolds a model with every register present and no behavior, ready to fill in.
- **Later:** extract a draft model from the reference manual's register descriptions with an LLM, then review it by hand and validate it with the HAL tests (2.7). Drafts are always marked as approximate until they pass validation.

**Touches:** new `virtulab/dsl/` (parser, validator, C# code generator), `virtulab/ip/`.
**Done when:** one existing hand-written model is re-expressed in the DSL with identical test results, and one I2C or UART block works across three STM32 families from a single model.

### 2.6 Clock, reset and power controllers first

Firmware blocks on the clock controller before `main()` does anything useful (PLL lock, oscillator ready, flash wait states), and these blocks differ in every family. They're the first model to write for each new family, before any communication peripheral.

- Model RCC (STM32), CLOCK/POWER (nRF), PMC (SAM) and SYSCON (NXP) per family, with the ready flags and the effective clock frequency. Baud-rate and timer models read that frequency.
- Model SysTick and the DWT cycle counter consistently, so `HAL_Delay` and timeouts behave.
- Reset cause registers can be set from `vl_sim`, to test watchdog and brown-out recovery paths.

**Touches:** `virtulab/ip/*/rcc*`, `virtulab/ip/nordic/clock`, …

### 2.7 VirtuLab console device

Replace the per-family UART code in `startup.c` (`VL_CONSOLE_STM32_USART`) with a `VirtuLab.Console` peripheral that the generator adds to every chip. It sits at a fixed reserved address and has a TX register and an exit register.

- The same runtime code then works on every composed chip, with no USART register variants per family. This becomes essential once chips are generated rather than hand-picked.
- Exit becomes a real signal from the peripheral, replacing the `VIRTULAB_EXIT:` sentinel and the 50 ms log polling in `emulator.py`.
- Firmware UARTs stay free for the code under test, and their output is captured separately in the report.

**Touches:** new `virtulab/ip/virtulab/console/`, `startup.c`, `emulator.py`, `generate.py`.

### 2.8 Validation matrix and fidelity report

Proves which chips are actually usable, and tells you which model to write next.

- **The vendor HAL is the test suite.** For every generated chip, build the vendor's own examples (STM32Cube HAL/LL init, nRF SDK and Zephyr samples): clock configuration, GPIO, UART print, I2C and SPI init, timer interrupt. A chip is usable for a level when those examples run to completion.
- **Levels per chip:** `boots` (reaches `main`) → `clocks` (clock tree configures) → `console` (prints) → `peripherals` (communication peripherals pass their samples) → `accurate` (every used block is tier accurate or declarative and validated).
- Run nightly across the catalog and publish the result as a coverage matrix in the docs and as a machine-readable file that `board check` uses.
- **The fidelity report** is part of every run: which blocks the firmware actually touched (traced from bus accesses), and the tier of each. "Your test passed, but `ADC1` is an auto stub" appears in the PR comment.
- Regressions in the matrix fail the VirtuLab release pipeline.

**Touches:** new `tests/matrix/`, `.github/workflows/` (nightly matrix), `report.py` (fidelity section), `emulator.py` (access tracing).
**Done when:** every STM32F4 and STM32L4 part reaches `console`, and the matrix is published.

**Initial family order:** STM32 F4 → L4 → F0/G0 → H7 → nRF52832/nRF52840 (devicetree-first, proves the pipeline isn't STM32-specific) → SAMD21 → ESP32-C3 (RISC-V).

---

## Phase 3: Virtual board and project generation

A team doesn't think "STM32F407". It thinks "STM32L476 at 80 MHz, with a BME280 on I2C1, SPI flash on SPI2 and a debug console on USART2". This phase lets them describe exactly that, check it, emulate it, and **generate the firmware project from it**. That takes over the job of the vendor's configuration tool (CubeMX, MCUXpresso Config Tools, MPLAB Harmony).

### 3.1 Board spec

Replaces `board:` names and raw `.repl` lines with a VirtuLab description. The same spec drives the virtual board, the generated init code and the real-board flash and debug configuration.

```yaml
# virtulab.yml
board:
  chip: STM32L476RG
  clocks:
    sources: { hse: 8MHz, lse: 32.768kHz }
    targets: { sysclk: 80MHz, apb1: 80MHz }        # the solver (3.5) finds PLL settings
  peripherals:                                    # what the firmware uses on the chip
    usart2: { mode: uart, baud: 115200, pins: { tx: PA2, rx: PA3 }, role: console }
    i2c1:   { speed: 400kHz }                     # pins chosen by the solver if omitted
    spi2:   { mode: master, clock: 10MHz }
    adc1:   { channels: [IN5] }
  modules:                                        # what's on the PCB around the chip
    bme280:  { model: bosch.bme280,      bus: i2c1, address: 0x76, int: PB5 }
    flash:   { model: winbond.w25q64,    bus: spi2, cs: PB12 }
    fan:     { model: generic.gpio_out,  pin: PA8 }
    button:  { model: generic.button,    pin: PC13, active: low }
    vbat:    { model: generic.analog,    adc: adc1.IN5, range: 0-3.3V }
  probe: { type: stlink, interface: swd }         # for the real board (4.2)
```

- **`peripherals:`** is the on-chip configuration that CubeMX's pinout and configuration views hold today: mode, speed, pins, DMA and interrupt priorities.
- **`modules:`** are the external parts. They attach to buses (I2C, SPI with chip select, UART), to pins, or to analog inputs (an ADC channel driven from `vl_sim`).
- Module names become the `vl_sim` paths (`vl_sim("bme280 Temperature 31.5")`), so tests don't depend on generated Renode paths like `sysbus.i2c1.tmp108`.
- Dev boards become **board presets**: a chip plus its on-board modules, oscillators and probe (`board: { preset: nucleo-l476rg, modules: {…} }`). That keeps today's board names working.
- Several boards in one file (`targets:`) let one firmware be tested on two hardware revisions.

**Touches:** `virtulab/config.py`, new `virtulab/board.py`, `generate.py`, `cli.py` (deprecate `--peripherals`).

### 3.2 Module library

External parts on the board, organized like the IP library (2.4), with the same tiers.

- **Datasheet-accurate models first** for the most common parts: temperature/humidity/pressure (TMP108, BME280, SHT3x), IMUs (LSM6DSx, MPU-6050, BMI270), SPI NOR flash (W25Q, MX25), EEPROMs (24Cxx), power monitors (INA219/INA226), RTCs (PCF85063, DS3231), and port expanders (MCP23017). Follow the approach in [`TMP108.cs`](virtulab/devices/TMP108.cs).
- **Generic register device:** a module defined by a YAML register table (address width, registers, reset values, fixed or `vl_sim`-driven responses). Enough for a driver to probe and initialize a part that has no model yet, and it can be written in minutes. Always reported as approximate.
- **Generic pin modules:** GPIO output (records level changes with timestamps for assertions), button, open-drain line, PWM capture, analog source.
- Modules can be written in the declarative DSL (2.5) with a device-side bus role (`bus: i2c-target`).
- **Modules can ship a driver.** A module entry can point at an open-source driver (the vendor's reference driver or a Zephyr sensor driver), so project generation (3.6) can include it. Model and driver are tested together.
- Each model ships with a firmware test in `tests/` that checks it against the datasheet register map. Known gaps are listed in the model's README.
- Users can keep project-local modules in their repo (`modules/*.yml`) and contribute them upstream.

**Touches:** `virtulab/devices/` → new `virtulab/modules/`, `tests/`.

### 3.3 `virtulab board check`

Shows the virtual board and its fidelity before anything is generated or emulated. It runs automatically at the start of every CI run and fails early on configuration errors.

```
$ virtulab board check
Chip    STM32L476RG              ✅ console level (stm32l4, nightly matrix)
Clocks  sysclk 80 MHz            ✅ HSE 8 MHz → PLL M=1 N=20 R=2, 4 flash wait states
usart2  PA2/PA3 115200 console   ✅
i2c1    PB6/PB7 400 kHz          ✅ pins chosen by solver
  bme280 @ 0x76                  ✅ datasheet model
spi2    PB13/PB14/PB15 10 MHz    ✅
  w25q64 (cs PB12)               ⚠️  generic register model, no erase timing
adc1    IN5 (PA0)                ✅ vbat analog source
PA8     fan                      ✅ generic GPIO output
```

- **Chip checks:** the part exists in the catalog, its matrix level, and the tier of every IP block the configuration uses.
- **Clock checks:** the requested frequencies are reachable within every PLL and bus limit. If not, the closest achievable value is reported.
- **Wiring checks:** bus address conflicts, pins used twice, chip-select pins that clash with other functions, modules on a bus the chip doesn't have, pins that don't support the requested alternate function (from the pin tables in 2.2).
- **Firmware cross-checks:** after one run, compare the peripherals and pins the firmware actually configured (from access tracing) with what the board declares. This catches hand-edited init code that drifted from the spec.
- Output as text, Markdown (for the PR comment) and JSON (for the editor in Phase 6 and the VS Code extension).

**Touches:** new `virtulab/check.py`, `report.py`, `cli.py`.

### 3.4 Board import (migration input)

Teams moving off a vendor IDE already have a configuration file that knows the chip and most of the wiring. Import it **once**. From then on, `virtulab.yml` is the source of truth and the vendor file can be deleted.

- **STM32CubeMX `.ioc`:** plain `key=value` text with the exact part number, the enabled peripherals and their modes, the pin assignments and the clock configuration. This gives `chip`, `clocks` and `peripherals` almost completely.
- **Zephyr / nRF Connect devicetree and overlays:** sensors are already declared with bus and address (`bme280@76 { compatible = "bosch,bme280"; }`), which maps almost one-to-one onto modules.
- **MCUXpresso `.mex`** and **MPLAB Harmony** configuration: later.
- **PlatformIO `platformio.ini`:** the board gives the chip. Modules are added by hand.
- `virtulab board import firmware.ioc` writes the `board:` section. It marks the external modules the user still has to declare, since vendor files don't know about the PCB.
- The import is checked by regenerating (3.6) and comparing the generated init code's register writes with the vendor-generated code's, traced on the virtual board.

**Touches:** new `virtulab/importers/` (`ioc.py`, `devicetree.py`, `mex.py`), `cli.py`.
**Done when:** the thermostat board is defined only in `virtulab.yml`, and an `.ioc` from a fresh CubeMX project imports into a board that passes `board check` with no edits other than adding the external sensor.

### 3.5 Pin and clock solver

Replaces CubeMX's pinout view and clock tree view. The user states intent, and VirtuLab finds a valid configuration.

- **Pin solver:** assigns pins for every peripheral that doesn't fix them, using the chip's alternate-function tables and package. It respects pins the user fixed, avoids conflicts and reserves the debug pins (SWD). When there's no valid assignment, it explains which constraint blocks it.
- **Clock solver:** given the oscillators on the board and target frequencies (`sysclk`, bus clocks, peripheral clocks such as USB 48 MHz or I2S), it searches the PLL multipliers and dividers within the family's limits (2.2 clock trees). It derives flash wait states and voltage scaling, prefers exact matches, and reports error in ppm when it can't match exactly. That error matters for UART baud rates.
- **Peripheral timing:** computes baud-rate, I2C timing (`TIMINGR` on STM32 I2C v2) and SPI prescaler values from the solved clocks.
- The solved result is written to a lock section (`virtulab.lock.yml`), so it's reviewable in PRs and stable across VirtuLab versions until the user re-solves.
- Shared by `board check` (3.3), project generation (3.6) and the editor (Phase 6).

**Touches:** new `virtulab/solve/` (`pins.py`, `clocks.py`), chip clock-tree data from 2.2.
**Done when:** the solver reproduces CubeMX's clock and pin results for 5 reference configurations across STM32F4 and STM32L4, and its output passes `board check`.

### 3.6 Project generation: `virtulab new` and `virtulab generate`

Replaces the vendor IDE's project wizard and code generator. The output is a standard project that builds with any CMake and needs no VirtuLab at build time.

```
$ virtulab new fan-controller --board nucleo-l476rg
$ tree fan-controller
fan-controller/
  virtulab.yml
  CMakeLists.txt  cmake/arm-none-eabi.cmake
  generated/            ← regenerated from virtulab.yml, never hand-edited
    startup_stm32l476xx.s  stm32l476rg.ld
    clock.c  pins.c  usart2.c  i2c1.c  spi2.c  adc1.c  board.h
  drivers/bme280/       ← from the module library
  src/main.c            ← user code, never touched by the generator
  test/test_main.c
  .github/workflows/virtulab.yml
  .vscode/launch.json  .vscode/extensions.json
```

- **Two backends, chosen per project:**
  - **Bare-metal (default):** CMSIS device headers and the vendor's open-source low-level drivers (STM32Cube LL, nrfx, MCUX SDK drivers), fetched at pinned versions. The generated init code calls them: clock setup from the solver, GPIO alternate functions, peripheral init with the computed timing values. That's equivalent to CubeMX's LL output.
  - **Zephyr:** generates a board definition (devicetree + Kconfig) and an application skeleton. Zephyr is already vendor-neutral, so this backend reuses its drivers and gets many chips quickly.
- **Strict separation of generated and user code.** Generated files live in `generated/` and are rewritten on every `virtulab generate`. User code calls `board_init()` and the generated peripheral handles. This avoids CubeMX's `/* USER CODE BEGIN */` blocks, which are fragile.
- **Generation is checked in CI.** `virtulab generate --check` fails when `generated/` is out of date with `virtulab.yml`, so spec and code can't drift.
- The generated linker script and startup file come from the chip IR (exact memory sizes, vector table from the IRQ list). The VirtuLab runtime is linked as the library from 1.3.
- The generated project includes the CI file and VS Code configuration, so a new project passes CI on its first push.
- **Middleware** (FreeRTOS, USB device stack, FatFS, lwIP, TinyUSB) is added as optional components with pinned versions, later and on demand. This is where CubeMX has the most features, so it's prioritized by what the validation track actually needs.

**Touches:** new `virtulab/project/` (templates, backends, `generate.py`), new `virtulab/vendor_libs/` (pinned library manifests), `cli.py`.
**Done when:** `virtulab new` for a Nucleo-L476RG with a BME280 produces a project that builds with plain CMake, passes its tests on the virtual board, and runs on the real Nucleo board flashed with `virtulab flash` (4.2), with no vendor tool installed.

### 3.7 `virtulab migrate`: leave the vendor IDE

For existing projects built inside a vendor IDE.

1. Import the board from `.ioc`, `.mex` or devicetree (3.4).
2. Convert the Eclipse managed build (`.cproject`: sources, include paths, defines, flags, linker script) into a `CMakeLists.txt`.
3. Move vendor-generated init code into `generated/` and the code inside `USER CODE` blocks into `src/`, reporting anything it couldn't place.
4. Run the old build and the new build, then compare the two ELFs (sections, sizes, symbols) and the register writes during init on the virtual board.
5. Write `virtulab.yml`, the CI file and the VS Code configuration.

**Done when:** two open-source STM32CubeIDE projects from the validation track migrate with an equivalent ELF, and their vendor project files can be deleted.

---

## Phase 4: Editor, debug and real hardware

Teams test by flashing and debugging on the chip. Without a vendor IDE, VirtuLab has to provide that experience against both the virtual board and the real one, from any editor.

### 4.1 Debug on the virtual board

- `virtulab debug` starts the virtual board with Renode's GDB server and halts at reset. Any GDB client can connect.
- **VS Code extension** (`virtulab.virtulab`), the primary editor experience:
  - build, test, debug and flash commands, with test results in the Test Explorer
  - debugging through Cortex-Debug or the built-in debug adapter, with no `launch.json` editing
  - an SVD peripheral register view generated from the chip IR
  - the `board check` view and fidelity tiers
  - a panel to change module values live (`bme280.temperature`) during a debug session
- Other editors (CLion, Neovim, Emacs) use the GDB server and the generated `compile_commands.json` directly.
- `vl_sim` commands can also be sent from the terminal during a session (`virtulab sim bme280 Temperature 40`).
- A failing CI run can be reproduced locally: `virtulab debug --from-report .virtulab/report.json` uses the same ELF, board and scenario.

**Touches:** new `virtulab/debug.py`, `emulator.py` (GDB server option), new `editors/vscode/`, new `docs/editors/`.
**Done when:** a developer sets a breakpoint in VS Code and steps through I2C driver code on the virtual board, with the TMP108 responding and the I2C registers visible in the peripheral view.

### 4.2 Flash and debug the real board

Replaces CubeProgrammer, nRF Util, J-Flash and the vendor GDB servers for day-to-day work.

- `virtulab flash` and `virtulab debug --probe` use [probe-rs](https://probe.rs) (ST-Link, J-Link, CMSIS-DAP, ESP USB-JTAG), with OpenOCD as a fallback for probes or chips probe-rs doesn't cover.
- The flash algorithm and the probe target come from the chip IR (CMSIS-Pack flash algorithms where needed), so no per-chip configuration is required.
- **Same tests, real hardware:** `virtulab test --probe` runs the same test ELF on the real board and reads results over RTT or semihosting, with the same report format. A virtual pass can be confirmed on the bench without changes.
- RTT console and `defmt`-style logging, in the CLI and the VS Code extension.
- **Option bytes, read-out protection, secure boot and TrustZone provisioning** stay explicitly out of the first version. Document which vendor command-line tool to use for them (STM32CubeProgrammer CLI, nRF Util), so the IDE is still never needed.

**Touches:** new `virtulab/probe.py`, `cli.py`, VS Code extension.
**Done when:** the generated Nucleo-L476RG project from 3.6 is flashed, debugged and tested on the real board from VS Code, with no vendor software installed.

### 4.3 `pipx install virtulab` with a Docker backend

- Publish the engine to PyPI. It is stdlib-only, so it has no dependencies.
- When the Arm toolchain, QEMU or Renode are missing from `PATH`, `virtulab run` runs itself inside `ghcr.io/yann-zurstrassen/virtulab-ci` with the project mounted. Developers keep their OS and editor and need only Docker.
- Local runs and CI use the same image, so a local pass means a CI pass.
- `virtulab debug` (4.1) forwards the GDB port out of the container. `virtulab flash` (4.2) runs on the host, because USB probes don't pass reliably into containers on macOS and Windows.
- The VS Code extension installs the CLI and pulls the image on first use, so a new developer goes from nothing to debugging in one step.

**Touches:** new `pyproject.toml`, `cli.py` (container re-exec), `release.yml` (PyPI and VS Code Marketplace publish jobs).

### 4.4 `virtulab init`

The entry point for any existing repository.

1. Detect the build system: `CMakeLists.txt`, `platformio.ini`, Zephyr `prj.conf`, `Makefile`, or vendor IDE project files (`.cproject`, `.ioc`, `.mex`).
2. If a vendor IDE project is found, offer `virtulab migrate` (3.7).
3. Otherwise detect the chip and board: PlatformIO `board`, the Zephyr board, or `-mcpu` and device defines. Write a `board:` section.
4. Run `board check` and show what's emulated, approximated and missing.
5. Write `virtulab.yml`, the CI file for the detected host (`.github/workflows/virtulab.yml` or `.gitlab-ci.yml`) and the VS Code configuration.
6. Run once and print the report.

**Done when:** a fresh PlatformIO STM32 project and a fresh CubeIDE project each go from `virtulab init` to a passing CI run, and the CubeIDE one no longer needs CubeIDE.

---

## Phase 5: Every CI, not just GitHub

- **JUnit XML** report next to `report.md`, so GitLab, Jenkins and Azure DevOps show test results natively. Add per-test timing.
- **GitLab CI/CD component:** `include: component: …/virtulab@1`, with MR comments through the GitLab API alongside `github.py`.
- **Footprint history** across `main`, with trend charts in the report.
- **Scenario files:** change module values on a timeline without writing C, by driving `vl_sim` commands from YAML, using module names from the board spec.

  ```yaml
  scenarios:
    overheat:
      - at: 0ms,   set: { bme280.temperature: 25 }
      - at: 500ms, set: { bme280.temperature: 85 }
      - expect: { fan: high, within: 100ms }
  ```

- **Hardware-in-the-loop runners:** a self-hosted runner with probe-attached boards runs `virtulab test --probe` (4.2) on the same tests, so a team can gate releases on a bench run without a separate setup.

---

## Phase 6: Visual board editor

The graphical replacement for CubeMX. Once the chip IR, the board IR, the solver and the `board check` JSON have settled, the editor is a UI over them. It is not a separate source of truth.

- Pick a chip from the catalog, with its validation level, memory, price-relevant package options and pinout shown.
- **Pinout view:** click a pin to assign a function, or let the solver (3.5) place peripherals. Conflicts and unsupported alternate functions are shown live, from the same checks as 3.3.
- **Clock view:** the family's clock tree with solved values. Set a target frequency and watch the solver update the PLLs.
- **Board view:** drag modules onto buses and pins, with each block's fidelity tier shown.
- Edits write `virtulab.yml` and run `virtulab generate`. The YAML in the repo stays authoritative and diff-reviewable.
- Run a scenario and watch module values and pin levels over time.
- Ships inside the VS Code extension first (webview), then as a local web UI (`virtulab board edit`), then as a hosted page linked from the PR report.

---

## Validation track (runs alongside all phases)

Onboard 3–5 real open-source firmware repositories, at least one of each, and take each one to "no vendor IDE needed":

| Starting point | Stack | Exercises |
| :--- | :--- | :--- |
| STM32CubeIDE (`.ioc` + `.cproject`) | STM32 HAL, Cube-generated | 3.4 import, 3.7 migrate, 2.6 RCC, 4.2 flash |
| PlatformIO | Arduino or bare STM32 | 1.2, 4.4 |
| Zephyr / nRF Connect | west, nRF52, devicetree sensors | 2.2 devicetree importer, 3.4 devicetree import, 3.6 Zephyr backend |
| Make | CMSIS, no vendor HAL | 1.2, 2.3 generated chip |
| New project from scratch | `virtulab new`, Nucleo-L476RG + BME280 | 3.5 solver, 3.6 generation, 4.1, 4.2 on the real board |

Record every point where a step needs a manual workaround, a missing model or a vendor tool, and feed it back into the phases above. A phase is complete only when the relevant reference projects run without workarounds. Missing models found here set the priority order for 2.4 and 3.2. Any remaining need for a vendor tool is a bug.

---

## Risks and open questions

| Risk | Mitigation |
| :--- | :--- |
| Behavior models are the long tail: a chip "boots" but its peripherals are wrong. | The tier system and fidelity report (2.4, 2.8) make it visible. Models are prioritized by the validation track and the nightly matrix. |
| Clock controllers differ per family and block everything. | Model them first for each family (2.6). Ready-rule stubs as a stopgap. |
| Replacing CubeMX is large: clock trees, pin muxing and middleware per family. | Clock trees are hand-written data per family (2.2), so one family at a time. Lean on the Zephyr backend for breadth. Add middleware only on demand. |
| Clock tree data isn't in SVD and is error-prone to transcribe. | Validate the solver against CubeMX results (3.5) and against register traces of vendor-generated init code on the virtual board. |
| Teams trust vendor-generated init code more than a newcomer's. | Generate code on the vendor's own LL drivers, compare register writes with vendor-generated code (3.4, 3.7), and keep generated code readable and checked in. |
| SVD files contain errors. | Prefer patched community sets, record provenance, allow per-project overrides (2.1, 2.2). |
| DMA, timing and interrupt latency are hard to model accurately. | Accurate C# models for those blocks. Document what isn't cycle-accurate. Real-board runs through `virtulab test --probe` (4.2) for timing-critical tests. |
| A user's sensor has no model. | Generic register device (3.2) gets drivers through init. Project-local modules can be contributed upstream. |
| Vendor library licenses differ (BSD-3 for STM32Cube and nrfx, others vary). | Fetch libraries at build time from their upstream repositories, never vendor them into VirtuLab. Check each license before adding a family. |
| Security provisioning (option bytes, secure boot, TrustZone) still needs vendor tools. | Out of scope for the first version. Document the vendor command-line tool (4.2), never the IDE. |
| Probe access from Docker on macOS and Windows. | Flash and probe debugging run on the host (4.3). Only build and emulation run in the container. |
| Dependence on Renode internals. | Generate `.repl` and models through one generator (2.3) and one DSL compiler (2.5), so engine changes are absorbed in one place. Keep the backend interface. |
| Overlap with Antmicro's dashboard and dts2repl, and with PlatformIO and Zephyr for project setup. | Reuse them and contribute fixes upstream. VirtuLab's differentiation is one hardware description driving generation, emulation, fidelity reporting, CI and real-board testing. |

## Non-goals

- Requiring any vendor IDE or vendor configuration tool, at any step.
- Writing new HALs. Generated code uses the vendors' open-source low-level drivers or Zephyr.
- A proprietary build system. Generated projects are plain CMake or Zephyr applications that build without VirtuLab.
- Writing a new CPU emulator. Renode and QEMU are the engines.
- Hand-maintaining a list of chips. Every chip is generated from data plus IP models.
- Cycle-accurate or analog-accurate simulation. Physical boards remain the final qualification step, through `virtulab test --probe`.
