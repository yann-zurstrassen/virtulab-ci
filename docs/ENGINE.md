# 🔧 Engine reference

Moved here from the previous README so nothing is lost. It documents the GitHub Action and CLI engine
(`virtulab/`), not the security checks, which live in the [`Makefile`](../Makefile) and the
[README](../README.md).

> **Verification status of this page.** The QEMU boards and the CRC example were re-run in this work
> (`docs/runs/engine-tests.txt`: 45 tests, 4 skipped). Everything that needs **Renode** (the `thermostat`
> example, `vl_sim()`, the `VirtuLab.TMP108` device library and its comparison with Renode's built-in model)
> is 🚧 **not re-run**: Renode is not installed on the machine used for this work.

## 🛠️ Quick start

**1. Write tests that run on the target** (`test/test_crc.c`):

```c
#include "crc.h"
#include "virtulab_test.h"

static void test_crc32_check_value(void)
{
    TEST_ASSERT_EQUAL_HEX32(0xCBF43926, crc32("123456789", 9));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_crc32_check_value);
    return UNITY_END();   // number of failures becomes the CI exit code
}
```

You don't need a vector table, startup code or linker script. VirtuLab provides them for the selected board, and `printf()` works.

**2. Add the workflow** (`.github/workflows/firmware-ci.yml`):

```yaml
name: Firmware CI

on:
  push:
    branches: [ main ]
  pull_request:

permissions:
  contents: read
  pull-requests: write   # for the sticky PR comment

jobs:
  emulate-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: yann-zurstrassen/virtulab-ci@v1
        with:
          board: lm3s6965evb
          sources: |
            src/**/*.c
            test/*.c
          include_dirs: include
          max_flash_increase: 2K   # optional budget
```

That's the whole setup. The baseline defaults to the PR base commit (or the previous commit on push) and is fetched automatically, even from a shallow checkout.

### Inputs

| Input | Default | Description |
| :--- | :--- | :--- |
| `board` | `lm3s6965evb` | Target board, see below |
| `sources` | `**/*.c` | Files or globs (C, C++, assembly), separated by spaces or newlines |
| `include_dirs` | | Include directories |
| `cflags` / `ldflags` | | Extra compiler / linker flags (defaults: `-Os -Wall -Wextra`) |
| `linker_script` | generated | Custom linker script |
| `runtime` | `true` | `false` to bring your own vector table and startup ([example](../examples/bare-metal)) |
| `peripherals` | | Extra devices on a Renode board: a `.repl` file or inline lines |
| `timeout` | `30s` | Emulation timeout (`500ms`, `30s`, `2m`) |
| `baseline_ref` | PR base | Git ref to compare the footprint against |
| `max_flash_increase` / `max_ram_increase` | | Fail when growth vs the baseline exceeds this (`512`, `4K`) |
| `working_directory` | `.` | Project directory inside the repo |
| `comment` | `true` | Post or update the sticky PR comment |
| `report_id` | `default` | Keeps comments separate when running a board matrix |

### Outputs

`status` (`passed` · `failed` · `crashed` · `timeout` · `build_failed` · `budget_exceeded`), `flash_bytes`, `ram_bytes`, `flash_delta`, `ram_delta`, `tests_total`, `tests_passed`, `tests_failed`, `emulation_seconds`, `report_path`.

---

## 🔌 Test drivers against virtual hardware

[`examples/thermostat`](../examples/thermostat) is an EV-charger fan controller for an STM32F407. It's written for real silicon: RCC clocks, pin alternate functions, and an I2C driver for a TI TMP108 temperature sensor. It runs on an emulated STM32F4 Discovery with a TMP108 on I2C1.

Declare the devices on your board (`board.repl`):

```
tmp108: VirtuLab.TMP108 @ i2c1 0x48
```

Then set the physical conditions from your tests:

```c
static void test_fan_hysteresis(void)
{
    vl_sim("sysbus.i2c1.tmp108 Temperature 30.5");
    thermostat_step(&thermostat);
    TEST_ASSERT_TRUE(fan_is_on());          // reads the PD12 GPIO output

    vl_sim("sysbus.i2c1.tmp108 Temperature 29.0");
    thermostat_step(&thermostat);
    TEST_ASSERT_TRUE(fan_is_on());          // between thresholds: keep running

    vl_sim("sysbus.i2c1.tmp108 Temperature 27.5");
    thermostat_step(&thermostat);
    TEST_ASSERT_FALSE(fan_is_on());
}
```

```sh
virtulab run -b stm32f4_discovery -s 'src/*.c' 'test/*.c' -I include -p board.repl
```

`vl_sim()` runs any Renode monitor command and returns 1 when the emulator accepted it. The firmware pauses until the command has been applied, so there are no races. Every command appears in the PR report. On QEMU boards it returns 0.

### 📚 The VirtuLab device library

Emulator peripheral models are often incomplete. Renode's built-in `Sensors.TMP108` is actually a TMP103 stub: one 8-bit register with 1 °C resolution. A driver written against the TMP108 datasheet reads 21.5 °C back as 21.06 °C from it. That's a false failure, and on real hardware the driver would be right.

`VirtuLab.TMP108` ([`virtulab/devices/TMP108.cs`](../virtulab/devices/TMP108.cs)) follows the datasheet: 16-bit registers, MSB first, 12-bit two's complement at 0.0625 °C. It is compiled into Renode automatically when a peripherals file references a `VirtuLab.*` device. Growing this library is the plan for closing gaps in the stock emulator models.

---

## 🐳 Use it anywhere (one line)

The image contains everything: the Arm GCC toolchain, QEMU, Renode, the device library and the engine. Your CI only needs Docker.

**In a Dockerfile.** Tests run during `docker build`, and a failing test fails the build:

```dockerfile
FROM ghcr.io/yann-zurstrassen/virtulab-ci:1
COPY . /workspace
RUN virtulab run -b stm32f4_discovery -s 'src/*.c' 'test/*.c' -I include -p board.repl
```

**GitLab CI:**

```yaml
firmware-tests:
  image:
    name: ghcr.io/yann-zurstrassen/virtulab-ci:1
    entrypoint: [""]
  script:
    - virtulab run -b stm32f4_discovery -s 'src/*.c' 'test/*.c' -I include -p board.repl
        --baseline "origin/$CI_DEFAULT_BRANCH"
  artifacts:
    when: always
    paths: [.virtulab/report.md]
```

**Any shell (Jenkins, Buildkite, your laptop):**

```sh
docker run --rm -v "$PWD:/workspace" ghcr.io/yann-zurstrassen/virtulab-ci:1 \
  run -b stm32f4_discovery -s 'src/*.c' 'test/*.c' -I include -p board.repl
```

GitHub additionally gets inline annotations, step outputs and the sticky PR comment. Other CI systems get the console report, the exit code and `.virtulab/report.md`.

**Without Docker:** install Python ≥ 3.10, the [Arm GNU toolchain](https://developer.arm.com/downloads/-/arm-gnu-toolchain-downloads), QEMU and [Renode](https://renode.io), then run `python3 -m virtulab run …` from this repository.

## 🎯 Supported boards

| Board | Emulator | CPU | Flash | RAM | Device |
| --- | --- | --- | ---: | ---: | --- |
| `stm32f4_discovery` | **Renode** (peripherals) | Cortex-M4F | 1 MiB | 128 KiB | ST STM32F407VG |
| `lm3s6965evb` | QEMU | Cortex-M3 | 256 KiB | 64 KiB | TI Stellaris LM3S6965 |
| `lm3s811evb` | QEMU | Cortex-M3 | 64 KiB | 8 KiB | TI Stellaris LM3S811 |
| `stm32vldiscovery` | QEMU | Cortex-M3 | 128 KiB | 8 KiB | ST STM32F100RB |
| `netduinoplus2` | QEMU | Cortex-M4F | 1 MiB | 128 KiB | ST STM32F405RG |
| `microbit` | QEMU | Cortex-M0 | 256 KiB | 16 KiB | Nordic nRF51822 |
| `mps2-an385` | QEMU | Cortex-M3 | 4 MiB | 4 MiB | Arm MPS2 AN385 |
| `mps2-an386` | QEMU | Cortex-M4F | 4 MiB | 4 MiB | Arm MPS2 AN386 |
| `mps2-an500` | QEMU | Cortex-M7F | 4 MiB | 128 KiB | Arm MPS2 AN500 |

Flash and RAM limits are the real chip's, so "does it fit?" answers match the part you'd buy. Every board runs the test suite in CI. QEMU boards emulate the CPU and memory map, but few peripherals, so use them for logic. Use Renode boards for drivers. Neither emulator models exact timing or analog behaviour; that's what the physical bench is still for.

---

## ⚙️ How it works

```
┌──────────────────────────── VirtuLab action container ────────────────────────────┐
│                                                                                   │
│  1. Build                 2. Footprint               3. Emulate                   │
│  arm-none-eabi-gcc  ──▶   size / nm, and the  ──▶    Renode: SoC + your devices   │
│  + VirtuLab runtime       same build at the          (UART console, vl_sim hook)  │
│  + generated .ld          baseline commit            QEMU: semihosting, CPU only  │
│                                                                                   │
└───────────────────────────────────────┬───────────────────────────────────────────┘
                                        ▼
               annotations · step outputs · job summary · sticky PR comment
```

The runtime (`virtulab/runtime/`) is linked into every image. It contains the vector table, `.data`/`.bss` init, FPU enable, C++ static constructors, semihosting-backed `printf`, `exit` via `SYS_EXIT_EXTENDED`, and fault handlers that print the stacked PC. All handlers are weak, so you can override `SysTick_Handler` and the rest.

## 🗺️ Roadmap

Next up is fitting existing projects as they are: run your own CMake, Make, PlatformIO or Zephyr build, keep your startup code, and describe the firmware once in `virtulab.yml`. After that, target any chip by part number, `pipx install virtulab` with a Docker backend, `virtulab init`, and JUnit and GitLab support. See [ROADMAP.md](../ROADMAP.md) for the phases and what "done" means for each.

## 🧑‍💻 Development

```sh
python3 -m unittest discover -s tests -t .   # e2e tests run when the toolchain, QEMU and Renode are on PATH
docker build -t virtulab . && docker run --rm -v "$PWD:/src" -w /src --entrypoint python3 virtulab -m unittest discover -s tests -t .
```

**Releasing:** push a `vX.Y.Z` tag to publish `ghcr.io/yann-zurstrassen/virtulab-ci` for amd64 and arm64 as `:X.Y.Z`, `:X.Y` and `:X` (`.github/workflows/release.yml`). Then move the `vX` git tag (`git tag -f v1 && git push -f origin v1`) so `uses: …@v1` picks up the release. `action.yml` runs the published `:1` image, while this repository's CI builds and tests the image from each commit.
