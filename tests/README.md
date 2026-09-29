# 🚀 VirtuLab CI — Demo Repository

> **"Vercel for Firmware"** — Automated QEMU/Renode Emulation, Binary Memory Analytics, and Inline Unit Test Parsing directly inside GitHub Pull Requests.

VirtuLab CI replaces slow, manual physical HIL (Hardware-in-the-Loop) bench testing with instant virtual microcontroller emulation in the cloud. Every commit compiles bare-metal C/C++, boots the binary inside a virtual CPU, parses unit test assertions, tracks RAM/Flash footprint changes, and posts actionable feedback directly to your Pull Request in **less than 5 seconds**.

---

## 📸 See It In Action (Live PR Showcase)

Experience how VirtuLab CI presents pull request diagnostic reports by checking out our live demo branches:

| Demo Branch / PR | Showcase Target | VirtuLab CI Output |
| --- | --- | --- |
| **[PR #1: Passing Build](https://www.google.com/search?q=https://github.com/virtulab-ci/virtulab-ci-demo/pull/1)** | Clean drivers & unit tests | ✅ All Unity tests pass. Green Flash/RAM footprint delta report. |
| **[PR #2: Memory Regression](https://www.google.com/search?q=https://github.com/virtulab-ci/virtulab-ci-demo/pull/2)** | Large static buffer allocation | ⚠️ **Memory Alert:** `+8192 B Flash` regression flag posted on PR. |
| **[PR #3: Failing Unit Test](https://www.google.com/search?q=https://github.com/virtulab-ci/virtulab-ci-demo/pull/3)** | Broken CRC calculation logic | ❌ Red inline code annotation highlighted directly on the failing code line in PR diff. |

---

## 🤖 Example Pull Request Summary Card

When a developer submits a PR, VirtuLab CI posts a sticky comment summary directly to the discussion thread:

```markdown
### 🤖 VirtuLab CI Diagnostic Report — Target: `lm3s6965evb`

**Status:** ✅ PASSED (Execution Time: `1.84s`)

| Metric | Current | Baseline Delta (`main`) | Status |
| :--- | :--- | :--- | :--- |
| **Flash (ROM)** | `6,340 B` | `+128 B` | ⚠️ Incremental Increase |
| **RAM** | `2,172 B` | `+0 B` | ✅ Normal |
| **Unit Tests** | `3 / 3` | — | ✅ All Assertions Passed |

<details>
<summary>🔍 View QEMU Execution Output Log</summary>

Running Flash Storage Driver Tests...
  [PASS] test_flash_init_and_erase
  [PASS] test_flash_write_and_read
  [PASS] test_flash_boundary_checks
All Flash Storage Driver tests executed successfully!
</details>

```

---

## 🔥 Key Features

* **⚡ Instant Virtual Execution:** Emulates ARM Cortex-M (M0/M3/M4/M7) and RISC-V targets inside QEMU and Renode without waiting for physical hardware availability.
* **📊 Memory Footprint Regression Tracking:** Automatically measures Flash (Text + Data) and RAM (Data + BSS) metrics on every build and calculates relative deltas against `main`.
* **❌ Native Line Annotations:** Automatically parses Unity/CUnit assertion failures and marks the exact line of C code that broke directly on the GitHub diff view.
* **🛡️ Deterministic Semihosting Shutdown:** Utilizes ARM semihosting syscall traps (`bkpt 0xab`) to pass hardware exit codes back to CI cleanly with zero hung processes.
* **🤖 PR Comment Bot:** Keeps code discussions clean by updating a single sticky comment per PR with memory usage graphs and execution statistics.

---

## ⚙️ How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            GitHub Actions Runner                            │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     VirtuLab Docker Engine Container                  │  │
│  │                                                                       │  │
│  │  1. Toolchain        2. Footprint Engine         3. Target Emulator   │  │
│  │ ┌─────────────────┐  ┌───────────────────────┐  ┌──────────────────┐  │  │
│  │ │ arm-none-eabi-  │  │ arm-none-eabi-size    │  │ qemu-system-arm  │  │  │
│  │ │ gcc             │  │ Delta Parser          │  │ / Antmicro Renode│  │  │
│  │ └────────┬────────┘  └───────────┬───────────┘  └────────┬─────────┘  │  │
│  └──────────┼───────────────────────┼───────────────────────┼────────────┘  │
│             ▼                       ▼                       ▼               │
│      [ firmware.elf ] ---> [ Memory Baseline ] ---> [ Semihosting Exit ]    │
│                                                              │              │
└──────────────────────────────────────────────────────────────┼──────────────┘
                                                               ▼
                                               [ GitHub PR Sticky Report ]

```

---

## 🛠️ Quick Start Integration

Add VirtuLab CI to your project in 10 seconds by adding `.github/workflows/firmware-ci.yml`:

```yaml
name: VirtuLab Firmware CI

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  emulate-and-test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Run VirtuLab CI Engine
        id: virtulab
        uses: virtulab-ci/virtulab-ci-action@v1
        with:
          board: 'lm3s6965evb'         # Target hardware board
          source_file: 'test_main.c'   # Main entry point or test runner
          linker_script: 'layout.ld'   # Custom linker script
          timeout: '30s'               # Execution safety timeout

      - name: Post PR Summary Comment
        if: github.event_name == 'pull_request' && always()
        uses: marocchino/sticky-pull-request-comment@v2
        with:
          header: virtulab-ci-report
          message: |
            ### 🤖 VirtuLab CI Diagnostic Report
            * **Flash:** `${{ steps.virtulab.outputs.flash_bytes }} B` (`${{ steps.virtulab.outputs.flash_delta }} B`)
            * **RAM:** `${{ steps.virtulab.outputs.ram_bytes }} B` (`${{ steps.virtulab.outputs.ram_delta }} B`)
            * **Tests:** `${{ steps.virtulab.outputs.tests_passed }}/${{ steps.virtulab.outputs.tests_total }} Passed`

```

---

## 🎯 Supported Hardware Architectures

| Target Board | Architecture | CPU | Emulator |
| --- | --- | --- | --- |
| `lm3s6965evb` | ARM Cortex-M3 | Stellaris LM3S6965 | QEMU |
| `stm32f4_discovery` | ARM Cortex-M4F | STM32F407VG | QEMU / Renode |
| `mps2-an500` | ARM Cortex-M7 | ARM MPS2 | QEMU |
| `nrf52840` | ARM Cortex-M4F | Nordic nRF52840 | Renode |
| `esp32c3` | RISC-V 32-bit | ESP32-C3 | QEMU |

---

## 🤝 Bring VirtuLab CI to Your Firmware Team

Interested in reducing physical bench testing bottlenecks, stopping firmware bloat, and accelerating PR review cycles for your embedded team?

* 🌐 **Website:** [virtulab.io](https://www.google.com/search?q=https://virtulab.io) *(Demo)*
* 📅 **Book a 15-Minute Preview Call:** [calendly.com/virtulab-ci/demo](https://calendly.com)
* ✉️ **Contact Us:** [sales@virtulab.io](https://www.google.com/search?q=mailto%3Asales%40virtulab.io)

---
