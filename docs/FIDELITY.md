# 🔬 Fidelity: what the emulator models, and what it does not

Emulation here is the fast layer of the test pyramid. It finds logic, memory-safety and
fault-handling bugs early. It does not replace hardware-in-the-loop (HIL) or bench qualification.
See [WHERE_EMULATION_STOPS.md](WHERE_EMULATION_STOPS.md).

How to read the status columns:

| Status | Meaning here |
| :--- | :--- |
| **modeled** | QEMU instantiates a device model for it (see the raw dump below) |
| **stubbed** | QEMU maps the address range as an `unimplemented-device`: no behaviour, accesses are only logged |
| **not modeled** | No device in the machine's memory map |

"Exercised" is a separate question: whether *this repo's tests* touch it. Modeled but not exercised means
the emulator could run it, and nothing here checks it.

## Target: `lm3s6965evb` (QEMU 11.1.1, Cortex-M3)

Source of truth: [`qemu-lm3s6965evb-devices.txt`](qemu-lm3s6965evb-devices.txt), captured with
`info qtree` and `info mtree` from `qemu-system-arm -M lm3s6965evb`. Nothing in this table was
filled in from memory of the datasheet.

| Block | Address (QEMU map) | Status | Exercised by this repo's tests |
| :--- | :--- | :--- | :--- |
| Cortex-M3 core, NVIC, SysTick | core | modeled | core and vector table: yes. NVIC priorities, SysTick: no |
| Flash (256 KiB) | `0x00000000` | modeled as **ROM** | read/execute only. Writes are not exercised |
| SRAM (64 KiB) | `0x20000000` | modeled | yes |
| Semihosting console and exit | n/a (host call) | modeled by QEMU, not a chip peripheral | yes: all test output and the exit code |
| System control (`ssys`, SYSCLK 12.5 MHz) | `0x400FE000` | modeled | no |
| GPIO ports A to G (7× PL061) | `0x40004000`… | modeled | no |
| UART0 to UART2 (3× PL011) | `0x4000C000`… | modeled | no (output goes through semihosting, not a UART) |
| SSI (PL022) with an OLED and SD model attached | `0x40008000` | modeled | no |
| I2C0, I2C1 | `0x40020000`… | modeled | no |
| General-purpose timers (4×) | `0x40030000`… | modeled | no |
| ADC | `0x40038000` | modeled | no |
| Watchdog | `0x40000000` | modeled | no |
| Ethernet MAC | `0x40048000` | modeled | no |
| PWM, QEI0, QEI1, analogue comparator | `0x40028000`… | **stubbed** | no |
| Hibernation module, flash controller | `0x400FC000`, `0x400FD000` | **stubbed** | no |
| DMA controller | none in the map | not modeled | no |
| External sensors on a bus | none | not modeled by QEMU | see "Sensor models" below |

### Sensor models

The sensor in this demo is **not** a QEMU device. It is a software model behind a small HAL
(`include/sensor_hal.h`), selected at link time by `targets/sensor_<name>.cfg`
(`make test SENSOR=faulty`). That makes the swap deterministic and cheap, but it means the I2C driver,
bus timing and electrical behaviour are **not** tested by this path. A true bus-level sensor model
needs an emulator that can attach devices (the repository's Renode path does this for the
`stm32f4_discovery` target, see below).

## Other targets in this repository

| Target | Emulator | Status in this work |
| :--- | :--- | :--- |
| `lm3s6965evb` | QEMU | Runs here. Assessed above |
| `stm32f4_discovery` (+ TMP108 on I2C) | Renode | `examples/thermostat`. 🚧 **Not verified here**: Renode is not installed on the machine this was written on, so its peripheral status is not assessed |
| `lm3s811evb`, `stm32vldiscovery`, `netduinoplus2`, `microbit`, `mps2-*` | QEMU | Listed by the engine and covered by its end-to-end tests in CI. 🚧 **Not assessed** for fidelity here |

## Known divergences from real hardware

These hold for emulators in general and for this setup in particular. None of them is measured by this repo.

| Area | What differs | Consequence |
| :--- | :--- | :--- |
| **Timing** | QEMU executes instructions, not clock cycles. There are no flash wait states, bus arbitration or cache effects | Cycle counts, WCET and timeout margins cannot be validated. Real-time deadlines need hardware |
| **Interrupt latency and jitter** | No cycle-accurate exception entry, tail-chaining or pipeline effects | Race conditions that depend on exact interrupt timing may not reproduce |
| **Flash** | The flash region is ROM in this machine. There is no erase/program timing, no wear, no write-protect or ECC behaviour | Bootloader, EEPROM-emulation and flash-wear logic cannot be validated |
| **Clock tree and power** | The system controller reports a fixed 12.5 MHz SYSCLK. PLL lock, brown-out, sleep modes and wake-up times are not realistic | Clock-dependent peripherals (baud rates, ADC sample rates) and low-power paths need hardware |
| **DMA contention** | No DMA controller in this machine | Bus contention and DMA/CPU races are invisible |
| **Peripheral errata and analog behaviour** | Models follow the documented register interface, not silicon errata, noise, or electrical limits | Sensor drift, ADC noise, signal integrity and EMC are out of scope |
| **Fault injection** | The skip sweep removes one instruction in software. A physical glitch can flip bits, corrupt multiple instructions, or hit the pipeline differently | A clean sweep is evidence, not proof. See below |
| **Fuzzing** | `make fuzz` runs the parser on the host with sanitizers. Host word size, alignment and libc differ from the target | It finds logic and memory bugs in the parser code, not target-specific ones |

## Validate on real hardware

Run these on the physical part before relying on any result from emulation:

1. **Anything timing-dependent:** interrupt deadlines, watchdog margins, communication timeouts. Measure with a logic analyser or the cycle counter.
2. **Peripheral drivers:** repeat the driver tests on the real bus with the real sensor. Compare register values, not only pass/fail.
3. **Flash, bootloader and update paths:** erase, program, power-fail in the middle of a write.
4. **Fault-injection findings:** treat each bypass found in emulation as a real finding. Treat "no bypass found" as "not found by a single-skip model". Repeat on the target with a glitching tool if the product needs an assurance level that demands it.
5. **Safety and security evidence:** use coverage and fuzz results as inputs to the evidence package, not as the package. Standards-based claims (for example MC/DC) are only valid if measured with a qualified tool. This repo measures **line and branch coverage only**.

When an emulator result and a bench result disagree, the bench is right and the model needs a fix. That
is the purpose of keeping HIL as the final gate.
